#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 화랑 AI 서버 전체 설치 & 실행 스크립트
# 서버: hwarangmain (RTX 5090 32GB / 128GB RAM)
# 웹서버: Apache2
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
err() { echo -e "${RED}[에러]${NC} $1"; }

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
# Database
DB_PASSWORD=hwarang_secure_2025
DATABASE_URL=postgresql://hwarang:hwarang_secure_2025@localhost:5432/hwarang

# Auth
NEXTAUTH_SECRET=hwarang-nextauth-secret-change-this-in-production
NEXTAUTH_URL=https://hwarang.ai
AUTH_TRUST_HOST=true

# API
API_SECRET_KEY=hwarang-api-secret-key-change-this
HWARANG_API_URL=http://localhost:8000

# Model
MODEL_DIR=/mnt/nvme2/hwarang/models
MODEL_NAME=hwarang-merged-v2
MODEL_PATH=/mnt/nvme2/hwarang/models/hwarang-merged-v2

# HFL
HFL_STORAGE=/mnt/nvme2/hwarang/hfl

# Redis
REDIS_URL=redis://localhost:6379/0
ENVEOF
log "  .env 파일 생성 완료"
else
log "  .env 파일 이미 존재"
fi

# ═══ 2단계: DB + Redis ═══
log "2단계: PostgreSQL + Redis"

sudo systemctl start postgresql 2>/dev/null || warn "PostgreSQL 시작 실패"
sudo -u postgres psql -c "CREATE USER hwarang WITH PASSWORD 'hwarang_secure_2025';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE hwarang OWNER hwarang;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE hwarang TO hwarang;" 2>/dev/null || true

sudo systemctl start redis-server 2>/dev/null || warn "Redis 시작 실패"

pg_isready -h localhost && log "  PostgreSQL ✅" || warn "  PostgreSQL ❌"
redis-cli ping 2>/dev/null | grep -q PONG && log "  Redis ✅" || warn "  Redis ❌"

# ═══ 3단계: API 서버 ═══
log "3단계: API 서버 (FastAPI + Grid/HFL 마스터)"
cd "$PROJECT_DIR/modules/hwarang-api"

poetry install --no-interaction 2>/dev/null || warn "poetry install 실패"

# 기존 프로세스 종료
pkill -f "uvicorn hwarang_api" 2>/dev/null || true
sleep 1

nohup poetry run uvicorn hwarang_api.main:create_app \
  --factory \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 2 \
  > $LOG_DIR/api.log 2>&1 &

sleep 3
curl -s http://localhost:8000/health > /dev/null && log "  API 서버 ✅ (포트 8000)" || warn "  API 서버 ❌"

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

  log "  vLLM 시작 중... (모델 로드 2-3분 소요)"
else
  warn "  모델 없음: $MODEL_DIR/hwarang-merged-v2"
  warn "  먼저 학습 + 머지를 완료하세요"
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
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 | grep -q "200\|308" && log "  웹 UI ✅ (포트 3000)" || warn "  웹 UI ❌"

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
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001 | grep -q "200\|308" && log "  관리자 ✅ (포트 3001)" || warn "  관리자 ❌"

# ═══ 7단계: Apache2 리버스 프록시 ═══
log "7단계: Apache2 리버스 프록시"

# 필요한 모듈 활성화
sudo a2enmod proxy proxy_http proxy_wstunnel rewrite headers ssl 2>/dev/null

# hwarang.ai 설정
sudo tee /etc/apache2/sites-available/hwarang.conf << 'APACHE'
<VirtualHost *:80>
    ServerName hwarang.ai
    ServerAlias www.hwarang.ai

    # HTTP → HTTPS 리다이렉트
    RewriteEngine On
    RewriteCond %{HTTPS} off
    RewriteRule ^(.*)$ https://%{HTTP_HOST}$1 [R=301,L]
</VirtualHost>

<VirtualHost *:443>
    ServerName hwarang.ai
    ServerAlias www.hwarang.ai

    # SSL (certbot이 자동 설정)
    # SSLEngine on
    # SSLCertificateFile /etc/letsencrypt/live/hwarang.ai/fullchain.pem
    # SSLCertificateKeyFile /etc/letsencrypt/live/hwarang.ai/privkey.pem

    # 보안 헤더
    Header always set X-Frame-Options DENY
    Header always set X-Content-Type-Options nosniff
    Header always set X-XSS-Protection "1; mode=block"
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"

    # ═══ API 프록시 ═══
    ProxyPreserveHost On

    # /api/* → FastAPI (포트 8000)
    ProxyPass /api/ http://127.0.0.1:8000/
    ProxyPassReverse /api/ http://127.0.0.1:8000/

    # /grid/* → Grid/HFL 마스터 (포트 8000)
    ProxyPass /grid/ http://127.0.0.1:8000/grid/
    ProxyPassReverse /grid/ http://127.0.0.1:8000/grid/

    # /v1/* → vLLM 모델 서빙 (포트 8080)
    ProxyPass /v1/ http://127.0.0.1:8080/v1/
    ProxyPassReverse /v1/ http://127.0.0.1:8080/v1/

    # ═══ SSE 스트리밍 설정 ═══
    # AI 채팅 스트리밍에 필수
    <Location /api/v1/chat/completions>
        ProxyPass http://127.0.0.1:8000/v1/chat/completions
        ProxyPassReverse http://127.0.0.1:8000/v1/chat/completions
        # 버퍼링 비활성화 (SSE)
        SetEnv proxy-sendcl 1
        SetEnv proxy-sendchunked 1
        RequestHeader set X-Forwarded-Proto "https"
    </Location>

    <Location /v1/chat/completions>
        ProxyPass http://127.0.0.1:8080/v1/chat/completions
        ProxyPassReverse http://127.0.0.1:8080/v1/chat/completions
        SetEnv proxy-sendcl 1
        SetEnv proxy-sendchunked 1
    </Location>

    # ═══ Grid LoRA 업로드 (100MB 허용) ═══
    <Location /grid/hfl/submit>
        LimitRequestBody 104857600
    </Location>

    # ═══ 웹 UI (Next.js) ═══
    # WebSocket 지원 (핫 리로드 등)
    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule ^/?(.*) ws://127.0.0.1:3000/$1 [P,L]

    # 정적 파일 캐시
    <Location /_next/static/>
        ProxyPass http://127.0.0.1:3000/_next/static/
        ProxyPassReverse http://127.0.0.1:3000/_next/static/
        Header set Cache-Control "public, max-age=31536000, immutable"
    </Location>

    # Next.js 프록시 (기본)
    ProxyPass / http://127.0.0.1:3000/
    ProxyPassReverse / http://127.0.0.1:3000/

    # 타임아웃 (AI 응답 대기)
    ProxyTimeout 300
    RequestHeader set X-Forwarded-Proto "https"
    RequestHeader set X-Real-IP %{REMOTE_ADDR}s

    # 로그
    ErrorLog ${APACHE_LOG_DIR}/hwarang-error.log
    CustomLog ${APACHE_LOG_DIR}/hwarang-access.log combined
</VirtualHost>
APACHE

# admin.hwarang.ai 설정
sudo tee /etc/apache2/sites-available/hwarang-admin.conf << 'APACHE'
<VirtualHost *:80>
    ServerName admin.hwarang.ai

    RewriteEngine On
    RewriteCond %{HTTPS} off
    RewriteRule ^(.*)$ https://%{HTTP_HOST}$1 [R=301,L]
</VirtualHost>

<VirtualHost *:443>
    ServerName admin.hwarang.ai

    # SSL
    # SSLEngine on
    # SSLCertificateFile /etc/letsencrypt/live/hwarang.ai/fullchain.pem
    # SSLCertificateKeyFile /etc/letsencrypt/live/hwarang.ai/privkey.pem

    # 보안 헤더
    Header always set X-Frame-Options DENY
    Header always set X-Content-Type-Options nosniff

    # API 프록시
    ProxyPreserveHost On
    ProxyPass /api/ http://127.0.0.1:8000/
    ProxyPassReverse /api/ http://127.0.0.1:8000/

    # Grid API
    ProxyPass /grid/ http://127.0.0.1:8000/grid/
    ProxyPassReverse /grid/ http://127.0.0.1:8000/grid/

    # 관리자 패널 (Next.js)
    ProxyPass / http://127.0.0.1:3001/
    ProxyPassReverse / http://127.0.0.1:3001/

    ProxyTimeout 60
    RequestHeader set X-Forwarded-Proto "https"

    ErrorLog ${APACHE_LOG_DIR}/hwarang-admin-error.log
    CustomLog ${APACHE_LOG_DIR}/hwarang-admin-access.log combined
</VirtualHost>
APACHE

# 사이트 활성화
sudo a2ensite hwarang.conf hwarang-admin.conf 2>/dev/null
sudo a2dissite 000-default.conf 2>/dev/null || true

# 설정 테스트 & 재시작
sudo apache2ctl configtest && sudo systemctl restart apache2
log "  Apache2 ✅"

# ═══ 8단계: SSL 인증서 ═══
log "8단계: SSL 인증서 (Let's Encrypt)"
if ! command -v certbot &> /dev/null; then
  sudo apt install -y certbot python3-certbot-apache 2>/dev/null
fi

# certbot 실행 (도메인 DNS가 서버 IP를 가리키고 있어야 함)
# sudo certbot --apache -d hwarang.ai -d www.hwarang.ai -d admin.hwarang.ai
warn "  SSL: sudo certbot --apache -d hwarang.ai -d www.hwarang.ai -d admin.hwarang.ai"
warn "  (도메인 DNS가 서버 IP를 가리키고 있어야 합니다)"

# ═══ 9단계: systemd 서비스 등록 ═══
log "9단계: systemd 서비스 (재부팅 시 자동 시작)"

sudo tee /etc/systemd/system/hwarang-api.service > /dev/null << EOF
[Unit]
Description=Hwarang API Server
After=postgresql.service redis-server.service

[Service]
Type=simple
User=perseismore
WorkingDirectory=$PROJECT_DIR/modules/hwarang-api
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$(which poetry || echo /home/perseismore/.local/bin/poetry) run uvicorn hwarang_api.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 2
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
ExecStart=$(which pnpm || echo /usr/bin/pnpm) start -- -p 3000
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
ExecStart=$(which pnpm || echo /usr/bin/pnpm) start -- -p 3001
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

check() {
  if $2 2>/dev/null; then
    echo -e "  ✅ $1"
  else
    echo -e "  ❌ $1"
  fi
}

check "PostgreSQL" "pg_isready -h localhost -p 5432 -q"
check "Redis" "redis-cli ping | grep -q PONG"
check "API 서버 (:8000)" "curl -sf http://localhost:8000/health > /dev/null"
check "Grid/HFL (:8000)" "curl -sf http://localhost:8000/grid/status > /dev/null"
check "웹 UI (:3000)" "curl -sf -o /dev/null http://localhost:3000"
check "관리자 (:3001)" "curl -sf -o /dev/null http://localhost:3001"
check "Apache2" "sudo apache2ctl configtest"

# vLLM은 로드 시간이 걸리므로 별도 확인
if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
  echo -e "  ✅ vLLM (:8080)"
else
  echo -e "  ⏳ vLLM (:8080) - 모델 로딩 중 (2-3분 대기)"
fi

echo ""
echo "═══════════════════════════════════════════"
echo " 접속 주소"
echo "═══════════════════════════════════════════"
echo "  웹:      https://hwarang.ai"
echo "  관리자:  https://admin.hwarang.ai"
echo "  API:     https://hwarang.ai/api/health"
echo "  Grid:    https://hwarang.ai/grid/status"
echo "  vLLM:    http://localhost:8080/v1/models"
echo ""
echo "═══════════════════════════════════════════"
echo " 관리 명령어"
echo "═══════════════════════════════════════════"
echo "  로그 확인:"
echo "    tail -f $LOG_DIR/api.log"
echo "    tail -f $LOG_DIR/vllm.log"
echo "    tail -f $LOG_DIR/web.log"
echo "    tail -f $LOG_DIR/admin.log"
echo ""
echo "  서비스 재시작:"
echo "    sudo systemctl restart hwarang-api"
echo "    sudo systemctl restart hwarang-web"
echo "    sudo systemctl restart hwarang-admin"
echo "    sudo systemctl restart hwarang-vllm"
echo ""
echo "  전체 재시작:"
echo "    sudo systemctl restart hwarang-{api,web,admin,vllm}"
echo ""
echo "  SSL 인증서:"
echo "    sudo certbot --apache -d hwarang.ai -d www.hwarang.ai -d admin.hwarang.ai"
echo "═══════════════════════════════════════════"
