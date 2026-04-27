#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — Debian/Ubuntu .deb 패키지 빌더
#
# 사용법:
#   ./build_deb.sh               # 현재 디렉토리에 .deb 생성
#   ./build_deb.sh /tmp/dist     # 지정 경로
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT_DIR="${1:-$DESKTOP_DIR/dist}"
mkdir -p "$OUT_DIR"

# 메타
VERSION="$(grep -E '"version"' "$DESKTOP_DIR/src-tauri/tauri.conf.json" | head -1 | sed -E 's/.*"version"[^"]*"([^"]+)".*/\1/')"
ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
PKG_NAME="hwarang-grid-agent"
DEB_NAME="${PKG_NAME}_${VERSION}_${ARCH}.deb"

# Tauri 빌드된 .deb 우선 사용
TAURI_DEB="$(find "$DESKTOP_DIR/src-tauri/target/release/bundle/deb" -name '*.deb' 2>/dev/null | head -1 || true)"
if [[ -n "$TAURI_DEB" ]]; then
    echo "[INFO] Tauri .deb 발견 → 그대로 사용"
    cp "$TAURI_DEB" "$OUT_DIR/$DEB_NAME"
    sha256sum "$OUT_DIR/$DEB_NAME" > "$OUT_DIR/$DEB_NAME.sha256"
    echo "[ OK ] $OUT_DIR/$DEB_NAME"
    exit 0
fi

# ─── 수동 .deb 빌드 (dpkg-deb) ───────────────────────────────────────────
echo "[INFO] Tauri .deb 없음 → 수동 빌드"

BINARY="$DESKTOP_DIR/src-tauri/target/release/hwarang-grid"
if [[ ! -f "$BINARY" ]]; then
    echo "[ERR] 바이너리 없음: $BINARY (cargo tauri build 먼저 실행)" >&2
    exit 1
fi

BUILD_ROOT="$(mktemp -d)"
trap 'rm -rf "$BUILD_ROOT"' EXIT

PKG_DIR="$BUILD_ROOT/${PKG_NAME}_${VERSION}_${ARCH}"

# 디렉토리 구조
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/local/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$PKG_DIR/usr/share/doc/$PKG_NAME"

# 바이너리
cp "$BINARY" "$PKG_DIR/usr/local/bin/hwarang-grid"
chmod 755 "$PKG_DIR/usr/local/bin/hwarang-grid"

# .desktop 런처
cp "$SCRIPT_DIR/hwarang-grid.desktop" "$PKG_DIR/usr/share/applications/"

# 아이콘
ICON_SRC="$DESKTOP_DIR/src-tauri/icons/icon.png"
[[ -f "$ICON_SRC" ]] || ICON_SRC="$(find "$DESKTOP_DIR/src-tauri/icons" -name '*.png' | head -1)"
if [[ -n "$ICON_SRC" ]]; then
    cp "$ICON_SRC" "$PKG_DIR/usr/share/icons/hicolor/256x256/apps/hwarang-grid.png"
fi

# control 파일
cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: net
Priority: optional
Architecture: $ARCH
Maintainer: Hwarang AI <support@hwarang.ai>
Depends: libc6, libgtk-3-0, libwebkit2gtk-4.1-0 | libwebkit2gtk-4.0-37, libayatana-appindicator3-1 | libappindicator3-1
Homepage: https://hwarang.ai
Description: 화랑 Grid Agent — GPU 공유 네트워크 참여
 GPU 공유 네트워크에 참여하여 유휴 GPU 자원을 제공하고
 HWR 코인 보상을 받을 수 있는 데스크탑 에이전트입니다.
 .
 - 자동 일시정지 (게임/렌더링 감지)
 - 안전 격리 (sandbox)
 - 실시간 수익 대시보드
EOF

# postinst (설치 후)
cat > "$PKG_DIR/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e

# 사용자 디렉토리 생성은 첫 실행 시 (사용자 권한 문제)
# desktop 데이터베이스 갱신
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi

echo "Hwarang Grid Agent 설치 완료"
echo "실행: hwarang-grid 또는 애플리케이션 메뉴에서 시작"
exit 0
EOF
chmod 755 "$PKG_DIR/DEBIAN/postinst"

# prerm (제거 전)
cat > "$PKG_DIR/DEBIAN/prerm" <<'EOF'
#!/bin/bash
set -e

# systemd user service 정지 시도 (각 사용자별이므로 best-effort)
if command -v systemctl >/dev/null 2>&1; then
    systemctl --user --machine="$(logname 2>/dev/null)@.host" stop hwarang-grid.service 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "$PKG_DIR/DEBIAN/prerm"

# 라이선스 / changelog
cat > "$PKG_DIR/usr/share/doc/$PKG_NAME/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: hwarang-grid-agent
Upstream-Contact: Hwarang AI <support@hwarang.ai>
Source: https://hwarang.ai

Files: *
Copyright: $(date +%Y) Hwarang AI
License: Proprietary
EOF

# 빌드
dpkg-deb --build --root-owner-group "$PKG_DIR" "$OUT_DIR/$DEB_NAME"

# 체크섬
(cd "$OUT_DIR" && sha256sum "$DEB_NAME" > "${DEB_NAME}.sha256")

echo "[ OK ] $OUT_DIR/$DEB_NAME"
ls -lh "$OUT_DIR/$DEB_NAME"
