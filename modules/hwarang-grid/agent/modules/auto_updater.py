"""모듈 9: 자동 업데이트 에이전트

에이전트 소프트웨어 자동 업데이트.
마스터에서 최신 버전 체크 → 다운로드 → 적용.
"""

import json, os, time, hashlib, logging

logger = logging.getLogger(__name__)

CURRENT_VERSION = "0.1.0"


class AutoUpdaterModule:
    def __init__(self, config):
        self.config = config
        self.current_version = CURRENT_VERSION

    def check_update(self, master_url: str) -> dict:
        """마스터에서 최신 버전 확인."""
        try:
            try:
                from ._http_util import make_request  # type: ignore
            except Exception:
                from modules._http_util import make_request  # type: ignore
            resp = make_request(f"{master_url}/api/grid/agent/version", timeout=10)
            data = json.loads(resp.read())
            latest = data.get("version", CURRENT_VERSION)
            channel = data.get("channel", "stable")

            if self.config.channel != channel:
                return {"update_available": False, "reason": f"채널 불일치 ({self.config.channel} != {channel})"}

            needs_update = latest != self.current_version
            return {
                "update_available": needs_update,
                "current": self.current_version,
                "latest": latest,
                "channel": channel,
                "download_url": data.get("download_url", ""),
                "changelog": data.get("changelog", ""),
            }
        except Exception as e:
            return {"update_available": False, "error": str(e)}

    def apply_update(self, download_url: str) -> dict:
        """업데이트 다운로드 + 적용."""
        try:
            try:
                from ._http_util import make_request  # type: ignore
            except Exception:
                from modules._http_util import make_request  # type: ignore
            update_dir = os.path.expanduser("~/.hwarang/updates")
            os.makedirs(update_dir, exist_ok=True)

            filepath = os.path.join(update_dir, "agent_update.tar.gz")
            resp = make_request(download_url, timeout=120)
            with open(filepath, "wb") as fh:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)

            file_hash = hashlib.sha256(open(filepath, "rb").read()).hexdigest()
            logger.info(f"업데이트 다운로드: {filepath} (hash: {file_hash[:16]})")

            # 실제 적용은 별도 스크립트로 (에이전트 재시작 필요)
            if self.config.auto_restart:
                logger.info("자동 재시작...")
                os.system(f"tar xzf {filepath} -C ~/.hwarang/agent/ && systemctl restart hwarang-agent")
            else:
                logger.info("수동 재시작 필요: systemctl restart hwarang-agent")

            return {"status": "downloaded", "path": filepath, "hash": file_hash[:16]}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
