"""화랑 AI Tool Calling 학습 데이터 (파일시스템 + 코드검색)"""
import json, os, logging, argparse
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TOOLS_DESC = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 코딩 어시스턴트입니다.
사용 가능한 도구가 있을 때 <tool_call> 태그로 호출합니다.

사용 가능한 도구:
- read_file(path: str): 파일 내용 읽기
- write_file(path: str, content: str): 파일 쓰기
- list_directory(path: str): 디렉토리 목록
- search_code(pattern: str, path: str): 코드 검색 (grep)
- glob_files(pattern: str): 파일명 패턴 검색
- edit_file(path: str, old: str, new: str): 파일 수정
- run_command(command: str): 쉘 명령 실행
- get_diagnostics(): 에디터 에러/경고 확인

도구 호출 형식:
<tool_call>
{"name": "도구명", "arguments": {"인자": "값"}}
</tool_call>

도구 결과 후에는 결과를 바탕으로 응답합니다. 도구가 불필요하면 직접 답변합니다."""

def m(messages):
    return {"messages": messages}

def sys():
    return {"role": "system", "content": TOOLS_DESC}

def user(c):
    return {"role": "user", "content": c}

def assistant(c):
    return {"role": "assistant", "content": c}

def tool(c):
    return {"role": "tool", "content": c}

DATA = [
    # ============================================================
    # 파일시스템 (15건)
    # ============================================================

    # 1. 단일 파일 읽기
    m([
        sys(),
        user("package.json 읽어줘"),
        assistant('''package.json 파일을 확인해드리겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "package.json"}}
</tool_call>'''),
        tool('''{
  "name": "hwarang-web",
  "version": "0.3.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "14.2.0",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "@prisma/client": "5.15.0"
  },
  "devDependencies": {
    "typescript": "5.4.5",
    "prisma": "5.15.0"
  }
}'''),
        assistant('''package.json 내용을 확인했습니다.

**프로젝트 정보:**
- 이름: `hwarang-web`
- 버전: 0.3.0
- 프레임워크: Next.js 14.2.0 + React 18.3.1
- DB: Prisma 5.15.0 (@prisma/client 포함)
- TypeScript 5.4.5 사용

**스크립트:**
- `npm run dev` — 개발 서버
- `npm run build` — 프로덕션 빌드
- `npm start` — 프로덕션 서버
- `npm run lint` — ESLint 검사

Next.js 기반의 화랑 웹 프로젝트이며, Prisma ORM으로 DB를 다루고 있네요.'''),
    ]),

    # 2. 파일 쓰기
    m([
        sys(),
        user("hello.py 파일 만들어 'Hello' 출력하게"),
        assistant('''간단한 Hello 출력 스크립트를 만들어드리겠습니다.

<tool_call>
{"name": "write_file", "arguments": {"path": "hello.py", "content": "print(\\"Hello\\")\\n"}}
</tool_call>'''),
        tool("File written: hello.py (14 bytes)"),
        assistant('''`hello.py` 파일을 생성했습니다.

```python
print("Hello")
```

실행하려면:
```bash
python hello.py
```

출력: `Hello`'''),
    ]),

    # 3. 디렉토리 목록
    m([
        sys(),
        user("src 폴더 뭐 있어?"),
        assistant('''src 폴더 내용을 확인해드리겠습니다.

<tool_call>
{"name": "list_directory", "arguments": {"path": "src"}}
</tool_call>'''),
        tool('''app/
components/
hooks/
lib/
styles/
types/
middleware.ts
config.ts'''),
        assistant('''`src` 폴더 구조입니다:

**디렉토리 (6개):**
- `app/` — Next.js App Router 라우트
- `components/` — 재사용 컴포넌트
- `hooks/` — 커스텀 React 훅
- `lib/` — 유틸리티/클라이언트 (API, DB 등)
- `styles/` — CSS/Tailwind 스타일
- `types/` — TypeScript 타입 정의

**파일 (2개):**
- `middleware.ts` — Next.js 미들웨어 (인증 등)
- `config.ts` — 전역 설정

전형적인 Next.js 14 App Router 구조네요. 특정 폴더 내부를 더 보고 싶으시면 말씀해주세요.'''),
    ]),

    # 4. 파일 수정 (edit_file)
    m([
        sys(),
        user("config.ts에서 port 3000을 8000으로 바꿔줘"),
        assistant('''config.ts 파일의 port 값을 수정하겠습니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": "config.ts", "old": "port: 3000", "new": "port: 8000"}}
</tool_call>'''),
        tool("Edit applied to config.ts: 1 replacement"),
        assistant('''`config.ts`의 포트를 3000 → 8000으로 변경했습니다.

```diff
- port: 3000
+ port: 8000
```

변경 사항이 1건 적용되었습니다. 개발 서버를 재시작하시면 `http://localhost:8000`에서 접근 가능합니다.

**참고:** Next.js에서는 `next dev -p 8000` 또는 환경변수 `PORT=8000`도 함께 확인하시면 좋습니다.'''),
    ]),

    # 5. 여러 파일 읽기 비교
    m([
        sys(),
        user("config.ts랑 package.json 비교해줘"),
        assistant('''두 파일을 각각 읽어서 비교해드리겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "config.ts"}}
</tool_call>'''),
        tool('''export const config = {
  port: 8000,
  apiUrl: "http://localhost:8000/api",
  version: "0.2.0",
  dbUrl: process.env.DATABASE_URL
};'''),
        assistant('''config.ts를 확인했습니다. 이어서 package.json도 읽겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "package.json"}}
</tool_call>'''),
        tool('''{
  "name": "hwarang-web",
  "version": "0.3.0",
  "scripts": { "dev": "next dev" },
  "dependencies": { "next": "14.2.0" }
}'''),
        assistant('''두 파일을 비교한 결과입니다.

**버전 불일치 발견!**
| 파일 | 버전 |
|---|---|
| package.json | `0.3.0` |
| config.ts | `0.2.0` |

**권장 조치:** `config.ts`의 version을 `0.3.0`으로 맞추거나, package.json에서 동적으로 import 하는 게 좋습니다.

```ts
import pkg from "../package.json";
export const config = {
  version: pkg.version,  // 항상 동기화
  // ...
};
```

이렇게 하면 한 곳만 관리해도 되어서 누락 위험이 줄어듭니다.'''),
    ]),

    # 6. 디렉토리 → 파일 읽기 체인
    m([
        sys(),
        user("src 폴더 훑어보고 첫 파일 읽어봐"),
        assistant('''먼저 src 폴더 구조를 확인하겠습니다.

<tool_call>
{"name": "list_directory", "arguments": {"path": "src"}}
</tool_call>'''),
        tool('''config.ts
middleware.ts
app/
components/'''),
        assistant('''첫 번째 파일인 `config.ts`를 읽어보겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/config.ts"}}
</tool_call>'''),
        tool('''export const APP_NAME = "화랑 AI";
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
export const MAX_TOKENS = 4096;'''),
        assistant('''`src/config.ts`의 내용입니다.

**전역 상수 3개:**
- `APP_NAME` — "화랑 AI"
- `API_BASE` — 환경변수 `NEXT_PUBLIC_API_BASE` 우선, 기본값 `http://localhost:8000`
- `MAX_TOKENS` — 4096

깔끔한 설정 상수 파일이며, API 엔드포인트는 환경별로 분리되어 있네요. 다음 파일을 볼까요?'''),
    ]),

    # 7. glob 검색
    m([
        sys(),
        user("*.test.ts 파일 다 찾아줘"),
        assistant('''프로젝트 전체에서 테스트 파일을 찾아보겠습니다.

<tool_call>
{"name": "glob_files", "arguments": {"pattern": "**/*.test.ts"}}
</tool_call>'''),
        tool('''src/lib/auth.test.ts
src/lib/db.test.ts
src/hooks/useAuth.test.ts
src/components/Button.test.ts
tests/integration/api.test.ts'''),
        assistant('''`*.test.ts` 파일 **5개**를 찾았습니다.

**단위 테스트 (4개):**
- `src/lib/auth.test.ts` — 인증 라이브러리
- `src/lib/db.test.ts` — DB 유틸
- `src/hooks/useAuth.test.ts` — 인증 훅
- `src/components/Button.test.ts` — 버튼 컴포넌트

**통합 테스트 (1개):**
- `tests/integration/api.test.ts`

실행: `npm test` 또는 특정 파일만 `npx vitest src/lib/auth.test.ts` — 특정 파일 내용이 궁금하시면 말씀해주세요.'''),
    ]),

    # 8. 존재 확인 후 수정 (list → edit)
    m([
        sys(),
        user(".env 있으면 API_KEY 추가해줘"),
        assistant('''먼저 프로젝트 루트에 .env 파일이 있는지 확인하겠습니다.

<tool_call>
{"name": "list_directory", "arguments": {"path": "."}}
</tool_call>'''),
        tool('''.env
.env.example
.gitignore
package.json
next.config.js
src/'''),
        assistant('''`.env` 파일이 존재합니다. 현재 내용을 확인 후 API_KEY를 추가하겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": ".env"}}
</tool_call>'''),
        tool('''DATABASE_URL=postgresql://user:pass@localhost:5432/hwarang
NEXTAUTH_SECRET=dev_secret
NEXTAUTH_URL=http://localhost:3000'''),
        assistant('''API_KEY가 없어서 파일 끝에 추가하겠습니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": ".env", "old": "NEXTAUTH_URL=http://localhost:3000", "new": "NEXTAUTH_URL=http://localhost:3000\\nAPI_KEY=replace_me_with_real_key"}}
</tool_call>'''),
        tool("Edit applied to .env: 1 replacement"),
        assistant('''`.env`에 `API_KEY=replace_me_with_real_key` 를 추가했습니다.

**다음 작업:**
1. `replace_me_with_real_key` 를 실제 키 값으로 교체
2. `.gitignore`에 `.env`가 포함되어 있는지 확인 (커밋 방지)
3. `.env.example`에도 `API_KEY=` 만 추가해서 팀원에게 안내

**주의:** API 키는 절대 Git에 커밋하지 마세요.'''),
    ]),

    # 9. 새 파일 만들고 확인 (write → read)
    m([
        sys(),
        user("src/lib/logger.ts 간단한 로거 만들어주고 확인까지 해줘"),
        assistant('''간단한 로거 파일을 생성하겠습니다.

<tool_call>
{"name": "write_file", "arguments": {"path": "src/lib/logger.ts", "content": "export const logger = {\\n  info: (msg: string) => console.log(`[INFO] ${new Date().toISOString()} ${msg}`),\\n  warn: (msg: string) => console.warn(`[WARN] ${new Date().toISOString()} ${msg}`),\\n  error: (msg: string, err?: unknown) => console.error(`[ERROR] ${new Date().toISOString()} ${msg}`, err),\\n};\\n"}}
</tool_call>'''),
        tool("File written: src/lib/logger.ts (312 bytes)"),
        assistant('''작성한 내용을 다시 읽어 확인하겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/lib/logger.ts"}}
</tool_call>'''),
        tool('''export const logger = {
  info: (msg: string) => console.log(`[INFO] ${new Date().toISOString()} ${msg}`),
  warn: (msg: string) => console.warn(`[WARN] ${new Date().toISOString()} ${msg}`),
  error: (msg: string, err?: unknown) => console.error(`[ERROR] ${new Date().toISOString()} ${msg}`, err),
};'''),
        assistant('''`src/lib/logger.ts` 생성 및 확인 완료했습니다.

**사용 예시:**
```ts
import { logger } from "@/lib/logger";

logger.info("사용자 로그인 시도");
logger.warn("토큰 곧 만료");
logger.error("DB 연결 실패", err);
```

ISO 타임스탬프가 자동으로 붙어서 프로덕션에서도 추적이 쉽습니다. 나중에 파일 로깅이 필요하면 `pino`나 `winston`으로 교체하시면 됩니다.'''),
    ]),

    # 10. 파일 삭제 후 목록 (run_command rm → list)
    m([
        sys(),
        user("tmp.txt 지우고 루트 목록 보여줘"),
        assistant('''tmp.txt를 삭제하고 루트를 다시 조회하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "rm -f tmp.txt"}}
</tool_call>'''),
        tool("(exit 0) removed 'tmp.txt'"),
        assistant('''삭제 완료. 이제 루트 목록을 확인하겠습니다.

<tool_call>
{"name": "list_directory", "arguments": {"path": "."}}
</tool_call>'''),
        tool('''.env
.gitignore
README.md
next.config.js
package.json
prisma/
src/
tsconfig.json'''),
        assistant('''`tmp.txt` 삭제 완료, 현재 루트에는 포함되어 있지 않습니다.

**현재 루트 (8개 항목):**
- 설정: `.env`, `.gitignore`, `tsconfig.json`, `next.config.js`
- 문서: `README.md`
- 메니페스트: `package.json`
- 디렉토리: `prisma/`, `src/`

깔끔하게 정리되었습니다.'''),
    ]),

    # 11. 경로 탐색
    m([
        sys(),
        user("modules/hwarang-web 어떤 구조야?"),
        assistant('''hwarang-web 모듈의 전체 구조를 살펴보겠습니다.

<tool_call>
{"name": "list_directory", "arguments": {"path": "modules/hwarang-web"}}
</tool_call>'''),
        tool('''.env.example
.gitignore
README.md
next.config.js
package.json
tsconfig.json
prisma/
public/
src/'''),
        assistant('''1단계 확인 후 src 내부도 보겠습니다.

<tool_call>
{"name": "list_directory", "arguments": {"path": "modules/hwarang-web/src"}}
</tool_call>'''),
        tool('''app/
components/
hooks/
lib/
types/
middleware.ts'''),
        assistant('''`modules/hwarang-web` 구조를 정리했습니다.

```
modules/hwarang-web/
├── .env.example       # 환경변수 템플릿
├── .gitignore
├── README.md
├── next.config.js     # Next.js 설정
├── package.json
├── tsconfig.json
├── prisma/            # DB 스키마
├── public/            # 정적 에셋
└── src/
    ├── app/           # App Router (페이지/API)
    ├── components/    # React 컴포넌트
    ├── hooks/         # 커스텀 훅
    ├── lib/           # 유틸/클라이언트
    ├── types/         # TS 타입
    └── middleware.ts  # 인증 미들웨어
```

표준적인 Next.js 14 App Router 구조입니다. Prisma를 사용하는 풀스택 웹 앱이네요.'''),
    ]),

    # 12. JSON 설정 파일 수정
    m([
        sys(),
        user("tsconfig.json에 strict: true 추가"),
        assistant('''먼저 tsconfig.json 현재 내용을 확인하겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "tsconfig.json"}}
</tool_call>'''),
        tool('''{
  "compilerOptions": {
    "target": "ES2022",
    "module": "esnext",
    "jsx": "preserve",
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*.ts", "src/**/*.tsx"]
}'''),
        assistant('''`strict: true` 옵션이 없네요. compilerOptions 블록에 추가하겠습니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": "tsconfig.json", "old": "\\"skipLibCheck\\": true", "new": "\\"skipLibCheck\\": true,\\n    \\"strict\\": true"}}
</tool_call>'''),
        tool("Edit applied to tsconfig.json: 1 replacement"),
        assistant('''`tsconfig.json`에 `"strict": true` 추가 완료.

```diff
  "skipLibCheck": true,
+ "strict": true
```

**영향:**
- `noImplicitAny`, `strictNullChecks`, `strictFunctionTypes` 등 모든 strict 계열 플래그가 켜집니다
- 기존 코드에서 타입 에러가 나올 수 있으니 `npx tsc --noEmit` 으로 먼저 확인해보세요

**권장:** 한 번에 다 고치기 어려우면 `strict: false`로 두고 개별 플래그(`strictNullChecks: true`)부터 점진 적용하는 방법도 있습니다.'''),
    ]),

    # 13. 대용량 파일 검색 (glob + read)
    m([
        sys(),
        user("스키마 파일 찾아서 모델 몇 개인지 세줘"),
        assistant('''Prisma 스키마 파일을 찾아보겠습니다.

<tool_call>
{"name": "glob_files", "arguments": {"pattern": "**/schema.prisma"}}
</tool_call>'''),
        tool("prisma/schema.prisma"),
        assistant('''스키마 파일을 찾았습니다. 내용을 읽어 모델 수를 세겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "prisma/schema.prisma"}}
</tool_call>'''),
        tool('''generator client { provider = "prisma-client-js" }
datasource db { provider = "postgresql"; url = env("DATABASE_URL") }

model User {
  id        String   @id @default(cuid())
  email     String   @unique
  sessions  Session[]
  apiKeys   ApiKey[]
}

model Session {
  id     String @id
  userId String
  user   User   @relation(fields: [userId], references: [id])
}

model ApiKey {
  id     String @id @default(cuid())
  userId String
  key    String @unique
  user   User   @relation(fields: [userId], references: [id])
}

model Project {
  id   String @id @default(cuid())
  name String
}

model Conversation {
  id     String @id @default(cuid())
  title  String
}'''),
        assistant('''`prisma/schema.prisma`에 **5개 모델**이 정의되어 있습니다.

| # | 모델 | 역할 |
|---|---|---|
| 1 | `User` | 사용자 계정 |
| 2 | `Session` | 로그인 세션 |
| 3 | `ApiKey` | API 키 관리 |
| 4 | `Project` | 프로젝트 |
| 5 | `Conversation` | 대화 기록 |

**관계:** User ↔ Session (1:N), User ↔ ApiKey (1:N) — Project와 Conversation은 아직 User와 연결되어 있지 않네요. 필요하시면 `userId` 관계를 추가하는 걸 추천드립니다.'''),
    ]),

    # 14. 여러 폴더 동시 조회
    m([
        sys(),
        user("components랑 hooks 폴더 각각 뭐 있는지 알려줘"),
        assistant('''먼저 components 폴더부터 조회하겠습니다.

<tool_call>
{"name": "list_directory", "arguments": {"path": "src/components"}}
</tool_call>'''),
        tool('''Button.tsx
Card.tsx
ChatBubble.tsx
CodeBlock.tsx
Sidebar.tsx
ThemeToggle.tsx'''),
        assistant('''이어서 hooks 폴더를 확인하겠습니다.

<tool_call>
{"name": "list_directory", "arguments": {"path": "src/hooks"}}
</tool_call>'''),
        tool('''useAuth.ts
useChat.ts
useDebounce.ts
useLocalStorage.ts
useTheme.ts'''),
        assistant('''두 폴더 내용을 정리했습니다.

**`src/components/` — 6개 컴포넌트**
- `Button.tsx` — 버튼
- `Card.tsx` — 카드 컨테이너
- `ChatBubble.tsx` — 채팅 말풍선
- `CodeBlock.tsx` — 코드 하이라이트 블록
- `Sidebar.tsx` — 사이드바
- `ThemeToggle.tsx` — 다크/라이트 전환

**`src/hooks/` — 5개 훅**
- `useAuth.ts` — 인증 상태
- `useChat.ts` — 채팅 로직
- `useDebounce.ts` — 디바운스
- `useLocalStorage.ts` — 로컬 스토리지 동기화
- `useTheme.ts` — 테마 훅

ChatBubble + useChat, ThemeToggle + useTheme 처럼 페어로 설계되어 있네요. 깔끔한 구조입니다.'''),
    ]),

    # 15. 파일 내용 기반 분석
    m([
        sys(),
        user("next.config.js 보고 SSR 설정 어떤지 분석해줘"),
        assistant('''next.config.js 내용을 확인해 SSR 관련 옵션을 분석하겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "next.config.js"}}
</tool_call>'''),
        tool('''/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "cdn.hwarang.ai" }
    ]
  },
  experimental: {
    serverActions: { bodySizeLimit: "2mb" }
  },
  async headers() {
    return [{
      source: "/(.*)",
      headers: [{ key: "X-Frame-Options", value: "DENY" }]
    }];
  }
};
module.exports = nextConfig;'''),
        assistant('''`next.config.js`를 분석한 결과입니다.

**SSR/렌더링 관련 설정:**

| 항목 | 값 | 의미 |
|---|---|---|
| `reactStrictMode` | `true` | 개발 시 이중 렌더링으로 부작용 감지 |
| `output` | `"standalone"` | 도커 배포 최적화 (node_modules 자동 포함) |
| `experimental.serverActions.bodySizeLimit` | `"2mb"` | 서버 액션 요청 본문 2MB 제한 |

**분석:**
1. **Standalone 출력** — Vercel이 아닌 자체 서버/컨테이너 배포를 가정한 설정입니다. Dockerfile에서 `.next/standalone`만 복사하면 됩니다
2. **Server Actions 활성** — Next.js 14 App Router의 서버 액션을 적극 사용하고 있으며, 파일 업로드나 대용량 폼 처리에 2MB까지 허용
3. **이미지 최적화** — `cdn.hwarang.ai` 도메인만 허용 — 외부 이미지 보안이 잘 잡혀있음
4. **X-Frame-Options: DENY** — 클릭재킹 방지, 프레임 임베드 불가

**추천 보완:**
- CSP(Content-Security-Policy) 헤더 추가
- `poweredByHeader: false` 로 `X-Powered-By` 숨기기'''),
    ]),

    # ============================================================
    # 코드 검색 (12건)
    # ============================================================

    # 16. 함수 정의 찾기
    m([
        sys(),
        user("calculateTotal 함수 어디 정의됐어?"),
        assistant('''프로젝트 내에서 함수 정의를 검색하겠습니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "function calculateTotal|const calculateTotal|export.*calculateTotal", "path": "src"}}
</tool_call>'''),
        tool('''src/lib/cart.ts:14:export function calculateTotal(items: CartItem[]): number {
src/lib/cart.ts:15:  return items.reduce((sum, it) => sum + it.price * it.qty, 0);
src/lib/cart.ts:16:}'''),
        assistant('''`calculateTotal` 함수는 **`src/lib/cart.ts:14`** 에 정의되어 있습니다.

```ts
// src/lib/cart.ts:14
export function calculateTotal(items: CartItem[]): number {
  return items.reduce((sum, it) => sum + it.price * it.qty, 0);
}
```

**기능:** 장바구니 아이템 배열에서 `price × qty` 의 합계를 계산합니다.

한 곳에서만 정의되어 있어 중복은 없네요. 이 함수를 어디서 호출하는지도 찾아드릴까요?'''),
    ]),

    # 17. 사용처 찾기
    m([
        sys(),
        user("useAuth 훅 어디서 쓰여?"),
        assistant('''useAuth 훅의 사용처를 검색하겠습니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "useAuth\\\\(", "path": "src"}}
</tool_call>'''),
        tool('''src/components/Sidebar.tsx:8:  const { user, logout } = useAuth();
src/app/dashboard/page.tsx:12:  const { user } = useAuth();
src/app/settings/page.tsx:6:  const { user, updateProfile } = useAuth();
src/components/ChatBubble.tsx:14:  const { user } = useAuth();
src/middleware.ts:22:  // useAuth() 는 클라이언트 전용 — 여기선 서버측 검증''') ,
        assistant('''`useAuth()` 훅은 **4곳**에서 실제로 호출되고 있습니다.

**사용처:**
| 파일 | 사용 값 |
|---|---|
| `src/components/Sidebar.tsx:8` | `user`, `logout` |
| `src/app/dashboard/page.tsx:12` | `user` |
| `src/app/settings/page.tsx:6` | `user`, `updateProfile` |
| `src/components/ChatBubble.tsx:14` | `user` |

**참고:** `src/middleware.ts:22` 는 주석에만 언급되어 있고 실제 호출 아님 (미들웨어는 서버사이드라 클라이언트 훅 사용 불가).

**노출되는 API:** `user`, `logout`, `updateProfile` — 훅이 이 세 가지를 반환한다고 추정할 수 있습니다. 정의부를 보시려면 말씀해주세요.'''),
    ]),

    # 18. TODO 찾기
    m([
        sys(),
        user("TODO 주석 다 찾아줘"),
        assistant('''프로젝트 전체에서 TODO 주석을 검색하겠습니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "TODO|FIXME|XXX", "path": "src"}}
</tool_call>'''),
        tool('''src/lib/auth.ts:42:// TODO: 리프레시 토큰 로직 추가
src/lib/db.ts:18:// FIXME: connection pool 크기 환경변수로
src/app/api/chat/route.ts:55:// TODO: 스트리밍 에러 핸들링
src/components/Sidebar.tsx:30:// XXX: 모바일에서 z-index 겹침 이슈
src/hooks/useChat.ts:67:// TODO: 재시도 로직 (지수 백오프)'''),
        assistant('''프로젝트 내 미완성 마커 **5건**을 찾았습니다.

**TODO (3건):**
1. `src/lib/auth.ts:42` — 리프레시 토큰 로직 추가
2. `src/app/api/chat/route.ts:55` — 스트리밍 에러 핸들링
3. `src/hooks/useChat.ts:67` — 재시도 로직 (지수 백오프)

**FIXME (1건):**
4. `src/lib/db.ts:18` — connection pool 크기 환경변수화

**XXX (1건):**
5. `src/components/Sidebar.tsx:30` — 모바일 z-index 겹침

**우선순위 제안:**
- **긴급**: `FIXME`(DB 풀) — 프로덕션 성능 직결
- **중요**: 인증 리프레시 토큰, API 에러 핸들링 — 안정성/UX
- **일반**: 재시도 로직, Sidebar z-index

이슈 트래커에 티켓화해서 관리하시면 좋겠네요.'''),
    ]),

    # 19. 에러 처리 패턴 찾기
    m([
        sys(),
        user("try catch 있는 파일 찾아"),
        assistant('''try/catch 블록이 있는 파일을 검색하겠습니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "try\\\\s*\\\\{", "path": "src"}}
</tool_call>'''),
        tool('''src/lib/auth.ts:20:  try {
src/lib/db.ts:35:  try {
src/app/api/chat/route.ts:12:  try {
src/app/api/upload/route.ts:18:  try {
src/hooks/useChat.ts:45:    try {'''),
        assistant('''try/catch가 사용된 **5개 파일**을 찾았습니다.

| 파일 | 라인 | 컨텍스트 추정 |
|---|---|---|
| `src/lib/auth.ts` | 20 | 토큰 검증/디코딩 |
| `src/lib/db.ts` | 35 | DB 쿼리 래핑 |
| `src/app/api/chat/route.ts` | 12 | 채팅 API 핸들러 |
| `src/app/api/upload/route.ts` | 18 | 업로드 API 핸들러 |
| `src/hooks/useChat.ts` | 45 | 클라이언트 fetch |

**관찰:**
- API 라우트 2개, 라이브러리 2개, 훅 1개 — 경계 지점(I/O)에서 주로 처리됨 - 좋은 패턴
- 컴포넌트에서 직접 try/catch는 없음 — 에러 바운더리로 위임한 것으로 보임

**권장:** 에러 로깅이 일관된지 확인해보세요. `logger.error()` 를 모든 catch에서 호출하는지 검사하려면 `catch` 블록만 검색해보시면 됩니다.'''),
    ]),

    # 20. 검색 후 수정 (search → edit)
    m([
        sys(),
        user("console.log 남은 거 찾아서 logger.info로 바꿔줘 (lib 폴더만)"),
        assistant('''먼저 lib 폴더의 console.log 사용처를 찾겠습니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "console\\\\.log", "path": "src/lib"}}
</tool_call>'''),
        tool('''src/lib/auth.ts:28:  console.log("user authenticated:", userId);
src/lib/db.ts:12:  console.log("connecting to db...");'''),
        assistant('''2건을 찾았습니다. 각각 교체하겠습니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": "src/lib/auth.ts", "old": "console.log(\\"user authenticated:\\", userId);", "new": "logger.info(`user authenticated: ${userId}`);"}}
</tool_call>'''),
        tool("Edit applied to src/lib/auth.ts: 1 replacement"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "src/lib/db.ts", "old": "console.log(\\"connecting to db...\\");", "new": "logger.info(\\"connecting to db...\\");"}}
</tool_call>'''),
        tool("Edit applied to src/lib/db.ts: 1 replacement"),
        assistant('''`src/lib/` 폴더의 `console.log` 2건을 모두 `logger.info` 로 교체했습니다.

**변경 요약:**
- `src/lib/auth.ts:28` — 템플릿 리터럴로 통합
- `src/lib/db.ts:12` — 문자열 유지

**주의:** 두 파일 상단에 `import { logger } from "@/lib/logger";` 가 들어있는지 확인하세요. 없으면 다음과 같이 추가해야 합니다:

```ts
import { logger } from "./logger";
```

필요하면 import 추가도 도와드리겠습니다.'''),
    ]),

    # 21. import 패턴 검색
    m([
        sys(),
        user("axios import 쓰는 파일 다 찾아"),
        assistant('''axios import 구문을 전역 검색하겠습니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "from [\\"']axios[\\"']|require\\\\([\\"']axios[\\"']\\\\)", "path": "."}}
</tool_call>'''),
        tool('''src/lib/api.ts:1:import axios from "axios";
src/lib/external/openai.ts:2:import axios, { AxiosError } from "axios";
src/hooks/useChat.ts:3:import axios from "axios";
tests/integration/api.test.ts:5:import axios from "axios";'''),
        assistant('''`axios`를 import 하는 파일 **4개**를 찾았습니다.

| 파일 | import 형태 |
|---|---|
| `src/lib/api.ts` | `axios` (default) |
| `src/lib/external/openai.ts` | `axios` + `AxiosError` |
| `src/hooks/useChat.ts` | `axios` (default) |
| `tests/integration/api.test.ts` | `axios` (default) |

**분석:**
- 프로덕션 코드 3개 + 테스트 1개
- `src/lib/api.ts` 가 공통 인스턴스일 가능성이 높음 — 다른 파일들이 이걸 거쳐가도록 리팩토링하면 인터셉터/타임아웃을 한 곳에서 관리 가능

**마이그레이션 고려:** Next.js 14+에서는 `fetch()` + Server Actions로 충분한 경우가 많아서, axios 의존성 제거도 검토해볼만 합니다.'''),
    ]),

    # 22. 환경변수 검색
    m([
        sys(),
        user("process.env 사용하는 곳 찾기"),
        assistant('''환경변수 사용처를 검색하겠습니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "process\\\\.env\\\\.", "path": "src"}}
</tool_call>'''),
        tool('''src/config.ts:2:  apiUrl: process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000",
src/config.ts:5:  dbUrl: process.env.DATABASE_URL
src/lib/auth.ts:8:  const secret = process.env.NEXTAUTH_SECRET;
src/lib/auth.ts:45:  if (process.env.NODE_ENV === "development") {
src/lib/external/openai.ts:5:  apiKey: process.env.OPENAI_API_KEY,
src/app/api/chat/route.ts:8:  const key = process.env.API_KEY;'''),
        assistant('''`process.env` 사용처 **6곳**을 찾았습니다.

**사용 중인 환경변수 (5종):**
| 변수명 | 위치 | 성격 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `src/config.ts:2` | 퍼블릭 (브라우저 노출 OK) |
| `DATABASE_URL` | `src/config.ts:5` | 시크릿 |
| `NEXTAUTH_SECRET` | `src/lib/auth.ts:8` | 시크릿 |
| `NODE_ENV` | `src/lib/auth.ts:45` | 시스템 |
| `OPENAI_API_KEY` | `src/lib/external/openai.ts:5` | 시크릿 |
| `API_KEY` | `src/app/api/chat/route.ts:8` | 시크릿 |

**권장 사항:**
1. `.env.example` 에 6개 변수 모두 문서화되어 있는지 확인
2. 시크릿들은 `NEXT_PUBLIC_` 접두사 **없이** 유지 (현재 OK)
3. 런타임 검증용 `zod` 스키마를 `src/env.ts` 에 만들어두면 실수 방지 가능

```ts
// src/env.ts 예시
import { z } from "zod";
export const env = z.object({
  DATABASE_URL: z.string().url(),
  NEXTAUTH_SECRET: z.string().min(32),
  OPENAI_API_KEY: z.string().startsWith("sk-"),
  API_KEY: z.string(),
}).parse(process.env);
```'''),
    ]),

    # 23. 중복 코드 찾기
    m([
        sys(),
        user("formatDate 함수 여러 파일에 있는지 확인"),
        assistant('''formatDate 정의를 전역 검색하겠습니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "function formatDate|const formatDate|formatDate\\\\s*=", "path": "src"}}
</tool_call>'''),
        tool('''src/lib/date.ts:3:export function formatDate(d: Date): string {
src/components/ChatBubble.tsx:18:  const formatDate = (d: Date) => d.toLocaleString("ko-KR");
src/app/dashboard/page.tsx:22:  const formatDate = (d: Date) => `${d.getFullYear()}-${d.getMonth()+1}-${d.getDate()}`;'''),
        assistant('''`formatDate` 가 **3곳에 중복** 정의되어 있습니다. 리팩토링 대상입니다.

**발견된 중복:**
| # | 파일 | 구현 |
|---|---|---|
| 1 | `src/lib/date.ts:3` | `export function formatDate(d: Date): string` (공용) |
| 2 | `src/components/ChatBubble.tsx:18` | `d.toLocaleString("ko-KR")` (한글 로케일) |
| 3 | `src/app/dashboard/page.tsx:22` | `${year}-${month+1}-${day}` (커스텀) |

**문제점:**
- 3가지 서로 다른 포맷이 존재 → UI 일관성 깨짐
- `src/lib/date.ts` 의 공용 구현이 있는데 두 곳이 자체 구현 사용

**리팩토링 제안:**
```ts
// src/lib/date.ts 에 옵션 지원 추가
export function formatDate(d: Date, style: "iso" | "ko" | "short" = "iso"): string {
  if (style === "ko") return d.toLocaleString("ko-KR");
  if (style === "short") return `${d.getFullYear()}-${d.getMonth()+1}-${d.getDate()}`;
  return d.toISOString();
}
```

그리고 두 파일에서 `import { formatDate } from "@/lib/date"` 로 통일하시면 됩니다. 제가 리팩토링 실행할까요?'''),
    ]),

    # 24. 테스트 파일 찾기 (glob → read)
    m([
        sys(),
        user("auth 관련 테스트 있나 보고 내용 보여줘"),
        assistant('''auth 관련 테스트 파일을 검색하겠습니다.

<tool_call>
{"name": "glob_files", "arguments": {"pattern": "**/*auth*.test.*"}}
</tool_call>'''),
        tool('''src/lib/auth.test.ts
src/hooks/useAuth.test.ts'''),
        assistant('''2개 찾았습니다. 라이브러리 테스트부터 읽어보겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/lib/auth.test.ts"}}
</tool_call>'''),
        tool('''import { describe, it, expect } from "vitest";
import { verifyToken, signToken } from "./auth";

describe("auth", () => {
  it("서명한 토큰을 다시 검증할 수 있어야 한다", () => {
    const token = signToken({ sub: "user-1" });
    const payload = verifyToken(token);
    expect(payload.sub).toBe("user-1");
  });

  it("잘못된 토큰은 예외를 던진다", () => {
    expect(() => verifyToken("invalid.token")).toThrow();
  });

  it("만료된 토큰은 거부한다", () => {
    const expired = signToken({ sub: "user-1" }, { expiresIn: -1 });
    expect(() => verifyToken(expired)).toThrow(/expired/i);
  });
});'''),
        assistant('''`src/lib/auth.test.ts` 내용 확인 완료.

**테스트 프레임워크:** Vitest
**테스트 케이스 3개:**
1. 토큰 서명 ↔ 검증 라운드트립
2. 잘못된 토큰 예외 처리
3. 만료 토큰 거부

**테스트되는 함수:** `signToken`, `verifyToken` (인자/옵션 구조 노출됨)

**커버리지 관점:**
- 정상 케이스 1 + 실패 케이스 2 — 균형 잘 잡힘
- 추가 고려: 서명 키 미스매치, 알고리즘 다운그레이드(`none`), 큰 페이로드 등

나머지 `src/hooks/useAuth.test.ts` 도 이어서 확인해드릴까요?'''),
    ]),

    # 25. 린터 에러 확인 (get_diagnostics)
    m([
        sys(),
        user("지금 코드 에러 있어?"),
        assistant('''에디터 진단 정보를 조회하겠습니다.

<tool_call>
{"name": "get_diagnostics", "arguments": {}}
</tool_call>'''),
        tool('''[
  {
    "file": "src/lib/auth.ts",
    "line": 28,
    "severity": "error",
    "message": "Cannot find name 'logger'. Did you forget to import it?"
  },
  {
    "file": "src/lib/db.ts",
    "line": 12,
    "severity": "error",
    "message": "Cannot find name 'logger'. Did you forget to import it?"
  },
  {
    "file": "src/app/dashboard/page.tsx",
    "line": 22,
    "severity": "warning",
    "message": "'formatDate' is defined but never used."
  }
]'''),
        assistant('''현재 **에러 2건 + 경고 1건** 이 있습니다.

**에러 (2건) — 즉시 수정 필요:**
| 파일 | 라인 | 메시지 |
|---|---|---|
| `src/lib/auth.ts` | 28 | `logger` import 누락 |
| `src/lib/db.ts` | 12 | `logger` import 누락 |

앞서 `console.log` → `logger.info` 리팩토링 후 import를 빼먹은 것 같습니다. 각 파일 상단에 다음을 추가해야 합니다:
```ts
import { logger } from "./logger";
```

**경고 (1건):**
- `src/app/dashboard/page.tsx:22` — 사용되지 않는 `formatDate` 지역 함수 (중복 코드 이슈로 이미 발견됐던 것)

**추천 순서:**
1. 두 파일에 logger import 추가 (빌드 복구)
2. 대시보드의 미사용 함수 제거 또는 `@/lib/date` 로 대체

import 추가 작업 진행할까요?'''),
    ]),

    # 26. 특정 패턴 → 여러 파일 수정
    m([
        sys(),
        user("http://localhost:3000을 쓰는 곳 다 찾아서 8000으로 바꿔"),
        assistant('''먼저 해당 URL을 하드코딩한 위치를 모두 찾겠습니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "http://localhost:3000", "path": "."}}
</tool_call>'''),
        tool('''.env.example:3:NEXTAUTH_URL=http://localhost:3000
src/lib/api.ts:4:const BASE = "http://localhost:3000";
README.md:28:개발 서버: http://localhost:3000
tests/integration/api.test.ts:3:const API = "http://localhost:3000";'''),
        assistant('''4개 파일에서 발견되었습니다. 문서(README)는 설명용이라 제외하고, 코드/설정 3곳을 수정하겠습니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": ".env.example", "old": "NEXTAUTH_URL=http://localhost:3000", "new": "NEXTAUTH_URL=http://localhost:8000"}}
</tool_call>'''),
        tool("Edit applied to .env.example: 1 replacement"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "src/lib/api.ts", "old": "const BASE = \\"http://localhost:3000\\";", "new": "const BASE = \\"http://localhost:8000\\";"}}
</tool_call>'''),
        tool("Edit applied to src/lib/api.ts: 1 replacement"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "tests/integration/api.test.ts", "old": "const API = \\"http://localhost:3000\\";", "new": "const API = \\"http://localhost:8000\\";"}}
</tool_call>'''),
        tool("Edit applied to tests/integration/api.test.ts: 1 replacement"),
        assistant('''3개 파일의 포트를 **3000 → 8000** 으로 변경 완료했습니다.

**수정된 파일:**
- `.env.example` (NEXTAUTH_URL)
- `src/lib/api.ts` (BASE 상수)
- `tests/integration/api.test.ts` (API 상수)

**README.md 는 일부러 건드리지 않았습니다.** — 포트는 문서에서 설명하는 기본값이라, 실제 포트가 8000으로 정착되면 README도 같이 업데이트하면 됩니다. 지금 README까지 바꿀까요?

**추가 권장:** 하드코딩된 URL을 한 곳(`src/config.ts`) 에 모아두고 다른 파일은 거기서 import 하도록 리팩토링하면 다음부터 한 줄만 바꾸면 됩니다.'''),
    ]),

    # 27. 복잡한 리팩토링 (search → read → edit)
    m([
        sys(),
        user("useChat 훅에서 fetch 하드코딩된 URL을 config 상수로 바꿔줘"),
        assistant('''단계별로 진행하겠습니다. 먼저 useChat 훅 내의 fetch 호출을 검색합니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "fetch\\\\(", "path": "src/hooks/useChat.ts"}}
</tool_call>'''),
        tool('''src/hooks/useChat.ts:42:    const res = await fetch("http://localhost:8000/api/chat", {
src/hooks/useChat.ts:78:    const res = await fetch("http://localhost:8000/api/chat/stream", {'''),
        assistant('''fetch가 2곳에 있네요. 파일 전체를 읽어 맥락을 파악하겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/hooks/useChat.ts"}}
</tool_call>'''),
        tool('''import { useState, useCallback } from "react";

export function useChat() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const send = useCallback(async (text: string) => {
    setLoading(true);
    const res = await fetch("http://localhost:8000/api/chat", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    setMessages((m) => [...m, data]);
    setLoading(false);
  }, []);

  const stream = useCallback(async (text: string) => {
    const res = await fetch("http://localhost:8000/api/chat/stream", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    return res.body;
  }, []);

  return { messages, loading, send, stream };
}'''),
        assistant('''config 상수를 import하고 URL을 치환하겠습니다. `src/config.ts` 의 `API_BASE` 를 활용합니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": "src/hooks/useChat.ts", "old": "import { useState, useCallback } from \\"react\\";", "new": "import { useState, useCallback } from \\"react\\";\\nimport { config } from \\"@/config\\";"}}
</tool_call>'''),
        tool("Edit applied to src/hooks/useChat.ts: 1 replacement"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "src/hooks/useChat.ts", "old": "fetch(\\"http://localhost:8000/api/chat\\", {", "new": "fetch(`${config.apiUrl}/api/chat`, {"}}
</tool_call>'''),
        tool("Edit applied to src/hooks/useChat.ts: 1 replacement"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "src/hooks/useChat.ts", "old": "fetch(\\"http://localhost:8000/api/chat/stream\\", {", "new": "fetch(`${config.apiUrl}/api/chat/stream`, {"}}
</tool_call>'''),
        tool("Edit applied to src/hooks/useChat.ts: 1 replacement"),
        assistant('''`src/hooks/useChat.ts` 리팩토링 완료했습니다.

**변경 사항 요약 (3단계):**
1. `import { config } from "@/config";` 추가
2. `send` 내부 fetch URL → `` `${config.apiUrl}/api/chat` ``
3. `stream` 내부 fetch URL → `` `${config.apiUrl}/api/chat/stream` ``

**효과:**
- 하드코딩된 `localhost:8000` 제거 → 개발/스테이징/프로덕션 환경별로 `NEXT_PUBLIC_API_BASE` 만 바꾸면 됨
- 두 fetch가 한 소스를 바라보므로 한쪽만 바뀌는 실수 방지

**확인 권장:**
```bash
npx tsc --noEmit        # 타입 에러 체크
npm test -- useChat     # 관련 테스트 실행
```

tsconfig의 `paths` 에 `"@/*": ["src/*"]` 가 설정되어 있는지도 한 번 확인해보세요. 없다면 상대 경로 `../config` 로 바꿔야 합니다.'''),
    ]),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/tools_filesystem.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"파일시스템+코드검색 tools: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
