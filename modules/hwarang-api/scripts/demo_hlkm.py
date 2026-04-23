"""HLKM 기능 데모 (스탠드얼론).

실제 DB/LLM 없이 메모리 상의 dict 만으로 HLKM 의 핵심 동작을 시연한다.

시연 단계:
    1) 사실 추가 (최저시급 2024/2025/2026)
    2) 시간 여행 검색 (2024 시점)
    3) 모순 감지 (충돌 값 입력)
    4) 인과 그래프 (임금→편의점비→상품가)
    5) 예측 (주4.5일제 PENDING 베이지안 업데이트)
    6) 자가 검증 (오래된 사실에 valid_to 설정)
    7) 기여 보상 계산 (코인 민팅 시뮬레이션)

실행:
    python -m scripts.demo_hlkm
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# ─────────────────────────────────────────────
# 색상 헬퍼 (ANSI). 비 TTY 환경이면 그대로 print.
# ─────────────────────────────────────────────
_C_HEAD = "\033[1;36m"
_C_OK = "\033[32m"
_C_WARN = "\033[33m"
_C_INFO = "\033[34m"
_C_DIM = "\033[2m"
_C_END = "\033[0m"


def head(title: str) -> None:
    print(f"\n{_C_HEAD}━━━ {title} ━━━{_C_END}")


def ok(msg: str) -> None:
    print(f"  {_C_OK}✓{_C_END} {msg}")


def info(msg: str) -> None:
    print(f"  {_C_INFO}ℹ{_C_END} {msg}")


def warn(msg: str) -> None:
    print(f"  {_C_WARN}⚠{_C_END} {msg}")


def dim(msg: str) -> None:
    print(f"  {_C_DIM}{msg}{_C_END}")


# ─────────────────────────────────────────────
# In-memory 스토어
# ─────────────────────────────────────────────
@dataclass
class Fact:
    id: str
    content: str
    entity: str
    domain: str
    valid_from: datetime
    valid_to: datetime | None = None
    last_verified_at: datetime | None = None
    half_life_days: int | None = 365
    confidence_t0: float = 1.0
    status: str = "CONFIRMED"
    source: str = "demo"
    predicted_valid_from: datetime | None = None
    prediction_confidence: float | None = None


@dataclass
class Edge:
    from_id: str
    to_id: str
    relation: str
    strength: float = 0.8
    evidence: str | None = None


@dataclass
class Store:
    facts: dict[str, Fact] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add(self, f: Fact) -> Fact:
        self.facts[f.id] = f
        return f

    def by_entity(self, entity: str) -> list[Fact]:
        return [f for f in self.facts.values() if f.entity == entity]


STORE = Store()


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _id_of(content: str) -> str:
    return "f_" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]


# ─────────────────────────────────────────────
# 1. 사실 추가
# ─────────────────────────────────────────────
async def step1_ingest() -> None:
    head("1단계 · 사실 추가 (최저시급 이력)")
    data = [
        ("2024년 대한민국 최저시급은 9,860원이다.", _utc(2024, 1, 1), _utc(2024, 12, 31)),
        ("2025년 대한민국 최저시급은 10,030원이다.", _utc(2025, 1, 1), _utc(2025, 12, 31)),
        ("2026년 대한민국 최저시급은 10,320원이다.", _utc(2026, 1, 1), None),
    ]
    for content, vf, vt in data:
        f = Fact(
            id=_id_of(content),
            content=content,
            entity="minimum_wage_kr",
            domain="law",
            valid_from=vf,
            valid_to=vt,
            last_verified_at=vf,
            half_life_days=1825,
            source="고용노동부 고시",
        )
        STORE.add(f)
        ok(f"insert {f.id}  vf={vf.date()}  vt={vt.date() if vt else 'NOW'}")


# ─────────────────────────────────────────────
# 2. 시간 여행 검색
# ─────────────────────────────────────────────
async def step2_time_travel() -> None:
    head("2단계 · 시간 여행 검색 (as_of=2024-06-15)")
    as_of = _utc(2024, 6, 15)
    matches = [
        f for f in STORE.by_entity("minimum_wage_kr")
        if f.valid_from <= as_of and (f.valid_to is None or f.valid_to > as_of)
    ]
    for f in matches:
        ok(f"{as_of.date()} 시점 유효: {f.content}")
    info(f"{len(matches)}건 일치. 현재(2026) 값이 아닌 당시 값을 돌려준다는 점에 주목.")


# ─────────────────────────────────────────────
# 3. 모순 감지
# ─────────────────────────────────────────────
def _simple_sim(a: str, b: str) -> float:
    """단어 Jaccard — 임베딩 대용."""
    wa, wb = set(a.split()), set(b.split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _extract_numbers(text: str) -> set[str]:
    import re
    return {m.group(1).replace(",", "") for m in re.finditer(r"(\d[\d,]*)", text)}


async def step3_contradiction() -> None:
    head("3단계 · 모순 감지 ('2024 최저시급 11,000원' 입력)")
    conflicting = Fact(
        id=_id_of("2024년 최저시급 11,000원"),
        content="2024년 대한민국 최저시급은 11,000원이다.",
        entity="minimum_wage_kr",
        domain="law",
        valid_from=_utc(2024, 1, 1),
        source="unverified_blog",
    )

    # L1 유사도
    existing_2024 = next(
        f for f in STORE.by_entity("minimum_wage_kr") if f.valid_from == _utc(2024, 1, 1)
    )
    sim = _simple_sim(conflicting.content, existing_2024.content)

    # L2 규칙
    same_entity = conflicting.entity == existing_2024.entity
    overlap = (
        conflicting.valid_from <= (existing_2024.valid_to or _utcnow().replace(year=9999))
        and existing_2024.valid_from <= (conflicting.valid_to or _utcnow().replace(year=9999))
    )
    nums_a = _extract_numbers(conflicting.content)
    nums_b = _extract_numbers(existing_2024.content)
    differing_nums = (nums_a | nums_b) - (nums_a & nums_b)
    rule_signal = 0.0
    if same_entity:
        rule_signal += 0.35
    if overlap:
        rule_signal += 0.2
    if differing_nums:
        rule_signal += 0.25

    info(f"L1 유사도: sim={sim:.2f}")
    info(f"L2 규칙 신호: {rule_signal:.2f} (동일엔티티={same_entity}, 겹침={overlap}, 숫자차={sorted(differing_nums)})")
    final = 0.4 * sim + 0.4 * rule_signal + 0.2 * 1.0  # L3 LLM 긍정 가정
    if final > 0.45 and differing_nums:
        warn(f"모순 감지! 최종 신뢰도={final:.2f} → DISPUTED 상태로 저장")
        conflicting.status = "DISPUTED"
        STORE.add(conflicting)
        STORE.edges.append(
            Edge(
                existing_2024.id,
                conflicting.id,
                "CONTRADICTS",
                strength=final,
                evidence=f"숫자 차이 {sorted(differing_nums)}",
            )
        )
    else:
        ok(f"모순 아님 (conf={final:.2f})")


# ─────────────────────────────────────────────
# 4. 인과 그래프
# ─────────────────────────────────────────────
async def step4_causal_graph() -> None:
    head("4단계 · 인과 그래프 (임금 → 편의점 운영비 → 상품 가격)")
    wage_2026 = next(
        f for f in STORE.by_entity("minimum_wage_kr") if f.valid_from == _utc(2026, 1, 1)
    )
    cvs = STORE.add(
        Fact(
            id=_id_of("편의점 운영비 상승"),
            content="2026년 최저시급 인상으로 편의점 운영비가 약 4% 상승.",
            entity="cvs_operating_cost",
            domain="market_price",
            valid_from=_utc(2026, 1, 1),
            half_life_days=180,
        )
    )
    goods = STORE.add(
        Fact(
            id=_id_of("편의점 가격 인상"),
            content="편의점 대표 품목 평균 가격이 2026년 상반기에 2.5% 인상되었다.",
            entity="cvs_goods_price",
            domain="market_price",
            valid_from=_utc(2026, 4, 1),
            half_life_days=180,
        )
    )
    STORE.edges.append(Edge(wage_2026.id, cvs.id, "CAUSES", 0.7))
    STORE.edges.append(Edge(cvs.id, goods.id, "CAUSES", 0.6))

    # BFS 깊이 3
    from collections import deque

    start = wage_2026.id
    visited = {start}
    queue: deque[tuple[str, int, list[str], float]] = deque([(start, 0, [start], 1.0)])
    ok(f"루트: {wage_2026.content[:40]}…")
    while queue:
        node, depth, path, strength = queue.popleft()
        if depth >= 3:
            continue
        for e in STORE.edges:
            if e.from_id == node and e.relation == "CAUSES" and e.to_id not in visited:
                visited.add(e.to_id)
                new_strength = strength * e.strength
                child = STORE.facts[e.to_id]
                indent = "  " * (depth + 1)
                print(
                    f"    {indent}→ d={depth + 1}  s={new_strength:.2f}  "
                    f"{child.content[:50]}…"
                )
                queue.append((e.to_id, depth + 1, path + [e.to_id], new_strength))


# ─────────────────────────────────────────────
# 5. 예측 (베이지안)
# ─────────────────────────────────────────────
def _bayesian_update(prior: float, likelihoods: list[tuple[float, float]]) -> float:
    p = max(1e-9, min(1 - 1e-9, prior))
    for p_eh, p_enh in likelihoods:
        p_eh = max(1e-9, min(1 - 1e-9, p_eh))
        p_enh = max(1e-9, min(1 - 1e-9, p_enh))
        num = p_eh * p
        den = num + p_enh * (1 - p)
        if den > 0:
            p = num / den
    return p


async def step5_prediction() -> None:
    head("5단계 · 예측 (주 4.5일제 PENDING)")
    pending = STORE.add(
        Fact(
            id=_id_of("주4.5일제 전면 시행 예정"),
            content="주 4.5일제 전면 시행이 2027년 1월 1일 예정.",
            entity="four_and_half_day_week_full",
            domain="law",
            valid_from=_utc(2026, 4, 1),
            status="PENDING",
            predicted_valid_from=_utc(2027, 1, 1),
            prediction_confidence=0.4,
            half_life_days=1825,
        )
    )
    prior = 0.4
    info(f"prior P(H) = {prior:.2f}  (과거 입법 예고 → 시행 전환율)")

    likelihoods = [
        (0.75, 0.30),  # 고용노동부 긍정 브리핑 (SUPPORTS)
        (0.65, 0.35),  # 대기업 시범 성공 사례 (DERIVED_FROM)
        (0.60, 0.40),  # 공공부문 만족도 설문 (SUPPORTS)
    ]
    for p_eh, p_enh in likelihoods:
        info(f"evidence: P(E|H)={p_eh:.2f}, P(E|¬H)={p_enh:.2f}")

    posterior = _bayesian_update(prior, likelihoods)
    pending.prediction_confidence = posterior
    ok(f"posterior P(H|E₁…Eₙ) = {posterior:.2f} (prior 대비 {'↑' if posterior > prior else '↓'})")
    info(f"예상 시행일: {pending.predicted_valid_from.date()}")


# ─────────────────────────────────────────────
# 6. 자가 검증 (retire older)
# ─────────────────────────────────────────────
async def step6_self_verify() -> None:
    head("6단계 · 자가 검증 (오래된 사실 valid_to 설정)")
    # 2024 최저시급은 이미 vt 가 있음. 최저시급 2025 를 강제로 만료시키는 시뮬레이션.
    target = next(f for f in STORE.by_entity("minimum_wage_kr") if f.valid_from == _utc(2025, 1, 1))
    info(f"대상: {target.content}")
    info("출처 재인출 → 2026년 고시로 대체됨 확인")
    target.valid_to = _utc(2025, 12, 31)
    target.status = "EXPIRED"
    ok(f"valid_to={target.valid_to.date()} 로 갱신, status=EXPIRED")

    # 신뢰도 감쇠 시연
    now = _utcnow()
    age_days = (now - (target.last_verified_at or target.valid_from)).total_seconds() / 86400
    half = target.half_life_days or 365
    decay = 0.5 ** (age_days / half)
    dim(f"age={age_days:.0f}d, half_life={half}d → confidence*{decay:.3f}")


# ─────────────────────────────────────────────
# 7. 기여 보상
# ─────────────────────────────────────────────
_BASE_REWARD = {"law": 100, "medical": 150, "tech": 50, "general": 20}
_TIER_BONUS = {"basic": 1.0, "verified": 1.3, "expert": 1.8}


def _calc_reward(quality: float, uniqueness: float, domain: str, tier: str) -> int:
    q = max(0.0, min(1.0, quality))
    u = max(0.0, min(1.0, uniqueness))
    base = _BASE_REWARD.get(domain, _BASE_REWARD["general"])
    bonus = _TIER_BONUS.get(tier, 1.0)
    return max(1, int(round(base * q * u * bonus)))


async def step7_reward() -> None:
    head("7단계 · 기여 보상 (코인 민팅 시뮬레이션)")
    cases = [
        ("user_alice", "law", "expert", 0.95, 0.80),
        ("user_bob", "tech", "verified", 0.85, 0.60),
        ("user_chris", "general", "basic", 0.70, 0.50),
    ]
    total = 0
    for user, domain, tier, q, u in cases:
        r = _calc_reward(q, u, domain, tier)
        total += r
        ok(
            f"{user} [{domain}/{tier}] quality={q:.2f} uniq={u:.2f}"
            f"  → {r} HWARANG 토큰"
        )
    info(f"총 민팅 예정 토큰: {total}")


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
async def main() -> None:
    print(f"{_C_HEAD}HLKM 데모 — Hwarang Living Knowledge Mesh{_C_END}")
    print(f"{_C_DIM}(메모리 모의 저장소, DB/LLM 미사용){_C_END}")
    await step1_ingest()
    await step2_time_travel()
    await step3_contradiction()
    await step4_causal_graph()
    await step5_prediction()
    await step6_self_verify()
    await step7_reward()

    head("요약")
    ok(f"팩트 {len(STORE.facts)}개, 엣지 {len(STORE.edges)}개 생성")
    dim("다음 단계: scripts/seed_hlkm.py --reset 로 실제 DB 에 반영하세요.")


if __name__ == "__main__":
    asyncio.run(main())
