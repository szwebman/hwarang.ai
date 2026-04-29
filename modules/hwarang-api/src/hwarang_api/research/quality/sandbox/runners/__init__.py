"""언어별 러너 보조 헬퍼.

실제 실행은 ``docker_runner`` / ``firejail_runner`` 가 담당.
이 모듈들은 인터프리터 명령, 파일 확장자, 추가 컴파일 단계 등 언어별
세부 정보를 반환한다.
"""

from __future__ import annotations

from . import go, javascript, python, rust, typescript

LANGUAGE_SPECS = {
    "python": python.SPEC,
    "javascript": javascript.SPEC,
    "typescript": typescript.SPEC,
    "rust": rust.SPEC,
    "go": go.SPEC,
}

__all__ = ["LANGUAGE_SPECS", "go", "javascript", "python", "rust", "typescript"]
