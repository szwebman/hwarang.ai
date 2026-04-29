"""Tiered KV Cache — RAM / 디스크 계층.

긴 컨텍스트 (256K 목표) 를 위해 Hot (GPU) / Warm (CPU RAM) / Cold (NVMe) 계층 분리.
LRU + 빈도 가중치로 promote/demote.
"""

from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Tier(str, Enum):
    HOT = "hot"  # GPU HBM
    WARM = "warm"  # CPU RAM
    COLD = "cold"  # NVMe SSD


@dataclass
class CacheEntry:
    block_id: str
    tier: Tier
    size_bytes: int
    access_count: int = 0


class TieredKVCache:
    """현재 stub. Phase 4.2 에서 mmap + cudaMemcpyAsync 구현."""

    def __init__(
        self,
        hot_capacity_bytes: int = 16 * 1024**3,
        warm_capacity_bytes: int = 256 * 1024**3,
        cold_path: Optional[str] = None,
    ):
        self.hot_capacity = hot_capacity_bytes
        self.warm_capacity = warm_capacity_bytes
        self.cold_path = cold_path
        self._hot: OrderedDict[str, CacheEntry] = OrderedDict()
        self._warm: OrderedDict[str, CacheEntry] = OrderedDict()
        self._cold: dict[str, CacheEntry] = {}

    def get(self, block_id: str):
        # TODO Phase 4.2: tier 별 fetch + promote
        raise NotImplementedError("TieredKVCache.get — 실 구현은 Phase 4.2")

    def put(self, block_id: str, tensor) -> None:
        # TODO Phase 4.2: 사이즈 측정 + tier 결정 + evict
        raise NotImplementedError("TieredKVCache.put — 실 구현은 Phase 4.2")

    def stats(self) -> dict[str, int]:
        return {
            "hot": len(self._hot),
            "warm": len(self._warm),
            "cold": len(self._cold),
        }
