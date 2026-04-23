"""HLKM 교차 언어 원본 추적 (Cross-lingual Origin Tracking).

영어 기사가 한국어로 번역되어 국내 언론에 실릴 때, 또는 그 반대의 경우에
자동으로 번역 관계를 감지하고 **원본성 (originality)** 을 판별한다.

핵심 아이디어
---------------
1. 유니코드 문자 범위 기반 **언어 감지** — 라이브러리 없이 한/영/일/중/아/러/라틴 구분.
2. **교차언어 임베딩** (bge-m3 같은 다국어 모델 가정) 의 코사인 유사도로 의미 동등성 판정.
3. 다국어 임베딩이 부실할 경우 **길이/문장수 비율 + LLM 평가** 로 fallback.
4. 먼저 발행된 쪽이 **원본 (original)**, 이후 것이 번역본 (translation).
5. `TranslationLink` 에 기록하고 번역본의 `translatedFromFactId`/`languageOriginal` 갱신.
6. 외신 통신사 패턴 (로이터, 연합뉴스 공동보도 등) 을 한국 기사 본문에서 추출.
7. 다단계 번역 체인 (영→일→한 등) 및 역번역 (한→영→한) 을 감지해 의미 왜곡 경고.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .embeddings import cosine, embed_text
from .llm import _chat
from .provenance import jaccard_similarity
from .types import KnowledgeFact

# ─────────────────────────────────────────────────────────────
# 상수/임계치
# ─────────────────────────────────────────────────────────────
_CROSS_LINGUAL_SIM_THRESHOLD = 0.75   # 교차언어 임베딩 번역 추정 임계
_CROSS_LINGUAL_SIM_STRICT = 0.85      # 거의 확실한 번역 관계
_LENGTH_RATIO_MIN = 0.45              # 길이 비율이 이 값 미만이면 요약/부분 번역
_LENGTH_RATIO_MAX = 2.2               # 이상이면 과도한 확장/편집
_SENTENCE_COUNT_RATIO_MAX = 2.5

# 한국 언론에서 자주 등장하는 외신 통신사
KOREAN_FOREIGN_WIRE_AGENCIES: list[str] = [
    "reuters",
    "ap",
    "afp",
    "bloomberg",
    "nyt",
    "wsj",
    "guardian",
    "bbc",
    "cnn",
    "kyodo",
    "xinhua",
    "tass",
]

# "(로이터)", "= AP", "연합뉴스=로이터" 같은 패턴
_WIRE_PATTERNS = [
    re.compile(r"\(\s*(로이터|AP|AFP|블룸버그|NYT|WSJ|가디언|BBC|CNN|교도|신화|타스)\s*[=]?\s*연?합?뉴?스?\s*\)"),
    re.compile(r"(로이터|AP|AFP|블룸버그|Reuters|Bloomberg|AFP)\s*=\s*연합뉴스"),
    re.compile(r"=\s*(AP|AFP|Reuters|Bloomberg)\b", re.IGNORECASE),
    re.compile(r"\((Reuters|AP|AFP|Bloomberg|NYT|WSJ|BBC|CNN)\)", re.IGNORECASE),
]


# ─────────────────────────────────────────────────────────────
# 1. 언어 감지 (유니코드 범위 기반)
# ─────────────────────────────────────────────────────────────
def _classify_char(ch: str) -> str:
    """단일 문자를 언어 카테고리로 분류.

    반환 값: "ko", "zh", "ja_kana", "ar", "ru", "latin", "digit", "other"
    """
    if not ch:
        return "other"
    code = ord(ch)
    # 한글 음절 / 자모
    if 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
        return "ko"
    # 한자 (CJK Unified Ideographs) — 단독으로는 중국어로 분류하되 일본어 문맥에서 보정.
    if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
        return "zh"
    # 히라가나 / 가타카나
    if 0x3040 <= code <= 0x309F or 0x30A0 <= code <= 0x30FF:
        return "ja_kana"
    # 아랍 문자
    if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
        return "ar"
    # 키릴 문자
    if 0x0400 <= code <= 0x04FF:
        return "ru"
    # 라틴 문자 (ASCII + Latin-1 확장 + Latin Extended)
    if (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A):
        return "latin"
    if 0x00C0 <= code <= 0x024F:
        return "latin"
    if ch.isdigit():
        return "digit"
    return "other"


def language_ratio(text: str) -> dict[str, float]:
    """각 언어 문자의 비율을 반환.

    공백/숫자/기호는 분모에서 제외하여 실제 언어 문자만 집계한다.
    반환 키: "ko", "zh", "ja_kana", "ar", "ru", "latin".
    """
    if not text:
        return {k: 0.0 for k in ("ko", "zh", "ja_kana", "ar", "ru", "latin")}

    counts: dict[str, int] = {
        "ko": 0,
        "zh": 0,
        "ja_kana": 0,
        "ar": 0,
        "ru": 0,
        "latin": 0,
    }
    total = 0
    for ch in text:
        if ch.isspace():
            continue
        cat = _classify_char(ch)
        if cat in counts:
            counts[cat] += 1
            total += 1
        elif cat in ("digit", "other"):
            # 기호/숫자는 분모에 포함하지 않는다 (언어 판별 노이즈).
            continue

    if total == 0:
        return {k: 0.0 for k in counts}
    return {k: v / total for k, v in counts.items()}


def detect_language(text: str) -> str:
    """빠른 언어 감지 (ISO 639-1 코드 반환).

    반환 값: "ko", "en", "ja", "zh", "ar", "ru", "mixed" 중 하나.
    - 한글이 10% 이상이면 "ko" (한국어에 한자·영문이 섞여도 한국어로 간주).
    - 히라가나/가타카나가 5% 이상이면 "ja" (한자+가나 조합은 일본어).
    - 한자만 많고 가나가 없으면 "zh".
    - 라틴 비율이 최대이면 "en".
    - 복수 언어가 비슷한 비율로 섞여 있으면 "mixed".
    """
    r = language_ratio(text)
    if max(r.values()) == 0.0:
        return "mixed"

    # 한국어는 한자/라틴이 섞여도 한글만 유의미 비율이면 한국어.
    if r["ko"] >= 0.10:
        return "ko"
    # 일본어는 가나로 판별 (한자+가나).
    if r["ja_kana"] >= 0.05:
        return "ja"
    # 중국어는 한자만 있을 때.
    if r["zh"] >= 0.20 and r["ja_kana"] < 0.02 and r["ko"] < 0.02:
        return "zh"
    if r["ar"] >= 0.30:
        return "ar"
    if r["ru"] >= 0.30:
        return "ru"
    if r["latin"] >= 0.50:
        return "en"

    # 우세한 언어가 하나도 없으면 최대값 기반 best-effort.
    best = max(r.items(), key=lambda kv: kv[1])
    best_lang, best_ratio = best
    # 2위와의 차이가 적으면 mixed.
    remaining = sorted(r.values(), reverse=True)
    if len(remaining) >= 2 and remaining[0] - remaining[1] < 0.1:
        return "mixed"
    return {
        "ko": "ko",
        "zh": "zh",
        "ja_kana": "ja",
        "ar": "ar",
        "ru": "ru",
        "latin": "en",
    }.get(best_lang, "mixed")


# ─────────────────────────────────────────────────────────────
# 2. 번역 관계 감지
# ─────────────────────────────────────────────────────────────
def _count_sentences(text: str) -> int:
    """간단한 문장 분할 기반 문장 수. 마침표/물음표/느낌표/한자 마침표로 분리."""
    if not text:
        return 0
    # 한국어/영어/일본어/중국어의 종결 부호를 모두 포함.
    parts = re.split(r"[.!?。！？]+", text)
    return sum(1 for p in parts if p.strip())


def _length_ratio(a: str, b: str) -> float:
    """두 텍스트의 길이 비율. 항상 >=1 (작은 쪽 기준)."""
    la, lb = max(len(a), 1), max(len(b), 1)
    return max(la, lb) / min(la, lb)


def _published_at(fact: KnowledgeFact) -> datetime:
    """fact 의 발행 시각 추정. valid_from 을 사용하되 timezone-naive 이면 UTC 로 가정."""
    dt = fact.valid_from
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def detect_translation_method(
    source_text: str, target_text: str, source_lang: str, target_lang: str
) -> str:
    """번역 방식을 추정. "machine" | "human" | "ai_llm" | "unknown".

    1) LLM 에 짧은 프롬프트로 질문.
    2) LLM 미설정/실패 시 휴리스틱 fallback:
       - 길이 비율이 0.9~1.1 이고 문장 수가 같으면 "machine" 경향 (literal 번역).
       - 길이 비율이 0.6~0.9 또는 1.1~1.4 이면 "human" (자연스러운 의역).
       - 길이 비율이 1.4 초과이면 "ai_llm" (설명적 확장).
       - 그 외 "unknown".
    """
    # 가능한 한 LLM 에게 판단을 맡긴다.
    system = (
        "You are a translation-style classifier. "
        "Answer with EXACTLY one token: machine | human | ai_llm | unknown."
    )
    prompt = (
        f"Source language: {source_lang}\nTarget language: {target_lang}\n"
        f"SOURCE:\n{source_text[:1500]}\n\nTARGET:\n{target_text[:1500]}\n\n"
        "Which translation style best describes TARGET?"
    )
    try:
        resp = (await _chat(prompt, system=system, max_tokens=8)).strip().lower()
    except Exception:
        resp = ""
    first = resp.split()[0] if resp else ""
    if first in ("machine", "human", "ai_llm", "unknown"):
        return first

    # Fallback: 길이 비율 + 문장 수 기반 휴리스틱.
    ratio = len(target_text) / max(len(source_text), 1)
    sc_src = _count_sentences(source_text)
    sc_tgt = _count_sentences(target_text)
    sentence_equal = sc_src > 0 and abs(sc_src - sc_tgt) <= 1

    if 0.9 <= ratio <= 1.15 and sentence_equal:
        return "machine"
    if 0.55 <= ratio < 0.9 or 1.15 < ratio <= 1.4:
        return "human"
    if ratio > 1.4:
        return "ai_llm"
    return "unknown"


async def translate_quality_score(
    source_text: str, target_text: str, source_lang: str, target_lang: str
) -> float:
    """번역 품질 0~1 추정.

    구성:
      - 의미 보존 (교차언어 임베딩 코사인, 가중치 0.6)
      - 길이 합리성 (가중치 0.2)
      - LLM 전문용어 평가 (가중치 0.2, 실패 시 0.5 로 중립 처리)
    """
    if not source_text or not target_text:
        return 0.0

    # 의미 보존.
    try:
        emb_s = await embed_text(source_text[:2000])
        emb_t = await embed_text(target_text[:2000])
        sem = max(0.0, min(1.0, (cosine(emb_s, emb_t) + 1.0) / 2.0))
    except Exception:
        sem = 0.5

    # 길이 합리성: 1.0 에 가까울수록 좋고, 극단으로 갈수록 페널티.
    lr = len(target_text) / max(len(source_text), 1)
    if _LENGTH_RATIO_MIN <= lr <= _LENGTH_RATIO_MAX:
        # 1.0 에서 가장 높고 양끝에서 0.4 까지 감소.
        dev = abs(math.log(lr)) if lr > 0 else 1.0
        len_score = max(0.4, 1.0 - dev * 0.4)
    else:
        len_score = 0.2

    # LLM 전문용어 평가.
    llm_score = 0.5
    system = (
        "Score the translation terminology accuracy 0.0~1.0. "
        "Reply with a single number only."
    )
    prompt = (
        f"{source_lang}->{target_lang}\n\nSOURCE:\n{source_text[:1200]}\n\n"
        f"TARGET:\n{target_text[:1200]}\n\nScore:"
    )
    try:
        resp = (await _chat(prompt, system=system, max_tokens=8)).strip()
        m = re.search(r"[01]?\.\d+|[01]", resp)
        if m:
            llm_score = max(0.0, min(1.0, float(m.group(0))))
    except Exception:
        llm_score = 0.5

    return round(sem * 0.6 + len_score * 0.2 + llm_score * 0.2, 4)


async def detect_translation_pair(
    fact_a: KnowledgeFact, fact_b: KnowledgeFact
) -> dict[str, Any]:
    """두 사실이 번역 관계인지 판정.

    절차:
      1) 언어 감지 → 다른 언어여야 번역 관계 성립.
      2) 교차언어 임베딩 코사인 유사도 계산.
      3) 길이/문장수 비율 검사 (요약이면 번역이 아닐 수 있음).
      4) 시간 순서 → 먼저 발행된 쪽이 원본.
      5) LLM 또는 휴리스틱으로 method 추정.
    """
    lang_a = fact_a.language or detect_language(fact_a.content)
    lang_b = fact_b.language or detect_language(fact_b.content)

    if lang_a == lang_b or lang_a == "mixed" or lang_b == "mixed":
        return {
            "is_translation": False,
            "source_fact": None,
            "target_fact": None,
            "source_lang": lang_a,
            "target_lang": lang_b,
            "similarity": 0.0,
            "confidence": 0.0,
            "method": "unknown",
        }

    # 교차언어 임베딩 유사도.
    try:
        emb_a = fact_a.embedding or await embed_text(fact_a.content[:2000])
        emb_b = fact_b.embedding or await embed_text(fact_b.content[:2000])
        sim = max(0.0, min(1.0, (cosine(emb_a, emb_b) + 1.0) / 2.0))
    except Exception:
        sim = 0.0

    # 길이 비율 — 요약/부분 번역 보정.
    ratio = len(fact_b.content) / max(len(fact_a.content), 1)
    length_ok = _LENGTH_RATIO_MIN <= ratio <= _LENGTH_RATIO_MAX

    # 다국어 임베딩이 부실할 때를 대비한 휴리스틱 보정:
    # - 영문 고유명사/숫자만 jaccard 로 잡아 보조 신호로 활용.
    try:
        jac = jaccard_similarity(fact_a.content, fact_b.content)
    except Exception:
        jac = 0.0
    # 다른 언어이면 jaccard 가 자연적으로 낮다. 고유명사/숫자가 공유되면 0.05~0.2 수준.
    jac_signal = min(jac * 2.0, 0.3)

    effective_sim = min(1.0, sim + jac_signal * 0.5)
    is_translation = effective_sim >= _CROSS_LINGUAL_SIM_THRESHOLD and length_ok

    # 시간 순서 — 먼저 발행된 쪽이 원본.
    pa = _published_at(fact_a)
    pb = _published_at(fact_b)
    if pa <= pb:
        source_fact, target_fact = fact_a, fact_b
        source_lang, target_lang = lang_a, lang_b
    else:
        source_fact, target_fact = fact_b, fact_a
        source_lang, target_lang = lang_b, lang_a

    method = "unknown"
    if is_translation:
        method = await detect_translation_method(
            source_fact.content, target_fact.content, source_lang, target_lang
        )

    # 신뢰도: 임베딩 유사도에 시간 차 가중치를 곱함 (같은 날은 가중치 낮음).
    time_gap_h = abs((pb - pa).total_seconds()) / 3600.0
    time_weight = min(1.0, 0.5 + time_gap_h / 48.0)  # 48시간 이상 차이면 1.0.
    confidence = round(effective_sim * 0.8 + time_weight * 0.2, 4) if is_translation else 0.0

    return {
        "is_translation": bool(is_translation),
        "source_fact": source_fact.id,
        "target_fact": target_fact.id,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "similarity": round(effective_sim, 4),
        "confidence": confidence,
        "method": method,
    }


# ─────────────────────────────────────────────────────────────
# 3. 등록
# ─────────────────────────────────────────────────────────────
async def register_translation(
    source_fact_id: str,
    target_fact_id: str,
    source_lang: str,
    target_lang: str,
    method: str,
    confidence: float,
    similarity: float,
) -> str | None:
    """`TranslationLink` 삽입 및 번역본의 원본 포인터 갱신.

    - unique on (sourceFactId, targetFactId) 이므로 중복 시 기존 레코드 반환.
    - target_fact(번역본) 의 `translatedFromFactId` / `languageOriginal` 를 갱신.
    """
    if not source_fact_id or not target_fact_id or source_fact_id == target_fact_id:
        return None

    link_id: str | None = None
    try:
        row = await prisma.translationlink.create(
            data={
                "sourceFactId": target_fact_id,   # 스키마상 sourceFactId=번역본
                "targetFactId": source_fact_id,   # targetFactId=원문
                "sourceLang": target_lang,
                "targetLang": source_lang,
                "translationMethod": method,
                "confidence": float(confidence),
                "textSimilarity": float(similarity),
            }
        )
        link_id = row.id
    except Exception:
        # 이미 존재하면 조회해서 id 반환.
        try:
            existing = await prisma.translationlink.find_unique(
                where={
                    "sourceFactId_targetFactId": {
                        "sourceFactId": target_fact_id,
                        "targetFactId": source_fact_id,
                    }
                }
            )
            link_id = existing.id if existing else None
        except Exception:
            link_id = None

    # 번역본 fact 에 원본 포인터 기록.
    try:
        await prisma.knowledgefact.update(
            where={"id": target_fact_id},
            data={
                "translatedFromFactId": source_fact_id,
                "languageOriginal": source_lang,
                "translationQuality": float(similarity),
            },
        )
    except Exception:
        pass

    return link_id


# ─────────────────────────────────────────────────────────────
# 4. 교차 언어 검색
# ─────────────────────────────────────────────────────────────
async def find_original_across_languages(
    fact_id: str, candidate_langs: list[str] | None = None
) -> KnowledgeFact | None:
    """같은 entity, 다른 언어, 더 이른 발행일 후보 중 원본 추정.

    교차언어 임베딩 유사도 ≥ 0.75 이고 시간상 선행이면 선택.
    복수 후보 중 유사도가 가장 높은 항목 반환.
    """
    try:
        cur = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    except Exception:
        cur = None
    if cur is None:
        return None

    my_lang = cur.language or detect_language(cur.content)
    where: dict[str, Any] = {"validFrom": {"lte": cur.validFrom}}
    if cur.entity:
        where["entity"] = cur.entity
    if candidate_langs:
        where["language"] = {"in": candidate_langs}
    where["NOT"] = {"id": fact_id}

    try:
        rows = await prisma.knowledgefact.find_many(where=where, take=50, order={"validFrom": "asc"})
    except Exception:
        rows = []

    if not rows:
        return None

    my_emb = cur.embedding or await embed_text(cur.content[:2000])

    best: tuple[float, Any] | None = None
    for r in rows:
        r_lang = r.language or detect_language(r.content)
        if r_lang == my_lang:
            continue
        try:
            r_emb = r.embedding or await embed_text(r.content[:2000])
            sim = max(0.0, min(1.0, (cosine(my_emb, r_emb) + 1.0) / 2.0))
        except Exception:
            sim = 0.0
        if sim < _CROSS_LINGUAL_SIM_THRESHOLD:
            continue
        if best is None or sim > best[0]:
            best = (sim, r)

    if not best:
        return None

    r = best[1]
    try:
        return KnowledgeFact(
            id=r.id,
            content=r.content,
            domain=r.domain,
            entity=r.entity,
            language=r.language or detect_language(r.content),
            source=r.source,
            source_url=r.sourceUrl,
            valid_from=r.validFrom,
        )
    except Exception:
        return None


async def find_translations_of(original_fact_id: str) -> list[dict[str, Any]]:
    """원문 fact 의 번역본 목록 조회 (`TranslationLink` + KnowledgeFact)."""
    try:
        links = await prisma.translationlink.find_many(
            where={"targetFactId": original_fact_id},
            order={"detectedAt": "desc"},
        )
    except Exception:
        links = []

    out: list[dict[str, Any]] = []
    for lk in links:
        try:
            f = await prisma.knowledgefact.find_unique(where={"id": lk.sourceFactId})
        except Exception:
            f = None
        out.append(
            {
                "link_id": lk.id,
                "fact_id": lk.sourceFactId,
                "language": lk.sourceLang,
                "method": lk.translationMethod,
                "confidence": float(lk.confidence),
                "similarity": float(lk.textSimilarity) if lk.textSimilarity is not None else None,
                "detected_at": lk.detectedAt,
                "content": f.content if f else None,
                "source": f.source if f else None,
                "source_url": f.sourceUrl if f else None,
            }
        )
    return out


async def scan_new_fact_for_translation(
    new_fact: KnowledgeFact, candidates_limit: int = 50
) -> dict[str, Any] | None:
    """새 fact 가 ingest 될 때 기존 다국어 fact 와 비교해 번역 관계를 감지.

    - 같은 entity + 다른 언어 후보 최대 `candidates_limit` 건.
    - 감지 시 `register_translation` 호출 후 결과 반환.
    - 감지 실패 시 None.
    """
    if not new_fact.content or not new_fact.id:
        return None

    my_lang = new_fact.language or detect_language(new_fact.content)
    where: dict[str, Any] = {"NOT": {"id": new_fact.id}}
    if new_fact.entity:
        where["entity"] = new_fact.entity

    try:
        rows = await prisma.knowledgefact.find_many(
            where=where, take=candidates_limit, order={"validFrom": "asc"}
        )
    except Exception:
        rows = []

    best: dict[str, Any] | None = None
    for r in rows:
        r_lang = r.language or detect_language(r.content)
        if r_lang == my_lang:
            continue
        try:
            other = KnowledgeFact(
                id=r.id,
                content=r.content,
                domain=r.domain,
                entity=r.entity,
                language=r_lang,
                source=r.source,
                source_url=r.sourceUrl,
                valid_from=r.validFrom,
            )
        except Exception:
            continue
        det = await detect_translation_pair(new_fact, other)
        if det.get("is_translation") and (best is None or det["similarity"] > best["similarity"]):
            best = det

    if not best:
        return None

    link_id = await register_translation(
        source_fact_id=best["source_fact"],
        target_fact_id=best["target_fact"],
        source_lang=best["source_lang"],
        target_lang=best["target_lang"],
        method=best["method"],
        confidence=best["confidence"],
        similarity=best["similarity"],
    )
    best["link_id"] = link_id
    return best


# ─────────────────────────────────────────────────────────────
# 5. 전파 분석
# ─────────────────────────────────────────────────────────────
async def trace_translation_chain(fact_id: str) -> list[dict[str, Any]]:
    """번역 체인 추적. 영→일→한 같은 다단계 번역 감지.

    - 현재 fact 에서 `translatedFromFactId` 를 따라 최상위 원본까지 거슬러 올라간다.
    - 그 후 원본의 모든 번역본을 언어별로 나열.
    """
    visited: set[str] = set()
    ancestors: list[Any] = []

    current = fact_id
    while current and current not in visited and len(visited) < 20:
        visited.add(current)
        try:
            row = await prisma.knowledgefact.find_unique(where={"id": current})
        except Exception:
            row = None
        if row is None:
            break
        ancestors.append(row)
        nxt = getattr(row, "translatedFromFactId", None)
        if not nxt:
            break
        current = nxt

    # 최상위 원본의 모든 번역본 펼치기.
    if not ancestors:
        return []
    root = ancestors[-1]
    chain_ids = [r.id for r in reversed(ancestors)]  # 원본 → ... → 현재

    try:
        descendants = await prisma.knowledgefact.find_many(
            where={"translatedFromFactId": root.id}, order={"validFrom": "asc"}
        )
    except Exception:
        descendants = []

    seen = set(chain_ids)
    combined: list[Any] = list(ancestors[::-1])  # 원본 먼저
    for d in descendants:
        if d.id not in seen:
            combined.append(d)
            seen.add(d.id)

    out: list[dict[str, Any]] = []
    for i, r in enumerate(combined):
        out.append(
            {
                "fact_id": r.id,
                "lang": r.language or detect_language(r.content),
                "published_at": r.validFrom,
                "is_original": i == 0,
                "content_preview": (r.content or "")[:120],
            }
        )
    return out


async def detect_back_translation(fact_a_id: str) -> dict[str, Any] | None:
    """역번역 감지 (한→영→한 같은 케이스).

    체인에서 언어가 A→B→A 패턴으로 재등장하면 역번역으로 판정.
    의미 왜곡 가능성이 있으므로 경고 플래그 포함.
    """
    chain = await trace_translation_chain(fact_a_id)
    if len(chain) < 3:
        return None

    langs = [c["lang"] for c in chain]
    # A-B-A 또는 A-B-C-A 등의 패턴.
    if langs[0] != langs[-1]:
        return None
    # 중간에 다른 언어가 최소 하나.
    middle = set(langs[1:-1])
    if not middle or langs[0] in middle and len(middle) == 1:
        return None

    # 원본과 최종본 임베딩 비교로 의미 왜곡 추정.
    try:
        first = await prisma.knowledgefact.find_unique(where={"id": chain[0]["fact_id"]})
        last = await prisma.knowledgefact.find_unique(where={"id": chain[-1]["fact_id"]})
    except Exception:
        first = last = None

    drift = 0.0
    if first and last:
        try:
            e1 = first.embedding or await embed_text(first.content[:2000])
            e2 = last.embedding or await embed_text(last.content[:2000])
            sim = max(0.0, min(1.0, (cosine(e1, e2) + 1.0) / 2.0))
            drift = round(1.0 - sim, 4)
        except Exception:
            drift = 0.0

    return {
        "original_fact_id": chain[0]["fact_id"],
        "back_translated_fact_id": chain[-1]["fact_id"],
        "language_path": langs,
        "chain_length": len(chain),
        "semantic_drift": drift,
        "warning": drift > 0.2,
    }


# ─────────────────────────────────────────────────────────────
# 6. 다국어 통합 응답
# ─────────────────────────────────────────────────────────────
async def unified_entity_across_languages(entity: str) -> dict[str, Any]:
    """entity 를 주제로 한 모든 언어 fact 를 통합.

    반환: {"ko": [...], "en": [...], ..., "primary_lang": "...", "original_found": bool}
    primary_lang 은 가장 오래된 fact 의 언어.
    """
    try:
        rows = await prisma.knowledgefact.find_many(
            where={"entity": entity}, order={"validFrom": "asc"}, take=200
        )
    except Exception:
        rows = []

    grouped: dict[str, list[dict[str, Any]]] = {}
    oldest: Any = None
    original_found = False
    for r in rows:
        lang = r.language or detect_language(r.content)
        grouped.setdefault(lang, []).append(
            {
                "fact_id": r.id,
                "content": (r.content or "")[:200],
                "source": r.source,
                "source_url": r.sourceUrl,
                "valid_from": r.validFrom,
                "is_original": getattr(r, "translatedFromFactId", None) is None,
            }
        )
        if oldest is None or r.validFrom < oldest.validFrom:
            oldest = r
        if getattr(r, "translatedFromFactId", None) is None:
            original_found = True

    primary_lang = (
        (oldest.language or detect_language(oldest.content)) if oldest else None
    )
    return {
        **grouped,
        "primary_lang": primary_lang,
        "original_found": original_found,
        "total_facts": len(rows),
    }


async def get_korean_equivalent(fact_id: str) -> KnowledgeFact | None:
    """fact 가 외국어면 대응하는 한국어 번역본 찾기.

    1) 번역본 관계 그래프에서 ko 언어 fact 탐색.
    2) 없으면 같은 entity 의 ko fact 중 임베딩 유사도 최고값 반환 (≥ 0.75).
    """
    try:
        cur = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    except Exception:
        cur = None
    if cur is None:
        return None

    cur_lang = cur.language or detect_language(cur.content)
    if cur_lang == "ko":
        # 이미 한국어.
        try:
            return KnowledgeFact(
                id=cur.id,
                content=cur.content,
                domain=cur.domain,
                entity=cur.entity,
                language="ko",
                source=cur.source,
                source_url=cur.sourceUrl,
                valid_from=cur.validFrom,
            )
        except Exception:
            return None

    # 1) TranslationLink 로 직접 연결된 ko 번역본.
    try:
        links = await prisma.translationlink.find_many(
            where={"targetFactId": fact_id, "sourceLang": "ko"}
        )
    except Exception:
        links = []
    for lk in links:
        try:
            f = await prisma.knowledgefact.find_unique(where={"id": lk.sourceFactId})
            if f:
                return KnowledgeFact(
                    id=f.id,
                    content=f.content,
                    domain=f.domain,
                    entity=f.entity,
                    language="ko",
                    source=f.source,
                    source_url=f.sourceUrl,
                    valid_from=f.validFrom,
                )
        except Exception:
            continue

    # 2) 같은 entity 의 ko fact 중 유사도 최고.
    if not cur.entity:
        return None
    try:
        cands = await prisma.knowledgefact.find_many(
            where={"entity": cur.entity, "language": "ko"}, take=30
        )
    except Exception:
        cands = []
    if not cands:
        return None

    my_emb = cur.embedding or await embed_text(cur.content[:2000])
    best: tuple[float, Any] | None = None
    for c in cands:
        try:
            c_emb = c.embedding or await embed_text(c.content[:2000])
            sim = max(0.0, min(1.0, (cosine(my_emb, c_emb) + 1.0) / 2.0))
        except Exception:
            sim = 0.0
        if sim >= _CROSS_LINGUAL_SIM_THRESHOLD and (best is None or sim > best[0]):
            best = (sim, c)

    if not best:
        return None

    c = best[1]
    try:
        return KnowledgeFact(
            id=c.id,
            content=c.content,
            domain=c.domain,
            entity=c.entity,
            language="ko",
            source=c.source,
            source_url=c.sourceUrl,
            valid_from=c.validFrom,
        )
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# 7. 한국 언론 특화: 외신 통신사 감지
# ─────────────────────────────────────────────────────────────
def extract_wire_agency(content: str) -> str | None:
    """"(로이터)", "로이터=연합뉴스", "= AP" 등 패턴으로 외신 통신사명 추출.

    매칭된 통신사를 소문자 ISO-ish 키로 반환 (reuters/ap/afp/...).
    """
    if not content:
        return None
    norm = unicodedata.normalize("NFKC", content)

    # 한국어 표기 → 표준 키 맵.
    ko_map = {
        "로이터": "reuters",
        "AP": "ap",
        "AFP": "afp",
        "블룸버그": "bloomberg",
        "NYT": "nyt",
        "WSJ": "wsj",
        "가디언": "guardian",
        "BBC": "bbc",
        "CNN": "cnn",
        "교도": "kyodo",
        "신화": "xinhua",
        "타스": "tass",
    }

    for pat in _WIRE_PATTERNS:
        m = pat.search(norm)
        if m:
            hit = m.group(1) if m.groups() else m.group(0)
            key = ko_map.get(hit, hit.lower())
            if key in KOREAN_FOREIGN_WIRE_AGENCIES:
                return key
    return None


async def detect_foreign_wire_origin(fact: KnowledgeFact) -> dict[str, Any] | None:
    """한국 기사가 외신 전재인지 감지.

    1) 본문 내 통신사 패턴 직접 추출.
    2) 추출 실패 시 영어 원문과의 번역 관계 탐색 (find_original_across_languages).
    """
    lang = fact.language or detect_language(fact.content)
    if lang != "ko":
        return None

    wire = extract_wire_agency(fact.content)
    if wire:
        return {
            "is_foreign_wire": True,
            "wire_agency": wire,
            "method": "pattern_match",
            "original_fact_id": None,
        }

    if not fact.id:
        return None

    original = await find_original_across_languages(fact.id, candidate_langs=["en"])
    if original is None:
        return None

    src = (original.source or "").lower()
    wire_match = next((w for w in KOREAN_FOREIGN_WIRE_AGENCIES if w in src), None)
    return {
        "is_foreign_wire": bool(wire_match),
        "wire_agency": wire_match,
        "method": "cross_lingual_match",
        "original_fact_id": original.id,
    }


# ─────────────────────────────────────────────────────────────
# 8. 통계
# ─────────────────────────────────────────────────────────────
async def translation_stats(domain: str | None = None) -> dict[str, Any]:
    """번역 관계 통계.

    반환: {"total_translations": N, "by_lang_pair": {"en->ko": ...}, "by_method": {...}}
    domain 필터가 있으면 원문 fact 의 domain 으로 필터.
    """
    try:
        links = await prisma.translationlink.find_many(take=5000)
    except Exception:
        links = []

    # domain 필터링을 위해 원문 fact id 수집.
    if domain:
        target_ids = [lk.targetFactId for lk in links]
        try:
            facts = await prisma.knowledgefact.find_many(
                where={"id": {"in": target_ids}, "domain": domain}
            )
            allowed = {f.id for f in facts}
            links = [lk for lk in links if lk.targetFactId in allowed]
        except Exception:
            pass

    by_pair: dict[str, int] = {}
    by_method: dict[str, int] = {}
    for lk in links:
        # 주의: 스키마상 sourceLang=번역본 언어, targetLang=원문 언어.
        pair = f"{lk.targetLang}->{lk.sourceLang}"
        by_pair[pair] = by_pair.get(pair, 0) + 1
        by_method[lk.translationMethod] = by_method.get(lk.translationMethod, 0) + 1

    return {
        "total_translations": len(links),
        "by_lang_pair": by_pair,
        "by_method": by_method,
    }


async def list_potential_back_translations(limit: int = 50) -> list[dict[str, Any]]:
    """잠재적 역번역 사례 리스트.

    `translatedFromFactId` 가 설정된 fact 중에서 역번역 의심 사례를 탐색.
    """
    try:
        rows = await prisma.knowledgefact.find_many(
            where={"NOT": {"translatedFromFactId": None}},
            take=min(limit * 4, 500),
            order={"validFrom": "desc"},
        )
    except Exception:
        rows = []

    out: list[dict[str, Any]] = []
    seen_chains: set[tuple[str, ...]] = set()
    for r in rows:
        if len(out) >= limit:
            break
        res = await detect_back_translation(r.id)
        if res is None:
            continue
        key = (res["original_fact_id"], res["back_translated_fact_id"])
        if key in seen_chains:
            continue
        seen_chains.add(key)
        out.append(res)
    return out


__all__ = [
    "KOREAN_FOREIGN_WIRE_AGENCIES",
    "detect_back_translation",
    "detect_foreign_wire_origin",
    "detect_language",
    "detect_translation_method",
    "detect_translation_pair",
    "extract_wire_agency",
    "find_original_across_languages",
    "find_translations_of",
    "get_korean_equivalent",
    "language_ratio",
    "list_potential_back_translations",
    "register_translation",
    "scan_new_fact_for_translation",
    "trace_translation_chain",
    "translate_quality_score",
    "translation_stats",
    "unified_entity_across_languages",
]
