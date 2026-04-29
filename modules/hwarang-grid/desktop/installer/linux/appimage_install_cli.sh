#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — AppImage 사용자용 CLI 등록 헬퍼
#
# AppImage 는 sandboxed 라서 시스템 PATH 등록이 까다롭다.
# 본 스크립트는 AppImage 를 1회 추출하여 hwarang-agent 사이드카를 꺼내고,
# ~/.local/bin/hwarang-agent symlink 를 만들어준다 (sudo 불필요).
#
# 사용법:
#   ./appimage_install_cli.sh /path/to/Hwarang-Grid-Agent.AppImage
#
# 이후 사용자는 ~/.local/bin 이 PATH 에 포함되어 있으면 즉시 사용 가능
# (Ubuntu/Debian/Fedora 최신 배포는 기본 포함).
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

APPIMAGE_PATH="${1:-./Hwarang-Grid-Agent.AppImage}"
EXTRACT_DIR="$HOME/.local/share/hwarang-grid"
LOCAL_BIN="$HOME/.local/bin"
SYMLINK="$LOCAL_BIN/hwarang-agent"

if [[ ! -f "$APPIMAGE_PATH" ]]; then
    echo "[ERROR] AppImage 경로를 지정하세요." >&2
    echo "        $0 /path/to/Hwarang-Grid-Agent.AppImage" >&2
    exit 1
fi

# 절대 경로 변환
APPIMAGE_PATH="$(cd "$(dirname "$APPIMAGE_PATH")" && pwd)/$(basename "$APPIMAGE_PATH")"

# 추출 디렉토리 정리 후 재추출 (idempotent)
rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"
cd "$EXTRACT_DIR"

chmod +x "$APPIMAGE_PATH" 2>/dev/null || true

echo "[INFO] AppImage 추출 중..."
if ! "$APPIMAGE_PATH" --appimage-extract >/dev/null 2>&1; then
    echo "[ERROR] AppImage 추출 실패. AppImage 파일이 손상되지 않았는지 확인하세요." >&2
    exit 2
fi

# 사이드카 탐색
SIDECAR="$(find squashfs-root -type f \
           \( -name 'hwarang-agent-x86_64-unknown-linux-gnu' \
              -o -name 'hwarang-agent' \
              -o -name 'hwarang-agent-aarch64-unknown-linux-gnu' \) \
           2>/dev/null | head -1)"

if [[ -z "$SIDECAR" ]]; then
    echo "[ERROR] AppImage 내에서 hwarang-agent 사이드카를 찾지 못했습니다." >&2
    echo "        예상 위치: squashfs-root/usr/bin/ 또는 ./binaries/" >&2
    exit 3
fi

ABS_SIDECAR="$EXTRACT_DIR/$SIDECAR"
chmod +x "$ABS_SIDECAR" 2>/dev/null || true

mkdir -p "$LOCAL_BIN"
ln -sf "$ABS_SIDECAR" "$SYMLINK"

echo "[ OK ] hwarang-agent → $SYMLINK"
echo
echo "─── PATH 확인 ───"
case ":$PATH:" in
    *":$LOCAL_BIN:"*)
        echo "[ OK ] \$HOME/.local/bin 이 이미 PATH 에 포함됨"
        echo "       바로 사용 가능: hwarang-agent --help"
        ;;
    *)
        echo "[ACTION] \$HOME/.local/bin 이 PATH 에 없습니다. 다음을 ~/.bashrc 또는 ~/.zshrc 에 추가:"
        echo
        echo '         export PATH="$HOME/.local/bin:$PATH"'
        echo
        echo "        그 다음:  source ~/.bashrc  (또는 새 터미널)"
        ;;
esac

exit 0
