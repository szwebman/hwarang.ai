#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — Linux 제거 스크립트
#
# 사용법:
#   ./uninstall_linux.sh             # 대화형
#   ./uninstall_linux.sh --yes-all   # 사용자 데이터까지
#   ./uninstall_linux.sh --keep      # 사용자 데이터 유지
#   ./uninstall_linux.sh --deb       # apt 로 .deb 패키지 제거 추가
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PKG_NAME="hwarang-grid-agent"
BINARY="/usr/local/bin/hwarang-grid"
DESKTOP_FILE="/usr/share/applications/hwarang-grid.desktop"
SVC_FILE="$HOME/.config/systemd/user/hwarang-grid.service"
HWARANG_DIR="$HOME/.hwarang"
ICON="/usr/share/icons/hicolor/256x256/apps/hwarang-grid.png"

MODE="ask"
USE_APT=0
for arg in "$@"; do
    case "$arg" in
        --yes-all|-y) MODE="yes" ;;
        --keep|-k)    MODE="keep" ;;
        --deb)        USE_APT=1 ;;
    esac
done

log()  { echo "[INFO] $*"; }
ok()   { echo "[ OK ] $*"; }
warn() { echo "[WARN] $*"; }

echo "═══════════════════════════════════════════"
echo " 화랑 Grid Agent 제거"
echo "═══════════════════════════════════════════"

# 1. systemd 서비스 정지/제거
if command -v systemctl &>/dev/null; then
    log "systemd user service 정지..."
    systemctl --user stop hwarang-grid.service 2>/dev/null || true
    systemctl --user disable hwarang-grid.service 2>/dev/null || true
    if [[ -f "$SVC_FILE" ]]; then
        rm -f "$SVC_FILE"
        ok "service 파일 제거: $SVC_FILE"
    fi
    systemctl --user daemon-reload 2>/dev/null || true
fi

# 2. 프로세스 종료
log "프로세스 종료..."
pkill -f hwarang-grid 2>/dev/null || true
sleep 1
ok "프로세스 종료"

# 3. .deb 패키지로 설치된 경우
if [[ $USE_APT -eq 1 ]] || dpkg -l 2>/dev/null | grep -q "^ii  $PKG_NAME "; then
    log ".deb 패키지 제거 (sudo 권한 필요)..."
    if sudo apt-get remove -y "$PKG_NAME" 2>/dev/null; then
        ok "apt 제거 완료"
    elif sudo dpkg -r "$PKG_NAME" 2>/dev/null; then
        ok "dpkg 제거 완료"
    else
        warn "패키지 제거 실패 (수동 제거 필요)"
    fi
else
    # 4. 수동 설치된 파일 정리
    log "수동 설치 파일 정리..."
    if [[ -f "$BINARY" ]]; then
        if rm -f "$BINARY" 2>/dev/null; then
            ok "바이너리 제거: $BINARY"
        else
            sudo rm -f "$BINARY"
            ok "바이너리 제거 (sudo): $BINARY"
        fi
    fi

    [[ -f "$DESKTOP_FILE" ]] && sudo rm -f "$DESKTOP_FILE" 2>/dev/null && ok "$DESKTOP_FILE"
    [[ -f "$ICON" ]]         && sudo rm -f "$ICON" 2>/dev/null         && ok "$ICON"

    # 데스크탑 DB 갱신
    if command -v update-desktop-database &>/dev/null; then
        sudo update-desktop-database -q 2>/dev/null || true
    fi
fi

# 5. AppImage (다운로드 폴더에 있으면)
log "AppImage 검색..."
for dir in "$HOME/Downloads" "$HOME/Desktop" "$HOME/Applications"; do
    if [[ -d "$dir" ]]; then
        find "$dir" -maxdepth 1 -name 'Hwarang-Grid-Agent*.AppImage' -print -exec rm -f {} \; 2>/dev/null || true
    fi
done

# 6. 사용자 데이터
if [[ -d "$HWARANG_DIR" ]]; then
    if [[ "$MODE" == "yes" ]]; then
        rm -rf "$HWARANG_DIR"
        ok "사용자 데이터 삭제: $HWARANG_DIR"
    elif [[ "$MODE" == "keep" ]]; then
        log "사용자 데이터 유지: $HWARANG_DIR"
    else
        echo
        read -r -p "사용자 데이터 ($HWARANG_DIR) 도 삭제하시겠습니까? [y/N]: " yn
        if [[ "${yn,,}" == "y" || "${yn,,}" == "yes" ]]; then
            rm -rf "$HWARANG_DIR"
            ok "사용자 데이터 삭제"
        else
            log "사용자 데이터 유지"
        fi
    fi
fi

echo
ok "═══════════════════════════════════════════"
ok " 화랑 Grid Agent 제거 완료"
ok "═══════════════════════════════════════════"
