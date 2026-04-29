"""HSEE Phase 5 — Knowledge Gap Detector.

화랑이 모르는 것을 자동으로 감지해 ``KnowledgeGap`` 테이블에 누적한다.

신호 (현재 구현):
1. RLHFFeedback 의 ``rating == -1`` 또는 ``isSatisfied == False``
2. 응답 신뢰도 메타가 0.5 미만인 (TODO — verification_meta 합쳐지면 활성화)
3. followupMsg 의 부정 신호 (만족도 점수 < 0)
4. HLKM 검색 0건 토픽 (TODO — 검색 미스 이벤트 누적 후 활성화)

매 6시간 cron 으로 ``detect_gaps()`` 가 호출된다.
``get_priority_gaps()`` 는 Curious Crawler 의 입력으로 사용된다.

연결:
  - 입력  : RLHFFeedback (Phase 1)
  - 출력  : KnowledgeGap.upsert
  - 의존  : hwarang_api.knowledge.llm._chat
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as _llm_chat

logger = logging.getLogger(__name__)


GAP_EXTRACT_PROMPT = """다음 대화 묶음에서 화랑이 답변 품질이 낮았던 공통 토픽을 추출해라.
형식: JSON 배열 [{{"topic": "...", "domain": "law|tax|medical|general", "sample_count": N, "urgency": 0.0~1.0}}]
대화들:
{conversations}
JSON 만 출력:"""


# 토픽 → 도메인 매핑 휴리스틱
_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "legal": ("법", "조항", "판례", "민법", "형법", "헌법", "소송", "재판"),
    "tax": ("세금", "세무", "신고", "공제", "부가세", "원천세", "연말정산"),
    "medical": ("병", "약", "진단", "증상", "치료", "처방", "병원"),
    "finance": ("금리", "주식", "부동산", "대출", "투자", "환율"),
    "tech": ("코드", "프로그래밍", "개발", "라이브러리", "framework"),
}


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _infer_domain(topic: str) -> str:
    """토픽에서 도메인 추정 — LLM 이 못 채워줄 때 fallback."""
    if not topic:
        return "general"
    for dom, words in _DOMAIN_KEYWORDS.items():
        if any(w in topic for w in words):
            return dom
    return "general"


def _recency_boost(last_seen: datetime | None) -> float:
    """최근에 본 gap 일수록 우선순위 가중. 30일 지나면 0.3 까지 감쇠."""
    if not last_seen:
        return 1.0
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    days = max(0, (_utcnow() - last_seen).days)
    return max(0.3, 1.0 - days * 0.05)


def _parse_topics(raw: str) -> list[dict[str, Any]]:
    """LLM 출력에서 JSON 배열만 안전하게 파싱."""
    if not raw:
        return []
    try:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group())
        if not isinstance(data, list):
            return []
        # 필수 필드 검증 + sanitize
        out: list[dict[str, Any]] = []
        for it in data:
            if not isinstance(it, dict):
                continue
            topic = str(it.get("topic", "")).strip()
            if not topic or len(topic) > 200:
                continue
            out.append(
                {
                    "topic": topic,
                    "domain": str(it.get("domain") or _infer_domain(topic)),
                    "sample_count": int(it.get("sample_count", 1) or 1),
                    "urgency": float(it.get("urgency", 0.5) or 0.5),
                }
            )
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("gap topic parse failed: %s", exc)
        return []


# ───────────────────────────────────────────────────────────────
# 진입점 1 : detect_gaps
# ───────────────────────────────────────────────────────────────
async def detect_gaps(window_hours: int = 24) -> dict[str, Any]:
    """주기적 실행 — 최근 ``window_hours`` 시간 윈도우의 부정 신호를 모아서
    LLM 으로 토픽 추출 → ``KnowledgeGap`` 누적.

    스케줄러가 6시간마다 호출. window_hours 는 24h 가 기본 — 같은 토픽이
    여러 사이클에 걸쳐 반복 검출되면 ``failureCount`` 가 자연스레 증가한다.
    """
    started = _utcnow()
    if not _prisma_ready():
        return {"gaps_recorded": 0, "reason": "db_unavailable"}

    cutoff = started - timedelta(hours=window_hours)

    # 1) 부정 신호 RLHF 수집
    try:
        low_sat = await prisma.rlhffeedback.find_many(
            where={
                "createdAt": {"gte": cutoff},
                "OR": [
                    {"rating": -1},
                    {"isSatisfied": False},
                ],
            },
            take=500,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("gap_detector: RLHF query failed: %s", exc)
        return {"gaps_recorded": 0, "reason": f"db_error:{exc}"}

    if not low_sat:
        return {
            "gaps_recorded": 0,
            "low_sat_inputs": 0,
            "window_hours": window_hours,
        }

    # 2) LLM 으로 공통 토픽 추출 (배치)
    sample = low_sat[:50]
    convo_text = "\n\n".join(
        f"Q: {(getattr(f, 'followupMsg', None) or '...')[:300]} "
        f"(도메인: {getattr(f, 'domain', None) or 'general'})"
        for f in sample
    )

    try:
        raw = await _llm_chat(
            GAP_EXTRACT_PROMPT.format(conversations=convo_text),
            max_tokens=512,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("gap_detector: LLM call failed: %s", exc)
        raw = ""

    topics = _parse_topics(raw)

    # 3) KnowledgeGap upsert
    new_gaps = 0
    for t in topics:
        topic = t["topic"]
        sample_count = max(1, int(t.get("sample_count", 1)))
        try:
            await prisma.knowledgegap.upsert(
                where={"topic": topic},
                data={
                    "create": {
                        "topic": topic,
                        "failureCount": sample_count,
                        "firstSeenAt": started,
                        "lastSeenAt": started,
                        "status": "open",
                    },
                    "update": {
                        "failureCount": {"increment": sample_count},
                        "lastSeenAt": started,
                    },
                },
            )
            new_gaps += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "gap_detector: upsert failed for %r: %s", topic, exc
            )

    return {
        "gaps_recorded": new_gaps,
        "low_sat_inputs": len(low_sat),
        "topics_extracted": len(topics),
        "window_hours": window_hours,
        "elapsed_seconds": (_utcnow() - started).total_seconds(),
    }


# ───────────────────────────────────────────────────────────────
# 진입점 2 : get_priority_gaps
# ───────────────────────────────────────────────────────────────
async def get_priority_gaps(limit: int = 20) -> list[dict[str, Any]]:
    """우선순위 높은 ``open`` gap 목록 — Curious Crawler 입력.

    우선순위 = ``failureCount * recency_boost(lastSeenAt)``.
    """
    if not _prisma_ready():
        return []

    try:
        gaps = await prisma.knowledgegap.find_many(
            where={"status": "open"},
            order=[
                {"failureCount": "desc"},
                {"lastSeenAt": "desc"},
            ],
            take=limit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_priority_gaps query failed: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    for g in gaps:
        last_seen = getattr(g, "lastSeenAt", None)
        priority = float(getattr(g, "failureCount", 1) or 1) * _recency_boost(
            last_seen
        )
        out.append(
            {
                "id": getattr(g, "id", None),
                "topic": g.topic,
                "priority": round(priority, 3),
                "domain": _infer_domain(g.topic),
                "failure_count": getattr(g, "failureCount", 0),
                "last_seen": last_seen.isoformat() if last_seen else None,
            }
        )
    return out


__all__ = ["detect_gaps", "get_priority_gaps"]
