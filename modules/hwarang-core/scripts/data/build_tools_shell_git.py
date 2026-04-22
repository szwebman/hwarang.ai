"""화랑 AI Tool Calling 학습 데이터 (쉘 + Git + 웹)"""
import json, os, logging, argparse
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TOOLS_DESC = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 코딩 어시스턴트입니다.
사용 가능한 도구가 있을 때 <tool_call> 태그로 호출합니다.

사용 가능한 도구:
- run_command(command: str): 쉘 명령 실행
- git_status(): Git 상태 확인
- git_diff(path: str): Git diff 보기
- git_log(limit: int): 커밋 히스토리
- git_commit(message: str): 커밋 생성
- git_branch(): 브랜치 목록
- web_search(query: str): 웹 검색
- fetch_url(url: str): URL 내용 가져오기
- read_file(path: str): 파일 읽기
- write_file(path: str, content: str): 파일 쓰기
- list_directory(path: str): 디렉토리 목록

도구 호출 형식:
<tool_call>
{"name": "도구명", "arguments": {"인자": "값"}}
</tool_call>

도구 결과를 받으면 그 결과를 바탕으로 응답합니다."""

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
    # 쉘 명령 (10건)
    # ============================================================

    # 1. 의존성 설치
    m([
        sys(),
        user("pnpm install 실행해줘"),
        assistant('''의존성을 설치하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm install"}}
</tool_call>'''),
        tool("""Lockfile is up to date, resolution step is skipped
Packages: +847
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
Progress: resolved 847, reused 820, downloaded 27, added 847, done

dependencies:
+ next 15.1.3
+ react 19.0.0
+ react-dom 19.0.0

devDependencies:
+ typescript 5.7.2
+ @types/node 22.10.2

Done in 12.4s"""),
        assistant("""의존성 설치가 완료되었습니다.

- 총 847개 패키지 설치 (27개 신규 다운로드, 820개는 캐시 재사용)
- 주요 의존성: Next.js 15.1.3, React 19.0.0, TypeScript 5.7.2
- 소요 시간: 12.4초

Next.js 15와 React 19 최신 버전이 설치되었네요. 이제 `pnpm dev`로 개발 서버를 띄울 수 있습니다."""),
    ]),

    # 2. 개발 서버 실행
    m([
        sys(),
        user("dev 서버 띄워줘"),
        assistant('''개발 서버를 실행하겠습니다. 먼저 package.json의 스크립트를 확인하겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "package.json"}}
</tool_call>'''),
        tool("""{
  "name": "hwarang-web",
  "version": "0.3.0",
  "scripts": {
    "dev": "next dev --turbopack -p 3000",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  }
}"""),
        assistant('''확인했습니다. Next.js + Turbopack 기반이네요.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm dev"}}
</tool_call>'''),
        tool("""> hwarang-web@0.3.0 dev
> next dev --turbopack -p 3000

   ▲ Next.js 15.1.3 (Turbopack)
   - Local:        http://localhost:3000
   - Network:      http://192.168.0.42:3000

 ✓ Starting...
 ✓ Ready in 1.8s"""),
        assistant("""개발 서버가 정상적으로 시작되었습니다.

- URL: http://localhost:3000
- 네트워크 접속: http://192.168.0.42:3000 (같은 와이파이에서 접속 가능)
- Turbopack 기반이라 Webpack 대비 약 10배 빠른 1.8초 만에 시작됐습니다.

브라우저에서 http://localhost:3000 을 열어 확인해보세요."""),
    ]),

    # 3. 테스트 실행
    m([
        sys(),
        user("test 돌려봐"),
        assistant('''테스트를 실행하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm test"}}
</tool_call>'''),
        tool(""" PASS  src/utils/format.test.ts
 PASS  src/components/Button.test.tsx
 FAIL  src/hooks/useAuth.test.ts
  ● useAuth › should return user when token is valid

    expect(received).toBe(expected)
    Expected: "user123"
    Received: undefined

      23 |   const { result } = renderHook(() => useAuth());
      24 |   await waitFor(() => {
    > 25 |     expect(result.current.user?.id).toBe("user123");
         |                                     ^
      26 |   });

Test Suites: 1 failed, 2 passed, 3 total
Tests:       1 failed, 14 passed, 15 total
Time:        4.231 s"""),
        assistant("""테스트 결과입니다.

**통과: 14/15 (93.3%)**

실패한 테스트:
- `src/hooks/useAuth.test.ts`의 `should return user when token is valid`
- 원인: `result.current.user`가 `undefined`로 반환됨
- 위치: 25번 줄

**추정 원인:**
`useAuth` 훅 내부에서 토큰 검증 후 사용자 정보를 state에 설정하는 부분이 누락됐거나, 비동기 처리가 완료되기 전에 테스트가 종료된 것 같습니다. `waitFor`의 타임아웃을 늘리거나 훅 구현을 점검해봐야 합니다.

해당 파일을 열어서 확인해드릴까요?"""),
    ]),

    # 4. 빌드
    m([
        sys(),
        user("production 빌드 실행"),
        assistant('''프로덕션 빌드를 진행하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm build"}}
</tool_call>'''),
        tool("""> hwarang-web@0.3.0 build
> next build

   ▲ Next.js 15.1.3

 ✓ Compiled successfully in 18.2s
 ✓ Linting and checking validity of types
 ✓ Collecting page data
 ✓ Generating static pages (24/24)
 ✓ Finalizing page optimization

Route (app)                              Size     First Load JS
┌ ○ /                                    1.8 kB          102 kB
├ ○ /_not-found                          142 B          88.3 kB
├ ○ /chat                                12.4 kB         145 kB
├ ○ /dashboard                           8.2 kB          138 kB
└ ○ /settings                            4.1 kB          118 kB
+ First Load JS shared by all            88.2 kB

○  (Static)  prerendered as static content"""),
        assistant("""빌드가 성공적으로 완료되었습니다.

**빌드 요약:**
- 컴파일: 18.2초
- 24개 정적 페이지 생성
- 타입 체크 및 린트 통과

**페이지별 번들 크기:**
| 경로 | Size | First Load JS |
|------|------|---------------|
| `/` | 1.8 kB | 102 kB |
| `/chat` | 12.4 kB | 145 kB |
| `/dashboard` | 8.2 kB | 138 kB |
| `/settings` | 4.1 kB | 118 kB |

First Load JS 공유 청크가 88.2KB로 적당한 편입니다. `/chat` 페이지가 가장 크지만 145KB 정도라 모바일에서도 괜찮습니다. `pnpm start`로 프로덕션 서버를 띄울 수 있습니다."""),
    ]),

    # 5. 디스크 사용량
    m([
        sys(),
        user("node_modules 용량 확인"),
        assistant('''node_modules 크기를 확인하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "du -sh node_modules"}}
</tool_call>'''),
        tool("1.2G\tnode_modules"),
        assistant('''node_modules가 1.2GB를 차지하고 있네요. 어떤 패키지가 많이 잡아먹는지 상위 10개를 확인해보겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "du -sh node_modules/* | sort -rh | head -10"}}
</tool_call>'''),
        tool("""312M\tnode_modules/.pnpm
184M\tnode_modules/next
92M\tnode_modules/@next
78M\tnode_modules/typescript
54M\tnode_modules/@types
41M\tnode_modules/react-dom
28M\tnode_modules/@vercel
24M\tnode_modules/webpack
21M\tnode_modules/eslint
18M\tnode_modules/tailwindcss"""),
        assistant("""**node_modules 분석 결과 (1.2GB)**

상위 10개 패키지:
1. `.pnpm` (312MB) - pnpm의 하드링크 저장소
2. `next` (184MB) - Next.js 본체
3. `@next` (92MB) - Next.js 서브패키지들
4. `typescript` (78MB) - TS 컴파일러
5. `@types` (54MB) - 타입 정의 모음

**정리 팁:**
- pnpm을 쓰고 있어서 다른 프로젝트와 디스크를 공유 중이니 실제 점유는 더 적습니다.
- 완전 초기화: `rm -rf node_modules && pnpm install`
- pnpm store 정리: `pnpm store prune` (미사용 패키지 제거)"""),
    ]),

    # 6. 프로세스 확인
    m([
        sys(),
        user("3000 포트 누가 쓰는지"),
        assistant('''3000번 포트 사용 중인 프로세스를 확인하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "lsof -i :3000"}}
</tool_call>'''),
        tool("""COMMAND   PID  USER   FD   TYPE  DEVICE SIZE/OFF NODE NAME
node    48231 user   21u  IPv6 0x1a2b      0t0  TCP *:hbci (LISTEN)
node    48231 user   22u  IPv4 0x3c4d      0t0  TCP localhost:3000 (LISTEN)"""),
        assistant("""3000번 포트는 **Node.js 프로세스(PID 48231)**가 사용 중입니다. 아마 이전에 띄운 개발 서버가 종료되지 않고 남아있는 것 같네요.

**종료 방법:**
```bash
kill 48231
# 또는 강제 종료
kill -9 48231
# 포트 기준 한 번에
lsof -ti:3000 | xargs kill -9
```

종료하고 다시 `pnpm dev`를 실행하면 됩니다. 바로 종료해드릴까요?"""),
    ]),

    # 7. 파일 검색
    m([
        sys(),
        user("프로젝트에서 큰 파일 10개 찾아"),
        assistant('''큰 파일 상위 10개를 찾아보겠습니다. node_modules와 .git은 제외하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "find . -type f -not -path './node_modules/*' -not -path './.git/*' -not -path './.next/*' -exec du -h {} + | sort -rh | head -10"}}
</tool_call>'''),
        tool("""142M\t./models/qwen2.5-7b.gguf
89M\t./public/videos/demo.mp4
24M\t./data/sft/korean_code.jsonl
18M\t./data/sft/design_patterns.jsonl
12M\t./public/images/hero-bg.png
8.4M\t./dist/bundle.js
6.2M\t./public/fonts/pretendard.woff2
4.8M\t./docs/patent/HFL_diagram.pdf
3.1M\t./logs/app.log
2.4M\t./data/eval/benchmark.json"""),
        assistant("""**큰 파일 TOP 10:**

| 순위 | 크기 | 파일 |
|------|------|------|
| 1 | 142MB | `models/qwen2.5-7b.gguf` |
| 2 | 89MB | `public/videos/demo.mp4` |
| 3 | 24MB | `data/sft/korean_code.jsonl` |
| 4 | 18MB | `data/sft/design_patterns.jsonl` |
| 5 | 12MB | `public/images/hero-bg.png` |

**권장 조치:**
- `models/*.gguf`는 Git LFS로 옮기거나 `.gitignore`에 추가 (142MB 모델)
- `public/videos/demo.mp4`는 CDN 호스팅 추천
- `hero-bg.png`는 WebP로 변환하면 60~70% 줄일 수 있습니다
- `data/sft/*.jsonl`은 훈련 데이터라 저장소 분리 고려

Git 히스토리에 이미 커밋됐다면 `git filter-repo`로 제거해야 저장소 크기가 줄어듭니다."""),
    ]),

    # 8. 로그 확인
    m([
        sys(),
        user("에러 로그 마지막 20줄 보여줘"),
        assistant('''로그 파일을 확인하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "tail -20 logs/error.log"}}
</tool_call>'''),
        tool("""2026-04-22 09:14:23 [ERROR] Database connection failed: timeout after 5000ms
  at PostgresPool.connect (/app/db/pool.js:42:15)
  at async getUserById (/app/services/user.js:18:22)
2026-04-22 09:14:24 [ERROR] Request failed: GET /api/users/123
  status: 500, duration: 5012ms
2026-04-22 09:15:02 [WARN] Slow query detected: SELECT * FROM chat_messages (1843ms)
2026-04-22 09:18:45 [ERROR] Redis connection lost, attempting reconnect...
2026-04-22 09:18:46 [INFO] Redis reconnected
2026-04-22 09:22:11 [ERROR] Unhandled promise rejection in chat stream
  TypeError: Cannot read property 'content' of undefined
  at processToolCall (/app/llm/tools.js:87:34)
2026-04-22 09:25:00 [ERROR] vLLM inference timeout after 30000ms
  model: qwen2.5-7b, prompt_tokens: 2048
2026-04-22 09:27:14 [INFO] Scaling up: adding 1 worker (current: 3)
2026-04-22 09:30:22 [ERROR] OOM killed: worker-2 (RSS: 8.2GB)
2026-04-22 09:31:00 [INFO] Worker-2 restarted
2026-04-22 09:45:18 [ERROR] Rate limit exceeded for IP 203.241.x.x"""),
        assistant("""**최근 에러 로그 분석 (오늘 09:14 ~ 09:45)**

심각도 순 주요 이슈:

**1. PostgreSQL 연결 타임아웃 (09:14)**
- 5초 후 타임아웃, `/api/users/123` 500 에러
- 커넥션 풀 설정 또는 DB 상태 점검 필요

**2. 워커 OOM (09:30)**
- worker-2가 8.2GB 메모리로 강제 종료됨
- vLLM 메모리 누수 가능성, `max_model_len` 조정 검토

**3. vLLM 추론 타임아웃 (09:25)**
- Qwen2.5-7B, 2048 토큰 프롬프트가 30초 초과
- 배치 크기 또는 GPU 부하 확인 필요

**4. tool_call 처리 버그 (09:22)**
- `processToolCall`에서 `content` 필드 `undefined` 접근
- `/app/llm/tools.js:87` 방어 코드 필요 (optional chaining)

가장 먼저 fix할 부분은 tool_call 크래시(코드 수정만 하면 됨)이고, 그다음 OOM 조사를 추천드립니다."""),
    ]),

    # 9. 권한 변경
    m([
        sys(),
        user("deploy.sh 실행 권한 줘"),
        assistant('''deploy.sh에 실행 권한을 부여하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "chmod +x deploy.sh && ls -la deploy.sh"}}
</tool_call>'''),
        tool("-rwxr-xr-x  1 user  staff  2847 Apr 22 10:15 deploy.sh"),
        assistant("""실행 권한 부여 완료했습니다.

- 권한: `-rwxr-xr-x` (소유자 rwx, 그룹 rx, 기타 rx)
- 파일 크기: 2,847 bytes

이제 `./deploy.sh`로 직접 실행할 수 있습니다. 서버 배포 스크립트라면 보안상 기타 사용자의 실행 권한은 제거하는 것도 고려해보세요:
```bash
chmod 750 deploy.sh  # 소유자+그룹만 실행 가능
```"""),
    ]),

    # 10. 서비스 재시작
    m([
        sys(),
        user("hwarang-api 서비스 재시작해줘"),
        assistant('''먼저 현재 PM2 프로세스 상태를 확인하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pm2 list"}}
</tool_call>'''),
        tool("""┌─────┬──────────────────┬─────────┬─────────┬──────────┬──────────┬──────┐
│ id  │ name             │ mode    │ status  │ cpu      │ memory   │ ↺    │
├─────┼──────────────────┼─────────┼─────────┼──────────┼──────────┼──────┤
│ 0   │ hwarang-api      │ cluster │ online  │ 1.2%     │ 428 MB   │ 3    │
│ 1   │ hwarang-worker   │ fork    │ online  │ 0.8%     │ 312 MB   │ 1    │
│ 2   │ hwarang-web      │ cluster │ online  │ 2.1%     │ 512 MB   │ 5    │
└─────┴──────────────────┴─────────┴─────────┴──────────┴──────────┴──────┘"""),
        assistant('''hwarang-api가 온라인 상태(428MB 사용 중)입니다. 재시작하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pm2 restart hwarang-api --update-env"}}
</tool_call>'''),
        tool("""[PM2] Applying action restartProcessId on app [hwarang-api](ids: [ 0 ])
[PM2] [hwarang-api](0) ✓
┌─────┬──────────────────┬─────────┬─────────┬──────────┬──────────┬──────┐
│ id  │ name             │ mode    │ status  │ cpu      │ memory   │ ↺    │
├─────┼──────────────────┼─────────┼─────────┼──────────┼──────────┼──────┤
│ 0   │ hwarang-api      │ cluster │ online  │ 45.3%    │ 162 MB   │ 4    │
└─────┴──────────────────┴─────────┴─────────┴──────────┴──────────┴──────┘"""),
        assistant("""hwarang-api 재시작 완료했습니다.

- 상태: online (재시작 카운트 3 → 4)
- 메모리: 428MB → 162MB (초기화됨)
- CPU: 45.3% (기동 중, 곧 안정화됨)
- `--update-env` 플래그로 환경변수도 최신 반영했습니다.

로그 모니터링하시려면:
```bash
pm2 logs hwarang-api --lines 50
```"""),
    ]),

    # ============================================================
    # Git (8건)
    # ============================================================

    # 11. 상태 확인
    m([
        sys(),
        user("git 변경사항 뭐 있어?"),
        assistant('''Git 상태를 확인하겠습니다.

<tool_call>
{"name": "git_status", "arguments": {}}
</tool_call>'''),
        tool("""On branch main
Your branch is ahead of 'origin/main' by 2 commits.
  (use "git push" to publish your local commits)

Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
        modified:   src/components/ChatView.tsx
        new file:   src/hooks/useToolCall.ts

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
        modified:   src/api/chat.ts
        modified:   package.json

Untracked files:
  (use "git add <file>..." to include in what will be committed)
        docs/tool_calling.md
        src/types/tool.ts"""),
        assistant("""**Git 상태 요약**

현재 브랜치: `main` (origin보다 2커밋 앞섬, push 대기 중)

**스테이징됨 (커밋 대기):**
- ✏️ `src/components/ChatView.tsx` (수정)
- ✨ `src/hooks/useToolCall.ts` (신규)

**변경됐으나 스테이징 안 됨:**
- ✏️ `src/api/chat.ts`
- ✏️ `package.json`

**추적 안 됨 (신규 파일):**
- `docs/tool_calling.md`
- `src/types/tool.ts`

Tool Calling 기능 작업 중이신 것 같네요. `docs/tool_calling.md`와 `src/types/tool.ts`도 같이 커밋하시려면 `git add`가 필요합니다."""),
    ]),

    # 12. diff 보기
    m([
        sys(),
        user("package.json 변경 내역 보여줘"),
        assistant('''package.json의 diff를 확인하겠습니다.

<tool_call>
{"name": "git_diff", "arguments": {"path": "package.json"}}
</tool_call>'''),
        tool("""diff --git a/package.json b/package.json
index 8a3c12f..d4e9b21 100644
--- a/package.json
+++ b/package.json
@@ -12,15 +12,18 @@
   "dependencies": {
     "next": "15.1.3",
     "react": "19.0.0",
     "react-dom": "19.0.0",
-    "axios": "^1.6.0",
+    "axios": "^1.7.9",
+    "zustand": "^5.0.2",
+    "zod": "^3.24.1",
     "tailwindcss": "^3.4.0"
   },
   "devDependencies": {
     "typescript": "^5.7.2",
     "@types/node": "^22.10.2",
-    "eslint": "^8.57.0"
+    "eslint": "^9.17.0",
+    "prettier": "^3.4.2"
   }
 }"""),
        assistant("""**package.json 변경사항**

**추가된 의존성:**
- `zustand ^5.0.2` - 상태 관리 라이브러리
- `zod ^3.24.1` - 런타임 스키마 검증

**업데이트된 의존성:**
- `axios` ^1.6.0 → ^1.7.9 (마이너 업데이트)
- `eslint` ^8.57.0 → ^9.17.0 (메이저 업데이트 - 설정 마이그레이션 필요할 수 있음)

**추가된 devDependencies:**
- `prettier ^3.4.2` - 코드 포매터

**주의점:**
- ESLint 9는 Flat Config 형식이 기본입니다. 기존 `.eslintrc.*` 파일이 있다면 `eslint.config.js`로 마이그레이션이 필요합니다.
- `pnpm install`을 한 번 더 돌려야 lockfile이 갱신됩니다."""),
    ]),

    # 13. 로그 보기
    m([
        sys(),
        user("최근 커밋 10개 보여줘"),
        assistant('''최근 커밋 히스토리를 조회하겠습니다.

<tool_call>
{"name": "git_log", "arguments": {"limit": 10}}
</tool_call>'''),
        tool("""b934482 (HEAD -> main) ui 에러
75f4e52 chat: 입력창 텍스트 세로 중앙 정렬 + IME 중복 전송 수정
4378056 인증수정
c0dae75 auth: API 키 Bearer 토큰 인증 지원 (VS Code 확장팩 연동)
2454bfe 수정
a91e3f2 feat: MTP (Multi-Token Prediction) 지원 추가
8d72c41 fix: vLLM 서빙 시 HPC 옵션 명시적 활성화
6e5a4c8 docs: HFL 특허 초안 KR 버전 추가
3b1f0ea feat: 연합 LoRA 학습 프로토콜 구현
1c4d8a9 chore: 26개 AI 기법 스택 문서화"""),
        assistant("""**최근 커밋 10개**

| 해시 | 메시지 |
|------|--------|
| `b934482` | ui 에러 |
| `75f4e52` | chat: 입력창 텍스트 세로 중앙 정렬 + IME 중복 전송 수정 |
| `4378056` | 인증수정 |
| `c0dae75` | auth: API 키 Bearer 토큰 인증 지원 |
| `2454bfe` | 수정 |
| `a91e3f2` | feat: MTP (Multi-Token Prediction) 지원 추가 |
| `8d72c41` | fix: vLLM 서빙 시 HPC 옵션 명시적 활성화 |
| `6e5a4c8` | docs: HFL 특허 초안 KR 버전 추가 |
| `3b1f0ea` | feat: 연합 LoRA 학습 프로토콜 구현 |
| `1c4d8a9` | chore: 26개 AI 기법 스택 문서화 |

**코멘트:**
- 최근 3개 커밋(`ui 에러`, `인증수정`, `수정`)은 메시지가 너무 짧습니다. Conventional Commits 형식(`fix:`, `feat:` 등)을 쓰시는 게 협업에 좋습니다.
- `a91e3f2` 이전까지는 잘 지켜지고 있었네요. 습관 회복 추천드립니다."""),
    ]),

    # 14. 커밋 생성 체인
    m([
        sys(),
        user("변경사항 확인하고 커밋해줘"),
        assistant('''먼저 현재 상태를 확인하겠습니다.

<tool_call>
{"name": "git_status", "arguments": {}}
</tool_call>'''),
        tool("""On branch feature/tool-calling
Changes to be committed:
        modified:   src/llm/prompt.py
        modified:   src/llm/tools.py
        new file:   tests/test_tool_calling.py"""),
        assistant('''3개 파일이 스테이징되어 있네요. 변경 내용을 살펴보겠습니다.

<tool_call>
{"name": "git_diff", "arguments": {"path": "--cached"}}
</tool_call>'''),
        tool("""diff --git a/src/llm/prompt.py b/src/llm/prompt.py
@@ -15,6 +15,12 @@ TOOLS_DESC = \"\"\"...
+- run_command(command: str): 쉘 명령 실행
+- git_status(): Git 상태 확인
+- web_search(query: str): 웹 검색
+\"\"\"
+
diff --git a/src/llm/tools.py b/src/llm/tools.py
@@ -1,4 +1,28 @@
+def parse_tool_call(text: str) -> dict | None:
+    \"\"\"<tool_call> 태그에서 JSON 추출\"\"\"
+    ...
+
+def execute_tool(name: str, args: dict) -> str:
+    \"\"\"도구 실행 디스패처\"\"\"
+    ...
diff --git a/tests/test_tool_calling.py b/tests/test_tool_calling.py
@@ -0,0 +1,42 @@
+def test_parse_tool_call_valid():
+    ...
+def test_execute_run_command():
+    ..."""),
        assistant('''Tool Calling 기능 구현이군요. 커밋 메시지를 작성해서 커밋하겠습니다.

<tool_call>
{"name": "git_commit", "arguments": {"message": "feat(llm): Tool Calling 지원 추가\\n\\n- prompt.py: 시스템 프롬프트에 사용 가능 도구 목록 추가\\n- tools.py: <tool_call> 태그 파싱 및 실행 디스패처 구현\\n- 테스트: 파싱/실행 단위 테스트 추가"}}
</tool_call>'''),
        tool("""[feature/tool-calling e8f2a14] feat(llm): Tool Calling 지원 추가
 3 files changed, 76 insertions(+), 2 deletions(-)
 create mode 100644 tests/test_tool_calling.py"""),
        assistant("""커밋 완료했습니다.

- **커밋 해시:** `e8f2a14`
- **브랜치:** `feature/tool-calling`
- **변경:** 3파일, +76줄 / -2줄

커밋 메시지는 Conventional Commits 형식(`feat(llm):`)으로 작성했고, 본문에 세부 변경사항을 정리했습니다. 이제 `git push origin feature/tool-calling`으로 원격에 올리고 PR을 생성하시면 됩니다."""),
    ]),

    # 15. 브랜치 확인
    m([
        sys(),
        user("브랜치 뭐뭐 있어?"),
        assistant('''브랜치 목록을 조회하겠습니다.

<tool_call>
{"name": "git_branch", "arguments": {}}
</tool_call>'''),
        tool("""* main
  develop
  feature/tool-calling
  feature/federated-lora
  feature/vscode-extension
  fix/auth-token-refresh
  release/v0.3.0
  remotes/origin/main
  remotes/origin/develop
  remotes/origin/feature/tool-calling
  remotes/origin/release/v0.3.0"""),
        assistant("""**브랜치 목록**

**로컬 브랜치 (7개):**
- ⭐ `main` (현재)
- `develop`
- `feature/tool-calling`
- `feature/federated-lora`
- `feature/vscode-extension`
- `fix/auth-token-refresh`
- `release/v0.3.0`

**원격 브랜치 (4개):**
- `origin/main`, `origin/develop`, `origin/feature/tool-calling`, `origin/release/v0.3.0`

**정리 필요 브랜치:**
- `feature/federated-lora`, `feature/vscode-extension`, `fix/auth-token-refresh`는 원격에 없음 → push되지 않았거나 이미 머지되어 삭제된 브랜치일 수 있음
- 머지 완료된 로컬 브랜치 정리: `git branch --merged main | grep -v main | xargs git branch -d`

현재 진행 중인 피처가 많네요. 작업 순서를 정리하시는 걸 추천드립니다."""),
    ]),

    # 16. 특정 파일 변경 이력
    m([
        sys(),
        user("src/llm/tools.py 누가 만들었고 누가 주로 수정했어?"),
        assistant('''해당 파일의 변경 이력을 조회하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "git log --follow --format='%h %an %ad %s' --date=short src/llm/tools.py"}}
</tool_call>'''),
        tool("""e8f2a14 김진성 2026-04-22 feat(llm): Tool Calling 지원 추가
a91e3f2 김진성 2026-04-15 feat: MTP (Multi-Token Prediction) 지원 추가
7c3e1f8 박성훈 2026-04-02 refactor: tool 실행기 분리
5b9d6a2 김진성 2026-03-28 fix: 토큰 카운팅 오류 수정
2a4f8c1 박성훈 2026-03-15 docs: tools.py 독스트링 보강
d1e7b93 김진성 2026-03-10 initial: tools.py 최초 생성"""),
        assistant('''작성자별 기여도도 확인해보겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "git log --follow --format='%an' src/llm/tools.py | sort | uniq -c | sort -rn"}}
</tool_call>'''),
        tool("""   4 김진성
   2 박성훈"""),
        assistant("""**`src/llm/tools.py` 변경 이력**

**최초 생성:**
- `d1e7b93` (2026-03-10) - **김진성** 님이 최초 생성

**기여자 (총 6개 커밋):**
- 김진성: 4회 (67%) - 주 기여자
- 박성훈: 2회 (33%)

**주요 변경 타임라인:**
1. 03-10 초기 생성 (김진성)
2. 03-15 문서화 보강 (박성훈)
3. 03-28 토큰 카운팅 버그 픽스 (김진성)
4. 04-02 실행기 리팩터링 (박성훈)
5. 04-15 MTP 지원 (김진성)
6. 04-22 Tool Calling 지원 (김진성) ← 최근

질문하거나 리뷰받을 때는 **김진성** 님께 먼저 문의하시는 게 좋겠습니다. 구조적 변경은 박성훈 님이 담당하신 것 같네요."""),
    ]),

    # 17. 변경사항 요약 후 커밋 메시지 제안
    m([
        sys(),
        user("지금 작업한 거 커밋 메시지 좀 지어줘"),
        assistant('''현재 변경사항을 분석해서 메시지를 제안드리겠습니다.

<tool_call>
{"name": "git_status", "arguments": {}}
</tool_call>'''),
        tool("""On branch feature/vscode-extension
Changes not staged for commit:
        modified:   modules/hwarang-vscode/src/providers/chat-view-provider.ts
        modified:   modules/hwarang-vscode/package.json
        modified:   modules/hwarang-vscode/.vscodeignore"""),
        assistant('''VS Code 확장팩 관련 수정이네요. 구체적인 변경 내용을 확인하겠습니다.

<tool_call>
{"name": "git_diff", "arguments": {"path": "modules/hwarang-vscode"}}
</tool_call>'''),
        tool("""diff --git a/modules/hwarang-vscode/src/providers/chat-view-provider.ts
@@ -142,6 +142,18 @@ export class ChatViewProvider {
-        const response = await fetch(`${apiUrl}/chat`, {
-          headers: { 'Content-Type': 'application/json' }
+        const apiKey = await this.getApiKey();
+        const response = await fetch(`${apiUrl}/chat`, {
+          headers: {
+            'Content-Type': 'application/json',
+            'Authorization': `Bearer ${apiKey}`
+          }
+        });
+        if (response.status === 401) {
+          vscode.window.showErrorMessage('API 키가 유효하지 않습니다');
+          return;
+        }

diff --git a/modules/hwarang-vscode/package.json
@@ -3,7 +3,7 @@
-  "version": "0.2.9",
+  "version": "0.3.0",

diff --git a/modules/hwarang-vscode/.vscodeignore
+*.vsix
+src/**/*.test.ts"""),
        assistant("""**변경 내용 분석**

1. **인증 추가** - `chat-view-provider.ts`에 Bearer 토큰 인증 로직 추가 + 401 에러 핸들링
2. **버전 업** - 0.2.9 → 0.3.0 (마이너 버전)
3. **패키징 최적화** - `.vscodeignore`에 vsix 및 테스트 파일 제외

**제안 커밋 메시지:**

```
feat(vscode): API 키 인증 및 v0.3.0 릴리스

- ChatViewProvider에 Bearer 토큰 인증 추가
- 401 Unauthorized 시 사용자 안내 메시지 표시
- .vscodeignore로 *.vsix, 테스트 파일 패키지 제외
- 버전 0.2.9 → 0.3.0
```

짧게 한 줄로 쓰시려면:
```
feat(vscode): API 키 인증 지원 및 v0.3.0 릴리스
```

이 메시지로 커밋 진행해드릴까요?"""),
    ]),

    # 18. 스테이징 후 커밋
    m([
        sys(),
        user("README만 빼고 다 커밋해줘"),
        assistant('''현재 변경된 파일 목록을 먼저 확인하겠습니다.

<tool_call>
{"name": "git_status", "arguments": {}}
</tool_call>'''),
        tool("""On branch main
Changes not staged for commit:
        modified:   README.md
        modified:   src/app.ts
        modified:   src/config.ts
        modified:   tests/app.test.ts

Untracked files:
        docs/CHANGELOG.md"""),
        assistant('''README.md 제외하고 나머지 파일만 스테이징하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "git add src/app.ts src/config.ts tests/app.test.ts docs/CHANGELOG.md"}}
</tool_call>'''),
        tool(""),
        assistant('''스테이징 확인하겠습니다.

<tool_call>
{"name": "git_status", "arguments": {}}
</tool_call>'''),
        tool("""On branch main
Changes to be committed:
        modified:   src/app.ts
        modified:   src/config.ts
        modified:   tests/app.test.ts
        new file:   docs/CHANGELOG.md

Changes not staged for commit:
        modified:   README.md"""),
        assistant('''README.md만 빼고 4개 파일이 잘 스테이징됐네요. 커밋하겠습니다.

<tool_call>
{"name": "git_commit", "arguments": {"message": "chore: 설정 업데이트 및 CHANGELOG 추가"}}
</tool_call>'''),
        tool("""[main 7f3c921] chore: 설정 업데이트 및 CHANGELOG 추가
 4 files changed, 58 insertions(+), 12 deletions(-)
 create mode 100644 docs/CHANGELOG.md"""),
        assistant("""커밋 완료했습니다.

- **해시:** `7f3c921`
- **4개 파일** 변경 (+58 / -12)
- `README.md`는 여전히 작업 트리에 남아있습니다 (스테이징 안 됨)

README.md는 따로 정리 후 별도 커밋하시면 깔끔합니다."""),
    ]),

    # ============================================================
    # 웹 (8건)
    # ============================================================

    # 19. 라이브러리 문서 검색
    m([
        sys(),
        user("Next.js 15 새 기능 알려줘"),
        assistant('''Next.js 15 릴리스 정보를 검색하겠습니다.

<tool_call>
{"name": "web_search", "arguments": {"query": "Next.js 15 new features release notes"}}
</tool_call>'''),
        tool("""[1] Next.js 15 - Vercel Blog (nextjs.org/blog/next-15)
Next.js 15 is now stable. Key features:
- React 19 RC support (stable in React)
- Async Request APIs (cookies, headers, params, searchParams)
- Caching semantics changed: fetch, GET Route Handlers, Client Router
- Turbopack Dev (stable)
- Partial Prerendering (experimental)
- next/after API

[2] What's New in Next.js 15 (dev.to/nextjs-15-whats-new)
- ESLint 9 support
- TypeScript config support (next.config.ts)
- Improved error UI and stack traces
- create-next-app redesigned

[3] Next.js 15.1 (nextjs.org/blog/next-15-1)
- React 19 stable
- after() API stable
- forbidden() / unauthorized() APIs (experimental)"""),
        assistant("""**Next.js 15 주요 신기능 정리**

**1. React 19 지원 (안정화)**
- Server Components, Actions, use() 훅 등 React 19 기능 전면 지원

**2. 비동기 Request API (Breaking Change)**
- `cookies()`, `headers()`, `params`, `searchParams`가 이제 비동기 (Promise 반환)
- 기존 코드는 `await` 추가 필요: `const c = await cookies()`

**3. 캐싱 정책 변경 (Breaking Change)**
- `fetch` 요청 기본값: `force-cache` → `no-store`
- GET Route Handlers 기본 캐싱 비활성화
- 클라이언트 라우터 캐시 기본 TTL 변경

**4. Turbopack Dev 정식 안정화**
- `next dev --turbopack`이 프로덕션 레벨

**5. Partial Prerendering (실험적)**
- 정적 셸 + 동적 콘텐츠 스트리밍 하이브리드

**6. `next/after` API**
- 응답 반환 후 백그라운드 작업 (로깅, 분석)

**7. `next.config.ts` 지원**
- 설정 파일 TypeScript 작성 가능

**마이그레이션 주의:**
비동기 API 전환이 가장 큰 변경이니, codemod 실행 추천:
```bash
npx @next/codemod@canary upgrade latest
```"""),
    ]),

    # 20. 에러 메시지 검색
    m([
        sys(),
        user("이 에러 뭐야: Cannot find module 'sharp'"),
        assistant('''해당 에러를 검색해보겠습니다.

<tool_call>
{"name": "web_search", "arguments": {"query": "Next.js Cannot find module sharp error fix"}}
</tool_call>'''),
        tool("""[1] Next.js Image Optimization - sharp dependency
Next.js 13+ requires `sharp` for image optimization in production.
Fix: npm install sharp

[2] GitHub Issue #54876 - vercel/next.js
Sharp is no longer bundled automatically since Next 13.5.
Install manually: pnpm add sharp

[3] Vercel Deployment Docs
Sharp is auto-installed on Vercel. For self-hosted:
- Install: npm install sharp
- For Apple Silicon: npm install --platform=darwin --arch=arm64 sharp"""),
        assistant("""**에러: `Cannot find module 'sharp'`**

**원인:**
Next.js 13.5부터 `sharp` 이미지 최적화 라이브러리가 자동 번들링에서 제외되었습니다. `next/image`를 프로덕션에서 사용하려면 직접 설치해야 합니다.

**해결 방법:**

```bash
# 기본
pnpm add sharp
# 또는
npm install sharp
```

**플랫폼별 주의사항:**

- **Apple Silicon (M1/M2/M3):**
  ```bash
  pnpm add sharp --config.arch=arm64 --config.platform=darwin
  ```
- **Docker (Alpine):**
  ```dockerfile
  RUN apk add --no-cache libc6-compat
  RUN npm install sharp
  ```
- **Vercel:** 자동 설치되므로 추가 작업 불필요

**확인:**
설치 후 `node_modules/sharp` 폴더가 생성됐는지, `pnpm list sharp`로 버전이 표시되는지 확인하세요. 여전히 에러가 나면 `rm -rf node_modules && pnpm install`로 재설치해보세요."""),
    ]),

    # 21. 패키지 정보 확인
    m([
        sys(),
        user("zustand 최신 버전이랑 주간 다운로드 얼마나 돼?"),
        assistant('''npm 페이지에서 zustand 정보를 가져오겠습니다.

<tool_call>
{"name": "fetch_url", "arguments": {"url": "https://www.npmjs.com/package/zustand"}}
</tool_call>'''),
        tool("""zustand
A small, fast and scalable bearbones state-management solution using simplified flux principles.

Version: 5.0.2
Last publish: 3 weeks ago
License: MIT
Unpacked Size: 284 kB
Weekly Downloads: 5,847,291
GitHub Stars: 47.8k
Dependencies: 1 (use-sync-external-store)

Install: npm i zustand"""),
        assistant("""**zustand 패키지 정보**

| 항목 | 값 |
|------|-----|
| 최신 버전 | **5.0.2** |
| 릴리스 | 3주 전 |
| 주간 다운로드 | **5,847,291회** (약 584만) |
| GitHub Stars | 47.8k |
| 라이선스 | MIT |
| 패키지 크기 | 284 kB |
| 의존성 | 1개 (`use-sync-external-store`) |

**평가:**
주간 584만 다운로드는 Redux Toolkit(비슷한 수준)과 견줄 만한 규모입니다. 의존성도 1개뿐이라 번들 크기에 부담 없고, 최근 업데이트(3주 전)도 활발하네요. React 상태 관리로 믿고 쓸 만합니다.

**설치:**
```bash
pnpm add zustand@^5.0.2
```

v5는 React 18+ 필요하고, v4 대비 `createStore` API가 약간 변경되었으니 마이그레이션 시 주의하세요."""),
    ]),

    # 22. API 문서 조회
    m([
        sys(),
        user("OpenAI Chat Completions API 파라미터 좀 알려줘"),
        assistant('''공식 문서를 가져오겠습니다.

<tool_call>
{"name": "fetch_url", "arguments": {"url": "https://platform.openai.com/docs/api-reference/chat/create"}}
</tool_call>'''),
        tool("""POST https://api.openai.com/v1/chat/completions

Request body:
- model (string, required): ID of the model
- messages (array, required): [{role, content}]
- temperature (number, 0-2, default 1): Sampling temperature
- top_p (number, 0-1, default 1): Nucleus sampling
- n (integer, default 1): Number of completions
- stream (boolean, default false): SSE streaming
- max_tokens (integer): Max tokens to generate
- presence_penalty (number, -2 to 2): Penalize repeated topics
- frequency_penalty (number, -2 to 2): Penalize repeated tokens
- logit_bias (object): Token-level bias
- user (string): End-user identifier
- tools (array): Tool definitions
- tool_choice (string|object): Control tool usage
- response_format (object): JSON mode etc
- seed (integer): Deterministic sampling"""),
        assistant("""**OpenAI Chat Completions API 주요 파라미터**

**필수:**
- `model`: 모델 ID (예: `gpt-4o`, `gpt-4-turbo`)
- `messages`: `[{role: "system|user|assistant|tool", content: "..."}]`

**샘플링 제어:**
- `temperature` (0~2, 기본 1): 높을수록 창의적, 낮을수록 결정적
- `top_p` (0~1, 기본 1): Nucleus 샘플링. temperature와 함께 조절 비추천
- `seed`: 같은 seed + 동일 요청 시 재현 가능한 결과
- `presence_penalty` (-2~2): 주제 반복 페널티
- `frequency_penalty` (-2~2): 토큰 반복 페널티

**길이/개수:**
- `max_tokens`: 생성 최대 토큰
- `n`: 생성할 응답 개수 (기본 1)

**스트리밍:**
- `stream`: `true`면 SSE로 청크 단위 반환

**Tool Calling:**
- `tools`: 함수 스펙 배열
- `tool_choice`: `auto` | `none` | `required` | 특정 함수 지정

**응답 형식:**
- `response_format`: `{type: "json_object"}`로 JSON 강제

**추천 기본값 (화랑 AI 기준):**
```json
{
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 2048,
  "stream": true
}
```

더 궁금한 파라미터 있으시면 말씀해주세요."""),
    ]),

    # 23. 최신 버전 확인
    m([
        sys(),
        user("Qwen 최신 버전이 뭐야?"),
        assistant('''Qwen 최신 모델 정보를 검색하겠습니다.

<tool_call>
{"name": "web_search", "arguments": {"query": "Qwen latest model version 2026"}}
</tool_call>'''),
        tool("""[1] Alibaba Qwen GitHub (github.com/QwenLM/Qwen)
Latest: Qwen3 (released Jan 2026)
- Qwen3-72B, Qwen3-30B-A3B (MoE), Qwen3-7B, Qwen3-1.8B
- Qwen3-Coder-30B (coding specialist)
- Context: 128K standard, 1M with YaRN

[2] Hugging Face Qwen Collections
- Qwen2.5 series (Sep 2024): 0.5B ~ 72B
- Qwen2.5-Coder: 0.5B ~ 32B
- QwQ-32B-Preview (reasoning, Nov 2024)
- Qwen3 (Jan 2026) - current SOTA

[3] Qwen Blog - Qwen3 Launch
Qwen3 features:
- Hybrid thinking/non-thinking modes
- 119 languages supported
- Agent-focused tool use training"""),
        assistant("""**Qwen 최신 버전 (2026년 4월 기준)**

**최신: Qwen3 (2026년 1월 출시)**

**주요 모델:**
| 모델 | 크기 | 용도 |
|------|------|------|
| Qwen3-72B | 72B | 플래그십 |
| Qwen3-30B-A3B | 30B MoE (3B 활성) | 효율적 고성능 |
| Qwen3-Coder-30B | 30B | 코딩 특화 |
| Qwen3-7B | 7B | 범용 |
| Qwen3-1.8B | 1.8B | 엣지 디바이스 |

**Qwen3 주요 특징:**
- **하이브리드 사고 모드**: thinking / non-thinking 모드 전환 가능
- **119개 언어 지원** (한국어 포함)
- **에이전트 특화**: Tool Use, 함수 호출 전용 학습
- **컨텍스트**: 128K 기본, YaRN 적용 시 1M까지

**이전 세대 (참고):**
- Qwen2.5 (2024.09) - 0.5B~72B
- Qwen2.5-Coder (0.5B~32B)
- QwQ-32B-Preview (추론 특화)

**화랑 AI 기준 추천:**
- 법률/복잡 코딩: Qwen3-72B 또는 DeepSeek V3
- 일반 코딩: **Qwen3-Coder-30B** (현재 라우팅 정책의 Qwen3-Coder-30B와 매칭)
- 일반 대화: Qwen3-7B

기존 `hwarang_model_routing_strategy`에 Qwen3 계열로 업그레이드 검토하실 만합니다."""),
    ]),

    # 24. 블로그/튜토리얼 검색
    m([
        sys(),
        user("React Server Components 어떻게 동작하는지 설명해줘"),
        assistant('''정확한 설명을 위해 좋은 리소스를 검색하겠습니다.

<tool_call>
{"name": "web_search", "arguments": {"query": "React Server Components how it works explained"}}
</tool_call>'''),
        tool("""[1] React Docs - Server Components (react.dev/reference/rsc/server-components)
Server Components run only on the server. They:
- Never ship to client bundle
- Can access DB, filesystem, server-only APIs
- Return serialized UI payload (RSC Payload)
- Cannot use state, effects, event handlers

[2] Dan Abramov - Making Sense of React Server Components
Mental model:
- Server Components = server-rendered, zero JS
- Client Components = hydrated, interactive
- Boundaries marked by "use client"
- Server imports Client OK; Client imports Server NOT OK (except as children)

[3] Vercel Blog - Understanding RSC
Render pipeline:
1. Server: render RSC tree → RSC Payload (serialized)
2. Network: stream payload to client
3. Client: reconcile with existing tree, hydrate Client Components"""),
        assistant("""**React Server Components (RSC) 동작 원리**

**핵심 개념**
RSC는 **서버에서만 실행**되는 컴포넌트입니다. 클라이언트 번들에 JS가 포함되지 않아요.

**컴포넌트 종류**

| 종류 | 실행 위치 | 표시 | 특징 |
|------|----------|------|------|
| Server Component | 서버 only | 기본값 | 번들 0, DB/FS 직접 접근 |
| Client Component | 서버→클라 | `"use client"` | state, effect, 이벤트 가능 |

**렌더링 파이프라인**

```
1. [서버] RSC 트리 렌더링
   ↓
2. [서버] RSC Payload 직렬화 (JSON 유사 포맷)
   ↓
3. [네트워크] 스트리밍 전송
   ↓
4. [클라] 기존 트리와 reconcile
   ↓
5. [클라] Client Component만 hydrate
```

**핵심 규칙**

1. **Server는 Client를 import 가능** (자식으로)
2. **Client는 Server를 직접 import 불가** (props나 children으로만 받음)
3. Server Component에서는 금지:
   - `useState`, `useEffect` 훅
   - 이벤트 핸들러 (`onClick` 등)
   - 브라우저 API (`window`, `localStorage`)

**예시**

```tsx
// app/page.tsx (Server Component - 기본)
import { db } from "@/lib/db"
import LikeButton from "./LikeButton"  // Client Component

export default async function Page() {
  const post = await db.post.findFirst()  // ← 서버에서 직접 DB 접근
  return (
    <article>
      <h1>{post.title}</h1>
      <LikeButton postId={post.id} />   // ← Client Component는 props 받아 hydrate
    </article>
  )
}

// LikeButton.tsx
"use client"
import { useState } from "react"
export default function LikeButton({ postId }) {
  const [liked, setLiked] = useState(false)
  return <button onClick={() => setLiked(!liked)}>{liked ? "♥" : "♡"}</button>
}
```

**장점:** 번들 크기 감소, 직접 데이터 페칭, 보안 (시크릿 노출 없음)
**단점:** 학습 곡선, 디버깅 복잡도 증가

Next.js 13+ App Router가 RSC 기반이고, Remix도 최근 지원 추가했습니다."""),
    ]),

    # 25. GitHub 이슈 검색
    m([
        sys(),
        user("Next.js에서 useSearchParams가 null 반환되는 버그 다른 사람도 겪어?"),
        assistant('''GitHub 이슈를 검색해보겠습니다.

<tool_call>
{"name": "web_search", "arguments": {"query": "Next.js useSearchParams returns null site:github.com"}}
</tool_call>'''),
        tool("""[1] vercel/next.js#58338 - useSearchParams returns null in Server Components
Status: Closed (by design)
Comment: useSearchParams only works in Client Components. In Server Components, use the `searchParams` prop of page.tsx.

[2] vercel/next.js#62515 - useSearchParams null during static rendering
Status: Open (24 reactions)
Comment: When page is statically optimized, useSearchParams returns null until CSR hydrates. Wrap in <Suspense>.

[3] vercel/next.js#49424 - useSearchParams null in middleware
Status: Closed (wontfix)
Comment: useSearchParams is a client hook. Use req.nextUrl.searchParams in middleware."""),
        assistant("""**네, 다른 분들도 겪는 흔한 이슈입니다.**

GitHub 이슈 기준으로 3가지 주요 원인이 있어요.

**1. Server Component에서 사용 (이슈 #58338)**
- `useSearchParams`는 **클라이언트 전용 훅**
- Server Component에서는 쓸 수 없음
- ✅ 해결: 페이지의 `searchParams` prop 사용
```tsx
// app/page.tsx (Server Component)
export default async function Page({ searchParams }: {
  searchParams: Promise<{ q?: string }>
}) {
  const { q } = await searchParams  // Next 15는 비동기
  return <div>검색어: {q}</div>
}
```

**2. 정적 렌더링 중 null (이슈 #62515, 현재 Open)**
- 페이지가 static으로 최적화되면 빌드 시점엔 searchParams를 모름
- 클라이언트에서 hydrate될 때까지 null
- ✅ 해결: `<Suspense>`로 감싸기
```tsx
import { Suspense } from "react"

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <SearchResults />
    </Suspense>
  )
}
```

**3. Middleware에서 사용 (이슈 #49424)**
- 미들웨어는 훅을 쓸 수 없음
- ✅ 해결: `req.nextUrl.searchParams` 사용
```ts
export function middleware(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q")
}
```

**현재 상황을 더 구체적으로 알려주시면** (Server/Client 중 어디서 쓰셨는지, 빌드 시점인지 런타임인지) 정확한 해결책을 좁혀드릴 수 있습니다."""),
    ]),

    # 26. 번역/용어 검색
    m([
        sys(),
        user("JavaScript의 hoisting이 뭐야?"),
        assistant('''hoisting 개념을 정확히 설명하기 위해 검색하겠습니다.

<tool_call>
{"name": "web_search", "arguments": {"query": "JavaScript hoisting explained var let const"}}
</tool_call>'''),
        tool("""[1] MDN - Hoisting
Hoisting is JavaScript's default behavior of moving declarations to the top of the current scope (script/function).
- var: declaration hoisted, initialized as undefined
- let/const: hoisted but in TDZ (Temporal Dead Zone), ReferenceError if accessed before declaration
- function declarations: fully hoisted (can call before definition)
- function expressions / arrow: treated like var/let/const

[2] JavaScript.info - Variable Hoisting
Only declarations are hoisted, not initializations.
Example:
  console.log(x)  // undefined (not ReferenceError)
  var x = 5

  console.log(y)  // ReferenceError: Cannot access 'y' before initialization
  let y = 5"""),
        assistant("""**JavaScript Hoisting (호이스팅)** 은 **변수·함수 선언이 스코프 최상단으로 "끌어올려지는" 것처럼 동작**하는 JS의 특성입니다.

**선언 종류별 동작**

| 선언 | 호이스팅? | 초기화 | 선언 전 접근 시 |
|------|----------|--------|----------------|
| `var` | ✅ | `undefined`로 초기화 | `undefined` (에러 X) |
| `let` | ✅ | ❌ (TDZ) | ReferenceError |
| `const` | ✅ | ❌ (TDZ) | ReferenceError |
| function 선언 | ✅ (전체) | 함수 자체로 | 호출 가능 |
| function 표현식 | var/let/const 규칙 따름 | | |

**예시로 이해하기**

```js
// var - 호이스팅되고 undefined 초기화
console.log(a)   // undefined
var a = 1

// let - TDZ 에 걸림
console.log(b)   // ReferenceError: Cannot access 'b' before initialization
let b = 1

// function 선언 - 완전히 호이스팅
hello()          // "안녕!" ← 호출 가능
function hello() { console.log("안녕!") }

// function 표현식 - var와 동일
hi()             // TypeError: hi is not a function
var hi = function() { console.log("hi") }
```

**TDZ (Temporal Dead Zone / 일시적 사각지대)**
`let`/`const`는 선언 전까지의 구간이 TDZ. 이 구간에서 접근하면 무조건 ReferenceError.

**왜 중요한가?**
- `var`의 예측 못 한 버그 예방 (`let`/`const` 권장 이유)
- 함수 선언 vs 함수 표현식의 차이 이해
- 빌드 도구/번들러의 코드 변환 이해 (Babel의 `let` → `var` 폴리필 등)

**실무 팁:**
모던 JS에서는 `let`/`const`만 쓰고 함수는 상단에 정의하는 습관이 호이스팅 관련 버그를 원천 차단합니다."""),
    ]),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/tools_shell_git.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"쉘+Git+웹 tools: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
