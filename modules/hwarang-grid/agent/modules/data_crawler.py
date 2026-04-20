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

    def upload_to_master(self, master_url: str, agent_id: str) -> dict:
        """수집 데이터를 마스터 서버에 업로드.

        로컬에 쌓인 크롤링 데이터를 마스터에 전송.
        마스터가 품질 검증 후 학습 데이터로 변환.
        업로드 완료된 파일은 .uploaded 마킹.
        """
        uploaded = 0
        failed = 0

        try:
            import httpx
            client = httpx.Client(timeout=60)

            for filename in os.listdir(self.storage_path):
                filepath = os.path.join(self.storage_path, filename)

                # 이미 업로드된 파일 건너뛰기
                if filename.endswith(".uploaded") or not filename.endswith(".jsonl"):
                    continue

                try:
                    with open(filepath, "rb") as f:
                        response = client.post(
                            f"{master_url}/grid/data/upload",
                            data={
                                "agent_id": agent_id,
                                "source": filename.split("_")[0],  # law, news, code
                            },
                            files={"data_file": (filename, f)},
                        )

                    if response.status_code == 200:
                        # 업로드 완료 마킹
                        os.rename(filepath, filepath + ".uploaded")
                        uploaded += 1
                        result = response.json()
                        reward = result.get("reward", 0)
                        if reward > 0:
                            logger.info(f"📤 데이터 업로드: {filename} → +{reward} HWR")
                    else:
                        failed += 1

                except Exception as e:
                    logger.warning(f"업로드 실패 [{filename}]: {e}")
                    failed += 1

            client.close()

        except ImportError:
            logger.warning("httpx 없음 → 데이터 업로드 불가")
            return {"error": "httpx 필요"}

        logger.info(f"데이터 업로드 완료: 성공 {uploaded}, 실패 {failed}")
        return {"uploaded": uploaded, "failed": failed}

    def convert_to_training_data(self) -> str | None:
        """수집된 원본 데이터를 SFT 학습 형식(JSONL)으로 변환.

        뉴스 → "이 뉴스를 요약해줘" Q&A
        법령 → "이 법령을 설명해줘" Q&A
        코드 → "이 코드를 설명해줘" Q&A
        """
        output_path = os.path.join(self.storage_path, "training_data.jsonl")
        count = 0

        with open(output_path, "w", encoding="utf-8") as fout:
            for filename in os.listdir(self.storage_path):
                if not filename.endswith(".jsonl") or filename == "training_data.jsonl":
                    continue

                filepath = os.path.join(self.storage_path, filename)
                source = filename.split("_")[0]

                try:
                    with open(filepath, encoding="utf-8") as fin:
                        for line in fin:
                            item = json.loads(line.strip())
                            training_item = self._to_qa_pair(source, item)
                            if training_item:
                                fout.write(json.dumps(training_item, ensure_ascii=False) + "\n")
                                count += 1
                except Exception:
                    continue

        if count > 0:
            logger.info(f"학습 데이터 변환: {count}건 → {output_path}")
            return output_path
        return None

    def _to_qa_pair(self, source: str, item: dict) -> dict | None:
        """원본 데이터를 Q&A 학습 형식으로 변환."""
        content = item.get("title", "") or item.get("content", "")
        if not content or len(content) < 20:
            return None

        system = "당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다."

        if source == "law":
            return {"messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"다음 법령에 대해 쉽게 설명해줘: {content}"},
                {"role": "assistant", "content": f"'{content}' 법령에 대해 설명드리겠습니다.\n\n{item.get('summary', content)}"},
            ]}
        elif source == "news":
            return {"messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"다음 뉴스를 요약해줘: {content}"},
                {"role": "assistant", "content": f"해당 뉴스의 핵심 내용입니다.\n\n{item.get('summary', content)}"},
            ]}
        elif source == "code":
            return {"messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"다음 코드를 설명해줘:\n```\n{content}\n```"},
                {"role": "assistant", "content": f"이 코드를 분석해드리겠습니다.\n\n{item.get('description', '이 코드는 ' + content[:100] + '...')}"},
            ]}
        return None

    def get_stats(self) -> dict:
        """크롤링 통계."""
        all_files = [f for f in os.listdir(self.storage_path) if not f.startswith(".")]
        pending = [f for f in all_files if f.endswith(".jsonl") and f != "training_data.jsonl"]
        uploaded = [f for f in all_files if f.endswith(".uploaded")]
        total_size = sum(
            os.path.getsize(os.path.join(self.storage_path, f))
            for f in all_files
            if os.path.isfile(os.path.join(self.storage_path, f))
        )
        return {
            "total_collected": self.collected_count,
            "pending_upload": len(pending),
            "uploaded": len(uploaded),
            "files": len(all_files),
            "storage_mb": round(total_size / 1024 / 1024, 1),
            "limit_mb": self.config.storage_limit_mb,
        }
