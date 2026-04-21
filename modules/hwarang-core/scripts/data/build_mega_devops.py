"""화랑 AI Docker/CI/CD 추가 학습 데이터

DevOps 실무 프로젝트 전체 코드 생성 학습.
"만들어줘" → 폴더 구조 + 각 파일 전체 코드 출력.

카테고리:
  - 마이크로서비스 아키텍처 (1건)
  - GitHub Actions CI/CD (1건)
  - Prometheus + Grafana 모니터링 (1건)
  - Kubernetes 배포 매니페스트 (1건)
  - Nginx + SSL 자동 갱신 (1건)
  - DB 백업/복원 자동화 (1건)
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
프로젝트 요청 시 폴더 구조와 각 파일의 전체 코드를 작성합니다.
실무에서 바로 사용할 수 있는 프로덕션 수준의 코드를 생성합니다.
설명은 한국어로, 코드는 완전한 형태로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 1. Docker 마이크로서비스 아키텍처 ═══
    m("Docker로 마이크로서비스 아키텍처 구성 만들어줘 전체 코드로",
'''Docker 기반 마이크로서비스 아키텍처를 구성해 드릴게요. API Gateway + Auth + User 서비스로 나누고, 내부 네트워크로 통신합니다.

## 폴더 구조

```
microservices/
├── docker-compose.yml
├── shared/
│   └── types.ts
├── gateway/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       └── index.ts
├── auth-service/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       └── index.ts
└── user-service/
    ├── Dockerfile
    ├── package.json
    └── src/
        └── index.ts
```

## docker-compose.yml

```yaml
version: "3.9"

services:
  gateway:
    build: ./gateway
    ports:
      - "3000:3000"
    environment:
      - AUTH_SERVICE_URL=http://auth-service:4001
      - USER_SERVICE_URL=http://user-service:4002
      - NODE_ENV=production
    depends_on:
      auth-service:
        condition: service_healthy
      user-service:
        condition: service_healthy
    networks:
      - backend
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  auth-service:
    build: ./auth-service
    environment:
      - JWT_SECRET=your-secret-key-change-in-prod
      - REDIS_URL=redis://redis:6379
      - NODE_ENV=production
    depends_on:
      - redis
    networks:
      - backend
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4001/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  user-service:
    build: ./user-service
    environment:
      - DATABASE_URL=postgresql://app:secret@postgres:5432/users
      - NODE_ENV=production
    depends_on:
      - postgres
    networks:
      - backend
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4002/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    networks:
      - backend

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: users
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
    volumes:
      - pg_data:/var/lib/postgresql/data
    networks:
      - backend

networks:
  backend:
    driver: bridge

volumes:
  redis_data:
  pg_data:
```

## shared/types.ts

```typescript
// 서비스 간 공유 타입 정의
export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  timestamp: string;
}

export interface User {
  id: string;
  email: string;
  name: string;
  createdAt: string;
}

export interface TokenPayload {
  userId: string;
  email: string;
  iat: number;
  exp: number;
}

export interface HealthStatus {
  service: string;
  status: "ok" | "error";
  uptime: number;
  version: string;
}
```

## gateway/Dockerfile

```dockerfile
FROM node:20-alpine
WORKDIR /app
RUN apk add --no-cache curl
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev
COPY src/ ./src/
EXPOSE 3000
CMD ["node", "src/index.ts"]
```

## gateway/package.json

```json
{
  "name": "api-gateway",
  "version": "1.0.0",
  "scripts": { "start": "node src/index.ts", "dev": "tsx watch src/index.ts" },
  "dependencies": {
    "express": "^4.18.2",
    "http-proxy-middleware": "^3.0.0",
    "cors": "^2.8.5",
    "helmet": "^7.1.0",
    "morgan": "^1.10.0",
    "express-rate-limit": "^7.1.5"
  }
}
```

## gateway/src/index.ts

```typescript
import express from "express";
import cors from "cors";
import helmet from "helmet";
import morgan from "morgan";
import rateLimit from "express-rate-limit";
import { createProxyMiddleware } from "http-proxy-middleware";

const app = express();
const PORT = 3000;

// 미들웨어
app.use(helmet());
app.use(cors({ origin: process.env.ALLOWED_ORIGINS?.split(",") || "*" }));
app.use(morgan("combined"));
app.use(rateLimit({ windowMs: 15 * 60 * 1000, max: 100 }));

// 헬스 체크
app.get("/health", (_req, res) => {
  res.json({ service: "gateway", status: "ok", uptime: process.uptime() });
});

// Auth 서비스 프록시
app.use("/api/auth", createProxyMiddleware({
  target: process.env.AUTH_SERVICE_URL || "http://auth-service:4001",
  changeOrigin: true,
  pathRewrite: { "^/api/auth": "/auth" },
}));

// User 서비스 프록시
app.use("/api/users", createProxyMiddleware({
  target: process.env.USER_SERVICE_URL || "http://user-service:4002",
  changeOrigin: true,
  pathRewrite: { "^/api/users": "/users" },
}));

// 404 핸들러
app.use((_req, res) => {
  res.status(404).json({ success: false, error: "Route not found" });
});

app.listen(PORT, () => console.log(`Gateway running on :${PORT}`));
```

## auth-service/Dockerfile

```dockerfile
FROM node:20-alpine
WORKDIR /app
RUN apk add --no-cache curl
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev
COPY src/ ./src/
EXPOSE 4001
CMD ["node", "src/index.ts"]
```

## auth-service/src/index.ts

```typescript
import express from "express";
import jwt from "jsonwebtoken";
import bcrypt from "bcryptjs";

const app = express();
app.use(express.json());

const JWT_SECRET = process.env.JWT_SECRET || "dev-secret";
const users = new Map<string, { id: string; email: string; password: string }>();

app.get("/health", (_req, res) => {
  res.json({ service: "auth-service", status: "ok", uptime: process.uptime() });
});

// 회원가입
app.post("/auth/register", async (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) return res.status(400).json({ error: "이메일과 비밀번호 필수" });
  if (users.has(email)) return res.status(409).json({ error: "이미 가입된 이메일" });
  const hashed = await bcrypt.hash(password, 12);
  const id = crypto.randomUUID();
  users.set(email, { id, email, password: hashed });
  const token = jwt.sign({ userId: id, email }, JWT_SECRET, { expiresIn: "24h" });
  res.status(201).json({ success: true, data: { token, userId: id } });
});

// 로그인
app.post("/auth/login", async (req, res) => {
  const { email, password } = req.body;
  const user = users.get(email);
  if (!user || !(await bcrypt.compare(password, user.password))) {
    return res.status(401).json({ error: "인증 실패" });
  }
  const token = jwt.sign({ userId: user.id, email }, JWT_SECRET, { expiresIn: "24h" });
  res.json({ success: true, data: { token, userId: user.id } });
});

// 토큰 검증 (내부 서비스용)
app.post("/auth/verify", (req, res) => {
  const { token } = req.body;
  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    res.json({ success: true, data: decoded });
  } catch {
    res.status(401).json({ success: false, error: "유효하지 않은 토큰" });
  }
});

app.listen(4001, () => console.log("Auth service running on :4001"));
```

## user-service/src/index.ts

```typescript
import express from "express";

const app = express();
app.use(express.json());

interface User { id: string; email: string; name: string; createdAt: string; }
const store = new Map<string, User>();

app.get("/health", (_req, res) => {
  res.json({ service: "user-service", status: "ok", uptime: process.uptime() });
});

// 사용자 목록
app.get("/users", (_req, res) => {
  res.json({ success: true, data: Array.from(store.values()) });
});

// 사용자 조회
app.get("/users/:id", (req, res) => {
  const user = store.get(req.params.id);
  if (!user) return res.status(404).json({ error: "사용자 없음" });
  res.json({ success: true, data: user });
});

// 사용자 생성
app.post("/users", (req, res) => {
  const { id, email, name } = req.body;
  const user: User = { id, email, name, createdAt: new Date().toISOString() };
  store.set(id, user);
  res.status(201).json({ success: true, data: user });
});

// 사용자 수정
app.patch("/users/:id", (req, res) => {
  const user = store.get(req.params.id);
  if (!user) return res.status(404).json({ error: "사용자 없음" });
  const updated = { ...user, ...req.body, id: user.id };
  store.set(user.id, updated);
  res.json({ success: true, data: updated });
});

app.listen(4002, () => console.log("User service running on :4002"));
```

각 서비스가 독립 컨테이너로 실행되고, Gateway가 라우팅을 담당합니다. `docker compose up --build`로 전체를 시작하세요.'''),

    # ═══ 2. GitHub Actions CI/CD 파이프라인 ═══
    m("GitHub Actions + Docker로 CI/CD 파이프라인 만들어줘 전체 코드로",
'''GitHub Actions로 CI(린트, 테스트, 빌드)와 CD(도커 이미지 빌드 + 배포)를 구성해 드릴게요.

## 폴더 구조

```
my-app/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── cd.yml
├── Dockerfile
├── .dockerignore
├── package.json
├── eslint.config.js
├── src/
│   └── index.ts
├── tests/
│   └── index.test.ts
└── scripts/
    └── notify-slack.sh
```

## .github/workflows/ci.yml

```yaml
name: CI Pipeline

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

env:
  NODE_VERSION: "20"

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: "npm"
      - run: npm ci
      - run: npm run lint

  test:
    name: Test
    runs-on: ubuntu-latest
    needs: lint
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: "npm"
      - run: npm ci
      - run: npm test -- --coverage
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
      - uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage/

  build:
    name: Docker Build Check
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          cache-from: type=gha
          cache-to: type=gha,mode=max
          tags: app:ci-${{ github.sha }}
```

## .github/workflows/cd.yml

```yaml
name: CD Pipeline

on:
  push:
    tags: ["v*.*.*"]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    name: Build & Push Image
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha

      - uses: docker/setup-buildx-action@v3

      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    name: Deploy to Server
    runs-on: ubuntu-latest
    needs: build-and-push
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: SSH 배포
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            cd /opt/app
            docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.ref_name }}
            docker compose down
            export IMAGE_TAG=${{ github.ref_name }}
            docker compose up -d
            docker image prune -f

      - name: Slack 알림
        if: always()
        env:
          SLACK_WEBHOOK: ${{ secrets.SLACK_WEBHOOK_URL }}
          DEPLOY_STATUS: ${{ job.status }}
          TAG: ${{ github.ref_name }}
        run: bash scripts/notify-slack.sh
```

## Dockerfile

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
USER appuser
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s CMD wget -q --spider http://localhost:3000/health || exit 1
CMD ["node", "dist/index.js"]
```

## .dockerignore

```
node_modules
.git
.github
coverage
*.md
.env*
tests
```

## scripts/notify-slack.sh

```bash
#!/usr/bin/env bash
# Slack 배포 알림 스크립트
set -euo pipefail

if [ "$DEPLOY_STATUS" = "success" ]; then
  COLOR="#36a64f"
  EMOJI=":white_check_mark:"
  TEXT="배포 성공"
else
  COLOR="#ff0000"
  EMOJI=":x:"
  TEXT="배포 실패"
fi

PAYLOAD=$(cat <<EOF
{
  "attachments": [{
    "color": "${COLOR}",
    "blocks": [
      {
        "type": "section",
        "text": {
          "type": "mrkdwn",
          "text": "${EMOJI} *${TEXT}*\\n*태그:* ${TAG}\\n*레포:* ${GITHUB_REPOSITORY}\\n*커밋:* ${GITHUB_SHA:0:7}"
        }
      }
    ]
  }]
}
EOF
)

curl -s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" "$SLACK_WEBHOOK"
echo "Slack 알림 전송 완료"
```

## eslint.config.js

```javascript
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "no-console": "warn",
    },
  },
  { ignores: ["dist/", "coverage/"] }
);
```

## tests/index.test.ts

```typescript
import { describe, it, expect } from "vitest";

describe("Health Check", () => {
  it("서버 상태 확인", async () => {
    const res = await fetch("http://localhost:3000/health");
    const data = await res.json();
    expect(res.status).toBe(200);
    expect(data.status).toBe("ok");
  });
});
```

Repository Secrets에 `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `SLACK_WEBHOOK_URL`을 등록하세요. 태그 push 시 자동으로 이미지 빌드 → GHCR 푸시 → SSH 배포 → Slack 알림이 실행됩니다.'''),

    # ═══ 3. Prometheus + Grafana 모니터링 ═══
    m("Docker + Prometheus + Grafana 모니터링 스택 만들어줘 전체 코드로",
'''Prometheus + Grafana 모니터링 스택을 Docker로 구성해 드릴게요. Node.js 앱에서 메트릭을 수집하고, 알림 규칙까지 설정합니다.

## 폴더 구조

```
monitoring-stack/
├── docker-compose.yml
├── prometheus/
│   ├── prometheus.yml
│   └── alert-rules.yml
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── prometheus.yml
│   │   └── dashboards/
│   │       ├── dashboard.yml
│   │       └── app-dashboard.json
│   └── grafana.ini
└── app/
    ├── Dockerfile
    ├── package.json
    └── src/
        └── index.ts
```

## docker-compose.yml

```yaml
version: "3.9"

services:
  app:
    build: ./app
    ports:
      - "3000:3000"
    networks:
      - monitoring

  prometheus:
    image: prom/prometheus:v2.51.0
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus/alert-rules.yml:/etc/prometheus/alert-rules.yml
      - prom_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=30d"
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:10.4.0
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/grafana.ini:/etc/grafana/grafana.ini
      - grafana_data:/var/lib/grafana
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin123
    depends_on:
      - prometheus
    networks:
      - monitoring

  alertmanager:
    image: prom/alertmanager:v0.27.0
    ports:
      - "9093:9093"
    networks:
      - monitoring

networks:
  monitoring:
    driver: bridge

volumes:
  prom_data:
  grafana_data:
```

## prometheus/prometheus.yml

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alert-rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]

  - job_name: "app"
    metrics_path: "/metrics"
    static_configs:
      - targets: ["app:3000"]
        labels:
          service: "my-app"
          environment: "production"
```

## prometheus/alert-rules.yml

```yaml
groups:
  - name: app_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "에러율 5% 초과"
          description: "{{ $labels.instance }}에서 에러율 {{ $value | humanizePercentage }}"

      - alert: HighResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P95 응답시간 1초 초과"

      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes / 1024 / 1024 > 512
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "메모리 사용량 512MB 초과"

      - alert: AppDown
        expr: up{job="app"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "앱 서비스 다운"
```

## grafana/provisioning/datasources/prometheus.yml

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

## grafana/provisioning/dashboards/dashboard.yml

```yaml
apiVersion: 1
providers:
  - name: "default"
    orgId: 1
    folder: ""
    type: file
    options:
      path: /etc/grafana/provisioning/dashboards
```

## grafana/provisioning/dashboards/app-dashboard.json

```json
{
  "dashboard": {
    "title": "App Monitoring",
    "uid": "app-main",
    "panels": [
      {
        "title": "초당 요청 수 (RPS)",
        "type": "timeseries",
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 0 },
        "targets": [{
          "expr": "sum(rate(http_requests_total[5m]))",
          "legendFormat": "RPS"
        }]
      },
      {
        "title": "응답 시간 (P50/P95/P99)",
        "type": "timeseries",
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 0 },
        "targets": [
          { "expr": "histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[5m]))", "legendFormat": "P50" },
          { "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))", "legendFormat": "P95" },
          { "expr": "histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))", "legendFormat": "P99" }
        ]
      },
      {
        "title": "HTTP 상태 코드 분포",
        "type": "piechart",
        "gridPos": { "h": 8, "w": 8, "x": 0, "y": 8 },
        "targets": [{
          "expr": "sum by (status) (increase(http_requests_total[1h]))",
          "legendFormat": "{{status}}"
        }]
      },
      {
        "title": "메모리 사용량 (MB)",
        "type": "stat",
        "gridPos": { "h": 8, "w": 8, "x": 8, "y": 8 },
        "targets": [{
          "expr": "process_resident_memory_bytes / 1024 / 1024",
          "legendFormat": "RSS"
        }]
      },
      {
        "title": "활성 연결 수",
        "type": "gauge",
        "gridPos": { "h": 8, "w": 8, "x": 16, "y": 8 },
        "targets": [{
          "expr": "active_connections",
          "legendFormat": "connections"
        }]
      }
    ],
    "time": { "from": "now-1h", "to": "now" },
    "refresh": "10s"
  }
}
```

## app/package.json

```json
{
  "name": "monitored-app",
  "version": "1.0.0",
  "scripts": { "start": "node src/index.ts", "dev": "tsx watch src/index.ts" },
  "dependencies": {
    "express": "^4.18.2",
    "prom-client": "^15.1.0"
  }
}
```

## app/src/index.ts

```typescript
import express from "express";
import client from "prom-client";

const app = express();

// 기본 메트릭 수집 (CPU, 메모리, GC 등)
client.collectDefaultMetrics({ prefix: "" });

// 커스텀 메트릭
const httpRequestsTotal = new client.Counter({
  name: "http_requests_total",
  help: "Total HTTP requests",
  labelNames: ["method", "path", "status"],
});

const httpRequestDuration = new client.Histogram({
  name: "http_request_duration_seconds",
  help: "HTTP request duration in seconds",
  labelNames: ["method", "path"],
  buckets: [0.01, 0.05, 0.1, 0.3, 0.5, 1, 2, 5],
});

const activeConnections = new client.Gauge({
  name: "active_connections",
  help: "Number of active connections",
});

// 메트릭 수집 미들웨어
app.use((req, res, next) => {
  activeConnections.inc();
  const end = httpRequestDuration.startTimer({ method: req.method, path: req.path });
  res.on("finish", () => {
    httpRequestsTotal.inc({ method: req.method, path: req.path, status: res.statusCode });
    end();
    activeConnections.dec();
  });
  next();
});

app.get("/health", (_req, res) => res.json({ status: "ok" }));

app.get("/api/data", (_req, res) => {
  res.json({ message: "모니터링 대상 API", timestamp: new Date().toISOString() });
});

// Prometheus 메트릭 엔드포인트
app.get("/metrics", async (_req, res) => {
  res.set("Content-Type", client.register.contentType);
  res.end(await client.register.metrics());
});

app.listen(3000, () => console.log("App with metrics on :3000"));
```

`docker compose up -d`로 시작 후, Grafana(http://localhost:3001)에 접속하면 자동 프로비저닝된 대시보드를 확인할 수 있습니다.'''),

    # ═══ 4. Kubernetes 배포 매니페스트 ═══
    m("Kubernetes 배포 매니페스트 전체 만들어줘 전체 코드로",
'''Kubernetes 프로덕션 배포에 필요한 전체 매니페스트를 만들어 드릴게요. Kustomize로 환경별 관리까지 포함합니다.

## 폴더 구조

```
k8s/
├── kustomization.yaml
├── namespace.yaml
├── deployment.yaml
├── service.yaml
├── ingress.yaml
├── configmap.yaml
├── secret.yaml
├── hpa.yaml
├── pdb.yaml
└── overlays/
    └── production/
        └── kustomization.yaml
```

## kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: my-app

resources:
  - namespace.yaml
  - configmap.yaml
  - secret.yaml
  - deployment.yaml
  - service.yaml
  - ingress.yaml
  - hpa.yaml
  - pdb.yaml

commonLabels:
  app.kubernetes.io/name: my-app
  app.kubernetes.io/managed-by: kustomize
```

## namespace.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: my-app
  labels:
    app.kubernetes.io/name: my-app
```

## configmap.yaml

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: my-app
data:
  NODE_ENV: "production"
  LOG_LEVEL: "info"
  PORT: "3000"
  CACHE_TTL: "3600"
  MAX_CONNECTIONS: "100"
```

## secret.yaml

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
  namespace: my-app
type: Opaque
stringData:
  DATABASE_URL: "postgresql://user:password@db-host:5432/myapp"
  JWT_SECRET: "change-this-in-production"
  REDIS_URL: "redis://:password@redis-host:6379"
```

## deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: my-app
spec:
  replicas: 3
  revisionHistoryLimit: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app.kubernetes.io/name: my-app
  template:
    metadata:
      labels:
        app.kubernetes.io/name: my-app
    spec:
      serviceAccountName: default
      terminationGracePeriodSeconds: 30
      containers:
        - name: app
          image: ghcr.io/myorg/my-app:latest
          ports:
            - name: http
              containerPort: 3000
              protocol: TCP
          envFrom:
            - configMapRef:
                name: app-config
            - secretRef:
                name: app-secrets
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /health
              port: http
            failureThreshold: 30
            periodSeconds: 2
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: my-app
```

## service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app
  namespace: my-app
spec:
  type: ClusterIP
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
  selector:
    app.kubernetes.io/name: my-app
---
apiVersion: v1
kind: Service
metadata:
  name: my-app-external
  namespace: my-app
spec:
  type: LoadBalancer
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
  selector:
    app.kubernetes.io/name: my-app
```

## ingress.yaml

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
  namespace: my-app
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - app.example.com
      secretName: app-tls-cert
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app
                port:
                  name: http
```

## hpa.yaml

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: my-app
  namespace: my-app
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30
      policies:
        - type: Pods
          value: 2
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Pods
          value: 1
          periodSeconds: 60
```

## pdb.yaml

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app
  namespace: my-app
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: my-app
```

## overlays/production/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../

patches:
  - target:
      kind: Deployment
      name: my-app
    patch: |
      - op: replace
        path: /spec/replicas
        value: 5
      - op: replace
        path: /spec/template/spec/containers/0/resources/requests/cpu
        value: 250m
      - op: replace
        path: /spec/template/spec/containers/0/resources/limits/cpu
        value: "1"
      - op: replace
        path: /spec/template/spec/containers/0/resources/limits/memory
        value: 1Gi
```

배포 명령: `kubectl apply -k k8s/` (기본) 또는 `kubectl apply -k k8s/overlays/production/` (프로덕션). HPA가 CPU 70%, 메모리 80% 기준으로 3~20개 Pod를 자동 스케일링합니다.'''),

    # ═══ 5. Nginx + SSL 자동 갱신 ═══
    m("Docker + Nginx + SSL 자동 갱신 구성 만들어줘 전체 코드로",
'''Docker + Nginx + Let\'s Encrypt SSL 자동 갱신 구성을 만들어 드릴게요. 초기 인증서 발급부터 자동 갱신까지 포함합니다.

## 폴더 구조

```
nginx-ssl/
├── docker-compose.yml
├── nginx/
│   ├── nginx.conf
│   └── conf.d/
│       └── default.conf
├── certbot/
│   └── renewal-hooks/
│       └── deploy/
│           └── reload-nginx.sh
├── scripts/
│   ├── init-letsencrypt.sh
│   └── cron-renew.sh
├── app/
│   ├── Dockerfile
│   └── src/
│       └── index.ts
└── .env
```

## docker-compose.yml

```yaml
version: "3.9"

services:
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - certbot_certs:/etc/letsencrypt:ro
      - certbot_www:/var/www/certbot:ro
    depends_on:
      - app
    restart: unless-stopped
    networks:
      - frontend

  app:
    build: ./app
    expose:
      - "3000"
    restart: unless-stopped
    networks:
      - frontend

  certbot:
    image: certbot/certbot:latest
    volumes:
      - certbot_certs:/etc/letsencrypt
      - certbot_www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew --webroot -w /var/www/certbot --quiet; sleep 12h & wait $${!}; done;'"
    restart: unless-stopped

volumes:
  certbot_certs:
  certbot_www:

networks:
  frontend:
    driver: bridge
```

## nginx/nginx.conf

```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # 로깅
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent"';
    access_log /var/log/nginx/access.log main;

    # 성능
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;

    # 보안 헤더
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Rate Limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

    include /etc/nginx/conf.d/*.conf;
}
```

## nginx/conf.d/default.conf

```nginx
# HTTP → HTTPS 리다이렉트
server {
    listen 80;
    server_name example.com www.example.com;

    # Certbot ACME 챌린지
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS 메인 서버
server {
    listen 443 ssl http2;
    server_name example.com www.example.com;

    # SSL 인증서
    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    # SSL 보안 설정
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    # 앱 프록시
    location / {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://app:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # 정적 파일 캐싱
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2)$ {
        proxy_pass http://app:3000;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

## scripts/init-letsencrypt.sh

```bash
#!/usr/bin/env bash
# 최초 SSL 인증서 발급 스크립트
set -euo pipefail

DOMAIN="${1:?도메인을 입력하세요 (예: example.com)}"
EMAIL="${2:?이메일을 입력하세요}"
STAGING="${3:-0}"  # 1이면 스테이징 (테스트용)

echo "=== Let's Encrypt SSL 인증서 발급 ==="
echo "도메인: $DOMAIN"
echo "이메일: $EMAIL"

# 스테이징 옵션
STAGING_ARG=""
if [ "$STAGING" = "1" ]; then
  STAGING_ARG="--staging"
  echo "모드: 스테이징 (테스트)"
fi

# 임시 자체 서명 인증서 생성 (Nginx 시작용)
echo "1) 임시 인증서 생성..."
docker compose run --rm --entrypoint "\
  mkdir -p /etc/letsencrypt/live/$DOMAIN && \
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
    -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
    -subj '/CN=localhost'" certbot

# Nginx 시작
echo "2) Nginx 시작..."
docker compose up -d nginx
sleep 5

# 임시 인증서 삭제
echo "3) 임시 인증서 삭제..."
docker compose run --rm --entrypoint "\
  rm -rf /etc/letsencrypt/live/$DOMAIN && \
  rm -rf /etc/letsencrypt/archive/$DOMAIN && \
  rm -rf /etc/letsencrypt/renewal/$DOMAIN.conf" certbot

# 실제 인증서 발급
echo "4) Let's Encrypt 인증서 발급..."
docker compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $STAGING_ARG \
    --email $EMAIL \
    --agree-tos --no-eff-email \
    -d $DOMAIN -d www.$DOMAIN \
    --force-renewal" certbot

# Nginx 재시작
echo "5) Nginx 재시작..."
docker compose exec nginx nginx -s reload

echo "=== SSL 인증서 발급 완료! ==="
```

## scripts/cron-renew.sh

```bash
#!/usr/bin/env bash
# 크론 갱신 스크립트 - 호스트 크론탭에 등록
# 0 3 * * 1 /path/to/cron-renew.sh >> /var/log/certbot-renew.log 2>&1
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$COMPOSE_DIR"

echo "[$(date)] SSL 인증서 갱신 시작"

docker compose run --rm certbot certbot renew --quiet

# 갱신 성공 시 Nginx 리로드
if [ $? -eq 0 ]; then
  docker compose exec -T nginx nginx -s reload
  echo "[$(date)] Nginx 리로드 완료"
fi

echo "[$(date)] SSL 갱신 완료"
```

## .env

```bash
DOMAIN=example.com
EMAIL=admin@example.com
```

## app/Dockerfile

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev
COPY src/ ./src/
EXPOSE 3000
CMD ["node", "src/index.ts"]
```

## app/src/index.ts

```typescript
import express from "express";

const app = express();

app.get("/health", (_req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

app.get("/", (_req, res) => {
  res.json({ message: "SSL 적용된 앱입니다", secure: true });
});

app.listen(3000, () => console.log("App running on :3000"));
```

사용법: `chmod +x scripts/*.sh && bash scripts/init-letsencrypt.sh example.com admin@example.com` 후 `docker compose up -d`로 실행하세요.'''),

    # ═══ 6. DB 백업/복원 자동화 ═══
    m("Docker로 데이터베이스 백업/복원 자동화 만들어줘 전체 코드로",
'''PostgreSQL 백업/복원 자동화를 Docker로 구성해 드릴게요. S3 업로드, 30일 로테이션, 크론 스케줄링까지 포함합니다.

## 폴더 구조

```
db-backup/
├── docker-compose.yml
├── backup/
│   ├── Dockerfile
│   ├── backup.sh
│   ├── restore.sh
│   ├── rotate.sh
│   ├── upload-s3.sh
│   └── crontab
├── .env
└── scripts/
    └── manual-backup.sh
```

## docker-compose.yml

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${DB_NAME:-myapp}
      POSTGRES_USER: ${DB_USER:-appuser}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-secret}
    volumes:
      - pg_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-appuser}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - db-net

  backup:
    build: ./backup
    environment:
      - PGHOST=postgres
      - PGPORT=5432
      - PGDATABASE=${DB_NAME:-myapp}
      - PGUSER=${DB_USER:-appuser}
      - PGPASSWORD=${DB_PASSWORD:-secret}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - AWS_DEFAULT_REGION=${AWS_REGION:-ap-northeast-2}
      - S3_BUCKET=${S3_BUCKET:-my-db-backups}
      - BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}
      - BACKUP_DIR=/backups
    volumes:
      - backup_data:/backups
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - db-net

volumes:
  pg_data:
  backup_data:

networks:
  db-net:
    driver: bridge
```

## backup/Dockerfile

```dockerfile
FROM alpine:3.19

RUN apk add --no-cache \
    postgresql16-client \
    aws-cli \
    bash \
    gzip \
    curl \
    tzdata

# 한국 시간대 설정
ENV TZ=Asia/Seoul
RUN cp /usr/share/zoneinfo/$TZ /etc/localtime

WORKDIR /app

COPY backup.sh restore.sh rotate.sh upload-s3.sh /app/
COPY crontab /etc/crontabs/root

RUN chmod +x /app/*.sh

# 크론 데몬으로 실행
CMD ["crond", "-f", "-d", "8"]
```

## backup/crontab

```
# 매일 새벽 2시 백업
0 2 * * * /app/backup.sh >> /var/log/backup.log 2>&1

# 매일 새벽 3시 오래된 백업 삭제
0 3 * * * /app/rotate.sh >> /var/log/backup.log 2>&1

# 매주 일요일 새벽 4시 S3 업로드
0 4 * * 0 /app/upload-s3.sh >> /var/log/backup.log 2>&1
```

## backup/backup.sh

```bash
#!/usr/bin/env bash
# PostgreSQL 전체 백업 스크립트
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="${PGDATABASE}_${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] 백업 시작: ${PGDATABASE}"

# pg_dump로 백업 생성 (커스텀 포맷 + gzip 압축)
pg_dump \
  --host="$PGHOST" \
  --port="$PGPORT" \
  --username="$PGUSER" \
  --dbname="$PGDATABASE" \
  --format=plain \
  --no-owner \
  --no-privileges \
  --verbose \
  2>/dev/null | gzip > "$FILEPATH"

# 백업 검증
FILESIZE=$(stat -f%z "$FILEPATH" 2>/dev/null || stat -c%s "$FILEPATH" 2>/dev/null)
if [ "$FILESIZE" -lt 100 ]; then
  echo "[$(date)] 오류: 백업 파일 크기가 너무 작음 (${FILESIZE} bytes)"
  rm -f "$FILEPATH"
  exit 1
fi

# 체크섬 생성
sha256sum "$FILEPATH" > "${FILEPATH}.sha256"

echo "[$(date)] 백업 완료: ${FILENAME} (${FILESIZE} bytes)"

# 최근 백업 목록 출력
echo "[$(date)] 현재 백업 목록:"
ls -lhS "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -10
```

## backup/restore.sh

```bash
#!/usr/bin/env bash
# PostgreSQL 복원 스크립트
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_FILE="${1:-}"

# 인자 없으면 최신 백업 사용
if [ -z "$BACKUP_FILE" ]; then
  BACKUP_FILE=$(ls -t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -1)
  if [ -z "$BACKUP_FILE" ]; then
    echo "오류: 백업 파일을 찾을 수 없습니다."
    exit 1
  fi
  echo "최신 백업 사용: $BACKUP_FILE"
fi

# 파일 존재 확인
if [ ! -f "$BACKUP_FILE" ]; then
  echo "오류: 파일 없음 - $BACKUP_FILE"
  exit 1
fi

# 체크섬 검증
if [ -f "${BACKUP_FILE}.sha256" ]; then
  echo "체크섬 검증 중..."
  if sha256sum -c "${BACKUP_FILE}.sha256" --quiet 2>/dev/null; then
    echo "체크섬 검증 성공"
  else
    echo "경고: 체크섬 불일치! 계속하시겠습니까? (y/N)"
    read -r CONFIRM
    [ "$CONFIRM" != "y" ] && exit 1
  fi
fi

echo "[$(date)] 복원 시작: $(basename "$BACKUP_FILE")"
echo "대상 DB: ${PGDATABASE}@${PGHOST}:${PGPORT}"

# 기존 연결 종료 및 DB 재생성
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname = '${PGDATABASE}' AND pid <> pg_backend_pid();
"

dropdb -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" --if-exists "$PGDATABASE"
createdb -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" "$PGDATABASE"

# 복원 실행
gunzip -c "$BACKUP_FILE" | psql \
  -h "$PGHOST" \
  -p "$PGPORT" \
  -U "$PGUSER" \
  -d "$PGDATABASE" \
  --quiet \
  --single-transaction

echo "[$(date)] 복원 완료!"

# 테이블 수 확인
TABLE_COUNT=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "
  SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';
")
echo "복원된 테이블 수: ${TABLE_COUNT}"
```

## backup/rotate.sh

```bash
#!/usr/bin/env bash
# 오래된 백업 파일 삭제 (기본 30일)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

echo "[$(date)] 백업 로테이션 시작 (보존: ${RETENTION_DAYS}일)"

# 삭제 전 카운트
BEFORE_COUNT=$(find "$BACKUP_DIR" -name "*.sql.gz" -type f | wc -l)

# 오래된 파일 삭제
DELETED=0
while IFS= read -r file; do
  echo "삭제: $(basename "$file")"
  rm -f "$file" "${file}.sha256"
  DELETED=$((DELETED + 1))
done < <(find "$BACKUP_DIR" -name "*.sql.gz" -type f -mtime +"$RETENTION_DAYS")

AFTER_COUNT=$(find "$BACKUP_DIR" -name "*.sql.gz" -type f | wc -l)

echo "[$(date)] 로테이션 완료: ${DELETED}개 삭제 (${BEFORE_COUNT} → ${AFTER_COUNT})"

# 디스크 사용량
DISK_USAGE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "백업 디스크 사용량: ${DISK_USAGE}"
```

## backup/upload-s3.sh

```bash
#!/usr/bin/env bash
# 백업 파일을 S3로 업로드
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
S3_BUCKET="${S3_BUCKET:-my-db-backups}"
S3_PREFIX="postgres/$(date +%Y/%m)"

echo "[$(date)] S3 업로드 시작: s3://${S3_BUCKET}/${S3_PREFIX}/"

# 최근 7일 백업만 업로드
UPLOADED=0
while IFS= read -r file; do
  BASENAME=$(basename "$file")
  echo "업로드: ${BASENAME}"
  aws s3 cp "$file" "s3://${S3_BUCKET}/${S3_PREFIX}/${BASENAME}" \
    --storage-class STANDARD_IA \
    --quiet

  # 체크섬 파일도 업로드
  if [ -f "${file}.sha256" ]; then
    aws s3 cp "${file}.sha256" "s3://${S3_BUCKET}/${S3_PREFIX}/${BASENAME}.sha256" --quiet
  fi
  UPLOADED=$((UPLOADED + 1))
done < <(find "$BACKUP_DIR" -name "*.sql.gz" -type f -mtime -7)

echo "[$(date)] S3 업로드 완료: ${UPLOADED}개 파일"

# S3 버킷 사용량
echo "S3 버킷 상태:"
aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" --summarize --human-readable 2>/dev/null | tail -2
```

## .env

```bash
DB_NAME=myapp
DB_USER=appuser
DB_PASSWORD=change-this-secret
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=ap-northeast-2
S3_BUCKET=my-db-backups
BACKUP_RETENTION_DAYS=30
```

## scripts/manual-backup.sh

```bash
#!/usr/bin/env bash
# 수동 백업 실행
set -euo pipefail
echo "수동 백업 실행..."
docker compose exec backup /app/backup.sh
echo "완료! 백업 목록:"
docker compose exec backup ls -lhS /backups/*.sql.gz | head -5
```

사용법: `docker compose up -d`로 시작하면 크론이 매일 새벽 2시 자동 백업합니다. 수동 백업은 `bash scripts/manual-backup.sh`, 복원은 `docker compose exec backup /app/restore.sh`를 실행하세요.'''),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mega_devops.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"DevOps 추가: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
