"""화랑 Grid 에이전트 메인

모든 모듈을 설정에 따라 시작/관리.
마스터 서버와 통신하며 HFL 연합 학습에 자동 참여.

전체 순환:
  1. 마스터에 등록 (GPU 정보, 티어)
  2. 30초마다 하트비트 (상태 + 새 명령 수신)
  3. 학습 라운드 참여 → 로컬 LoRA 학습 → 마스터 업로드
  4. 새 통합 LoRA 자동 다운로드
  5. 코인 리워드 적립

사용법:
    # 기본 실행
    python agent_main.py

    # 프리셋으로 실행
    python agent_main.py --preset full

    # 설정 보기
    python agent_main.py --show-config

    # 데몬 모드 (백그라운드)
    python agent_main.py --daemon
"""

import argparse
import logging
import signal
import sys
import time
import threading
import os
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-12s] %(levelname)-7s %(message)s",
)
logger = logging.getLogger("hwarang-agent")

# 설정
from config.agent_config import (
    AgentConfig, preset_minimal, preset_full,
    preset_learning_focused, preset_night_only,
)

# 모듈들
from modules.data_crawler import DataCrawlerModule
from modules.benchmark_runner import BenchmarkModule
from modules.rag_indexer import RAGIndexerModule
from modules.system_monitor import SystemMonitorModule
from modules.ab_tester import ABTestModule
from modules.response_cache import ResponseCacheModule
from modules.safety_filter import SafetyFilterModule
from modules.reward_verifier import RewardVerifierModule
from modules.auto_updater import AutoUpdaterModule
from modules.translator import TranslatorModule
from modules.local_finetune import LocalFinetuneModule
from modules.sleep_learning import SleepLearningModule


class HwarangAgent:
    """화랑 Grid 에이전트.

    설정에 따라 모듈을 시작하고, 마스터와 통신.
    HFL 연합 학습에 자동 참여하여 생태계에 기여.
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.running = False
        self.modules: dict[str, object] = {}
        self.threads: list[threading.Thread] = []

        # HFL 상태
        self.master_url = config.network.master_url
        self.agent_id = config.agent_id
        self.current_lora_version = 0
        self.hfl_active = False  # 현재 학습 중인지
        self._http_client = None

        self._init_modules()

    def _get_http(self):
        """HTTP 클라이언트 (lazy init)."""
        if self._http_client is None:
            try:
                import httpx
                self._http_client = httpx.Client(timeout=30)
            except ImportError:
                logger.warning("httpx 없음 → 마스터 통신 비활성")
        return self._http_client

    def _init_modules(self):
        """활성화된 모듈 초기화."""
        mc = self.config.modules

        if mc.crawling.enabled:
            self.modules["crawling"] = DataCrawlerModule(mc.crawling)
        if mc.benchmark.enabled:
            self.modules["benchmark"] = BenchmarkModule(mc.benchmark)
        if mc.rag.enabled:
            self.modules["rag"] = RAGIndexerModule(mc.rag)
        if mc.monitoring.enabled:
            self.modules["monitoring"] = SystemMonitorModule(mc.monitoring)
        if mc.ab_test.enabled:
            self.modules["ab_test"] = ABTestModule(mc.ab_test)
        if mc.cache.enabled:
            self.modules["cache"] = ResponseCacheModule(mc.cache)
        if mc.safety.enabled:
            self.modules["safety"] = SafetyFilterModule(mc.safety)
        if mc.reward_verification.enabled:
            self.modules["reward_verification"] = RewardVerifierModule(mc.reward_verification)
        if mc.auto_update.enabled:
            self.modules["auto_update"] = AutoUpdaterModule(mc.auto_update)

        # HFL 관련 모듈 (항상 초기화)
        self.modules["local_finetune"] = LocalFinetuneModule()
        self.modules["sleep_learning"] = SleepLearningModule()

        logger.info(f"초기화된 모듈: {list(self.modules.keys())}")

    def start(self):
        """에이전트 시작."""
        self.running = True

        logger.info("\n" + "=" * 60)
        logger.info(" 🏹 화랑 Grid 에이전트 시작")
        logger.info("=" * 60)
        self.config.print_config()

        # 마스터 등록
        self._register_with_master()

        # 최신 LoRA 다운로드
        self._pull_latest_lora()

        # 모듈별 백그라운드 스레드 시작
        if "monitoring" in self.modules:
            self._start_thread("monitoring", self._run_monitoring)

        if "crawling" in self.modules:
            self._start_thread("crawling", self._run_crawling)

        if "auto_update" in self.modules:
            self._start_thread("auto_update", self._run_auto_update)

        # HFL 학습 루프 (핵심!)
        self._start_thread("hfl_loop", self._run_hfl_loop)

        # 수면 학습 감시
        self._start_thread("sleep_watch", self._run_sleep_watch)

        # 메인 루프 (마스터 통신 + heartbeat)
        self._main_loop()

    def stop(self):
        """에이전트 중지."""
        logger.info("에이전트 종료 중...")
        self.running = False
        if self._http_client:
            self._http_client.close()
        for t in self.threads:
            t.join(timeout=5)
        logger.info("에이전트 종료 완료")

    # ════════════════════════════════════════════════════════════
    # 마스터 통신
    # ════════════════════════════════════════════════════════════

    def _register_with_master(self):
        """마스터 서버에 등록."""
        logger.info(f"마스터 등록: {self.master_url}")

        http = self._get_http()
        if not http:
            logger.warning("HTTP 클라이언트 없음 → 오프라인 모드")
            return

        try:
            gpu_info = self._detect_gpu()
            response = http.post(
                f"{self.master_url}/hfl/register",
                data={
                    "agent_id": self.agent_id,
                    "gpu_name": gpu_info.get("name", "unknown"),
                    "vram_gb": gpu_info.get("vram_gb", 0),
                    "tier": self.config.tier or "lite",
                },
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ 마스터 등록 완료: {self.agent_id}")

                # 현재 LoRA 정보 수신
                if result.get("current_lora"):
                    self.current_lora_version = result["current_lora"].get("version", 0)
                    logger.info(f"   현재 LoRA 버전: v{self.current_lora_version}")
            else:
                logger.error(f"마스터 등록 실패: HTTP {response.status_code}")

        except Exception as e:
            logger.error(f"마스터 연결 실패: {e} → 오프라인 모드로 계속")

    def _send_heartbeat(self) -> dict | None:
        """마스터에 상태 전송 + 명령 수신."""
        http = self._get_http()
        if not http:
            return None

        status = {
            "agent_id": self.agent_id,
            "status": "training" if self.hfl_active else "idle",
            "modules": list(self.modules.keys()),
            "lora_version": self.current_lora_version,
            "timestamp": time.time(),
        }

        if "monitoring" in self.modules:
            metrics = self.modules["monitoring"].collect_metrics()
            status["gpu"] = metrics.get("gpu", {})

        try:
            response = http.post(
                f"{self.master_url}/hfl/heartbeat",
                data={
                    "agent_id": self.agent_id,
                    "metrics": json.dumps(status),
                },
            )

            if response.status_code == 200:
                result = response.json()
                return result
        except Exception:
            pass

        return None

    def _main_loop(self):
        """메인 루프: heartbeat + 작업 수신 + LoRA 업데이트."""
        while self.running:
            try:
                # 하트비트 전송 + 명령 수신
                result = self._send_heartbeat()

                if result:
                    commands = result.get("commands", [])
                    for cmd in commands:
                        self._handle_command(cmd)

                time.sleep(30)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"메인 루프 오류: {e}")
                time.sleep(10)

    def _handle_command(self, command: dict):
        """마스터에서 받은 명령 처리."""
        cmd_type = command.get("type")

        if cmd_type == "update_lora":
            server_version = command.get("version", 0)
            if server_version > self.current_lora_version:
                logger.info(f"🔄 새 LoRA 감지: v{self.current_lora_version} → v{server_version}")
                self._pull_latest_lora()

        elif cmd_type == "train":
            task = command.get("task", {})
            if not self.hfl_active:
                self._start_hfl_training(task)

    # ════════════════════════════════════════════════════════════
    # HFL 연합 학습 루프
    # ════════════════════════════════════════════════════════════

    def _run_hfl_loop(self):
        """HFL 학습 라운드 자동 참여 루프."""
        logger.info("HFL 학습 루프 시작 (60초 간격 체크)")

        while self.running:
            try:
                if self.hfl_active:
                    time.sleep(30)
                    continue

                # 마스터에서 학습 작업 확인
                http = self._get_http()
                if not http:
                    time.sleep(60)
                    continue

                try:
                    response = http.get(
                        f"{self.master_url}/hfl/round/task/{self.agent_id}",
                        timeout=10,
                    )

                    if response.status_code == 200:
                        task = response.json()
                        if task.get("task") == "train_lora":
                            logger.info(f"📋 학습 작업 수신: 라운드 {task.get('round_id')}")
                            self._start_hfl_training(task)
                except Exception:
                    pass

                time.sleep(60)

            except Exception as e:
                logger.error(f"HFL 루프 오류: {e}")
                time.sleep(60)

    def _start_hfl_training(self, task: dict):
        """HFL 학습 실행 → 완료 후 마스터에 업로드."""
        if self.hfl_active:
            return

        self.hfl_active = True
        round_id = task.get("round_id", "unknown")
        config = task.get("config", {})

        logger.info(f"🏋️ HFL 학습 시작: 라운드 {round_id}")
        logger.info(f"   설정: r={config.get('lora_r', 16)}, "
                     f"steps={config.get('steps_per_round', 100)}")

        try:
            finetune: LocalFinetuneModule = self.modules["local_finetune"]

            # 학습 데이터 다운로드 (마스터에서)
            data_path = self._download_training_data(task.get("data_url"))
            if not data_path:
                logger.error("학습 데이터 다운로드 실패")
                self.hfl_active = False
                return

            # 모델 경로 (로컬에 있는 베이스 모델)
            model_path = self._get_local_model_path()
            if not model_path:
                logger.error("로컬 모델 없음")
                self.hfl_active = False
                return

            # LoRA 학습 실행
            lora_name = f"hfl_{round_id}"
            result = finetune.train_local_lora(
                model_path=model_path,
                data_path=data_path,
                lora_name=lora_name,
                epochs=config.get("epochs", 1),
            )

            if result.get("status") == "success":
                logger.info(f"✅ 학습 완료: {lora_name}")

                # 마스터에 업로드!
                upload_result = finetune.share_lora(
                    lora_name=lora_name,
                    master_url=self.master_url,
                    agent_id=self.agent_id,
                    round_id=round_id,
                )

                if upload_result.get("status") == "uploaded":
                    logger.info(f"📤 LoRA 업로드 완료!")
                    server_resp = upload_result.get("server_response", {})
                    if server_resp.get("verified"):
                        logger.info(f"   품질 점수: {server_resp.get('quality_score', 0):.2f}")
                    if server_resp.get("aggregation") == "started":
                        logger.info(f"   🔀 통합 시작됨!")
                else:
                    logger.error(f"업로드 실패: {upload_result}")
            else:
                logger.error(f"학습 실패: {result}")

        except Exception as e:
            logger.error(f"HFL 학습 에러: {e}")
        finally:
            self.hfl_active = False

    def _download_training_data(self, data_url: str | None) -> str | None:
        """마스터에서 학습 데이터 다운로드."""
        if not data_url:
            # 로컬 데이터 사용 (에이전트의 자체 데이터)
            local_data = os.path.expanduser("~/.hwarang/local_loras/local_data.jsonl")
            if os.path.exists(local_data):
                return local_data
            return None

        http = self._get_http()
        if not http:
            return None

        try:
            url = f"{self.master_url}{data_url}" if data_url.startswith("/") else data_url
            response = http.get(url, timeout=120)

            if response.status_code == 200:
                save_path = os.path.expanduser("~/.hwarang/training_data.jsonl")
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"학습 데이터 다운로드: {len(response.content)/1024:.0f}KB")
                return save_path
        except Exception as e:
            logger.error(f"데이터 다운로드 실패: {e}")

        return None

    def _get_local_model_path(self) -> str | None:
        """로컬에 설치된 베이스 모델 경로."""
        candidates = [
            os.path.expanduser("~/.hwarang/models/qwen2.5-32b"),
            os.path.expanduser("~/.hwarang/models/qwen2.5-7b"),
            "/mnt/nvme2/hwarang/models/qwen2.5-32b",
            "/mnt/nvme2/hwarang/models/qwen2.5-7b",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    # ════════════════════════════════════════════════════════════
    # LoRA 업데이트
    # ════════════════════════════════════════════════════════════

    def _pull_latest_lora(self):
        """마스터에서 최신 통합 LoRA 다운로드."""
        finetune: LocalFinetuneModule = self.modules.get("local_finetune")
        if not finetune:
            return

        result = finetune.pull_latest_lora(self.master_url)

        if result.get("status") == "updated":
            self.current_lora_version = result["version"]
            logger.info(f"✅ LoRA 업데이트: v{self.current_lora_version} ({result.get('size_mb', 0)}MB)")
        elif result.get("status") == "up_to_date":
            logger.info(f"LoRA 최신 상태: v{self.current_lora_version}")
        elif result.get("error"):
            logger.debug(f"LoRA 업데이트 스킵: {result['error']}")

    # ════════════════════════════════════════════════════════════
    # 수면 학습
    # ════════════════════════════════════════════════════════════

    def _run_sleep_watch(self):
        """유휴 감지 → 수면 학습 → 완료 시 마스터 업로드."""
        sleep_mod: SleepLearningModule = self.modules.get("sleep_learning")
        if not sleep_mod:
            return

        logger.info("수면 학습 감시 시작")

        while self.running:
            try:
                idle_seconds = sleep_mod.get_idle_time()

                # 5분 이상 유휴 + 현재 학습 중 아님
                if idle_seconds > 300 and not self.hfl_active:
                    logger.info(f"💤 유휴 감지 ({idle_seconds}초) → 수면 학습 시작")
                    self.hfl_active = True

                    try:
                        finetune: LocalFinetuneModule = self.modules["local_finetune"]
                        model_path = self._get_local_model_path()
                        data_path = self._download_training_data(None)

                        if model_path and data_path:
                            lora_name = f"sleep_{int(time.time())}"
                            result = finetune.train_local_lora(
                                model_path=model_path,
                                data_path=data_path,
                                lora_name=lora_name,
                                epochs=1,
                            )

                            if result.get("status") == "success":
                                logger.info(f"💤 수면 학습 완료 → 마스터 업로드")
                                finetune.share_lora(
                                    lora_name=lora_name,
                                    master_url=self.master_url,
                                    agent_id=self.agent_id,
                                )
                    finally:
                        self.hfl_active = False

                time.sleep(60)  # 1분마다 유휴 체크

            except Exception as e:
                logger.error(f"수면 학습 오류: {e}")
                self.hfl_active = False
                time.sleep(60)

    # ════════════════════════════════════════════════════════════
    # GPU 감지
    # ════════════════════════════════════════════════════════════

    def _detect_gpu(self) -> dict:
        """GPU 정보 감지."""
        try:
            import torch
            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                vram = torch.cuda.get_device_properties(0).total_mem / (1024**3)
                return {"name": name, "vram_gb": round(vram, 1)}
        except ImportError:
            pass

        # nvidia-smi 폴백
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                name = parts[0]
                vram = float(parts[1].replace(" MiB", "")) / 1024
                return {"name": name, "vram_gb": round(vram, 1)}
        except Exception:
            pass

        return {"name": "unknown", "vram_gb": 0}

    # ════════════════════════════════════════════════════════════
    # 기존 모듈 루프
    # ════════════════════════════════════════════════════════════

    def _start_thread(self, name: str, target):
        """백그라운드 스레드 시작."""
        t = threading.Thread(target=target, name=f"hwarang-{name}", daemon=True)
        t.start()
        self.threads.append(t)
        logger.info(f"  스레드 시작: {name}")

    def _run_monitoring(self):
        """모니터링 루프."""
        monitor = self.modules["monitoring"]
        while self.running:
            metrics = monitor.collect_metrics()
            if metrics["alerts"]:
                for alert in metrics["alerts"]:
                    logger.warning(f"⚠️ {alert}")
            time.sleep(self.config.modules.monitoring.report_interval_sec)

    def _run_crawling(self):
        """크롤링 루프: 수집 → 마스터 업로드 → 학습 데이터 변환."""
        crawler = self.modules["crawling"]
        while self.running:
            # 1. 데이터 수집
            result = crawler.run_cycle()
            if result["total"] > 0:
                logger.info(f"📦 크롤링 완료: {result['total']}건")

                # 2. 마스터에 업로드
                upload = crawler.upload_to_master(self.master_url, self.agent_id)
                if upload.get("uploaded", 0) > 0:
                    logger.info(f"📤 데이터 업로드: {upload['uploaded']}건 → 마스터")

                # 3. 로컬 학습 데이터로도 변환 (수면 학습에 사용)
                training_path = crawler.convert_to_training_data()
                if training_path:
                    logger.info(f"🔄 학습 데이터 변환 완료: {training_path}")

            time.sleep(self.config.modules.crawling.interval_hours * 3600)

    def _run_auto_update(self):
        """자동 업데이트 체크 루프."""
        updater = self.modules["auto_update"]
        while self.running:
            check = updater.check_update(self.config.network.master_url)
            if check.get("update_available"):
                logger.info(f"🔄 업데이트 가능: {check['current']} → {check['latest']}")
                if self.config.modules.auto_update.auto_restart:
                    updater.apply_update(check["download_url"])
            time.sleep(self.config.modules.auto_update.check_interval_hours * 3600)


# ─── 메인 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="화랑 Grid 에이전트")
    parser.add_argument("--preset", choices=["minimal", "full", "learning", "night"])
    parser.add_argument("--show-config", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--config", default=None, help="설정 파일 경로")
    args = parser.parse_args()

    # 프리셋 또는 기존 설정 로드
    if args.preset:
        presets = {
            "minimal": preset_minimal,
            "full": preset_full,
            "learning": preset_learning_focused,
            "night": preset_night_only,
        }
        config = presets[args.preset]()
        config.save()
    else:
        config = AgentConfig.load(args.config) if args.config else AgentConfig.load()

    if args.show_config:
        config.print_config()
        return

    # 에이전트 시작
    agent = HwarangAgent(config)

    # 시그널 핸들러
    def signal_handler(sig, frame):
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    agent.start()


if __name__ == "__main__":
    main()
