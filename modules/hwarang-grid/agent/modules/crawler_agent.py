"""분산 크롤 워커 — 마스터에서 작업 임대 후 URL fetch → 결과 제출.

마스터 API 와 통합되는 분산 크롤러로, 기존 `data_crawler.py`(로컬 RSS/HTML
스크래퍼)와 달리 마스터가 발행한 작업 큐에서 임대 받아 처리한다.

특징:
- 동시 N개 작업 (기본 3개, GPU/대역폭 따라 조정)
- 주기적 heartbeat 로 lease 유지 (3분 간격)
- 실패/콘텐츠 없음 시 자동 release
- HTML / RSS / PDF / JSON / text 파서 자동 분기
- robots.txt 존중 (도메인별 캐시)
- User-Agent: HwarangBot/1.0

API 엔드포인트 (마스터):
  POST /api/crawl/lease            → 작업 N개 임대
  POST /api/crawl/heartbeat/{id}   → lease 연장
  POST /api/crawl/submit/{id}      → 결과 제출
  POST /api/crawl/release/{id}     → 작업 반환 (실패/skip)
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from ._http_util import make_request

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# 설정
# ────────────────────────────────────────────────────────────────────────


@dataclass
class CrawlerConfig:
    """크롤러 워커 설정.

    domain_filter:
        도메인 전문 에이전트 한정용 (예: ["legal"], ["news"]).
        None / 빈 리스트면 모든 도메인 작업 수신.
    """

    master_url: str
    api_key: str
    agent_id: str
    domain_filter: Optional[list[str]] = None
    max_concurrent: int = 3
    poll_interval_seconds: int = 30
    user_agent: str = "HwarangBot/1.0 (+https://hwarang.ai/bot)"
    request_timeout_sec: int = 15
    respect_robots: bool = True
    heartbeat_interval_sec: int = 180  # lease 갱신 (3분)
    max_content_chars: int = 5000      # 본문 최대 크기

    def lease_url(self) -> str:
        return f"{self.master_url.rstrip('/')}/api/crawl/lease"

    def heartbeat_url(self, job_id: str) -> str:
        return f"{self.master_url.rstrip('/')}/api/crawl/heartbeat/{job_id}"

    def submit_url(self, job_id: str) -> str:
        return f"{self.master_url.rstrip('/')}/api/crawl/submit/{job_id}"

    def release_url(self, job_id: str) -> str:
        return f"{self.master_url.rstrip('/')}/api/crawl/release/{job_id}"


# ────────────────────────────────────────────────────────────────────────
# 크롤러 본체
# ────────────────────────────────────────────────────────────────────────


class CrawlerAgent:
    """단일 에이전트의 크롤 워커. agent_main 의 백그라운드 task 로 실행."""

    def __init__(self, cfg: CrawlerConfig):
        self.cfg = cfg
        self._stop = asyncio.Event()
        self._active_jobs: dict[str, asyncio.Task] = {}
        self._robots_cache: dict[str, Optional[RobotFileParser]] = {}

    # ── 라이프사이클 ──────────────────────────────────────────

    async def run(self) -> None:
        """메인 루프 — 동시 워커 N개를 spawn 하고 stop 이벤트 대기."""
        logger.info(
            "크롤러 워커 시작 (agent=%s, concurrent=%d, domain_filter=%s)",
            self.cfg.agent_id,
            self.cfg.max_concurrent,
            self.cfg.domain_filter,
        )

        workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self.cfg.max_concurrent)
        ]

        try:
            await self._stop.wait()
        finally:
            for w in workers:
                w.cancel()
            # 미완료 lease 들 release (best-effort)
            for job_id in list(self._active_jobs.keys()):
                try:
                    await self._release_job(job_id, "agent_shutdown")
                except Exception:
                    pass
            await asyncio.gather(*workers, return_exceptions=True)

    def stop(self) -> None:
        """외부에서 호출 — graceful 종료 신호."""
        self._stop.set()

    # ── 워커 루프 ─────────────────────────────────────────────

    async def _worker_loop(self, worker_id: int) -> None:
        """단일 워커 — 작업 1개씩 처리."""
        while not self._stop.is_set():
            try:
                jobs = await self._lease_jobs(max_jobs=1)
                if not jobs:
                    # 빈 큐 → 대기 (stop 이벤트도 polling)
                    try:
                        await asyncio.wait_for(
                            self._stop.wait(),
                            timeout=self.cfg.poll_interval_seconds,
                        )
                        return  # stop 신호 수신
                    except asyncio.TimeoutError:
                        continue

                for job in jobs:
                    job_id = job.get("id")
                    if not job_id:
                        continue
                    self._active_jobs[job_id] = asyncio.current_task()  # type: ignore[assignment]
                    try:
                        await self._process_job(job)
                    finally:
                        self._active_jobs.pop(job_id, None)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("워커 %d 오류: %s", worker_id, exc)
                # 백오프
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=10)
                    return
                except asyncio.TimeoutError:
                    continue

    # ── 마스터 API 호출 ───────────────────────────────────────

    async def _lease_jobs(self, max_jobs: int) -> list[dict]:
        """마스터에서 작업 N개 임대."""
        body = json.dumps({
            "agent_id": self.cfg.agent_id,
            "max_jobs": max_jobs,
            "domain_filter": self.cfg.domain_filter or [],
        }).encode("utf-8")

        try:
            data = await asyncio.to_thread(self._post_json, self.cfg.lease_url(), body, 10.0)
            if not data:
                return []
            return data.get("jobs", []) or []
        except Exception as exc:
            logger.warning("lease 실패: %s", exc)
            return []

    async def _submit_result(self, job_id: str, content: dict) -> None:
        payload = {
            "agent_id": self.cfg.agent_id,
            "title": content.get("title"),
            "content": content.get("content"),
            "publishedAt": content.get("publishedAt"),
            "contentHash": content.get("contentHash"),
        }
        body = json.dumps(payload).encode("utf-8")
        try:
            await asyncio.to_thread(
                self._post_json, self.cfg.submit_url(job_id), body, 10.0
            )
        except Exception as exc:
            logger.warning("submit 실패 %s: %s", job_id, exc)
            # 제출 실패 → release 시도
            await self._release_job(job_id, f"submit_failed: {str(exc)[:120]}")

    async def _release_job(self, job_id: str, reason: str) -> None:
        body = json.dumps({"reason": reason[:200]}).encode("utf-8")
        try:
            await asyncio.to_thread(
                self._post_json, self.cfg.release_url(job_id), body, 5.0
            )
        except Exception as exc:
            logger.debug("release 실패 (무시) %s: %s", job_id, exc)

    async def _send_heartbeat(self, job_id: str) -> None:
        try:
            await asyncio.to_thread(
                self._post_json, self.cfg.heartbeat_url(job_id), b"", 5.0
            )
        except Exception as exc:
            logger.debug("heartbeat 실패 %s: %s", job_id, exc)

    def _post_json(self, url: str, body: bytes, timeout: float) -> Optional[dict]:
        """make_request 동기 wrapper — 응답 JSON 파싱."""
        headers = {"Content-Type": "application/json"} if body else None
        resp = make_request(
            url,
            method="POST",
            data=body if body else None,
            timeout=timeout,
            headers=headers,
        )
        try:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
        finally:
            try:
                resp.close()
            except Exception:
                pass

    # ── 작업 처리 ─────────────────────────────────────────────

    async def _process_job(self, job: dict) -> None:
        """단일 작업: robots 확인 → fetch → 파싱 → 제출."""
        job_id = job["id"]
        url = job.get("url", "")
        if not url:
            await self._release_job(job_id, "missing_url")
            return

        # robots.txt 체크
        if self.cfg.respect_robots and not await self._is_allowed(url):
            logger.info("robots disallow: %s", url)
            await self._release_job(job_id, "robots_disallowed")
            return

        # heartbeat 백그라운드 task — 긴 fetch 동안 lease 만료 방지
        hb_task = asyncio.create_task(self._heartbeat_loop(job_id))
        try:
            content = await self._fetch_and_parse(url, job)
        except Exception as exc:
            logger.warning("작업 %s fetch 실패: %s", job_id, exc)
            hb_task.cancel()
            await self._release_job(job_id, f"fetch_error: {str(exc)[:120]}")
            return
        finally:
            hb_task.cancel()

        if not content or not content.get("content"):
            await self._release_job(job_id, "no_content")
            return

        await self._submit_result(job_id, content)

    async def _heartbeat_loop(self, job_id: str) -> None:
        """주기적으로 lease 연장."""
        try:
            while True:
                await asyncio.sleep(self.cfg.heartbeat_interval_sec)
                await self._send_heartbeat(job_id)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("heartbeat_loop 종료 %s: %s", job_id, exc)

    # ── HTTP fetch ────────────────────────────────────────────

    async def _fetch_and_parse(self, url: str, job: dict) -> Optional[dict]:
        """URL 가져와서 content-type / jobType 따라 파싱."""
        try:
            import httpx  # type: ignore
        except ImportError:
            logger.error("httpx 미설치 — 크롤러 불가")
            return None

        async with httpx.AsyncClient(
            timeout=self.cfg.request_timeout_sec,
            headers={"User-Agent": self.cfg.user_agent},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                logger.info("HTTP %d on %s", resp.status_code, url)
                return None

            ctype = (resp.headers.get("content-type") or "").lower()
            metadata = job.get("metadata", {}) or {}
            job_type = (job.get("jobType") or "").lower()

            # jobType 우선, 그다음 content-type
            if job_type in ("rss", "rss_item") or "rss" in ctype or "xml" in ctype:
                # RSS 아이템은 보통 content 가 metadata 에 이미 있음 — HTML 처리로 fallback
                if "html" in ctype:
                    return self._parse_html(resp.text, url, metadata)
                return self._parse_html(resp.text, url, metadata)
            if "text/html" in ctype or job_type == "html":
                return self._parse_html(resp.text, url, metadata)
            if "application/pdf" in ctype or job_type == "pdf":
                return self._parse_pdf(resp.content, url)
            if "json" in ctype or job_type == "json":
                return self._parse_json(resp.text, url, metadata)
            # 텍스트로 처리 (plain/text 등)
            text = resp.text or ""
            return {
                "title": metadata.get("title", ""),
                "content": text[: self.cfg.max_content_chars],
                "publishedAt": metadata.get("published"),
                "contentHash": hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest(),
            }

    # ── 파서들 ────────────────────────────────────────────────

    def _parse_html(self, html: str, url: str, metadata: dict) -> dict:
        """HTML → title + main content."""
        try:
            from bs4 import BeautifulSoup  # type: ignore

            soup = BeautifulSoup(html, "html.parser")

            # 제목 추출
            title = None
            og = soup.find("meta", property="og:title")
            if og and og.get("content"):
                title = og.get("content")
            if not title and soup.title and soup.title.string:
                title = soup.title.string

            # 본문 — article 또는 main 우선
            article = soup.find("article") or soup.find("main")
            if article:
                content = article.get_text(separator="\n", strip=True)
            else:
                # 광고/헤더/푸터 제거 후 전체 텍스트
                for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
                    tag.decompose()
                content = soup.get_text(separator="\n", strip=True)

            content = content[: self.cfg.max_content_chars]

            # 발행일
            pub = metadata.get("published")
            if not pub:
                meta_pub = soup.find("meta", property="article:published_time")
                if meta_pub and meta_pub.get("content"):
                    pub = meta_pub.get("content")

            return {
                "title": (title or metadata.get("title", "") or "").strip()[:300],
                "content": content,
                "publishedAt": pub,
                "contentHash": hashlib.sha256(
                    content.encode("utf-8", "ignore")
                ).hexdigest(),
            }
        except ImportError:
            # bs4 없음 — raw text fallback
            text = html[: self.cfg.max_content_chars]
            return {
                "title": metadata.get("title", ""),
                "content": text,
                "publishedAt": metadata.get("published"),
                "contentHash": hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest(),
            }
        except Exception as exc:
            logger.debug("HTML 파싱 실패 %s: %s", url, exc)
            text = html[: self.cfg.max_content_chars]
            return {
                "title": metadata.get("title", ""),
                "content": text,
                "publishedAt": metadata.get("published"),
                "contentHash": hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest(),
            }

    def _parse_pdf(self, data: bytes, url: str) -> Optional[dict]:
        """PDF → 텍스트 (pypdf 가용 시 첫 10페이지)."""
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            logger.debug("pypdf 미설치 — PDF skip: %s", url)
            return None

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = reader.pages[:10]
            text = "\n".join((p.extract_text() or "") for p in pages)
            text = text[: self.cfg.max_content_chars]
            title = ""
            try:
                if reader.metadata and reader.metadata.title:
                    title = str(reader.metadata.title)
            except Exception:
                pass
            return {
                "title": title[:300],
                "content": text,
                "publishedAt": None,
                "contentHash": hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest(),
            }
        except Exception as exc:
            logger.debug("PDF 파싱 실패 %s: %s", url, exc)
            return None

    def _parse_json(self, text: str, url: str, metadata: dict) -> dict:
        """JSON API → metadata 유지하면서 본문 그대로."""
        body = text[: self.cfg.max_content_chars]
        return {
            "title": metadata.get("title", ""),
            "content": body,
            "publishedAt": metadata.get("published"),
            "contentHash": hashlib.sha256(body.encode("utf-8", "ignore")).hexdigest(),
        }

    # ── robots.txt ────────────────────────────────────────────

    async def _is_allowed(self, url: str) -> bool:
        """robots.txt 체크 (도메인별 캐시). 못 가져오면 허용."""
        parsed = urlparse(url)
        domain = parsed.netloc
        if not domain:
            return True

        if domain not in self._robots_cache:
            rp = RobotFileParser()
            rp.set_url(f"{parsed.scheme}://{domain}/robots.txt")
            try:
                # blocking I/O → executor 로 회피
                await asyncio.get_event_loop().run_in_executor(None, rp.read)
                self._robots_cache[domain] = rp
            except Exception:
                # 못 가져오면 None 캐시 → 허용
                self._robots_cache[domain] = None
                return True

        rp = self._robots_cache.get(domain)
        if rp is None:
            return True
        try:
            return rp.can_fetch(self.cfg.user_agent, url)
        except Exception:
            return True


__all__ = ["CrawlerAgent", "CrawlerConfig"]
