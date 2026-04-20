"""화랑 AI DevOps/인프라 학습 데이터

Docker, Kubernetes, CI/CD, Nginx, 모니터링 등.

사용법:
    python scripts/data/build_devops_data.py \
        --output data/sft/devops.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 DevOps 엔지니어 수준의 인프라 어시스턴트입니다.
설명은 한국어로, 설정 파일과 명령어는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ Docker ═══
    m("Docker 멀티스테이지 빌드 알려줘",
'''멀티스테이지 빌드로 프로덕션 이미지 크기를 줄입니다.

```dockerfile
# ═══ Node.js (Next.js) 멀티스테이지 ═══

# 1단계: 의존성 설치
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable pnpm && pnpm install --frozen-lockfile

# 2단계: 빌드
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# 환경변수 주입
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# 3단계: 프로덕션 (최종 이미지)
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# 보안: non-root 사용자
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# 필요한 파일만 복사
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

```dockerfile
# ═══ Python (FastAPI) 멀티스테이지 ═══

# 1단계: 의존성 빌드
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install poetry
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt -o requirements.txt --without-hashes
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# 2단계: 프로덕션
FROM python:3.12-slim AS runner
WORKDIR /app

# 보안: non-root
RUN useradd --create-home appuser

# 빌드된 wheel만 설치
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY . .
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

이미지 크기 비교:
- 일반 빌드: ~1.2GB
- 멀티스테이지: ~150MB (90% 감소)'''),

    # ═══ Docker Compose ═══
    m("Docker Compose로 개발환경 구성해줘",
'''풀스택 개발환경을 Docker Compose로 구성합니다.

```yaml
# docker-compose.yml
services:
  # PostgreSQL
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: hwarang
      POSTGRES_USER: hwarang
      POSTGRES_PASSWORD: ${DB_PASSWORD:-devpassword}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hwarang"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  # FastAPI 백엔드
  api:
    build:
      context: ./modules/hwarang-api
      dockerfile: Dockerfile
      target: development  # 개발용 스테이지
    ports:
      - "8000:8000"
    volumes:
      - ./modules/hwarang-api:/app  # 핫 리로드
    environment:
      - DATABASE_URL=postgresql+asyncpg://hwarang:${DB_PASSWORD:-devpassword}@db:5432/hwarang
      - REDIS_URL=redis://redis:6379/0
      - DEBUG=true
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  # Next.js 프론트엔드
  web:
    build:
      context: ./modules/hwarang-web
      dockerfile: Dockerfile
      target: development
    ports:
      - "3000:3000"
    volumes:
      - ./modules/hwarang-web:/app
      - /app/node_modules  # node_modules는 컨테이너 것 사용
      - /app/.next          # .next도 컨테이너 것 사용
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      - api
    command: pnpm dev

  # Nginx 리버스 프록시 (프로덕션)
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./docker/nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./docker/nginx/certs:/etc/nginx/certs
    depends_on:
      - api
      - web
    profiles:
      - production  # docker compose --profile production up

volumes:
  postgres_data:
```

자주 쓰는 명령어:
```bash
# 개발 시작
docker compose up -d

# 로그 보기
docker compose logs -f api

# DB 초기화
docker compose down -v && docker compose up -d

# 프로덕션
docker compose --profile production up -d --build
```'''),

    # ═══ Nginx ═══
    m("Nginx 리버스 프록시 설정 알려줘",
'''Next.js + FastAPI 구성의 Nginx 설정입니다.

```nginx
# /etc/nginx/nginx.conf

worker_processes auto;
events {
    worker_connections 1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;

    # 로깅
    log_format main '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" '
                    'rt=$request_time';

    access_log /var/log/nginx/access.log main;
    error_log  /var/log/nginx/error.log warn;

    # 성능
    sendfile on;
    tcp_nopush on;
    keepalive_timeout 65;
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 1000;

    # Rate Limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

    # 업스트림
    upstream api_backend {
        server api:8000;
        keepalive 32;
    }

    upstream web_frontend {
        server web:3000;
        keepalive 32;
    }

    # HTTP → HTTPS 리다이렉트
    server {
        listen 80;
        server_name hwarang.ai www.hwarang.ai;
        return 301 https://$host$request_uri;
    }

    # 메인 사이트
    server {
        listen 443 ssl http2;
        server_name hwarang.ai www.hwarang.ai;

        # SSL
        ssl_certificate     /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;
        ssl_protocols       TLSv1.2 TLSv1.3;

        # 보안 헤더
        add_header X-Frame-Options DENY always;
        add_header X-Content-Type-Options nosniff always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Strict-Transport-Security "max-age=31536000" always;

        # API 프록시
        location /api/ {
            limit_req zone=api burst=20 nodelay;

            proxy_pass http://api_backend/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # SSE 스트리밍 지원
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 300s;
        }

        # WebSocket
        location /ws/ {
            proxy_pass http://api_backend/ws/;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_read_timeout 86400;
        }

        # 프론트엔드
        location / {
            proxy_pass http://web_frontend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        # 정적 파일 캐싱
        location /_next/static/ {
            proxy_pass http://web_frontend;
            expires 365d;
            add_header Cache-Control "public, immutable";
        }

        # 파일 업로드 크기 제한
        client_max_body_size 50M;
    }

    # 관리자 패널
    server {
        listen 443 ssl http2;
        server_name admin.hwarang.ai;

        ssl_certificate     /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;

        # IP 제한 (관리자만)
        allow 1.2.3.4;  # 사무실 IP
        deny all;

        location / {
            proxy_pass http://admin_frontend;
        }
    }
}
```

핵심 포인트:
- SSE 스트리밍: `proxy_buffering off` 필수
- WebSocket: `Upgrade` 헤더 전달
- Rate Limiting: API와 로그인에 별도 적용
- 관리자: IP 화이트리스트로 보호'''),

    # ═══ CI/CD ═══
    m("GitHub Actions CI/CD 파이프라인 알려줘",
'''풀스택 프로젝트의 CI/CD 파이프라인입니다.

```yaml
# .github/workflows/ci.yml
name: CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # ═══ 테스트 ═══
  test-api:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 5s --health-retries 5
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: 의존성 설치
        working-directory: modules/hwarang-api
        run: |
          pip install poetry
          poetry install

      - name: 린트
        working-directory: modules/hwarang-api
        run: |
          poetry run ruff check .
          poetry run mypy .

      - name: 테스트
        working-directory: modules/hwarang-api
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379/0
        run: poetry run pytest --cov=app --cov-report=xml -v

      - name: 커버리지 업로드
        uses: codecov/codecov-action@v4
        with:
          file: modules/hwarang-api/coverage.xml

  test-web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm

      - name: 의존성 설치
        working-directory: modules/hwarang-web
        run: pnpm install --frozen-lockfile

      - name: 린트 & 타입 체크
        working-directory: modules/hwarang-web
        run: |
          pnpm lint
          pnpm type-check

      - name: 테스트
        working-directory: modules/hwarang-web
        run: pnpm test -- --coverage

      - name: 빌드 확인
        working-directory: modules/hwarang-web
        run: pnpm build

  # ═══ Docker 빌드 & 배포 ═══
  deploy:
    needs: [test-api, test-web]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Docker 빌드 (API)
        uses: docker/build-push-action@v5
        with:
          context: modules/hwarang-api
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-api:latest

      - name: Docker 빌드 (Web)
        uses: docker/build-push-action@v5
        with:
          context: modules/hwarang-web
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-web:latest

      - name: 서버 배포
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /opt/hwarang
            docker compose pull
            docker compose up -d --remove-orphans
            docker system prune -f
```

핵심:
- PR 시 → 테스트만 실행
- main 머지 시 → 테스트 + 빌드 + 배포
- `services`로 테스트 DB/Redis 자동 실행
- `needs`로 테스트 통과 후에만 배포'''),

    # ═══ Kubernetes ═══
    m("Kubernetes 기본 배포 설정 알려줘",
'''K8s로 FastAPI + Next.js를 배포하는 설정입니다.

```yaml
# k8s/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hwarang-api
  labels:
    app: hwarang-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: hwarang-api
  template:
    metadata:
      labels:
        app: hwarang-api
    spec:
      containers:
        - name: api
          image: ghcr.io/persismore/hwarang-api:latest
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: hwarang-secrets
                  key: database-url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: hwarang-secrets
                  key: redis-url
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          # 헬스 체크
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          # 안전한 종료
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
      terminationGracePeriodSeconds: 30

---
# 서비스
apiVersion: v1
kind: Service
metadata:
  name: hwarang-api
spec:
  selector:
    app: hwarang-api
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP

---
# HPA (자동 스케일링)
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: hwarang-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: hwarang-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70

---
# Ingress (외부 접근)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hwarang-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "30"
spec:
  tls:
    - hosts:
        - hwarang.ai
        - api.hwarang.ai
      secretName: hwarang-tls
  rules:
    - host: api.hwarang.ai
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: hwarang-api
                port:
                  number: 80
    - host: hwarang.ai
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: hwarang-web
                port:
                  number: 80

---
# Secret (비밀 정보)
apiVersion: v1
kind: Secret
metadata:
  name: hwarang-secrets
type: Opaque
stringData:
  database-url: "postgresql+asyncpg://user:pass@db:5432/hwarang"
  redis-url: "redis://redis:6379/0"
```

배포 명령어:
```bash
# 적용
kubectl apply -f k8s/

# 상태 확인
kubectl get pods -l app=hwarang-api
kubectl logs -f deployment/hwarang-api

# 롤링 업데이트
kubectl set image deployment/hwarang-api api=ghcr.io/persismore/hwarang-api:v2

# 롤백
kubectl rollout undo deployment/hwarang-api
```'''),

    # ═══ 모니터링 ═══
    m("서버 모니터링 설정 알려줘 Prometheus Grafana",
'''Prometheus + Grafana로 모니터링을 구성합니다.

```yaml
# docker-compose.monitoring.yml
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/dashboards:/etc/grafana/provisioning/dashboards
    depends_on:
      - prometheus

  node-exporter:
    image: prom/node-exporter:latest
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro

  nvidia-exporter:
    image: nvcr.io/nvidia/k8s/dcgm-exporter:latest
    runtime: nvidia
    ports:
      - "9400:9400"
    environment:
      - NVIDIA_VISIBLE_DEVICES=all

volumes:
  prometheus_data:
  grafana_data:
```

```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alert_rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  - job_name: "fastapi"
    static_configs:
      - targets: ["api:8000"]
    metrics_path: "/metrics"

  - job_name: "node"
    static_configs:
      - targets: ["node-exporter:9100"]

  - job_name: "nvidia-gpu"
    static_configs:
      - targets: ["nvidia-exporter:9400"]
```

```python
# FastAPI에 메트릭 추가
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import FastAPI, Response

# 메트릭 정의
REQUEST_COUNT = Counter(
    "http_requests_total",
    "총 HTTP 요청 수",
    ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP 요청 처리 시간",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]
)
ACTIVE_REQUESTS = Gauge(
    "http_active_requests",
    "현재 처리 중인 요청 수"
)
GPU_MEMORY = Gauge("gpu_memory_used_bytes", "GPU 메모리 사용량")
MODEL_INFERENCE_TIME = Histogram(
    "model_inference_seconds",
    "모델 추론 시간",
    ["model_name"]
)

app = FastAPI()

@app.middleware("http")
async def metrics_middleware(request, call_next):
    ACTIVE_REQUESTS.inc()
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)
    ACTIVE_REQUESTS.dec()
    return response

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

```yaml
# monitoring/alert_rules.yml
groups:
  - name: hwarang-alerts
    rules:
      - alert: 높은_에러율
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "API 에러율 높음 ({{ $value }})"

      - alert: GPU_메모리_부족
        expr: gpu_memory_used_bytes / gpu_memory_total_bytes > 0.95
        for: 2m
        labels:
          severity: warning

      - alert: 응답_지연
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P95 응답 시간 5초 초과"
```

핵심 대시보드 항목:
- QPS (초당 요청 수)
- P50/P95/P99 응답 시간
- 에러율 (4xx, 5xx)
- GPU 사용률/메모리
- 활성 연결 수'''),

    # ═══ 서버 보안 ═══
    m("리눅스 서버 보안 설정 알려줘",
'''프로덕션 서버 기본 보안 설정입니다.

```bash
#!/bin/bash
# server_hardening.sh - 서버 보안 강화 스크립트

# 1. 시스템 업데이트
apt update && apt upgrade -y
apt install -y fail2ban ufw unattended-upgrades

# 2. 방화벽 (UFW)
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw enable

# 3. SSH 보안 강화
cat >> /etc/ssh/sshd_config << 'EOF'
# 패스워드 인증 비활성화 (키 인증만)
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
# 특정 사용자만 SSH 허용
AllowUsers deploy
EOF
systemctl restart sshd

# 4. Fail2ban (브루트포스 방지)
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = 22
logpath = /var/log/auth.log

[nginx-http-auth]
enabled = true
port = 80,443
logpath = /var/log/nginx/error.log
EOF
systemctl enable fail2ban
systemctl start fail2ban

# 5. 자동 보안 업데이트
dpkg-reconfigure -plow unattended-upgrades

# 6. 커널 보안 파라미터
cat >> /etc/sysctl.conf << 'EOF'
# SYN flood 방지
net.ipv4.tcp_syncookies = 1
# IP 스푸핑 방지
net.ipv4.conf.all.rp_filter = 1
# ICMP 리다이렉트 비활성화
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
# 로깅
net.ipv4.conf.all.log_martians = 1
EOF
sysctl -p

# 7. 로그 감사 설정
apt install -y auditd
auditctl -w /etc/passwd -p wa -k user_modification
auditctl -w /etc/shadow -p wa -k password_modification
auditctl -w /var/log/ -p wa -k log_modification

echo "✅ 서버 보안 설정 완료"
```

추가 보안 체크리스트:
- [ ] SSL/TLS 인증서 자동 갱신 (certbot)
- [ ] Docker 이미지 취약점 스캔 (trivy)
- [ ] 환경변수로 비밀정보 관리 (절대 코드에 하드코딩 금지)
- [ ] 정기 백업 + 복구 테스트
- [ ] 접근 로그 모니터링'''),

    # ═══ 백업 ═══
    m("서버 자동 백업 스크립트 알려줘",
'''PostgreSQL + 파일 자동 백업 스크립트입니다.

```bash
#!/bin/bash
# backup.sh - 자동 백업 스크립트
# crontab: 0 3 * * * /opt/scripts/backup.sh >> /var/log/backup.log 2>&1

set -euo pipefail

# 설정
BACKUP_DIR="/backup"
DB_NAME="hwarang"
DB_USER="hwarang"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)
S3_BUCKET="s3://hwarang-backups"

# 색상
GREEN='\\033[0;32m'
RED='\\033[0;31m'
NC='\\033[0m'

log() { echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# 1. PostgreSQL 백업
log "PostgreSQL 백업 시작..."
DB_BACKUP="$BACKUP_DIR/db/hwarang_${DATE}.sql.gz"
mkdir -p "$BACKUP_DIR/db"

pg_dump -U "$DB_USER" "$DB_NAME" \
    --format=custom \
    --compress=9 \
    --file="$DB_BACKUP"

DB_SIZE=$(du -sh "$DB_BACKUP" | cut -f1)
log "DB 백업 완료: $DB_BACKUP ($DB_SIZE)"

# 2. 업로드 파일 백업
log "파일 백업 시작..."
FILE_BACKUP="$BACKUP_DIR/files/uploads_${DATE}.tar.gz"
mkdir -p "$BACKUP_DIR/files"

tar -czf "$FILE_BACKUP" \
    --exclude="*.tmp" \
    -C /opt/hwarang uploads/

FILE_SIZE=$(du -sh "$FILE_BACKUP" | cut -f1)
log "파일 백업 완료: $FILE_BACKUP ($FILE_SIZE)"

# 3. 설정 파일 백업
CONFIG_BACKUP="$BACKUP_DIR/config/config_${DATE}.tar.gz"
mkdir -p "$BACKUP_DIR/config"

tar -czf "$CONFIG_BACKUP" \
    /etc/nginx/nginx.conf \
    /opt/hwarang/docker-compose.yml \
    /opt/hwarang/.env \
    2>/dev/null || true

# 4. S3 업로드 (선택)
if command -v aws &> /dev/null; then
    log "S3 업로드 중..."
    aws s3 cp "$DB_BACKUP" "$S3_BUCKET/db/"
    aws s3 cp "$FILE_BACKUP" "$S3_BUCKET/files/"
    log "S3 업로드 완료"
fi

# 5. 오래된 백업 삭제
log "오래된 백업 정리 (${RETENTION_DAYS}일 이전)..."
find "$BACKUP_DIR" -type f -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -type d -empty -delete

# 6. 결과 알림
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "═══════════════════════════════"
log "백업 완료!"
log "  DB:     $DB_SIZE"
log "  파일:   $FILE_SIZE"
log "  전체:   $TOTAL_SIZE"
log "  보관:   ${RETENTION_DAYS}일"
log "═══════════════════════════════"

# 슬랙 알림 (선택)
# curl -X POST "$SLACK_WEBHOOK" \
#   -H 'Content-type: application/json' \
#   -d "{\"text\": \"✅ 백업 완료: DB($DB_SIZE) + 파일($FILE_SIZE)\"}"
```

복구 명령어:
```bash
# DB 복구
pg_restore -U hwarang -d hwarang --clean backup.sql.gz

# 파일 복구
tar -xzf uploads_backup.tar.gz -C /opt/hwarang/
```

crontab 설정:
```
# 매일 새벽 3시 백업
0 3 * * * /opt/scripts/backup.sh >> /var/log/backup.log 2>&1

# 매주 일요일 전체 백업
0 2 * * 0 /opt/scripts/full_backup.sh >> /var/log/backup.log 2>&1
```'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/devops.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI DevOps/인프라 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  DevOps: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
