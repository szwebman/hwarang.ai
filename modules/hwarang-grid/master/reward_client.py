"""HWARANG 코인 리워드 클라이언트

HFL 마스터에서 에이전트에 코인 리워드를 지급.
블록체인 스마트 컨트랙트를 호출하거나,
hwarang-api의 리워드 엔드포인트를 통해 지급.

사용법:
    client = RewardClient(api_url="https://api.hwarang.ai")
    await client.reward_agent(
        agent_id="agent_abc123",
        amount=100,
        reason="hfl_round_5_contribution",
    )
"""

import logging
import time
import json
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RewardRecord:
    agent_id: str
    wallet_address: str
    amount: float          # HWR 토큰
    reason: str
    round_id: str = ""
    quality_score: float = 0.0
    timestamp: float = field(default_factory=time.time)
    tx_hash: str = ""      # 블록체인 트랜잭션 해시
    status: str = "pending"  # pending, confirmed, failed


class RewardClient:
    """코인 리워드 클라이언트.

    방법 1: hwarang-api 경유 (권장)
      → API가 서버 지갑에서 에이전트 지갑으로 전송

    방법 2: 직접 블록체인 호출 (web3py)
      → 마스터가 직접 스마트 컨트랙트 호출
    """

    def __init__(
        self,
        api_url: str = "https://api.hwarang.ai",
        api_key: str = "",
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.reward_history: list[RewardRecord] = []

    async def reward_agent(
        self,
        agent_id: str,
        wallet_address: str,
        amount: float,
        reason: str,
        round_id: str = "",
        quality_score: float = 0.0,
    ) -> RewardRecord:
        """에이전트에 코인 리워드 지급.

        hwarang-api의 /api/rewards/emit 엔드포인트를 호출.
        API 서버가 서버 지갑에서 에이전트 지갑으로 토큰 전송.
        """
        record = RewardRecord(
            agent_id=agent_id,
            wallet_address=wallet_address,
            amount=amount,
            reason=reason,
            round_id=round_id,
            quality_score=quality_score,
        )

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/api/rewards/emit",
                    json={
                        "agent_id": agent_id,
                        "wallet_address": wallet_address,
                        "amount": amount,
                        "reason": reason,
                        "metadata": {
                            "round_id": round_id,
                            "quality_score": quality_score,
                            "timestamp": time.time(),
                        },
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )

                if response.status_code == 200:
                    result = response.json()
                    record.tx_hash = result.get("tx_hash", "")
                    record.status = "confirmed"
                    logger.info(
                        f"💰 리워드 지급: {agent_id} → {amount} HWR "
                        f"(사유: {reason}, tx: {record.tx_hash[:16]}...)"
                    )
                else:
                    record.status = "failed"
                    logger.error(f"리워드 실패: HTTP {response.status_code}")

        except ImportError:
            # httpx 없으면 기록만 (나중에 배치 처리)
            record.status = "queued"
            logger.info(f"💰 리워드 큐잉: {agent_id} → {amount} HWR (오프라인)")

        except Exception as e:
            record.status = "failed"
            logger.error(f"리워드 에러: {e}")

        self.reward_history.append(record)
        return record

    def calculate_reward(
        self,
        contribution_weight: float,
        quality_score: float,
        gpu_tier: str = "standard",
        is_sleep_learning: bool = False,
    ) -> float:
        """리워드 금액 계산.

        공식:
          기본 = 100 HWR × 기여도
          품질 보너스 = 50 × 품질점수
          티어 배수 = lite:1.0, standard:1.5, full:3.0
          수면 학습 = ×0.5 (자동이므로 절반)
        """
        tier_multiplier = {"lite": 1.0, "standard": 1.5, "full": 3.0}.get(gpu_tier, 1.0)

        base = 100 * contribution_weight
        quality_bonus = 50 * quality_score
        total = (base + quality_bonus) * tier_multiplier

        if is_sleep_learning:
            total *= 0.5

        return round(total, 2)

    async def batch_reward(self, rewards: list[dict]) -> list[RewardRecord]:
        """여러 에이전트에 일괄 리워드."""
        records = []
        for r in rewards:
            record = await self.reward_agent(**r)
            records.append(record)
        return records

    def get_stats(self) -> dict:
        """리워드 통계."""
        total = len(self.reward_history)
        confirmed = sum(1 for r in self.reward_history if r.status == "confirmed")
        total_amount = sum(r.amount for r in self.reward_history if r.status == "confirmed")

        return {
            "total_rewards": total,
            "confirmed": confirmed,
            "failed": total - confirmed,
            "total_amount_hwr": total_amount,
        }
