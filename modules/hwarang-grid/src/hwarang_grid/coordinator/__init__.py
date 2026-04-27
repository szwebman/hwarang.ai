"""HWARANG Grid Coordinator (마스터 측).

에이전트들이 참여할 HFL 라운드를 생성·관리·집계하는 오케스트레이션 계층.

주요 모듈:
    - round_manager: 라운드 CRUD + 참가자/투표/보상 집계
    - routes:        FastAPI 라우터 (에이전트가 호출하는 엔드포인트)
    - data_shard_prep: HLKM 팩트 → 도메인 SFT 샤드 변환

FastAPI 통합 예시 (hwarang-api main.py):
    from hwarang_grid.coordinator.routes import router as grid_router
    app.include_router(grid_router)
"""

from __future__ import annotations

__all__ = [
    "round_manager",
    "routes",
    "data_shard_prep",
]
