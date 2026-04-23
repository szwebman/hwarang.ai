"""Database models and session management.

지금은 가벼운 어댑터. hwarang-web의 Prisma 클라이언트를 Python에서 쓰려면
별도 프로세스로 호출하거나, prisma-client-py 를 직접 사용.

HLKM 모듈들이 `from hwarang_api.db import prisma` 를 임포트하므로,
여기서 단일 싱글톤을 제공.
"""

from __future__ import annotations

try:
    # prisma-client-py가 생성한 클라이언트
    from prisma import Prisma  # type: ignore

    prisma = Prisma()  # 애플리케이션 시작 시 `await prisma.connect()` 필요

    async def connect_db() -> None:
        if not prisma.is_connected():
            await prisma.connect()

    async def disconnect_db() -> None:
        if prisma.is_connected():
            await prisma.disconnect()

except ImportError:
    # prisma-client-py 미설치 환경(개발 초기)에서도 임포트는 되게
    class _PrismaStub:
        def __getattr__(self, name: str):
            raise RuntimeError(
                "prisma-client-py 가 설치되지 않았습니다. "
                "'pip install prisma' 후 `prisma generate --schema=../hwarang-web/prisma/schema.prisma` 실행하세요."
            )

        def is_connected(self) -> bool:
            return False

    prisma = _PrismaStub()  # type: ignore[assignment]

    async def connect_db() -> None:
        pass

    async def disconnect_db() -> None:
        pass


__all__ = ["prisma", "connect_db", "disconnect_db"]
