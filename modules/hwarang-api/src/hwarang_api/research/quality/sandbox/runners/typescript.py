"""TypeScript 러너 스펙 — tsx 가 자동 컴파일 + 실행 처리.

tsx (https://github.com/privatenumber/tsx) 는 esbuild 기반으로 TS 를
즉시 변환해 node 로 실행한다. 별도 build 단계가 필요 없다.
"""

from __future__ import annotations

SPEC = {
    "language": "typescript",
    "extension": ".ts",
    "image": "hwarang/node-runner:latest",
    "docker_cmd": ["npx", "tsx", "/code/main.ts"],
    "host_cmd": ["npx", "tsx"],
    "needs_compile": False,  # tsx 가 내부에서 처리
}

__all__ = ["SPEC"]
