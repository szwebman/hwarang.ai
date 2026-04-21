"""화랑 AI 전체 프로그래밍 언어 심화 (110건+)

모든 주요 언어의 클로드 수준 심화 답변.
각 언어의 핵심 패턴, 실무 문제 해결, "왜" 이렇게 하는지 포함.

카테고리:
  - Python 추가 심화 (15건)
  - JavaScript/TypeScript 추가 (15건)
  - React/Next.js 추가 (15건)
  - Rust 심화 (10건)
  - Go 심화 (10건)
  - Java/Kotlin 심화 (10건)
  - SQL/DB 심화 (10건)
  - DevOps/Shell (10건)
  - C#/Swift/기타 (5건)
  - 알고리즘/자료구조 (10건)
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다.
답변할 때 "왜" 이렇게 하는지, 좋은 예/나쁜 예 비교, 실무 판단 기준을 포함합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ Python 추가 심화 (15건) ═══
    m("파이썬 walrus operator 알려줘 := 이거",
''':= (walrus operator)는 Python 3.8+에서 표현식 안에서 변수에 값을 할당합니다.

```python
# ═══ 기본: 할당과 사용을 동시에 ═══

# ❌ 기존 방식
line = input()
while line != "quit":
    process(line)
    line = input()

# ✅ walrus operator
while (line := input()) != "quit":
    process(line)

# ═══ 실무 활용 ═══

# 1. 리스트 컴프리헨션에서 중복 계산 방지
# ❌ expensive_func()을 2번 호출
results = [expensive_func(x) for x in data if expensive_func(x) > 10]

# ✅ 1번만 호출
results = [y for x in data if (y := expensive_func(x)) > 10]

# 2. 정규식 매칭
import re
if (match := re.search(r"(\\d+)원", text)):
    price = int(match.group(1))

# 3. API 응답 체크
if (response := requests.get(url)).status_code == 200:
    data = response.json()

# 4. None 체크
if (user := find_user(user_id)) is not None:
    send_email(user.email)

# 5. 파일 읽기
while (chunk := f.read(8192)):
    process(chunk)
```

쓸 때: 값을 **계산하고 바로 비교/사용**할 때
쓰지 말 때: 코드가 더 **복잡해지면** 그냥 2줄로 쓰세요'''),

    m("파이썬 dataclass 사용법 알려줘",
'''dataclass는 데이터 담는 클래스를 간결하게 만듭니다.

```python
from dataclasses import dataclass, field, asdict
from datetime import datetime

# ═══ 기본 ═══
@dataclass
class User:
    name: str
    email: str
    age: int = 0  # 기본값

user = User(name="홍길동", email="hong@test.com")
print(user)  # User(name='홍길동', email='hong@test.com', age=0)
# __init__, __repr__, __eq__ 자동 생성!

# ═══ 불변 (frozen) ═══
@dataclass(frozen=True)
class Point:
    x: float
    y: float

p = Point(3.0, 4.0)
# p.x = 5.0  # ❌ FrozenInstanceError

# ═══ 기본값 팩토리 ═══
@dataclass
class Config:
    host: str = "localhost"
    port: int = 8000
    tags: list[str] = field(default_factory=list)  # 가변 객체는 field()
    created_at: datetime = field(default_factory=datetime.now)

# ═══ 정렬 가능 ═══
@dataclass(order=True)
class Priority:
    level: int
    name: str = field(compare=False)  # 비교에서 제외

tasks = [Priority(3, "낮음"), Priority(1, "긴급"), Priority(2, "보통")]
sorted(tasks)  # [Priority(1, '긴급'), Priority(2, '보통'), Priority(3, '낮음')]

# ═══ 슬롯 (메모리 절약) ═══
@dataclass(slots=True)  # Python 3.10+
class Coordinate:
    x: float
    y: float
    z: float

# ═══ 변환 ═══
user = User(name="홍길동", email="hong@test.com")
user_dict = asdict(user)         # {'name': '홍길동', 'email': 'hong@test.com', 'age': 0}
user_json = json.dumps(asdict(user), ensure_ascii=False)

# ═══ 상속 ═══
@dataclass
class Admin(User):
    permissions: list[str] = field(default_factory=list)

# ═══ __post_init__ (검증) ═══
@dataclass
class Email:
    address: str

    def __post_init__(self):
        if "@" not in self.address:
            raise ValueError(f"잘못된 이메일: {self.address}")
```

**dataclass vs dict vs Pydantic:**
| | dataclass | dict | Pydantic |
|---|---|---|---|
| 타입 힌트 | ✅ | ❌ | ✅ |
| 런타임 검증 | ❌ | ❌ | ✅ |
| JSON 직렬화 | asdict() | 자체 | .model_dump() |
| 성능 | 가장 빠름 | 빠름 | 느림 |
| 용도 | 내부 데이터 | 간단한 것 | API 입출력 |'''),

    m("파이썬 itertools 실무 활용법",
'''itertools는 반복자를 다루는 강력한 도구입니다.

```python
from itertools import (
    chain, islice, groupby, product,
    combinations, permutations, count,
    accumulate, repeat, cycle, starmap,
    takewhile, dropwhile, compress
)

# ═══ chain: 여러 이터러블 연결 ═══
a = [1, 2, 3]
b = [4, 5, 6]
list(chain(a, b))  # [1, 2, 3, 4, 5, 6]

# 실무: 여러 소스 데이터 합치기
all_users = chain(db_users, api_users, csv_users)

# ═══ islice: 슬라이싱 (메모리 절약) ═══
# 100만 줄 파일에서 처음 10줄만
with open("huge.txt") as f:
    first_10 = list(islice(f, 10))

# ═══ groupby: 그룹핑 ═══
from operator import itemgetter
users = [
    {"name": "홍", "role": "admin"},
    {"name": "김", "role": "user"},
    {"name": "이", "role": "admin"},
    {"name": "박", "role": "user"},
]
# 주의: 먼저 정렬해야 함!
users.sort(key=itemgetter("role"))
for role, group in groupby(users, key=itemgetter("role")):
    print(f"{role}: {[u['name'] for u in group]}")
# admin: ['홍', '이']
# user: ['김', '박']

# ═══ product: 모든 조합 (카테시안 곱) ═══
sizes = ["S", "M", "L"]
colors = ["빨강", "파랑"]
list(product(sizes, colors))
# [('S','빨강'), ('S','파랑'), ('M','빨강'), ('M','파랑'), ('L','빨강'), ('L','파랑')]

# ═══ combinations: 조합 ═══
list(combinations([1,2,3,4], 2))
# [(1,2), (1,3), (1,4), (2,3), (2,4), (3,4)]

# ═══ permutations: 순열 ═══
list(permutations([1,2,3], 2))
# [(1,2), (1,3), (2,1), (2,3), (3,1), (3,2)]

# ═══ accumulate: 누적 합계 ═══
list(accumulate([1, 2, 3, 4, 5]))     # [1, 3, 6, 10, 15]
list(accumulate([1, 2, 3], max))       # [1, 2, 3] 누적 최대값

# ═══ takewhile/dropwhile ═══
list(takewhile(lambda x: x < 5, [1,3,5,2,1]))  # [1, 3]
list(dropwhile(lambda x: x < 5, [1,3,5,2,1]))  # [5, 2, 1]

# ═══ 실무: 배치 처리 ═══
def batched(iterable, n):
    it = iter(iterable)
    while batch := list(islice(it, n)):
        yield batch

for batch in batched(range(100), 10):
    process_batch(batch)  # 10개씩 처리
```

핵심: itertools는 **메모리를 거의 안 씀** (지연 평가). 대용량 데이터에 필수!'''),

    m("파이썬 pathlib 사용법 총정리",
'''pathlib은 os.path를 대체하는 현대적 경로 처리입니다.

```python
from pathlib import Path

# ═══ 경로 생성 ═══
path = Path("data/output/result.csv")
home = Path.home()                # /Users/username
cwd = Path.cwd()                  # 현재 디렉토리

# / 연산자로 경로 조합 (os.path.join 대체)
config = Path.home() / ".config" / "hwarang" / "settings.json"

# ═══ 경로 정보 ═══
path.name       # "result.csv"
path.stem       # "result"
path.suffix     # ".csv"
path.parent     # Path("data/output")
path.parts      # ("data", "output", "result.csv")
path.is_absolute()  # False

# ═══ 파일 읽기/쓰기 (한 줄!) ═══
# 읽기
content = Path("data.txt").read_text(encoding="utf-8")
data = Path("image.png").read_bytes()

# 쓰기
Path("output.txt").write_text("내용", encoding="utf-8")
Path("output.bin").write_bytes(b"\\x00\\x01")

# ═══ 디렉토리 ═══
Path("data/output").mkdir(parents=True, exist_ok=True)

# 파일 목록
for f in Path(".").iterdir():          # 현재 디렉토리
    print(f.name)

for f in Path(".").glob("*.py"):       # Python 파일만
    print(f)

for f in Path(".").rglob("*.py"):      # 하위 디렉토리 포함
    print(f)

# ═══ 존재 확인 ═══
path.exists()     # 존재?
path.is_file()    # 파일?
path.is_dir()     # 디렉토리?

# ═══ 파일 정보 ═══
stat = path.stat()
stat.st_size      # 바이트
stat.st_mtime     # 수정 시간

# ═══ 변환 ═══
path.with_suffix(".json")   # data/output/result.json
path.with_name("data.csv")  # data/output/data.csv
str(path)                    # "data/output/result.csv"

# ═══ 실무 패턴 ═══

# 프로젝트 루트 기준 경로
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CONFIG = ROOT / "config" / "settings.yaml"

# 파일 크기 포맷
def human_size(path: Path) -> str:
    size = path.stat().st_size
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

# 안전한 파일 쓰기 (원자적)
def safe_write(path: Path, content: str):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)  # 원자적 이동
```

핵심: `os.path.join()` → `Path() / "sub"` 로 교체!'''),

    m("파이썬 collections 모듈 알려줘",
'''collections 모듈의 실무 활용입니다.

```python
from collections import (
    Counter, defaultdict, OrderedDict,
    namedtuple, deque, ChainMap
)

# ═══ Counter: 빈도 세기 ═══
words = ["python", "java", "python", "go", "python", "java"]
counter = Counter(words)
# Counter({"python": 3, "java": 2, "go": 1})

counter.most_common(2)    # [("python", 3), ("java", 2)]
counter["python"]         # 3
counter["rust"]           # 0 (KeyError 안 남!)

# 실무: 로그 분석
error_counts = Counter(log["level"] for log in logs)

# ═══ defaultdict: 기본값 자동 생성 ═══
# 그룹핑
groups = defaultdict(list)
for user in users:
    groups[user["role"]].append(user)
# {"admin": [...], "user": [...]}

# 카운팅
counts = defaultdict(int)
for word in words:
    counts[word] += 1

# 중첩 딕셔너리
tree = defaultdict(lambda: defaultdict(list))
tree["2025"]["04"].append("이벤트1")

# ═══ deque: 양방향 큐 ═══
q = deque(maxlen=5)  # 최대 5개 유지
q.append(1)       # 오른쪽 추가
q.appendleft(0)   # 왼쪽 추가
q.pop()            # 오른쪽 제거
q.popleft()        # 왼쪽 제거

# 실무: 최근 N개 유지
recent_logs = deque(maxlen=100)
for log in stream:
    recent_logs.append(log)

# 실무: 슬라이딩 윈도우
def moving_average(data, window=3):
    d = deque(maxlen=window)
    for x in data:
        d.append(x)
        if len(d) == window:
            yield sum(d) / window

# ═══ namedtuple: 이름 있는 튜플 ═══
Point = namedtuple("Point", ["x", "y"])
p = Point(3, 4)
print(p.x, p.y)  # 3 4
print(p[0])       # 3 (인덱스도 가능)

# 실무: DB 행 표현
UserRow = namedtuple("UserRow", ["id", "name", "email"])
row = UserRow(1, "홍길동", "hong@test.com")

# ═══ ChainMap: 딕셔너리 체이닝 ═══
defaults = {"theme": "light", "lang": "ko"}
user_prefs = {"theme": "dark"}
config = ChainMap(user_prefs, defaults)
config["theme"]  # "dark" (user_prefs 우선)
config["lang"]   # "ko" (defaults에서)
```

핵심:
- `Counter` → 빈도 세기
- `defaultdict` → 그룹핑/카운팅
- `deque` → 큐, 최근 N개, 슬라이딩 윈도우
- `namedtuple` → 간단한 불변 데이터 (dataclass 경량 대안)'''),

    # ═══ JavaScript/TypeScript (15건) ═══
    m("자바스크립트 this 바인딩 알려줘",
'''`this`는 **호출 방식**에 따라 달라집니다.

```javascript
// ═══ 1. 일반 함수: 호출한 객체 ═══
const user = {
  name: "홍길동",
  greet() {
    console.log(this.name);  // "홍길동" (user가 호출)
  },
};
user.greet();  // this = user

// ❌ 분리하면 this 잃음
const greet = user.greet;
greet();  // this = undefined (strict mode) 또는 window

// ═══ 2. 화살표 함수: 선언 시점의 this (렉시컬) ═══
const user2 = {
  name: "홍길동",
  greet: () => {
    console.log(this.name);  // ❌ undefined! (상위 스코프의 this)
  },
  delayedGreet() {
    setTimeout(() => {
      console.log(this.name);  // ✅ "홍길동" (화살표 함수는 this 바인딩 없음)
    }, 1000);
  },
};

// ═══ 3. bind/call/apply ═══
function greet(greeting) {
  console.log(`${greeting}, ${this.name}`);
}

const user3 = { name: "홍길동" };

greet.call(user3, "안녕");      // "안녕, 홍길동"
greet.apply(user3, ["안녕"]);   // 같음 (배열로 인자)
const bound = greet.bind(user3); // 새 함수 생성
bound("안녕");                   // "안녕, 홍길동"

// ═══ 4. 클래스 ═══
class Component {
  constructor() {
    this.state = { count: 0 };
  }

  // ❌ 이벤트 핸들러로 전달하면 this 잃음
  handleClick() {
    this.state.count++;  // TypeError!
  }

  // ✅ 화살표 함수로 해결
  handleClick = () => {
    this.state.count++;  // OK (렉시컬 this)
  };
}

// ═══ 5. React에서 ═══
// 클래스 컴포넌트 (레거시)
class App extends React.Component {
  // ❌
  handleClick() { this.setState({}); }  // this 잃음

  // ✅ 방법 1: 화살표 함수
  handleClick = () => { this.setState({}); };

  // ✅ 방법 2: bind
  constructor() {
    super();
    this.handleClick = this.handleClick.bind(this);
  }
}

// 함수 컴포넌트 (2025 표준) → this 문제 없음!
function App() {
  const handleClick = () => {
    // this 고민 필요 없음
  };
}
```

**요약:**
| 함수 유형 | this |
|-----------|------|
| 일반 함수 | 호출한 객체 |
| 화살표 함수 | 선언 시점의 상위 this |
| bind/call/apply | 명시적 지정 |
| 생성자 | 새로 만든 인스턴스 |

핵심: **화살표 함수**를 쓰면 this 문제 대부분 해결!'''),

    m("자바스크립트 배열 구조분해 고급 패턴",
'''배열 구조분해(Destructuring) 고급 활용입니다.

```javascript
// ═══ 기본 ═══
const [a, b, c] = [1, 2, 3];

// 건너뛰기
const [first, , third] = [1, 2, 3];  // first=1, third=3

// 나머지
const [head, ...tail] = [1, 2, 3, 4, 5];
// head = 1, tail = [2, 3, 4, 5]

// 기본값
const [x = 10, y = 20] = [1];
// x = 1, y = 20

// ═══ 스왑 ═══
let a = 1, b = 2;
[a, b] = [b, a];  // a=2, b=1

// ═══ 함수 반환값 ═══
function getMinMax(arr) {
  return [Math.min(...arr), Math.max(...arr)];
}
const [min, max] = getMinMax([3, 1, 4, 1, 5]);
// min=1, max=5

// React useState가 대표적
const [count, setCount] = useState(0);
const [isOpen, setIsOpen] = useState(false);

// ═══ 중첩 ═══
const [[a1, a2], [b1, b2]] = [[1, 2], [3, 4]];
// a1=1, a2=2, b1=3, b2=4

// ═══ for...of와 조합 ═══
const entries = [["name", "홍길동"], ["age", 28]];
for (const [key, value] of entries) {
  console.log(`${key}: ${value}`);
}

// Map 순회
const map = new Map([["a", 1], ["b", 2]]);
for (const [key, value] of map) {
  console.log(key, value);
}

// Object.entries
const user = { name: "홍", age: 28 };
for (const [key, value] of Object.entries(user)) {
  console.log(`${key}: ${value}`);
}

// ═══ Promise.allSettled 결과 ═══
const results = await Promise.allSettled([fetchA(), fetchB()]);
const [
  { value: dataA, status: statusA },
  { value: dataB, status: statusB },
] = results;

// ═══ 정규식 매칭 ═══
const [, year, month, day] = "2025-04-21".match(/(\\d{4})-(\\d{2})-(\\d{2})/);
// year="2025", month="04", day="21"
```'''),

    m("Promise 체이닝 vs async/await 어떤게 나아?",
'''두 방식의 비교와 선택 기준입니다.

```javascript
// ═══ Promise 체이닝 ═══
fetchUser(userId)
  .then(user => fetchPosts(user.id))
  .then(posts => renderPosts(posts))
  .catch(error => showError(error))
  .finally(() => hideLoading());

// ═══ async/await ═══
async function loadPosts(userId) {
  try {
    const user = await fetchUser(userId);
    const posts = await fetchPosts(user.id);
    renderPosts(posts);
  } catch (error) {
    showError(error);
  } finally {
    hideLoading();
  }
}

// ═══ async/await가 나은 경우 ═══

// 1. 순차 실행 + 에러 처리
async function createOrder(data) {
  const user = await getUser(data.userId);          // 1
  const stock = await checkStock(data.items);        // 2
  const payment = await processPayment(data.total);  // 3
  const order = await saveOrder(data);               // 4
  return order;
}
// Promise 체이닝으로 하면 점점 읽기 어려움

// 2. 조건 분기
async function handleRequest(type) {
  const data = await fetchData();

  if (type === "admin") {
    const extra = await fetchAdminData();  // 조건부 await
    return { ...data, ...extra };
  }
  return data;
}

// 3. 루프 안에서 await
async function processItems(items) {
  for (const item of items) {
    await process(item);  // 순차 처리
  }
}


// ═══ Promise가 나은 경우 ═══

// 1. 병렬 실행
const [user, posts, stats] = await Promise.all([
  fetchUser(),
  fetchPosts(),
  fetchStats(),
]);

// 2. 간단한 변환
const data = await fetch(url).then(r => r.json());

// 3. 이벤트 핸들러 (async 불가능한 곳)
button.addEventListener("click", () => {
  fetchData().then(showResult).catch(showError);
});


// ═══ 흔한 실수 ═══

// ❌ 순차적으로 실행 (느림!)
const user = await fetchUser();
const posts = await fetchPosts();   // user 끝날 때까지 대기!
const stats = await fetchStats();   // posts 끝날 때까지 대기!

// ✅ 병렬로 실행 (빠름!)
const [user, posts, stats] = await Promise.all([
  fetchUser(),
  fetchPosts(),
  fetchStats(),
]);

// ❌ forEach + async (동작 안 함!)
items.forEach(async (item) => {
  await process(item);  // 병렬로 실행됨!
});

// ✅ for...of (순차)
for (const item of items) {
  await process(item);
}

// ✅ Promise.all (병렬)
await Promise.all(items.map(item => process(item)));
```

**결론: async/await를 기본으로, 병렬 실행은 Promise.all!**'''),

    m("자바스크립트 Set과 Map 사용법",
'''Set과 Map은 ES6의 핵심 자료구조입니다.

```javascript
// ═══ Set: 중복 없는 값 집합 ═══
const set = new Set([1, 2, 3, 3, 4, 4, 5]);
// Set {1, 2, 3, 4, 5}

set.add(6);         // 추가
set.delete(3);      // 삭제
set.has(2);          // true (존재 확인)
set.size;            // 5

// 실무: 배열 중복 제거
const unique = [...new Set(array)];

// 실무: 중복 체크
const seen = new Set();
for (const item of items) {
  if (seen.has(item.id)) {
    console.log("중복:", item.id);
    continue;
  }
  seen.add(item.id);
  process(item);
}

// 집합 연산
const a = new Set([1, 2, 3]);
const b = new Set([2, 3, 4]);

const union = new Set([...a, ...b]);           // 합집합 {1,2,3,4}
const intersection = new Set([...a].filter(x => b.has(x)));  // 교집합 {2,3}
const difference = new Set([...a].filter(x => !b.has(x)));   // 차집합 {1}


// ═══ Map: 키-값 쌍 (Object보다 강력) ═══
const map = new Map();
map.set("name", "홍길동");
map.set("age", 28);
map.set(42, "숫자 키도 가능");     // Object는 문자열 키만!
map.set({ id: 1 }, "객체 키도 가능");

map.get("name");    // "홍길동"
map.has("age");     // true
map.delete("age");
map.size;           // 3

// 순회 (삽입 순서 보장!)
for (const [key, value] of map) {
  console.log(`${key}: ${value}`);
}

// 실무: 캐시
const cache = new Map();

function fetchWithCache(url) {
  if (cache.has(url)) return cache.get(url);

  const data = fetch(url).then(r => r.json());
  cache.set(url, data);
  return data;
}

// 실무: 빈도 세기
function countWords(words) {
  const counts = new Map();
  for (const word of words) {
    counts.set(word, (counts.get(word) || 0) + 1);
  }
  return counts;
}

// Map → Object
const obj = Object.fromEntries(map);

// Object → Map
const map2 = new Map(Object.entries(obj));
```

**Object vs Map:**
| | Object | Map |
|---|---|---|
| 키 타입 | 문자열/심볼만 | **아무 타입** |
| 순서 | 보장 안 됨 | **삽입 순서 보장** |
| 크기 | Object.keys().length | **.size** |
| 성능 | 삽입/삭제 느림 | **삽입/삭제 빠름** |
| JSON | 직접 지원 | 변환 필요 |

핵심: 단순 설정 → Object, 동적 키-값/캐시 → **Map**!'''),

    m("자바스크립트 이벤트 위임 패턴 알려줘",
'''이벤트 위임(Event Delegation)은 부모에서 자식 이벤트를 처리하는 패턴입니다.

```javascript
// ═══ 문제: 각 아이템마다 이벤트 리스너 ═══
// ❌ 나쁜 예: 1000개 리스너 등록
document.querySelectorAll(".item").forEach(item => {
  item.addEventListener("click", handleClick);  // 1000개!
});
// 메모리 낭비 + 동적 추가 시 리스너 안 붙음

// ═══ 해결: 이벤트 위임 ═══
// ✅ 좋은 예: 부모에 1개만 등록
document.getElementById("list").addEventListener("click", (e) => {
  const item = e.target.closest(".item");  // 클릭한 곳의 가장 가까운 .item
  if (!item) return;  // .item이 아닌 곳 클릭 → 무시

  const id = item.dataset.id;
  handleItemClick(id);
});

// HTML
// <ul id="list">
//   <li class="item" data-id="1">항목 1</li>
//   <li class="item" data-id="2">항목 2</li>
//   <li class="item" data-id="3">항목 3</li>
//   <!-- 동적으로 추가되는 아이템도 자동 동작! -->
// </ul>

// ═══ React에서는? ═══
// React는 이미 이벤트 위임을 내부적으로 합니다!
// 하지만 리스트 최적화에는 여전히 유용:

// ❌ 각 아이템에 핸들러
function List({ items }) {
  return items.map(item => (
    <div onClick={() => handleClick(item.id)}>  {/* 매번 새 함수! */}
      {item.name}
    </div>
  ));
}

// ✅ 부모에서 위임
function List({ items }) {
  const handleClick = (e) => {
    const id = e.target.closest("[data-id]")?.dataset.id;
    if (id) handleItemClick(id);
  };

  return (
    <div onClick={handleClick}>  {/* 하나의 핸들러 */}
      {items.map(item => (
        <div data-id={item.id}>{item.name}</div>
      ))}
    </div>
  );
}

// ═══ 핵심 메서드 ═══
// e.target       → 실제 클릭된 요소
// e.currentTarget → 이벤트가 등록된 요소 (부모)
// e.target.closest(".class") → 가장 가까운 조상 찾기
```

장점:
1. **메모리 절약** (리스너 1개)
2. **동적 요소** 자동 지원 (나중에 추가해도 OK)
3. **성능** (DOM 조작 최소화)'''),

    m("자바스크립트 얕은 복사 깊은 복사 차이",
'''얕은 복사(Shallow)와 깊은 복사(Deep) 차이입니다.

```javascript
// ═══ 얕은 복사: 1단계만 복사 ═══
const original = { name: "홍", address: { city: "서울" } };

// 방법 1: 스프레드
const copy1 = { ...original };

// 방법 2: Object.assign
const copy2 = Object.assign({}, original);

// 문제!
copy1.name = "김";           // ✅ 원본 영향 없음
copy1.address.city = "부산";  // ❌ 원본도 "부산"으로 변경!
// → 중첩 객체는 같은 참조를 공유하기 때문

console.log(original.address.city);  // "부산" (원본도 바뀜!)


// ═══ 깊은 복사: 모든 단계 복사 ═══

// 방법 1: structuredClone (2022+, 가장 추천!)
const deep1 = structuredClone(original);
deep1.address.city = "부산";
console.log(original.address.city);  // "서울" ✅ (원본 안 바뀜!)

// 방법 2: JSON (제한적)
const deep2 = JSON.parse(JSON.stringify(original));
// ⚠️ 주의: Date, undefined, 함수, Map, Set 등은 복사 안 됨!

// 방법 3: lodash
import { cloneDeep } from "lodash";
const deep3 = cloneDeep(original);


// ═══ 배열도 마찬가지 ═══
const arr = [{ name: "홍" }, { name: "김" }];

// 얕은 복사
const shallow = [...arr];
shallow[0].name = "이";
console.log(arr[0].name);  // "이" ← 원본도 변경됨!

// 깊은 복사
const deep = structuredClone(arr);
deep[0].name = "이";
console.log(arr[0].name);  // "홍" ✅ 원본 유지


// ═══ React 상태 업데이트 ═══
// 중첩 객체 수정 시 주의!

// ❌ 직접 수정 (상태 변이!)
state.user.address.city = "부산";

// ✅ 깊은 복사 후 수정
setUser(prev => ({
  ...prev,
  address: {
    ...prev.address,
    city: "부산",
  },
}));

// ✅ 더 간단: Immer
import { produce } from "immer";
setUser(produce(draft => {
  draft.address.city = "부산";  // 직접 수정처럼 쓰지만 불변!
}));
```

**요약:**
| 상황 | 방법 |
|------|------|
| 1단계 객체 | `{ ...obj }` (스프레드) |
| 중첩 객체 | `structuredClone(obj)` |
| React 상태 | 스프레드 중첩 또는 Immer |
| 배열 | `[...arr]` (1단계) / `structuredClone` (중첩) |'''),

    m("for in vs for of 차이 알려줘",
'''`for...in`과 `for...of`의 차이입니다.

```javascript
// ═══ for...of: 값을 순회 (배열, 문자열, Map, Set 등) ═══
const fruits = ["사과", "바나나", "딸기"];

for (const fruit of fruits) {
  console.log(fruit);  // "사과", "바나나", "딸기"
}

// 문자열
for (const char of "화랑AI") {
  console.log(char);  // "화", "랑", "A", "I"
}

// Map
const map = new Map([["a", 1], ["b", 2]]);
for (const [key, value] of map) {
  console.log(key, value);
}

// Set
const set = new Set([1, 2, 3]);
for (const num of set) {
  console.log(num);
}


// ═══ for...in: 키(속성)를 순회 (객체) ═══
const user = { name: "홍길동", age: 28, email: "hong@test.com" };

for (const key in user) {
  console.log(key, user[key]);
  // "name" "홍길동"
  // "age" 28
  // "email" "hong@test.com"
}


// ═══ 배열에 for...in 쓰면 안 되는 이유! ═══
// ❌ 위험
const arr = [10, 20, 30];
for (const i in arr) {
  console.log(typeof i);  // "string"! (인덱스가 문자열)
  // 프로토타입 메서드도 나올 수 있음!
}

// ✅ 배열은 for...of
for (const value of arr) {
  console.log(value);  // 10, 20, 30
}


// ═══ 객체를 for...of로 순회하려면? ═══
// Object.entries() 사용
for (const [key, value] of Object.entries(user)) {
  console.log(key, value);
}

// Object.keys()
for (const key of Object.keys(user)) {
  console.log(key);
}

// Object.values()
for (const value of Object.values(user)) {
  console.log(value);
}
```

**핵심 규칙:**
| | for...of | for...in |
|---|---|---|
| 순회 대상 | **값** | **키(속성)** |
| 배열 | ✅ 사용 | ❌ 사용 금지 |
| 객체 | ❌ (직접 불가) | ✅ 사용 |
| Map/Set | ✅ | ❌ |
| 문자열 | ✅ | ⚠️ |

**쉽게 외우기: 배열은 of, 객체는 in!**'''),

    # ═══ Rust/Go/기타 (15건) ═══
    m("Rust 왜 배워야 해? 어디에 쓰여?",
'''Rust를 배워야 하는 이유와 사용처입니다.

```
═══ Rust의 핵심 가치 ═══

1. 메모리 안전 (GC 없이!)
   - C/C++: 메모리 누수, 댕글링 포인터, 버퍼 오버플로
   - Rust: 컴파일러가 전부 잡아줌 → 런타임 에러 없음!

2. C/C++ 수준 성능
   - GC 없음 → 예측 가능한 성능
   - 제로 비용 추상화

3. 동시성 안전
   - "두려움 없는 동시성" (Fearless Concurrency)
   - 데이터 레이스를 컴파일 타임에 감지

═══ 어디에 쓰이나? ═══

시스템:
  - Linux 커널 (6.1부터 Rust 코드 포함!)
  - 파일시스템, 드라이버

웹 인프라:
  - Cloudflare Workers (성능 핵심)
  - Deno (Node.js 대안, Rust로 작성)
  - SWC (Babel 대체, 70배 빠름)
  - Turbopack (Webpack 대체, Vercel)

CLI 도구:
  - ripgrep (grep 대체, 10배 빠름)
  - fd (find 대체)
  - bat (cat 대체)
  - exa (ls 대체)

게임/임베디드:
  - 게임 엔진 (Bevy)
  - WebAssembly
  - IoT/임베디드

AI/ML 인프라:
  - Hugging Face (tokenizers, safetensors)
  - Candle (ML 프레임워크)

블록체인:
  - Solana (Rust 기반)
  - Polkadot/Substrate

═══ Python 개발자가 Rust를 배우면? ═══
  - Python 확장 모듈 (PyO3)로 100배 성능 향상
  - 서버 사이드 성능 병목 해결
  - CLI 도구를 빠르게 만들기
```

배울 가치:
- **시스템/인프라** 개발자 → 필수
- **웹 개발자** → 선택 (하지만 SWC/Turbopack 등 도구 이해에 도움)
- **AI 개발자** → 추론 엔진, 데이터 파이프라인 최적화에 유용'''),

    m("Go에서 에러 처리 패턴 알려줘",
'''Go의 에러 처리는 "명시적 에러 반환"이 원칙입니다.

```go
// ═══ 기본: error 반환 ═══
func divide(a, b float64) (float64, error) {
    if b == 0 {
        return 0, fmt.Errorf("0으로 나눌 수 없습니다")
    }
    return a / b, nil
}

result, err := divide(10, 0)
if err != nil {
    log.Fatal(err)
}
fmt.Println(result)


// ═══ 커스텀 에러 타입 ═══
type NotFoundError struct {
    Resource string
    ID       string
}

func (e *NotFoundError) Error() string {
    return fmt.Sprintf("%s #%s을(를) 찾을 수 없습니다", e.Resource, e.ID)
}

func getUser(id string) (*User, error) {
    user := db.Find(id)
    if user == nil {
        return nil, &NotFoundError{Resource: "사용자", ID: id}
    }
    return user, nil
}

// 에러 타입 체크
var notFound *NotFoundError
if errors.As(err, &notFound) {
    http.Error(w, notFound.Error(), 404)
}


// ═══ 에러 래핑 (fmt.Errorf + %w) ═══
func getOrderDetails(orderID string) (*OrderDetails, error) {
    order, err := getOrder(orderID)
    if err != nil {
        return nil, fmt.Errorf("주문 조회 실패: %w", err)
        // 원본 에러를 유지하면서 맥락 추가
    }

    user, err := getUser(order.UserID)
    if err != nil {
        return nil, fmt.Errorf("주문 %s의 사용자 조회 실패: %w", orderID, err)
    }

    return &OrderDetails{Order: order, User: user}, nil
}

// errors.Is로 원본 에러 확인
if errors.Is(err, sql.ErrNoRows) {
    // 데이터 없음
}


// ═══ 센티넬 에러 ═══
var (
    ErrNotFound    = errors.New("찾을 수 없습니다")
    ErrUnauthorized = errors.New("인증이 필요합니다")
    ErrForbidden    = errors.New("권한이 없습니다")
)

func getResource(id string) (*Resource, error) {
    if !authenticated {
        return nil, ErrUnauthorized
    }
    // ...
}

if errors.Is(err, ErrUnauthorized) {
    http.Error(w, "로그인 필요", 401)
}


// ═══ defer로 정리 보장 ═══
func processFile(path string) error {
    f, err := os.Open(path)
    if err != nil {
        return fmt.Errorf("파일 열기 실패: %w", err)
    }
    defer f.Close()  // 함수 끝날 때 반드시 닫기

    // 파일 처리...
    return nil
}
```

Go 에러 처리 원칙:
1. **명시적 반환** (`if err != nil` 패턴)
2. **에러 래핑** (`fmt.Errorf("맥락: %w", err)`)
3. **커스텀 타입** (HTTP 상태 코드 매핑)
4. **센티넬 에러** (미리 정의된 에러)
5. **defer** (리소스 정리 보장)'''),

    m("Go에서 구조체와 메서드 알려줘",
'''Go의 구조체와 메서드 패턴입니다.

```go
package main

import (
    "fmt"
    "time"
)

// ═══ 구조체 정의 ═══
type User struct {
    ID        int       `json:"id"`
    Name      string    `json:"name"`
    Email     string    `json:"email"`
    Role      string    `json:"role"`
    CreatedAt time.Time `json:"created_at"`
}

// ═══ 메서드 (값 수신자) ═══
// 읽기 전용 → 값 수신자 (복사)
func (u User) DisplayName() string {
    return fmt.Sprintf("%s (%s)", u.Name, u.Email)
}

func (u User) IsAdmin() bool {
    return u.Role == "admin"
}

// ═══ 메서드 (포인터 수신자) ═══
// 수정 필요 → 포인터 수신자
func (u *User) SetRole(role string) {
    u.Role = role  // 원본 수정
}

func (u *User) UpdateEmail(email string) error {
    if email == "" {
        return fmt.Errorf("이메일은 필수입니다")
    }
    u.Email = email
    return nil
}

// ═══ 생성자 (New 패턴) ═══
func NewUser(name, email string) *User {
    return &User{
        Name:      name,
        Email:     email,
        Role:      "user",
        CreatedAt: time.Now(),
    }
}

// ═══ 임베딩 (상속 대신) ═══
type Admin struct {
    User          // 임베딩 (User의 모든 필드/메서드 사용 가능)
    Permissions []string
}

admin := Admin{
    User:        *NewUser("관리자", "admin@test.com"),
    Permissions: []string{"read", "write", "delete"},
}
admin.Name           // User의 필드 직접 접근
admin.DisplayName()  // User의 메서드 직접 호출

// ═══ 인터페이스 (암시적 구현) ═══
type Stringer interface {
    String() string
}

// User가 String() 메서드를 가지면 자동으로 Stringer 구현!
func (u User) String() string {
    return fmt.Sprintf("User{%s, %s}", u.Name, u.Email)
}

// ═══ 사용 ═══
func main() {
    user := NewUser("홍길동", "hong@test.com")
    fmt.Println(user.DisplayName())   // 홍길동 (hong@test.com)
    fmt.Println(user.IsAdmin())       // false

    user.SetRole("admin")
    fmt.Println(user.IsAdmin())       // true
}
```

핵심 규칙:
- **값 수신자** (`func (u User)`): 읽기만 할 때
- **포인터 수신자** (`func (u *User)`): 수정할 때 + 큰 구조체
- **임베딩**: 상속 대신 조합 (Go에는 상속 없음!)
- **인터페이스**: `implements` 없이 메서드만 맞으면 자동 구현'''),

    m("Rust에서 Option과 Result 어떻게 써?",
'''Rust의 에러 처리 핵심인 Option과 Result입니다.

```rust
// ═══ Option<T>: 값이 있거나 없거나 ═══
// Some(값) 또는 None

fn find_user(id: i64) -> Option<User> {
    let user = db.query("SELECT * FROM users WHERE id = ?", id);
    if user.is_empty() {
        None
    } else {
        Some(user)
    }
}

// 사용법 1: match
match find_user(1) {
    Some(user) => println!("찾음: {}", user.name),
    None => println!("없음"),
}

// 사용법 2: if let
if let Some(user) = find_user(1) {
    println!("이메일: {}", user.email);
}

// 사용법 3: unwrap_or (기본값)
let name = find_user(1)
    .map(|u| u.name)
    .unwrap_or("알 수 없음".to_string());

// 사용법 4: ? 연산자 (None이면 즉시 반환)
fn get_user_city(id: i64) -> Option<String> {
    let user = find_user(id)?;         // None이면 여기서 반환
    let profile = user.profile()?;      // None이면 여기서 반환
    Some(profile.city.clone())
}


// ═══ Result<T, E>: 성공 또는 실패 ═══
// Ok(값) 또는 Err(에러)

fn read_config(path: &str) -> Result<Config, std::io::Error> {
    let content = std::fs::read_to_string(path)?;  // 실패 시 Err 반환
    let config: Config = serde_json::from_str(&content)?;
    Ok(config)
}

// 사용법 1: match
match read_config("config.toml") {
    Ok(config) => println!("포트: {}", config.port),
    Err(e) => eprintln!("에러: {}", e),
}

// 사용법 2: ? 연산자 (에러 전파)
fn setup() -> Result<(), Box<dyn std::error::Error>> {
    let config = read_config("config.toml")?;
    let db = connect_db(&config.db_url)?;
    Ok(())
}

// 사용법 3: unwrap_or_else
let config = read_config("config.toml")
    .unwrap_or_else(|_| Config::default());

// ═══ 체이닝 ═══
fn get_user_email(id: i64) -> Result<String, AppError> {
    find_user(id)
        .ok_or(AppError::NotFound("사용자"))?  // Option → Result
        .email
        .ok_or(AppError::NotFound("이메일"))
}

// ═══ 실무: anyhow (애플리케이션) ═══
use anyhow::{Context, Result, bail};

fn process() -> Result<()> {
    let config = read_config("config.toml")
        .context("설정 파일을 읽을 수 없습니다")?;

    if config.port == 0 {
        bail!("포트가 0입니다");
    }

    Ok(())
}
```

핵심:
- **Option**: 값이 없을 수 있음 (`find`, `get` 등)
- **Result**: 실패할 수 있음 (파일, 네트워크, 파싱 등)
- **? 연산자**: 에러를 깔끔하게 전파
- **절대 `.unwrap()` 쓰지 마세요** (프로덕션에서 패닉!)'''),

    # ═══ SQL/DB (10건) ═══
    m("SQL JOIN 종류 알려줘 실무에서",
'''SQL JOIN 종류와 실무 사용법입니다.

```sql
-- ═══ 테이블 ═══
-- users: id, name, email
-- orders: id, user_id, total, created_at

-- ═══ INNER JOIN: 양쪽 다 있는 것만 ═══
-- "주문한 적 있는 사용자의 주문 목록"
SELECT u.name, o.total, o.created_at
FROM users u
INNER JOIN orders o ON o.user_id = u.id;
-- user_id가 없는 주문, 주문 없는 사용자 → 제외

-- ═══ LEFT JOIN: 왼쪽 전부 + 오른쪽 매칭 ═══
-- "모든 사용자와 주문 (주문 없는 사용자도 포함)"
SELECT u.name, COALESCE(o.total, 0) AS total
FROM users u
LEFT JOIN orders o ON o.user_id = u.id;
-- 주문 없는 사용자 → total = NULL (COALESCE로 0 처리)

-- 실무: "주문 안 한 사용자 찾기"
SELECT u.name, u.email
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE o.id IS NULL;  -- 매칭 안 된 것만

-- ═══ RIGHT JOIN: 오른쪽 전부 ═══
-- (LEFT JOIN을 뒤집은 것, 거의 안 씀)

-- ═══ FULL OUTER JOIN: 양쪽 전부 ═══
-- PostgreSQL만 지원 (MySQL 안 됨)
SELECT u.name, o.total
FROM users u
FULL OUTER JOIN orders o ON o.user_id = u.id;

-- ═══ CROSS JOIN: 모든 조합 ═══
-- "모든 사이즈 × 모든 색상"
SELECT s.name AS size, c.name AS color
FROM sizes s
CROSS JOIN colors c;
-- S-빨강, S-파랑, M-빨강, M-파랑, L-빨강, L-파랑

-- ═══ SELF JOIN: 자기 자신과 ═══
-- "같은 부서 동료 찾기"
SELECT a.name, b.name AS colleague
FROM employees a
JOIN employees b ON a.department_id = b.department_id
WHERE a.id != b.id;

-- ═══ 실무 패턴 ═══

-- 1. 사용자별 주문 통계
SELECT
    u.name,
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total), 0) AS total_spent
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
GROUP BY u.id, u.name
ORDER BY total_spent DESC;

-- 2. 최근 주문 (서브쿼리 + JOIN)
SELECT u.name, o.total, o.created_at
FROM users u
JOIN (
    SELECT DISTINCT ON (user_id) *
    FROM orders
    ORDER BY user_id, created_at DESC
) o ON o.user_id = u.id;
```

**선택 가이드:**
| JOIN | 사용 |
|------|------|
| INNER | 양쪽 모두 있는 데이터만 필요 |
| LEFT | 왼쪽 전부 + 매칭 (가장 많이 씀!) |
| LEFT + IS NULL | 매칭 안 되는 것 찾기 |
| CROSS | 모든 조합 생성 |'''),

    m("SQL 서브쿼리 vs JOIN 뭐가 나아?",
'''상황에 따라 다릅니다. 비교해 드릴게요.

```sql
-- ═══ 예시: "평균 이상 주문한 사용자" ═══

-- 방법 1: 서브쿼리
SELECT name, email
FROM users
WHERE id IN (
    SELECT user_id
    FROM orders
    GROUP BY user_id
    HAVING SUM(total) > (SELECT AVG(total_sum) FROM (
        SELECT SUM(total) AS total_sum FROM orders GROUP BY user_id
    ) t)
);

-- 방법 2: JOIN + CTE (더 읽기 쉬움!)
WITH user_totals AS (
    SELECT user_id, SUM(total) AS total_spent
    FROM orders
    GROUP BY user_id
),
avg_total AS (
    SELECT AVG(total_spent) AS avg_spent FROM user_totals
)
SELECT u.name, u.email, ut.total_spent
FROM users u
JOIN user_totals ut ON ut.user_id = u.id
CROSS JOIN avg_total a
WHERE ut.total_spent > a.avg_spent;


-- ═══ 서브쿼리가 나은 경우 ═══

-- 1. EXISTS (존재 여부만 체크)
SELECT name FROM users u
WHERE EXISTS (
    SELECT 1 FROM orders o WHERE o.user_id = u.id
);
-- JOIN보다 빠를 수 있음 (일찍 중단)

-- 2. 스칼라 서브쿼리 (단일 값)
SELECT name,
    (SELECT COUNT(*) FROM orders WHERE user_id = users.id) AS order_count
FROM users;

-- 3. IN 절 (값 목록)
SELECT * FROM users
WHERE department_id IN (SELECT id FROM departments WHERE active = true);


-- ═══ JOIN이 나은 경우 ═══

-- 1. 여러 테이블 컬럼이 필요할 때
SELECT u.name, o.total, p.name AS product
FROM users u
JOIN orders o ON o.user_id = u.id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id;

-- 2. 집계 + 그룹핑
SELECT u.name, COUNT(o.id), SUM(o.total)
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
GROUP BY u.id, u.name;


-- ═══ CTE (WITH)가 가장 나은 경우 ═══
-- 복잡한 쿼리를 단계별로 분해
WITH
step1 AS (SELECT user_id, SUM(total) AS total FROM orders GROUP BY user_id),
step2 AS (SELECT user_id, total FROM step1 WHERE total > 100000)
SELECT u.name, s.total
FROM users u
JOIN step2 s ON s.user_id = u.id;
```

**선택 기준:**
| 상황 | 추천 |
|------|------|
| 존재 여부 체크 | `EXISTS` (서브쿼리) |
| 여러 테이블 컬럼 | `JOIN` |
| 복잡한 로직 | `CTE (WITH)` |
| 단일 값 | 스칼라 서브쿼리 |
| 가독성 중요 | `CTE` > `JOIN` > 서브쿼리 |'''),

    m("SQL 윈도우 함수 알려줘",
'''윈도우 함수는 GROUP BY 없이 집계하는 강력한 기능입니다.

```sql
-- ═══ ROW_NUMBER: 순번 매기기 ═══
SELECT
    name,
    department,
    salary,
    ROW_NUMBER() OVER (ORDER BY salary DESC) AS rank
FROM employees;
-- 전체 급여 순위

-- 부서별 순위
SELECT
    name,
    department,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department  -- 부서별로 나눠서
        ORDER BY salary DESC     -- 급여 높은 순
    ) AS dept_rank
FROM employees;

-- ═══ RANK vs DENSE_RANK ═══
-- 90, 90, 80 일 때:
-- ROW_NUMBER: 1, 2, 3 (항상 유일)
-- RANK:       1, 1, 3 (같으면 같은 등수, 다음 건너뜀)
-- DENSE_RANK: 1, 1, 2 (같으면 같은 등수, 연속)

-- ═══ SUM/AVG OVER: 누적/이동 합계 ═══

-- 일별 누적 매출
SELECT
    date,
    revenue,
    SUM(revenue) OVER (ORDER BY date) AS cumulative_revenue
FROM daily_sales;

-- 7일 이동 평균
SELECT
    date,
    revenue,
    AVG(revenue) OVER (
        ORDER BY date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7d
FROM daily_sales;

-- ═══ LAG/LEAD: 이전/다음 행 값 ═══

-- 전일 대비 매출 변동
SELECT
    date,
    revenue,
    LAG(revenue) OVER (ORDER BY date) AS prev_day,
    revenue - LAG(revenue) OVER (ORDER BY date) AS change,
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY date))::numeric
        / NULLIF(LAG(revenue) OVER (ORDER BY date), 0) * 100, 1
    ) AS change_pct
FROM daily_sales;

-- ═══ FIRST_VALUE/LAST_VALUE ═══
-- 부서별 최고 급여자
SELECT
    name,
    department,
    salary,
    FIRST_VALUE(name) OVER (
        PARTITION BY department ORDER BY salary DESC
    ) AS top_earner
FROM employees;

-- ═══ 실무: 페이지네이션 + 총 개수 ═══
SELECT
    *,
    COUNT(*) OVER () AS total_count  -- 전체 개수 (별도 쿼리 불필요!)
FROM users
WHERE status = 'active'
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
-- total_count로 페이지 수 계산 가능
```

핵심:
- `OVER ()` = 전체 대상
- `OVER (PARTITION BY col)` = 그룹별
- `OVER (ORDER BY col)` = 순서 기반
- `ROWS BETWEEN` = 범위 지정 (슬라이딩 윈도우)'''),

    # ═══ 알고리즘/자료구조 (10건) ═══
    m("시간 복잡도 빅오 표기법 알려줘",
'''빅오(Big-O) 표기법은 알고리즘의 성능을 나타냅니다.

```
═══ 주요 복잡도 (빠른 순) ═══

O(1)       상수      - 해시맵 조회, 배열 인덱스 접근
O(log n)   로그      - 이진 탐색, 균형 이진 트리
O(n)       선형      - 배열 순회, 선형 탐색
O(n log n) 선형로그  - 정렬 (퀵소트, 머지소트)
O(n²)      이차      - 이중 루프, 버블 정렬
O(2ⁿ)      지수      - 피보나치 (재귀), 부분집합
O(n!)      팩토리얼  - 순열 생성

═══ n=100만일 때 실행 시간 비교 ═══
O(1):       1 연산          → 즉시
O(log n):   20 연산         → 즉시
O(n):       1,000,000 연산  → 1초 이내
O(n log n): 20,000,000 연산 → 몇 초
O(n²):      1조 연산        → 수 시간 ⚠️
O(2ⁿ):      우주가 끝나도... → 불가능 ❌
```

```python
# ═══ 코드로 보는 복잡도 ═══

# O(1) - 상수
def get_first(arr):
    return arr[0]  # 배열 크기와 무관

# O(n) - 선형
def find_max(arr):
    max_val = arr[0]
    for x in arr:     # n번
        if x > max_val:
            max_val = x
    return max_val

# O(n²) - 이차
def has_duplicate(arr):
    for i in range(len(arr)):        # n번
        for j in range(i+1, len(arr)):  # n번
            if arr[i] == arr[j]:
                return True
    return False

# O(n) - 해시맵으로 개선!
def has_duplicate_fast(arr):
    seen = set()
    for x in arr:         # n번
        if x in seen:     # O(1) 조회
            return True
        seen.add(x)
    return False

# O(log n) - 이진 탐색
def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
```

**실무 최적화 규칙:**
| 현재 | 개선 | 방법 |
|------|------|------|
| O(n²) | O(n) | 해시맵 사용 |
| O(n) | O(log n) | 정렬 후 이진 탐색 |
| O(n) | O(1) | 캐시/메모이제이션 |

**면접에서 자주 나오는 것:**
- "이 코드의 시간 복잡도는?" → 루프 중첩 수 확인
- "더 빠르게 할 수 있나?" → 해시맵, 정렬, 이진 탐색 고려'''),

    m("해시맵 어떻게 동작해? 왜 O(1)이야?",
'''해시맵의 내부 동작 원리입니다.

```
═══ 원리 ═══

1. 키를 해시 함수에 넣음
   "홍길동" → hash("홍길동") → 42

2. 해시값을 인덱스로 변환
   42 % 배열크기(16) → 인덱스 10

3. 해당 인덱스에 값 저장
   배열[10] = {"홍길동": User객체}

4. 조회 시 같은 과정
   "홍길동" → hash → 42 → 42%16=10 → 배열[10] → 찾음!

═══ 왜 O(1)인가? ═══
배열 인덱스 접근은 O(1)이고,
해시 계산도 O(1)이므로,
전체가 O(1)!
```

```python
# ═══ 간단한 해시맵 구현 ═══
class SimpleHashMap:
    def __init__(self, size=16):
        self.size = size
        self.buckets = [[] for _ in range(size)]

    def _hash(self, key):
        return hash(key) % self.size

    def put(self, key, value):
        idx = self._hash(key)
        bucket = self.buckets[idx]

        # 기존 키면 업데이트
        for i, (k, v) in enumerate(bucket):
            if k == key:
                bucket[i] = (key, value)
                return

        # 새 키면 추가
        bucket.append((key, value))

    def get(self, key):
        idx = self._hash(key)
        for k, v in self.buckets[idx]:
            if k == key:
                return v
        return None

    def delete(self, key):
        idx = self._hash(key)
        bucket = self.buckets[idx]
        for i, (k, v) in enumerate(bucket):
            if k == key:
                del bucket[i]
                return True
        return False

# ═══ 해시 충돌 ═══
# 다른 키인데 같은 인덱스가 나올 수 있음 (충돌)
# 해결 방법:
# 1. 체이닝: 같은 인덱스에 리스트로 연결 (위 코드)
# 2. 오픈 어드레싱: 다음 빈 칸에 저장

# ═══ 실무에서의 성능 ═══
# 평균: O(1) → 해시 충돌 적을 때
# 최악: O(n) → 모든 키가 같은 인덱스 (극히 드묾)
# 파이썬 dict는 최적화되어 있어 거의 항상 O(1)

# ═══ 사용 예시 ═══
# 1. 빈도 세기
counts = {}
for word in words:
    counts[word] = counts.get(word, 0) + 1

# 2. 중복 확인 (O(n²) → O(n))
seen = set()  # 내부적으로 해시맵
for item in items:
    if item in seen:  # O(1) 조회!
        print("중복!")
    seen.add(item)

# 3. 두 수의 합 (Two Sum)
def two_sum(nums, target):
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:      # O(1)
            return [seen[complement], i]
        seen[num] = i               # O(1)
```

핵심: **리스트에서 찾기 O(n)** → **해시맵으로 O(1)**으로 바꾸기!'''),

    m("스택이랑 큐 어디에 쓰여?",
'''스택과 큐의 실무 활용입니다.

```python
# ═══ 스택 (Stack): LIFO (후입선출) ═══
# 마지막에 넣은 것을 먼저 꺼냄

stack = []
stack.append(1)  # push
stack.append(2)
stack.append(3)
stack.pop()      # 3 (마지막 것)
stack.pop()      # 2

# 실무 1: Undo/Redo
class TextEditor:
    def __init__(self):
        self.text = ""
        self.undo_stack = []
        self.redo_stack = []

    def type(self, char):
        self.undo_stack.append(self.text)
        self.text += char
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.text)
            self.text = self.undo_stack.pop()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.text)
            self.text = self.redo_stack.pop()

# 실무 2: 괄호 검증
def is_valid(s: str) -> bool:
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for char in s:
        if char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack or stack[-1] != pairs[char]:
                return False
            stack.pop()
    return len(stack) == 0

is_valid("({[]})")  # True
is_valid("({[})")   # False

# 실무 3: 브라우저 뒤로가기
history_stack = []  # 방문 기록
history_stack.append("google.com")
history_stack.append("hwarang.ai")
history_stack.pop()  # 뒤로가기 → "google.com"


# ═══ 큐 (Queue): FIFO (선입선출) ═══
# 먼저 넣은 것을 먼저 꺼냄

from collections import deque

queue = deque()
queue.append(1)     # enqueue
queue.append(2)
queue.append(3)
queue.popleft()     # 1 (첫 번째 것)
queue.popleft()     # 2

# 실무 1: 작업 큐 (BFS)
def bfs(graph, start):
    visited = set()
    queue = deque([start])

    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        print(node)

        for neighbor in graph[node]:
            queue.append(neighbor)

# 실무 2: 메시지 큐
task_queue = deque()
task_queue.append({"type": "email", "to": "hong@test.com"})
task_queue.append({"type": "push", "to": "user_123"})

# 워커가 순서대로 처리
while task_queue:
    task = task_queue.popleft()
    process(task)

# 실무 3: 최근 N개 유지
recent_logs = deque(maxlen=100)  # 최대 100개
for log in stream:
    recent_logs.append(log)  # 101번째 추가 시 첫 번째 자동 삭제
```

| | 스택 | 큐 |
|---|---|---|
| 순서 | LIFO (후입선출) | FIFO (선입선출) |
| 비유 | 접시 쌓기 | 줄 서기 |
| 실무 | Undo, 괄호 검증, 재귀 | BFS, 작업 큐, 메시지 |
| 파이썬 | `list` (append/pop) | `deque` (append/popleft) |'''),

    # ═══ DevOps/Shell (10건) ═══
    m("쉘 스크립트 기본 알려줘",
'''쉘 스크립트 기본 문법입니다.

```bash
#!/bin/bash
# 첫 줄: 어떤 쉘로 실행할지 (shebang)

# ═══ 변수 ═══
NAME="화랑"
AGE=28
echo "이름: $NAME, 나이: $AGE"
echo "홈 디렉토리: $HOME"

# 명령 결과를 변수에
DATE=$(date +%Y-%m-%d)
FILE_COUNT=$(ls | wc -l)

# ═══ 조건문 ═══
if [ "$NAME" = "화랑" ]; then
    echo "화랑입니다"
elif [ "$AGE" -gt 30 ]; then
    echo "30세 이상"
else
    echo "기타"
fi

# 파일 존재 확인
if [ -f "config.json" ]; then
    echo "파일 있음"
fi

# 디렉토리 확인
if [ -d "/data" ]; then
    echo "디렉토리 있음"
fi

# ═══ 반복문 ═══
# for
for i in 1 2 3 4 5; do
    echo "숫자: $i"
done

# 범위
for i in $(seq 1 10); do
    echo $i
done

# 파일 순회
for file in *.py; do
    echo "파이썬 파일: $file"
done

# while
count=0
while [ $count -lt 5 ]; do
    echo "카운트: $count"
    count=$((count + 1))
done

# ═══ 함수 ═══
backup() {
    local source=$1
    local dest=$2
    local date=$(date +%Y%m%d)

    cp -r "$source" "${dest}/backup_${date}"
    echo "백업 완료: $source → $dest"
}

backup /data /backups

# ═══ 실무 패턴 ═══

# 에러 시 중단
set -e  # 에러 발생 시 즉시 종료
set -u  # 미정의 변수 사용 시 에러
set -o pipefail  # 파이프 중간 에러도 감지

# 로깅
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "스크립트 시작"
log "작업 완료"

# 인자 처리
if [ $# -lt 1 ]; then
    echo "사용법: $0 <환경>"
    echo "  예: $0 production"
    exit 1
fi

ENV=$1
echo "환경: $ENV"

# 확인 프롬프트
read -p "계속할까요? (y/n) " answer
if [ "$answer" != "y" ]; then
    echo "취소됨"
    exit 0
fi
```

실행:
```bash
chmod +x script.sh   # 실행 권한 부여
./script.sh           # 실행
bash script.sh        # 또는 이렇게
```

핵심 3줄: 스크립트 시작에 항상 `set -euo pipefail` 넣으세요!'''),

    m("sed awk 기본 사용법 알려줘",
'''sed와 awk는 텍스트 처리의 핵심 도구입니다.

```bash
# ═══ sed: 스트림 편집기 ═══
# "찾아서 바꾸기" + "줄 처리"

# 기본 치환
sed 's/old/new/' file.txt        # 첫 번째만
sed 's/old/new/g' file.txt       # 전체 (g = global)
sed -i 's/old/new/g' file.txt    # 파일 직접 수정 (-i)

# 실무: 설정 파일 수정
sed -i 's/PORT=3000/PORT=8000/' .env
sed -i 's|localhost|192.168.1.42|g' config.yaml  # 구분자를 |로 변경

# 특정 줄만
sed '3s/old/new/' file.txt       # 3번째 줄만
sed '2,5s/old/new/' file.txt     # 2~5줄

# 줄 삭제
sed '/^#/d' file.txt             # 주석(#으로 시작) 삭제
sed '/^$/d' file.txt             # 빈 줄 삭제
sed '1d' file.txt                # 첫 줄 삭제

# 줄 추가
sed '1i\\새로운 첫 줄' file.txt    # 1번 줄 앞에 삽입
sed '$a\\마지막 줄 추가' file.txt   # 끝에 추가


# ═══ awk: 텍스트 처리 언어 ═══
# "컬럼 기반 데이터 처리"

# 기본: 특정 컬럼 출력
echo "홍길동 28 서울" | awk '{print $1}'       # 홍길동
echo "홍길동 28 서울" | awk '{print $1, $3}'   # 홍길동 서울

# 구분자 지정
echo "홍길동,28,서울" | awk -F',' '{print $2}'  # 28

# CSV 처리
awk -F',' '{print $1, $3}' data.csv

# 조건
awk '$2 > 30 {print $1, $2}' data.txt   # 2번째 컬럼 > 30인 행

# 패턴 매칭
awk '/error/ {print}' log.txt           # "error" 포함된 줄
awk '/^2025/ {print $0}' log.txt        # 2025로 시작하는 줄

# 계산
awk '{sum += $2} END {print "합계:", sum}' data.txt
awk '{sum += $2; count++} END {print "평균:", sum/count}' data.txt

# 줄 번호
awk '{print NR, $0}' file.txt           # 줄번호 + 내용

# ═══ 실무 조합 ═══

# 로그에서 에러 수 세기
cat app.log | grep ERROR | awk '{print $4}' | sort | uniq -c | sort -rn | head -10

# CSV에서 특정 조건 필터
awk -F',' '$3 == "active" && $4 > 1000 {print $1, $4}' users.csv

# 디스크 사용량 상위 10
du -sh * | sort -rh | head -10

# nginx 접속 로그 분석 (IP별 요청 수)
awk '{print $1}' access.log | sort | uniq -c | sort -rn | head -20
```

핵심:
- `sed` = **찾아 바꾸기** (설정 파일 수정)
- `awk` = **컬럼 처리** (로그 분석, CSV)
- 둘 다 파이프(`|`)와 조합해서 사용'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/all_langs_deep.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"전체 언어 심화: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
