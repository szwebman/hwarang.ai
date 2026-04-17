"""모듈 6: 응답 캐시 에이전트

자주 묻는 질문의 응답을 로컬 캐싱 → 즉시 응답.
캐시 히트율이 높을수록 서버 부하 감소.
"""

import hashlib, json, os, time, logging

logger = logging.getLogger(__name__)


class ResponseCacheModule:
    def __init__(self, config):
        self.config = config
        self.cache_path = os.path.expanduser("~/.hwarang/response_cache")
        os.makedirs(self.cache_path, exist_ok=True)
        self.cache: dict[str, dict] = {}
        self.hits = 0
        self.misses = 0
        self._load_cache()

    def _cache_key(self, prompt: str) -> str:
        return hashlib.md5(prompt.strip().lower().encode()).hexdigest()

    def get(self, prompt: str) -> str | None:
        key = self._cache_key(prompt)
        entry = self.cache.get(key)
        if entry:
            age_hours = (time.time() - entry["timestamp"]) / 3600
            if age_hours < self.config.ttl_hours:
                entry["hits"] += 1
                self.hits += 1
                return entry["response"]
            else:
                del self.cache[key]  # 만료
        self.misses += 1
        return None

    def put(self, prompt: str, response: str):
        key = self._cache_key(prompt)
        self.cache[key] = {
            "prompt": prompt[:200],
            "response": response,
            "timestamp": time.time(),
            "hits": 0,
        }
        self._enforce_limit()
        self._save_cache()

    def _enforce_limit(self):
        total_size = sum(len(e["response"]) for e in self.cache.values())
        while total_size > self.config.max_cache_mb * 1024 * 1024 and self.cache:
            oldest_key = min(self.cache, key=lambda k: self.cache[k]["timestamp"])
            total_size -= len(self.cache[oldest_key]["response"])
            del self.cache[oldest_key]

    def _save_cache(self):
        path = os.path.join(self.cache_path, "cache.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False)

    def _load_cache(self):
        path = os.path.join(self.cache_path, "cache.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.cache = json.load(f)

    def get_stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "entries": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / max(total, 1) * 100, 1),
        }
