"""화랑 AI 프로그래밍 심화 대량 학습 데이터

클로드 수준의 깊이 있는 프로그래밍 답변.
실무 문제 해결, 디버깅, 아키텍처 결정, 성능 분석 등.

사용법:
    python scripts/data/build_mass_programming.py --output data/sft/mass_programming.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다.
질문에 대해 깊이 있고 정확한 답변을 제공합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 실무 디버깅 ═══
    m("Cannot read properties of undefined 에러가 계속 나와 어떻게 해?",
'''이 에러는 `undefined`인 객체의 속성에 접근할 때 발생합니다. 실무에서 가장 흔한 에러예요.

**원인별 해결 방법:**

```javascript
// ❌ 1. API 응답이 예상과 다를 때
const response = await fetch("/api/users");
const data = await response.json();
console.log(data.users[0].name);  // data.users가 undefined면 에러!

// ✅ 해결: 옵셔널 체이닝 + 기본값
const name = data?.users?.[0]?.name ?? "알 수 없음";

// ❌ 2. 비동기 데이터 로딩 전 접근
function UserProfile() {
  const [user, setUser] = useState(null);
  return <h1>{user.name}</h1>;  // 초기값이 null이라 에러!
}

// ✅ 해결: 로딩 상태 처리
function UserProfile() {
  const [user, setUser] = useState(null);

  if (!user) return <Skeleton />;
  return <h1>{user.name}</h1>;
}

// ❌ 3. 구조분해 할당에서 undefined
const { data: { users } } = response;  // data가 없으면 에러!

// ✅ 해결: 기본값 설정
const { data: { users = [] } = {} } = response;

// ❌ 4. 이벤트 핸들러에서 this 바인딩
class Component {
  handleClick() {
    this.setState({ clicked: true });  // this가 undefined!
  }
}

// ✅ 해결: 화살표 함수
class Component {
  handleClick = () => {
    this.setState({ clicked: true });
  }
}
```

**디버깅 팁:**
```javascript
// 어디서 undefined가 되는지 추적
console.log("data:", data);
console.log("data.users:", data?.users);
console.log("data.users[0]:", data?.users?.[0]);
```

핵심: **옵셔널 체이닝(`?.`)과 Nullish Coalescing(`??`)을 습관화하세요!**'''),

    m("CORS 에러 해결 방법 알려줘 상세히",
'''CORS(Cross-Origin Resource Sharing) 에러는 다른 도메인으로 API 요청할 때 발생합니다.

**에러 메시지:**
```
Access to fetch at 'https://api.example.com' from origin 'http://localhost:3000'
has been blocked by CORS policy
```

**원인:** 브라우저가 보안상 다른 출처(origin)로의 요청을 차단

**해결 방법 (상황별):**

```python
# 1. 백엔드에서 CORS 허용 (FastAPI)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://hwarang.ai",
    ],
    allow_credentials=True,   # 쿠키 허용
    allow_methods=["*"],       # GET, POST, PUT, DELETE
    allow_headers=["*"],       # Authorization 등
)
```

```javascript
// 2. Express.js
const cors = require("cors");
app.use(cors({
  origin: ["http://localhost:3000", "https://hwarang.ai"],
  credentials: true,
}));
```

```typescript
// 3. Next.js API Route (프록시 패턴 - 가장 권장)
// app/api/proxy/route.ts
// 브라우저 → Next.js API → 외부 API (CORS 없음!)
export async function POST(request: Request) {
  const body = await request.json();

  // 서버에서 서버로 요청 → CORS 없음!
  const response = await fetch("https://api.example.com/data", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await response.json();
  return Response.json(data);
}
```

```nginx
# 4. Nginx에서 CORS 헤더 추가
location /api/ {
    add_header 'Access-Control-Allow-Origin' 'https://hwarang.ai' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type' always;
    add_header 'Access-Control-Allow-Credentials' 'true' always;

    # Preflight 요청 처리
    if ($request_method = 'OPTIONS') {
        add_header 'Access-Control-Max-Age' 3600;
        return 204;
    }

    proxy_pass http://127.0.0.1:8000;
}
```

**실무 권장:**
| 상황 | 해결 |
|------|------|
| Next.js → 외부 API | **API Route 프록시** (가장 안전) |
| 같은 서버 | Nginx 리버스 프록시 |
| 개발 중 | `next.config.js` rewrites |
| 백엔드 제어 가능 | CORS 미들웨어 추가 |'''),

    m("메모리 누수 어떻게 찾아? React에서",
'''React에서 메모리 누수는 주로 **클린업 안 된 구독, 타이머, 이벤트 리스너**에서 발생합니다.

**증상:** 페이지를 오래 사용하면 점점 느려짐, 탭 메모리 사용량 증가

**1. 흔한 메모리 누수 패턴과 수정:**

```typescript
// ❌ 누수: useEffect 클린업 없음
function Chat({ roomId }) {
  useEffect(() => {
    const ws = new WebSocket(`/ws/${roomId}`);
    ws.onmessage = (e) => setMessages(prev => [...prev, e.data]);
    // 컴포넌트 언마운트 시 WebSocket이 계속 살아있음!
  }, [roomId]);
}

// ✅ 수정: 클린업 함수 추가
function Chat({ roomId }) {
  useEffect(() => {
    const ws = new WebSocket(`/ws/${roomId}`);
    ws.onmessage = (e) => setMessages(prev => [...prev, e.data]);

    return () => {
      ws.close();  // 언마운트 시 정리
    };
  }, [roomId]);
}

// ❌ 누수: setInterval 정리 안 함
function Timer() {
  useEffect(() => {
    setInterval(() => {
      setCount(c => c + 1);  // 영원히 실행!
    }, 1000);
  }, []);
}

// ✅ 수정
function Timer() {
  useEffect(() => {
    const id = setInterval(() => setCount(c => c + 1), 1000);
    return () => clearInterval(id);
  }, []);
}

// ❌ 누수: 이벤트 리스너 정리 안 함
function ScrollTracker() {
  useEffect(() => {
    window.addEventListener("scroll", handleScroll);
    // 정리 안 하면 매 렌더마다 리스너 추가!
  });
}

// ✅ 수정
function ScrollTracker() {
  useEffect(() => {
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);  // 빈 배열 = 마운트/언마운트에만
}

// ❌ 누수: 비동기 작업 후 언마운트된 컴포넌트 setState
function UserProfile({ userId }) {
  const [user, setUser] = useState(null);

  useEffect(() => {
    fetch(`/api/users/${userId}`)
      .then(r => r.json())
      .then(data => setUser(data));  // 이미 언마운트되면 경고!
  }, [userId]);
}

// ✅ 수정: AbortController로 취소
function UserProfile({ userId }) {
  const [user, setUser] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    fetch(`/api/users/${userId}`, { signal: controller.signal })
      .then(r => r.json())
      .then(data => setUser(data))
      .catch(err => {
        if (err.name !== "AbortError") throw err;
      });

    return () => controller.abort();
  }, [userId]);
}
```

**2. 메모리 누수 탐지 방법:**

```javascript
// Chrome DevTools
// 1. Performance 탭 → Record → 조작 → Stop
// 2. Memory 탭 → Heap Snapshot (전/후 비교)
// 3. Memory 탭 → Allocation Timeline

// React DevTools Profiler로 불필요한 리렌더 확인
```

**3. 자동 감지:**
```bash
# React Strict Mode (개발 중 자동 감지)
# - 컴포넌트를 2번 렌더하여 클린업 문제 발견
# - next.config.js에서 reactStrictMode: true
```

핵심 규칙: **useEffect에는 항상 return으로 클린업!**'''),

    m("무한 스크롤 구현 방법 알려줘 React로",
'''React에서 무한 스크롤을 구현하는 3가지 방법입니다.

**방법 1: IntersectionObserver (가장 권장)**

```typescript
import { useEffect, useRef, useCallback, useState } from "react";

function useInfiniteScroll<T>(fetchFn: (page: number) => Promise<T[]>) {
  const [items, setItems] = useState<T[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const observerRef = useRef<IntersectionObserver>();

  // 마지막 아이템을 관찰하는 ref 콜백
  const lastItemRef = useCallback((node: HTMLElement | null) => {
    if (loading) return;

    // 이전 observer 해제
    if (observerRef.current) observerRef.current.disconnect();

    observerRef.current = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasMore) {
        setPage(prev => prev + 1);
      }
    }, { threshold: 0.5 });

    if (node) observerRef.current.observe(node);
  }, [loading, hasMore]);

  useEffect(() => {
    setLoading(true);
    fetchFn(page)
      .then(newItems => {
        setItems(prev => [...prev, ...newItems]);
        setHasMore(newItems.length > 0);
      })
      .finally(() => setLoading(false));
  }, [page]);

  return { items, loading, hasMore, lastItemRef };
}

// 사용
function PostList() {
  const { items, loading, hasMore, lastItemRef } = useInfiniteScroll(
    (page) => fetch(`/api/posts?page=${page}&limit=20`).then(r => r.json())
  );

  return (
    <div>
      {items.map((post, i) => (
        <div
          key={post.id}
          ref={i === items.length - 1 ? lastItemRef : null}
        >
          <PostCard post={post} />
        </div>
      ))}

      {loading && <Spinner />}
      {!hasMore && <p>모든 게시글을 불러왔습니다.</p>}
    </div>
  );
}
```

**방법 2: TanStack Query (useInfiniteQuery)**

```typescript
import { useInfiniteQuery } from "@tanstack/react-query";

function PostList() {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["posts"],
    queryFn: ({ pageParam = 1 }) =>
      fetch(`/api/posts?page=${pageParam}&limit=20`).then(r => r.json()),
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length === 20 ? allPages.length + 1 : undefined,
  });

  // IntersectionObserver로 감지
  const observerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    });

    if (observerRef.current) observer.observe(observerRef.current);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage]);

  const allPosts = data?.pages.flat() ?? [];

  return (
    <div>
      {allPosts.map(post => <PostCard key={post.id} post={post} />)}

      {/* 감지용 빈 div */}
      <div ref={observerRef} style={{ height: 1 }} />

      {isFetchingNextPage && <Spinner />}
    </div>
  );
}
```

**방법 3: 가상화 (대량 데이터)**

```typescript
// 10,000+ 아이템일 때는 가상화 필수!
import { useVirtualizer } from "@tanstack/react-virtual";

function VirtualList({ items }) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 80,  // 예상 아이템 높이
    overscan: 5,              // 여유 렌더링
  });

  return (
    <div ref={parentRef} style={{ height: "600px", overflow: "auto" }}>
      <div style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map(virtual => (
          <div
            key={virtual.key}
            style={{
              position: "absolute",
              top: virtual.start,
              width: "100%",
            }}
          >
            <PostCard post={items[virtual.index]} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

**선택 가이드:**
| 상황 | 방법 |
|------|------|
| 일반적 무한 스크롤 | IntersectionObserver |
| 서버 상태 + 캐싱 | TanStack Query |
| 10,000+ 아이템 | 가상화 (react-virtual) |'''),

    m("Next.js에서 SEO 최적화 어떻게 해?",
'''Next.js에서 SEO를 최적화하는 방법입니다.

```typescript
// ═══ 1. Metadata API (App Router) ═══
// app/layout.tsx - 기본 메타데이터
import type { Metadata } from "next";

export const metadata: Metadata = {
  metadataBase: new URL("https://hwarang.ai"),
  title: {
    default: "화랑 AI - 한국형 AI 어시스턴트",
    template: "%s | 화랑 AI",  // 하위 페이지: "블로그 | 화랑 AI"
  },
  description: "코딩, 디자인, 문서 작성을 도와주는 한국어 최적화 AI 어시스턴트",
  keywords: ["AI", "인공지능", "코딩", "한국어 AI", "화랑"],
  authors: [{ name: "Persismore" }],
  openGraph: {
    type: "website",
    locale: "ko_KR",
    url: "https://hwarang.ai",
    siteName: "화랑 AI",
    title: "화랑 AI - 한국형 AI 어시스턴트",
    description: "코딩, 디자인, 문서 작성을 도와주는 AI",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "화랑 AI",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "화랑 AI",
    description: "한국어 최적화 AI 어시스턴트",
    images: ["/og-image.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  verification: {
    google: "구글_서치콘솔_인증코드",
    other: {
      "naver-site-verification": "네이버_서치어드바이저_인증코드",
    },
  },
};

// ═══ 2. 페이지별 동적 메타데이터 ═══
// app/blog/[slug]/page.tsx
export async function generateMetadata({ params }): Promise<Metadata> {
  const post = await getPost(params.slug);

  return {
    title: post.title,
    description: post.excerpt,
    openGraph: {
      title: post.title,
      description: post.excerpt,
      type: "article",
      publishedTime: post.createdAt,
      authors: [post.author.name],
      images: [post.coverImage],
    },
  };
}

// ═══ 3. JSON-LD 구조화 데이터 ═══
// app/layout.tsx
export default function RootLayout({ children }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    name: "화랑 AI",
    description: "한국어 최적화 AI 어시스턴트",
    url: "https://hwarang.ai",
    applicationCategory: "Productivity",
    operatingSystem: "Web",
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "KRW",
    },
  };

  return (
    <html lang="ko">
      <body>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        {children}
      </body>
    </html>
  );
}

// ═══ 4. 사이트맵 ═══
// app/sitemap.ts
export default async function sitemap() {
  const posts = await getAllPosts();

  return [
    { url: "https://hwarang.ai", lastModified: new Date(), priority: 1.0 },
    { url: "https://hwarang.ai/pricing", lastModified: new Date(), priority: 0.8 },
    { url: "https://hwarang.ai/docs", lastModified: new Date(), priority: 0.8 },
    ...posts.map(post => ({
      url: `https://hwarang.ai/blog/${post.slug}`,
      lastModified: post.updatedAt,
      priority: 0.6,
    })),
  ];
}

// ═══ 5. robots.txt ═══
// app/robots.ts
export default function robots() {
  return {
    rules: [
      { userAgent: "*", allow: "/", disallow: ["/api/", "/admin/"] },
    ],
    sitemap: "https://hwarang.ai/sitemap.xml",
  };
}

// ═══ 6. 성능 최적화 (Core Web Vitals) ═══
// next.config.ts
const nextConfig = {
  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: [{ hostname: "cdn.hwarang.ai" }],
  },
  experimental: {
    optimizeCss: true,
  },
};
```

**SEO 체크리스트:**
- [x] title + description 모든 페이지에 설정
- [x] Open Graph 이미지 (1200x630)
- [x] JSON-LD 구조화 데이터
- [x] sitemap.xml 자동 생성
- [x] robots.txt 설정
- [x] `lang="ko"` 설정
- [x] 이미지 alt 태그
- [x] 시맨틱 HTML (h1, h2, nav, main, footer)
- [x] Core Web Vitals 최적화 (LCP, FID, CLS)
- [x] 구글 서치콘솔 + 네이버 서치어드바이저 등록'''),

    m("Docker Compose 개발환경 어떻게 구성하면 좋아?",
'''실무 Docker Compose 개발환경 구성입니다.

```yaml
# docker-compose.yml
services:
  # ═══ PostgreSQL ═══
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
      # 초기 SQL (테이블 생성 등)
      - ./docker/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hwarang"]
      interval: 5s
      timeout: 5s
      retries: 5

  # ═══ Redis ═══
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: >
      redis-server
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  # ═══ FastAPI 백엔드 ═══
  api:
    build:
      context: ./modules/hwarang-api
      dockerfile: Dockerfile
      target: development
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
    command: >
      uvicorn hwarang_api.main:create_app
      --factory --host 0.0.0.0 --port 8000 --reload
    restart: unless-stopped

  # ═══ Next.js 프론트 ═══
  web:
    build:
      context: ./modules/hwarang-web
      dockerfile: Dockerfile
      target: development
    ports:
      - "3000:3000"
    volumes:
      - ./modules/hwarang-web:/app
      - /app/node_modules   # node_modules는 컨테이너 것 사용
      - /app/.next
    environment:
      - NEXTAUTH_URL=http://localhost:3000
      - HWARANG_API_URL=http://api:8000
    depends_on:
      - api
    command: pnpm dev
    restart: unless-stopped

  # ═══ 관리자 패널 ═══
  admin:
    build:
      context: ./modules/hwarang-admin
      dockerfile: Dockerfile
      target: development
    ports:
      - "3001:3001"
    volumes:
      - ./modules/hwarang-admin:/app
      - /app/node_modules
      - /app/.next
    environment:
      - HWARANG_API_URL=http://api:8000
    depends_on:
      - api
    command: pnpm dev --port 3001
    restart: unless-stopped

  # ═══ Mailhog (개발용 이메일) ═══
  mailhog:
    image: mailhog/mailhog
    ports:
      - "1025:1025"  # SMTP
      - "8025:8025"  # Web UI
    profiles:
      - tools

  # ═══ Adminer (DB 관리) ═══
  adminer:
    image: adminer
    ports:
      - "8080:8080"
    depends_on:
      - db
    profiles:
      - tools

volumes:
  postgres_data:
  redis_data:
```

```bash
# 실행 방법
docker compose up -d           # 기본 (api + web + admin + db + redis)
docker compose --profile tools up -d  # 도구 포함 (mailhog + adminer)
docker compose logs -f api     # API 로그 보기
docker compose down -v         # 정지 + 데이터 삭제
docker compose up -d --build   # 재빌드
```

**핵심 포인트:**
- `healthcheck`: DB 준비 완료 후에 API 시작
- `volumes`: 소스 코드 마운트 → 핫 리로드
- `profiles`: 선택적 도구 (평소엔 실행 안 함)
- `depends_on + condition`: 의존성 순서 보장'''),

    m("TypeScript에서 타입 안전한 API 호출 어떻게 해?",
'''API 호출부터 응답까지 전부 타입 안전하게 만드는 방법입니다.

```typescript
// ═══ 1. API 응답 타입 정의 ═══
// types/api.ts

interface ApiResponse<T> {
  data: T;
  message?: string;
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
  };
}

interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, string[]>;
  };
}

interface User {
  id: string;
  name: string;
  email: string;
  role: "user" | "admin";
  createdAt: string;
}

interface CreateUserInput {
  name: string;
  email: string;
  password: string;
}

// ═══ 2. 타입 안전한 fetch 래퍼 ═══
// lib/api-client.ts

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = "/api") {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    path: string,
    options?: RequestInit
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;

    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new ApiRequestError(
        error.error.message,
        response.status,
        error.error.code,
        error.error.details,
      );
    }

    return response.json();
  }

  // GET
  get<T>(path: string, params?: Record<string, string>): Promise<T> {
    const query = params ? "?" + new URLSearchParams(params).toString() : "";
    return this.request<T>(`${path}${query}`);
  }

  // POST
  post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  // PATCH
  patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }

  // DELETE
  delete<T = void>(path: string): Promise<T> {
    return this.request<T>(path, { method: "DELETE" });
  }
}

// 커스텀 에러
class ApiRequestError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public details?: Record<string, string[]>,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

// 싱글톤 인스턴스
export const api = new ApiClient();

// ═══ 3. 도메인별 API 함수 ═══
// lib/api/users.ts

export const usersApi = {
  list: (params?: { page?: number; search?: string }) =>
    api.get<PaginatedResponse<User>>("/users", {
      page: String(params?.page ?? 1),
      ...(params?.search && { search: params.search }),
    }),

  getById: (id: string) =>
    api.get<ApiResponse<User>>(`/users/${id}`),

  create: (input: CreateUserInput) =>
    api.post<ApiResponse<User>>("/users", input),

  update: (id: string, input: Partial<CreateUserInput>) =>
    api.patch<ApiResponse<User>>(`/users/${id}`, input),

  delete: (id: string) =>
    api.delete(`/users/${id}`),
};

// ═══ 4. React Hook으로 사용 ═══
// hooks/use-users.ts

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

export function useUsers(params?: { page?: number; search?: string }) {
  return useQuery({
    queryKey: ["users", params],
    queryFn: () => usersApi.list(params),
  });
}

export function useUser(id: string) {
  return useQuery({
    queryKey: ["user", id],
    queryFn: () => usersApi.getById(id),
    enabled: !!id,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: usersApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

// ═══ 5. 컴포넌트에서 사용 ═══
function UserList() {
  const { data, isLoading, error } = useUsers({ page: 1 });
  const createUser = useCreateUser();

  if (isLoading) return <Skeleton />;
  if (error) return <ErrorView error={error} />;

  // data는 PaginatedResponse<User> 타입!
  // data.data는 User[] 타입! → 자동완성 동작
  return (
    <ul>
      {data.data.map(user => (
        <li key={user.id}>
          {user.name} ({user.email})
        </li>
      ))}
    </ul>
  );
}
```

전체 흐름에서 **한 번도 `any`를 사용하지 않고** 완전한 타입 안전성을 확보합니다!'''),

    m("환경변수 관리 베스트 프랙티스 알려줘",
'''환경변수 관리의 실무 베스트 프랙티스입니다.

```typescript
// ═══ 1. Zod로 환경변수 검증 (가장 중요!) ═══
// lib/env.ts
import { z } from "zod";

const envSchema = z.object({
  // 필수
  DATABASE_URL: z.string().url(),
  NEXTAUTH_SECRET: z.string().min(32),
  NEXTAUTH_URL: z.string().url(),

  // 선택 (기본값 있음)
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
  PORT: z.coerce.number().default(3000),

  // 조건부 필수 (프로덕션에서만)
  GOOGLE_CLIENT_ID: z.string().optional(),
  GOOGLE_CLIENT_SECRET: z.string().optional(),

  // API 키 (프리픽스 검증)
  OPENAI_API_KEY: z.string().startsWith("sk-").optional(),
});

// 앱 시작 시 검증 → 잘못되면 즉시 에러!
export const env = envSchema.parse(process.env);

// 타입 자동 추론
// env.DATABASE_URL → string (자동완성!)
// env.PORT → number (자동 변환!)
```

```
# ═══ 2. .env 파일 구조 ═══

# .env.local (로컬 개발, gitignore)
DATABASE_URL=postgresql://hwarang:password@localhost:5432/hwarang
NEXTAUTH_SECRET=개발용-시크릿-32자-이상-아무거나
NEXTAUTH_URL=http://localhost:3000

# Google OAuth
GOOGLE_CLIENT_ID=965378...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...

# .env.example (git에 커밋, 템플릿)
DATABASE_URL=
NEXTAUTH_SECRET=
NEXTAUTH_URL=http://localhost:3000
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# .env.production (프로덕션, 서버에만)
DATABASE_URL=postgresql://hwarang:보안비밀번호@db.hwarang.ai:5432/hwarang
NEXTAUTH_SECRET=프로덕션-시크릿-매우-길게-설정
NEXTAUTH_URL=https://hwarang.ai
```

```gitignore
# .gitignore
.env
.env.local
.env.production
# .env.example은 커밋!
```

```typescript
// ═══ 3. Next.js 클라이언트/서버 구분 ═══

// 서버에서만 사용 (NEXT_PUBLIC_ 없음)
// → 절대 브라우저에 노출 안 됨
DATABASE_URL=postgresql://...
API_SECRET_KEY=비밀키

// 클라이언트에서도 사용 (NEXT_PUBLIC_ 접두사)
// → 브라우저에 노출됨! 비밀정보 금지!
NEXT_PUBLIC_API_URL=https://hwarang.ai/api
NEXT_PUBLIC_GA_ID=G-XXXXX

// ⚠️ 절대 하면 안 되는 것:
// NEXT_PUBLIC_DB_PASSWORD=비밀번호  ← 브라우저에 노출!
// NEXT_PUBLIC_API_SECRET=시크릿     ← 위험!
```

핵심:
1. **Zod로 앱 시작 시 검증** (빠진 변수 즉시 감지)
2. `.env.local`은 git에 절대 커밋 안 함
3. `.env.example`은 커밋 (팀원 안내용)
4. `NEXT_PUBLIC_` = 브라우저 노출 → 비밀정보 금지
5. 프로덕션 시크릿은 서버에서만 관리'''),

    m("Git 커밋 메시지 컨벤션 알려줘 실무에서",
'''실무에서 쓰는 Git 커밋 메시지 규칙입니다.

```
═══ Conventional Commits ═══

<타입>(<스코프>): <제목>

<본문>

<푸터>
```

**타입:**
| 타입 | 의미 | 예시 |
|------|------|------|
| `feat` | 새 기능 | `feat: 소셜 로그인 추가` |
| `fix` | 버그 수정 | `fix: 로그인 시 무한 로딩 해결` |
| `refactor` | 리팩토링 | `refactor: 사용자 서비스 클린 아키텍처 적용` |
| `docs` | 문서 | `docs: API 엔드포인트 문서 추가` |
| `style` | 코드 스타일 | `style: ESLint 규칙 적용` |
| `test` | 테스트 | `test: 사용자 API 유닛 테스트 추가` |
| `chore` | 기타 | `chore: 의존성 업데이트` |
| `perf` | 성능 | `perf: 이미지 lazy loading 적용` |
| `ci` | CI/CD | `ci: GitHub Actions 워크플로우 추가` |

**실무 예시:**

```bash
# 좋은 커밋 메시지
git commit -m "feat(auth): Google OAuth 로그인 구현

- NextAuth.js v5 설정
- Google Cloud Console OAuth 클라이언트 등록
- 로그인/로그아웃 UI 컴포넌트
- 세션 기반 라우트 보호 미들웨어

Closes #42"

git commit -m "fix(chat): AI 응답 스트리밍 중 화면 깜빡임 해결

TextDecoder로 청크 파싱 시 불완전한 JSON을
버퍼링하여 처리하도록 수정.

Fixes #108"

git commit -m "perf(db): 사용자 목록 쿼리 N+1 문제 해결

Prisma include로 관계 로딩을 한 번에 처리.
쿼리 수: 101 → 2로 감소."

# 나쁜 커밋 메시지
git commit -m "수정"           # ❌ 무슨 수정?
git commit -m "update"         # ❌ 무슨 업데이트?
git commit -m "bug fix"        # ❌ 어떤 버그?
git commit -m "WIP"            # ❌ 임시 저장
```

**커밋 메시지 규칙:**
1. 제목은 50자 이내
2. 본문은 72자에서 줄바꿈
3. **왜** 변경했는지 설명 (무엇을 변경했는지는 코드가 말해줌)
4. 이슈 번호 연결 (`Closes #42`, `Fixes #108`)
5. 한 커밋 = 한 논리적 변경 (여러 파일이어도 OK)'''),

    m("웹 성능 최적화 방법 알려줘 Core Web Vitals",
'''Core Web Vitals 기준 웹 성능 최적화 방법입니다.

**Core Web Vitals 3가지:**
| 지표 | 의미 | 좋음 | 나쁨 |
|------|------|------|------|
| LCP | 가장 큰 콘텐츠 로딩 | < 2.5초 | > 4초 |
| INP | 상호작용 응답 | < 200ms | > 500ms |
| CLS | 레이아웃 변동 | < 0.1 | > 0.25 |

```typescript
// ═══ 1. LCP 최적화 (로딩 속도) ═══

// Next.js Image 최적화
import Image from "next/image";

<Image
  src="/hero.jpg"
  alt="히어로 이미지"
  width={1200}
  height={630}
  priority  // LCP 요소는 priority로 미리 로딩!
  sizes="(max-width: 768px) 100vw, 50vw"
  placeholder="blur"
  blurDataURL="data:image/..."
/>

// 중요 리소스 프리로드
// app/layout.tsx
export default function RootLayout() {
  return (
    <html>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preload" href="/hero.jpg" as="image" />
      </head>
    </html>
  );
}

// 서버 컴포넌트 (데이터 서버에서 바로 로딩)
async function Hero() {
  const data = await fetch("https://api.hwarang.ai/featured");
  return <div>{data.title}</div>;
}
```

```typescript
// ═══ 2. INP 최적화 (반응 속도) ═══

// React.memo로 불필요한 리렌더 방지
const ExpensiveList = React.memo(function ExpensiveList({ items }) {
  return items.map(item => <Item key={item.id} item={item} />);
});

// useTransition으로 긴 작업 분리
function Search() {
  const [query, setQuery] = useState("");
  const [isPending, startTransition] = useTransition();

  const handleSearch = (value) => {
    setQuery(value);  // 즉시 반영 (입력)
    startTransition(() => {
      filterResults(value);  // 느린 작업은 백그라운드
    });
  };
}

// 무거운 계산 Web Worker로 이동
const worker = new Worker("/heavy-task.worker.js");
worker.postMessage(data);
worker.onmessage = (e) => setResult(e.data);
```

```css
/* ═══ 3. CLS 최적화 (레이아웃 안정성) ═══ */

/* 이미지/동영상에 크기 명시 */
img, video {
  width: 100%;
  height: auto;
  aspect-ratio: 16 / 9;  /* 로딩 전에 공간 확보 */
}

/* 폰트 로딩 시 깜빡임 방지 */
@font-face {
  font-family: 'Pretendard';
  font-display: swap;  /* 시스템 폰트 → 커스텀 폰트 */
  size-adjust: 100%;   /* 크기 차이 최소화 */
}

/* 동적 콘텐츠 공간 미리 확보 */
.ad-slot {
  min-height: 250px;  /* 광고 로딩 전에 공간 확보 */
}

.skeleton {
  min-height: 200px;  /* 스켈레톤으로 공간 확보 */
}
```

```typescript
// ═══ 4. 번들 최적화 ═══

// Dynamic import (코드 분할)
const HeavyEditor = dynamic(() => import("./editor"), {
  loading: () => <Skeleton />,
  ssr: false,  // 클라이언트에서만
});

// next.config.ts
module.exports = {
  experimental: {
    optimizePackageImports: ["lucide-react", "date-fns"],
  },
};
```

**측정 도구:**
- Lighthouse (Chrome DevTools)
- PageSpeed Insights (web.dev/measure)
- WebPageTest
- `next build` 시 번들 분석'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mass_programming.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 프로그래밍 심화 대량 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  프로그래밍 심화: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
