"""Primary Source API 어댑터 — 한국 1차 출처 직접 검색.

화랑이 self-question 모드에서 confidence 가 낮을 때, **즉시** 1차 출처 API
에 직접 검색을 던져 답을 얻고 HLKM 에 저장한다 (Eager 모드).

지원 출처:
  - 법제처 (law.go.kr)
  - 통계청 KOSIS (kosis.kr)
  - 국세청 / 홈택스 (nts.go.kr)
  - 식약처 (mfds.go.kr)
  - 한국은행 ECOS (ecos.bok.or.kr)
  - 기상청 (data.kma.go.kr)

설계 원칙:
  1. 모든 어댑터는 `PrimarySourceAPI` 인터페이스를 구현.
  2. **API 키 없으면 빈 리스트** — 호출측이 graceful 하게 fallback.
  3. 미구현/일시 장애도 빈 리스트 (절대 raise 하지 않음).
  4. `search_primary_sources(query, domain)` 가 도메인 매칭 어댑터를
     **동시 호출** 후 평탄화 결과 반환.

각 어댑터는 호출자가 응답을 동일한 ``SearchResult`` dataclass 로 받도록
공통 모양을 보장한다.
"""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── 공통 타입 ───────────────────────────────────────────────────
@dataclass
class SearchResult:
    """1차 출처 API 검색 결과 단위."""

    title: str
    content: str
    url: str
    source_domain: str
    published_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── 베이스 ──────────────────────────────────────────────────────
class PrimarySourceAPI(ABC):
    """모든 1차 출처 어댑터 공통 인터페이스."""

    name: str = "base"
    source_domain: str = ""
    api_key_env: str = ""

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "").strip() if self.api_key_env else ""

    def is_configured(self) -> bool:
        return bool(self.api_key) if self.api_key_env else True

    @abstractmethod
    async def search(
        self, query: str, top_k: int = 5
    ) -> list[SearchResult]:  # pragma: no cover
        ...

    async def health(self) -> dict[str, Any]:
        """헬스 체크 — 키 등록 여부 + 단순 호출 결과."""
        if not self.is_configured():
            return {
                "name": self.name,
                "source_domain": self.source_domain,
                "configured": False,
                "ok": False,
                "reason": "missing_api_key",
            }
        try:
            results = await self.search("test", top_k=1)
            return {
                "name": self.name,
                "source_domain": self.source_domain,
                "configured": True,
                "ok": True,
                "sample_count": len(results),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "name": self.name,
                "source_domain": self.source_domain,
                "configured": True,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }


# ─── HTTP 헬퍼 ───────────────────────────────────────────────────
async def _http_get_json(
    url: str, params: dict[str, Any], timeout: float = 10.0
) -> dict[str, Any] | list[Any] | None:
    try:
        import httpx
    except Exception:  # noqa: BLE001
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.debug(
                    "primary api %s status=%d", url, resp.status_code
                )
                return None
            try:
                return resp.json()
            except Exception:  # noqa: BLE001
                return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("primary api %s 호출 실패: %s", url, exc)
        return None


async def _http_get_text(
    url: str, params: dict[str, Any], timeout: float = 10.0
) -> str:
    try:
        import httpx
    except Exception:  # noqa: BLE001
        return ""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return ""
            return resp.text
    except Exception:  # noqa: BLE001
        return ""


# ─── 어댑터 1: 법제처 ─────────────────────────────────────────────
class LawGoKrAPI(PrimarySourceAPI):
    """법제처 국가법령정보센터 OpenAPI.

    https://www.law.go.kr/DRF/lawSearch.do
    환경변수: HWARANG_LAW_API_KEY (OC 코드).
    """

    name = "law_go_kr"
    source_domain = "law.go.kr"
    api_key_env = "HWARANG_LAW_API_KEY"

    async def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if not self.api_key or not query:
            return []

        params = {
            "OC": self.api_key,
            "target": "law",
            "query": query,
            "type": "JSON",
            "display": top_k,
        }
        data = await _http_get_json(
            "https://www.law.go.kr/DRF/lawSearch.do", params
        )
        if not isinstance(data, dict):
            return []

        items = (data.get("LawSearch", {}) or {}).get("law", []) or []
        if isinstance(items, dict):
            items = [items]

        results: list[SearchResult] = []
        for item in items[:top_k]:
            if not isinstance(item, dict):
                continue
            law_id = (
                item.get("법령ID")
                or item.get("법령일련번호")
                or item.get("MST")
            )
            title = item.get("법령명한글") or item.get("법령명") or ""
            published = item.get("공포일자") or item.get("시행일자")
            content = await self._get_law_content(law_id)
            if not content:
                content = title
            results.append(
                SearchResult(
                    title=str(title),
                    content=str(content)[:3000],
                    url=(
                        f"https://www.law.go.kr/lsInfoP.do?lsiSeq={law_id}"
                        if law_id
                        else "https://www.law.go.kr/"
                    ),
                    source_domain=self.source_domain,
                    published_at=str(published) if published else None,
                    metadata={"law_id": str(law_id) if law_id else None,
                              "type": "law"},
                )
            )
        return results

    async def _get_law_content(self, law_id: Any) -> str:
        """법령 본문(요약) 가져오기. 실패 시 빈 문자열."""
        if not law_id or not self.api_key:
            return ""
        params = {
            "OC": self.api_key,
            "target": "law",
            "MST": str(law_id),
            "type": "JSON",
        }
        data = await _http_get_json(
            "https://www.law.go.kr/DRF/lawService.do", params
        )
        if not isinstance(data, dict):
            return ""
        # 법제처 응답은 중첩이 깊다 — 안전하게 본문/조문 추출.
        try:
            law = data.get("법령", {}) or {}
            articles = (law.get("조문", {}) or {}).get("조문단위", [])
            if isinstance(articles, dict):
                articles = [articles]
            chunks: list[str] = []
            for art in articles[:10]:
                if not isinstance(art, dict):
                    continue
                title = art.get("조문제목") or art.get("조문번호") or ""
                body = art.get("조문내용") or ""
                chunks.append(f"{title} {body}".strip())
            text = "\n".join(c for c in chunks if c)
            return text or law.get("기본정보", {}).get("법령명_한글", "")
        except Exception:  # noqa: BLE001
            return ""


# ─── 어댑터 2: 통계청 KOSIS ───────────────────────────────────────
class KosisAPI(PrimarySourceAPI):
    """통계청 KOSIS OpenAPI.

    https://kosis.kr/openapi/
    환경변수: HWARANG_KOSIS_API_KEY.
    """

    name = "kosis"
    source_domain = "kosis.kr"
    api_key_env = "HWARANG_KOSIS_API_KEY"

    async def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if not self.api_key or not query:
            return []

        # statisticsList.do — 통계표 검색
        params = {
            "method": "getList",
            "apiKey": self.api_key,
            "format": "json",
            "jsonVD": "Y",
            "vwCd": "MT_ZTITLE",
            "parentListId": "",
            "searchNm": query,
            "pageNo": "1",
            "rowsPerPage": str(top_k),
        }
        data = await _http_get_json(
            "https://kosis.kr/openapi/statisticsList.do", params
        )
        items: list[Any]
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # 에러 응답은 dict
            return []
        else:
            return []

        results: list[SearchResult] = []
        for item in items[:top_k]:
            if not isinstance(item, dict):
                continue
            title = item.get("LIST_NM") or item.get("TBL_NM") or ""
            org = item.get("ORG_NM") or "통계청"
            tbl_id = item.get("TBL_ID") or item.get("LIST_ID") or ""
            content = f"{title} ({org}) — KOSIS 통계표 ID {tbl_id}"
            url = (
                f"https://kosis.kr/statHtml/statHtml.do?orgId="
                f"{item.get('ORG_ID', '')}&tblId={tbl_id}"
            )
            results.append(
                SearchResult(
                    title=str(title),
                    content=str(content)[:3000],
                    url=url,
                    source_domain=self.source_domain,
                    published_at=item.get("PUB_DT") or item.get("CHN_DT"),
                    metadata={
                        "tbl_id": str(tbl_id),
                        "org_id": str(item.get("ORG_ID", "")),
                        "type": "statistics",
                    },
                )
            )
        return results


# ─── 어댑터 3: 국세청 ────────────────────────────────────────────
class NtsAPI(PrimarySourceAPI):
    """국세청 — 공공데이터포털 OpenAPI.

    환경변수: HWARANG_NTS_API_KEY (data.go.kr 의 serviceKey).

    실제 NTS 는 단일 검색 API 가 아니라 도메인별 (사업자/세법예규/판례) 가
    모두 다른 엔드포인트라 stub 에 가까움. 키가 등록되면 사업자 상태 조회
    데모 호출만 시도하고, 그 외 질의는 빈 리스트.
    """

    name = "nts"
    source_domain = "nts.go.kr"
    api_key_env = "HWARANG_NTS_API_KEY"

    async def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if not self.api_key or not query:
            return []

        # 데모: 공공데이터포털 사업자등록정보 조회 (질의가 사업자번호 형태일 때만)
        digits = "".join(c for c in query if c.isdigit())
        if len(digits) == 10:
            params = {
                "serviceKey": self.api_key,
                "returnType": "JSON",
            }
            url = "https://api.odcloud.kr/api/nts-businessman/v1/status"
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        url,
                        params=params,
                        json={"b_no": [digits]},
                    )
                    if resp.status_code != 200:
                        return []
                    data = resp.json()
            except Exception:  # noqa: BLE001
                return []

            items = data.get("data", []) if isinstance(data, dict) else []
            results: list[SearchResult] = []
            for item in items[:top_k]:
                if not isinstance(item, dict):
                    continue
                results.append(
                    SearchResult(
                        title=f"사업자 {item.get('b_no', '')} 상태",
                        content=(
                            f"납세자 상태: {item.get('b_stt', '')}, "
                            f"과세유형: {item.get('tax_type', '')}"
                        ),
                        url="https://www.nts.go.kr/",
                        source_domain=self.source_domain,
                        published_at=None,
                        metadata={"type": "businessman_status"},
                    )
                )
            return results

        # 일반 세법/예규 검색은 별도 API 키 발급이 필요해 stub.
        return []


# ─── 어댑터 4: 식약처 ────────────────────────────────────────────
class MfdsAPI(PrimarySourceAPI):
    """식약처 의약품/식품 정보 — 공공데이터포털 OpenAPI.

    환경변수: HWARANG_MFDS_API_KEY.
    """

    name = "mfds"
    source_domain = "mfds.go.kr"
    api_key_env = "HWARANG_MFDS_API_KEY"

    async def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if not self.api_key or not query:
            return []

        # 식품의약품안전처 의약품제품정보 — getDrugPrdtPrmsnDtlInq01
        params = {
            "serviceKey": self.api_key,
            "type": "json",
            "item_name": query,
            "numOfRows": str(top_k),
            "pageNo": "1",
        }
        data = await _http_get_json(
            "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService06"
            "/getDrugPrdtPrmsnDtlInq05",
            params,
        )
        if not isinstance(data, dict):
            return []

        try:
            body = data.get("body") or {}
            items = body.get("items") or []
            if isinstance(items, dict):
                items = [items]
        except Exception:  # noqa: BLE001
            items = []

        results: list[SearchResult] = []
        for item in items[:top_k]:
            if not isinstance(item, dict):
                continue
            name = item.get("ITEM_NAME") or item.get("itemName") or ""
            entp = item.get("ENTP_NAME") or item.get("entpName") or ""
            efcy = item.get("EE_DOC_DATA") or item.get("efcyQesitm") or ""
            content = f"{name} ({entp}) — {efcy}"
            results.append(
                SearchResult(
                    title=str(name),
                    content=str(content)[:3000],
                    url="https://nedrug.mfds.go.kr/",
                    source_domain=self.source_domain,
                    published_at=item.get("ITEM_PERMIT_DATE"),
                    metadata={"type": "drug"},
                )
            )
        return results


# ─── 어댑터 5: 한국은행 ECOS ──────────────────────────────────────
class EcosAPI(PrimarySourceAPI):
    """한국은행 ECOS 경제통계 API.

    https://ecos.bok.or.kr/api/
    환경변수: HWARANG_ECOS_API_KEY.

    ECOS 는 통계코드를 미리 알아야 데이터 호출이 가능하므로, 본 어댑터는
    `KeyStatisticList` (100대 통계) 를 호출해 query 와 가장 매칭이 잘 되는
    행을 우선순위로 반환한다.
    """

    name = "ecos"
    source_domain = "ecos.bok.or.kr"
    api_key_env = "HWARANG_ECOS_API_KEY"

    async def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if not self.api_key or not query:
            return []

        url = (
            f"https://ecos.bok.or.kr/api/KeyStatisticList/{self.api_key}"
            "/json/kr/1/100/"
        )
        data = await _http_get_json(url, params={})
        if not isinstance(data, dict):
            return []

        try:
            rows = (data.get("KeyStatisticList") or {}).get("row") or []
        except Exception:  # noqa: BLE001
            rows = []

        # query 키워드 매칭으로 정렬 (단순 substring score)
        q = query.strip()
        scored: list[tuple[int, dict]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get("KEYSTAT_NAME") or ""
            score = name.count(q[:4]) if q else 0
            if q and q[:2] in name:
                score += 1
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [r for _, r in scored[:top_k]]

        results: list[SearchResult] = []
        for row in top:
            name = row.get("KEYSTAT_NAME", "")
            value = row.get("DATA_VALUE", "")
            unit = row.get("UNIT_NAME", "")
            cycle = row.get("CYCLE", "")
            content = (
                f"{name}: {value} {unit} ({cycle}) — 한국은행 ECOS"
            )
            results.append(
                SearchResult(
                    title=str(name),
                    content=content[:3000],
                    url="https://ecos.bok.or.kr/",
                    source_domain=self.source_domain,
                    published_at=str(row.get("CYCLE", "")) or None,
                    metadata={
                        "stat_code": row.get("CLASS_NAME", ""),
                        "type": "economic_indicator",
                    },
                )
            )
        return results


# ─── 어댑터 6: 기상청 ────────────────────────────────────────────
class KmaAPI(PrimarySourceAPI):
    """기상청 단기예보/기상자료개방포털.

    환경변수: HWARANG_KMA_API_KEY.

    기본은 좌표 기반이라 query 만으로는 위치 매핑이 불완전해 stub 에 가까움.
    "서울/부산/..." 등 광역시 이름을 만나면 해당 격자좌표로 단기예보를 호출.
    """

    name = "kma"
    source_domain = "kma.go.kr"
    api_key_env = "HWARANG_KMA_API_KEY"

    # 광역시 → KMA 격자 좌표 (X, Y)
    _CITY_GRID: dict[str, tuple[int, int]] = {
        "서울": (60, 127),
        "부산": (98, 76),
        "대구": (89, 90),
        "인천": (55, 124),
        "광주": (58, 74),
        "대전": (67, 100),
        "울산": (102, 84),
        "세종": (66, 103),
        "제주": (52, 38),
    }

    async def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if not self.api_key or not query:
            return []

        # 광역시 매칭
        city = next((c for c in self._CITY_GRID if c in query), None)
        if not city:
            return []
        nx, ny = self._CITY_GRID[city]

        # 단기예보 (getVilageFcst) — 발표시각 파라미터는 단순 02시 사용
        from datetime import datetime, timezone, timedelta

        kst = timezone(timedelta(hours=9))
        now = datetime.now(tz=kst)
        base_date = now.strftime("%Y%m%d")
        base_time = "0200"

        params = {
            "serviceKey": self.api_key,
            "pageNo": "1",
            "numOfRows": "12",
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": str(nx),
            "ny": str(ny),
        }
        data = await _http_get_json(
            "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
            "/getVilageFcst",
            params,
        )
        if not isinstance(data, dict):
            return []

        try:
            items = (
                ((data.get("response") or {}).get("body") or {}).get("items")
                or {}
            ).get("item") or []
        except Exception:  # noqa: BLE001
            items = []

        # 카테고리별 가장 빠른 시각 1개씩 발췌 → 사람이 읽을 요약
        first_per_cat: dict[str, dict] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            cat = it.get("category", "")
            if cat not in first_per_cat:
                first_per_cat[cat] = it

        summary_parts: list[str] = []
        for cat, it in first_per_cat.items():
            summary_parts.append(f"{cat}={it.get('fcstValue', '')}")

        if not summary_parts:
            return []

        return [
            SearchResult(
                title=f"{city} 단기예보 ({base_date} {base_time} KST)",
                content=", ".join(summary_parts)[:3000],
                url="https://www.weather.go.kr/",
                source_domain=self.source_domain,
                published_at=base_date,
                metadata={"city": city, "nx": nx, "ny": ny, "type": "weather"},
            )
        ][:top_k]


# ─── 라우터 / 디스패처 ───────────────────────────────────────────
# 도메인 → 어댑터 인스턴스 리스트.
# 어댑터 자체는 stateless 라 모듈 로드 시 1번만 만들어둔다.
_LAW = LawGoKrAPI()
_KOSIS = KosisAPI()
_NTS = NtsAPI()
_MFDS = MfdsAPI()
_ECOS = EcosAPI()
_KMA = KmaAPI()

DOMAIN_TO_APIS: dict[str, list[PrimarySourceAPI]] = {
    "legal": [_LAW],
    "law": [_LAW],
    "tax": [_NTS, _LAW],
    "statistics": [_KOSIS],
    "stat": [_KOSIS],
    "medical": [_MFDS],
    "drug": [_MFDS],
    "food": [_MFDS],
    "finance": [_ECOS, _NTS],
    "economy": [_ECOS],
    "weather": [_KMA],
    "kma": [_KMA],
    "general": [],
}


ALL_APIS: list[PrimarySourceAPI] = [_LAW, _KOSIS, _NTS, _MFDS, _ECOS, _KMA]


async def search_primary_sources(
    query: str, domain: str, top_k: int = 5
) -> list[SearchResult]:
    """도메인 매칭 모든 1차 출처 동시 검색.

    하나의 어댑터가 실패해도 다른 어댑터의 결과는 그대로 활용한다.
    `domain` 미매칭 → 빈 리스트.
    """
    apis = DOMAIN_TO_APIS.get((domain or "general").lower(), [])
    if not apis or not query:
        return []

    results = await asyncio.gather(
        *[api.search(query, top_k=top_k) for api in apis],
        return_exceptions=True,
    )

    flat: list[SearchResult] = []
    for r in results:
        if isinstance(r, Exception):
            logger.debug("primary API 실패: %s", r)
            continue
        if isinstance(r, list):
            flat.extend(r)

    return flat[: top_k * 2]


async def primary_sources_health() -> list[dict[str, Any]]:
    """6개 어댑터의 키 등록 여부 + 단순 호출 결과 요약."""
    return await asyncio.gather(*[api.health() for api in ALL_APIS])


__all__ = [
    "SearchResult",
    "PrimarySourceAPI",
    "LawGoKrAPI",
    "KosisAPI",
    "NtsAPI",
    "MfdsAPI",
    "EcosAPI",
    "KmaAPI",
    "DOMAIN_TO_APIS",
    "ALL_APIS",
    "search_primary_sources",
    "primary_sources_health",
]
