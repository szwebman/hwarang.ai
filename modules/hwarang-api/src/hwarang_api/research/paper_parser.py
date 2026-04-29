"""arxiv PDF → 구조화 (intro/method/results 분리).

도구:
1. arxiv 라이브러리 (메타데이터)
2. pypdf 또는 pdfminer (전체 텍스트)
3. 정규식 + LLM 으로 섹션 분할

매 시간 cron — pending Paper 들 처리 → status="parsed"
"""

from __future__ import annotations

import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


SECTION_PATTERNS = {
    "abstract": r"(?i)abstract",
    "introduction": r"(?i)1\.?\s*introduction|^introduction",
    "method": r"(?i)\b(?:methods?|approach|model|architecture)\b",
    "results": r"(?i)\b(?:results?|experiments?|evaluation)\b",
    "conclusion": r"(?i)\b(?:conclusions?|discussion)\b",
    "references": r"(?i)\breferences\b",
}


CONTRIBUTION_PROMPT = """다음 논문 abstract 와 introduction 에서:
1. 핵심 기여 (1줄 한국어)
2. method 요약 (5줄 한국어)

JSON: {{"contribution": "...", "method": "..."}}
JSON 만 출력:

abstract+intro:
{text}"""


async def parse_pending_papers(batch_size: int = 20) -> dict:
    """매 시간 cron — pending → parsed."""
    try:
        pending = await prisma.paper.find_many(
            where={"status": "pending"},
            take=batch_size,
            order={"publishedAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper.find_many 실패: %s", exc)
        return {"parsed": 0, "reason": "db_error"}

    if not pending:
        return {"parsed": 0, "candidates": 0}

    parsed_count = 0
    failed = 0

    for paper in pending:
        try:
            full_text = await _download_pdf_text(paper.pdfUrl)
            if not full_text:
                # PDF 못 읽음 — abstract 만으로 진행
                full_text = paper.abstract or ""

            sections = _split_sections(full_text)

            # LLM 으로 contribution / method 추출
            ai_summary = await _extract_summary(
                f"{paper.abstract}\n\n{sections.get('introduction', '')[:3000]}"
            )

            # Github 링크 본문에서 한 번 더 검색
            code_url = paper.codeUrl
            if not code_url:
                m = re.search(r"github\.com/[\w\-]+/[\w\-]+", full_text)
                if m:
                    code_url = f"https://{m.group()}"

            await prisma.paper.update(
                where={"id": paper.id},
                data={
                    "contribution": ai_summary.get("contribution", "")[:500],
                    "methodSummary": ai_summary.get("method", "")[:1500],
                    "codeUrl": code_url,
                    "status": "parsed",
                    "parsedAt": datetime.now(timezone.utc),
                },
            )
            parsed_count += 1
        except Exception as e:  # noqa: BLE001
            logger.debug("paper parse 실패 %s: %s", paper.arxivId, e)
            failed += 1

    return {
        "parsed": parsed_count,
        "failed": failed,
        "candidates": len(pending),
    }


async def _download_pdf_text(pdf_url: str) -> Optional[str]:
    """PDF 다운로드 + 텍스트 추출."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(pdf_url, follow_redirects=True)
        if resp.status_code != 200:
            return None

        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(resp.content))
        # 첫 30 페이지까지만 (긴 논문 방지)
        text = "\n".join(
            (p.extract_text() or "") for p in reader.pages[:30]
        )
        return text[:50000]
    except ImportError:
        logger.warning("pypdf 미설치 — PDF 파싱 불가")
        return None
    except Exception as e:  # noqa: BLE001
        logger.debug("PDF download/parse 실패: %s", e)
        return None


def _split_sections(text: str) -> dict:
    """간단한 정규식 기반 섹션 분할."""
    sections: dict[str, str] = {}
    for name, pattern in SECTION_PATTERNS.items():
        m = re.search(pattern, text)
        if not m:
            continue
        start = m.end()
        # 다음 섹션 시작 지점 찾기
        next_starts = []
        for other_name, other_pattern in SECTION_PATTERNS.items():
            if other_name == name:
                continue
            other_m = re.search(other_pattern, text[start:])
            if other_m:
                next_starts.append(start + other_m.start())
        end = min(next_starts) if next_starts else len(text)
        sections[name] = text[start:end].strip()[:5000]
    return sections


async def _extract_summary(text: str) -> dict:
    """LLM 으로 contribution + method 추출 — 실패 시 빈 dict."""
    try:
        raw = await llm_chat(CONTRIBUTION_PROMPT.format(text=text[:4000]))
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:  # noqa: BLE001
        pass
    return {"contribution": "", "method": ""}
