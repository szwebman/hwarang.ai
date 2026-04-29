"""Rust 러너 스펙 — rustc 컴파일 후 실행."""

from __future__ import annotations

SPEC = {
    "language": "rust",
    "extension": ".rs",
    "image": "hwarang/rust-runner:latest",
    # 컴파일 + 실행을 sh 로 묶음. /tmp 만 쓰기 가능 (read-only fs + tmpfs)
    "docker_cmd": [
        "sh",
        "-c",
        "rustc /code/main.rs -o /tmp/main && /tmp/main",
    ],
    "host_cmd": None,  # firejail 미지원
    "needs_compile": True,
}

__all__ = ["SPEC"]
