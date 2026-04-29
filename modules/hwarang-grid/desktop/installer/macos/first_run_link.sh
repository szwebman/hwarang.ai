#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — macOS 첫 실행 hwarang-agent CLI symlink (osascript 권한 다이얼로그)
#
# 호출:  ./first_run_link.sh "/Applications/Hwarang Grid Agent.app"
#
# .dmg 번들로 설치한 사용자는 .pkg postinstall 이 동작하지 않으므로,
# Tauri main.rs setup() 에서 첫 실행 시 1회만 본 스크립트를 시도하면
# osascript 가 GUI 권한 다이얼로그를 띄워 sudo symlink 를 만든다.
#
# 거절 시 .skip_cli_link 마커가 ~/.hwarang/ 에 생기고 다시 묻지 않는다.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

APP_PATH="${1:-/Applications/Hwarang Grid Agent.app}"
HWARANG_DIR="$HOME/.hwarang"
SKIP_MARKER="$HWARANG_DIR/.skip_cli_link"
SYMLINK="/usr/local/bin/hwarang-agent"

mkdir -p "$HWARANG_DIR" 2>/dev/null || true

# 사용자가 거절한 적 있으면 다시 시도 안 함
if [[ -f "$SKIP_MARKER" ]]; then
    exit 0
fi

ARCH="$(uname -m)"
case "$ARCH" in
    arm64)  TRIPLE="aarch64-apple-darwin" ;;
    x86_64) TRIPLE="x86_64-apple-darwin" ;;
    *)      TRIPLE="" ;;
esac

SIDECAR_DIR="${APP_PATH}/Contents/Resources/binaries"
CANDIDATES=(
    "${SIDECAR_DIR}/hwarang-agent-${TRIPLE}"
    "${SIDECAR_DIR}/hwarang-agent"
    "${SIDECAR_DIR}/hwarang-agent-universal-apple-darwin"
)

BINARY=""
for c in "${CANDIDATES[@]}"; do
    if [[ -n "$c" && -f "$c" ]]; then
        BINARY="$c"
        break
    fi
done

if [[ -z "$BINARY" ]]; then
    echo "[WARN] 사이드카를 찾지 못함 — 종료"
    exit 0
fi

# 이미 올바른 symlink 면 끝
if [[ -L "$SYMLINK" ]]; then
    CURRENT_TARGET="$(readlink "$SYMLINK" 2>/dev/null || true)"
    if [[ "$CURRENT_TARGET" == "$BINARY" ]]; then
        exit 0
    fi
fi

# osascript 로 관리자 권한 요청 (GUI 다이얼로그)
# 거절(-128)되면 마커 파일 생성하여 재시도 차단
SCRIPT="mkdir -p /usr/local/bin && ln -sf '$BINARY' '$SYMLINK' && chmod +x '$BINARY'"

if osascript -e "do shell script \"$SCRIPT\" with administrator privileges" >/dev/null 2>&1; then
    echo "[ OK ] hwarang-agent CLI → $SYMLINK"
    rm -f "$SKIP_MARKER" 2>/dev/null || true
else
    rc=$?
    echo "[INFO] CLI symlink 등록 거절 또는 실패 (코드 $rc) — 다시 묻지 않음"
    touch "$SKIP_MARKER" 2>/dev/null || true
fi

exit 0
