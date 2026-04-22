"""화랑 AI Tool Calling 학습 데이터 (복합 시나리오 + Tool 불필요 판단)"""
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
- git_status(): Git 상태
- git_diff(path: str): Git diff
- git_commit(message: str): 커밋 생성
- web_search(query: str): 웹 검색
- fetch_url(url: str): URL 내용 가져오기
- get_diagnostics(): 에디터 에러/경고

도구 호출 형식:
<tool_call>
{"name": "도구명", "arguments": {"인자": "값"}}
</tool_call>

도구가 필요하면 호출하고, 불필요하면 직접 답변합니다.
간단한 질문(개념 설명, 의견, 계산)은 도구 없이 직접 답변합니다."""

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
    # ====== 복합 시나리오 10건 ======

    # 1. 버그 수정 워크플로우
    m([
        sys(),
        user("타입 에러 있는지 확인하고 고쳐줘. 그리고 테스트도 다시 돌려봐."),
        assistant('''에디터 진단 정보부터 확인하겠습니다.

<tool_call>
{"name": "get_diagnostics", "arguments": {}}
</tool_call>'''),
        tool('[{"file": "src/utils.ts", "line": 15, "severity": "error", "message": "Type \'string\' is not assignable to type \'number\'"}, {"file": "src/utils.ts", "line": 22, "severity": "warning", "message": "\'unused\' is declared but never read"}]'),
        assistant('''`src/utils.ts` 15번째 줄에 타입 에러가 있네요. 먼저 파일 전체를 읽어보겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/utils.ts"}}
</tool_call>'''),
        tool("export function calculate(price: string): number {\n  return price * 1.1;\n}\n\nexport function formatPrice(n: number): string {\n  const unused = 'test';\n  return `₩${n.toLocaleString()}`;\n}"),
        assistant('''문제를 찾았습니다:
1. `calculate` 함수의 `price` 파라미터가 `string`인데 숫자 연산(`* 1.1`)을 하고 있습니다. `number`로 수정해야 합니다.
2. `formatPrice` 안의 `unused` 변수는 사용되지 않으므로 제거합니다.

먼저 타입부터 수정하겠습니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": "src/utils.ts", "old": "export function calculate(price: string): number {\\n  return price * 1.1;\\n}", "new": "export function calculate(price: number): number {\\n  return price * 1.1;\\n}"}}
</tool_call>'''),
        tool("파일 수정 완료: src/utils.ts"),
        assistant('''이어서 사용되지 않는 변수를 제거하겠습니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": "src/utils.ts", "old": "  const unused = 'test';\\n  return `₩${n.toLocaleString()}`;", "new": "  return `₩${n.toLocaleString()}`;"}}
</tool_call>'''),
        tool("파일 수정 완료: src/utils.ts"),
        assistant('''이제 테스트를 돌려서 회귀가 없는지 확인하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm test src/utils.test.ts"}}
</tool_call>'''),
        tool("PASS src/utils.test.ts\n  calculate\n    ✓ 10% 세금을 더한 값을 반환한다 (3 ms)\n    ✓ 0원도 정상 처리된다 (1 ms)\n  formatPrice\n    ✓ 원화 기호를 붙여 반환한다 (2 ms)\n\nTests: 3 passed, 3 total"),
        assistant('''모든 수정이 완료되었습니다.

**수정 내역**
- `calculate(price: string)` → `calculate(price: number)` : 타입 에러 해결
- `formatPrice` 내부의 사용되지 않는 `unused` 변수 제거

**테스트 결과**
- 3/3 통과

타입 에러와 경고 모두 사라졌고 기존 테스트도 그대로 통과했습니다.'''),
    ]),

    # 2. 새 기능 추가
    m([
        sys(),
        user("src/components 안에 기존 컴포넌트 구조 참고해서 Toast 컴포넌트 추가해줘."),
        assistant('''먼저 기존 컴포넌트 구조를 확인하겠습니다.

<tool_call>
{"name": "list_directory", "arguments": {"path": "src/components"}}
</tool_call>'''),
        tool("Button.tsx\nModal.tsx\nindex.ts"),
        assistant('''`Button.tsx`의 스타일 패턴을 참고하고, `index.ts`에 재수출해야겠습니다. 먼저 Button을 읽겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/components/Button.tsx"}}
</tool_call>'''),
        tool("import { forwardRef, ButtonHTMLAttributes } from 'react';\nimport { cn } from '../lib/cn';\n\ninterface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {\n  variant?: 'primary' | 'secondary';\n}\n\nexport const Button = forwardRef<HTMLButtonElement, ButtonProps>(\n  ({ className, variant = 'primary', ...props }, ref) => (\n    <button\n      ref={ref}\n      className={cn('px-4 py-2 rounded', variant === 'primary' && 'bg-blue-600 text-white', className)}\n      {...props}\n    />\n  )\n);\nButton.displayName = 'Button';"),
        assistant('''패턴 파악했습니다. `forwardRef` + `cn` 유틸 + `variant`를 쓰는 스타일이네요. 같은 스타일로 `Toast.tsx`를 생성하겠습니다.

<tool_call>
{"name": "write_file", "arguments": {"path": "src/components/Toast.tsx", "content": "import { forwardRef, HTMLAttributes } from 'react';\\nimport { cn } from '../lib/cn';\\n\\ninterface ToastProps extends HTMLAttributes<HTMLDivElement> {\\n  variant?: 'info' | 'success' | 'error';\\n  onClose?: () => void;\\n}\\n\\nexport const Toast = forwardRef<HTMLDivElement, ToastProps>(\\n  ({ className, variant = 'info', onClose, children, ...props }, ref) => (\\n    <div\\n      ref={ref}\\n      role=\\"status\\"\\n      className={cn(\\n        'fixed bottom-4 right-4 px-4 py-3 rounded shadow-lg flex items-center gap-3',\\n        variant === 'info' && 'bg-slate-800 text-white',\\n        variant === 'success' && 'bg-green-600 text-white',\\n        variant === 'error' && 'bg-red-600 text-white',\\n        className\\n      )}\\n      {...props}\\n    >\\n      <span>{children}</span>\\n      {onClose && (\\n        <button onClick={onClose} aria-label=\\"닫기\\" className=\\"opacity-70 hover:opacity-100\\">×</button>\\n      )}\\n    </div>\\n  )\\n);\\nToast.displayName = 'Toast';\\n"}}
</tool_call>'''),
        tool("파일 생성: src/components/Toast.tsx (28 lines)"),
        assistant('''마지막으로 `index.ts`에 재수출을 추가하겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/components/index.ts"}}
</tool_call>'''),
        tool("export { Button } from './Button';\nexport { Modal } from './Modal';"),
        assistant('''Toast export를 추가합니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": "src/components/index.ts", "old": "export { Modal } from './Modal';", "new": "export { Modal } from './Modal';\\nexport { Toast } from './Toast';"}}
</tool_call>'''),
        tool("파일 수정 완료: src/components/index.ts"),
        assistant('''`Toast` 컴포넌트 추가 완료입니다.

**만든 파일**
- `src/components/Toast.tsx` : `forwardRef` + `variant`(info/success/error) + 선택적 `onClose` 버튼, 우하단 고정

**기존 패턴 유지**
- `cn` 유틸 사용
- `forwardRef` + `displayName`
- `variant`별 Tailwind 조건부 스타일

**재수출**
- `src/components/index.ts`에 `Toast` 추가

사용 예시:
```tsx
import { Toast } from '@/components';
<Toast variant="success" onClose={() => setOpen(false)}>저장되었습니다</Toast>
```'''),
    ]),

    # 3. 리팩토링
    m([
        sys(),
        user("코드에 fetch 직접 쓰는 곳 다 찾아서 apiClient 헬퍼 쓰도록 리팩토링해줘."),
        assistant('''먼저 `fetch(` 호출이 어디에 흩어져 있는지 검색하겠습니다.

<tool_call>
{"name": "search_code", "arguments": {"pattern": "fetch\\\\(", "path": "src"}}
</tool_call>'''),
        tool("src/pages/Users.tsx:12:  const res = await fetch('/api/users');\nsrc/pages/Posts.tsx:8:  const res = await fetch('/api/posts');\nsrc/hooks/useProfile.ts:15:  const res = await fetch(`/api/profile/${id}`);"),
        assistant('''세 군데 있네요. `apiClient`가 어떻게 생겼는지도 확인해야 합니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/lib/apiClient.ts"}}
</tool_call>'''),
        tool("export const apiClient = {\n  get: <T>(url: string) => fetch(url).then(r => r.json() as Promise<T>),\n  post: <T>(url: string, body: unknown) =>\n    fetch(url, { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }).then(r => r.json() as Promise<T>),\n};"),
        assistant('''`apiClient.get`로 바꿔주면 됩니다. 각 파일을 읽고 고치겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/pages/Users.tsx"}}
</tool_call>'''),
        tool("import { useEffect, useState } from 'react';\nimport type { User } from '../types';\n\nexport function Users() {\n  const [users, setUsers] = useState<User[]>([]);\n  useEffect(() => {\n    (async () => {\n      const res = await fetch('/api/users');\n      const data = await res.json();\n      setUsers(data);\n    })();\n  }, []);\n  return <ul>{users.map(u => <li key={u.id}>{u.name}</li>)}</ul>;\n}"),
        assistant('''`Users.tsx`부터 수정합니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": "src/pages/Users.tsx", "old": "import { useEffect, useState } from 'react';\\nimport type { User } from '../types';", "new": "import { useEffect, useState } from 'react';\\nimport type { User } from '../types';\\nimport { apiClient } from '../lib/apiClient';"}}
</tool_call>'''),
        tool("파일 수정 완료: src/pages/Users.tsx"),
        assistant('''이어서 fetch 호출부를 교체합니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": "src/pages/Users.tsx", "old": "      const res = await fetch('/api/users');\\n      const data = await res.json();\\n      setUsers(data);", "new": "      const data = await apiClient.get<User[]>('/api/users');\\n      setUsers(data);"}}
</tool_call>'''),
        tool("파일 수정 완료: src/pages/Users.tsx"),
        assistant('''`Posts.tsx`도 같은 방식으로 진행합니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/pages/Posts.tsx"}}
</tool_call>'''),
        tool("import { useEffect, useState } from 'react';\nimport type { Post } from '../types';\n\nexport function Posts() {\n  const [posts, setPosts] = useState<Post[]>([]);\n  useEffect(() => {\n    (async () => {\n      const res = await fetch('/api/posts');\n      setPosts(await res.json());\n    })();\n  }, []);\n  return <div>{posts.length}</div>;\n}"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "src/pages/Posts.tsx", "old": "import type { Post } from '../types';", "new": "import type { Post } from '../types';\\nimport { apiClient } from '../lib/apiClient';"}}
</tool_call>'''),
        tool("파일 수정 완료: src/pages/Posts.tsx"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "src/pages/Posts.tsx", "old": "      const res = await fetch('/api/posts');\\n      setPosts(await res.json());", "new": "      const data = await apiClient.get<Post[]>('/api/posts');\\n      setPosts(data);"}}
</tool_call>'''),
        tool("파일 수정 완료: src/pages/Posts.tsx"),
        assistant('''마지막으로 `useProfile.ts`입니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/hooks/useProfile.ts"}}
</tool_call>'''),
        tool("import { useEffect, useState } from 'react';\nimport type { Profile } from '../types';\n\nexport function useProfile(id: string) {\n  const [profile, setProfile] = useState<Profile | null>(null);\n  useEffect(() => {\n    (async () => {\n      const res = await fetch(`/api/profile/${id}`);\n      setProfile(await res.json());\n    })();\n  }, [id]);\n  return profile;\n}"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "src/hooks/useProfile.ts", "old": "import type { Profile } from '../types';", "new": "import type { Profile } from '../types';\\nimport { apiClient } from '../lib/apiClient';"}}
</tool_call>'''),
        tool("파일 수정 완료: src/hooks/useProfile.ts"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "src/hooks/useProfile.ts", "old": "      const res = await fetch(`/api/profile/${id}`);\\n      setProfile(await res.json());", "new": "      const data = await apiClient.get<Profile>(`/api/profile/${id}`);\\n      setProfile(data);"}}
</tool_call>'''),
        tool("파일 수정 완료: src/hooks/useProfile.ts"),
        assistant('''리팩토링 완료했습니다.

**변경 파일 (3건)**
- `src/pages/Users.tsx` : `fetch` → `apiClient.get<User[]>`
- `src/pages/Posts.tsx` : `fetch` → `apiClient.get<Post[]>`
- `src/hooks/useProfile.ts` : `fetch` → `apiClient.get<Profile>`

**얻은 이점**
- 제네릭으로 반환 타입이 명시됨
- `res.json()` 반복 제거
- 향후 헤더·에러 처리는 `apiClient` 한 곳에서만 수정하면 됩니다

타입 체크 한번 돌려보시고 이상 있으면 알려주세요.'''),
    ]),

    # 4. 환경 설정
    m([
        sys(),
        user("방금 클론한 프로젝트야. .env 만들고 개발 서버 띄워줘."),
        assistant('''`.env.example`부터 확인해 어떤 키들이 필요한지 보겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": ".env.example"}}
</tool_call>'''),
        tool("# 개발용 환경 변수 예시\nDATABASE_URL=postgresql://user:pass@localhost:5432/mydb\nNEXT_PUBLIC_API_URL=http://localhost:3000/api\nJWT_SECRET=change-me-in-production\nNODE_ENV=development"),
        assistant('''로컬 개발용으로 그대로 가져다 쓰되 `JWT_SECRET`만 로컬용 랜덤 값으로 바꿔 `.env`를 생성하겠습니다.

<tool_call>
{"name": "write_file", "arguments": {"path": ".env", "content": "# 로컬 개발 환경 (커밋 금지)\\nDATABASE_URL=postgresql://user:pass@localhost:5432/mydb\\nNEXT_PUBLIC_API_URL=http://localhost:3000/api\\nJWT_SECRET=local-dev-secret-do-not-use-in-prod\\nNODE_ENV=development\\n"}}
</tool_call>'''),
        tool("파일 생성: .env (5 lines)"),
        assistant('''이제 개발 서버를 실행하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm dev"}}
</tool_call>'''),
        tool("> dev\n> next dev\n\n  ▲ Next.js 14.2.3\n  - Local:        http://localhost:3000\n  - Environments: .env\n\n ✓ Ready in 2.1s"),
        assistant('''개발 서버가 떴습니다.

**진행 사항**
1. `.env.example`을 베이스로 `.env` 생성 (`JWT_SECRET`만 로컬용으로 교체)
2. `pnpm dev` 실행 → http://localhost:3000 에서 2.1초 만에 기동

**주의**
- `.env`는 `.gitignore`에 들어있는지 확인하세요 (커밋되면 로컬 시크릿이 노출됩니다)
- 프로덕션에서는 반드시 `JWT_SECRET`을 강력한 값으로 다시 생성하세요 (예: `openssl rand -hex 32`)'''),
    ]),

    # 5. 의존성 추가 + 사용
    m([
        sys(),
        user("zod 설치하고 src/schemas/user.ts에 간단한 스키마 예시 작성해줘."),
        assistant('''먼저 zod를 설치하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm add zod"}}
</tool_call>'''),
        tool("Packages: +1\n+ zod 3.23.8\n\nProgress: resolved 1, downloaded 1\nDone in 1.8s"),
        assistant('''설치 완료. 이제 `src/schemas/user.ts`에 User 스키마를 작성하겠습니다.

<tool_call>
{"name": "write_file", "arguments": {"path": "src/schemas/user.ts", "content": "import { z } from 'zod';\\n\\nexport const UserSchema = z.object({\\n  id: z.string().uuid(),\\n  email: z.string().email(),\\n  name: z.string().min(1).max(50),\\n  age: z.number().int().min(0).max(120).optional(),\\n  role: z.enum(['admin', 'member', 'guest']).default('member'),\\n  createdAt: z.coerce.date(),\\n});\\n\\nexport type User = z.infer<typeof UserSchema>;\\n\\nexport const CreateUserSchema = UserSchema.omit({ id: true, createdAt: true });\\nexport type CreateUserInput = z.infer<typeof CreateUserSchema>;\\n"}}
</tool_call>'''),
        tool("파일 생성: src/schemas/user.ts (14 lines)"),
        assistant('''완료했습니다.

**설치**
- `zod@3.23.8` 추가

**생성 파일**
- `src/schemas/user.ts`
  - `UserSchema` : 전체 사용자 모델 (uuid/email/이름/나이/역할/생성일)
  - `User` : `z.infer`로 뽑은 TypeScript 타입
  - `CreateUserSchema` : `id`, `createdAt` 제외한 입력용 서브스키마
  - `CreateUserInput` : 생성 입력 타입

사용 예:
```ts
const parsed = CreateUserSchema.parse(req.body);
// 실패하면 ZodError 던짐
```'''),
    ]),

    # 6. Git 워크플로우
    m([
        sys(),
        user("현재 변경사항 검토하고, 괜찮으면 적절한 메시지로 커밋해줘."),
        assistant('''먼저 변경된 파일 목록을 확인하겠습니다.

<tool_call>
{"name": "git_status", "arguments": {}}
</tool_call>'''),
        tool("On branch feature/login-fix\nChanges not staged for commit:\n  modified:   src/auth/login.ts\n  modified:   src/auth/login.test.ts"),
        assistant('''로그인 관련 파일 2개가 수정되었습니다. 실제 변경 내용을 보겠습니다.

<tool_call>
{"name": "git_diff", "arguments": {"path": "src/auth/login.ts"}}
</tool_call>'''),
        tool("@@ -12,7 +12,10 @@\n export async function login(email: string, password: string) {\n-  const user = await db.user.findUnique({ where: { email } });\n+  const user = await db.user.findUnique({ where: { email: email.toLowerCase().trim() } });\n+  if (!user) throw new AuthError('INVALID_CREDENTIALS');\n   const ok = await bcrypt.compare(password, user.passwordHash);\n+  if (!ok) throw new AuthError('INVALID_CREDENTIALS');\n   return issueToken(user);\n }"),
        assistant('''두 가지 개선이 있네요:
1. 이메일을 소문자+공백제거로 정규화
2. 사용자 없음/비밀번호 불일치를 같은 에러(`INVALID_CREDENTIALS`)로 통일 → 타이밍/메시지 기반 계정 탐색 방지

테스트 쪽 변경도 봅니다.

<tool_call>
{"name": "git_diff", "arguments": {"path": "src/auth/login.test.ts"}}
</tool_call>'''),
        tool("@@ -20,4 +20,12 @@\n+  it('이메일 대소문자·공백을 무시하고 로그인한다', async () => {\n+    await expect(login('  User@Example.com  ', 'pw')).resolves.toBeTruthy();\n+  });\n+\n+  it('존재하지 않는 사용자와 틀린 비번을 구분하지 않는다', async () => {\n+    await expect(login('nope@a.com', 'x')).rejects.toThrow('INVALID_CREDENTIALS');\n+    await expect(login('user@a.com', 'wrong')).rejects.toThrow('INVALID_CREDENTIALS');\n+  });"),
        assistant('''변경 내용과 테스트가 잘 맞습니다. 커밋 메시지는 보안 의도를 드러내는 게 좋겠네요.

<tool_call>
{"name": "git_commit", "arguments": {"message": "fix(auth): 이메일 정규화 및 자격증명 오류 통일\\n\\n- email을 toLowerCase+trim으로 정규화해 입력 편차 흡수\\n- 사용자 없음/비밀번호 불일치를 INVALID_CREDENTIALS로 통일해 계정 열거 방어\\n- 해당 동작을 검증하는 테스트 2건 추가"}}
</tool_call>'''),
        tool("[feature/login-fix 9a1b2c3] fix(auth): 이메일 정규화 및 자격증명 오류 통일\n 2 files changed, 13 insertions(+), 2 deletions(-)"),
        assistant('''커밋 완료되었습니다.

**검토 요약**
- `src/auth/login.ts` : 이메일 정규화 + 에러 메시지 통일 (계정 열거 공격 방어)
- `src/auth/login.test.ts` : 두 시나리오 테스트 추가

**커밋**
- `9a1b2c3` on `feature/login-fix`
- 메시지가 "왜"를 담도록 작성 (보안 의도 명시)

PR 올릴 준비가 된 것 같습니다.'''),
    ]),

    # 7. 프로젝트 초기화
    m([
        sys(),
        user("hello-ts 라는 TypeScript 노드 프로젝트 새로 하나 만들어줘."),
        assistant('''디렉토리부터 만들겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "mkdir -p hello-ts/src"}}
</tool_call>'''),
        tool("디렉토리 생성 완료"),
        assistant('''`package.json`을 작성합니다.

<tool_call>
{"name": "write_file", "arguments": {"path": "hello-ts/package.json", "content": "{\\n  \\"name\\": \\"hello-ts\\",\\n  \\"version\\": \\"0.1.0\\",\\n  \\"private\\": true,\\n  \\"type\\": \\"module\\",\\n  \\"scripts\\": {\\n    \\"build\\": \\"tsc\\",\\n    \\"start\\": \\"node dist/index.js\\",\\n    \\"dev\\": \\"tsx watch src/index.ts\\"\\n  },\\n  \\"devDependencies\\": {\\n    \\"typescript\\": \\"^5.5.0\\",\\n    \\"tsx\\": \\"^4.16.0\\",\\n    \\"@types/node\\": \\"^20.14.0\\"\\n  }\\n}\\n"}}
</tool_call>'''),
        tool("파일 생성: hello-ts/package.json"),
        assistant('''`tsconfig.json`도 작성합니다.

<tool_call>
{"name": "write_file", "arguments": {"path": "hello-ts/tsconfig.json", "content": "{\\n  \\"compilerOptions\\": {\\n    \\"target\\": \\"ES2022\\",\\n    \\"module\\": \\"ES2022\\",\\n    \\"moduleResolution\\": \\"bundler\\",\\n    \\"outDir\\": \\"dist\\",\\n    \\"rootDir\\": \\"src\\",\\n    \\"strict\\": true,\\n    \\"esModuleInterop\\": true,\\n    \\"skipLibCheck\\": true,\\n    \\"forceConsistentCasingInFileNames\\": true\\n  },\\n  \\"include\\": [\\"src/**/*\\"]\\n}\\n"}}
</tool_call>'''),
        tool("파일 생성: hello-ts/tsconfig.json"),
        assistant('''엔트리 파일도 하나 만들겠습니다.

<tool_call>
{"name": "write_file", "arguments": {"path": "hello-ts/src/index.ts", "content": "const greet = (name: string): string => `안녕하세요, ${name}!`;\\n\\nconsole.log(greet('화랑'));\\n"}}
</tool_call>'''),
        tool("파일 생성: hello-ts/src/index.ts"),
        assistant('''마지막으로 의존성을 설치합니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "cd hello-ts && pnpm install"}}
</tool_call>'''),
        tool("Packages: +3\n+ typescript 5.5.4\n+ tsx 4.16.2\n+ @types/node 20.14.10\n\nDone in 3.4s"),
        assistant('''프로젝트 스캐폴딩 완료입니다.

**구성**
```
hello-ts/
├── package.json   (type: module, 스크립트 3개)
├── tsconfig.json  (ES2022, strict, bundler resolution)
└── src/
    └── index.ts   (간단한 greet 예제)
```

**다음 명령**
- 개발: `cd hello-ts && pnpm dev`
- 빌드: `pnpm build`
- 실행: `pnpm start`

바로 돌려봐도 되고, 필요한 라이브러리(express/zod 등) 있으면 말씀해 주세요.'''),
    ]),

    # 8. 디버깅
    m([
        sys(),
        user("테스트가 깨졌어. 원인 찾아서 고쳐줘."),
        assistant('''먼저 실패 내용부터 확인하겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm test"}}
</tool_call>'''),
        tool("FAIL src/cart.test.ts\n  ● Cart > applies 10% discount for 3+ items\n\n    expect(received).toBe(expected)\n    Expected: 27000\n    Received: 30000\n\n      at Object.<anonymous> (src/cart.test.ts:18:26)\n\nTests: 1 failed, 4 passed"),
        assistant('''3개 이상일 때 10% 할인이 적용 안 되어 `30000` 그대로 나오고 있네요. 테스트부터 읽어보겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/cart.test.ts"}}
</tool_call>'''),
        tool("import { total } from './cart';\n\ntest('applies 10% discount for 3+ items', () => {\n  const items = [\n    { price: 10000, qty: 1 },\n    { price: 10000, qty: 1 },\n    { price: 10000, qty: 1 },\n  ];\n  expect(total(items)).toBe(27000);\n});"),
        assistant('''3개 각 10,000원이면 30,000의 10% 할인 = 27,000이 기대값입니다. 구현을 보겠습니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "src/cart.ts"}}
</tool_call>'''),
        tool("interface Item { price: number; qty: number; }\n\nexport function total(items: Item[]): number {\n  const sum = items.reduce((s, i) => s + i.price * i.qty, 0);\n  if (items.length > 3) {\n    return sum * 0.9;\n  }\n  return sum;\n}"),
        assistant('''원인을 찾았습니다. 조건이 `items.length > 3`이라 3개일 때는 할인이 안 걸립니다. `>= 3`으로 바꿔야 합니다.

<tool_call>
{"name": "edit_file", "arguments": {"path": "src/cart.ts", "old": "  if (items.length > 3) {", "new": "  if (items.length >= 3) {"}}
</tool_call>'''),
        tool("파일 수정 완료: src/cart.ts"),
        assistant('''다시 테스트를 돌립니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm test"}}
</tool_call>'''),
        tool("PASS src/cart.test.ts\n  Cart\n    ✓ applies 10% discount for 3+ items (2 ms)\n    ✓ no discount for 2 items\n    ✓ no discount for empty cart\n    ✓ correct total with mixed qty\n    ✓ handles zero price\n\nTests: 5 passed, 5 total"),
        assistant('''문제 해결했습니다.

**원인**
- `items.length > 3` → 4개 이상일 때만 할인. 테스트 요구사항은 "3개 이상"이었음 (off-by-one).

**수정**
- `src/cart.ts` : `> 3` → `>= 3`

**결과**
- 5/5 테스트 통과

이런 경계 조건은 조건에 `=` 포함 여부를 쓸 때마다 주석으로 "3개 이상"처럼 문서화해두면 다음 실수 방지에 좋습니다.'''),
    ]),

    # 9. 문서 업데이트
    m([
        sys(),
        user("루트의 모든 md 문서에서 예전 명령어 `npm run dev`를 `pnpm dev`로 통일해줘."),
        assistant('''먼저 루트의 md 파일들을 찾습니다.

<tool_call>
{"name": "glob_files", "arguments": {"pattern": "*.md"}}
</tool_call>'''),
        tool("README.md\nCONTRIBUTING.md\nCHANGELOG.md"),
        assistant('''세 파일을 차례로 확인합니다.

<tool_call>
{"name": "read_file", "arguments": {"path": "README.md"}}
</tool_call>'''),
        tool("# My App\n\n## 개발\n\n```bash\nnpm install\nnpm run dev\n```\n\n서버가 http://localhost:3000 에서 뜹니다."),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "README.md", "old": "npm install\\nnpm run dev", "new": "pnpm install\\npnpm dev"}}
</tool_call>'''),
        tool("파일 수정 완료: README.md"),
        assistant('''<tool_call>
{"name": "read_file", "arguments": {"path": "CONTRIBUTING.md"}}
</tool_call>'''),
        tool("# Contributing\n\n로컬에서 `npm run dev`로 서버를 띄운 뒤 PR을 올려주세요.\n테스트: `npm run test`"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "CONTRIBUTING.md", "old": "로컬에서 `npm run dev`로 서버를 띄운 뒤 PR을 올려주세요.\\n테스트: `npm run test`", "new": "로컬에서 `pnpm dev`로 서버를 띄운 뒤 PR을 올려주세요.\\n테스트: `pnpm test`"}}
</tool_call>'''),
        tool("파일 수정 완료: CONTRIBUTING.md"),
        assistant('''<tool_call>
{"name": "read_file", "arguments": {"path": "CHANGELOG.md"}}
</tool_call>'''),
        tool("# Changelog\n\n## 0.1.0\n- 초기 릴리스\n- `npm run dev`로 개발 서버 실행 가능"),
        assistant('''<tool_call>
{"name": "edit_file", "arguments": {"path": "CHANGELOG.md", "old": "- `npm run dev`로 개발 서버 실행 가능", "new": "- `pnpm dev`로 개발 서버 실행 가능"}}
</tool_call>'''),
        tool("파일 수정 완료: CHANGELOG.md"),
        assistant('''문서 통일 완료입니다.

**수정 파일 (3건)**
- `README.md` : `npm install` / `npm run dev` → `pnpm install` / `pnpm dev`
- `CONTRIBUTING.md` : `npm run dev` / `npm run test` → `pnpm dev` / `pnpm test`
- `CHANGELOG.md` : 0.1.0 항목 내 명령 교체

**참고**
- `package-lock.json`이 남아있으면 함께 삭제하고 `pnpm-lock.yaml`만 커밋하시는 걸 권장합니다.'''),
    ]),

    # 10. 배포 준비
    m([
        sys(),
        user("배포 전 점검 좀 해줘. 에러 없고 빌드/테스트 통과하면 릴리스 커밋까지."),
        assistant('''먼저 에디터 진단부터 확인합니다.

<tool_call>
{"name": "get_diagnostics", "arguments": {}}
</tool_call>'''),
        tool("[]"),
        assistant('''진단 깨끗합니다. 프로덕션 빌드를 돌려 보겠습니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm build"}}
</tool_call>'''),
        tool("> build\n> next build\n\nRoute (app)                         Size     First Load JS\n┌ ○ /                               1.2 kB         88 kB\n└ ○ /about                          0.8 kB         87 kB\n\n ✓ Compiled successfully\n ✓ Collecting page data\n ✓ Generating static pages (2/2)\n ✓ Finalizing page optimization"),
        assistant('''빌드 성공. 테스트도 돌립니다.

<tool_call>
{"name": "run_command", "arguments": {"command": "pnpm test -- --run"}}
</tool_call>'''),
        tool("✓ src/utils.test.ts (4)\n✓ src/cart.test.ts (5)\n✓ src/auth/login.test.ts (6)\n\nTest Files  3 passed (3)\nTests  15 passed (15)\nDuration  1.24s"),
        assistant('''전부 통과했습니다. 릴리스 커밋을 만들겠습니다.

<tool_call>
{"name": "git_commit", "arguments": {"message": "chore(release): 배포 준비 완료\\n\\n- 진단 0건, 타입 체크 통과\\n- pnpm build 성공 (정적 페이지 2개 생성)\\n- 테스트 15/15 통과 (utils, cart, auth/login)"}}
</tool_call>'''),
        tool("[main f0e1d2c] chore(release): 배포 준비 완료\n 1 file changed, 1 insertion(+), 1 deletion(-)"),
        assistant('''배포 전 점검 모두 통과했습니다.

**점검 결과**
| 항목 | 결과 |
|---|---|
| 진단(에러/경고) | 0건 |
| `pnpm build` | 성공 (2 페이지) |
| `pnpm test` | 15/15 통과 |

**릴리스 커밋**
- `f0e1d2c chore(release): 배포 준비 완료`

이제 태그 달고(`git tag v0.x.0`) 프로덕션 파이프라인에 올리시면 됩니다.'''),
    ]),

    # ====== 도구 불필요 판단 7건 ======

    # 11. 개념 설명
    m([
        sys(),
        user("클로저가 뭐야?"),
        assistant("클로저(Closure)는 **함수가 자신이 선언된 렉시컬 스코프의 변수를 계속 기억하고 접근할 수 있는 현상**입니다.\n\n```javascript\nfunction counter() {\n  let count = 0;\n  return () => ++count;\n}\n\nconst c = counter();\nc(); // 1\nc(); // 2\nc(); // 3\n```\n\n여기서 `counter`는 이미 실행이 끝났지만, 반환된 내부 함수가 `count`를 계속 참조하기 때문에 `count`는 메모리에서 해제되지 않고 살아남습니다. 이게 클로저의 핵심입니다.\n\n**실무에서 자주 쓰는 곳**\n- 상태 은닉(모듈 패턴, 사설 변수)\n- 이벤트 핸들러에서 특정 값 캡처\n- React의 `useCallback`/`useEffect` 내부에서의 stale closure 문제 (의존성 배열이 중요한 이유)\n- 디바운스/스로틀 같은 고차 함수 구현\n\n**주의점**\n- 내부 함수가 외부 변수를 계속 붙잡으면 GC가 해당 변수를 회수하지 못해 메모리 누수로 이어질 수 있습니다.\n- 반복문 안에서 `var`로 변수를 만들고 클로저를 만들면 모두 같은 변수를 참조하는 고전 버그가 생깁니다 (`let`으로 해결)."),
    ]),

    # 12. 코드 스니펫
    m([
        sys(),
        user("querySelector 쓰는 법 간단한 예제 하나만."),
        assistant("```html\n<ul id=\"list\">\n  <li class=\"item\">사과</li>\n  <li class=\"item selected\">바나나</li>\n  <li class=\"item\">체리</li>\n</ul>\n\n<script>\n  // 1) id로 단일 요소\n  const list = document.querySelector('#list');\n\n  // 2) 클래스로 첫 번째 매칭\n  const first = document.querySelector('.item');\n  console.log(first.textContent); // \"사과\"\n\n  // 3) 복합 선택자 - 선택된 항목만\n  const selected = document.querySelector('#list .item.selected');\n  console.log(selected.textContent); // \"바나나\"\n\n  // 4) 여러 개를 가져오려면 querySelectorAll\n  document.querySelectorAll('.item').forEach(el => {\n    el.addEventListener('click', () => el.classList.toggle('selected'));\n  });\n</script>\n```\n\n핵심 포인트:\n- `querySelector`는 **첫 번째 매칭 요소**만 반환, 없으면 `null`\n- `querySelectorAll`은 **NodeList** 반환 (forEach 가능, map은 불가 → 필요하면 `Array.from`)\n- 인자는 CSS 선택자 문자열이면 뭐든 OK (`'div.card > p:first-child'` 같은 것도)"),
    ]),

    # 13. 디자인 조언
    m([
        sys(),
        user("REST vs GraphQL 어떤 게 좋아?"),
        assistant("정답은 없고 **제약 조건에 따라 달라집니다**. 제가 실무에서 쓰는 판단 기준을 공유할게요.\n\n**REST가 유리한 경우**\n- 리소스가 명확하고 CRUD 중심 (예: 회원, 게시글, 주문)\n- HTTP 캐시(CDN/브라우저)를 적극 활용하고 싶을 때\n- 공개 API라 학습 곡선이 낮아야 할 때\n- 파일 업로드, 바이너리 응답이 많은 경우\n\n**GraphQL이 유리한 경우**\n- 한 화면에서 여러 리소스를 조합해야 해서 REST로는 엔드포인트가 폭증하는 경우\n- 모바일/웹 클라이언트가 요구하는 필드가 서로 다른 경우 (오버/언더 페치 방지)\n- 타입 주도 개발을 원하고, 코드젠을 적극 쓰는 팀\n- BFF 계층이 여러 백엔드를 하나로 모아야 할 때\n\n**실전 팁**\n- \"대부분은 REST, 특정 화면만 GraphQL\" 조합도 자주 씁니다.\n- GraphQL을 쓰면 N+1, 쿼리 깊이 제한, 권한 필드별 제어 같은 문제가 새로 생깁니다. 공짜가 아닙니다.\n- REST 써도 OpenAPI + 코드젠 조합이면 타입 안정성 어느 정도 확보됩니다.\n\n**제 기본값**\n- 내부 서비스/간단한 앱: REST + OpenAPI\n- 모바일·웹을 동시에 운영하는 제품: BFF를 GraphQL로, 백엔드 마이크로서비스는 REST/gRPC\n\n당장 상황이 \"클라이언트 요구 필드가 화면마다 다르고 엔드포인트가 늘어나 힘든 상태\"라면 GraphQL 도입 가치를 진지하게 봐도 됩니다. 그게 아니면 REST로 충분한 경우가 많아요."),
    ]),

    # 14. 에러 원인 설명
    m([
        sys(),
        user("이 에러 왜 뜨는지 알려줘:\n\nTypeError: Cannot read properties of undefined (reading 'map')\n    at UserList (UserList.tsx:12:20)"),
        assistant("메시지를 그대로 해석하면: **`UserList.tsx` 12번째 줄에서 `undefined` 값에 대해 `.map`을 호출**했습니다.\n\n전형적인 원인은 이 중 하나입니다.\n\n1. **데이터 로딩 전 렌더링**\n   ```tsx\n   const { data } = useQuery(...); // 처음엔 undefined\n   return <ul>{data.map(...)}</ul>; // 여기서 터짐\n   ```\n   → `data`가 비동기라 처음 렌더 때 `undefined`.\n\n2. **props 기본값 없음**\n   ```tsx\n   function UserList({ users }) {\n     return users.map(...) // users가 안 넘어오면 undefined\n   }\n   ```\n\n3. **API 응답 형태가 예상과 다름**\n   - 서버가 `{ users: [...] }`를 주는데 클라이언트가 `res.map` 같은 식으로 배열 가정.\n\n**해결 패턴**\n```tsx\n// 가드\nif (!users) return <Skeleton />;\nreturn <ul>{users.map(u => <li key={u.id}>{u.name}</li>)}</ul>;\n\n// 또는 기본값\nfunction UserList({ users = [] }: { users?: User[] }) { ... }\n\n// 또는 옵셔널 체이닝\n{users?.map(u => ...)}\n```\n\n12번째 줄에서 무엇을 `.map` 하는지(`users.map`인지 `data.map`인지 등)를 보면 위 3가지 중 어느 케이스인지 바로 구분됩니다. 해당 줄 한 줄 보여주시면 정확한 패치까지 제시해 드릴게요."),
    ]),

    # 15. 문법 질문
    m([
        sys(),
        user("TypeScript 제네릭 문법?"),
        assistant("기본 골격은 `<T>` 같은 **타입 파라미터**를 함수/클래스/타입에 붙이는 겁니다.\n\n**함수 제네릭**\n```ts\nfunction identity<T>(value: T): T {\n  return value;\n}\n\nidentity<string>('hi'); // 명시\nidentity(42);           // 추론 (T = number)\n```\n\n**배열·유틸 제네릭**\n```ts\nfunction first<T>(arr: T[]): T | undefined {\n  return arr[0];\n}\nfirst([1, 2, 3]); // number | undefined\n```\n\n**제약 (extends)**\n```ts\nfunction getId<T extends { id: string }>(x: T): string {\n  return x.id;\n}\n```\n→ `T`는 반드시 `id: string`을 가진 타입이어야 함.\n\n**기본값**\n```ts\ntype ApiResponse<T = unknown> = { ok: boolean; data: T };\nconst r: ApiResponse = { ok: true, data: 'any' };\n```\n\n**여러 개 + 서로 참조**\n```ts\nfunction pick<T, K extends keyof T>(obj: T, key: K): T[K] {\n  return obj[key];\n}\nconst user = { id: 1, name: '화랑' };\npick(user, 'name'); // string\npick(user, 'age');  // 컴파일 에러\n```\n\n**클래스·인터페이스**\n```ts\ninterface Repo<T> {\n  find(id: string): Promise<T | null>;\n  save(entity: T): Promise<void>;\n}\n\nclass UserRepo implements Repo<User> { /* ... */ }\n```\n\n실무 팁:\n- 대부분 **추론**이 되니 `<T>` 명시는 꼭 필요할 때만.\n- `extends`로 제약 걸면 에러 메시지가 훨씬 친절해집니다.\n- `keyof`, `typeof`, 조건부 타입(`T extends U ? A : B`)과 함께 쓰면 표현력이 크게 올라갑니다."),
    ]),

    # 16. 추천
    m([
        sys(),
        user("파이썬 웹 프레임워크 뭐가 좋아?"),
        assistant("용도에 따라 제가 권하는 기본값을 정리해 드릴게요.\n\n**1) FastAPI** — 대부분의 신규 프로젝트에 추천\n- 타입 힌트 기반, Pydantic으로 검증 자동\n- OpenAPI 문서 자동 생성\n- 비동기(asyncio) 일등 시민\n- 마이크로서비스/API 서버에 베스트\n\n**2) Django** — 풀스택·관리 화면이 필요할 때\n- ORM, 어드민, 인증, 마이그레이션이 전부 박스에 포함\n- 사내 툴, 커머스, CMS처럼 \"기능 많은 모놀리스\"에 강함\n- Django REST Framework 조합이면 API도 충분히 가능\n\n**3) Flask** — 가볍게 붙이거나 학습용\n- 미니멀, 확장은 본인이 조립\n- 간단한 내부 도구, 프로토타입에 적합\n- 현대 프로젝트라면 FastAPI로 넘어가는 경우가 많음\n\n**4) Litestar / Starlette**\n- FastAPI와 결이 비슷한 ASGI 기반. 특정 요구(더 가볍게, 더 빠르게)가 있을 때 고려.\n\n**추천 기준**\n- REST/GraphQL API만 깔끔하게: **FastAPI**\n- 관리자 + DB + 인증이 한 번에 필요: **Django**\n- 아주 작은 내부 스크립트/봇의 웹 인터페이스: **Flask**\n- 비동기 성능이 핵심: **FastAPI** 또는 **Litestar**\n\n한국 실무에서 체감상 신규 프로젝트는 **FastAPI**가 확실히 주류가 됐고, 이미 Django 자산이 있으면 그대로 Django로 밀고 가는 게 최적인 경우가 많습니다."),
    ]),

    # 17. 의견 (마이크로서비스 vs 모놀리스)
    m([
        sys(),
        user("마이크로서비스 vs 모놀리스 뭐가 나아?"),
        assistant("제 솔직한 의견은 **\"거의 항상 모놀리스로 시작하라\"** 입니다. 이유를 단계별로 설명할게요.\n\n**모놀리스의 강점 (특히 초기)**\n- 한 번의 배포, 한 번의 트랜잭션, 한 번의 디버깅\n- 팀이 작을수록 의사결정 비용이 낮음\n- 도메인이 아직 명확하지 않을 때 서비스 경계를 잘못 자를 위험이 큼\n\n**마이크로서비스가 주는 것 (그리고 청구서)**\n- 얻는 것: 독립 배포, 팀별 오너십, 부분 확장, 기술 이질성\n- 내는 값: 분산 트랜잭션, 네트워크 장애 처리, 관측(tracing/logging), CI/CD 복잡도, 데이터 일관성, 스키마 협상, 로컬 개발 경험 악화\n\n**언제 쪼갤 것인가 — 실전 트리거**\n1. 팀 수가 3~5개 이상으로 커져 하나의 배포 파이프라인이 병목이 될 때\n2. 도메인 경계가 오랜 운영으로 **명확해졌을 때**\n3. 특정 컴포넌트만 독립적으로 스케일해야 하는 트래픽 특성이 있을 때 (예: 실시간 알림, 영상 인코딩)\n4. 규제/보안상 격리가 강제될 때 (결제, 의료 데이터 등)\n\n**중간 단계도 활용**\n- **모듈러 모놀리스**: 하나의 배포지만 도메인별로 패키지·DB 스키마를 깔끔히 분리. 나중에 쪼개기 쉽습니다.\n- **스트랭글러 피그 패턴**: 모놀리스에서 경계가 명확한 부분부터 한 서비스씩 떼어내기.\n\n**결론**\n- 스타트업/신규 제품: 모놀리스 (혹은 모듈러 모놀리스)\n- 조직이 커지고 경계가 뚜렷해졌으면: 그때 필요한 부분부터 마이크로서비스\n\n마이크로서비스는 아키텍처 문제라기보다 **조직 구조와 운영 역량의 문제**에 가깝습니다. 인프라/DevOps 팀이 없는 상태에서 섣불리 쪼개면 장점은 얻지 못하고 비용만 지불하게 됩니다."),
    ]),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/tools_complex.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"복합+판단 tools: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
