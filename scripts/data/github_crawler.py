#!/usr/bin/env python3
"""
한국 GitHub 저장소 크롤러.

수집 대상:
- 한국 IT 기업의 organization 저장소
- 한국어 README/주석을 가진 인기 저장소
- 한국 OSS 커뮤니티 저장소

사용법:
    export GITHUB_TOKEN="ghp_..."
    python scripts/data/github_crawler.py --output data/raw/github

필요 패키지:
    pip install PyGithub aiohttp aiofiles tqdm
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import AsyncIterator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# 한국 organization 목록
# ============================================================
KOREAN_ORGANIZATIONS = [
    # 대기업
    "naver", "navercorp", "naver-fin", "naver-payments",
    "kakao", "kakaopay", "kakao-tech", "kakaobrain",
    "linecorp", "line",
    "samsung", "samsung-research",
    "lge-onest", "lg-cns",
    "hyundaiautoever",
    "skplanet", "sk-shieldus",
    "nhnent", "nhn-cloud", "navercloudplatform",

    # 유니콘/스타트업
    "woowabros",        # 우아한형제들
    "toss-im",          # 토스
    "tossbank",
    "daangn",           # 당근
    "musinsa",          # 무신사
    "coupang",          # 쿠팡
    "29cm",
    "wadiz",
    "kreamio",          # 크림
    "GabiaCorp",        # 가비아

    # 게임
    "ncsoft",
    "krafton-aim",
    "smilegate",
    "pearlabyss",
    "nexon-platform",

    # 핀테크/금융
    "kakaobank",
    "viva-republica",   # 토스 본사

    # OSS/커뮤니티
    "PyConKR",
    "JS-DevKR",
    "kr-developers",
    "FrontEnd-In-KR",

    # 교육
    "modulabs",         # 모두의연구소
    "bjpublic",
    "rust-kr",
    "golang-kr",
]

# 한국어 코드 검색 쿼리
SEARCH_QUERIES = [
    "language:python in:readme 한국",
    "language:javascript in:readme 한국",
    "language:typescript in:readme 한글",
    "language:java in:readme 한국",
    "language:go in:readme 한국",
    "language:python stars:>50 size:>10 한글",
    "korean nlp language:python stars:>20",
    "한국어 자연어처리 stars:>10",
    "kakao api language:python stars:>5",
    "naver api language:javascript stars:>5",
]

# 수집할 코드 파일 확장자
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".kt", ".kts",
    ".go", ".rs", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp",
    ".cs", ".swift", ".scala",
    ".lua", ".r", ".sql",
    ".html", ".css", ".scss", ".vue", ".svelte",
    ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".toml",
    ".md",  # README 등 문서
}

# 무시할 디렉토리/파일
IGNORE_PATTERNS = {
    "node_modules", ".git", "venv", "env", "__pycache__",
    "dist", "build", ".next", "target", "out",
    "vendor", ".idea", ".vscode",
    "test", "tests", "__tests__",  # 일단은 테스트 코드 제외
    "package-lock.json", "yarn.lock", "Pipfile.lock",
    ".DS_Store",
}

# 파일 크기 제한
MIN_FILE_SIZE = 100        # 100 bytes 미만 제외
MAX_FILE_SIZE = 100_000    # 100KB 이상 제외 (자동생성 파일 등)


@dataclass
class CrawledFile:
    """크롤링된 파일 메타데이터."""
    repo: str
    path: str
    language: str
    content: str
    size: int
    has_korean: bool
    korean_ratio: float
    url: str
    stars: int
    file_hash: str


def has_korean_text(text: str, min_chars: int = 10) -> bool:
    """텍스트에 한글이 포함되었는지 확인."""
    korean_chars = sum(1 for c in text if "\uAC00" <= c <= "\uD7A3")
    return korean_chars >= min_chars


def korean_ratio(text: str) -> float:
    """한글 비율 계산 (0.0 ~ 1.0)."""
    if not text:
        return 0.0
    korean = sum(1 for c in text if "\uAC00" <= c <= "\uD7A3")
    return korean / len(text)


def detect_language(filename: str) -> str:
    """파일명에서 언어 감지."""
    ext_to_lang = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".jsx": "javascript",
        ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
        ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
        ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
        ".cs": "csharp", ".swift": "swift", ".scala": "scala",
        ".html": "html", ".css": "css", ".scss": "scss",
        ".vue": "vue", ".svelte": "svelte",
        ".sh": "shell", ".bash": "shell", ".zsh": "shell",
        ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
        ".md": "markdown",
        ".sql": "sql", ".lua": "lua", ".r": "r",
    }
    for ext, lang in ext_to_lang.items():
        if filename.endswith(ext):
            return lang
    return "unknown"


def should_skip_file(path: str) -> bool:
    """이 파일을 건너뛸지 결정."""
    parts = path.split("/")
    return any(p in IGNORE_PATTERNS for p in parts)


class GitHubCrawler:
    """한국 GitHub 저장소 크롤러."""

    def __init__(self, token: str, output_dir: Path, max_repos: int = 5000):
        self.token = token
        self.output_dir = output_dir
        self.max_repos = max_repos
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 진행 상황 저장 파일
        self.state_file = output_dir / "crawler_state.json"
        self.state = self._load_state()

        # 통계
        self.stats = {
            "repos_processed": 0,
            "files_collected": 0,
            "korean_files": 0,
            "total_bytes": 0,
        }

    def _load_state(self) -> dict:
        """이전 진행 상태 불러오기."""
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"processed_repos": [], "seen_hashes": []}

    def _save_state(self):
        """진행 상태 저장."""
        self.state_file.write_text(json.dumps(self.state, indent=2))

    def crawl(self):
        """전체 크롤링 실행."""
        try:
            from github import Github, GithubException
        except ImportError:
            logger.error("PyGithub이 필요합니다: pip install PyGithub")
            return

        gh = Github(self.token)

        # 1. 한국 organization 크롤링
        logger.info(f"한국 organization 크롤링 시작 ({len(KOREAN_ORGANIZATIONS)}개)")
        for org_name in KOREAN_ORGANIZATIONS:
            try:
                self._crawl_organization(gh, org_name)
            except GithubException as e:
                logger.warning(f"  {org_name}: {e}")
                continue
            except Exception as e:
                logger.error(f"  {org_name}: {e}")
                continue

            self._save_state()
            if self.stats["repos_processed"] >= self.max_repos:
                break

        # 2. 검색 쿼리 크롤링
        if self.stats["repos_processed"] < self.max_repos:
            logger.info("검색 쿼리 크롤링 시작")
            for query in SEARCH_QUERIES:
                try:
                    self._crawl_search(gh, query)
                except Exception as e:
                    logger.error(f"  query '{query}': {e}")
                    continue

                self._save_state()
                if self.stats["repos_processed"] >= self.max_repos:
                    break

        # 최종 통계
        self._print_stats()

    def _crawl_organization(self, gh, org_name: str):
        """한 organization의 모든 저장소 크롤링."""
        logger.info(f"[{org_name}] 시작")
        try:
            org = gh.get_organization(org_name)
            repos = org.get_repos(type="public")
        except Exception as e:
            logger.warning(f"  organization 접근 실패: {e}")
            return

        for repo in repos:
            if repo.full_name in self.state["processed_repos"]:
                continue
            if repo.stargazers_count < 5:  # 별점 5 미만 제외
                continue
            if repo.archived:  # 아카이브된 저장소 제외
                continue
            try:
                self._crawl_repo(repo)
                self.state["processed_repos"].append(repo.full_name)
            except Exception as e:
                logger.warning(f"  {repo.full_name}: {e}")
                continue

            if self.stats["repos_processed"] >= self.max_repos:
                break

    def _crawl_search(self, gh, query: str):
        """검색 쿼리로 저장소 찾기."""
        logger.info(f"[검색] {query}")
        try:
            results = gh.search_repositories(query=query, sort="stars", order="desc")
        except Exception as e:
            logger.warning(f"  검색 실패: {e}")
            return

        count = 0
        for repo in results:
            if count >= 100:  # 쿼리당 최대 100개
                break
            if repo.full_name in self.state["processed_repos"]:
                continue
            if repo.archived:
                continue
            try:
                self._crawl_repo(repo)
                self.state["processed_repos"].append(repo.full_name)
                count += 1
            except Exception as e:
                logger.warning(f"  {repo.full_name}: {e}")
                continue

            if self.stats["repos_processed"] >= self.max_repos:
                break

    def _crawl_repo(self, repo):
        """단일 저장소의 파일 수집."""
        repo_name = repo.full_name.replace("/", "_")
        repo_dir = self.output_dir / repo_name
        repo_dir.mkdir(parents=True, exist_ok=True)

        # 메타데이터 저장
        metadata = {
            "name": repo.full_name,
            "stars": repo.stargazers_count,
            "language": repo.language,
            "description": repo.description,
            "url": repo.html_url,
        }
        (repo_dir / "_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2)
        )

        # 파일 크롤링 (재귀)
        files_collected = 0
        try:
            contents = repo.get_contents("")
            queue = list(contents)
            while queue and files_collected < 200:  # 저장소당 최대 200개 파일
                content = queue.pop(0)
                if content.type == "dir":
                    if not should_skip_file(content.path):
                        try:
                            queue.extend(repo.get_contents(content.path))
                        except Exception:
                            pass
                else:
                    if self._process_file(repo, content, repo_dir):
                        files_collected += 1
        except Exception as e:
            logger.debug(f"  파일 순회 중 오류: {e}")

        self.stats["repos_processed"] += 1
        if self.stats["repos_processed"] % 10 == 0:
            logger.info(
                f"  진행: {self.stats['repos_processed']}개 저장소, "
                f"{self.stats['files_collected']}개 파일, "
                f"{self.stats['total_bytes'] / 1e6:.1f}MB"
            )

    def _process_file(self, repo, content, repo_dir: Path) -> bool:
        """단일 파일 처리. 수집되면 True 반환."""
        # 1. 파일 필터링
        filename = content.name
        if should_skip_file(content.path):
            return False

        ext_match = any(filename.endswith(ext) for ext in CODE_EXTENSIONS)
        if not ext_match:
            return False

        if content.size < MIN_FILE_SIZE or content.size > MAX_FILE_SIZE:
            return False

        # 2. 내용 다운로드
        try:
            file_content = content.decoded_content.decode("utf-8", errors="ignore")
        except Exception:
            return False

        # 3. 한국어 포함 여부 (마크다운/주석)
        is_korean = has_korean_text(file_content)
        ratio = korean_ratio(file_content)

        # 한국어가 거의 없는 코드는 일부만 수집 (영어 코드도 필요함)
        if not is_korean and ratio < 0.01:
            # 10% 확률로만 수집
            import random
            if random.random() > 0.1:
                return False

        # 4. 중복 체크
        file_hash = hashlib.md5(file_content.encode()).hexdigest()
        if file_hash in self.state["seen_hashes"]:
            return False
        self.state["seen_hashes"].append(file_hash)

        # 5. 저장
        crawled = CrawledFile(
            repo=repo.full_name,
            path=content.path,
            language=detect_language(filename),
            content=file_content,
            size=content.size,
            has_korean=is_korean,
            korean_ratio=ratio,
            url=content.html_url,
            stars=repo.stargazers_count,
            file_hash=file_hash,
        )

        # JSONL로 저장 (한 줄에 하나의 파일)
        output_file = repo_dir / "files.jsonl"
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(crawled), ensure_ascii=False) + "\n")

        self.stats["files_collected"] += 1
        if is_korean:
            self.stats["korean_files"] += 1
        self.stats["total_bytes"] += content.size

        return True

    def _print_stats(self):
        logger.info("=" * 60)
        logger.info("크롤링 완료!")
        logger.info(f"  저장소: {self.stats['repos_processed']:,}개")
        logger.info(f"  파일: {self.stats['files_collected']:,}개")
        logger.info(f"  한국어 파일: {self.stats['korean_files']:,}개")
        logger.info(f"  총 용량: {self.stats['total_bytes'] / 1e9:.2f}GB")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="한국 GitHub 크롤러")
    parser.add_argument("--output", default="data/raw/github", help="출력 디렉토리")
    parser.add_argument("--max-repos", type=int, default=5000, help="최대 저장소 수")
    parser.add_argument("--token", default=None, help="GitHub Token (또는 GITHUB_TOKEN env)")
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error("GitHub Token이 필요합니다")
        logger.error("  export GITHUB_TOKEN='ghp_...'")
        logger.error("  또는 --token 옵션 사용")
        return

    crawler = GitHubCrawler(
        token=token,
        output_dir=Path(args.output),
        max_repos=args.max_repos,
    )
    crawler.crawl()


if __name__ == "__main__":
    main()
