#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — Linux 첫 실행 / 설치 후 동작
#
# 동작:
#   1. ~/.hwarang/ 디렉토리 생성
#   2. systemd user service 등록 (자동시작)
#   3. NVIDIA 드라이버 / CUDA 감지
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

HWARANG_DIR="$HOME/.hwarang"
SVC_DIR="$HOME/.config/systemd/user"
SVC_FILE="$SVC_DIR/hwarang-grid.service"
BINARY="${HWARANG_BINARY:-/usr/local/bin/hwarang-grid}"

log()  { echo "[INFO] $*"; }
ok()   { echo "[ OK ] $*"; }
warn() { echo "[WARN] $*"; }

# 1. 사용자 디렉토리
log "사용자 디렉토리 초기화..."
mkdir -p "$HWARANG_DIR"/{logs,cache,config}
chmod 700 "$HWARANG_DIR"
ok "$HWARANG_DIR"

# 2. systemd user service
ENABLE_AUTOSTART="${HWARANG_AUTOSTART:-1}"
if [[ "$ENABLE_AUTOSTART" == "1" ]] && command -v systemctl &>/dev/null; then
    log "systemd user service 등록..."
    mkdir -p "$SVC_DIR"

    cat > "$SVC_FILE" <<UNIT
[Unit]
Description=Hwarang Grid Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${BINARY} --background
Restart=on-failure
RestartSec=5
StandardOutput=append:${HWARANG_DIR}/logs/agent.out.log
StandardError=append:${HWARANG_DIR}/logs/agent.err.log

# 리소스 제한 (호스트 보호)
CPUQuota=80%
MemoryMax=80%

[Install]
WantedBy=default.target
UNIT

    systemctl --user daemon-reload
    systemctl --user enable hwarang-grid.service
    # systemctl --user start hwarang-grid.service  # 즉시 시작은 사용자 선택
    ok "systemd user service 등록: $SVC_FILE"
    log "수동 시작: systemctl --user start hwarang-grid.service"
else
    log "자동 시작 비활성화 또는 systemd 없음"
fi

# 3. GPU 드라이버 감지
log "GPU 환경 감지..."
if command -v nvidia-smi &>/dev/null; then
    GPU="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
    if [[ -n "$GPU" ]]; then
        ok "NVIDIA GPU 감지: $GPU"
    else
        warn "nvidia-smi 있으나 GPU 응답 없음"
    fi
elif lspci 2>/dev/null | grep -qi 'nvidia'; then
    warn "NVIDIA GPU 발견되었으나 드라이버 미설치"
    warn "설치: https://www.nvidia.com/Download/index.aspx"
elif lspci 2>/dev/null | grep -qi 'amd\|radeon'; then
    log "AMD GPU 감지 (ROCm 지원 예정)"
else
    warn "GPU 감지 실패 (CPU 모드로 동작)"
fi

ok "초기화 완료"
echo "  사용자 데이터:    $HWARANG_DIR"
echo "  systemd service:  $SVC_FILE"
echo "  바이너리:         $BINARY"
