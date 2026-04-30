"""화랑 AI LoRA v4 학습 데이터 — Chain-of-Thought (CoT) + Reasoning Trace

v3 까지 부족했던 "사고 과정 명시" 패턴을 보강한다.
Claude Code 처럼 답하기 전에 "왜 이걸 하는지" 단계별 추론을 보여주는 1500 샘플.

시나리오 분포 (총 1500):
  CoT-1 디버깅 추론       : 300
  CoT-2 아키텍처 결정      : 300
  CoT-3 성능 분석          : 200
  CoT-4 보안 분석          : 200
  CoT-5 마이그레이션        : 200
  CoT-6 트레이드오프 분석   : 200
  CoT-7 자기 평가 + 다음    : 300

생성 패턴:
  assistant 응답 = (사고 시작) → (즉시 tool_call) → (tool 결과) →
                  (결과 기반 다음 추론) → (필요시 tool_call) → (마무리)

추론 키워드 = "이유 / 가능성 / 확률 / 보통 / 일반적으로 / 함정 /
              고려할 점 / 우선순위 / 트레이드오프 / 결정 트리 / 우선"

정체성 키워드 = "화랑 / 퍼시스모어"  (전체 30% 샘플에 자연스럽게 삽입)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# v1 헬퍼 재사용 (같은 디렉토리)
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from build_tools_multiturn import (  # noqa: E402
    TOOLS_DESC, m, sys as _sys, user, assistant, tool, tc, acall,
)


def syss():
    return _sys()


# ============================================================
# 공통: 정체성 멘트 + 추론 키워드 검증
# ============================================================

IDENTITY_PHRASES = [
    "화랑 AI 로서 ",
    "퍼시스모어 가이드라인에 따라 ",
    "화랑 스타일로 정리하면, ",
    "(화랑 권장: 검증된 우선순위로 접근) ",
    "퍼시스모어 코딩 표준 기준으로 ",
    "화랑 베스트 프랙티스 기준 ",
]

REASONING_KEYWORDS = [
    "이유", "원인", "가능성", "확률", "보통", "일반적으로",
    "함정", "고려할 점", "우선순위", "트레이드오프",
    "결정 트리", "먼저", "다음으로", "따라서", "왜냐하면",
]


def _sprinkle_identity(text: str, rng: random.Random) -> str:
    """30% 확률로 정체성 멘트를 자연스럽게 prefix"""
    if rng.random() < 0.30:
        return rng.choice(IDENTITY_PHRASES) + text
    return text


def _has_two_keywords(text: str) -> bool:
    return sum(1 for kw in REASONING_KEYWORDS if kw in text) >= 2


# ============================================================
# 도메인 + 흔한 이슈 (디버깅/성능/보안 공통)
# ============================================================

DOMAINS_WITH_CONTEXT = [
    {
        "name": "react",
        "common_issues": [
            "hydration mismatch", "useEffect 무한 루프", "stale closure",
            "key prop 누락 경고", "리렌더링 폭주",
        ],
        "typical_file": "src/App.tsx",
        "typical_content": "import { useEffect, useState } from 'react';\n\nexport default function App() {\n  const [count, setCount] = useState(0);\n  useEffect(() => { setCount(count + 1); });\n  return <div>{count}</div>;\n}\n",
        "stack": "React 18 + Vite",
    },
    {
        "name": "next.js",
        "common_issues": [
            "Server Component 에서 useState 호출", "fetch 캐시 문제",
            "환경변수 NEXT_PUBLIC_ 누락", "middleware 무한 redirect",
        ],
        "typical_file": "app/page.tsx",
        "typical_content": "'use client';\nimport { useState } from 'react';\nexport default function Page() {\n  const [n] = useState(0);\n  return <div>{n}</div>;\n}\n",
        "stack": "Next.js 14 App Router",
    },
    {
        "name": "fastapi",
        "common_issues": [
            "async route 에서 sync ORM 사용", "Pydantic v1↔v2 혼용",
            "CORS preflight 실패", "BackgroundTasks 미동작",
        ],
        "typical_file": "app/main.py",
        "typical_content": "from fastapi import FastAPI\nfrom sqlalchemy.orm import Session\n\napp = FastAPI()\n\n@app.get('/users')\nasync def list_users(db: Session):\n    return db.query(User).all()\n",
        "stack": "FastAPI + SQLAlchemy",
    },
    {
        "name": "django",
        "common_issues": [
            "N+1 쿼리", "migration conflict", "static files 404",
            "CSRF 토큰 미포함", "settings.DEBUG=True 배포",
        ],
        "typical_file": "myapp/views.py",
        "typical_content": "from django.shortcuts import render\nfrom .models import Post\n\ndef index(request):\n    posts = Post.objects.all()\n    return render(request, 'index.html', { 'posts': posts })\n",
        "stack": "Django 4 + PostgreSQL",
    },
    {
        "name": "spring boot",
        "common_issues": [
            "LazyInitializationException", "@Transactional self-invocation",
            "circular dependency", "application.yml override 실패",
        ],
        "typical_file": "src/main/java/com/app/UserService.java",
        "typical_content": "@Service\npublic class UserService {\n  @Autowired UserRepository repo;\n  public List<User> all() { return repo.findAll(); }\n}\n",
        "stack": "Spring Boot 3 + JPA",
    },
    {
        "name": "express",
        "common_issues": [
            "async error 미캐치", "body-parser 누락",
            "headers already sent", "라우트 순서 충돌",
        ],
        "typical_file": "server.js",
        "typical_content": "const express = require('express');\nconst app = express();\napp.get('/', async (req, res) => {\n  const data = await load();\n  res.json(data);\n});\napp.listen(3000);\n",
        "stack": "Node.js + Express 4",
    },
    {
        "name": "nestjs",
        "common_issues": [
            "DI provider not found", "Guards 실행 순서",
            "Pipe validation 미작동", "Module circular import",
        ],
        "typical_file": "src/users/users.controller.ts",
        "typical_content": "@Controller('users')\nexport class UsersController {\n  constructor(private svc: UsersService) {}\n  @Get() all() { return this.svc.all(); }\n}\n",
        "stack": "NestJS 10 + TypeORM",
    },
    {
        "name": "vue",
        "common_issues": [
            "reactive 가 unwrap 안됨", "watcher 무한 호출",
            "Composition API 에서 this 참조", "Pinia store 초기화 순서",
        ],
        "typical_file": "src/App.vue",
        "typical_content": "<script setup>\nimport { ref, watch } from 'vue';\nconst n = ref(0);\nwatch(n, () => n.value++);\n</script>\n",
        "stack": "Vue 3 + Vite",
    },
    {
        "name": "flutter",
        "common_issues": [
            "setState after dispose", "BuildContext across async gap",
            "FutureBuilder 재실행", "Provider rebuild 폭주",
        ],
        "typical_file": "lib/main.dart",
        "typical_content": "class _HomeState extends State<Home> {\n  @override\n  Widget build(BuildContext c) => FutureBuilder(future: load(), builder: (_, s) => Text('\$s'));\n}\n",
        "stack": "Flutter 3 + Riverpod",
    },
    {
        "name": "rust",
        "common_issues": [
            "borrow checker 충돌", "async lifetime", "Send/Sync trait 부재",
            "Cargo feature flag conflict",
        ],
        "typical_file": "src/main.rs",
        "typical_content": "fn main() {\n  let v = vec![1,2,3];\n  let r = &v;\n  drop(v);\n  println!(\"{:?}\", r);\n}\n",
        "stack": "Rust 1.75 + Tokio",
    },
    {
        "name": "go",
        "common_issues": [
            "goroutine leak", "nil map 쓰기 panic",
            "context 전파 누락", "interface vs concrete 혼용",
        ],
        "typical_file": "main.go",
        "typical_content": "package main\nimport \"net/http\"\nfunc main() {\n  http.HandleFunc(\"/\", func(w http.ResponseWriter, r *http.Request) {\n    w.Write([]byte(\"hi\"))\n  })\n  http.ListenAndServe(\":8080\", nil)\n}\n",
        "stack": "Go 1.22 + chi",
    },
    {
        "name": "kotlin",
        "common_issues": [
            "coroutine cancel 미전파", "Flow collector 중복 수집",
            "lateinit 미초기화", "Compose recomposition 폭주",
        ],
        "typical_file": "src/main/kotlin/Main.kt",
        "typical_content": "fun main() = runBlocking {\n  val job = launch { delay(1000); println(\"done\") }\n  job.join()\n}\n",
        "stack": "Kotlin + Ktor",
    },
    {
        "name": "swift",
        "common_issues": [
            "retain cycle", "@MainActor 누락", "SwiftUI body 재계산 폭주",
            "async let 순서 의존",
        ],
        "typical_file": "Sources/App/ContentView.swift",
        "typical_content": "import SwiftUI\nstruct ContentView: View {\n  @State var n = 0\n  var body: some View { Text(\"\\(n)\") }\n}\n",
        "stack": "SwiftUI + iOS 17",
    },
    {
        "name": "python",
        "common_issues": [
            "mutable default argument", "GIL contention",
            "circular import", "asyncio loop 중첩",
        ],
        "typical_file": "app/utils.py",
        "typical_content": "def push(item, bucket=[]):\n  bucket.append(item)\n  return bucket\n",
        "stack": "Python 3.11",
    },
    {
        "name": "typescript",
        "common_issues": [
            "any 누수", "as 단언 오용", "Generic constraint 부재",
            "tsconfig strict 오프",
        ],
        "typical_file": "src/api.ts",
        "typical_content": "export async function fetchUser(id: any): Promise<any> {\n  const r = await fetch('/u/' + id);\n  return r.json();\n}\n",
        "stack": "TypeScript 5 + Node",
    },
    {
        "name": "postgres",
        "common_issues": [
            "인덱스 부재", "MVCC bloat", "lock contention",
            "잘못된 isolation level",
        ],
        "typical_file": "schema.sql",
        "typical_content": "CREATE TABLE orders (id bigserial PRIMARY KEY, user_id bigint, total numeric);\n-- index on user_id 누락\n",
        "stack": "PostgreSQL 16",
    },
    {
        "name": "redis",
        "common_issues": [
            "BIG KEY 로 메모리 폭주", "KEYS * 명령으로 블록",
            "TTL 미설정 누수", "pipeline 미사용",
        ],
        "typical_file": "src/cache.ts",
        "typical_content": "await redis.set('user:' + id, JSON.stringify(user));\n// TTL 없음\n",
        "stack": "Redis 7",
    },
    {
        "name": "mongodb",
        "common_issues": [
            "인덱스 누락 collscan", "$lookup 폭주", "writeConcern 부재",
            "mongoose populate N+1",
        ],
        "typical_file": "src/models/user.ts",
        "typical_content": "const schema = new Schema({ email: String });\n// email 인덱스 없음\n",
        "stack": "MongoDB 7 + Mongoose",
    },
    {
        "name": "kubernetes",
        "common_issues": [
            "CrashLoopBackOff", "ImagePullBackOff",
            "OOMKilled", "service selector 불일치",
        ],
        "typical_file": "k8s/deployment.yaml",
        "typical_content": "apiVersion: apps/v1\nkind: Deployment\nspec:\n  template:\n    spec:\n      containers: [{ name: app, image: app:latest }]\n",
        "stack": "Kubernetes 1.29",
    },
    {
        "name": "docker",
        "common_issues": [
            "이미지 레이어 캐시 무효화", "COPY . . 비효율",
            "multi-stage 누락", "root 사용자 보안",
        ],
        "typical_file": "Dockerfile",
        "typical_content": "FROM node:20\nCOPY . /app\nRUN npm install\nCMD [\"node\",\"index.js\"]\n",
        "stack": "Docker 24",
    },
]


GENERIC_DEBUG_CAUSES = [
    "환경변수 차이",
    "DB 스키마/데이터 차이",
    "의존성 버전 lock 불일치",
    "timezone/locale 차이",
    "캐시 stale",
    "race condition",
    "권한 (IAM/RBAC)",
    "네트워크 (방화벽/DNS)",
    "OS 차이 (mac↔linux)",
    "메모리 한계",
]


# ============================================================
# CoT-1: 디버깅 추론 (300)
# ============================================================

SCENARIO_COT_DEBUG = []


def _gen_cot_debug(rng: random.Random):
    domain = rng.choice(DOMAINS_WITH_CONTEXT)
    issue = rng.choice(domain["common_issues"])
    causes = rng.sample(GENERIC_DEBUG_CAUSES, 4)
    probs = [40, 25, 20, 15]
    rng.shuffle(probs)

    user_msg = rng.choice([
        f"{domain['name']} 에서 {issue} 가 발생해. 도와줘",
        f"우리 {domain['stack']} 인데 {issue} 때문에 막혔어",
        f"{domain['name']} {issue} — 이거 어떻게 잡지?",
        f"테스트는 통과하는데 {domain['name']} 환경에서만 {issue} 가 떠",
    ])

    reasoning_first = (
        f"{issue} 의 일반적 원인 4가지를 확률 우선순위로 정리합니다.\n\n"
        f"1. {causes[0]} (약 {probs[0]}%, 가장 흔함)\n"
        f"2. {causes[1]} (약 {probs[1]}%)\n"
        f"3. {causes[2]} (약 {probs[2]}%)\n"
        f"4. {causes[3]} (약 {probs[3]}%)\n\n"
        f"이유: {domain['stack']} 스택에서 {issue} 는 보통 환경/설정 레이어에서 시작됩니다.\n"
        f"가능한 함정: 코드만 보고 잡으려 하면 시간 낭비. 먼저 {causes[0]} 부터 확인합니다.\n"
        f"다음 단계: 해당 파일을 열어 실제 상태 점검."
    )
    reasoning_first = _sprinkle_identity(reasoning_first, rng)
    first_msg = reasoning_first + "\n\n" + tc("read_file", {"path": domain["typical_file"]})

    reasoning_second = (
        f"파일 내용 확인 결과, 의심 가는 패턴이 보입니다.\n"
        f"따라서 {causes[1]} 보다 {causes[0]} 쪽이 진짜 원인일 가능성이 높습니다.\n"
        f"이유: 코드 상에 해당 패턴이 직접 노출되어 있기 때문.\n"
        f"다음 행동: 즉시 패치합니다."
    )
    new_content = "// FIX: " + issue + "\n" + domain["typical_content"]
    second_msg = reasoning_second + "\n\n" + tc(
        "edit_file",
        {"path": domain["typical_file"], "old": domain["typical_content"], "new": new_content},
    )

    final = (
        f"수정 완료. 핵심 정리:\n"
        f"- 증상: {issue}\n"
        f"- 진짜 원인: {causes[0]} (확률 {probs[0]}% 예측이 적중)\n"
        f"- 일반적으로 {causes[1]} 도 자주 보이지만 이 케이스는 아님\n"
        f"- 다음 단계: 회귀 테스트 추가 권장"
    )

    return m([
        syss(),
        user(user_msg),
        assistant(first_msg),
        tool(domain["typical_content"]),
        assistant(second_msg),
        tool(f"Edit applied to {domain['typical_file']}: 1 replacement"),
        assistant(final),
    ])


_rng_debug = random.Random(2026_01)
for _ in range(300):
    SCENARIO_COT_DEBUG.append(_gen_cot_debug(_rng_debug))


# ============================================================
# CoT-2: 아키텍처 결정 (300)
# ============================================================

SCENARIO_COT_ARCH = []

ARCH_TOPICS = [
    {
        "topic": "결제 시스템",
        "branches": [
            ("한국 + 일회성", "포트원 (간편 통합, 다수 PG 추상화)"),
            ("한국 + 정기결제", "토스페이먼츠 (빌링 키 안정적)"),
            ("글로벌", "Stripe (문서/SDK 최강)"),
        ],
        "probe_file": "package.json",
        "probe_content": '{\n  "name": "shop",\n  "dependencies": { "next": "14.0.0", "react": "18.2.0" }\n}\n',
        "verdict": "한국 + 일회성 → 포트원 권장",
    },
    {
        "topic": "인증",
        "branches": [
            ("B2C 소셜", "NextAuth + 카카오/네이버"),
            ("B2B SSO", "WorkOS or Auth0"),
            ("자체 + 무료", "Lucia + Argon2"),
        ],
        "probe_file": "package.json",
        "probe_content": '{\n  "dependencies": { "next": "14.0.0" }\n}\n',
        "verdict": "Next.js 면 NextAuth 가 가장 통합 비용 낮음",
    },
    {
        "topic": "큐/메시지 브로커",
        "branches": [
            ("작은 워커 + Redis 이미 있음", "BullMQ"),
            ("멀티 컨슈머 + 영속성 강함", "RabbitMQ"),
            ("이벤트 스트리밍 + 재처리", "Kafka"),
        ],
        "probe_file": "docker-compose.yml",
        "probe_content": "services:\n  redis: { image: redis:7 }\n",
        "verdict": "Redis 이미 운영 중이면 BullMQ 가 운영 비용 최저",
    },
    {
        "topic": "검색",
        "branches": [
            ("문서 < 10만 개", "Postgres tsvector"),
            ("실시간 + 패싯", "Meilisearch"),
            ("로그/이벤트 + 분석", "Elasticsearch / OpenSearch"),
        ],
        "probe_file": "schema.sql",
        "probe_content": "CREATE TABLE posts (id bigserial, body text);\n",
        "verdict": "Postgres 안에 데이터가 이미 있고 양도 적으면 tsvector 가 가장 단순",
    },
    {
        "topic": "DB 선택",
        "branches": [
            ("관계형 + 트랜잭션 강함", "PostgreSQL"),
            ("스키마 자주 변함 + 임베디드 문서", "MongoDB"),
            ("OLAP/분석", "ClickHouse"),
        ],
        "probe_file": "package.json",
        "probe_content": '{\n  "dependencies": { "prisma": "5.0.0" }\n}\n',
        "verdict": "Prisma 쓰는 중이면 PostgreSQL 이 1순위",
    },
    {
        "topic": "프론트엔드 프레임워크",
        "branches": [
            ("SEO + SSR 필요", "Next.js"),
            ("관리자 / SPA 충분", "Vite + React"),
            ("정적 페이지 위주", "Astro"),
        ],
        "probe_file": "package.json",
        "probe_content": '{\n  "dependencies": { "react": "18.2.0" }\n}\n',
        "verdict": "마케팅 페이지 + SEO 가 핵심이면 Next.js",
    },
    {
        "topic": "백엔드 프레임워크",
        "branches": [
            ("Python 팀 + 빠른 API", "FastAPI"),
            ("JVM 팀 + 안정성", "Spring Boot"),
            ("Node 팀 + 단일 언어", "NestJS"),
        ],
        "probe_file": "requirements.txt",
        "probe_content": "fastapi\nuvicorn\n",
        "verdict": "이미 Python + FastAPI 면 그대로 유지가 비용 최저",
    },
    {
        "topic": "배포 인프라",
        "branches": [
            ("MVP/소규모", "Vercel / Render"),
            ("Docker 단일 컨테이너", "Fly.io"),
            ("쿠버네티스 + 멀티 서비스", "EKS / GKE"),
        ],
        "probe_file": "Dockerfile",
        "probe_content": "FROM node:20\n",
        "verdict": "단일 컨테이너 + 글로벌 배포라면 Fly.io 가 가성비",
    },
    {
        "topic": "관찰성",
        "branches": [
            ("저비용 + 단순", "Sentry + Vercel Logs"),
            ("자체 호스팅 + 풀스택", "Grafana + Loki + Tempo"),
            ("SaaS 풀패키지", "Datadog"),
        ],
        "probe_file": "package.json",
        "probe_content": '{\n  "dependencies": {}\n}\n',
        "verdict": "초기 단계면 Sentry + 기본 로그가 충분",
    },
    {
        "topic": "상태 관리 (프론트)",
        "branches": [
            ("간단/지역", "useState + Context"),
            ("복잡 + 비동기", "Zustand 또는 TanStack Query"),
            ("거대 SPA + 디버그 강함", "Redux Toolkit"),
        ],
        "probe_file": "src/App.tsx",
        "probe_content": "export default function App(){ return <div/> }\n",
        "verdict": "데이터 패칭이 핵심이면 TanStack Query 부터",
    },
]


def _gen_cot_arch(rng: random.Random):
    topic = rng.choice(ARCH_TOPICS)
    user_msg = rng.choice([
        f"{topic['topic']} 추가하려는데 어떻게 가는 게 좋을까?",
        f"{topic['topic']} 도입 검토 중인데 추천 좀",
        f"{topic['topic']} 선택 도와줘",
        f"우리 프로젝트에 맞는 {topic['topic']} 가 뭘까?",
    ])

    branches_text = "\n".join(
        f"- {cond} → **{rec}**" for cond, rec in topic["branches"]
    )
    reasoning_first = (
        f"{topic['topic']} 결정은 컨텍스트 의존이 큽니다. 먼저 결정 트리를 정리합니다.\n\n"
        f"{branches_text}\n\n"
        f"이유: 각 분기마다 운영 비용/학습 비용/락인 트레이드오프가 다릅니다.\n"
        f"가능한 함정: 인기 있다고 무조건 따라가면 over-engineering 됩니다.\n"
        f"다음 단계: 현재 프로젝트 컨텍스트부터 확인합니다."
    )
    reasoning_first = _sprinkle_identity(reasoning_first, rng)
    first_msg = reasoning_first + "\n\n" + tc("read_file", {"path": topic["probe_file"]})

    reasoning_second = (
        f"확인 결과, 현재 스택에서는 결정 트리의 첫 번째 분기에 해당합니다.\n"
        f"따라서 결론: **{topic['verdict']}**.\n"
        f"이유: 추가 인프라 도입 비용 < 기존 스택 활용 가치.\n"
        f"우선순위: 일단 가장 단순한 옵션으로 시작 → 한계 도달 시 교체."
    )
    second_msg = reasoning_second + "\n\n" + tc(
        "search_code", {"pattern": topic["topic"][:6], "path": "."}
    )

    final = (
        f"정리:\n"
        f"- 결정: {topic['verdict']}\n"
        f"- 이유: 컨텍스트 일치 + 운영 비용 최소\n"
        f"- 다음 액션: 작은 PoC 부터 (1주 내 prototype)\n"
        f"- 트레이드오프: 미래에 규모 커지면 재평가 필요"
    )

    return m([
        syss(),
        user(user_msg),
        assistant(first_msg),
        tool(topic["probe_content"]),
        assistant(second_msg),
        tool("No matches found / 0 results"),
        assistant(final),
    ])


_rng_arch = random.Random(2026_02)
for _ in range(300):
    SCENARIO_COT_ARCH.append(_gen_cot_arch(_rng_arch))


# ============================================================
# CoT-3: 성능 분석 (200)
# ============================================================

SCENARIO_COT_PERF = []

PERF_CAUSES = [
    ("N+1 쿼리", 40, "ORM 로그 또는 query 카운터"),
    ("인덱스 부재", 25, "EXPLAIN ANALYZE"),
    ("외부 API 동기 호출", 15, "분산 추적 (trace)"),
    ("JSON 직렬화 큰 객체", 10, "응답 페이로드 크기"),
    ("CPU 바운드 작업", 10, "프로파일러 (py-spy/pprof)"),
]


def _gen_cot_perf(rng: random.Random):
    domain = rng.choice(DOMAINS_WITH_CONTEXT)
    endpoint = rng.choice([
        "/api/users", "/api/orders", "/api/posts", "/api/feed",
        "/api/dashboard", "/graphql", "/api/search",
    ])
    user_msg = rng.choice([
        f"{endpoint} 가 너무 느려. 1.5초 이상 걸려",
        f"{domain['name']} API {endpoint} 가 느린데 원인 모르겠어",
        f"부하 테스트 돌리니까 {endpoint} 가 P95 가 2초 넘어",
    ])

    causes_text = "\n".join(
        f"{i+1}. {c[0]} (약 {c[1]}%) → 진단: {c[2]}"
        for i, c in enumerate(PERF_CAUSES)
    )
    reasoning_first = (
        f"느린 API 의 일반적 원인 5개와 진단 순서를 우선순위로 정리합니다.\n\n"
        f"{causes_text}\n\n"
        f"이유: {domain['stack']} 처럼 ORM 을 쓰는 스택은 N+1 가 1순위.\n"
        f"가능한 함정: CPU 부터 의심하면 보통 헛다리. DB → 외부 → 직렬화 → CPU 순서가 효율적.\n"
        f"먼저 해당 endpoint 의 코드와 쿼리 로그를 확인합니다."
    )
    reasoning_first = _sprinkle_identity(reasoning_first, rng)
    first_msg = reasoning_first + "\n\n" + tc("read_file", {"path": domain["typical_file"]})

    reasoning_second = (
        f"코드 확인 결과 N+1 패턴이 발견됐습니다.\n"
        f"이유: 반복문 안에서 관련 객체를 매번 가져옵니다.\n"
        f"따라서 eager loading / select_related / JOIN 으로 1쿼리화 합니다.\n"
        f"우선순위: 인덱스 추가는 그 다음."
    )
    second_msg = reasoning_second + "\n\n" + tc(
        "edit_file",
        {
            "path": domain["typical_file"],
            "old": domain["typical_content"][:40],
            "new": "# perf: eager-load 적용\n" + domain["typical_content"][:40],
        },
    )

    final = (
        f"수정 완료. 예상 효과:\n"
        f"- 쿼리 수: N+1 → 1 (10배 이상 감소)\n"
        f"- P95: 2s → 200ms 수준\n"
        f"- 다음 단계: EXPLAIN 으로 인덱스 검증 + 외부 API 비동기화 검토\n"
        f"- 함정: 너무 큰 JOIN 은 메모리 폭주, LIMIT 도 같이 검토"
    )

    return m([
        syss(),
        user(user_msg),
        assistant(first_msg),
        tool(domain["typical_content"]),
        assistant(second_msg),
        tool(f"Edit applied to {domain['typical_file']}: 1 replacement"),
        assistant(final),
    ])


_rng_perf = random.Random(2026_03)
for _ in range(200):
    SCENARIO_COT_PERF.append(_gen_cot_perf(_rng_perf))


# ============================================================
# CoT-4: 보안 분석 (200)
# ============================================================

SCENARIO_COT_SECURITY = []

OWASP_CHECKS = [
    ("BOLA (객체 권한)", "다른 user 의 ID 로 접근 가능?"),
    ("인증 부재 / 약한 인증", "토큰 검증 누락"),
    ("과도한 데이터 노출", "전체 user 객체 그대로 반환?"),
    ("Rate limiting", "초당 요청 제한 없음"),
    ("SQL/NoSQL injection", "쿼리에 사용자 입력 직접 삽입?"),
    ("CORS 과다 허용", "Access-Control-Allow-Origin: *"),
    ("Mass assignment", "req.body 통째로 모델에 주입"),
    ("로깅에 비밀 노출", "JWT/패스워드 로그"),
]


def _gen_cot_security(rng: random.Random):
    domain = rng.choice(DOMAINS_WITH_CONTEXT)
    user_msg = rng.choice([
        f"이 {domain['name']} API 안전한가? 점검해줘",
        f"{domain['name']} 보안 리뷰 부탁",
        f"OWASP 기준으로 우리 API 봐줘",
    ])

    sample_checks = rng.sample(OWASP_CHECKS, 5)
    checks_text = "\n".join(
        f"{i+1}. **{name}**: {q}" for i, (name, q) in enumerate(sample_checks)
    )
    reasoning_first = (
        f"API 보안은 OWASP API Top 10 기준으로 우선순위 점검합니다.\n\n"
        f"{checks_text}\n\n"
        f"이유: 1번 BOLA 가 실무에서 가장 흔한 취약점입니다.\n"
        f"가능한 함정: 인증만 보고 권한 점검 빠뜨리면 BOLA 그대로 노출.\n"
        f"먼저 라우트 코드를 봅니다."
    )
    reasoning_first = _sprinkle_identity(reasoning_first, rng)
    first_msg = reasoning_first + "\n\n" + tc("read_file", {"path": domain["typical_file"]})

    reasoning_second = (
        f"코드 점검 결과:\n"
        f"- 인증은 있으나 권한 체크가 누락 → {sample_checks[0][0]} 위험\n"
        f"- {sample_checks[2][0]} 가능성도 보입니다.\n"
        f"이유: req.params.id 를 그대로 사용하고 ownership 검증 없음.\n"
        f"우선순위: BOLA 부터 패치."
    )
    second_msg = reasoning_second + "\n\n" + tc(
        "edit_file",
        {
            "path": domain["typical_file"],
            "old": domain["typical_content"][:30],
            "new": "// SECURITY: ownership check\n" + domain["typical_content"][:30],
        },
    )

    final = (
        f"보안 패치 완료. 정리:\n"
        f"- 수정: ownership 체크 추가 (BOLA 차단)\n"
        f"- 추가 권장: rate limiting (express-rate-limit / slowapi)\n"
        f"- 다음 단계: secret scanning (gitleaks) + dependency scan (osv-scanner)\n"
        f"- 함정: 운영 환경 변수에 secret 평문 저장하지 말 것"
    )

    return m([
        syss(),
        user(user_msg),
        assistant(first_msg),
        tool(domain["typical_content"]),
        assistant(second_msg),
        tool(f"Edit applied to {domain['typical_file']}: 1 replacement"),
        assistant(final),
    ])


_rng_sec = random.Random(2026_04)
for _ in range(200):
    SCENARIO_COT_SECURITY.append(_gen_cot_security(_rng_sec))


# ============================================================
# CoT-5: 마이그레이션 (200)
# ============================================================

SCENARIO_COT_MIGRATION = []

MIGRATION_CASES = [
    {
        "from": "JavaScript", "to": "TypeScript",
        "probe_cmd": "find . -name '*.js' | wc -l",
        "probe_out": "342",
        "tip": "10K LOC 이상 → 점진적 (allowJs:true, 폴더 단위 단계 전환)",
    },
    {
        "from": "Vue 2", "to": "Vue 3",
        "probe_cmd": "grep -r 'Vue.extend' src | wc -l",
        "probe_out": "57",
        "tip": "Composition API 로 점진 → @vue/compat 브릿지 사용",
    },
    {
        "from": "Pages Router", "to": "App Router (Next.js)",
        "probe_cmd": "ls pages",
        "probe_out": "_app.tsx index.tsx api login.tsx",
        "tip": "병렬 실행 가능 → 새 라우트만 app/ 에 추가",
    },
    {
        "from": "REST", "to": "GraphQL",
        "probe_cmd": "ls src/routes",
        "probe_out": "users.ts orders.ts posts.ts",
        "tip": "Fragment-driven 화면이면 ROI 높음, 단순 CRUD 면 비용 ↑",
    },
    {
        "from": "Express", "to": "Fastify",
        "probe_cmd": "grep -r 'app.use' src | wc -l",
        "probe_out": "23",
        "tip": "미들웨어 적으면 1주 내, 많으면 호환 어댑터 도입",
    },
    {
        "from": "Mongoose", "to": "Prisma (Mongo)",
        "probe_cmd": "grep -r 'mongoose.model' src | wc -l",
        "probe_out": "18",
        "tip": "스키마 추출 자동화 부재 → 모델 단위로 단계 이전",
    },
    {
        "from": "Redux", "to": "Zustand",
        "probe_cmd": "grep -r 'createSlice' src | wc -l",
        "probe_out": "11",
        "tip": "slice 단위로 store 분리 → 동시 운영 가능",
    },
    {
        "from": "CSS Modules", "to": "Tailwind",
        "probe_cmd": "find src -name '*.module.css' | wc -l",
        "probe_out": "89",
        "tip": "AST 기반 자동 변환 어려움 → 페이지 단위 수동 (디자인 토큰 동기 필수)",
    },
    {
        "from": "Webpack", "to": "Vite",
        "probe_cmd": "cat webpack.config.js | wc -l",
        "probe_out": "210",
        "tip": "커스텀 loader 많으면 Vite 플러그인 매핑 검토 후 결정",
    },
    {
        "from": "Python 3.9", "to": "Python 3.12",
        "probe_cmd": "python --version",
        "probe_out": "Python 3.9.16",
        "tip": "deprecation 일괄 점검 (asyncio API 변경) + 의존성 lock 재생성",
    },
]


def _gen_cot_migration(rng: random.Random):
    case = rng.choice(MIGRATION_CASES)
    user_msg = rng.choice([
        f"{case['from']} 에서 {case['to']} 로 마이그레이션",
        f"{case['from']} → {case['to']} 옮기려는데 어떻게 시작?",
        f"{case['to']} 로 갈아타려는데 평가해줘",
    ])

    reasoning_first = (
        f"{case['from']} → {case['to']} 마이그레이션은 점진적 vs 한방이 핵심 결정입니다.\n\n"
        f"평가 항목 우선순위:\n"
        f"1. 코드 규모 (10K LOC 이상이면 점진 권장)\n"
        f"2. 테스트 커버리지 (낮으면 위험 ↑, 회귀 잡기 어려움)\n"
        f"3. 팀의 {case['to']} 경험\n"
        f"4. 의존성 호환성\n\n"
        f"이유: 한방 마이그레이션은 회귀 비용이 폭증합니다.\n"
        f"가능한 함정: 일정 압박으로 한방으로 가다 롤백 못하는 케이스 다수.\n"
        f"먼저 규모부터 측정합니다."
    )
    reasoning_first = _sprinkle_identity(reasoning_first, rng)
    first_msg = reasoning_first + "\n\n" + tc("run_command", {"command": case["probe_cmd"]})

    reasoning_second = (
        f"규모 측정 결과: `{case['probe_out']}`.\n"
        f"이를 바탕으로 결론: **점진적 마이그레이션 권장**.\n"
        f"이유: 한방 시 회귀 위험 > 점진 시 일시적 이중 유지 비용.\n"
        f"전략: {case['tip']}"
    )
    second_msg = reasoning_second + "\n\n" + tc(
        "write_file",
        {"path": "MIGRATION_PLAN.md", "content": f"# {case['from']} → {case['to']}\n\n{case['tip']}\n"},
    )

    final = (
        f"마이그레이션 계획서 작성 완료. 다음 액션:\n"
        f"- 1주차: 빌드 파이프라인 dual 운영 셋업\n"
        f"- 2~4주차: 모듈 단위 이전 + 회귀 테스트\n"
        f"- 5주차: legacy 제거\n"
        f"- 함정: 모든 코드 한 번에 손대면 코드리뷰 폭주 → 모듈별 PR 분리"
    )

    return m([
        syss(),
        user(user_msg),
        assistant(first_msg),
        tool(case["probe_out"]),
        assistant(second_msg),
        tool("File written: MIGRATION_PLAN.md"),
        assistant(final),
    ])


_rng_mig = random.Random(2026_05)
for _ in range(200):
    SCENARIO_COT_MIGRATION.append(_gen_cot_migration(_rng_mig))


# ============================================================
# CoT-6: 트레이드오프 분석 (200)
# ============================================================

SCENARIO_COT_TRADEOFF = []

TRADEOFFS = [
    {
        "a": "Redis", "b": "Memcached",
        "a_pros": ["데이터 구조 (List/Set/Sorted Set/Hash)", "pub/sub", "영속화 옵션"],
        "b_pros": ["멀티스레드 (CPU 활용 ↑)", "단순 KV 만 — 가벼움", "작은 객체 빠름"],
    },
    {
        "a": "PostgreSQL", "b": "MySQL",
        "a_pros": ["JSONB + 표현식 인덱스", "고급 SQL (CTE/Window)", "확장 풍부"],
        "b_pros": ["복제/운영 도구 풍부", "관리형 옵션 다수", "단순 워크로드 빠름"],
    },
    {
        "a": "REST", "b": "GraphQL",
        "a_pros": ["캐시 인프라 성숙", "단순 / 학습 비용 낮음", "HTTP 시맨틱 활용"],
        "b_pros": ["over-fetch 제거", "타입 시스템 통합", "fragment 재사용"],
    },
    {
        "a": "Server Components", "b": "Client Components",
        "a_pros": ["번들 0", "DB 직접 접근", "SEO 친화"],
        "b_pros": ["인터랙션 자유", "브라우저 API 사용", "stateful UI"],
    },
    {
        "a": "Microservices", "b": "Monolith",
        "a_pros": ["독립 배포", "팀 분리 가능", "기술 다양성"],
        "b_pros": ["운영 단순", "트랜잭션 강함", "초기 비용 낮음"],
    },
    {
        "a": "SSR", "b": "SSG",
        "a_pros": ["실시간 데이터", "사용자별 콘텐츠", "동적 라우팅"],
        "b_pros": ["CDN 캐시", "응답 빠름", "비용 저렴"],
    },
    {
        "a": "Tailwind", "b": "CSS-in-JS",
        "a_pros": ["빌드 산출물 작음", "디자인 토큰 일관", "런타임 비용 0"],
        "b_pros": ["JS 변수와 결합", "동적 스타일", "컴포넌트 캡슐화"],
    },
    {
        "a": "TanStack Query", "b": "SWR",
        "a_pros": ["mutation 우수", "devtools 강력", "옵션 풍부"],
        "b_pros": ["가벼움", "API 단순", "Vercel 통합"],
    },
    {
        "a": "Prisma", "b": "Drizzle",
        "a_pros": ["성숙한 마이그레이션", "타입 안정 강함", "도구 풍부"],
        "b_pros": ["SQL-first", "엣지 런타임 친화", "오버헤드 ↓"],
    },
    {
        "a": "JWT", "b": "Session 쿠키",
        "a_pros": ["stateless", "마이크로서비스 친화", "모바일 친화"],
        "b_pros": ["revoke 즉시", "XSS 위험 ↓ (httpOnly)", "토큰 크기 작음"],
    },
    {
        "a": "Kafka", "b": "RabbitMQ",
        "a_pros": ["스트림 재처리", "고처리량", "장기 보관"],
        "b_pros": ["라우팅 유연", "운영 단순", "낮은 지연"],
    },
    {
        "a": "WebSocket", "b": "SSE",
        "a_pros": ["양방향", "바이너리 지원", "낮은 지연"],
        "b_pros": ["HTTP 그대로", "재연결 자동", "프록시 친화"],
    },
]


def _gen_cot_tradeoff(rng: random.Random):
    t = rng.choice(TRADEOFFS)
    user_msg = rng.choice([
        f"{t['a']} vs {t['b']} ?",
        f"{t['a']} 와 {t['b']} 중에 뭐가 나아?",
        f"{t['a']} {t['b']} 비교해줘",
    ])

    a_pros_text = "\n".join(f"- {p}" for p in t["a_pros"])
    b_pros_text = "\n".join(f"- {p}" for p in t["b_pros"])

    reasoning_first = (
        f"{t['a']} vs {t['b']} 는 사용 패턴에 따라 답이 달라집니다. 트레이드오프 표를 정리합니다.\n\n"
        f"### {t['a']} 우위\n{a_pros_text}\n\n"
        f"### {t['b']} 우위\n{b_pros_text}\n\n"
        f"이유: 한쪽이 절대 우위인 경우는 드물고 워크로드가 결정합니다.\n"
        f"가능한 함정: 인터넷 인기 순위로 고르면 우리 워크로드와 어긋나기 쉬움.\n"
        f"질문: 현재 프로젝트의 사용 패턴 먼저 확인합니다."
    )
    reasoning_first = _sprinkle_identity(reasoning_first, rng)
    first_msg = reasoning_first + "\n\n" + tc("list_directory", {"path": "src"})

    reasoning_second = (
        f"디렉토리 구조를 보니 사용 패턴이 보입니다.\n"
        f"따라서 추천: **{t['a']}** (현재 워크로드 기준).\n"
        f"이유: {t['a_pros'][0]} 가 우리 케이스에 직결됩니다.\n"
        f"단, {t['b_pros'][0]} 가 결정적이 되면 재평가 필요."
    )
    second_msg = reasoning_second + "\n\n" + tc("read_file", {"path": "package.json"})

    final = (
        f"결론 정리:\n"
        f"- 추천: {t['a']}\n"
        f"- 이유 1: {t['a_pros'][0]}\n"
        f"- 이유 2: {t['a_pros'][1]}\n"
        f"- 함정: {t['b']} 로 가야 하는 케이스 = {t['b_pros'][0]} 가 핵심 요구사항일 때\n"
        f"- 다음 단계: 작은 PoC 로 가정 검증"
    )

    return m([
        syss(),
        user(user_msg),
        assistant(first_msg),
        tool("src/\n  components/\n  pages/\n  utils/\n"),
        assistant(second_msg),
        tool('{ "dependencies": {} }'),
        assistant(final),
    ])


_rng_tradeoff = random.Random(2026_06)
for _ in range(200):
    SCENARIO_COT_TRADEOFF.append(_gen_cot_tradeoff(_rng_tradeoff))


# ============================================================
# CoT-7: 자기 평가 + 다음 단계 (300)
# ============================================================

SCENARIO_COT_REFLECT = []

REFLECT_TASKS = [
    {
        "task": "5개 API 함수 중복 로직 정리",
        "probe": ("search_code", {"pattern": "fetch", "path": "src/api"}),
        "probe_out": "src/api/users.ts:12: const r = await fetch(...)\nsrc/api/orders.ts:9: const r = await fetch(...)\nsrc/api/posts.ts:14: const r = await fetch(...)\nsrc/api/feed.ts:8: const r = await fetch(...)\nsrc/api/admin.ts:22: const r = await fetch(...)\n",
        "find_a": "5개 함수 중 3개가 거의 동일한 fetch + json 패턴",
        "find_b": "2개는 헤더/에러 처리가 달라 통합 시 위험",
        "plan_a": "공통 부분 → utils/api.ts 의 apiFetch() 로 추출",
        "plan_b": "다른 패턴 2개는 그대로 (over-engineering 방지)",
        "next_action": ("write_file", {"path": "src/utils/api.ts", "content": "export async function apiFetch<T>(url: string): Promise<T> {\n  const r = await fetch(url);\n  if (!r.ok) throw new Error(String(r.status));\n  return r.json();\n}\n"}),
    },
    {
        "task": "테스트 누락 영역 점검",
        "probe": ("run_command", {"command": "npm test -- --coverage"}),
        "probe_out": "Statements: 64% / Branches: 48% / Functions: 71%\nUncovered: src/utils/auth.ts (12%), src/api/payments.ts (28%)\n",
        "find_a": "auth.ts 와 payments.ts 가 핵심인데 커버리지 매우 낮음",
        "find_b": "전체 평균은 60%대로 나쁘지 않으나 위험 영역에 편중",
        "plan_a": "auth/payments 우선 90% 목표",
        "plan_b": "나머지는 변경 시점에 점진",
        "next_action": ("write_file", {"path": "src/utils/auth.test.ts", "content": "import { test, expect } from 'vitest';\nimport { verify } from './auth';\n\ntest('verify rejects expired', () => { expect(verify('expired')).toBe(false); });\n"}),
    },
    {
        "task": "의존성 노후도 점검",
        "probe": ("run_command", {"command": "npm outdated"}),
        "probe_out": "Package    Current  Latest\nreact      18.0.0   18.3.0\nnext       13.4.0   14.1.0\ntypescript 5.0.0    5.4.0\n",
        "find_a": "next 13 → 14 는 메이저, App Router 안정화 포함",
        "find_b": "react/typescript 는 마이너 — 안전",
        "plan_a": "react/typescript 먼저 패치",
        "plan_b": "next 14 는 별도 PR + 회귀 테스트 후",
        "next_action": ("edit_file", {"path": "package.json", "old": '"react": "18.0.0"', "new": '"react": "18.3.0"'}),
    },
    {
        "task": "큰 파일 식별",
        "probe": ("run_command", {"command": "find src -name '*.ts' -size +500c | head"}),
        "probe_out": "src/components/Dashboard.tsx (1240 lines)\nsrc/utils/index.ts (890 lines)\n",
        "find_a": "Dashboard.tsx 1240 줄 — 분리 후보",
        "find_b": "utils/index.ts 가 잡탕 export — 책임 분리 필요",
        "plan_a": "Dashboard 를 도메인별 5개 컴포넌트로 분할",
        "plan_b": "utils/index.ts 는 폴더로 변환 (utils/date.ts, utils/format.ts ...)",
        "next_action": ("read_file", {"path": "src/components/Dashboard.tsx"}),
    },
    {
        "task": "에러 처리 일관성 점검",
        "probe": ("search_code", {"pattern": "try", "path": "src"}),
        "probe_out": "src/api/users.ts: try-catch 있음 (re-throw)\nsrc/api/orders.ts: try-catch 없음\nsrc/api/posts.ts: try-catch 있음 (swallow)\n",
        "find_a": "3개 파일에서 처리 정책이 다 다름",
        "find_b": "swallow 패턴은 디버깅 어렵게 함 — 가장 위험",
        "plan_a": "전역 errorHandler 미들웨어로 통일",
        "plan_b": "swallow 는 즉시 제거 (silent failure 함정)",
        "next_action": ("write_file", {"path": "src/middleware/errorHandler.ts", "content": "export function errorHandler(err: Error, req, res, next) {\n  console.error(err);\n  res.status(500).json({ error: err.message });\n}\n"}),
    },
    {
        "task": "리팩토링 영향 평가",
        "probe": ("search_code", {"pattern": "useUser", "path": "src"}),
        "probe_out": "src/hooks/useUser.ts: 정의\nsrc/pages/Profile.tsx: 사용\nsrc/components/Header.tsx: 사용\nsrc/pages/Settings.tsx: 사용\n",
        "find_a": "useUser 훅이 3곳에서 사용됨",
        "find_b": "변경 시 영향 범위는 좁음 — 안전한 리팩토링 후보",
        "plan_a": "시그니처 유지하면서 내부만 react-query 로 교체",
        "plan_b": "테스트 추가 후 진행",
        "next_action": ("read_file", {"path": "src/hooks/useUser.ts"}),
    },
    {
        "task": "환경변수 누락 점검",
        "probe": ("read_file", {"path": ".env.example"}),
        "probe_out": "DATABASE_URL=\nJWT_SECRET=\nSTRIPE_KEY=\nSENTRY_DSN=\n",
        "find_a": "4개 변수 중 2개만 .env 에 실제 값 있음",
        "find_b": "STRIPE_KEY 누락 시 결제 실패",
        "plan_a": "런타임 부팅 시 zod 로 env 검증",
        "plan_b": ".env.example 를 source of truth 로 유지",
        "next_action": ("write_file", {"path": "src/env.ts", "content": "import { z } from 'zod';\nexport const env = z.object({\n  DATABASE_URL: z.string().url(),\n  JWT_SECRET: z.string().min(32),\n  STRIPE_KEY: z.string().startsWith('sk_'),\n  SENTRY_DSN: z.string().url(),\n}).parse(process.env);\n"}),
    },
    {
        "task": "빌드 시간 분석",
        "probe": ("run_command", {"command": "npm run build -- --profile"}),
        "probe_out": "Total: 92s\n  TS check: 41s\n  Webpack: 38s\n  Asset: 13s\n",
        "find_a": "TS check 가 41초 — 가장 큰 비용",
        "find_b": "Webpack 38초도 큼 → Vite 도 검토 가능",
        "plan_a": "tsc --noEmit 분리 + project references 도입",
        "plan_b": "Vite 마이그레이션은 별도 평가",
        "next_action": ("read_file", {"path": "tsconfig.json"}),
    },
]


def _gen_cot_reflect(rng: random.Random):
    case = rng.choice(REFLECT_TASKS)
    user_msg = rng.choice([
        f"{case['task']} 좀 봐줘",
        f"{case['task']}.",
        f"코드베이스에서 {case['task']} 해줄래?",
    ])

    intro = (
        f"먼저 현재 상태를 객관적으로 측정합니다.\n"
        f"이유: 가정만으로 리팩토링하면 over-engineering 위험.\n"
        f"우선순위: 데이터 → 분석 → 행동."
    )
    intro = _sprinkle_identity(intro, rng)
    first_msg = intro + "\n\n" + tc(case["probe"][0], case["probe"][1])

    reflect = (
        f"확인 완료. 발견:\n"
        f"- {case['find_a']}\n"
        f"- {case['find_b']}\n\n"
        f"리팩토링 plan:\n"
        f"- {case['plan_a']}\n"
        f"- {case['plan_b']}\n\n"
        f"이유: 일반적으로 변경 비용이 가장 낮은 부분부터 손대는 게 ROI 높음.\n"
        f"가능한 함정: 두 영역을 한 PR 에 묶으면 리뷰 어려움 → 분리.\n"
        f"다음 행동: 첫 번째 plan 즉시 실행."
    )
    second_msg = reflect + "\n\n" + tc(case["next_action"][0], case["next_action"][1])

    final = (
        f"실행 완료. 자기 평가:\n"
        f"- 잘한 점: 측정 → 분석 → 행동 순서 유지, 작은 단위 PR\n"
        f"- 함정 회피: 통합 위험 있는 2번 plan 은 일부러 안 건드림\n"
        f"- 다음 단계: 회귀 테스트 추가 후 두 번째 plan 검토\n"
        f"- 우선순위: 측정 가능한 효과 (커버리지/응답시간) 부터 추적"
    )

    return m([
        syss(),
        user(user_msg),
        assistant(first_msg),
        tool(case["probe_out"]),
        assistant(second_msg),
        tool("OK"),
        assistant(final),
    ])


_rng_reflect = random.Random(2026_07)
for _ in range(300):
    SCENARIO_COT_REFLECT.append(_gen_cot_reflect(_rng_reflect))


# ============================================================
# 검증
# ============================================================

assert len(SCENARIO_COT_DEBUG) == 300, f"DEBUG: {len(SCENARIO_COT_DEBUG)}"
assert len(SCENARIO_COT_ARCH) == 300, f"ARCH: {len(SCENARIO_COT_ARCH)}"
assert len(SCENARIO_COT_PERF) == 200, f"PERF: {len(SCENARIO_COT_PERF)}"
assert len(SCENARIO_COT_SECURITY) == 200, f"SEC: {len(SCENARIO_COT_SECURITY)}"
assert len(SCENARIO_COT_MIGRATION) == 200, f"MIG: {len(SCENARIO_COT_MIGRATION)}"
assert len(SCENARIO_COT_TRADEOFF) == 200, f"TRADE: {len(SCENARIO_COT_TRADEOFF)}"
assert len(SCENARIO_COT_REFLECT) == 300, f"REFLECT: {len(SCENARIO_COT_REFLECT)}"


def _verify_keywords(samples, label):
    """모든 샘플의 첫 assistant 메시지에 추론 키워드가 2개 이상 들어있는지"""
    bad = 0
    for s in samples:
        first_assistant = next(
            (msg["content"] for msg in s["messages"] if msg["role"] == "assistant"), ""
        )
        if not _has_two_keywords(first_assistant):
            bad += 1
    if bad:
        logger.warning(f"  [{label}] 키워드 부족 샘플: {bad}/{len(samples)}")


_verify_keywords(SCENARIO_COT_DEBUG, "DEBUG")
_verify_keywords(SCENARIO_COT_ARCH, "ARCH")
_verify_keywords(SCENARIO_COT_PERF, "PERF")
_verify_keywords(SCENARIO_COT_SECURITY, "SEC")
_verify_keywords(SCENARIO_COT_MIGRATION, "MIG")
_verify_keywords(SCENARIO_COT_TRADEOFF, "TRADE")
_verify_keywords(SCENARIO_COT_REFLECT, "REFLECT")


# ============================================================
# 출력
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/cot_v4.jsonl")
    args = parser.parse_args()

    all_data = (
        SCENARIO_COT_DEBUG +
        SCENARIO_COT_ARCH +
        SCENARIO_COT_PERF +
        SCENARIO_COT_SECURITY +
        SCENARIO_COT_MIGRATION +
        SCENARIO_COT_TRADEOFF +
        SCENARIO_COT_REFLECT
    )
    assert len(all_data) == 1500, f"total: {len(all_data)}"

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # 통계: 정체성 키워드 포함 비율
    ident_count = 0
    for item in all_data:
        text = json.dumps(item, ensure_ascii=False)
        if "화랑" in text or "퍼시스모어" in text:
            ident_count += 1
    ident_ratio = 100.0 * ident_count / len(all_data)

    # 통계: 키워드별 분포
    kw_dist = {kw: 0 for kw in REASONING_KEYWORDS}
    for item in all_data:
        text = json.dumps(item, ensure_ascii=False)
        for kw in REASONING_KEYWORDS:
            if kw in text:
                kw_dist[kw] += 1

    logger.info(f"[OK] {len(all_data)} 샘플 → {args.output}")
    logger.info(f"  CoT-1 디버깅:       {len(SCENARIO_COT_DEBUG)}")
    logger.info(f"  CoT-2 아키텍처:     {len(SCENARIO_COT_ARCH)}")
    logger.info(f"  CoT-3 성능:         {len(SCENARIO_COT_PERF)}")
    logger.info(f"  CoT-4 보안:         {len(SCENARIO_COT_SECURITY)}")
    logger.info(f"  CoT-5 마이그레이션: {len(SCENARIO_COT_MIGRATION)}")
    logger.info(f"  CoT-6 트레이드오프: {len(SCENARIO_COT_TRADEOFF)}")
    logger.info(f"  CoT-7 자기평가:     {len(SCENARIO_COT_REFLECT)}")
    logger.info(f"  정체성 키워드 포함: {ident_count}/{len(all_data)} ({ident_ratio:.1f}%)")
    logger.info(f"  추론 키워드 분포 (top):")
    for kw, c in sorted(kw_dist.items(), key=lambda x: -x[1])[:8]:
        logger.info(f"    {kw}: {c}")
