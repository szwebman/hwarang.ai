"""에이전트 평판 시스템

온체인 평판 점수. 높을수록 더 많은 작업 + 보상.

평판 = f(작업 완료율, 응답 품질, 가동 시간, 검증 정확도)

변동:
  작업 완료 → +0.01
  작업 실패 → -0.05
  높은 품질 피드백 → +0.02
  부정 행위 감지 → -0.3
  연속 가동 보너스 → 일당 +0.005
"""

import time, json, os, logging

logger = logging.getLogger(__name__)


class ReputationModule:
    def __init__(self, config=None):
        self.score = 0.5           # 초기 평판 (0~1)
        self.history: list[dict] = []
        self.data_path = os.path.expanduser("~/.hwarang/reputation.json")
        self._load()

    def record_event(self, event_type: str, details: str = ""):
        """이벤트 기록 + 평판 업데이트."""
        deltas = {
            "task_completed": 0.01,
            "task_failed": -0.05,
            "high_quality": 0.02,
            "low_quality": -0.02,
            "uptime_bonus": 0.005,
            "fraud_detected": -0.3,
            "peer_validation_correct": 0.01,
            "peer_validation_wrong": -0.03,
        }

        delta = deltas.get(event_type, 0)
        old_score = self.score
        self.score = max(0.0, min(1.0, self.score + delta))

        self.history.append({
            "timestamp": time.time(),
            "event": event_type,
            "delta": delta,
            "old_score": round(old_score, 4),
            "new_score": round(self.score, 4),
            "details": details,
        })

        if len(self.history) > 1000:
            self.history = self.history[-500:]

        self._save()
        return {"score": self.score, "delta": delta}

    def get_tier(self) -> str:
        """평판 등급."""
        if self.score >= 0.9: return "diamond"
        if self.score >= 0.8: return "gold"
        if self.score >= 0.6: return "silver"
        if self.score >= 0.4: return "bronze"
        return "unranked"

    def get_reward_multiplier(self) -> float:
        """평판 기반 보상 배율."""
        multipliers = {
            "diamond": 1.5,
            "gold": 1.3,
            "silver": 1.1,
            "bronze": 1.0,
            "unranked": 0.8,
        }
        return multipliers.get(self.get_tier(), 1.0)

    def get_stats(self) -> dict:
        recent = self.history[-50:]
        return {
            "score": round(self.score, 4),
            "tier": self.get_tier(),
            "reward_multiplier": self.get_reward_multiplier(),
            "total_events": len(self.history),
            "recent_trend": sum(e["delta"] for e in recent),
        }

    def _save(self):
        with open(self.data_path, "w") as f:
            json.dump({"score": self.score, "history": self.history[-200:]}, f)

    def _load(self):
        try:
            with open(self.data_path) as f:
                data = json.load(f)
                self.score = data.get("score", 0.5)
                self.history = data.get("history", [])
        except: pass
