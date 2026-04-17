"""에이전트 전문화 자동 진화

에이전트가 자기가 잘하는 분야를 자동 발견.
잘하는 일 → 더 많이 배정 → 더 잘하게 됨 → 선순환.

초기: 범용 → 시간 경과 → 자동 특화
  코딩 질문 많이 처리 → 코딩 평판↑ → 코딩 특화 선언
"""

import time, json, os, logging
from collections import Counter

logger = logging.getLogger(__name__)


class AutoSpecializationModule:
    def __init__(self, config=None):
        self.domain_stats: Counter = Counter()
        self.domain_scores: dict[str, list[float]] = {}
        self.specialization: str | None = None
        self.specialization_confidence: float = 0.0
        self.data_path = os.path.expanduser("~/.hwarang/specialization.json")
        self._load()

    def record_task(self, domain: str, quality_score: float):
        """작업 수행 기록."""
        self.domain_stats[domain] += 1
        if domain not in self.domain_scores:
            self.domain_scores[domain] = []
        self.domain_scores[domain].append(quality_score)

        # 최근 100개만 유지
        if len(self.domain_scores[domain]) > 100:
            self.domain_scores[domain] = self.domain_scores[domain][-50:]

        self._evaluate_specialization()
        self._save()

    def _evaluate_specialization(self):
        """전문화 평가: 특정 도메인이 압도적이면 전문화 선언."""
        if sum(self.domain_stats.values()) < 20:
            return  # 데이터 부족

        total = sum(self.domain_stats.values())
        best_domain = self.domain_stats.most_common(1)[0]
        domain, count = best_domain

        ratio = count / total
        avg_score = sum(self.domain_scores.get(domain, [0])) / max(len(self.domain_scores.get(domain, [1])), 1)

        # 40% 이상 + 평균 점수 7+ → 전문화
        if ratio > 0.4 and avg_score > 7.0:
            old = self.specialization
            self.specialization = domain
            self.specialization_confidence = ratio * avg_score / 10

            if old != domain:
                logger.info(f"🎯 전문화 발견: {domain} (비율 {ratio:.0%}, 품질 {avg_score:.1f})")

    def get_specialization(self) -> dict:
        """현재 전문화 정보."""
        return {
            "specialization": self.specialization,
            "confidence": round(self.specialization_confidence, 2),
            "domain_distribution": dict(self.domain_stats),
            "domain_quality": {
                d: round(sum(scores) / max(len(scores), 1), 1)
                for d, scores in self.domain_scores.items()
            },
        }

    def should_accept_task(self, domain: str) -> float:
        """이 도메인 작업을 수락해야 하는 정도 (0~1).

        전문화된 도메인 → 높은 점수 → 우선 수락
        """
        if self.specialization is None:
            return 0.5  # 범용

        if domain == self.specialization:
            return 0.9 + self.specialization_confidence * 0.1

        # 전문화 아닌 도메인도 가끔 수락 (다양성 유지)
        return 0.3

    def _save(self):
        with open(self.data_path, "w") as f:
            json.dump({
                "stats": dict(self.domain_stats),
                "scores": {d: s[-50:] for d, s in self.domain_scores.items()},
                "specialization": self.specialization,
            }, f)

    def _load(self):
        try:
            with open(self.data_path) as f:
                data = json.load(f)
                self.domain_stats = Counter(data.get("stats", {}))
                self.domain_scores = data.get("scores", {})
                self.specialization = data.get("specialization")
        except: pass
