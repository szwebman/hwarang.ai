"""Go 러너 스펙 — go run 으로 실행."""

from __future__ import annotations

SPEC = {
    "language": "go",
    "extension": ".go",
    "image": "hwarang/go-runner:latest",
    "docker_cmd": ["go", "run", "/code/main.go"],
    "host_cmd": None,  # firejail 미지원
    "needs_compile": False,  # go run 이 내부 처리
}

__all__ = ["SPEC"]
