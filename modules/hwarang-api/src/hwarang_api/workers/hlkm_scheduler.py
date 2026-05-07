"""HLKM 백그라운드 잡 스케줄러.

APScheduler 같은 외부 의존성 없이 ``asyncio`` 만으로 구현.

지원하는 잡 유형:
  * 주기 잡 (`_run_job`) : 고정 간격(초) 마다 실행
  * 크론 잡 (`_run_cron_job`) : 매일 특정 시각 (KST) 실행
  * 요일 잡 (`_run_weekly_job`) : 매주 특정 요일/시각 (KST) 실행

각 잡은 개별 예외를 흡수해 루프 자체가 죽지 않도록 한다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# KST = UTC+9
KST = timezone(timedelta(hours=9))

JobFn = Callable[[], Awaitable[Any]]


def _is_scheduler_leader() -> bool:
    """다중 인스턴스 배포 시 cron 잡을 1대만 돌리기 위한 가드.

    환경변수 ``HWARANG_SCHEDULER_LEADER``:
      * 미설정 → 기본 leader=True (단일 인스턴스 가정, 개발/소규모)
      * "0"/"false"/"no"/"off" → leader=False (cron 비활성, API 만 서빙)
      * 그 외 ("1"/"true"/...) → leader=True
    수평확장 (k8s replicas>1, docker-compose scale 등) 운영 시
    1 대만 ``HWARANG_SCHEDULER_LEADER=1``, 나머지는 ``=0`` 으로 설정해야
    외부 API rate limit / 중복 LoRA 학습이 발생하지 않음.
    """
    raw = os.environ.get("HWARANG_SCHEDULER_LEADER")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _now_kst() -> datetime:
    return datetime.now(tz=KST)


def _seconds_until_next(hour: int, minute: int, weekday: int | None = None) -> float:
    """다음 발화 시각까지 남은 초.

    - ``weekday`` (0=월~6=일) 가 주어지면 요일까지 일치해야 함.
    - KST 기준.
    """
    now = _now_kst()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if weekday is None:
        if target <= now:
            target += timedelta(days=1)
    else:
        # 요일 보정
        days_ahead = (weekday - now.weekday()) % 7
        target += timedelta(days=days_ahead)
        if target <= now:
            target += timedelta(days=7)

    return max(1.0, (target - now).total_seconds())


# ---------------------------------------------------------------------------
# 스케줄러
# ---------------------------------------------------------------------------
class HLKMScheduler:
    """HLKM 백그라운드 잡 관리자.

    사용 예::

        sched = get_scheduler()
        await sched.start()
        ...
        await sched.stop()
    """

    def __init__(self) -> None:
        self.tasks: list[asyncio.Task] = []
        self.running: bool = False
        self.last_run: dict[str, datetime] = {}
        self.last_result: dict[str, dict] = {}
        self.last_error: dict[str, str] = {}

    # -- 수명 관리 ----------------------------------------------------------
    async def start(self) -> None:
        """등록된 모든 잡을 백그라운드 태스크로 띄운다. 중복 호출 안전.

        다중 인스턴스 배포에서는 ``HWARANG_SCHEDULER_LEADER=0`` 으로 설정한
        인스턴스에서는 cron 잡을 띄우지 않는다 (API 라우터만 서빙).
        """
        if self.running:
            logger.info("HLKMScheduler already running")
            return

        if not _is_scheduler_leader():
            logger.info(
                "HLKMScheduler: this instance is NOT the scheduler leader "
                "(HWARANG_SCHEDULER_LEADER=0) — cron jobs disabled. host=%s",
                socket.gethostname(),
            )
            # running=False 유지 → API 만 서빙
            return

        self.running = True
        logger.info(
            "HLKMScheduler starting (LEADER, host=%s)...", socket.gethostname()
        )

        loop = asyncio.get_running_loop()

        # 잡 정의 (이름, 스케줄 타입, 작업 함수)
        # 지연 임포트로 prisma/의존 모듈 부재 시에도 import 자체는 성공하게 함.
        self.tasks = [
            loop.create_task(
                self._run_cron_job("daily_verify", 3, 0, self._job_daily_verify),
                name="hlkm.daily_verify",
            ),
            loop.create_task(
                self._run_job("hrag_law_sync", 6 * 3600, self._job_hrag_law),
                name="hlkm.hrag_law_sync",
            ),
            loop.create_task(
                self._run_job("hrag_weather_sync", 3600, self._job_hrag_weather),
                name="hlkm.hrag_weather_sync",
            ),
            loop.create_task(
                self._run_job("hrag_news_sync", 1800, self._job_hrag_news),
                name="hlkm.hrag_news_sync",
            ),
            loop.create_task(
                self._run_weekly_job(
                    "halflife_retrain", weekday=6, hour=4, minute=0,
                    job_fn=self._job_halflife_retrain,
                ),
                name="hlkm.halflife_retrain",
            ),
            loop.create_task(
                self._run_cron_job(
                    "next_check_updater", 2, 0, self._job_update_next_check
                ),
                name="hlkm.next_check_updater",
            ),
            loop.create_task(
                self._run_job("aging_detector", 4 * 3600, self._job_detect_aging),
                name="hlkm.aging_detector",
            ),
            loop.create_task(
                self._run_cron_job(
                    "pending_predictions", 1, 0, self._job_update_pending
                ),
                name="hlkm.pending_predictions",
            ),
            loop.create_task(
                self._run_cron_job("gap_scanner", 5, 0, self._job_scan_gaps),
                name="hlkm.gap_scanner",
            ),
            # 분산 크롤 디스패처 — 매 5 분마다 due 인 TrustedSource 의 URL 을
            # CrawlJob 큐에 push. 실제 크롤은 에이전트가 /api/crawl/lease 로
            # 가져가서 처리한다 (기존 6 시간 직접 크롤은 분산화로 대체).
            loop.create_task(
                self._run_job(
                    "dispatch_crawls", 5 * 60, self._job_dispatch_crawls
                ),
                name="hlkm.dispatch_crawls",
            ),
            # 마스터 fallback 크롤 — 매 10 분마다 30 분 이상 leased 안 된
            # CrawlJob 을 마스터가 직접 처리. 에이전트 0 명/부족 시
            # 시스템 멈춤 방지. 에이전트 충분하면 candidates=0 으로 자동 비활성.
            loop.create_task(
                self._run_job(
                    "master_fallback_crawl",
                    10 * 60,
                    self._job_master_fallback_crawl,
                ),
                name="hlkm.master_fallback_crawl",
            ),
            # ── HSEE Phase 5 — 호기심 사이클 ─────────────────────
            # 매 6시간 — RLHF 부정 신호로 KnowledgeGap 누적
            loop.create_task(
                self._run_job(
                    "detect_gaps", 6 * 3600, self._job_detect_gaps
                ),
                name="hlkm.detect_gaps",
            ),
            # 매 1시간 — 우선순위 gap 에 대해 표적 크롤 큐잉
            loop.create_task(
                self._run_job(
                    "curious_crawl", 1 * 3600, self._job_curious_crawl
                ),
                name="hlkm.curious_crawl",
            ),
            # 매일 03:00 KST — sleep consolidation (학습+모순+archive+gap 마감)
            loop.create_task(
                self._run_cron_job(
                    "sleep_cycle", 3, 0, self._job_sleep_cycle
                ),
                name="hlkm.sleep_cycle",
            ),
            # ── HSEE Phase 5 — 추론 엔진 (Causal + Hypothesis) ───────
            # 매 1시간 — 최근 추가된 사실에서 인과 관계 자동 추출
            loop.create_task(
                self._run_job(
                    "auto_extract_causal", 1 * 3600, self._job_auto_extract_causal
                ),
                name="hlkm.auto_extract_causal",
            ),
            # 매 12시간 — 반복 인과 패턴에서 가설 자동 생성
            loop.create_task(
                self._run_job(
                    "generate_hypotheses", 12 * 3600, self._job_generate_hypotheses
                ),
                name="hlkm.generate_hypotheses",
            ),
            # 매 6시간 — pending 가설 재검증
            loop.create_task(
                self._run_job(
                    "verify_hypotheses", 6 * 3600, self._job_verify_hypotheses
                ),
                name="hlkm.verify_hypotheses",
            ),
            # 매 24시간 — validated 가설 → 사실 일괄 승격
            loop.create_task(
                self._run_job(
                    "promote_validated", 24 * 3600, self._job_promote_validated
                ),
                name="hlkm.promote_validated",
            ),
            # ── HSEE Phase 4 — Trusted Source 자동 갱신 ───────────
            # 매일 04:00 KST — 1차 출처 API (법제처/KOSIS/국세청/MFDS/ECOS/KMA)
            # 도메인별 대표 쿼리 호출 → HLKM 에 사실 ingest + TrustedSource
            # lastCrawledAt 갱신. 분산 크롤(_job_dispatch_crawls)과 별도로,
            # 1차 출처의 "변경 감지 + 신뢰도 신호" 만 빠르게 채운다.
            loop.create_task(
                self._run_cron_job(
                    "crawl_trusted_sources",
                    4,
                    0,
                    self._job_crawl_trusted_sources_phase4,
                ),
                name="hlkm.crawl_trusted_sources",
            ),
            # ── HSEE Phase 5 — Self-Adversarial ──────────────────
            # 매일 04:00 KST (sleep_cycle 03:00 다음 단계) — 자기 답변 공격 + 약점 수집
            loop.create_task(
                self._run_cron_job(
                    "adversarial_self_play",
                    4,
                    0,
                    self._job_adversarial_self_play,
                ),
                name="hlkm.adversarial_self_play",
            ),
            # ── HSEE Phase 5.5 — Self-Questioning Engine ─────────
            # 매 30분 — 화랑이 능동적으로 5 패턴 × 5 토픽 질문 + 자체 답변
            # confidence < 0.5 인 질문은 KnowledgeGap 으로 누적, < 0.3 은
            # Socratic dive 로 추가 파고듦.
            loop.create_task(
                self._run_job(
                    "self_question", 30 * 60, self._job_self_question
                ),
                name="hlkm.self_question",
            ),
            # ── HSEE Phase 5.5 — Eager Questioning (집중 학습 세션) ────
            # 매일 02:00 KST (새벽 GPU 한가) — 10 토픽 × 5 질문 모두 eager 답변
            # confidence 낮으면 즉시 1차 출처 API (법제처/KOSIS/ECOS/...) 직접
            # 호출 후 HLKM 에 사실 저장 → 다음엔 즉시 답.
            loop.create_task(
                self._run_cron_job(
                    "eager_questioning", 2, 0, self._job_eager_questioning
                ),
                name="hlkm.eager_questioning",
            ),
            # ── Research Engine — Group A (arxiv 매일 수집) ─────
            # 매일 06:00 KST — cs.AI/CL/LG/stat.ML 신규 논문 수집 + Paper upsert
            loop.create_task(
                self._run_cron_job(
                    "arxiv_daily", 6, 0, self._job_arxiv_daily
                ),
                name="hlkm.arxiv_daily",
            ),
            # 매 1시간 — pending Paper PDF 파싱 + LLM contribution 추출
            loop.create_task(
                self._run_job(
                    "parse_pending_papers", 3600, self._job_parse_pending_papers
                ),
                name="hlkm.parse_pending_papers",
            ),
            # ── Research Engine — Group B (요약 + 트렌드) ───────
            # 매 1시간 — parsed Paper → koreanSummary + 적용성 평가 → "summarized"
            loop.create_task(
                self._run_job(
                    "summarize_papers", 3600, self._job_summarize_papers
                ),
                name="hlkm.summarize_papers",
            ),
            # 매주 일요일 23:00 KST — 키워드 빈도 + 4주 baseline 비교 + emerging 알림
            loop.create_task(
                self._run_weekly_job(
                    "weekly_trends",
                    weekday=6,
                    hour=23,
                    minute=0,
                    job_fn=self._job_weekly_trends,
                ),
                name="hlkm.weekly_trends",
            ),
            # ── Research Engine — Group C (적용 제안 + 관리자 검토) ─
            # 매 6시간 — applicabilityScore >= 0.7 + summarized Paper 를
            # PaperApplication + GrowthDecision 으로 자동 변환.
            loop.create_task(
                self._run_job(
                    "application_engine",
                    6 * 3600,
                    self._job_application_engine,
                ),
                name="hlkm.application_engine",
            ),
            # ── Code Engine — 코딩 출처 통합 크롤 ────────────────
            # 매 1시간 — GitHub Releases / HN / SO / 한국 tech 블로그 RSS 동시 fetch
            # → KnowledgeFact(domain="code") + SourceCitation 으로 저장.
            loop.create_task(
                self._run_job("dev_crawl", 3600, self._job_dev_crawl),
                name="hlkm.dev_crawl",
            ),
            # 매 6시간 — 최근 ingest 된 code 도메인 fact 들에서 LLM 패턴 추출.
            # LLM 비용 고려해 6시간 간격 (dev_crawl 6배수와 정합).
            loop.create_task(
                self._run_job(
                    "code_pattern", 6 * 3600, self._job_code_pattern
                ),
                name="hlkm.code_pattern",
            ),
            # ── Design Engine — 디자인 출처 통합 크롤 ───────────
            # 매 6시간 — Awwwards / Smashing / CSS-Tricks / 한국 디자인 / shadcn
            # → KnowledgeFact(domain="design") + SourceCitation 으로 저장.
            loop.create_task(
                self._run_job(
                    "design_crawl", 6 * 3600, self._job_design_crawl
                ),
                name="hlkm.design_crawl",
            ),
            # 매 12시간 — 최근 ingest 된 design 도메인 fact 들에서 LLM 시각 패턴 추출.
            loop.create_task(
                self._run_job(
                    "design_pattern", 12 * 3600, self._job_design_pattern
                ),
                name="hlkm.design_pattern",
            ),
            # ── Code Quality Pipeline — LoRA 학습 데이터 정제 ──────
            # 매 6시간 — 최근 ingest 된 code fact 들에 qualityScore 채움.
            loop.create_task(
                self._run_job(
                    "code_quality", 6 * 3600, self._job_code_quality
                ),
                name="hlkm.code_quality",
            ),
            # 매 12시간 — high_quality fact → CodePair 자동 생성 (LLM).
            loop.create_task(
                self._run_job(
                    "code_pair_build",
                    12 * 3600,
                    self._job_code_pair_build,
                ),
                name="hlkm.code_pair_build",
            ),
            # 매 6시간 — untested CodePair 들 샌드박스 실행 검증.
            loop.create_task(
                self._run_job(
                    "code_pair_execute",
                    6 * 3600,
                    self._job_code_pair_execute,
                ),
                name="hlkm.code_pair_execute",
            ),
            # ── Group C — 주간 코드/디자인 트렌드 + LoRA 재학습 제안 ──
            # 매주 일요일 22:00 KST — 4주 baseline 비교 + emerging 감지 +
            # GrowthDecision 자동 생성 (Application Engine).
            loop.create_task(
                self._run_weekly_job(
                    "tech_trends",
                    weekday=6,
                    hour=22,
                    minute=0,
                    job_fn=self._job_tech_trends,
                ),
                name="hlkm.tech_trends",
            ),
            # ── HFL Code/Design Round 자동 트리거 ─────────────────
            # 매 6 시간 — 코드 도메인 라운드 시작 조건 (RLHF 1k+ / pair 500+ /
            # 24h 경과) 평가 후 통과하면 RoundOrchestrator 로 라운드 자동 개시.
            loop.create_task(
                self._run_job(
                    "code_round_check", 6 * 3600, self._job_code_round_check
                ),
                name="hlkm.code_round_check",
            ),
            # 매 6 시간 — 디자인 도메인 라운드 (RLHF 500+ / pattern 200+ / 48h).
            loop.create_task(
                self._run_job(
                    "design_round_check",
                    6 * 3600,
                    self._job_design_round_check,
                ),
                name="hlkm.design_round_check",
            ),
            # 매 1 시간 — qualityScore 가 비어있는 COMPLETED 코드/디자인 라운드들에
            # 대해 hold-out 평가 + 자동 채택/롤백.
            loop.create_task(
                self._run_job(
                    "code_round_validate",
                    3600,
                    self._job_code_round_validate,
                ),
                name="hlkm.code_round_validate",
            ),
            # ── Phase 6 — Master Cognitive Loop ──────────────────
            # 매 15 분 — 마스터가 자율로 observe → reason → execute → reflect.
            # HWARANG_COGNITIVE_ENABLED=false 면 cognitive_cycle 자체가 skip.
            # 일일 액션 한도는 HWARANG_COGNITIVE_MAX_ACTIONS_DAY (기본 20).
            #
            # 안전 폴백으로 Phase 7 이 활성이어도 그대로 유지.
            loop.create_task(
                self._run_job(
                    "master_cognitive",
                    15 * 60,
                    self._job_master_cognitive,
                ),
                name="hlkm.master_cognitive",
            ),
            # ── Phase 7 — Free Will Mode ─────────────────────────
            # HWARANG_FREEWILL_ENABLED=true 일 때만 무한 루프 시작.
            # 기본 OFF — 검증 후 활성. 폴백으로 Phase 6 cron 도 살아있음.
            loop.create_task(
                self._run_job(
                    "free_will_init", 60, self._job_free_will_loop
                ),
                name="hlkm.free_will_init",
            ),
            # 매일 새벽 1시 KST — 창의적 목표 자유 생성 → GrowthDecision 큐잉
            loop.create_task(
                self._run_cron_job(
                    "creative_goals", 1, 0, self._job_creative_goals
                ),
                name="hlkm.creative_goals",
            ),
            # 매 30 분 — 자발적 호기심 (한가할 때 메타 질문 답변)
            loop.create_task(
                self._run_job(
                    "spontaneous_curiosity",
                    30 * 60,
                    self._job_spontaneous_curiosity,
                ),
                name="hlkm.spontaneous_curiosity",
            ),
            # 매주 일요일 23:00 KST — 다음 주 의도 선언
            loop.create_task(
                self._run_weekly_job(
                    "weekly_intent",
                    weekday=6, hour=23, minute=0,
                    job_fn=self._job_weekly_intent,
                ),
                name="hlkm.weekly_intent",
            ),
            # ── HSEE Phase 2 — 주간 Continuous Learning ──────────
            # 매주 일요일 03:00 KST — 7일치 RLHFFeedback (암묵 신호) → DPO 페어
            # → identity_v3/v7 누적 → lora_train.py → eval_full.py → 게이트 통과
            # 시 vLLM hot-swap + A/B 실험 시작.
            loop.create_task(
                self._run_weekly_job(
                    "weekly_lora_train",
                    weekday=6, hour=3, minute=0,
                    job_fn=self._job_weekly_lora_train,
                ),
                name="hlkm.weekly_lora_train",
            ),
            # ── HSEE Phase 2 — A/B 자동 롤백 모니터 ──────────────
            # 매 6 시간 — treatment 의 암묵 부정 신호가 control 대비 +20% 이상이면
            # vLLM /v1/unload_lora_adapter 호출 + 실험 비활성화.
            loop.create_task(
                self._run_job(
                    "ab_rollback_monitor",
                    6 * 3600,
                    self._job_ab_rollback_monitor,
                ),
                name="hlkm.ab_rollback_monitor",
            ),
        ]
        logger.info("HLKMScheduler: %d jobs scheduled", len(self.tasks))

    async def stop(self) -> None:
        """모든 잡 태스크를 취소하고 정리."""
        if not self.running:
            return
        self.running = False
        logger.info("HLKMScheduler stopping %d task(s)...", len(self.tasks))
        for t in self.tasks:
            t.cancel()
        # 취소 완료 대기
        for t in self.tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self.tasks = []
        logger.info("HLKMScheduler stopped")

    # -- 잡 실행 루프 -------------------------------------------------------
    async def _run_job(
        self, name: str, interval_seconds: int, job_fn: JobFn
    ) -> None:
        """``interval_seconds`` 주기로 ``job_fn`` 을 호출하는 영구 루프."""
        logger.info("job[%s] every %ds", name, interval_seconds)
        # 최초 실행은 살짝 지연시켜 기동 시점 폭주 방지.
        await asyncio.sleep(min(30, interval_seconds))
        while self.running:
            await self._invoke(name, job_fn)
            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                raise

    async def _run_cron_job(
        self, name: str, hour: int, minute: int, job_fn: JobFn
    ) -> None:
        """매일 KST ``hour:minute`` 에 ``job_fn`` 을 호출."""
        logger.info("cron[%s] daily at %02d:%02d KST", name, hour, minute)
        while self.running:
            wait_s = _seconds_until_next(hour, minute)
            try:
                await asyncio.sleep(wait_s)
            except asyncio.CancelledError:
                raise
            if not self.running:
                return
            await self._invoke(name, job_fn)

    async def _run_weekly_job(
        self, name: str, weekday: int, hour: int, minute: int, job_fn: JobFn
    ) -> None:
        """매주 ``weekday``(0=월) ``hour:minute`` KST 에 실행."""
        logger.info(
            "weekly[%s] weekday=%d %02d:%02d KST", name, weekday, hour, minute
        )
        while self.running:
            wait_s = _seconds_until_next(hour, minute, weekday=weekday)
            try:
                await asyncio.sleep(wait_s)
            except asyncio.CancelledError:
                raise
            if not self.running:
                return
            await self._invoke(name, job_fn)

    # 잡별 분산 락 TTL (초). 학습/평가 잡은 길게.
    # TTL 만료 시 다른 인스턴스가 takeover 가능 (인스턴스 크래시 대비).
    _LOCK_TTL: dict[str, int] = {
        "weekly_lora_train": 6 * 3600,        # 학습 1~3 시간
        "halflife_retrain": 6 * 3600,
        "ab_rollback_monitor": 30 * 60,
        "crawl_trusted_sources_phase4": 30 * 60,
        "sleep_cycle": 60 * 60,
        "daily_verify": 60 * 60,
        "gap_scanner": 30 * 60,
        # 그 외는 _DEFAULT_LOCK_TTL
    }
    _DEFAULT_LOCK_TTL: int = 30 * 60

    async def _invoke(self, name: str, job_fn: JobFn) -> None:
        """단일 실행을 감싸는 공통 로직 (로그 + 예외 + 스태츠 + 분산 락)."""
        # 설정에서 토글 확인 (이름 → 플래그 매핑). 설정 모듈 부재 시 무시.
        if not await self._is_enabled(name):
            logger.debug("job[%s] disabled by settings", name)
            return

        # 분산 락 시도 — LEADER 가드의 백업 안전망.
        # DB 미가용 / 테이블 없음 / 기타 예외 → True 반환 (fail-open: env 가드만 사용).
        from hwarang_api.workers import scheduler_lock as _lock

        ttl = self._LOCK_TTL.get(name, self._DEFAULT_LOCK_TTL)
        host = socket.gethostname()
        acquired = await _lock.try_acquire(name, ttl_seconds=ttl)
        if not acquired:
            logger.info(
                "job[%s] skipped — held by another instance (DB lock). "
                "this_host=%s",
                name,
                host,
            )
            return

        logger.info(
            "job[%s] run start (host=%s, db_lock=acquired, ttl=%ds)",
            name,
            host,
            ttl,
        )
        started = datetime.now(tz=timezone.utc)
        try:
            result = await job_fn()
            summary: dict = result if isinstance(result, dict) else {"result": result}
            self.last_run[name] = started
            self.last_result[name] = summary
            self.last_error.pop(name, None)
            logger.info("job[%s] ok (host=%s): %s", name, host, summary)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.last_run[name] = started
            self.last_error[name] = f"{type(exc).__name__}: {exc}"
            logger.exception("job[%s] failed: %s", name, exc)
        finally:
            # 다음 인스턴스가 즉시 픽업 가능하도록 즉시 해제.
            # (실패해도 TTL 만료 후 자동 takeover)
            await _lock.release(name)

    async def _is_enabled(self, name: str) -> bool:
        """스케줄러 토글 플래그 조회. 설정 모듈 미가용 시 기본 활성."""
        flag_map = {
            "daily_verify": "daily_verify_enabled",
            "hrag_law_sync": "hrag_law_sync_enabled",
            "hrag_weather_sync": "hrag_weather_sync_enabled",
            "hrag_news_sync": "hrag_news_sync_enabled",
            "halflife_retrain": "halflife_retrain_enabled",
            "weekly_lora_train": "weekly_lora_train_enabled",
            "ab_rollback_monitor": "ab_rollback_monitor_enabled",
        }
        field = flag_map.get(name)
        if field is None:
            return True
        try:
            from hwarang_api.knowledge.settings import get_settings

            s = await get_settings()
            return bool(getattr(s, field, True))
        except Exception:  # noqa: BLE001
            return True

    # -- 개별 잡 본체 -------------------------------------------------------
    async def _job_daily_verify(self) -> dict:
        from hwarang_api.knowledge import run_daily_verification
        from hwarang_api.knowledge.settings import get_settings

        s = await get_settings()
        return await run_daily_verification(limit=s.max_verifications_per_run)

    async def _job_hrag_law(self) -> dict:
        from hwarang_api.knowledge import sync_from_hrag

        return await sync_from_hrag("law")

    async def _job_hrag_weather(self) -> dict:
        from hwarang_api.knowledge import sync_from_hrag

        return await sync_from_hrag("weather")

    async def _job_hrag_news(self) -> dict:
        from hwarang_api.knowledge import sync_from_hrag

        return await sync_from_hrag("news")

    async def _job_halflife_retrain(self) -> dict:
        from hwarang_api.knowledge.half_life import HalfLifeModel

        model = HalfLifeModel()
        await model.train()
        return {"trained": True}

    async def _job_update_next_check(self) -> dict:
        from hwarang_api.knowledge.half_life import update_all_next_check_times

        count = await update_all_next_check_times()
        return {"updated": count}

    async def _job_detect_aging(self) -> dict:
        from hwarang_api.knowledge.self_verify import detect_aging_facts

        aged = await detect_aging_facts()
        if aged:
            logger.warning("HLKM aging facts detected: %d", len(aged))
        return {"aged_count": len(aged), "sample": aged[:5]}

    async def _job_update_pending(self) -> dict:
        from hwarang_api.knowledge.prediction import update_pending_predictions

        count = await update_pending_predictions()
        return {"updated": count}

    async def _job_scan_gaps(self) -> dict:
        """미해결 지식 공백에 대해 대체 출처 탐색 시도."""
        from hwarang_api.db import prisma
        from hwarang_api.knowledge.self_verify import find_alternative_source
        from hwarang_api.knowledge.types import KnowledgeFact

        try:
            gaps = await prisma.knowledgegap.find_many(
                where={"status": "open"},
                order={"failureCount": "desc"},
                take=20,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("gap scan DB failed: %s", exc)
            return {"scanned": 0, "found": 0}

        found = 0
        for g in gaps:
            stub = KnowledgeFact(
                content=g.topic,
                domain="general",
                valid_from=datetime.now(tz=timezone.utc),
                source="gap_scanner",
                entity=g.topic,
            )
            url = await find_alternative_source(stub)
            if url:
                found += 1
                try:
                    await prisma.knowledgegap.update(
                        where={"id": g.id},
                        data={"status": "searching"},
                    )
                except Exception:  # noqa: BLE001
                    pass
        return {"scanned": len(gaps), "found": found}

    async def _job_crawl_trusted_sources(self) -> dict:
        """[DEPRECATED] 마스터 직접 크롤 — Phase 4.1 분산 크롤로 대체.

        하위 호환을 위해 함수만 유지 (직접 호출 금지). 새 코드는
        ``_job_dispatch_crawls`` 만 사용.
        """
        from hwarang_api.knowledge.source_crawler import crawl_all_sources

        return await crawl_all_sources()

    async def _job_dispatch_crawls(self) -> dict:
        """분산 크롤 디스패처 — due 인 TrustedSource 의 URL 을 CrawlJob 큐에 push."""
        from hwarang_api.knowledge.crawl_dispatcher import dispatch_pending_crawls

        return await dispatch_pending_crawls()

    # ── HSEE Phase 5 잡 본체 ───────────────────────────────────
    async def _job_detect_gaps(self) -> dict:
        from hwarang_api.learning.gap_detector import detect_gaps

        return await detect_gaps(window_hours=24)

    async def _job_curious_crawl(self) -> dict:
        from hwarang_api.learning.curious_crawler import (
            proactive_crawl_cycle,
        )

        return await proactive_crawl_cycle()

    async def _job_sleep_cycle(self) -> dict:
        from hwarang_api.learning.sleep_consolidator import sleep_cycle

        return await sleep_cycle()

    # ── HSEE Phase 5 추론 엔진 잡 본체 ─────────────────────────
    async def _job_auto_extract_causal(self) -> dict:
        from hwarang_api.knowledge.causal_extractor import auto_extract_recent

        return await auto_extract_recent(window_hours=2)

    async def _job_generate_hypotheses(self) -> dict:
        from hwarang_api.knowledge.hypothesis_engine import (
            generate_hypotheses_from_patterns,
        )

        return await generate_hypotheses_from_patterns()

    async def _job_verify_hypotheses(self) -> dict:
        from hwarang_api.knowledge.hypothesis_engine import (
            verify_pending_hypotheses,
        )

        return await verify_pending_hypotheses()

    async def _job_promote_validated(self) -> dict:
        from hwarang_api.knowledge.hypothesis_engine import (
            promote_validated_hypotheses,
        )

        return await promote_validated_hypotheses()

    async def _job_adversarial_self_play(self) -> dict:
        """HSEE Phase 5 — 화랑이 자기 답변 공격해서 약점을 ReplaySample 로 수집."""
        from hwarang_api.learning.adversarial_tester import (
            run_adversarial_self_play,
        )

        return await run_adversarial_self_play(samples=20)

    async def _job_crawl_trusted_sources_phase4(self) -> dict:
        """HSEE Phase 4 — 1차 출처 API 주기 호출 + Trusted Source 자동 갱신.

        매일 04:00 KST. ``crawl_trusted_sources`` 가 도메인별 대표 쿼리로
        primary_source_apis 를 호출하고, HLKM 사실 ingest + lastCrawledAt 갱신.
        """
        from hwarang_api.knowledge.source_crawler import crawl_trusted_sources

        return await crawl_trusted_sources()

    async def _job_self_question(self) -> dict:
        """HSEE Phase 5.5 — 화랑이 자기 자신에게 5 패턴 질문을 던지고
        자체 답변 + 신뢰도 평가. 신뢰도 낮은 질문은 KnowledgeGap 으로 누적.
        """
        from hwarang_api.learning.self_questioner import (
            child_questioning_cycle,
        )

        return await child_questioning_cycle(
            topic_count=5, questions_per_topic=5
        )

    async def _job_eager_questioning(self) -> dict:
        """HSEE Phase 5.5 Eager — 매일 02:00 KST 집중 학습 세션.

        confidence 부족하면 즉시 1차 출처 API 직접 호출 후 답을 얻고
        결과를 HLKM 에 사실로 저장. 다음 호출 시엔 같은 질문에 즉시 답.
        """
        from hwarang_api.learning.self_questioner import (
            eager_questioning_cycle,
        )

        return await eager_questioning_cycle(
            topic_count=10,
            questions_per_topic=5,
            enable_socratic=True,
        )

    # ── Research Engine — Group A 잡 본체 ───────────────────────
    async def _job_arxiv_daily(self) -> dict:
        """매일 06:00 KST — arxiv 신규 논문 수집 + Paper upsert."""
        from hwarang_api.research.arxiv_crawler import daily_arxiv_cycle

        return await daily_arxiv_cycle()

    async def _job_parse_pending_papers(self) -> dict:
        """매 1시간 — pending Paper 들 PDF 파싱 + LLM contribution 추출."""
        from hwarang_api.research.paper_parser import parse_pending_papers

        return await parse_pending_papers(batch_size=20)

    # ── Research Engine — Group B 잡 본체 ───────────────────────
    async def _job_summarize_papers(self) -> dict:
        """매 1시간 — parsed Paper → 한국어 요약 + 화랑 적용성 평가."""
        from hwarang_api.research.auto_summarizer import (
            summarize_pending_papers,
        )

        return await summarize_pending_papers(batch_size=15)

    async def _job_weekly_trends(self) -> dict:
        """매주 일요일 23:00 KST — 주간 키워드 트렌드 + emerging 알림."""
        from hwarang_api.research.trend_tracker import weekly_trend_analysis

        return await weekly_trend_analysis()

    # ── Code Engine 잡 본체 ────────────────────────────────────
    async def _job_dev_crawl(self) -> dict:
        """매 1시간 — 코딩 출처 4종 (GitHub/HN/SO/한국 RSS) 통합 크롤."""
        from hwarang_api.research.dev_source_crawler import daily_dev_crawl

        return await daily_dev_crawl()

    async def _job_code_pattern(self) -> dict:
        """매 6시간 — 최근 ingest 된 code fact 들에서 재사용 패턴 추출."""
        from hwarang_api.research.code_pattern_extractor import (
            extract_patterns_from_recent_facts,
        )

        return await extract_patterns_from_recent_facts(window_hours=6)

    # ── Design Engine 잡 본체 ──────────────────────────────────
    async def _job_design_crawl(self) -> dict:
        """매 6시간 — 디자인 출처 5종 (Awwwards/Smashing/CSS-Tricks/한국/shadcn) 크롤."""
        from hwarang_api.research.design_source_crawler import (
            daily_design_crawl,
        )

        return await daily_design_crawl()

    async def _job_design_pattern(self) -> dict:
        """매 12시간 — 최근 ingest 된 design fact 들에서 시각 패턴 추출."""
        from hwarang_api.research.design_pattern_extractor import (
            extract_design_patterns,
        )

        return await extract_design_patterns(window_hours=24)

    # ── Code Quality Pipeline 잡 본체 ──────────────────────────
    async def _job_code_quality(self) -> dict:
        """매 6시간 — 최근 code fact 들 품질 평가 + qualityScore 저장."""
        from hwarang_api.research.quality.code_quality_filter import (
            filter_recent_facts,
        )

        return await filter_recent_facts(window_hours=24)

    async def _job_code_pair_build(self) -> dict:
        """매 12시간 — high_quality fact → CodePair (LLM 자연어 질문+정답)."""
        from hwarang_api.research.quality.code_pair_builder import (
            build_pairs_from_high_quality,
        )

        return await build_pairs_from_high_quality(limit=50)

    async def _job_code_pair_execute(self) -> dict:
        """매 6시간 — untested CodePair 들 샌드박스 실행 검증."""
        from hwarang_api.research.quality.code_executor import (
            execute_pending_pairs,
        )

        return await execute_pending_pairs(batch_size=50)

    # ── Group C — 주간 코드/디자인 트렌드 잡 본체 ──────────────
    async def _job_tech_trends(self) -> dict:
        """매주 일요일 22:00 KST — 코드 + 디자인 트렌드 동시 분석.

        1. 지난 주 vs 4주 baseline (3주 평균) 비교
        2. velocity 30%+ + 임계 건수(code=3, design=2) → emerging
        3. emerging 5+/3+ → GrowthDecision 자동 생성 (LoRA 재학습 제안)
        4. Slack/Discord 알림
        """
        from hwarang_api.research.tech_trend_tracker import (
            weekly_tech_trends_full_cycle,
        )

        return await weekly_tech_trends_full_cycle()

    # ── Research Engine — Group C 잡 본체 ───────────────────────
    async def _job_application_engine(self) -> dict:
        """매 6시간 — score>=0.7 + summarized Paper 를 분석해
        PaperApplication 1~3 개 + GrowthDecision 자동 생성.
        관리자가 승인해야 실제 패치가 큐로 들어감.
        """
        from hwarang_api.research.application_engine import (
            analyze_summarized_papers,
        )

        return await analyze_summarized_papers(batch_size=10)

    # ── HFL Code/Design Round 자동 트리거 잡 본체 ──────────────
    async def _job_code_round_check(self) -> dict:
        """매 6 시간 — 코드 라운드 시작 조건 평가 + 자동 시작."""
        from hwarang_api.grid.code_round.code_round_orchestrator import (
            evaluate_code_round_trigger,
            start_code_round,
        )

        decision = await evaluate_code_round_trigger()
        if not decision.should_start:
            return {
                "skipped": True,
                "reason": decision.reason,
                "rlhf": decision.rlhf_count,
                "pairs": decision.pair_count,
                "hours_since_last": decision.hours_since_last,
            }

        # 라운드 broadcast 는 grid.py 의 callback 이 필요 — 지연 import
        broadcast = None
        try:
            from hwarang_api.routers.grid import broadcast_round_event

            broadcast = broadcast_round_event
        except Exception:  # noqa: BLE001
            pass

        return await start_code_round(broadcast_callback=broadcast)

    async def _job_design_round_check(self) -> dict:
        """매 6 시간 — 디자인 라운드 시작 조건 평가 + 자동 시작."""
        from hwarang_api.grid.code_round.design_round_orchestrator import (
            evaluate_design_round_trigger,
            start_design_round,
        )

        decision = await evaluate_design_round_trigger()
        if not decision.should_start:
            return {
                "skipped": True,
                "reason": decision.reason,
                "rlhf": decision.rlhf_count,
                "patterns": decision.pattern_count,
                "hours_since_last": decision.hours_since_last,
            }

        broadcast = None
        try:
            from hwarang_api.routers.grid import broadcast_round_event

            broadcast = broadcast_round_event
        except Exception:  # noqa: BLE001
            pass

        return await start_design_round(broadcast_callback=broadcast)

    async def _job_code_round_validate(self) -> dict:
        """매 1 시간 — 미검증 (qualityScore=NULL) 라운드들 hold-out 평가."""
        from hwarang_api.db import prisma
        from hwarang_api.grid.code_round.code_round_quality import (
            validate_completed_round,
        )

        if not getattr(prisma, "is_connected", lambda: False)():
            return {"skipped": "db_unavailable"}

        # 신규 컬럼 (qualityScore) 미존재 환경에서도 동작하도록 폴백.
        pending: list = []
        try:
            pending = await prisma.round.find_many(
                where={
                    "domain": {"in": ["code", "design"]},
                    "status": "COMPLETED",
                    "qualityScore": None,
                },
                take=5,
            )
        except Exception:  # noqa: BLE001
            # qualityScore 컬럼이 없으면 config.qualityScore 폴백으로 최근 라운드 5 개만
            try:
                rows = await prisma.round.find_many(
                    where={
                        "domain": {"in": ["code", "design"]},
                        "status": "COMPLETED",
                    },
                    order={"completedAt": "desc"},
                    take=10,
                )
                pending = [
                    r
                    for r in rows
                    if not (
                        isinstance(getattr(r, "config", None), dict)
                        and r.config.get("qualityScore") is not None
                    )
                ][:5]
            except Exception as exc:  # noqa: BLE001
                logger.warning("code_round_validate 폴백 조회 실패: %s", exc)
                return {"skipped": "lookup_failed"}

        results = []
        for r in pending:
            try:
                results.append(await validate_completed_round(r.id))
            except Exception as exc:  # noqa: BLE001
                logger.warning("validate_completed_round 실패 (%s): %s", r.id, exc)
                results.append({"round_id": r.id, "error": str(exc)})

        return {"validated": len(results), "results": results}

    # ── Phase 6 — Master Cognitive Loop 잡 본체 ────────────────
    async def _job_master_cognitive(self) -> dict:
        """매 15 분 — 마스터 자율 사고 사이클 (observe + reason + execute + reflect).

        ``HWARANG_COGNITIVE_ENABLED=false`` 면 ``cognitive_cycle`` 가
        ``{"skipped": True, "reason": "disabled"}`` 반환.
        일일 액션 한도 도달 시 ``{"skipped": True, "reason": "daily_limit"}``.
        """
        from hwarang_api.cognitive import cognitive_cycle

        return await cognitive_cycle(actor="master")

    # ── Phase 7 — Free Will Mode 잡 본체 ───────────────────────
    async def _job_free_will_loop(self) -> dict:
        """Free Will 무한 루프 시작 — 한 번만 호출, 이후 자체 루프.

        ``HWARANG_FREEWILL_ENABLED=true`` 일 때만 시작. 그렇지 않으면 noop.
        한 번 시작되면 ``_free_will_started`` 플래그로 중복 시작 방지.
        """
        if getattr(self, "_free_will_started", False):
            return {"already_running": True}

        if (os.getenv("HWARANG_FREEWILL_ENABLED", "").lower()
                not in ("1", "true", "yes", "on")):
            return {"started": False, "reason": "freewill_disabled"}

        self._free_will_started = True
        loop = asyncio.get_running_loop()
        loop.create_task(self._run_free_will(), name="hlkm.free_will_loop")
        return {"started": True}

    async def _run_free_will(self) -> None:
        """Free Will 루프 본체 — 별도 태스크로 실행."""
        try:
            from hwarang_api.cognitive.free_will import free_will_loop

            await free_will_loop()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Free Will 루프 종료 (예외): %s", exc)
        finally:
            self._free_will_started = False

    async def _job_creative_goals(self) -> dict:
        """매일 1번 — 창의적 목표 자유 생성 → GrowthDecision 큐잉."""
        from hwarang_api.cognitive.free_will import free_will_goal_cycle

        return await free_will_goal_cycle()

    async def _job_spontaneous_curiosity(self) -> dict:
        """매 30 분 — 자발적 호기심 사이클."""
        from hwarang_api.cognitive.spontaneous import spontaneous_curiosity_cycle

        return await spontaneous_curiosity_cycle()

    async def _job_weekly_intent(self) -> dict:
        """매주 일요일 23:00 KST — 다음 주 의도 선언."""
        from hwarang_api.cognitive.intent import declare_weekly_intent

        return await declare_weekly_intent()

    # ── HSEE Phase 2 — 주간 Continuous Learning + 자동 롤백 ────
    async def _job_weekly_lora_train(self) -> dict:
        """매주 일요일 03:00 KST — 7일치 암묵 신호 → DPO → LoRA → A/B."""
        from hwarang_api.learning.weekly_trainer import (
            run_weekly_training_cycle,
        )

        return await run_weekly_training_cycle()

    async def _job_ab_rollback_monitor(self) -> dict:
        """매 6 시간 — A/B treatment 부정 신호 비율 검사 + 임계 시 unload."""
        from hwarang_api.learning.auto_rollback import monitor_and_rollback

        return await monitor_and_rollback()

    async def _job_master_fallback_crawl(self) -> dict:
        """에이전트가 안 가져간 작업을 마스터가 직접 처리 (fallback).

        30 분 이상 ``pending`` 인 CrawlJob 을 최대 5 개 까지 직접 fetch + ingest.
        에이전트가 충분히 처리 중이면 후보가 없어 ``processed=0`` 으로 자동
        비활성. 에이전트 0 명일 때 시스템이 멈추지 않게 하는 boot-strap 보호.
        """
        from hwarang_api.knowledge.master_fallback_crawler import (
            run_fallback_cycle,
        )

        return await run_fallback_cycle(stale_minutes=30, max_jobs=5)

    # -- 상태 조회 ----------------------------------------------------------
    def status(self) -> dict:
        """관리자 대시보드용 요약."""
        jobs = []
        for t in self.tasks:
            name = t.get_name().replace("hlkm.", "")
            jobs.append(
                {
                    "name": name,
                    "running": not t.done(),
                    "last_run": self.last_run.get(name).isoformat()
                    if self.last_run.get(name)
                    else None,
                    "last_result": self.last_result.get(name),
                    "last_error": self.last_error.get(name),
                }
            )
        return {
            "running": self.running,
            "job_count": len(self.tasks),
            "jobs": jobs,
        }


# ---------------------------------------------------------------------------
# 글로벌 싱글톤
# ---------------------------------------------------------------------------
scheduler: HLKMScheduler = HLKMScheduler()


def get_scheduler() -> HLKMScheduler:
    """전역 스케줄러 인스턴스 반환."""
    return scheduler


# ---------------------------------------------------------------------------
# FastAPI 연결 가이드 (main.py 에 추가)
# ---------------------------------------------------------------------------
# lifespan() 안에서:
#
#     from hwarang_api.workers.hlkm_scheduler import get_scheduler
#
#     sched = get_scheduler()
#     await sched.start()
#     try:
#         yield
#     finally:
#         await sched.stop()
#
# 또는 app.on_event("startup")/("shutdown") 훅을 쓰는 레거시 방식:
#
#     @app.on_event("startup")
#     async def _hlkm_start():
#         await get_scheduler().start()
#
#     @app.on_event("shutdown")
#     async def _hlkm_stop():
#         await get_scheduler().stop()
