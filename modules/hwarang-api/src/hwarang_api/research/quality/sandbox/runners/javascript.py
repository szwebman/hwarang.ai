"""JavaScript 러너 스펙."""

from __future__ import annotations

SPEC = {
    "language": "javascript",
    "extension": ".js",
    "image": "hwarang/node-runner:latest",
    "docker_cmd": ["node", "/code/main.js"],
    "host_cmd": ["node"],
    "needs_compile": False,
}

__all__ = ["SPEC"]
