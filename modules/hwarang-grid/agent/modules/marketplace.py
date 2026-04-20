"""에이전트 마켓플레이스

에이전트가 "능력"을 가격과 함께 등록.
유저 요청 시 최적 에이전트 자동 매칭.
경쟁으로 가격 ↓, 품질 ↑.

등록 예:
  {"skill": "legal", "price_hwr": 5, "avg_quality": 8.5, "response_sec": 3}
  {"skill": "coding", "price_hwr": 3, "avg_quality": 7.0, "response_sec": 2}
"""

import json, time, logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ServiceListing:
    agent_id: str
    skill: str               # coding, legal, tax, design, translation
    price_hwr: float         # 건당 가격 (HWR)
    avg_quality: float       # 평균 품질 (0~10)
    avg_response_sec: float  # 평균 응답 시간
    max_concurrent: int
    current_load: int
    reputation: float        # 에이전트 평판
    listed_at: float


class MarketplaceModule:
    def __init__(self, config=None):
        self.listings: dict[str, list[ServiceListing]] = {}  # skill → listings
        self.transactions = 0
        self.total_revenue_hwr = 0

    def register_listing(self, listing: ServiceListing):
        """서비스 등록."""
        if listing.skill not in self.listings:
            self.listings[listing.skill] = []

        # 기존 등록 업데이트
        self.listings[listing.skill] = [
            l for l in self.listings[listing.skill] if l.agent_id != listing.agent_id
        ]
        self.listings[listing.skill].append(listing)
        logger.info(f"마켓 등록: {listing.agent_id} → {listing.skill} @ {listing.price_hwr} HWR")

    def find_best_provider(self, skill: str, priority: str = "quality"):
        """요청에 맞는 최적 제공자 찾기.

        priority: "quality" | "price" | "speed" | "balanced"
        """
        candidates = [
            l for l in self.listings.get(skill, [])
            if l.current_load < l.max_concurrent
        ]

        if not candidates:
            return None

        if priority == "price":
            candidates.sort(key=lambda l: l.price_hwr)
        elif priority == "quality":
            candidates.sort(key=lambda l: l.avg_quality, reverse=True)
        elif priority == "speed":
            candidates.sort(key=lambda l: l.avg_response_sec)
        else:  # balanced
            candidates.sort(
                key=lambda l: l.avg_quality / max(l.price_hwr, 0.1) / max(l.avg_response_sec, 0.1),
                reverse=True,
            )

        return candidates[0]

    def execute_transaction(self, buyer_id: str, listing: ServiceListing) -> dict:
        """거래 실행."""
        self.transactions += 1
        self.total_revenue_hwr += listing.price_hwr

        return {
            "tx_id": f"mkt_{self.transactions}_{int(time.time())}",
            "buyer": buyer_id,
            "seller": listing.agent_id,
            "skill": listing.skill,
            "price_hwr": listing.price_hwr,
            "timestamp": time.time(),
        }

    def get_market_stats(self) -> dict:
        """시장 통계."""
        all_listings = [l for lists in self.listings.values() for l in lists]
        return {
            "total_listings": len(all_listings),
            "skills_available": list(self.listings.keys()),
            "transactions": self.transactions,
            "total_volume_hwr": self.total_revenue_hwr,
            "avg_prices": {
                skill: round(sum(l.price_hwr for l in lists) / max(len(lists), 1), 1)
                for skill, lists in self.listings.items()
            },
        }
