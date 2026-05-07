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
        task_type: str = "hfl_round",
        streak_days: int = 0,
        use_emission_api: bool = True,
    ) -> float:
        """리워드 금액 계산.

        공식:
          기본 = 100 HWR × 기여도
          품질 보너스 = 50 × 품질점수
          티어 배수 = lite:1.0, standard:1.5, full:3.0
          수면 학습 = ×0.5 (자동이므로 절반)

        use_emission_api=True 면 hwarang-api의 /api/coin/emission-rate 를
        조회하여 supply/demand/halving 계수까지 반영. 실패 시 로컬 공식만 사용.
        """
        tier_multiplier = {"lite": 1.0, "standard": 1.5, "full": 3.0}.get(gpu_tier, 1.0)

        base = 100 * contribution_weight
        quality_bonus = 50 * quality_score
        local_total = (base + quality_bonus) * tier_multiplier

        if is_sleep_learning:
            local_total *= 0.5

        if not use_emission_api:
            return round(local_total, 2)

        # /api/coin/emission-rate 호출 — 실패 시 로컬 값으로 폴백
        global_mult = self._fetch_global_multiplier()
        if global_mult is None:
            return round(local_total, 2)

        # 작업 배율 + 연속 보너스 적용 (특허 공식)
        task_mult = {
            "inference": 1.0, "sft_train": 2.0, "dpo_train": 2.5,
            "feedback_verify": 0.5, "data_gen": 1.5, "hfl_round": 2.0,
        }.get(task_type, 1.0)
        streak_mult = 1.0 + 0.5 * min(1.0, max(0, streak_days) / 30.0)

        total = local_total * global_mult * task_mult * streak_mult
        return round(total, 2)

    def _fetch_global_multiplier(self) -> float | None:
        """/api/coin/emission-rate 호출 → global_multiplier 반환.

        네트워크 실패 / API 미배포 시 None.
        """
        try:
            import httpx
        except ImportError:
            return None

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"{self.api_url}/api/coin/emission-rate",
                    headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else None,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return float(data.get("global_multiplier", 1.0))
        except Exception as exc:
            logger.debug(f"emission-rate 조회 실패 (폴백 사용): {exc}")
        return None

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
