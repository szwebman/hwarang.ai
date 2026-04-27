"""Hwarang Grid Agent 단일 실행파일 빌드 스크립트.

PyInstaller로 Python 인터프리터 + 모든 의존성을 단일 실행파일로 묶어서
Tauri 사이드카로 사용한다.

Tauri 사이드카는 OS별 binary suffix 규칙을 따른다:
  - macOS:   hwarang-agent-aarch64-apple-darwin (Apple Silicon)
             hwarang-agent-x86_64-apple-darwin
  - Windows: hwarang-agent-x86_64-pc-windows-msvc.exe
  - Linux:   hwarang-agent-x86_64-unknown-linux-gnu

사용법:
    python build_binary.py            # 현재 OS용
    python build_binary.py --target macos-arm64
    python build_binary.py --clean
    python build_binary.py --onedir
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("build_binary")

# ────────────────────────────────────────────────────────────────────────
# 경로/상수
# ────────────────────────────────────────────────────────────────────────

AGENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_DIR.parent
DESKTOP_BIN_DIR = PROJECT_ROOT / "desktop" / "src-tauri" / "binaries"
ENTRYPOINT = AGENT_DIR / "cli.py"
SPEC_FILE = AGENT_DIR / "hwarang-agent.spec"
DIST_DIR = AGENT_DIR / "dist"
BUILD_DIR = AGENT_DIR / "build"

# Target triple ↔ alias 매핑 (Tauri 규칙 기반)
TARGET_TRIPLES: dict[str, str] = {
    "macos-arm64": "aarch64-apple-darwin",
    "macos-x64": "x86_64-apple-darwin",
    "windows-x64": "x86_64-pc-windows-msvc",
    "linux-x64": "x86_64-unknown-linux-gnu",
    "linux-arm64": "aarch64-unknown-linux-gnu",
}

# PyInstaller에 포함시킬 hidden import (런타임 동적 import 대응)
HIDDEN_IMPORTS: list[str] = [
    "asyncio",
    "asyncio.subprocess",
    "json",
    "signal",
    "logging",
    "logging.handlers",
    "pathlib",
    "datetime",
    "argparse",
    # 사이드카 핵심
    "modules.gpu_detector",
    "modules.system_monitor",
    "modules.participation_control",
    "modules.round_subscription",
    "modules.earnings_tracker",
    "modules.safety_guards",
    "modules.domain_specialization",
    "modules.status_writer",
    "modules.pid_manager",
]

# 선택적 — 설치돼 있으면 포함, 아니면 스킵
OPTIONAL_IMPORTS: list[str] = [
    "torch",
    "transformers",
    "peft",
    "sentencepiece",
    "tokenizers",
    "accelerate",
    "bitsandbytes",
    "datasets",
    "httpx",
    "yaml",
    "psutil",
    "numpy",
]

# 묶지 않을 모듈 (사이즈 감축)
EXCLUDES: list[str] = [
    "tkinter",
    "matplotlib",
    "PIL",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "wx",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "sphinx",
    "babel",
    "pandas.tests",
    "numpy.tests",
    "scipy.tests",
]


# ────────────────────────────────────────────────────────────────────────
# Target / Triple 감지
# ────────────────────────────────────────────────────────────────────────


def detect_current_triple() -> str:
    """현재 시스템의 Tauri-style target triple 추론."""
    sysname = platform.system().lower()
    machine = platform.machine().lower()

    if sysname == "darwin":
        if machine in ("arm64", "aarch64"):
            return "aarch64-apple-darwin"
        return "x86_64-apple-darwin"
    if sysname == "windows":
        return "x86_64-pc-windows-msvc"
    if sysname == "linux":
        if machine in ("aarch64", "arm64"):
            return "aarch64-unknown-linux-gnu"
        return "x86_64-unknown-linux-gnu"
    raise RuntimeError(f"지원하지 않는 OS: {sysname}/{machine}")


def resolve_triple(target: str | None) -> str:
    """--target 인자를 triple로 변환.

    - None → 현재 OS 자동 감지
    - alias → 매핑
    - triple 형식 그대로 → 그대로 반환
    """
    if not target:
        return detect_current_triple()
    if target in TARGET_TRIPLES:
        return TARGET_TRIPLES[target]
    if "-" in target and target.count("-") >= 2:
        return target
    raise ValueError(
        f"알 수 없는 --target: {target} (사용 가능: {', '.join(TARGET_TRIPLES)})"
    )


def is_windows_triple(triple: str) -> bool:
    return "windows" in triple


def output_binary_name(triple: str) -> str:
    """Tauri 사이드카 명명 규칙."""
    suffix = ".exe" if is_windows_triple(triple) else ""
    return f"hwarang-agent-{triple}{suffix}"


# ────────────────────────────────────────────────────────────────────────
# PyInstaller 호출
# ────────────────────────────────────────────────────────────────────────


def ensure_pyinstaller() -> None:
    """PyInstaller가 설치되어 있는지 확인."""
    try:
        import PyInstaller  # type: ignore  # noqa: F401
    except ImportError:
        logger.error("PyInstaller가 설치되어 있지 않습니다.")
        logger.error("설치: pip install pyinstaller>=6.0")
        sys.exit(2)


def filter_optional_imports() -> list[str]:
    """현재 환경에 실제 설치된 OPTIONAL_IMPORTS만 반환."""
    available: list[str] = []
    for mod in OPTIONAL_IMPORTS:
        try:
            __import__(mod)
            available.append(mod)
        except Exception:
            logger.debug("선택 모듈 누락 (스킵): %s", mod)
    return available


def build_pyinstaller_args(
    *,
    triple: str,
    onedir: bool,
    extra_hidden: list[str],
) -> list[str]:
    """PyInstaller 실행 인자 구성."""
    name = "hwarang-agent"
    args: list[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        name,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(AGENT_DIR),
    ]

    if onedir:
        args.append("--onedir")
    else:
        args.append("--onefile")

    # Windows: 콘솔 창 숨김 (트레이 백그라운드 데몬용)
    if is_windows_triple(triple):
        args.append("--noconsole")
    else:
        # 다른 OS는 console 모드 유지 (로그 출력 + nohup 호환)
        args.append("--console")

    # strip + 사이즈 감축
    if not is_windows_triple(triple):
        # macOS / Linux: strip 가능 (Windows는 PyInstaller가 무시)
        args.append("--strip")

    # hidden imports
    for h in [*HIDDEN_IMPORTS, *extra_hidden]:
        args.extend(["--hidden-import", h])

    # excludes
    for e in EXCLUDES:
        args.extend(["--exclude-module", e])

    # 검색 경로 (modules/ 임포트 가능하게)
    args.extend(["--paths", str(AGENT_DIR)])

    # 진입점
    args.append(str(ENTRYPOINT))

    return args


def run_pyinstaller(triple: str, onedir: bool) -> Path:
    """PyInstaller 실행 후 결과 경로 반환."""
    ensure_pyinstaller()

    optional = filter_optional_imports()
    logger.info("선택 모듈 포함: %s", optional or "(없음)")

    args = build_pyinstaller_args(
        triple=triple,
        onedir=onedir,
        extra_hidden=optional,
    )
    logger.info("PyInstaller 실행: %s", " ".join(args))

    result = subprocess.run(args, cwd=AGENT_DIR)
    if result.returncode != 0:
        logger.error("PyInstaller 빌드 실패 (exit=%s)", result.returncode)
        sys.exit(result.returncode)

    # 결과 경로
    if onedir:
        produced = DIST_DIR / "hwarang-agent"
    else:
        ext = ".exe" if is_windows_triple(triple) else ""
        produced = DIST_DIR / f"hwarang-agent{ext}"
    if not produced.exists():
        logger.error("빌드 결과를 찾을 수 없음: %s", produced)
        sys.exit(1)
    return produced


# ────────────────────────────────────────────────────────────────────────
# 결과물 → Tauri binaries/ 복사
# ────────────────────────────────────────────────────────────────────────


def copy_to_tauri(produced: Path, triple: str) -> Path:
    """빌드 결과를 desktop/src-tauri/binaries/<sidecar-name> 으로 복사."""
    DESKTOP_BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = DESKTOP_BIN_DIR / output_binary_name(triple)

    if produced.is_dir():
        # onedir 모드 → 디렉토리 통째로 복사 (사이드카로 쓰려면 onefile 권장)
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.copytree(produced, target)
    else:
        if target.exists():
            target.unlink()
        shutil.copy2(produced, target)
        # 실행 권한 보장 (macOS / Linux)
        if not is_windows_triple(triple):
            try:
                os.chmod(target, 0o755)
            except Exception as exc:
                logger.warning("chmod 실패: %s", exc)

    logger.info("복사 완료: %s", target)
    return target


def verify_binary(binary: Path, triple: str) -> bool:
    """빌드된 실행파일이 동작하는지 간단 검증."""
    if binary.is_dir():
        logger.info("onedir 빌드 — 검증 스킵")
        return True

    is_native = triple == detect_current_triple()
    if not is_native:
        logger.info("크로스 빌드 — 실행 검증 스킵 (triple=%s)", triple)
        return True

    try:
        result = subprocess.run(
            [str(binary), "version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            logger.warning(
                "검증 실패 (exit=%s) stdout=%r stderr=%r",
                result.returncode, result.stdout, result.stderr,
            )
            return False
        logger.info("검증 성공: %s", result.stdout.strip())
        return True
    except Exception as exc:
        logger.warning("검증 중 예외: %s", exc)
        return False


# ────────────────────────────────────────────────────────────────────────
# Clean
# ────────────────────────────────────────────────────────────────────────


def clean_artifacts() -> None:
    """빌드 산출물 제거."""
    for path in (DIST_DIR, BUILD_DIR):
        if path.exists():
            logger.info("제거: %s", path)
            shutil.rmtree(path, ignore_errors=True)
    # spec은 유지 (수동 편집된 경우 보존)


# ────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="build_binary",
        description="Hwarang Grid Agent PyInstaller 빌드 스크립트",
    )
    p.add_argument(
        "--target",
        help="대상 플랫폼: " + ", ".join(TARGET_TRIPLES) + " 또는 직접 triple",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="dist/build 디렉토리 제거 후 종료",
    )
    p.add_argument(
        "--onedir",
        action="store_true",
        help="--onefile 대신 onedir 모드 (디버깅용)",
    )
    p.add_argument(
        "--no-copy",
        action="store_true",
        help="Tauri binaries/ 로 복사하지 않음",
    )
    p.add_argument(
        "--skip-verify",
        action="store_true",
        help="빌드 후 실행 검증 생략",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.getenv("HWARANG_LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    args = _parse_args(argv)

    if args.clean:
        clean_artifacts()
        logger.info("[OK] clean 완료")
        return 0

    triple = resolve_triple(args.target)
    logger.info("빌드 대상 triple: %s", triple)

    produced = run_pyinstaller(triple=triple, onedir=args.onedir)
    logger.info("산출물: %s", produced)

    if not args.no_copy:
        target = copy_to_tauri(produced, triple)
    else:
        target = produced

    if not args.skip_verify:
        ok = verify_binary(target, triple)
        if not ok:
            logger.warning(
                "검증에 실패했지만 결과 파일은 생성되었습니다 (수동 확인 필요).",
            )

    logger.info("[DONE] %s", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
