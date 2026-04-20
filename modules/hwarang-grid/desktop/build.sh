#!/bin/bash
# 화랑 Grid Agent 데스크탑 빌드 스크립트
#
# 사전 요구:
#   - Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
#   - Node.js 20+
#   - Tauri CLI: cargo install tauri-cli
#   - (Mac) Xcode Command Line Tools: xcode-select --install
#   - (Windows) Visual Studio Build Tools
#
# 사용법:
#   ./build.sh           # 현재 OS용 빌드
#   ./build.sh mac       # macOS .dmg
#   ./build.sh windows   # Windows .exe (크로스 컴파일 또는 Windows에서)
#   ./build.sh dev       # 개발 모드 실행

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "═══════════════════════════════════════════"
echo " 화랑 Grid Agent 빌드"
echo "═══════════════════════════════════════════"

# Rust 확인
if ! command -v cargo &> /dev/null; then
    echo "Rust가 설치되어 있지 않습니다."
    echo "설치: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    exit 1
fi

# Tauri CLI 확인
if ! command -v cargo-tauri &> /dev/null; then
    echo "Tauri CLI 설치 중..."
    cargo install tauri-cli
fi

MODE="${1:-build}"

case "$MODE" in
    dev)
        echo "개발 모드 시작..."
        cargo tauri dev
        ;;

    mac|macos)
        echo "macOS 빌드 (.dmg)..."
        cargo tauri build --target universal-apple-darwin 2>/dev/null || cargo tauri build

        echo ""
        echo "═══ 빌드 완료! ═══"
        DMG=$(find src-tauri/target -name "*.dmg" 2>/dev/null | head -1)
        if [ -n "$DMG" ]; then
            echo "DMG: $DMG"
            echo "크기: $(du -sh "$DMG" | cut -f1)"
        fi
        ls -la src-tauri/target/release/bundle/dmg/ 2>/dev/null || true
        ;;

    windows|win)
        echo "Windows 빌드 (.exe)..."

        if [[ "$(uname)" == "Darwin" || "$(uname)" == "Linux" ]]; then
            echo "크로스 컴파일 (Windows 타겟 필요)..."
            echo "Windows에서 직접 빌드하는 것을 권장합니다."
            echo ""
            echo "Windows에서 실행:"
            echo "  1. Rust 설치: https://rustup.rs"
            echo "  2. cargo install tauri-cli"
            echo "  3. cargo tauri build"
            exit 1
        fi

        cargo tauri build

        echo ""
        echo "═══ 빌드 완료! ═══"
        ls -la src-tauri/target/release/bundle/nsis/ 2>/dev/null || true
        ;;

    build)
        echo "현재 OS용 빌드..."
        cargo tauri build

        echo ""
        echo "═══ 빌드 완료! ═══"
        echo ""
        echo "출력 위치:"

        if [[ "$(uname)" == "Darwin" ]]; then
            ls -la src-tauri/target/release/bundle/dmg/ 2>/dev/null && echo ""
            ls -la src-tauri/target/release/bundle/macos/ 2>/dev/null
        elif [[ "$(uname)" == *"MINGW"* || "$(uname)" == *"MSYS"* ]]; then
            ls -la src-tauri/target/release/bundle/nsis/ 2>/dev/null
        else
            ls -la src-tauri/target/release/bundle/appimage/ 2>/dev/null
        fi
        ;;

    clean)
        echo "빌드 캐시 정리..."
        cd src-tauri && cargo clean
        echo "정리 완료"
        ;;

    *)
        echo "사용법: ./build.sh [dev|mac|windows|build|clean]"
        echo ""
        echo "  dev      - 개발 모드 실행 (핫 리로드)"
        echo "  mac      - macOS .dmg 빌드"
        echo "  windows  - Windows .exe 빌드"
        echo "  build    - 현재 OS용 빌드"
        echo "  clean    - 빌드 캐시 정리"
        ;;
esac
