"""자체개선 제안 감사 로그 (append-only JSONL).

기본 위치: /var/log/hwarang/self_modify_audit.log
fallback: <project_root>/logs/self_modify_audit.log
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


PRIMARY_LOG_PATH = Path("/var/log/hwarang/self_modify_audit.log")


def _resolve_log_path() -> Path:
    """기본 경로가 쓰기 가능하면 사용, 아니면 프로젝트 루트의 logs/ 로 fallback."""
    try:
        PRIMARY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        # 쓰기 권한 테스트
        with open(PRIMARY_LOG_PATH, "a", encoding="utf-8"):
            pass
        return PRIMARY_LOG_PATH
    except Exception:
        # fallback: cwd 또는 모듈 위치 기반
        fallback_root = Path.cwd() / "logs"
        try:
            fallback_root.mkdir(parents=True, exist_ok=True)
            return fallback_root / "self_modify_audit.log"
        except Exception as e:
            logger.error(f"감사 로그 경로 생성 실패: {e}")
            # 최후 수단: /tmp
            return Path("/tmp/self_modify_audit.log")


_LOG_PATH: Optional[Path] = None


def _get_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        _LOG_PATH = _resolve_log_path()
    return _LOG_PATH


def log_proposal(entry: dict[str, Any]) -> None:
    """제안 1건을 append-only JSONL 로 기록.

    Args:
        entry: 최소 다음 키 포함 권장:
            file_path, risk_level, validation_passed, pr_url_if_any, blocked_reasons
    """
    payload = dict(entry)
    payload.setdefault("timestamp", time.time())
    payload.setdefault("timestamp_iso", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    line = json.dumps(payload, ensure_ascii=False)
    path = _get_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        logger.error(f"감사 로그 기록 실패 ({path}): {e}")


def recent_proposals(n: int = 20) -> list[dict[str, Any]]:
    """최근 n 건의 제안 로그를 반환."""
    path = _get_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last = lines[-n:] if n > 0 else lines
        out = []
        for line in last:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    except Exception as e:
        logger.error(f"감사 로그 읽기 실패: {e}")
        return []
