"""HLKM 공통 임베딩 유틸.

실제 임베딩 서버(bge-m3 등)가 있을 때는 HTTP 호출,
없을 때는 해싱 기반 fallback(결정적 1024-dim 벡터)을 사용한다.

디펜던시 최소화를 위해 httpx / numpy 는 lazy import.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Any

_EMBED_DIM = 1024
_EMBED_URL = os.getenv("EMBEDDING_SERVER_URL", "http://localhost:8080/embed")
_EMBED_TIMEOUT = float(os.getenv("EMBEDDING_TIMEOUT", "5.0"))


def _hash_embed(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """결정적 해싱 기반 임베딩 (fallback).

    - 8바이트 단위로 SHA-256 체인을 돌려 float 벡터를 만든다.
    - L2 정규화된 dim 차원 벡터를 반환.
    """
    if not text:
        return [0.0] * dim

    buf = bytearray()
    seed = text.encode("utf-8")
    while len(buf) < dim * 4:  # 4바이트 per float
        seed = hashlib.sha256(seed).digest()
        buf.extend(seed)

    vec: list[float] = []
    for i in range(dim):
        chunk = buf[i * 4 : i * 4 + 4]
        # 4바이트 → 부호있는 float(-1~1 근사)
        n = int.from_bytes(chunk, "little", signed=False)
        vec.append((n / 0xFFFFFFFF) * 2.0 - 1.0)

    # L2 정규화
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


async def embed_text(text: str, model: str = "bge-m3") -> list[float]:
    """단일 문장을 임베딩한다.

    우선 HTTP 임베딩 서버를 호출하고, 실패 시 해싱 fallback.
    반환 차원은 `_EMBED_DIM` (1024). 서버가 다른 차원을 주면 잘라내거나 0-패딩.
    """
    try:
        import httpx

        async with httpx.AsyncClient(timeout=_EMBED_TIMEOUT) as client:
            r = await client.post(_EMBED_URL, json={"text": text, "model": model})
            if r.status_code == 200:
                payload: Any = r.json()
                vec = payload.get("embedding") or payload.get("vector") or payload.get("data")
                if isinstance(vec, list) and vec and isinstance(vec[0], (int, float)):
                    vec_f = [float(x) for x in vec]
                    if len(vec_f) >= _EMBED_DIM:
                        return vec_f[:_EMBED_DIM]
                    return vec_f + [0.0] * (_EMBED_DIM - len(vec_f))
    except Exception:
        # HTTP 실패/미구현 → fallback.
        pass
    return _hash_embed(text)


async def embed_batch(texts: list[str], model: str = "bge-m3") -> list[list[float]]:
    """배치 임베딩.

    서버가 batch 엔드포인트를 지원하면 한 번에, 아니면 각각 호출 후 수집.
    """
    if not texts:
        return []
    try:
        import httpx

        async with httpx.AsyncClient(timeout=_EMBED_TIMEOUT) as client:
            r = await client.post(
                _EMBED_URL, json={"texts": texts, "model": model, "batch": True}
            )
            if r.status_code == 200:
                payload: Any = r.json()
                vecs = payload.get("embeddings") or payload.get("data")
                if isinstance(vecs, list) and len(vecs) == len(texts):
                    out: list[list[float]] = []
                    for vec in vecs:
                        vec_f = [float(x) for x in vec]
                        if len(vec_f) >= _EMBED_DIM:
                            out.append(vec_f[:_EMBED_DIM])
                        else:
                            out.append(vec_f + [0.0] * (_EMBED_DIM - len(vec_f)))
                    return out
    except Exception:
        pass
    # fallback: 개별 호출
    out2: list[list[float]] = []
    for t in texts:
        out2.append(await embed_text(t, model))
    return out2


def cosine(a: list[float], b: list[float]) -> float:
    """순수 Python 코사인 유사도.

    길이 불일치 또는 zero-vector 인 경우 0.0 반환.
    """
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        x = a[i]
        y = b[i]
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def batch_cosine(query: list[float], matrix: list[list[float]]) -> list[float]:
    """쿼리 벡터와 행렬 각 행의 코사인 유사도.

    numpy 가 있으면 벡터화, 없으면 pure-Python fallback.
    """
    if not matrix:
        return []
    if not query:
        return [0.0] * len(matrix)
    try:
        import numpy as np

        q = np.asarray(query, dtype=np.float32)
        m = np.asarray(matrix, dtype=np.float32)
        qn = float(np.linalg.norm(q))
        if qn == 0.0:
            return [0.0] * len(matrix)
        mn = np.linalg.norm(m, axis=1)
        # 0인 행 보호
        safe = np.where(mn == 0, 1.0, mn)
        sims = (m @ q) / (safe * qn)
        sims = np.where(mn == 0, 0.0, sims)
        return [float(x) for x in sims.tolist()]
    except Exception:
        return [cosine(query, row) for row in matrix]


__all__ = ["embed_text", "embed_batch", "cosine", "batch_cosine"]
