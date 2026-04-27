#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — 설치 검증 스크립트
#
# 동작 (현재 OS 자동 감지):
#   1. 실행파일 존재 여부
#   2. 사용자 디렉토리 (~/.hwarang) 존재 + 권한
#   3. GPU 드라이버 (NVIDIA 우선)
#   4. 네트워크 도달성 (hwarang.ai)
#   5. 자동 시작 등록 여부
#   6. agent_status.json 5초 이내 갱신 (실행 중 검증)
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail   # -e 제외 (개별 체크 실패해도 계속)

PASS=0
FAIL=0
WARN=0

OS="$(uname -s | tr A-Z a-z)"
HWARANG_DIR="$HOME/.hwarang"
STATUS_FILE="$HWARANG_DIR/agent_status.json"

# ─── 컬러 ───────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}[ OK ]${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; FAIL=$((FAIL+1)); }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; WARN=$((WARN+1)); }
info() { echo "  [INFO] $1"; }

echo "═══════════════════════════════════════════"
echo " 화랑 Grid Agent 설치 검증 ($OS)"
echo "═══════════════════════════════════════════"

# ─── 1. 실행 파일 ───────────────────────────────────────────────────────
echo
echo "[1/6] 실행 파일 확인"

case "$OS" in
    darwin)
        APP="/Applications/Hwarang Grid Agent.app"
        BIN="$APP/Contents/MacOS/Hwarang Grid Agent"
        if [[ -d "$APP" ]]; then
            pass "$APP"
            [[ -x "$BIN" ]] && pass "실행 가능" || fail "실행 권한 없음: $BIN"
        else
            fail ".app 번들 없음"
        fi
        ;;
    linux)
        if command -v hwarang-grid &>/dev/null; then
            pass "$(command -v hwarang-grid)"
        elif [[ -x "/usr/local/bin/hwarang-grid" ]]; then
            pass "/usr/local/bin/hwarang-grid"
        else
            fail "hwarang-grid 바이너리 없음"
        fi
        ;;
    msys*|mingw*|cygwin*)
        BIN="$LOCALAPPDATA/HwarangGrid/hwarang-grid.exe"
        [[ -f "$BIN" ]] && pass "$BIN" || fail "$BIN 없음"
        ;;
esac

# ─── 2. 사용자 디렉토리 ─────────────────────────────────────────────────
echo
echo "[2/6] 사용자 디렉토리 확인"
if [[ -d "$HWARANG_DIR" ]]; then
    pass "$HWARANG_DIR"
    PERM="$(stat -f '%A' "$HWARANG_DIR" 2>/dev/null || stat -c '%a' "$HWARANG_DIR" 2>/dev/null)"
    if [[ "$PERM" == "700" ]]; then
        pass "권한 700"
    else
        warn "권한이 700 이 아님: $PERM (chmod 700 권장)"
    fi
    for sub in logs cache config; do
        [[ -d "$HWARANG_DIR/$sub" ]] && pass "$sub/" || warn "$sub/ 없음"
    done
else
    fail "$HWARANG_DIR 없음 (앱 첫 실행 시 자동 생성됨)"
fi

# ─── 3. GPU 드라이버 ────────────────────────────────────────────────────
echo
echo "[3/6] GPU 드라이버 확인"
if command -v nvidia-smi &>/dev/null; then
    GPU="$(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null | head -1)"
    if [[ -n "$GPU" ]]; then
        pass "NVIDIA: $GPU"
    else
        warn "nvidia-smi 있으나 응답 없음"
    fi
elif [[ "$OS" == "darwin" ]]; then
    METAL="$(system_profiler SPDisplaysDataType 2>/dev/null | grep -i 'Metal' | head -1)"
    [[ -n "$METAL" ]] && pass "Apple Metal: $METAL" || warn "GPU 정보 없음"
else
    warn "NVIDIA GPU 미감지 (CPU 모드로 동작 가능)"
fi

# ─── 4. 네트워크 ────────────────────────────────────────────────────────
echo
echo "[4/6] 네트워크 연결 확인"
if curl -fsS --max-time 5 https://hwarang.ai >/dev/null 2>&1 \
   || curl -fsS --max-time 5 https://api.hwarang.ai/health >/dev/null 2>&1; then
    pass "hwarang.ai 도달 가능"
else
    fail "hwarang.ai 도달 불가 (방화벽/네트워크 확인)"
fi

# ─── 5. 자동 시작 ───────────────────────────────────────────────────────
echo
echo "[5/6] 자동 시작 등록"
case "$OS" in
    darwin)
        PLIST="$HOME/Library/LaunchAgents/ai.hwarang.grid.plist"
        if [[ -f "$PLIST" ]]; then
            pass "LaunchAgent: $PLIST"
            launchctl list 2>/dev/null | grep -q ai.hwarang.grid && pass "load 됨" || warn "plist 있으나 load 안 됨"
        else
            warn "자동 시작 미설정"
        fi
        ;;
    linux)
        SVC="$HOME/.config/systemd/user/hwarang-grid.service"
        if [[ -f "$SVC" ]]; then
            pass "systemd: $SVC"
            systemctl --user is-enabled hwarang-grid.service &>/dev/null && pass "enable 됨" || warn "enable 안 됨"
        else
            warn "systemd user service 미등록"
        fi
        ;;
    msys*|mingw*|cygwin*)
        if reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v HwarangGrid &>/dev/null; then
            pass "HKCU\\...\\Run\\HwarangGrid 등록됨"
        else
            warn "자동 시작 레지스트리 없음"
        fi
        ;;
esac

# ─── 6. 에이전트 상태 (실행 중일 때) ────────────────────────────────────
echo
echo "[6/6] 에이전트 상태 (5초 이내 갱신 확인)"
if [[ -f "$STATUS_FILE" ]]; then
    NOW="$(date +%s)"
    MTIME="$(stat -f '%m' "$STATUS_FILE" 2>/dev/null || stat -c '%Y' "$STATUS_FILE" 2>/dev/null)"
    AGE=$((NOW - MTIME))
    if [[ $AGE -le 5 ]]; then
        pass "agent_status.json 갱신됨 (${AGE}초 전)"
    elif [[ $AGE -le 60 ]]; then
        warn "agent_status.json 오래됨 (${AGE}초 전 — 에이전트 정지 상태일 수 있음)"
    else
        warn "agent_status.json 매우 오래됨 (${AGE}초 전)"
    fi
else
    warn "$STATUS_FILE 없음 (앱 미실행 또는 첫 실행 전)"
fi

# ─── 결과 요약 ──────────────────────────────────────────────────────────
echo
echo "═══════════════════════════════════════════"
echo "  PASS: $PASS"
echo "  WARN: $WARN"
echo "  FAIL: $FAIL"
echo "═══════════════════════════════════════════"

if [[ $FAIL -eq 0 ]]; then
    echo -e "${GREEN}설치 검증 통과${NC}"
    exit 0
else
    echo -e "${RED}설치에 문제가 있습니다. 위 [FAIL] 항목 확인하세요.${NC}"
    exit 1
fi
