"""모듈 3: RAG 인덱싱 에이전트

로컬 문서를 벡터 임베딩 → 분산 RAG 인덱스.
마스터가 검색 요청 시 로컬 인덱스에서 검색.

보상: 문서 인덱싱 10건당 1 HWR
"""

import os, json, logging, hashlib

logger = logging.getLogger(__name__)


class RAGIndexerModule:
    def __init__(self, config):
        self.config = config
        self.index_path = os.path.expanduser("~/.hwarang/rag_index")
        os.makedirs(self.index_path, exist_ok=True)
        self.indexed_count = 0

    def index_documents(self, docs_path: str) -> dict:
        """로컬 문서 인덱싱."""
        if not os.path.exists(docs_path):
            return {"error": "경로 없음", "indexed": 0}

        files = []
        for root, _, filenames in os.walk(docs_path):
            for f in filenames:
                if f.endswith((".txt", ".md", ".pdf", ".jsonl")):
                    files.append(os.path.join(root, f))

        indexed = 0
        for fp in files[:self.config.max_docs]:
            try:
                text = self._read_file(fp)
                if text:
                    doc_id = hashlib.md5(fp.encode()).hexdigest()[:12]
                    self._store_index(doc_id, fp, text)
                    indexed += 1
            except Exception as e:
                logger.warning(f"인덱싱 실패: {fp}: {e}")

        self.indexed_count += indexed
        return {"indexed": indexed, "total_files": len(files)}

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """로컬 인덱스 검색 (간단 키워드 매칭)."""
        results = []
        index_file = os.path.join(self.index_path, "index.jsonl")
        if not os.path.exists(index_file):
            return []

        query_words = set(query.lower().split())
        with open(index_file, encoding="utf-8") as f:
            for line in f:
                try:
                    doc = json.loads(line)
                    text_words = set(doc.get("text", "").lower().split())
                    score = len(query_words & text_words) / max(len(query_words), 1)
                    if score > 0:
                        results.append({"doc_id": doc["id"], "path": doc["path"], "score": score, "snippet": doc["text"][:200]})
                except: pass

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _read_file(self, path: str) -> str:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                return f.read()[:5000]
        except: return ""

    def _store_index(self, doc_id: str, path: str, text: str):
        index_file = os.path.join(self.index_path, "index.jsonl")
        with open(index_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": doc_id, "path": path, "text": text[:2000]}, ensure_ascii=False) + "\n")
