"""HSEE Phase 5.5 — Self-Questioning Engine.

화랑이 아이처럼 끊임없이 자기에게 질문 → 자기 답 시도 → 약점 자각.

기존 Phase 5 는 사용자가 실패 신호를 줘야 ``KnowledgeGap`` 이 생겼다 (수동).
Phase 5.5 는 **사용자 없이도** 한가할 때 능동적으로 질문을 던지고
신뢰도가 낮으면 직접 ``KnowledgeGap`` 을 만든다.

매 30분 cron 으로 호출되는 ``child_questioning_cycle`` 의 흐름::

    1) 최근 24h 활동 + 무작위 옛 사실에서 5 토픽 random walk 샘플
    2) 토픽당 5 패턴 × 1 질문 = 25 질문 생성
    3) sanity filter (LLM 평가) 로 무의미 질문 제거
    4) 각 질문 self_answer:
         - HLKM temporal_search → 관련 사실 5건
         - LLM 답변 + 자체 confidence (0~1)
    5) confidence < 0.5 → KnowledgeGap upsert (priority 가중)
    6) confidence < 0.3 → Socratic dive (max depth 5) 추가 발동

엔드포인트는 ``routers/learning.py`` 의 ``/self-question/*`` 참조.
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


# ─── 5 질문 패턴 ────────────────────────────────────────────────
QUESTION_PATTERNS: dict[str, str] = {
    "why": (
        "다음 사실에 대해 '왜 그런가?' 라는 한국어 질문 1개를 생성해라. "
        "추가 설명 없이 질문만:\n사실: {fact}"
    ),
    "boundary": (
        "다음 사실의 예외 케이스나 경계 조건을 묻는 한국어 질문 1개:\n사실: {fact}"
    ),
    "compare": (
        "다음 사실과 유사하지만 다른 영역/상황과 비교하는 한국어 질문 1개:"
        "\n사실: {fact}"
    ),
    "what_if": (
        "다음 사실이 다른 시기/지역/조건이면 어떻게 다른지 묻는 한국어 질문 1개:"
        "\n사실: {fact}"
    ),
    "continuation": (
        "다음 사실의 결과로 어떤 일이 따를 수 있는지 묻는 한국어 질문 1개:"
        "\n사실: {fact}"
    ),
}


SANITY_FILTER_PROMPT = """다음 질문이 의미 있는 학습 가치가 있는지 판단해라.
의미 있음: 답하기 어렵거나 깊이 있는 사실 / 인과 / 미래 예측을 묻는 것
의미 없음: 동어반복, 자명한 정의, 답이 명확한 단순 사실

질문: {question}
JSON: {{"useful": true|false, "reason": "한 줄"}}
JSON 만 출력:"""


SELF_ANSWER_CONFIDENCE_PROMPT = """다음 질문에 답하고, 그 답에 대한 자신감을 0~1 로 매겨라.

질문: {question}
관련 사실:
{facts}

JSON: {{"answer": "답변", "confidence": 0.0~1.0, "missing_info": "필요한 추가 정보"}}
JSON 만 출력:"""


SOCRATIC_NEXT_PROMPT = """다음 답변에서 가장 의문이 드는 부분에 대해 '왜?' 또는
'그럼 어떻게?' 라는 한국어 질문 1개를 생성해라. 추가 설명 없이 질문만:
답변: {answer}"""


# 도메인별 중요도 가중치 — 동일한 confidence 부족이라도 법률/세무/의료가
# 더 우선순위 높게 KnowledgeGap 에 누적되도록 priority 보정.
_DOMAIN_IMPORTANCE: dict[str, float] = {
    "legal": 1.5,
    "law": 1.5,
    "tax": 1.4,
    "medical": 1.4,
    "finance": 1.2,
    "tech": 1.0,
    "general": 1.0,
}


# ─── 데이터 클래스 ───────────────────────────────────────────────
@dataclass
class SelfQuestion:
    pattern: str
    question: str
    source_fact_id: str
    domain: str


@dataclass
class SelfAnswerResult:
    question: str
    answer: str
    confidence: float
    missing_info: str
    used_fact_ids: list[str]


# ─── 유틸 ────────────────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:  # noqa: BLE001
        return False


def _topic_importance(domain: str) -> float:
    return _DOMAIN_IMPORTANCE.get((domain or "general").lower(), 1.0)


def _parse_first_json(raw: str) -> dict[str, Any] | None:
    """LLM 응답에서 첫 JSON 객체만 안전 파싱."""
    if not raw:
        return None
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group())
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _clean_question(raw: str) -> str:
    """LLM 출력에서 한 줄 질문만 추출."""
    if not raw:
        return ""
    line = raw.strip().splitlines()[0].strip()
    line = line.lstrip("-•*0123456789. ").strip()
    line = line[:300]
    if line and "?" not in line:
        line += "?"
    return line


# ─── 메인 사이클 ─────────────────────────────────────────────────
async def child_questioning_cycle(
    topic_count: int = 5,
    questions_per_topic: int = 5,
) -> dict[str, Any]:
    """매 30분 cron — 능동 질문 사이클.

    Args:
        topic_count: 샘플링할 사실(토픽) 수.
        questions_per_topic: 토픽당 시도 패턴 수 (현재 max=5).

    Returns:
        통계 dict.
    """
    started = _utcnow()
    if not _prisma_ready():
        return {"questions_asked": 0, "reason": "db_unavailable"}

    topics = await _sample_recent_topics(topic_count)
    if not topics:
        return {
            "questions_asked": 0,
            "reason": "no_recent_topics",
            "elapsed_seconds": (_utcnow() - started).total_seconds(),
        }

    questions_asked = 0
    questions_filtered = 0
    gaps_created = 0
    socratic_chains = 0
    low_conf_total = 0

    pattern_keys = list(QUESTION_PATTERNS.keys())[: max(1, questions_per_topic)]

    for topic_fact in topics:
        try:
            generated = await _generate_questions(topic_fact, pattern_keys)
        except Exception as exc:  # noqa: BLE001
            logger.debug("질문 생성 실패: %s", exc)
            continue

        useful = await _filter_useful(generated)
        questions_filtered += len(generated) - len(useful)

        for q in useful:
            questions_asked += 1
            try:
                answer = await self_answer(q.question, q.domain)
            except Exception as exc:  # noqa: BLE001
                logger.debug("self_answer 실패: %s", exc)
                continue

            if answer.confidence < 0.5:
                low_conf_total += 1
                priority = (1.0 - answer.confidence) * 100.0 * _topic_importance(
                    q.domain
                )
                if await _record_gap(q.question, started, priority_hint=priority):
                    gaps_created += 1

                if answer.confidence < 0.3:
                    chain = await socratic_dive(
                        q.question, q.domain, max_depth=3
                    )
                    if chain:
                        socratic_chains += 1

    return {
        "topics_sampled": len(topics),
        "questions_generated": questions_asked + questions_filtered,
        "questions_asked": questions_asked,
        "questions_filtered": questions_filtered,
        "low_confidence": low_conf_total,
        "gaps_created": gaps_created,
        "socratic_chains": socratic_chains,
        "elapsed_seconds": (_utcnow() - started).total_seconds(),
    }


# ─── 토픽 sampling ───────────────────────────────────────────────
async def _sample_recent_topics(count: int) -> list[Any]:
    """최근 24h 6 + 옛 4 mix → ``count`` 개 random sample.

    호기심 다양성을 위해 옛 사실도 섞는다.
    """
    now = _utcnow()
    cutoff = now - timedelta(hours=24)

    try:
        recent = await prisma.knowledgefact.find_many(
            where={
                "createdAt": {"gte": cutoff},
                "status": "CONFIRMED",
            },
            take=20,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("recent fact 조회 실패: %s", exc)
        recent = []

    try:
        older = await prisma.knowledgefact.find_many(
            where={
                "createdAt": {"lt": cutoff},
                "status": "CONFIRMED",
            },
            take=10,
            order={"createdAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("older fact 조회 실패: %s", exc)
        older = []

    pool = list(recent) + list(older)
    if not pool:
        return []
    return random.sample(pool, min(count, len(pool)))


# ─── 질문 생성 ───────────────────────────────────────────────────
async def _generate_questions(
    fact: Any,
    pattern_keys: list[str] | None = None,
) -> list[SelfQuestion]:
    """1 사실 → ``len(pattern_keys)`` 질문."""
    keys = pattern_keys or list(QUESTION_PATTERNS.keys())
    fact_content = (getattr(fact, "content", "") or "")[:500]
    fact_id = str(getattr(fact, "id", "manual") or "manual")
    domain = (getattr(fact, "domain", None) or "general")

    if not fact_content:
        return []

    out: list[SelfQuestion] = []
    for key in keys:
        template = QUESTION_PATTERNS.get(key)
        if not template:
            continue
        try:
            prompt = template.format(fact=fact_content)
            raw = await llm_chat(prompt, max_tokens=128)
            question = _clean_question(raw)
            if not question:
                continue
            out.append(
                SelfQuestion(
                    pattern=key,
                    question=question,
                    source_fact_id=fact_id,
                    domain=domain,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("질문 생성 실패 [%s]: %s", key, exc)
            continue
    return out


async def _filter_useful(questions: list[SelfQuestion]) -> list[SelfQuestion]:
    """무의미 질문을 LLM 평가로 제거. 파싱 실패는 보수적으로 통과."""
    if not questions:
        return []
    out: list[SelfQuestion] = []
    for q in questions:
        try:
            raw = await llm_chat(
                SANITY_FILTER_PROMPT.format(question=q.question),
                max_tokens=80,
            )
            verdict = _parse_first_json(raw)
            if verdict is None:
                # 파싱 실패 → 보수적으로 통과
                out.append(q)
                continue
            if bool(verdict.get("useful", True)):
                out.append(q)
        except Exception:  # noqa: BLE001
            out.append(q)
    return out


# ─── 자기 답변 ───────────────────────────────────────────────────
async def self_answer(question: str, domain: str = "general") -> SelfAnswerResult:
    """HLKM 검색 + LLM 답변 + 자체 confidence."""
    if not question:
        return SelfAnswerResult(
            question=question,
            answer="",
            confidence=0.3,
            missing_info="empty_question",
            used_fact_ids=[],
        )

    facts: list[Any] = []
    try:
        from hwarang_api.knowledge.search import temporal_search
        from hwarang_api.knowledge.types import SearchQuery

        sq = SearchQuery(
            query=question,
            domain=(domain if domain and domain != "general" else None),
            limit=5,
        )
        result = await temporal_search(sq)
        facts = list(getattr(result, "facts", []) or [])
    except Exception as exc:  # noqa: BLE001
        logger.debug("temporal_search 실패: %s", exc)
        facts = []

    if facts:
        facts_text = "\n".join(
            f"- {(getattr(f, 'content', '') or '')[:200]}" for f in facts[:5]
        )
    else:
        facts_text = "관련 사실 없음"

    try:
        raw = await llm_chat(
            SELF_ANSWER_CONFIDENCE_PROMPT.format(
                question=question[:500],
                facts=facts_text,
            ),
            max_tokens=384,
        )
        data = _parse_first_json(raw)
        if data is not None:
            try:
                conf = float(data.get("confidence", 0.5))
            except Exception:  # noqa: BLE001
                conf = 0.5
            conf = max(0.0, min(1.0, conf))
            answer_text = str(data.get("answer", ""))[:1000]
            missing = str(data.get("missing_info", ""))[:300]
            used_ids = [
                str(getattr(f, "id", "") or "") for f in facts[:5]
            ]
            return SelfAnswerResult(
                question=question,
                answer=answer_text,
                confidence=conf,
                missing_info=missing,
                used_fact_ids=used_ids,
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("self_answer LLM 호출 실패: %s", exc)

    # 3) Trusted Source verifier 로 cross-check (선택, 더 정확하지만 느림)
    # TODO: phase2 통합 시 verify_claim 호출

    return SelfAnswerResult(
        question=question,
        answer="",
        confidence=0.3,
        missing_info="자체 평가 실패",
        used_fact_ids=[],
    )


# ─── KnowledgeGap 기록 ──────────────────────────────────────────
async def _record_gap(
    question: str,
    started: datetime,
    priority_hint: float | None = None,
) -> bool:
    """confidence 가 낮은 질문을 ``KnowledgeGap`` 으로 upsert.

    priority 는 ``failureCount`` 누적으로 표현 (스키마에 priority 컬럼 없음).
    재발견 시 ``failureCount += 1`` 로 자연스레 우선순위가 올라간다.
    """
    topic = (question or "").strip()[:200]
    if not topic:
        return False
    try:
        await prisma.knowledgegap.upsert(
            where={"topic": topic},
            data={
                "create": {
                    "topic": topic,
                    "failureCount": 1,
                    "firstSeenAt": started,
                    "lastSeenAt": started,
                    "status": "open",
                },
                "update": {
                    "failureCount": {"increment": 1},
                    "lastSeenAt": started,
                },
            },
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("KnowledgeGap upsert 실패 %r: %s", topic[:60], exc)
        return False


# ─── Socratic Dive ───────────────────────────────────────────────
async def socratic_dive(
    initial_question: str,
    domain: str = "general",
    max_depth: int = 5,
) -> list[dict[str, Any]]:
    """아이의 끊임없는 '왜?' — 답에서 다음 질문, ``max_depth`` 층까지.

    종료 조건:
      * depth 가 ``max_depth`` 도달
      * confidence < 0.3 (이때 해당 질문도 KnowledgeGap 으로 기록)
      * 다음 질문 생성 실패
    """
    chain: list[dict[str, Any]] = []
    current_q = (initial_question or "").strip()
    if not current_q:
        return chain

    for depth in range(max_depth):
        result = await self_answer(current_q, domain)
        chain.append(
            {
                "depth": depth,
                "question": current_q,
                "answer": result.answer,
                "confidence": round(result.confidence, 3),
                "missing": result.missing_info,
            }
        )

        if result.confidence < 0.3:
            await _record_gap(current_q, _utcnow())
            break

        try:
            raw = await llm_chat(
                SOCRATIC_NEXT_PROMPT.format(answer=result.answer[:500]),
                max_tokens=128,
            )
            next_q = _clean_question(raw)
            if not next_q:
                break
            current_q = next_q
        except Exception:  # noqa: BLE001
            break

    return chain


# ─── 관리자 디버그 진입점 ────────────────────────────────────────
async def manual_question_about(
    topic: str, domain: str = "general"
) -> dict[str, Any]:
    """관리자가 임의 토픽에 대해 즉시 self-question 트리거 (디버그용)."""
    topic = (topic or "").strip()
    if not topic:
        return {"topic": "", "questions": [], "reason": "empty_topic"}

    fake_fact = type(
        "F",
        (),
        {"id": "manual", "content": topic, "domain": domain},
    )()

    generated = await _generate_questions(fake_fact)
    useful = await _filter_useful(generated)

    results: list[dict[str, Any]] = []
    for q in useful:
        try:
            answer = await self_answer(q.question, q.domain)
        except Exception as exc:  # noqa: BLE001
            logger.debug("manual self_answer 실패: %s", exc)
            continue
        results.append(
            {
                "pattern": q.pattern,
                "question": q.question,
                "confidence": round(answer.confidence, 3),
                "answer": answer.answer,
                "missing": answer.missing_info,
            }
        )

    return {
        "topic": topic,
        "domain": domain,
        "generated": len(generated),
        "useful": len(useful),
        "questions": results,
    }


# ────────────────────────────────────────────────────────────
# Eager Mode — confidence 낮으면 1차 출처 API 직접 호출
# ────────────────────────────────────────────────────────────
EAGER_RETRY_PROMPT = """다음 질문에 1차 출처 자료를 참고해서 답하라.
자신감(confidence) 0~1, 인용 출처 URL 도 함께 적어라.

질문: {question}

1차 출처:
{context}

JSON: {{"answer": "...", "confidence": 0.0~1.0, "missing_info": "...", "citations": ["url1", ...]}}
JSON 만 출력:"""


def _parse_date(raw: str | None) -> datetime | None:
    """``YYYYMMDD`` / ``YYYY-MM-DD`` / ISO → datetime (UTC)."""
    if not raw:
        return None
    raw = str(raw).strip()
    fmts = ("%Y%m%d", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y.%m.%d")
    for f in fmts:
        try:
            return datetime.strptime(raw, f).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


async def _ingest_api_results(results: list, domain: str) -> int:
    """1차 출처 API 결과 → KnowledgeFact + SourceCitation 저장.

    매칭되는 ``TrustedSource`` 가 등록돼 있어야 SourceCitation 이 만들어진다.
    ``TrustedSource`` 가 없으면 KnowledgeFact 만 저장 (출처는 source_url 로).
    """
    if not results:
        return 0

    try:
        from hwarang_api.knowledge.pipeline import ingest_fact
        from hwarang_api.knowledge.types import (
            KnowledgeFact,
            KnowledgeVisibility,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingest_fact 임포트 실패: %s", exc)
        return 0

    saved = 0
    for r in results:
        try:
            domain_str = getattr(r, "source_domain", "") or ""
            url = getattr(r, "url", "") or ""
            title = getattr(r, "title", "") or ""
            content = getattr(r, "content", "") or ""
            published = getattr(r, "published_at", None)

            # TrustedSource 매칭 (있으면)
            source_obj = None
            try:
                source_obj = await prisma.trustedsource.find_first(
                    where={"domain": domain_str},
                )
            except Exception:  # noqa: BLE001
                source_obj = None

            display_name = (
                getattr(source_obj, "displayName", None) or domain_str or "primary"
            )
            trust = (
                (getattr(source_obj, "trustLevel", 80) or 80) / 100.0
                if source_obj
                else 0.8
            )

            fact = KnowledgeFact(
                content=f"{title}. {content[:2000]}".strip(),
                domain=domain or "general",
                source=display_name,
                source_url=url or None,
                source_type="official",
                confidence_t0=max(0.0, min(1.0, trust)),
                visibility=KnowledgeVisibility.PUBLIC,
                valid_from=_parse_date(published) or _utcnow(),
            )
            try:
                ingest_result = await ingest_fact(fact, bypass_gate=True)
            except Exception as exc:  # noqa: BLE001
                logger.debug("ingest_fact 실패: %s", exc)
                continue

            fact_id = ingest_result.get("fact_id") if isinstance(
                ingest_result, dict
            ) else None

            # SourceCitation 은 TrustedSource 가 있을 때만
            if source_obj and fact_id:
                try:
                    await prisma.sourcecitation.create(
                        data={
                            "factId": fact_id,
                            "sourceId": source_obj.id,
                            "url": url,
                            "title": title[:500],
                            "excerpt": content[:500],
                            "publishedAt": _parse_date(published),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("SourceCitation 저장 실패: %s", exc)

            saved += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("API 결과 저장 실패: %s", exc)
            continue

    return saved


async def self_answer_eager(
    question: str,
    domain: str = "general",
    confidence_threshold: float = 0.5,
) -> SelfAnswerResult:
    """Eager 모드 — confidence 부족하면 즉시 1차 출처 API 호출 후 재답변.

    흐름:
      1. patient ``self_answer`` (HLKM + LLM)
      2. confidence >= threshold → 그대로 반환
      3. < threshold → 1차 출처 API 동시 검색
      4. API 결과 컨텍스트로 LLM 재답변
      5. API 결과를 HLKM 에 사실로 저장 (다음엔 즉시 답)
    """
    patient = await self_answer(question, domain)
    if patient.confidence >= confidence_threshold:
        return patient

    try:
        from hwarang_api.knowledge.primary_source_apis import (
            search_primary_sources,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("primary_source_apis 임포트 실패: %s", exc)
        return patient

    api_results = await search_primary_sources(question, domain, top_k=5)
    if not api_results:
        # 1차 출처도 비었으면 그대로 patient 반환 (gap 으로 떨어짐)
        return patient

    # API 결과 → HLKM 저장 먼저 (LLM 실패해도 사실은 남김)
    try:
        await _ingest_api_results(api_results, domain)
    except Exception as exc:  # noqa: BLE001
        logger.debug("API 결과 ingest 실패: %s", exc)

    context = "\n\n".join(
        f"[{r.source_domain}] {r.title}\n{(r.content or '')[:1000]}"
        for r in api_results[:5]
    )

    try:
        raw = await llm_chat(
            EAGER_RETRY_PROMPT.format(question=question[:500], context=context),
            max_tokens=512,
        )
        data = _parse_first_json(raw)
        if data is not None:
            try:
                conf = float(data.get("confidence", 0.7))
            except Exception:  # noqa: BLE001
                conf = 0.7
            conf = max(0.0, min(1.0, conf))
            answer_text = str(data.get("answer", ""))[:1500]
            missing = str(data.get("missing_info", ""))[:300]
            return SelfAnswerResult(
                question=question,
                answer=answer_text,
                confidence=conf,
                missing_info=missing,
                used_fact_ids=[r.url for r in api_results[:5] if r.url],
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("eager LLM 재답변 실패: %s", exc)

    return patient


# ────────────────────────────────────────────────────────────
# Eager Cycle — 매일 새벽 2시 집중 학습 세션
# ────────────────────────────────────────────────────────────
async def eager_questioning_cycle(
    topic_count: int = 10,
    questions_per_topic: int = 5,
    enable_socratic: bool = True,
) -> dict[str, Any]:
    """집중 학습 세션 — patient 보다 더 많이, 모든 질문에 eager 답변.

    매일 새벽 2시 (KST) cron 으로 1회. LLM/API 호출이 많아 비용은 비싸지만
    GPU 한가한 시간대를 활용한다.
    """
    started = _utcnow()
    if not _prisma_ready():
        return {"questions_asked": 0, "reason": "db_unavailable"}

    topics = await _sample_recent_topics(topic_count)
    if not topics:
        return {
            "questions_asked": 0,
            "reason": "no_recent_topics",
            "elapsed_seconds": (_utcnow() - started).total_seconds(),
        }

    pattern_keys = list(QUESTION_PATTERNS.keys())[: max(1, questions_per_topic)]

    questions_asked = 0
    api_calls = 0
    facts_ingested = 0
    socratic_chains = 0
    gaps_created = 0

    for topic_fact in topics:
        try:
            generated = await _generate_questions(topic_fact, pattern_keys)
        except Exception as exc:  # noqa: BLE001
            logger.debug("질문 생성 실패: %s", exc)
            continue

        useful = await _filter_useful(generated)

        for q in useful[:questions_per_topic]:
            questions_asked += 1
            try:
                result = await self_answer_eager(q.question, q.domain)
            except Exception as exc:  # noqa: BLE001
                logger.debug("self_answer_eager 실패: %s", exc)
                continue

            # used_fact_ids 가 URL 형식이면 API 결과 활용된 것
            api_used = bool(result.used_fact_ids) and any(
                str(x).startswith("http") for x in result.used_fact_ids
            )
            if api_used:
                api_calls += 1
                facts_ingested += len(result.used_fact_ids)

            if result.confidence < 0.5:
                priority = (1.0 - result.confidence) * 100.0 * _topic_importance(
                    q.domain
                )
                if await _record_gap(
                    q.question, started, priority_hint=priority
                ):
                    gaps_created += 1

                if enable_socratic and result.confidence < 0.4:
                    chain = await socratic_dive(
                        q.question, q.domain, max_depth=3
                    )
                    if chain:
                        socratic_chains += 1

    return {
        "topics_explored": len(topics),
        "questions_asked": questions_asked,
        "primary_api_calls": api_calls,
        "facts_ingested": facts_ingested,
        "socratic_chains": socratic_chains,
        "gaps_created": gaps_created,
        "elapsed_seconds": (_utcnow() - started).total_seconds(),
    }


__all__ = [
    "QUESTION_PATTERNS",
    "SelfQuestion",
    "SelfAnswerResult",
    "child_questioning_cycle",
    "self_answer",
    "self_answer_eager",
    "eager_questioning_cycle",
    "socratic_dive",
    "manual_question_about",
]
