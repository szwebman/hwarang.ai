"""화랑 AI 프로그래밍 패턴 학습 데이터

함수형, 반응형, 동시성, 메타프로그래밍, 이벤트 드리븐 등 최신 프로그래밍 패턴.

사용법:
    python scripts/data/build_programming_patterns.py \
        --output data/sft/programming_patterns.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 소프트웨어 엔지니어 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 함수형 프로그래밍 ═══
    m("함수형 프로그래밍 패턴 알려줘 TypeScript Python으로",
'''함수형 프로그래밍(FP)의 핵심 패턴입니다.

```typescript
// ═══ TypeScript 함수형 패턴 ═══

// 1. 순수 함수 (Pure Function) - 같은 입력 → 같은 출력, 부수효과 없음
const calculateTax = (price: number, rate: number): number => price * rate;

// 2. 불변성 (Immutability)
// ❌ 변이 (Mutation)
const addItemBad = (cart: Item[], item: Item) => {
  cart.push(item);  // 원본 변경!
  return cart;
};

// ✅ 불변 (Immutable)
const addItem = (cart: readonly Item[], item: Item): Item[] => [...cart, item];
const removeItem = (cart: readonly Item[], id: string): Item[] =>
  cart.filter((item) => item.id !== id);
const updateItem = (cart: readonly Item[], id: string, updates: Partial<Item>): Item[] =>
  cart.map((item) => (item.id === id ? { ...item, ...updates } : item));

// 3. 고차 함수 (Higher-Order Function)
const withRetry = <T>(fn: () => Promise<T>, maxRetries: number = 3) => {
  return async (): Promise<T> => {
    let lastError: Error;
    for (let i = 0; i < maxRetries; i++) {
      try {
        return await fn();
      } catch (e) {
        lastError = e as Error;
        await new Promise((r) => setTimeout(r, 1000 * (i + 1)));
      }
    }
    throw lastError!;
  };
};

// 사용
const fetchWithRetry = withRetry(() => fetch("/api/data"), 3);

// 4. 함수 합성 (Composition)
const pipe = <T>(...fns: ((arg: T) => T)[]) =>
  (value: T): T => fns.reduce((acc, fn) => fn(acc), value);

const processUser = pipe(
  (user: User) => ({ ...user, name: user.name.trim() }),
  (user: User) => ({ ...user, email: user.email.toLowerCase() }),
  (user: User) => ({ ...user, age: Math.max(0, user.age) }),
);

const result = processUser({ name: " 홍길동 ", email: "HONG@Test.COM", age: -1 });
// { name: "홍길동", email: "hong@test.com", age: 0 }

// 5. 커링 (Currying)
const multiply = (a: number) => (b: number) => a * b;
const double = multiply(2);
const triple = multiply(3);

console.log(double(5));  // 10
console.log(triple(5));  // 15

// 실무 활용: 설정 주입
const createLogger = (prefix: string) => (level: string) => (message: string) =>
  console.log(`[${prefix}] ${level}: ${message}`);

const apiLogger = createLogger("API");
const apiError = apiLogger("ERROR");
apiError("요청 실패");  // [API] ERROR: 요청 실패

// 6. Option/Maybe 패턴 (null 안전)
type Option<T> = { type: "some"; value: T } | { type: "none" };

const some = <T>(value: T): Option<T> => ({ type: "some", value });
const none = <T>(): Option<T> => ({ type: "none" });

const map = <T, U>(opt: Option<T>, fn: (v: T) => U): Option<U> =>
  opt.type === "some" ? some(fn(opt.value)) : none();

const getOrElse = <T>(opt: Option<T>, defaultValue: T): T =>
  opt.type === "some" ? opt.value : defaultValue;

// 사용
const findUser = (id: number): Option<User> =>
  users.has(id) ? some(users.get(id)!) : none();

const userName = getOrElse(
  map(findUser(1), (u) => u.name),
  "알 수 없음"
);
```

```python
# ═══ Python 함수형 패턴 ═══

from functools import reduce, partial, lru_cache
from typing import Callable, TypeVar, Iterator
from itertools import chain, islice, starmap

T = TypeVar("T")
U = TypeVar("U")

# 1. 파이프라인 패턴
def pipeline(*funcs):
    """함수를 순서대로 합성합니다."""
    def composed(data):
        return reduce(lambda acc, fn: fn(acc), funcs, data)
    return composed

# 데이터 처리 파이프라인
process = pipeline(
    lambda users: filter(lambda u: u["active"], users),      # 활성만
    lambda users: map(lambda u: u["email"], users),           # 이메일만
    lambda emails: map(str.lower, emails),                    # 소문자
    list,                                                       # 리스트로
)

emails = process(users)

# 2. 불변 데이터 (frozen dataclass)
from dataclasses import dataclass, replace

@dataclass(frozen=True)
class Config:
    host: str = "localhost"
    port: int = 8000
    debug: bool = False

# replace로 새 객체 생성 (원본 불변)
dev_config = Config(debug=True)
prod_config = replace(dev_config, debug=False, host="0.0.0.0")

# 3. 메모이제이션
@lru_cache(maxsize=256)
def fibonacci(n: int) -> int:
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# 4. 부분 적용 (Partial Application)
from functools import partial

def log(level: str, module: str, message: str):
    print(f"[{level}] {module}: {message}")

api_error = partial(log, "ERROR", "API")
api_error("요청 실패")  # [ERROR] API: 요청 실패
```

함수형 프로그래밍 핵심:
- **순수 함수**: 부수효과 없음, 테스트 쉬움
- **불변성**: 데이터 변이 방지, 예측 가능
- **합성**: 작은 함수 조합으로 복잡한 로직
- **고차 함수**: 함수를 인자로 받거나 반환'''),

    # ═══ 반응형 프로그래밍 ═══
    m("반응형 프로그래밍 패턴 알려줘 RxJS",
'''반응형 프로그래밍은 데이터 스트림을 다루는 패턴입니다.

```typescript
// ═══ RxJS 반응형 패턴 (2025 최신) ═══
import {
  Observable, Subject, BehaviorSubject,
  fromEvent, interval, merge, combineLatest,
  timer, from,
} from "rxjs";
import {
  map, filter, debounceTime, distinctUntilChanged,
  switchMap, mergeMap, catchError, retry, take,
  tap, shareReplay, scan, throttleTime,
  takeUntil, finalize, exhaustMap,
} from "rxjs/operators";

// 1. 검색 자동완성 (디바운스 + 중복 제거 + 취소)
const searchInput = document.getElementById("search") as HTMLInputElement;

const search$ = fromEvent(searchInput, "input").pipe(
  map((e) => (e.target as HTMLInputElement).value.trim()),
  filter((query) => query.length >= 2),       // 2자 이상
  debounceTime(300),                           // 300ms 대기
  distinctUntilChanged(),                      // 같은 값 무시
  switchMap((query) =>                         // 이전 요청 취소
    from(fetch(`/api/search?q=${query}`).then((r) => r.json())).pipe(
      catchError(() => []),                    // 에러 시 빈 배열
    )
  ),
);

search$.subscribe((results) => renderResults(results));

// 2. 실시간 데이터 폴링 (자동 새로고침)
const polling$ = timer(0, 5000).pipe(  // 즉시 시작, 5초 간격
  switchMap(() => from(fetch("/api/stats").then((r) => r.json()))),
  retry({ count: 3, delay: 1000 }),    // 3회 재시도
  shareReplay(1),                       // 구독자 간 결과 공유
);

// 3. 무한 스크롤
const scroll$ = fromEvent(window, "scroll").pipe(
  throttleTime(200),
  filter(() => {
    const { scrollHeight, scrollTop, clientHeight } = document.documentElement;
    return scrollHeight - scrollTop - clientHeight < 200;  // 하단 200px
  }),
  exhaustMap(() =>                     // 이전 요청 완료 후에만
    from(fetchNextPage()),
  ),
);

// 4. 상태 관리 (Redux 대체)
interface AppState {
  users: User[];
  loading: boolean;
  error: string | null;
}

type Action =
  | { type: "LOAD_START" }
  | { type: "LOAD_SUCCESS"; users: User[] }
  | { type: "LOAD_ERROR"; error: string };

const action$ = new Subject<Action>();
const initialState: AppState = { users: [], loading: false, error: null };

const state$ = action$.pipe(
  scan((state: AppState, action: Action): AppState => {
    switch (action.type) {
      case "LOAD_START":
        return { ...state, loading: true, error: null };
      case "LOAD_SUCCESS":
        return { ...state, loading: false, users: action.users };
      case "LOAD_ERROR":
        return { ...state, loading: false, error: action.error };
    }
  }, initialState),
  shareReplay(1),
);

// 디스패치
action$.next({ type: "LOAD_START" });

// 5. 여러 소스 결합
const user$ = new BehaviorSubject<User | null>(null);
const permissions$ = new BehaviorSubject<string[]>([]);

const canEdit$ = combineLatest([user$, permissions$]).pipe(
  map(([user, perms]) => !!user && perms.includes("edit")),
  distinctUntilChanged(),
);

// 6. 메모리 누수 방지
class MyComponent {
  private destroy$ = new Subject<void>();

  init() {
    interval(1000).pipe(
      takeUntil(this.destroy$),  // 컴포넌트 파괴 시 자동 구독 해제
    ).subscribe((tick) => this.update(tick));
  }

  destroy() {
    this.destroy$.next();
    this.destroy$.complete();
  }
}

// 7. 에러 복구 전략
const resilientStream$ = source$.pipe(
  retry({
    count: 3,
    delay: (error, retryCount) => timer(1000 * retryCount),  // 지수 백오프
  }),
  catchError((err) => {
    console.error("최종 실패:", err);
    return of(fallbackValue);  // 폴백 값
  }),
);
```

RxJS 연산자 선택 가이드:
| 상황 | 연산자 |
|------|--------|
| 이전 요청 취소 | `switchMap` |
| 모든 요청 병렬 | `mergeMap` |
| 순서 보장 | `concatMap` |
| 중복 방지 (1개만) | `exhaustMap` |
| 입력 지연 | `debounceTime` |
| 빈도 제한 | `throttleTime` |
| 값 변경 시만 | `distinctUntilChanged` |
| 여러 소스 결합 | `combineLatest` |'''),

    # ═══ 동시성/병렬 패턴 ═══
    m("동시성 프로그래밍 패턴 알려줘",
'''동시성(Concurrency)과 병렬(Parallelism) 프로그래밍 패턴입니다.

```typescript
// ═══ TypeScript/Node.js 동시성 패턴 ═══

// 1. Promise.all - 병렬 실행 (모두 성공해야)
async function fetchDashboard() {
  const [users, orders, stats] = await Promise.all([
    fetchUsers(),
    fetchOrders(),
    fetchStats(),
  ]);
  return { users, orders, stats };
}

// 2. Promise.allSettled - 병렬 실행 (실패해도 계속)
async function sendNotifications(userIds: string[]) {
  const results = await Promise.allSettled(
    userIds.map((id) => sendEmail(id))
  );

  const succeeded = results.filter((r) => r.status === "fulfilled").length;
  const failed = results.filter((r) => r.status === "rejected").length;
  console.log(`성공: ${succeeded}, 실패: ${failed}`);
}

// 3. 동시성 제한 (Concurrency Limiter)
async function asyncPool<T, R>(
  items: T[],
  concurrency: number,
  fn: (item: T) => Promise<R>
): Promise<R[]> {
  const results: R[] = [];
  const executing = new Set<Promise<void>>();

  for (const item of items) {
    const p = fn(item).then((result) => {
      results.push(result);
      executing.delete(p);
    });
    executing.add(p);

    if (executing.size >= concurrency) {
      await Promise.race(executing);
    }
  }

  await Promise.all(executing);
  return results;
}

// 최대 5개 동시 다운로드
await asyncPool(urls, 5, downloadFile);

// 4. 작업 큐 (Task Queue)
class TaskQueue {
  private queue: (() => Promise<void>)[] = [];
  private running = 0;
  private concurrency: number;

  constructor(concurrency: number = 3) {
    this.concurrency = concurrency;
  }

  async add<T>(task: () => Promise<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      this.queue.push(async () => {
        try {
          resolve(await task());
        } catch (e) {
          reject(e);
        }
      });
      this.process();
    });
  }

  private async process() {
    while (this.running < this.concurrency && this.queue.length > 0) {
      this.running++;
      const task = this.queue.shift()!;
      task().finally(() => {
        this.running--;
        this.process();
      });
    }
  }
}

const queue = new TaskQueue(3);
await queue.add(() => processImage("photo1.jpg"));
await queue.add(() => processImage("photo2.jpg"));

// 5. Worker Threads (CPU 바운드)
import { Worker, isMainThread, parentPort, workerData } from "worker_threads";

if (isMainThread) {
  // 메인 스레드: 워커 생성
  function runWorker(data: any): Promise<any> {
    return new Promise((resolve, reject) => {
      const worker = new Worker(__filename, { workerData: data });
      worker.on("message", resolve);
      worker.on("error", reject);
    });
  }

  // 4개 워커로 병렬 처리
  const chunks = splitArray(largeData, 4);
  const results = await Promise.all(chunks.map(runWorker));
} else {
  // 워커 스레드: 무거운 계산
  const result = heavyComputation(workerData);
  parentPort!.postMessage(result);
}

// 6. AbortController (취소)
async function fetchWithCancel(url: string, timeoutMs: number) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, { signal: controller.signal });
    return await response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}
```

```python
# ═══ Python 동시성 패턴 ═══

import asyncio
from concurrent.futures import ProcessPoolExecutor

# 세마포어로 동시성 제한
async def limited_fetch(urls: list[str], max_concurrent: int = 10):
    sem = asyncio.Semaphore(max_concurrent)
    async def fetch_one(url):
        async with sem:
            async with httpx.AsyncClient() as client:
                return await client.get(url)
    return await asyncio.gather(*[fetch_one(url) for url in urls])

# 생산자-소비자 패턴
async def producer_consumer():
    queue = asyncio.Queue(maxsize=100)

    async def producer():
        for item in generate_items():
            await queue.put(item)
        await queue.put(None)  # 종료 신호

    async def consumer(worker_id: int):
        while True:
            item = await queue.get()
            if item is None:
                await queue.put(None)
                break
            await process(item)
            queue.task_done()

    await asyncio.gather(
        producer(),
        *[consumer(i) for i in range(5)]  # 5개 워커
    )
```

동시성 패턴 선택:
| 작업 유형 | 패턴 |
|-----------|------|
| I/O 바운드 (API, DB) | `async/await` + `Promise.all` |
| CPU 바운드 | Worker Threads / multiprocessing |
| 동시성 제한 | Semaphore / asyncPool |
| 작업 대기열 | Task Queue / Bull |
| 취소 필요 | AbortController |'''),

    # ═══ 이벤트 드리븐 ═══
    m("이벤트 드리븐 아키텍처 패턴 알려줘",
'''이벤트 드리븐 아키텍처(EDA)의 실무 패턴입니다.

```typescript
// ═══ 1. 이벤트 에미터 (Event Emitter) ═══
import { EventEmitter } from "events";

// 타입 안전한 이벤트 에미터
type AppEvents = {
  "user:created": [user: User];
  "user:updated": [user: User, changes: Partial<User>];
  "order:placed": [order: Order];
  "order:paid": [orderId: string, amount: number];
  "error": [error: Error, context: string];
};

class TypedEmitter {
  private emitter = new EventEmitter();

  on<K extends keyof AppEvents>(event: K, listener: (...args: AppEvents[K]) => void) {
    this.emitter.on(event, listener as any);
    return this;
  }

  emit<K extends keyof AppEvents>(event: K, ...args: AppEvents[K]) {
    this.emitter.emit(event, ...args);
  }

  off<K extends keyof AppEvents>(event: K, listener: (...args: AppEvents[K]) => void) {
    this.emitter.off(event, listener as any);
  }
}

const bus = new TypedEmitter();

// 이벤트 핸들러 등록
bus.on("user:created", async (user) => {
  await sendWelcomeEmail(user);
  await createDefaultSettings(user);
  await trackAnalytics("signup", { userId: user.id });
});

bus.on("order:placed", async (order) => {
  await reserveInventory(order.items);
  await notifyShop(order);
});

// 이벤트 발행
bus.emit("user:created", newUser);

// ═══ 2. 도메인 이벤트 패턴 ═══
interface DomainEvent {
  type: string;
  timestamp: Date;
  aggregateId: string;
  payload: Record<string, unknown>;
}

class Order {
  private events: DomainEvent[] = [];

  place(items: OrderItem[]) {
    // 비즈니스 로직
    this.status = "placed";
    this.items = items;

    // 도메인 이벤트 기록
    this.events.push({
      type: "OrderPlaced",
      timestamp: new Date(),
      aggregateId: this.id,
      payload: { items, total: this.total },
    });
  }

  cancel(reason: string) {
    if (this.status === "shipped") {
      throw new Error("배송 시작 후 취소 불가");
    }
    this.status = "cancelled";
    this.events.push({
      type: "OrderCancelled",
      timestamp: new Date(),
      aggregateId: this.id,
      payload: { reason },
    });
  }

  pullEvents(): DomainEvent[] {
    const events = [...this.events];
    this.events = [];
    return events;
  }
}

// 리포지토리에서 이벤트 발행
async function saveOrder(order: Order) {
  await db.save(order);
  const events = order.pullEvents();
  for (const event of events) {
    await eventBus.publish(event);  // 비동기 처리
  }
}

// ═══ 3. CQRS (Command Query Responsibility Segregation) ═══
// 쓰기(Command)와 읽기(Query) 분리

// 커맨드 (쓰기)
interface CreateOrderCommand {
  type: "CreateOrder";
  customerId: string;
  items: { productId: string; quantity: number }[];
}

class CommandHandler {
  async handle(command: CreateOrderCommand) {
    const order = new Order(command.customerId, command.items);
    await this.orderRepo.save(order);
    // 이벤트 발행 → Read Model 업데이트
  }
}

// 쿼리 (읽기) - 별도 최적화된 모델
interface OrderSummary {
  id: string;
  customerName: string;  // 비정규화
  itemCount: number;
  total: number;
  status: string;
}

class QueryHandler {
  async getOrderSummaries(customerId: string): Promise<OrderSummary[]> {
    // 읽기 전용 DB/캐시에서 조회 (빠름)
    return this.readDb.query(
      "SELECT * FROM order_summaries WHERE customer_id = ?",
      [customerId]
    );
  }
}

// ═══ 4. 이벤트 소싱 (Event Sourcing) ═══
// 상태 대신 이벤트의 시퀀스를 저장

class EventStore {
  async append(aggregateId: string, events: DomainEvent[]) {
    await db.insert("events", events.map((e) => ({
      aggregate_id: aggregateId,
      type: e.type,
      payload: JSON.stringify(e.payload),
      timestamp: e.timestamp,
    })));
  }

  async getEvents(aggregateId: string): Promise<DomainEvent[]> {
    return db.query(
      "SELECT * FROM events WHERE aggregate_id = ? ORDER BY timestamp",
      [aggregateId]
    );
  }
}

// 이벤트에서 현재 상태 재구성
function rebuildOrder(events: DomainEvent[]): Order {
  const order = new Order();
  for (const event of events) {
    switch (event.type) {
      case "OrderPlaced":
        order.status = "placed";
        order.items = event.payload.items;
        break;
      case "OrderPaid":
        order.status = "paid";
        break;
      case "OrderCancelled":
        order.status = "cancelled";
        break;
    }
  }
  return order;
}
```

이벤트 드리븐 핵심:
- **느슨한 결합**: 서비스 간 직접 호출 대신 이벤트 발행
- **도메인 이벤트**: 비즈니스 의미를 가진 이벤트 (OrderPlaced, UserCreated)
- **CQRS**: 쓰기/읽기 모델 분리 → 각각 최적화
- **이벤트 소싱**: 상태 대신 이벤트 히스토리 저장 → 시간 여행 가능'''),

    # ═══ 에러 처리 패턴 ═══
    m("에러 처리 프로그래밍 패턴 알려줘 최신으로",
'''2025년 기준 최신 에러 처리 패턴입니다.

```typescript
// ═══ 1. Result 패턴 (Go/Rust 스타일) ═══
// 예외 대신 반환값으로 에러 처리

type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

function ok<T>(value: T): Result<T, never> {
  return { ok: true, value };
}

function err<E>(error: E): Result<never, E> {
  return { ok: false, error };
}

// 사용
async function createUser(data: CreateUserInput): Result<User, string> {
  if (!data.email.includes("@")) {
    return err("올바른 이메일을 입력하세요");
  }

  const existing = await db.user.findByEmail(data.email);
  if (existing) {
    return err("이미 가입된 이메일입니다");
  }

  const user = await db.user.create(data);
  return ok(user);
}

// 호출
const result = await createUser(input);
if (!result.ok) {
  return res.status(400).json({ error: result.error });
}
console.log(result.value.name);  // 타입 안전

// 2. Result 체이닝
function mapResult<T, U, E>(result: Result<T, E>, fn: (v: T) => U): Result<U, E> {
  return result.ok ? ok(fn(result.value)) : result;
}

async function flatMapResult<T, U, E>(
  result: Result<T, E>,
  fn: (v: T) => Promise<Result<U, E>>
): Promise<Result<U, E>> {
  return result.ok ? fn(result.value) : result;
}

// ═══ 2. Either 모나드 ═══
class Either<L, R> {
  private constructor(
    private readonly left: L | null,
    private readonly right: R | null,
  ) {}

  static left<L>(value: L): Either<L, never> {
    return new Either(value, null);
  }

  static right<R>(value: R): Either<never, R> {
    return new Either(null, value);
  }

  map<U>(fn: (r: R) => U): Either<L, U> {
    return this.right !== null
      ? Either.right(fn(this.right))
      : Either.left(this.left!);
  }

  flatMap<U>(fn: (r: R) => Either<L, U>): Either<L, U> {
    return this.right !== null ? fn(this.right) : Either.left(this.left!);
  }

  fold<U>(onLeft: (l: L) => U, onRight: (r: R) => U): U {
    return this.right !== null ? onRight(this.right) : onLeft(this.left!);
  }
}

// 파이프라인 에러 처리
const processOrder = (input: OrderInput) =>
  validateOrder(input)                    // Either<Error, ValidOrder>
    .flatMap(checkInventory)               // Either<Error, OrderWithStock>
    .flatMap(calculateShipping)            // Either<Error, OrderWithShipping>
    .flatMap(processPayment)               // Either<Error, PaidOrder>
    .fold(
      (error) => ({ status: 400, error: error.message }),
      (order) => ({ status: 201, data: order }),
    );

// ═══ 3. 에러 바운더리 (React) ═══
"use client";
import { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}

class ErrorBoundary extends Component<Props, { hasError: boolean; error: Error | null }> {
  state = { hasError: false, error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
    // 에러 리포팅 서비스로 전송
    reportError(error, info);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="p-8 text-center">
          <h2 className="text-xl font-bold">오류가 발생했습니다</h2>
          <p className="mt-2 text-gray-500">{this.state.error?.message}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-4 rounded bg-blue-600 px-4 py-2 text-white"
          >
            다시 시도
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ═══ 4. Retry with Circuit Breaker ═══
class SmartRetry {
  private failures = 0;
  private lastFailure = 0;
  private state: "closed" | "open" | "half-open" = "closed";

  constructor(
    private maxRetries = 3,
    private breakerThreshold = 5,
    private cooldown = 30000,
  ) {}

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === "open") {
      if (Date.now() - this.lastFailure > this.cooldown) {
        this.state = "half-open";
      } else {
        throw new Error("서킷 오픈: 서비스 일시 중단");
      }
    }

    for (let i = 0; i <= this.maxRetries; i++) {
      try {
        const result = await fn();
        this.onSuccess();
        return result;
      } catch (e) {
        if (i === this.maxRetries) {
          this.onFailure();
          throw e;
        }
        await this.delay(i);
      }
    }
    throw new Error("unreachable");
  }

  private onSuccess() { this.failures = 0; this.state = "closed"; }
  private onFailure() {
    this.failures++;
    this.lastFailure = Date.now();
    if (this.failures >= this.breakerThreshold) this.state = "open";
  }
  private delay(attempt: number) {
    return new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** attempt, 30000)));
  }
}
```

에러 처리 전략:
- **Result 패턴**: 예외 대신 반환값 → 에러 무시 불가
- **Either 모나드**: 함수형 에러 체이닝
- **Error Boundary**: React 컴포넌트 에러 격리
- **Circuit Breaker**: 장애 전파 방지'''),

    # ═══ 상태 머신 ═══
    m("상태 머신 패턴 알려줘 XState 포함",
'''상태 머신으로 복잡한 상태 전이를 명확하게 관리합니다.

```typescript
// ═══ XState v5 (2025 최신) ═══
import { createMachine, assign, createActor } from "xstate";

// 1. 주문 상태 머신
const orderMachine = createMachine({
  id: "order",
  initial: "draft",
  context: {
    orderId: "",
    items: [] as OrderItem[],
    total: 0,
    error: null as string | null,
  },
  states: {
    draft: {
      on: {
        ADD_ITEM: {
          actions: assign({
            items: ({ context, event }) => [...context.items, event.item],
            total: ({ context, event }) => context.total + event.item.price,
          }),
        },
        SUBMIT: {
          target: "validating",
          guard: ({ context }) => context.items.length > 0,
        },
      },
    },
    validating: {
      invoke: {
        src: "validateOrder",
        onDone: { target: "pending_payment" },
        onError: {
          target: "draft",
          actions: assign({ error: ({ event }) => event.error.message }),
        },
      },
    },
    pending_payment: {
      on: {
        PAY: { target: "processing_payment" },
        CANCEL: { target: "cancelled" },
      },
      after: {
        // 30분 후 자동 취소
        1800000: { target: "cancelled" },
      },
    },
    processing_payment: {
      invoke: {
        src: "processPayment",
        onDone: { target: "confirmed" },
        onError: {
          target: "pending_payment",
          actions: assign({ error: ({ event }) => event.error.message }),
        },
      },
    },
    confirmed: {
      on: {
        SHIP: { target: "shipped" },
        CANCEL: { target: "refunding" },
      },
    },
    shipped: {
      on: {
        DELIVER: { target: "delivered" },
        RETURN: { target: "return_requested" },
      },
    },
    delivered: {
      type: "final",
    },
    return_requested: {
      on: {
        APPROVE_RETURN: { target: "refunding" },
        REJECT_RETURN: { target: "delivered" },
      },
    },
    refunding: {
      invoke: {
        src: "processRefund",
        onDone: { target: "refunded" },
        onError: { target: "refund_failed" },
      },
    },
    refunded: { type: "final" },
    refund_failed: {
      on: { RETRY_REFUND: { target: "refunding" } },
    },
    cancelled: { type: "final" },
  },
});

// 사용
const actor = createActor(orderMachine);
actor.subscribe((snapshot) => {
  console.log("현재 상태:", snapshot.value);
  console.log("컨텍스트:", snapshot.context);
});

actor.start();
actor.send({ type: "ADD_ITEM", item: { name: "노트북", price: 1500000 } });
actor.send({ type: "SUBMIT" });

// 2. 간단한 직접 구현 (라이브러리 없이)
type OrderState = "draft" | "pending" | "confirmed" | "shipped" | "delivered" | "cancelled";
type OrderEvent = "submit" | "pay" | "ship" | "deliver" | "cancel";

const transitions: Record<OrderState, Partial<Record<OrderEvent, OrderState>>> = {
  draft:     { submit: "pending", cancel: "cancelled" },
  pending:   { pay: "confirmed", cancel: "cancelled" },
  confirmed: { ship: "shipped", cancel: "cancelled" },
  shipped:   { deliver: "delivered" },
  delivered: {},
  cancelled: {},
};

function transition(state: OrderState, event: OrderEvent): OrderState {
  const nextState = transitions[state]?.[event];
  if (!nextState) {
    throw new Error(`잘못된 전이: ${state} + ${event}`);
  }
  return nextState;
}

let state: OrderState = "draft";
state = transition(state, "submit");   // "pending"
state = transition(state, "pay");      // "confirmed"
state = transition(state, "ship");     // "shipped"
// transition(state, "cancel");  // Error! shipped에서 cancel 불가
```

상태 머신 적용 시나리오:
- **주문 처리**: draft → pending → confirmed → shipped → delivered
- **인증 플로우**: idle → loading → authenticated / error
- **파일 업로드**: idle → uploading(progress) → success / failed
- **위자드/스텝폼**: step1 → step2 → step3 → complete
- **게임 상태**: menu → playing → paused → gameover'''),

    # ═══ 의존성 주입 ═══
    m("의존성 주입 패턴 알려줘 TypeScript Python",
'''의존성 주입(DI)으로 테스트 가능하고 유연한 코드를 만듭니다.

```typescript
// ═══ TypeScript DI 패턴 ═══

// 1. 인터페이스 기반 (수동 DI)
interface UserRepository {
  findById(id: string): Promise<User | null>;
  save(user: User): Promise<User>;
}

interface EmailService {
  send(to: string, subject: string, body: string): Promise<void>;
}

// 구현체
class PrismaUserRepository implements UserRepository {
  constructor(private db: PrismaClient) {}

  async findById(id: string) {
    return this.db.user.findUnique({ where: { id } });
  }

  async save(user: User) {
    return this.db.user.upsert({
      where: { id: user.id },
      update: user,
      create: user,
    });
  }
}

class ResendEmailService implements EmailService {
  async send(to: string, subject: string, body: string) {
    await resend.emails.send({ from: "noreply@hwarang.ai", to, subject, html: body });
  }
}

// 서비스 (의존성 주입)
class UserService {
  constructor(
    private userRepo: UserRepository,     // 인터페이스
    private emailService: EmailService,   // 인터페이스
  ) {}

  async register(data: RegisterInput): Promise<User> {
    const user = await this.userRepo.save(new User(data));
    await this.emailService.send(user.email, "환영합니다", "가입 완료!");
    return user;
  }
}

// 조립 (Composition Root)
const userRepo = new PrismaUserRepository(prisma);
const emailService = new ResendEmailService();
const userService = new UserService(userRepo, emailService);

// 테스트 (Mock 주입)
const mockRepo: UserRepository = {
  findById: vi.fn().mockResolvedValue({ id: "1", name: "테스트" }),
  save: vi.fn().mockImplementation((u) => Promise.resolve(u)),
};
const mockEmail: EmailService = {
  send: vi.fn().mockResolvedValue(undefined),
};
const testService = new UserService(mockRepo, mockEmail);

// 2. tsyringe (DI 컨테이너)
import { container, injectable, inject } from "tsyringe";

@injectable()
class UserService {
  constructor(
    @inject("UserRepository") private userRepo: UserRepository,
    @inject("EmailService") private email: EmailService,
  ) {}
}

// 등록
container.register("UserRepository", { useClass: PrismaUserRepository });
container.register("EmailService", { useClass: ResendEmailService });

// 해결
const service = container.resolve(UserService);
```

```python
# ═══ Python DI 패턴 ═══

from abc import ABC, abstractmethod
from dataclasses import dataclass

# 1. 프로토콜 기반 (duck typing)
from typing import Protocol

class UserRepository(Protocol):
    async def find_by_id(self, user_id: int) -> User | None: ...
    async def save(self, user: User) -> User: ...

class EmailService(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...

# 서비스
class UserService:
    def __init__(self, repo: UserRepository, email: EmailService):
        self._repo = repo
        self._email = email

    async def register(self, data: dict) -> User:
        user = await self._repo.save(User(**data))
        await self._email.send(user.email, "환영합니다", "가입 완료!")
        return user

# 2. FastAPI Depends (프레임워크 DI)
from fastapi import Depends, FastAPI

app = FastAPI()

def get_user_repo() -> UserRepository:
    return SQLAlchemyUserRepository(get_session())

def get_email_service() -> EmailService:
    return SMTPEmailService()

def get_user_service(
    repo: UserRepository = Depends(get_user_repo),
    email: EmailService = Depends(get_email_service),
) -> UserService:
    return UserService(repo, email)

@app.post("/users")
async def create_user(
    data: CreateUserInput,
    service: UserService = Depends(get_user_service),
):
    return await service.register(data.dict())

# 3. 테스트에서 의존성 교체
app.dependency_overrides[get_user_repo] = lambda: MockUserRepository()
app.dependency_overrides[get_email_service] = lambda: MockEmailService()
```

DI 핵심:
- **인터페이스에 의존** (구현체에 의존하지 않음)
- **조립은 최상위에서** (Composition Root)
- **테스트에서 Mock 주입** (DB/이메일 없이 테스트)
- **프레임워크 DI**: FastAPI `Depends`, NestJS `@Injectable`'''),

    # ═══ 메모이제이션 & 캐싱 패턴 ═══
    m("캐싱 전략 패턴 알려줘 프로그래밍에서",
'''애플리케이션 레벨 캐싱 전략 패턴입니다.

```typescript
// ═══ 1. 메모이제이션 (함수 결과 캐시) ═══
function memoize<T extends (...args: any[]) => any>(fn: T): T {
  const cache = new Map<string, ReturnType<T>>();

  return ((...args: Parameters<T>) => {
    const key = JSON.stringify(args);
    if (cache.has(key)) return cache.get(key)!;
    const result = fn(...args);
    cache.set(key, result);
    return result;
  }) as T;
}

// TTL 있는 메모이제이션
function memoizeWithTTL<T extends (...args: any[]) => any>(
  fn: T,
  ttlMs: number = 60000
): T {
  const cache = new Map<string, { value: ReturnType<T>; expiresAt: number }>();

  return ((...args: Parameters<T>) => {
    const key = JSON.stringify(args);
    const cached = cache.get(key);
    const now = Date.now();

    if (cached && cached.expiresAt > now) {
      return cached.value;
    }

    const result = fn(...args);
    cache.set(key, { value: result, expiresAt: now + ttlMs });
    return result;
  }) as T;
}

// ═══ 2. Cache-Aside (가장 일반적) ═══
class UserService {
  constructor(
    private db: Database,
    private cache: Redis,
  ) {}

  async getUser(id: string): Promise<User> {
    // 1. 캐시 확인
    const cached = await this.cache.get(`user:${id}`);
    if (cached) return JSON.parse(cached);

    // 2. DB 조회
    const user = await this.db.user.findUnique({ where: { id } });
    if (!user) throw new NotFoundError("User", id);

    // 3. 캐시 저장 (5분 TTL)
    await this.cache.setex(`user:${id}`, 300, JSON.stringify(user));
    return user;
  }

  async updateUser(id: string, data: Partial<User>): Promise<User> {
    const user = await this.db.user.update({ where: { id }, data });
    // 캐시 무효화
    await this.cache.del(`user:${id}`);
    return user;
  }
}

// ═══ 3. Write-Through (쓰기 시 캐시 동시 업데이트) ═══
async function writeThrough(id: string, data: User) {
  // DB와 캐시 동시 업데이트
  await Promise.all([
    db.user.update({ where: { id }, data }),
    cache.setex(`user:${id}`, 300, JSON.stringify(data)),
  ]);
}

// ═══ 4. Stale-While-Revalidate ═══
async function getWithSWR<T>(
  key: string,
  fetcher: () => Promise<T>,
  maxAge: number = 60,    // 신선 기간 (초)
  staleAge: number = 300, // 오래된 데이터 허용 기간 (초)
): Promise<T> {
  const cached = await cache.get(key);

  if (cached) {
    const { data, fetchedAt } = JSON.parse(cached);
    const age = (Date.now() - fetchedAt) / 1000;

    if (age < maxAge) {
      return data;  // 신선한 데이터
    }

    if (age < staleAge) {
      // 오래됐지만 허용 범위 → 일단 반환 + 백그라운드 갱신
      refreshInBackground(key, fetcher);
      return data;
    }
  }

  // 캐시 없거나 너무 오래됨 → 새로 가져오기
  const fresh = await fetcher();
  await cache.set(key, JSON.stringify({ data: fresh, fetchedAt: Date.now() }));
  return fresh;
}

// ═══ 5. React 캐싱 (TanStack Query) ═══
function useUser(userId: string) {
  return useQuery({
    queryKey: ["user", userId],
    queryFn: () => fetchUser(userId),
    staleTime: 5 * 60 * 1000,     // 5분간 fresh
    gcTime: 30 * 60 * 1000,        // 30분간 GC 안 함
    refetchOnWindowFocus: true,    // 탭 전환 시 리페치
    retry: 2,
  });
}

// 선행 데이터 로딩 (prefetch)
function UserList() {
  const queryClient = useQueryClient();

  return (
    <ul>
      {users.map((user) => (
        <li
          key={user.id}
          onMouseEnter={() => {
            // 마우스 올리면 미리 로드
            queryClient.prefetchQuery({
              queryKey: ["user", user.id],
              queryFn: () => fetchUser(user.id),
            });
          }}
        >
          <Link href={`/users/${user.id}`}>{user.name}</Link>
        </li>
      ))}
    </ul>
  );
}
```

캐싱 전략 선택:
| 전략 | 적합한 상황 |
|------|-------------|
| Cache-Aside | 읽기 많은 데이터 (사용자, 설정) |
| Write-Through | 항상 최신 데이터 필요 |
| SWR | UX 중시 (빠른 응답 + 백그라운드 갱신) |
| Write-Behind | 쓰기 빈번한 데이터 (조회수, 로그) |'''),

    # ═══ 옵저버/미들웨어 패턴 ═══
    m("미들웨어 패턴이랑 플러그인 패턴 알려줘",
'''미들웨어와 플러그인 패턴으로 확장 가능한 코드를 만듭니다.

```typescript
// ═══ 1. 미들웨어 패턴 (Express/Koa 스타일) ═══
type Context = {
  request: Request;
  response: Response;
  state: Record<string, unknown>;
};

type Middleware = (ctx: Context, next: () => Promise<void>) => Promise<void>;

class MiddlewarePipeline {
  private middlewares: Middleware[] = [];

  use(middleware: Middleware) {
    this.middlewares.push(middleware);
    return this;
  }

  async execute(ctx: Context) {
    let index = 0;
    const next = async () => {
      if (index < this.middlewares.length) {
        const middleware = this.middlewares[index++];
        await middleware(ctx, next);
      }
    };
    await next();
  }
}

// 미들웨어 구현
const logger: Middleware = async (ctx, next) => {
  const start = Date.now();
  console.log(`→ ${ctx.request.method} ${ctx.request.url}`);
  await next();
  console.log(`← ${ctx.response.status} (${Date.now() - start}ms)`);
};

const auth: Middleware = async (ctx, next) => {
  const token = ctx.request.headers.get("Authorization");
  if (!token) {
    ctx.response = new Response("인증 필요", { status: 401 });
    return;  // next() 안 부름 → 체인 중단
  }
  ctx.state.user = await verifyToken(token);
  await next();
};

const rateLimit = (max: number, windowMs: number): Middleware => {
  const requests = new Map<string, number[]>();

  return async (ctx, next) => {
    const ip = ctx.request.headers.get("x-forwarded-for") || "unknown";
    const now = Date.now();
    const windowStart = now - windowMs;

    const timestamps = (requests.get(ip) || []).filter((t) => t > windowStart);
    if (timestamps.length >= max) {
      ctx.response = new Response("요청 한도 초과", { status: 429 });
      return;
    }

    timestamps.push(now);
    requests.set(ip, timestamps);
    await next();
  };
};

// 조립
const app = new MiddlewarePipeline();
app.use(logger);
app.use(rateLimit(100, 60000));
app.use(auth);
app.use(async (ctx, next) => {
  // 실제 핸들러
  ctx.response = new Response(JSON.stringify({ data: "hello" }));
});

// ═══ 2. 플러그인 패턴 ═══
interface Plugin {
  name: string;
  version: string;
  install(app: App): void | Promise<void>;
}

class App {
  private plugins = new Map<string, Plugin>();
  private hooks = new Map<string, ((...args: any[]) => any)[]>();

  async use(plugin: Plugin) {
    if (this.plugins.has(plugin.name)) {
      throw new Error(`플러그인 중복: ${plugin.name}`);
    }
    await plugin.install(this);
    this.plugins.set(plugin.name, plugin);
    console.log(`✅ 플러그인 설치: ${plugin.name} v${plugin.version}`);
  }

  // 훅 등록
  hook(name: string, fn: (...args: any[]) => any) {
    const hooks = this.hooks.get(name) || [];
    hooks.push(fn);
    this.hooks.set(name, hooks);
  }

  // 훅 실행
  async applyHooks<T>(name: string, value: T): Promise<T> {
    const hooks = this.hooks.get(name) || [];
    let result = value;
    for (const hook of hooks) {
      result = await hook(result);
    }
    return result;
  }
}

// 플러그인 구현
const analyticsPlugin: Plugin = {
  name: "analytics",
  version: "1.0.0",
  install(app) {
    app.hook("request:before", (ctx) => {
      ctx.startTime = Date.now();
      return ctx;
    });
    app.hook("request:after", (ctx) => {
      const duration = Date.now() - ctx.startTime;
      trackEvent("api_request", { path: ctx.path, duration });
      return ctx;
    });
  },
};

const cachePlugin: Plugin = {
  name: "cache",
  version: "1.0.0",
  install(app) {
    const cache = new Map();
    app.hook("request:before", (ctx) => {
      const cached = cache.get(ctx.cacheKey);
      if (cached) ctx.response = cached;
      return ctx;
    });
    app.hook("request:after", (ctx) => {
      if (ctx.cacheable) cache.set(ctx.cacheKey, ctx.response);
      return ctx;
    });
  },
};

// 사용
const app = new App();
await app.use(analyticsPlugin);
await app.use(cachePlugin);

// ═══ 3. 인터셉터 패턴 (Axios 스타일) ═══
class HttpClient {
  private requestInterceptors: ((config: RequestConfig) => RequestConfig)[] = [];
  private responseInterceptors: ((response: Response) => Response)[] = [];

  interceptRequest(fn: (config: RequestConfig) => RequestConfig) {
    this.requestInterceptors.push(fn);
  }

  interceptResponse(fn: (response: Response) => Response) {
    this.responseInterceptors.push(fn);
  }

  async request(config: RequestConfig) {
    // 요청 인터셉터
    let finalConfig = config;
    for (const interceptor of this.requestInterceptors) {
      finalConfig = interceptor(finalConfig);
    }

    // 실제 요청
    let response = await fetch(finalConfig.url, finalConfig);

    // 응답 인터셉터
    for (const interceptor of this.responseInterceptors) {
      response = interceptor(response);
    }
    return response;
  }
}

// 인터셉터 등록
const client = new HttpClient();
client.interceptRequest((config) => {
  config.headers.Authorization = `Bearer ${getToken()}`;
  return config;
});
client.interceptResponse((response) => {
  if (response.status === 401) refreshToken();
  return response;
});
```

패턴 선택:
| 패턴 | 사용 시나리오 |
|------|--------------|
| 미들웨어 | 요청/응답 파이프라인 (로깅, 인증, 에러) |
| 플러그인 | 기능 확장 (서드파티, 선택적 기능) |
| 인터셉터 | HTTP 클라이언트 공통 처리 |
| 훅 | 특정 시점에 코드 삽입 (라이프사이클) |'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/programming_patterns.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 프로그래밍 패턴 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  프로그래밍 패턴: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
