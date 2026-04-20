"""에이전트 길드 (Guild) - 소규모 GPU 연합 (세계 최초)

에이전트끼리 "길드"를 결성.
소규모 GPU도 모여서 큰 일 가능.

구조:
  길드 = 에이전트 N대의 연합
  길드 리더 = 평판 최고 에이전트 (자동 선출)
  길드 VRAM = 멤버 VRAM 합산
  길드 작업 = 큰 모델 분산 추론 / 대규모 학습

예:
  코딩 길드: RTX 4060 × 10대 = 80GB VRAM
  → 합치면 RTX 5090 2.5대급
  → 길드 단위로 복잡한 작업 수주
  → 보상은 기여도로 분배

보상 분배:
  길드 보상 = 작업 보상 총액
  리더 보너스: 10%
  기여도 분배: 나머지 90% (GPU 성능 × 참여 시간 비례)
"""

import time, json, hashlib, logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GuildMember:
    agent_id: str
    gpu_name: str
    vram_gb: float
    reputation: float
    joined_at: float
    contribution_score: float = 0  # 누적 기여도
    is_leader: bool = False


@dataclass
class Guild:
    guild_id: str
    name: str
    specialty: str                    # coding, legal, general
    members: list[GuildMember] = field(default_factory=list)
    created_at: float = 0
    total_tasks: int = 0
    total_rewards: float = 0
    min_reputation: float = 0.4      # 최소 가입 평판
    max_members: int = 20

    @property
    def total_vram_gb(self) -> float:
        return sum(m.vram_gb for m in self.members)

    @property
    def leader(self):
        leaders = [m for m in self.members if m.is_leader]
        return leaders[0] if leaders else None

    @property
    def member_count(self) -> int:
        return len(self.members)


class AgentGuildModule:
    def __init__(self, config=None):
        self.my_guild: Guild  = None
        self.available_guilds: list[Guild] = []
        self.data_path = os.path.expanduser("~/.hwarang/guild.json") if 'os' in dir() else "/tmp/guild.json"

    def create_guild(
        self,
        name: str,
        specialty: str,
        founder_id: str,
        founder_gpu: str,
        founder_vram: float,
        founder_reputation: float,
    ) -> Guild:
        """길드 생성. 생성자가 자동 리더."""
        guild = Guild(
            guild_id=hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:12],
            name=name,
            specialty=specialty,
            created_at=time.time(),
        )

        founder = GuildMember(
            agent_id=founder_id,
            gpu_name=founder_gpu,
            vram_gb=founder_vram,
            reputation=founder_reputation,
            joined_at=time.time(),
            is_leader=True,
        )
        guild.members.append(founder)

        self.my_guild = guild
        logger.info(f"🏰 길드 생성: {name} ({specialty}), 리더 {founder_id}")
        return guild

    def join_guild(
        self,
        guild: Guild,
        agent_id: str,
        gpu_name: str,
        vram_gb: float,
        reputation: float,
    ) -> dict:
        """길드 가입."""
        if guild.member_count >= guild.max_members:
            return {"error": "길드 인원 초과"}
        if reputation < guild.min_reputation:
            return {"error": f"평판 부족 (필요 {guild.min_reputation}, 현재 {reputation})"}

        # 중복 가입 체크
        if any(m.agent_id == agent_id for m in guild.members):
            return {"error": "이미 가입됨"}

        member = GuildMember(
            agent_id=agent_id,
            gpu_name=gpu_name,
            vram_gb=vram_gb,
            reputation=reputation,
            joined_at=time.time(),
        )
        guild.members.append(member)

        logger.info(
            f"🏰 길드 가입: {agent_id} → {guild.name} "
            f"(멤버 {guild.member_count}, 총 VRAM {guild.total_vram_gb}GB)"
        )

        return {"status": "joined", "guild": guild.name, "total_vram": guild.total_vram_gb}

    def leave_guild(self, guild: Guild, agent_id: str) -> dict:
        """길드 탈퇴."""
        guild.members = [m for m in guild.members if m.agent_id != agent_id]

        # 리더가 탈퇴하면 차기 리더 선출
        if not any(m.is_leader for m in guild.members) and guild.members:
            new_leader = max(guild.members, key=lambda m: m.reputation)
            new_leader.is_leader = True
            logger.info(f"새 리더 선출: {new_leader.agent_id}")

        return {"status": "left", "remaining_members": guild.member_count}

    def elect_leader(self, guild: Guild):
        """리더 선출 (평판 최고)."""
        if not guild.members:
            return None

        for m in guild.members:
            m.is_leader = False

        new_leader = max(guild.members, key=lambda m: m.reputation)
        new_leader.is_leader = True
        logger.info(f"리더 선출: {new_leader.agent_id} (평판 {new_leader.reputation})")
        return new_leader

    def distribute_reward(self, guild: Guild, total_reward: float) -> dict[str, float]:
        """보상 분배 (기여도 비례).

        리더: 10% 보너스
        나머지: GPU 성능 비례 분배
        """
        if not guild.members:
            return {}

        leader_bonus = total_reward * 0.10
        pool = total_reward * 0.90

        # GPU VRAM 비례
        total_vram = guild.total_vram_gb
        distribution = {}

        for member in guild.members:
            share = (member.vram_gb / max(total_vram, 1)) * pool
            if member.is_leader:
                share += leader_bonus
            distribution[member.agent_id] = round(share, 2)
            member.contribution_score += share

        guild.total_rewards += total_reward
        guild.total_tasks += 1

        return distribution

    def get_guild_power(self, guild: Guild) -> dict:
        """길드 전투력(?) 분석."""
        return {
            "guild": guild.name,
            "specialty": guild.specialty,
            "members": guild.member_count,
            "total_vram_gb": guild.total_vram_gb,
            "equivalent": f"≈ RTX 5090 × {guild.total_vram_gb / 32:.1f}대",
            "leader": guild.leader.agent_id if guild.leader else None,
            "avg_reputation": round(
                sum(m.reputation for m in guild.members) / max(guild.member_count, 1), 2
            ),
            "total_tasks": guild.total_tasks,
            "total_rewards": guild.total_rewards,
            "gpu_distribution": {
                m.agent_id: f"{m.gpu_name} ({m.vram_gb}GB)"
                for m in guild.members
            },
        }

    def find_guilds_for_task(self, required_vram: float, specialty: str) -> list[Guild]:
        """작업에 적합한 길드 찾기."""
        return [
            g for g in self.available_guilds
            if g.total_vram_gb >= required_vram
            and (g.specialty == specialty or g.specialty == "general")
        ]


import os  # 모듈 상단에 있어야 하지만 안전을 위해

if __name__ == "__main__":
    # 시뮬레이션
    gm = AgentGuildModule()

    # 길드 생성
    guild = gm.create_guild("코딩 마스터즈", "coding", "agent_kr_01", "RTX 5090", 32, 0.9)

    # 멤버 추가
    members = [
        ("agent_kr_02", "RTX 4090", 24, 0.8),
        ("agent_kr_03", "RTX 4080", 16, 0.7),
        ("agent_kr_04", "RTX 4060", 8, 0.6),
        ("agent_kr_05", "RTX 4060", 8, 0.65),
    ]
    for aid, gpu, vram, rep in members:
        gm.join_guild(guild, aid, gpu, vram, rep)

    # 길드 파워
    power = gm.get_guild_power(guild)
    print(f"\n길드: {power['guild']}")
    print(f"  멤버: {power['members']}명")
    print(f"  총 VRAM: {power['total_vram_gb']}GB ({power['equivalent']})")
    print(f"  리더: {power['leader']}")

    # 보상 분배
    dist = gm.distribute_reward(guild, 100)
    print(f"\n보상 분배 (100 HWR):")
    for agent_id, reward in sorted(dist.items(), key=lambda x: x[1], reverse=True):
        print(f"  {agent_id}: {reward} HWR")
