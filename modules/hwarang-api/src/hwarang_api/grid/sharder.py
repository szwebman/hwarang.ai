"""DataShardingService — 라운드 데이터 샤딩 + validation 분리.

기존 :mod:`hwarang_api.routers.grid` 는 모든 에이전트에게 동일한 데이터를
주고 (사실상 ``data_url`` 도 placeholder), peer 평가용 validation set 도
분리되어 있지 않았다.

이 모듈은:

1. ``validation_fraction`` 만큼을 떼어 별도의 *eval-shard* 로 보존
2. 나머지를 ``strategy`` 에 따라 에이전트 수만큼 분할
   * ``iid``: 균등 무작위 셔플
   * ``non_iid``: Dirichlet(α=0.5) 비대칭 분할
   * ``domain_partition``: 에이전트 도메인 specialization 에 맞춰 자르기
3. 각 샤드의 ``data_url`` 을 만들고 메타를 ``ShardPlan`` 으로 반환
4. (옵션) Prisma ``DataShard`` 레코드 작성

실제 샘플 파일 생성은 stub (TODO) — 데이터 소스가 외부 스토리지에 따라
다르므로 여기서는 메타데이터 / URL 만 만든다.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

logger = logging.getLogger(__name__)

Strategy = Literal["iid", "non_iid", "domain_partition"]

DEFAULT_BUCKET = "hwarang-grid"


def _shard_url(round_id: str, shard_idx: int, kind: str = "train") -> str:
    """기본 샤드 URL 패턴.

    실제 운영에서는 환경변수로 base URL 을 바꿀 수 있게 하지만,
    grid.py 가 ``/api/grid/rounds/{round_id}/data`` 도 같이 받도록
    되어 있어 일관성을 위해 s3 형식과 라우터 형식을 둘 다 허용.
    """
    return f"s3://{DEFAULT_BUCKET}/rounds/{round_id}/shard_{shard_idx:03d}_{kind}.jsonl"


def _validation_url(round_id: str) -> str:
    return f"s3://{DEFAULT_BUCKET}/rounds/{round_id}/eval.jsonl"


class DataShardingService:
    """라운드 데이터를 샤드로 나누고 validation set 을 분리한다."""

    @dataclass
    class ShardPlan:
        round_id: str
        shards: list[dict[str, Any]] = field(default_factory=list)
        validation_shard: dict[str, Any] = field(default_factory=dict)
        strategy: str = "iid"
        data_source_url: str = ""

        def by_agent(self, agent_id: str) -> dict[str, Any] | None:
            for s in self.shards:
                if s.get("agent_id") == agent_id:
                    return s
            return None

    # ──────────────────────────────────────────────────────
    # 메인 진입점
    # ──────────────────────────────────────────────────────
    async def plan(
        self,
        round_id: str,
        agents: list[str] | list[dict[str, Any]],
        data_source_url: str,
        sample_count: int,
        strategy: Strategy = "iid",
        validation_fraction: float = 0.15,
        agent_domains: dict[str, list[str]] | None = None,
        persist: bool = True,
    ) -> "DataShardingService.ShardPlan":
        """샤드 계획 생성.

        Parameters
        ----------
        round_id
            대상 라운드 ID.
        agents
            ``[agent_id, ...]`` 또는 ``[{"agent_id":..., "domains":[...]}, ...]``.
            ``domain_partition`` 전략은 후자 형태 또는 ``agent_domains`` 인자가 필요.
        data_source_url
            원본 데이터 위치 (jsonl/parquet). 실제 IO 는 stub.
        sample_count
            전체 샘플 수.
        strategy
            ``iid`` / ``non_iid`` / ``domain_partition``.
        validation_fraction
            validation set 비율 (0~0.5).
        agent_domains
            ``domain_partition`` 시 명시적 매핑. 없으면 ``agents`` dict 에서 읽음.
        persist
            True 면 Prisma ``DataShard`` 레코드도 생성.
        """
        if sample_count <= 0:
            raise ValueError("sample_count > 0 이어야 함")
        if not (0.0 <= validation_fraction < 0.5):
            raise ValueError("validation_fraction 은 [0, 0.5) 범위")

        agent_ids, agent_domain_map = self._normalize_agents(agents, agent_domains)
        if not agent_ids:
            raise ValueError("agents 가 비어 있음")

        val_count = int(round(sample_count * validation_fraction))
        train_count = sample_count - val_count

        # 전략별 카운트 분할 (실제 인덱스는 stub — 카운트만 정확하게)
        if strategy == "iid":
            shard_counts = self._split_iid(train_count, len(agent_ids))
        elif strategy == "non_iid":
            shard_counts = self._split_dirichlet(train_count, len(agent_ids), alpha=0.5)
        elif strategy == "domain_partition":
            shard_counts = self._split_domain_partition(
                train_count, agent_ids, agent_domain_map
            )
        else:
            raise ValueError(f"알 수 없는 strategy: {strategy}")

        shards: list[dict[str, Any]] = []
        for idx, (agent_id, n) in enumerate(zip(agent_ids, shard_counts)):
            url = _shard_url(round_id, idx, "train")
            shards.append({
                "shard_idx": idx,
                "agent_id": agent_id,
                "data_url": url,
                "sample_count": int(n),
                "strategy": strategy,
                "is_validation": False,
                "checksum": self._fake_checksum(round_id, idx, n),
            })

        validation_shard = {
            "shard_idx": len(agent_ids),  # train 샤드 뒤
            "agent_id": None,
            "data_url": _validation_url(round_id),
            "sample_count": int(val_count),
            "strategy": strategy,
            "is_validation": True,
            "checksum": self._fake_checksum(round_id, "val", val_count),
        }

        # TODO: 실제 데이터 분할/업로드 — 외부 스토리지 IO 가 정해지면 구현.
        # 현재는 메타데이터만 반환하고, 에이전트가 data_url 을 받아 가서
        # 백엔드가 lazy 하게 jsonl 을 잘라준다는 가정.

        if persist:
            await self._persist_shards(round_id, shards, validation_shard)

        return DataShardingService.ShardPlan(
            round_id=round_id,
            shards=shards,
            validation_shard=validation_shard,
            strategy=strategy,
            data_source_url=data_source_url,
        )

    # ──────────────────────────────────────────────────────
    # grid.py 의 ``/eval-shard`` 가 호출하는 진입점
    # ──────────────────────────────────────────────────────
    async def get_validation_shard(
        self, round_id: str, agent_id: str
    ) -> dict[str, Any]:
        """라운드의 validation shard 메타데이터.

        Prisma 에 저장돼 있으면 그것을, 없으면 URL 만 합성해 반환.
        """
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            prisma = None  # type: ignore[assignment]

        if prisma is not None and getattr(prisma, "is_connected", lambda: False)():
            try:
                row = await prisma.datashard.find_first(  # type: ignore[attr-defined]
                    where={"roundId": round_id, "isValidation": True},
                )
                if row is not None:
                    return {
                        "round_id": round_id,
                        "agent_id": agent_id,
                        "shard_kind": "validation",
                        "data_url": row.dataUrl,
                        "sample_count": row.sampleCount,
                        "checksum": row.checksum,
                    }
            except Exception as e:
                logger.debug("validation_shard 조회 실패(무시): %s", e)

        # 폴백: URL 합성
        return {
            "round_id": round_id,
            "agent_id": agent_id,
            "shard_kind": "validation",
            "data_url": _validation_url(round_id),
            "sample_count": 0,
            "checksum": None,
        }

    # ──────────────────────────────────────────────────────
    # 분할 알고리즘
    # ──────────────────────────────────────────────────────
    @staticmethod
    def _split_iid(total: int, n_agents: int) -> list[int]:
        if n_agents <= 0:
            return []
        base, rem = divmod(total, n_agents)
        out = [base] * n_agents
        for i in range(rem):
            out[i] += 1
        return out

    @staticmethod
    def _split_dirichlet(total: int, n_agents: int, alpha: float = 0.5) -> list[int]:
        """Dirichlet(α) 비율로 비대칭 분할 (non-IID).

        numpy 가 있으면 진짜 Dirichlet sampling, 없으면 hash 기반 deterministic
        지프 유사 분포로 폴백.
        """
        if n_agents <= 0 or total <= 0:
            return [0] * n_agents
        try:
            import numpy as np  # type: ignore

            rng = np.random.default_rng(seed=42)
            props = rng.dirichlet([alpha] * n_agents)
        except Exception:
            # 결정적 폴백 — 1/(i+1) 가중치 → 정규화
            raw = [1.0 / (i + 1) for i in range(n_agents)]
            s = sum(raw)
            props = [r / s for r in raw]

        counts = [int(round(p * total)) for p in props]
        # 합이 정확히 total 이 되도록 보정
        diff = total - sum(counts)
        i = 0
        while diff != 0 and counts:
            if diff > 0:
                counts[i % n_agents] += 1
                diff -= 1
            else:
                if counts[i % n_agents] > 0:
                    counts[i % n_agents] -= 1
                    diff += 1
            i += 1
        return counts

    @staticmethod
    def _split_domain_partition(
        total: int,
        agent_ids: list[str],
        agent_domain_map: dict[str, list[str]],
    ) -> list[int]:
        """도메인 클러스터별로 균등하게 분할.

        같은 도메인을 가진 에이전트들이 1 그룹으로 묶이고, 그룹별로 균등 배분 후
        그룹 내부에서 IID. 도메인 정보 없는 에이전트는 'misc' 그룹.
        """
        if not agent_ids:
            return []

        groups: dict[str, list[int]] = {}
        for idx, aid in enumerate(agent_ids):
            domains = agent_domain_map.get(aid) or ["misc"]
            key = domains[0] if domains else "misc"
            groups.setdefault(key, []).append(idx)

        counts = [0] * len(agent_ids)
        n_groups = len(groups)
        if n_groups == 0:
            return DataShardingService._split_iid(total, len(agent_ids))

        per_group = DataShardingService._split_iid(total, n_groups)
        for (group_key, indices), group_total in zip(groups.items(), per_group):
            inner = DataShardingService._split_iid(group_total, len(indices))
            for local_idx, agent_idx in enumerate(indices):
                counts[agent_idx] = inner[local_idx]
        return counts

    # ──────────────────────────────────────────────────────
    # 헬퍼
    # ──────────────────────────────────────────────────────
    @staticmethod
    def _normalize_agents(
        agents: list[str] | list[dict[str, Any]],
        agent_domains: dict[str, list[str]] | None,
    ) -> tuple[list[str], dict[str, list[str]]]:
        ids: list[str] = []
        domain_map: dict[str, list[str]] = dict(agent_domains or {})
        for a in agents:
            if isinstance(a, str):
                ids.append(a)
            elif isinstance(a, dict):
                aid = a.get("agent_id")
                if not aid:
                    continue
                ids.append(aid)
                if "domains" in a and aid not in domain_map:
                    domain_map[aid] = list(a["domains"] or [])
                elif "specialization" in a and aid not in domain_map:
                    domain_map[aid] = [str(a["specialization"])]
        return ids, domain_map

    @staticmethod
    def _fake_checksum(round_id: str, key: Any, n: int) -> str:
        h = hashlib.sha256(f"{round_id}:{key}:{n}".encode()).hexdigest()
        return h[:32]

    @staticmethod
    async def _persist_shards(
        round_id: str,
        shards: Iterable[dict[str, Any]],
        validation_shard: dict[str, Any],
    ) -> None:
        """Prisma ``DataShard`` 작성 (있을 때만)."""
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            return
        if not getattr(prisma, "is_connected", lambda: False)():
            return

        all_records = list(shards) + [validation_shard]
        for s in all_records:
            try:
                await prisma.datashard.upsert(  # type: ignore[attr-defined]
                    where={
                        "roundId_shardIdx": {
                            "roundId": round_id,
                            "shardIdx": s["shard_idx"],
                        }
                    },
                    data={
                        "create": {
                            "roundId": round_id,
                            "shardIdx": s["shard_idx"],
                            "dataUrl": s["data_url"],
                            "sampleCount": s["sample_count"],
                            "isValidation": s.get("is_validation", False),
                            "checksum": s.get("checksum"),
                        },
                        "update": {
                            "dataUrl": s["data_url"],
                            "sampleCount": s["sample_count"],
                            "checksum": s.get("checksum"),
                        },
                    },
                )
            except Exception as e:
                logger.debug("DataShard upsert 실패(idx=%s, 무시): %s", s.get("shard_idx"), e)


__all__ = ["DataShardingService"]
