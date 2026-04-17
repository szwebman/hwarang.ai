"""에이전트 DNA 진화 (세계 최초)

각 에이전트가 고유 DNA (LoRA 가중치 조합) 보유.
성능 좋은 에이전트 DNA 교배 → 더 좋은 에이전트 자동 탄생.

유전 알고리즘:
  1. DNA = LoRA 가중치 (각 레이어의 rank, alpha, 가중치)
  2. 적합도 = 벤치마크 점수 + 유저 평점 + 응답 속도
  3. 선택 = 적합도 상위 30%
  4. 교배 = 두 DNA의 LoRA를 SLERP merge
  5. 변이 = 랜덤 레이어 가중치 변동 (±5%)
  6. 세대 교체 = 주 1회
"""

import json, os, time, random, hashlib, logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentDNA:
    dna_id: str
    generation: int = 0
    parent_ids: list[str] = field(default_factory=list)
    lora_path: str = ""           # LoRA 어댑터 경로
    traits: dict = field(default_factory=dict)  # 특성 (코딩, 법률, 속도 등)
    fitness: float = 0.0          # 적합도 점수
    created_at: float = 0


class AgentDNAModule:
    def __init__(self, config=None):
        self.my_dna: AgentDNA | None = None
        self.population: list[AgentDNA] = []
        self.generation = 0
        self.data_path = os.path.expanduser("~/.hwarang/dna")
        os.makedirs(self.data_path, exist_ok=True)

    def initialize_dna(self, lora_path: str, initial_fitness: float = 5.0) -> AgentDNA:
        """초기 DNA 생성."""
        dna = AgentDNA(
            dna_id=hashlib.md5(f"{time.time()}{random.random()}".encode()).hexdigest()[:12],
            generation=0,
            lora_path=lora_path,
            traits={"coding": 0.5, "legal": 0.5, "speed": 0.5, "korean": 0.5},
            fitness=initial_fitness,
            created_at=time.time(),
        )
        self.my_dna = dna
        return dna

    def crossover(self, parent_a: AgentDNA, parent_b: AgentDNA) -> AgentDNA:
        """두 DNA 교배 → 자식 DNA 생성.

        LoRA 가중치를 SLERP로 합성 (실제는 merge 스크립트 호출).
        """
        child_id = hashlib.md5(f"{parent_a.dna_id}{parent_b.dna_id}{time.time()}".encode()).hexdigest()[:12]

        # 특성 유전 (각 trait를 부모 중 랜덤 + 변이)
        child_traits = {}
        for trait in parent_a.traits:
            if random.random() > 0.5:
                base = parent_a.traits.get(trait, 0.5)
            else:
                base = parent_b.traits.get(trait, 0.5)
            # 변이 (±10%)
            mutation = base * random.uniform(-0.1, 0.1)
            child_traits[trait] = max(0, min(1, base + mutation))

        # 적합도 예상 = 부모 평균 + 약간의 랜덤
        expected_fitness = (parent_a.fitness + parent_b.fitness) / 2 * random.uniform(0.9, 1.1)

        child = AgentDNA(
            dna_id=child_id,
            generation=max(parent_a.generation, parent_b.generation) + 1,
            parent_ids=[parent_a.dna_id, parent_b.dna_id],
            lora_path="",  # merge 후 설정
            traits=child_traits,
            fitness=expected_fitness,
            created_at=time.time(),
        )

        logger.info(
            f"DNA 교배: {parent_a.dna_id[:6]} × {parent_b.dna_id[:6]} → {child_id[:6]} "
            f"(세대 {child.generation})"
        )
        return child

    def natural_selection(self, population: list[AgentDNA], top_ratio: float = 0.3) -> list[AgentDNA]:
        """자연 선택: 적합도 상위 30%만 생존."""
        sorted_pop = sorted(population, key=lambda d: d.fitness, reverse=True)
        survivors = sorted_pop[:max(1, int(len(sorted_pop) * top_ratio))]
        eliminated = len(sorted_pop) - len(survivors)
        logger.info(f"자연 선택: {len(survivors)} 생존, {eliminated} 도태")
        return survivors

    def evolve_generation(self) -> list[AgentDNA]:
        """한 세대 진화.

        1. 선택 (상위 30%)
        2. 교배 (생존자끼리)
        3. 변이
        4. 새 세대 구성
        """
        if len(self.population) < 2:
            logger.info("진화 불가: 인구 부족 (<2)")
            return self.population

        # 선택
        survivors = self.natural_selection(self.population)

        # 교배
        children = []
        for i in range(len(self.population) - len(survivors)):
            parent_a = random.choice(survivors)
            parent_b = random.choice(survivors)
            if parent_a.dna_id != parent_b.dna_id:
                child = self.crossover(parent_a, parent_b)
                children.append(child)

        # 새 세대
        self.generation += 1
        self.population = survivors + children
        logger.info(f"세대 {self.generation}: {len(self.population)}개 DNA (생존 {len(survivors)} + 신규 {len(children)})")
        return self.population

    def get_stats(self) -> dict:
        if not self.population:
            return {"generation": self.generation, "population": 0}

        fitnesses = [d.fitness for d in self.population]
        return {
            "generation": self.generation,
            "population": len(self.population),
            "best_fitness": max(fitnesses),
            "avg_fitness": sum(fitnesses) / len(fitnesses),
            "best_dna": max(self.population, key=lambda d: d.fitness).dna_id[:8],
            "my_dna": self.my_dna.dna_id[:8] if self.my_dna else None,
        }
