"""학습 라운드 후 자기 평가.

라운드 끝나면:
1. 학습 시간 / 사용 GPU 등 측정
2. 마스터에서 받은 quality score 와 비교
3. "다음엔 X 도메인 우선" 같은 lesson 누적

저장 위치: ~/.hwarang/agent_stats.json
- 일자별 rounds_completed / rounds_failed / assessments[] 누적
- 90일 이상 데이터는 자동 정리
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SelfAssessment:
    round_id: str
    domain: str
    duration_minutes: float
    quality_score: Optional[float]  # 마스터에서 평가 받은 점수
    self_quality_estimate: float    # 자기 추정 (loss 등)
    hwr_earned: float
    lesson: Optional[str]


async def assess_round_outcome(
    round_id: str,
    domain: str,
    duration_minutes: float,
    quality_score: Optional[float],
    self_quality_estimate: float,
    hwr_earned: float,
) -> SelfAssessment:
    """라운드 종료 후 자기 평가.

    Args:
        round_id: 끝난 라운드 ID.
        domain: 라운드 도메인 (legal/medical/code/general 등).
        duration_minutes: 학습 소요 시간.
        quality_score: 마스터에서 받은 합산 품질 점수 (0~1). None 이면 미평가.
        self_quality_estimate: 학습 loss 등으로 자기 추정한 품질 (0~1).
        hwr_earned: 이번 라운드로 적립된 HWR.

    Returns:
        SelfAssessment — lesson 필드에 다음 라운드를 위한 교훈.
    """

    # 교훈 도출
    lesson: Optional[str] = None
    if quality_score is not None:
        if quality_score < 0.5:
            lesson = f"{domain} 도메인 라운드 품질 낮음 — 다음엔 거절 고려"
        elif quality_score > 0.8:
            lesson = f"{domain} 도메인 잘함 — 같은 도메인 더 적극 참여"

    # 자기 추정 vs 실제 비교
    if quality_score is not None and self_quality_estimate:
        diff = abs(quality_score - self_quality_estimate)
        if diff > 0.2:
            extra = f"자기 추정 오류 {diff:.2f} — 메트릭 보정 필요"
            lesson = f"{lesson} / {extra}" if lesson else extra

    assessment = SelfAssessment(
        round_id=round_id,
        domain=domain,
        duration_minutes=duration_minutes,
        quality_score=quality_score,
        self_quality_estimate=self_quality_estimate,
        hwr_earned=hwr_earned,
        lesson=lesson,
    )

    # 캐시에 저장
    try:
        _save_assessment(assessment)
    except Exception as exc:  # 파일 쓰기 실패는 평가 자체를 막지 않음
        logger.warning("self_assessor 저장 실패: %s", exc)
    return assessment


def _save_assessment(a: SelfAssessment) -> None:
    """~/.hwarang/agent_stats.json 에 누적."""
    path = Path.home() / ".hwarang" / "agent_stats.json"
    path.parent.mkdir(exist_ok=True)

    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}

    today = datetime.now().strftime("%Y-%m-%d")
    if today not in data:
        data[today] = {
            "rounds_completed": 0,
            "rounds_failed": 0,
            "assessments": [],
        }

    bucket = data[today]
    if a.quality_score is not None and a.quality_score > 0.5:
        bucket["rounds_completed"] = int(bucket.get("rounds_completed", 0)) + 1
    elif a.quality_score is not None and a.quality_score <= 0.5:
        bucket["rounds_failed"] = int(bucket.get("rounds_failed", 0)) + 1

    bucket.setdefault("assessments", []).append({
        "round_id": a.round_id,
        "domain": a.domain,
        "duration_minutes": a.duration_minutes,
        "quality": a.quality_score,
        "self_estimate": a.self_quality_estimate,
        "hwr": a.hwr_earned,
        "lesson": a.lesson,
        "ts": datetime.now().isoformat(timespec="seconds"),
    })

    # 90일 이상 데이터 정리
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    data = {k: v for k, v in data.items() if k >= cutoff}

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    # 최근 라운드 점수도 별도 캐시 (state_collector 가 읽음)
    if a.quality_score is not None:
        recent_path = Path.home() / ".hwarang" / "agent_recent.json"
        try:
            recent_data: dict = {}
            if recent_path.exists():
                recent_data = json.loads(recent_path.read_text()) or {}
                if not isinstance(recent_data, dict):
                    recent_data = {}
            recent_data["last_round_score"] = a.quality_score
            recent_data["last_round_id"] = a.round_id
            recent_data["last_round_domain"] = a.domain
            recent_data["last_round_ts"] = datetime.now().isoformat(timespec="seconds")
            recent_path.write_text(json.dumps(recent_data, ensure_ascii=False, indent=2))
        except Exception as exc:
            logger.debug("agent_recent.json 쓰기 실패: %s", exc)
