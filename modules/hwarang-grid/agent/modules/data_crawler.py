"""모듈 1: 데이터 크롤링 에이전트

한국 뉴스/법령/코드를 자동 수집 → 마스터에 전달.
지속 학습(CL)의 데이터 공급원.

크롤링 소스:
  - 법제처 API (법령 개정)
  - RSS 뉴스 피드 (기술/IT/AI)
  - GitHub 트렌딩 (코드)
  - Stack Overflow (한국어 Q&A)

보상: 수집 건당 0.5 HWR, 품질 검증 후 보너스
"""

import json, os, time, logging, hashlib, re
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class _TextExtractor(HTMLParser):
    """HTML에서 텍스트만 추출."""
    def __init__(self):
        super().__init__()
        self.result = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.result.append(text)

    def get_text(self):
        return " ".join(self.result)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_text()


def _fetch_url(url: str, timeout: int = 10) -> str | None:
    """URL에서 콘텐츠를 가져옴."""
    try:
        req = Request(url, headers={
            "User-Agent": "HwarangBot/1.0 (https://hwarang.ai; AI research)",
        })
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        logger.debug(f"URL 가져오기 실패: {url} - {e}")
        return None


class DataCrawlerModule:
    def __init__(self, config):
        self.config = config
        self.collected_count = 0
        self.storage_path = os.path.expanduser("~/.hwarang/crawled_data")
        os.makedirs(self.storage_path, exist_ok=True)
        self._seen_hashes: set[str] = set()
        self._load_seen_hashes()

    def _load_seen_hashes(self):
        """중복 방지를 위한 기존 해시 로드."""
        hash_file = os.path.join(self.storage_path, ".seen_hashes")
        if os.path.exists(hash_file):
            with open(hash_file) as f:
                self._seen_hashes = set(f.read().strip().split("\n"))

    def _save_seen_hashes(self):
        hash_file = os.path.join(self.storage_path, ".seen_hashes")
        # 최근 10000개만 유지
        recent = list(self._seen_hashes)[-10000:]
        with open(hash_file, "w") as f:
            f.write("\n".join(recent))

    def _is_new(self, text: str) -> bool:
        """중복 체크."""
        h = hashlib.md5(text.encode()).hexdigest()
        if h in self._seen_hashes:
            return False
        self._seen_hashes.add(h)
        return True

    def run_cycle(self) -> dict:
        """한 사이클 크롤링."""
        results = {"sources": {}, "total": 0}
        max_items = getattr(self.config, "max_items_per_run", 20)

        for source in self.config.sources:
            try:
                if source == "law":
                    items = self._crawl_law(max_items)
                elif source == "news":
                    items = self._crawl_news(max_items)
                elif source == "code":
                    items = self._crawl_code(max_items)
                elif source == "stackoverflow":
                    items = self._crawl_stackoverflow(max_items)
                else:
                    items = []

                results["sources"][source] = len(items)
                results["total"] += len(items)

                if items:
                    self._save_items(source, items)

            except Exception as e:
                logger.warning(f"크롤링 실패 [{source}]: {e}")

        self.collected_count += results["total"]
        self._save_seen_hashes()
        return results

    # ════════════════════════════════════════════════════════════
    # 법령 크롤링
    # ════════════════════════════════════════════════════════════

    def _crawl_law(self, max_items: int = 20) -> list[dict]:
        """법제처 법령 업데이트."""
        api_key = os.environ.get("LAW_GO_KR_API_KEY", "")
        if not api_key:
            logger.debug("LAW_GO_KR_API_KEY 없음 → 법령 크롤링 스킵")
            return []

        try:
            url = (
                f"http://www.law.go.kr/DRF/lawSearch.do"
                f"?OC={api_key}&target=law&type=JSON&query=개정&display={max_items}"
            )
            content = _fetch_url(url)
            if not content:
                return []

            data = json.loads(content)
            laws = data.get("LawSearch", {}).get("law", [])
            items = []
            for law in laws[:max_items]:
                title = law.get("법령명한글", "")
                if not title or not self._is_new(title):
                    continue
                items.append({
                    "type": "law",
                    "title": title,
                    "date": law.get("공포일자", ""),
                    "law_id": law.get("법령일련번호", ""),
                    "summary": f"{title} (개정일: {law.get('공포일자', '')})",
                })
            return items
        except Exception as e:
            logger.warning(f"법령 크롤링 에러: {e}")
            return []

    # ════════════════════════════════════════════════════════════
    # 뉴스 크롤링 (RSS 피드)
    # ════════════════════════════════════════════════════════════

    def _crawl_news(self, max_items: int = 20) -> list[dict]:
        """기술/AI 뉴스를 RSS 피드에서 수집."""
        rss_feeds = [
            # 한국 IT 뉴스
            ("https://feeds.feedburner.com/blogspot/hsDo", "구글 한국 블로그"),
            ("https://zdnet.co.kr/rss/all_news.xml", "ZDNet Korea"),
            ("https://www.aitimes.com/rss/allArticle.xml", "AI 타임스"),
            ("https://www.bloter.net/feed", "블로터"),
            # 글로벌 기술 뉴스
            ("https://hnrss.org/newest?q=AI+LLM&count=10", "Hacker News AI"),
            ("https://arxiv.org/rss/cs.CL", "arXiv NLP"),
        ]

        items = []
        for feed_url, source_name in rss_feeds:
            if len(items) >= max_items:
                break
            try:
                feed_items = self._parse_rss(feed_url, source_name)
                items.extend(feed_items)
            except Exception as e:
                logger.debug(f"RSS 피드 실패 [{source_name}]: {e}")

        return items[:max_items]

    def _parse_rss(self, url: str, source_name: str) -> list[dict]:
        """RSS XML을 파싱하여 뉴스 항목 추출."""
        content = _fetch_url(url, timeout=15)
        if not content:
            return []

        items = []
        # 간단한 XML 파싱 (외부 라이브러리 없이)
        # <item> 또는 <entry> 태그 찾기
        item_pattern = re.compile(
            r'<(?:item|entry)>(.*?)</(?:item|entry)>',
            re.DOTALL
        )
        title_pattern = re.compile(r'<title[^>]*>(.*?)</title>', re.DOTALL)
        desc_pattern = re.compile(
            r'<(?:description|summary|content)[^>]*>(.*?)</(?:description|summary|content)>',
            re.DOTALL
        )
        link_pattern = re.compile(r'<link[^>]*>([^<]*)</link>|<link[^>]*href="([^"]*)"', re.DOTALL)
        date_pattern = re.compile(r'<(?:pubDate|published|updated)>(.*?)</(?:pubDate|published|updated)>', re.DOTALL)

        for match in item_pattern.finditer(content):
            block = match.group(1)

            title_m = title_pattern.search(block)
            title = _html_to_text(title_m.group(1)).strip() if title_m else ""

            if not title or len(title) < 5 or not self._is_new(title):
                continue

            desc_m = desc_pattern.search(block)
            description = ""
            if desc_m:
                raw_desc = desc_m.group(1).strip()
                if raw_desc.startswith("<![CDATA["):
                    raw_desc = raw_desc[9:]
                if raw_desc.endswith("]]>"):
                    raw_desc = raw_desc[:-3]
                description = _html_to_text(raw_desc)[:500]

            link_m = link_pattern.search(block)
            link = ""
            if link_m:
                link = link_m.group(1) or link_m.group(2) or ""

            date_m = date_pattern.search(block)
            pub_date = date_m.group(1).strip() if date_m else ""

            items.append({
                "type": "news",
                "title": title,
                "description": description,
                "link": link.strip(),
                "date": pub_date,
                "source": source_name,
                "summary": f"{title}. {description[:200]}",
            })

        return items

    # ════════════════════════════════════════════════════════════
    # 코드 크롤링 (GitHub)
    # ════════════════════════════════════════════════════════════

    def _crawl_code(self, max_items: int = 20) -> list[dict]:
        """GitHub 트렌딩 저장소 크롤링."""
        items = []

        # GitHub 트렌딩 페이지 (API 키 불필요)
        for lang in ["python", "typescript", "rust", "go"]:
            if len(items) >= max_items:
                break
            try:
                url = f"https://github.com/trending/{lang}?since=daily"
                html = _fetch_url(url, timeout=15)
                if not html:
                    continue

                repos = self._parse_github_trending(html, lang)
                items.extend(repos)
            except Exception as e:
                logger.debug(f"GitHub 트렌딩 실패 [{lang}]: {e}")

        # GitHub API (키 있으면 더 많이)
        gh_token = os.environ.get("GITHUB_TOKEN", "")
        if gh_token and len(items) < max_items:
            try:
                api_items = self._crawl_github_api(gh_token, max_items - len(items))
                items.extend(api_items)
            except Exception as e:
                logger.debug(f"GitHub API 실패: {e}")

        return items[:max_items]

    def _parse_github_trending(self, html: str, language: str) -> list[dict]:
        """GitHub 트렌딩 HTML에서 저장소 정보 추출."""
        items = []

        # 저장소 이름 추출: /user/repo
        repo_pattern = re.compile(r'href="/([^/]+/[^/]+)"[^>]*class="[^"]*"[^>]*>\s*\n?\s*([^<]+)', re.MULTILINE)
        # 설명 추출
        desc_pattern = re.compile(r'<p class="col-9[^"]*">\s*(.*?)\s*</p>', re.DOTALL)
        # 스타 수
        star_pattern = re.compile(r'stargazers[^>]*>\s*\n?\s*([\d,]+)', re.MULTILINE)

        # Article 블록 기반 추출
        article_pattern = re.compile(r'<article[^>]*>(.*?)</article>', re.DOTALL)

        for article in article_pattern.finditer(html):
            block = article.group(1)

            # 저장소 URL
            href_m = re.search(r'href="/([^"]+)"', block)
            if not href_m:
                continue
            repo_path = href_m.group(1).strip()
            if repo_path.count("/") != 1:
                continue

            if not self._is_new(repo_path):
                continue

            # 설명
            desc_m = re.search(r'<p[^>]*>\s*(.*?)\s*</p>', block, re.DOTALL)
            description = _html_to_text(desc_m.group(1)).strip() if desc_m else ""

            # 스타
            star_m = re.search(r'([\d,]+)\s*$', block)

            items.append({
                "type": "code",
                "title": repo_path,
                "description": description[:300],
                "language": language,
                "url": f"https://github.com/{repo_path}",
                "summary": f"GitHub 트렌딩 [{language}]: {repo_path} - {description[:200]}",
            })

            if len(items) >= 5:
                break

        return items

    def _crawl_github_api(self, token: str, max_items: int) -> list[dict]:
        """GitHub API로 최근 인기 저장소 검색."""
        from datetime import timedelta
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        url = (
            f"https://api.github.com/search/repositories"
            f"?q=language:python+created:>{week_ago}&sort=stars&order=desc&per_page={max_items}"
        )

        try:
            req = Request(url, headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "HwarangBot/1.0",
            })
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            items = []
            for repo in data.get("items", [])[:max_items]:
                name = repo.get("full_name", "")
                if not self._is_new(name):
                    continue
                items.append({
                    "type": "code",
                    "title": name,
                    "description": (repo.get("description") or "")[:300],
                    "language": repo.get("language", ""),
                    "url": repo.get("html_url", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "summary": f"GitHub: {name} - {repo.get('description', '')[:200]}",
                })
            return items
        except Exception:
            return []

    # ════════════════════════════════════════════════════════════
    # Stack Overflow 크롤링
    # ════════════════════════════════════════════════════════════

    def _crawl_stackoverflow(self, max_items: int = 20) -> list[dict]:
        """Stack Overflow 한국어/인기 질문 수집."""
        items = []

        # Stack Overflow API (키 불필요, rate limit 있음)
        tags = ["python", "javascript", "react", "typescript", "docker"]

        for tag in tags:
            if len(items) >= max_items:
                break
            try:
                url = (
                    f"https://api.stackexchange.com/2.3/questions"
                    f"?order=desc&sort=activity&tagged={tag}"
                    f"&site=stackoverflow&pagesize=5&filter=withbody"
                )
                content = _fetch_url(url, timeout=10)
                if not content:
                    continue

                data = json.loads(content)
                for q in data.get("items", []):
                    title = q.get("title", "")
                    if not title or not self._is_new(title):
                        continue

                    body = _html_to_text(q.get("body", ""))[:500]

                    items.append({
                        "type": "stackoverflow",
                        "title": title,
                        "description": body,
                        "tags": q.get("tags", []),
                        "url": q.get("link", ""),
                        "score": q.get("score", 0),
                        "summary": f"Q: {title}\n{body[:300]}",
                    })
            except Exception as e:
                logger.debug(f"StackOverflow 실패 [{tag}]: {e}")

        return items[:max_items]

    # ════════════════════════════════════════════════════════════
    # 저장 / 업로드 / 변환
    # ════════════════════════════════════════════════════════════

    def _save_items(self, source: str, items: list):
        """수집 데이터 로컬 저장."""
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        path = os.path.join(self.storage_path, f"{source}_{date_str}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        logger.info(f"저장: {source} {len(items)}건 → {path}")

    def upload_to_master(self, master_url: str, agent_id: str) -> dict:
        """수집 데이터를 마스터 서버에 업로드."""
        uploaded = 0
        failed = 0

        try:
            import httpx
            client = httpx.Client(timeout=60)

            for filename in sorted(os.listdir(self.storage_path)):
                filepath = os.path.join(self.storage_path, filename)
                if filename.endswith(".uploaded") or not filename.endswith(".jsonl"):
                    continue
                if filename == "training_data.jsonl":
                    continue

                try:
                    with open(filepath, "rb") as f:
                        response = client.post(
                            f"{master_url}/grid/data/upload",
                            data={
                                "agent_id": agent_id,
                                "source": filename.split("_")[0],
                            },
                            files={"data_file": (filename, f)},
                        )
                    if response.status_code == 200:
                        os.rename(filepath, filepath + ".uploaded")
                        uploaded += 1
                        result = response.json()
                        reward = result.get("reward", 0)
                        if reward > 0:
                            logger.info(f"📤 업로드: {filename} → +{reward} HWR")
                    else:
                        failed += 1
                except Exception as e:
                    logger.warning(f"업로드 실패 [{filename}]: {e}")
                    failed += 1

            client.close()
        except ImportError:
            return {"error": "httpx 필요"}

        return {"uploaded": uploaded, "failed": failed}

    def convert_to_training_data(self) -> str | None:
        """수집 데이터를 SFT 학습 형식(JSONL)으로 변환."""
        output_path = os.path.join(self.storage_path, "training_data.jsonl")
        count = 0

        system = "당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다."

        with open(output_path, "w", encoding="utf-8") as fout:
            for filename in sorted(os.listdir(self.storage_path)):
                if not filename.endswith(".jsonl") or filename == "training_data.jsonl":
                    continue
                filepath = os.path.join(self.storage_path, filename)
                source = filename.split("_")[0]

                try:
                    with open(filepath, encoding="utf-8") as fin:
                        for line in fin:
                            item = json.loads(line.strip())
                            qa = self._to_qa_pair(source, item, system)
                            if qa:
                                fout.write(json.dumps(qa, ensure_ascii=False) + "\n")
                                count += 1
                except Exception:
                    continue

        if count > 0:
            logger.info(f"학습 데이터 변환: {count}건 → {output_path}")
            return output_path
        return None

    def _to_qa_pair(self, source: str, item: dict, system: str) -> dict | None:
        """원본 데이터를 Q&A 학습 형식으로 변환."""
        title = item.get("title", "")
        desc = item.get("description", "") or item.get("summary", "")
        if not title or len(title) < 5:
            return None

        if source == "law":
            return {"messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"'{title}' 법령에 대해 쉽게 설명해줘"},
                {"role": "assistant", "content": f"'{title}' 법령에 대해 설명드리겠습니다.\n\n{desc}"},
            ]}
        elif source == "news":
            return {"messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"다음 뉴스를 요약해줘: {title}"},
                {"role": "assistant", "content": f"'{title}' 뉴스 요약입니다.\n\n{desc}"},
            ]}
        elif source == "code":
            lang = item.get("language", "")
            return {"messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"GitHub의 {title} 프로젝트에 대해 설명해줘"},
                {"role": "assistant", "content": f"{title}은(는) {lang} 프로젝트입니다.\n\n{desc}"},
            ]}
        elif source == "stackoverflow":
            tags_str = ", ".join(item.get("tags", []))
            return {"messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": title},
                {"role": "assistant", "content": f"관련 기술: {tags_str}\n\n{desc}"},
            ]}
        return None

    def get_stats(self) -> dict:
        """크롤링 통계."""
        all_files = [f for f in os.listdir(self.storage_path)
                     if not f.startswith(".") and os.path.isfile(os.path.join(self.storage_path, f))]
        pending = [f for f in all_files if f.endswith(".jsonl") and f != "training_data.jsonl"]
        uploaded = [f for f in all_files if f.endswith(".uploaded")]
        total_size = sum(
            os.path.getsize(os.path.join(self.storage_path, f))
            for f in all_files
        )
        return {
            "total_collected": self.collected_count,
            "pending_upload": len(pending),
            "uploaded": len(uploaded),
            "files": len(all_files),
            "storage_mb": round(total_size / 1024 / 1024, 1),
            "limit_mb": getattr(self.config, "storage_limit_mb", 500),
        }
