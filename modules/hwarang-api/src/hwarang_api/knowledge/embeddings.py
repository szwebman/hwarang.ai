"""HLKM 공통 임베딩 유틸.

실제 임베딩 서버(bge-m3 등)가 있을 때는 HTTP 호출,
없을 때는 해싱 기반 fallback(결정적 1024-dim 벡터)을 사용한다.

디펜던시 최소화를 위해 httpx / numpy 는 lazy import.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import Any

logger = logging.getLogger(__name__)

# 환경변수
#   EMBEDDING_SERVER_URL  — 빈 문자열이면 fallback 강제
#   EMBEDDING_DIM         — 기본 1024 (bge-m3 차원)
#   EMBEDDING_TIMEOUT     — 단건 호출 타임아웃 (초)
#   EMBEDDING_API_KEY     — bge-m3/TEI/OpenAI 서버에 Bearer 인증
#   EMBEDDING_MODEL       — 서버에 모델명 강제 지정 (옵션)
_EMBED_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
_EMBED_URL = os.getenv("EMBEDDING_SERVER_URL", "")
_EMBED_TIMEOUT = float(os.getenv("EMBEDDING_TIMEOUT", "10"))
_EMBED_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
_EMBED_MODEL_OVERRIDE = os.getenv("EMBEDDING_MODEL", "")


def _auth_headers() -> dict[str, str]:
    """공통 헤더 — Bearer 토큰이 있으면 Authorization 추가."""
    headers = {"Content-Type": "application/json"}
    if _EMBED_API_KEY:
        headers["Authorization"] = f"Bearer {_EMBED_API_KEY}"
    return headers


def _normalize_url(base: str, suffix: str = "") -> str:
    """EMBEDDING_SERVER_URL 이 /embed 로 끝나든 root 든 모두 허용."""
    base = base.rstrip("/")
    if suffix and not base.endswith(suffix):
        return base + suffix
    return base


def _extract_single_vector(payload: Any) -> list[float] | None:
    """다양한 응답 포맷에서 단일 임베딩 추출.

    지원 포맷:
      - TEI:        [[float, ...]]              (배열 1개)
      - TEI single: [float, ...]
      - OpenAI:     {"data":[{"embedding":[...]}]}
      - 자체:       {"embedding":[...]} | {"vector":[...]}
    """
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, list):
            return [float(x) for x in first]
        if isinstance(first, (int, float)):
            return [float(x) for x in payload]
    if isinstance(payload, dict):
        if "data" in payload and isinstance(payload["data"], list) and payload["data"]:
            row = payload["data"][0]
            if isinstance(row, dict) and "embedding" in row:
                return [float(x) for x in row["embedding"]]
        for key in ("embedding", "vector"):
            v = payload.get(key)
            if isinstance(v, list) and v and isinstance(v[0], (int, float)):
                return [float(x) for x in v]
    return None


def _extract_batch_vectors(payload: Any, n: int) -> list[list[float]] | None:
    """배치 응답에서 임베딩 리스트 추출."""
    if isinstance(payload, list) and len(payload) == n:
        # TEI: [[...], [...]]
        if all(isinstance(row, list) for row in payload):
            return [[float(x) for x in row] for row in payload]
    if isinstance(payload, dict):
        if "data" in payload and isinstance(payload["data"], list) and len(payload["data"]) == n:
            out: list[list[float]] = []
            for row in payload["data"]:
                if isinstance(row, dict) and "embedding" in row:
                    out.append([float(x) for x in row["embedding"]])
                else:
                    return None
            return out
        for key in ("embeddings", "vectors"):
            v = payload.get(key)
            if isinstance(v, list) and len(v) == n:
                return [[float(x) for x in row] for row in v]
    return None


def _fit_dim(vec: list[float], dim: int = _EMBED_DIM) -> list[float]:
    """차원 보정 — 길면 자르고, 짧으면 0-패딩."""
    if len(vec) >= dim:
        return vec[:dim]
    return vec + [0.0] * (dim - len(vec))


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

    1. EMBEDDING_SERVER_URL 설정되어 있으면 bge-m3/TEI/OpenAI-호환 서버 호출
       - TEI 표준:   POST /embed   {"inputs": "...", "normalize": true}
       - 자체 형식:  POST /embed   {"text": "...", "model": "bge-m3"}
       - OpenAI:    POST /v1/embeddings {"input": "...", "model": "..."}
    2. 실패/미설정 시 SHA-256 해싱 결정적 fallback (의미 검색 불가, 동작만 보장)

    반환 차원은 `_EMBED_DIM` (기본 1024). 서버가 다른 차원이면 잘라내거나 0-패딩.
    """
    if _EMBED_URL:
        try:
            import httpx

            url = _normalize_url(_EMBED_URL, "/embed") if "/embed" not in _EMBED_URL else _EMBED_URL.rstrip("/")
            payload_model = _EMBED_MODEL_OVERRIDE or model
            # TEI 형식 우선 (BAAI/bge-m3 가 TEI 로 가장 흔히 서빙됨)
            body = {"inputs": text, "normalize": True, "model": payload_model, "text": text}
            async with httpx.AsyncClient(timeout=_EMBED_TIMEOUT) as client:
                r = await client.post(url, json=body, headers=_auth_headers())
                if r.status_code == 200:
                    vec = _extract_single_vector(r.json())
                    if vec is not None:
                        return _fit_dim(vec)
                else:
                    logger.warning(
                        "embedding server %s status=%s body=%s",
                        url, r.status_code, r.text[:200],
                    )
        except Exception as exc:
            logger.warning("bge-m3 embedding 실패, fallback 사용: %s", exc)
    return _hash_embed(text)


async def embed_batch(texts: list[str], model: str = "bge-m3") -> list[list[float]]:
    """배치 임베딩.

    서버가 batch 엔드포인트를 지원하면 한 번에 처리, 아니면 fallback 으로 개별 호출.
    """
    if not texts:
        return []
    if _EMBED_URL:
        try:
            import httpx

            url = _normalize_url(_EMBED_URL, "/embed") if "/embed" not in _EMBED_URL else _EMBED_URL.rstrip("/")
            payload_model = _EMBED_MODEL_OVERRIDE or model
            # TEI 는 inputs 가 list 면 자동 배치
            body = {
                "inputs": texts,
                "normalize": True,
                "model": payload_model,
                "texts": texts,
                "batch": True,
            }
            async with httpx.AsyncClient(timeout=_EMBED_TIMEOUT * 2) as client:
                r = await client.post(url, json=body, headers=_auth_headers())
                if r.status_code == 200:
                    vecs = _extract_batch_vectors(r.json(), len(texts))
                    if vecs is not None:
                        return [_fit_dim(v) for v in vecs]
                else:
                    logger.warning(
                        "embedding batch %s status=%s body=%s",
                        url, r.status_code, r.text[:200],
                    )
        except Exception as exc:
            logger.warning("bge-m3 batch embedding 실패, fallback 사용: %s", exc)
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
