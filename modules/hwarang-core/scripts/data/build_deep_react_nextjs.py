"""화랑 AI React/Next.js 심화 학습 데이터

렌더링 최적화, 캐싱 전략, Suspense, 서버 액션, ISR, 미들웨어 등.

사용법:
    python scripts/data/build_deep_react_nextjs.py --output data/sft/deep_react_nextjs.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 프론트엔드 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("React 리렌더링 최적화 심화 알려줘 왜 불필요한 리렌더가 일어나는지",
'''React 리렌더링의 원인과 해결법을 깊이 파봅니다.

```tsx
// ═══ 리렌더링이 일어나는 3가지 원인 ═══
// 1. state 변경
// 2. 부모 컴포넌트 리렌더
// 3. context 값 변경

// ═══ 문제 1: 부모 리렌더 → 모든 자식 리렌더 ═══
// ❌ 부모 state 변경 시 ExpensiveList도 리렌더!
function Parent() {
  const [count, setCount] = useState(0);

  return (
    <div>
      <button onClick={() => setCount(c => c + 1)}>
        클릭: {count}
      </button>
      {/* count와 무관한데 매번 리렌더됨! */}
      <ExpensiveList items={staticItems} />
    </div>
  );
}

// ✅ 해결 1: React.memo
const ExpensiveList = React.memo(function ExpensiveList({
  items,
}: {
  items: Item[];
}) {
  console.log("렌더링!"); // props 변경 시만 출력
  return (
    <ul>
      {items.map((item) => (
        <li key={item.id}>{item.name}</li>
      ))}
    </ul>
  );
});

// ✅ 해결 2: 컴포지션 패턴 (state를 아래로 내림)
function Parent() {
  return (
    <div>
      <CounterButton /> {/* state가 여기 안에만 */}
      <ExpensiveList items={staticItems} /> {/* 리렌더 안 됨! */}
    </div>
  );
}

function CounterButton() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(c => c + 1)}>클릭: {count}</button>;
}

// ═══ 문제 2: 인라인 객체/함수가 매번 새 참조 ═══
// ❌ 매 렌더마다 새 객체 → memo 무효화!
function Parent() {
  const [count, setCount] = useState(0);

  return (
    <Child
      style={{ color: "red" }}           // ❌ 매번 새 객체!
      onClick={() => console.log("hi")}  // ❌ 매번 새 함수!
      config={{ theme: "dark" }}          // ❌ 매번 새 객체!
    />
  );
}

// ✅ useMemo + useCallback
function Parent() {
  const [count, setCount] = useState(0);

  const style = useMemo(() => ({ color: "red" }), []);
  const handleClick = useCallback(() => console.log("hi"), []);
  const config = useMemo(() => ({ theme: "dark" }), []);

  return <Child style={style} onClick={handleClick} config={config} />;
}

// ═══ 문제 3: Context 변경 → 모든 소비자 리렌더 ═══
// ❌ theme 변경 시 UserInfo도 리렌더!
const AppContext = createContext({ theme: "light", user: null });

function App() {
  const [theme, setTheme] = useState("light");
  const [user, setUser] = useState(null);

  return (
    <AppContext.Provider value={{ theme, user }}>
      <ThemeToggle />  {/* theme만 사용 */}
      <UserInfo />     {/* user만 사용하는데 theme 변경 시도 리렌더! */}
    </AppContext.Provider>
  );
}

// ✅ 해결: Context 분리
const ThemeContext = createContext("light");
const UserContext = createContext(null);

function App() {
  const [theme, setTheme] = useState("light");
  const [user, setUser] = useState(null);

  return (
    <ThemeContext.Provider value={theme}>
      <UserContext.Provider value={user}>
        <ThemeToggle />  {/* theme 변경 시만 리렌더 */}
        <UserInfo />     {/* user 변경 시만 리렌더 */}
      </UserContext.Provider>
    </ThemeContext.Provider>
  );
}

// ═══ 문제 4: 리스트 렌더링 최적화 ═══
// ❌ key={index} → 순서 변경 시 전체 리렌더
{items.map((item, index) => <Item key={index} {...item} />)}

// ✅ key={고유ID} → 변경된 항목만 리렌더
{items.map((item) => <Item key={item.id} {...item} />)}

// ═══ 디버깅: React DevTools Profiler ═══
// 1. React DevTools → Profiler 탭
// 2. "Highlight updates when components render" 활성화
// 3. Record → 조작 → Stop
// 4. 각 컴포넌트의 렌더링 횟수/시간 확인

// why-did-you-render 라이브러리
// 불필요한 리렌더 자동 감지
import React from "react";
if (process.env.NODE_ENV === "development") {
  const whyDidYouRender = require("@welldone-software/why-did-you-render");
  whyDidYouRender(React, { trackAllPureComponents: true });
}
```

리렌더 최적화 우선순위:
1. **컴포지션**: state를 사용하는 곳으로 내리기 (가장 효과적)
2. **Context 분리**: 자주 변하는 값과 안 변하는 값 분리
3. **React.memo**: 순수 컴포넌트에 적용
4. **useMemo/useCallback**: 참조 안정성이 필요할 때만
5. **가상화**: 1000+ 항목 리스트는 `react-window` 사용'''),

    m("Next.js 캐싱 전략 심화 알려줘 ISR revalidate unstable_cache",
'''Next.js App Router의 캐싱 레이어를 깊이 파봅니다.

```tsx
// ═══ Next.js 4단계 캐싱 ═══
// 1. Request Memoization (같은 렌더에서 중복 요청 제거)
// 2. Data Cache (fetch 결과 서버 캐시)
// 3. Full Route Cache (정적 페이지 캐시)
// 4. Router Cache (클라이언트 라우터 캐시)

// ═══ 1. fetch 캐싱 제어 ═══

// 기본: 영구 캐시 (빌드 시 1회)
const data = await fetch("https://api.example.com/data");
// = fetch(url, { cache: "force-cache" })

// 캐시 안 함 (매 요청마다)
const data = await fetch("https://api.example.com/data", {
  cache: "no-store",
});

// 시간 기반 재검증 (ISR)
const data = await fetch("https://api.example.com/data", {
  next: { revalidate: 60 },  // 60초마다 백그라운드 재생성
});

// 태그 기반 재검증
const data = await fetch("https://api.example.com/posts", {
  next: { tags: ["posts"] },
});

// 서버 액션에서 태그 무효화
"use server";
import { revalidateTag, revalidatePath } from "next/cache";

export async function createPost(formData: FormData) {
  await db.post.create({ data: { ... } });
  revalidateTag("posts");        // 태그로 무효화
  revalidatePath("/blog");       // 경로로 무효화
  revalidatePath("/", "layout"); // 전체 레이아웃 무효화
}

// ═══ 2. unstable_cache (DB 쿼리 캐싱) ═══
import { unstable_cache } from "next/cache";

// fetch가 아닌 DB 쿼리/함수 결과를 캐싱
const getCachedUser = unstable_cache(
  async (userId: string) => {
    return db.user.findUnique({
      where: { id: userId },
      include: { posts: true },
    });
  },
  ["user-by-id"],           // 캐시 키 prefix
  {
    revalidate: 300,         // 5분 TTL
    tags: ["users"],         // 태그 (무효화용)
  }
);

// 사용
const user = await getCachedUser(userId);

// 무효화
revalidateTag("users");

// ═══ 3. 페이지 레벨 캐싱 ═══

// 정적 생성 (빌드 시) → 가장 빠름
// app/blog/[slug]/page.tsx
export async function generateStaticParams() {
  const posts = await db.post.findMany({ select: { slug: true } });
  return posts.map((post) => ({ slug: post.slug }));
}

// ISR (시간 기반 재생성)
export const revalidate = 60;  // 페이지 전체 60초 캐시

// 동적 (매 요청)
export const dynamic = "force-dynamic";

// ═══ 4. 세그먼트별 캐싱 전략 ═══
// app/dashboard/layout.tsx
export const revalidate = 300;  // 대시보드 전체 5분

// app/dashboard/stats/page.tsx
export const revalidate = 10;   // 통계는 10초 (더 자주)

// app/dashboard/settings/page.tsx
export const revalidate = 3600; // 설정은 1시간

// ═══ 5. 온디맨드 재검증 (Webhook) ═══
// app/api/revalidate/route.ts
import { revalidateTag } from "next/cache";
import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  const secret = request.headers.get("x-webhook-secret");
  if (secret !== process.env.WEBHOOK_SECRET) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { tag } = await request.json();
  revalidateTag(tag);
  return Response.json({ revalidated: true, now: Date.now() });
}

// CMS에서 콘텐츠 변경 시 → POST /api/revalidate { tag: "posts" }

// ═══ 6. 캐시 디버깅 ═══

// next.config.ts에서 로깅 활성화
const nextConfig = {
  logging: {
    fetches: {
      fullUrl: true,  // fetch URL + 캐시 상태 로그
    },
  },
};

// 서버 로그에서 확인:
// GET https://api.example.com/data (cache: HIT)
// GET https://api.example.com/users (cache: MISS)
// GET https://api.example.com/posts (cache: SKIP - no-store)

// ═══ 7. 캐싱 전략 조합 ═══

// 예: 블로그 사이트
// - 홈페이지: ISR 60초
// - 블로그 목록: ISR 300초 + 태그("posts")
// - 블로그 상세: 정적 생성 + 태그("post-{slug}")
// - 대시보드: 동적 (no-store)
// - 사용자 프로필: ISR 3600초 + 태그("user-{id}")
// - 검색 결과: 동적 (쿼리 파라미터)
```

캐싱 전략 선택:
| 콘텐츠 유형 | 전략 | revalidate |
|-------------|------|------------|
| 마케팅 페이지 | 정적 (빌드) | false |
| 블로그 글 | ISR + 태그 | 300초 |
| 상품 목록 | ISR + 태그 | 60초 |
| 대시보드 | 동적 | 0 (no-store) |
| 사용자 설정 | ISR + 태그 | 3600초 |
| 검색 결과 | 동적 | 0 |
| API 프록시 | 시간 기반 | 10-60초 |'''),

    m("React Suspense랑 Streaming SSR 심화 알려줘",
'''Suspense와 Streaming SSR로 최적의 로딩 경험을 만듭니다.

```tsx
// ═══ 1. Suspense 기본 원리 ═══
// Suspense = "아직 준비 안 된 것을 기다리는 방법"
// 서버 컴포넌트에서 await → 자동으로 Suspense 경계까지 스트리밍

// app/dashboard/page.tsx
import { Suspense } from "react";

export default function Dashboard() {
  return (
    <div className="grid grid-cols-3 gap-4">
      {/* 각각 독립적으로 로딩 → 빠른 것부터 보여줌 */}
      <Suspense fallback={<StatsSkeleton />}>
        <Stats />     {/* 0.5초 */}
      </Suspense>

      <Suspense fallback={<ChartSkeleton />}>
        <Chart />     {/* 2초 */}
      </Suspense>

      <Suspense fallback={<TableSkeleton />}>
        <RecentUsers /> {/* 1초 */}
      </Suspense>
    </div>
  );
}

// 각 컴포넌트는 독립적으로 데이터 페칭
async function Stats() {
  // 이 await 동안 fallback(스켈레톤) 표시
  const stats = await db.getStats();  // 0.5초
  return (
    <div className="rounded-xl border p-6">
      <h3 className="text-2xl font-bold">{stats.totalUsers.toLocaleString()}</h3>
      <p className="text-gray-500">전체 사용자</p>
    </div>
  );
}

async function Chart() {
  const data = await analyticsService.getMonthlyData();  // 2초
  return <BarChart data={data} />;
}

// ═══ 2. Streaming SSR 동작 원리 ═══
// 1) 서버가 HTML 셸(레이아웃 + 스켈레톤)을 즉시 전송
// 2) 각 Suspense 경계가 완료되면 <script>로 교체 HTML 스트리밍
// 3) 클라이언트에서 React가 스켈레톤을 실제 컨텐츠로 교체

// 사용자 경험:
// 0ms:   셸 + 스켈레톤 3개 표시 (TTFB 즉시)
// 500ms: Stats 컨텐츠로 교체
// 1000ms: RecentUsers 컨텐츠로 교체
// 2000ms: Chart 컨텐츠로 교체

// ═══ 3. loading.tsx (자동 Suspense) ═══
// app/dashboard/loading.tsx
export default function DashboardLoading() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-8 w-48 bg-gray-200 rounded" />
      <div className="grid grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-32 bg-gray-200 rounded-xl" />
        ))}
      </div>
    </div>
  );
}
// → app/dashboard/page.tsx를 자동으로 Suspense로 감쌈

// ═══ 4. 병렬 데이터 페칭 ═══

// ❌ 순차 (워터폴) - 느림!
async function Page() {
  const user = await getUser();        // 1초
  const posts = await getPosts();      // 1초
  const comments = await getComments(); // 1초
  // 총 3초!
}

// ✅ 병렬 (Promise.all) - 빠름!
async function Page() {
  const [user, posts, comments] = await Promise.all([
    getUser(),        // 1초
    getPosts(),       // 1초  → 동시 실행
    getComments(),    // 1초
  ]);
  // 총 1초!
}

// ✅ 더 좋은 패턴: Suspense로 점진적 표시
async function Page() {
  const user = await getUser();  // 이건 빠르니까 먼저

  return (
    <div>
      <h1>{user.name}</h1>
      <Suspense fallback={<PostsSkeleton />}>
        <Posts userId={user.id} />  {/* 별도 스트리밍 */}
      </Suspense>
      <Suspense fallback={<CommentsSkeleton />}>
        <Comments userId={user.id} />  {/* 별도 스트리밍 */}
      </Suspense>
    </div>
  );
}

// ═══ 5. Error Boundary + Suspense ═══
// app/dashboard/error.tsx
"use client";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="p-8 text-center">
      <h2 className="text-xl font-bold text-red-500">오류 발생</h2>
      <p className="mt-2 text-gray-600">{error.message}</p>
      <button
        onClick={reset}
        className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-white"
      >
        다시 시도
      </button>
    </div>
  );
}

// ═══ 6. useOptimistic (낙관적 업데이트) ═══
"use client";
import { useOptimistic } from "react";

function TodoList({ todos, addTodo }: Props) {
  const [optimisticTodos, addOptimisticTodo] = useOptimistic(
    todos,
    (state, newTodo: string) => [
      ...state,
      { id: crypto.randomUUID(), text: newTodo, pending: true },
    ]
  );

  async function handleSubmit(formData: FormData) {
    const text = formData.get("text") as string;
    addOptimisticTodo(text);     // 즉시 UI 업데이트
    await addTodo(text);         // 서버 액션 (실패 시 자동 롤백)
  }

  return (
    <form action={handleSubmit}>
      <input name="text" />
      <ul>
        {optimisticTodos.map((todo) => (
          <li key={todo.id} className={todo.pending ? "opacity-50" : ""}>
            {todo.text}
          </li>
        ))}
      </ul>
    </form>
  );
}
```

Suspense/Streaming 핵심:
- **Suspense 경계**: 독립적으로 로딩/에러 처리
- **Streaming SSR**: 빠른 것부터 스트리밍 → TTFB 최소화
- **병렬 페칭**: `Promise.all` 또는 Suspense 분리
- **낙관적 업데이트**: 서버 응답 전에 UI 먼저 반영
- **error.tsx**: Suspense 경계별 에러 처리'''),

    m("Next.js Server Actions 심화 패턴 알려줘",
'''Server Actions의 고급 패턴과 실무 활용법입니다.

```tsx
// ═══ 1. 기본 Server Action ═══
// app/actions/user.ts
"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { auth } from "@/auth";

// 입력 검증 스키마
const createUserSchema = z.object({
  name: z.string().min(2, "이름은 2자 이상"),
  email: z.string().email("올바른 이메일을 입력하세요"),
  role: z.enum(["user", "admin"]).default("user"),
});

// 타입 안전한 액션 결과
type ActionResult<T = void> =
  | { success: true; data: T }
  | { success: false; error: string; fieldErrors?: Record<string, string[]> };

export async function createUser(
  prevState: ActionResult<User> | null,
  formData: FormData,
): Promise<ActionResult<User>> {
  // 인증 확인
  const session = await auth();
  if (!session || session.user.role !== "admin") {
    return { success: false, error: "권한이 없습니다" };
  }

  // 입력 검증
  const parsed = createUserSchema.safeParse({
    name: formData.get("name"),
    email: formData.get("email"),
    role: formData.get("role"),
  });

  if (!parsed.success) {
    return {
      success: false,
      error: "입력값 오류",
      fieldErrors: parsed.error.flatten().fieldErrors,
    };
  }

  // DB 저장
  try {
    const user = await db.user.create({ data: parsed.data });
    revalidatePath("/admin/users");
    return { success: true, data: user };
  } catch (e) {
    if (e.code === "P2002") {
      return { success: false, error: "이미 가입된 이메일입니다" };
    }
    return { success: false, error: "서버 오류가 발생했습니다" };
  }
}

// ═══ 2. useActionState (React 19) ═══
"use client";
import { useActionState } from "react";
import { createUser } from "@/app/actions/user";

function CreateUserForm() {
  const [state, formAction, isPending] = useActionState(createUser, null);

  return (
    <form action={formAction} className="space-y-4">
      <div>
        <label htmlFor="name">이름</label>
        <input
          id="name"
          name="name"
          className={cn("input", state?.fieldErrors?.name && "border-red-500")}
        />
        {state?.fieldErrors?.name?.map((err) => (
          <p key={err} className="text-sm text-red-500">{err}</p>
        ))}
      </div>

      <div>
        <label htmlFor="email">이메일</label>
        <input id="email" name="email" type="email" className="input" />
        {state?.fieldErrors?.email?.map((err) => (
          <p key={err} className="text-sm text-red-500">{err}</p>
        ))}
      </div>

      {state?.error && !state.success && (
        <div className="rounded-lg bg-red-50 p-3 text-red-500">{state.error}</div>
      )}

      {state?.success && (
        <div className="rounded-lg bg-green-50 p-3 text-green-500">
          사용자가 생성되었습니다!
        </div>
      )}

      <button
        type="submit"
        disabled={isPending}
        className="rounded-lg bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
      >
        {isPending ? "생성 중..." : "사용자 생성"}
      </button>
    </form>
  );
}

// ═══ 3. 파일 업로드 Server Action ═══
"use server";

export async function uploadAvatar(formData: FormData): Promise<ActionResult<string>> {
  const session = await auth();
  if (!session) return { success: false, error: "로그인 필요" };

  const file = formData.get("avatar") as File;
  if (!file || file.size === 0) {
    return { success: false, error: "파일을 선택하세요" };
  }

  // 검증
  if (file.size > 5 * 1024 * 1024) {
    return { success: false, error: "5MB 이하 파일만 가능합니다" };
  }
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    return { success: false, error: "JPG, PNG, WebP만 가능합니다" };
  }

  // S3 업로드
  const buffer = Buffer.from(await file.arrayBuffer());
  const key = `avatars/${session.user.id}/${Date.now()}.${file.type.split("/")[1]}`;

  await s3.putObject({
    Bucket: "hwarang-uploads",
    Key: key,
    Body: buffer,
    ContentType: file.type,
  });

  const url = `https://cdn.hwarang.ai/${key}`;

  // DB 업데이트
  await db.user.update({
    where: { id: session.user.id },
    data: { avatarUrl: url },
  });

  revalidatePath("/profile");
  return { success: true, data: url };
}

// ═══ 4. 낙관적 업데이트 + Server Action ═══
"use client";

function LikeButton({ postId, initialLiked, initialCount }: Props) {
  const [liked, setLiked] = useState(initialLiked);
  const [count, setCount] = useState(initialCount);

  async function handleLike() {
    // 낙관적 업데이트 (즉시 UI 반영)
    const newLiked = !liked;
    setLiked(newLiked);
    setCount((c) => (newLiked ? c + 1 : c - 1));

    try {
      await toggleLike(postId);  // Server Action
    } catch {
      // 실패 시 롤백
      setLiked(!newLiked);
      setCount((c) => (newLiked ? c - 1 : c + 1));
      toast.error("좋아요 처리에 실패했습니다");
    }
  }

  return (
    <button onClick={handleLike} className="flex items-center gap-1">
      <HeartIcon className={liked ? "fill-red-500 text-red-500" : "text-gray-400"} />
      <span>{count}</span>
    </button>
  );
}

// ═══ 5. Server Action에서 redirect ═══
"use server";

export async function deleteUser(userId: string) {
  const session = await auth();
  if (session?.user.role !== "admin") {
    throw new Error("권한 없음");
  }

  await db.user.delete({ where: { id: userId } });
  revalidatePath("/admin/users");
  redirect("/admin/users");  // 리다이렉트 (try/catch 밖에서!)
}
```

Server Actions 핵심:
- **폼 + 검증**: `useActionState` + Zod
- **파일 업로드**: FormData에서 File 추출
- **낙관적 업데이트**: 즉시 UI → 실패 시 롤백
- **캐시 무효화**: `revalidatePath` / `revalidateTag`
- **리다이렉트**: `redirect()` (try/catch 밖에서)
- **인증 확인**: 모든 액션에서 `auth()` 체크'''),

    m("React useEffect 함정이랑 올바른 사용법 심화 알려줘",
'''useEffect의 흔한 실수와 올바른 패턴을 깊이 파봅니다.

```tsx
// ═══ 함정 1: 불필요한 useEffect ═══

// ❌ 파생 상태를 useEffect로 동기화
function SearchResults({ items, query }) {
  const [filteredItems, setFilteredItems] = useState([]);

  useEffect(() => {
    setFilteredItems(items.filter(item =>
      item.name.includes(query)
    ));
  }, [items, query]);  // 불필요한 리렌더 유발!

  return <List items={filteredItems} />;
}

// ✅ useMemo로 계산 (리렌더 없음)
function SearchResults({ items, query }) {
  const filteredItems = useMemo(
    () => items.filter(item => item.name.includes(query)),
    [items, query]
  );

  return <List items={filteredItems} />;
}

// ═══ 함정 2: 이벤트 핸들러 대신 useEffect ═══

// ❌ 제출 후 처리를 useEffect로
function Form() {
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (submitted) {
      sendAnalytics("form_submitted");
      showToast("저장 완료!");
      setSubmitted(false);
    }
  }, [submitted]);

  return <button onClick={() => setSubmitted(true)}>제출</button>;
}

// ✅ 이벤트 핸들러에서 직접 처리
function Form() {
  async function handleSubmit() {
    await saveData();
    sendAnalytics("form_submitted");
    showToast("저장 완료!");
  }

  return <button onClick={handleSubmit}>제출</button>;
}

// ═══ 함정 3: 클린업 누락 (메모리 누수) ═══

// ❌ 클린업 없음 → 컴포넌트 언마운트 후에도 실행!
function Chat({ roomId }) {
  useEffect(() => {
    const ws = new WebSocket(`/ws/${roomId}`);
    ws.onmessage = (event) => {
      setMessages(prev => [...prev, JSON.parse(event.data)]);
    };
    // 클린업 없음! → 메모리 누수 + 에러
  }, [roomId]);
}

// ✅ 클린업 함수 반환
function Chat({ roomId }) {
  useEffect(() => {
    const ws = new WebSocket(`/ws/${roomId}`);
    ws.onmessage = (event) => {
      setMessages(prev => [...prev, JSON.parse(event.data)]);
    };

    return () => {
      ws.close();  // roomId 변경 또는 언마운트 시 정리
    };
  }, [roomId]);
}

// ═══ 함정 4: 경쟁 조건 (Race Condition) ═══

// ❌ 빠르게 입력 변경 시 이전 요청이 나중에 도착할 수 있음
function Search({ query }) {
  const [results, setResults] = useState([]);

  useEffect(() => {
    fetch(`/api/search?q=${query}`)
      .then(res => res.json())
      .then(data => setResults(data));  // 이전 query의 결과가 덮어쓸 수 있음!
  }, [query]);
}

// ✅ cleanup으로 이전 요청 무시
function Search({ query }) {
  const [results, setResults] = useState([]);

  useEffect(() => {
    let cancelled = false;

    fetch(`/api/search?q=${query}`)
      .then(res => res.json())
      .then(data => {
        if (!cancelled) {  // 취소되지 않은 경우만 반영
          setResults(data);
        }
      });

    return () => {
      cancelled = true;  // 이전 요청 결과 무시
    };
  }, [query]);
}

// ✅✅ 더 좋은 방법: AbortController
function Search({ query }) {
  const [results, setResults] = useState([]);

  useEffect(() => {
    const controller = new AbortController();

    fetch(`/api/search?q=${query}`, { signal: controller.signal })
      .then(res => res.json())
      .then(data => setResults(data))
      .catch(err => {
        if (err.name !== "AbortError") throw err;
      });

    return () => controller.abort();  // 이전 요청 자체를 취소
  }, [query]);
}

// ═══ 함정 5: 무한 루프 ═══

// ❌ 객체를 의존성에 넣으면 매 렌더마다 실행!
function Component({ id }) {
  const options = { id, limit: 20 };  // 매번 새 객체!

  useEffect(() => {
    fetchData(options);
  }, [options]);  // 무한 루프!
}

// ✅ 원시값을 의존성으로 사용
function Component({ id }) {
  useEffect(() => {
    fetchData({ id, limit: 20 });
  }, [id]);  // id가 바뀔 때만
}

// ═══ useEffect가 적절한 경우 ═══
// 1. 외부 시스템과 동기화 (WebSocket, EventSource, DOM API)
// 2. 타이머/인터벌
// 3. 브라우저 이벤트 리스너 (resize, scroll, online/offline)
// 4. 서드파티 라이브러리 초기화 (차트, 지도)

// 올바른 예: 윈도우 리사이즈 감지
function useWindowSize() {
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    function handleResize() {
      setSize({ width: window.innerWidth, height: window.innerHeight });
    }

    handleResize();  // 초기값
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);  // 마운트/언마운트에만

  return size;
}
```

useEffect 판단 기준:
| 상황 | useEffect? | 대안 |
|------|-----------|------|
| 파생 상태 계산 | ❌ | `useMemo` |
| 이벤트 후 처리 | ❌ | 이벤트 핸들러 |
| 외부 시스템 동기화 | ✅ | - |
| API 데이터 페칭 | ⚠️ | TanStack Query / Server Component |
| DOM 측정 | ✅ | `useLayoutEffect` |
| 타이머 | ✅ | - |'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/deep_react_nextjs.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI React/Next.js 심화 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  React/Next.js 심화: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
