"""Embedding API - 텍스트 → 벡터 변환.

RAG, 유사도 검색, 클러스터링 등에 사용됩니다.
OpenAI /v1/embeddings 호환 API.

사용법:
    embedder = EmbeddingService()
    vectors = embedder.embed(["안녕하세요", "파이썬 코드"])
    similarity = embedder.similarity("질문", "문서 내용")
"""

from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    embeddings: list[list[float]]
    model: str
    token_count: int


class EmbeddingService:
    """임베딩 서비스."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-large"):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model loaded: {self.model_name}")
        except ImportError:
            logger.warning("sentence-transformers 필요: pip install sentence-transformers")

    def embed(self, texts: list[str], normalize: bool = True) -> EmbeddingResult:
        """텍스트 리스트 → 벡터 리스트."""
        self._load()
        if self._model:
            vectors = self._model.encode(texts, normalize_embeddings=normalize)
            return EmbeddingResult(
                embeddings=vectors.tolist(),
                model=self.model_name,
                token_count=sum(len(t.split()) for t in texts),
            )
        # Fallback
        dim = 1024
        return EmbeddingResult(
            embeddings=[np.random.randn(dim).tolist() for _ in texts],
            model="random", token_count=0,
        )

    def similarity(self, text_a: str, text_b: str) -> float:
        """두 텍스트의 코사인 유사도 (0~1)."""
        result = self.embed([text_a, text_b])
        a, b = np.array(result.embeddings[0]), np.array(result.embeddings[1])
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def batch_similarity(self, query: str, documents: list[str]) -> list[float]:
        """쿼리와 문서 리스트의 유사도."""
        result = self.embed([query] + documents)
        q_vec = np.array(result.embeddings[0])
        scores = []
        for i in range(1, len(result.embeddings)):
            d_vec = np.array(result.embeddings[i])
            score = float(np.dot(q_vec, d_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(d_vec)))
            scores.append(score)
        return scores
