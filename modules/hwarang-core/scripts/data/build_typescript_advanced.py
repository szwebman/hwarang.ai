"""화랑 AI TypeScript 고급 학습 데이터

제네릭, 유틸리티 타입, 조건부 타입, 타입 가드, 데코레이터 등.

사용법:
    python scripts/data/build_typescript_advanced.py \
        --output data/sft/typescript_advanced.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 TypeScript 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("TypeScript 제네릭 고급 패턴 알려줘",
'''제네릭으로 타입 안전하고 재사용 가능한 코드를 만듭니다.

```typescript
// ═══ 1. 제네릭 함수 ═══

// 배열에서 특정 키로 그룹핑
function groupBy<T, K extends keyof T>(items: T[], key: K): Map<T[K], T[]> {
  const map = new Map<T[K], T[]>();
  for (const item of items) {
    const group = item[key];
    const arr = map.get(group) || [];
    arr.push(item);
    map.set(group, arr);
  }
  return map;
}

// 사용
const users = [
  { name: "홍길동", role: "admin" },
  { name: "김철수", role: "user" },
  { name: "이영희", role: "admin" },
];
const grouped = groupBy(users, "role");
// Map { "admin" => [{...}, {...}], "user" => [{...}] }

// 깊은 객체 접근 (타입 안전)
type DeepKeyOf<T> = T extends object
  ? { [K in keyof T]: K extends string
      ? T[K] extends object ? `${K}.${DeepKeyOf<T[K]>}` | K : K
      : never
    }[keyof T]
  : never;

function deepGet<T, P extends string>(obj: T, path: P): unknown {
  return path.split(".").reduce((acc: any, key) => acc?.[key], obj);
}

// ═══ 2. 제네릭 클래스 ═══

// 타입 안전한 이벤트 에미터
class TypedEventEmitter<Events extends Record<string, any[]>> {
  private listeners = new Map<keyof Events, Set<Function>>();

  on<K extends keyof Events>(event: K, listener: (...args: Events[K]) => void) {
    const set = this.listeners.get(event) || new Set();
    set.add(listener);
    this.listeners.set(event, set);
    return () => set.delete(listener);
  }

  emit<K extends keyof Events>(event: K, ...args: Events[K]) {
    this.listeners.get(event)?.forEach((fn) => fn(...args));
  }
}

// 사용
type AppEvents = {
  "user:login": [user: User];
  "user:logout": [];
  "message:new": [message: Message, sender: User];
};

const emitter = new TypedEventEmitter<AppEvents>();
emitter.on("user:login", (user) => console.log(user.name)); // ✅ 타입 추론
emitter.emit("message:new", message, sender);                // ✅ 인자 타입 체크

// ═══ 3. 제네릭 제약 (Constraints) ═══

// Comparable 제약
function max<T extends { valueOf(): number }>(a: T, b: T): T {
  return a.valueOf() > b.valueOf() ? a : b;
}

// 특정 키 보장
function pluck<T, K extends keyof T>(items: T[], key: K): T[K][] {
  return items.map((item) => item[key]);
}

const names = pluck(users, "name");  // string[]
const roles = pluck(users, "role");  // string[]

// 최소 하나의 속성 보장
type AtLeastOne<T> = {
  [K in keyof T]: Pick<T, K> & Partial<Omit<T, K>>;
}[keyof T];

type SearchParams = AtLeastOne<{
  name: string;
  email: string;
  phone: string;
}>;

// 최소 하나는 필수
const params: SearchParams = { name: "홍길동" };  // ✅
// const bad: SearchParams = {};  // ❌ 에러!

// ═══ 4. 제네릭 + 조건부 타입 ═══

// API 응답 타입 자동 추론
type ApiEndpoints = {
  "/users": { response: User[]; params: { page: number } };
  "/users/:id": { response: User; params: { id: string } };
  "/posts": { response: Post[]; params: { limit: number } };
};

async function api<T extends keyof ApiEndpoints>(
  endpoint: T,
  params: ApiEndpoints[T]["params"]
): Promise<ApiEndpoints[T]["response"]> {
  const url = buildUrl(endpoint, params);
  const res = await fetch(url);
  return res.json();
}

// 완전한 타입 추론
const users = await api("/users", { page: 1 });      // User[]
const user = await api("/users/:id", { id: "123" });  // User
```

제네릭 실무 규칙:
- 타입 파라미터는 **실제로 사용될 때만** 추가
- `extends`로 제약을 걸어 타입 안전성 확보
- 제네릭보다 유니온이 간단하면 유니온 사용
- IDE 자동완성이 잘 되는 방향으로 설계'''),

    m("TypeScript 유틸리티 타입 완전 정리해줘",
'''TypeScript 유틸리티 타입 전체 정리 + 커스텀 유틸리티입니다.

```typescript
// ═══ 내장 유틸리티 타입 ═══

interface User {
  id: number;
  name: string;
  email: string;
  role: "admin" | "user";
  createdAt: Date;
}

// 1. Partial<T> - 모든 속성 선택적
type UserUpdate = Partial<User>;
// { id?: number; name?: string; email?: string; ... }

// 2. Required<T> - 모든 속성 필수
type StrictUser = Required<User>;

// 3. Pick<T, K> - 특정 속성만 선택
type UserPreview = Pick<User, "id" | "name">;
// { id: number; name: string }

// 4. Omit<T, K> - 특정 속성 제외
type UserInput = Omit<User, "id" | "createdAt">;
// { name: string; email: string; role: "admin" | "user" }

// 5. Record<K, V> - 키-값 매핑
type RolePermissions = Record<User["role"], string[]>;
// { admin: string[]; user: string[] }

// 6. Readonly<T> - 모든 속성 읽기 전용
type FrozenUser = Readonly<User>;
// const user: FrozenUser; user.name = "x"; // ❌ 에러

// 7. ReturnType<T> - 함수 반환 타입 추출
function createUser() { return { id: 1, name: "홍길동" }; }
type CreatedUser = ReturnType<typeof createUser>;
// { id: number; name: string }

// 8. Parameters<T> - 함수 매개변수 타입 추출
type CreateUserParams = Parameters<typeof createUser>;
// []

// 9. Awaited<T> - Promise 언래핑
type UserData = Awaited<Promise<User>>;  // User

// 10. Extract / Exclude
type AdminRole = Extract<User["role"], "admin">;  // "admin"
type NonAdmin = Exclude<User["role"], "admin">;    // "user"

// 11. NonNullable
type MaybeString = string | null | undefined;
type DefiniteString = NonNullable<MaybeString>;  // string

// ═══ 커스텀 유틸리티 타입 ═══

// 1. DeepPartial (중첩 객체도 선택적)
type DeepPartial<T> = T extends object
  ? { [K in keyof T]?: DeepPartial<T[K]> }
  : T;

// 2. DeepReadonly (중첩 객체도 읽기 전용)
type DeepReadonly<T> = T extends object
  ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
  : T;

// 3. 특정 키만 필수, 나머지 선택
type RequireKeys<T, K extends keyof T> = Omit<Partial<T>, K> & Pick<T, K>;
type UserWithName = RequireKeys<User, "name" | "email">;
// name, email 필수, 나머지 선택

// 4. Nullable (null 허용)
type Nullable<T> = { [K in keyof T]: T[K] | null };

// 5. 값 타입 추출
type ValueOf<T> = T[keyof T];
type UserValues = ValueOf<User>;  // number | string | Date | "admin" | "user"

// 6. 함수 키만 추출
type FunctionKeys<T> = {
  [K in keyof T]: T[K] extends (...args: any[]) => any ? K : never;
}[keyof T];

// 7. 변경 감지 타입
type Changes<T> = {
  [K in keyof T]?: {
    old: T[K];
    new: T[K];
  };
};
type UserChanges = Changes<User>;
// { name?: { old: string; new: string }; ... }

// 8. 경로 타입 (API 라우트)
type PathParams<T extends string> =
  T extends `${infer _}:${infer Param}/${infer Rest}`
    ? { [K in Param | keyof PathParams<Rest>]: string }
    : T extends `${infer _}:${infer Param}`
    ? { [K in Param]: string }
    : {};

type Params = PathParams<"/users/:userId/posts/:postId">;
// { userId: string; postId: string }

// ═══ 실무 조합 ═══

// API 요청/응답 타입
type ApiRequest<T> = {
  body: Omit<T, "id" | "createdAt" | "updatedAt">;
  params: Pick<T, "id">;
  response: T;
};

// 폼 타입 (id 제외, 필드별 에러)
type FormData<T> = Omit<T, "id" | "createdAt">;
type FormErrors<T> = Partial<Record<keyof FormData<T>, string>>;

const errors: FormErrors<User> = {
  name: "이름은 필수입니다",
  email: "올바른 이메일을 입력하세요",
};
```

유틸리티 타입 사용 가이드:
| 상황 | 타입 |
|------|------|
| API 입력 (id 제외) | `Omit<T, "id">` |
| 수정 요청 (일부만) | `Partial<T>` |
| 미리보기 (일부만) | `Pick<T, "id" \\| "name">` |
| 설정 (깊은 병합) | `DeepPartial<T>` |
| 불변 데이터 | `Readonly<T>` |
| 폼 에러 | `Partial<Record<keyof T, string>>` |'''),

    m("TypeScript 타입 가드랑 타입 좁히기 알려줘",
'''타입 가드로 런타임에 타입을 안전하게 좁힙니다.

```typescript
// ═══ 1. typeof 가드 ═══
function process(input: string | number) {
  if (typeof input === "string") {
    return input.toUpperCase();  // string으로 좁혀짐
  }
  return input.toFixed(2);       // number로 좁혀짐
}

// ═══ 2. instanceof 가드 ═══
class ApiError extends Error {
  constructor(public statusCode: number, message: string) {
    super(message);
  }
}

class ValidationError extends Error {
  constructor(public field: string, message: string) {
    super(message);
  }
}

function handleError(error: unknown) {
  if (error instanceof ApiError) {
    console.log(`API 에러 ${error.statusCode}: ${error.message}`);
  } else if (error instanceof ValidationError) {
    console.log(`검증 에러 (${error.field}): ${error.message}`);
  } else if (error instanceof Error) {
    console.log(`일반 에러: ${error.message}`);
  } else {
    console.log(`알 수 없는 에러: ${error}`);
  }
}

// ═══ 3. in 연산자 가드 ═══
type Dog = { bark(): void; breed: string };
type Cat = { meow(): void; color: string };
type Animal = Dog | Cat;

function makeSound(animal: Animal) {
  if ("bark" in animal) {
    animal.bark();  // Dog로 좁혀짐
  } else {
    animal.meow();  // Cat으로 좁혀짐
  }
}

// ═══ 4. 커스텀 타입 가드 (is 키워드) ═══
interface User {
  type: "user";
  name: string;
  email: string;
}

interface Admin {
  type: "admin";
  name: string;
  permissions: string[];
}

type Account = User | Admin;

// 타입 가드 함수
function isAdmin(account: Account): account is Admin {
  return account.type === "admin";
}

function getPermissions(account: Account): string[] {
  if (isAdmin(account)) {
    return account.permissions;  // Admin으로 좁혀짐
  }
  return [];
}

// 배열 필터링에서 타입 가드
const accounts: Account[] = [...];
const admins = accounts.filter(isAdmin);  // Admin[] 타입!

// ═══ 5. 판별 유니온 (Discriminated Union) ═══
type Result<T> =
  | { success: true; data: T }
  | { success: false; error: string };

function handleResult<T>(result: Result<T>) {
  if (result.success) {
    console.log(result.data);   // T 타입
  } else {
    console.log(result.error);  // string 타입
  }
}

// API 상태 관리
type RequestState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; error: Error };

function renderState<T>(state: RequestState<T>) {
  switch (state.status) {
    case "idle":
      return <Placeholder />;
    case "loading":
      return <Spinner />;
    case "success":
      return <Content data={state.data} />;  // T 타입
    case "error":
      return <ErrorView error={state.error} />;
  }
}

// ═══ 6. assertion 함수 ═══
function assertDefined<T>(
  value: T | null | undefined,
  message: string = "값이 없습니다"
): asserts value is T {
  if (value === null || value === undefined) {
    throw new Error(message);
  }
}

function processUser(user: User | null) {
  assertDefined(user, "사용자를 찾을 수 없습니다");
  // 이 이후부터 user는 User 타입 (null 아님)
  console.log(user.name);
}

// ═══ 7. satisfies 연산자 (TS 4.9+) ═══
type Colors = Record<string, [number, number, number] | string>;

const palette = {
  red: [255, 0, 0],
  green: "#00ff00",
  blue: [0, 0, 255],
} satisfies Colors;

// 타입 추론 유지 + 타입 체크
palette.red[0];       // ✅ number (튜플로 추론됨)
palette.green.toUpperCase(); // ✅ string으로 추론됨
```

타입 좁히기 선택:
| 상황 | 방법 |
|------|------|
| 원시 타입 구분 | `typeof` |
| 클래스 인스턴스 | `instanceof` |
| 속성 존재 확인 | `in` 연산자 |
| 복잡한 조건 | 커스텀 타입 가드 (`is`) |
| 태그 기반 유니온 | 판별 유니온 (`type` / `status`) |
| null 체크 | `assertDefined` |'''),

    m("TypeScript 고급 타입 패턴 알려줘 템플릿 리터럴 타입 포함",
'''TypeScript 5.x 고급 타입 패턴입니다.

```typescript
// ═══ 1. 템플릿 리터럴 타입 ═══

// API 엔드포인트 타입
type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";
type ApiVersion = "v1" | "v2";
type Resource = "users" | "posts" | "comments";

type ApiEndpoint = `/${ApiVersion}/${Resource}`;
// "/v1/users" | "/v1/posts" | "/v1/comments" | "/v2/users" | ...

// CSS 유틸리티 타입
type Size = "sm" | "md" | "lg" | "xl";
type Direction = "t" | "r" | "b" | "l" | "x" | "y";
type SpacingClass = `p${Direction}-${Size}` | `m${Direction}-${Size}`;
// "pt-sm" | "pt-md" | ... | "mx-xl" | "my-xl"

// 이벤트 핸들러 타입
type EventName = "click" | "change" | "submit" | "focus";
type HandlerName = `on${Capitalize<EventName>}`;
// "onClick" | "onChange" | "onSubmit" | "onFocus"

// ═══ 2. 조건부 타입 고급 ═══

// 배열이면 요소 타입, 아니면 그대로
type UnwrapArray<T> = T extends (infer U)[] ? U : T;
type A = UnwrapArray<string[]>;   // string
type B = UnwrapArray<number>;      // number

// Promise 깊이 무관하게 언래핑
type DeepAwaited<T> = T extends Promise<infer U> ? DeepAwaited<U> : T;
type C = DeepAwaited<Promise<Promise<string>>>;  // string

// 함수 첫 번째 인자 타입
type FirstArg<T extends (...args: any) => any> = T extends (first: infer F, ...rest: any) => any ? F : never;
type D = FirstArg<(name: string, age: number) => void>;  // string

// ═══ 3. Mapped Types 고급 ═══

// 읽기 전용 필드만 추출
type ReadonlyKeys<T> = {
  [K in keyof T]-?: IfEquals<
    { [Q in K]: T[K] },
    { -readonly [Q in K]: T[K] },
    never,
    K
  >;
}[keyof T];

// getter/setter 자동 생성
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

type Setters<T> = {
  [K in keyof T as `set${Capitalize<string & K>}`]: (value: T[K]) => void;
};

type UserAccessors = Getters<User> & Setters<User>;
// { getName: () => string; setName: (value: string) => void; ... }

// 특정 타입의 키만 추출
type KeysOfType<T, V> = {
  [K in keyof T]: T[K] extends V ? K : never;
}[keyof T];

type StringKeys = KeysOfType<User, string>;  // "name" | "email"
type NumberKeys = KeysOfType<User, number>;   // "id"

// ═══ 4. infer 패턴 ═══

// 라우트 파라미터 추출
type ExtractParams<T extends string> =
  T extends `${string}:${infer Param}/${infer Rest}`
    ? Param | ExtractParams<Rest>
    : T extends `${string}:${infer Param}`
    ? Param
    : never;

type Params = ExtractParams<"/api/users/:userId/posts/:postId">;
// "userId" | "postId"

// JSON 파싱 타입 (재귀)
type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

// ═══ 5. const assertion + as const ═══
const ROUTES = {
  HOME: "/",
  USERS: "/users",
  USER_DETAIL: "/users/:id",
  SETTINGS: "/settings",
} as const;

type Route = typeof ROUTES[keyof typeof ROUTES];
// "/" | "/users" | "/users/:id" | "/settings"

// enum 대신 as const
const Status = {
  ACTIVE: "active",
  INACTIVE: "inactive",
  PENDING: "pending",
} as const;

type StatusType = typeof Status[keyof typeof Status];
// "active" | "inactive" | "pending"

// ═══ 6. 브랜드 타입 (Branded Types) ═══
// 구조적으로 같지만 의미적으로 다른 타입 구분

type Brand<T, B extends string> = T & { __brand: B };

type UserId = Brand<string, "UserId">;
type PostId = Brand<string, "PostId">;

function getUser(id: UserId): User { ... }
function getPost(id: PostId): Post { ... }

const userId = "user_123" as UserId;
const postId = "post_456" as PostId;

getUser(userId);   // ✅
getUser(postId);   // ❌ 타입 에러! PostId는 UserId가 아님

// 통화 타입
type KRW = Brand<number, "KRW">;
type USD = Brand<number, "USD">;

function addKRW(a: KRW, b: KRW): KRW {
  return (a + b) as KRW;
}

const price1 = 10000 as KRW;
const price2 = 20000 as KRW;
const dollars = 100 as USD;

addKRW(price1, price2);  // ✅
addKRW(price1, dollars);  // ❌ KRW와 USD 혼합 불가
```

고급 타입 핵심:
- **템플릿 리터럴**: 문자열 패턴 타입 생성
- **조건부 타입 + infer**: 타입에서 정보 추출
- **Mapped Types**: 기존 타입 변환
- **as const**: 리터럴 타입 보존
- **브랜드 타입**: 같은 구조, 다른 의미 구분'''),

    m("TypeScript + Zod 스키마 검증 패턴 알려줘",
'''Zod로 런타임 검증 + TypeScript 타입 추론을 동시에 합니다.

```typescript
import { z } from "zod";

// ═══ 1. 스키마 정의 ═══
const userSchema = z.object({
  name: z.string().min(2, "이름은 2자 이상").max(50),
  email: z.string().email("올바른 이메일을 입력하세요"),
  age: z.number().int().min(0).max(150).optional(),
  role: z.enum(["admin", "user", "editor"]),
  tags: z.array(z.string()).max(10).default([]),
  profile: z.object({
    bio: z.string().max(500).optional(),
    avatar: z.string().url().optional(),
    links: z.array(z.string().url()).max(5).default([]),
  }).optional(),
  createdAt: z.coerce.date(),  // 문자열 → Date 자동 변환
});

// 타입 자동 추론
type User = z.infer<typeof userSchema>;
// { name: string; email: string; age?: number; role: "admin" | "user" | "editor"; ... }

// ═══ 2. 변환 스키마 ═══
const createUserSchema = userSchema
  .omit({ createdAt: true })     // createdAt 제외
  .extend({                        // 필드 추가
    password: z.string().min(8).regex(/[A-Z]/, "대문자 포함 필수"),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "비밀번호가 일치하지 않습니다",
    path: ["confirmPassword"],
  });

type CreateUserInput = z.infer<typeof createUserSchema>;

// ═══ 3. 환경변수 검증 ═══
const envSchema = z.object({
  NODE_ENV: z.enum(["development", "production", "test"]),
  DATABASE_URL: z.string().url(),
  REDIS_URL: z.string().url(),
  JWT_SECRET: z.string().min(32),
  PORT: z.coerce.number().default(3000),
  OPENAI_API_KEY: z.string().startsWith("sk-").optional(),
});

// 앱 시작 시 검증
const env = envSchema.parse(process.env);
// 실패 시 상세한 에러 메시지 + 앱 중단

// ═══ 4. API 요청/응답 검증 ═══
// Next.js API Route
import { NextRequest, NextResponse } from "next/server";

const searchParamsSchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  sort: z.enum(["name", "createdAt", "email"]).default("createdAt"),
  order: z.enum(["asc", "desc"]).default("desc"),
  q: z.string().min(1).optional(),
});

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const params = searchParamsSchema.safeParse(
    Object.fromEntries(searchParams)
  );

  if (!params.success) {
    return NextResponse.json(
      { error: "입력값 오류", details: params.error.flatten() },
      { status: 422 }
    );
  }

  // params.data는 완전히 타입 안전
  const { page, limit, sort, order, q } = params.data;
  // ...
}

// ═══ 5. 판별 유니온 스키마 ═══
const notificationSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("email"),
    to: z.string().email(),
    subject: z.string(),
    body: z.string(),
  }),
  z.object({
    type: z.literal("sms"),
    phone: z.string().regex(/^01[0-9]-\\d{4}-\\d{4}$/),
    message: z.string().max(90),
  }),
  z.object({
    type: z.literal("push"),
    token: z.string(),
    title: z.string(),
    body: z.string(),
  }),
]);

type Notification = z.infer<typeof notificationSchema>;

// ═══ 6. 재사용 가능한 스키마 조합 ═══
// 공통 필드
const withId = z.object({ id: z.string().uuid() });
const withTimestamps = z.object({
  createdAt: z.coerce.date(),
  updatedAt: z.coerce.date(),
});

// 합성
const fullUserSchema = userSchema.merge(withId).merge(withTimestamps);
type FullUser = z.infer<typeof fullUserSchema>;

// 페이지네이션 응답
function paginatedSchema<T extends z.ZodType>(itemSchema: T) {
  return z.object({
    data: z.array(itemSchema),
    pagination: z.object({
      page: z.number(),
      limit: z.number(),
      total: z.number(),
      totalPages: z.number(),
    }),
  });
}

const userListSchema = paginatedSchema(fullUserSchema);
type UserListResponse = z.infer<typeof userListSchema>;
```

Zod 핵심:
- **스키마 = 타입**: 한 번 정의하면 검증 + 타입 추론 동시
- `parse()` → 실패 시 예외 / `safeParse()` → Result 반환
- `z.coerce` → 자동 타입 변환 (string→number, string→date)
- `refine()` → 커스텀 검증 (비밀번호 확인 등)
- `discriminatedUnion()` → 판별 유니온 검증'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/typescript_advanced.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI TypeScript 고급 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  TypeScript 고급: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
