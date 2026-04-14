"""A/B Testing + Feature Flags.

A/B Testing: 모델 v1 vs v2 어느 게 나은지 실험
Feature Flag: 특정 유저/플랜에만 기능 켜기

예시:
  - 50% 유저는 30B v1, 50%는 30B v2로 라우팅 → 품질 비교
  - Pro 유저만 Vision 기능 활성화
  - 베타 유저만 새 모델 사용 가능
"""

from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# A/B Testing
# ============================================================

@dataclass
class Experiment:
    """A/B 테스트 실험."""
    id: str
    name: str
    variants: dict[str, float]  # {"control": 0.5, "treatment": 0.5}
    active: bool = True
    results: dict[str, dict] = field(default_factory=dict)  # variant → metrics


class ABTestManager:
    """A/B 테스트 관리."""

    def __init__(self):
        self._experiments: dict[str, Experiment] = {}

    def create_experiment(self, id: str, name: str, variants: dict[str, float]):
        self._experiments[id] = Experiment(id=id, name=name, variants=variants)

    def assign_variant(self, experiment_id: str, user_id: str) -> str | None:
        """유저를 실험 그룹에 할당 (결정적: 같은 유저 = 같은 그룹)."""
        exp = self._experiments.get(experiment_id)
        if not exp or not exp.active:
            return None

        # 유저 ID 기반 해시 → 0~1 사이 값
        hash_val = int(hashlib.md5(f"{experiment_id}:{user_id}".encode()).hexdigest(), 16)
        position = (hash_val % 10000) / 10000.0

        cumulative = 0.0
        for variant, weight in exp.variants.items():
            cumulative += weight
            if position < cumulative:
                return variant

        return list(exp.variants.keys())[-1]

    def record_metric(self, experiment_id: str, variant: str, metric: str, value: float):
        """실험 결과 기록."""
        exp = self._experiments.get(experiment_id)
        if not exp:
            return
        if variant not in exp.results:
            exp.results[variant] = {}
        if metric not in exp.results[variant]:
            exp.results[variant][metric] = {"sum": 0, "count": 0}

        exp.results[variant][metric]["sum"] += value
        exp.results[variant][metric]["count"] += 1

    def get_results(self, experiment_id: str) -> dict:
        """실험 결과 요약."""
        exp = self._experiments.get(experiment_id)
        if not exp:
            return {}

        summary = {}
        for variant, metrics in exp.results.items():
            summary[variant] = {}
            for metric, data in metrics.items():
                avg = data["sum"] / max(data["count"], 1)
                summary[variant][metric] = {
                    "average": round(avg, 4),
                    "count": data["count"],
                }
        return {"experiment": exp.name, "variants": summary}


# ============================================================
# Feature Flags
# ============================================================

@dataclass
class FeatureFlag:
    """기능 플래그."""
    name: str
    enabled: bool = False
    description: str = ""
    allowed_plans: list[str] = field(default_factory=list)   # ["pro", "business"]
    allowed_users: list[str] = field(default_factory=list)   # 특정 유저 ID
    percentage: float = 0.0  # 점진적 롤아웃 (0~100%)


class FeatureFlagManager:
    """기능 플래그 관리."""

    def __init__(self):
        self._flags: dict[str, FeatureFlag] = {}

    def register(self, flag: FeatureFlag):
        self._flags[flag.name] = flag

    def is_enabled(self, flag_name: str, user_id: str = "", plan: str = "") -> bool:
        """이 유저에게 이 기능이 활성화되어 있는지."""
        flag = self._flags.get(flag_name)
        if not flag or not flag.enabled:
            return False

        # 특정 유저 허용
        if flag.allowed_users and user_id in flag.allowed_users:
            return True

        # 플랜 기반
        if flag.allowed_plans and plan in flag.allowed_plans:
            return True

        # 퍼센트 기반 롤아웃
        if flag.percentage > 0 and user_id:
            hash_val = int(hashlib.md5(f"{flag_name}:{user_id}".encode()).hexdigest(), 16)
            return (hash_val % 100) < flag.percentage

        # 모든 조건에 해당 안 하면 False
        return not flag.allowed_plans and not flag.allowed_users and flag.percentage == 0

    def get_user_features(self, user_id: str, plan: str) -> dict[str, bool]:
        """유저에게 활성화된 모든 기능."""
        return {
            name: self.is_enabled(name, user_id, plan)
            for name in self._flags
        }

    @property
    def all_flags(self) -> list[FeatureFlag]:
        return list(self._flags.values())
