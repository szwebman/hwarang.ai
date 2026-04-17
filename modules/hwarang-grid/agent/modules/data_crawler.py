"""모듈 1: 데이터 크롤링 에이전트

한국 뉴스/법령/코드를 자동 수집 → 마스터에 전달.
지속 학습(CL)의 데이터 공급원.

크롤링 소스:
  - 법제처 API (법령 개정)
  - 기술 뉴스 (네이버/Google)
  - GitHub 트렌딩 (코드)
  - Stack Overflow 한국어

보상: 수집 건당 0.5 HWR, 품질 검증 후 보너스
"""

import json, os, time, logging, hashlib
from datetime import datetime

logger = logging.getLogger(__name__)


class DataCrawlerModule:
    def __init__(self, config):
        self.config = config
        self.collected_count = 0
        self.storage_path = os.path.expanduser("~/.hwarang/crawled_data")
        os.makedirs(self.storage_path, exist_ok=True)

    def run_cycle(self) -> dict:
        """한 사이클 크롤링."""
        results = {"sources": {}, "total": 0}

        for source in self.config.sources:
            try:
                if source == "law":
                    items = self._crawl_law()
                elif source == "news":
                    items = self._crawl_news()
                elif source == "code":
                    items = self._crawl_code()
                else:
                    items = []

                results["sources"][source] = len(items)
                results["total"] += len(items)

                # 로컬 저장
                if items:
                    self._save_items(source, items)

            except Exception as e:
                logger.warning(f"크롤링 실패 [{source}]: {e}")

        self.collected_count += results["total"]
        return results

    def _crawl_law(self) -> list[dict]:
        """법제처 법령 업데이트."""
        api_key = os.environ.get("LAW_GO_KR_API_KEY", "")
        if not api_key: return []

        import urllib.request
        try:
            url = f"http://www.law.go.kr/DRF/lawSearch.do?OC={api_key}&target=law&type=JSON&query=개정&display=10"
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read())
            laws = data.get("LawSearch", {}).get("law", [])
            return [{"type": "law", "title": l.get("법령명한글", ""), "date": l.get("공포일자", "")} for l in laws[:self.config.max_items_per_run]]
        except: return []

    def _crawl_news(self) -> list[dict]:
        """기술 뉴스. (실제는 네이버 API 필요)"""
        return []  # TODO: 네이버 뉴스 API 연동

    def _crawl_code(self) -> list[dict]:
        """GitHub 트렌딩. (실제는 GitHub API 필요)"""
        return []  # TODO: GitHub API 연동

    def _save_items(self, source: str, items: list):
        """수집 데이터 로컬 저장."""
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        path = os.path.join(self.storage_path, f"{source}_{date_str}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def get_stats(self) -> dict:
        """크롤링 통계."""
        files = list(os.listdir(self.storage_path))
        total_size = sum(os.path.getsize(os.path.join(self.storage_path, f)) for f in files)
        return {
            "total_collected": self.collected_count,
            "files": len(files),
            "storage_mb": round(total_size / 1024 / 1024, 1),
            "limit_mb": self.config.storage_limit_mb,
        }
