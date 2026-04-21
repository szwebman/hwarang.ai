"""화랑 AI 추가 학습 데이터 (DevOps/모바일 보강)

DevOps 실무 5건 + React Native 모바일 앱 5건.
각 항목: 폴더 구조 + 6~10개 파일 전체 코드.

카테고리:
  - DevContainer 개발 환경 (1건)
  - 모노레포 CI/CD (1건)
  - Redis 클러스터 + 세션 (1건)
  - Terraform AWS 인프라 (1건)
  - ELK 로그 수집 (1건)
  - SNS 피드 앱 (1건)
  - 음식 배달 앱 (1건)
  - 뉴스 리더 앱 (1건)
  - QR코드 스캐너 앱 (1건)
  - 채팅 앱 (1건)
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
    # ═══ 1. DevContainer 개발 환경 ═══
    m("Docker로 개발 환경 자동 설정(devcontainer) 만들어줘 전체 코드로",
'''Docker 기반 DevContainer 개발 환경을 만들어 드릴게요. VS Code에서 컨테이너를 열면 Node.js + PostgreSQL + Redis가 자동 세팅됩니다.

## 폴더 구조

```
my-project/
├── .devcontainer/
│   ├── devcontainer.json
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── postCreateCommand.sh
│   └── extensions.json
├── src/
│   └── index.ts
├── package.json
├── tsconfig.json
└── .env.example
```

## .devcontainer/devcontainer.json

```json
{
  "name": "My Project Dev",
  "dockerComposeFile": "docker-compose.yml",
  "service": "app",
  "workspaceFolder": "/workspace",
  "remoteUser": "node",
  "features": {
    "ghcr.io/devcontainers/features/git:1": {},
    "ghcr.io/devcontainers/features/github-cli:1": {},
    "ghcr.io/devcontainers/features/docker-in-docker:2": {}
  },
  "customizations": {
    "vscode": {
      "settings": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "esbenp.prettier-vscode",
        "editor.codeActionsOnSave": { "source.fixAll.eslint": "explicit" },
        "typescript.preferences.importModuleSpecifier": "relative",
        "terminal.integrated.defaultProfile.linux": "zsh"
      },
      "extensions": [
        "dbaeumer.vscode-eslint",
        "esbenp.prettier-vscode",
        "ms-azuretools.vscode-docker",
        "prisma.prisma",
        "bradlc.vscode-tailwindcss",
        "mikestead.dotenv",
        "humao.rest-client",
        "eamodio.gitlens",
        "christian-kohler.path-intellisense",
        "streetsidesoftware.code-spell-checker"
      ]
    }
  },
  "postCreateCommand": "bash .devcontainer/postCreateCommand.sh",
  "forwardPorts": [3000, 5432, 6379],
  "portsAttributes": {
    "3000": { "label": "App", "onAutoForward": "notify" },
    "5432": { "label": "PostgreSQL", "onAutoForward": "silent" },
    "6379": { "label": "Redis", "onAutoForward": "silent" }
  }
}
```

## .devcontainer/Dockerfile

```dockerfile
FROM mcr.microsoft.com/devcontainers/typescript-node:1-20-bullseye

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \\
    postgresql-client \\
    redis-tools \\
    jq \\
    htop \\
    && rm -rf /var/lib/apt/lists/*

# pnpm 글로벌 설치
RUN npm install -g pnpm@latest

# zsh 플러그인 (oh-my-zsh는 devcontainer에 내장)
RUN git clone https://github.com/zsh-users/zsh-autosuggestions \\
    /home/node/.oh-my-zsh/custom/plugins/zsh-autosuggestions && \\
    git clone https://github.com/zsh-users/zsh-syntax-highlighting \\
    /home/node/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting && \\
    sed -i 's/plugins=(git)/plugins=(git zsh-autosuggestions zsh-syntax-highlighting node npm docker)/' \\
    /home/node/.zshrc

# 작업 디렉터리
WORKDIR /workspace

# node 유저로 전환
USER node
```

## .devcontainer/docker-compose.yml

```yaml
version: "3.9"

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ..:/workspace:cached
      - node_modules:/workspace/node_modules
    command: sleep infinity
    environment:
      DATABASE_URL: postgresql://devuser:devpass@db:5432/devdb
      REDIS_URL: redis://redis:6379
      NODE_ENV: development
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - devnet

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: devuser
      POSTGRES_PASSWORD: devpass
      POSTGRES_DB: devdb
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U devuser -d devdb"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks:
      - devnet

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redisdata:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks:
      - devnet

volumes:
  node_modules:
  pgdata:
  redisdata:

networks:
  devnet:
    driver: bridge
```

## .devcontainer/postCreateCommand.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== DevContainer 초기 설정 시작 ==="

# 의존성 설치
if [ -f "pnpm-lock.yaml" ]; then
  pnpm install --frozen-lockfile
elif [ -f "package-lock.json" ]; then
  npm ci
else
  pnpm install
fi

# 환경변수 파일 생성
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo ".env 파일 생성 완료"
fi

# DB 마이그레이션 (Prisma 사용 시)
if [ -f "prisma/schema.prisma" ]; then
  npx prisma generate
  npx prisma db push --skip-generate
  echo "Prisma 마이그레이션 완료"
fi

# Git 설정
git config pull.rebase true
git config core.autocrlf input

# 유용한 alias 추가
cat >> ~/.zshrc << 'ALIASES'
alias dev="pnpm dev"
alias build="pnpm build"
alias test="pnpm test"
alias lint="pnpm lint"
alias db="npx prisma studio"
alias logs="docker compose logs -f"
ALIASES

echo "=== DevContainer 설정 완료 ==="
```

## .env.example

```env
DATABASE_URL=postgresql://devuser:devpass@db:5432/devdb
REDIS_URL=redis://redis:6379
NODE_ENV=development
PORT=3000
JWT_SECRET=change-me-in-production
```

## package.json

```json
{
  "name": "my-project",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "build": "tsc && node dist/index.js",
    "lint": "eslint src --ext .ts",
    "test": "vitest run",
    "db:studio": "prisma studio",
    "db:push": "prisma db push"
  },
  "dependencies": {
    "express": "^4.18.2",
    "ioredis": "^5.3.2",
    "@prisma/client": "^5.10.0"
  },
  "devDependencies": {
    "typescript": "^5.3.3",
    "tsx": "^4.7.0",
    "vitest": "^1.2.2",
    "eslint": "^8.56.0",
    "prisma": "^5.10.0",
    "@types/express": "^4.17.21"
  }
}
```

## src/index.ts

```typescript
import express from "express";
import Redis from "ioredis";

const app = express();
const port = Number(process.env.PORT) || 3000;

// Redis 연결
const redis = new Redis(process.env.REDIS_URL || "redis://localhost:6379");

redis.on("connect", () => console.log("Redis 연결 성공"));
redis.on("error", (err) => console.error("Redis 에러:", err));

app.use(express.json());

// 헬스 체크
app.get("/health", async (_req, res) => {
  const redisOk = redis.status === "ready";
  res.json({
    status: redisOk ? "healthy" : "degraded",
    redis: redis.status,
    uptime: process.uptime(),
    timestamp: new Date().toISOString(),
  });
});

// 캐시 예시 API
app.get("/api/data/:key", async (req, res) => {
  const { key } = req.params;
  const cached = await redis.get(`cache:${key}`);
  if (cached) {
    return res.json({ source: "cache", data: JSON.parse(cached) });
  }
  // 실제로는 DB 조회
  const data = { key, value: `sample-${Date.now()}` };
  await redis.setex(`cache:${key}`, 60, JSON.stringify(data));
  res.json({ source: "db", data });
});

app.listen(port, () => {
  console.log(`서버 시작: http://localhost:${port}`);
});
```

DevContainer를 열면 VS Code가 자동으로 Docker 환경을 빌드하고, PostgreSQL/Redis가 준비된 상태에서 바로 개발을 시작할 수 있습니다.'''),

    # ═══ 2. 모노레포 CI/CD ═══
    m("GitHub Actions로 모노레포 CI/CD 만들어줘 전체 코드로",
'''GitHub Actions 기반 모노레포 CI/CD를 만들어 드릴게요. 변경된 패키지만 선택적으로 빌드하며, Turborepo 캐시를 활용합니다.

## 폴더 구조

```
monorepo/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── deploy.yml
│       └── pr-check.yml
├── packages/
│   ├── web/
│   │   └── package.json
│   ├── api/
│   │   └── package.json
│   └── shared/
│       └── package.json
├── turbo.json
├── package.json
├── pnpm-workspace.yaml
└── scripts/
    └── detect-changes.sh
```

## .github/workflows/ci.yml

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

env:
  TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
  TURBO_TEAM: ${{ vars.TURBO_TEAM }}

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      web: ${{ steps.filter.outputs.web }}
      api: ${{ steps.filter.outputs.api }}
      shared: ${{ steps.filter.outputs.shared }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            web:
              - "packages/web/**"
              - "packages/shared/**"
            api:
              - "packages/api/**"
              - "packages/shared/**"
            shared:
              - "packages/shared/**"

  lint-and-type:
    needs: detect-changes
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
        with:
          version: 8
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo lint typecheck --cache-dir=.turbo

  test:
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        package:
          - name: web
            changed: ${{ needs.detect-changes.outputs.web }}
          - name: api
            changed: ${{ needs.detect-changes.outputs.api }}
          - name: shared
            changed: ${{ needs.detect-changes.outputs.shared }}
        exclude:
          - package:
              changed: "false"
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
        with:
          version: 8
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo test --filter=${{ matrix.package.name }} --cache-dir=.turbo
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-${{ matrix.package.name }}
          path: packages/${{ matrix.package.name }}/coverage/

  build:
    needs: [lint-and-type, test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
        with:
          version: 8
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo build --cache-dir=.turbo
      - uses: actions/upload-artifact@v4
        with:
          name: build-artifacts
          path: |
            packages/web/.next/
            packages/api/dist/
```

## .github/workflows/deploy.yml

```yaml
name: Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      package:
        description: "배포할 패키지"
        required: true
        type: choice
        options: [web, api, all]

jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      web: ${{ steps.check.outputs.web }}
      api: ${{ steps.check.outputs.api }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      - id: check
        run: |
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            PKG="${{ inputs.package }}"
            echo "web=$( [ '$PKG' = 'web' ] || [ '$PKG' = 'all' ] && echo true || echo false )" >> $GITHUB_OUTPUT
            echo "api=$( [ '$PKG' = 'api' ] || [ '$PKG' = 'all' ] && echo true || echo false )" >> $GITHUB_OUTPUT
          else
            bash scripts/detect-changes.sh >> $GITHUB_OUTPUT
          fi

  deploy-web:
    needs: detect
    if: needs.detect.outputs.web == 'true'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
        with: { version: 8 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo build --filter=web
      - uses: amondnet/vercel-action@v25
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_WEB_PROJECT_ID }}
          vercel-args: "--prod"

  deploy-api:
    needs: detect
    if: needs.detect.outputs.api == 'true'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
        with: { version: 8 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo build --filter=api
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - run: |
          docker build -t ghcr.io/${{ github.repository }}/api:${{ github.sha }} packages/api
          docker push ghcr.io/${{ github.repository }}/api:${{ github.sha }}
```

## .github/workflows/pr-check.yml

```yaml
name: PR Check

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  pr-size:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check PR size
        run: |
          ADDITIONS=$(gh pr view ${{ github.event.number }} --json additions -q '.additions')
          if [ "$ADDITIONS" -gt 1000 ]; then
            echo "::warning::PR이 1000줄 이상입니다. 분리를 고려하세요."
          fi
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  bundle-size:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
        with: { version: 8 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo build --filter=web
      - uses: andresz1/size-limit-action@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          directory: packages/web
```

## turbo.json

```json
{
  "$schema": "https://turbo.build/schema.json",
  "globalDependencies": ["**/.env.*local"],
  "pipeline": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "dist/**"],
      "env": ["NODE_ENV", "DATABASE_URL"]
    },
    "lint": {
      "dependsOn": ["^build"]
    },
    "typecheck": {
      "dependsOn": ["^build"]
    },
    "test": {
      "dependsOn": ["^build"],
      "outputs": ["coverage/**"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    }
  }
}
```

## pnpm-workspace.yaml

```yaml
packages:
  - "packages/*"
```

## scripts/detect-changes.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# 직전 커밋 대비 변경 파일 감지
CHANGED=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || git diff --name-only HEAD)

WEB=false
API=false

while IFS= read -r file; do
  case "$file" in
    packages/web/*|packages/shared/*) WEB=true ;;
    packages/api/*|packages/shared/*) API=true ;;
  esac
done <<< "$CHANGED"

echo "web=$WEB"
echo "api=$API"
```

## package.json (루트)

```json
{
  "name": "monorepo",
  "private": true,
  "scripts": {
    "dev": "turbo dev",
    "build": "turbo build",
    "lint": "turbo lint",
    "test": "turbo test",
    "typecheck": "turbo typecheck",
    "clean": "turbo clean && rm -rf node_modules"
  },
  "devDependencies": {
    "turbo": "^1.12.0"
  },
  "packageManager": "pnpm@8.15.0"
}
```

변경된 패키지만 선택적으로 빌드/배포하므로 CI 시간을 크게 절약할 수 있습니다. Turborepo 원격 캐시를 활성화하면 팀원 간 빌드 캐시도 공유됩니다.'''),

    # ═══ 3. Redis 클러스터 + 세션 관리 ═══
    m("Docker로 Redis 클러스터 + 세션 관리 만들어줘 전체 코드로",
'''Docker 기반 Redis Sentinel 클러스터와 Express 세션 관리를 만들어 드릴게요. 마스터 장애 시 자동 페일오버됩니다.

## 폴더 구조

```
redis-session/
├── docker-compose.yml
├── sentinel/
│   └── sentinel.conf
├── src/
│   ├── app.ts
│   ├── redis.ts
│   ├── session.ts
│   ├── cache.ts
│   └── routes/
│       └── auth.ts
├── scripts/
│   └── failover-test.sh
├── package.json
└── tsconfig.json
```

## docker-compose.yml

```yaml
version: "3.9"

services:
  redis-master:
    image: redis:7-alpine
    command: redis-server --appendonly yes --requirepass redispass
    ports:
      - "6379:6379"
    volumes:
      - redis-master-data:/data
    networks:
      - redis-net
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "redispass", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis-replica-1:
    image: redis:7-alpine
    command: redis-server --appendonly yes --replicaof redis-master 6379 --requirepass redispass --masterauth redispass
    depends_on:
      redis-master:
        condition: service_healthy
    networks:
      - redis-net

  redis-replica-2:
    image: redis:7-alpine
    command: redis-server --appendonly yes --replicaof redis-master 6379 --requirepass redispass --masterauth redispass
    depends_on:
      redis-master:
        condition: service_healthy
    networks:
      - redis-net

  sentinel-1:
    image: redis:7-alpine
    command: redis-sentinel /etc/sentinel.conf
    volumes:
      - ./sentinel/sentinel.conf:/etc/sentinel.conf:ro
    depends_on:
      - redis-master
      - redis-replica-1
      - redis-replica-2
    networks:
      - redis-net
    ports:
      - "26379:26379"

  sentinel-2:
    image: redis:7-alpine
    command: redis-sentinel /etc/sentinel.conf
    volumes:
      - ./sentinel/sentinel.conf:/etc/sentinel.conf:ro
    depends_on:
      - redis-master
    networks:
      - redis-net
    ports:
      - "26380:26379"

  sentinel-3:
    image: redis:7-alpine
    command: redis-sentinel /etc/sentinel.conf
    volumes:
      - ./sentinel/sentinel.conf:/etc/sentinel.conf:ro
    depends_on:
      - redis-master
    networks:
      - redis-net
    ports:
      - "26381:26379"

  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      SENTINEL_HOSTS: sentinel-1:26379,sentinel-2:26379,sentinel-3:26379
      REDIS_PASSWORD: redispass
      SESSION_SECRET: my-super-secret-key
    depends_on:
      - sentinel-1
      - sentinel-2
      - sentinel-3
    networks:
      - redis-net

volumes:
  redis-master-data:

networks:
  redis-net:
    driver: bridge
```

## sentinel/sentinel.conf

```
port 26379
sentinel monitor mymaster redis-master 6379 2
sentinel auth-pass mymaster redispass
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 10000
sentinel parallel-syncs mymaster 1
sentinel resolve-hostnames yes
sentinel announce-hostnames yes
```

## src/redis.ts

```typescript
import Redis from "ioredis";

const sentinelHosts = (process.env.SENTINEL_HOSTS || "localhost:26379")
  .split(",")
  .map((h) => {
    const [host, port] = h.split(":");
    return { host, port: Number(port) };
  });

// Sentinel 기반 연결 — 마스터 자동 감지
export const redis = new Redis({
  sentinels: sentinelHosts,
  name: "mymaster",
  password: process.env.REDIS_PASSWORD || "redispass",
  sentinelPassword: process.env.REDIS_PASSWORD || "redispass",
  retryStrategy(times: number) {
    const delay = Math.min(times * 200, 5000);
    console.log(`Redis 재연결 시도 #${times} (${delay}ms 후)`);
    return delay;
  },
  reconnectOnError(err: Error) {
    const targetErrors = ["READONLY", "ECONNREFUSED"];
    return targetErrors.some((e) => err.message.includes(e));
  },
  enableReadyCheck: true,
  maxRetriesPerRequest: 3,
});

redis.on("connect", () => console.log("Redis Sentinel 연결 성공"));
redis.on("error", (err) => console.error("Redis 에러:", err.message));
redis.on("+failover", () => console.log("페일오버 감지 — 새 마스터 연결 중"));

// 읽기 전용 레플리카 (읽기 분산)
export const redisReadonly = new Redis({
  sentinels: sentinelHosts,
  name: "mymaster",
  password: process.env.REDIS_PASSWORD || "redispass",
  sentinelPassword: process.env.REDIS_PASSWORD || "redispass",
  role: "slave",
  enableReadyCheck: true,
});
```

## src/session.ts

```typescript
import session from "express-session";
import connectRedis from "connect-redis";
import { redis } from "./redis";

const RedisStore = connectRedis(session);

export const sessionMiddleware = session({
  store: new RedisStore({
    client: redis as any,
    prefix: "sess:",
    ttl: 60 * 60 * 24, // 24시간
    disableTouch: false,
  }),
  secret: process.env.SESSION_SECRET || "fallback-secret",
  resave: false,
  saveUninitialized: false,
  rolling: true,
  cookie: {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    maxAge: 1000 * 60 * 60 * 24, // 24시간
    sameSite: "lax",
  },
  name: "sid",
});
```

## src/cache.ts

```typescript
import { redis, redisReadonly } from "./redis";

export class CacheService {
  // 캐시 조회 (레플리카에서 읽기)
  async get<T>(key: string): Promise<T | null> {
    const data = await redisReadonly.get(`cache:${key}`);
    return data ? JSON.parse(data) : null;
  }

  // 캐시 저장 (마스터에 쓰기)
  async set(key: string, value: unknown, ttlSeconds = 300): Promise<void> {
    await redis.setex(`cache:${key}`, ttlSeconds, JSON.stringify(value));
  }

  // 캐시 무효화
  async invalidate(pattern: string): Promise<number> {
    const keys = await redis.keys(`cache:${pattern}`);
    if (keys.length === 0) return 0;
    return redis.del(...keys);
  }

  // 캐시 또는 조회 패턴
  async getOrSet<T>(
    key: string,
    fetcher: () => Promise<T>,
    ttlSeconds = 300
  ): Promise<T> {
    const cached = await this.get<T>(key);
    if (cached !== null) return cached;
    const data = await fetcher();
    await this.set(key, data, ttlSeconds);
    return data;
  }

  // 분산 락 (간단 구현)
  async acquireLock(resource: string, ttlMs = 5000): Promise<string | null> {
    const token = `lock:${Date.now()}:${Math.random().toString(36).slice(2)}`;
    const result = await redis.set(
      `lock:${resource}`,
      token,
      "PX",
      ttlMs,
      "NX"
    );
    return result === "OK" ? token : null;
  }

  async releaseLock(resource: string, token: string): Promise<boolean> {
    const script = `
      if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
      else return 0 end
    `;
    const result = await redis.eval(script, 1, `lock:${resource}`, token);
    return result === 1;
  }
}

export const cache = new CacheService();
```

## src/routes/auth.ts

```typescript
import { Router, Request, Response } from "express";
import { redis } from "../redis";

const router = Router();

// 로그인
router.post("/login", async (req: Request, res: Response) => {
  const { username, password } = req.body;
  // 실제로는 DB 조회 + bcrypt 비교
  if (username === "admin" && password === "1234") {
    (req.session as any).user = { id: 1, username, role: "admin" };
    await redis.hset(`user:${1}:sessions`, req.sessionID, Date.now().toString());
    return res.json({ message: "로그인 성공" });
  }
  res.status(401).json({ error: "인증 실패" });
});

// 로그아웃
router.post("/logout", async (req: Request, res: Response) => {
  const user = (req.session as any).user;
  if (user) {
    await redis.hdel(`user:${user.id}:sessions`, req.sessionID);
  }
  req.session.destroy((err) => {
    if (err) return res.status(500).json({ error: "로그아웃 실패" });
    res.clearCookie("sid");
    res.json({ message: "로그아웃 완료" });
  });
});

// 전체 세션 만료 (모든 기기 로그아웃)
router.post("/logout-all", async (req: Request, res: Response) => {
  const user = (req.session as any).user;
  if (!user) return res.status(401).json({ error: "로그인 필요" });
  const sessions = await redis.hkeys(`user:${user.id}:sessions`);
  for (const sid of sessions) {
    await redis.del(`sess:${sid}`);
  }
  await redis.del(`user:${user.id}:sessions`);
  res.json({ message: `${sessions.length}개 세션 만료 완료` });
});

// 현재 사용자
router.get("/me", (req: Request, res: Response) => {
  const user = (req.session as any).user;
  if (!user) return res.status(401).json({ error: "로그인 필요" });
  res.json({ user });
});

export default router;
```

## src/app.ts

```typescript
import express from "express";
import { sessionMiddleware } from "./session";
import authRoutes from "./routes/auth";
import { cache } from "./cache";

const app = express();
app.use(express.json());
app.use(sessionMiddleware);

app.get("/health", async (_req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

// 캐시 예시
app.get("/api/products", async (_req, res) => {
  const products = await cache.getOrSet("products:all", async () => {
    return [
      { id: 1, name: "노트북", price: 1200000 },
      { id: 2, name: "키보드", price: 89000 },
    ];
  }, 120);
  res.json(products);
});

app.use("/auth", authRoutes);

app.listen(3000, () => console.log("서버 시작: http://localhost:3000"));
```

## scripts/failover-test.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Redis Sentinel 페일오버 테스트 ==="

echo "[1] 현재 마스터 확인"
docker compose exec sentinel-1 redis-cli -p 26379 sentinel get-master-addr-by-name mymaster

echo ""
echo "[2] 마스터 컨테이너 중지"
docker compose stop redis-master
sleep 3

echo ""
echo "[3] 페일오버 후 새 마스터 확인"
docker compose exec sentinel-1 redis-cli -p 26379 sentinel get-master-addr-by-name mymaster

echo ""
echo "[4] 앱 헬스 체크"
curl -s http://localhost:3000/health | jq .

echo ""
echo "[5] 이전 마스터 복구"
docker compose start redis-master
sleep 3

echo ""
echo "[6] 최종 상태 확인"
docker compose exec sentinel-1 redis-cli -p 26379 sentinel get-master-addr-by-name mymaster
echo "=== 테스트 완료 ==="
```

Sentinel이 마스터 장애를 감지하면 자동으로 레플리카를 마스터로 승격합니다. ioredis가 자동으로 새 마스터에 재연결됩니다.'''),

    # ═══ 4. Terraform AWS 인프라 ═══
    m("Terraform으로 AWS 인프라 자동화 만들어줘 전체 코드로",
'''Terraform으로 AWS 인프라를 자동화해 드릴게요. VPC, EC2, RDS, S3를 포함한 완전한 구성입니다.

## 폴더 구조

```
terraform-aws/
├── main.tf
├── variables.tf
├── outputs.tf
├── terraform.tfvars.example
├── modules/
│   ├── vpc/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── ec2/
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
├── scripts/
│   └── user_data.sh
└── .gitignore
```

## variables.tf

```hcl
variable "aws_region" {
  description = "AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "project_name" {
  description = "프로젝트 이름 (리소스 태그용)"
  type        = string
  default     = "my-app"
}

variable "environment" {
  description = "환경 (dev/staging/prod)"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment는 dev, staging, prod 중 하나여야 합니다."
  }
}

variable "vpc_cidr" {
  description = "VPC CIDR 블록"
  type        = string
  default     = "10.0.0.0/16"
}

variable "ec2_instance_type" {
  description = "EC2 인스턴스 타입"
  type        = string
  default     = "t3.medium"
}

variable "ec2_key_pair" {
  description = "EC2 SSH 키 페어 이름"
  type        = string
}

variable "db_username" {
  description = "RDS 마스터 사용자명"
  type        = string
  default     = "appuser"
  sensitive   = true
}

variable "db_password" {
  description = "RDS 마스터 비밀번호"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS 인스턴스 클래스"
  type        = string
  default     = "db.t3.medium"
}

variable "allowed_ssh_cidrs" {
  description = "SSH 접근 허용 CIDR 목록"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
```

## main.tf

```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket         = "my-terraform-state-bucket"
    key            = "infra/terraform.tfstate"
    region         = "ap-northeast-2"
    dynamodb_table = "terraform-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  azs         = ["${var.aws_region}a", "${var.aws_region}c"]
}

# ── VPC ──
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "${local.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${local.name_prefix}-igw" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags = { Name = "${local.name_prefix}-public-${count.index + 1}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = local.azs[count.index]
  tags = { Name = "${local.name_prefix}-private-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "${local.name_prefix}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ── 보안 그룹 ──
resource "aws_security_group" "web" {
  name_prefix = "${local.name_prefix}-web-"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidrs
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${local.name_prefix}-web-sg" }
}

resource "aws_security_group" "db" {
  name_prefix = "${local.name_prefix}-db-"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from web"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.web.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${local.name_prefix}-db-sg" }
}

# ── EC2 ──
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_instance" "web" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.ec2_instance_type
  key_name               = var.ec2_key_pair
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.web.id]
  user_data              = file("${path.module}/scripts/user_data.sh")

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "${local.name_prefix}-web" }
}

# ── RDS PostgreSQL ──
resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnet"
  subnet_ids = aws_subnet.private[*].id
  tags       = { Name = "${local.name_prefix}-db-subnet" }
}

resource "aws_db_instance" "main" {
  identifier             = "${local.name_prefix}-db"
  engine                 = "postgres"
  engine_version         = "15.4"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  max_allocated_storage  = 100
  storage_encrypted      = true
  db_name                = "appdb"
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  multi_az               = var.environment == "prod"
  skip_final_snapshot    = var.environment != "prod"
  backup_retention_period = var.environment == "prod" ? 7 : 1
  tags = { Name = "${local.name_prefix}-db" }
}

# ── S3 ──
resource "aws_s3_bucket" "assets" {
  bucket = "${local.name_prefix}-assets-${data.aws_caller_identity.current.account_id}"
  tags   = { Name = "${local.name_prefix}-assets" }
}

resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "assets" {
  bucket = aws_s3_bucket.assets.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "assets" {
  bucket                  = aws_s3_bucket.assets.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_caller_identity" "current" {}
```

## outputs.tf

```hcl
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "ec2_public_ip" {
  description = "EC2 퍼블릭 IP"
  value       = aws_instance.web.public_ip
}

output "rds_endpoint" {
  description = "RDS 엔드포인트"
  value       = aws_db_instance.main.endpoint
}

output "s3_bucket_name" {
  description = "S3 버킷 이름"
  value       = aws_s3_bucket.assets.id
}

output "ssh_command" {
  description = "SSH 접속 명령어"
  value       = "ssh -i ~/.ssh/${var.ec2_key_pair}.pem ec2-user@${aws_instance.web.public_ip}"
}
```

## terraform.tfvars.example

```hcl
aws_region        = "ap-northeast-2"
project_name      = "my-app"
environment       = "dev"
vpc_cidr          = "10.0.0.0/16"
ec2_instance_type = "t3.medium"
ec2_key_pair      = "my-keypair"
db_username       = "appuser"
db_password       = "CHANGE-ME-strong-password-123!"
db_instance_class = "db.t3.medium"
allowed_ssh_cidrs = ["YOUR_IP/32"]
```

## scripts/user_data.sh

```bash
#!/bin/bash
set -euxo pipefail

# 시스템 업데이트
dnf update -y

# Node.js 20 설치
dnf install -y nodejs20 npm git

# Docker 설치
dnf install -y docker
systemctl enable docker && systemctl start docker
usermod -aG docker ec2-user

# 앱 디렉터리 생성
mkdir -p /opt/app
chown ec2-user:ec2-user /opt/app

# CloudWatch Agent
dnf install -y amazon-cloudwatch-agent

echo "User data 실행 완료" >> /var/log/user-data.log
```

## .gitignore

```
.terraform/
*.tfstate
*.tfstate.backup
*.tfvars
!terraform.tfvars.example
.terraform.lock.hcl
```

`terraform init` 후 `terraform plan`으로 변경 사항을 확인하고, `terraform apply`로 인프라를 생성합니다. tfvars.example을 복사해서 실제 값을 채운 후 사용하세요.'''),

    # ═══ 5. ELK 로그 수집 파이프라인 ═══
    m("Docker + ELK 로그 수집 파이프라인 만들어줘 전체 코드로",
'''Docker 기반 ELK(Elasticsearch + Logstash + Kibana) 로그 수집 파이프라인을 만들어 드릴게요. Filebeat로 앱 로그를 수집합니다.

## 폴더 구조

```
elk-stack/
├── docker-compose.yml
├── elasticsearch/
│   └── elasticsearch.yml
├── logstash/
│   ├── logstash.yml
│   ├── pipeline/
│   │   └── main.conf
│   └── templates/
│       └── app-logs.json
├── kibana/
│   └── kibana.yml
├── filebeat/
│   └── filebeat.yml
├── app/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       └── index.ts
└── scripts/
    └── setup-kibana.sh
```

## docker-compose.yml

```yaml
version: "3.9"

services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.12.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - xpack.security.http.ssl.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
      - cluster.name=elk-logs
    volumes:
      - ./elasticsearch/elasticsearch.yml:/usr/share/elasticsearch/config/elasticsearch.yml:ro
      - es-data:/usr/share/elasticsearch/data
    ports:
      - "9200:9200"
    networks:
      - elk
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:9200/_cluster/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10

  logstash:
    image: docker.elastic.co/logstash/logstash:8.12.0
    volumes:
      - ./logstash/logstash.yml:/usr/share/logstash/config/logstash.yml:ro
      - ./logstash/pipeline:/usr/share/logstash/pipeline:ro
      - ./logstash/templates:/usr/share/logstash/templates:ro
    ports:
      - "5044:5044"
      - "5000:5000/tcp"
      - "5000:5000/udp"
    environment:
      - "LS_JAVA_OPTS=-Xms256m -Xmx256m"
    depends_on:
      elasticsearch:
        condition: service_healthy
    networks:
      - elk

  kibana:
    image: docker.elastic.co/kibana/kibana:8.12.0
    volumes:
      - ./kibana/kibana.yml:/usr/share/kibana/config/kibana.yml:ro
    ports:
      - "5601:5601"
    depends_on:
      elasticsearch:
        condition: service_healthy
    networks:
      - elk

  filebeat:
    image: docker.elastic.co/beats/filebeat:8.12.0
    user: root
    volumes:
      - ./filebeat/filebeat.yml:/usr/share/filebeat/filebeat.yml:ro
      - app-logs:/var/log/app:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    depends_on:
      - logstash
    networks:
      - elk

  app:
    build: ./app
    volumes:
      - app-logs:/var/log/app
    ports:
      - "3000:3000"
    environment:
      - LOG_DIR=/var/log/app
      - NODE_ENV=production
    networks:
      - elk

volumes:
  es-data:
  app-logs:

networks:
  elk:
    driver: bridge
```

## elasticsearch/elasticsearch.yml

```yaml
cluster.name: "elk-logs"
network.host: 0.0.0.0
path.data: /usr/share/elasticsearch/data
http.port: 9200
xpack.security.enabled: false
xpack.license.self_generated.type: basic
indices.query.bool.max_clause_count: 4096
action.destructive_requires_name: true
```

## logstash/logstash.yml

```yaml
http.host: "0.0.0.0"
path.config: /usr/share/logstash/pipeline
xpack.monitoring.enabled: false
pipeline.workers: 2
pipeline.batch.size: 125
pipeline.batch.delay: 50
```

## logstash/pipeline/main.conf

```
input {
  beats {
    port => 5044
  }
  tcp {
    port => 5000
    codec => json_lines
  }
}

filter {
  # JSON 로그 파싱
  if [message] =~ /^\{/ {
    json {
      source => "message"
      target => "parsed"
      skip_on_invalid_json => true
    }
    if [parsed][level] {
      mutate { add_field => { "log_level" => "%{[parsed][level]}" } }
    }
    if [parsed][service] {
      mutate { add_field => { "service_name" => "%{[parsed][service]}" } }
    }
  }

  # 타임스탬프 처리
  if [parsed][timestamp] {
    date {
      match => ["[parsed][timestamp]", "ISO8601"]
      target => "@timestamp"
    }
  }

  # 에러 로그에 태그 추가
  if [log_level] in ["error", "fatal"] {
    mutate { add_tag => ["error_log"] }
  }

  # HTTP 요청 로그 파싱
  if [parsed][method] and [parsed][url] {
    mutate {
      add_field => {
        "http_method" => "%{[parsed][method]}"
        "http_url" => "%{[parsed][url]}"
        "http_status" => "%{[parsed][statusCode]}"
        "response_time_ms" => "%{[parsed][responseTime]}"
      }
    }
    mutate {
      convert => {
        "http_status" => "integer"
        "response_time_ms" => "integer"
      }
    }
  }

  # 불필요한 필드 제거
  mutate {
    remove_field => ["host", "agent", "ecs", "input", "log"]
  }
}

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    index => "app-logs-%{+YYYY.MM.dd}"
    template => "/usr/share/logstash/templates/app-logs.json"
    template_name => "app-logs"
    template_overwrite => true
  }

  # 에러 로그는 별도 인덱스
  if "error_log" in [tags] {
    elasticsearch {
      hosts => ["http://elasticsearch:9200"]
      index => "app-errors-%{+YYYY.MM.dd}"
    }
  }

  # 디버깅용 stdout
  stdout {
    codec => rubydebug { metadata => false }
  }
}
```

## logstash/templates/app-logs.json

```json
{
  "index_patterns": ["app-logs-*"],
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "index.lifecycle.name": "app-logs-policy",
    "index.lifecycle.rollover_alias": "app-logs"
  },
  "mappings": {
    "properties": {
      "@timestamp": { "type": "date" },
      "log_level": { "type": "keyword" },
      "service_name": { "type": "keyword" },
      "http_method": { "type": "keyword" },
      "http_url": { "type": "keyword" },
      "http_status": { "type": "integer" },
      "response_time_ms": { "type": "integer" },
      "message": { "type": "text" },
      "parsed": { "type": "object", "dynamic": true }
    }
  }
}
```

## kibana/kibana.yml

```yaml
server.name: kibana
server.host: "0.0.0.0"
server.port: 5601
elasticsearch.hosts: ["http://elasticsearch:9200"]
monitoring.ui.container.elasticsearch.enabled: true
i18n.locale: "ko"
```

## filebeat/filebeat.yml

```yaml
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /var/log/app/*.log
    json.keys_under_root: true
    json.add_error_key: true
    json.message_key: message
    multiline.pattern: '^\{'
    multiline.negate: true
    multiline.match: after

  - type: container
    enabled: true
    paths:
      - /var/lib/docker/containers/*/*.log
    processors:
      - add_docker_metadata:
          host: "unix:///var/run/docker.sock"

output.logstash:
  hosts: ["logstash:5044"]

logging.level: warning
logging.to_files: true
logging.files:
  path: /var/log/filebeat
  name: filebeat
  keepfiles: 3
```

## app/src/index.ts

```typescript
import express from "express";
import fs from "fs";
import path from "path";

const app = express();
const LOG_DIR = process.env.LOG_DIR || "./logs";
const logFile = path.join(LOG_DIR, "app.log");

// 로그 디렉터리 생성
fs.mkdirSync(LOG_DIR, { recursive: true });

// 구조화 로그 함수
function log(level: string, message: string, extra: Record<string, unknown> = {}) {
  const entry = JSON.stringify({
    timestamp: new Date().toISOString(),
    level,
    service: "my-app",
    message,
    ...extra,
  });
  fs.appendFileSync(logFile, entry + "\\n");
  console.log(entry);
}

// 요청 로깅 미들웨어
app.use((req, res, next) => {
  const start = Date.now();
  res.on("finish", () => {
    log("info", "HTTP Request", {
      method: req.method,
      url: req.originalUrl,
      statusCode: res.statusCode,
      responseTime: Date.now() - start,
      userAgent: req.get("user-agent"),
      ip: req.ip,
    });
  });
  next();
});

app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok" }));

app.get("/api/test", (_req, res) => {
  log("info", "테스트 API 호출");
  res.json({ message: "Hello from app!" });
});

app.get("/api/error-test", (_req, res) => {
  log("error", "의도적 에러 테스트", { errorCode: "TEST_ERROR" });
  res.status(500).json({ error: "Test error" });
});

app.listen(3000, () => log("info", "서버 시작", { port: 3000 }));
```

## app/package.json

```json
{
  "name": "elk-demo-app",
  "version": "1.0.0",
  "scripts": { "start": "tsx src/index.ts" },
  "dependencies": { "express": "^4.18.2" },
  "devDependencies": { "tsx": "^4.7.0", "@types/express": "^4.17.21" }
}
```

## scripts/setup-kibana.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

KIBANA_URL="http://localhost:5601"
ES_URL="http://localhost:9200"

echo "=== Kibana 초기 설정 ==="

echo "[1] Elasticsearch 상태 확인"
curl -sf "$ES_URL/_cluster/health?pretty"

echo ""
echo "[2] Index Pattern 생성"
curl -sf -X POST "$KIBANA_URL/api/saved_objects/index-pattern/app-logs-*" \\
  -H "kbn-xsrf: true" \\
  -H "Content-Type: application/json" \\
  -d '{"attributes":{"title":"app-logs-*","timeFieldName":"@timestamp"}}'

echo ""
echo "[3] ILM 정책 생성 (30일 보관)"
curl -sf -X PUT "$ES_URL/_ilm/policy/app-logs-policy" \\
  -H "Content-Type: application/json" \\
  -d '{
    "policy": {
      "phases": {
        "hot":    { "actions": { "rollover": { "max_size": "5gb", "max_age": "7d" } } },
        "warm":   { "min_age": "7d", "actions": { "shrink": { "number_of_shards": 1 } } },
        "delete": { "min_age": "30d", "actions": { "delete": {} } }
      }
    }
  }'

echo ""
echo "=== 설정 완료 — Kibana: $KIBANA_URL ==="
```

`docker compose up -d`로 전체 스택을 시작하고, http://localhost:5601 에서 Kibana 대시보드를 확인할 수 있습니다.'''),

    # ═══ 6. SNS 피드 앱 ═══
    m("React Native로 SNS 피드 앱 만들어줘 전체 코드로",
'''React Native SNS 피드 앱을 만들어 드릴게요. 인스타그램 스타일의 피드, 좋아요 애니메이션, 댓글 입력을 포함합니다.

## 폴더 구조

```
sns-feed-app/
├── App.tsx
├── src/
│   ├── screens/
│   │   ├── FeedScreen.tsx
│   │   └── ProfileScreen.tsx
│   ├── components/
│   │   ├── PostCard.tsx
│   │   ├── LikeButton.tsx
│   │   ├── CommentInput.tsx
│   │   └── ProfileHeader.tsx
│   ├── store/
│   │   └── useFeedStore.ts
│   └── types/
│       └── index.ts
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "sns-feed-app",
  "version": "1.0.0",
  "scripts": { "start": "expo start", "android": "expo start --android", "ios": "expo start --ios" },
  "dependencies": {
    "expo": "~50.0.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/bottom-tabs": "^6.5.12",
    "react-native-screens": "~3.29.0",
    "react-native-safe-area-context": "4.8.2",
    "zustand": "^4.5.0",
    "react-native-reanimated": "~3.6.0",
    "expo-image": "~1.10.0"
  }
}
```

## src/types/index.ts

```typescript
export interface User {
  id: string;
  username: string;
  displayName: string;
  avatarUrl: string;
  bio: string;
  postsCount: number;
  followersCount: number;
  followingCount: number;
}

export interface Comment {
  id: string;
  userId: string;
  username: string;
  text: string;
  createdAt: string;
}

export interface Post {
  id: string;
  user: Pick<User, "id" | "username" | "avatarUrl">;
  imageUrl: string;
  caption: string;
  likes: number;
  isLiked: boolean;
  comments: Comment[];
  createdAt: string;
}
```

## src/store/useFeedStore.ts

```typescript
import { create } from "zustand";
import type { Post, Comment } from "../types";

interface FeedState {
  posts: Post[];
  isRefreshing: boolean;
  toggleLike: (postId: string) => void;
  addComment: (postId: string, text: string) => void;
  refreshFeed: () => Promise<void>;
}

const MOCK_POSTS: Post[] = Array.from({ length: 20 }, (_, i) => ({
  id: `post-${i + 1}`,
  user: {
    id: `user-${(i % 5) + 1}`,
    username: ["design_kim", "dev_park", "photo_lee", "food_choi", "travel_jung"][i % 5],
    avatarUrl: `https://i.pravatar.cc/100?img=${(i % 5) + 1}`,
  },
  imageUrl: `https://picsum.photos/600/600?random=${i + 1}`,
  caption: [
    "오늘 카페에서 작업 중 ☕",
    "새 프로젝트 시작했습니다 🚀",
    "주말 나들이 🌸",
    "오늘의 점심 🍱",
    "야경이 정말 예쁘다 🌃",
  ][i % 5],
  likes: Math.floor(Math.random() * 500) + 10,
  isLiked: false,
  comments: [
    { id: `c-${i}-1`, userId: "u1", username: "friend_1", text: "멋지다!", createdAt: new Date().toISOString() },
    { id: `c-${i}-2`, userId: "u2", username: "friend_2", text: "좋아요 👍", createdAt: new Date().toISOString() },
  ],
  createdAt: new Date(Date.now() - i * 3600000).toISOString(),
}));

export const useFeedStore = create<FeedState>((set) => ({
  posts: MOCK_POSTS,
  isRefreshing: false,

  toggleLike: (postId) =>
    set((state) => ({
      posts: state.posts.map((p) =>
        p.id === postId
          ? { ...p, isLiked: !p.isLiked, likes: p.isLiked ? p.likes - 1 : p.likes + 1 }
          : p
      ),
    })),

  addComment: (postId, text) =>
    set((state) => ({
      posts: state.posts.map((p) =>
        p.id === postId
          ? {
              ...p,
              comments: [
                ...p.comments,
                {
                  id: `c-${Date.now()}`,
                  userId: "me",
                  username: "나",
                  text,
                  createdAt: new Date().toISOString(),
                },
              ],
            }
          : p
      ),
    })),

  refreshFeed: async () => {
    set({ isRefreshing: true });
    await new Promise((r) => setTimeout(r, 1000));
    set({ isRefreshing: false });
  },
}));
```

## src/components/LikeButton.tsx

```typescript
import React, { useCallback } from "react";
import { Pressable, StyleSheet } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withSequence,
} from "react-native-reanimated";

interface Props {
  isLiked: boolean;
  onPress: () => void;
}

export default function LikeButton({ isLiked, onPress }: Props) {
  const scale = useSharedValue(1);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePress = useCallback(() => {
    scale.value = withSequence(
      withSpring(1.4, { damping: 4, stiffness: 300 }),
      withSpring(1, { damping: 6, stiffness: 200 })
    );
    onPress();
  }, [onPress]);

  return (
    <Pressable onPress={handlePress}>
      <Animated.Text style={[styles.icon, animatedStyle]}>
        {isLiked ? "❤️" : "🤍"}
      </Animated.Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  icon: { fontSize: 26 },
});
```

## src/components/PostCard.tsx

```typescript
import React, { useState } from "react";
import { View, Text, Image, StyleSheet, Pressable } from "react-native";
import LikeButton from "./LikeButton";
import CommentInput from "./CommentInput";
import type { Post } from "../types";

interface Props {
  post: Post;
  onLike: () => void;
  onComment: (text: string) => void;
}

export default function PostCard({ post, onLike, onComment }: Props) {
  const [showComments, setShowComments] = useState(false);

  const timeAgo = () => {
    const diff = Date.now() - new Date(post.createdAt).getTime();
    const hours = Math.floor(diff / 3600000);
    if (hours < 1) return "방금 전";
    if (hours < 24) return `${hours}시간 전`;
    return `${Math.floor(hours / 24)}일 전`;
  };

  return (
    <View style={styles.container}>
      {/* 헤더 */}
      <View style={styles.header}>
        <Image source={{ uri: post.user.avatarUrl }} style={styles.avatar} />
        <Text style={styles.username}>{post.user.username}</Text>
        <Text style={styles.more}>⋯</Text>
      </View>

      {/* 이미지 */}
      <Image source={{ uri: post.imageUrl }} style={styles.image} />

      {/* 액션 버튼 */}
      <View style={styles.actions}>
        <LikeButton isLiked={post.isLiked} onPress={onLike} />
        <Pressable onPress={() => setShowComments(!showComments)}>
          <Text style={styles.actionIcon}>💬</Text>
        </Pressable>
        <Pressable>
          <Text style={styles.actionIcon}>📤</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        <Pressable>
          <Text style={styles.actionIcon}>🔖</Text>
        </Pressable>
      </View>

      {/* 좋아요 수 */}
      <Text style={styles.likes}>좋아요 {post.likes.toLocaleString()}개</Text>

      {/* 캡션 */}
      <Text style={styles.caption}>
        <Text style={styles.captionUser}>{post.user.username} </Text>
        {post.caption}
      </Text>

      {/* 댓글 */}
      {post.comments.length > 0 && (
        <Pressable onPress={() => setShowComments(!showComments)}>
          <Text style={styles.commentCount}>
            댓글 {post.comments.length}개 모두 보기
          </Text>
        </Pressable>
      )}

      {showComments && post.comments.map((c) => (
        <Text key={c.id} style={styles.comment}>
          <Text style={styles.commentUser}>{c.username} </Text>
          {c.text}
        </Text>
      ))}

      {/* 댓글 입력 */}
      {showComments && <CommentInput onSubmit={onComment} />}

      {/* 시간 */}
      <Text style={styles.time}>{timeAgo()}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: "#fff", marginBottom: 8 },
  header: { flexDirection: "row", alignItems: "center", padding: 12 },
  avatar: { width: 36, height: 36, borderRadius: 18, marginRight: 10 },
  username: { fontWeight: "700", fontSize: 14, flex: 1 },
  more: { fontSize: 18, color: "#666" },
  image: { width: "100%", aspectRatio: 1 },
  actions: { flexDirection: "row", alignItems: "center", padding: 12, gap: 16 },
  actionIcon: { fontSize: 24 },
  likes: { fontWeight: "700", paddingHorizontal: 12, fontSize: 14 },
  caption: { paddingHorizontal: 12, paddingTop: 4, fontSize: 14 },
  captionUser: { fontWeight: "700" },
  commentCount: { paddingHorizontal: 12, paddingTop: 4, color: "#999", fontSize: 13 },
  comment: { paddingHorizontal: 12, paddingTop: 2, fontSize: 13 },
  commentUser: { fontWeight: "700" },
  time: { paddingHorizontal: 12, paddingTop: 4, paddingBottom: 8, color: "#999", fontSize: 11 },
});
```

## src/components/CommentInput.tsx

```typescript
import React, { useState } from "react";
import { View, TextInput, Pressable, Text, StyleSheet } from "react-native";

interface Props {
  onSubmit: (text: string) => void;
}

export default function CommentInput({ onSubmit }: Props) {
  const [text, setText] = useState("");

  const handleSubmit = () => {
    if (!text.trim()) return;
    onSubmit(text.trim());
    setText("");
  };

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.input}
        placeholder="댓글 달기..."
        value={text}
        onChangeText={setText}
        onSubmitEditing={handleSubmit}
        returnKeyType="send"
      />
      {text.trim().length > 0 && (
        <Pressable onPress={handleSubmit}>
          <Text style={styles.submit}>게시</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 8, borderTopWidth: 0.5, borderTopColor: "#eee" },
  input: { flex: 1, fontSize: 14, paddingVertical: 4 },
  submit: { color: "#3897f0", fontWeight: "700", fontSize: 14, marginLeft: 8 },
});
```

## src/components/ProfileHeader.tsx

```typescript
import React from "react";
import { View, Text, Image, StyleSheet, Pressable } from "react-native";
import type { User } from "../types";

interface Props {
  user: User;
}

export default function ProfileHeader({ user }: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.top}>
        <Image source={{ uri: user.avatarUrl }} style={styles.avatar} />
        <View style={styles.stats}>
          <StatItem label="게시물" value={user.postsCount} />
          <StatItem label="팔로워" value={user.followersCount} />
          <StatItem label="팔로잉" value={user.followingCount} />
        </View>
      </View>
      <Text style={styles.displayName}>{user.displayName}</Text>
      <Text style={styles.bio}>{user.bio}</Text>
      <Pressable style={styles.editBtn}>
        <Text style={styles.editText}>프로필 편집</Text>
      </Pressable>
    </View>
  );
}

function StatItem({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.statItem}>
      <Text style={styles.statValue}>{value.toLocaleString()}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, backgroundColor: "#fff" },
  top: { flexDirection: "row", alignItems: "center" },
  avatar: { width: 80, height: 80, borderRadius: 40, marginRight: 24 },
  stats: { flex: 1, flexDirection: "row", justifyContent: "space-around" },
  statItem: { alignItems: "center" },
  statValue: { fontWeight: "700", fontSize: 16 },
  statLabel: { fontSize: 12, color: "#666", marginTop: 2 },
  displayName: { fontWeight: "700", fontSize: 14, marginTop: 12 },
  bio: { fontSize: 14, color: "#333", marginTop: 4 },
  editBtn: { marginTop: 12, borderWidth: 1, borderColor: "#ddd", borderRadius: 8, paddingVertical: 6, alignItems: "center" },
  editText: { fontWeight: "600", fontSize: 14 },
});
```

## src/screens/FeedScreen.tsx

```typescript
import React from "react";
import { FlatList, Text, StyleSheet, SafeAreaView } from "react-native";
import PostCard from "../components/PostCard";
import { useFeedStore } from "../store/useFeedStore";

export default function FeedScreen() {
  const { posts, isRefreshing, toggleLike, addComment, refreshFeed } = useFeedStore();

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.logo}>SNS Feed</Text>
      <FlatList
        data={posts}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <PostCard
            post={item}
            onLike={() => toggleLike(item.id)}
            onComment={(text) => addComment(item.id, text)}
          />
        )}
        refreshing={isRefreshing}
        onRefresh={refreshFeed}
        showsVerticalScrollIndicator={false}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fafafa" },
  logo: { fontSize: 22, fontWeight: "800", textAlign: "center", paddingVertical: 12, backgroundColor: "#fff", borderBottomWidth: 0.5, borderBottomColor: "#ddd" },
});
```

## App.tsx

```typescript
import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import FeedScreen from "./src/screens/FeedScreen";
import ProfileScreen from "./src/screens/ProfileScreen";

const Tab = createBottomTabNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <Tab.Navigator screenOptions={{ headerShown: false }}>
        <Tab.Screen name="Feed" component={FeedScreen} options={{ tabBarIcon: () => null, tabBarLabel: "홈" }} />
        <Tab.Screen name="Profile" component={ProfileScreen} options={{ tabBarIcon: () => null, tabBarLabel: "프로필" }} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
```

피드 당겨 새로고침, 좋아요 스프링 애니메이션, 댓글 펼침/접힘이 모두 동작합니다.'''),

    # ═══ 7. 음식 배달 앱 ═══
    m("React Native로 음식 배달 앱 만들어줘 전체 코드로",
'''React Native 음식 배달 앱을 만들어 드릴게요. 음식점 목록, 메뉴 카테고리, 장바구니, 주문 추적 화면을 포함합니다.

## 폴더 구조

```
delivery-app/
├── App.tsx
├── src/
│   ├── screens/
│   │   ├── HomeScreen.tsx
│   │   ├── RestaurantScreen.tsx
│   │   ├── CartScreen.tsx
│   │   └── OrderTrackScreen.tsx
│   ├── components/
│   │   ├── RestaurantCard.tsx
│   │   ├── MenuCategoryTabs.tsx
│   │   ├── MenuItem.tsx
│   │   └── CartItem.tsx
│   ├── store/
│   │   └── useCartStore.ts
│   └── data/
│       └── restaurants.ts
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "delivery-app",
  "version": "1.0.0",
  "scripts": { "start": "expo start", "android": "expo start --android", "ios": "expo start --ios" },
  "dependencies": {
    "expo": "~50.0.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/native-stack": "^6.9.17",
    "react-native-screens": "~3.29.0",
    "react-native-safe-area-context": "4.8.2",
    "zustand": "^4.5.0"
  }
}
```

## src/data/restaurants.ts

```typescript
export interface MenuItemType {
  id: string;
  name: string;
  description: string;
  price: number;
  imageUrl: string;
  category: string;
}

export interface Restaurant {
  id: string;
  name: string;
  imageUrl: string;
  rating: number;
  reviewCount: number;
  deliveryTime: string;
  deliveryFee: number;
  categories: string[];
  menu: MenuItemType[];
}

export const RESTAURANTS: Restaurant[] = [
  {
    id: "r1",
    name: "김치찌개 명가",
    imageUrl: "https://picsum.photos/400/200?random=10",
    rating: 4.7,
    reviewCount: 342,
    deliveryTime: "25-35분",
    deliveryFee: 2000,
    categories: ["찌개", "밥", "반찬"],
    menu: [
      { id: "m1", name: "김치찌개", description: "묵은지로 끓인 진한 김치찌개", price: 9000, imageUrl: "https://picsum.photos/100/100?random=20", category: "찌개" },
      { id: "m2", name: "된장찌개", description: "두부와 야채가 듬뿍", price: 8500, imageUrl: "https://picsum.photos/100/100?random=21", category: "찌개" },
      { id: "m3", name: "공기밥", description: "국내산 쌀", price: 1000, imageUrl: "https://picsum.photos/100/100?random=22", category: "밥" },
      { id: "m4", name: "계란말이", description: "바삭하게 구운 계란말이", price: 5000, imageUrl: "https://picsum.photos/100/100?random=23", category: "반찬" },
      { id: "m5", name: "김치전", description: "바삭한 김치전", price: 7000, imageUrl: "https://picsum.photos/100/100?random=24", category: "반찬" },
    ],
  },
  {
    id: "r2",
    name: "피자 팩토리",
    imageUrl: "https://picsum.photos/400/200?random=11",
    rating: 4.5,
    reviewCount: 218,
    deliveryTime: "30-40분",
    deliveryFee: 3000,
    categories: ["피자", "파스타", "사이드"],
    menu: [
      { id: "m6", name: "마르게리타", description: "토마토, 모짜렐라, 바질", price: 15000, imageUrl: "https://picsum.photos/100/100?random=25", category: "피자" },
      { id: "m7", name: "페퍼로니", description: "페퍼로니 듬뿍", price: 17000, imageUrl: "https://picsum.photos/100/100?random=26", category: "피자" },
      { id: "m8", name: "까르보나라", description: "크리미한 까르보나라", price: 12000, imageUrl: "https://picsum.photos/100/100?random=27", category: "파스타" },
      { id: "m9", name: "감자튀김", description: "바삭한 감자튀김", price: 5000, imageUrl: "https://picsum.photos/100/100?random=28", category: "사이드" },
      { id: "m10", name: "콜라", description: "500ml", price: 2000, imageUrl: "https://picsum.photos/100/100?random=29", category: "사이드" },
    ],
  },
  {
    id: "r3",
    name: "초밥 장인",
    imageUrl: "https://picsum.photos/400/200?random=12",
    rating: 4.9,
    reviewCount: 567,
    deliveryTime: "20-30분",
    deliveryFee: 0,
    categories: ["초밥", "롤", "사시미"],
    menu: [
      { id: "m11", name: "모둠초밥 12p", description: "신선한 초밥 12피스", price: 22000, imageUrl: "https://picsum.photos/100/100?random=30", category: "초밥" },
      { id: "m12", name: "연어초밥 6p", description: "노르웨이산 연어", price: 14000, imageUrl: "https://picsum.photos/100/100?random=31", category: "초밥" },
      { id: "m13", name: "캘리포니아롤", description: "아보카도 캘리포니아롤", price: 12000, imageUrl: "https://picsum.photos/100/100?random=32", category: "롤" },
      { id: "m14", name: "연어사시미", description: "두툼한 연어회", price: 18000, imageUrl: "https://picsum.photos/100/100?random=33", category: "사시미" },
    ],
  },
];
```

## src/store/useCartStore.ts

```typescript
import { create } from "zustand";
import type { MenuItemType } from "../data/restaurants";

export interface CartItemType {
  menu: MenuItemType;
  quantity: number;
  restaurantId: string;
  restaurantName: string;
}

interface CartState {
  items: CartItemType[];
  addItem: (menu: MenuItemType, restaurantId: string, restaurantName: string) => void;
  removeItem: (menuId: string) => void;
  updateQuantity: (menuId: string, delta: number) => void;
  clearCart: () => void;
  totalPrice: () => number;
  totalItems: () => number;
}

export const useCartStore = create<CartState>((set, get) => ({
  items: [],

  addItem: (menu, restaurantId, restaurantName) =>
    set((state) => {
      const existing = state.items.find((i) => i.menu.id === menu.id);
      if (existing) {
        return { items: state.items.map((i) => i.menu.id === menu.id ? { ...i, quantity: i.quantity + 1 } : i) };
      }
      return { items: [...state.items, { menu, quantity: 1, restaurantId, restaurantName }] };
    }),

  removeItem: (menuId) =>
    set((state) => ({ items: state.items.filter((i) => i.menu.id !== menuId) })),

  updateQuantity: (menuId, delta) =>
    set((state) => ({
      items: state.items
        .map((i) => i.menu.id === menuId ? { ...i, quantity: i.quantity + delta } : i)
        .filter((i) => i.quantity > 0),
    })),

  clearCart: () => set({ items: [] }),

  totalPrice: () => get().items.reduce((sum, i) => sum + i.menu.price * i.quantity, 0),

  totalItems: () => get().items.reduce((sum, i) => sum + i.quantity, 0),
}));
```

## src/components/RestaurantCard.tsx

```typescript
import React from "react";
import { View, Text, Image, StyleSheet, Pressable } from "react-native";
import type { Restaurant } from "../data/restaurants";

interface Props {
  restaurant: Restaurant;
  onPress: () => void;
}

export default function RestaurantCard({ restaurant, onPress }: Props) {
  return (
    <Pressable style={styles.card} onPress={onPress}>
      <Image source={{ uri: restaurant.imageUrl }} style={styles.image} />
      <View style={styles.info}>
        <Text style={styles.name}>{restaurant.name}</Text>
        <View style={styles.meta}>
          <Text style={styles.rating}>⭐ {restaurant.rating}</Text>
          <Text style={styles.review}>({restaurant.reviewCount})</Text>
          <Text style={styles.dot}> · </Text>
          <Text style={styles.time}>{restaurant.deliveryTime}</Text>
        </View>
        <Text style={styles.fee}>
          {restaurant.deliveryFee === 0 ? "무료배달" : `배달비 ${restaurant.deliveryFee.toLocaleString()}원`}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: "#fff", borderRadius: 12, marginBottom: 12, overflow: "hidden", elevation: 2, shadowColor: "#000", shadowOpacity: 0.1, shadowRadius: 4 },
  image: { width: "100%", height: 160 },
  info: { padding: 12 },
  name: { fontSize: 16, fontWeight: "700" },
  meta: { flexDirection: "row", alignItems: "center", marginTop: 4 },
  rating: { fontSize: 13, fontWeight: "600" },
  review: { fontSize: 12, color: "#888", marginLeft: 2 },
  dot: { color: "#ccc" },
  time: { fontSize: 12, color: "#666" },
  fee: { fontSize: 12, color: "#e74c3c", marginTop: 4 },
});
```

## src/components/MenuItem.tsx

```typescript
import React from "react";
import { View, Text, Image, StyleSheet, Pressable } from "react-native";
import type { MenuItemType } from "../data/restaurants";

interface Props {
  item: MenuItemType;
  onAdd: () => void;
}

export default function MenuItem({ item, onAdd }: Props) {
  return (
    <View style={styles.row}>
      <View style={styles.info}>
        <Text style={styles.name}>{item.name}</Text>
        <Text style={styles.desc} numberOfLines={2}>{item.description}</Text>
        <Text style={styles.price}>{item.price.toLocaleString()}원</Text>
      </View>
      <Image source={{ uri: item.imageUrl }} style={styles.image} />
      <Pressable style={styles.addBtn} onPress={onAdd}>
        <Text style={styles.addText}>+</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", padding: 12, borderBottomWidth: 0.5, borderBottomColor: "#eee", alignItems: "center" },
  info: { flex: 1, marginRight: 12 },
  name: { fontSize: 15, fontWeight: "600" },
  desc: { fontSize: 12, color: "#888", marginTop: 2 },
  price: { fontSize: 14, fontWeight: "700", marginTop: 4 },
  image: { width: 70, height: 70, borderRadius: 8 },
  addBtn: { position: "absolute", right: 8, bottom: 8, backgroundColor: "#3498db", width: 28, height: 28, borderRadius: 14, justifyContent: "center", alignItems: "center" },
  addText: { color: "#fff", fontSize: 18, fontWeight: "700", lineHeight: 20 },
});
```

## src/components/MenuCategoryTabs.tsx

```typescript
import React from "react";
import { ScrollView, Pressable, Text, StyleSheet } from "react-native";

interface Props {
  categories: string[];
  active: string;
  onChange: (cat: string) => void;
}

export default function MenuCategoryTabs({ categories, active, onChange }: Props) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.container}>
      {categories.map((cat) => (
        <Pressable key={cat} style={[styles.tab, active === cat && styles.activeTab]} onPress={() => onChange(cat)}>
          <Text style={[styles.label, active === cat && styles.activeLabel]}>{cat}</Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: "#fff", paddingVertical: 8 },
  tab: { paddingHorizontal: 16, paddingVertical: 8, marginHorizontal: 4, borderRadius: 20, backgroundColor: "#f0f0f0" },
  activeTab: { backgroundColor: "#3498db" },
  label: { fontSize: 14, color: "#333" },
  activeLabel: { color: "#fff", fontWeight: "600" },
});
```

## src/screens/OrderTrackScreen.tsx

```typescript
import React, { useState, useEffect } from "react";
import { View, Text, StyleSheet, SafeAreaView } from "react-native";

const STEPS = [
  { key: "accepted", label: "주문 접수", icon: "📋" },
  { key: "preparing", label: "조리 중", icon: "👨‍🍳" },
  { key: "delivering", label: "배달 중", icon: "🛵" },
  { key: "done", label: "배달 완료", icon: "✅" },
];

export default function OrderTrackScreen() {
  const [currentStep, setCurrentStep] = useState(0);
  const [estimatedMin, setEstimatedMin] = useState(30);

  useEffect(() => {
    // 데모: 5초마다 단계 진행
    const timer = setInterval(() => {
      setCurrentStep((prev) => {
        if (prev >= STEPS.length - 1) {
          clearInterval(timer);
          return prev;
        }
        setEstimatedMin((m) => Math.max(0, m - 10));
        return prev + 1;
      });
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.title}>주문 현황</Text>
      <Text style={styles.estimate}>
        {currentStep < STEPS.length - 1
          ? `약 ${estimatedMin}분 후 도착 예정`
          : "배달이 완료되었습니다!"}
      </Text>

      <View style={styles.steps}>
        {STEPS.map((step, idx) => (
          <View key={step.key} style={styles.stepRow}>
            <View style={[styles.circle, idx <= currentStep && styles.activeCircle]}>
              <Text style={styles.stepIcon}>{step.icon}</Text>
            </View>
            <Text style={[styles.stepLabel, idx <= currentStep && styles.activeLabel]}>
              {step.label}
            </Text>
            {idx < STEPS.length - 1 && (
              <View style={[styles.line, idx < currentStep && styles.activeLine]} />
            )}
          </View>
        ))}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff", padding: 20 },
  title: { fontSize: 22, fontWeight: "700", textAlign: "center" },
  estimate: { fontSize: 16, color: "#3498db", textAlign: "center", marginTop: 8, marginBottom: 32 },
  steps: { paddingLeft: 20 },
  stepRow: { flexDirection: "row", alignItems: "center", marginBottom: 32, position: "relative" },
  circle: { width: 48, height: 48, borderRadius: 24, backgroundColor: "#eee", justifyContent: "center", alignItems: "center" },
  activeCircle: { backgroundColor: "#e8f5e9" },
  stepIcon: { fontSize: 22 },
  stepLabel: { marginLeft: 16, fontSize: 16, color: "#999" },
  activeLabel: { color: "#333", fontWeight: "600" },
  line: { position: "absolute", left: 23, top: 48, width: 2, height: 32, backgroundColor: "#eee" },
  activeLine: { backgroundColor: "#4caf50" },
});
```

## App.tsx

```typescript
import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import HomeScreen from "./src/screens/HomeScreen";
import RestaurantScreen from "./src/screens/RestaurantScreen";
import CartScreen from "./src/screens/CartScreen";
import OrderTrackScreen from "./src/screens/OrderTrackScreen";

const Stack = createNativeStackNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="Home" component={HomeScreen} options={{ title: "배달의장인" }} />
        <Stack.Screen name="Restaurant" component={RestaurantScreen} options={{ title: "" }} />
        <Stack.Screen name="Cart" component={CartScreen} options={{ title: "장바구니" }} />
        <Stack.Screen name="OrderTrack" component={OrderTrackScreen} options={{ title: "주문 추적", headerBackVisible: false }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
```

음식점 목록에서 터치하면 메뉴로 이동하고, 장바구니에서 수량 조절 후 주문하면 실시간 추적 화면이 표시됩니다.'''),

    # ═══ 8. 뉴스 리더 앱 ═══
    m("React Native로 뉴스 리더 앱 만들어줘 전체 코드로",
'''React Native 뉴스 리더 앱을 만들어 드릴게요. 카테고리 탭, WebView 기사 보기, 북마크, 공유, 다크모드를 포함합니다.

## 폴더 구조

```
news-reader/
├── App.tsx
├── src/
│   ├── screens/
│   │   ├── FeedScreen.tsx
│   │   ├── ArticleScreen.tsx
│   │   └── BookmarkScreen.tsx
│   ├── components/
│   │   ├── CategoryTabs.tsx
│   │   ├── ArticleCard.tsx
│   │   └── ThemeToggle.tsx
│   ├── store/
│   │   └── useNewsStore.ts
│   └── context/
│       └── ThemeContext.tsx
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "news-reader",
  "version": "1.0.0",
  "scripts": { "start": "expo start", "android": "expo start --android", "ios": "expo start --ios" },
  "dependencies": {
    "expo": "~50.0.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/bottom-tabs": "^6.5.12",
    "@react-navigation/native-stack": "^6.9.17",
    "react-native-screens": "~3.29.0",
    "react-native-safe-area-context": "4.8.2",
    "react-native-webview": "13.6.4",
    "zustand": "^4.5.0",
    "expo-sharing": "~1.11.0",
    "@react-native-async-storage/async-storage": "1.21.0"
  }
}
```

## src/context/ThemeContext.tsx

```typescript
import React, { createContext, useContext, useState, useMemo, ReactNode } from "react";
import { useColorScheme } from "react-native";

interface Theme {
  dark: boolean;
  colors: {
    bg: string;
    card: string;
    text: string;
    textSecondary: string;
    border: string;
    primary: string;
    tabBar: string;
  };
}

const lightTheme: Theme = {
  dark: false,
  colors: {
    bg: "#f5f5f5",
    card: "#ffffff",
    text: "#111111",
    textSecondary: "#666666",
    border: "#eeeeee",
    primary: "#1a73e8",
    tabBar: "#ffffff",
  },
};

const darkTheme: Theme = {
  dark: true,
  colors: {
    bg: "#121212",
    card: "#1e1e1e",
    text: "#e0e0e0",
    textSecondary: "#999999",
    border: "#333333",
    primary: "#8ab4f8",
    tabBar: "#1e1e1e",
  },
};

const ThemeContext = createContext<{ theme: Theme; toggleTheme: () => void }>({
  theme: lightTheme,
  toggleTheme: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const systemScheme = useColorScheme();
  const [isDark, setIsDark] = useState(systemScheme === "dark");

  const value = useMemo(
    () => ({
      theme: isDark ? darkTheme : lightTheme,
      toggleTheme: () => setIsDark((prev) => !prev),
    }),
    [isDark]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
```

## src/store/useNewsStore.ts

```typescript
import { create } from "zustand";

export interface Article {
  id: string;
  title: string;
  summary: string;
  imageUrl: string;
  url: string;
  source: string;
  category: string;
  publishedAt: string;
  isBookmarked: boolean;
}

const CATEGORIES = ["전체", "정치", "경제", "IT", "스포츠", "문화"];

const MOCK_ARTICLES: Article[] = Array.from({ length: 30 }, (_, i) => ({
  id: `art-${i + 1}`,
  title: [
    "AI 반도체 시장, 올해 500억 달러 돌파 전망",
    "국내 스타트업 해외 투자 유치 역대 최고",
    "프로야구 개막전 관중 20만 명 돌파",
    "차세대 배터리 기술 상용화 임박",
    "문화재 디지털 복원 프로젝트 성과 발표",
    "금리 인하 기대감에 부동산 시장 활기",
  ][i % 6],
  summary: "기사의 주요 내용을 요약한 텍스트입니다. 자세한 내용은 기사를 확인하세요.",
  imageUrl: `https://picsum.photos/400/200?random=${i + 100}`,
  url: `https://example.com/article/${i + 1}`,
  source: ["한국일보", "경제신문", "IT뉴스", "스포츠투데이", "문화일보"][i % 5],
  category: CATEGORIES[1 + (i % 5)],
  publishedAt: new Date(Date.now() - i * 1800000).toISOString(),
  isBookmarked: false,
}));

interface NewsState {
  articles: Article[];
  activeCategory: string;
  categories: string[];
  isRefreshing: boolean;
  setCategory: (cat: string) => void;
  toggleBookmark: (id: string) => void;
  refreshArticles: () => Promise<void>;
  filteredArticles: () => Article[];
  bookmarkedArticles: () => Article[];
}

export const useNewsStore = create<NewsState>((set, get) => ({
  articles: MOCK_ARTICLES,
  activeCategory: "전체",
  categories: CATEGORIES,
  isRefreshing: false,

  setCategory: (cat) => set({ activeCategory: cat }),

  toggleBookmark: (id) =>
    set((state) => ({
      articles: state.articles.map((a) =>
        a.id === id ? { ...a, isBookmarked: !a.isBookmarked } : a
      ),
    })),

  refreshArticles: async () => {
    set({ isRefreshing: true });
    await new Promise((r) => setTimeout(r, 1000));
    set({ isRefreshing: false });
  },

  filteredArticles: () => {
    const { articles, activeCategory } = get();
    return activeCategory === "전체" ? articles : articles.filter((a) => a.category === activeCategory);
  },

  bookmarkedArticles: () => get().articles.filter((a) => a.isBookmarked),
}));
```

## src/components/CategoryTabs.tsx

```typescript
import React from "react";
import { ScrollView, Pressable, Text, StyleSheet } from "react-native";
import { useTheme } from "../context/ThemeContext";

interface Props {
  categories: string[];
  active: string;
  onSelect: (cat: string) => void;
}

export default function CategoryTabs({ categories, active, onSelect }: Props) {
  const { theme } = useTheme();

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={[styles.container, { backgroundColor: theme.colors.card }]}>
      {categories.map((cat) => (
        <Pressable
          key={cat}
          style={[styles.tab, active === cat && { backgroundColor: theme.colors.primary }]}
          onPress={() => onSelect(cat)}
        >
          <Text style={[styles.label, active === cat ? { color: "#fff" } : { color: theme.colors.text }]}>
            {cat}
          </Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { paddingVertical: 8, paddingHorizontal: 4 },
  tab: { paddingHorizontal: 16, paddingVertical: 8, marginHorizontal: 4, borderRadius: 20, backgroundColor: "#f0f0f0" },
  label: { fontSize: 14, fontWeight: "500" },
});
```

## src/components/ArticleCard.tsx

```typescript
import React from "react";
import { View, Text, Image, StyleSheet, Pressable } from "react-native";
import { useTheme } from "../context/ThemeContext";
import type { Article } from "../store/useNewsStore";

interface Props {
  article: Article;
  onPress: () => void;
  onBookmark: () => void;
}

export default function ArticleCard({ article, onPress, onBookmark }: Props) {
  const { theme } = useTheme();
  const timeAgo = () => {
    const diff = Date.now() - new Date(article.publishedAt).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}분 전`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}시간 전`;
    return `${Math.floor(hours / 24)}일 전`;
  };

  return (
    <Pressable style={[styles.card, { backgroundColor: theme.colors.card }]} onPress={onPress}>
      <Image source={{ uri: article.imageUrl }} style={styles.image} />
      <View style={styles.body}>
        <Text style={[styles.title, { color: theme.colors.text }]} numberOfLines={2}>
          {article.title}
        </Text>
        <Text style={[styles.summary, { color: theme.colors.textSecondary }]} numberOfLines={2}>
          {article.summary}
        </Text>
        <View style={styles.footer}>
          <Text style={[styles.source, { color: theme.colors.textSecondary }]}>
            {article.source} · {timeAgo()}
          </Text>
          <Pressable onPress={onBookmark}>
            <Text style={styles.bookmark}>{article.isBookmarked ? "🔖" : "📑"}</Text>
          </Pressable>
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: 12, marginHorizontal: 16, marginBottom: 12, overflow: "hidden", elevation: 2, shadowColor: "#000", shadowOpacity: 0.08, shadowRadius: 4 },
  image: { width: "100%", height: 180 },
  body: { padding: 12 },
  title: { fontSize: 16, fontWeight: "700", lineHeight: 22 },
  summary: { fontSize: 13, marginTop: 4, lineHeight: 18 },
  footer: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8 },
  source: { fontSize: 12 },
  bookmark: { fontSize: 20 },
});
```

## src/components/ThemeToggle.tsx

```typescript
import React from "react";
import { Pressable, Text, StyleSheet } from "react-native";
import { useTheme } from "../context/ThemeContext";

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <Pressable onPress={toggleTheme} style={styles.btn}>
      <Text style={styles.icon}>{theme.dark ? "☀️" : "🌙"}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: { marginRight: 12 },
  icon: { fontSize: 22 },
});
```

## src/screens/FeedScreen.tsx

```typescript
import React from "react";
import { FlatList, SafeAreaView, StyleSheet } from "react-native";
import CategoryTabs from "../components/CategoryTabs";
import ArticleCard from "../components/ArticleCard";
import { useNewsStore } from "../store/useNewsStore";
import { useTheme } from "../context/ThemeContext";
import { useNavigation } from "@react-navigation/native";

export default function FeedScreen() {
  const { categories, activeCategory, setCategory, toggleBookmark, isRefreshing, refreshArticles, filteredArticles } = useNewsStore();
  const { theme } = useTheme();
  const navigation = useNavigation<any>();
  const articles = filteredArticles();

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.colors.bg }]}>
      <CategoryTabs categories={categories} active={activeCategory} onSelect={setCategory} />
      <FlatList
        data={articles}
        keyExtractor={(a) => a.id}
        renderItem={({ item }) => (
          <ArticleCard
            article={item}
            onPress={() => navigation.navigate("Article", { article: item })}
            onBookmark={() => toggleBookmark(item.id)}
          />
        )}
        refreshing={isRefreshing}
        onRefresh={refreshArticles}
        contentContainerStyle={{ paddingTop: 8, paddingBottom: 20 }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
});
```

## src/screens/ArticleScreen.tsx

```typescript
import React from "react";
import { View, StyleSheet, Pressable, Text, Share } from "react-native";
import { WebView } from "react-native-webview";
import { useRoute } from "@react-navigation/native";
import type { Article } from "../store/useNewsStore";

export default function ArticleScreen() {
  const route = useRoute<any>();
  const article: Article = route.params.article;

  const handleShare = async () => {
    await Share.share({ title: article.title, url: article.url, message: `${article.title}\n${article.url}` });
  };

  return (
    <View style={styles.container}>
      <WebView source={{ uri: article.url }} style={{ flex: 1 }} startInLoadingState />
      <View style={styles.toolbar}>
        <Text style={styles.source}>{article.source}</Text>
        <Pressable onPress={handleShare}>
          <Text style={styles.share}>공유 📤</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  toolbar: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 12, backgroundColor: "#fff", borderTopWidth: 0.5, borderTopColor: "#ddd" },
  source: { fontSize: 13, color: "#666" },
  share: { fontSize: 14, fontWeight: "600", color: "#1a73e8" },
});
```

## App.tsx

```typescript
import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { ThemeProvider, useTheme } from "./src/context/ThemeContext";
import ThemeToggle from "./src/components/ThemeToggle";
import FeedScreen from "./src/screens/FeedScreen";
import ArticleScreen from "./src/screens/ArticleScreen";
import BookmarkScreen from "./src/screens/BookmarkScreen";

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

function FeedStack() {
  const { theme } = useTheme();
  return (
    <Stack.Navigator screenOptions={{ headerStyle: { backgroundColor: theme.colors.card }, headerTintColor: theme.colors.text }}>
      <Stack.Screen name="FeedMain" component={FeedScreen} options={{ title: "뉴스", headerRight: () => <ThemeToggle /> }} />
      <Stack.Screen name="Article" component={ArticleScreen} options={{ title: "기사" }} />
    </Stack.Navigator>
  );
}

function AppTabs() {
  const { theme } = useTheme();
  return (
    <Tab.Navigator screenOptions={{ headerShown: false, tabBarStyle: { backgroundColor: theme.colors.tabBar } }}>
      <Tab.Screen name="Feed" component={FeedStack} options={{ tabBarLabel: "뉴스", tabBarIcon: () => null }} />
      <Tab.Screen name="Bookmarks" component={BookmarkScreen} options={{ tabBarLabel: "북마크", tabBarIcon: () => null }} />
    </Tab.Navigator>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <NavigationContainer>
        <AppTabs />
      </NavigationContainer>
    </ThemeProvider>
  );
}
```

카테고리 탭으로 필터링, 기사 터치 시 WebView 표시, 북마크 저장, 공유, 다크모드 토글이 모두 동작합니다.'''),

    # ═══ 9. QR코드 스캐너 앱 ═══
    m("React Native로 QR코드 스캐너 앱 만들어줘 전체 코드로",
'''React Native QR코드 스캐너 앱을 만들어 드릴게요. 카메라 스캔, 스캔 이력, QR 생성, 결과 처리를 포함합니다.

## 폴더 구조

```
qr-scanner-app/
├── App.tsx
├── src/
│   ├── screens/
│   │   ├── ScanScreen.tsx
│   │   ├── HistoryScreen.tsx
│   │   └── GenerateScreen.tsx
│   ├── components/
│   │   ├── ScanOverlay.tsx
│   │   ├── ResultModal.tsx
│   │   └── HistoryItem.tsx
│   ├── store/
│   │   └── useScanStore.ts
│   └── utils/
│       └── resultHandler.ts
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "qr-scanner-app",
  "version": "1.0.0",
  "scripts": { "start": "expo start", "android": "expo start --android", "ios": "expo start --ios" },
  "dependencies": {
    "expo": "~50.0.0",
    "expo-camera": "~14.0.0",
    "expo-barcode-scanner": "~12.9.0",
    "expo-haptics": "~12.8.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/bottom-tabs": "^6.5.12",
    "react-native-screens": "~3.29.0",
    "react-native-safe-area-context": "4.8.2",
    "react-native-qrcode-svg": "^6.2.0",
    "react-native-svg": "14.1.0",
    "zustand": "^4.5.0",
    "@react-native-async-storage/async-storage": "1.21.0"
  }
}
```

## src/utils/resultHandler.ts

```typescript
import { Linking } from "react-native";

export type ResultType = "url" | "text" | "contact" | "wifi" | "email" | "phone";

export interface ScanResult {
  type: ResultType;
  raw: string;
  display: string;
  action?: string;
}

export function parseQRResult(data: string): ScanResult {
  // URL
  if (/^https?:\/\//i.test(data)) {
    return { type: "url", raw: data, display: data, action: "브라우저로 열기" };
  }

  // 이메일
  if (/^mailto:/i.test(data) || /^[\w.-]+@[\w.-]+\.\w+$/.test(data)) {
    const email = data.replace(/^mailto:/i, "");
    return { type: "email", raw: data, display: email, action: "이메일 보내기" };
  }

  // 전화번호
  if (/^tel:/i.test(data) || /^(\+?\d{2,3}[-\s]?\d{3,4}[-\s]?\d{4})$/.test(data)) {
    const phone = data.replace(/^tel:/i, "");
    return { type: "phone", raw: data, display: phone, action: "전화 걸기" };
  }

  // WiFi
  if (/^WIFI:/i.test(data)) {
    const ssid = data.match(/S:([^;]*)/)?.[1] || "Unknown";
    return { type: "wifi", raw: data, display: `WiFi: ${ssid}`, action: "네트워크 설정 열기" };
  }

  // vCard (연락처)
  if (/^BEGIN:VCARD/i.test(data)) {
    const name = data.match(/FN:(.+)/)?.[1] || "연락처";
    return { type: "contact", raw: data, display: name, action: "연락처에 추가" };
  }

  // 기본: 텍스트
  return { type: "text", raw: data, display: data };
}

export async function handleAction(result: ScanResult) {
  switch (result.type) {
    case "url":
      await Linking.openURL(result.raw);
      break;
    case "email":
      await Linking.openURL(result.raw.startsWith("mailto:") ? result.raw : `mailto:${result.raw}`);
      break;
    case "phone":
      await Linking.openURL(result.raw.startsWith("tel:") ? result.raw : `tel:${result.raw}`);
      break;
    case "wifi":
      await Linking.openSettings();
      break;
  }
}
```

## src/store/useScanStore.ts

```typescript
import { create } from "zustand";
import type { ScanResult } from "../utils/resultHandler";

export interface HistoryEntry {
  id: string;
  result: ScanResult;
  scannedAt: string;
}

interface ScanState {
  history: HistoryEntry[];
  addScan: (result: ScanResult) => void;
  removeScan: (id: string) => void;
  clearHistory: () => void;
}

export const useScanStore = create<ScanState>((set) => ({
  history: [],

  addScan: (result) =>
    set((state) => ({
      history: [
        { id: `scan-${Date.now()}`, result, scannedAt: new Date().toISOString() },
        ...state.history,
      ].slice(0, 100), // 최대 100건
    })),

  removeScan: (id) =>
    set((state) => ({ history: state.history.filter((h) => h.id !== id) })),

  clearHistory: () => set({ history: [] }),
}));
```

## src/components/ScanOverlay.tsx

```typescript
import React from "react";
import { View, StyleSheet, Dimensions } from "react-native";

const { width } = Dimensions.get("window");
const SCAN_SIZE = width * 0.7;

export default function ScanOverlay() {
  return (
    <View style={styles.container}>
      <View style={styles.top} />
      <View style={styles.middle}>
        <View style={styles.side} />
        <View style={styles.scanArea}>
          {/* 코너 표시 */}
          <View style={[styles.corner, styles.topLeft]} />
          <View style={[styles.corner, styles.topRight]} />
          <View style={[styles.corner, styles.bottomLeft]} />
          <View style={[styles.corner, styles.bottomRight]} />
        </View>
        <View style={styles.side} />
      </View>
      <View style={styles.bottom} />
    </View>
  );
}

const OVERLAY = "rgba(0,0,0,0.6)";
const CORNER_LEN = 24;
const CORNER_WIDTH = 4;

const styles = StyleSheet.create({
  container: { ...StyleSheet.absoluteFillObject },
  top: { flex: 1, backgroundColor: OVERLAY },
  middle: { flexDirection: "row", height: SCAN_SIZE },
  side: { flex: 1, backgroundColor: OVERLAY },
  scanArea: { width: SCAN_SIZE, height: SCAN_SIZE, borderRadius: 4, position: "relative" },
  bottom: { flex: 1, backgroundColor: OVERLAY },
  corner: { position: "absolute", borderColor: "#00ff88" },
  topLeft: { top: 0, left: 0, borderTopWidth: CORNER_WIDTH, borderLeftWidth: CORNER_WIDTH, width: CORNER_LEN, height: CORNER_LEN },
  topRight: { top: 0, right: 0, borderTopWidth: CORNER_WIDTH, borderRightWidth: CORNER_WIDTH, width: CORNER_LEN, height: CORNER_LEN },
  bottomLeft: { bottom: 0, left: 0, borderBottomWidth: CORNER_WIDTH, borderLeftWidth: CORNER_WIDTH, width: CORNER_LEN, height: CORNER_LEN },
  bottomRight: { bottom: 0, right: 0, borderBottomWidth: CORNER_WIDTH, borderRightWidth: CORNER_WIDTH, width: CORNER_LEN, height: CORNER_LEN },
});
```

## src/components/ResultModal.tsx

```typescript
import React from "react";
import { View, Text, Modal, Pressable, StyleSheet } from "react-native";
import type { ScanResult } from "../utils/resultHandler";

interface Props {
  visible: boolean;
  result: ScanResult | null;
  onClose: () => void;
  onAction: () => void;
  onCopy: () => void;
}

const TYPE_ICONS: Record<string, string> = {
  url: "🔗", text: "📝", contact: "👤", wifi: "📶", email: "📧", phone: "📞",
};

export default function ResultModal({ visible, result, onClose, onAction, onCopy }: Props) {
  if (!result) return null;
  return (
    <Modal transparent visible={visible} animationType="slide">
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <Text style={styles.icon}>{TYPE_ICONS[result.type] || "📄"}</Text>
          <Text style={styles.type}>{result.type.toUpperCase()}</Text>
          <Text style={styles.display} selectable>{result.display}</Text>
          <View style={styles.actions}>
            <Pressable style={styles.btn} onPress={onCopy}>
              <Text style={styles.btnText}>복사</Text>
            </Pressable>
            {result.action && (
              <Pressable style={[styles.btn, styles.primaryBtn]} onPress={onAction}>
                <Text style={[styles.btnText, styles.primaryText]}>{result.action}</Text>
              </Pressable>
            )}
          </View>
          <Pressable onPress={onClose}>
            <Text style={styles.close}>닫기</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.5)" },
  sheet: { backgroundColor: "#fff", borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, alignItems: "center" },
  icon: { fontSize: 40 },
  type: { fontSize: 12, color: "#888", marginTop: 4, letterSpacing: 2 },
  display: { fontSize: 16, textAlign: "center", marginTop: 12, marginBottom: 20, lineHeight: 22 },
  actions: { flexDirection: "row", gap: 12, marginBottom: 16 },
  btn: { paddingVertical: 10, paddingHorizontal: 24, borderRadius: 8, borderWidth: 1, borderColor: "#ddd" },
  primaryBtn: { backgroundColor: "#3498db", borderColor: "#3498db" },
  btnText: { fontSize: 15, fontWeight: "600" },
  primaryText: { color: "#fff" },
  close: { fontSize: 14, color: "#999", paddingVertical: 8 },
});
```

## src/screens/ScanScreen.tsx

```typescript
import React, { useState, useCallback } from "react";
import { View, Text, StyleSheet, Alert } from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Haptics from "expo-haptics";
import * as Clipboard from "expo-clipboard";
import ScanOverlay from "../components/ScanOverlay";
import ResultModal from "../components/ResultModal";
import { parseQRResult, handleAction } from "../utils/resultHandler";
import { useScanStore } from "../store/useScanStore";
import type { ScanResult } from "../utils/resultHandler";

export default function ScanScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [result, setResult] = useState<ScanResult | null>(null);
  const addScan = useScanStore((s) => s.addScan);

  const handleBarCodeScanned = useCallback(({ data }: { data: string }) => {
    if (scanned) return;
    setScanned(true);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    const parsed = parseQRResult(data);
    setResult(parsed);
    addScan(parsed);
  }, [scanned, addScan]);

  if (!permission) return <View />;
  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.permText}>카메라 권한이 필요합니다</Text>
        <Text style={styles.permBtn} onPress={requestPermission}>권한 허용</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        style={StyleSheet.absoluteFillObject}
        barcodeScannerSettings={{ barcodeTypes: ["qr", "ean13", "code128"] }}
        onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
      />
      <ScanOverlay />
      <Text style={styles.hint}>QR 코드를 사각형 안에 맞춰주세요</Text>
      <ResultModal
        visible={!!result}
        result={result}
        onClose={() => { setResult(null); setScanned(false); }}
        onAction={async () => {
          if (result) await handleAction(result);
          setResult(null);
          setScanned(false);
        }}
        onCopy={async () => {
          if (result) {
            await Clipboard.setStringAsync(result.raw);
            Alert.alert("복사 완료", "클립보드에 복사되었습니다.");
          }
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  permText: { fontSize: 16, marginBottom: 12 },
  permBtn: { fontSize: 16, color: "#3498db", fontWeight: "600" },
  hint: { position: "absolute", bottom: 120, alignSelf: "center", color: "#fff", fontSize: 14, backgroundColor: "rgba(0,0,0,0.5)", paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 },
});
```

## src/screens/GenerateScreen.tsx

```typescript
import React, { useState } from "react";
import { View, Text, TextInput, StyleSheet, SafeAreaView, ScrollView, Pressable } from "react-native";
import QRCode from "react-native-qrcode-svg";

type QRType = "text" | "url" | "wifi";

export default function GenerateScreen() {
  const [type, setType] = useState<QRType>("text");
  const [text, setText] = useState("");
  const [wifiSSID, setWifiSSID] = useState("");
  const [wifiPass, setWifiPass] = useState("");

  const qrValue = () => {
    if (type === "wifi") return `WIFI:S:${wifiSSID};T:WPA;P:${wifiPass};;`;
    if (type === "url" && text && !text.startsWith("http")) return `https://${text}`;
    return text;
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>QR 코드 생성</Text>

        {/* 타입 선택 */}
        <View style={styles.types}>
          {(["text", "url", "wifi"] as QRType[]).map((t) => (
            <Pressable key={t} style={[styles.typeBtn, type === t && styles.activeType]} onPress={() => setType(t)}>
              <Text style={[styles.typeLabel, type === t && styles.activeTypeLabel]}>
                {{ text: "텍스트", url: "URL", wifi: "WiFi" }[t]}
              </Text>
            </Pressable>
          ))}
        </View>

        {/* 입력 */}
        {type === "wifi" ? (
          <>
            <TextInput style={styles.input} placeholder="WiFi 이름 (SSID)" value={wifiSSID} onChangeText={setWifiSSID} />
            <TextInput style={styles.input} placeholder="비밀번호" value={wifiPass} onChangeText={setWifiPass} secureTextEntry />
          </>
        ) : (
          <TextInput
            style={[styles.input, styles.multiline]}
            placeholder={type === "url" ? "https://example.com" : "텍스트를 입력하세요"}
            value={text}
            onChangeText={setText}
            multiline={type === "text"}
          />
        )}

        {/* QR 코드 */}
        {qrValue().length > 0 && (
          <View style={styles.qrBox}>
            <QRCode value={qrValue()} size={200} backgroundColor="#fff" color="#000" />
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  content: { padding: 20, alignItems: "center" },
  title: { fontSize: 22, fontWeight: "700", marginBottom: 20 },
  types: { flexDirection: "row", gap: 8, marginBottom: 20 },
  typeBtn: { paddingHorizontal: 20, paddingVertical: 10, borderRadius: 20, backgroundColor: "#f0f0f0" },
  activeType: { backgroundColor: "#3498db" },
  typeLabel: { fontSize: 14, color: "#333" },
  activeTypeLabel: { color: "#fff", fontWeight: "600" },
  input: { width: "100%", borderWidth: 1, borderColor: "#ddd", borderRadius: 12, padding: 14, fontSize: 16, marginBottom: 12 },
  multiline: { height: 100, textAlignVertical: "top" },
  qrBox: { marginTop: 24, padding: 20, backgroundColor: "#fff", borderRadius: 12, elevation: 4, shadowColor: "#000", shadowOpacity: 0.1, shadowRadius: 8 },
});
```

## src/screens/HistoryScreen.tsx

```typescript
import React from "react";
import { View, Text, FlatList, Pressable, StyleSheet, SafeAreaView, Alert } from "react-native";
import { useScanStore } from "../store/useScanStore";

const TYPE_ICONS: Record<string, string> = {
  url: "🔗", text: "📝", contact: "👤", wifi: "📶", email: "📧", phone: "📞",
};

export default function HistoryScreen() {
  const { history, removeScan, clearHistory } = useScanStore();

  const handleClear = () => {
    Alert.alert("이력 삭제", "모든 스캔 이력을 삭제하시겠습니까?", [
      { text: "취소", style: "cancel" },
      { text: "삭제", style: "destructive", onPress: clearHistory },
    ]);
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>스캔 이력</Text>
        {history.length > 0 && (
          <Pressable onPress={handleClear}>
            <Text style={styles.clear}>전체 삭제</Text>
          </Pressable>
        )}
      </View>
      <FlatList
        data={history}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <Pressable
            style={styles.item}
            onLongPress={() => {
              Alert.alert("삭제", "이 항목을 삭제하시겠습니까?", [
                { text: "취소", style: "cancel" },
                { text: "삭제", style: "destructive", onPress: () => removeScan(item.id) },
              ]);
            }}
          >
            <Text style={styles.icon}>{TYPE_ICONS[item.result.type] || "📄"}</Text>
            <View style={styles.info}>
              <Text style={styles.display} numberOfLines={1}>{item.result.display}</Text>
              <Text style={styles.time}>{new Date(item.scannedAt).toLocaleString("ko-KR")}</Text>
            </View>
          </Pressable>
        )}
        ListEmptyComponent={<Text style={styles.empty}>스캔 이력이 없습니다</Text>}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f9f9f9" },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 16, backgroundColor: "#fff" },
  title: { fontSize: 20, fontWeight: "700" },
  clear: { fontSize: 14, color: "#e74c3c" },
  item: { flexDirection: "row", alignItems: "center", padding: 14, backgroundColor: "#fff", borderBottomWidth: 0.5, borderBottomColor: "#eee" },
  icon: { fontSize: 24, marginRight: 12 },
  info: { flex: 1 },
  display: { fontSize: 15, fontWeight: "500" },
  time: { fontSize: 12, color: "#999", marginTop: 2 },
  empty: { textAlign: "center", marginTop: 60, color: "#999", fontSize: 15 },
});
```

## App.tsx

```typescript
import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import ScanScreen from "./src/screens/ScanScreen";
import HistoryScreen from "./src/screens/HistoryScreen";
import GenerateScreen from "./src/screens/GenerateScreen";

const Tab = createBottomTabNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <Tab.Navigator screenOptions={{ headerShown: false }}>
        <Tab.Screen name="Scan" component={ScanScreen} options={{ tabBarLabel: "스캔", tabBarIcon: () => null }} />
        <Tab.Screen name="History" component={HistoryScreen} options={{ tabBarLabel: "이력", tabBarIcon: () => null }} />
        <Tab.Screen name="Generate" component={GenerateScreen} options={{ tabBarLabel: "생성", tabBarIcon: () => null }} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
```

카메라 스캔 시 햅틱 피드백과 함께 결과 모달이 표시됩니다. URL/전화/이메일/WiFi 유형을 자동 감지합니다.'''),

    # ═══ 10. 채팅 앱 ═══
    m("React Native로 채팅 앱 만들어줘 전체 코드로",
'''React Native 채팅 앱을 만들어 드릴게요. 대화 목록, 채팅방, 이미지 메시지, 타이핑 인디케이터, 자동 스크롤을 포함합니다.

## 폴더 구조

```
chat-app/
├── App.tsx
├── src/
│   ├── screens/
│   │   ├── ConversationListScreen.tsx
│   │   └── ChatRoomScreen.tsx
│   ├── components/
│   │   ├── ConversationItem.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── ChatInput.tsx
│   │   ├── TypingIndicator.tsx
│   │   └── ImageMessage.tsx
│   ├── store/
│   │   └── useChatStore.ts
│   └── types/
│       └── index.ts
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "chat-app",
  "version": "1.0.0",
  "scripts": { "start": "expo start", "android": "expo start --android", "ios": "expo start --ios" },
  "dependencies": {
    "expo": "~50.0.0",
    "expo-image-picker": "~14.7.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/native-stack": "^6.9.17",
    "react-native-screens": "~3.29.0",
    "react-native-safe-area-context": "4.8.2",
    "zustand": "^4.5.0"
  }
}
```

## src/types/index.ts

```typescript
export interface User {
  id: string;
  name: string;
  avatarUrl: string;
  isOnline: boolean;
}

export interface Message {
  id: string;
  senderId: string;
  text?: string;
  imageUrl?: string;
  createdAt: string;
  read: boolean;
}

export interface Conversation {
  id: string;
  participant: User;
  messages: Message[];
  lastMessage: string;
  lastMessageAt: string;
  unreadCount: number;
}
```

## src/store/useChatStore.ts

```typescript
import { create } from "zustand";
import type { Conversation, Message, User } from "../types";

const ME: User = { id: "me", name: "나", avatarUrl: "https://i.pravatar.cc/100?img=68", isOnline: true };

const USERS: User[] = [
  { id: "u1", name: "김민수", avatarUrl: "https://i.pravatar.cc/100?img=1", isOnline: true },
  { id: "u2", name: "이수진", avatarUrl: "https://i.pravatar.cc/100?img=5", isOnline: false },
  { id: "u3", name: "박지호", avatarUrl: "https://i.pravatar.cc/100?img=8", isOnline: true },
  { id: "u4", name: "최유나", avatarUrl: "https://i.pravatar.cc/100?img=9", isOnline: false },
  { id: "u5", name: "정태현", avatarUrl: "https://i.pravatar.cc/100?img=11", isOnline: true },
];

function mockMessages(userId: string): Message[] {
  const msgs: Message[] = [];
  const templates = [
    "안녕하세요!", "오늘 회의 있나요?", "네 알겠습니다", "좋은 하루 되세요!",
    "파일 보내드렸습니다", "확인했습니다 감사합니다", "내일 미팅 가능할까요?",
    "링크 공유합니다", "수고하셨습니다", "점심 뭐 먹을까요?",
  ];
  for (let i = 0; i < 15; i++) {
    const isMine = i % 3 === 0;
    msgs.push({
      id: `${userId}-msg-${i}`,
      senderId: isMine ? "me" : userId,
      text: templates[i % templates.length],
      createdAt: new Date(Date.now() - (15 - i) * 300000).toISOString(),
      read: i < 12,
    });
  }
  // 이미지 메시지 추가
  msgs.push({
    id: `${userId}-img-1`,
    senderId: userId,
    imageUrl: `https://picsum.photos/300/200?random=${userId}`,
    createdAt: new Date(Date.now() - 60000).toISOString(),
    read: false,
  });
  return msgs;
}

const CONVERSATIONS: Conversation[] = USERS.map((user) => {
  const messages = mockMessages(user.id);
  const last = messages[messages.length - 1];
  return {
    id: `conv-${user.id}`,
    participant: user,
    messages,
    lastMessage: last.text || "사진을 보냈습니다",
    lastMessageAt: last.createdAt,
    unreadCount: messages.filter((m) => !m.read && m.senderId !== "me").length,
  };
});

interface ChatState {
  me: User;
  conversations: Conversation[];
  typingUsers: Record<string, boolean>;
  sendMessage: (convId: string, text?: string, imageUrl?: string) => void;
  markAsRead: (convId: string) => void;
  setTyping: (userId: string, typing: boolean) => void;
  simulateReply: (convId: string) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  me: ME,
  conversations: CONVERSATIONS,
  typingUsers: {},

  sendMessage: (convId, text, imageUrl) =>
    set((state) => ({
      conversations: state.conversations.map((conv) => {
        if (conv.id !== convId) return conv;
        const newMsg: Message = {
          id: `msg-${Date.now()}`,
          senderId: "me",
          text,
          imageUrl,
          createdAt: new Date().toISOString(),
          read: false,
        };
        return {
          ...conv,
          messages: [...conv.messages, newMsg],
          lastMessage: text || "사진을 보냈습니다",
          lastMessageAt: newMsg.createdAt,
        };
      }),
    })),

  markAsRead: (convId) =>
    set((state) => ({
      conversations: state.conversations.map((conv) =>
        conv.id === convId
          ? {
              ...conv,
              unreadCount: 0,
              messages: conv.messages.map((m) => ({ ...m, read: true })),
            }
          : conv
      ),
    })),

  setTyping: (userId, typing) =>
    set((state) => ({
      typingUsers: { ...state.typingUsers, [userId]: typing },
    })),

  simulateReply: (convId) => {
    const conv = get().conversations.find((c) => c.id === convId);
    if (!conv) return;

    // 타이핑 표시
    get().setTyping(conv.participant.id, true);

    setTimeout(() => {
      get().setTyping(conv.participant.id, false);
      const replies = ["네 확인했습니다!", "감사합니다 😊", "조금 뒤에 확인할게요", "좋습니다 👍", "알겠습니다~"];
      const reply = replies[Math.floor(Math.random() * replies.length)];
      set((state) => ({
        conversations: state.conversations.map((c) => {
          if (c.id !== convId) return c;
          const newMsg: Message = {
            id: `reply-${Date.now()}`,
            senderId: c.participant.id,
            text: reply,
            createdAt: new Date().toISOString(),
            read: false,
          };
          return {
            ...c,
            messages: [...c.messages, newMsg],
            lastMessage: reply,
            lastMessageAt: newMsg.createdAt,
            unreadCount: c.unreadCount + 1,
          };
        }),
      }));
    }, 2000 + Math.random() * 1000);
  },
}));
```

## src/components/ConversationItem.tsx

```typescript
import React from "react";
import { View, Text, Image, StyleSheet, Pressable } from "react-native";
import type { Conversation } from "../types";

interface Props {
  conversation: Conversation;
  onPress: () => void;
}

export default function ConversationItem({ conversation, onPress }: Props) {
  const { participant, lastMessage, lastMessageAt, unreadCount } = conversation;

  const timeLabel = () => {
    const diff = Date.now() - new Date(lastMessageAt).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "방금";
    if (mins < 60) return `${mins}분 전`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}시간 전`;
    return `${Math.floor(hours / 24)}일 전`;
  };

  return (
    <Pressable style={styles.container} onPress={onPress}>
      <View style={styles.avatarWrap}>
        <Image source={{ uri: participant.avatarUrl }} style={styles.avatar} />
        {participant.isOnline && <View style={styles.online} />}
      </View>
      <View style={styles.body}>
        <View style={styles.row}>
          <Text style={styles.name}>{participant.name}</Text>
          <Text style={styles.time}>{timeLabel()}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.lastMsg} numberOfLines={1}>{lastMessage}</Text>
          {unreadCount > 0 && (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{unreadCount}</Text>
            </View>
          )}
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flexDirection: "row", padding: 14, backgroundColor: "#fff", borderBottomWidth: 0.5, borderBottomColor: "#eee" },
  avatarWrap: { position: "relative", marginRight: 12 },
  avatar: { width: 52, height: 52, borderRadius: 26 },
  online: { position: "absolute", bottom: 2, right: 2, width: 12, height: 12, borderRadius: 6, backgroundColor: "#4caf50", borderWidth: 2, borderColor: "#fff" },
  body: { flex: 1, justifyContent: "center" },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  name: { fontSize: 16, fontWeight: "600" },
  time: { fontSize: 12, color: "#999" },
  lastMsg: { fontSize: 14, color: "#888", flex: 1, marginTop: 2, marginRight: 8 },
  badge: { backgroundColor: "#e74c3c", borderRadius: 10, minWidth: 20, height: 20, justifyContent: "center", alignItems: "center", paddingHorizontal: 6 },
  badgeText: { color: "#fff", fontSize: 11, fontWeight: "700" },
});
```

## src/components/MessageBubble.tsx

```typescript
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import ImageMessage from "./ImageMessage";
import type { Message } from "../types";

interface Props {
  message: Message;
  isMine: boolean;
}

export default function MessageBubble({ message, isMine }: Props) {
  const time = new Date(message.createdAt).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });

  if (message.imageUrl) {
    return (
      <View style={[styles.row, isMine && styles.rowMine]}>
        {isMine && <Text style={styles.time}>{time}</Text>}
        <ImageMessage uri={message.imageUrl} isMine={isMine} />
        {!isMine && <Text style={styles.time}>{time}</Text>}
      </View>
    );
  }

  return (
    <View style={[styles.row, isMine && styles.rowMine]}>
      {isMine && <Text style={styles.time}>{time}</Text>}
      <View style={[styles.bubble, isMine ? styles.mine : styles.other]}>
        <Text style={[styles.text, isMine ? styles.textMine : styles.textOther]}>
          {message.text}
        </Text>
      </View>
      {!isMine && <Text style={styles.time}>{time}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "flex-end", marginBottom: 6, paddingHorizontal: 12 },
  rowMine: { justifyContent: "flex-end" },
  bubble: { maxWidth: "75%", paddingVertical: 10, paddingHorizontal: 14, borderRadius: 18 },
  mine: { backgroundColor: "#3498db", borderBottomRightRadius: 4 },
  other: { backgroundColor: "#f0f0f0", borderBottomLeftRadius: 4 },
  text: { fontSize: 15, lineHeight: 20 },
  textMine: { color: "#fff" },
  textOther: { color: "#333" },
  time: { fontSize: 10, color: "#bbb", marginHorizontal: 6, marginBottom: 2 },
});
```

## src/components/ImageMessage.tsx

```typescript
import React from "react";
import { Image, StyleSheet, Pressable, Alert } from "react-native";

interface Props {
  uri: string;
  isMine: boolean;
}

export default function ImageMessage({ uri, isMine }: Props) {
  return (
    <Pressable onPress={() => Alert.alert("이미지 보기", "전체 화면 보기 (미구현)")}>
      <Image
        source={{ uri }}
        style={[styles.image, isMine ? styles.mine : styles.other]}
        resizeMode="cover"
      />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  image: { width: 200, height: 150, borderRadius: 12 },
  mine: { borderBottomRightRadius: 4 },
  other: { borderBottomLeftRadius: 4 },
});
```

## src/components/TypingIndicator.tsx

```typescript
import React, { useEffect } from "react";
import { View, StyleSheet } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withDelay,
  withTiming,
} from "react-native-reanimated";

export default function TypingIndicator() {
  const dots = [useSharedValue(0), useSharedValue(0), useSharedValue(0)];

  useEffect(() => {
    dots.forEach((dot, i) => {
      dot.value = withRepeat(
        withDelay(i * 200, withTiming(1, { duration: 400 })),
        -1,
        true
      );
    });
  }, []);

  return (
    <View style={styles.container}>
      <View style={styles.bubble}>
        {dots.map((dot, i) => {
          const style = useAnimatedStyle(() => ({
            opacity: 0.3 + dot.value * 0.7,
            transform: [{ translateY: -dot.value * 4 }],
          }));
          return <Animated.View key={i} style={[styles.dot, style]} />;
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { paddingHorizontal: 12, marginBottom: 6 },
  bubble: { flexDirection: "row", backgroundColor: "#f0f0f0", borderRadius: 18, borderBottomLeftRadius: 4, paddingVertical: 12, paddingHorizontal: 16, alignSelf: "flex-start", gap: 4 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#999" },
});
```

## src/components/ChatInput.tsx

```typescript
import React, { useState } from "react";
import { View, TextInput, Pressable, Text, StyleSheet } from "react-native";
import * as ImagePicker from "expo-image-picker";

interface Props {
  onSend: (text: string) => void;
  onSendImage: (uri: string) => void;
}

export default function ChatInput({ onSend, onSendImage }: Props) {
  const [text, setText] = useState("");

  const handleSend = () => {
    if (!text.trim()) return;
    onSend(text.trim());
    setText("");
  };

  const handleImagePick = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.7,
    });
    if (!result.canceled && result.assets[0]) {
      onSendImage(result.assets[0].uri);
    }
  };

  return (
    <View style={styles.container}>
      <Pressable onPress={handleImagePick} style={styles.imageBtn}>
        <Text style={styles.imageIcon}>📷</Text>
      </Pressable>
      <TextInput
        style={styles.input}
        placeholder="메시지를 입력하세요"
        value={text}
        onChangeText={setText}
        onSubmitEditing={handleSend}
        returnKeyType="send"
        multiline
        maxLength={1000}
      />
      <Pressable
        onPress={handleSend}
        style={[styles.sendBtn, text.trim().length > 0 && styles.sendActive]}
        disabled={text.trim().length === 0}
      >
        <Text style={[styles.sendText, text.trim().length > 0 && styles.sendTextActive]}>전송</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flexDirection: "row", alignItems: "flex-end", padding: 8, backgroundColor: "#fff", borderTopWidth: 0.5, borderTopColor: "#ddd" },
  imageBtn: { padding: 8 },
  imageIcon: { fontSize: 24 },
  input: { flex: 1, backgroundColor: "#f5f5f5", borderRadius: 20, paddingHorizontal: 16, paddingVertical: 8, fontSize: 15, maxHeight: 100, marginHorizontal: 8 },
  sendBtn: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 18 },
  sendActive: { backgroundColor: "#3498db" },
  sendText: { fontSize: 15, fontWeight: "600", color: "#ccc" },
  sendTextActive: { color: "#fff" },
});
```

## src/screens/ConversationListScreen.tsx

```typescript
import React from "react";
import { FlatList, SafeAreaView, StyleSheet, Text } from "react-native";
import ConversationItem from "../components/ConversationItem";
import { useChatStore } from "../store/useChatStore";
import { useNavigation } from "@react-navigation/native";

export default function ConversationListScreen() {
  const conversations = useChatStore((s) => s.conversations);
  const navigation = useNavigation<any>();

  const sorted = [...conversations].sort(
    (a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime()
  );

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.header}>채팅</Text>
      <FlatList
        data={sorted}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <ConversationItem
            conversation={item}
            onPress={() => navigation.navigate("ChatRoom", { conversationId: item.id })}
          />
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  header: { fontSize: 28, fontWeight: "800", padding: 16, paddingBottom: 8 },
});
```

## src/screens/ChatRoomScreen.tsx

```typescript
import React, { useRef, useEffect } from "react";
import { FlatList, SafeAreaView, StyleSheet, KeyboardAvoidingView, Platform } from "react-native";
import MessageBubble from "../components/MessageBubble";
import ChatInput from "../components/ChatInput";
import TypingIndicator from "../components/TypingIndicator";
import { useChatStore } from "../store/useChatStore";
import { useRoute } from "@react-navigation/native";

export default function ChatRoomScreen() {
  const route = useRoute<any>();
  const { conversationId } = route.params;
  const { conversations, sendMessage, markAsRead, typingUsers, simulateReply } = useChatStore();
  const conv = conversations.find((c) => c.id === conversationId);
  const flatListRef = useRef<FlatList>(null);
  const isTyping = conv ? typingUsers[conv.participant.id] : false;

  useEffect(() => {
    if (conv) markAsRead(conv.id);
  }, [conv?.messages.length]);

  // 자동 스크롤
  useEffect(() => {
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
  }, [conv?.messages.length, isTyping]);

  if (!conv) return null;

  const handleSend = (text: string) => {
    sendMessage(conv.id, text);
    simulateReply(conv.id);
  };

  const handleSendImage = (uri: string) => {
    sendMessage(conv.id, undefined, uri);
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={90}
      >
        <FlatList
          ref={flatListRef}
          data={conv.messages}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <MessageBubble message={item} isMine={item.senderId === "me"} />
          )}
          contentContainerStyle={styles.messages}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: false })}
          ListFooterComponent={isTyping ? <TypingIndicator /> : null}
        />
        <ChatInput onSend={handleSend} onSendImage={handleSendImage} />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  flex: { flex: 1 },
  messages: { paddingVertical: 12 },
});
```

## App.tsx

```typescript
import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import ConversationListScreen from "./src/screens/ConversationListScreen";
import ChatRoomScreen from "./src/screens/ChatRoomScreen";
import { useChatStore } from "./src/store/useChatStore";

const Stack = createNativeStackNavigator();

function ChatRoomHeader() {
  // 네비게이션 헤더에서 참가자 이름 표시
  return null;
}

export default function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen
          name="Conversations"
          component={ConversationListScreen}
          options={{ headerShown: false }}
        />
        <Stack.Screen
          name="ChatRoom"
          component={ChatRoomScreen}
          options={({ route }: any) => {
            const conversations = useChatStore.getState().conversations;
            const conv = conversations.find((c) => c.id === route.params.conversationId);
            return { title: conv?.participant.name || "채팅" };
          }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
```

메시지 전송 후 2~3초 뒤 자동 답장이 옵니다. 타이핑 인디케이터가 표시되고, 이미지도 전송 가능합니다.'''),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mega_extra_3.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"추가 데이터 3: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
