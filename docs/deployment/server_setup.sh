#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 화랑 AI 서버 전체 설치 & 실행 스크립트
# 서버: hwarangmain (RTX 5090 32GB / 128GB RAM)
# 웹서버: Nginx
# ═══════════════════════════════════════════════════════════════

set -e

PROJECT_DIR="/home/perseismore/hwarang.ai"
MODEL_DIR="/mnt/nvme2/hwarang/models"
HFL_DIR="/mnt/nvme2/hwarang/hfl"
LOG_DIR="/var/log/hwarang"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[경고]${NC} $1"; }

echo "═══════════════════════════════════════════"
echo " 화랑 AI 서버 전체 설치 & 실행"
echo "═══════════════════════════════════════════"
echo ""

# ═══ 0단계: 디렉토리 준비 ═══
log "0단계: 디렉토리 준비"
sudo mkdir -p $LOG_DIR $HFL_DIR
sudo chown -R perseismore:perseismore $LOG_DIR $HFL_DIR 2>/dev/null || true

# ═══ 1단계: 환경 변수 ═══
log "1단계: 환경 변수 설정"

if [ ! -f "$PROJECT_DIR/.env" ]; then
cat > "$PROJECT_DIR/.env" << 'ENVEOF'
DB_PASSWORD=hwarang_secure_2025
DATABASE_URL=postgresql://hwarang:hwarang_secure_2025@localhost:5432/hwarang
NEXTAUTH_SECRET=hwarang-nextauth-secret-change-this-in-production
NEXTAUTH_URL=https://hwarang.ai
AUTH_TRUST_HOST=true
API_SECRET_KEY=hwarang-api-secret-key-change-this
HWARANG_API_URL=http://localhost:8000
MODEL_DIR=/mnt/nvme2/hwarang/models
MODEL_NAME=hwarang-merged-v2
MODEL_PATH=/mnt/nvme2/hwarang/models/hwarang-merged-v2
HFL_STORAGE=/mnt/nvme2/hwarang/hfl
REDIS_URL=redis://localhost:6379/0
ENVEOF
log "  .env 생성 완료"
else
log "  .env 이미 존재"
fi

# ═══ 2단계: DB + Redis ═══
log "2단계: PostgreSQL + Redis"
sudo systemctl start postgresql 2>/dev/null || true
sudo -u postgres psql -c "CREATE USER hwarang WITH PASSWORD 'hwarang_secure_2025';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE hwarang OWNER hwarang;" 2>/dev/null || true
sudo systemctl start redis-server 2>/dev/null || true

pg_isready -h localhost && log "  PostgreSQL ✅" || warn "  PostgreSQL ❌"
redis-cli ping 2>/dev/null | grep -q PONG && log "  Redis ✅" || warn "  Redis ❌"

# ═══ 3단계: API 서버 ═══
log "3단계: API 서버 (FastAPI + Grid/HFL)"
cd "$PROJECT_DIR/modules/hwarang-api"
poetry install --no-interaction 2>/dev/null || true

pkill -f "uvicorn hwarang_api" 2>/dev/null || true
sleep 1

nohup poetry run uvicorn hwarang_api.main:create_app \
  --factory --host 0.0.0.0 --port 8000 --workers 2 \
  > $LOG_DIR/api.log 2>&1 &

sleep 3
curl -sf http://localhost:8000/health > /dev/null && log "  API ✅ (:8000)" || warn "  API ❌"

# ═══ 4단계: vLLM 모델 서빙 ═══
log "4단계: vLLM AI 모델 서빙"
cd "$PROJECT_DIR/modules/hwarang-core"

if [ -d "$MODEL_DIR/hwarang-merged-v2" ]; then
  pkill -f "vllm serve" 2>/dev/null || true
  sleep 2

  nohup poetry run vllm serve "$MODEL_DIR/hwarang-merged-v2" \
    --quantization bitsandbytes \
    --load-format bitsandbytes \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.95 \
    --enforce-eager \
    --port 8080 \
    > $LOG_DIR/vllm.log 2>&1 &

  log "  vLLM 시작 중 (모델 로드 2-3분)"
else
  warn "  모델 없음: $MODEL_DIR/hwarang-merged-v2"
fi

# ═══ 5단계: 웹 UI ═══
log "5단계: 웹 UI (hwarang.ai)"
cd "$PROJECT_DIR/modules/hwarang-web"

cat > .env.local << 'EOF'
NEXTAUTH_URL=https://hwarang.ai
NEXTAUTH_SECRET=hwarang-nextauth-secret-change-this-in-production
AUTH_TRUST_HOST=true
HWARANG_API_URL=http://localhost:8000
NEXT_PUBLIC_API_URL=https://hwarang.ai/api
EOF

pnpm install --frozen-lockfile 2>/dev/null || pnpm install
pnpm build 2>/dev/null

pkill -f "next-server.*3000" 2>/dev/null || true
sleep 1
nohup pnpm start -- -p 3000 > $LOG_DIR/web.log 2>&1 &
sleep 3
curl -sf -o /dev/null http://localhost:3000 && log "  웹 UI ✅ (:3000)" || warn "  웹 UI ❌"

# ═══ 6단계: 관리자 패널 ═══
log "6단계: 관리자 패널 (admin.hwarang.ai)"
cd "$PROJECT_DIR/modules/hwarang-admin"

cat > .env.local << 'EOF'
HWARANG_API_URL=http://localhost:8000
DATABASE_URL=postgresql://hwarang:hwarang_secure_2025@localhost:5432/hwarang
EOF

pnpm install --frozen-lockfile 2>/dev/null || pnpm install
pnpm build 2>/dev/null

pkill -f "next-server.*3001" 2>/dev/null || true
sleep 1
nohup pnpm start -- -p 3001 > $LOG_DIR/admin.log 2>&1 &
sleep 3
curl -sf -o /dev/null http://localhost:3001 && log "  관리자 ✅ (:3001)" || warn "  관리자 ❌"

# ═══ 7단계: Nginx 리버스 프록시 ═══
log "7단계: Nginx 리버스 프록시"

sudo apt install -y nginx 2>/dev/null || true

sudo tee /etc/nginx/sites-available/hwarang << 'NGINX'
# ═══ hwarang.ai ═══
server {
    listen 80;
    server_name hwarang.ai www.hwarang.ai;

    # HTTP → HTTPS 리다이렉트 (SSL 설정 후 활성화)
    # return 301 https://$host$request_uri;

    # ─── 보안 헤더 ───
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # ─── API 프록시 (FastAPI :8000) ───
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 스트리밍 (AI 채팅)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # ─── Grid/HFL 마스터 ───
    location /grid/ {
        proxy_pass http://127.0.0.1:8000/grid/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # LoRA 업로드 (최대 100MB)
        client_max_body_size 100M;
        proxy_read_timeout 300s;
    }

    # ─── vLLM AI 모델 (SSE 스트리밍) ───
    location /v1/ {
        proxy_pass http://127.0.0.1:8080/v1/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # SSE 스트리밍 필수
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        chunked_transfer_encoding on;
    }

    # ─── WebSocket ───
    location /ws/ {
        proxy_pass http://127.0.0.1:3000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # ─── Next.js 정적 파일 (1년 캐시) ───
    location /_next/static/ {
        proxy_pass http://127.0.0.1:3000/_next/static/;
        expires 365d;
        add_header Cache-Control "public, immutable";
    }

    # ─── Next.js 이미지 최적화 ───
    location /_next/image {
        proxy_pass http://127.0.0.1:3000/_next/image;
        proxy_set_header Host $host;
    }

    # ─── 웹 UI (Next.js :3000) ───
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket (HMR)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # ─── 파일 업로드 제한 ───
    client_max_body_size 50M;

    # ─── 로그 ───
    access_log /var/log/nginx/hwarang-access.log;
    error_log /var/log/nginx/hwarang-error.log;
}

# ═══ admin.hwarang.ai ═══
server {
    listen 80;
    server_name admin.hwarang.ai;

    # 보안 헤더
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;

    # API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 60s;
    }

    # Grid
    location /grid/ {
        proxy_pass http://127.0.0.1:8000/grid/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 100M;
    }

    # 관리자 패널 (Next.js :3001)
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # 정적 파일 캐시
    location /_next/static/ {
        proxy_pass http://127.0.0.1:3001/_next/static/;
        expires 365d;
        add_header Cache-Control "public, immutable";
    }

    access_log /var/log/nginx/hwarang-admin-access.log;
    error_log /var/log/nginx/hwarang-admin-error.log;
}
NGINX

# 사이트 활성화
sudo ln -sf /etc/nginx/sites-available/hwarang /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null

# 설정 테스트 & 재시작
sudo nginx -t && sudo systemctl restart nginx
log "  Nginx ✅"

# ═══ 8단계: SSL ═══
log "8단계: SSL 인증서 (Let's Encrypt)"
if ! command -v certbot &> /dev/null; then
  sudo apt install -y certbot python3-certbot-nginx 2>/dev/null
fi
warn "  SSL 설정: sudo certbot --nginx -d hwarang.ai -d www.hwarang.ai -d admin.hwarang.ai"

# ═══ 9단계: systemd 서비스 ═══
log "9단계: systemd 서비스 등록"

sudo tee /etc/systemd/system/hwarang-api.service > /dev/null << EOF
[Unit]
Description=Hwarang API Server
After=postgresql.service redis-server.service
[Service]
Type=simple
User=perseismore
WorkingDirectory=$PROJECT_DIR/modules/hwarang-api
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$(which poetry 2>/dev/null || echo /home/perseismore/.local/bin/poetry) run uvicorn hwarang_api.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/hwarang-web.service > /dev/null << EOF
[Unit]
Description=Hwarang Web UI
After=hwarang-api.service
[Service]
Type=simple
User=perseismore
WorkingDirectory=$PROJECT_DIR/modules/hwarang-web
EnvironmentFile=$PROJECT_DIR/modules/hwarang-web/.env.local
ExecStart=$(which pnpm 2>/dev/null || echo /usr/bin/pnpm) start -- -p 3000
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/hwarang-admin.service > /dev/null << EOF
[Unit]
Description=Hwarang Admin Panel
After=hwarang-api.service
[Service]
Type=simple
User=perseismore
WorkingDirectory=$PROJECT_DIR/modules/hwarang-admin
EnvironmentFile=$PROJECT_DIR/modules/hwarang-admin/.env.local
ExecStart=$(which pnpm 2>/dev/null || echo /usr/bin/pnpm) start -- -p 3001
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/hwarang-vllm.service > /dev/null << EOF
[Unit]
Description=Hwarang vLLM Model Serving
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR/modules/hwarang-core
ExecStart=/root/.cache/pypoetry/virtualenvs/hwarang-core-QjBp7HmI-py3.12/bin/vllm serve $MODEL_DIR/hwarang-merged-v2 --quantization bitsandbytes --load-format bitsandbytes --max-model-len 4096 --gpu-memory-utilization 0.95 --enforce-eager --port 8080
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable hwarang-api hwarang-web hwarang-admin hwarang-vllm 2>/dev/null
log "  systemd 등록 완료"

# ═══ 10단계: 최종 확인 ═══
echo ""
echo "═══════════════════════════════════════════"
echo " 서비스 상태 확인"
echo "═══════════════════════════════════════════"

check() { if eval "$2" 2>/dev/null; then echo -e "  ✅ $1"; else echo -e "  ❌ $1"; fi; }

check "PostgreSQL" "pg_isready -h localhost -q"
check "Redis" "redis-cli ping | grep -q PONG"
check "API (:8000)" "curl -sf http://localhost:8000/health > /dev/null"
check "Grid/HFL" "curl -sf http://localhost:8000/grid/status > /dev/null"
check "웹 UI (:3000)" "curl -sf -o /dev/null http://localhost:3000"
check "관리자 (:3001)" "curl -sf -o /dev/null http://localhost:3001"
check "Nginx" "sudo nginx -t 2>/dev/null"

if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
  echo -e "  ✅ vLLM (:8080)"
else
  echo -e "  ⏳ vLLM (:8080) - 모델 로딩 중"
fi

echo ""
echo "═══════════════════════════════════════════"
echo " 접속 주소"
echo "═══════════════════════════════════════════"
echo "  웹:     https://hwarang.ai"
echo "  관리자: https://admin.hwarang.ai"
echo "  API:    https://hwarang.ai/api/health"
echo "  Grid:   https://hwarang.ai/grid/status"
echo ""
echo " 관리 명령어"
echo "═══════════════════════════════════════════"
echo "  로그: tail -f $LOG_DIR/{api,vllm,web,admin}.log"
echo "  재시작: sudo systemctl restart hwarang-{api,web,admin,vllm}"
echo "  SSL: sudo certbot --nginx -d hwarang.ai -d www.hwarang.ai -d admin.hwarang.ai"
echo "═══════════════════════════════════════════"
