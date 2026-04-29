"""HSEE Phase 3 — 미분류 질문에서 새 도메인 자동 발견.

기존 도메인 분류기가 ``general`` 로 떨어뜨렸고 만족도가 낮은 질문들을
임베딩 → K-means 클러스터링하여 새 도메인 후보를 추출한다.

플로우:
1. ``RLHFFeedback`` 에서 ``domain == "general" AND isSatisfied == False`` 인
   followupMsg / 메시지를 모은다.
2. 각 메시지를 ``embed_text`` (bge-m3 또는 fallback 해시) 로 벡터화.
3. ``sklearn.cluster.KMeans`` 로 클러스터링. 적절한 ``k`` 는 silhouette 또는
   샘플 수 기반 휴리스틱.
4. 각 클러스터의 대표 텍스트 5 개와 LLM 으로 추출한 도메인 이름·설명을
   ``EmergentDomain`` 에 upsert.

의존성:
- ``scikit-learn`` (선택) — 없으면 단순 그리디 클러스터링으로 fallback
- ``numpy`` (선택)
- ``hwarang_api.knowledge.embeddings.embed_text``
- ``hwarang_api.knowledge.llm._chat`` (도메인 이름 추출)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# 클러스터 최소 크기 — 이보다 작으면 후보로 등록 안 함
DEFAULT_MIN_CLUSTER_SIZE = 50
DEFAULT_MAX_CLUSTERS = 10
DEFAULT_FETCH_LIMIT = 2000


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


# ────────────────────────────────────────────────────────────
# 메인 API
# ────────────────────────────────────────────────────────────
async def discover_emergent_domains(
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
    max_clusters: int = DEFAULT_MAX_CLUSTERS,
    fetch_limit: int = DEFAULT_FETCH_LIMIT,
) -> list[dict[str, Any]]:
    """미분류 질문에서 K-means 클러스터링으로 새 도메인 후보 추출.

    Returns
    -------
    list[dict]
        등록 / 업데이트된 ``EmergentDomain`` 후보 dict 목록.
    """
    if not _prisma_ready():
        return []

    # 1) 미분류 질문 수집
    texts = await _collect_unmatched_texts(fetch_limit=fetch_limit)
    if len(texts) < min_cluster_size:
        return []

    # 2) 임베딩
    embeddings = await _embed_texts(texts)
    if len(embeddings) < min_cluster_size:
        return []

    # 3) 클러스터링
    n_clusters = max(2, min(max_clusters, len(embeddings) // min_cluster_size))
    labels = _cluster(embeddings, n_clusters=n_clusters)

    # 4) 클러스터별 대표 + EmergentDomain 저장
    candidates: list[dict[str, Any]] = []
    for cluster_id in range(n_clusters):
        cluster_texts = [
            texts[i] for i, l in enumerate(labels) if l == cluster_id
        ]
        if len(cluster_texts) < min_cluster_size:
            continue

        name, desc = await _name_cluster(cluster_texts)
        if not name:
            continue

        try:
            row = await prisma.emergentdomain.upsert(
                where={"candidateName": name},
                data={
                    "create": {
                        "candidateName": name,
                        "description": desc,
                        "exampleQueries": cluster_texts[:5],
                        "sampleCount": len(cluster_texts),
                    },
                    "update": {
                        "description": desc,
                        "exampleQueries": cluster_texts[:5],
                        "sampleCount": {"increment": len(cluster_texts)},
                    },
                },
            )
            candidates.append(_emergent_to_dict(row))
        except Exception as e:  # pragma: no cover
            logger.warning(f"EmergentDomain upsert 실패 ({name}): {e}")

    return candidates


# ────────────────────────────────────────────────────────────
# 데이터 수집
# ────────────────────────────────────────────────────────────
async def _collect_unmatched_texts(fetch_limit: int) -> list[str]:
    """RLHFFeedback 의 followupMsg + Message 본문에서 미분류 질문 수집."""
    try:
        rows = await prisma.rlhffeedback.find_many(
            where={"domain": "general", "isSatisfied": False},
            take=fetch_limit,
            order={"createdAt": "desc"},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"RLHFFeedback 조회 실패: {e}")
        return []

    out: list[str] = []
    for f in rows:
        msg = (f.followupMsg or "").strip()
        if msg and len(msg) > 5:
            out.append(msg[:1000])
    return out


# ────────────────────────────────────────────────────────────
# 임베딩
# ────────────────────────────────────────────────────────────
async def _embed_texts(texts: list[str]) -> list[list[float]]:
    """``embed_batch`` 사용. 실패 시 ``embed_text`` 하나씩."""
    try:
        from hwarang_api.knowledge.embeddings import embed_batch  # type: ignore

        return await embed_batch(texts)
    except Exception as e:  # pragma: no cover
        logger.warning(f"embed_batch 실패, 단건 fallback: {e}")

    try:
        from hwarang_api.knowledge.embeddings import embed_text  # type: ignore

        out: list[list[float]] = []
        for t in texts:
            try:
                out.append(await embed_text(t))
            except Exception:
                continue
        return out
    except Exception as e:  # pragma: no cover
        logger.warning(f"embed_text fallback 실패: {e}")
        return []


# ────────────────────────────────────────────────────────────
# 클러스터링
# ────────────────────────────────────────────────────────────
def _cluster(embeddings: list[list[float]], n_clusters: int) -> list[int]:
    """K-means. sklearn 없으면 그리디 fallback."""
    try:
        from sklearn.cluster import KMeans  # type: ignore
        import numpy as np  # type: ignore

        arr = np.array(embeddings, dtype="float32")
        km = KMeans(n_clusters=n_clusters, n_init=4, random_state=42)
        labels = km.fit_predict(arr)
        return [int(x) for x in labels]
    except Exception as e:  # pragma: no cover
        logger.warning(f"sklearn KMeans 실패, greedy fallback: {e}")
        return _greedy_cluster(embeddings, n_clusters=n_clusters)


def _greedy_cluster(
    embeddings: list[list[float]], n_clusters: int
) -> list[int]:
    """sklearn 없을 때 — 단순 코사인 기반 greedy 분할.

    품질은 낮지만 의존성 없이 작동.
    """
    if not embeddings:
        return []

    # 처음 n_clusters 개를 centroid 로
    centroids = embeddings[:n_clusters]
    labels: list[int] = []
    for v in embeddings:
        best, best_sim = 0, -2.0
        for i, c in enumerate(centroids):
            s = _cosine(v, c)
            if s > best_sim:
                best_sim = s
                best = i
        labels.append(best)
    return labels


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = sum(x * x for x in a[:n]) ** 0.5
    nb = sum(x * x for x in b[:n]) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ────────────────────────────────────────────────────────────
# 클러스터 이름 추출 (LLM)
# ────────────────────────────────────────────────────────────
async def _name_cluster(
    texts: list[str], max_examples: int = 8
) -> tuple[Optional[str], Optional[str]]:
    """LLM 으로 도메인 이름 (영문 1단어) + 한국어 설명 추출."""
    sample = texts[:max_examples]
    prompt = (
        "다음 한국어 질문들의 공통 주제를 식별하고, 영문 1단어 도메인 이름과 "
        "한국어 한 줄 설명을 출력하세요. 형식은 정확히 다음과 같이:\n"
        "name: <영문소문자 한 단어>\n"
        "desc: <한국어 한 줄 설명>\n\n"
        "질문 목록:\n"
        + "\n".join(f"- {t}" for t in sample)
    )

    try:
        from hwarang_api.knowledge.llm import _chat  # type: ignore

        raw = await _chat(prompt, max_tokens=120)
    except Exception as e:  # pragma: no cover
        logger.debug(f"LLM 호출 실패, heuristic 사용: {e}")
        raw = ""

    name = _parse_field(raw, "name")
    desc = _parse_field(raw, "desc")

    # LLM 실패 시 휴리스틱 fallback — 가장 흔한 명사 추출은 어려우므로 timestamp 기반
    if not name:
        name = f"emergent_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        desc = desc or "auto-discovered cluster"

    # 도메인 이름 정규화
    name = re.sub(r"[^a-z0-9_]", "", name.lower())[:40] or None
    return name, desc


def _parse_field(raw: str, key: str) -> Optional[str]:
    if not raw:
        return None
    for line in raw.splitlines():
        line = line.strip()
        if line.lower().startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


# ────────────────────────────────────────────────────────────
# 조회 / 승격
# ────────────────────────────────────────────────────────────
async def list_emergent(
    promoted: Optional[bool] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not _prisma_ready():
        return []
    where: dict[str, Any] = {}
    if promoted is not None:
        where["isPromoted"] = promoted
    rows = await prisma.emergentdomain.find_many(
        where=where,
        order={"sampleCount": "desc"},
        take=limit,
    )
    return [_emergent_to_dict(r) for r in rows]


async def promote_emergent(emergent_id: str) -> dict[str, Any]:
    """관리자 승인 — EmergentDomain 을 정식 도메인으로 표시."""
    if not _prisma_ready():
        return {"promoted": False, "reason": "db_unavailable"}
    try:
        row = await prisma.emergentdomain.update(
            where={"id": emergent_id},
            data={
                "isPromoted": True,
                "promotedAt": datetime.now(timezone.utc),
            },
        )
        return {"promoted": True, "domain": row.candidateName}
    except Exception as e:  # pragma: no cover
        logger.warning(f"promote_emergent 실패: {e}")
        return {"promoted": False, "error": str(e)}


def _emergent_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "candidateName": r.candidateName,
        "description": r.description,
        "exampleQueries": list(r.exampleQueries or []),
        "sampleCount": r.sampleCount,
        "isPromoted": r.isPromoted,
        "promotedAt": r.promotedAt.isoformat() if r.promotedAt else None,
        "firstSeenAt": r.firstSeenAt.isoformat() if r.firstSeenAt else None,
        "lastUpdatedAt": r.lastUpdatedAt.isoformat() if r.lastUpdatedAt else None,
    }


__all__ = [
    "discover_emergent_domains",
    "list_emergent",
    "promote_emergent",
]
