"""화랑 LoRA v9 학습 데이터 — 긴 응답 한국어 only 강제 4000건.

v8 (3500건, 정체성 100%) 의 약점:
  짧은 응답 (평균 100~200 토큰) 위주로 학습돼,
  긴 reasoning/코드설명/프로젝트 평가 같은 긴 응답에서
  base Qwen 의 한국어→중국어 code-switching 누출이 잔존.

  실제 누출 예시:
    "이 프로젝트는: 초기 단계라 아직은 평균 (3~4점) 수준.
     但从不使用外部工具或API。如果用户要求，可以说..."

v9 목표:
  긴 응답 (400~1500 자) 도 한국어 only 로 강제.
  코드 블록 내 영문 식별자/주석은 OK 지만 설명 본문은 한국어.
  표(markdown table) 셀 내용도 한국어.

카테고리 (총 4000):
  L1 코드 리뷰 긴 분석 (1000)   응답 600자 이상
  L2 프로젝트 평가 (800)        응답 400자 이상
  L3 기술 비교/장단점 (800)     응답 500자 이상
  L4 디자인 시스템 분석 (600)   응답 600자 이상
  L5 트러블슈팅 다단계 (800)    응답 600자 이상

검증 (빌더 내장):
  1. 한자(CJK)·키릴·히라가나/가타카나·베트남어 0건
  2. 코드 블록 ```...``` 밖 5단어 이상 연속 영어 0건
  3. 환각 용어 0건
  4. 카테고리별 최소 길이 미달 폐기
  5. 재생성 max 3회, 실패시 prompt 스킵
  6. --validate: 생성된 jsonl 전체 재검증
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import sys
from typing import Callable

random.seed(9001)


# ============================================================
# 검증 정규식 헬퍼 (v8 패턴 재사용 + 길이 추가)
# ============================================================

_CJK = re.compile(r"[一-鿿]")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_HIRAKATA = re.compile(r"[぀-ヿ]")
_VIET_LATIN = re.compile(
    r"[Ạ-ỹ]|[ạáảãàặắằẳẵệếềểễỉịòóỏõộốồổỗợớờởỡụúủũựứừửữỳýỷỹ]"
)
_HALLUC = re.compile(
    r"\b(Multiplex|MTP|Quoll|Annexion|Observations|SemaConnect|Aquila|Mega Telemetry)\b"
)
_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]+`")
# 코드 블록 밖에서 5단어 이상 연속된 영어 시퀀스 탐지.
# 한국어/숫자/구두점이 끼면 영어 시퀀스가 끊긴 것으로 본다.
_LONG_EN_RUN = re.compile(r"(?:[A-Za-z][A-Za-z\-']*\s+){4,}[A-Za-z][A-Za-z\-']*")

MIN_LEN = {"L1": 600, "L2": 400, "L3": 500, "L4": 600, "L5": 600}


def is_clean_long_korean(text: str, category: str) -> tuple[bool, str]:
    """긴 응답이 한국어 only 정책 + 최소 길이를 만족하는지 검사.

    Returns:
        (ok, reason)
    """
    code_stripped = _CODE_BLOCK.sub("", text)
    code_stripped = _INLINE_CODE.sub("", code_stripped)
    if _CJK.search(code_stripped):
        return False, "cjk"
    if _CYRILLIC.search(code_stripped):
        return False, "cyrillic"
    if _HIRAKATA.search(code_stripped):
        return False, "hirakata"
    if _VIET_LATIN.search(code_stripped):
        return False, "viet"
    if _HALLUC.search(text):
        return False, "halluc"
    if _LONG_EN_RUN.search(code_stripped):
        return False, "long_en_run"
    min_len = MIN_LEN.get(category[:2], 400)
    if len(text) < min_len:
        return False, "too_short"
    return True, "ok"


# ============================================================
# 공용 부분 풀 (서론 / 본론 연결 / 결론 — 카테고리별)
# ============================================================

L_INTRO = {
    "L1": [
        "코드를 천천히 훑어 보면서 구조와 의도부터 정리해 봤습니다.",
        "기능 동작은 무리 없어 보이지만, 유지보수 관점에서 몇 가지 짚어 두면 좋을 부분이 있어요.",
        "전체적인 구조는 이해하기 쉽게 짜여 있고, 큰 결함은 보이지 않았습니다. 다만 디테일에서 다듬을 여지가 보여요.",
        "리뷰 포인트를 구조, 가독성, 안정성, 성능 네 갈래로 나눠 정리해 봤습니다.",
        "처음 보는 사람이 흐름을 따라가기 좋은 코드입니다. 다만 변경이 잦은 부분에서 약점이 드러날 수 있어 보여요.",
    ],
    "L2": [
        "지금 보여 주신 정보 안에서 가능한 평가를 정리해 보겠습니다.",
        "초기 단계 프로젝트라는 점을 고려하면 전반적으로 합리적인 출발선에 있다고 봅니다.",
        "현재 구성과 목표를 함께 놓고 보면 강점과 약점이 비교적 또렷하게 나뉩니다.",
        "방향성 자체는 시장에 충분히 통할 만하다고 봅니다. 다만 실행 단계에서 다잡아야 할 포인트가 몇 개 보입니다.",
        "결론부터 말씀드리면 핵심 가설을 빨리 검증할 수 있느냐가 가장 큰 변수입니다.",
    ],
    "L3": [
        "두 기술은 비슷한 문제를 다르게 푸는 도구라 어느 한쪽이 절대적으로 우위라고 말하긴 어렵습니다.",
        "선택 기준을 팀 역량, 운영 부담, 생태계, 장기 유지 비용으로 나눠 비교해 보겠습니다.",
        "둘 다 성숙한 선택지라 잘못된 선택이라기보다 상황에 맞지 않는 선택이 더 흔합니다.",
        "단순히 성능 수치가 아니라 운영과 학습 곡선, 팀 문화까지 함께 봐야 결정이 흔들리지 않습니다.",
        "장단점을 표로 정리한 뒤, 어떤 상황에서 어느 쪽이 더 어울리는지 사례 중심으로 풀어 보겠습니다.",
    ],
    "L4": [
        "디자인 시스템 관점에서는 토큰, 컴포넌트, 패턴 세 층을 따로 떼어 보는 것이 시작입니다.",
        "보내 주신 화면을 토큰과 패턴 단위로 분해해 보고, 일관성과 접근성을 함께 점검해 봤습니다.",
        "전체 색상 체계와 타이포 스케일을 먼저 살펴보고, 컴포넌트 단위 일관성을 짚어 보겠습니다.",
        "기본 구성은 깔끔하지만, 다크 모드와 접근성 측면에서 더 챙겨야 할 항목이 보입니다.",
        "시각적으로는 정돈돼 있는 편입니다. 다만 토큰화 정도와 재사용성에는 개선 여지가 있어요.",
    ],
    "L5": [
        "에러 메시지와 스택 트레이스를 함께 보면 원인이 한 가지가 아니라 여러 층에 걸쳐 있을 가능성이 큽니다.",
        "현상만 보면 단순한 버그처럼 보이지만, 재현 조건을 좁혀 보면 다른 원인이 드러날 수 있어요.",
        "이런 패턴의 에러는 환경 차이, 의존성 충돌, 비동기 흐름 셋 중 하나에서 자주 발생합니다.",
        "원인을 좁히기 위해 가설을 세 가지 정도 세우고 하나씩 검증하는 방향으로 풀어 보겠습니다.",
        "스택 트레이스의 가장 깊은 호출부터 거꾸로 따라가 보면 어디서 가정이 깨졌는지 보입니다.",
    ],
}

L_OUTRO = {
    "L1": [
        "전반적으로 큰 그림은 좋고, 위에서 짚은 부분만 보완해도 한층 단단해질 수 있습니다.",
        "리팩터링은 한 번에 다 손대기보다 한 가지씩 끝맺고 다음으로 넘어가는 흐름을 권장드려요.",
        "단기 작업 목록을 짧게 뽑고, 우선순위 높은 항목부터 PR 단위로 나눠 보세요.",
        "테스트 보강과 함께 진행하면 회귀 위험을 크게 줄일 수 있습니다.",
        "위 제안은 모두 권고이며, 팀 컨벤션과 어긋나면 팀 규칙을 우선해 주세요.",
    ],
    "L2": [
        "지금은 너무 많은 가설을 동시에 검증하지 말고, 가장 큰 리스크 한두 개에 집중하시길 추천합니다.",
        "방향성은 합리적이니, 실행 속도와 측정 가능한 지표 설계에 시간을 더 쓰시면 좋겠습니다.",
        "초기 단계의 평가는 늘 변동성이 큽니다. 다음 한 분기 단위로 다시 점검해 보세요.",
        "정성적 피드백과 정량 지표를 함께 추적하면 의사 결정이 한층 단단해집니다.",
        "결국 사용자 문제 정의가 가장 큰 변수이니, 거기에 가장 많은 시간을 쓰시는 것을 권합니다.",
    ],
    "L3": [
        "정답이 있는 비교는 아니므로, 팀 상황에 맞춰 한 번 더 점검해 보시길 권합니다.",
        "선택 후에도 1~2 분기마다 가정이 여전히 유효한지 검토하면 큰 비용 없이 방향을 다잡을 수 있어요.",
        "기술 선택은 사람이 50, 도구가 50 입니다. 팀이 가장 잘 다룰 수 있는 도구가 결국 빠릅니다.",
        "도입 후 6 개월 시점의 운영 비용을 먼저 추정해 보면 의사 결정이 한층 또렷해집니다.",
        "결론은 둘 중 무엇을 고르냐보다 결정 이유를 문서로 남기느냐가 더 중요합니다.",
    ],
    "L4": [
        "토큰 단위 정리만 마쳐도 디자인 시스템의 절반은 완성된 셈입니다.",
        "접근성 항목은 한 번 잡아 두면 이후 컴포넌트 추가가 훨씬 가벼워집니다.",
        "디자이너와 개발자가 같은 용어로 토큰을 부를 수 있도록 명명 규칙부터 합의해 보세요.",
        "스타일가이드 문서 한 페이지만 잘 정리해도 신규 입사자의 적응 속도가 크게 빨라집니다.",
        "장기적으로는 컴포넌트보다 패턴 라이브러리에 더 투자할 가치가 있다고 봅니다.",
    ],
    "L5": [
        "위 절차대로 좁혀도 재현이 안 된다면 환경 변수와 의존성 락 파일을 한 번 더 점검해 보세요.",
        "원인을 찾은 뒤에는 같은 류의 회귀를 막을 수 있는 짧은 테스트 한 개라도 꼭 남기시길 권합니다.",
        "버그 자체보다 재현 조건을 문서로 남기는 게 다음 회귀 비용을 크게 줄여 줍니다.",
        "위 점검 항목을 체크리스트로 만들어 두면 비슷한 사고에서 시간을 크게 절약할 수 있습니다.",
        "패치 후에는 같은 경로의 로그를 일정 기간 유지해 회귀 여부를 모니터링해 주세요.",
    ],
}


# ============================================================
# L1 코드 리뷰 (1000) — 50+ 종 코드 풀
# ============================================================

L1_CODES = [
    ("Python", "FastAPI 라우터", """```python
@router.post("/users")
async def create_user(payload: dict, db = Depends(get_db)):
    user = User(name=payload["name"], email=payload["email"])
    db.add(user)
    db.commit()
    return {"id": user.id}
```"""),
    ("Python", "동기 파일 처리 루프", """```python
def process_files(paths):
    results = []
    for p in paths:
        f = open(p, 'r')
        data = f.read()
        results.append(parse(data))
    return results
```"""),
    ("Python", "재귀 피보나치", """```python
def fib(n):
    if n < 2:
        return n
    return fib(n-1) + fib(n-2)
```"""),
    ("Python", "Pandas 그룹 집계", """```python
import pandas as pd
df = pd.read_csv("sales.csv")
result = df.groupby("region").agg({"amount": "sum"}).reset_index()
result.to_csv("out.csv", index=False)
```"""),
    ("Python", "Django 뷰", """```python
def user_detail(request, pk):
    user = User.objects.get(pk=pk)
    posts = Post.objects.filter(author=user)
    return render(request, "user.html", {"user": user, "posts": posts})
```"""),
    ("Python", "비동기 HTTP 호출", """```python
import asyncio, httpx

async def fetch_all(urls):
    async with httpx.AsyncClient() as c:
        return [await c.get(u) for u in urls]
```"""),
    ("Python", "SQL 인젝션 위험 코드", """```python
def search(name):
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM users WHERE name = '{name}'")
    return cur.fetchall()
```"""),
    ("Python", "예외 광범위 캐치", """```python
def safe_run(fn):
    try:
        return fn()
    except:
        return None
```"""),
    ("Python", "캐싱 데코레이터", """```python
_cache = {}
def memo(fn):
    def wrap(*a):
        if a not in _cache:
            _cache[a] = fn(*a)
        return _cache[a]
    return wrap
```"""),
    ("Python", "테스트 픽스처", """```python
@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()
```"""),
    ("TypeScript", "React 폼", """```tsx
function Form() {
  const [name, setName] = useState("");
  return <input value={name} onChange={e => setName(e.target.value)} />;
}
```"""),
    ("TypeScript", "Next.js API 라우트", """```ts
export async function POST(req: Request) {
  const body = await req.json();
  const user = await db.user.create({ data: body });
  return Response.json(user);
}
```"""),
    ("TypeScript", "Zustand 스토어", """```ts
const useStore = create<State>((set) => ({
  count: 0,
  inc: () => set((s) => ({ count: s.count + 1 })),
}));
```"""),
    ("TypeScript", "타입 가드", """```ts
function isUser(x: unknown): x is User {
  return typeof x === "object" && x !== null && "id" in x;
}
```"""),
    ("TypeScript", "비동기 에러 처리", """```ts
async function load() {
  const r = await fetch("/api/data");
  return r.json();
}
```"""),
    ("TypeScript", "React 메모이제이션", """```tsx
const Child = memo(({ items }: { items: Item[] }) => (
  <ul>{items.map(i => <li key={i.id}>{i.name}</li>)}</ul>
));
```"""),
    ("TypeScript", "tRPC 라우터", """```ts
export const userRouter = router({
  get: publicProcedure.input(z.object({ id: z.string() }))
    .query(({ input }) => db.user.findUnique({ where: { id: input.id } })),
});
```"""),
    ("TypeScript", "Express 미들웨어", """```ts
app.use((req, res, next) => {
  console.log(req.method, req.url);
  next();
});
```"""),
    ("TypeScript", "Vue 컴포지션", """```ts
const count = ref(0);
const double = computed(() => count.value * 2);
watch(count, (v) => console.log(v));
```"""),
    ("Go", "HTTP 핸들러", """```go
func handler(w http.ResponseWriter, r *http.Request) {
    body, _ := io.ReadAll(r.Body)
    w.Write(body)
}
```"""),
    ("Go", "고루틴 패턴", """```go
func process(items []int) {
    for _, it := range items {
        go func() {
            doWork(it)
        }()
    }
}
```"""),
    ("Go", "에러 처리", """```go
func read(path string) ([]byte, error) {
    f, err := os.Open(path)
    if err != nil {
        return nil, err
    }
    defer f.Close()
    return io.ReadAll(f)
}
```"""),
    ("Go", "채널 워커 풀", """```go
func worker(jobs <-chan int, results chan<- int) {
    for j := range jobs {
        results <- j * 2
    }
}
```"""),
    ("Go", "컨텍스트 타임아웃", """```go
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
res, err := db.QueryContext(ctx, "SELECT 1")
```"""),
    ("Rust", "Result 처리", """```rust
fn parse(s: &str) -> Result<i32, ParseIntError> {
    s.parse::<i32>()
}
```"""),
    ("Rust", "Option 체이닝", """```rust
fn first_name(user: &User) -> Option<String> {
    user.profile.as_ref().map(|p| p.name.clone())
}
```"""),
    ("Rust", "비동기 함수", """```rust
async fn fetch_user(id: u64) -> Result<User, Error> {
    let resp = reqwest::get(format!("/users/{}", id)).await?;
    resp.json().await.map_err(Into::into)
}
```"""),
    ("Rust", "라이프타임", """```rust
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}
```"""),
    ("Rust", "트레이트 구현", """```rust
impl Display for User {
    fn fmt(&self, f: &mut Formatter) -> fmt::Result {
        write!(f, "{}({})", self.name, self.id)
    }
}
```"""),
    ("SQL", "JOIN 쿼리", """```sql
SELECT u.id, u.name, COUNT(o.id) AS orders
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE u.active = TRUE
GROUP BY u.id, u.name
ORDER BY orders DESC;
```"""),
    ("SQL", "윈도우 함수", """```sql
SELECT
  user_id,
  amount,
  SUM(amount) OVER (PARTITION BY user_id ORDER BY created_at) AS running
FROM orders;
```"""),
    ("SQL", "인덱스 미사용 쿼리", """```sql
SELECT * FROM logs
WHERE DATE(created_at) = '2026-05-01'
  AND status LIKE '%error%';
```"""),
    ("SQL", "트랜잭션", """```sql
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
```"""),
    ("SQL", "CTE 재귀", """```sql
WITH RECURSIVE tree AS (
  SELECT id, parent_id, 1 AS depth FROM nodes WHERE parent_id IS NULL
  UNION ALL
  SELECT n.id, n.parent_id, t.depth + 1
  FROM nodes n JOIN tree t ON n.parent_id = t.id
)
SELECT * FROM tree;
```"""),
    ("React", "useEffect 의존성", """```tsx
useEffect(() => {
  fetch(`/api/user/${id}`).then(r => r.json()).then(setUser);
}, []);
```"""),
    ("React", "커스텀 훅", """```tsx
function useDebounce<T>(value: T, delay: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}
```"""),
    ("React", "조건부 렌더링", """```tsx
function Page({ user }) {
  if (!user) return <Loading />;
  return user.admin ? <Admin /> : <Dashboard />;
}
```"""),
    ("Vue", "컴포저블", """```ts
export function useCounter(initial = 0) {
  const count = ref(initial);
  const inc = () => count.value++;
  return { count, inc };
}
```"""),
    ("Vue", "watch 비동기", """```ts
watch(query, async (q) => {
  results.value = await searchApi(q);
});
```"""),
    ("Flutter", "상태 관리", """```dart
class CounterNotifier extends ChangeNotifier {
  int _count = 0;
  int get count => _count;
  void increment() {
    _count++;
    notifyListeners();
  }
}
```"""),
    ("Flutter", "비동기 위젯", """```dart
FutureBuilder<User>(
  future: fetchUser(),
  builder: (ctx, snap) => snap.hasData
    ? Text(snap.data!.name)
    : CircularProgressIndicator(),
)
```"""),
    ("Python", "Pydantic 모델", """```python
class User(BaseModel):
    id: int
    name: str
    email: EmailStr
    age: int | None = None
```"""),
    ("Python", "asyncio gather", """```python
async def main():
    results = await asyncio.gather(*[fetch(u) for u in urls])
    return results
```"""),
    ("Python", "context manager", """```python
class Timer:
    def __enter__(self):
        self.t = time.time()
        return self
    def __exit__(self, *a):
        print(time.time() - self.t)
```"""),
    ("TypeScript", "타입 좁히기 누락", """```ts
function size(x: string | string[]) {
  return x.length;
}
```"""),
    ("Go", "defer 누수", """```go
for _, f := range files {
    fp, _ := os.Open(f)
    defer fp.Close()
    process(fp)
}
```"""),
    ("Rust", "borrow checker", """```rust
let mut v = vec![1, 2, 3];
let first = &v[0];
v.push(4);
println!("{}", first);
```"""),
    ("SQL", "N+1 위험", """```sql
SELECT id FROM posts WHERE author_id = 1;
-- 각 id 마다 다시:
SELECT * FROM comments WHERE post_id = ?;
```"""),
    ("React", "key prop 누락", """```tsx
{items.map(i => <Item data={i} />)}
```"""),
    ("Python", "datetime 비교", """```python
if log["time"] > datetime.now():
    archive(log)
```"""),
    ("TypeScript", "any 남용", """```ts
function parse(data: any): any {
  return JSON.parse(data);
}
```"""),
    ("Go", "race condition", """```go
var counter int
for i := 0; i < 100; i++ {
    go func() { counter++ }()
}
```"""),
]

L1_REVIEW_POINTS = {
    "FastAPI 라우터": [
        "요청 본문을 dict 로 받기보다 Pydantic 모델로 검증하면 잘못된 페이로드를 라우터 진입 전에 막을 수 있습니다.",
        "트랜잭션 경계가 commit 한 줄에만 묶여 있어, 예외가 나면 세션이 어떻게 정리되는지 추적이 어려워 보입니다.",
        "응답으로 id 만 돌려주기보다 생성된 리소스 전체나 Location 헤더를 함께 주면 클라이언트 사용성이 올라갑니다.",
        "동일 이메일 중복 처리, 유니크 제약 위반 시 어떻게 반응할지 명시적으로 잡아 주는 것이 좋습니다.",
    ],
    "동기 파일 처리 루프": [
        "open 호출이 with 문 없이 진행돼 예외 발생 시 파일 디스크립터가 닫히지 않을 수 있습니다.",
        "파일 수가 많아지면 한 번에 메모리로 올라가는 양이 누적돼 OOM 위험이 있습니다.",
        "I/O 가 동기로 직렬화돼 있어 멀티프로세싱이나 asyncio 로 병렬화하면 처리 시간이 크게 줄어듭니다.",
        "에러가 나는 파일이 있어도 전체가 멈추지 않도록, 개별 파일 단위 예외 처리를 보강할 필요가 있습니다.",
    ],
    "재귀 피보나치": [
        "같은 부분 문제를 반복 호출해 호출 수가 지수적으로 폭증합니다. functools.lru_cache 한 줄이면 기하급수적으로 줄어듭니다.",
        "재귀 깊이가 n 에 비례해 늘어나 큰 n 에서는 RecursionError 위험이 있습니다.",
        "반복문이나 iterative DP 로 바꾸면 O(n) 시간, O(1) 공간으로도 가능합니다.",
        "타입 힌트와 docstring 이 있으면 사용처에서 음수나 매우 큰 값이 들어올 때의 동작을 짐작하기 쉬워집니다.",
    ],
    "Pandas 그룹 집계": [
        "스크립트성 코드라면 무난하지만, 컬럼 누락이나 타입 추론 실패에 대비한 검증이 비어 있습니다.",
        "큰 파일에서는 read_csv 의 dtype 명시와 chunksize 분할 처리가 메모리 효율에 큰 도움이 됩니다.",
        "결과 CSV 가 매번 덮어쓰기되는 구조라, 의도하지 않은 중복 실행에서 이전 결과를 잃을 수 있습니다.",
        "테스트 가능성을 위해 read/aggregate/write 세 책임을 함수 단위로 분리해 두면 좋습니다.",
    ],
    "Django 뷰": [
        "User.objects.get 은 존재하지 않는 pk 에서 DoesNotExist 를 던지므로 get_object_or_404 가 안전합니다.",
        "Post 쿼리에 select_related/prefetch_related 가 없어 N+1 쿼리 위험이 있습니다.",
        "권한 검사가 비어 있어 다른 사용자의 상세 페이지도 그대로 노출되는 구조입니다.",
        "응답 페이로드 크기가 큰 경우를 위해 페이지네이션이나 부분 로딩 전략을 함께 두는 것이 좋습니다.",
    ],
    "비동기 HTTP 호출": [
        "await 가 리스트 컴프리헨션 안에서 순차로 처리돼 사실상 동기처럼 동작합니다. asyncio.gather 로 묶어야 병렬이 됩니다.",
        "응답 본문을 메모리에 한 번에 올리는 구조라 큰 파일에서는 부담이 큽니다.",
        "재시도, 타임아웃, 에러 응답 처리에 대한 정책이 코드에 드러나 있지 않습니다.",
        "수많은 URL 을 동시에 호출할 때는 세마포어로 동시성 한계를 명확히 잡아야 상대 서버를 보호할 수 있습니다.",
    ],
    "SQL 인젝션 위험 코드": [
        "f-string 으로 사용자 입력을 SQL 에 끼워 넣고 있어 인젝션에 그대로 노출됩니다. 파라미터 바인딩이 필수입니다.",
        "ORM 또는 prepared statement 로 바꾸면 보안과 함께 쿼리 플랜 캐시 효율도 좋아집니다.",
        "에러 시 stack trace 가 사용자에게 노출되는 경로가 없는지 별도로 점검해야 합니다.",
        "유닛 테스트에서 인젝션 입력을 시뮬레이션하는 케이스를 한두 개 두면 회귀 방지에 효과적입니다.",
    ],
    "예외 광범위 캐치": [
        "except 절에 타입이 없어 의도하지 않은 예외까지 삼키는 구조라 디버깅이 매우 어려워집니다.",
        "예외 발생 사실 자체가 어디로도 흘러가지 않아 운영 환경에서 침묵 실패가 누적될 수 있습니다.",
        "최소한 except Exception 으로 좁히고, 로그로 traceback 을 남기는 형태가 안전합니다.",
        "정말 일부 예외만 안전하게 처리해야 한다면 그 예외 타입을 구체적으로 명시하는 게 맞습니다.",
    ],
    "캐싱 데코레이터": [
        "전역 dict 를 캐시로 쓰고 있어 멀티 스레드 환경에서 경쟁 상태가 발생할 수 있습니다.",
        "캐시 크기 제한이 없어 오래 도는 프로세스에서는 메모리 누수처럼 보일 수 있습니다.",
        "functools.lru_cache 를 쓰면 동일 기능에 크기 제한과 통계가 기본 제공됩니다.",
        "인자에 mutable 객체가 들어오면 키로 쓰기 어려워 TypeError 가 날 수 있는 부분도 함께 처리해야 합니다.",
    ],
    "테스트 픽스처": [
        "인메모리 SQLite 를 쓰는 구성은 단위 테스트에 적합하지만, 실제 운영 DB 와 동작 차이가 있을 수 있는 점을 인지해야 합니다.",
        "트랜잭션 격리 수준이나 외래 키 제약 등이 실제와 다르게 동작할 수 있어 통합 테스트로 보완하는 게 좋습니다.",
        "픽스처 스코프를 명시하면 함수마다 새로 만들지, 모듈 단위로 공유할지 의도를 분명히 할 수 있습니다.",
        "닫기 처리는 yield 다음에 들어가 있어 좋지만, 예외 발생 시에도 안전한지 try/finally 형태를 함께 고려할 수 있습니다.",
    ],
}

# 일반 점검 항목 (코드별 특정 항목이 없을 때 fallback)
L1_GENERIC_POINTS = [
    "변수와 함수 이름이 의도를 충분히 드러내는지 한 번 더 점검해 보세요. 짧은 이름이 가독성을 깎는 경우가 잦습니다.",
    "단일 함수가 여러 책임을 동시에 지면 테스트 작성이 어려워집니다. 입력 검증, 핵심 로직, 부수 효과를 분리해 보세요.",
    "에러 처리 흐름이 행복 경로와 같은 들여쓰기에 섞여 있으면 의도가 흐려집니다. early return 으로 분리하면 가독성이 올라갑니다.",
    "로깅 메시지에 컨텍스트(요청 id, 사용자 id, 핵심 파라미터)를 함께 남기면 운영 추적이 훨씬 수월합니다.",
    "외부 입력은 신뢰하지 않는다는 원칙을 코드 어디서 적용하고 있는지 한 번 더 명시적으로 표시해 두면 좋습니다.",
    "테스트가 부족한 분기는 회귀 시 가장 먼저 깨지는 영역입니다. 최소한 행복 경로와 에러 경로 한 쌍은 확보해 두는 것이 안전합니다.",
    "함수 단위 시그니처에 타입 힌트가 있으면 호출 측 실수를 IDE 가 미리 잡아 줍니다.",
    "동시 실행 가능한 코드 경로에서 공유 상태가 있는지 한 번 더 살펴 보면 좋습니다.",
    "외부 의존성(파일, 네트워크, DB) 호출에는 타임아웃과 재시도 정책을 명시적으로 두는 것이 안전합니다.",
    "주석이 코드 동작과 어긋나 있는지 가장 흔한 함정입니다. 코드를 바꿨다면 주석도 함께 점검해 주세요.",
]


def gen_l1():
    lang, name, code = random.choice(L1_CODES)
    q_templates = [
        f"이 {lang} 코드 리뷰 해줘.\n\n{code}",
        f"아래 코드 한 번 봐 주세요. 어떤 부분을 다듬어야 할까요?\n\n{code}",
        f"{name} 인데 코드 리뷰 부탁드립니다.\n\n{code}",
        f"이 코드에서 개선할 점이 있을까요?\n\n{code}",
        f"PR 올리기 전에 리뷰 한 번 해 주세요.\n\n{code}",
    ]
    q = random.choice(q_templates)

    intro = random.choice(L_INTRO["L1"])
    outro = random.choice(L_OUTRO["L1"])

    # 점검 항목 5~7개 조합 (특정 + 일반 섞기)
    specific = L1_REVIEW_POINTS.get(name, [])
    generic_pool = list(L1_GENERIC_POINTS)
    random.shuffle(generic_pool)
    n_points = random.randint(5, 7)
    points: list[str] = []
    if specific:
        points.extend(random.sample(specific, min(len(specific), n_points - 2)))
    while len(points) < n_points:
        cand = generic_pool.pop()
        if cand not in points:
            points.append(cand)

    sections = [
        "## 전체 인상",
        intro,
        "",
        "## 점검 포인트",
    ]
    for i, p in enumerate(points, 1):
        sections.append(f"{i}. {p}")
    sections.append("")
    sections.append("## 우선순위 제안")
    sections.append(
        "- 단기: 입력 검증, 에러 처리, 로깅 보강처럼 회귀 위험이 적고 효과가 큰 항목.\n"
        "- 중기: 책임 분리와 테스트 보강을 함께 진행해 리팩터링 안전망 확보.\n"
        "- 장기: 동시성, 성능, 운영 관찰 가능성 영역을 별도 트랙으로 진행."
    )
    sections.append("")
    sections.append("## 마무리")
    sections.append(outro)

    a = "\n".join(sections)
    return q, a


# ============================================================
# L2 프로젝트 평가 (800) — 30+ 종 프로젝트 컨텍스트
# ============================================================

L2_PROJECTS = [
    "Next.js 풀스택 SaaS 초기 단계, 사용자 50명, 결제 미연동",
    "이커머스 모바일 앱, MAU 5만, 결제 전환율 1.2 퍼센트로 정체",
    "AI 챗봇 B2B SaaS, 기업 고객 3 곳 PoC 단계, GPT API 의존",
    "오픈소스 라이브러리, GitHub 별 800, 기여자 5명, 문서 부족",
    "사내 데이터 대시보드, 부서별 KPI 통합, 권한 관리 미흡",
    "교육 플랫폼 MVP, 무료 사용자만 존재, 유료 전환 모델 없음",
    "헬스케어 웹 앱, 의료기기 인증 대기 중, 사용자 테스트 미실시",
    "물류 운영 시스템, 배송 추적 코어, 레거시 PHP 일부 잔존",
    "구독형 뉴스레터 도구, 이메일 발송량 월 10만, 인증 단순",
    "P2P 거래 마켓플레이스, 양면 시장 초기, 신뢰 시스템 부재",
    "Flutter 모바일 게임, 캐주얼 퍼즐, 광고 수익 모델만 존재",
    "Web3 NFT 마켓, 사용자 정체, 가스비 부담 큼",
    "지식 그래프 검색 엔진, R&D 단계, 상용화 시점 미정",
    "재무 분석 SaaS, 회계 법인 3곳 사용, 보안 감사 미통과",
    "원격 협업 도구, 화상 회의 + 화이트보드, 경쟁 너무 많음",
    "음악 스트리밍 인디 플랫폼, 아티스트 200명, 저작권 관리 수동",
    "부동산 매물 검색, 크롤링 기반, 정합성 이슈 빈번",
    "AI 코딩 어시스턴트, VS Code 확장, 활성 사용자 2000명",
    "여행 일정 추천 앱, 콘텐츠 큐레이션 위주, 수익 모델 부재",
    "스마트홈 IoT 허브, 디바이스 호환성 30종, 펌웨어 업데이트 수동",
    "데이터 라벨링 플랫폼, 크라우드워커 1000명, 품질 검증 약함",
    "구독형 도시락 배송, 주 1500건, 메뉴 다양성 부족",
    "퇴직연금 추천 핀테크, 라이선스 협의 중, 사용자 0",
    "스타트업 인사 관리 SaaS, 50인 미만 기업 타깃, MAU 200",
    "교육용 인터랙티브 영상 플랫폼, 콘텐츠 30시간, 학습 효과 검증 미흡",
    "오프라인 매장 POS 시스템, 200개 매장 도입, 결산 보고서 약점",
    "API 게이트웨이 오픈소스, 별 5천, 엔터프라이즈 도입 없음",
    "농산물 직거래 앱, 농가 100곳, 결제 정산 수동",
    "법률 문서 자동화 SaaS, 변호사 30명 사용, LLM 환각 우려",
    "보안 침해 대응 플랫폼, MSP 2곳 도입, 오탐률 높음",
    "어린이 교육 콘텐츠 구독, 부모 사용자 5천, 이탈률 30 퍼센트",
]

L2_STRENGTHS = [
    "초기 단계에서 핵심 가치 제안이 명확히 잡혀 있다는 점은 큰 강점입니다.",
    "기술 스택이 익숙한 도구 위주로 구성돼 있어, 학습 비용 없이 빠르게 반복 실험이 가능합니다.",
    "단순한 정보 구조 덕분에 신규 사용자가 핵심 기능을 빨리 이해할 수 있는 구성입니다.",
    "팀의 운영 부담을 최소화하는 방향으로 인프라가 짜여 있어 초기 비용 효율이 좋습니다.",
    "도메인 전문성을 가진 인력이 합류해 있다면, 이는 다른 팀이 쉽게 따라가기 힘든 강점입니다.",
    "MVP 가 빨리 시장에 나가 있는 점은 정성적·정량적 피드백을 동시에 모을 수 있어 큰 자산입니다.",
    "API 우선 설계 덕분에 클라이언트가 늘어도 백엔드 부담이 선형적으로만 늘어납니다.",
]

L2_WEAKNESSES = [
    "수익 모델이 단일하거나 검증되지 않은 상태라 자금 흐름이 외부 변수에 크게 흔들릴 수 있습니다.",
    "사용자 이탈 원인을 정량 지표가 아니라 직관으로 추정하는 단계에 머물러 있어, 의사 결정이 느려질 위험이 있습니다.",
    "사용자 데이터 수집 범위와 동의 절차가 단순해 보여, 규제 대응 비용이 뒤늦게 들 가능성이 있습니다.",
    "코어 기능 외부 의존성이 한두 곳에 집중돼 있어, 단가나 가용성 리스크가 그대로 전이될 수 있습니다.",
    "초기 사용자 풀이 좁아 통계적으로 유의한 실험이 어려운 단계입니다.",
    "운영 자동화가 부족해 사용자가 늘면 단위 운영 비용이 비례 이상으로 증가할 위험이 있습니다.",
    "경쟁사 대비 차별화 요소가 한 줄로 설명되지 않는다면, 시장 진입에서 가장 큰 걸림돌이 될 수 있습니다.",
]

L2_NEXT = [
    "다음 한 분기는 가장 큰 가설 한두 개에 집중하고, 그 외 모든 작업은 보류해 보세요.",
    "사용자 인터뷰 10건과 정량 지표 5개를 짝지어 추적하는 체계부터 만들어 보시길 권합니다.",
    "유료 전환 가능성을 검증하려면 일부 코어 사용자 대상 가격 실험을 작게라도 진행해야 합니다.",
    "지표 정의를 먼저 합의한 뒤, 단순한 대시보드 하나만 두고 모두 같은 숫자를 보게 만드는 것이 첫 단계입니다.",
    "공급자 의존 리스크는 추상화 계층 하나만 두어도 크게 완화됩니다.",
    "성장 가설이 막힐 때를 대비해 비상용 가설 한두 개를 미리 문서화해 두면 의사 결정이 빨라집니다.",
    "투자 유치를 고민 중이라면, 지표 추적 도구와 단위경제 정리부터 먼저 마치는 것이 좋습니다.",
]


def gen_l2():
    ctx = random.choice(L2_PROJECTS)
    q_templates = [
        f"이 프로젝트 평가 좀 해줘 — {ctx}",
        f"우리 프로젝트 진단 부탁드립니다.\n컨텍스트: {ctx}",
        f"현재 상황에서 가장 위험한 부분이 뭘까요?\n프로젝트: {ctx}",
        f"객관적인 평가가 필요해서 여쭤봅니다. {ctx}",
        f"투자 미팅 전에 한 번 점검 부탁드려요. {ctx}",
    ]
    q = random.choice(q_templates)

    intro = random.choice(L_INTRO["L2"])
    outro = random.choice(L_OUTRO["L2"])
    strengths = random.sample(L2_STRENGTHS, k=3)
    weaknesses = random.sample(L2_WEAKNESSES, k=3)
    nexts = random.sample(L2_NEXT, k=3)

    parts = [
        "## 전체 인상",
        intro,
        "",
        "## 강점",
    ]
    for s in strengths:
        parts.append(f"- {s}")
    parts.append("")
    parts.append("## 약점 / 리스크")
    for w in weaknesses:
        parts.append(f"- {w}")
    parts.append("")
    parts.append("## 우선순위 제안")
    for i, n in enumerate(nexts, 1):
        parts.append(f"{i}. {n}")
    parts.append("")
    parts.append("## 마무리")
    parts.append(outro)

    a = "\n".join(parts)
    return q, a


# ============================================================
# L3 기술 비교 (800) — 50+ 쌍
# ============================================================

L3_PAIRS = [
    ("React", "Vue", "프론트엔드 프레임워크"),
    ("Next.js", "Remix", "리액트 메타 프레임워크"),
    ("Vue", "Svelte", "선언형 UI 프레임워크"),
    ("Angular", "React", "프론트엔드 프레임워크"),
    ("GraphQL", "REST", "API 스타일"),
    ("gRPC", "REST", "서비스 간 통신"),
    ("Postgres", "MongoDB", "데이터베이스"),
    ("Postgres", "MySQL", "관계형 DB"),
    ("MongoDB", "DynamoDB", "NoSQL"),
    ("Redis", "Memcached", "캐시"),
    ("Docker", "Podman", "컨테이너 런타임"),
    ("Kubernetes", "Nomad", "오케스트레이션"),
    ("AWS", "GCP", "클라우드"),
    ("AWS Lambda", "Cloudflare Workers", "서버리스"),
    ("Next.js App Router", "Pages Router", "라우팅 모델"),
    ("Tailwind", "CSS Modules", "스타일링"),
    ("Tailwind", "Styled Components", "스타일링"),
    ("Material UI", "Ant Design", "UI 컴포넌트 라이브러리"),
    ("Redux", "Zustand", "상태 관리"),
    ("Redux Toolkit", "Jotai", "상태 관리"),
    ("Zustand", "Jotai", "상태 관리"),
    ("Vite", "Webpack", "번들러"),
    ("Vite", "Turbopack", "번들러"),
    ("pnpm", "npm", "패키지 매니저"),
    ("pnpm", "yarn", "패키지 매니저"),
    ("Jest", "Vitest", "JS 테스트"),
    ("Playwright", "Cypress", "E2E 테스트"),
    ("Pytest", "unittest", "Python 테스트"),
    ("FastAPI", "Flask", "Python 웹 프레임워크"),
    ("Django", "FastAPI", "Python 웹 프레임워크"),
    ("Go", "Rust", "시스템 언어"),
    ("Go", "Node.js", "백엔드 런타임"),
    ("Rust", "C++", "시스템 언어"),
    ("Python", "Go", "백엔드 언어"),
    ("TypeScript", "Flow", "JS 타입 시스템"),
    ("Deno", "Node.js", "JS 런타임"),
    ("Bun", "Node.js", "JS 런타임"),
    ("SQLite", "Postgres", "임베디드/서버 DB"),
    ("Elasticsearch", "OpenSearch", "검색 엔진"),
    ("Kafka", "RabbitMQ", "메시지 브로커"),
    ("Kafka", "Redis Streams", "스트림 처리"),
    ("Terraform", "Pulumi", "IaC"),
    ("Terraform", "CloudFormation", "IaC"),
    ("GitHub Actions", "GitLab CI", "CI/CD"),
    ("Vercel", "Netlify", "프론트엔드 배포"),
    ("Cloudflare Pages", "Vercel", "프론트엔드 배포"),
    ("Prisma", "Drizzle", "TS ORM"),
    ("SQLAlchemy", "Tortoise ORM", "Python ORM"),
    ("OpenAI API", "Anthropic API", "LLM API"),
    ("vLLM", "TGI", "LLM 서빙"),
    ("LangChain", "LlamaIndex", "LLM 프레임워크"),
    ("Pinecone", "Weaviate", "벡터 DB"),
    ("Qdrant", "Milvus", "벡터 DB"),
]


def gen_l3():
    a, b, kind = random.choice(L3_PAIRS)
    q_templates = [
        f"{a} vs {b} 비교 해 줘.",
        f"{a} 와 {b} 중에 뭐가 더 나아? ({kind})",
        f"{kind} 고르고 있는데 {a} 랑 {b} 장단점 알려줘.",
        f"{a} 에서 {b} 로 옮기려는데 가치가 있을까?",
        f"{a} 와 {b} 의 차이를 표로 보여줘.",
    ]
    q = random.choice(q_templates)

    intro = random.choice(L_INTRO["L3"])
    outro = random.choice(L_OUTRO["L3"])

    a_strengths = [
        f"{a} 는 학습 곡선이 비교적 완만하고 생태계가 넓다는 점이 큰 강점입니다.",
        f"{a} 는 커뮤니티 답변과 레퍼런스가 풍부해 막혔을 때 해결 비용이 낮습니다.",
        f"{a} 는 도구 체인이 안정적이고, 운영 경험을 가진 인력 풀이 두텁습니다.",
        f"{a} 는 점진적 도입이 쉬워, 기존 코드와 섞어 쓰는 부담이 작습니다.",
    ]
    b_strengths = [
        f"{b} 는 최신 설계 철학을 더 적극적으로 반영해 성능과 개발 경험에서 인상적인 장점이 있습니다.",
        f"{b} 는 보일러플레이트가 적어 작은 팀이 빠르게 결과를 내는 데 유리합니다.",
        f"{b} 는 핵심 영역에서 더 일관된 API 를 제공해 학습 후 생산성이 빠르게 올라옵니다.",
        f"{b} 는 차세대 기능을 빠르게 흡수해, 미래 호환성에서 비교적 유리한 위치를 점하고 있습니다.",
    ]
    a_weaknesses = [
        f"{a} 는 오래된 패턴이 누적돼 있어, 새 코드와 옛 코드의 스타일 차이가 학습 부담으로 돌아올 수 있습니다.",
        f"{a} 는 일부 영역에서 디폴트 동작이 보수적이라, 적극적인 최적화에는 추가 설정이 필요합니다.",
        f"{a} 는 강력한 만큼 자유도가 커서, 팀 컨벤션이 약하면 일관성이 쉽게 무너집니다.",
    ]
    b_weaknesses = [
        f"{b} 는 비교적 새로워 운영 사례 풀이 좁고, 장기 호환성과 인력 수급 측면에서 변동성이 더 큽니다.",
        f"{b} 는 일부 엣지 케이스에서 도구 지원이 아직 부족할 수 있어, 도입 전에 PoC 가 거의 필수입니다.",
        f"{b} 는 생태계가 빠르게 변해 매년 베스트 프랙티스가 달라지는 부담이 있습니다.",
    ]

    table_rows = [
        ("학습 곡선", "비교적 완만하고 자료 풍부", "초반 컨셉 정리 후 가속, 자료는 점차 충실"),
        ("성능", "충분히 안정적인 영역", "최신 설계 덕분에 일부 시나리오에서 우위"),
        ("생태계", "패키지와 통합 도구가 두텁다", "핵심 위주이며 빠르게 확장 중"),
        ("운영 부담", "익숙한 패턴 덕에 낮음", "도구 체인 성숙도 따라 변동"),
        ("팀 적합도", "기존 인력 활용에 유리", "새 인력 채용·교육 시 유리"),
    ]

    parts = [
        "## 결론 요약",
        intro,
        "",
        f"## {a} 의 강점",
    ]
    for s in random.sample(a_strengths, k=2):
        parts.append(f"- {s}")
    parts.append("")
    parts.append(f"## {b} 의 강점")
    for s in random.sample(b_strengths, k=2):
        parts.append(f"- {s}")
    parts.append("")
    parts.append(f"## {a} 의 약점")
    for w in random.sample(a_weaknesses, k=2):
        parts.append(f"- {w}")
    parts.append("")
    parts.append(f"## {b} 의 약점")
    for w in random.sample(b_weaknesses, k=2):
        parts.append(f"- {w}")
    parts.append("")
    parts.append("## 비교 표")
    parts.append(f"| 항목 | {a} | {b} |")
    parts.append("| --- | --- | --- |")
    for col, av, bv in table_rows:
        parts.append(f"| {col} | {av} | {bv} |")
    parts.append("")
    parts.append("## 선택 가이드")
    parts.append(
        f"- 안정적인 운영 사례와 기존 자산이 중요하다면 {a} 가 무난한 출발선입니다.\n"
        f"- 새로운 설계 철학과 작은 팀의 속도를 중시한다면 {b} 가 매력적인 선택이 됩니다.\n"
        f"- 어느 쪽이든 도입 전에 작은 규모의 PoC 로 운영 부담을 미리 측정해 보세요."
    )
    parts.append("")
    parts.append("## 마무리")
    parts.append(outro)

    return q, "\n".join(parts)


# ============================================================
# L4 디자인 시스템 (600) — 30+ 종 컴포넌트/시스템
# ============================================================

L4_SUBJECTS = [
    "Tailwind 기반 버튼 컴포넌트의 디자인 토큰 정리",
    "Material UI 와 Ant Design 의 폼 컴포넌트 비교",
    "다크 모드 대응을 위한 색상 토큰 설계",
    "타이포 스케일 8단계 구성과 가독성",
    "접근성을 고려한 폼 검증 메시지 패턴",
    "키보드 포커스 링 디자인과 시각 일관성",
    "대시보드 카드 위계 정리 (헤더, 본문, 액션)",
    "모달과 드로어의 사용 시점 구분",
    "에러/경고/성공 색상 시스템 분리 원칙",
    "테이블 행 hover/selected 상태 정의",
    "버튼 사이즈/유형 매트릭스 설계",
    "아이콘 사용 가이드와 alt 텍스트",
    "토스트 알림의 위치, 길이, 우선순위",
    "모바일 우선 디자인에서 터치 타깃 크기",
    "그리드 시스템 12 컬럼과 24 컬럼 비교",
    "ARIA 라벨 사용 패턴",
    "리스트 vs 카드 vs 테이블 정보 표현 선택",
    "스켈레톤 로딩 vs 스피너 선택",
    "Empty state 디자인 패턴",
    "에러 페이지 (404, 500) 디자인 일관성",
    "input 컴포넌트 변형 (filled, outlined, underlined)",
    "Tag/Chip 컴포넌트 색상 의미 매핑",
    "Stepper 컴포넌트 진행 표시 패턴",
    "Avatar 컴포넌트 fallback 처리",
    "Tooltip vs Popover 사용 구분",
    "Card hover/elevation 정도 가이드",
    "Drawer 메뉴 정보 구조 우선순위",
    "Breadcrumb 컴포넌트 깊이 처리",
    "Search input 자동완성 패턴",
    "데이터 시각화 색상 팔레트 선택",
]

L4_POINTS = [
    "색상 토큰은 의미 단위(primary, success, warning, danger, neutral)로 먼저 잡고, 명도 단계는 그 위에 얹어야 의미 충돌을 막을 수 있습니다.",
    "타이포 스케일은 모듈러 비율(예: 1.25배)을 기준으로 잡되, 실제 화면에서 충분히 구분되는지 눈으로 다시 확인해야 합니다.",
    "포커스 링은 키보드 사용자의 핵심 단서이므로, 디자인적으로 거슬린다는 이유로 제거해서는 안 됩니다.",
    "텍스트와 배경의 대비비 4.5:1 (WCAG AA) 이상은 본문 텍스트의 최소선으로 잡는 것이 안전합니다.",
    "다크 모드에서는 단순 색상 반전이 아니라 표면 위계(elevation) 를 더 부드럽게 재정의해야 합니다.",
    "버튼 사이즈는 4 단계 이상으로 늘리지 말고 sm/md/lg 세 단계 + xs 한 단계 정도로 묶는 것을 권합니다.",
    "상태 색상(에러/경고/성공)은 색상에만 의존하지 말고 아이콘과 텍스트로 같은 의미를 한 번 더 전달해야 합니다.",
    "에러 메시지는 한 문장 안에 무엇이 잘못됐는지, 어떻게 해결할 수 있는지를 함께 담는 것이 좋습니다.",
    "Empty state 는 단순히 데이터가 없다는 안내가 아니라, 다음 행동으로 유도하는 CTA 까지 함께 두어야 합니다.",
    "Tooltip 은 보조 정보용이고, 의사 결정에 꼭 필요한 내용은 영구적으로 표시되는 자리에 두어야 합니다.",
    "토큰 명명은 디자이너와 개발자가 같은 이름으로 부를 수 있어야 합니다. 색상 코드 자체보다 의미 이름을 우선하세요.",
    "컴포넌트 변형이 너무 많으면 디자인 일관성이 흔들립니다. 변형 추가 전에 기존 변형과의 사용 시점 차이를 문서로 정리해 보세요.",
    "스크린리더 사용자를 위해 핵심 액션 버튼에는 시각 텍스트 외에도 aria-label 을 명시적으로 두는 것이 안전합니다.",
    "모바일 터치 타깃은 최소 44 픽셀 정도를 확보해야 손가락 오조작을 줄일 수 있습니다.",
    "데이터 시각화에서는 색약 사용자를 위해 색상만이 아니라 모양/패턴 차이를 함께 활용하는 것이 좋습니다.",
]


def gen_l4():
    subj = random.choice(L4_SUBJECTS)
    q_templates = [
        f"{subj} 분석해 줘.",
        f"디자인 시스템 관점에서 {subj} 점검 부탁드립니다.",
        f"{subj} 어떻게 잡는 게 좋을까요?",
        f"이 부분 작업 중인데 — {subj}. 개선 포인트 있을까요?",
    ]
    q = random.choice(q_templates)

    intro = random.choice(L_INTRO["L4"])
    outro = random.choice(L_OUTRO["L4"])

    points = random.sample(L4_POINTS, k=6)
    table_rows = [
        ("토큰화 정도", "의미 단위 + 단계 단위", "임시 색상 값 잔존 여부 점검"),
        ("접근성", "키보드 포커스, 대비비, ARIA 라벨", "스크린리더 시나리오로 점검"),
        ("일관성", "유사 컴포넌트 변형 수 제한", "사용 시점 문서화"),
        ("다크 모드", "표면 위계 재정의", "단순 반전 금지"),
        ("반응형", "터치 타깃 44 픽셀 이상", "모바일 우선 흐름"),
    ]

    parts = [
        "## 전체 인상",
        intro,
        "",
        "## 점검 항목",
    ]
    for i, p in enumerate(points, 1):
        parts.append(f"{i}. {p}")
    parts.append("")
    parts.append("## 평가 표")
    parts.append("| 항목 | 핵심 기준 | 점검 포인트 |")
    parts.append("| --- | --- | --- |")
    for col, std, chk in table_rows:
        parts.append(f"| {col} | {std} | {chk} |")
    parts.append("")
    parts.append("## 우선순위 제안")
    parts.append(
        "- 단기: 색상과 타이포 토큰 정리, 접근성 핵심 항목(대비비, 포커스 링) 적용.\n"
        "- 중기: 컴포넌트 변형 수 축소와 사용 가이드 문서화.\n"
        "- 장기: 패턴 라이브러리 구축과 디자인-개발 동기화 프로세스 정착."
    )
    parts.append("")
    parts.append("## 마무리")
    parts.append(outro)

    return q, "\n".join(parts)


# ============================================================
# L5 트러블슈팅 (800) — 60+ 종 에러/스택
# ============================================================

L5_ERRORS = [
    ("Python", "ImportError: cannot import name 'X' from partially initialized module", """```
File "app/models.py", line 3, in <module>
  from app.services import X
ImportError: cannot import name 'X' from partially initialized module 'app.services'
```"""),
    ("Python", "AttributeError: NoneType has no attribute", """```
Traceback (most recent call last):
  File "main.py", line 24, in handle
    user.profile.update(name)
AttributeError: 'NoneType' object has no attribute 'update'
```"""),
    ("Python", "TypeError dict expected str key", """```
TypeError: keys must be str, int, float, bool or None, not UUID
```"""),
    ("Python", "asyncio RuntimeError event loop is closed", """```
RuntimeError: Event loop is closed
```"""),
    ("Python", "sqlalchemy DetachedInstanceError", """```
sqlalchemy.orm.exc.DetachedInstanceError: Instance <User at 0x..> is not bound to a Session
```"""),
    ("Node.js", "EADDRINUSE 포트 점유", """```
Error: listen EADDRINUSE: address already in use :::3000
```"""),
    ("Node.js", "Cannot find module", """```
Error: Cannot find module 'lodash'
Require stack:
- /app/src/utils.js
```"""),
    ("Node.js", "MaxListenersExceededWarning", """```
(node:1234) MaxListenersExceededWarning: Possible EventEmitter memory leak detected. 11 listeners added.
```"""),
    ("Node.js", "Unhandled promise rejection", """```
UnhandledPromiseRejectionWarning: Error: connect ECONNREFUSED 127.0.0.1:6379
```"""),
    ("TypeScript", "TS2339 Property does not exist", """```
src/handler.ts:14:12 - error TS2339: Property 'name' does not exist on type '{}'.
```"""),
    ("TypeScript", "Type 'undefined' not assignable", """```
Type 'string | undefined' is not assignable to type 'string'.
```"""),
    ("React", "Hook 호출 규칙 위반", """```
Invalid hook call. Hooks can only be called inside of the body of a function component.
```"""),
    ("React", "Maximum update depth exceeded", """```
Maximum update depth exceeded. This can happen when a component calls setState inside useEffect.
```"""),
    ("Next.js", "Hydration mismatch", """```
Hydration failed because the initial UI does not match what was rendered on the server.
```"""),
    ("Next.js", "Module not found in App Router", """```
Module not found: Can't resolve '@/lib/db'
```"""),
    ("Go", "panic nil map", """```
panic: assignment to entry in nil map

goroutine 1 [running]:
main.add(...)
  /app/main.go:12
```"""),
    ("Go", "concurrent map write", """```
fatal error: concurrent map writes

goroutine 7 [running]:
runtime.throw(...)
```"""),
    ("Go", "interface conversion panic", """```
panic: interface conversion: interface {} is string, not int
```"""),
    ("Rust", "borrow already mutable", """```
error[E0499]: cannot borrow `*self` as mutable more than once at a time
```"""),
    ("Rust", "use of moved value", """```
error[E0382]: use of moved value: `s`
```"""),
    ("Postgres", "deadlock detected", """```
ERROR: deadlock detected
DETAIL: Process 12345 waits for ShareLock on transaction 67890
```"""),
    ("Postgres", "duplicate key violates unique constraint", """```
ERROR: duplicate key value violates unique constraint "users_email_key"
```"""),
    ("MySQL", "Lock wait timeout exceeded", """```
ERROR 1205 (HY000): Lock wait timeout exceeded; try restarting transaction
```"""),
    ("Redis", "MISCONF Redis is configured to save", """```
MISCONF Redis is configured to save RDB snapshots, but it is currently not able to persist on disk.
```"""),
    ("Docker", "no space left on device", """```
Error response from daemon: write /var/lib/docker/tmp/...: no space left on device
```"""),
    ("Docker", "exec format error", """```
exec /usr/local/bin/app: exec format error
```"""),
    ("Kubernetes", "CrashLoopBackOff", """```
NAME       READY   STATUS             RESTARTS   AGE
app-7f...  0/1     CrashLoopBackOff   5          7m
```"""),
    ("Kubernetes", "ImagePullBackOff", """```
Failed to pull image "ghcr.io/x/y:v1.2.3": rpc error: code = Unknown
```"""),
    ("Nginx", "upstream timed out", """```
upstream timed out (110: Connection timed out) while reading response header
```"""),
    ("CI", "out of memory in build", """```
The build was terminated: out-of-memory event detected
```"""),
    ("Browser", "CORS preflight 차단", """```
Access to fetch at 'https://api.example.com/x' from origin 'https://app.example.com' has been blocked by CORS policy
```"""),
    ("Browser", "Mixed content", """```
Mixed Content: The page at 'https://...' was loaded over HTTPS, but requested an insecure resource 'http://...'
```"""),
    ("OAuth", "redirect_uri_mismatch", """```
error=redirect_uri_mismatch
```"""),
    ("JWT", "JsonWebTokenError invalid signature", """```
JsonWebTokenError: invalid signature
```"""),
    ("Webpack", "Module parse failed", """```
Module parse failed: Unexpected token (1:0)
You may need an appropriate loader to handle this file type.
```"""),
    ("Vite", "Failed to resolve import", """```
Failed to resolve import "@/components/Button" from "src/App.vue"
```"""),
    ("Prisma", "P2002 unique constraint", """```
PrismaClientKnownRequestError: Unique constraint failed on the fields: (`email`)
```"""),
    ("Prisma", "P2025 record not found", """```
PrismaClientKnownRequestError: An operation failed because it depends on one or more records that were required but not found
```"""),
    ("Python", "ModuleNotFoundError 가상환경", """```
ModuleNotFoundError: No module named 'requests'
```"""),
    ("Python", "RecursionError maximum depth", """```
RecursionError: maximum recursion depth exceeded
```"""),
    ("Python", "JSONDecodeError", """```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```"""),
    ("Python", "Permission denied 파일 쓰기", """```
PermissionError: [Errno 13] Permission denied: '/var/log/app.log'
```"""),
    ("Node.js", "ESM/CJS interop", """```
Error [ERR_REQUIRE_ESM]: require() of ES Module .../node_modules/x/index.js
```"""),
    ("Node.js", "Heap out of memory", """```
FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory
```"""),
    ("Mac", "코드사이닝 실패", """```
errSecInternalComponent
```"""),
    ("git", "rebase 충돌", """```
CONFLICT (content): Merge conflict in src/index.ts
error: could not apply abc1234... feat: x
```"""),
    ("git", "detached HEAD", """```
You are in 'detached HEAD' state. ...
```"""),
    ("AWS", "S3 AccessDenied", """```
An error occurred (AccessDenied) when calling the GetObject operation: Access Denied
```"""),
    ("AWS", "Lambda timeout", """```
Task timed out after 3.00 seconds
```"""),
    ("Stripe", "webhook signature 검증 실패", """```
StripeSignatureVerificationError: No signatures found matching the expected signature
```"""),
    ("FCM", "registration token not registered", """```
messaging/registration-token-not-registered
```"""),
    ("Sentry", "rate limit exceeded", """```
429 Too Many Requests - x-sentry-rate-limit
```"""),
    ("TLS", "certificate has expired", """```
SSL: CERTIFICATE_VERIFY_FAILED certificate has expired
```"""),
    ("ESLint", "no-unused-vars", """```
'x' is defined but never used. eslint(no-unused-vars)
```"""),
    ("Flutter", "Gradle build failed", """```
FAILURE: Build failed with an exception.
> Could not resolve com.google.firebase:firebase-bom:32.0.0
```"""),
    ("Android", "INSTALL_FAILED_INSUFFICIENT_STORAGE", """```
adb: failed to install apk: INSTALL_FAILED_INSUFFICIENT_STORAGE
```"""),
    ("iOS", "code signing required", """```
error: Signing for "App" requires a development team.
```"""),
    ("Python", "asyncio Task was destroyed but pending", """```
Task was destroyed but it is pending!
```"""),
    ("Python", "UnicodeDecodeError utf-8", """```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0
```"""),
    ("Postgres", "too many connections", """```
FATAL: too many connections for role "app_user"
```"""),
    ("Postgres", "could not serialize", """```
ERROR: could not serialize access due to concurrent update
```"""),
]

L5_HYPOTHESES = [
    "환경 변수가 로컬과 배포 환경에서 다르게 주입돼, 한쪽에서만 재현되는 경우가 흔합니다.",
    "의존성 락 파일이 최신 상태가 아니어서, 빌드 머신마다 다른 버전이 설치돼 동작이 갈리는 경우가 있습니다.",
    "비동기 흐름에서 await 를 빠뜨려, 약속이 완료되기 전에 다음 단계로 넘어가는 패턴이 자주 원인이 됩니다.",
    "공유 자원(파일, 캐시, DB 커넥션)에 동시 접근이 일어나면서 일정 부하 이상에서만 드러나는 경합이 있습니다.",
    "타임존이 서버, DB, 클라이언트 사이에서 어긋나 같은 데이터를 다르게 해석하는 사례가 있습니다.",
    "캐시가 stale 상태로 유지돼 새 데이터가 반영되지 않는 패턴도 살펴볼 만합니다.",
    "권한 또는 토큰이 만료된 상태로 유지돼, 정상 흐름처럼 보이지만 응답만 빈 값으로 떨어지는 경우가 있습니다.",
    "외부 API 측 변경으로 응답 스키마가 미세하게 달라져, 기존 파서가 깨지는 사례가 종종 있습니다.",
]

L5_VERIFY = [
    "로컬에서 환경 변수를 배포 환경과 동일하게 맞춘 뒤 재현되는지 먼저 확인해 보세요.",
    "락 파일을 다시 생성한 뒤, 같은 커밋에서 다른 머신이 동일한 버전을 받는지 비교해 보세요.",
    "문제 함수에 임시 로그를 충분히 깔아, 어느 시점에 가정이 깨지는지 좁혀 보세요.",
    "동시성 가설이라면 단일 워커/단일 커넥션으로 강제해 동일 증상이 사라지는지 확인해 보세요.",
    "타임존 가설은 UTC 기준으로 같은 시점을 표현했을 때 양쪽이 같은지 비교해 보면 빠르게 좁힐 수 있습니다.",
    "캐시 가설이라면 캐시를 비우고 동일 요청이 정상 응답을 주는지 우선 점검해 보세요.",
    "토큰 만료 가설은 만료 시각을 강제로 짧게 잡아 같은 증상이 빨리 재현되는지 확인하는 방법이 빠릅니다.",
]

L5_PREVENT = [
    "회귀 방지용 단위 테스트를 한 개라도 좋으니 반드시 추가해, 같은 시나리오가 자동으로 잡히도록 만드세요.",
    "원인 분석 결과를 ADR 또는 사건 노트로 짧게라도 남기면 다음 회귀에서 진입 비용이 크게 줄어듭니다.",
    "운영 환경의 핵심 지표(에러율, 지연, 큐 길이)에 임계 알림을 걸어 두면 같은 류의 사고를 조기에 잡을 수 있습니다.",
    "외부 API 의존부에는 응답 스키마 검증 한 단을 두어, 변경을 즉시 감지할 수 있도록 하세요.",
    "동시성이 의심되는 영역에는 의도적으로 race 를 유도하는 부하 시험을 주기적으로 돌려 보면 좋습니다.",
]


def gen_l5():
    domain, name, trace = random.choice(L5_ERRORS)
    q_templates = [
        f"이 에러 해결 도와줘.\n\n{trace}",
        f"{domain} 에서 이런 에러가 떴는데 원인이 뭘까요?\n\n{trace}",
        f"디버깅 좀 부탁드립니다 — {name}.\n\n{trace}",
        f"운영 환경에서 이 에러가 갑자기 발생했어요.\n\n{trace}",
        f"로컬에서는 안 나고 배포 환경에서만 이 에러가 나요.\n\n{trace}",
    ]
    q = random.choice(q_templates)

    intro = random.choice(L_INTRO["L5"])
    outro = random.choice(L_OUTRO["L5"])
    hyps = random.sample(L5_HYPOTHESES, k=3)
    vers = random.sample(L5_VERIFY, k=3)
    prevs = random.sample(L5_PREVENT, k=3)

    parts = [
        "## 1단계 — 현상 정리",
        intro,
        f"에러 영역은 {domain} 쪽이고, 메시지의 핵심은 `{name}` 관련 문제로 보입니다. "
        "메시지가 가리키는 라인은 표면일 수 있고, 진짜 원인은 그 한두 호출 위 또는 외부 상태에 있는 경우가 잦습니다.",
        "",
        "## 2단계 — 가설",
    ]
    for i, h in enumerate(hyps, 1):
        parts.append(f"{i}. {h}")
    parts.append("")
    parts.append("## 3단계 — 검증 순서")
    for i, v in enumerate(vers, 1):
        parts.append(f"{i}. {v}")
    parts.append("")
    parts.append("## 4단계 — 해결 방향")
    parts.append(
        "- 가장 가능성이 높은 가설부터 한 번에 하나씩 바꾸고, 변경 전후 동작을 비교합니다.\n"
        "- 한 번에 여러 변수를 바꾸지 말고, 변경 단위가 작을수록 원인 식별이 빨라집니다.\n"
        "- 임시 우회가 가능하다면 빠르게 막아 두고, 근본 원인은 별도 작업으로 분리하세요."
    )
    parts.append("")
    parts.append("## 5단계 — 재발 방지")
    for i, p in enumerate(prevs, 1):
        parts.append(f"{i}. {p}")
    parts.append("")
    parts.append("## 마무리")
    parts.append(outro)

    return q, "\n".join(parts)


# ============================================================
# 빌더 본체
# ============================================================

CATEGORIES: list[tuple[str, int, Callable[[], tuple[str, str]]]] = [
    ("L1_code_review", 1000, gen_l1),
    ("L2_project_eval", 800, gen_l2),
    ("L3_tech_compare", 800, gen_l3),
    ("L4_design_system", 600, gen_l4),
    ("L5_troubleshoot", 800, gen_l5),
]


def build_sample(gen: Callable[[], tuple[str, str]], category: str, max_retries: int = 3):
    """gen() 으로 (q, a) 를 만들고 검증. 실패하면 재시도, 모두 실패하면 None."""
    last_reason = "unknown"
    for _ in range(max_retries):
        q, a = gen()
        ok, reason = is_clean_long_korean(a, category[:2])
        if ok:
            return {
                "messages": [
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": a},
                ],
                "_meta": {
                    "category": category[:2],
                    "len": len(a),
                    "src": "ko_long_v9",
                },
            }, "ok"
        last_reason = reason
    return None, last_reason


def build_all(verbose: bool = False) -> tuple[list[dict], dict]:
    samples: list[dict] = []
    stats = {
        "total_target": 0,
        "ok": 0,
        "skipped": 0,
        "by_reason": {},
        "by_cat": {},
        "lens_by_cat": {},
    }
    for name, count, gen in CATEGORIES:
        stats["total_target"] += count
        cat_ok = 0
        cat_skip = 0
        lens: list[int] = []
        for _ in range(count):
            sample, reason = build_sample(gen, name)
            if sample is None:
                cat_skip += 1
                stats["skipped"] += 1
                stats["by_reason"][reason] = stats["by_reason"].get(reason, 0) + 1
                continue
            samples.append(sample)
            lens.append(sample["_meta"]["len"])
            cat_ok += 1
            stats["ok"] += 1
        stats["by_cat"][name] = {"ok": cat_ok, "skipped": cat_skip}
        if lens:
            stats["lens_by_cat"][name] = {
                "mean": round(statistics.mean(lens), 1),
                "median": int(statistics.median(lens)),
                "min": min(lens),
                "max": max(lens),
            }
        if verbose:
            print(f"  {name}: ok={cat_ok}, skipped={cat_skip}")
    return samples, stats


def write_jsonl(path: str, samples: list[dict]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def validate_file(path: str) -> int:
    """jsonl 파일을 다시 읽어 모든 assistant 응답을 재검증. dirty 개수 반환."""
    dirty = 0
    total = 0
    by_reason: dict[str, int] = {}
    by_cat_len: dict[str, list[int]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            meta = obj.get("_meta", {})
            cat = meta.get("category", "??")
            for m in obj.get("messages", []):
                if m.get("role") != "assistant":
                    continue
                total += 1
                content = m.get("content", "")
                ok, reason = is_clean_long_korean(content, cat)
                if not ok:
                    dirty += 1
                    by_reason[reason] = by_reason.get(reason, 0) + 1
                by_cat_len.setdefault(cat, []).append(len(content))
    print(f"[validate] total={total}, dirty={dirty}, ok={total - dirty}")
    if by_reason:
        print(f"  dirty_reasons={by_reason}")
    for cat, lens in sorted(by_cat_len.items()):
        if lens:
            print(
                f"  {cat}: n={len(lens)}, "
                f"mean={round(statistics.mean(lens), 1)}, "
                f"median={int(statistics.median(lens))}, "
                f"min={min(lens)}, max={max(lens)}"
            )
    return dirty


def main():
    parser = argparse.ArgumentParser(description="화랑 v9 긴 응답 한국어 only SFT 데이터 빌더")
    parser.add_argument("--output", default="../../data/sft/ko_long_v9.jsonl")
    parser.add_argument("--validate", action="store_true",
                        help="기존 출력 파일을 재검증만 수행")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    out = os.path.abspath(args.output)

    if args.validate:
        if not os.path.exists(out):
            print(f"파일 없음: {out}", file=sys.stderr)
            sys.exit(2)
        dirty = validate_file(out)
        sys.exit(0 if dirty == 0 else 1)

    samples, stats = build_all(verbose=args.verbose)
    write_jsonl(out, samples)
    print(f"[build_ko_long_v9] {len(samples)} samples → {out}")
    print(f"  target={stats['total_target']}, ok={stats['ok']}, skipped={stats['skipped']}")
    print(f"  by_cat={stats['by_cat']}")
    if stats["lens_by_cat"]:
        print("  length stats:")
        for cat, s in stats["lens_by_cat"].items():
            print(f"    {cat}: mean={s['mean']}, median={s['median']}, min={s['min']}, max={s['max']}")
    if stats["by_reason"]:
        print(f"  skip_reasons={stats['by_reason']}")


if __name__ == "__main__":
    main()
