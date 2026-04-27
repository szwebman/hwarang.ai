#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — macOS 첫 실행 / 설치 후 동작
#
# 호출 시점:
#   - .app 첫 실행 시 Tauri 앱 내부에서 호출 (또는 사용자 수동)
#   - DMG 설치 후 환경 초기화
#
# 동작:
#   1. ~/.hwarang/ 디렉토리 생성
#   2. LaunchAgent plist 등록 (자동시작 옵션 활성화 시)
#   3. com.apple.quarantine 속성 제거 (배포 후 첫 실행)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

APP_NAME="Hwarang Grid Agent"
APP_PATH="/Applications/${APP_NAME}.app"
LABEL="ai.hwarang.grid"
HWARANG_DIR="$HOME/.hwarang"
LA_DIR="$HOME/Library/LaunchAgents"
PLIST="$LA_DIR/${LABEL}.plist"

log()  { echo "[INFO] $*"; }
ok()   { echo "[ OK ] $*"; }
warn() { echo "[WARN] $*"; }

# 1. 디렉토리 생성
log "사용자 디렉토리 초기화..."
mkdir -p "$HWARANG_DIR"/{logs,cache,config}
chmod 700 "$HWARANG_DIR"
ok "$HWARANG_DIR"

# 2. quarantine 제거 (다운로드 후 macOS가 자동으로 붙임)
if [[ -d "$APP_PATH" ]]; then
    log "quarantine 속성 제거 시도..."
    if xattr -dr com.apple.quarantine "$APP_PATH" 2>/dev/null; then
        ok "quarantine 제거 완료"
    else
        warn "quarantine 제거 실패 (권한 문제 가능, 무시해도 됨)"
    fi
fi

# 3. 자동 시작 LaunchAgent 등록
ENABLE_AUTOSTART="${HWARANG_AUTOSTART:-1}"
if [[ "$ENABLE_AUTOSTART" == "1" ]]; then
    log "자동 시작 등록 (LaunchAgent)..."
    mkdir -p "$LA_DIR"

    cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${APP_PATH}/Contents/MacOS/Hwarang Grid Agent</string>
    <string>--background</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key><false/>
  </dict>
  <key>StandardOutPath</key><string>${HWARANG_DIR}/logs/agent.out.log</string>
  <key>StandardErrorPath</key><string>${HWARANG_DIR}/logs/agent.err.log</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST

    # 기존 등록 해제 후 재등록
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    ok "LaunchAgent 등록: $PLIST"
else
    log "자동 시작 비활성화 (HWARANG_AUTOSTART != 1)"
fi

# 4. 결과
ok "초기화 완료"
echo "  사용자 데이터:    $HWARANG_DIR"
echo "  자동 시작 plist:  $PLIST (활성화된 경우)"
echo "  앱 경로:          $APP_PATH"
