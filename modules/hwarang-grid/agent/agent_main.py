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
from modules.optimizer import (
    AgentWatchdog, ConnectionPool, DataDeduplicator, get_model_cache,
)
from modules.lora_compressor import NetworkAdaptiveTransfer

# 추가 모듈 (전부 연결)
from modules.agent_dna import AgentDNAModule
from modules.agent_guild import AgentGuildModule
from modules.ai_mentor import AIMentorModule
from modules.auto_specialization import AutoSpecializationModule
from modules.marketplace import MarketplaceModule
from modules.model_distributor import ModelDistributorModule
from modules.offline_agent import OfflineAgentModule
from modules.p2p_collaboration import P2PCollaborationModule
from modules.reputation import ReputationModule

# ──────────────────────────────────────────────────────────────────
# HWARANG Grid 확장 모듈 (도메인 특화 + 라운드 오케스트레이션)
# 각 모듈은 graceful import — 선택적 의존성 누락 시 스킵.
# ──────────────────────────────────────────────────────────────────
try:
    from modules import domain_specialization
except Exception as _exc:
    domain_specialization = None  # type: ignore
    logger.warning("domain_specialization 임포트 실패: %s", _exc)

try:
    from modules import round_subscription
except Exception as _exc:
    round_subscription = None  # type: ignore
    logger.warning("round_subscription 임포트 실패: %s", _exc)

try:
    from modules import participation_control
except Exception as _exc:
    participation_control = None  # type: ignore
    logger.warning("participation_control 임포트 실패: %s", _exc)

try:
    from modules import contribution_vote
except Exception as _exc:
    contribution_vote = None  # type: ignore
    logger.warning("contribution_vote 임포트 실패: %s", _exc)

try:
    from modules import earnings_tracker
except Exception as _exc:
    earnings_tracker = None  # type: ignore
    logger.warning("earnings_tracker 임포트 실패: %s", _exc)

try:
    from modules import safety_guards
except Exception as _exc:
    safety_guards = None  # type: ignore
    logger.warning("safety_guards 임포트 실패: %s", _exc)

# 데몬 모드 plumbing — 모두 graceful import (없어도 정상 동작)
try:
    from modules import status_writer  # type: ignore
except Exception as _exc:
    status_writer = None  # type: ignore
    logger.warning("status_writer 임포트 실패: %s", _exc)

try:
    from modules import pid_manager  # type: ignore
except Exception as _exc:
    pid_manager = None  # type: ignore
    logger.warning("pid_manager 임포트 실패: %s", _exc)

# 인지(자율 결정) 모듈 — graceful import
try:
    from modules.cognitive import (  # type: ignore
        decide_about_round,
        RoundOffer as CognitiveRoundOffer,
    )
except Exception as _exc:
    decide_about_round = None  # type: ignore
    CognitiveRoundOffer = None  # type: ignore
    logger.warning("cognitive 모듈 임포트 실패: %s", _exc)

# 인지 callback 서버 — Master 의 consult 받기
try:
    from modules.cognitive.callback_server import (  # type: ignore
        start_callback_server as _start_cognitive_callback,
        stop_callback_server as _stop_cognitive_callback,
        build_callback_url as _build_callback_url,
    )
except Exception as _exc:
    _start_cognitive_callback = None  # type: ignore
    _stop_cognitive_callback = None  # type: ignore
    _build_callback_url = None  # type: ignore
    logger.debug("cognitive callback_server 임포트 실패: %s", _exc)


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
        self.hfl_active = False
        self._http_client = None

        # 분산 크롤 워커 상태
        self._crawler_agent = None
        self._crawler_thread: threading.Thread | None = None

        # 데몬 모드 / 상태 추적
        self._daemon_mode: bool = False
        self._started_at = None
        self.last_error: str | None = None
        self._status_writer_thread: threading.Thread | None = None
        self._status_stop_event = None  # asyncio.Event (생성 시점 미정)

        # cognitive callback 서버 상태 (마스터 → 에이전트 consult 수신)
        self._callback_runner = None
        self._callback_loop = None
        self._callback_thread: threading.Thread | None = None
        self._callback_url: str = ""

        # ~/.hwarang/ 자동 생성
        try:
            os.makedirs(os.path.expanduser("~/.hwarang"), exist_ok=True)
            os.makedirs(os.path.expanduser("~/.hwarang/logs"), exist_ok=True)
        except Exception as _exc:
            logger.warning("~/.hwarang 디렉토리 생성 실패: %s", _exc)

        # 최적화 모듈
        self.watchdog = AgentWatchdog()
        self.deduplicator = DataDeduplicator()
        self.adaptive_transfer = NetworkAdaptiveTransfer()

        # ── HWARANG Grid 확장 상태 ──
        self.domain_profile = None       # DomainProfile 인스턴스
        self.safety_config = None        # SafetyConfig 인스턴스
        self.api_key = getattr(config, "api_key", None) or os.environ.get(
            "HWARANG_AGENT_KEY", "devkey"
        )

        self._init_modules()
        self._init_grid_extensions()

    def _get_http(self):
        """HTTP 클라이언트 (커넥션 풀 사용)."""
        client = ConnectionPool.get().get_client()
        if client:
            return client
        # 폴백
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

        # 추가 모듈 (항상 초기화)
        self.modules["reputation"] = ReputationModule()
        self.modules["ai_mentor"] = AIMentorModule()
        self.modules["auto_specialization"] = AutoSpecializationModule()
        self.modules["marketplace"] = MarketplaceModule()
        self.modules["offline_agent"] = OfflineAgentModule()
        self.modules["model_distributor"] = ModelDistributorModule()
        self.modules["agent_dna"] = AgentDNAModule()
        self.modules["agent_guild"] = AgentGuildModule()
        self.modules["p2p"] = P2PCollaborationModule()

        logger.info(f"초기화된 모듈: {len(self.modules)}개 - {list(self.modules.keys())}")

    # ────────────────────────────────────────────────────────────
    # HWARANG Grid 확장 초기화
    # ────────────────────────────────────────────────────────────

    def _init_grid_extensions(self):
        """도메인 프로필 + safety config 로드, 마스터 동기화."""
        # 프로필 로드
        if domain_specialization is not None:
            try:
                self.domain_profile = domain_specialization.load_profile()
                logger.info(
                    "도메인 프로필 로드: preset=%s, primary=%s",
                    self.domain_profile.preset,
                    self.domain_profile.primary_domains,
                )
            except Exception as exc:
                logger.warning("도메인 프로필 로드 실패: %s", exc)

        # safety config
        if safety_guards is not None:
            try:
                self.safety_config = safety_guards.load_safety_config()
                logger.info("safety 로드: max_vram=%sGB", getattr(self.safety_config, "max_vram_gb", "?"))
            except Exception as exc:
                logger.warning("safety 로드 실패: %s", exc)

    def _sync_profile_with_master(self):
        """시작 시 프로필을 마스터에 동기화."""
        if domain_specialization is None or self.domain_profile is None:
            return
        try:
            import asyncio as _asyncio
            loop = _asyncio.new_event_loop()
            try:
                ok = loop.run_until_complete(
                    domain_specialization.sync_with_master(
                        master_url=self.master_url,
                        agent_id=self.agent_id,
                        profile=self.domain_profile,
                        api_key=self.api_key,
                    )
                )
                logger.info("프로필 마스터 동기화: %s", "OK" if ok else "FAIL")
            finally:
                loop.close()
        except Exception as exc:
            logger.warning("프로필 동기화 중 예외: %s", exc)

    def _run_auto_participation_loop(self):
        """round_subscription.auto_participation_loop 을 백그라운드로 실행.

        round 조건 충족 시 participation_control.join_round 를 호출한다.
        """
        if round_subscription is None or self.domain_profile is None:
            logger.info("자동 참여 루프 스킵 (모듈/프로필 없음)")
            return
        try:
            import asyncio as _asyncio

            async def _on_eligible(round_meta, ev):
                """라운드 적합 판정 → (인지 결정) → 참여/거절."""
                if participation_control is None:
                    logger.info("participation_control 없음 — 수동 join 필요")
                    return

                # ── 인지(자율 결정) 게이트 ─────────────────
                # round_subscription 의 1차 적합성(VRAM/티어/마감)을 통과한 뒤,
                # 사용자 활동/배터리/야간/도메인 적성 등을 더해 한 번 더 판단.
                cognitive_on = (
                    os.environ.get("HWARANG_AGENT_COGNITIVE", "false").lower()
                    in ("1", "true", "yes")
                )
                if cognitive_on and decide_about_round is not None and CognitiveRoundOffer is not None:
                    try:
                        offer = CognitiveRoundOffer(
                            round_id=round_meta.round_id,
                            domain=getattr(round_meta, "domain", "general") or "general",
                            estimated_minutes=int(getattr(round_meta, "estimated_time_minutes", 30) or 30),
                            estimated_hwr=float(getattr(round_meta, "estimated_reward", 100) or 100),
                            min_vram_gb=float(getattr(round_meta, "min_vram_gb", 8) or 8),
                            sample_count=int(getattr(round_meta, "sample_count", 1000) or 1000),
                        )
                        use_llm = os.environ.get("HWARANG_AGENT_LLM_DECIDE", "false").lower() in (
                            "1", "true", "yes",
                        )
                        decision = await decide_about_round(offer, use_llm=use_llm)
                        logger.info(
                            "라운드 %s 인지 결정: %s (conf=%.2f) — %s",
                            offer.round_id, decision.action, decision.confidence, decision.reasoning,
                        )
                        if decision.action != "accept":
                            try:
                                await participation_control.decline_round(
                                    master_url=self.master_url,
                                    agent_id=self.agent_id,
                                    api_key=self.api_key,
                                    round_id=offer.round_id,
                                    reason=f"cognitive:{decision.action}:{decision.reasoning}"[:200],
                                )
                            except Exception as exc:
                                logger.debug("decline 전송 실패: %s", exc)
                            if decision.suggested_alternatives:
                                logger.info(
                                    "  대안 추천: %s",
                                    ", ".join(decision.suggested_alternatives),
                                )
                            return
                    except Exception as exc:
                        # 인지 모듈 오류는 join 을 막지 않음 (폴백: 그냥 join)
                        logger.warning("cognitive 결정 실패, 기본 join 진행: %s", exc)

                try:
                    await participation_control.join_round(
                        master_url=self.master_url,
                        agent_id=self.agent_id,
                        api_key=self.api_key,
                        round_id=round_meta.round_id,
                    )
                    logger.info("라운드 참여 요청 전송: %s", round_meta.round_id)
                except Exception as exc:
                    logger.warning("join 실패: %s", exc)

            stop_event = _asyncio.Event()

            async def _shutdown_watcher():
                while self.running:
                    await _asyncio.sleep(2)
                stop_event.set()

            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
            try:
                loop.create_task(_shutdown_watcher())
                # 환경변수로 WS/폴링 토글 + 폴링 간격 오버라이드
                _prefer_ws = (
                    os.environ.get("HWARANG_PREFER_WEBSOCKET", "true").lower()
                    not in ("0", "false", "no")
                )
                try:
                    _poll_interval = int(
                        os.environ.get("HWARANG_POLL_INTERVAL", "60") or 60
                    )
                except Exception:
                    _poll_interval = 60

                loop.run_until_complete(
                    round_subscription.auto_participation_loop(
                        master_url=self.master_url,
                        agent_id=self.agent_id,
                        api_key=self.api_key,
                        profile=self.domain_profile,
                        on_eligible_round=_on_eligible,
                        stop_event=stop_event,
                        poll_interval_seconds=_poll_interval,
                        prefer_websocket=_prefer_ws,
                    )
                )
            finally:
                loop.close()
        except Exception as exc:
            logger.error("자동 참여 루프 종료: %s", exc)

    def start(self):
        """에이전트 시작."""
        from datetime import datetime as _dt, timezone as _tz
        self.running = True
        self._started_at = _dt.now(_tz.utc)

        logger.info("\n" + "=" * 60)
        logger.info(" 🏹 화랑 Grid 에이전트 시작")
        logger.info("=" * 60)
        self.config.print_config()

        # PID 파일 (데몬 모드일 때만 — CLI 가 이미 기록한 경우 덮어쓰지 않게 stale 만 정리)
        if self._daemon_mode and pid_manager is not None:
            try:
                pid_manager.cleanup_stale()
                if not pid_manager.is_running() or pid_manager.read_pid() == os.getpid():
                    pid_manager.write_pid()
            except Exception as exc:
                logger.warning("PID 파일 처리 실패: %s", exc)

        # 자동 복구: 이전 크래시 확인 + PID 기록
        self.watchdog.start()
        checkpoint = self.watchdog.load_checkpoint()
        if checkpoint:
            self.current_lora_version = checkpoint.get("lora_version", 0)
            logger.info(f"체크포인트 복원: LoRA v{self.current_lora_version}")

        # cognitive callback 서버 — register 전에 띄워야 callback_url 등록 가능
        self._start_callback_server_if_enabled()

        # 마스터 등록
        self._register_with_master()

        # 도메인 프로필을 마스터에 동기화 (확장)
        self._sync_profile_with_master()

        # 최신 LoRA 다운로드
        self._pull_latest_lora()

        # 모듈별 백그라운드 스레드 시작
        if "monitoring" in self.modules:
            self._start_thread("monitoring", self._run_monitoring)

        if "crawling" in self.modules:
            self._start_thread("crawling", self._run_crawling)

        if "auto_update" in self.modules:
            self._start_thread("auto_update", self._run_auto_update)

        # P2P 피어 발견 시작
        if "p2p" in self.modules:
            gpu_info = self._detect_gpu()
            self.modules["p2p"].start(
                agent_id=self.agent_id,
                gpu_name=gpu_info.get("name", ""),
                vram_gb=gpu_info.get("vram_gb", 0),
                tier=getattr(self.config, "tier", "lite"),
            )

        # AI 멘토 관찰 시작
        self._start_thread("mentor", self._run_mentor)

        # 오프라인 큐 동기화
        self._start_thread("offline_sync", self._run_offline_sync)

        # HFL 학습 루프 (핵심!)
        self._start_thread("hfl_loop", self._run_hfl_loop)

        # 수면 학습 감시
        self._start_thread("sleep_watch", self._run_sleep_watch)

        # HWARANG Grid 자동 참여 루프 (라운드 구독)
        if round_subscription is not None and self.domain_profile is not None:
            self._start_thread("auto_participation", self._run_auto_participation_loop)

        # 분산 크롤 워커 (마스터 큐에서 작업 임대)
        try:
            crawl_cfg = self.config.modules.crawling
            if getattr(crawl_cfg, "enabled", False) and getattr(crawl_cfg, "distributed_enabled", True):
                self._start_thread("crawler_worker", self._run_crawler_worker)
        except Exception as exc:
            logger.warning("크롤러 워커 시작 실패: %s", exc)

        # status_writer (데몬 모드 + 모듈 로드된 경우 — CLI가 이미 띄웠으면 중복 방지)
        if (
            self._daemon_mode
            and status_writer is not None
            and self._status_writer_thread is None
        ):
            self._start_thread("status_writer", self._run_status_writer_loop)

        # 메인 루프 (마스터 통신 + heartbeat)
        self._main_loop()

    def stop(self):
        """에이전트 중지 (graceful shutdown)."""
        logger.info("에이전트 종료 중...")
        self.running = False

        # status_writer 에 stop 신호
        if self._status_stop_event is not None:
            try:
                self._status_stop_event.set()
            except Exception:
                pass

        # 상태 파일에 stopped 기록
        if status_writer is not None:
            try:
                status_writer.write_status_sync({"status": "stopped"})
            except Exception as exc:
                logger.debug("status_writer 종료 기록 실패: %s", exc)

        # 체크포인트 저장
        self.watchdog.save_checkpoint({
            "lora_version": self.current_lora_version,
            "modules": list(self.modules.keys()),
            "status": "stopped",
        })
        self.watchdog.cleanup()
        self.watchdog.reset_crash_count()

        # cognitive callback 서버 중지
        try:
            self._stop_callback_server()
        except Exception as exc:
            logger.debug("callback 서버 중지 실패: %s", exc)

        # P2P 중지
        if "p2p" in self.modules:
            self.modules["p2p"].stop()

        # 크롤러 워커 중지 신호 (run_until_complete 가 _watcher 에 의해 곧 종료됨)
        if self._crawler_agent is not None:
            try:
                self._crawler_agent.stop()
            except Exception:
                pass

        # 커넥션 풀 정리
        ConnectionPool.get().close()

        # 모델 캐시 정리
        get_model_cache().clear()

        if self._http_client:
            self._http_client.close()
        for t in self.threads:
            t.join(timeout=5)

        # PID 파일 제거 (데몬 모드)
        if self._daemon_mode and pid_manager is not None:
            try:
                pid_manager.remove_pid()
            except Exception as exc:
                logger.debug("PID 파일 제거 실패: %s", exc)

        logger.info("에이전트 종료 완료")

    # ════════════════════════════════════════════════════════════
    # status_writer (데몬 모드)
    # ════════════════════════════════════════════════════════════

    def _run_status_writer_loop(self):
        """asyncio 루프 안에서 status_writer_loop 를 구동한다."""
        if status_writer is None:
            return
        import asyncio as _asyncio

        try:
            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
            self._status_stop_event = _asyncio.Event()

            async def _get_state():
                return await status_writer.collect_state(self)

            async def _watch():
                while self.running and not self._status_stop_event.is_set():
                    await _asyncio.sleep(2)
                self._status_stop_event.set()

            try:
                interval = int(os.environ.get("HWARANG_STATUS_INTERVAL", "30") or 30)
            except Exception:
                interval = 30
            try:
                loop.run_until_complete(_asyncio.gather(
                    _watch(),
                    status_writer.status_writer_loop(
                        _get_state,
                        interval_sec=interval,
                        stop_event=self._status_stop_event,
                    ),
                ))
            finally:
                loop.close()
        except Exception as exc:
            logger.warning("status_writer_loop 종료: %s", exc)

    # ════════════════════════════════════════════════════════════
    # cognitive callback 서버 (마스터 → 에이전트 consult 수신)
    # ════════════════════════════════════════════════════════════

    def _start_callback_server_if_enabled(self):
        """``HWARANG_AGENT_COGNITIVE=true`` 일 때 별도 스레드에 aiohttp 서버 기동.

        스레드 분리 이유: agent_main 의 메인 스레드는 동기 ``_main_loop`` 라
        asyncio 루프를 호스팅하지 않음. 콜백은 짧은 응답이라 별도 루프로 충분.
        """
        cognitive_on = os.environ.get("HWARANG_AGENT_COGNITIVE", "false").lower() in (
            "1", "true", "yes",
        )
        if not cognitive_on:
            return
        if _start_cognitive_callback is None or _build_callback_url is None:
            logger.warning("aiohttp 미설치 — cognitive callback 서버 비활성")
            return

        try:
            port = int(os.environ.get("HWARANG_AGENT_CALLBACK_PORT", "7878") or 7878)
        except Exception:
            port = 7878

        try:
            self._callback_url = _build_callback_url(port)
        except Exception as exc:
            logger.warning("callback URL 결정 실패: %s", exc)
            self._callback_url = ""

        import asyncio as _asyncio

        ready = threading.Event()

        def _run_loop():
            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
            self._callback_loop = loop
            try:
                self._callback_runner = loop.run_until_complete(
                    _start_cognitive_callback(port=port)
                )
                if self._callback_runner is None:
                    logger.warning("callback 서버 runner 없음 (aiohttp 미설치?)")
                    ready.set()
                    return
                ready.set()
                loop.run_forever()
            except Exception as exc:
                logger.warning("callback 서버 루프 오류: %s", exc)
                ready.set()
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        t = threading.Thread(target=_run_loop, name="cognitive-callback", daemon=True)
        t.start()
        # 최대 5초 대기 — 바인딩 실패해도 register 는 진행
        ready.wait(timeout=5.0)
        self._callback_thread = t
        logger.info(
            "cognitive callback 서버 — url=%s (port=%d)",
            self._callback_url or "(미상)", port,
        )

    def _stop_callback_server(self):
        """callback 서버 정리 — stop() 에서 호출."""
        if self._callback_runner is None or self._callback_loop is None:
            return
        import asyncio as _asyncio

        try:
            fut = _asyncio.run_coroutine_threadsafe(
                _stop_cognitive_callback(self._callback_runner),
                self._callback_loop,
            )
            try:
                fut.result(timeout=5.0)
            except Exception as exc:
                logger.debug("callback runner cleanup 결과 대기 실패: %s", exc)
        except Exception as exc:
            logger.debug("callback runner cleanup 예약 실패: %s", exc)

        try:
            self._callback_loop.call_soon_threadsafe(self._callback_loop.stop)
        except Exception:
            pass
        self._callback_runner = None
        self._callback_loop = None

    # ════════════════════════════════════════════════════════════
    # 마스터 통신
    # ════════════════════════════════════════════════════════════

    def _auth_headers(self) -> dict:
        """공통 Authorization 헤더 (Bearer 토큰)."""
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    def _register_with_master(self):
        """마스터 서버에 등록."""
        logger.info(f"마스터 등록: {self.master_url}")

        http = self._get_http()
        if not http:
            logger.warning("HTTP 클라이언트 없음 → 오프라인 모드")
            return

        try:
            gpu_info = self._detect_gpu()
            # 도메인 — DomainProfile 이 있으면 primary_domains 직렬화
            domains_json = "[]"
            try:
                if self.domain_profile is not None:
                    primaries = list(getattr(self.domain_profile, "primary_domains", []) or [])
                    domains_json = json.dumps(primaries)
            except Exception:
                domains_json = "[]"

            response = http.post(
                f"{self.master_url}/api/grid/register",
                data={
                    "agent_id": self.agent_id,
                    "gpu_name": gpu_info.get("name", "unknown"),
                    "vram_gb": gpu_info.get("vram_gb", 0),
                    "tier": self.config.tier or "lite",
                    "domains": domains_json,
                    "callback_url": self._callback_url or "",
                    "callback_token": os.environ.get("HWARANG_AGENT_CALLBACK_TOKEN", ""),
                    "region": os.environ.get("HWARANG_AGENT_REGION", "kr"),
                },
                headers=self._auth_headers(),
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
                f"{self.master_url}/api/grid/heartbeat",
                data={
                    "agent_id": self.agent_id,
                    "metrics": json.dumps(status),
                },
                headers=self._auth_headers(),
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
                # pause flag 체크 (CLI 가 기록)
                if self._is_paused():
                    logger.debug("pause 상태 → 대기")
                    time.sleep(30)
                    continue

                # 하트비트 전송 + 명령 수신
                result = self._send_heartbeat()

                if result:
                    commands = result.get("commands", [])
                    for cmd in commands:
                        self._handle_command(cmd)

                # 주기적 체크포인트 (30초마다)
                self.watchdog.save_checkpoint({
                    "lora_version": self.current_lora_version,
                    "modules": list(self.modules.keys()),
                    "status": "running" if self.hfl_active else "idle",
                })

                time.sleep(30)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"메인 루프 오류: {e}")
                time.sleep(10)

    def _is_paused(self) -> bool:
        """CLI 의 pause 플래그 확인."""
        try:
            if participation_control is not None:
                return bool(participation_control.is_paused())
        except Exception:
            pass
        # 파일 기반 fallback
        flag = os.path.expanduser("~/.hwarang/pause.flag")
        if not os.path.exists(flag):
            return False
        try:
            with open(flag, "r", encoding="utf-8") as f:
                data = json.load(f)
            until = data.get("until")
            if until:
                from datetime import datetime
                if datetime.utcnow().isoformat() > until:
                    os.remove(flag)
                    return False
            return True
        except Exception:
            return True

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
                        f"{self.master_url}/api/grid/rounds/task/{self.agent_id}",
                        timeout=10,
                        headers=self._auth_headers(),
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

                # 적응형 압축 업로드 (대역폭 측정 → 자동 전략 선택)
                lora_output_dir = os.path.join(
                    finetune.lora_path, lora_name,
                )
                upload_result = self.adaptive_transfer.adaptive_upload(
                    lora_path=lora_output_dir,
                    master_url=self.master_url,
                    agent_id=self.agent_id,
                    round_id=round_id,
                )

                if upload_result.get("status") == "uploaded":
                    cfg = upload_result.get("config", {})
                    logger.info(
                        f"📤 적응형 업로드 완료! "
                        f"(전략: {cfg.get('strategy')}, "
                        f"크기: {cfg.get('estimated_size_mb')}MB)"
                    )
                else:
                    # 폴백: 원본 업로드
                    logger.warning("적응형 업로드 실패 → 원본 업로드 시도")
                    upload_result = finetune.share_lora(
                        lora_name=lora_name,
                        master_url=self.master_url,
                        agent_id=self.agent_id,
                        round_id=round_id,
                    )
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
        """GPU 정보 감지 (NVIDIA/AMD/Intel/Apple Silicon 지원)."""
        try:
            from modules.gpu_detector import detect_gpu
            return detect_gpu()
        except ImportError:
            pass

        # 폴백: 기본 감지
        try:
            import torch
            if torch.cuda.is_available():
                return {"name": torch.cuda.get_device_name(0),
                        "vram_gb": round(torch.cuda.get_device_properties(0).total_mem / 1024**3, 1)}
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return {"name": "Apple Silicon (MPS)", "vram_gb": 0}
        except ImportError:
            pass

        return {"name": "CPU only", "vram_gb": 0}

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

    def _run_crawler_worker(self):
        """분산 크롤 워커 — 마스터 큐에서 작업 임대 → fetch → 제출.

        agent_main 의 스레드 모델 안에서 자체 asyncio loop 를 띄워
        `crawler_agent.CrawlerAgent` 를 구동한다.
        """
        try:
            from modules.crawler_agent import CrawlerAgent, CrawlerConfig
        except Exception as exc:
            logger.warning("crawler_agent 임포트 실패: %s", exc)
            return

        crawl_cfg = self.config.modules.crawling
        cfg = CrawlerConfig(
            master_url=self.master_url,
            api_key=self.api_key or "",
            agent_id=self.agent_id,
            domain_filter=list(getattr(crawl_cfg, "domain_filter", []) or []) or None,
            max_concurrent=getattr(crawl_cfg, "max_concurrent", 3),
            poll_interval_seconds=getattr(crawl_cfg, "poll_interval_seconds", 30),
            request_timeout_sec=getattr(crawl_cfg, "request_timeout", 15),
            respect_robots=getattr(crawl_cfg, "respect_robots", True),
        )

        import asyncio as _asyncio
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        try:
            crawler = CrawlerAgent(cfg)
            self._crawler_agent = crawler

            async def _watcher():
                while self.running:
                    await _asyncio.sleep(2)
                crawler.stop()

            try:
                loop.run_until_complete(
                    _asyncio.gather(_watcher(), crawler.run())
                )
            except Exception as exc:
                logger.warning("크롤러 워커 종료: %s", exc)
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self._crawler_agent = None

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

    def _run_mentor(self):
        """AI 멘토: 사용자 질문 패턴 분석."""
        mentor = self.modules.get("ai_mentor")
        if not mentor:
            return
        while self.running:
            # 주간 리포트 (매 6시간 체크)
            try:
                stats = mentor.get_weekly_report()
                if stats.get("total_questions", 0) > 0:
                    logger.info(f"📚 멘토 리포트: {stats.get('total_questions')}건 질문, "
                                f"주요 분야: {stats.get('top_topics', [])[:3]}")
            except Exception:
                pass
            time.sleep(6 * 3600)

    def _run_offline_sync(self):
        """오프라인 큐 동기화."""
        offline = self.modules.get("offline_agent")
        if not offline:
            return
        while self.running:
            try:
                if offline.is_online():
                    synced = offline.sync_queue(self.master_url)
                    if synced and synced.get("synced", 0) > 0:
                        logger.info(f"📡 오프라인 큐 동기화: {synced['synced']}건")
                else:
                    logger.debug("오프라인 상태 → 큐 대기")
            except Exception:
                pass
            time.sleep(60)


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
    if args.daemon:
        agent._daemon_mode = True

    # 시그널 핸들러 — SIGTERM 은 safety_guards.emergency_shutdown 호출
    def signal_handler(sig, frame):
        logger.warning("신호 수신: %s", sig)
        try:
            if sig == signal.SIGTERM and safety_guards is not None:
                import asyncio as _asyncio
                try:
                    _asyncio.run(safety_guards.emergency_shutdown(
                        reason=f"signal_{sig}"
                    ))
                except Exception as exc:
                    logger.warning("emergency_shutdown 실패: %s", exc)
        finally:
            agent.stop()
            sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    agent.start()


if __name__ == "__main__":
    main()
