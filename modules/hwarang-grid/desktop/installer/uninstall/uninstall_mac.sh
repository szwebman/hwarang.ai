#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — macOS 제거 스크립트
#
# 사용법:
#   ./uninstall_mac.sh            # 대화형 (사용자 데이터 유지 여부 묻기)
#   ./uninstall_mac.sh --yes-all  # 사용자 데이터까지 모두 삭제
#   ./uninstall_mac.sh --keep     # 사용자 데이터 유지
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

APP_NAME="Hwarang Grid Agent"
APP_PATH="/Applications/${APP_NAME}.app"
LABEL="ai.hwarang.grid"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
HWARANG_DIR="$HOME/.hwarang"
APP_SUPPORT="$HOME/Library/Application Support/Hwarang Grid Agent"
CACHES="$HOME/Library/Caches/Hwarang Grid Agent"
LOGS="$HOME/Library/Logs/Hwarang Grid Agent"
PREFS="$HOME/Library/Preferences/ai.hwarang.grid.plist"

MODE="ask"
case "${1:-}" in
    --yes-all|-y) MODE="yes" ;;
    --keep|-k)    MODE="keep" ;;
esac

log()  { echo "[INFO] $*"; }
ok()   { echo "[ OK ] $*"; }
warn() { echo "[WARN] $*"; }

echo "═══════════════════════════════════════════"
echo " 화랑 Grid Agent 제거"
echo "═══════════════════════════════════════════"

# 1. 데몬 종료
log "에이전트 종료 중..."
if pgrep -f "Hwarang Grid Agent" >/dev/null 2>&1; then
    pkill -f "Hwarang Grid Agent" 2>/dev/null || true
    sleep 1
fi
if command -v hwarang-agent &>/dev/null; then
    hwarang-agent stop 2>/dev/null || true
fi
ok "프로세스 종료"

# 2. LaunchAgent 제거
if [[ -f "$PLIST" ]]; then
    log "LaunchAgent 해제..."
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    ok "LaunchAgent 제거: $PLIST"
fi

# 3. 앱 삭제
if [[ -d "$APP_PATH" ]]; then
    log "앱 삭제..."
    if rm -rf "$APP_PATH" 2>/dev/null; then
        ok "$APP_PATH 삭제 완료"
    else
        warn "권한 부족 → sudo 시도..."
        sudo rm -rf "$APP_PATH"
        ok "$APP_PATH 삭제 완료 (sudo)"
    fi
else
    warn "$APP_PATH 가 없음 (이미 제거됨)"
fi

# 4. 시스템 캐시 / 환경 설정
log "시스템 캐시 / 설정 정리..."
rm -rf "$APP_SUPPORT" 2>/dev/null || true
rm -rf "$CACHES" 2>/dev/null || true
rm -rf "$LOGS" 2>/dev/null || true
rm -f  "$PREFS" 2>/dev/null || true
ok "정리 완료"

# 5. 사용자 데이터
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
            log "사용자 데이터 유지 (수동 삭제: rm -rf $HWARANG_DIR)"
        fi
    fi
fi

echo
ok "═══════════════════════════════════════════"
ok " 화랑 Grid Agent 제거 완료"
ok "═══════════════════════════════════════════"
