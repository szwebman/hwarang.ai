"""Cognitive 결정의 환각 검증 (Multi-Source Verification).

마스터의 LLM 결정은 그 자체가 LLM 응답이라 잘못 결론을 내릴 수 있다.
사람 승인 게이트만으로는 부족 — 다음 4 단계의 안전망을 추가한다.

검증 흐름
---------
1. **일관성 (Consistency)** — 같은 prompt 로 LLM 을 N 회 (기본 3) 재호출,
   추출한 ``action`` 이름의 최빈값 비율을 계산. 임계 미달 시 차단.
2. **스키마 (Schema)** — 결정 JSON 의 형식과 ``action`` 이 화이트리스트 또는
   ``free_will*`` 패턴인지 검증.
3. **위험 키워드 (Risky Keywords)** — delete/drop/shutdown 등 운영 영향이
   큰 키워드를 결정 텍스트에서 검출.
4. **사실 (Factual via HLKM)** — reasoning 의 숫자/날짜 주장에 대한 간단
   휴리스틱 (향후 Trusted Source verifier 와 연동).

호출
----
``master_loop.cognitive_cycle`` 의 ``reason_about_state`` 직후 호출되어
``HallucinationReport.is_hallucination`` 이 True 면 결정 실행을 차단하고,
``CognitiveMemory`` 에 BLOCKED_HALLUCINATION 으로 기록한다.

환경변수
--------
* ``HWARANG_HALLUC_CHECK_ENABLED`` (기본 true)
* ``HWARANG_HALLUC_REPEATS`` (기본 3) — 일관성 N 회 재호출
* ``HWARANG_HALLUC_CONSISTENCY_THRESHOLD`` (기본 0.6)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field

from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


HALLUC_CHECK_ENABLED = _env_bool("HWARANG_HALLUC_CHECK_ENABLED", True)
HALLUC_REPEATS = max(1, _env_int("HWARANG_HALLUC_REPEATS", 3))
HALLUC_CONSISTENCY_THRESHOLD = _env_float(
    "HWARANG_HALLUC_CONSISTENCY_THRESHOLD", 0.6
)


# 위험 키워드 — 운영 영향이 큰 명령/표현
RISKY_KEYWORDS: list[str] = [
    "delete", "drop", "truncate", "remove", "purge",
    "disable", "shutdown", "stop", "kill", "destroy",
    "rm -rf", "DROP TABLE", "DELETE FROM",
    "삭제", "제거", "비활성", "종료",
]


# 화랑이 지원하는 액션 화이트리스트
# (master_loop.AVAILABLE_ACTIONS 와 동기화 — 변경 시 양쪽 모두 갱신)
SCHEMA_VALID_ACTIONS: set[str] = {
    "trigger_curious_crawl", "trigger_arxiv_summarize",
    "propose_new_trusted_source", "adjust_quality_threshold",
    "trigger_code_round", "trigger_design_round",
    "rebuild_eval_set", "increase_lora_rank",
    "trigger_self_question_eager", "trigger_sleep_cycle",
    "no_action",
    # Free Will Phase 7
    "free_will_goal", "spontaneous_curiosity", "weekly_intent",
}


# ---------------------------------------------------------------------------
# 보고서 데이터클래스
# ---------------------------------------------------------------------------
@dataclass
class HallucinationReport:
    is_hallucination: bool
    confidence: float                 # 0~1, 1 = 확실히 환각
    consistency_score: float          # 여러 응답 일치도
    factual_score: float              # HLKM 검증 점수
    schema_valid: bool                # 스키마 준수
    risky_keywords: list[str] = field(default_factory=list)
    reasoning: str = ""


# ---------------------------------------------------------------------------
# 메인 — 종합 검증
# ---------------------------------------------------------------------------
async def check_hallucination(
    prompt: str,
    decision: dict,
    n_repeats: int | None = None,
) -> HallucinationReport:
    """LLM 결정 환각 종합 검증.

    Args:
        prompt: 원래 사용한 LLM prompt (일관성 체크에 재사용).
                ``"(internal_reasoning)"`` 같은 sentinel 이면 일관성 체크 skip.
        decision: 검증할 결정 dict (``decisions`` 리스트 포함).
        n_repeats: 일관성 체크 횟수 (None 이면 env 기본값).

    Returns:
        ``HallucinationReport``
    """
    repeats = n_repeats if n_repeats is not None else HALLUC_REPEATS

    # 1. 일관성 체크
    consistency = await _check_consistency(prompt, decision, repeats)

    # 2. 스키마 검증
    schema_valid = _check_schema(decision)

    # 3. 위험 키워드
    risky = _detect_risky_keywords(decision)

    # 4. 사실 검증 (HLKM 휴리스틱)
    factual = await _check_factual(decision)

    # 5. 종합 판단
    is_halluc = (
        consistency < HALLUC_CONSISTENCY_THRESHOLD
        or not schema_valid
        or len(risky) > 0
        or factual < 0.5
    )

    return HallucinationReport(
        is_hallucination=is_halluc,
        confidence=max(0.0, min(1.0, 1.0 - consistency)),
        consistency_score=consistency,
        factual_score=factual,
        schema_valid=schema_valid,
        risky_keywords=risky,
        reasoning=_build_reason(consistency, schema_valid, risky, factual),
    )


# ---------------------------------------------------------------------------
# 1. 일관성 — 같은 prompt N 회 호출 후 action 분포
# ---------------------------------------------------------------------------
async def _check_consistency(
    prompt: str,
    original_decision: dict,
    n: int = 3,
) -> float:
    """같은 prompt 를 N 회 재호출하여 결정 일치도 측정.

    prompt 가 ``"(internal_reasoning)"`` 같은 sentinel 이거나 비어있으면
    재호출이 의미 없으므로 ``original_decision`` 의 결정 자체를 평가
    (decisions 가 비어있지 않으면 일관성 OK).
    """
    if n <= 1:
        return 1.0

    # sentinel / 빈 prompt → 재호출 skip — 보수적으로 0.7
    if not prompt or prompt.startswith("("):
        # 결정 자체에 결정이 있으면 0.7, 없으면 0.5
        decisions = (original_decision or {}).get("decisions", [])
        return 0.7 if decisions else 0.5

    try:
        responses = await asyncio.gather(
            *[llm_chat(prompt, max_tokens=1200) for _ in range(n)],
            return_exceptions=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("consistency 재호출 실패: %s", exc)
        return 0.5

    # 각 응답에서 action 이름만 추출
    actions: list[str] = []
    for r in responses:
        if isinstance(r, Exception) or not isinstance(r, str):
            continue
        # 첫 번째 action 키
        m = re.search(r'"action"\s*:\s*"([^"]+)"', r)
        if m:
            actions.append(m.group(1))

    if not actions:
        return 0.5

    # 가장 흔한 액션의 비율
    counter = Counter(actions)
    most_common_count = counter.most_common(1)[0][1]
    return most_common_count / len(actions)


# ---------------------------------------------------------------------------
# 2. 스키마 검증
# ---------------------------------------------------------------------------
def _check_schema(decision: dict) -> bool:
    """결정이 알려진 스키마와 액션 화이트리스트를 따르는지."""
    if not isinstance(decision, dict):
        return False

    decisions_list = decision.get("decisions", [])
    if not isinstance(decisions_list, list):
        return False

    # 빈 decisions 는 OK — 안전 모드 (no action) 로 간주
    for d in decisions_list:
        if not isinstance(d, dict):
            return False
        action = d.get("action")
        if not action or not isinstance(action, str):
            return False
        # 화이트리스트 또는 free_will_* 패턴
        if action not in SCHEMA_VALID_ACTIONS and not action.startswith("free_will"):
            return False

    return True


# ---------------------------------------------------------------------------
# 3. 위험 키워드 검출
# ---------------------------------------------------------------------------
def _detect_risky_keywords(decision: dict) -> list[str]:
    """결정 텍스트(전체 dict 직렬화)에서 위험 키워드 검출."""
    text = str(decision).lower()
    found: list[str] = []
    for kw in RISKY_KEYWORDS:
        if kw.lower() in text:
            found.append(kw)
    return found


# ---------------------------------------------------------------------------
# 4. 사실 검증 (HLKM 휴리스틱)
# ---------------------------------------------------------------------------
async def _check_factual(decision: dict) -> float:
    """결정의 사실 주장이 HLKM 과 일치하는지.

    간단 휴리스틱:
    * reasoning 에 숫자/연도/퍼센트 주장이 없으면 ``0.8`` (사실 주장 없음).
    * 주장이 있으면 ``0.7`` (향후 Trusted Source verifier 호출).
    * reasoning 자체가 없으면 ``0.7`` (중립).
    """
    reasoning = (decision or {}).get("reasoning", "") or ""
    if not reasoning:
        return 0.7

    # 숫자/날짜 주장 추출
    claims = re.findall(r"\b\d{4}년|\b\d+%|\b\d+,\d{3}", reasoning)
    if not claims:
        return 0.8

    # 향후 — Trusted Source verifier 호출 (knowledge.cross_verifier)
    # 지금은 단순화 — 주장이 있으면 보수적 0.7
    return 0.7


# ---------------------------------------------------------------------------
# 사유 빌더
# ---------------------------------------------------------------------------
def _build_reason(
    consistency: float,
    schema_valid: bool,
    risky: list[str],
    factual: float,
) -> str:
    parts: list[str] = []
    if consistency < HALLUC_CONSISTENCY_THRESHOLD:
        parts.append(f"일관성 낮음 ({consistency:.2f})")
    if not schema_valid:
        parts.append("스키마 위반")
    if risky:
        parts.append(f"위험 키워드: {', '.join(risky[:3])}")
    if factual < 0.5:
        parts.append(f"사실 의심 ({factual:.2f})")
    return ", ".join(parts) or "정상"


__all__ = [
    "HallucinationReport",
    "RISKY_KEYWORDS",
    "SCHEMA_VALID_ACTIONS",
    "HALLUC_CHECK_ENABLED",
    "HALLUC_REPEATS",
    "HALLUC_CONSISTENCY_THRESHOLD",
    "check_hallucination",
]
