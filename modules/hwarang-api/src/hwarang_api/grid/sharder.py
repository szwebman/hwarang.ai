"""DataShardingService — 라운드 데이터 샤딩 + validation 분리 (실제 IO 포함).

기존 :mod:`hwarang_api.routers.grid` 는 모든 에이전트에게 동일한 데이터를
주고 (사실상 ``data_url`` 도 placeholder), peer 평가용 validation set 도
분리되어 있지 않았다.

이 모듈은:

1. ``data_source_url`` (file:// / http(s):// / s3:// / 절대경로) 에서 JSONL 을 읽음
2. ``validation_fraction`` 만큼을 떼어 별도의 *eval-shard* 로 디스크에 저장
3. 나머지를 ``strategy`` 에 따라 에이전트 수만큼 분할해 디스크에 저장
   * ``iid``: 균등 무작위 셔플
   * ``non_iid``: Dirichlet(α=0.5) 비대칭 분할
   * ``domain_partition``: 에이전트 도메인 specialization 에 맞춰 자르기
4. 각 샤드의 ``data_url`` 을 만들고 메타를 ``ShardPlan`` 으로 반환
5. (옵션) Prisma ``DataShard`` 레코드 작성
6. (옵션) ``HWARANG_SHARD_S3_BUCKET`` 이 있으면 S3 업로드, 없으면 로컬 디스크

환경변수
--------
HWARANG_SHARD_DIR
    샤드 저장 루트 (기본 ``/var/hwarang/shards``).
HWARANG_SHARD_BASE_URL
    샤드 공개 URL prefix (기본 ``http://localhost:8000/static/shards``).
HWARANG_SHARD_S3_BUCKET
    설정되면 S3 에 업로드 (boto3 import 실패 시 로컬 폴백).
HWARANG_SHARD_MAX_LINES
    한 라운드에서 읽을 최대 JSONL 라인 수 (기본 10000).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

logger = logging.getLogger(__name__)

Strategy = Literal["iid", "non_iid", "domain_partition"]

# ─── 환경변수 / 기본값 ─────────────────────────────────────────
SHARD_DIR = Path(os.getenv("HWARANG_SHARD_DIR", "/var/hwarang/shards"))
PUBLIC_BASE_URL = os.getenv(
    "HWARANG_SHARD_BASE_URL", "http://localhost:8000/static/shards"
).rstrip("/")
S3_BUCKET = os.getenv("HWARANG_SHARD_S3_BUCKET", "").strip() or None
MAX_LINES = int(os.getenv("HWARANG_SHARD_MAX_LINES", "10000"))


# ─── URL 생성 ───────────────────────────────────────────────────
def _shard_url(round_id: str, shard_idx: int, kind: str = "train") -> str:
    if kind == "train":
        return f"{PUBLIC_BASE_URL}/{round_id}/shard_{shard_idx:03d}.jsonl"
    return f"{PUBLIC_BASE_URL}/{round_id}/{kind}.jsonl"


def _validation_url(round_id: str) -> str:
    return f"{PUBLIC_BASE_URL}/{round_id}/eval.jsonl"


# ─── 데이터 IO ──────────────────────────────────────────────────
def _read_jsonl_lines(source: str, max_lines: int = MAX_LINES) -> list[dict[str, Any]]:
    """data_source_url 에서 JSONL 을 읽어 list[dict] 로 반환.

    지원 스킴:
      * 절대경로 또는 ``file://...``
      * ``http://``, ``https://`` (httpx 가용 시)
      * ``s3://bucket/key`` (boto3 가용 시)
    """
    samples: list[dict[str, Any]] = []

    if not source:
        return samples

    # file:// or 절대경로
    if source.startswith("file://"):
        local = source[len("file://") :]
    elif source.startswith(("/", "./")) or (len(source) > 1 and source[1] == ":"):
        local = source
    else:
        local = None

    if local is not None:
        p = Path(local)
        if not p.exists():
            logger.warning("data_source_url not found: %s", p)
            return samples
        with p.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return samples

    if source.startswith("http://") or source.startswith("https://"):
        try:
            import httpx  # type: ignore

            with httpx.Client(timeout=60.0) as client:
                with client.stream("GET", source) as resp:
                    resp.raise_for_status()
                    count = 0
                    for line in resp.iter_lines():
                        if count >= max_lines:
                            break
                        if not line:
                            continue
                        try:
                            samples.append(json.loads(line))
                            count += 1
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.warning("HTTP fetch 실패 %s: %s", source, e)
        return samples

    if source.startswith("s3://"):
        try:
            import boto3  # type: ignore

            without_scheme = source[len("s3://") :]
            bucket, _, key = without_scheme.partition("/")
            obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
            body = obj["Body"]
            count = 0
            for raw in body.iter_lines():
                if count >= max_lines:
                    break
                if not raw:
                    continue
                try:
                    samples.append(json.loads(raw))
                    count += 1
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.warning("S3 fetch 실패 %s: %s", source, e)
        return samples

    logger.warning("알 수 없는 data_source_url 스킴: %s", source)
    return samples


def _write_jsonl(path: Path, samples: list[dict[str, Any]]) -> None:
    """샘플을 JSONL 로 디스크에 쓴다 (디렉토리 자동 생성)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _maybe_upload_s3(local_path: Path, round_id: str, name: str) -> str | None:
    """S3_BUCKET 이 설정돼 있으면 업로드하고 s3 URL 반환. 실패 시 None."""
    if not S3_BUCKET:
        return None
    try:
        import boto3  # type: ignore

        key = f"rounds/{round_id}/{name}"
        boto3.client("s3").upload_file(str(local_path), S3_BUCKET, key)
        return f"s3://{S3_BUCKET}/{key}"
    except Exception as e:
        logger.warning("S3 upload graceful fallback (로컬만 유지): %s", e)
        return None


# ─── 메인 서비스 ────────────────────────────────────────────────
class DataShardingService:
    """라운드 데이터를 샤드로 나누고 validation set 을 분리한다 (실제 IO)."""

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
        """샤드 계획 생성 + 실제 데이터 분할/디스크 저장.

        Parameters
        ----------
        round_id
            대상 라운드 ID.
        agents
            ``[agent_id, ...]`` 또는 ``[{"agent_id":..., "domains":[...]}, ...]``.
        data_source_url
            원본 데이터 위치 (file:// / http(s):// / s3:// / 절대경로). JSONL.
        sample_count
            샘플 카운트 힌트 (실제 읽은 라인 수와 다를 수 있음).
        strategy
            ``iid`` / ``non_iid`` / ``domain_partition``.
        validation_fraction
            validation set 비율 (0~0.5).
        agent_domains
            ``domain_partition`` 시 명시적 매핑.
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

        # 1) 데이터 로드 (실제 IO)
        samples = _read_jsonl_lines(data_source_url, max_lines=MAX_LINES)
        if not samples:
            logger.warning(
                "샘플 없음 — data_source_url=%s. 메타데이터만 반환.", data_source_url
            )

        # 2) Validation 분리 (전체 섞은 뒤 앞부분)
        rng = random.Random(round_id)  # 결정적
        if samples:
            rng.shuffle(samples)
        actual_total = len(samples) if samples else sample_count
        val_count = int(round(actual_total * validation_fraction))
        train_count = actual_total - val_count

        eval_samples = samples[:val_count] if samples else []
        train_samples = samples[val_count:] if samples else []

        # 3) 전략별 분할
        if strategy == "iid":
            shard_counts = self._split_iid(train_count, len(agent_ids))
            shard_chunks = self._chunk_iid(train_samples, shard_counts)
        elif strategy == "non_iid":
            shard_counts = self._split_dirichlet(train_count, len(agent_ids), alpha=0.5)
            shard_chunks = self._chunk_iid(train_samples, shard_counts)
        elif strategy == "domain_partition":
            shard_counts = self._split_domain_partition(
                train_count, agent_ids, agent_domain_map
            )
            shard_chunks = self._chunk_by_domain(
                train_samples, agent_ids, agent_domain_map, shard_counts
            )
        else:
            raise ValueError(f"알 수 없는 strategy: {strategy}")

        # 4) 디스크 저장 + (선택) S3 업로드
        round_dir = SHARD_DIR / round_id
        round_dir.mkdir(parents=True, exist_ok=True)

        eval_path = round_dir / "eval.jsonl"
        if eval_samples:
            _write_jsonl(eval_path, eval_samples)
        eval_s3 = _maybe_upload_s3(eval_path, round_id, "eval.jsonl") if eval_samples else None

        shards: list[dict[str, Any]] = []
        for idx, agent_id in enumerate(agent_ids):
            chunk = shard_chunks[idx] if idx < len(shard_chunks) else []
            shard_path = round_dir / f"shard_{idx:03d}.jsonl"
            if chunk:
                _write_jsonl(shard_path, chunk)
            s3_url = (
                _maybe_upload_s3(shard_path, round_id, f"shard_{idx:03d}.jsonl")
                if chunk
                else None
            )
            data_url = s3_url or _shard_url(round_id, idx, "train")
            shards.append({
                "shard_idx": idx,
                "agent_id": agent_id,
                "data_url": data_url,
                "sample_count": len(chunk) if chunk else int(shard_counts[idx]),
                "strategy": strategy,
                "is_validation": False,
                "checksum": self._checksum_path(shard_path) if chunk else
                            self._fake_checksum(round_id, idx, shard_counts[idx]),
            })

        validation_shard = {
            "shard_idx": len(agent_ids),
            "agent_id": None,
            "data_url": eval_s3 or _validation_url(round_id),
            "sample_count": len(eval_samples) if eval_samples else val_count,
            "strategy": strategy,
            "is_validation": True,
            "checksum": self._checksum_path(eval_path) if eval_samples else
                        self._fake_checksum(round_id, "val", val_count),
        }

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
    # eval-shard 헬퍼들
    # ──────────────────────────────────────────────────────
    async def get_validation_shard(
        self, round_id: str, agent_id: str
    ) -> dict[str, Any]:
        """라운드의 validation shard 메타데이터 (Prisma 우선, URL 폴백)."""
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

        # 디스크에 직접 있는지도 확인 (sample_count 채우기 위해)
        eval_path = SHARD_DIR / round_id / "eval.jsonl"
        sample_count = 0
        if eval_path.exists():
            try:
                with eval_path.open("r", encoding="utf-8") as f:
                    sample_count = sum(1 for line in f if line.strip())
            except Exception:
                pass

        return {
            "round_id": round_id,
            "agent_id": agent_id,
            "shard_kind": "validation",
            "data_url": _validation_url(round_id),
            "sample_count": sample_count,
            "checksum": None,
        }

    @staticmethod
    def read_eval_shard(round_id: str) -> list[dict[str, Any]]:
        """grid.py 의 ``/eval-shard`` 가 호출할 헬퍼.

        디스크의 ``{SHARD_DIR}/{round_id}/eval.jsonl`` 을 읽어 list[dict] 로 반환.
        파일 없으면 빈 리스트.
        """
        eval_path = SHARD_DIR / round_id / "eval.jsonl"
        if not eval_path.exists():
            return []
        out: list[dict[str, Any]] = []
        try:
            with eval_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning("read_eval_shard 실패 %s: %s", eval_path, e)
        return out

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
        """Dirichlet(α) 비율로 비대칭 분할 (non-IID)."""
        if n_agents <= 0 or total <= 0:
            return [0] * n_agents
        try:
            import numpy as np  # type: ignore

            rng = np.random.default_rng(seed=42)
            props = rng.dirichlet([alpha] * n_agents)
        except Exception:
            raw = [1.0 / (i + 1) for i in range(n_agents)]
            s = sum(raw)
            props = [r / s for r in raw]

        counts = [int(round(p * total)) for p in props]
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

    # ─── 실제 chunk 만들기 ──────────────────────────────────
    @staticmethod
    def _chunk_iid(
        samples: list[dict[str, Any]], counts: list[int]
    ) -> list[list[dict[str, Any]]]:
        """순차적으로 잘라 list[list[dict]] 반환."""
        out: list[list[dict[str, Any]]] = []
        cursor = 0
        for n in counts:
            chunk = samples[cursor : cursor + int(n)]
            out.append(chunk)
            cursor += int(n)
        return out

    @staticmethod
    def _chunk_by_domain(
        samples: list[dict[str, Any]],
        agent_ids: list[str],
        agent_domain_map: dict[str, list[str]],
        counts: list[int],
    ) -> list[list[dict[str, Any]]]:
        """샘플의 ``domain`` 라벨로 그룹핑 후 같은 도메인 에이전트들에게 우선 배분."""
        # 샘플을 도메인별로 buckets 화
        buckets: dict[str, list[dict[str, Any]]] = {}
        for s in samples:
            d = (s.get("domain") or s.get("category") or "misc")
            buckets.setdefault(str(d), []).append(s)

        out: list[list[dict[str, Any]]] = [[] for _ in agent_ids]
        for idx, aid in enumerate(agent_ids):
            need = int(counts[idx])
            if need <= 0:
                continue
            preferred = (agent_domain_map.get(aid) or ["misc"])[0]
            # 1차: 선호 도메인에서 가져오기
            taken = buckets.get(preferred, [])
            take = taken[:need]
            del taken[: len(take)]
            out[idx].extend(take)
            need -= len(take)
            # 2차: 부족하면 아무 도메인이나
            if need > 0:
                for k in list(buckets.keys()):
                    if need <= 0:
                        break
                    avail = buckets[k]
                    take = avail[:need]
                    del avail[: len(take)]
                    out[idx].extend(take)
                    need -= len(take)
        return out

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
    def _checksum_path(path: Path) -> str:
        """파일의 sha256 (32 chars) 반환."""
        try:
            h = hashlib.sha256()
            with path.open("rb") as f:
                for blk in iter(lambda: f.read(64 * 1024), b""):
                    h.update(blk)
            return h.hexdigest()[:32]
        except Exception:
            return ""

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


__all__ = ["DataShardingService", "SHARD_DIR", "PUBLIC_BASE_URL"]
