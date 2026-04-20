"""화랑 AI 프론트엔드 심화 학습 데이터

React/Next.js 고급, 상태관리, SSR/SSG, 접근성, 애니메이션 등.

사용법:
    python scripts/data/build_frontend_data.py \
        --output data/sft/frontend_advanced.jsonl
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
    # ═══ React Server Components ═══
    m("Next.js App Router에서 서버 컴포넌트랑 클라이언트 컴포넌트 차이 알려줘",
'''Next.js 13+ App Router의 핵심 개념입니다.

```tsx
// ═══ 서버 컴포넌트 (기본값) ═══
// app/users/page.tsx
// 'use client' 없으면 서버 컴포넌트

import { db } from "@/lib/db";

// 서버에서 직접 DB 조회 가능 (API 불필요!)
export default async function UsersPage() {
  const users = await db.user.findMany({
    orderBy: { createdAt: "desc" },
    take: 20,
  });

  return (
    <div>
      <h1>사용자 목록</h1>
      {/* 서버에서 렌더링 → JS 번들에 포함 안 됨 */}
      {users.map((user) => (
        <UserCard key={user.id} user={user} />
      ))}
      {/* 클라이언트 컴포넌트는 여기에 삽입 */}
      <SearchFilter />
    </div>
  );
}

// 서버 컴포넌트 (DB 직접 접근)
async function UserCard({ user }: { user: User }) {
  const postCount = await db.post.count({
    where: { authorId: user.id },
  });

  return (
    <div className="p-4 border rounded-lg">
      <h3>{user.name}</h3>
      <p>{user.email}</p>
      <p>게시글 {postCount}개</p>
    </div>
  );
}

// ═══ 클라이언트 컴포넌트 ═══
// components/search-filter.tsx
"use client";
// 'use client' 선언 → 브라우저에서 실행

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

export function SearchFilter() {
  const [query, setQuery] = useState("");
  const [isPending, startTransition] = useTransition();
  const router = useRouter();

  const handleSearch = (value: string) => {
    setQuery(value);
    // URL 파라미터 변경 → 서버 컴포넌트 리렌더
    startTransition(() => {
      router.push(`/users?q=${value}`);
    });
  };

  return (
    <div>
      <input
        type="text"
        value={query}
        onChange={(e) => handleSearch(e.target.value)}
        placeholder="사용자 검색..."
        className="border rounded px-3 py-2"
      />
      {isPending && <span>검색 중...</span>}
    </div>
  );
}

// ═══ Server Actions ═══
// app/actions.ts
"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

export async function createUser(formData: FormData) {
  const name = formData.get("name") as string;
  const email = formData.get("email") as string;

  // 서버에서 직접 DB 조작
  await db.user.create({
    data: { name, email },
  });

  revalidatePath("/users");  // 캐시 무효화
  redirect("/users");         // 리다이렉트
}

// 폼에서 사용
// <form action={createUser}>
//   <input name="name" />
//   <input name="email" />
//   <button type="submit">추가</button>
// </form>
```

**서버 vs 클라이언트 컴포넌트 사용 기준:**

| 기능 | 서버 | 클라이언트 |
|------|------|------------|
| DB 직접 접근 | ✅ | ❌ |
| useState/useEffect | ❌ | ✅ |
| 이벤트 핸들러 (onClick) | ❌ | ✅ |
| 브라우저 API (localStorage) | ❌ | ✅ |
| 데이터 페칭 | ✅ (await) | ✅ (useEffect) |
| SEO | ✅ | ⚠️ |
| 번들 크기 | 0 | 포함됨 |

원칙: **기본은 서버 컴포넌트**, 상호작용이 필요한 부분만 `"use client"`.'''),

    # ═══ 상태관리 ═══
    m("React 상태관리 방법 비교해줘 Zustand Context 등",
'''2025년 기준 React 상태관리 비교입니다.

```tsx
// ═══ 1. Zustand (가장 추천) ═══
// 간단하고 빠르고 보일러플레이트 없음
import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

interface AuthStore {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthStore>()(
  devtools(
    persist(
      (set, get) => ({
        user: null,
        token: null,

        login: async (email, password) => {
          const res = await fetch("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ email, password }),
          });
          const { user, token } = await res.json();
          set({ user, token });
        },

        logout: () => set({ user: null, token: null }),

        isAuthenticated: () => !!get().token,
      }),
      { name: "auth-store" }  // localStorage에 저장
    )
  )
);

// 사용법 (컴포넌트)
function Header() {
  const { user, logout, isAuthenticated } = useAuthStore();

  if (!isAuthenticated()) return <LoginButton />;
  return (
    <div>
      <span>{user?.name}</span>
      <button onClick={logout}>로그아웃</button>
    </div>
  );
}

// 선택적 구독 (리렌더 최적화)
function UserName() {
  // user가 바뀔 때만 리렌더
  const name = useAuthStore((state) => state.user?.name);
  return <span>{name}</span>;
}

// ═══ 2. React Context (간단한 전역 상태) ═══
// 테마, 언어 등 자주 바뀌지 않는 것에 적합
import { createContext, useContext, useState, ReactNode } from "react";

interface ThemeContextType {
  theme: "light" | "dark";
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("ThemeProvider 안에서 사용하세요");
  return context;
}

// ═══ 3. TanStack Query (서버 상태) ═══
// API 데이터 캐싱, 로딩 상태, 에러 처리 자동화
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

function UserList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["users"],
    queryFn: () => fetch("/api/users").then((r) => r.json()),
    staleTime: 5 * 60 * 1000,    // 5분간 캐시 유지
    refetchOnWindowFocus: true,   // 탭 복귀 시 리페치
  });

  if (isLoading) return <Skeleton />;
  if (error) return <Error message={error.message} />;
  return <ul>{data.map((u) => <li key={u.id}>{u.name}</li>)}</ul>;
}

function CreateUserForm() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (data: CreateUserInput) =>
      fetch("/api/users", { method: "POST", body: JSON.stringify(data) }),
    onSuccess: () => {
      // 사용자 목록 캐시 무효화 → 자동 리페치
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      mutation.mutate({ name: "홍길동", email: "hong@test.com" });
    }}>
      <button disabled={mutation.isPending}>
        {mutation.isPending ? "추가 중..." : "사용자 추가"}
      </button>
    </form>
  );
}
```

**선택 가이드:**
| 상황 | 추천 |
|------|------|
| 서버 데이터 (API) | TanStack Query |
| 클라이언트 전역 상태 | Zustand |
| 테마/언어 (적은 업데이트) | React Context |
| 폼 상태 | React Hook Form |
| 복잡한 비동기 로직 | Zustand + TanStack Query |'''),

    # ═══ Custom Hooks ═══
    m("React 커스텀 훅 실무 패턴 알려줘",
'''실무에서 자주 쓰는 커스텀 훅 모음입니다.

```tsx
import { useState, useEffect, useRef, useCallback } from "react";

// 1. useDebounce - 입력 디바운스
function useDebounce<T>(value: T, delay: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// 사용: 검색 입력에서 API 호출 최소화
function SearchInput() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    if (debouncedQuery) {
      fetchSearchResults(debouncedQuery);
    }
  }, [debouncedQuery]);
}

// 2. useLocalStorage - 로컬 스토리지 동기화
function useLocalStorage<T>(key: string, initialValue: T) {
  const [storedValue, setStoredValue] = useState<T>(() => {
    if (typeof window === "undefined") return initialValue;
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch {
      return initialValue;
    }
  });

  const setValue = useCallback((value: T | ((val: T) => T)) => {
    const valueToStore = value instanceof Function ? value(storedValue) : value;
    setStoredValue(valueToStore);
    window.localStorage.setItem(key, JSON.stringify(valueToStore));
  }, [key, storedValue]);

  return [storedValue, setValue] as const;
}

// 3. useMediaQuery - 반응형 감지
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(query);
    setMatches(media.matches);
    const listener = (e: MediaQueryListEvent) => setMatches(e.matches);
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [query]);

  return matches;
}

// 사용
function Layout() {
  const isMobile = useMediaQuery("(max-width: 768px)");
  return isMobile ? <MobileLayout /> : <DesktopLayout />;
}

// 4. useIntersectionObserver - 무한 스크롤 / Lazy Load
function useIntersectionObserver(
  callback: () => void,
  options?: IntersectionObserverInit
) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) callback();
    }, options);

    observer.observe(element);
    return () => observer.disconnect();
  }, [callback, options]);

  return ref;
}

// 무한 스크롤 사용
function PostList() {
  const { data, fetchNextPage, hasNextPage } = useInfiniteQuery({...});
  const loadMoreRef = useIntersectionObserver(() => {
    if (hasNextPage) fetchNextPage();
  });

  return (
    <div>
      {data?.pages.map((page) =>
        page.posts.map((post) => <PostCard key={post.id} post={post} />)
      )}
      <div ref={loadMoreRef} /> {/* 이 요소가 보이면 다음 페이지 로드 */}
    </div>
  );
}

// 5. useCopyToClipboard - 클립보드 복사
function useCopyToClipboard() {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, []);

  return { copy, copied };
}

// 6. useClickOutside - 외부 클릭 감지
function useClickOutside(
  ref: React.RefObject<HTMLElement>,
  handler: () => void
) {
  useEffect(() => {
    const listener = (e: MouseEvent) => {
      if (!ref.current || ref.current.contains(e.target as Node)) return;
      handler();
    };
    document.addEventListener("mousedown", listener);
    return () => document.removeEventListener("mousedown", listener);
  }, [ref, handler]);
}

// 드롭다운 닫기
function Dropdown() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false));

  return (
    <div ref={ref}>
      <button onClick={() => setOpen(!open)}>메뉴</button>
      {open && <DropdownMenu />}
    </div>
  );
}
```

커스텀 훅 규칙:
- `use`로 시작 (React 규칙)
- 하나의 관심사만 담당
- 반환값은 `[value, setter]` 또는 객체 `{ data, loading }`
- 내부에서 다른 훅 사용 가능'''),

    # ═══ CSS/TailwindCSS ═══
    m("TailwindCSS 실무 패턴 알려줘 반응형 다크모드 포함",
'''TailwindCSS 실무 패턴과 컴포넌트 구성입니다.

```tsx
// ═══ 1. 반응형 디자인 ═══
// sm:640px, md:768px, lg:1024px, xl:1280px, 2xl:1536px

function ResponsiveLayout() {
  return (
    <div className="
      grid
      grid-cols-1         {/* 모바일: 1열 */}
      md:grid-cols-2      {/* 태블릿: 2열 */}
      lg:grid-cols-3      {/* 데스크탑: 3열 */}
      xl:grid-cols-4      {/* 대형: 4열 */}
      gap-4 p-4
    ">
      {items.map((item) => (
        <Card key={item.id} item={item} />
      ))}
    </div>
  );
}

// ═══ 2. 다크모드 ═══
// tailwind.config.ts: darkMode: "class"

function ThemeToggle() {
  return (
    <div className="
      bg-white dark:bg-gray-900
      text-gray-900 dark:text-gray-100
      border border-gray-200 dark:border-gray-700
      rounded-lg p-6
      transition-colors duration-200
    ">
      <h2 className="text-xl font-bold">제목</h2>
      <p className="text-gray-600 dark:text-gray-400">
        설명 텍스트
      </p>
    </div>
  );
}

// ═══ 3. 재사용 가능한 컴포넌트 (CVA) ═══
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // 기본 스타일
  "inline-flex items-center justify-center rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-500",
        secondary: "bg-gray-100 text-gray-900 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-100",
        danger: "bg-red-600 text-white hover:bg-red-700",
        ghost: "hover:bg-gray-100 dark:hover:bg-gray-800",
        link: "text-blue-600 underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-6 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  isLoading?: boolean;
}

function Button({ className, variant, size, isLoading, children, ...props }: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={isLoading}
      {...props}
    >
      {isLoading && <Spinner className="mr-2 h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

// 사용
<Button variant="primary" size="lg">저장</Button>
<Button variant="danger" isLoading={saving}>삭제</Button>
<Button variant="ghost" size="icon"><MenuIcon /></Button>

// ═══ 4. 애니메이션 ═══
function AnimatedCard() {
  return (
    <div className="
      transform transition-all duration-300 ease-in-out
      hover:scale-105 hover:shadow-xl
      active:scale-95
    ">
      <div className="animate-fade-in">
        {/* 컨텐츠 */}
      </div>
    </div>
  );
}

// tailwind.config.ts에 커스텀 애니메이션 추가
// animation: {
//   "fade-in": "fadeIn 0.5s ease-in-out",
//   "slide-up": "slideUp 0.3s ease-out",
// },
// keyframes: {
//   fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
//   slideUp: { "0%": { transform: "translateY(10px)", opacity: "0" }, "100%": { transform: "translateY(0)", opacity: "1" } },
// },

// ═══ 5. cn() 유틸리티 ═══
// lib/utils.ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// 조건부 클래스 적용
<div className={cn(
  "rounded-lg p-4",
  isActive && "bg-blue-100 border-blue-500",
  isError && "bg-red-100 border-red-500",
  className  // 외부에서 전달받은 클래스
)} />
```

Tailwind 실무 팁:
- `cn()` (clsx + tailwind-merge) 필수 유틸
- CVA로 variant 기반 컴포넌트 설계
- `group` / `peer` 클래스로 부모/형제 상태 기반 스타일링
- `@apply`는 최소한으로 (유틸리티 퍼스트 원칙)'''),

    # ═══ 폼 처리 ═══
    m("React Hook Form 사용법 알려줘 Zod 포함",
'''React Hook Form + Zod로 타입 안전한 폼을 만듭니다.

```tsx
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

// 1. Zod 스키마 정의
const signupSchema = z.object({
  name: z.string()
    .min(2, "이름은 2자 이상 입력하세요")
    .max(50, "이름은 50자 이하로 입력하세요"),
  email: z.string()
    .email("올바른 이메일을 입력하세요"),
  password: z.string()
    .min(8, "비밀번호는 8자 이상이어야 합니다")
    .regex(/[A-Z]/, "대문자를 포함해야 합니다")
    .regex(/[0-9]/, "숫자를 포함해야 합니다")
    .regex(/[^A-Za-z0-9]/, "특수문자를 포함해야 합니다"),
  confirmPassword: z.string(),
  agreeTerms: z.boolean().refine((val) => val, {
    message: "이용약관에 동의해야 합니다",
  }),
}).refine((data) => data.password === data.confirmPassword, {
  message: "비밀번호가 일치하지 않습니다",
  path: ["confirmPassword"],
});

// 타입 자동 추론
type SignupForm = z.infer<typeof signupSchema>;

// 2. 폼 컴포넌트
export function SignupForm() {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    watch,
    reset,
  } = useForm<SignupForm>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      name: "",
      email: "",
      password: "",
      confirmPassword: "",
      agreeTerms: false,
    },
  });

  const onSubmit = async (data: SignupForm) => {
    try {
      const response = await fetch("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify(data),
      });
      if (!response.ok) throw new Error("가입 실패");
      reset();
      toast.success("가입 완료!");
    } catch (error) {
      toast.error("가입에 실패했습니다");
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {/* 이름 */}
      <div>
        <label htmlFor="name" className="block text-sm font-medium">
          이름
        </label>
        <input
          id="name"
          {...register("name")}
          className={cn(
            "mt-1 block w-full rounded-lg border px-3 py-2",
            errors.name
              ? "border-red-500 focus:ring-red-500"
              : "border-gray-300 focus:ring-blue-500"
          )}
        />
        {errors.name && (
          <p className="mt-1 text-sm text-red-500">{errors.name.message}</p>
        )}
      </div>

      {/* 이메일 */}
      <div>
        <label htmlFor="email">이메일</label>
        <input id="email" type="email" {...register("email")} />
        {errors.email && <p className="text-red-500">{errors.email.message}</p>}
      </div>

      {/* 비밀번호 */}
      <div>
        <label htmlFor="password">비밀번호</label>
        <input id="password" type="password" {...register("password")} />
        {errors.password && <p className="text-red-500">{errors.password.message}</p>}
        {/* 비밀번호 강도 표시 */}
        <PasswordStrength password={watch("password")} />
      </div>

      {/* 비밀번호 확인 */}
      <div>
        <label htmlFor="confirmPassword">비밀번호 확인</label>
        <input id="confirmPassword" type="password" {...register("confirmPassword")} />
        {errors.confirmPassword && (
          <p className="text-red-500">{errors.confirmPassword.message}</p>
        )}
      </div>

      {/* 이용약관 동의 */}
      <div className="flex items-center gap-2">
        <input id="terms" type="checkbox" {...register("agreeTerms")} />
        <label htmlFor="terms">이용약관에 동의합니다</label>
        {errors.agreeTerms && (
          <p className="text-red-500">{errors.agreeTerms.message}</p>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full rounded-lg bg-blue-600 py-2 text-white"
      >
        {isSubmitting ? "가입 중..." : "회원가입"}
      </button>
    </form>
  );
}
```

핵심:
- Zod로 스키마 정의 → 타입 자동 추론 (`z.infer`)
- `zodResolver`로 RHF와 연결
- `register`로 입력 필드 등록 (ref + onChange 자동)
- `errors` 객체로 에러 메시지 표시
- `isSubmitting`으로 중복 제출 방지'''),

    # ═══ Next.js API 라우트 ═══
    m("Next.js API Route 패턴 알려줘",
'''Next.js App Router의 API 라우트 패턴입니다.

```typescript
// app/api/users/route.ts
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { z } from "zod";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

// GET /api/users?page=1&limit=20&search=홍
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const page = parseInt(searchParams.get("page") || "1");
    const limit = Math.min(parseInt(searchParams.get("limit") || "20"), 100);
    const search = searchParams.get("search") || "";

    const where = search
      ? {
          OR: [
            { name: { contains: search } },
            { email: { contains: search } },
          ],
        }
      : {};

    const [users, total] = await Promise.all([
      db.user.findMany({
        where,
        skip: (page - 1) * limit,
        take: limit,
        orderBy: { createdAt: "desc" },
        select: {
          id: true,
          name: true,
          email: true,
          createdAt: true,
          _count: { select: { posts: true } },
        },
      }),
      db.user.count({ where }),
    ]);

    return NextResponse.json({
      data: users,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error("사용자 조회 실패:", error);
    return NextResponse.json(
      { error: "서버 오류가 발생했습니다" },
      { status: 500 }
    );
  }
}

// POST /api/users
const createUserSchema = z.object({
  name: z.string().min(2).max(50),
  email: z.string().email(),
});

export async function POST(request: NextRequest) {
  // 인증 확인
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "로그인 필요" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const validated = createUserSchema.parse(body);

    // 중복 확인
    const existing = await db.user.findUnique({
      where: { email: validated.email },
    });
    if (existing) {
      return NextResponse.json(
        { error: "이미 존재하는 이메일입니다" },
        { status: 409 }
      );
    }

    const user = await db.user.create({ data: validated });

    return NextResponse.json(user, { status: 201 });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(
        { error: "입력값 오류", details: error.errors },
        { status: 422 }
      );
    }
    return NextResponse.json(
      { error: "서버 오류" },
      { status: 500 }
    );
  }
}

// app/api/users/[id]/route.ts
// GET/PATCH/DELETE /api/users/:id
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await request.json();

  const user = await db.user.update({
    where: { id },
    data: body,
  });

  return NextResponse.json(user);
}
```

핵심:
- Zod로 입력 검증
- `getServerSession`으로 인증 확인
- 페이지네이션은 `page`/`limit` 쿼리 파라미터
- 에러 응답은 일관된 `{ error: string }` 형식
- dynamic route는 `[id]/route.ts`'''),

    # ═══ 접근성 ═══
    m("웹 접근성 실무 가이드 알려줘",
'''WCAG 기준 웹 접근성 실무 구현입니다.

```tsx
// 1. 시맨틱 HTML + ARIA
function NavigationMenu() {
  return (
    <nav aria-label="메인 내비게이션">
      <ul role="menubar">
        <li role="none">
          <a href="/" role="menuitem" aria-current="page">홈</a>
        </li>
        <li role="none">
          <a href="/about" role="menuitem">소개</a>
        </li>
      </ul>
    </nav>
  );
}

// 2. 모달 접근성 (포커스 트랩 + ESC 닫기)
function AccessibleModal({ isOpen, onClose, title, children }) {
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    // 이전 포커스 저장
    const previousFocus = document.activeElement as HTMLElement;
    modalRef.current?.focus();

    // ESC 키로 닫기
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();

      // 포커스 트랩
      if (e.key === "Tab") {
        const focusable = modalRef.current?.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusable?.length) return;

        const first = focusable[0] as HTMLElement;
        const last = focusable[focusable.length - 1] as HTMLElement;

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();  // 포커스 복원
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      ref={modalRef}
      tabIndex={-1}
      className="fixed inset-0 z-50 flex items-center justify-center"
    >
      {/* 백드롭 */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* 모달 컨텐츠 */}
      <div className="relative bg-white rounded-lg p-6 max-w-md w-full">
        <h2 id="modal-title" className="text-xl font-bold">{title}</h2>
        {children}
        <button
          onClick={onClose}
          aria-label="닫기"
          className="absolute top-4 right-4"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

// 3. 폼 접근성
function AccessibleForm() {
  return (
    <form aria-label="회원가입 폼">
      <div>
        <label htmlFor="email">
          이메일 <span aria-hidden="true">*</span>
          <span className="sr-only">(필수)</span>
        </label>
        <input
          id="email"
          type="email"
          aria-required="true"
          aria-invalid={!!errors.email}
          aria-describedby={errors.email ? "email-error" : undefined}
        />
        {errors.email && (
          <p id="email-error" role="alert" className="text-red-500">
            {errors.email}
          </p>
        )}
      </div>
    </form>
  );
}

// 4. 스크린 리더 전용 텍스트
// globals.css
// .sr-only {
//   position: absolute; width: 1px; height: 1px;
//   padding: 0; margin: -1px; overflow: hidden;
//   clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
// }

// 5. 이미지 대체 텍스트
<img src="/logo.png" alt="화랑 AI 로고" />
<img src="/decoration.svg" alt="" aria-hidden="true" /> {/* 장식용 */}

// 6. 스킵 네비게이션
function SkipNav() {
  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 bg-blue-600 text-white px-4 py-2 rounded z-50"
    >
      메인 컨텐츠로 건너뛰기
    </a>
  );
}
```

접근성 체크리스트:
- [ ] 키보드만으로 모든 기능 사용 가능
- [ ] 포커스 표시 visible (outline 제거 금지)
- [ ] 색상 대비 4.5:1 이상 (텍스트), 3:1 (큰 텍스트)
- [ ] 이미지에 alt 속성 (장식용은 alt="")
- [ ] 폼 입력에 label 연결
- [ ] 에러 메시지를 role="alert"로 알림
- [ ] 모달 포커스 트랩 + ESC 닫기'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/frontend_advanced.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 프론트엔드 심화 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  프론트엔드: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
