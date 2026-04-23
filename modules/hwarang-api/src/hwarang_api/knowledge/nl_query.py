"""HLKM ③ Natural Language Temporal Query.

자연어 질문에서 **시간 표현을 추출**해 구조화된 SearchQuery 로 변환한다.

지원 형식:
    - 절대 날짜: "2020년", "2024-01-15", "2025년 3월", "2023-7"
    - 상대 표현: "작년", "지난달", "이번 달", "내년", "어제", "지난주"
    - 기간 범위: "2020년부터 2023년까지", "2020~2023", "from 2020 to 2023"
    - 모호한 시기: "코로나 초기", "IMF 때" → LLM fallback
    - 도메인 힌트: "법률 관련", "의료"
    - 엔티티 힌트: "최저시급", "근로기준법"

LLM helper (선택적):
    아래 시그니처의 placeholder 가 `hwarang_api.knowledge.llm` 에 추가되면 사용된다.

    ``async def llm_extract_temporal(text: str, now_iso: str) -> dict:``

    반환 구조 예: `{"iso": "2020-03-01", "confidence": 0.8}` 또는 `{}`.
"""

from __future__ import annotations

import calendar
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .types import SearchQuery

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _floor_month(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _month_start(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=timezone.utc)


def _year_start(year: int) -> datetime:
    return datetime(year, 1, 1, tzinfo=timezone.utc)


def _year_end(year: int) -> datetime:
    return datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


def _month_end(year: int, month: int) -> datetime:
    last_day = calendar.monthrange(year, month)[1]
    return datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)


# ─────────────────────────────────────────────
# 정규식 (모듈 로드 시 컴파일)
# ─────────────────────────────────────────────
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_ISO_MONTH = re.compile(r"\b(\d{4})-(\d{1,2})\b")
_KO_YEAR_MONTH = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월")
_KO_YEAR = re.compile(r"(\d{4})\s*년")
_KO_YEAR_MONTH_DAY = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")

_RANGE_KO_YEAR_SPAN = re.compile(r"(\d{4})\s*년?\s*[부터~\-]+\s*(\d{4})\s*년?(?:까지)?")
_RANGE_EN = re.compile(r"from\s+(\d{4})(?:\s*-\s*(\d{1,2}))?\s+to\s+(\d{4})(?:\s*-\s*(\d{1,2}))?", re.I)

# 도메인 힌트 키워드
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "law": ["법률", "법", "법령", "조례", "근로기준법", "민법", "형법"],
    "medical_guideline": ["의료", "의학", "진료", "가이드라인", "치료"],
    "technology": ["기술", "IT", "소프트웨어", "AI", "인공지능", "프로그래밍"],
    "news": ["뉴스", "속보", "보도"],
    "market_price": ["가격", "시세", "환율", "주가"],
    "weather": ["날씨", "기온", "강수"],
}


# ─────────────────────────────────────────────
# Korean regex parser
# ─────────────────────────────────────────────
def extract_date_korean(text: str, now: datetime) -> datetime | None:
    """정규식 기반 한국어/영어 날짜 빠른 파서.

    인식 우선순위 (먼저 매치된 것이 승리):
        1. YYYY년 MM월 DD일
        2. YYYY-MM-DD
        3. YYYY년 MM월
        4. YYYY-MM
        5. YYYY년 / 4자리 연도
        6. 상대 표현 (작년, 어제, 지난주 등)

    매칭 실패 시 None.
    """
    t = text.strip()

    m = _KO_YEAR_MONTH_DAY.search(t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d, tzinfo=timezone.utc)
        except ValueError:
            pass

    m = _ISO_DATE.search(t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d, tzinfo=timezone.utc)
        except ValueError:
            pass

    m = _KO_YEAR_MONTH.search(t)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return _month_start(y, mo)

    m = _ISO_MONTH.search(t)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return _month_start(y, mo)

    m = _KO_YEAR.search(t)
    if m:
        return _year_start(int(m.group(1)))

    # 상대 표현
    if "어제" in t:
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if "오늘" in t:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if "내일" in t:
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if "지난주" in t or "저번주" in t:
        return (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    if "이번 주" in t or "이번주" in t:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if "다음 주" in t or "다음주" in t:
        return (now + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    if "지난달" in t or "저번달" in t:
        prev = _floor_month(now) - timedelta(days=1)
        return _month_start(prev.year, prev.month)
    if "이번 달" in t or "이번달" in t:
        return _month_start(now.year, now.month)
    if "다음 달" in t or "다음달" in t:
        nxt_year = now.year + (1 if now.month == 12 else 0)
        nxt_month = 1 if now.month == 12 else now.month + 1
        return _month_start(nxt_year, nxt_month)
    if "작년" in t or "지난해" in t:
        return _year_start(now.year - 1)
    if "올해" in t or "금년" in t:
        return _year_start(now.year)
    if "내년" in t or "다음해" in t:
        return _year_start(now.year + 1)
    if "재작년" in t:
        return _year_start(now.year - 2)

    return None


# ─────────────────────────────────────────────
# LLM fallback
# ─────────────────────────────────────────────
async def extract_date_via_llm(text: str, now: datetime) -> datetime | None:
    """모호한 시기 표현(예: "코로나 초기") 을 LLM 에 위임해 ISO 날짜로 변환한다.

    llm.py 에 `llm_extract_temporal(text, now_iso)` 가 존재하면 호출한다.
    반환 형태: `{"iso": "2020-03-01", "confidence": 0.8}` 또는 빈 dict.
    미구현 시 _chat 을 직접 호출해 ISO 문자열 파싱을 시도한다.
    """
    try:
        from hwarang_api.knowledge import llm as _llm_mod  # type: ignore
    except Exception as exc:
        logger.debug("llm module unavailable: %s", exc)
        return None

    extractor = getattr(_llm_mod, "llm_extract_temporal", None)
    now_iso = now.isoformat()

    if callable(extractor):
        try:
            result = await extractor(text, now_iso)
        except Exception as exc:
            logger.debug("llm_extract_temporal failed: %s", exc)
            return None
        iso = (result or {}).get("iso") if isinstance(result, dict) else None
        if iso:
            try:
                dt = datetime.fromisoformat(iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                return None
        return None

    # fallback: _chat helper 로 ISO 날짜만 요구
    chat = getattr(_llm_mod, "_chat", None)
    if not callable(chat):
        return None

    system = (
        "You convert fuzzy Korean/English time expressions to an ISO date. "
        "Reply ONLY with 'YYYY-MM-DD' or 'NONE'."
    )
    prompt = f"Expression: {text}\nReference date: {now_iso}"
    try:
        resp = await chat(prompt, system=system, max_tokens=20)
    except Exception as exc:
        logger.debug("llm _chat failed: %s", exc)
        return None
    if not resp:
        return None
    match = _ISO_DATE.search(resp)
    if not match:
        return None
    try:
        return datetime(
            int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc
        )
    except ValueError:
        return None


# ─────────────────────────────────────────────
# 범위 감지
# ─────────────────────────────────────────────
def detect_time_range(text: str, now: datetime) -> tuple[datetime, datetime] | None:
    """'2020~2023년', '2020년부터 작년까지', 'from 2020 to 2023' 패턴 감지.

    반환: (start, end) 튜플. 감지 실패 시 None.
    """
    t = text.strip()

    m = _RANGE_EN.search(t)
    if m:
        y1 = int(m.group(1))
        mo1 = int(m.group(2)) if m.group(2) else 1
        y2 = int(m.group(3))
        mo2 = int(m.group(4)) if m.group(4) else 12
        try:
            return (_month_start(y1, mo1), _month_end(y2, mo2))
        except ValueError:
            pass

    m = _RANGE_KO_YEAR_SPAN.search(t)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y2 < y1:
            y1, y2 = y2, y1
        return (_year_start(y1), _year_end(y2))

    # "2020년부터 작년까지" 형태: 좌측 연도 + 우측 상대표현
    m = re.search(r"(\d{4})\s*년\s*부터\s*(.+?)\s*까지", t)
    if m:
        start = _year_start(int(m.group(1)))
        end_expr = m.group(2)
        end_dt = extract_date_korean(end_expr, now)
        if end_dt is not None:
            # 상대 연도면 연말로 보정
            if end_dt.month == 1 and end_dt.day == 1:
                end_dt = _year_end(end_dt.year)
            return (start, end_dt)

    # 좌측 상대 + 우측 연도
    m = re.search(r"(작년|재작년|올해|지난달|이번\s*달)\s*부터\s*(\d{4})\s*년\s*까지", t)
    if m:
        start_dt = extract_date_korean(m.group(1), now)
        end_dt = _year_end(int(m.group(2)))
        if start_dt is not None:
            return (start_dt, end_dt)

    return None


# ─────────────────────────────────────────────
# 도메인 / 엔티티 힌트
# ─────────────────────────────────────────────
def _detect_domain(text: str) -> str | None:
    """키워드 매칭으로 도메인 추정. 매칭 없으면 None."""
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return domain
    return None


def _detect_entity(text: str) -> str | None:
    """엔티티 힌트 추출.

    간단한 휴리스틱:
        - `'단어'` 또는 `"단어"` 따옴표로 감싼 표현 우선.
        - "최저시급", "근로기준법" 같이 도메인 사전에 있는 표현을 둘째로.
    """
    m = re.search(r"['\"‘’“”]([^'\"‘’“”]{2,30})['\"‘’“”]", text)
    if m:
        return m.group(1).strip()

    seed_entities = [
        "최저시급", "근로기준법", "민법", "형법", "부가가치세",
        "기준금리", "환율", "코스피", "비트코인",
    ]
    for ent in seed_entities:
        if ent in text:
            return ent
    return None


# ─────────────────────────────────────────────
# 메인 파서
# ─────────────────────────────────────────────
def _strip_time_expressions(text: str) -> str:
    """질문에서 시간 관련 표현을 제거해 순수 질문 부분만 남긴다."""
    cleaned = text
    for pattern in (
        _RANGE_EN, _RANGE_KO_YEAR_SPAN,
        _KO_YEAR_MONTH_DAY, _ISO_DATE,
        _KO_YEAR_MONTH, _ISO_MONTH,
        _KO_YEAR,
    ):
        cleaned = pattern.sub(" ", cleaned)
    for token in [
        "어제", "오늘", "내일", "지난주", "저번주", "이번 주", "이번주",
        "다음 주", "다음주", "지난달", "저번달", "이번 달", "이번달",
        "다음 달", "다음달", "작년", "지난해", "올해", "금년", "내년",
        "다음해", "재작년",
    ]:
        cleaned = cleaned.replace(token, " ")
    return re.sub(r"\s+", " ", cleaned).strip()


async def parse_temporal_query(
    question: str,
    current_time: datetime | None = None,
) -> SearchQuery:
    """자연어 질문을 SearchQuery 로 변환한다.

    처리 순서:
        1. 시간 범위 감지 → as_of_date = 범위 종료 시각.
        2. 단일 날짜 감지 (한국어/영어 정규식).
        3. 실패 시 LLM fallback 으로 모호 표현 해석.
        4. 도메인 / 엔티티 힌트 추출 후 질문 본문 정리.

    범위 질의의 경우 SearchQuery 가 범위를 직접 표현하지 못하므로
    `as_of_date` 에 범위 끝을 넣고, 본문 앞에 `[range:YYYY-MM-DD~YYYY-MM-DD]` 태그를
    붙여 상위 계층이 활용할 수 있도록 한다.
    """
    now = (current_time or _utcnow())
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    as_of: datetime | None = None
    range_tag: str | None = None

    span = detect_time_range(question, now)
    if span is not None:
        start, end = span
        as_of = end
        range_tag = f"[range:{start.date().isoformat()}~{end.date().isoformat()}]"

    if as_of is None:
        as_of = extract_date_korean(question, now)

    if as_of is None:
        # 연도/월/일 숫자가 전혀 없는 경우에만 LLM 호출 (비용 절약)
        has_numeric = any(
            p.search(question) for p in (_ISO_DATE, _KO_YEAR, _KO_YEAR_MONTH)
        )
        if not has_numeric:
            as_of = await extract_date_via_llm(question, now)

    domain = _detect_domain(question)
    entity = _detect_entity(question)

    cleaned = _strip_time_expressions(question)
    if entity and entity not in cleaned:
        cleaned = f"{entity} {cleaned}".strip()
    if range_tag:
        cleaned = f"{range_tag} {cleaned}".strip()

    return SearchQuery(
        query=cleaned or question.strip(),
        as_of_date=as_of,
        domain=domain,
    )


# ─────────────────────────────────────────────
# 애매한 질의를 위한 후보 제안
# ─────────────────────────────────────────────
async def suggest_alternate_dates(question: str) -> list[datetime]:
    """질문이 시간적으로 모호할 때 2~3개 후보 날짜를 제안한다.

    휴리스틱:
        - 질문 안에 모호 키워드(예: "최근", "요즘", "근래") 가 있으면
          현재/3개월 전/1년 전 을 제안.
        - 특정 시기 키워드가 있으면 사전 매핑된 후보를 반환.
        - 그 외에는 빈 리스트.
    """
    now = _utcnow()
    candidates: list[datetime] = []

    fuzzy_now_keywords = ["최근", "요즘", "근래", "요사이", "recently", "nowadays"]
    if any(kw in question for kw in fuzzy_now_keywords):
        candidates = [
            now,
            now - timedelta(days=90),
            now - timedelta(days=365),
        ]
        return candidates

    era_hints: dict[str, list[datetime]] = {
        "코로나 초기": [
            datetime(2020, 2, 1, tzinfo=timezone.utc),
            datetime(2020, 4, 1, tzinfo=timezone.utc),
        ],
        "코로나": [
            datetime(2020, 3, 1, tzinfo=timezone.utc),
            datetime(2021, 6, 1, tzinfo=timezone.utc),
            datetime(2022, 12, 1, tzinfo=timezone.utc),
        ],
        "IMF": [
            datetime(1997, 12, 3, tzinfo=timezone.utc),
            datetime(1998, 6, 1, tzinfo=timezone.utc),
        ],
        "금융위기": [
            datetime(2008, 9, 15, tzinfo=timezone.utc),
            datetime(2009, 3, 1, tzinfo=timezone.utc),
        ],
    }
    for key, cands in era_hints.items():
        if key in question:
            return cands

    return candidates


__all__ = [
    "parse_temporal_query",
    "extract_date_korean",
    "extract_date_via_llm",
    "detect_time_range",
    "suggest_alternate_dates",
]
