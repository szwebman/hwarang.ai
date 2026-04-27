#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# macOS DMG 빌더 — create-dmg 우선, 없으면 hdiutil 폴백
#
# 사용법:
#   build_dmg.sh <app-path> <output-dmg-path>
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

APP_PATH="${1:-}"
DMG_PATH="${2:-}"

if [[ -z "$APP_PATH" || -z "$DMG_PATH" ]]; then
    echo "사용법: $0 <app-path> <output-dmg-path>" >&2
    exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
    echo "에러: .app 번들이 없습니다: $APP_PATH" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAYOUT="$SCRIPT_DIR/dmg_layout.json"

mkdir -p "$(dirname "$DMG_PATH")"
rm -f "$DMG_PATH"

# create-dmg (npm 패키지 또는 brew) 사용 가능하면 우선
if command -v create-dmg &>/dev/null; then
    echo "[INFO] create-dmg 사용..."

    BG_ARG=()
    if [[ -f "$SCRIPT_DIR/background.png" ]]; then
        BG_ARG=(--background "$SCRIPT_DIR/background.png")
    fi

    create-dmg \
        --volname "Hwarang Grid Agent" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 128 \
        --icon "Hwarang Grid Agent.app" 150 200 \
        --hide-extension "Hwarang Grid Agent.app" \
        --app-drop-link 450 200 \
        --no-internet-enable \
        "${BG_ARG[@]}" \
        "$DMG_PATH" \
        "$APP_PATH"
else
    echo "[INFO] create-dmg 없음 → hdiutil 폴백"
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT

    cp -R "$APP_PATH" "$TMP_DIR/"
    ln -s /Applications "$TMP_DIR/Applications"

    hdiutil create \
        -volname "Hwarang Grid Agent" \
        -srcfolder "$TMP_DIR" \
        -ov \
        -format UDZO \
        -imagekey zlib-level=9 \
        "$DMG_PATH"
fi

echo "[ OK ] DMG 생성 완료: $DMG_PATH"
ls -lh "$DMG_PATH"
