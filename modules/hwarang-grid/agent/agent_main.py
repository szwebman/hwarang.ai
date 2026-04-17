"""화랑 Grid 에이전트 메인

모든 모듈을 설정에 따라 시작/관리.

사용법:
    # 기본 실행
    python agent_main.py

    # 프리셋으로 실행
    python agent_main.py --preset full

    # 설정 보기
    python agent_main.py --show-config

    # 특정 모듈만
    python agent_main.py --modules serving,learning,benchmark

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


class HwarangAgent:
    """화랑 Grid 에이전트.

    설정에 따라 모듈을 시작하고, 마스터와 통신.
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.running = False
        self.modules: dict[str, object] = {}
        self.threads: list[threading.Thread] = []

        self._init_modules()

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

        # 모듈별 백그라운드 스레드 시작
        if "monitoring" in self.modules:
            self._start_thread("monitoring", self._run_monitoring)

        if "crawling" in self.modules:
            self._start_thread("crawling", self._run_crawling)

        if "auto_update" in self.modules:
            self._start_thread("auto_update", self._run_auto_update)

        # 메인 루프 (마스터 통신 + heartbeat)
        self._main_loop()

    def stop(self):
        """에이전트 중지."""
        logger.info("에이전트 종료 중...")
        self.running = False
        for t in self.threads:
            t.join(timeout=5)
        logger.info("에이전트 종료 완료")

    def _register_with_master(self):
        """마스터 서버에 등록."""
        logger.info(f"마스터 등록: {self.config.network.master_url}")
        # TODO: 실제 HTTP 등록 호출

    def _main_loop(self):
        """메인 루프: heartbeat + 작업 수신."""
        while self.running:
            try:
                # Heartbeat
                self._send_heartbeat()

                # 마스터에서 작업 확인
                # task = self._check_for_tasks()
                # if task: self._execute_task(task)

                time.sleep(30)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"메인 루프 오류: {e}")
                time.sleep(10)

    def _send_heartbeat(self):
        """마스터에 상태 전송."""
        status = {
            "agent_id": self.config.agent_id,
            "modules": list(self.modules.keys()),
            "timestamp": time.time(),
        }

        if "monitoring" in self.modules:
            metrics = self.modules["monitoring"].collect_metrics()
            status["gpu"] = metrics.get("gpu", {})
            status["alerts"] = metrics.get("alerts", [])

        if "cache" in self.modules:
            status["cache"] = self.modules["cache"].get_stats()

        # TODO: 실제 마스터 전송

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
        """크롤링 루프."""
        crawler = self.modules["crawling"]
        while self.running:
            result = crawler.run_cycle()
            if result["total"] > 0:
                logger.info(f"📦 크롤링 완료: {result['total']}건")
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
