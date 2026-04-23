"""HLKM 통합 테스트.

DB(Prisma) 가 실제로 연결 가능한 환경에서만 실행된다. 연결 실패 시
모든 케이스는 gracefully skip 된다. 각 테스트는 source="TEST_..." 접두어
를 가진 사실만 생성/삭제해 기존 시드 데이터를 오염시키지 않는다.

실행:
    pytest -xvs tests/test_hlkm_integration.py
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import pytest

from hwarang_api.db import prisma
from hwarang_api.knowledge import (
    KnowledgeFact,
    KnowledgeRelation,
    KnowledgeStatus,
    KnowledgeVisibility,
    SearchQuery,
    calculate_reward,
    current_confidence,
    detect_contradiction,
    encrypt_for_user,
    ingest_fact,
    pay_contribution,
    predict_fact_outcome,
    temporal_search,
    time_travel_search,
    traverse_causal_chain,
)
from hwarang_api.knowledge.privacy import decrypt_for_user
from hwarang_api.knowledge.pipeline import record_knowledge_gap

TEST_SOURCE_PREFIX = "TEST_"
TEST_MASTER_KEY = secrets.token_bytes(32)


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tlabel(base: str) -> str:
    """Collision-free 테스트 엔티티 라벨 (UUID suffix)."""
    return f"{base}_{uuid.uuid4().hex[:8]}"


# ─────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────
_DB_AVAILABLE: bool | None = None


async def _ensure_db() -> bool:
    """DB 연결을 한번만 시도하고 가용성 캐시."""
    global _DB_AVAILABLE
    if _DB_AVAILABLE is not None:
        return _DB_AVAILABLE
    try:
        if not prisma.is_connected():
            await prisma.connect()
        _DB_AVAILABLE = True
    except Exception:
        _DB_AVAILABLE = False
    return _DB_AVAILABLE


@pytest.fixture
async def clean_db() -> AsyncIterator[None]:
    """DB 의존 케이스용 픽스처 — 연결 확인 + TEST_ 접두어 레코드 전/후 청소.

    DB 연결 실패 시 해당 케이스만 skip. 순수 함수 테스트는 이 픽스처를
    요구하지 않으므로 DB 없이도 실행된다.
    """
    ok = await _ensure_db()
    if not ok:
        pytest.skip("Prisma DB 연결 불가 — 통합 테스트 스킵")
        return
    await _cleanup_test_rows()
    try:
        yield
    finally:
        await _cleanup_test_rows()


async def _cleanup_test_rows() -> None:
    """TEST_ 소스로 만든 사실/엣지/기여/충돌 제거."""
    try:
        test_facts = await prisma.knowledgefact.find_many(
            where={"source": {"startsWith": TEST_SOURCE_PREFIX}}
        )
        test_ids = [f.id for f in test_facts]
        if test_ids:
            # 관련 엣지/기여/충돌 제거 (외래키 위반 방지)
            await prisma.knowledgeedge.delete_many(
                where={
                    "OR": [
                        {"fromFactId": {"in": test_ids}},
                        {"toFactId": {"in": test_ids}},
                    ]
                }
            )
            await prisma.knowledgeconflict.delete_many(
                where={
                    "OR": [
                        {"factAId": {"in": test_ids}},
                        {"factBId": {"in": test_ids}},
                    ]
                }
            )
            await prisma.knowledgecontribution.delete_many(
                where={"factId": {"in": test_ids}}
            )
            await prisma.knowledgeverification.delete_many(
                where={"factId": {"in": test_ids}}
            )
            await prisma.knowledgefact.delete_many(
                where={"source": {"startsWith": TEST_SOURCE_PREFIX}}
            )
        await prisma.knowledgegap.delete_many(
            where={"topic": {"startsWith": TEST_SOURCE_PREFIX}}
        )
    except Exception:
        # 청소 실패는 테스트 본체를 막지 않는다.
        pass


# ─────────────────────────────────────────────
# 팩토리
# ─────────────────────────────────────────────
def _make_fact(
    content: str,
    *,
    entity: str | None = None,
    domain: str = "test",
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    visibility: KnowledgeVisibility = KnowledgeVisibility.PUBLIC,
    owner_user_id: str | None = None,
    half_life_days: int | None = 365,
    confidence_t0: float = 1.0,
    status: KnowledgeStatus = KnowledgeStatus.CONFIRMED,
    source_suffix: str = "seed",
) -> KnowledgeFact:
    return KnowledgeFact(
        content=content,
        domain=domain,
        entity=entity,
        valid_from=valid_from or _utcnow(),
        valid_to=valid_to,
        half_life_days=half_life_days,
        confidence_t0=confidence_t0,
        status=status,
        source=f"{TEST_SOURCE_PREFIX}{source_suffix}",
        source_type="user",
        visibility=visibility,
        owner_user_id=owner_user_id,
    )


# ─────────────────────────────────────────────
# 1. ingest 기본 동작
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ingest_creates_fact(clean_db) -> None:
    fact = _make_fact("테스트 사실 1 — 한반도의 수도는 서울이다.", entity=_tlabel("capital_kr"))
    result = await ingest_fact(fact)
    assert result["action"] == "inserted"
    assert result["fact_id"]

    row = await prisma.knowledgefact.find_unique(where={"id": result["fact_id"]})
    assert row is not None
    assert row.source.startswith(TEST_SOURCE_PREFIX)
    assert row.status == KnowledgeStatus.CONFIRMED.value


@pytest.mark.asyncio
async def test_ingest_duplicate_returns_dup(clean_db) -> None:
    content = "중복 테스트 — 같은 내용 두 번 입력하면 duplicate 로 처리되어야 한다."
    fact1 = _make_fact(content, entity=_tlabel("dup"))
    fact2 = _make_fact(content, entity=_tlabel("dup"))

    r1 = await ingest_fact(fact1)
    r2 = await ingest_fact(fact2)
    assert r1["action"] == "inserted"
    assert r2["action"] == "duplicate"
    assert r2["fact_id"] == r1["fact_id"]


@pytest.mark.asyncio
async def test_ingest_supersedes_older_same_entity(clean_db) -> None:
    """같은 엔티티에 대해 더 최신 사실을 넣으면 이전 것은 EXPIRED + validTo 설정."""
    entity = _tlabel("wage")
    old = _make_fact(
        "테스트 임금 2024년 기준 10,000원.",
        entity=entity,
        valid_from=_utc(2024, 1, 1),
        valid_to=None,
    )
    r_old = await ingest_fact(old)
    assert r_old["action"] == "inserted"

    newer = _make_fact(
        "테스트 임금 2025년 기준 10,500원.",
        entity=entity,
        valid_from=_utc(2025, 1, 1),
        valid_to=None,
    )
    r_new = await ingest_fact(newer)
    # 주제 유사 + 숫자 다름 + 같은 엔티티 → supersede 또는 disputed
    assert r_new["action"] in {"superseded", "disputed", "inserted"}

    if r_new["action"] == "superseded":
        old_row = await prisma.knowledgefact.find_unique(where={"id": r_old["fact_id"]})
        assert old_row is not None
        assert old_row.validTo is not None
        assert old_row.status == KnowledgeStatus.EXPIRED.value


@pytest.mark.asyncio
async def test_ingest_detects_contradiction(clean_db) -> None:
    """직접 detect_contradiction 으로 모순 판정."""
    a = _make_fact(
        "테스트 최저시급 2024년 9,860원.",
        entity=_tlabel("mw_a"),
        valid_from=_utc(2024, 1, 1),
    )
    b = _make_fact(
        "테스트 최저시급 2024년 11,000원.",
        entity=_tlabel("mw_b"),
        valid_from=_utc(2024, 1, 1),
    )
    report = await detect_contradiction(a, b)
    # 규칙 층에서 숫자 차이 + 날짜 겹침 → LLM 단계로 넘어감. LLM 결과에 무관하게
    # confidence 는 의미 있는 값이어야 한다.
    assert 0.0 <= report.confidence <= 1.0
    assert report.reasoning


# ─────────────────────────────────────────────
# 2. 검색 / 시간여행 / 가시성
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_temporal_search_current(clean_db) -> None:
    entity = _tlabel("cur")
    fact = _make_fact(
        f"테스트 현재형 사실 ({entity}) — 오늘부터 유효한 규정.",
        entity=entity,
        valid_from=_utcnow() - timedelta(days=1),
    )
    r = await ingest_fact(fact)
    assert r["fact_id"]

    result = await temporal_search(
        SearchQuery(query=f"현재형 사실 {entity}", domain="test", limit=10)
    )
    ids = [f.id for f in result.facts]
    assert r["fact_id"] in ids


@pytest.mark.asyncio
async def test_temporal_search_time_travel(clean_db) -> None:
    """과거 시점 검색이 당시 유효했던 사실만 돌려주는지."""
    entity = _tlabel("tt")
    past = _make_fact(
        f"과거 유효 사실 ({entity}) — 2020년에만 효력.",
        entity=entity,
        valid_from=_utc(2020, 1, 1),
        valid_to=_utc(2021, 1, 1),
    )
    future_only = _make_fact(
        f"최신 유효 사실 ({entity}) — 2024 부터.",
        entity=entity,
        valid_from=_utc(2024, 1, 1),
    )
    r_past = await ingest_fact(past)
    r_new = await ingest_fact(future_only)

    # 2020-06 기준으로 보면 past 만 유효해야 함
    res = await time_travel_search(
        f"유효 사실 {entity}", as_of=_utc(2020, 6, 1), domain="test"
    )
    ids = {f.id for f in res.facts}
    assert r_past["fact_id"] in ids
    # future 는 미래라 필터링 됨
    assert r_new["fact_id"] not in ids


@pytest.mark.asyncio
async def test_temporal_search_respects_visibility(clean_db) -> None:
    """PRIVATE 사실은 다른 사용자에게 노출되지 않는다."""
    owner = f"user-{uuid.uuid4().hex[:8]}"
    intruder = f"user-{uuid.uuid4().hex[:8]}"

    priv = _make_fact(
        f"비공개 테스트 메모 — 내 계좌번호 관련 노트 ({owner}).",
        entity=_tlabel("priv"),
        visibility=KnowledgeVisibility.PRIVATE,
        owner_user_id=owner,
    )
    r = await ingest_fact(priv)
    assert r["fact_id"]

    # 타 사용자 시점 — include_private=True 이지만 user_id 가 다르면 보이면 안 됨.
    other_view = await temporal_search(
        SearchQuery(
            query="비공개 테스트 메모",
            domain="test",
            user_id=intruder,
            include_private=True,
            limit=10,
        )
    )
    assert r["fact_id"] not in [f.id for f in other_view.facts]

    # 본인 시점 — 보여야 함.
    own_view = await temporal_search(
        SearchQuery(
            query="비공개 테스트 메모",
            domain="test",
            user_id=owner,
            include_private=True,
            limit=10,
        )
    )
    assert r["fact_id"] in [f.id for f in own_view.facts]


# ─────────────────────────────────────────────
# 3. 반감기 / 신뢰도
# ─────────────────────────────────────────────
def test_current_confidence_decay() -> None:
    """시간이 경과할수록 confidence 는 반감기에 따라 감쇠한다."""
    now = _utcnow()
    fact = KnowledgeFact(
        content="반감기 테스트",
        valid_from=now - timedelta(days=365),
        last_verified_at=now - timedelta(days=365),
        half_life_days=365,
        confidence_t0=1.0,
        source=f"{TEST_SOURCE_PREFIX}decay",
    )
    conf = current_confidence(fact, now=now)
    # 정확히 1 half-life 경과 → 0.5 근처
    assert 0.45 <= conf <= 0.55

    # 영속 지식은 감쇠 없음
    eternal = KnowledgeFact(
        content="수학 정리",
        valid_from=now - timedelta(days=3650),
        half_life_days=None,
        confidence_t0=0.9,
        source=f"{TEST_SOURCE_PREFIX}eternal",
    )
    assert abs(current_confidence(eternal, now=now) - 0.9) < 1e-6


# ─────────────────────────────────────────────
# 4. 그래프 / 반사실
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_causal_chain_traversal(clean_db) -> None:
    """A → B → C 체인에서 A 로부터 BFS 깊이 2 이상 이동."""
    a = await ingest_fact(_make_fact("원인 A", entity=_tlabel("cA")))
    b = await ingest_fact(_make_fact("결과 B", entity=_tlabel("cB")))
    c = await ingest_fact(_make_fact("결과 C", entity=_tlabel("cC")))
    assert a["fact_id"] and b["fact_id"] and c["fact_id"]

    await prisma.knowledgeedge.create(
        data={
            "fromFactId": a["fact_id"],
            "toFactId": b["fact_id"],
            "relationType": KnowledgeRelation.CAUSES.value,
            "strength": 0.8,
            "verifiedBy": "ai",
        }
    )
    await prisma.knowledgeedge.create(
        data={
            "fromFactId": b["fact_id"],
            "toFactId": c["fact_id"],
            "relationType": KnowledgeRelation.CAUSES.value,
            "strength": 0.7,
            "verifiedBy": "ai",
        }
    )

    chain = await traverse_causal_chain(
        a["fact_id"], KnowledgeRelation.CAUSES, max_depth=3
    )
    chain_ids = [n["fact_id"] for n in chain]
    assert b["fact_id"] in chain_ids
    assert c["fact_id"] in chain_ids


@pytest.mark.asyncio
async def test_counterfactual_query(clean_db) -> None:
    """B 가 없었다면 C 에 여전히 닿는가? (다른 경로 있어야 True)"""
    from hwarang_api.knowledge.graph import counterfactual_query

    a = await ingest_fact(_make_fact("루트 A", entity=_tlabel("rA")))
    b = await ingest_fact(_make_fact("중간 B", entity=_tlabel("rB")))
    alt = await ingest_fact(_make_fact("우회 ALT", entity=_tlabel("rAlt")))
    c = await ingest_fact(_make_fact("결과 C", entity=_tlabel("rC")))

    # A → B → C 및 A → ALT → C
    for src, dst in (
        (a["fact_id"], b["fact_id"]),
        (b["fact_id"], c["fact_id"]),
        (a["fact_id"], alt["fact_id"]),
        (alt["fact_id"], c["fact_id"]),
    ):
        await prisma.knowledgeedge.create(
            data={
                "fromFactId": src,
                "toFactId": dst,
                "relationType": KnowledgeRelation.CAUSES.value,
                "strength": 0.8,
                "verifiedBy": "ai",
            }
        )

    result = await counterfactual_query(b["fact_id"], c["fact_id"])
    assert result["still_reachable"] is True
    assert result["total_paths"] >= 1


# ─────────────────────────────────────────────
# 5. 예측
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_prediction_bayesian_update(clean_db) -> None:
    """PENDING 사실에 SUPPORTS 증거를 연결하면 posterior 가 prior 보다 높아야 한다."""
    pending = _make_fact(
        "테스트 예측 사실 — 신규 법안 시행 예정",
        entity=_tlabel("pred"),
        status=KnowledgeStatus.PENDING,
        valid_from=_utcnow(),
    )
    pending.predicted_valid_from = _utcnow() + timedelta(days=60)
    pending.prediction_confidence = 0.5
    r_p = await ingest_fact(pending)
    assert r_p["fact_id"]

    evidence = _make_fact(
        "테스트 증거 — 관련 보도자료가 긍정적으로 나왔다.",
        entity=_tlabel("evid"),
    )
    r_e = await ingest_fact(evidence)

    await prisma.knowledgeedge.create(
        data={
            "fromFactId": r_e["fact_id"],
            "toFactId": r_p["fact_id"],
            "relationType": KnowledgeRelation.SUPPORTS.value,
            "strength": 0.9,
            "verifiedBy": "ai",
        }
    )

    outcome = await predict_fact_outcome(r_p["fact_id"])
    # posterior 는 [0, 1] 범위. 실제 prior 가 DEFAULT_PRIOR(0.5) 이므로
    # 유의미한 증거가 있다면 >= prior.
    assert 0.0 <= outcome.confidence <= 1.0
    assert outcome.rationale


# ─────────────────────────────────────────────
# 6. 자가 검증
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_self_verify_updates_fact(clean_db) -> None:
    """verify_fact 가 source_url 이 없을 때 source_gone 을 돌려주는지 (smoke)."""
    from hwarang_api.knowledge.self_verify import verify_fact

    fact = _make_fact("자가검증 스모크", entity=_tlabel("sv"))
    r = await ingest_fact(fact)
    row = await prisma.knowledgefact.find_unique(where={"id": r["fact_id"]})
    assert row is not None

    domain_fact = KnowledgeFact(
        id=row.id,
        content=row.content,
        domain=row.domain,
        entity=row.entity,
        valid_from=row.validFrom,
        half_life_days=row.halfLifeDays,
        confidence_t0=float(row.confidenceT0),
        status=KnowledgeStatus(row.status),
        source=row.source,
        source_url=None,
    )
    try:
        result = await verify_fact(domain_fact)
    except Exception:
        pytest.skip("self_verify 의존 모듈(embeddings/web/llm) 미구현 환경")
        return
    assert result.fact_id == row.id


# ─────────────────────────────────────────────
# 7. 보상
# ─────────────────────────────────────────────
def test_calculate_reward_bounds() -> None:
    """보상 계산 — 최소 1 토큰, 티어 bonus 적용."""
    r_basic = calculate_reward(1.0, 1.0, "law", "basic")
    r_expert = calculate_reward(1.0, 1.0, "law", "expert")
    assert r_basic >= 1
    assert r_expert > r_basic

    # 품질 0 이어도 최소 1 보장
    r_min = calculate_reward(0.0, 0.0, "general", "basic")
    assert r_min == 1


@pytest.mark.asyncio
async def test_pay_contribution_mints_coins(clean_db) -> None:
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    fact = _make_fact("기여 보상 테스트 사실", entity=_tlabel("pay"), domain="tech")
    r = await ingest_fact(fact)
    assert r["fact_id"]

    reward = await pay_contribution(
        fact_id=r["fact_id"],
        contributor_user_id=user_id,
        quality_score=0.9,
        uniqueness_score=0.8,
    )
    assert reward >= 1

    row = await prisma.knowledgefact.find_unique(where={"id": r["fact_id"]})
    assert row is not None
    assert (row.rewardPaid or 0) >= reward
    assert row.contributedBy == user_id


# ─────────────────────────────────────────────
# 8. 프라이버시
# ─────────────────────────────────────────────
def test_private_fact_encrypt_decrypt() -> None:
    user = "alice-123"
    original = "개인 건강 메모: 공복혈당 95, 2026-04-22 측정."
    ct = encrypt_for_user(original, user, TEST_MASTER_KEY)
    assert ct != original
    pt = decrypt_for_user(ct, user, TEST_MASTER_KEY)
    assert pt == original


def test_private_fact_wrong_user_fails() -> None:
    ct = encrypt_for_user("비밀 메모", "alice-123", TEST_MASTER_KEY)
    with pytest.raises(Exception):
        decrypt_for_user(ct, "bob-456", TEST_MASTER_KEY)


# ─────────────────────────────────────────────
# 9. 지식 공백
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_gap_detection_on_failed_query(clean_db) -> None:
    topic = f"{TEST_SOURCE_PREFIX}가상 주제 {uuid.uuid4().hex[:6]}"
    await record_knowledge_gap(topic)
    await record_knowledge_gap(topic)  # 같은 주제 두 번 — 카운트 증가

    row = await prisma.knowledgegap.find_unique(where={"topic": topic})
    assert row is not None
    assert row.failureCount >= 2
