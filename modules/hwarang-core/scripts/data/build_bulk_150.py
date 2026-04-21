"""500건 달성을 위한 벌크 데이터 150건

다양한 분야의 실무 Q&A. 짧지만 깊이 있는 답변.
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ JavaScript/TypeScript 실무 (30건) ═══
    m("map, filter, reduce 차이 알려줘",
'''배열 메서드 3총사입니다.

```javascript
const numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

// map: 변환 (1:1 매핑)
const doubled = numbers.map(n => n * 2);
// [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]

// filter: 조건에 맞는 것만 추출
const evens = numbers.filter(n => n % 2 === 0);
// [2, 4, 6, 8, 10]

// reduce: 하나의 값으로 축소
const sum = numbers.reduce((acc, n) => acc + n, 0);
// 55

// 실무 조합
const result = users
  .filter(u => u.isActive)           // 활성 사용자만
  .map(u => ({ name: u.name, email: u.email }))  // 필요한 필드만
  .reduce((acc, u) => {              // 이메일별 그룹핑
    acc[u.email] = u.name;
    return acc;
  }, {});
```

| 메서드 | 입력 | 출력 | 용도 |
|--------|------|------|------|
| `map` | 배열 N개 | 배열 N개 | 변환 |
| `filter` | 배열 N개 | 배열 ≤N개 | 필터링 |
| `reduce` | 배열 N개 | 값 1개 | 집계 |'''),

    m("async/await 에러 처리 패턴 알려줘",
'''async/await에서 에러를 깔끔하게 처리하는 패턴입니다.

```typescript
// ❌ 매번 try/catch (장황)
async function getUser() {
  try {
    const user = await fetchUser();
    return user;
  } catch (error) {
    console.error(error);
    return null;
  }
}

// ✅ 패턴 1: Go 스타일 래퍼
async function to<T>(promise: Promise<T>): Promise<[null, T] | [Error, null]> {
  try {
    const data = await promise;
    return [null, data];
  } catch (error) {
    return [error as Error, null];
  }
}

// 사용
const [error, user] = await to(fetchUser(id));
if (error) {
  return res.status(500).json({ error: error.message });
}
console.log(user.name);  // 타입 안전!

// ✅ 패턴 2: 상위 레벨 에러 바운더리
async function handleRequest(req, res) {
  const user = await fetchUser(req.params.id);  // 실패 시 throw
  const posts = await fetchPosts(user.id);       // 실패 시 throw
  return res.json({ user, posts });
}

// 글로벌 에러 핸들러가 잡아줌
app.use((error, req, res, next) => {
  res.status(error.status || 500).json({ error: error.message });
});

// ✅ 패턴 3: Promise.allSettled (부분 실패 허용)
const [userResult, postsResult] = await Promise.allSettled([
  fetchUser(id),
  fetchPosts(id),
]);

const user = userResult.status === "fulfilled" ? userResult.value : null;
const posts = postsResult.status === "fulfilled" ? postsResult.value : [];
```'''),

    m("spread operator 활용법 알려줘",
'''스프레드 연산자(...) 활용법입니다.

```typescript
// 1. 배열 복사/합치기
const a = [1, 2, 3];
const b = [...a, 4, 5];         // [1, 2, 3, 4, 5]
const c = [...a, ...b];          // 합치기
const copy = [...a];             // 얕은 복사

// 2. 객체 복사/병합
const user = { name: "홍길동", age: 28 };
const updated = { ...user, age: 29 };  // age만 변경
const full = { ...user, email: "hong@test.com" };  // 필드 추가

// 3. 불변 업데이트 (React 상태)
const [items, setItems] = useState([]);
setItems(prev => [...prev, newItem]);              // 추가
setItems(prev => prev.filter(i => i.id !== id));  // 삭제
setItems(prev => prev.map(i =>                    // 수정
  i.id === id ? { ...i, name: "새이름" } : i
));

// 4. 함수 인자 펼치기
const args = [1, 2, 3];
Math.max(...args);  // Math.max(1, 2, 3)

// 5. 나머지 파라미터 (rest)
function log(first, ...rest) {
  console.log(first);   // 첫 번째
  console.log(rest);    // 나머지 배열
}

// 6. 구조 분해 + rest
const { id, ...rest } = user;  // id 제외한 나머지
const [head, ...tail] = [1, 2, 3, 4];  // head=1, tail=[2,3,4]

// 7. 조건부 속성
const config = {
  name: "화랑",
  ...(isDev && { debug: true }),      // 개발 모드일 때만
  ...(user && { userId: user.id }),    // user 있을 때만
};
```'''),

    m("optional chaining이랑 nullish coalescing 알려줘",
'''`?.`와 `??` 연산자 설명입니다.

```typescript
// ═══ Optional Chaining (?.) ═══
// undefined/null이면 에러 대신 undefined 반환

const user = { profile: { address: { city: "서울" } } };

// ❌ 길고 반복적
if (user && user.profile && user.profile.address) {
  console.log(user.profile.address.city);
}

// ✅ 간결
console.log(user?.profile?.address?.city);  // "서울"
console.log(user?.settings?.theme);          // undefined (에러 안 남)

// 메서드 호출
user?.sendEmail?.();           // 메서드 있으면 호출, 없으면 undefined
array?.[0];                    // 배열 접근
map?.get?.("key");             // Map 접근


// ═══ Nullish Coalescing (??) ═══
// null 또는 undefined일 때만 기본값 (0, "", false는 유효!)

// ❌ || 의 문제: 0, "", false도 기본값으로 대체됨
const count = data.count || 10;   // data.count가 0이면 → 10 (의도와 다름!)

// ✅ ?? 사용: null/undefined만 기본값
const count = data.count ?? 10;   // data.count가 0이면 → 0 (의도대로!)
const name = data.name ?? "알 수 없음";
const flag = data.enabled ?? true;

// 실무 조합
const city = user?.profile?.address?.city ?? "미설정";
const theme = settings?.theme ?? "light";
const page = Number(searchParams.get("page")) || 1;  // 여기선 || 적절

// ═══ 비교 ═══
// ||  : falsy 값 (0, "", false, null, undefined) → 기본값
// ??  : nullish 값 (null, undefined만) → 기본값
```'''),

    m("구조 분해 할당 심화 알려줘",
'''구조 분해(Destructuring) 심화 패턴입니다.

```typescript
// ═══ 객체 ═══
const user = { name: "홍길동", age: 28, email: "hong@test.com", role: "admin" };

// 기본
const { name, age } = user;

// 이름 변경
const { name: userName, email: userEmail } = user;

// 기본값
const { theme = "light", lang = "ko" } = settings;

// 중첩
const { profile: { address: { city } } } = user;

// 나머지
const { id, ...updateData } = user;  // id 제외
await prisma.user.update({ where: { id }, data: updateData });

// ═══ 배열 ═══
const [first, second, ...rest] = [1, 2, 3, 4, 5];
const [, , third] = [1, 2, 3];  // 3번째만

// 스왑
let a = 1, b = 2;
[a, b] = [b, a];  // a=2, b=1

// ═══ 함수 매개변수 ═══
// 옵션 객체 패턴
function createUser({
  name,
  email,
  role = "user",
  isActive = true,
}: {
  name: string;
  email: string;
  role?: string;
  isActive?: boolean;
}) {
  // ...
}

// React 컴포넌트
function Card({ title, children, className = "" }: CardProps) {
  return <div className={className}>{children}</div>;
}

// ═══ 실무 패턴 ═══
// API 응답 파싱
const { data: users, pagination: { total, page } } = await api.getUsers();

// React 훅 반환
const [state, setState] = useState(initial);
const { data, error, isLoading } = useQuery(...);

// import 구조 분해
import { useState, useEffect, useCallback } from "react";
```'''),

    m("타입 가드 패턴 알려줘 TypeScript",
'''TypeScript 타입 가드로 런타임에 타입을 안전하게 좁힙니다.

```typescript
// 1. typeof 가드
function process(value: string | number) {
  if (typeof value === "string") {
    return value.toUpperCase();  // string 확정
  }
  return value.toFixed(2);      // number 확정
}

// 2. in 연산자
type Dog = { bark: () => void };
type Cat = { meow: () => void };

function speak(pet: Dog | Cat) {
  if ("bark" in pet) {
    pet.bark();  // Dog 확정
  } else {
    pet.meow();  // Cat 확정
  }
}

// 3. 커스텀 타입 가드 (is)
function isUser(obj: unknown): obj is User {
  return (
    typeof obj === "object" &&
    obj !== null &&
    "name" in obj &&
    "email" in obj
  );
}

// 배열에서 사용
const items: (User | null)[] = [...];
const users = items.filter((item): item is User => item !== null);
// users: User[] 타입!

// 4. 판별 유니온 (가장 추천)
type Result =
  | { status: "success"; data: User }
  | { status: "error"; message: string }
  | { status: "loading" };

function render(result: Result) {
  switch (result.status) {
    case "success": return <User data={result.data} />;
    case "error": return <Error msg={result.message} />;
    case "loading": return <Spinner />;
  }
}

// 5. assertion 함수
function assertDefined<T>(val: T | null | undefined, msg?: string): asserts val is T {
  if (val == null) throw new Error(msg || "값이 없습니다");
}

const user = await findUser(id);
assertDefined(user, "사용자를 찾을 수 없습니다");
// 이 이후 user는 확정된 User 타입
console.log(user.name);
```'''),

    m("Array 메서드 총정리 해줘",
'''자주 쓰는 배열 메서드 총정리입니다.

```javascript
const arr = [1, 2, 3, 4, 5];

// ═══ 변환 ═══
arr.map(x => x * 2)           // [2, 4, 6, 8, 10]
arr.flatMap(x => [x, x*2])    // [1,2, 2,4, 3,6, 4,8, 5,10]
Array.from({length:5}, (_, i) => i)  // [0, 1, 2, 3, 4]

// ═══ 필터 ═══
arr.filter(x => x > 3)        // [4, 5]
arr.find(x => x > 3)          // 4 (첫 번째)
arr.findIndex(x => x > 3)     // 3 (인덱스)

// ═══ 검사 ═══
arr.includes(3)                // true
arr.every(x => x > 0)         // true (모두 만족)
arr.some(x => x > 4)          // true (하나라도)

// ═══ 축소 ═══
arr.reduce((sum, x) => sum + x, 0)  // 15
arr.reduceRight(...)           // 오른쪽부터

// ═══ 정렬 ═══
[3,1,2].sort()                 // [1, 2, 3]
[3,1,2].sort((a,b) => b - a)  // [3, 2, 1] 내림차순
[...arr].sort()                // 원본 보존

// ═══ 추가/제거 (불변) ═══
[...arr, 6]                    // 끝에 추가
[0, ...arr]                    // 앞에 추가
arr.filter(x => x !== 3)      // 3 제거
arr.slice(1, 3)                // [2, 3] (인덱스 1~2)

// ═══ 변형 (원본 변경) ═══
arr.push(6)                    // 끝에 추가
arr.pop()                      // 끝에서 제거
arr.unshift(0)                 // 앞에 추가
arr.shift()                    // 앞에서 제거
arr.splice(2, 1)               // 인덱스 2에서 1개 제거

// ═══ 2025 신규 ═══
arr.at(-1)                     // 5 (마지막)
arr.findLast(x => x < 4)      // 3
arr.toSorted()                 // 정렬 (원본 불변!)
arr.toReversed()               // 뒤집기 (원본 불변!)
arr.toSpliced(2, 1)            // splice (원본 불변!)
arr.with(2, 99)                // 인덱스 2를 99로 (원본 불변!)
Object.groupBy(arr, x => x%2 ? 'odd' : 'even')  // 그룹핑
```

핵심: **원본 변경 피하려면** `toSorted`, `toReversed`, `toSpliced`, `with` 사용!'''),

    m("fetch API 사용법 알려줘 실무에서",
'''fetch API 실무 사용법입니다.

```typescript
// ═══ 기본 사용 ═══

// GET
const response = await fetch("/api/users");
const users = await response.json();

// POST
const response = await fetch("/api/users", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ name: "홍길동", email: "hong@test.com" }),
});

// ═══ 에러 처리 (중요!) ═══
// fetch는 404, 500에서도 에러를 throw 안 함!

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.message || `HTTP ${response.status}`);
  }

  return response.json();
}

// ═══ 타임아웃 ═══
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 5000);

try {
  const data = await fetch(url, { signal: controller.signal });
} catch (err) {
  if (err.name === "AbortError") console.log("타임아웃!");
} finally {
  clearTimeout(timeout);
}

// ═══ 재시도 ═══
async function fetchWithRetry(url: string, retries = 3): Promise<Response> {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url);
      if (res.ok) return res;
      if (res.status < 500) throw new Error(`HTTP ${res.status}`);
    } catch (err) {
      if (i === retries - 1) throw err;
      await new Promise(r => setTimeout(r, 1000 * (i + 1)));
    }
  }
  throw new Error("최대 재시도 초과");
}

// ═══ 스트리밍 (AI 응답) ═══
const response = await fetch("/api/chat", {
  method: "POST",
  body: JSON.stringify({ messages }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const text = decoder.decode(value);
  // 실시간으로 UI에 추가
  setResponse(prev => prev + text);
}
```'''),

    m("localStorage vs sessionStorage vs Cookie 차이",
'''웹 스토리지 비교입니다.

```javascript
// ═══ 비교 ═══
//                    localStorage    sessionStorage    Cookie
// 용량              5-10MB          5-10MB            4KB
// 만료              영구            탭 닫으면 삭제    설정 가능
// 서버 전송         안 됨           안 됨             매 요청마다 전송
// 접근              클라이언트만    클라이언트만       서버+클라이언트

// ═══ localStorage (영구 저장) ═══
// 용도: 테마 설정, 언어, 최근 검색어, 장바구니 임시 저장
localStorage.setItem("theme", "dark");
localStorage.getItem("theme");  // "dark"
localStorage.removeItem("theme");

// 객체 저장
localStorage.setItem("user", JSON.stringify({ name: "홍길동" }));
const user = JSON.parse(localStorage.getItem("user") || "null");

// ═══ sessionStorage (탭 세션) ═══
// 용도: 폼 임시 저장, 페이지 이동 간 상태, 1회성 데이터
sessionStorage.setItem("formDraft", JSON.stringify(formData));
// 탭 닫으면 자동 삭제 → 보안!

// ═══ Cookie (서버 전송) ═══
// 용도: 인증 토큰, 세션 ID, 서버가 읽어야 하는 것
document.cookie = "token=abc123; path=/; max-age=86400; Secure; SameSite=Strict";

// Next.js 서버에서 읽기
import { cookies } from "next/headers";
const token = cookies().get("token")?.value;

// ═══ 선택 가이드 ═══
// 인증 토큰 → Cookie (HttpOnly, Secure)
// 테마/언어 → localStorage
// 폼 임시저장 → sessionStorage
// 장바구니 → localStorage (비로그인) or 서버 (로그인)
// 절대 비밀정보 → 어디에도 저장하지 마세요!
```'''),

    m("CSS Flexbox 총정리 해줘",
'''Flexbox 핵심 총정리입니다.

```css
/* ═══ 컨테이너 (부모) ═══ */
.container {
  display: flex;
  flex-direction: row;         /* row | column | row-reverse | column-reverse */
  justify-content: center;     /* 메인축 정렬: flex-start | center | flex-end | space-between | space-around | space-evenly */
  align-items: center;         /* 교차축 정렬: flex-start | center | flex-end | stretch | baseline */
  flex-wrap: wrap;             /* nowrap(기본) | wrap | wrap-reverse */
  gap: 1rem;                   /* 아이템 간격 */
}

/* ═══ 아이템 (자식) ═══ */
.item {
  flex: 1;                     /* flex-grow: 1, flex-shrink: 1, flex-basis: 0% */
  flex-grow: 1;                /* 남은 공간 차지 비율 */
  flex-shrink: 0;              /* 줄어들지 않음 */
  flex-basis: 200px;           /* 기본 크기 */
  align-self: flex-end;        /* 개별 교차축 정렬 */
  order: -1;                   /* 순서 변경 */
}

/* ═══ 실무 패턴 ═══ */

/* 1. 완벽한 센터링 */
.center {
  display: flex;
  justify-content: center;
  align-items: center;
}

/* 2. 네비게이션 바 */
.navbar {
  display: flex;
  justify-content: space-between;  /* 로고 왼쪽, 메뉴 오른쪽 */
  align-items: center;
}

/* 3. 카드 레이아웃 (같은 높이) */
.cards {
  display: flex;
  gap: 1rem;
}
.card {
  flex: 1;                     /* 균등 분배 */
  display: flex;
  flex-direction: column;
}
.card-body { flex: 1; }        /* 카드 내용이 남은 공간 차지 → 버튼 하단 고정 */

/* 4. 사이드바 + 콘텐츠 */
.layout {
  display: flex;
}
.sidebar { width: 250px; flex-shrink: 0; }  /* 고정 너비 */
.main { flex: 1; }                          /* 나머지 */

/* 5. 가운데 + 오른쪽 정렬 (margin-left: auto 트릭) */
.toolbar {
  display: flex;
  align-items: center;
  gap: 1rem;
}
.toolbar .right { margin-left: auto; }  /* 오른쪽으로 밀기 */

/* 6. 텍스트 말줄임 (flex 안에서) */
.truncate {
  min-width: 0;               /* flex 아이템 오버플로 허용 */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

핵심: `justify-content` = **메인축**, `align-items` = **교차축**!'''),

    # ═══ React 실무 (20건) ═══
    m("React에서 폼 다루는 방법 알려줘 간단히",
'''React 폼 처리 3가지 방법입니다.

```tsx
// 1. 기본 (useState)
function SimpleForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    console.log({ name, email });
  };

  return (
    <form onSubmit={handleSubmit}>
      <input value={name} onChange={e => setName(e.target.value)} />
      <input value={email} onChange={e => setEmail(e.target.value)} />
      <button type="submit">제출</button>
    </form>
  );
}

// 2. FormData (간단한 서버 액션)
function FormDataForm() {
  const handleSubmit = (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData);
    console.log(data);  // { name: "...", email: "..." }
  };

  return (
    <form onSubmit={handleSubmit}>
      <input name="name" />
      <input name="email" />
      <button type="submit">제출</button>
    </form>
  );
}

// 3. React Hook Form + Zod (추천)
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

const schema = z.object({
  name: z.string().min(2, "2자 이상"),
  email: z.string().email("올바른 이메일"),
});

function RHFForm() {
  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(schema),
  });

  return (
    <form onSubmit={handleSubmit(data => console.log(data))}>
      <input {...register("name")} />
      {errors.name && <p>{errors.name.message}</p>}
      <input {...register("email")} />
      {errors.email && <p>{errors.email.message}</p>}
      <button type="submit">제출</button>
    </form>
  );
}
```

선택: 간단한 폼 → useState, 복잡한 폼 → **React Hook Form + Zod**!'''),

    m("useRef 어떻게 쓰는거야?",
'''useRef의 2가지 용도입니다.

```tsx
import { useRef, useEffect } from "react";

// ═══ 1. DOM 접근 ═══
function TextInput() {
  const inputRef = useRef<HTMLInputElement>(null);

  const focusInput = () => {
    inputRef.current?.focus();  // DOM 요소 직접 접근
  };

  return (
    <div>
      <input ref={inputRef} />
      <button onClick={focusInput}>포커스</button>
    </div>
  );
}

// ═══ 2. 값 보관 (리렌더 안 됨) ═══
function Timer() {
  const countRef = useRef(0);           // 리렌더 없이 값 유지
  const intervalRef = useRef<number>(); // 타이머 ID 보관

  const start = () => {
    intervalRef.current = setInterval(() => {
      countRef.current += 1;
      console.log(countRef.current);  // 리렌더 없이 증가
    }, 1000);
  };

  const stop = () => {
    clearInterval(intervalRef.current);
  };

  return (
    <div>
      <button onClick={start}>시작</button>
      <button onClick={stop}>중지</button>
    </div>
  );
}

// ═══ 3. 이전 값 기억 ═══
function usePrevious<T>(value: T): T | undefined {
  const ref = useRef<T>();
  useEffect(() => { ref.current = value; });
  return ref.current;
}

// 사용
const prevCount = usePrevious(count);
// count가 5이고 이전에 4였으면 → prevCount = 4
```

핵심: `useState` = 값 변경 시 리렌더, `useRef` = 값 변경해도 리렌더 안 됨!'''),

    m("useMemo vs useCallback 차이",
'''둘 다 메모이제이션이지만 용도가 다릅니다.

```tsx
// ═══ useMemo: 값을 메모이제이션 ═══
// "비싼 계산 결과를 캐시"

const sortedUsers = useMemo(() => {
  console.log("정렬 중...");  // users 변경 시에만 실행
  return [...users].sort((a, b) => a.name.localeCompare(b.name));
}, [users]);  // users가 바뀔 때만 재계산


// ═══ useCallback: 함수를 메모이제이션 ═══
// "함수 참조를 유지" (자식에게 전달할 때)

const handleClick = useCallback((id: string) => {
  setSelectedId(id);
}, []);  // 빈 배열 → 항상 같은 함수 참조

// 자식에게 전달 (React.memo와 조합)
<MemoizedChild onClick={handleClick} />


// ═══ 언제 쓰나? ═══

// useMemo 쓸 때:
// 1. 비싼 계산 (정렬, 필터, 변환)
const filtered = useMemo(() => items.filter(complexFilter), [items]);

// 2. 참조 안정성 (객체/배열을 props로 전달)
const style = useMemo(() => ({ color: "red" }), []);


// useCallback 쓸 때:
// 1. React.memo 자식에게 함수 전달
// 2. useEffect 의존성에 함수가 필요할 때
const fetchData = useCallback(async () => {
  const data = await api.get(url);
  setData(data);
}, [url]);

useEffect(() => { fetchData(); }, [fetchData]);


// ═══ 쓰지 말아야 할 때 ═══
// ❌ 단순 계산
const double = useMemo(() => count * 2, [count]);  // 불필요!
// ✅ 그냥
const double = count * 2;

// ❌ 자식에 안 넘기는 함수
const handleClick = useCallback(() => { ... }, []);  // 불필요!
// ✅ 그냥
const handleClick = () => { ... };
```

규칙: **성능 문제가 실제로 있을 때만** 사용. 추측으로 쓰지 마세요!'''),

    # ═══ Python 실무 (15건) ═══
    m("파이썬 리스트 컴프리헨션 고급 패턴",
'''리스트 컴프리헨션 고급 활용입니다.

```python
# 기본
squares = [x**2 for x in range(10)]

# 조건부
evens = [x for x in range(20) if x % 2 == 0]

# 중첩 (2D → 1D)
matrix = [[1,2,3], [4,5,6], [7,8,9]]
flat = [x for row in matrix for x in row]
# [1, 2, 3, 4, 5, 6, 7, 8, 9]

# 조건부 값 변환
labels = ["양수" if x > 0 else "음수" if x < 0 else "영" for x in [-1, 0, 1, 2]]
# ["음수", "영", "양수", "양수"]

# 딕셔너리 컴프리헨션
word_lengths = {word: len(word) for word in ["파이썬", "자바", "고"]}
# {"파이썬": 3, "자바": 2, "고": 1}

# 집합 컴프리헨션
unique_lengths = {len(word) for word in words}

# 중첩 조건
result = [
    (x, y)
    for x in range(5)
    for y in range(5)
    if x != y
    if x + y < 5
]

# 실무: API 응답 파싱
users_by_id = {u["id"]: u["name"] for u in api_response["users"]}
active_emails = [u["email"] for u in users if u["status"] == "active"]
error_messages = [e["message"] for e in errors if e["level"] == "critical"]

# 제너레이터 표현식 (메모리 절약)
total = sum(order.total for order in orders)  # 리스트 안 만듦!
large_files = (f for f in files if f.size > 1_000_000)  # 지연 평가
```'''),

    m("파이썬 with문 사용법 알려줘",
'''`with`문(컨텍스트 매니저) 사용법입니다.

```python
# ═══ 파일 ═══
# ❌ 수동 관리 (닫기 잊을 수 있음)
f = open("file.txt")
data = f.read()
f.close()

# ✅ with (자동 닫기)
with open("file.txt", "r", encoding="utf-8") as f:
    data = f.read()
# 여기서 자동으로 f.close()

# 여러 파일 동시
with open("input.txt") as fin, open("output.txt", "w") as fout:
    fout.write(fin.read().upper())

# ═══ DB 연결 ═══
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
# 자동 commit/close

# ═══ 락 (Lock) ═══
import threading
lock = threading.Lock()

with lock:  # 자동 acquire/release
    shared_data.append(item)

# ═══ 임시 파일/디렉토리 ═══
import tempfile

with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
    tmp.write(b"data")
    process(tmp.name)
# 자동 삭제

# ═══ 직접 만들기 ═══
from contextlib import contextmanager

@contextmanager
def timer(label=""):
    import time
    start = time.time()
    yield  # with 블록 실행
    print(f"[{label}] {time.time()-start:.2f}초")

with timer("데이터 처리"):
    process_data()
# [데이터 처리] 1.23초

# ═══ suppress (예외 무시) ═══
from contextlib import suppress

with suppress(FileNotFoundError):
    os.remove("temp.txt")  # 없어도 에러 안 남
```

핵심: `with`는 **리소스 정리를 보장**합니다. 파일, DB, 락 등에 필수!'''),

    m("파이썬 f-string 포맷팅 고급 알려줘",
'''f-string 고급 기능입니다.

```python
name = "홍길동"
price = 1234567.89
ratio = 0.856

# 기본
f"안녕, {name}!"

# 숫자 포맷팅
f"{price:,.0f}원"          # "1,234,568원" (천 단위 쉼표)
f"{price:>15,.2f}"        # "   1,234,567.89" (우측 정렬, 15자리)
f"{ratio:.1%}"            # "85.6%" (퍼센트)
f"{42:08d}"               # "00000042" (0 채우기)
f"{255:#x}"               # "0xff" (16진수)
f"{7:#b}"                 # "0b111" (2진수)

# 날짜
from datetime import datetime
now = datetime.now()
f"{now:%Y-%m-%d %H:%M}"  # "2025-04-21 10:30"
f"{now:%A}"               # "Monday"

# 표현식
f"{'짝수' if x%2==0 else '홀수'}"
f"{len(items)} 개"
f"{user.name!r}"          # repr() 호출 → "'홍길동'"
f"{text!s}"               # str() 호출

# 디버깅 (Python 3.8+)
x = 42
f"{x = }"                 # "x = 42" (변수명 + 값)
f"{x**2 = }"              # "x**2 = 1764"

# 중괄호 이스케이프
f"JSON: {{'key': '{name}'}}"  # "JSON: {'key': '홍길동'}"

# 정렬
f"{'왼쪽':<10}"           # "왼쪽        "
f"{'가운데':^10}"         # "   가운데   "
f"{'오른쪽':>10}"         # "      오른쪽"
f"{'채우기':*^10}"        # "***채우기***"

# 실무
items = ["사과", "바나나", "딸기"]
print(f"총 {len(items)}개: {', '.join(items)}")
# "총 3개: 사과, 바나나, 딸기"

for i, item in enumerate(items, 1):
    print(f"  {i:2d}. {item}")
#   1. 사과
#   2. 바나나
#   3. 딸기
```'''),

    # ═══ 기타 실무 (25건) ═══
    m("HTTP 상태 코드 정리해줘",
'''자주 쓰는 HTTP 상태 코드입니다.

```
═══ 2xx 성공 ═══
200 OK              - 요청 성공 (GET 조회, PUT 수정)
201 Created         - 생성 성공 (POST)
204 No Content      - 성공했지만 응답 바디 없음 (DELETE)

═══ 3xx 리다이렉트 ═══
301 Moved Permanently  - 영구 이동 (SEO에 영향)
302 Found              - 임시 이동
304 Not Modified       - 캐시 사용 (변경 없음)

═══ 4xx 클라이언트 에러 ═══
400 Bad Request     - 잘못된 요청 (문법 오류)
401 Unauthorized    - 인증 필요 (로그인 안 함)
403 Forbidden       - 권한 없음 (로그인 했지만 접근 불가)
404 Not Found       - 리소스 없음
405 Method Not Allowed - 허용되지 않은 HTTP 메서드
409 Conflict        - 충돌 (이미 존재, 동시 수정)
422 Unprocessable   - 검증 실패 (입력값 오류)
429 Too Many Requests - 요청 한도 초과 (Rate Limit)

═══ 5xx 서버 에러 ═══
500 Internal Server Error - 서버 내부 오류
502 Bad Gateway          - 게이트웨이 오류 (프록시 뒤 서버 문제)
503 Service Unavailable  - 서비스 불가 (점검/과부하)
504 Gateway Timeout      - 게이트웨이 타임아웃
```

실무 매핑:
| API 동작 | 성공 | 실패 |
|----------|------|------|
| GET /users | 200 | 404 |
| POST /users | 201 | 400, 409, 422 |
| PUT /users/:id | 200 | 400, 404, 422 |
| DELETE /users/:id | 204 | 404 |
| 로그인 | 200 | 401 |
| 권한 없는 접근 | - | 403 |'''),

    m("정규표현식 자주 쓰는 패턴 알려줘",
'''실무에서 자주 쓰는 정규표현식 모음입니다.

```javascript
// ═══ 검증 ═══
const patterns = {
  // 이메일
  email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,

  // 비밀번호 (8자+, 대문자, 소문자, 숫자, 특수문자)
  password: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*]).{8,}$/,

  // 한국 전화번호
  phone: /^01[0-9]-?\d{3,4}-?\d{4}$/,

  // URL
  url: /^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_+.~#?&//=]*)$/,

  // 한글만
  korean: /^[가-힣]+$/,

  // 사업자등록번호 (000-00-00000)
  bizNo: /^\d{3}-\d{2}-\d{5}$/,

  // IP 주소
  ip: /^(\d{1,3}\.){3}\d{1,3}$/,
};

// ═══ 추출 ═══
// 해시태그
const tags = text.match(/#[가-힣a-zA-Z0-9_]+/g);
// ["#개발", "#파이썬"]

// URL 추출
const urls = text.match(/https?:\/\/[^\s]+/g);

// 숫자만
const numbers = "가격: 12,500원".replace(/[^\d]/g, "");
// "12500"

// ═══ 변환 ═══
// camelCase → kebab-case
"backgroundColor".replace(/[A-Z]/g, m => `-${m.toLowerCase()}`);
// "background-color"

// 전화번호 포맷팅
"01012345678".replace(/(\d{3})(\d{4})(\d{4})/, "$1-$2-$3");
// "010-1234-5678"

// HTML 태그 제거
html.replace(/<[^>]*>/g, "");

// 연속 공백 → 하나로
text.replace(/\s+/g, " ").trim();
```'''),

    m("package.json scripts 작성법 알려줘",
'''package.json scripts 실무 패턴입니다.

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint . --ext .ts,.tsx",
    "lint:fix": "eslint . --ext .ts,.tsx --fix",
    "type-check": "tsc --noEmit",
    "format": "prettier --write .",
    "test": "vitest",
    "test:watch": "vitest --watch",
    "test:coverage": "vitest --coverage",
    "db:push": "prisma db push",
    "db:migrate": "prisma migrate dev",
    "db:seed": "prisma db seed",
    "db:studio": "prisma studio",
    "clean": "rm -rf .next node_modules/.cache",
    "check": "npm run lint && npm run type-check && npm run test",
    "precommit": "lint-staged"
  }
}
```

자주 쓰는 패턴:
- `dev`: 개발 서버
- `build` + `start`: 프로덕션
- `lint` + `lint:fix`: 코드 품질
- `type-check`: 타입 검사 (빌드 없이)
- `check`: CI에서 전체 검증
- `db:*`: DB 관련 명령어 그룹핑'''),

    m(".gitignore 뭐 넣어야해?",
'''프로젝트별 .gitignore 핵심입니다.

```gitignore
# ═══ Node.js / Next.js ═══
node_modules/
.next/
out/
.pnpm-store/

# ═══ Python ═══
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/

# ═══ 환경변수 (절대 커밋 금지!) ═══
.env
.env.local
.env.production
.env.*.local

# ═══ IDE ═══
.vscode/
.idea/
*.swp
*.swo

# ═══ OS ═══
.DS_Store
Thumbs.db

# ═══ 빌드 산출물 ═══
dist/
build/
*.tsbuildinfo

# ═══ 로그 ═══
*.log
logs/

# ═══ 테스트 ═══
coverage/
.nyc_output/

# ═══ Docker ═══
docker-compose.override.yml

# ═══ AI/ML ═══
*.pt
*.pth
*.ckpt
*.safetensors
models/
checkpoints/

# ═══ 데이터베이스 ═══
*.db
*.sqlite3
```

핵심 규칙:
- `.env` → 절대 커밋 안 함
- `node_modules/` → 무조건 무시
- `.env.example` → 커밋 (템플릿 공유용)
- 모델 파일 → 용량 커서 무시 (별도 다운로드)'''),

    m("npm vs yarn vs pnpm 뭐 써야해?",
'''2025년 기준 패키지 매니저 비교입니다.

```
             npm          yarn         pnpm
속도         보통          빠름         가장 빠름
디스크       중복 설치     중복 설치    하드링크 (절약!)
Monorepo    workspaces   workspaces   workspaces (최고)
Lock 파일    package-lock yarn.lock    pnpm-lock
점유율       가장 높음     보통         빠르게 성장
```

**2025 추천: pnpm**

이유:
1. **디스크 절약**: 같은 패키지 중복 설치 안 함 (심볼릭 링크)
2. **속도**: npm 대비 2-3배 빠름
3. **엄격**: 유령 의존성 방지 (선언 안 한 패키지 접근 차단)
4. **모노레포**: workspace 지원 최고

```bash
# pnpm 설치
npm install -g pnpm

# 기본 명령어 (npm과 거의 동일)
pnpm install              # 의존성 설치
pnpm add react            # 패키지 추가
pnpm add -D vitest        # devDependencies
pnpm remove lodash        # 제거
pnpm run dev              # 스크립트 실행
pnpm dlx create-next-app  # npx 대체
```

선택 기준:
- 새 프로젝트 → **pnpm**
- 팀에서 이미 yarn 쓰는 중 → yarn 유지
- 호환성 중시 → npm (기본 내장)'''),

    m("환경변수 NODE_ENV 뭐야?",
'''`NODE_ENV`는 실행 환경을 구분하는 환경변수입니다.

```javascript
// 값: "development" | "production" | "test"

// ═══ 동작 차이 ═══
if (process.env.NODE_ENV === "development") {
  // 개발 모드에서만
  console.log("디버그:", data);
  // 소스맵 활성화
  // 핫 리로드 활성화
  // 에러 상세 표시
}

if (process.env.NODE_ENV === "production") {
  // 프로덕션에서만
  // 코드 최소화 (minify)
  // 소스맵 비활성화
  // 에러 간략 표시
  // 로그 레벨 최소화
}

// ═══ 프레임워크별 동작 ═══

// Next.js
// next dev → NODE_ENV=development
// next build && next start → NODE_ENV=production

// React (CRA/Vite)
// npm start → development
// npm run build → production

// ═══ 조건부 코드 ═══
const config = {
  apiUrl: process.env.NODE_ENV === "production"
    ? "https://api.hwarang.ai"
    : "http://localhost:8000",

  logLevel: process.env.NODE_ENV === "development" ? "debug" : "error",
};

// ═══ 번들 최적화 ═══
// production 빌드 시 아래 코드가 제거됨 (tree-shaking)
if (process.env.NODE_ENV !== "production") {
  // 개발용 도구 (프로덕션 번들에 안 들어감!)
  require("why-did-you-render")(React);
}
```

핵심: 직접 설정하지 마세요. 빌드 도구가 자동 설정합니다!'''),

    # ═══ 인프라/DevOps (10건) ═══
    m("SSH 키 생성하고 서버 접속하는 법",
'''SSH 키 생성부터 접속까지입니다.

```bash
# 1. SSH 키 생성
ssh-keygen -t ed25519 -C "your@email.com"
# Enter file: ~/.ssh/id_ed25519 (기본값)
# Enter passphrase: (빈 값 또는 비밀번호)

# 2. 공개키 서버에 복사
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@서버IP
# 또는 수동으로
cat ~/.ssh/id_ed25519.pub | ssh user@서버IP "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

# 3. 접속
ssh user@서버IP

# 4. 편의 설정 (~/.ssh/config)
Host hwarang
  HostName 192.168.1.42
  User perseismore
  IdentityFile ~/.ssh/id_ed25519

# 이제 이렇게만:
ssh hwarang

# 5. 보안 설정 (서버에서)
sudo nano /etc/ssh/sshd_config
# PasswordAuthentication no  ← 비밀번호 로그인 비활성화
# PermitRootLogin no         ← root 로그인 금지
sudo systemctl restart sshd
```'''),

    m("리눅스 명령어 자주 쓰는 거 알려줘",
'''실무에서 매일 쓰는 리눅스 명령어입니다.

```bash
# ═══ 파일/디렉토리 ═══
ls -la                    # 상세 목록
cd /path/to/dir           # 이동
pwd                       # 현재 위치
mkdir -p dir/sub          # 중첩 디렉토리 생성
cp -r src/ dest/          # 디렉토리 복사
mv old new                # 이름 변경/이동
rm -rf dir/               # 강제 삭제 (주의!)
find . -name "*.log"      # 파일 검색
du -sh */                 # 디렉토리 크기

# ═══ 텍스트 ═══
cat file.txt              # 파일 내용
head -20 file.txt         # 처음 20줄
tail -f log.txt           # 실시간 로그 (Ctrl+C 종료)
grep -r "에러" .          # 재귀 검색
grep -n "패턴" file       # 줄번호 표시
wc -l file.txt            # 줄 수

# ═══ 프로세스 ═══
ps aux | grep node        # 프로세스 찾기
kill PID                  # 종료
kill -9 PID               # 강제 종료
htop                      # 시스템 모니터
lsof -i :3000             # 포트 사용 프로세스

# ═══ 네트워크 ═══
curl -X POST http://... -d '{}'  # API 호출
netstat -tlnp             # 열린 포트
ping google.com           # 연결 확인
ss -tlnp                  # 소켓 상태

# ═══ 시스템 ═══
df -h                     # 디스크 사용량
free -h                   # 메모리 사용량
uptime                    # 가동 시간
systemctl status nginx    # 서비스 상태
journalctl -u nginx -f    # 서비스 로그

# ═══ 권한 ═══
chmod 755 script.sh       # 실행 권한
chown user:group file     # 소유자 변경
sudo !!                   # 이전 명령 sudo로 재실행
```'''),

    m("cron 스케줄 설정법 알려줘",
'''cron으로 정기 작업 예약하는 방법입니다.

```bash
# crontab 편집
crontab -e

# ═══ 형식 ═══
# 분  시  일  월  요일  명령어
# 0-59 0-23 1-31 1-12 0-7(0,7=일)

# ═══ 예시 ═══
# 매일 새벽 3시
0 3 * * * /opt/scripts/backup.sh

# 매시간
0 * * * * /opt/scripts/healthcheck.sh

# 5분마다
*/5 * * * * /opt/scripts/monitor.sh

# 평일 오전 9시
0 9 * * 1-5 /opt/scripts/report.sh

# 매월 1일 자정
0 0 1 * * /opt/scripts/monthly.sh

# 매주 일요일 새벽 2시
0 2 * * 0 /opt/scripts/weekly_backup.sh

# ═══ 실무 팁 ═══
# 로그 기록
0 3 * * * /opt/scripts/backup.sh >> /var/log/backup.log 2>&1

# 환경변수 로드
0 * * * * source /etc/environment && /opt/scripts/task.sh

# 목록 확인
crontab -l

# 시스템 cron (root)
sudo cat /etc/crontab
```

| 표현식 | 의미 |
|--------|------|
| `*/5 * * * *` | 5분마다 |
| `0 */2 * * *` | 2시간마다 |
| `0 9-18 * * 1-5` | 평일 9-18시 매시 |
| `0 0 * * 0` | 매주 일요일 자정 |'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/bulk_150.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"벌크 데이터: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
