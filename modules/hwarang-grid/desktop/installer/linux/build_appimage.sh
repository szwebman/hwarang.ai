#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — AppImage 빌더 (linuxdeploy 기반)
#
# 사전 요구:
#   - linuxdeploy: https://github.com/linuxdeploy/linuxdeploy/releases
#   - linuxdeploy-plugin-gtk (Tauri는 GTK/WebKit 의존)
#
# 사용법:
#   ./build_appimage.sh
#   ./build_appimage.sh /path/to/output
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT_DIR="${1:-$DESKTOP_DIR/dist}"
mkdir -p "$OUT_DIR"

VERSION="$(grep -E '"version"' "$DESKTOP_DIR/src-tauri/tauri.conf.json" | head -1 | sed -E 's/.*"version"[^"]*"([^"]+)".*/\1/')"
ARCH="$(uname -m)"
APPIMG_NAME="Hwarang-Grid-Agent-${VERSION}-${ARCH}.AppImage"

# Tauri 가 이미 .AppImage 만들면 그대로 사용
TAURI_APPIMG="$(find "$DESKTOP_DIR/src-tauri/target/release/bundle/appimage" -name '*.AppImage' 2>/dev/null | head -1 || true)"
if [[ -n "$TAURI_APPIMG" ]]; then
    echo "[INFO] Tauri AppImage 발견 → 그대로 사용"
    cp "$TAURI_APPIMG" "$OUT_DIR/$APPIMG_NAME"
    chmod +x "$OUT_DIR/$APPIMG_NAME"
    sha256sum "$OUT_DIR/$APPIMG_NAME" > "$OUT_DIR/$APPIMG_NAME.sha256"
    echo "[ OK ] $OUT_DIR/$APPIMG_NAME"
    exit 0
fi

# ─── linuxdeploy 수동 빌드 ──────────────────────────────────────────────
echo "[INFO] linuxdeploy 기반 수동 빌드"

LINUXDEPLOY="${LINUXDEPLOY:-$(command -v linuxdeploy || echo '')}"
if [[ -z "$LINUXDEPLOY" ]]; then
    echo "[ERR] linuxdeploy 가 설치되어 있지 않습니다." >&2
    echo "      https://github.com/linuxdeploy/linuxdeploy/releases 에서 다운로드하세요." >&2
    exit 1
fi

BINARY="$DESKTOP_DIR/src-tauri/target/release/hwarang-grid"
if [[ ! -f "$BINARY" ]]; then
    echo "[ERR] 바이너리 없음: $BINARY (cargo tauri build 먼저 실행)" >&2
    exit 2
fi

BUILD_ROOT="$(mktemp -d)"
trap 'rm -rf "$BUILD_ROOT"' EXIT

APPDIR="$BUILD_ROOT/AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp "$BINARY" "$APPDIR/usr/bin/hwarang-grid"
chmod +x "$APPDIR/usr/bin/hwarang-grid"

cp "$SCRIPT_DIR/hwarang-grid.desktop" "$APPDIR/usr/share/applications/"

ICON_SRC="$DESKTOP_DIR/src-tauri/icons/icon.png"
[[ -f "$ICON_SRC" ]] || ICON_SRC="$(find "$DESKTOP_DIR/src-tauri/icons" -name '*.png' | head -1)"
if [[ -n "$ICON_SRC" ]]; then
    cp "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/hwarang-grid.png"
fi

# linuxdeploy 실행
export OUTPUT="$OUT_DIR/$APPIMG_NAME"
"$LINUXDEPLOY" --appdir "$APPDIR" \
    --desktop-file "$APPDIR/usr/share/applications/hwarang-grid.desktop" \
    --icon-file "$APPDIR/usr/share/icons/hicolor/256x256/apps/hwarang-grid.png" \
    --plugin gtk \
    --output appimage

chmod +x "$OUTPUT"
(cd "$OUT_DIR" && sha256sum "$APPIMG_NAME" > "${APPIMG_NAME}.sha256")

echo "[ OK ] $OUTPUT"
ls -lh "$OUTPUT"
