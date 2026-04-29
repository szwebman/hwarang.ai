"""변경 제안 생성 모듈.

LLM에게 현재 파일과 관찰된 문제를 제시하고, 최소한의 변경 제안을 받는다.
Hard-block 경로는 절대 제안하지 않는다.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

RiskLevel = Literal["low", "medium", "high", "critical"]


# Hard-block: 절대 자체 변경 제안을 허용하지 않는 경로 패턴.
# 인증/결제/스키마/배포/자기 자신 디렉터리 — 한 번 잘못 건드리면 시스템 전체가 위험.
HARD_BLOCK_PATTERNS: tuple[str, ...] = (
    "prisma/schema.prisma",
    "scripts/deploy.sh",
    "modules/hwarang-api/src/hwarang_api/auth/",
    "modules/hwarang-api/src/hwarang_api/billing/",
    "cognitive/self_modify/",  # 재귀적 자기 변경 금지
)

HARD_BLOCK_FILENAME_REGEX = re.compile(r"(^|/)\.env(\..+)?$")


@dataclass
class ChangeProposal:
    """LLM이 생성한 코드 변경 제안.

    Attributes:
        file_path: 대상 파일 (절대 또는 프로젝트 루트 상대 경로)
        current_code: 현재 파일 내용
        proposed_code: LLM이 제안한 새 내용
        reason: 변경 이유
        expected_benefit: 예상되는 이점
        risk_level: low / medium / high / critical
    """

    file_path: str
    current_code: str
    proposed_code: str
    reason: str
    expected_benefit: str
    risk_level: RiskLevel = "medium"


def is_hard_blocked(file_path: str) -> bool:
    """Hard-block 경로인지 검사."""
    normalized = file_path.replace("\\", "/")
    for pattern in HARD_BLOCK_PATTERNS:
        if pattern in normalized:
            return True
    if HARD_BLOCK_FILENAME_REGEX.search(normalized):
        return True
    return False


def analyze_risk(proposal: ChangeProposal) -> RiskLevel:
    """파일 경로 기반으로 위험도를 자동 조정한다.

    LLM이 risk_level을 낮게 평가했더라도, 경로 자체가 민감하면 강제로 상향한다.
    """
    path = proposal.file_path.replace("\\", "/").lower()
    declared = proposal.risk_level

    # critical 경로 — 자동으로 critical 로 강제 상향
    critical_keywords = (
        "auth/",
        "billing/",
        "admin/",
        "prisma/schema",
        "deploy.sh",
        "scripts/deploy",
        "alembic/",
        "migrations/",
    )
    for kw in critical_keywords:
        if kw in path:
            return "critical"

    # high — LLM 프롬프트, 주요 로직
    if "prompt" in path or "/llm/" in path or path.endswith("_prompt.py"):
        return "high" if declared in ("low", "medium") else declared

    # low — 표시용 문자열만 변경
    if path.endswith((".md", ".txt", ".rst")) or "/i18n/" in path or "/locales/" in path:
        return "low"

    # 그 외에는 LLM 선언값 유지(단, 알려진 단계만 허용)
    if declared not in ("low", "medium", "high", "critical"):
        return "high"  # 모호 → 보수적으로 상향
    return declared


def _safe_read(file_path: str) -> Optional[str]:
    """프로젝트 루트 기준 또는 절대 경로로 안전하게 파일을 읽는다."""
    try:
        p = Path(file_path)
        if not p.exists():
            # 프로젝트 루트 기준으로 시도
            return None
        if p.is_dir():
            return None
        # 1MB 초과 파일은 자체개선 대상이 아니라고 판단 (보수적 거부)
        if p.stat().st_size > 1_000_000:
            logger.warning(f"파일이 너무 크다(>1MB), 거부: {file_path}")
            return None
        return p.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"파일 읽기 실패 {file_path}: {e}")
        return None


def _extract_json_block(text: str) -> Optional[dict[str, Any]]:
    """LLM 응답에서 JSON 객체를 안전하게 추출한다."""
    if not text:
        return None
    # 코드 펜스 제거 시도
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    # 첫 번째 균형 잡힌 { ... } 시도
    start = text.find("{")
    if start >= 0:
        candidates.append(text[start:])

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    return None


def generate_proposal(
    file_path: str,
    observation: str,
    llm: Any,
) -> Optional[ChangeProposal]:
    """LLM을 호출해 변경 제안을 생성한다.

    Args:
        file_path: 대상 파일 경로
        observation: 관찰된 문제 (LLM에게 전달할 설명)
        llm: 호출 가능한 LLM 인터페이스. `llm(prompt: str) -> str` 또는
             `llm.generate(prompt: str) -> str` 를 지원.

    Returns:
        ChangeProposal 또는 None (hard-block, 파일 부재, JSON 파싱 실패 시)
    """
    # 1차 방어: hard-block
    if is_hard_blocked(file_path):
        logger.warning(f"Hard-blocked 경로, 제안 거부: {file_path}")
        return None

    current = _safe_read(file_path)
    if current is None:
        logger.warning(f"파일 읽기 실패 또는 부재, 제안 거부: {file_path}")
        return None

    prompt = (
        "당신은 화랑 시스템의 자체개선 보조자다.\n"
        f"현재 파일이 다음 문제를 가지고 있다: {observation}\n\n"
        "최소한의 변경으로 개선해라. 50줄 이상 변경은 금지.\n"
        "위험한 패턴(exec, eval, os.system, shell=True, hardcoded API key)은 절대 사용하지 마라.\n\n"
        "현재 파일 내용:\n"
        "```\n"
        f"{current}\n"
        "```\n\n"
        "JSON으로만 응답해라(다른 텍스트 금지). 스키마:\n"
        "{\n"
        '  "proposed_code": "<수정된 전체 파일 내용>",\n'
        '  "reason": "<변경 이유 (한국어)>",\n'
        '  "risk_level": "low" | "medium" | "high" | "critical",\n'
        '  "expected_benefit": "<예상 이점 (한국어)>"\n'
        "}\n"
    )

    try:
        if callable(llm):
            response = llm(prompt)
        elif hasattr(llm, "generate"):
            response = llm.generate(prompt)
        else:
            logger.error("LLM 인터페이스가 호환되지 않는다 (callable 또는 .generate 필요)")
            return None
    except Exception as e:
        logger.error(f"LLM 호출 실패: {e}")
        return None

    if not isinstance(response, str):
        response = str(response)

    parsed = _extract_json_block(response)
    if parsed is None:
        logger.warning("LLM 응답 JSON 파싱 실패, 제안 거부")
        return None

    required = ("proposed_code", "reason", "risk_level", "expected_benefit")
    for key in required:
        if key not in parsed:
            logger.warning(f"LLM 응답에 필수 키 누락: {key}, 제안 거부")
            return None

    risk = parsed.get("risk_level")
    if risk not in ("low", "medium", "high", "critical"):
        logger.warning(f"잘못된 risk_level: {risk}, 제안 거부")
        return None

    proposal = ChangeProposal(
        file_path=file_path,
        current_code=current,
        proposed_code=str(parsed["proposed_code"]),
        reason=str(parsed["reason"]),
        expected_benefit=str(parsed["expected_benefit"]),
        risk_level=risk,
    )

    # 2차 방어: 자동 위험도 상향
    proposal.risk_level = analyze_risk(proposal)
    return proposal
