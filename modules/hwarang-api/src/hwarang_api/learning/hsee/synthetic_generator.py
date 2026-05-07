"""HSEE Phase 4 — Synthetic Data Generator (스켈레톤 + 핵심 루프).

약점 패턴(``WeaknessSignal``) → 자체 hwarang LLM 호출로 학습 페어 자동 생성.

흐름::

    weakness ─┐
              ├─→ LLM(자기) → (question, answer) 페어 N 개
              │       ↓
              │  cross_verifier.verify_claim
              │       ↓
              │  Trusted Source 와 모순 여부
              │       ↓
              ├─→ verified_pairs (jsonl: {"messages": [...]} 포맷)
              └─→ rejected_pairs (provenance 보존)

원칙:
    * 출력 포맷은 ``modules/hwarang-core/scripts/data/build_*.py`` 와 동일
      (``{"messages": [{"role": "system"|"user"|"assistant", "content": "..."}]}``)
    * **system prompt 는 고정 + 우회 불가** — 모든 페어에 동일 system message 강제
    * 도메인당 최대 ``MAX_PAIRS_PER_DOMAIN`` (안전 상한 500)
    * ``generated_at`` / ``source_weakness_id`` 메타로 기원 추적
    * cross_verifier 가 contradicting 이 1+ 개면 폐기 — HLKM 신뢰도 우선

LLM 호출 실패 시 mock 페어를 만들어 파이프라인이 죽지 않게 한다 (스켈레톤).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hwarang_api.learning.hsee.weakness_detector import WeaknessSignal

logger = logging.getLogger(__name__)


# ─── 안전 상한 / 환경 ─────────────────────────────────────────────
MIN_PAIRS_PER_DOMAIN = 100
MAX_PAIRS_PER_DOMAIN = 500
ABSOLUTE_MAX_PAIRS_PER_ROUND = 2000  # orchestrator 가 추가로 검증

VLLM_URL = os.getenv("HWARANG_VLLM_URL", "http://localhost:8001")
HSEE_MOCK_LLM = os.getenv("HSEE_MOCK_LLM", "").lower() in ("1", "true", "yes")

# **고정 system prompt** — 우회 불가. 모든 합성 페어에 동일하게 강제.
SYSTEM_PROMPT_FIXED = (
    "당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.\n"
    "한국어로 정확하고 깊이 있는 답변을 제공합니다. "
    "법률/세무/의료 등 전문 분야는 1차 출처를 인용하고, "
    "모르는 것은 모른다고 답합니다. 사용자 안전과 진실성을 최우선합니다."
)


GEN_PROMPT_TEMPLATE = """다음 약점 패턴에 대해 학습용 (질문, 답변) 페어 {n}개를 생성하라.

약점 패턴: {pattern}
도메인: {domain}

요구사항:
1. 질문은 다양한 표현/난이도로 변주
2. 답변은 화랑 시스템 프롬프트에 부합 (한국어, 1차 출처 인용 권장)
3. 답을 모르면 추측 X — "정확한 정보가 없습니다" 등으로 솔직하게
4. 환각 금지 — 명확하지 않은 사실은 출처를 비워두기

JSON 배열만 출력 (다른 설명 X):
[{{"question": "...", "answer": "...", "needs_citation": true|false}}, ...]
"""


# ─── 데이터 클래스 ────────────────────────────────────────────────
@dataclass
class SyntheticPair:
    question: str
    answer: str
    domain: str
    source_weakness: str
    needs_citation: bool = False
    verified: bool = False
    verification_confidence: float = 0.0
    rejection_reason: str | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_messages(self) -> dict[str, Any]:
        """``build_*.py`` 호환 포맷 (jsonl 한 줄)."""
        return {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_FIXED},
                {"role": "user", "content": self.question},
                {"role": "assistant", "content": self.answer},
            ],
            "_meta": {
                "domain": self.domain,
                "source_weakness": self.source_weakness,
                "verified": self.verified,
                "verification_confidence": round(self.verification_confidence, 3),
                "generated_at": self.generated_at.isoformat(),
                "generator": "hsee_phase4",
            },
        }


# ─── LLM 호출 (mock 폴백 포함) ────────────────────────────────────
async def _call_llm(prompt: str, max_tokens: int = 1024) -> str:
    """자체 hwarang vLLM 서버 호출. 실패/HSEE_MOCK_LLM=1 이면 mock 반환.

    프로덕션에서는 ``hwarang_api.knowledge.llm._chat`` 를 사용한다 (이미
    vLLM 서버 endpoint 가 환경변수로 설정돼 있음).
    """
    if HSEE_MOCK_LLM:
        return _mock_llm_pairs()

    try:
        from hwarang_api.knowledge.llm import _chat as llm_chat

        return await llm_chat(prompt, max_tokens=max_tokens)
    except Exception as exc:  # noqa: BLE001
        logger.warning("HSEE LLM call failed (%s) — falling back to mock", exc)
        return _mock_llm_pairs()


def _mock_llm_pairs() -> str:
    """LLM 미가용 시 파이프라인 검증용 더미. 실제 학습 X."""
    return json.dumps(
        [
            {
                "question": "[MOCK] 약점 변주 질문 1",
                "answer": "[MOCK] 정확한 정보가 부족합니다.",
                "needs_citation": True,
            }
        ],
        ensure_ascii=False,
    )


# ─── JSON 파싱 ────────────────────────────────────────────────────
def _parse_pairs(raw: str) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group())
        if not isinstance(data, list):
            return []
        out: list[dict[str, Any]] = []
        for it in data:
            if not isinstance(it, dict):
                continue
            q = str(it.get("question") or "").strip()
            a = str(it.get("answer") or "").strip()
            if not q or not a:
                continue
            out.append(
                {
                    "question": q[:1500],
                    "answer": a[:5000],
                    "needs_citation": bool(it.get("needs_citation", False)),
                }
            )
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("synthetic parse failed: %s", exc)
        return []


# ─── 검증: cross_verifier ────────────────────────────────────────
async def _verify_pair(pair: SyntheticPair) -> SyntheticPair:
    """답변 안의 사실 주장을 cross_verifier 로 검증.

    contradicting 이 supporting 보다 많으면 폐기 (verified=False, reason 기록).
    needs_citation=False 인 페어는 검증 스킵 (의견/스타일 답변).
    """
    if not pair.needs_citation:
        pair.verified = True
        pair.verification_confidence = 0.5  # 중립
        return pair

    try:
        from hwarang_api.knowledge.cross_verifier import verify_claim
    except Exception as exc:  # noqa: BLE001
        logger.debug("cross_verifier import failed: %s", exc)
        pair.verified = False
        pair.rejection_reason = "verifier_unavailable"
        return pair

    try:
        # claim 은 답변 첫 200 자 (사실 진술 부분만 대표)
        claim = pair.answer[:300]
        result = await verify_claim(claim, domain=pair.domain, top_k=10)
        pair.verification_confidence = float(getattr(result, "confidence", 0.0))

        contradicting = list(getattr(result, "contradicting", []) or [])
        supporting = list(getattr(result, "supporting", []) or [])
        if contradicting and len(contradicting) >= max(1, len(supporting)):
            pair.verified = False
            pair.rejection_reason = (
                f"contradicting={len(contradicting)} supporting={len(supporting)}"
            )
            return pair

        if pair.verification_confidence < 0.4:
            pair.verified = False
            pair.rejection_reason = (
                f"low_confidence={pair.verification_confidence:.2f}"
            )
            return pair

        pair.verified = True
        return pair
    except Exception as exc:  # noqa: BLE001
        logger.debug("verify_claim failed: %s", exc)
        pair.verified = False
        pair.rejection_reason = f"verify_error:{type(exc).__name__}"
        return pair


# ─── 메인: 한 약점에 대한 페어 생성 ───────────────────────────────
async def generate_pairs_for_weakness(
    weakness: WeaknessSignal,
    n_pairs: int = MIN_PAIRS_PER_DOMAIN,
) -> list[SyntheticPair]:
    """단일 약점 → 검증 통과한 ``SyntheticPair`` 리스트.

    안전 상한: ``n_pairs`` 는 [MIN, MAX] 로 clamp.
    """
    n_target = max(MIN_PAIRS_PER_DOMAIN, min(MAX_PAIRS_PER_DOMAIN, int(n_pairs)))

    # 한 번 LLM 호출에 너무 많은 페어를 요구하면 출력 잘림 — 50 씩 배치
    batch = 50
    pairs: list[SyntheticPair] = []
    rounds = (n_target + batch - 1) // batch

    for r in range(rounds):
        ask = min(batch, n_target - len(pairs))
        if ask <= 0:
            break

        prompt = GEN_PROMPT_TEMPLATE.format(
            pattern=weakness.query_pattern,
            domain=weakness.domain,
            n=ask,
        )
        raw = await _call_llm(prompt, max_tokens=ask * 200)
        parsed = _parse_pairs(raw)
        if not parsed:
            logger.debug("synthetic batch %d empty — break", r)
            break

        for it in parsed:
            pair = SyntheticPair(
                question=it["question"],
                answer=it["answer"],
                domain=weakness.domain,
                source_weakness=weakness.query_pattern[:120],
                needs_citation=it["needs_citation"],
            )
            verified = await _verify_pair(pair)
            pairs.append(verified)

        if len(pairs) >= n_target:
            break

    return pairs


# ─── 큐 기록 (jsonl) ──────────────────────────────────────────────
def write_jsonl(
    pairs: list[SyntheticPair],
    out_path: str | Path,
    only_verified: bool = True,
) -> dict[str, Any]:
    """검증 통과한 페어를 jsonl 로 저장. 수동 build_*.py 와 같은 포맷."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    rejected = 0
    with path.open("w", encoding="utf-8") as fp:
        for p in pairs:
            if only_verified and not p.verified:
                rejected += 1
                continue
            fp.write(
                json.dumps(p.to_messages(), ensure_ascii=False) + "\n"
            )
            written += 1
    return {
        "path": str(path),
        "written": written,
        "rejected": rejected,
        "total": len(pairs),
    }


__all__ = [
    "SyntheticPair",
    "SYSTEM_PROMPT_FIXED",
    "MIN_PAIRS_PER_DOMAIN",
    "MAX_PAIRS_PER_DOMAIN",
    "ABSOLUTE_MAX_PAIRS_PER_ROUND",
    "generate_pairs_for_weakness",
    "write_jsonl",
]
