"""Adversarial Self-Play 라우터 (Group θ).

엔드포인트
----------
* POST /api/self-play/debate          — 다회차 토론 실행
* POST /api/self-play/auto-debate     — 자동 트리거 + (필요시) 토론 실행
* POST /api/self-play/find-errors     — transcript 에서 모순/근거없음 추출
* GET  /api/self-play/personas        — 페르소나 목록
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hwarang_api.cognitive.self_play import (
    PERSONAS,
    AutoDebateTrigger,
    ConsensusFinder,
    DebateOrchestrator,
    ErrorDiscoverer,
)
from hwarang_api.cognitive.self_play.debate_orchestrator import (
    DEFAULT_PERSONAS,
    Turn,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/self-play", tags=["SelfPlay"])


# ────────────────────────────────────────────────────────────
# 요청 모델
# ────────────────────────────────────────────────────────────
class DebateRequest(BaseModel):
    question: str = Field(..., description="원 질문")
    initial_answer: str = Field(..., description="토론 대상 초기 답변")
    personas: Optional[list[str]] = Field(
        default=None, description="페르소나 이름 목록 (미지정 시 기본값)"
    )
    rounds: int = Field(default=3, ge=1, le=12, description="라운드 수")


class AutoDebateRequest(BaseModel):
    question: str
    draft_answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class TurnIn(BaseModel):
    round: int
    persona: str
    content: str
    timestamp: Optional[float] = None


class FindErrorsRequest(BaseModel):
    transcript: list[TurnIn]
    initial_answer: Optional[str] = None


# ────────────────────────────────────────────────────────────
# 엔드포인트
# ────────────────────────────────────────────────────────────
@router.get("/personas")
async def list_personas() -> dict[str, Any]:
    """등록된 페르소나 목록 반환."""
    return {
        "personas": [
            {
                "name": p.name,
                "focus": p.focus,
                "system_prompt": p.system_prompt,
            }
            for p in PERSONAS.values()
        ],
        "defaults": DEFAULT_PERSONAS,
    }


@router.post("/debate")
async def debate(body: DebateRequest) -> dict[str, Any]:
    """다회차 토론 실행 → 통합 답변 반환."""
    orchestrator = DebateOrchestrator()
    try:
        result = await orchestrator.run_debate(
            question=body.question,
            initial_answer=body.initial_answer,
            personas=body.personas,
            rounds=body.rounds,
        )
    except ValueError as e:
        # 비용 가드 위반
        raise HTTPException(status_code=400, detail=str(e))

    # 합의 분석 추가
    consensus = await ConsensusFinder().analyze_consensus(result.transcript)

    payload = result.to_dict()
    payload["consensus"] = consensus.to_dict()
    return payload


@router.post("/auto-debate")
async def auto_debate(body: AutoDebateRequest) -> dict[str, Any]:
    """자동 트리거 — 필요할 때만 토론 실행.

    토론 불필요 시 {triggered: false, ...} 만 반환.
    """
    trig = AutoDebateTrigger()
    triggered = trig.should_debate(body.question, body.draft_answer, body.confidence)
    if not triggered:
        return {
            "triggered": False,
            "reason": "신뢰도 충분 + 위험 키워드 없음 + 절대주의 표현 없음",
            "draft_answer": body.draft_answer,
        }

    personas = trig.recommended_personas(body.question)
    orchestrator = DebateOrchestrator()
    try:
        result = await orchestrator.run_debate(
            question=body.question,
            initial_answer=body.draft_answer,
            personas=personas,
            rounds=3,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    consensus = await ConsensusFinder().analyze_consensus(result.transcript)
    payload = result.to_dict()
    payload["triggered"] = True
    payload["selected_personas"] = personas
    payload["consensus"] = consensus.to_dict()
    return payload


@router.post("/find-errors")
async def find_errors(body: FindErrorsRequest) -> dict[str, Any]:
    """transcript 에서 모순 + 근거 없는 클레임 + 수정안 생성."""
    transcript: list[Turn] = [
        Turn(
            round=t.round,
            persona=t.persona,
            content=t.content,
            timestamp=t.timestamp if t.timestamp is not None else 0.0,
        )
        for t in body.transcript
    ]

    discoverer = ErrorDiscoverer()
    contradictions = await discoverer.find_self_contradictions(transcript)
    unsupported = await discoverer.find_unsupported_claims(
        body.initial_answer or "",
        transcript,
    )
    corrections = await discoverer.propose_corrections(contradictions, unsupported)

    return {
        "contradictions": [c.to_dict() for c in contradictions],
        "unsupported_claims": unsupported,
        "proposed_corrections": corrections,
    }
