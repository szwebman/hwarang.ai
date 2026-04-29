"""화랑 관련성 정밀 필터 (이중).

1단계 (arxiv_crawler.is_hwarang_relevant): 키워드 substring 매칭
2단계 (이 모듈): LLM 기반 정밀 평가 — 적용 가능 모듈 + 신뢰도
"""

from __future__ import annotations

import json
import re

from hwarang_api.knowledge.llm import _chat as llm_chat


RELEVANCE_PROMPT = """다음 AI 논문이 화랑 (한국어 LLM, 도메인 특화 LoRA, 연합학습, 지식그래프) 시스템에 적용 가능한가?

논문:
제목: {title}
초록: {abstract}

JSON: {{"relevant": true|false, "score": 0~1, "applicable_modules": ["..."], "reasoning": "한 줄"}}
JSON 만 출력:"""


HWARANG_MODULES = [
    "HSEE Phase 1 (compounding loop)",
    "HSEE Phase 2 (online LoRA + EWC)",
    "HSEE Phase 3 (self-growing)",
    "HSEE Phase 4 (custom inference engine)",
    "HSEE Phase 5 (curiosity / self-questioning)",
    "HNTL (neural topic LoRA routing)",
    "HRAG (Korean retrieval)",
    "HFL (federated LoRA training)",
    "HLKM (knowledge graph + temporal)",
    "TrustedSource (fact verification)",
    "Speculative Decoding",
    "Quantization (AWQ/GPTQ)",
    "Korean tokenizer",
]


async def evaluate_relevance(paper) -> dict:
    """LLM 으로 정밀 평가 — paper 는 Prisma Paper 또는 dict.

    반환: {"relevant": bool, "score": float, "applicable_modules": [str], "reasoning": str}
    실패 시 보수적 기본값 반환 (relevant=True, score=0.5).
    """
    title = getattr(paper, "title", None) or paper.get("title", "")
    abstract = getattr(paper, "abstract", None) or paper.get("abstract", "")

    try:
        raw = await llm_chat(
            RELEVANCE_PROMPT.format(
                title=title[:200],
                abstract=abstract[:1500],
            )
        )
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:  # noqa: BLE001
        pass
    return {
        "relevant": True,
        "score": 0.5,
        "applicable_modules": [],
        "reasoning": "",
    }
