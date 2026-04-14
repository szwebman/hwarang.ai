"""RAG Retriever - 벡터 검색 + 키워드 검색 하이브리드.

질문이 들어오면:
1. 임베딩으로 변환 → 벡터 DB에서 유사 문서 검색
2. 키워드로 BM25 검색 (보조)
3. 두 결과 합쳐서 최종 컨텍스트 구성
4. LLM에 [검색 결과 + 질문] 전달

사용법:
    retriever = HwarangRetriever(collection="legal")
    await retriever.add_documents(docs)

    results = await retriever.search("전세 사기 대처법")
    context = retriever.build_context(results)
    # → context를 LLM 프롬프트에 삽입
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """검색 가능한 문서."""
    id: str
    content: str
    metadata: dict = field(default_factory=dict)
    # metadata 예: {"source": "민법", "article": "103조", "date": "2024-01-01"}
    embedding: list[float] | None = None


@dataclass
class SearchResult:
    """검색 결과."""
    document: Document
    score: float
    match_type: str  # "vector", "keyword", "hybrid"


class HwarangRetriever:
    """하이브리드 검색 엔진 (벡터 + 키워드).

    지원하는 Vector DB:
    - Qdrant (추천, 자체 호스팅)
    - ChromaDB (간단, 임베디드)
    - FAISS (빠름, 메모리)
    """

    def __init__(
        self,
        collection: str = "default",
        vector_db: str = "chroma",  # "chroma", "qdrant", "faiss"
        embedding_model: str = "intfloat/multilingual-e5-large",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        top_k: int = 5,
    ):
        self.collection = collection
        self.vector_db_type = vector_db
        self.embedding_model_name = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k

        self._db = None
        self._embedding_model = None

    async def initialize(self):
        """DB + 임베딩 모델 초기화."""
        # 임베딩 모델 로드
        self._embedding_model = self._load_embedding_model()

        # Vector DB 초기화
        if self.vector_db_type == "chroma":
            self._db = ChromaBackend(self.collection)
        elif self.vector_db_type == "qdrant":
            self._db = QdrantBackend(self.collection)
        elif self.vector_db_type == "faiss":
            self._db = FAISSBackend(self.collection)

        await self._db.initialize()
        logger.info(f"RAG Retriever 초기화: {self.vector_db_type}/{self.collection}")

    def _load_embedding_model(self):
        """임베딩 모델 로드."""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(self.embedding_model_name)
            logger.info(f"임베딩 모델 로드: {self.embedding_model_name}")
            return model
        except ImportError:
            logger.warning("sentence-transformers 없음. 간단한 임베딩 사용.")
            return None

    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트를 벡터로 변환."""
        if self._embedding_model:
            embeddings = self._embedding_model.encode(texts, normalize_embeddings=True)
            return embeddings.tolist()
        # Fallback: 간단한 해시 기반 (테스트용)
        return [[float(ord(c) % 100) / 100 for c in t[:384]] for t in texts]

    # ---- 문서 관리 ----

    async def add_documents(self, documents: list[Document]):
        """문서 추가 (자동 청크 분할 + 임베딩)."""
        all_chunks = []
        for doc in documents:
            chunks = self._chunk_text(doc.content, doc.metadata)
            all_chunks.extend(chunks)

        # 임베딩 생성
        texts = [c.content for c in all_chunks]
        embeddings = self.embed(texts)

        for chunk, emb in zip(all_chunks, embeddings):
            chunk.embedding = emb

        # DB에 저장
        await self._db.upsert(all_chunks)
        logger.info(f"{len(documents)}개 문서 → {len(all_chunks)}개 청크 추가")

    async def add_text(self, text: str, metadata: dict = None):
        """텍스트 직접 추가."""
        doc = Document(
            id=hashlib.md5(text.encode()).hexdigest(),
            content=text,
            metadata=metadata or {},
        )
        await self.add_documents([doc])

    def _chunk_text(self, text: str, metadata: dict) -> list[Document]:
        """텍스트를 청크로 분할."""
        chunks = []
        words = text.split()
        for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)
            if len(chunk_text) < 50:
                continue

            chunks.append(Document(
                id=f"{hashlib.md5(chunk_text.encode()).hexdigest()}",
                content=chunk_text,
                metadata={**metadata, "chunk_index": len(chunks)},
            ))
        return chunks

    # ---- 검색 ----

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        filter_metadata: dict | None = None,
    ) -> list[SearchResult]:
        """하이브리드 검색 (벡터 + 키워드)."""
        k = top_k or self.top_k

        # 1. 벡터 검색
        query_embedding = self.embed([query])[0]
        vector_results = await self._db.vector_search(
            query_embedding, k=k, filter_metadata=filter_metadata
        )

        # 2. 키워드 검색 (BM25 스타일)
        keyword_results = await self._db.keyword_search(
            query, k=k, filter_metadata=filter_metadata
        )

        # 3. 결과 합치기 (RRF: Reciprocal Rank Fusion)
        combined = self._reciprocal_rank_fusion(vector_results, keyword_results)

        return combined[:k]

    def _reciprocal_rank_fusion(
        self,
        vector_results: list[SearchResult],
        keyword_results: list[SearchResult],
        k: int = 60,
    ) -> list[SearchResult]:
        """RRF로 두 검색 결과 합치기."""
        scores: dict[str, float] = {}
        docs: dict[str, Document] = {}

        for rank, result in enumerate(vector_results):
            doc_id = result.document.id
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
            docs[doc_id] = result.document

        for rank, result in enumerate(keyword_results):
            doc_id = result.document.id
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
            docs[doc_id] = result.document

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        return [
            SearchResult(
                document=docs[doc_id],
                score=scores[doc_id],
                match_type="hybrid",
            )
            for doc_id in sorted_ids
        ]

    # ---- 컨텍스트 구성 ----

    def build_context(
        self,
        results: list[SearchResult],
        max_tokens: int = 3000,
        include_sources: bool = True,
    ) -> str:
        """검색 결과를 LLM 컨텍스트로 변환."""
        context_parts = []
        sources = []
        total_chars = 0
        char_limit = max_tokens * 3  # 대략 토큰 → 문자 변환

        for i, result in enumerate(results):
            doc = result.document
            text = doc.content

            if total_chars + len(text) > char_limit:
                text = text[:char_limit - total_chars]

            context_parts.append(f"[문서 {i+1}]\n{text}")
            total_chars += len(text)

            if include_sources and doc.metadata:
                source_info = doc.metadata.get("source", "")
                article = doc.metadata.get("article", "")
                if source_info:
                    sources.append(f"[{i+1}] {source_info} {article}".strip())

            if total_chars >= char_limit:
                break

        context = "\n\n".join(context_parts)

        if include_sources and sources:
            context += "\n\n출처:\n" + "\n".join(sources)

        return context

    def build_rag_prompt(
        self,
        query: str,
        context: str,
        system_prompt: str = "",
    ) -> list[dict]:
        """RAG 프롬프트 구성."""
        default_system = (
            "당신은 제공된 문서를 기반으로 정확하게 답변하는 AI입니다.\n"
            "반드시 문서에 있는 내용만 답변하고, 없는 내용은 '해당 정보를 찾을 수 없습니다'라고 답하세요.\n"
            "답변 시 출처([문서 N])를 반드시 표시하세요."
        )

        return [
            {"role": "system", "content": system_prompt or default_system},
            {"role": "user", "content": f"참고 문서:\n{context}\n\n질문: {query}"},
        ]


# ============================================================
# Vector DB 백엔드 (추상화)
# ============================================================

class VectorDBBackend:
    """Vector DB 추상 클래스."""

    async def initialize(self): ...
    async def upsert(self, documents: list[Document]): ...
    async def vector_search(self, embedding, k, filter_metadata) -> list[SearchResult]: ...
    async def keyword_search(self, query, k, filter_metadata) -> list[SearchResult]: ...


class ChromaBackend(VectorDBBackend):
    """ChromaDB 백엔드 (간단, 로컬)."""

    def __init__(self, collection: str):
        self.collection_name = collection
        self._client = None
        self._collection = None

    async def initialize(self):
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path="./vectordb/chroma")
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except ImportError:
            logger.error("chromadb 필요: pip install chromadb")

    async def upsert(self, documents: list[Document]):
        if not self._collection:
            return
        self._collection.upsert(
            ids=[d.id for d in documents],
            embeddings=[d.embedding for d in documents if d.embedding],
            documents=[d.content for d in documents],
            metadatas=[d.metadata for d in documents],
        )

    async def vector_search(self, embedding, k=5, filter_metadata=None) -> list[SearchResult]:
        if not self._collection:
            return []
        where = filter_metadata if filter_metadata else None
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=k,
            where=where,
        )
        return [
            SearchResult(
                document=Document(id=id_, content=doc, metadata=meta),
                score=1.0 - dist,
                match_type="vector",
            )
            for id_, doc, meta, dist in zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    async def keyword_search(self, query, k=5, filter_metadata=None) -> list[SearchResult]:
        if not self._collection:
            return []
        where_doc = {"$contains": query} if len(query) < 100 else None
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=k,
                where_document=where_doc,
            )
            return [
                SearchResult(
                    document=Document(id=id_, content=doc, metadata=meta),
                    score=1.0 - dist,
                    match_type="keyword",
                )
                for id_, doc, meta, dist in zip(
                    results["ids"][0],
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                )
            ]
        except Exception:
            return []


class QdrantBackend(VectorDBBackend):
    """Qdrant 백엔드 (프로덕션 추천)."""

    def __init__(self, collection: str, url: str = "http://localhost:6333"):
        self.collection_name = collection
        self.url = url
        self._client = None

    async def initialize(self):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            self._client = QdrantClient(url=self.url)
            # 컬렉션 생성 (없으면)
            collections = [c.name for c in self._client.get_collections().collections]
            if self.collection_name not in collections:
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
                )
        except ImportError:
            logger.error("qdrant-client 필요: pip install qdrant-client")

    async def upsert(self, documents: list[Document]):
        if not self._client:
            return
        from qdrant_client.models import PointStruct
        points = [
            PointStruct(
                id=abs(hash(d.id)) % (2**63),
                vector=d.embedding,
                payload={"content": d.content, "metadata": d.metadata, "doc_id": d.id},
            )
            for d in documents if d.embedding
        ]
        self._client.upsert(collection_name=self.collection_name, points=points)

    async def vector_search(self, embedding, k=5, filter_metadata=None) -> list[SearchResult]:
        if not self._client:
            return []
        results = self._client.search(
            collection_name=self.collection_name,
            query_vector=embedding,
            limit=k,
        )
        return [
            SearchResult(
                document=Document(
                    id=r.payload.get("doc_id", str(r.id)),
                    content=r.payload.get("content", ""),
                    metadata=r.payload.get("metadata", {}),
                ),
                score=r.score,
                match_type="vector",
            )
            for r in results
        ]

    async def keyword_search(self, query, k=5, filter_metadata=None) -> list[SearchResult]:
        return []  # Qdrant은 벡터 검색 전문, 키워드는 별도


class FAISSBackend(VectorDBBackend):
    """FAISS 백엔드 (인메모리, 빠름)."""

    def __init__(self, collection: str):
        self.collection_name = collection
        self._index = None
        self._documents: list[Document] = []

    async def initialize(self):
        try:
            import faiss
            self._index = faiss.IndexFlatIP(1024)  # Inner Product (코사인 유사도)
        except ImportError:
            logger.error("faiss-cpu 필요: pip install faiss-cpu")

    async def upsert(self, documents: list[Document]):
        if not self._index:
            return
        import numpy as np
        embeddings = np.array([d.embedding for d in documents if d.embedding], dtype="float32")
        if len(embeddings) > 0:
            import faiss
            faiss.normalize_L2(embeddings)
            self._index.add(embeddings)
            self._documents.extend(documents)

    async def vector_search(self, embedding, k=5, filter_metadata=None) -> list[SearchResult]:
        if not self._index or self._index.ntotal == 0:
            return []
        import numpy as np
        query = np.array([embedding], dtype="float32")
        import faiss
        faiss.normalize_L2(query)
        scores, indices = self._index.search(query, k)

        return [
            SearchResult(
                document=self._documents[idx],
                score=float(score),
                match_type="vector",
            )
            for score, idx in zip(scores[0], indices[0])
            if idx < len(self._documents)
        ]

    async def keyword_search(self, query, k=5, filter_metadata=None) -> list[SearchResult]:
        # 간단한 BM25 스타일 키워드 매칭
        results = []
        query_words = set(query.lower().split())
        for doc in self._documents:
            doc_words = set(doc.content.lower().split())
            overlap = len(query_words & doc_words)
            if overlap > 0:
                score = overlap / max(len(query_words), 1)
                results.append(SearchResult(document=doc, score=score, match_type="keyword"))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]
