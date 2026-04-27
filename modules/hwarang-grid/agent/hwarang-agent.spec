# -*- mode: python ; coding: utf-8 -*-
#
# Hwarang Grid Agent — PyInstaller spec
#
# 일반적으로는 build_binary.py 가 동적으로 인자를 구성하지만,
# 세밀한 커스터마이즈가 필요하면 이 spec 파일을 사용하라:
#
#     pyinstaller hwarang-agent.spec
#
# 이 spec은 build_binary.py 의 기본값과 일치한다.

from __future__ import annotations

import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────
# 경로 / 진입점
# ──────────────────────────────────────────────────────────────────

AGENT_DIR = Path(SPECPATH).resolve() if "SPECPATH" in globals() else Path.cwd()
ENTRYPOINT = str(AGENT_DIR / "cli.py")

# ──────────────────────────────────────────────────────────────────
# Hidden imports — runtime 동적 import 대상
# ──────────────────────────────────────────────────────────────────

HIDDEN_IMPORTS = [
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

# 선택적 (설치되어 있으면 자동 포함)
for _opt in [
    "torch",
    "transformers",
    "peft",
    "accelerate",
    "tokenizers",
    "sentencepiece",
    "datasets",
    "httpx",
    "yaml",
    "psutil",
    "numpy",
    "bitsandbytes",
]:
    try:
        __import__(_opt)
        HIDDEN_IMPORTS.append(_opt)
    except Exception:
        pass

# ──────────────────────────────────────────────────────────────────
# Excludes — 사이즈 줄이기
# ──────────────────────────────────────────────────────────────────

EXCLUDES = [
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

# ──────────────────────────────────────────────────────────────────
# Analysis
# ──────────────────────────────────────────────────────────────────

a = Analysis(
    [ENTRYPOINT],
    pathex=[str(AGENT_DIR)],
    binaries=[],
    datas=[
        # 프리셋 YAML 동봉 (data_crawler/domain_specialization 에서 사용)
        (str(AGENT_DIR / "config"), "config"),
    ],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Windows: 콘솔 숨김, 기타 OS: console 유지
_console = not sys.platform.startswith("win")
_strip = not sys.platform.startswith("win")  # Windows는 strip 미지원

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="hwarang-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=_strip,
    upx=False,            # UPX는 macOS 코드사이닝과 충돌 가능 → 끔
    upx_exclude=[],
    runtime_tmpdir=None,
    console=_console,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
