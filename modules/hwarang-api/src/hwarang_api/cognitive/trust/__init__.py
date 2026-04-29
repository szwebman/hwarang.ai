"""화랑 통합 신뢰 시스템 (Unified Trust facade).

두 도메인의 평판 시스템 — Agent / Source — 을 단일 인터페이스로 조회하기 위한
얇은 facade. 저장은 각 도메인 모듈이 그대로 담당한다.

자세한 설명은 ``unified_trust`` 모듈 docstring 참조.
"""

from .unified_trust import TrustKind, UnifiedTrust

__all__ = ["TrustKind", "UnifiedTrust"]
