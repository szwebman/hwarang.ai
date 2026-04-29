"""Python 러너 스펙."""

from __future__ import annotations

SPEC = {
    "language": "python",
    "extension": ".py",
    "image": "hwarang/python-runner:latest",
    "docker_cmd": ["python3", "/code/main.py"],
    "host_cmd": ["python3"],
    "needs_compile": False,
}

__all__ = ["SPEC"]
