"""HLKM - 정치 도메인 편향 자동 감지.

같은 사실을 서로 다른 정치적 입장으로 보도하는 문제를 감지한다.
출처(언론사) 기반 프로파일 + 어휘 기반 빠른 판정 + LLM 보조 판정을
순차적으로 적용해 -1(극좌) ~ +1(극우) 스코어와 라벨을 매긴다.

중요 원칙:
    편향 판단은 **절대 답변을 검열하지 않는다**. 투명하게 표시만 하고
    모든 관점(progressive / centrist / conservative / mixed)을 보존해
    사용자에게 다양한 시각을 제시한다.

의존:
    - hwarang_api.db.prisma
    - .types.KnowledgeFact
    - .llm._chat
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from hwarang_api.db import prisma

from .llm import _chat
from .types import KnowledgeFact

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 한국어 편향 어휘 사전
# ─────────────────────────────────────────────
KOREAN_BIAS_LEXICON: dict[str, list[str]] = {
    "progressive_markers": [  # 진보 성향
        "민주주의",
        "노동자",
        "불평등",
        "기득권",
        "재벌개혁",
        "분배",
        "복지확대",
        "진보적",
        "시민운동",
        "촛불",
        "적폐",
    ],
    "conservative_markers": [  # 보수 성향
        "안보",
        "자유시장",
        "성장",
        "기업경쟁력",
        "법치",
        "보수적",
        "안정",
        "전통",
        "국익",
        "빨갱이",
        "좌편향",
    ],
    "propaganda_markers": [  # 선전성
        "당당히",
        "역사적인",
        "위대한",
        "치욕적",
        "굴욕",
        "참사",
        "지옥",
        "포퓰리즘",
        "독재",
        "파시즘",
    ],
    "loaded_terms": [  # 프레임이 강한 용어
        "촛불세력",
        "태극기부대",
        "빨갱이",
        "꼴통",
        "틀딱",
        "좌빨",
    ],
}


# ─────────────────────────────────────────────
# 한국 주요 언론사 편향 시드 레지스트리
# (공개 평가, MBFC 유사 기준 - 학술/시민단체 공개 자료 기반)
# ─────────────────────────────────────────────
SEED_MEDIA_BIAS_PROFILES: list[dict] = [
    {
        "mediaOutlet": "hani",
        "displayName": "한겨레",
        "domain": "hani.co.kr",
        "biasScore": -0.6,
        "biasLabel": "PROGRESSIVE",
        "factualityRating": "high",
    },
    {
        "mediaOutlet": "khan",
        "displayName": "경향신문",
        "domain": "khan.co.kr",
        "biasScore": -0.55,
        "biasLabel": "PROGRESSIVE",
        "factualityRating": "high",
    },
    {
        "mediaOutlet": "ohmynews",
        "displayName": "오마이뉴스",
        "domain": "ohmynews.com",
        "biasScore": -0.5,
        "biasLabel": "PROGRESSIVE",
        "factualityRating": "mixed",
    },
    {
        "mediaOutlet": "pressian",
        "displayName": "프레시안",
        "domain": "pressian.com",
        "biasScore": -0.45,
        "biasLabel": "PROGRESSIVE",
        "factualityRating": "mixed",
    },
    {
        "mediaOutlet": "yonhap",
        "displayName": "연합뉴스",
        "domain": "yna.co.kr",
        "biasScore": -0.05,
        "biasLabel": "CENTRIST",
        "factualityRating": "high",
    },
    {
        "mediaOutlet": "kbs",
        "displayName": "KBS",
        "domain": "kbs.co.kr",
        "biasScore": 0.0,
        "biasLabel": "CENTRIST",
        "factualityRating": "high",
    },
    {
        "mediaOutlet": "joongang",
        "displayName": "중앙일보",
        "domain": "joongang.co.kr",
        "biasScore": 0.3,
        "biasLabel": "CONSERVATIVE",
        "factualityRating": "high",
    },
    {
        "mediaOutlet": "donga",
        "displayName": "동아일보",
        "domain": "donga.com",
        "biasScore": 0.4,
        "biasLabel": "CONSERVATIVE",
        "factualityRating": "high",
    },
    {
        "mediaOutlet": "chosun",
        "displayName": "조선일보",
        "domain": "chosun.com",
        "biasScore": 0.55,
        "biasLabel": "CONSERVATIVE",
        "factualityRating": "mixed",
    },
    {
        "mediaOutlet": "skyedaily",
        "displayName": "스카이데일리",
        "domain": "skyedaily.com",
        "biasScore": 0.75,
        "biasLabel": "FAR_RIGHT",
        "factualityRating": "low",
    },
    {
        "mediaOutlet": "newdaily",
        "displayName": "뉴데일리",
        "domain": "newdaily.co.kr",
        "biasScore": 0.7,
        "biasLabel": "FAR_RIGHT",
        "factualityRating": "low",
    },
]


_VALID_LABELS = {
    "FAR_LEFT",
    "PROGRESSIVE",
    "CENTRIST",
    "CONSERVATIVE",
    "FAR_RIGHT",
    "MIXED",
    "NON_POLITICAL",
    "UNKNOWN",
}

_DISPLAY_LABEL_KO: dict[str, str] = {
    "FAR_LEFT": "극좌",
    "PROGRESSIVE": "진보",
    "CENTRIST": "중도",
    "CONSERVATIVE": "보수",
    "FAR_RIGHT": "극우",
    "MIXED": "혼재",
    "NON_POLITICAL": "비정치",
    "UNKNOWN": "미상",
}


# ─────────────────────────────────────────────
# 점수 ↔ 라벨 변환
# ─────────────────────────────────────────────
def score_to_label(score: float) -> str:
    """편향 점수를 라벨로 변환.

    - -1.0 ~ -0.66 → FAR_LEFT
    - -0.66 ~ -0.2 → PROGRESSIVE
    - -0.2  ~ +0.2 → CENTRIST
    - +0.2  ~ +0.66 → CONSERVATIVE
    - +0.66 ~ +1.0 → FAR_RIGHT
    """
    if score <= -0.66:
        return "FAR_LEFT"
    if score <= -0.2:
        return "PROGRESSIVE"
    if score < 0.2:
        return "CENTRIST"
    if score < 0.66:
        return "CONSERVATIVE"
    return "FAR_RIGHT"


def bias_display_label(label: str) -> str:
    """라벨 문자열 → 사용자용 한글 라벨."""
    return _DISPLAY_LABEL_KO.get(label, "미상")


# ─────────────────────────────────────────────
# 시드
# ─────────────────────────────────────────────
async def seed_media_bias_profiles() -> int:
    """SEED_MEDIA_BIAS_PROFILES 를 DB 에 upsert.

    이미 존재하는 outlet 은 biasScore/biasLabel 만 갱신하지 않고
    유지(운영자가 직접 수정 가능). 반환값은 신규 생성된 row 수.
    """
    created = 0
    for profile in SEED_MEDIA_BIAS_PROFILES:
        outlet = profile["mediaOutlet"]
        try:
            existing = await prisma.mediabiasprofile.find_unique(
                where={"mediaOutlet": outlet}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("seed_media_bias_profiles lookup failed: %s", exc)
            continue
        if existing:
            continue
        try:
            await prisma.mediabiasprofile.create(
                data={
                    "mediaOutlet": outlet,
                    "biasScore": profile["biasScore"],
                    "biasLabel": profile["biasLabel"],
                    "factualityRating": profile.get("factualityRating", "unknown"),
                    "sources": [
                        profile.get("displayName", outlet),
                        profile.get("domain", ""),
                    ],
                }
            )
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("seed_media_bias_profiles create failed for %s: %s", outlet, exc)
    return created


# ─────────────────────────────────────────────
# Outlet 추출
# ─────────────────────────────────────────────
def extract_outlet_from_source(source: str) -> str | None:
    """URL 또는 출처명에서 outlet 키를 추출.

    - URL 이면 hostname 에서 도메인 매칭
    - 문자열이면 displayName 매칭
    """
    if not source:
        return None
    s = source.strip()

    # URL 우선
    host: str = ""
    if s.startswith("http://") or s.startswith("https://"):
        try:
            host = (urlparse(s).hostname or "").lower()
        except Exception:  # noqa: BLE001
            host = ""
    else:
        # 도메인 유사 문자열일 수도
        m = re.search(r"([a-z0-9\-]+\.[a-z0-9\-.]+)", s.lower())
        if m:
            host = m.group(1)

    if host:
        host = host.removeprefix("www.")
        for profile in SEED_MEDIA_BIAS_PROFILES:
            dom = str(profile.get("domain", "")).lower()
            if dom and (host == dom or host.endswith("." + dom)):
                return str(profile["mediaOutlet"])

    # 이름/한글 매칭
    low = s.lower()
    for profile in SEED_MEDIA_BIAS_PROFILES:
        display = str(profile.get("displayName", ""))
        outlet = str(profile["mediaOutlet"]).lower()
        if display and display in s:
            return str(profile["mediaOutlet"])
        if outlet and outlet in low:
            return str(profile["mediaOutlet"])
    return None


# ─────────────────────────────────────────────
# 어휘 기반 감지
# ─────────────────────────────────────────────
async def detect_bias_lexicon(content: str) -> tuple[float, list[str]]:
    """어휘 매칭 기반 빠른 편향 감지.

    진보 마커는 -1 방향, 보수 마커는 +1 방향으로 점수를 누적한 뒤
    총 히트 수로 정규화해 [-1, +1] 범위의 점수를 만든다.
    """
    if not content:
        return (0.0, [])

    triggers: list[str] = []
    prog = 0
    cons = 0
    for term in KOREAN_BIAS_LEXICON["progressive_markers"]:
        if term in content:
            prog += 1
            triggers.append(term)
    for term in KOREAN_BIAS_LEXICON["conservative_markers"]:
        if term in content:
            cons += 1
            triggers.append(term)
    # loaded terms 는 극단 방향으로 가산
    for term in KOREAN_BIAS_LEXICON["loaded_terms"]:
        if term in content:
            # 좌/우 양쪽 극단 어휘 — 대체로 우편향 표현이 많아 기본은 보수쪽
            if term in {"꼴통", "틀딱", "좌빨"}:
                cons += 2
            else:
                prog += 2
            triggers.append(term)

    total = prog + cons
    if total == 0:
        return (0.0, [])
    raw = (cons - prog) / max(total, 1)
    score = max(-1.0, min(1.0, raw))
    return (score, triggers)


# ─────────────────────────────────────────────
# 출처 기반 감지
# ─────────────────────────────────────────────
async def detect_bias_from_source(source_or_url: str) -> tuple[float, str] | None:
    """MediaBiasProfile 조회 기반 편향 감지."""
    outlet = extract_outlet_from_source(source_or_url)
    if not outlet:
        return None
    try:
        row = await prisma.mediabiasprofile.find_unique(where={"mediaOutlet": outlet})
    except Exception as exc:  # noqa: BLE001
        logger.debug("detect_bias_from_source lookup failed: %s", exc)
        row = None
    if row:
        score = float(getattr(row, "biasScore", 0.0) or 0.0)
        label = str(getattr(row, "biasLabel", "UNKNOWN") or "UNKNOWN")
        return (score, label)
    # 시드 프로파일에서 fallback
    for profile in SEED_MEDIA_BIAS_PROFILES:
        if profile["mediaOutlet"] == outlet:
            return (float(profile["biasScore"]), str(profile["biasLabel"]))
    return None


# ─────────────────────────────────────────────
# LLM 기반 감지
# ─────────────────────────────────────────────
async def detect_bias_llm(content: str) -> tuple[float, str, list[str]]:
    """LLM 으로 편향 판정.

    응답 형식: ``SCORE LABEL phrase1|phrase2|phrase3``
    실패 시 (0.0, "UNKNOWN", []) 반환.
    """
    system = (
        "You are a neutral media analyst. Assess the political bias of the given Korean text. "
        "Reply in EXACTLY one line with: "
        "'<score> <label> <phrase1>|<phrase2>|<phrase3>' where "
        "score is a float in [-1, 1] (-1 far-left, +1 far-right), "
        "label is one of FAR_LEFT, PROGRESSIVE, CENTRIST, CONSERVATIVE, FAR_RIGHT, "
        "MIXED, NON_POLITICAL, and phrases are up to three short Korean evidence snippets. "
        "No extra words."
    )
    try:
        resp = await _chat(content[:1500], system=system, max_tokens=80)
    except Exception as exc:  # noqa: BLE001
        logger.debug("detect_bias_llm call failed: %s", exc)
        return (0.0, "UNKNOWN", [])
    if not resp:
        return (0.0, "UNKNOWN", [])

    text = resp.strip()
    m = re.match(r"^\s*(-?[0-9.]+)\s+([A-Z_]+)\s*(.*)$", text)
    if not m:
        return (0.0, "UNKNOWN", [])
    try:
        score = max(-1.0, min(1.0, float(m.group(1))))
    except ValueError:
        score = 0.0
    label = m.group(2)
    if label not in _VALID_LABELS:
        label = score_to_label(score)
    phrases_raw = m.group(3).strip()
    phrases = [p.strip() for p in phrases_raw.split("|") if p.strip()][:3]
    return (score, label, phrases)


# ─────────────────────────────────────────────
# 메인 감지 파이프라인
# ─────────────────────────────────────────────
async def detect_bias(fact: KnowledgeFact) -> dict:
    """fact 의 편향을 단계별로 감지.

    우선순위:
        1. 출처 기반 (있으면 가장 강력한 신호)
        2. 어휘 기반 (빠른 감지)
        3. LLM (불확실할 때 보조)

    세 방법의 결과를 가중 평균해 최종 점수/라벨 산출.
    BiasDetection row 를 insert 하고 KnowledgeFact.biasScore/biasLabel 갱신.
    """
    triggers: list[str] = []
    methods_used: list[str] = []
    scores: list[tuple[float, float]] = []  # (score, weight)

    # 1) 출처
    source = fact.source or fact.source_url or ""
    src_result = await detect_bias_from_source(source) if source else None
    if src_result is not None:
        scores.append((src_result[0], 0.5))
        methods_used.append("source")

    # 2) 어휘
    lex_score, lex_triggers = await detect_bias_lexicon(fact.content)
    if lex_triggers:
        scores.append((lex_score, 0.3))
        triggers.extend(lex_triggers)
        methods_used.append("lexicon")

    # 3) LLM (불확실한 경우만)
    need_llm = False
    if not scores:
        need_llm = True
    elif len(scores) == 1 and abs(scores[0][0]) < 0.2:
        need_llm = True
    elif len(triggers) >= 3 and abs(lex_score) < 0.25:
        need_llm = True

    llm_phrases: list[str] = []
    if need_llm:
        llm_score, llm_label, llm_phrases = await detect_bias_llm(fact.content)
        if llm_label != "UNKNOWN":
            scores.append((llm_score, 0.4))
            methods_used.append("llm")
            triggers.extend(llm_phrases)

    # 집계
    if not scores:
        final_score = 0.0
        final_label = "UNKNOWN"
        confidence = 0.2
    else:
        total_w = sum(w for _, w in scores)
        final_score = sum(s * w for s, w in scores) / total_w
        final_score = max(-1.0, min(1.0, final_score))
        final_label = score_to_label(final_score)
        # 방법이 여러 개이고 같은 방향이면 confidence 상승
        same_sign = all((s >= 0) == (final_score >= 0) for s, _ in scores)
        base_conf = 0.5 + 0.1 * len(scores)
        confidence = min(0.95, base_conf + (0.15 if same_sign and len(scores) >= 2 else 0.0))

    method_str = "+".join(methods_used) if methods_used else "none"
    dedup_triggers = list(dict.fromkeys(triggers))[:10]

    # BiasDetection 기록 + KnowledgeFact 업데이트
    if fact.id:
        try:
            await prisma.biasdetection.create(
                data={
                    "factId": fact.id,
                    "method": method_str,
                    "biasScore": final_score,
                    "biasLabel": final_label,
                    "confidence": confidence,
                    "triggerPhrases": dedup_triggers,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("detect_bias insert failed: %s", exc)
        try:
            await prisma.knowledgefact.update(
                where={"id": fact.id},
                data={"biasScore": final_score, "biasLabel": final_label},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("detect_bias update failed: %s", exc)

    return {
        "score": final_score,
        "label": final_label,
        "confidence": confidence,
        "method": method_str,
        "trigger_phrases": dedup_triggers,
    }


# ─────────────────────────────────────────────
# 배치 처리
# ─────────────────────────────────────────────
async def batch_detect_bias(domain: str = "politics", limit: int = 200) -> dict:
    """정치 도메인에서 biasLabel 이 비어있는 fact 들을 일괄 감지."""
    where: dict[str, Any] = {"domain": domain, "biasLabel": None}
    try:
        rows = await prisma.knowledgefact.find_many(where=where, take=limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch_detect_bias find failed: %s", exc)
        return {"total": 0, "labeled": 0, "by_label": {}}

    by_label: dict[str, int] = {lbl: 0 for lbl in _VALID_LABELS}
    labeled = 0
    for row in rows:
        try:
            fact = KnowledgeFact(
                id=row.id,
                content=getattr(row, "content", ""),
                domain=getattr(row, "domain", domain),
                valid_from=getattr(row, "validFrom"),
                source=getattr(row, "source", "") or "",
                source_url=getattr(row, "sourceUrl", None),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("batch_detect_bias row parse failed: %s", exc)
            continue
        res = await detect_bias(fact)
        lbl = res.get("label")
        if lbl and lbl in by_label:
            by_label[lbl] += 1
            labeled += 1
    return {"total": len(rows), "labeled": labeled, "by_label": by_label}


# ─────────────────────────────────────────────
# 관점 균형
# ─────────────────────────────────────────────
async def find_balanced_perspective(entity: str) -> dict:
    """같은 entity 에 대한 사실들을 bias 스펙트럼 별로 정리.

    답변 시 사용자에게 ``진보 / 중도 / 보수 / 혼재`` 네 그룹을 동시에
    제시해 편향된 시각에 갇히지 않게 한다.
    """
    try:
        rows = await prisma.knowledgefact.find_many(where={"entity": entity}, take=300)
    except Exception as exc:  # noqa: BLE001
        logger.warning("find_balanced_perspective failed: %s", exc)
        return {"progressive": [], "centrist": [], "conservative": [], "mixed": []}

    buckets: dict[str, list[dict]] = {
        "progressive": [],
        "centrist": [],
        "conservative": [],
        "mixed": [],
    }
    for row in rows:
        lbl = getattr(row, "biasLabel", None) or "UNKNOWN"
        item = {
            "fact_id": row.id,
            "content": (getattr(row, "content", "") or "")[:200],
            "bias_score": float(getattr(row, "biasScore", 0.0) or 0.0),
            "bias_label": lbl,
            "source": getattr(row, "source", "") or "",
        }
        if lbl in {"FAR_LEFT", "PROGRESSIVE"}:
            buckets["progressive"].append(item)
        elif lbl == "CENTRIST":
            buckets["centrist"].append(item)
        elif lbl in {"FAR_RIGHT", "CONSERVATIVE"}:
            buckets["conservative"].append(item)
        else:
            buckets["mixed"].append(item)

    # 각 버킷 최대 5개
    for k in buckets:
        buckets[k] = buckets[k][:5]
    return buckets


# ─────────────────────────────────────────────
# 에코 체임버 경고
# ─────────────────────────────────────────────
async def warn_echo_chamber_by_bias(fact_ids: list[str]) -> dict | None:
    """답변 근거 fact 들의 bias label 이 한쪽으로 쏠리면 경고 반환.

    절대 검열하지 않고, 사용자에게 투명하게 표시만 한다.
    """
    if not fact_ids:
        return None
    try:
        rows = await prisma.knowledgefact.find_many(where={"id": {"in": fact_ids}})
    except Exception as exc:  # noqa: BLE001
        logger.debug("warn_echo_chamber_by_bias fetch failed: %s", exc)
        return None
    if not rows:
        return None

    labels = [getattr(r, "biasLabel", None) for r in rows]
    labels = [lbl for lbl in labels if lbl and lbl not in {"UNKNOWN", "NON_POLITICAL"}]
    if len(labels) < 2:
        return None

    # 같은 라벨로 80% 이상 쏠리면 경고
    counts: dict[str, int] = {}
    for lbl in labels:
        counts[lbl] = counts.get(lbl, 0) + 1
    top_lbl, top_cnt = max(counts.items(), key=lambda kv: kv[1])
    ratio = top_cnt / len(labels)
    if ratio < 0.8:
        return None

    # 진보/보수 한쪽으로 완전히 편중된 경우 경고
    if top_lbl in {"PROGRESSIVE", "FAR_LEFT", "CONSERVATIVE", "FAR_RIGHT"}:
        ko_lbl = bias_display_label(top_lbl)
        msg = (
            f"모든 출처가 {ko_lbl}({top_lbl}) 성향입니다. "
            f"다른 관점도 고려하세요."
        )
        return {
            "warning": True,
            "dominant_label": top_lbl,
            "ratio": ratio,
            "message": msg,
            "sources": [getattr(r, "source", "") for r in rows],
        }
    return None


# ─────────────────────────────────────────────
# MediaBiasProfile CRUD
# ─────────────────────────────────────────────
async def get_bias_profile(media_outlet_or_url: str) -> dict | None:
    """outlet 이름 또는 URL 로 MediaBiasProfile 조회."""
    outlet = extract_outlet_from_source(media_outlet_or_url) or media_outlet_or_url
    try:
        row = await prisma.mediabiasprofile.find_unique(where={"mediaOutlet": outlet})
    except Exception as exc:  # noqa: BLE001
        logger.debug("get_bias_profile failed: %s", exc)
        return None
    if not row:
        return None
    return {
        "mediaOutlet": getattr(row, "mediaOutlet", outlet),
        "biasScore": float(getattr(row, "biasScore", 0.0) or 0.0),
        "biasLabel": getattr(row, "biasLabel", "UNKNOWN"),
        "factualityRating": getattr(row, "factualityRating", "unknown"),
        "sources": list(getattr(row, "sources", []) or []),
        "updatedAt": getattr(row, "updatedAt", None),
    }


async def list_media_bias_profiles() -> list[dict]:
    """모든 MediaBiasProfile 반환 (biasScore 오름차순)."""
    try:
        rows = await prisma.mediabiasprofile.find_many(order={"biasScore": "asc"})
    except Exception as exc:  # noqa: BLE001
        logger.debug("list_media_bias_profiles failed: %s", exc)
        return []
    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "mediaOutlet": getattr(row, "mediaOutlet", ""),
                "biasScore": float(getattr(row, "biasScore", 0.0) or 0.0),
                "biasLabel": getattr(row, "biasLabel", "UNKNOWN"),
                "factualityRating": getattr(row, "factualityRating", "unknown"),
                "sources": list(getattr(row, "sources", []) or []),
            }
        )
    return out


async def update_media_bias_profile(outlet: str, **updates: Any) -> None:
    """MediaBiasProfile 부분 업데이트.

    허용 필드: biasScore, biasLabel, factualityRating, sources.
    """
    allowed = {"biasScore", "biasLabel", "factualityRating", "sources"}
    data = {k: v for k, v in updates.items() if k in allowed}
    if not data:
        return
    try:
        await prisma.mediabiasprofile.update(
            where={"mediaOutlet": outlet},
            data=data,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("update_media_bias_profile failed: %s", exc)


__all__ = [
    "KOREAN_BIAS_LEXICON",
    "SEED_MEDIA_BIAS_PROFILES",
    "seed_media_bias_profiles",
    "detect_bias_lexicon",
    "detect_bias_from_source",
    "detect_bias_llm",
    "detect_bias",
    "score_to_label",
    "bias_display_label",
    "batch_detect_bias",
    "find_balanced_perspective",
    "warn_echo_chamber_by_bias",
    "get_bias_profile",
    "list_media_bias_profiles",
    "update_media_bias_profile",
    "extract_outlet_from_source",
]
