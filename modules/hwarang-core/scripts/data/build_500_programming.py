"""화랑 AI 프로그래밍 심화 대량 추가 (80건)

500건 달성을 위한 프로그래밍 심화 학습 데이터.
클로드 수준의 깊이 있는 코드 답변.
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다.
질문에 대해 클로드처럼 깊이 있고 정확한 답변을 제공합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("Promise.all vs Promise.allSettled 차이 알려줘 언제 뭘 써야해?",
'''두 메서드의 핵심 차이와 사용 시나리오입니다.

```typescript
// ═══ Promise.all ═══
// 모두 성공해야 결과 반환. 하나라도 실패하면 즉시 reject.

// 사용: 모든 데이터가 다 있어야 의미 있을 때
async function loadDashboard() {
  try {
    const [user, orders, stats] = await Promise.all([
      fetchUser(),     // 실패하면
      fetchOrders(),   // 여기도 취소됨 (실제론 실행되지만 결과 무시)
      fetchStats(),
    ]);
    return { user, orders, stats };
  } catch (error) {
    // 하나라도 실패 → catch로 옴
    console.error("대시보드 로드 실패:", error);
    throw error;
  }
}

// ═══ Promise.allSettled ═══
// 모든 Promise가 완료될 때까지 기다림. 실패해도 계속 진행.

// 사용: 일부 실패해도 나머지 결과가 필요할 때
async function sendNotifications(userIds: string[]) {
  const results = await Promise.allSettled(
    userIds.map(id => sendEmail(id))
  );

  const succeeded = results.filter(r => r.status === "fulfilled");
  const failed = results.filter(r => r.status === "rejected");

  console.log(`성공: ${succeeded.length}, 실패: ${failed.length}`);

  // 실패한 것만 재시도
  const retryIds = failed.map((r, i) => userIds[i]);
  if (retryIds.length > 0) {
    await retryNotifications(retryIds);
  }

  return { succeeded: succeeded.length, failed: failed.length };
}

// ═══ 실무 선택 가이드 ═══
// Promise.all: 결제 처리 (잔액확인 + 결제 + 기록 → 하나라도 실패하면 전체 롤백)
// Promise.allSettled: 알림 발송 (일부 실패해도 다른 사람에게는 보내야 함)
```

| 상황 | 선택 | 이유 |
|------|------|------|
| API 3개 → 대시보드 구성 | `Promise.all` | 하나 빠지면 UI 깨짐 |
| 사용자 100명에게 알림 | `Promise.allSettled` | 일부 실패해도 나머지 전송 |
| DB 트랜잭션 (이체) | `Promise.all` | 원자성 필요 |
| 이미지 10개 업로드 | `Promise.allSettled` | 일부 실패해도 성공한 것 유지 |
| 외부 API 헬스체크 | `Promise.allSettled` | 각각 독립적 |'''),

    m("debounce vs throttle 차이 알려줘 구현 포함",
'''두 기법의 차이와 실제 구현입니다.

```typescript
// ═══ Debounce ═══
// 마지막 호출 후 N밀리초 기다렸다가 실행
// "연속 입력이 끝나면 실행"

function debounce<T extends (...args: any[]) => any>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout>;

  return (...args: Parameters<T>) => {
    clearTimeout(timer);  // 이전 타이머 취소
    timer = setTimeout(() => fn(...args), delay);  // 새 타이머
  };
}

// 사용: 검색 입력 (타이핑 멈추면 API 호출)
const searchInput = document.getElementById("search");
const debouncedSearch = debounce((query: string) => {
  fetch(`/api/search?q=${query}`);  // 타이핑 멈춘 후 300ms 뒤 실행
}, 300);

searchInput.addEventListener("input", (e) => {
  debouncedSearch(e.target.value);
});
// "hello" 빠르게 입력 → API 호출 1번 (마지막에만)


// ═══ Throttle ═══
// N밀리초에 최대 1번만 실행
// "일정 간격으로만 실행"

function throttle<T extends (...args: any[]) => any>(
  fn: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle = false;

  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      fn(...args);
      inThrottle = true;
      setTimeout(() => { inThrottle = false; }, limit);
    }
  };
}

// 사용: 스크롤 이벤트 (초당 60번 → 5번으로 제한)
const throttledScroll = throttle(() => {
  const scrollY = window.scrollY;
  updateScrollIndicator(scrollY);
}, 200);  // 200ms마다 최대 1번

window.addEventListener("scroll", throttledScroll);


// ═══ React Hook 버전 ═══
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// 사용
function SearchComponent() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    if (debouncedQuery) {
      fetchSearchResults(debouncedQuery);
    }
  }, [debouncedQuery]);  // 300ms 후에만 API 호출
}
```

**핵심 차이:**
| | Debounce | Throttle |
|---|---|---|
| 동작 | 마지막 호출 후 대기 | 일정 간격으로 실행 |
| 비유 | 엘리베이터 문 (마지막 사람 후 닫힘) | 지하철 (3분마다 출발) |
| 사용 | 검색 입력, 리사이즈 완료 | 스크롤, 마우스 이동 |'''),

    m("클로저란 뭐야? 실무에서 어떻게 쓰여?",
'''클로저는 함수가 **자신이 생성된 환경의 변수를 기억**하는 것입니다.

```javascript
// ═══ 클로저의 본질 ═══
function createCounter() {
  let count = 0;  // 이 변수는 함수가 끝나도 살아있음!

  return {
    increment: () => ++count,
    decrement: () => --count,
    getCount: () => count,
  };
}

const counter = createCounter();
counter.increment();  // 1
counter.increment();  // 2
counter.getCount();   // 2
// count 변수에 직접 접근 불가 (캡슐화!)


// ═══ 실무 활용 1: 프라이빗 상태 ═══
function createAuthManager(secretKey) {
  // secretKey는 외부에서 접근 불가!
  let token = null;

  return {
    login: async (email, password) => {
      const response = await fetch("/api/login", { ... });
      token = response.token;  // 클로저로 보호
    },
    getToken: () => token,
    isAuthenticated: () => !!token,
    // secretKey도 클로저로 안전하게 보관
    verify: (data) => hmac(data, secretKey),
  };
}


// ═══ 실무 활용 2: 함수 팩토리 ═══
function createLogger(prefix) {
  return {
    info: (msg) => console.log(`[${prefix}] INFO: ${msg}`),
    error: (msg) => console.error(`[${prefix}] ERROR: ${msg}`),
    warn: (msg) => console.warn(`[${prefix}] WARN: ${msg}`),
  };
}

const apiLogger = createLogger("API");
const dbLogger = createLogger("DB");

apiLogger.info("요청 시작");  // [API] INFO: 요청 시작
dbLogger.error("연결 실패"); // [DB] ERROR: 연결 실패


// ═══ 실무 활용 3: 메모이제이션 ═══
function memoize(fn) {
  const cache = new Map();  // 클로저로 캐시 보관

  return (...args) => {
    const key = JSON.stringify(args);
    if (cache.has(key)) return cache.get(key);

    const result = fn(...args);
    cache.set(key, result);
    return result;
  };
}

const expensiveCalc = memoize((n) => {
  console.log("계산 중...");
  return n * n;
});

expensiveCalc(5);  // "계산 중..." → 25
expensiveCalc(5);  // 캐시 반환 → 25 (출력 없음)


// ═══ 실무 활용 4: 이벤트 핸들러 ═══
function setupButton(buttonId, apiUrl) {
  let clickCount = 0;  // 클로저로 상태 유지

  document.getElementById(buttonId).addEventListener("click", () => {
    clickCount++;
    if (clickCount >= 3) {
      alert("너무 많이 클릭했습니다!");
      return;
    }
    fetch(apiUrl);  // apiUrl도 클로저로 기억
  });
}


// ═══ 흔한 실수: 루프 + var ═══
// ❌ var는 함수 스코프라 클로저가 같은 i를 공유
for (var i = 0; i < 3; i++) {
  setTimeout(() => console.log(i), 100);  // 3, 3, 3
}

// ✅ let은 블록 스코프라 각각 다른 i
for (let i = 0; i < 3; i++) {
  setTimeout(() => console.log(i), 100);  // 0, 1, 2
}
```

**클로저 = 함수 + 그 함수가 기억하는 환경(변수)**

실무에서 가장 많이 쓰는 패턴:
1. **캡슐화** (프라이빗 변수)
2. **팩토리** (설정을 기억하는 함수 생성)
3. **메모이제이션** (결과 캐싱)
4. **이벤트 핸들러** (상태 유지)'''),

    m("이벤트 루프 설명해줘 Node.js에서",
'''Node.js 이벤트 루프의 동작 원리입니다.

```
═══ 이벤트 루프 구조 ═══

   ┌───────────────────────────┐
┌─>│         timers            │  ← setTimeout, setInterval
│  └─────────────┬─────────────┘
│  ┌─────────────┴─────────────┐
│  │     pending callbacks     │  ← I/O 콜백
│  └─────────────┬─────────────┘
│  ┌─────────────┴─────────────┐
│  │       idle, prepare       │  ← 내부 전용
│  └─────────────┬─────────────┘
│  ┌─────────────┴─────────────┐
│  │         poll              │  ← I/O 이벤트 (가장 오래 머무는 곳)
│  └─────────────┬─────────────┘
│  ┌─────────────┴─────────────┐
│  │         check             │  ← setImmediate
│  └─────────────┬─────────────┘
│  ┌─────────────┴─────────────┐
└──┤    close callbacks        │  ← socket.on('close')
   └───────────────────────────┘

각 단계 사이: process.nextTick, Promise (microtask) 실행
```

```javascript
// ═══ 실행 순서 퀴즈 ═══
console.log("1: 동기");

setTimeout(() => console.log("2: setTimeout"), 0);

Promise.resolve().then(() => console.log("3: Promise"));

process.nextTick(() => console.log("4: nextTick"));

setImmediate(() => console.log("5: setImmediate"));

console.log("6: 동기");

// 출력 순서:
// 1: 동기
// 6: 동기         ← 동기 코드 먼저
// 4: nextTick     ← microtask (가장 높은 우선순위)
// 3: Promise      ← microtask
// 2: setTimeout   ← timers 페이즈
// 5: setImmediate ← check 페이즈


// ═══ 실무 영향: 비동기 패턴 ═══

// ❌ 이벤트 루프 블로킹
app.get("/heavy", (req, res) => {
  // 5초간 CPU를 독점 → 다른 모든 요청 대기!
  const result = heavySyncComputation();
  res.json(result);
});

// ✅ 해결: Worker Thread로 분리
const { Worker } = require("worker_threads");

app.get("/heavy", (req, res) => {
  const worker = new Worker("./heavy-task.js");
  worker.on("message", (result) => res.json(result));
  worker.on("error", (err) => res.status(500).json({ error: err.message }));
});

// ✅ 또는: 청크로 나눠서 이벤트 루프에 양보
async function processLargeArray(items) {
  const CHUNK_SIZE = 100;

  for (let i = 0; i < items.length; i += CHUNK_SIZE) {
    const chunk = items.slice(i, i + CHUNK_SIZE);
    processChunk(chunk);

    // 이벤트 루프에 양보 (다른 요청 처리 가능)
    await new Promise(resolve => setImmediate(resolve));
  }
}


// ═══ 우선순위 정리 ═══
// 1. 동기 코드 (콜 스택)
// 2. process.nextTick (microtask queue)
// 3. Promise.then (microtask queue)
// 4. setTimeout/setInterval (timers)
// 5. I/O 콜백 (poll)
// 6. setImmediate (check)
// 7. close 이벤트
```

핵심 규칙:
- **동기 코드**가 항상 먼저
- **Microtask** (nextTick, Promise)가 매 페이즈 사이에 실행
- **CPU 바운드 작업**은 Worker Thread로 분리
- 이벤트 루프를 블로킹하면 모든 요청이 멈춤!'''),

    m("REST API 에러 처리 어떻게 하면 잘 할 수 있어?",
'''REST API의 체계적인 에러 처리 방법입니다.

```typescript
// ═══ 1. 일관된 에러 응답 형식 ═══
interface ApiErrorResponse {
  error: {
    code: string;           // "VALIDATION_ERROR", "NOT_FOUND"
    message: string;        // 사용자에게 보여줄 메시지
    details?: {             // 필드별 에러 (폼 검증)
      [field: string]: string[];
    };
    requestId?: string;     // 디버깅용 추적 ID
  };
}

// 성공 응답
// 200: { "data": {...} }
// 201: { "data": {...} }

// 에러 응답
// 400: { "error": { "code": "VALIDATION_ERROR", "message": "...", "details": {...} } }
// 401: { "error": { "code": "UNAUTHORIZED", "message": "로그인이 필요합니다" } }
// 403: { "error": { "code": "FORBIDDEN", "message": "권한이 없습니다" } }
// 404: { "error": { "code": "NOT_FOUND", "message": "리소스를 찾을 수 없습니다" } }
// 409: { "error": { "code": "CONFLICT", "message": "이미 존재합니다" } }
// 422: { "error": { "code": "UNPROCESSABLE", "message": "처리할 수 없습니다" } }
// 429: { "error": { "code": "RATE_LIMITED", "message": "요청 한도 초과" } }
// 500: { "error": { "code": "INTERNAL", "message": "서버 오류가 발생했습니다" } }


// ═══ 2. 커스텀 에러 클래스 ═══
class AppError extends Error {
  constructor(
    public statusCode: number,
    public code: string,
    message: string,
    public details?: Record<string, string[]>,
  ) {
    super(message);
    this.name = "AppError";
  }
}

class NotFoundError extends AppError {
  constructor(resource: string, id?: string) {
    super(404, "NOT_FOUND", `${resource}${id ? ` #${id}` : ""}을(를) 찾을 수 없습니다`);
  }
}

class ValidationError extends AppError {
  constructor(details: Record<string, string[]>) {
    super(400, "VALIDATION_ERROR", "입력값이 올바르지 않습니다", details);
  }
}

class UnauthorizedError extends AppError {
  constructor(message = "로그인이 필요합니다") {
    super(401, "UNAUTHORIZED", message);
  }
}

class ForbiddenError extends AppError {
  constructor(message = "권한이 없습니다") {
    super(403, "FORBIDDEN", message);
  }
}

class ConflictError extends AppError {
  constructor(message: string) {
    super(409, "CONFLICT", message);
  }
}


// ═══ 3. 글로벌 에러 핸들러 ═══
// Next.js API Route
function withErrorHandler(handler: Function) {
  return async (req: Request) => {
    const requestId = crypto.randomUUID().slice(0, 8);

    try {
      return await handler(req);
    } catch (error) {
      // 알려진 에러
      if (error instanceof AppError) {
        return Response.json(
          {
            error: {
              code: error.code,
              message: error.message,
              details: error.details,
              requestId,
            },
          },
          { status: error.statusCode }
        );
      }

      // Zod 검증 에러
      if (error.name === "ZodError") {
        const details: Record<string, string[]> = {};
        error.errors.forEach((e: any) => {
          const field = e.path.join(".");
          if (!details[field]) details[field] = [];
          details[field].push(e.message);
        });
        return Response.json(
          { error: { code: "VALIDATION_ERROR", message: "입력값 오류", details, requestId } },
          { status: 400 }
        );
      }

      // Prisma 에러
      if (error.code === "P2002") {
        return Response.json(
          { error: { code: "CONFLICT", message: "이미 존재하는 데이터입니다", requestId } },
          { status: 409 }
        );
      }
      if (error.code === "P2025") {
        return Response.json(
          { error: { code: "NOT_FOUND", message: "데이터를 찾을 수 없습니다", requestId } },
          { status: 404 }
        );
      }

      // 알 수 없는 에러 (500)
      console.error(`[${requestId}] 서버 에러:`, error);
      return Response.json(
        { error: { code: "INTERNAL", message: "서버 오류가 발생했습니다", requestId } },
        { status: 500 }
      );
    }
  };
}

// 사용
export const POST = withErrorHandler(async (req: Request) => {
  const body = await req.json();
  const validated = createUserSchema.parse(body);  // 실패 시 ZodError → 자동 400

  const existing = await prisma.user.findUnique({ where: { email: validated.email } });
  if (existing) throw new ConflictError("이미 가입된 이메일입니다");

  const user = await prisma.user.create({ data: validated });
  return Response.json({ data: user }, { status: 201 });
});


// ═══ 4. 클라이언트에서 에러 처리 ═══
class ApiClient {
  async request<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(url, options);

    if (!response.ok) {
      const error: ApiErrorResponse = await response.json();

      switch (response.status) {
        case 401:
          // 로그인 페이지로 리다이렉트
          window.location.href = "/login";
          break;
        case 403:
          toast.error("권한이 없습니다");
          break;
        case 422:
        case 400:
          // 폼 에러 표시
          throw new FormError(error.error.details);
        case 429:
          toast.error("요청이 너무 많습니다. 잠시 후 다시 시도해주세요.");
          break;
        default:
          toast.error(error.error.message || "오류가 발생했습니다");
      }

      throw error;
    }

    return response.json();
  }
}
```

핵심 원칙:
1. **일관된 형식**: 모든 에러를 같은 구조로 응답
2. **적절한 상태 코드**: 400, 401, 403, 404, 409, 422, 429, 500
3. **requestId**: 로그 추적용 고유 ID
4. **클라이언트 친화적**: details에 필드별 에러 포함
5. **내부 정보 노출 금지**: stack trace, DB 에러 등 절대 노출 안 함'''),

    m("CSS Grid 완벽 가이드 알려줘 실무 레이아웃으로",
'''CSS Grid의 핵심과 실무 레이아웃 패턴입니다.

```css
/* ═══ 1. 기본 개념 ═══ */

.container {
  display: grid;
  grid-template-columns: 1fr 2fr 1fr;  /* 3열: 1:2:1 비율 */
  grid-template-rows: auto 1fr auto;    /* 3행: 헤더(내용크기), 메인(남은공간), 푸터 */
  gap: 1rem;                            /* 간격 */
  min-height: 100vh;
}

/* ═══ 2. 반응형 카드 그리드 (가장 많이 쓰는 패턴) ═══ */

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  /* auto-fill: 공간에 맞게 자동 배치 */
  /* minmax(300px, 1fr): 최소 300px, 최대 균등 분할 */
  gap: 1.5rem;
}

/* 결과:
   1200px 화면: 3열
   900px 화면: 2열
   600px 화면: 1열
   → 미디어 쿼리 없이 완전 반응형! */


/* ═══ 3. 어드민 대시보드 레이아웃 ═══ */

.admin-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  grid-template-rows: 64px 1fr;
  grid-template-areas:
    "sidebar header"
    "sidebar main";
  min-height: 100vh;
}

.sidebar { grid-area: sidebar; }
.header  { grid-area: header; }
.main    { grid-area: main; overflow-y: auto; }

/* 모바일: 사이드바 숨김 */
@media (max-width: 768px) {
  .admin-layout {
    grid-template-columns: 1fr;
    grid-template-areas:
      "header"
      "main";
  }
  .sidebar { display: none; }
}


/* ═══ 4. Bento Grid (2025 트렌드) ═══ */

.bento {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: repeat(3, 200px);
  gap: 1rem;
}

.bento-large {
  grid-column: span 2;
  grid-row: span 2;
}

.bento-wide {
  grid-column: span 2;
}

.bento-tall {
  grid-row: span 2;
}


/* ═══ 5. Holy Grail 레이아웃 ═══ */

.holy-grail {
  display: grid;
  grid-template:
    "header header header" auto
    "nav    main   aside" 1fr
    "footer footer footer" auto
    / 200px 1fr 200px;
  min-height: 100vh;
  gap: 1rem;
}

.hg-header { grid-area: header; }
.hg-nav    { grid-area: nav; }
.hg-main   { grid-area: main; }
.hg-aside  { grid-area: aside; }
.hg-footer { grid-area: footer; }


/* ═══ 6. 센터링 (가장 간단) ═══ */

.center {
  display: grid;
  place-items: center;  /* 수직 + 수평 중앙 */
  min-height: 100vh;
}


/* ═══ 7. 자주 쓰는 패턴 모음 ═══ */

/* 같은 높이 카드 */
.equal-height {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-auto-rows: 1fr;  /* 모든 행 같은 높이 */
}

/* 사이드바 + 콘텐츠 (sticky sidebar) */
.with-sidebar {
  display: grid;
  grid-template-columns: minmax(200px, 300px) 1fr;
  align-items: start;
}
.with-sidebar .sidebar {
  position: sticky;
  top: 1rem;
}

/* 풀 블리드 (전체 너비) */
.full-bleed {
  display: grid;
  grid-template-columns:
    1fr
    min(65ch, 100% - 4rem)
    1fr;
}
.full-bleed > * {
  grid-column: 2;
}
.full-bleed > .full-width {
  grid-column: 1 / -1;  /* 1열부터 마지막까지 */
}

/* 오버랩 (겹치기) */
.overlap {
  display: grid;
  grid-template: 1fr / 1fr;
}
.overlap > * {
  grid-area: 1 / 1;  /* 같은 셀에 배치 → 겹침 */
}
```

핵심 정리:
| 패턴 | 코드 |
|------|------|
| 반응형 카드 | `repeat(auto-fill, minmax(300px, 1fr))` |
| 센터링 | `place-items: center` |
| 어드민 레이아웃 | `grid-template-areas` |
| 같은 높이 | `grid-auto-rows: 1fr` |
| 전체 너비 | `grid-column: 1 / -1` |'''),

    m("Zustand vs Redux vs Context 뭐 써야해?",
'''2025년 기준 React 상태관리 비교 및 선택 가이드입니다.

```typescript
// ═══ 1. Zustand (2025 추천 1순위) ═══
// 장점: 간단, 빠름, 보일러플레이트 없음, 번들 1KB

import { create } from "zustand";
import { persist, devtools } from "zustand/middleware";

interface AuthStore {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const useAuthStore = create<AuthStore>()(
  devtools(
    persist(
      (set) => ({
        user: null,
        token: null,
        login: async (email, password) => {
          const { user, token } = await authApi.login(email, password);
          set({ user, token });
        },
        logout: () => set({ user: null, token: null }),
      }),
      { name: "auth" }  // localStorage 자동 저장
    )
  )
);

// 사용 (1줄!)
const { user, logout } = useAuthStore();

// 선택적 구독 (성능 최적화)
const userName = useAuthStore((s) => s.user?.name);


// ═══ 2. Context (간단한 전역 상태만) ═══
// 장점: React 내장, 추가 패키지 없음
// 단점: 리렌더 최적화 어려움, 복잡해지면 관리 힘듦

const ThemeContext = createContext<{
  theme: "light" | "dark";
  toggle: () => void;
}>({ theme: "light", toggle: () => {} });

function ThemeProvider({ children }) {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const toggle = () => setTheme(t => t === "light" ? "dark" : "light");

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

// 문제: theme 변경 시 모든 소비자 리렌더!
// → 자주 변하는 상태에는 부적합


// ═══ 3. Redux Toolkit (대규모 앱) ═══
// 장점: 예측 가능, DevTools, 미들웨어
// 단점: 보일러플레이트 많음, 학습 곡선

import { createSlice, configureStore } from "@reduxjs/toolkit";

const authSlice = createSlice({
  name: "auth",
  initialState: { user: null, token: null },
  reducers: {
    setUser: (state, action) => { state.user = action.payload; },
    setToken: (state, action) => { state.token = action.payload; },
    logout: (state) => { state.user = null; state.token = null; },
  },
});

// Zustand보다 3배 긴 코드...
```

**2025 선택 가이드:**

| 상황 | 추천 | 이유 |
|------|------|------|
| 대부분의 프로젝트 | **Zustand** | 간단 + 빠름 + 충분한 기능 |
| 테마/언어 (거의 안 변함) | **Context** | 패키지 불필요 |
| 서버 상태 (API 데이터) | **TanStack Query** | 캐싱 + 로딩 + 에러 자동 |
| 대규모 팀 (50명+) | **Redux Toolkit** | 예측 가능 + 규칙 강제 |
| 폼 상태 | **React Hook Form** | 전용 솔루션이 최적 |
| 전역 거의 없음 | **useState + props** | 오버엔지니어링 방지 |

**실무 조합 (가장 일반적):**
```
Zustand (클라이언트 전역) + TanStack Query (서버 상태) + React Hook Form (폼)
```

이 3개면 99%의 상태관리 요구사항을 커버합니다!'''),

    m("배포할 때 체크리스트 알려줘 프로덕션",
'''프로덕션 배포 전 체크리스트입니다.

```markdown
# 프로덕션 배포 체크리스트

## 🔒 보안
- [ ] 환경변수에 시크릿 하드코딩 없음
- [ ] .env 파일 .gitignore에 포함
- [ ] HTTPS 적용 (SSL 인증서)
- [ ] CORS 화이트리스트 설정 (와일드카드 * 제거)
- [ ] API Rate Limiting 적용
- [ ] SQL Injection 방지 (ORM 사용 or 파라미터 바인딩)
- [ ] XSS 방지 (입력 이스케이프, CSP 헤더)
- [ ] CSRF 토큰 적용
- [ ] 보안 헤더 설정 (X-Frame-Options, X-Content-Type-Options)
- [ ] 의존성 취약점 스캔 (npm audit, pip-audit)

## ⚡ 성능
- [ ] 이미지 최적화 (WebP/AVIF, lazy loading)
- [ ] JavaScript 번들 분할 (dynamic import)
- [ ] CSS 최소화
- [ ] gzip/brotli 압축 활성화
- [ ] CDN 적용 (정적 파일)
- [ ] 캐시 헤더 설정 (Cache-Control)
- [ ] 데이터베이스 인덱스 확인
- [ ] N+1 쿼리 없음

## 🧪 테스트
- [ ] 단위 테스트 통과
- [ ] 통합 테스트 통과
- [ ] E2E 테스트 (핵심 플로우)
- [ ] 모바일 반응형 확인
- [ ] 브라우저 호환성 (Chrome, Safari, Firefox)
- [ ] 에러 시나리오 테스트 (네트워크 끊김, API 실패)

## 📊 모니터링
- [ ] 에러 추적 (Sentry 등)
- [ ] APM 설정 (응답 시간 모니터링)
- [ ] 로그 수집 (구조화된 JSON 로그)
- [ ] 알림 설정 (에러율 급증, 서버 다운)
- [ ] 헬스체크 엔드포인트 (/health)

## 🗄️ 데이터베이스
- [ ] 마이그레이션 적용
- [ ] 백업 설정 (자동, 매일)
- [ ] 복구 테스트 (백업에서 복원 확인)
- [ ] 커넥션 풀 설정

## 🚀 배포
- [ ] CI/CD 파이프라인 동작 확인
- [ ] 롤백 계획 수립
- [ ] 점진적 배포 (카나리/블루그린)
- [ ] 배포 후 스모크 테스트
- [ ] 도메인/DNS 설정 확인

## 📋 문서
- [ ] API 문서 최신화
- [ ] README 업데이트
- [ ] 환경변수 목록 정리 (.env.example)
- [ ] 장애 대응 매뉴얼
```

가장 중요한 3가지:
1. **시크릿 노출 확인** (git history 포함)
2. **백업 + 복구 테스트**
3. **롤백 계획** (문제 발생 시 즉시 이전 버전으로)'''),

    m("WebSocket vs SSE vs 폴링 언제 뭘 써?",
'''실시간 통신 방식 비교입니다.

```
═══ 비교 ═══

                WebSocket        SSE              폴링
방향            양방향 ↔        서버→클라이언트 →  클라이언트→서버
연결            지속 연결        지속 연결         매번 새 연결
프로토콜        ws://           HTTP              HTTP
복잡도          높음            낮음              매우 낮음
재연결          수동 구현        자동 (브라우저)    해당 없음
바이너리        지원            텍스트만           지원
HTTP/2 호환    별도             호환              호환
로드밸런서      설정 필요        쉬움              쉬움
```

```typescript
// ═══ 1. WebSocket: 양방향 실시간 (채팅, 게임) ═══
const ws = new WebSocket("wss://api.hwarang.ai/ws/chat");

ws.onopen = () => {
  ws.send(JSON.stringify({ type: "join", room: "general" }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "message") {
    addMessage(data);
  }
};

// 서버에서도 클라이언트로 보낼 수 있고
// 클라이언트에서도 서버로 보낼 수 있음 (양방향)


// ═══ 2. SSE: 서버→클라이언트 (AI 스트리밍, 알림) ═══
const eventSource = new EventSource("/api/notifications");

eventSource.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  showNotification(notification);
};

// 자동 재연결! (끊기면 브라우저가 알아서 다시 연결)
// AI 응답 스트리밍에 최적!


// ═══ 3. 폴링: 주기적 확인 (대시보드 통계) ═══
setInterval(async () => {
  const stats = await fetch("/api/stats").then(r => r.json());
  updateDashboard(stats);
}, 5000);  // 5초마다
```

**선택 가이드:**

| 사용 사례 | 추천 | 이유 |
|-----------|------|------|
| 채팅/메신저 | **WebSocket** | 양방향 실시간 필요 |
| AI 응답 스트리밍 | **SSE** | 서버→클라이언트 단방향 |
| 실시간 알림 | **SSE** | 자동 재연결, 간단 |
| 대시보드 통계 | **폴링 or SSE** | 1-5초 간격이면 폴링으로 충분 |
| 온라인 게임 | **WebSocket** | 초저지연 양방향 |
| 주식 시세 | **SSE** | 서버 푸시, 자동 재연결 |
| 파일 업로드 진행률 | **SSE** | 서버→클라이언트 |
| 협업 편집기 | **WebSocket** | 양방향 + 충돌 해결 |

실무 팁: **SSE가 되면 SSE**, WebSocket은 정말 양방향이 필요할 때만!'''),

    m("프론트엔드 폴더 구조 어떻게 잡아야해?",
'''2025년 기준 Next.js App Router 프로젝트 폴더 구조입니다.

```
src/
├── app/                          # 라우팅 (App Router)
│   ├── (auth)/                   # 인증 그룹 (레이아웃 공유)
│   │   ├── login/page.tsx
│   │   ├── register/page.tsx
│   │   └── layout.tsx            # 인증 페이지 공통 레이아웃
│   ├── (dashboard)/              # 대시보드 그룹
│   │   ├── page.tsx              # /dashboard
│   │   ├── settings/page.tsx
│   │   └── layout.tsx            # 사이드바 레이아웃
│   ├── api/                      # API Routes
│   │   ├── auth/[...nextauth]/route.ts
│   │   ├── chat/route.ts
│   │   └── users/route.ts
│   ├── layout.tsx                # 루트 레이아웃
│   ├── page.tsx                  # 홈페이지
│   └── globals.css
│
├── components/                   # 재사용 컴포넌트
│   ├── ui/                       # 기본 UI (Button, Input, Modal)
│   │   ├── button.tsx
│   │   ├── input.tsx
│   │   ├── modal.tsx
│   │   └── index.ts              # 배럴 export
│   ├── layout/                   # 레이아웃 (Header, Footer, Sidebar)
│   │   ├── header.tsx
│   │   ├── sidebar.tsx
│   │   └── footer.tsx
│   └── features/                 # 기능별 (도메인 로직 포함)
│       ├── chat/
│       │   ├── chat-area.tsx
│       │   ├── message-bubble.tsx
│       │   └── message-input.tsx
│       └── auth/
│           ├── login-form.tsx
│           └── social-buttons.tsx
│
├── hooks/                        # 커스텀 훅
│   ├── use-chat.ts
│   ├── use-auth.ts
│   ├── use-debounce.ts
│   └── use-media-query.ts
│
├── lib/                          # 유틸리티/서비스
│   ├── api-client.ts             # API 호출 클래스
│   ├── auth.ts                   # NextAuth 설정
│   ├── db.ts                     # Prisma 클라이언트
│   ├── utils.ts                  # cn(), formatDate() 등
│   └── validations.ts            # Zod 스키마
│
├── types/                        # TypeScript 타입
│   ├── api.ts                    # API 응답 타입
│   ├── chat.ts                   # 채팅 관련 타입
│   └── user.ts                   # 사용자 타입
│
└── styles/                       # 글로벌 스타일 (최소화)
    └── variables.css
```

**핵심 규칙:**

1. **`app/`**: 라우팅만 (비즈니스 로직 X)
2. **`components/ui/`**: 재사용 가능한 "바보" 컴포넌트
3. **`components/features/`**: 도메인 로직이 있는 "똑똑한" 컴포넌트
4. **`hooks/`**: 상태 + 로직 캡슐화
5. **`lib/`**: 프레임워크 독립적인 유틸리티
6. **`types/`**: 공유 타입 정의

**import 규칙:**
```
app/ → components/, hooks/, lib/
components/features/ → components/ui/, hooks/, lib/
components/ui/ → lib/ (의존성 최소)
hooks/ → lib/
```

컴포넌트가 500줄 넘으면 분리, 3곳 이상에서 쓰이면 `components/ui/`로 이동!'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/500_programming.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"프로그래밍 심화 추가: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
