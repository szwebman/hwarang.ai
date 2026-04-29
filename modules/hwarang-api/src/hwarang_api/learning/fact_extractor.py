"""응답 → 객관적 사실 추출 → HLKM 주입.

LLM(`hwarang_api.knowledge.llm._chat`) 으로 응답을 파싱해서 주관 의견·추측을 걷어내고
JSON 배열 형태의 사실만 받아 ``ingest_fact`` 로 보낸다.

자동 추출은 KYC/contributor 식별과 무관 (``bypass_gate=True``).
응답 1 개당 최대 ``MAX_FACTS_PER_RESPONSE`` 개까지만 저장한다.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from hwarang_api.knowledge.llm import _chat
from hwarang_api.knowledge.pipeline import ingest_fact
from hwarang_api.knowledge.types import (
    KnowledgeFact,
    KnowledgeStatus,
    KnowledgeVisibility,
)

logger = logging.getLogger(__name__)

MIN_RESPONSE_CHARS = 50
MIN_FACT_CHARS = 20
MAX_FACTS_PER_RESPONSE = 10

EXTRACT_SYSTEM = (
    "You are a strict fact extractor. Output ONLY a JSON array. "
    "Each element is {\"content\": \"<one objective fact>\", \"domain\": \"law|medical|tax|code|finance|tech|general\"}. "
    "Skip opinions, speculation, generic advice, or background commentary."
)

EXTRACT_PROMPT = """다음 응답에서 객관적 사실만 추출해라.
- 의견, 추측, 일반 조언, 배경 설명 제외.
- 한 문장 = 한 사실, 명사로 시작하는 자연스러운 한국어.
- 출력은 JSON 배열만, 마크다운 코드펜스 금지.

응답:
\"\"\"
{response}
\"\"\"

JSON:"""


_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def parse_json_array(raw: str) -> list[dict[str, Any]]:
    """LLM 출력에서 JSON 배열을 견고하게 복구."""
    if not raw:
        return []
    text = raw.strip()
    # 코드펜스 제거
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # 1차: 그대로 파싱
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except Exception:
        pass

    # 2차: 첫 [ ... ] 블록만 추출
    m = _JSON_ARRAY_RE.search(text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except Exception:
        return []
    return []


async def extract_and_ingest_facts(response: str, domain: str = "general") -> dict:
    """응답에서 사실을 추출 → HLKM ingest_fact.

    반환: ``{"extracted": int, "ingested": int, "fact_ids": [str], "skipped": int}``
    실패해도 예외를 올리지 않는다 (fire-and-forget 친화).
    """
    if not response or len(response) < MIN_RESPONSE_CHARS:
        return {"extracted": 0, "ingested": 0, "fact_ids": [], "skipped": 0}

    try:
        raw = await _chat(
            EXTRACT_PROMPT.format(response=response[:4000]),
            system=EXTRACT_SYSTEM,
            max_tokens=512,
        )
    except Exception as e:
        logger.debug(f"LLM 사실 추출 호출 실패: {e}")
        return {"extracted": 0, "ingested": 0, "fact_ids": [], "error": str(e)}

    facts = parse_json_array(raw)
    if not facts:
        return {"extracted": 0, "ingested": 0, "fact_ids": [], "skipped": 0}

    ingested = 0
    skipped = 0
    fact_ids: list[str] = []
    now = datetime.now(timezone.utc)

    for f in facts[:MAX_FACTS_PER_RESPONSE]:
        content = (f.get("content") or "").strip()
        if not content or len(content) < MIN_FACT_CHARS:
            skipped += 1
            continue

        fact_domain = (f.get("domain") or domain or "general").strip().lower()

        try:
            fact = KnowledgeFact(
                content=content,
                domain=fact_domain,
                source="auto_extracted",
                source_type="agent",
                valid_from=now,
                last_verified_at=now,
                confidence_t0=0.5,  # LLM 추출은 보수적
                status=KnowledgeStatus.PENDING,
                visibility=KnowledgeVisibility.PUBLIC,
            )
            result = await ingest_fact(fact, bypass_gate=True)
            fid = result.get("fact_id")
            if fid:
                fact_ids.append(fid)
                if result.get("action") in {"inserted", "superseded"}:
                    ingested += 1
                else:
                    skipped += 1
            else:
                skipped += 1
        except Exception as e:  # pragma: no cover
            logger.debug(f"ingest_fact 실패(스킵): {e}")
            skipped += 1
            continue

    return {
        "extracted": len(facts),
        "ingested": ingested,
        "fact_ids": fact_ids,
        "skipped": skipped,
    }


__all__ = ["extract_and_ingest_facts", "parse_json_array"]
