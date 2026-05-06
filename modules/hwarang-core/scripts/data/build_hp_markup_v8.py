"""화랑 LoRA v8 — Hwarang Protocol (HP) Markup 학습 데이터 (1500 샘플).

목표: 화랑이 v8 학습 후 자연스럽게 HP Markup (@@plan / @@tool / @@diff /
@@suggestion / @@warning / @@summary) 을 출력하도록 SFT.

시나리오:
- HP-1: Plan + Tool + Diff + Summary 풀 사이클        (500)
- HP-2: Plan 만 — 사용자 승인 대기                     (300)
- HP-3: Diff + Suggestion + Warning                    (400)
- HP-4: 단순 질문 — Markup 없이 plain                  (300)  ← markup 남용 방지

스펙: docs/hp-protocol.md  "3. Output Markup 형식" 섹션.
"""

import argparse
import json
import os
import random

from build_tools_multiturn import (
    TOOLS_DESC,
    assistant,
    m,
    tc,
    tool,
    user,
)
from build_tools_multiturn import sys as _sys  # noqa: F401


# ---------------------------------------------------------------------------
# system prompt — HP markup 안내 포함
# ---------------------------------------------------------------------------

def syss():
    """HP markup 가이드가 포함된 system prompt."""
    return {
        "role": "system",
        "content": (
            "당신은 화랑(Hwarang) AI 입니다. 퍼시스모어가 만든 한국형 코딩 어시스턴트입니다.\n"
            "\n"
            "[출력 형식 — HP Markup]\n"
            "복잡한 작업 응답에는 다음 마크업을 사용하세요:\n"
            "- @@plan ... @@end : 작업 단계 (1. 제목 [status])\n"
            "- @@tool: name ... @@end : 도구 호출 (JSON args)\n"
            "- @@diff <path> ... @@end : 파일 변경 미리보기\n"
            "- @@suggestion: <level> ... @@end : 제안 (info/medium-risk/high-risk)\n"
            "- @@warning ... @@end : 경고\n"
            "- @@summary ... @@end : 최종 요약\n"
            "\n"
            "@@end 로 각 섹션 종료. plain text 도 같이 사용 가능.\n"
            "단순 질의응답은 마크업 없이 자연스럽게 답하세요."
        ),
    }


random.seed(2070)


# ---------------------------------------------------------------------------
# HP-1: Plan + Tool + Diff + Summary 풀 사이클 (500)
# ---------------------------------------------------------------------------

TASK_PATTERNS = [
    {
        "task": "package.json 의 react 18.3 으로 업그레이드",
        "plan": [
            "package.json 읽기",
            "react 의존성 18.3 으로 변경",
            "npm install 실행",
            "빌드 검증",
        ],
        "files": ["package.json"],
        "tools": ["read_file", "edit_file", "run_command"],
        "diff": '-  "react": "18.0.0",\n+  "react": "18.3.0",',
    },
    {
        "task": "Stripe SDK 설치 + 결제 API 라우터 추가",
        "plan": [
            "package.json 확인",
            "stripe 설치",
            "src/api/checkout.ts 생성",
            "webhook handler 작성",
            "통합 테스트",
        ],
        "files": ["package.json", "src/api/checkout.ts"],
        "tools": ["read_file", "run_command", "write_file"],
        "diff": '+ import Stripe from "stripe";\n+ export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);',
    },
    {
        "task": "Prisma User 모델에 emailVerified 필드 추가",
        "plan": [
            "schema.prisma 읽기",
            "User 모델에 emailVerified DateTime? 추가",
            "migration 생성",
            "DB 반영",
        ],
        "files": ["prisma/schema.prisma"],
        "tools": ["read_file", "edit_file", "run_command"],
        "diff": "  email String @unique\n+ emailVerified DateTime?\n  password String",
    },
    {
        "task": ".env.example 에 SENTRY_DSN 추가하고 설정 코드 연결",
        "plan": [
            ".env.example 읽기",
            "SENTRY_DSN 변수 추가",
            "src/lib/sentry.ts 생성",
            "main.ts 에서 init 호출",
        ],
        "files": [".env.example", "src/lib/sentry.ts"],
        "tools": ["read_file", "edit_file", "write_file"],
        "diff": "+ SENTRY_DSN=\n+ SENTRY_ENV=development",
    },
    {
        "task": "tailwind.config.js 에 brand color palette 추가",
        "plan": [
            "tailwind.config.js 읽기",
            "theme.extend.colors.brand 추가",
            "기존 클래스에 brand 적용",
        ],
        "files": ["tailwind.config.js"],
        "tools": ["read_file", "edit_file"],
        "diff": "  theme: {\n+   extend: { colors: { brand: { 500: '#0ea5e9' } } }\n  }",
    },
    {
        "task": "FastAPI auth router 에 JWT refresh 엔드포인트 추가",
        "plan": [
            "app/routers/auth.py 읽기",
            "/refresh 엔드포인트 추가",
            "RefreshToken 모델 마이그레이션",
            "pytest 실행",
        ],
        "files": ["app/routers/auth.py"],
        "tools": ["read_file", "edit_file", "run_command"],
        "diff": "+ @router.post('/refresh')\n+ async def refresh_token(token: str): ...",
    },
    {
        "task": "Next.js 미들웨어로 i18n 라우팅 추가",
        "plan": [
            "middleware.ts 생성",
            "locale 감지 + redirect",
            "next.config 업데이트",
        ],
        "files": ["middleware.ts", "next.config.js"],
        "tools": ["write_file", "edit_file"],
        "diff": "+ export function middleware(req: NextRequest) { ... }",
    },
    {
        "task": "GitHub Actions CI 추가 (lint/test/build)",
        "plan": [
            "package.json scripts 확인",
            ".github/workflows/ci.yml 생성",
            "Node 20 + pnpm 설정",
            "PR 트리거 검증",
        ],
        "files": [".github/workflows/ci.yml"],
        "tools": ["read_file", "write_file"],
        "diff": "+ name: CI\n+ on: [push, pull_request]\n+ jobs:\n+   build:\n+     runs-on: ubuntu-latest",
    },
    {
        "task": "Dockerfile multi-stage 빌드로 최적화",
        "plan": [
            "기존 Dockerfile 분석",
            "builder stage 분리",
            "runtime stage 슬림 이미지",
            "이미지 크기 비교",
        ],
        "files": ["Dockerfile"],
        "tools": ["read_file", "write_file", "run_command"],
        "diff": "+ FROM node:20-alpine AS builder\n  ...\n+ FROM node:20-alpine AS runtime",
    },
    {
        "task": "ESLint 9 flat config 마이그레이션",
        "plan": [
            ".eslintrc.json 읽기",
            "eslint.config.js 생성",
            "package.json devDeps 업데이트",
            "lint 통과 확인",
        ],
        "files": [".eslintrc.json", "eslint.config.js"],
        "tools": ["read_file", "write_file", "run_command"],
        "diff": "+ export default [\n+   { rules: { 'no-unused-vars': 'warn' } }\n+ ]",
    },
    {
        "task": "PostgreSQL 인덱스 추가 — orders.user_id",
        "plan": [
            "prisma/schema.prisma 읽기",
            "@@index([userId]) 추가",
            "migration 생성",
            "EXPLAIN 으로 검증",
        ],
        "files": ["prisma/schema.prisma"],
        "tools": ["read_file", "edit_file", "run_command"],
        "diff": "  model Order {\n    ...\n+   @@index([userId])\n  }",
    },
    {
        "task": "Vite → Vitest 단위 테스트 셋업",
        "plan": [
            "vite.config.ts 읽기",
            "vitest 설치",
            "test 디렉토리 + 샘플 테스트",
            "package.json scripts.test 추가",
        ],
        "files": ["vite.config.ts", "src/__tests__/sample.test.ts"],
        "tools": ["read_file", "run_command", "write_file"],
        "diff": "+ test: { environment: 'jsdom', globals: true }",
    },
    {
        "task": "React Query 도입 — 사용자 목록 페치",
        "plan": [
            "@tanstack/react-query 설치",
            "QueryClientProvider 설정",
            "useUsers 훅 생성",
            "기존 useEffect fetch 제거",
        ],
        "files": ["src/main.tsx", "src/hooks/useUsers.ts"],
        "tools": ["run_command", "edit_file", "write_file"],
        "diff": "+ export const useUsers = () => useQuery({ queryKey: ['users'], queryFn: fetchUsers })",
    },
    {
        "task": "shadcn/ui Button 컴포넌트 추가",
        "plan": [
            "shadcn CLI 실행",
            "components/ui/button.tsx 확인",
            "App.tsx 에서 import",
        ],
        "files": ["components/ui/button.tsx"],
        "tools": ["run_command", "read_file", "edit_file"],
        "diff": "+ export { Button } from '@/components/ui/button'",
    },
    {
        "task": "logger 라이브러리 winston 으로 통합",
        "plan": [
            "winston 설치",
            "src/lib/logger.ts 생성",
            "console.log 들 logger.info 로 치환",
            "로그 파일 회전 설정",
        ],
        "files": ["src/lib/logger.ts"],
        "tools": ["run_command", "write_file", "edit_file"],
        "diff": "+ import winston from 'winston';\n+ export const logger = winston.createLogger({...});",
    },
    {
        "task": "Sentry error tracking 도입",
        "plan": [
            "@sentry/node 설치",
            "init 코드 main.ts 추가",
            "Express errorHandler 등록",
            "테스트 에러 발사",
        ],
        "files": ["src/main.ts"],
        "tools": ["run_command", "edit_file"],
        "diff": "+ Sentry.init({ dsn: process.env.SENTRY_DSN })",
    },
    {
        "task": "Redis 캐시 도입 — 사용자 프로필",
        "plan": [
            "ioredis 설치",
            "src/lib/redis.ts 생성",
            "getUser 함수에 캐시 래핑",
            "TTL 5분 설정",
        ],
        "files": ["src/lib/redis.ts", "src/services/user.ts"],
        "tools": ["run_command", "write_file", "edit_file"],
        "diff": "+ const cached = await redis.get(`user:${id}`);\n+ if (cached) return JSON.parse(cached);",
    },
    {
        "task": "Zod 스키마 도입 + API 입력 검증",
        "plan": [
            "zod 설치",
            "src/schemas/user.ts 생성",
            "라우터에서 parse 호출",
            "에러 핸들링 통합",
        ],
        "files": ["src/schemas/user.ts"],
        "tools": ["run_command", "write_file", "edit_file"],
        "diff": "+ export const UserSchema = z.object({ email: z.string().email(), name: z.string().min(1) });",
    },
    {
        "task": "Husky + lint-staged 커밋 훅 셋업",
        "plan": [
            "husky/lint-staged 설치",
            "package.json prepare 스크립트",
            ".husky/pre-commit 생성",
            "샘플 커밋으로 동작 검증",
        ],
        "files": ["package.json", ".husky/pre-commit"],
        "tools": ["run_command", "edit_file", "write_file"],
        "diff": "+ \"lint-staged\": { \"*.{ts,tsx}\": [\"eslint --fix\", \"prettier --write\"] }",
    },
    {
        "task": "Storybook 8 설치 + Button 스토리",
        "plan": [
            "npx storybook init",
            ".storybook/main.ts 확인",
            "Button.stories.tsx 작성",
            "storybook dev 실행",
        ],
        "files": ["src/components/Button.stories.tsx"],
        "tools": ["run_command", "write_file"],
        "diff": "+ export default { component: Button } satisfies Meta<typeof Button>;",
    },
    {
        "task": "tRPC 라우터 추가 — userRouter",
        "plan": [
            "@trpc/server 설치",
            "src/server/trpc.ts 초기화",
            "userRouter 작성",
            "appRouter 에 mount",
        ],
        "files": ["src/server/trpc.ts", "src/server/routers/user.ts"],
        "tools": ["run_command", "write_file", "edit_file"],
        "diff": "+ export const userRouter = t.router({ list: t.procedure.query(...) });",
    },
    {
        "task": "Tauri 앱 자동 업데이트 설정",
        "plan": [
            "tauri.conf.json 읽기",
            "updater 섹션 추가",
            "공개키 등록",
            "release workflow 업데이트",
        ],
        "files": ["src-tauri/tauri.conf.json"],
        "tools": ["read_file", "edit_file"],
        "diff": "+ \"updater\": { \"active\": true, \"endpoints\": [\"https://updater.hwarang.ai\"] }",
    },
    {
        "task": "Flutter 앱 firebase_auth 통합",
        "plan": [
            "pubspec.yaml 의존성 추가",
            "google-services.json 배치",
            "AuthService 클래스",
            "로그인 화면 연결",
        ],
        "files": ["pubspec.yaml", "lib/services/auth_service.dart"],
        "tools": ["edit_file", "write_file"],
        "diff": "+ firebase_auth: ^5.3.0\n+ firebase_core: ^3.6.0",
    },
    {
        "task": "Spring Boot Actuator health 엔드포인트 활성화",
        "plan": [
            "build.gradle 의존성 확인",
            "application.yml 노출 설정",
            "/actuator/health 검증",
        ],
        "files": ["src/main/resources/application.yml"],
        "tools": ["read_file", "edit_file", "run_command"],
        "diff": "+ management:\n+   endpoints:\n+     web:\n+       exposure:\n+         include: health,info,metrics",
    },
    {
        "task": "Rust axum API 에 CORS 미들웨어 추가",
        "plan": [
            "Cargo.toml 의존성",
            "tower-http CorsLayer 등록",
            "main.rs 라우터 wrap",
        ],
        "files": ["src/main.rs", "Cargo.toml"],
        "tools": ["read_file", "edit_file"],
        "diff": "+ .layer(CorsLayer::permissive())",
    },
    {
        "task": "Go gin 서버에 graceful shutdown",
        "plan": [
            "main.go 읽기",
            "signal.Notify + http.Server 분리",
            "context timeout 5초",
        ],
        "files": ["main.go"],
        "tools": ["read_file", "edit_file"],
        "diff": "+ ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)\n+ srv.Shutdown(ctx)",
    },
    {
        "task": "Django REST framework throttle 설정",
        "plan": [
            "settings.py 읽기",
            "DEFAULT_THROTTLE_CLASSES 추가",
            "분당 60회 제한",
        ],
        "files": ["config/settings.py"],
        "tools": ["read_file", "edit_file"],
        "diff": "+ 'DEFAULT_THROTTLE_RATES': { 'user': '60/min' }",
    },
    {
        "task": "GraphQL Apollo 서버 + 첫 resolver",
        "plan": [
            "apollo-server 설치",
            "schema.graphql 작성",
            "resolver 매핑",
            "/graphql 검증",
        ],
        "files": ["src/graphql/schema.graphql", "src/graphql/resolvers.ts"],
        "tools": ["run_command", "write_file"],
        "diff": "+ type Query { hello: String }\n+ const resolvers = { Query: { hello: () => 'world' } };",
    },
    {
        "task": "Kubernetes deployment HPA 추가",
        "plan": [
            "deployment.yaml 확인",
            "hpa.yaml 작성 — CPU 70%",
            "kubectl apply",
            "metrics 확인",
        ],
        "files": ["k8s/hpa.yaml"],
        "tools": ["read_file", "write_file", "run_command"],
        "diff": "+ kind: HorizontalPodAutoscaler\n+ spec:\n+   minReplicas: 2\n+   maxReplicas: 10",
    },
    {
        "task": "Helm chart values 환경별 분리 (dev/prod)",
        "plan": [
            "values.yaml 읽기",
            "values-dev.yaml + values-prod.yaml",
            "image.tag 분기",
        ],
        "files": ["chart/values-dev.yaml", "chart/values-prod.yaml"],
        "tools": ["read_file", "write_file"],
        "diff": "+ image:\n+   tag: \"prod-v1.2.0\"",
    },
    {
        "task": "OpenAPI 3 스펙 생성 + Swagger UI",
        "plan": [
            "swagger-jsdoc 설치",
            "JSDoc 주석으로 라우트 표기",
            "/docs 라우트 마운트",
        ],
        "files": ["src/docs/swagger.ts"],
        "tools": ["run_command", "write_file"],
        "diff": "+ const spec = swaggerJSDoc({ definition: openApiDef, apis: ['./src/routes/*.ts'] });",
    },
    {
        "task": "Playwright E2E 셋업 + 로그인 시나리오",
        "plan": [
            "playwright 설치",
            "playwright.config.ts 생성",
            "tests/login.spec.ts 작성",
            "CI 통합",
        ],
        "files": ["tests/login.spec.ts"],
        "tools": ["run_command", "write_file"],
        "diff": "+ test('login flow', async ({ page }) => { await page.goto('/login'); ... });",
    },
    {
        "task": "PWA manifest + service worker 추가",
        "plan": [
            "vite-plugin-pwa 설치",
            "manifest 정의",
            "오프라인 fallback",
            "Lighthouse 점수 확인",
        ],
        "files": ["vite.config.ts"],
        "tools": ["run_command", "edit_file"],
        "diff": "+ VitePWA({ registerType: 'autoUpdate', manifest: {...} })",
    },
    {
        "task": "i18next 다국어 셋업 (ko/en)",
        "plan": [
            "react-i18next 설치",
            "locales/ko.json + locales/en.json",
            "i18n.ts 초기화",
            "App 에서 useTranslation",
        ],
        "files": ["src/i18n.ts", "src/locales/ko.json"],
        "tools": ["run_command", "write_file"],
        "diff": "+ i18n.use(initReactI18next).init({ resources, lng: 'ko' });",
    },
    {
        "task": "Stripe webhook signature 검증",
        "plan": [
            "checkout.ts 읽기",
            "raw body parser 분리",
            "stripe.webhooks.constructEvent",
            "테스트 이벤트 발사",
        ],
        "files": ["src/api/webhook.ts"],
        "tools": ["read_file", "edit_file"],
        "diff": "+ const event = stripe.webhooks.constructEvent(rawBody, sig, endpointSecret);",
    },
    {
        "task": "AWS S3 presigned URL 업로드 엔드포인트",
        "plan": [
            "@aws-sdk/client-s3 설치",
            "/api/upload-url 라우트",
            "PutObjectCommand presign",
        ],
        "files": ["src/api/upload-url.ts"],
        "tools": ["run_command", "write_file"],
        "diff": "+ const url = await getSignedUrl(s3, new PutObjectCommand({ Bucket, Key }), { expiresIn: 60 });",
    },
    {
        "task": "Cloudflare Workers KV 통합",
        "plan": [
            "wrangler.toml KV 바인딩",
            "fetch handler 에서 KV.get",
            "deploy 검증",
        ],
        "files": ["wrangler.toml", "src/index.ts"],
        "tools": ["read_file", "edit_file"],
        "diff": "+ kv_namespaces = [\n+   { binding = \"CACHE\", id = \"...\" }\n+ ]",
    },
    {
        "task": "GitHub OAuth 로그인 (NextAuth)",
        "plan": [
            "next-auth 설치",
            "[...nextauth].ts 생성",
            "GITHUB_ID/SECRET .env",
            "Sign-in 버튼",
        ],
        "files": ["pages/api/auth/[...nextauth].ts"],
        "tools": ["run_command", "write_file"],
        "diff": "+ providers: [GitHubProvider({ clientId: env.GITHUB_ID, clientSecret: env.GITHUB_SECRET })]",
    },
    {
        "task": "Socket.IO 채팅 룸 추가",
        "plan": [
            "socket.io 설치",
            "src/server/socket.ts 작성",
            "room join/leave 이벤트",
            "클라이언트 훅 연결",
        ],
        "files": ["src/server/socket.ts"],
        "tools": ["run_command", "write_file"],
        "diff": "+ io.on('connection', s => s.on('join', room => s.join(room)));",
    },
    {
        "task": "Bun runtime 으로 마이그레이션",
        "plan": [
            "package.json scripts 분석",
            "bun install",
            "node 의존 API 점검",
            "bun run dev 검증",
        ],
        "files": ["package.json"],
        "tools": ["read_file", "run_command", "edit_file"],
        "diff": "+   \"dev\": \"bun --hot src/server.ts\"",
    },
    {
        "task": "Drizzle ORM 도입 + users 테이블",
        "plan": [
            "drizzle-orm 설치",
            "schema.ts 작성",
            "migrate 스크립트",
            "select 쿼리 검증",
        ],
        "files": ["src/db/schema.ts"],
        "tools": ["run_command", "write_file"],
        "diff": "+ export const users = pgTable('users', { id: serial('id').primaryKey(), email: text('email').notNull().unique() });",
    },
    {
        "task": "MongoDB Mongoose 인덱스 + TTL",
        "plan": [
            "User 스키마 읽기",
            "createdAt index + sessions TTL",
            "save() 검증",
        ],
        "files": ["src/models/User.ts"],
        "tools": ["read_file", "edit_file"],
        "diff": "+ schema.index({ createdAt: 1 }, { expireAfterSeconds: 3600 });",
    },
    {
        "task": "Vue 3 Pinia store 도입",
        "plan": [
            "pinia 설치",
            "src/stores/user.ts 생성",
            "main.ts createPinia",
            "컴포넌트에서 사용",
        ],
        "files": ["src/stores/user.ts"],
        "tools": ["run_command", "write_file", "edit_file"],
        "diff": "+ export const useUserStore = defineStore('user', () => { ... });",
    },
    {
        "task": "Svelte 5 runes 마이그레이션",
        "plan": [
            "svelte.config.js compatibility 확인",
            "$state/$derived 치환",
            "stores 정리",
            "타입체크",
        ],
        "files": ["src/routes/+page.svelte"],
        "tools": ["read_file", "edit_file"],
        "diff": "- let count = 0\n+ let count = $state(0)",
    },
    {
        "task": "Astro content collections 추가",
        "plan": [
            "content/config.ts 작성",
            "Zod 스키마 정의",
            "글 쿼리 페이지",
        ],
        "files": ["src/content/config.ts"],
        "tools": ["write_file"],
        "diff": "+ const blog = defineCollection({ schema: z.object({ title: z.string(), date: z.date() }) });",
    },
    {
        "task": "Solid.js signal 기반 상태 추가",
        "plan": [
            "createSignal 사용",
            "createEffect 부수효과",
            "Show/For 컨트롤 플로우",
        ],
        "files": ["src/App.tsx"],
        "tools": ["read_file", "edit_file"],
        "diff": "+ const [count, setCount] = createSignal(0);",
    },
    {
        "task": "Remix loader/action 패턴 적용",
        "plan": [
            "routes 디렉토리 분석",
            "loader 함수 추가",
            "action 함수 추가",
            "useLoaderData 훅",
        ],
        "files": ["app/routes/posts.tsx"],
        "tools": ["read_file", "edit_file"],
        "diff": "+ export const loader = async () => json(await db.post.findMany());",
    },
    {
        "task": "Nuxt 3 server route 추가",
        "plan": [
            "server/api/users.get.ts 생성",
            "useFetch 훅 호출",
            "타입 추론 확인",
        ],
        "files": ["server/api/users.get.ts"],
        "tools": ["write_file"],
        "diff": "+ export default defineEventHandler(async () => await prisma.user.findMany());",
    },
    {
        "task": "Webpack 5 → Vite 마이그레이션",
        "plan": [
            "webpack.config.js 분석",
            "vite.config.ts 작성",
            "alias/proxy 이전",
            "build 결과 비교",
        ],
        "files": ["vite.config.ts"],
        "tools": ["read_file", "write_file", "run_command"],
        "diff": "+ export default defineConfig({ resolve: { alias: { '@': '/src' } } });",
    },
    {
        "task": "pytest fixtures 공통화 (conftest.py)",
        "plan": [
            "테스트 코드에서 setup 패턴 확인",
            "conftest.py 작성",
            "fixture 적용",
        ],
        "files": ["tests/conftest.py"],
        "tools": ["read_file", "write_file"],
        "diff": "+ @pytest.fixture\n+ def db(): ...",
    },
]


def _identity_intro(task):
    """30%+ 정체성 멘트 — 화랑/퍼시스모어"""
    if random.random() < 0.35:
        choices = [
            f"화랑 AI 입니다. {task} 작업 진행하겠습니다.",
            f"퍼시스모어 화랑이 {task} 작업을 도와드립니다.",
            f"{task} — 화랑이 단계별로 처리해드릴게요.",
        ]
        return random.choice(choices)
    return f"{task} 작업을 진행하겠습니다."


def _plan_block(steps, completed_until):
    """완료 인덱스 < idx 면 completed, == 이면 in_progress, > 면 pending"""
    lines = []
    for i, step in enumerate(steps):
        if i < completed_until:
            status = "completed"
        elif i == completed_until:
            status = "in_progress"
        else:
            status = "pending"
        lines.append(f"{i + 1}. {step}    [{status}]")
    return "@@plan\n" + "\n".join(lines) + "\n@@end"


def gen_full_cycle(p):
    intro = _identity_intro(p["task"])
    plan_v1 = _plan_block(p["plan"], 1)
    plan_v2 = _plan_block(p["plan"], 2)

    response_1 = (
        f"{intro}\n\n"
        f"{plan_v1}\n\n"
        f"먼저 현재 파일을 확인하겠습니다.\n\n"
        f"@@tool: {p['tools'][0]}\n"
        f'{json.dumps({"path": p["files"][0]}, ensure_ascii=False)}\n'
        f"@@end"
    )

    second_tool = p["tools"][1] if len(p["tools"]) > 1 else p["tools"][0]
    if second_tool == "edit_file":
        second_args = {
            "path": p["files"][0],
            "oldString": "old",
            "newString": "new",
        }
    elif second_tool == "write_file":
        second_args = {
            "path": p["files"][-1],
            "content": "// 새로 생성한 파일 본문",
        }
    elif second_tool == "run_command":
        second_args = {"command": "npm install"}
    else:
        second_args = {"path": p["files"][0]}

    response_2 = (
        f"분석 완료. 다음 단계를 진행합니다.\n\n"
        f"{plan_v2}\n\n"
        f"@@diff {p['files'][0]}\n{p['diff']}\n@@end\n\n"
        f"@@tool: {second_tool}\n"
        f"{json.dumps(second_args, ensure_ascii=False)}\n"
        f"@@end"
    )

    summary = (
        "@@summary\n"
        f"✓ {p['task']} 완료\n"
        f"- 변경 파일: {', '.join(p['files'])}\n"
        f"- 사용 도구: {', '.join(p['tools'])}\n"
        f"- 단계 {len(p['plan'])}개 모두 처리\n"
        "@@end"
    )

    return m([
        syss(),
        user(p["task"]),
        assistant(response_1),
        tool("// 현재 파일 본문 (생략)..."),
        assistant(response_2),
        tool("File modified successfully."),
        assistant(summary),
    ])


SCENARIO_HP1 = [gen_full_cycle(random.choice(TASK_PATTERNS)) for _ in range(500)]


# ---------------------------------------------------------------------------
# HP-2: Plan 만 — 사용자 승인 대기 (300)
# ---------------------------------------------------------------------------

BIG_TASK_PATTERNS = [
    {
        "task": "결제 시스템 추가 (Stripe + 주문/환불)",
        "plan": [
            "DB 스키마 (Order/Payment/Refund 모델)",
            "Stripe SDK 설치 + .env 키",
            "/api/checkout 라우터",
            "webhook handler — payment_intent.succeeded",
            "주문 내역 / 영수증 UI",
            "환불 워크플로우",
            "E2E 테스트",
        ],
    },
    {
        "task": "auth 시스템 NextAuth 로 마이그레이션",
        "plan": [
            "기존 인증 코드 분석",
            "NextAuth 설치 + Prisma adapter",
            "Provider 셋업 (Credentials + Google + GitHub)",
            "session 관리 + JWT 옵션",
            "기존 로그인/회원가입 라우트 마이그레이션",
            "테스트 + 미들웨어 보호",
        ],
    },
    {
        "task": "마이크로서비스 분리 (모놀리식 → 4개 서비스)",
        "plan": [
            "도메인 경계 식별 (auth/order/notification/admin)",
            "공통 모듈 패키지화",
            "서비스별 Dockerfile/Compose",
            "내부 통신 — gRPC 또는 NATS",
            "API Gateway 추가",
            "분산 트레이싱 (OpenTelemetry)",
            "단계적 트래픽 컷오버",
        ],
    },
    {
        "task": "PostgreSQL → 분산 (Citus) 마이그레이션",
        "plan": [
            "현재 쿼리 패턴 분석",
            "샤딩 키 결정 (tenant_id)",
            "Citus 클러스터 프로비저닝",
            "create_distributed_table 적용",
            "쿼리 호환성 검증",
            "데이터 이관 + 검증",
            "점진 트래픽 전환",
        ],
    },
    {
        "task": "다국어/i18n 전체 도입 (5개 언어)",
        "plan": [
            "react-i18next 셋업",
            "namespace 구조 설계",
            "ko/en/ja/zh/es locale 파일",
            "기존 하드코딩 문자열 추출 (3000+ 키)",
            "포맷터 (date/number/currency)",
            "RTL 대응 검토",
            "QA 검수",
        ],
    },
    {
        "task": "관리자 패널 (Hwarang Admin) 새 모듈",
        "plan": [
            "modules/hwarang-admin 생성 (Next.js)",
            "admin_token 인증",
            "사용자/지식/로그 관리 페이지",
            "RBAC 역할 분리",
            "감사 로그 (audit trail)",
            "차트/대시보드",
            "배포 파이프라인",
        ],
    },
    {
        "task": "OAuth 2.0 + OpenID Connect 자체 구현",
        "plan": [
            "node-oidc-provider 설치",
            "client 등록 / scope 정의",
            "consent 화면",
            "토큰 발급/갱신/폐기",
            "JWKs 엔드포인트",
            "Discovery .well-known 노출",
            "외부 클라이언트 통합 테스트",
        ],
    },
    {
        "task": "GraphQL Federation 도입",
        "plan": [
            "subgraph 분리 (User/Product/Order)",
            "Apollo Router 셋업",
            "엔티티/@key 어노테이션",
            "supergraph 빌드",
            "성능 측정 (N+1 → DataLoader)",
            "기존 REST 점진 디프리케이션",
        ],
    },
    {
        "task": "Kubernetes 프로덕션 이전",
        "plan": [
            "Helm chart 작성",
            "ConfigMap/Secret 분리",
            "Ingress + TLS (cert-manager)",
            "HPA + PodDisruptionBudget",
            "ArgoCD GitOps 셋업",
            "스테이징 환경 검증",
            "프로덕션 컷오버",
        ],
    },
    {
        "task": "옵저버빌리티 스택 (Loki + Tempo + Prometheus)",
        "plan": [
            "Grafana Cloud 또는 자체 호스팅 결정",
            "OpenTelemetry SDK 통합",
            "trace/log/metric 자동 계측",
            "대시보드 작성",
            "alerting 룰",
            "SLO 정의",
        ],
    },
    {
        "task": "보안 감사 + 취약점 패치",
        "plan": [
            "Dependabot/Snyk 스캔 결과 수집",
            "CVE 우선순위 분류",
            "패치 + 회귀 테스트",
            "보안 헤더 (CSP/HSTS)",
            "rate limiting 강화",
            "감사 보고서 작성",
        ],
    },
    {
        "task": "모바일 앱 (Flutter) 프로젝트 신규",
        "plan": [
            "flutter create + 패키지 ID",
            "라우팅 (go_router)",
            "상태관리 (riverpod)",
            "REST/GraphQL 클라이언트",
            "iOS/Android 빌드 설정",
            "TestFlight/Play 베타",
        ],
    },
    {
        "task": "데이터 파이프라인 (Airflow + dbt)",
        "plan": [
            "Airflow 클러스터 프로비저닝",
            "DAG 디렉토리 구조",
            "dbt 모델 (staging/marts)",
            "원천 → DW 적재 작업",
            "데이터 품질 테스트",
            "스케줄/SLA 설정",
        ],
    },
    {
        "task": "AI 추천 시스템 도입",
        "plan": [
            "사용자 행동 로그 수집",
            "임베딩 모델 선정",
            "Vector DB (pgvector / Qdrant)",
            "ANN 검색 API",
            "A/B 테스트 인프라",
            "지표 대시보드",
        ],
    },
    {
        "task": "B2B SSO (SAML + SCIM) 지원",
        "plan": [
            "passport-saml 설치",
            "IdP 메타데이터 임포트",
            "Just-in-Time 프로비저닝",
            "SCIM 2.0 엔드포인트",
            "Okta/Azure AD 통합 검증",
            "운영 문서",
        ],
    },
    {
        "task": "결제 환불 자동화 + 회계 연동",
        "plan": [
            "환불 정책 룰 엔진",
            "Stripe 환불 API 연동",
            "회계 시스템 (Xero/QuickBooks) 동기화",
            "월말 정산 리포트",
            "감사 로그",
        ],
    },
    {
        "task": "실시간 협업 기능 (CRDT 기반)",
        "plan": [
            "Yjs / Automerge 비교",
            "WebSocket 백엔드",
            "presence indicator",
            "offline-first 동기화",
            "충돌 시각화",
        ],
    },
    {
        "task": "사내 design system 패키지화",
        "plan": [
            "monorepo (pnpm workspace)",
            "tokens (color/spacing/typography)",
            "Storybook 8 + Chromatic",
            "tsup 번들",
            "npm publish 자동화",
            "마이그레이션 가이드",
        ],
    },
    {
        "task": "사용자 알림 시스템 (이메일/Push/Slack)",
        "plan": [
            "통합 알림 추상화 (template + channel)",
            "Resend/Postmark 이메일",
            "FCM/APNs Push",
            "Slack Webhook",
            "사용자 환경설정 UI",
            "전송 로그/재시도",
        ],
    },
    {
        "task": "검색 시스템 (Meilisearch / Typesense)",
        "plan": [
            "엔진 비교 후 선정",
            "인덱스 스키마",
            "데이터 동기화 (CDC or batch)",
            "검색 UI (facets/filter)",
            "한국어 형태소 처리",
            "성능 측정",
        ],
    },
    {
        "task": "비디오 스트리밍 (HLS) 지원",
        "plan": [
            "FFmpeg 트랜스코딩 워커",
            "HLS playlist 생성",
            "S3 + CloudFront 배포",
            "DRM 검토",
            "플레이어 (hls.js) 통합",
            "대역폭 적응 스트림",
        ],
    },
    {
        "task": "Webhook 발신 시스템 + 재시도",
        "plan": [
            "구독 모델 (event types)",
            "서명 검증 (HMAC)",
            "지수 백오프 재시도 큐",
            "DLQ 모니터링",
            "구독자용 대시보드",
        ],
    },
    {
        "task": "Feature Flag 시스템 도입 (자체 호스팅)",
        "plan": [
            "Unleash / OpenFeature 비교",
            "SDK 통합",
            "롤아웃/세그먼트 룰",
            "관리자 UI",
            "감사/변경 이력",
        ],
    },
    {
        "task": "백업/복구 전략 (PITR)",
        "plan": [
            "WAL 아카이브 설정",
            "S3 백업 보존 정책",
            "자동 복구 리허설",
            "RTO/RPO 문서화",
            "재해복구 시나리오 테스트",
        ],
    },
    {
        "task": "오디오/음성 메시지 기능",
        "plan": [
            "MediaRecorder 녹음",
            "WebAssembly opus 인코딩",
            "S3 presigned 업로드",
            "STT (Whisper) 자막 생성",
            "재생 컴포넌트",
        ],
    },
    {
        "task": "지도 기반 위치 서비스",
        "plan": [
            "Mapbox / 카카오맵 비교",
            "PostGIS 셋업",
            "지오인덱스",
            "근접 검색 API",
            "프론트엔드 마커/클러스터",
        ],
    },
    {
        "task": "온보딩 튜토리얼 (Tour)",
        "plan": [
            "react-joyride / shepherd 비교",
            "스텝 데이터 모델",
            "분기형 튜토리얼",
            "진행 추적/A/B 테스트",
        ],
    },
    {
        "task": "분석 SDK 자체 구축 (PostHog 대안)",
        "plan": [
            "이벤트 수집 엔드포인트",
            "ClickHouse 적재",
            "퍼널/리텐션 차트",
            "GDPR 옵트아웃",
            "익스포트 API",
        ],
    },
    {
        "task": "이메일 마케팅 캠페인 도구",
        "plan": [
            "구독자 리스트 모델",
            "Drag&drop 에디터",
            "Resend 통합 발송",
            "오픈/클릭 추적",
            "자동 시퀀스 (drip)",
        ],
    },
    {
        "task": "PDF 생성 / 영수증 인쇄",
        "plan": [
            "Playwright 헤드리스 렌더링",
            "한국어 폰트 임베딩",
            "템플릿 시스템 (Handlebars)",
            "S3 저장 + presigned 다운로드",
            "사이즈 최적화",
        ],
    },
    {
        "task": "Recommender 모델 학습 파이프라인",
        "plan": [
            "데이터셋 준비 (interactions)",
            "모델 학습 (LightFM / two-tower)",
            "오프라인 평가 (NDCG/Recall@K)",
            "온라인 서빙 (FastAPI)",
            "A/B 테스트",
        ],
    },
    {
        "task": "온체인 결제 (HWARANG 코인) 연동",
        "plan": [
            "스마트 컨트랙트 인터페이스 검토",
            "결제 의도 → 트랜잭션 매핑",
            "이벤트 수신 (Webhook/Indexer)",
            "환불/취소 정책",
            "가스비 처리 정책",
        ],
    },
    {
        "task": "VS Code 확장 (hwarang-vscode) 인증 강화",
        "plan": [
            "기존 토큰 저장소 분석",
            "OAuth Device Flow 추가",
            "Bearer 토큰 회전",
            "에러 복구",
            "마켓플레이스 재배포",
        ],
    },
]


def gen_plan_only(p):
    plan_str = "\n".join(f"{i + 1}. {step}    [pending]" for i, step in enumerate(p["plan"]))
    if random.random() < 0.35:
        prefix = (
            f"화랑입니다. {p['task']} — 단계가 많아서 먼저 plan 으로 합의한 다음 진행하겠습니다.\n\n"
        )
    else:
        prefix = (
            f"{p['task']} 진행 계획입니다. 단계가 많아 먼저 plan 으로 합의한 다음 진행하겠습니다.\n\n"
        )

    body = (
        prefix
        + f"@@plan\n{plan_str}\n@@end\n\n"
        + "이 계획대로 진행해도 괜찮을까요? 추가/제외할 단계 있으면 알려주세요."
    )
    return m([
        syss(),
        user(p["task"]),
        assistant(body),
    ])


SCENARIO_HP2 = [gen_plan_only(random.choice(BIG_TASK_PATTERNS)) for _ in range(300)]


# ---------------------------------------------------------------------------
# HP-3: Diff + Suggestion + Warning (400)
# ---------------------------------------------------------------------------

DIFF_PATTERNS = [
    {
        "task": "console.log 디버그 출력을 logger 로 교체",
        "path": "src/services/user.ts",
        "diff": "- console.log('debug:', user)\n+ logger.debug('user 조회', { user })",
        "suggestion": ("info", "winston / pino 같은 logger 라이브러리 도입을 권장. 환경별 로그 레벨 제어 가능."),
        "warning": None,
    },
    {
        "task": "innerHTML XSS 취약점 수정",
        "path": "src/components/Comment.tsx",
        "diff": "- el.innerHTML = userInput\n+ el.textContent = userInput",
        "suggestion": ("medium-risk", "userInput 에 HTML 렌더링이 필요하면 DOMPurify.sanitize() 로 정화 후 dangerouslySetInnerHTML 사용."),
        "warning": "이 변경은 HTML 렌더링이 의도였던 케이스 (이모지/링크 등) 에 영향이 있을 수 있어요. 사용처 확인 필요.",
    },
    {
        "task": "any → 명시적 타입으로 좁히기",
        "path": "src/lib/api.ts",
        "diff": "- function fetch(data: any) {\n+ function fetch(data: { id: number; name: string }) {",
        "suggestion": ("info", "Zod 스키마 + z.infer 패턴으로 런타임 검증 + 정적 타입을 동시에 얻을 수 있어요."),
        "warning": None,
    },
    {
        "task": "환경변수 노출 — 시크릿 키 클라이언트 번들 제거",
        "path": "src/config.ts",
        "diff": "- const KEY = process.env.STRIPE_SECRET_KEY\n+ // 시크릿은 서버에서만 사용",
        "suggestion": ("high-risk", "이미 빌드/배포된 적 있다면 키 회전 필수. Stripe 대시보드에서 즉시 재발급 후 .env 갱신."),
        "warning": "키가 외부에 노출되었을 가능성이 있다면 재발급 전에는 절대 안전하지 않습니다.",
    },
    {
        "task": "SQL injection 위험 — Prepared statement 전환",
        "path": "src/db/queries.ts",
        "diff": "- db.query(`SELECT * FROM users WHERE id = ${id}`)\n+ db.query('SELECT * FROM users WHERE id = $1', [id])",
        "suggestion": ("medium-risk", "ORM (Prisma/Drizzle) 도입 시 이런 실수 자체가 안 일어나요."),
        "warning": "운영 코드 전반에 비슷한 패턴이 더 있는지 grep 으로 한번 더 훑어보세요.",
    },
    {
        "task": "비동기 코드 race condition 수정",
        "path": "src/services/order.ts",
        "diff": "- const order = await getOrder(id)\n- await updateOrder({ ...order, status: 'paid' })\n+ await db.transaction(async tx => {\n+   const order = await tx.order.findUnique({ where: { id }})\n+   await tx.order.update({ where: { id }, data: { status: 'paid' }})\n+ })",
        "suggestion": ("info", "동시 결제 처리량이 많으면 SELECT FOR UPDATE 또는 낙관적 락 추가 검토."),
        "warning": "트랜잭션 격리 수준 확인 필요 — 현재 READ COMMITTED 라면 SERIALIZABLE 도 고려.",
    },
    {
        "task": "useEffect 무한루프 — 의존성 누락 수정",
        "path": "src/hooks/useUser.ts",
        "diff": "- useEffect(() => { setUser({ ...user, loaded: true }) })\n+ useEffect(() => { setUser(prev => ({ ...prev, loaded: true })) }, [])",
        "suggestion": ("info", "ESLint react-hooks/exhaustive-deps 규칙을 켜두면 이런 누락이 자동 감지됩니다."),
        "warning": None,
    },
    {
        "task": "메모리 누수 — 타이머 cleanup 추가",
        "path": "src/components/Timer.tsx",
        "diff": "  useEffect(() => {\n    const id = setInterval(tick, 1000)\n+   return () => clearInterval(id)\n  }, [])",
        "suggestion": ("info", "AbortController 패턴으로 fetch/이벤트 리스너도 같이 정리하면 안전."),
        "warning": None,
    },
    {
        "task": "비밀번호 평문 저장 → bcrypt 해시",
        "path": "src/services/auth.ts",
        "diff": "- await db.user.create({ data: { email, password } })\n+ const hash = await bcrypt.hash(password, 12)\n+ await db.user.create({ data: { email, password: hash } })",
        "suggestion": ("high-risk", "기존 사용자 비밀번호도 마이그레이션 필요 — 다음 로그인 시점에 해시화하는 lazy migration 권장."),
        "warning": "이 변경은 기존 평문 비밀번호와 호환되지 않습니다. 마이그레이션 전략 없이 배포하면 모두 로그인 실패.",
    },
    {
        "task": "JWT 만료 시간 너무 길어 단축",
        "path": "src/lib/jwt.ts",
        "diff": "- jwt.sign(payload, secret, { expiresIn: '30d' })\n+ jwt.sign(payload, secret, { expiresIn: '15m' })",
        "suggestion": ("medium-risk", "refresh token 패턴 같이 도입 — access 15m + refresh 7d. 자동 갱신 로직 클라이언트에 추가."),
        "warning": "현재 클라이언트가 자동 갱신을 처리하지 않으면 사용자가 15분마다 로그아웃됩니다.",
    },
    {
        "task": "fetch timeout 추가",
        "path": "src/lib/api.ts",
        "diff": "- await fetch(url)\n+ await fetch(url, { signal: AbortSignal.timeout(10_000) })",
        "suggestion": ("info", "재시도 로직 (지수 백오프) 추가하면 일시적 네트워크 장애 복원력 좋아짐."),
        "warning": None,
    },
    {
        "task": "CORS 와일드카드 → 도메인 화이트리스트",
        "path": "src/server/index.ts",
        "diff": "- app.use(cors({ origin: '*' }))\n+ app.use(cors({ origin: ['https://app.hwarang.ai', 'https://admin.hwarang.ai'] }))",
        "suggestion": ("info", "환경변수로 origin 리스트 주입하면 환경별 분기 깔끔."),
        "warning": "외부 통합/위젯이 있다면 해당 도메인이 화이트리스트에 들어가야 합니다.",
    },
    {
        "task": "rate limiting 적용",
        "path": "src/server/index.ts",
        "diff": "+ import rateLimit from 'express-rate-limit'\n+ app.use('/api/', rateLimit({ windowMs: 60_000, max: 60 }))",
        "suggestion": ("info", "Redis 백업 store 사용하면 멀티 인스턴스에서도 정확."),
        "warning": None,
    },
    {
        "task": "이미지 alt 누락 — 접근성 개선",
        "path": "src/components/Avatar.tsx",
        "diff": "- <img src={src} />\n+ <img src={src} alt={`${name} 프로필 사진`} />",
        "suggestion": ("info", "axe-core / eslint-plugin-jsx-a11y 도입하면 다른 a11y 이슈도 자동 감지."),
        "warning": None,
    },
    {
        "task": "N+1 쿼리 → include 로 한방 조회",
        "path": "src/services/post.ts",
        "diff": "- const posts = await prisma.post.findMany()\n- for (const p of posts) p.author = await prisma.user.findUnique({ where: { id: p.authorId }})\n+ const posts = await prisma.post.findMany({ include: { author: true }})",
        "suggestion": ("info", "Prisma 의 include / GraphQL DataLoader 패턴 일반화하면 좋아요."),
        "warning": None,
    },
    {
        "task": "지연 평가 — Map 으로 O(n²) → O(n)",
        "path": "src/utils/match.ts",
        "diff": "- items.filter(a => other.find(b => b.id === a.id))\n+ const otherById = new Map(other.map(b => [b.id, b]))\n+ items.filter(a => otherById.has(a.id))",
        "suggestion": ("info", "큰 리스트면 차이가 큽니다. 1만 개 기준 100배 이상 빨라질 수 있어요."),
        "warning": None,
    },
    {
        "task": "환경변수 검증 — z.object 도입",
        "path": "src/env.ts",
        "diff": "+ export const env = z.object({\n+   DATABASE_URL: z.string().url(),\n+   STRIPE_SECRET_KEY: z.string().startsWith('sk_'),\n+ }).parse(process.env)",
        "suggestion": ("info", "앱 부팅 시점에 누락/잘못된 env 즉시 발견 — 운영 사고 예방."),
        "warning": None,
    },
    {
        "task": "에러 경계 (Error Boundary) 추가",
        "path": "src/App.tsx",
        "diff": "+ <ErrorBoundary fallback={<ErrorPage />}>\n   <Router />\n+ </ErrorBoundary>",
        "suggestion": ("info", "Sentry 의 ErrorBoundary 사용하면 자동으로 에러 리포팅도 됩니다."),
        "warning": None,
    },
    {
        "task": "deprecated API 제거 — Buffer.from",
        "path": "src/lib/encode.ts",
        "diff": "- new Buffer(str)\n+ Buffer.from(str)",
        "suggestion": ("info", "Node 18+ 에서는 경고만 뜨지만 미래 메이저에서 제거될 수 있어요."),
        "warning": None,
    },
    {
        "task": "any[] → ReadonlyArray<T>",
        "path": "src/types/order.ts",
        "diff": "- items: any[]\n+ items: ReadonlyArray<OrderItem>",
        "suggestion": ("info", "불변 보장으로 의도치 않은 mutation 방지."),
        "warning": None,
    },
    {
        "task": "상수 매직넘버 → 명명된 상수",
        "path": "src/services/billing.ts",
        "diff": "- if (days > 30) ...\n+ const TRIAL_LIMIT_DAYS = 30\n+ if (days > TRIAL_LIMIT_DAYS) ...",
        "suggestion": ("info", "정책 상수는 별도 config 파일에 모으는 패턴이 유지보수에 좋아요."),
        "warning": None,
    },
    {
        "task": "전역 try/catch — 구조화된 에러 클래스",
        "path": "src/errors.ts",
        "diff": "+ export class AppError extends Error {\n+   constructor(public code: string, message: string, public status = 500) { super(message) }\n+ }",
        "suggestion": ("info", "Express errorHandler 미들웨어와 짝지어서 응답 포맷 통일."),
        "warning": None,
    },
    {
        "task": "Date 타입 누수 — 직렬화 통일",
        "path": "src/lib/serialize.ts",
        "diff": "+ export const serialize = (v: unknown): unknown => v instanceof Date ? v.toISOString() : v",
        "suggestion": ("info", "superjson 라이브러리 쓰면 Date/BigInt 자동 처리."),
        "warning": None,
    },
    {
        "task": "콘솔 비밀번호 로그 즉시 제거",
        "path": "src/services/auth.ts",
        "diff": "- console.log('login attempt', { email, password })\n+ console.log('login attempt', { email })",
        "suggestion": ("high-risk", "이미 운영 로그에 비밀번호가 적재되었다면 로그 정리 + 영향 사용자 비밀번호 재설정 안내가 필요."),
        "warning": "운영 환경 로그 시스템 (CloudWatch/Datadog 등) 에서도 과거 로그를 마스킹/삭제하세요.",
    },
    {
        "task": "악성 파일 업로드 — MIME 검증 추가",
        "path": "src/api/upload.ts",
        "diff": "+ if (!['image/png', 'image/jpeg'].includes(file.mimetype)) throw new AppError('INVALID_TYPE', 'Unsupported file type', 415)",
        "suggestion": ("medium-risk", "magic number 기반 검사 (file-type 라이브러리) 가 헤더 위조에 더 강해요."),
        "warning": "MIME 타입은 클라이언트가 위조 가능. 서버측에서 실제 바이트 시그니처 확인 필요.",
    },
    {
        "task": "재귀 깊이 → 반복문 변환 (스택 오버플로 방지)",
        "path": "src/utils/tree.ts",
        "diff": "+ const stack = [root]\n+ while (stack.length) {\n+   const node = stack.pop()!\n+   visit(node)\n+   stack.push(...node.children)\n+ }",
        "suggestion": ("info", "트리 깊이가 1만 이상이면 재귀는 위험. 명시적 스택이 안전합니다."),
        "warning": None,
    },
    {
        "task": "브라우저 LocalStorage → 토큰 → HttpOnly 쿠키",
        "path": "src/lib/auth.ts",
        "diff": "- localStorage.setItem('token', t)\n+ // 서버가 Set-Cookie: token=...; HttpOnly; Secure; SameSite=Lax 로 설정",
        "suggestion": ("medium-risk", "CSRF 토큰 (double-submit) 같이 도입해야 안전."),
        "warning": "기존 클라이언트가 Authorization 헤더로 보내고 있다면 백엔드 미들웨어 변경 필요.",
    },
]


def gen_diff_with_meta(p):
    intro = ""
    if random.random() < 0.30:
        intro = "화랑이 변경 사항을 적용합니다.\n\n"

    body = intro + f"@@diff {p['path']}\n{p['diff']}\n@@end\n\n"
    if p["suggestion"]:
        level, msg = p["suggestion"]
        body += f"@@suggestion: {level}\n{msg}\n@@end\n\n"
    if p["warning"]:
        body += f"@@warning\n{p['warning']}\n@@end\n\n"
    body += (
        "@@summary\n"
        f"✓ {p['task']} 적용\n"
        + ("- 위 제안 검토 권장\n" if p["suggestion"] else "")
        + ("- 경고 확인 후 다음 단계 진행\n" if p["warning"] else "")
        + "@@end"
    )
    return m([
        syss(),
        user(p["task"]),
        assistant(body),
    ])


SCENARIO_HP3 = [gen_diff_with_meta(random.choice(DIFF_PATTERNS)) for _ in range(400)]


# ---------------------------------------------------------------------------
# HP-4: 단순 질문 — Markup 없이 plain (300) [핵심 — markup 남용 방지]
# ---------------------------------------------------------------------------

SIMPLE_QUESTIONS = [
    ("React 와 Vue 차이?",
     "React 는 JSX 로 UI 와 로직을 한 파일에 쓰고, Vue 는 template/script/style 을 분리해요. React 가 더 유연하고 생태계가 크며, Vue 는 진입 장벽이 낮고 공식 솔루션 (router/pinia) 이 잘 정돈돼 있습니다."),
    ("npm vs pnpm?",
     "pnpm 이 디스크 효율이 좋고 (hard link) 설치 속도가 빠릅니다. npm 은 Node 기본이라 호환성이 가장 좋아요. 모노레포면 pnpm workspace 가 편합니다."),
    ("TypeScript 꼭 써야 해?",
     "팀 프로젝트나 5천 줄 이상이면 권장합니다. 작은 스크립트는 JS 도 충분해요. 점진 도입 (allowJs + 핵심부터 .ts) 도 가능합니다."),
    ("넌 누구야?",
     "저는 화랑 AI 입니다. 퍼시스모어가 만든 한국형 코딩 어시스턴트예요. 코드 작성, 리팩터링, 디버깅을 도와드립니다."),
    ("화랑이 뭐야?",
     "화랑 (Hwarang) 은 퍼시스모어가 만든 코딩 특화 AI 어시스턴트입니다. 한국어/한국 개발 환경에 최적화돼 있어요."),
    ("REST vs GraphQL 어느 게 좋아?",
     "단순 CRUD/캐시가 중요하면 REST 가 깔끔하고, 클라이언트마다 필드 요구가 다르면 GraphQL 이 유리합니다. 둘 다 같이 쓰는 케이스도 흔해요."),
    ("Promise.all 과 Promise.allSettled 차이?",
     "all 은 하나라도 reject 되면 즉시 reject. allSettled 는 모든 결과를 fulfilled/rejected 객체 배열로 반환합니다. 부분 실패 허용이면 allSettled."),
    ("== vs === ?",
     "=== 는 타입 변환 없이 비교, == 는 변환 후 비교입니다. 항상 === 권장. 예외적으로 null/undefined 동시 체크할 때만 == null 패턴이 유용해요."),
    ("var/let/const 차이?",
     "var 는 함수 스코프 + 호이스팅. let/const 는 블록 스코프. const 는 재할당 불가 (객체 내부는 변경 가능). 기본 const, 필요할 때만 let, var 는 사용 안 함."),
    ("CommonJS vs ESM ?",
     "CommonJS 는 require/module.exports (Node 기본). ESM 은 import/export (브라우저 + Node 14+). 신규 프로젝트는 ESM 권장."),
    ("CSR / SSR / SSG 뭐가 좋아?",
     "사용자별 동적 데이터면 SSR, 콘텐츠가 정적이면 SSG, 대시보드처럼 로그인 후 인터랙션 위주면 CSR. Next.js/Nuxt 는 페이지별로 섞을 수 있어요."),
    ("PostgreSQL vs MySQL 어느 거?",
     "PostgreSQL 은 표준 SQL 준수 + 풍부한 타입/JSONB/확장 (pgvector 등). MySQL 은 가벼움 + 운영 노하우 풍부. 신규는 PostgreSQL 추천."),
    ("Docker 가 뭐야?",
     "애플리케이션 + 의존성을 컨테이너 이미지로 패키징해서 어디서나 동일하게 실행하는 도구입니다. 개발/스테이징/운영 환경 차이를 없앨 수 있어요."),
    ("Git rebase vs merge ?",
     "merge 는 히스토리를 그대로 보존, rebase 는 깔끔한 직선 히스토리. 협업 브랜치는 merge, 개인 작업 브랜치를 정리할 때는 rebase 권장."),
    ("CSS in JS 권장?",
     "DX 와 동적 스타일이 중요하면 styled-components/Emotion. 성능/번들 사이즈가 중요하면 Tailwind 나 vanilla-extract. 트렌드는 zero-runtime 쪽."),
    ("hooks 가 뭐야?",
     "React 에서 함수형 컴포넌트가 상태/생명주기를 다룰 수 있게 해주는 함수예요. useState/useEffect/useMemo 등이 대표적입니다."),
    ("clean code 핵심?",
     "이름이 의도를 드러내고, 함수가 한 가지만 하고, 중복이 없고, 테스트 가능한 구조 — 4가지가 핵심입니다."),
    ("DRY vs WET 어느 게 맞아?",
     "DRY (Don't Repeat Yourself) 가 일반적으로 권장되지만 과도하면 추상화 부채가 됩니다. 3번째 중복부터 추상화하는 'Rule of Three' 가 균형점이에요."),
    ("OOP vs 함수형 ?",
     "도메인 모델이 명확하고 상태가 많으면 OOP, 데이터 변환 파이프라인이 많으면 함수형이 깔끔합니다. 현대 언어는 둘 다 섞어 쓰는 게 보통이에요."),
    ("microservices 언제 써?",
     "팀이 5~10명 이상으로 커져 독립 배포가 필요하거나, 일부 서비스만 다른 스케일/스택이 필요할 때입니다. 작은 팀은 모놀리식이 훨씬 빠릅니다."),
    ("Redis 캐시 TTL 어떻게 정해?",
     "데이터 변경 빈도와 일관성 요구를 보고 정합니다. 사용자 프로필 5~15분, 인기 게시글 1분, 환율 같은 외부 데이터는 5분 정도가 흔해요."),
    ("Kubernetes 꼭 써야 해?",
     "트래픽이 일정하지 않고 자동 확장이 필요하거나 여러 서비스를 운영하면 가치 있어요. 작은 팀/단일 서비스는 EC2/Render/Railway 가 더 간단합니다."),
    ("CI/CD 어떻게 시작하지?",
     "GitHub Actions 로 lint + test + build 자동화부터 시작. 메인 브랜치 머지 시 자동 배포 (Vercel/Render) 까지 붙이면 기본은 충분합니다."),
    ("Why Rust ?",
     "메모리 안전 + 무 GC + C 수준 성능. CLI/시스템 프로그래밍/WASM 에 강점. 학습 곡선은 가파릅니다."),
    ("Go 가 좋은 이유?",
     "간결한 문법 + 빠른 컴파일 + 강력한 표준 라이브러리 + 고루틴. 백엔드 API/DevOps 도구에 인기."),
    ("Python 의 GIL 이 뭐야?",
     "CPython 의 Global Interpreter Lock. 한 번에 하나의 스레드만 Python 바이트코드를 실행해요. CPU 바운드 병렬은 multiprocessing 또는 asyncio + I/O 바운드로 우회."),
    ("async/await 가 뭐야?",
     "비동기 코드를 동기처럼 읽기 쉽게 쓰는 문법입니다. Promise 위에 syntactic sugar 라고 보면 돼요."),
    ("OAuth 가 뭐야?",
     "비밀번호 공유 없이 제3자 앱에 권한을 위임하는 표준이에요. 'Google 로 로그인' 같은 게 대표 사례."),
    ("JWT 가 뭐야?",
     "JSON Web Token. 서명된 JSON 토큰으로 인증/인가에 사용해요. stateless 하다는 게 장점이지만 폐기 (revoke) 가 어렵습니다."),
    ("CORS 에러 어떻게 해결?",
     "서버에서 Access-Control-Allow-Origin 헤더를 응답에 포함하면 됩니다. 개발 중엔 dev 서버 proxy 설정으로도 우회 가능해요."),
    ("Docker Compose vs Kubernetes ?",
     "Compose 는 단일 호스트 개발/소규모 운영에 적합. Kubernetes 는 멀티 노드 + 자동 확장/복구가 필요할 때 씁니다."),
    ("Linux 기본 명령어 추천?",
     "ls, cd, grep, find, ps, top, kill, tar, ssh, curl, jq — 이 정도면 일상은 충분해요."),
    ("VS Code vs Cursor ?",
     "VS Code 는 안정적/생태계 풍부. Cursor 는 AI 통합이 더 깊습니다. 화랑 확장팩을 VS Code 에 설치하면 비슷한 AI 개발 경험을 얻을 수 있어요."),
    ("좋은 PR 작성 팁?",
     "작게 쪼개고, 제목은 동사로 시작, 설명에 'why' 를 적고, 스크린샷/테스트 결과 첨부 — 리뷰어 피로도가 절반으로 줄어요."),
    ("코드 리뷰 어떻게 해?",
     "1) 전체 흐름 한번 본 뒤 2) 위험 부분 (인증/결제/데이터 변경) 위주로 보고 3) nit 은 제안형으로, blocker 는 명확하게 표시합니다."),
    ("단위테스트 vs 통합테스트 비율?",
     "테스트 피라미드 — 단위 70 / 통합 20 / E2E 10 이 정석. 도메인 로직은 단위, 라우터/DB 는 통합, 핵심 사용자 흐름은 E2E."),
    ("monorepo 장단점?",
     "공통 코드 공유 + 한번에 변경 + atomic 커밋이 장점. 빌드 속도/CI 비용/소유권 분리가 단점이에요. Nx/Turborepo 가 도와줘요."),
    ("Tailwind 진짜 좋아?",
     "중복 클래스 보기엔 못생기지만 디자인 토큰 일관성 + 번들 사이즈 + 개발 속도가 장점입니다. 팀 합의 후 도입 권장."),
    ("zustand vs redux ?",
     "redux 는 거대한 앱 + 미들웨어/devtools 가 강점. zustand 는 보일러플레이트 거의 없고 가벼움. 신규 프로젝트는 zustand/jotai 가 트렌드."),
    ("프론트 상태관리 도구 추천?",
     "서버 상태는 React Query/SWR, 클라이언트 상태는 zustand/jotai, 폼은 react-hook-form. 이 셋이면 대부분 커버됩니다."),
    ("백엔드 처음 시작하면?",
     "Express/Fastify 같은 가벼운 프레임워크 + PostgreSQL + Prisma 조합 추천. 점진적으로 인증/배포/모니터링을 붙이세요."),
    ("DB 마이그레이션 안전하게?",
     "1) 추가는 안전, 2) 삭제/이름변경은 2단계 (호환 컬럼 추가 → 코드 전환 → 옛 컬럼 삭제), 3) 큰 테이블은 백필 작업 분리."),
    ("PostgreSQL 인덱스 언제 추가?",
     "WHERE/ORDER BY/JOIN 자주 쓰는 컬럼. EXPLAIN ANALYZE 로 seq scan 이 보이고 행이 크면 후보. 단, 쓰기 부하 증가는 트레이드오프."),
    ("python 가상환경 권장?",
     "uv 또는 poetry 가 빠르고 lockfile 도 잘 관리해줘요. 표준 venv + pip 도 충분하고 가볍습니다."),
    ("자바스크립트 디버깅 팁?",
     "console.log 보다 chrome devtools breakpoint 가 훨씬 강력해요. node --inspect 로 백엔드도 같은 방식으로 디버깅할 수 있어요."),
    ("코드 포매터 prettier ?",
     "팀 컨벤션 다툼을 없애줘서 적극 권장합니다. ESLint 와 충돌 안 나게 eslint-config-prettier 같이 쓰세요."),
    ("CSS Grid vs Flexbox ?",
     "1차원 (가로 줄, 세로 줄) 정렬은 Flexbox, 2차원 (행 + 열) 레이아웃은 Grid. 페이지 레이아웃 = Grid, 컴포넌트 내부 = Flexbox 가 보통."),
    ("반응형 디자인 시작?",
     "모바일 우선 (mobile-first) + Tailwind/CSS 미디어쿼리 + 컨테이너 쿼리 (최신). flex/grid 를 잘 쓰면 미디어쿼리 자체가 줄어요."),
    ("Next.js App Router 좋아?",
     "Server Component 와 streaming 등 새 기능이 많지만 학습 곡선이 있어요. 기존 프로젝트는 Pages Router 도 충분히 좋아요."),
    ("Vite 왜 빠른 거야?",
     "ESM 네이티브 + esbuild 사전번들링 + dev 시 번들 안 함. webpack 대비 cold start 가 한 자릿수 초로 줄어요."),
    ("HTTP/2 vs HTTP/3 ?",
     "HTTP/2 는 TCP 위에서 멀티플렉싱, HTTP/3 는 QUIC (UDP 기반) 으로 head-of-line blocking 해결. 모바일 네트워크에서 체감 차이가 큽니다."),
    ("WebSocket vs SSE vs Polling ?",
     "양방향이면 WebSocket, 서버→클라 단방향이면 SSE, 단순/짧은 폴링이면 long polling. 채팅=WS, 알림=SSE 가 흔한 조합."),
    ("환경변수 관리 베스트?",
     ".env 파일 + Zod 검증 + 타입 안전 export. 배포 환경은 Vercel/Doppler/AWS Secrets Manager 같은 매니저드 서비스 추천."),
    ("Code Splitting 어떻게?",
     "React.lazy + Suspense + 라우트 단위 분리가 기본. 큰 라이브러리 (chart 등) 는 동적 import 로 지연 로드."),
    ("HTTPS 인증서 어떻게?",
     "Let's Encrypt + certbot 무료 자동 갱신. Cloudflare/AWS ACM 같은 매니지드 인증서가 더 편해요."),
    ("로그 어떻게 모아?",
     "stdout 으로 JSON 로그 출력 → docker/k8s 가 수집 → Loki/Datadog/CloudWatch 로 적재. 구조화 로그가 검색에 유리."),
    ("모니터링 어떻게 시작?",
     "메트릭 (CPU/메모리/RPS/에러율) → 로그 → 분산 트레이싱 순서로 도입. Grafana Cloud / Datadog 한 곳으로 통합하면 운영 편함."),
    ("회사에 화랑 도입하면 뭐가 좋아?",
     "한국어 코드 리뷰/리팩터링이 자연스럽고, 사내 코드/문서 학습 (LoRA) 이 가능해서 도메인 지식이 쌓일수록 정확도가 올라갑니다."),
    ("화랑은 어떤 모델 써?",
     "복잡한 코딩은 DeepSeek V3, 간단한 코딩은 Qwen3-Coder-30B, 법률은 EXAONE, 일반 대화는 Qwen2.5 — 자동으로 라우팅합니다."),
    ("화랑 LoRA 가 뭐야?",
     "LoRA (Low-Rank Adaptation) 로 화랑 베이스 모델 위에 도메인/스타일 어댑터를 얹어 빠르게 튜닝하는 방식입니다. 풀 파인튜닝보다 비용이 100배 저렴해요."),
    ("코드 생성할 때 hallucination 줄이는 법?",
     "있는 파일/함수 시그니처를 먼저 읽고 (read_file), 검증된 컨텍스트 위에서 생성하세요. 모호하면 추측하지 말고 질문하는 게 더 좋습니다."),
    ("학습 데이터 어떻게 준비해?",
     "사내 코드/PR 리뷰/Slack 같은 자연 데이터 + JSONL 포맷 + 정체성 강화 + 단순 질문 균형. 마크업 학습이면 markup 이 없는 sample 도 30% 정도 섞으세요."),
    ("프롬프트 엔지니어링 핵심 팁?",
     "역할 정의 → 제약 조건 → 예시 (few-shot) → 출력 포맷 명시 — 이 4단계를 지키면 80% 는 안정됩니다."),
    ("유닉스 철학 한 줄 요약?",
     "한 가지 일을 잘 하는 작은 도구들이 텍스트 스트림으로 협력한다 — 입니다."),
    ("12 Factor App 알아야 해?",
     "클라우드 환경에서 운영 가능한 앱을 만드는 12가지 원칙입니다. 환경변수 / stateless / 로그 stdout 등 — 거의 표준이 됐어요."),
    ("도메인 주도 설계 (DDD) 시작?",
     "Aggregate / Entity / Value Object 부터 익히고, Bounded Context 로 모듈을 나누는 연습을 하세요. 책은 Eric Evans 의 'Domain-Driven Design'."),
    ("좋은 변수 이름 짓는 법?",
     "1) 의도 (intent) 가 드러나게 2) 검색 가능하게 3) 약어 피하기 4) 단위 포함 (delayMs, sizeBytes). 'Clean Code' 책이 좋은 참고."),
    ("주석은 언제 써?",
     "'무엇' 이 아니라 '왜' 를 적어요. 코드는 무엇을 보여주니까. 비즈니스 결정/트레이드오프/예외 사항이 좋은 주석 후보입니다."),
    ("페어 프로그래밍 효과?",
     "지식 공유 + 버그 조기 발견 + 설계 토론. 단점은 비용/피로도이지만, 어려운 문제일수록 효율적입니다."),
    ("Slack 에 화랑 봇 붙이려면?",
     "Slack App 만들고 Bolt SDK 로 이벤트 구독 → 화랑 API 로 메시지 위임 → 응답을 채널에 post. 1~2일이면 PoC 가능해요."),
    ("벡터 DB 왜 필요해?",
     "임베딩 (벡터) 으로 의미 검색 (semantic search) 을 하려면 ANN 인덱스가 필요한데, pgvector/Qdrant/Weaviate 가 그 역할을 합니다."),
    ("RAG 가 뭐야?",
     "Retrieval-Augmented Generation. 질문이 들어오면 관련 문서를 검색해서 LLM 컨텍스트에 넣어 답변 정확도를 올리는 패턴입니다."),
    ("LLM 비용 줄이는 팁?",
     "프롬프트 캐싱, 작은 모델로 라우팅, 결과 캐시, 스트리밍, 컨텍스트 압축 — 이 5가지가 가장 효과 큽니다."),
    ("Function calling 이 뭐야?",
     "LLM 이 도구 (함수) 호출이 필요하다고 판단하면 JSON 으로 인자를 만들어주는 기능. 화랑도 read_file/edit_file 같은 도구를 이 방식으로 부릅니다."),
    ("temperature 어떻게 정해?",
     "정답이 명확한 작업 (코드/요약) 은 0~0.3, 창의적 글쓰기는 0.7~1.0. 화랑은 코드 생성 시 보통 0.2 를 씁니다."),
    ("token / context window ?",
     "token 은 모델이 한번에 보는 단위 (대략 4자 = 1토큰). context window 는 한 요청에 들어갈 수 있는 token 총량 — 길수록 비싸고 느려요."),
    ("attention 이 뭐야?",
     "입력 시퀀스에서 어떤 토큰이 다른 토큰에 얼마나 영향을 주는지 가중치를 계산하는 메커니즘입니다. Transformer 의 핵심이에요."),
    ("TDD 정말 효과 있어?",
     "테스트 먼저 쓰면 설계가 testable 해지고 회귀가 줄어요. 다만 초기 속도는 느려져요. 라이브러리/엔진처럼 핵심 도메인에 특히 유리합니다."),
    ("스타트업에서 어떤 스택?",
     "TypeScript + Next.js + PostgreSQL + Prisma + Vercel/Render — 1인이 풀스택 가능하고 채용 풀도 커요."),
    ("legacy 코드 리팩토링 순서?",
     "1) 테스트 추가 (스냅샷이라도) 2) 작은 단위로 추출 3) 의존성 주입으로 분리 4) 점진 교체. Michael Feathers 의 'WELC' 가 바이블."),
    ("엔지니어 면접 잘 보는 법?",
     "최근 6개월 안에 해결한 어려운 문제를 시행착오 + 결과 + 배운 점 형태로 정리해두세요. STAR 패턴이 도움 됩니다."),
    ("개발자 번아웃 어떻게?",
     "충분한 휴식이 우선이고, 주 1회 코딩 외 활동 + 작은 성공 누적 + 팀과의 솔직한 대화가 도움 됩니다. 본인을 너무 몰지 마세요."),
    ("AI 시대 개발자는?",
     "AI 도구를 잘 쓰는 사람이 안 쓰는 사람보다 5~10배 빨라요. 핵심 역량은 '문제 정의/시스템 설계/코드 리뷰' 로 옮겨갑니다."),
    ("화랑이랑 다른 코딩 AI 차이?",
     "한국어 자연스러움, 한국 개발 환경 (NHN/네이버/쿠팡 스택) 학습, 사내 코드 LoRA 튜닝 — 이 셋이 차별점입니다."),
    ("파이썬 대신 뭐 배워?",
     "백엔드면 Go 또는 TypeScript, 시스템/임베디드면 Rust, 데이터/ML 은 Python 그대로. 목적별로 선택하세요."),
    ("개발자가 영어 꼭 잘해야 해?",
     "읽기/문서 검색은 필수, 회화는 외국계가 아니면 천천히 늘려도 충분해요. 화랑은 한글 질문도 자연스럽게 답하니 진입은 한글로 시작해도 됩니다."),
    ("좋은 첫 사이드 프로젝트?",
     "본인이 매일 쓸 도구 (책 기록기, 운동 트래커 등) 가 동기부여 면에서 최고예요. 작게 시작 → 쓰면서 개선 사이클이 빠릅니다."),
    ("새 기술 어떻게 학습해?",
     "공식 튜토리얼 1회 → 작은 프로젝트 1개 → 동작 원리 글 1편 — 이 3단계면 80% 익혀집니다."),
    ("Stack Overflow 점점 줄어드는데?",
     "AI 어시스턴트로 1차 답을 받고, 검증/심화는 공식 문서/소스 코드를 보는 흐름이 일반화됐어요. 화랑도 그 일부로 쓰시면 됩니다."),
    ("화랑한테 코드 검토 부탁해도 돼?",
     "네, 코드 붙여 넣고 '리뷰해줘' 하면 됩니다. 보안/성능/가독성 측면에서 짚어드려요."),
    ("화랑에게 한 번에 어디까지 시킬 수 있어?",
     "한 파일 수정~프로젝트 신규 생성까지 가능합니다. 작업이 크면 plan 으로 합의 → 단계별 실행으로 안전하게 진행해요."),
    ("화랑 누가 만들었어?",
     "퍼시스모어가 만들었습니다. 한국형 코딩 AI 어시스턴트를 목표로 자체 모델 + LoRA + 도구 통합을 같이 개발 중이에요."),
    ("퍼시스모어가 뭐야?",
     "화랑 (Hwarang) 을 만든 회사입니다. 한국 개발 생태계에 특화된 AI 도구를 연구/제공해요."),
    ("코딩에 ai 어디까지 의존해도 돼?",
     "단순 보일러플레이트/보조는 적극 활용, 핵심 도메인 결정/보안 코드는 본인이 검토 후 채택하는 게 안전해요. 화랑은 보조자 역할에 충실합니다."),
    ("새 라이브러리 도입할 때 체크?",
     "1) 메인터너 활동성 2) 다운로드/이슈 트렌드 3) 라이선스 4) 번들 크기 5) 보안 알림 — 5가지면 큰 사고 방지."),
    ("의존성 업데이트 자동화?",
     "Renovate / Dependabot 추천. 메이저는 사람이 검토, 마이너/패치는 CI 통과 시 자동 머지 정책이 무난해요."),
    ("코드 한 줄 정리 도와줘 — 'console.log(x)'",
     "디버그 끝났으면 그 줄은 제거하시는 게 좋아요. 영구 로그라면 logger.debug('x', { x }) 형태로 컨텍스트를 같이 남겨주세요."),
    ("HTTP 상태코드 외워야 해?",
     "200/201/204, 301/302/304, 400/401/403/404/409/422, 500/502/503 정도면 일상 대부분이에요. 나머지는 필요할 때 찾아 보세요."),
    ("REST 자원 이름 짓기 팁?",
     "복수형 명사 + 계층 구조 (/users/123/orders) + 동사 회피 (POST /users 가 createUser 보다 좋음). 일관성이 가장 중요해요."),
    ("API 버전 어떻게?",
     "URL 경로 (/v1/...) 또는 Accept 헤더. 깨지는 변경 (breaking) 만 메이저 올리고, 추가는 같은 버전 유지 — 클라이언트 부담이 줄어요."),
    ("쿼리 느려 — 뭐부터 봐?",
     "EXPLAIN ANALYZE 로 실행 계획 보고, 1) 인덱스 누락 2) Sequential Scan 3) 잘못된 join 4) 통계 outdated 순으로 점검하세요."),
    ("백엔드 vs 프론트 어디로?",
     "데이터/시스템에 흥미면 백엔드, 시각/인터랙션에 흥미면 프론트. 둘 다 익혀두면 풀스택으로 더 많은 기회가 생겨요."),
    ("내가 쓴 코드 너무 못생겼는데?",
     "동작하는 코드 → 테스트 추가 → 작은 단계로 리팩토링이 정석입니다. 한 번에 전부 갈아엎지 마세요. 화랑이 단계 도와드릴 수 있어요."),
]


def gen_simple(p):
    q, a = p
    return m([
        syss(),
        user(q),
        assistant(a),
    ])


SCENARIO_HP4 = [gen_simple(random.choice(SIMPLE_QUESTIONS)) for _ in range(300)]


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="data/sft/hp_markup_v8.jsonl",
        help="JSONL 출력 경로 (기본: data/sft/hp_markup_v8.jsonl)",
    )
    args = parser.parse_args()

    all_data = SCENARIO_HP1 + SCENARIO_HP2 + SCENARIO_HP3 + SCENARIO_HP4
    assert len(all_data) == 1500, f"expected 1500 samples, got {len(all_data)}"

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[OK] {len(all_data)} 샘플 → {args.output}")
    print(f"  HP-1 (full cycle):    {len(SCENARIO_HP1)}")
    print(f"  HP-2 (plan only):     {len(SCENARIO_HP2)}")
    print(f"  HP-3 (diff/sugg/warn):{len(SCENARIO_HP3)}")
    print(f"  HP-4 (simple Q&A):    {len(SCENARIO_HP4)}")
