"""HLKM 시드 스크립트.

실제 한국 도메인 지식(법률, 기술, 의료, 시세)과 예측/갭/충돌 레코드를
DB 에 주입한다. 통합 테스트·데모·개발 환경에서 재현 가능한 상태를
만들기 위한 용도.

사용:
    python -m scripts.seed_hlkm
    python -m scripts.seed_hlkm --reset   # 기존 HLKM 테이블 비우고 시드

각 카테고리별 함수는 high-level `ingest_fact()` 를 사용해 파이프라인
로직(중복·모순·재검증 스케줄링)을 함께 검증한다. 엣지·갭·충돌은 전용
헬퍼가 없어 raw prisma 로 기록한다.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# .env 자동 로드 (DATABASE_URL 을 prisma 가 읽게)
try:
    from dotenv import load_dotenv

    _here = Path(__file__).resolve().parent.parent  # modules/hwarang-api/
    for candidate in [_here / ".env", _here.parent / "hwarang-web" / ".env"]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
except ImportError:
    pass

if not os.getenv("DATABASE_URL"):
    print("❌ DATABASE_URL 이 설정되지 않았습니다. .env 파일 또는 환경변수로 지정하세요.", file=sys.stderr)
    sys.exit(1)

from hwarang_api.db import prisma
from hwarang_api.knowledge import (
    KnowledgeFact,
    KnowledgeRelation,
    KnowledgeStatus,
    KnowledgeVisibility,
    ingest_fact,
)

# 시드 과정에서 생성한 ingest_fact 결과를 라벨로 추적하기 위한 레지스트리.
# 엣지 연결 시 동일 내용 기반으로 fact_id 를 다시 찾아 쓴다.
_REG: dict[str, str] = {}


def _utc(year: int, month: int, day: int) -> datetime:
    """시드 날짜를 UTC aware 로 반환."""
    return datetime(year, month, day, tzinfo=timezone.utc)


async def _ingest(
    label: str,
    content: str,
    *,
    domain: str,
    entity: str,
    valid_from: datetime,
    valid_to: datetime | None = None,
    half_life_days: int | None = None,
    source: str = "고용노동부 고시",
    source_type: str = "official",
    tags: list[str] | None = None,
    status: KnowledgeStatus = KnowledgeStatus.CONFIRMED,
    predicted_valid_from: datetime | None = None,
    prediction_confidence: float | None = None,
    confidence_t0: float = 1.0,
) -> str | None:
    """단일 사실을 생성하고 라벨→id 매핑을 저장한다."""
    fact = KnowledgeFact(
        content=content,
        domain=domain,
        entity=entity,
        tags=tags or [],
        valid_from=valid_from,
        valid_to=valid_to,
        half_life_days=half_life_days,
        source=source,
        source_type=source_type,  # type: ignore[arg-type]
        status=status,
        predicted_valid_from=predicted_valid_from,
        prediction_confidence=prediction_confidence,
        confidence_t0=confidence_t0,
        visibility=KnowledgeVisibility.PUBLIC,
    )
    result = await ingest_fact(fact)
    fact_id = result.get("fact_id")
    if fact_id:
        _REG[label] = fact_id
    print(
        f"  [{result.get('action', '?'):>10}] {label:<40} → {fact_id or '(dry)'}"
    )
    return fact_id


# ─────────────────────────────────────────────
# 리셋
# ─────────────────────────────────────────────
async def reset_hlkm() -> None:
    """HLKM 관련 테이블을 모두 비운다. 파괴적 작업이므로 --reset 필요."""
    print(">>> HLKM 테이블 초기화 중…")
    # 외래키 역순으로 삭제
    for model in (
        "knowledgecontribution",
        "knowledgeconflict",
        "knowledgeverification",
        "knowledgeedge",
        "knowledgegap",
        "knowledgefact",
    ):
        try:
            deleted = await getattr(prisma, model).delete_many()
            print(f"    - {model}: {deleted} rows deleted")
        except Exception as exc:  # noqa: BLE001
            print(f"    ! {model}: {exc}")
    print(">>> 초기화 완료.\n")


# ─────────────────────────────────────────────
# 법률
# ─────────────────────────────────────────────
async def seed_law_facts() -> None:
    """법률 도메인 시드 — 최저시급 이력 + 근로기준법/중대재해법."""
    print("[law] 법률 사실 시드…")

    # 최저시급 2020 ~ 2026 (엔티티=minimum_wage_kr)
    wages = [
        ("wage_2020", "2020년 대한민국 최저시급은 8,590원이다.", _utc(2020, 1, 1), _utc(2020, 12, 31)),
        ("wage_2021", "2021년 대한민국 최저시급은 8,720원이다.", _utc(2021, 1, 1), _utc(2021, 12, 31)),
        ("wage_2022", "2022년 대한민국 최저시급은 9,160원이다.", _utc(2022, 1, 1), _utc(2022, 12, 31)),
        ("wage_2023", "2023년 대한민국 최저시급은 9,620원이다.", _utc(2023, 1, 1), _utc(2023, 12, 31)),
        ("wage_2024", "2024년 대한민국 최저시급은 9,860원이다.", _utc(2024, 1, 1), _utc(2024, 12, 31)),
        ("wage_2025", "2025년 대한민국 최저시급은 10,030원이다.", _utc(2025, 1, 1), _utc(2025, 12, 31)),
        ("wage_2026", "2026년 대한민국 최저시급은 10,320원이다.", _utc(2026, 1, 1), None),
    ]
    for label, content, vf, vt in wages:
        await _ingest(
            label,
            content,
            domain="law",
            entity="minimum_wage_kr",
            valid_from=vf,
            valid_to=vt,
            half_life_days=1825,
            source="고용노동부 고시",
            tags=["최저임금", "노동"],
        )

    # 근로기준법 개정 — 주 52시간제 2019
    await _ingest(
        "labor_52h_2019",
        "근로기준법 개정으로 주 52시간 근무제가 2019년부터 단계적 시행되었다.",
        domain="law",
        entity="labor_standards_act",
        valid_from=_utc(2019, 4, 1),
        valid_to=None,
        half_life_days=1825,
        source="국회 본회의 의결",
        tags=["근로기준법", "주52시간"],
    )

    # 주 4.5일제 시범 2026
    await _ingest(
        "labor_45d_2026",
        "2026년부터 공공부문 및 일부 대기업에서 주 4.5일제 시범 시행이 시작되었다.",
        domain="law",
        entity="four_and_half_day_week",
        valid_from=_utc(2026, 1, 1),
        valid_to=None,
        half_life_days=1825,
        source="고용노동부 시범사업 공고",
        tags=["주4.5일제", "근로기준법"],
    )

    # 중대재해법 2022
    await _ingest(
        "severe_accident_2022",
        "중대재해처벌법이 2022년 1월 27일부터 50인 이상 사업장에 시행되었다.",
        domain="law",
        entity="severe_accident_act",
        valid_from=_utc(2022, 1, 27),
        valid_to=None,
        half_life_days=1825,
        source="고용노동부 고시",
        tags=["중대재해법", "산업안전"],
    )


# ─────────────────────────────────────────────
# 기술
# ─────────────────────────────────────────────
async def seed_tech_facts() -> None:
    """기술 도메인 — 프레임워크/라이브러리 릴리스."""
    print("[tech] 기술 사실 시드…")
    await _ingest(
        "nextjs_14",
        "Next.js 14 가 2023년 10월 26일 정식 출시되었다. Server Actions GA 포함.",
        domain="tech",
        entity="nextjs",
        valid_from=_utc(2023, 10, 26),
        valid_to=_utc(2024, 10, 21),
        half_life_days=180,
        source="Vercel 공식 블로그",
        source_type="official",
        tags=["framework", "react"],
    )
    await _ingest(
        "nextjs_15",
        "Next.js 15 가 2024년 10월 21일 정식 출시되었다. React 19 지원, Turbopack 안정화.",
        domain="tech",
        entity="nextjs",
        valid_from=_utc(2024, 10, 21),
        valid_to=None,
        half_life_days=180,
        source="Vercel 공식 블로그",
        source_type="official",
        tags=["framework", "react"],
    )
    await _ingest(
        "react_18",
        "React 18 이 2022년 3월 29일 릴리스되었다. Concurrent Features 도입.",
        domain="tech",
        entity="react",
        valid_from=_utc(2022, 3, 29),
        valid_to=_utc(2024, 12, 5),
        half_life_days=180,
        source="React 공식 블로그",
        source_type="official",
        tags=["library", "ui"],
    )
    await _ingest(
        "react_19",
        "React 19 가 2024년 12월 5일 릴리스되었다. Actions/useOptimistic/메타데이터 통합 포함.",
        domain="tech",
        entity="react",
        valid_from=_utc(2024, 12, 5),
        valid_to=None,
        half_life_days=180,
        source="React 공식 블로그",
        source_type="official",
        tags=["library", "ui"],
    )


# ─────────────────────────────────────────────
# 의료
# ─────────────────────────────────────────────
async def seed_medical_facts() -> None:
    """의료 가이드라인 — 코로나19 격리 권고 2020 vs 2023."""
    print("[medical] 의료 가이드라인 시드…")
    await _ingest(
        "covid_iso_2020",
        "코로나19 확진자는 최소 14일 격리하는 것을 원칙으로 한다 (2020년 질병관리본부 지침).",
        domain="medical",
        entity="covid_isolation_guideline",
        valid_from=_utc(2020, 3, 1),
        valid_to=_utc(2023, 6, 1),
        half_life_days=730,
        source="질병관리본부 2020 코로나19 대응 지침",
        source_type="official",
        tags=["COVID-19", "격리", "가이드라인"],
    )
    await _ingest(
        "covid_iso_2023",
        "코로나19 확진자는 권고사항으로 5일 자가격리를 유지한다 (2023년 질병관리청 개정 지침).",
        domain="medical",
        entity="covid_isolation_guideline",
        valid_from=_utc(2023, 6, 1),
        valid_to=None,
        half_life_days=730,
        source="질병관리청 2023 코로나19 관리 지침",
        source_type="official",
        tags=["COVID-19", "격리", "가이드라인"],
    )


# ─────────────────────────────────────────────
# 시장가격 (초단기 half-life)
# ─────────────────────────────────────────────
async def seed_market_facts() -> None:
    """시세 — 삼성전자 주가 3일치."""
    print("[market_price] 시세 시드…")
    prices = [
        ("samsung_20260421", "삼성전자(005930) 2026-04-21 종가는 82,300원이다.", _utc(2026, 4, 21)),
        ("samsung_20260422", "삼성전자(005930) 2026-04-22 종가는 83,100원이다.", _utc(2026, 4, 22)),
        ("samsung_20260423", "삼성전자(005930) 2026-04-23 종가는 82,700원이다.", _utc(2026, 4, 23)),
    ]
    for label, content, day in prices:
        await _ingest(
            label,
            content,
            domain="market_price",
            entity="samsung_electronics_005930",
            valid_from=day,
            valid_to=day + timedelta(days=1),
            half_life_days=1,
            source="KRX 장마감 데이터",
            source_type="official",
            tags=["stock", "KRX"],
        )


# ─────────────────────────────────────────────
# 예측
# ─────────────────────────────────────────────
async def seed_pending_predictions() -> None:
    """아직 확정되지 않은 예측 사실."""
    print("[pending] 예측 사실 시드…")
    await _ingest(
        "pred_45d_full",
        "주 4.5일제 전면 시행이 2027년 1월 1일에 예정되어 있다 (관계부처 협의 중).",
        domain="law",
        entity="four_and_half_day_week_full",
        valid_from=_utc(2026, 4, 1),  # 의제 발효 시점
        valid_to=None,
        half_life_days=1825,
        source="고용노동부 보도자료",
        source_type="official",
        tags=["주4.5일제", "입법예고"],
        status=KnowledgeStatus.PENDING,
        predicted_valid_from=_utc(2027, 1, 1),
        prediction_confidence=0.4,
        confidence_t0=0.4,
    )
    await _ingest(
        "pred_bok_rate_cut",
        "한국은행 기준금리 0.25bp 인하가 2026년 6월 금통위에서 결정될 것으로 예상된다.",
        domain="law",
        entity="bok_base_rate",
        valid_from=_utc(2026, 4, 10),
        valid_to=None,
        half_life_days=30,
        source="한국은행 통화정책 브리핑",
        source_type="official",
        tags=["기준금리", "통화정책"],
        status=KnowledgeStatus.PENDING,
        predicted_valid_from=_utc(2026, 6, 1),
        prediction_confidence=0.6,
        confidence_t0=0.6,
    )


# ─────────────────────────────────────────────
# 엣지 (raw prisma)
# ─────────────────────────────────────────────
async def _create_edge(
    from_label: str,
    to_label: str,
    relation: KnowledgeRelation,
    *,
    strength: float = 0.8,
    evidence: str | None = None,
) -> None:
    from_id = _REG.get(from_label)
    to_id = _REG.get(to_label)
    if not from_id or not to_id:
        print(f"    ! edge skip ({from_label} → {to_label}) — id 누락")
        return
    try:
        await prisma.knowledgeedge.create(
            data={
                "fromFactId": from_id,
                "toFactId": to_id,
                "relationType": relation.value,
                "strength": strength,
                "evidence": evidence,
                "verifiedBy": "ai",
            }
        )
        print(f"    edge  {from_label}  --[{relation.value}]-->  {to_label}")
    except Exception as exc:  # noqa: BLE001
        print(f"    ! edge create failed ({from_label} → {to_label}): {exc}")


async def seed_edges() -> None:
    """엣지 시드. 가상 후행 사실(편의점 비용, 건설업 안전 비용)도 함께 추가."""
    print("[edges] 엣지 시드…")

    # 가상 파급효과 사실 (엣지의 to_fact 노드)
    await _ingest(
        "cvs_cost_up",
        "2026년 최저시급 인상에 따라 편의점 평균 운영비가 약 4% 상승한 것으로 추정된다.",
        domain="market_price",
        entity="cvs_operating_cost",
        valid_from=_utc(2026, 1, 1),
        valid_to=None,
        half_life_days=180,
        source="편의점산업협회 분석",
        source_type="community",
        tags=["편의점", "운영비"],
    )
    await _ingest(
        "construction_safety_cost",
        "중대재해법 시행 이후 건설업 안전관리 비용이 평균 12% 증가한 것으로 조사되었다.",
        domain="market_price",
        entity="construction_safety_cost",
        valid_from=_utc(2022, 6, 1),
        valid_to=None,
        half_life_days=365,
        source="건설산업연구원 보고서",
        source_type="community",
        tags=["건설업", "안전", "중대재해법"],
    )

    await _create_edge("wage_2026", "cvs_cost_up", KnowledgeRelation.CAUSES, strength=0.7)
    await _create_edge(
        "severe_accident_2022",
        "construction_safety_cost",
        KnowledgeRelation.CAUSES,
        strength=0.85,
    )
    # KnowledgeRelation 에는 SUPERSEDES 가 없으므로 TEMPORAL_AFTER + ALTERNATIVE_TO 로 표현.
    await _create_edge(
        "nextjs_15",
        "nextjs_14",
        KnowledgeRelation.TEMPORAL_AFTER,
        strength=1.0,
        evidence="Next.js 15 가 14 의 후속 안정 버전",
    )
    await _create_edge(
        "covid_iso_2020",
        "covid_iso_2023",
        KnowledgeRelation.CONTRADICTS,
        strength=0.9,
        evidence="격리 기간 14일 → 5일로 대체",
    )


# ─────────────────────────────────────────────
# 갭
# ─────────────────────────────────────────────
async def seed_gaps() -> None:
    """자주 실패하는 질의 주제(knowledge gap)."""
    print("[gaps] 지식 공백 시드…")
    now = datetime.now(timezone.utc)
    gaps = [
        ("주휴수당 계산 법률", 7),
        ("개인정보보호법 2025 개정", 4),
        ("AI 저작권법", 12),
    ]
    for topic, failure_count in gaps:
        try:
            await prisma.knowledgegap.upsert(
                where={"topic": topic},
                data={
                    "create": {
                        "topic": topic,
                        "failureCount": failure_count,
                        "firstSeenAt": now - timedelta(days=failure_count),
                        "lastSeenAt": now,
                        "status": "open",
                    },
                    "update": {
                        "failureCount": failure_count,
                        "lastSeenAt": now,
                    },
                },
            )
            print(f"    gap: {topic} (failures={failure_count})")
        except Exception as exc:  # noqa: BLE001
            print(f"    ! gap upsert failed: {topic}: {exc}")


# ─────────────────────────────────────────────
# 충돌
# ─────────────────────────────────────────────
async def seed_conflicts() -> None:
    """코로나 격리 지침 모순 기록."""
    print("[conflicts] 충돌 시드…")
    a = _REG.get("covid_iso_2020")
    b = _REG.get("covid_iso_2023")
    if not a or not b:
        print("    ! covid 팩트 id 없음 — 충돌 시드 스킵")
        return
    try:
        await prisma.knowledgeconflict.create(
            data={
                "factAId": a,
                "factBId": b,
                "resolutionState": "open",
                "resolutionNote": "격리 기간 상충 — 14일(2020) vs 5일(2023). 시점별 적용으로 실무상 자연 해소.",
            }
        )
        print("    conflict: covid_iso_2020 ⇔ covid_iso_2023")
    except Exception as exc:  # noqa: BLE001
        print(f"    ! conflict create failed: {exc}")


# ─────────────────────────────────────────────
# 엔트리포인트
# ─────────────────────────────────────────────
async def seed(reset: bool = False) -> None:
    print(">>> HLKM 시드 시작")
    await prisma.connect()
    try:
        if reset:
            await reset_hlkm()

        await seed_law_facts()
        await seed_tech_facts()
        await seed_medical_facts()
        await seed_market_facts()
        await seed_pending_predictions()
        await seed_edges()
        await seed_gaps()
        await seed_conflicts()

        print("\n>>> HLKM 시드 완료!")
        print(f"    총 등록 사실: {len(_REG)}")
    finally:
        await prisma.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(description="HLKM seed data loader")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="기존 HLKM 테이블을 모두 삭제 후 시드 (주의: 파괴적)",
    )
    args = parser.parse_args()
    asyncio.run(seed(reset=args.reset))
    return 0


if __name__ == "__main__":
    sys.exit(main())
