"""화랑 AI 프로그래밍 언어/패턴 보강 (120건+)

모든 주요 언어의 클로드 수준 답변 학습.
"왜 이렇게 하는지" + "좋은예/나쁜예" + "실무 판단 기준" 포함.

카테고리:
  - Python 실무 패턴 (20건)
  - TypeScript/JavaScript 심화 (20건)
  - React/Next.js 패턴 (20건)
  - 백엔드/API 패턴 (15건)
  - DB/SQL 패턴 (15건)
  - DevOps/인프라 (10건)
  - Rust/Go/기타 언어 (10건)
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
    # ═══ Python 실무 (20건) ═══
    m("파이썬 딕셔너리 활용법 알려줘 실무에서",
'''딕셔너리 실무 활용 패턴입니다.

```python
# ═══ 기본 CRUD ═══
user = {"name": "홍길동", "age": 28, "email": "hong@test.com"}

# 안전한 접근 (KeyError 방지)
name = user.get("name", "알 수 없음")        # ✅
phone = user.get("phone")                      # None (에러 안 남)
# name = user["phone"]                         # ❌ KeyError!

# 업데이트
user.update({"age": 29, "city": "서울"})       # 여러 키 동시 업데이트
user |= {"age": 30}                             # Python 3.9+ 병합

# ═══ 컴프리헨션 ═══
# 리스트 → 딕셔너리
users = [{"id": 1, "name": "홍"}, {"id": 2, "name": "김"}]
user_map = {u["id"]: u for u in users}         # {1: {...}, 2: {...}}

# 필터링
active = {k: v for k, v in users_dict.items() if v["status"] == "active"}

# 키/값 변환
upper_keys = {k.upper(): v for k, v in config.items()}

# ═══ defaultdict (자동 초기화) ═══
from collections import defaultdict

# 그룹핑
groups = defaultdict(list)
for item in items:
    groups[item["category"]].append(item)
# {"코딩": [...], "디자인": [...]}

# 카운팅
counts = defaultdict(int)
for word in words:
    counts[word] += 1

# ═══ 병합 패턴 ═══
defaults = {"theme": "light", "lang": "ko", "font_size": 14}
user_prefs = {"theme": "dark", "font_size": 16}
config = {**defaults, **user_prefs}  # user_prefs가 우선
# {"theme": "dark", "lang": "ko", "font_size": 16}

# Python 3.9+
config = defaults | user_prefs

# ═══ 실무: API 응답 파싱 ═══
response = {"data": {"users": [{"id": 1, "name": "홍"}]}, "meta": {"total": 100}}

# 안전한 중첩 접근
users = response.get("data", {}).get("users", [])
total = response.get("meta", {}).get("total", 0)

# ═══ 패턴 매칭 (Python 3.10+) ═══
match command:
    case {"action": "create", "data": data}:
        create_item(data)
    case {"action": "delete", "id": item_id}:
        delete_item(item_id)
    case _:
        raise ValueError("알 수 없는 명령")
```

핵심 규칙:
- `dict[key]` 대신 `dict.get(key, default)` 사용 (안전)
- `defaultdict`로 그룹핑/카운팅 간결화
- `{**a, **b}` 또는 `a | b`로 병합 (뒤가 우선)'''),

    m("파이썬 클래스 언제 쓰고 함수로 언제 해?",
'''클래스 vs 함수 선택 기준입니다.

```python
# ═══ 함수가 적합한 경우 ═══
# 1. 상태가 필요 없는 단순 변환
def calculate_tax(price: int, rate: float = 0.1) -> int:
    return int(price * rate)

# 2. 유틸리티/헬퍼
def format_phone(phone: str) -> str:
    return f"{phone[:3]}-{phone[3:7]}-{phone[7:]}"

# 3. 파이프라인 (입력 → 출력)
def process_order(order: dict) -> dict:
    validated = validate(order)
    priced = calculate_price(validated)
    return priced


# ═══ 클래스가 적합한 경우 ═══
# 1. 상태(state)를 유지해야 할 때
class ShoppingCart:
    def __init__(self):
        self.items: list[dict] = []
        self.discount_code: str | None = None

    def add(self, item: dict):
        self.items.append(item)

    def total(self) -> int:
        base = sum(i["price"] * i["qty"] for i in self.items)
        if self.discount_code:
            base = int(base * 0.9)
        return base

# 2. 관련 동작을 그룹핑할 때
class UserService:
    def __init__(self, db: Database):
        self.db = db  # 의존성 보관

    async def get(self, id: int) -> User:
        return await self.db.users.find(id)

    async def create(self, data: dict) -> User:
        return await self.db.users.create(data)

# 3. 프로토콜/인터페이스가 필요할 때
class PaymentGateway(Protocol):
    def charge(self, amount: int) -> bool: ...
    def refund(self, tx_id: str) -> bool: ...


# ═══ 판단 기준 ═══
# "이 코드에 self.xxx가 필요한가?"
#   YES → 클래스
#   NO  → 함수

# "여러 메서드가 같은 데이터를 공유하는가?"
#   YES → 클래스
#   NO  → 함수

# "테스트할 때 상태를 초기화해야 하는가?"
#   YES → 클래스 (인스턴스 새로 만들면 됨)
#   NO  → 함수
```

실무 원칙:
| 상황 | 선택 |
|------|------|
| 단순 계산/변환 | 함수 |
| 상태 유지 | 클래스 |
| DB 서비스 | 클래스 (DB 연결 보관) |
| 유틸리티 | 함수 |
| API 클라이언트 | 클래스 (인증/설정 보관) |
| 설정 객체 | dataclass |

**기본: 함수로 시작 → 상태 필요하면 클래스로 전환**'''),

    m("파이썬 예외 처리 제대로 하는 법",
'''예외 처리 실무 패턴입니다.

```python
# ═══ 원칙: 구체적으로 잡기 ═══

# ❌ 나쁜 예: 모든 에러를 삼킴
try:
    result = do_something()
except:
    pass  # 무슨 에러인지 모름!

# ❌ 나쁜 예: Exception으로 다 잡기
try:
    result = do_something()
except Exception:
    print("에러 발생")  # SystemExit, KeyboardInterrupt까지 잡힘

# ✅ 좋은 예: 구체적 예외만 잡기
try:
    user = await db.users.find(user_id)
except UserNotFoundError:
    return {"error": "사용자를 찾을 수 없습니다"}, 404
except DatabaseConnectionError as e:
    logger.error(f"DB 연결 실패: {e}")
    return {"error": "서버 오류"}, 500


# ═══ 커스텀 예외 계층 ═══
class AppError(Exception):
    """앱 기본 예외."""
    def __init__(self, message: str, code: str = "UNKNOWN"):
        super().__init__(message)
        self.code = code

class NotFoundError(AppError):
    def __init__(self, resource: str, id: str):
        super().__init__(f"{resource} #{id}을 찾을 수 없습니다", "NOT_FOUND")

class ValidationError(AppError):
    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}", "VALIDATION")

# 사용
def get_user(user_id: int) -> User:
    user = db.find(user_id)
    if not user:
        raise NotFoundError("사용자", str(user_id))
    return user


# ═══ 패턴: 변환 후 전파 ═══
# 저수준 에러 → 비즈니스 에러로 변환
def transfer_money(from_id: int, to_id: int, amount: int):
    try:
        sender = get_user(from_id)
        if sender.balance < amount:
            raise ValidationError("amount", "잔액이 부족합니다")
        # ...
    except IntegrityError:
        raise ValidationError("transfer", "동시 처리 충돌")


# ═══ 패턴: 재시도 ═══
import time

def retry(max_attempts=3, delay=1.0):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (TimeoutError, ConnectionError) as e:
                    if attempt == max_attempts:
                        raise
                    time.sleep(delay * attempt)
                    logger.warning(f"재시도 {attempt}/{max_attempts}: {e}")
        return wrapper
    return decorator

@retry(max_attempts=3, delay=0.5)
def call_external_api():
    return requests.get("https://api.example.com", timeout=5)


# ═══ 패턴: 정리 보장 (finally) ═══
def process_file(path: str):
    f = open(path)
    try:
        data = f.read()
        return parse(data)
    except ParseError as e:
        logger.error(f"파싱 실패: {e}")
        raise
    finally:
        f.close()  # 에러 발생해도 반드시 실행!

# 더 좋은 방법: with문
with open(path) as f:
    data = f.read()
```

핵심:
1. **구체적** 예외만 잡기 (Exception ❌)
2. **비즈니스 예외** 계층 만들기
3. **변환**: 저수준 → 고수준 에러
4. **전파**: 처리 못 하면 잡지 말고 올려보내기
5. **정리**: finally 또는 with문으로 리소스 보장'''),

    m("파이썬 타입 힌트 어떻게 써야해?",
'''Python 타입 힌트 실무 사용법입니다.

```python
from typing import Optional, Union
from collections.abc import Sequence

# ═══ 기본 ═══
def greet(name: str) -> str:
    return f"안녕하세요, {name}님!"

def add(a: int, b: int) -> int:
    return a + b

# ═══ 컬렉션 ═══
# Python 3.9+ (내장 타입 그대로)
def process(items: list[str]) -> dict[str, int]:
    return {item: len(item) for item in items}

# 중첩
users: list[dict[str, str | int]] = [
    {"name": "홍길동", "age": 28},
]

# ═══ Optional (None 가능) ═══
def find_user(id: int) -> Optional[dict]:  # dict | None
    user = db.get(id)
    return user  # None일 수 있음

# Python 3.10+
def find_user(id: int) -> dict | None:
    ...

# ═══ 함수 타입 ═══
from collections.abc import Callable

def apply(func: Callable[[int, int], int], a: int, b: int) -> int:
    return func(a, b)

# 콜백
OnComplete = Callable[[str], None]

def download(url: str, on_complete: OnComplete) -> None:
    data = fetch(url)
    on_complete(data)

# ═══ TypedDict (딕셔너리 구조) ═══
from typing import TypedDict

class UserDict(TypedDict):
    name: str
    email: str
    age: int
    role: str  # NotRequired[str] for optional

def create_user(data: UserDict) -> UserDict:
    ...

# ═══ 제네릭 ═══
from typing import TypeVar, Generic

T = TypeVar("T")

class Repository(Generic[T]):
    def find(self, id: int) -> T | None: ...
    def save(self, item: T) -> T: ...

user_repo: Repository[User] = UserRepository()

# ═══ 실무 패턴 ═══

# API 응답
class ApiResponse(TypedDict):
    data: list[dict]
    total: int
    page: int

# 설정
from dataclasses import dataclass

@dataclass
class Config:
    host: str = "localhost"
    port: int = 8000
    debug: bool = False
    workers: int = 4

# 열거형
from enum import Enum

class UserRole(Enum):
    ADMIN = "admin"
    USER = "user"
    EDITOR = "editor"

def check_permission(role: UserRole) -> bool:
    return role == UserRole.ADMIN
```

핵심 규칙:
- 함수 시그니처에는 **항상** 타입 힌트
- 변수는 타입이 명확하면 생략 OK (`name = "홍길동"`)
- `Any` 최소화 (쓰면 타입 안전성 무의미)
- `mypy --strict`로 검증'''),

    m("파이썬 가상환경 왜 쓰고 어떻게 관리해?",
'''가상환경은 프로젝트별 패키지를 격리합니다.

```bash
# ═══ 왜 필요한가? ═══
# 프로젝트 A: Django 4.2 필요
# 프로젝트 B: Django 5.0 필요
# → 가상환경 없으면 충돌!

# ═══ 방법 1: venv (기본 내장) ═══
python -m venv .venv          # 가상환경 생성
source .venv/bin/activate     # 활성화 (Mac/Linux)
.venv\\Scripts\\activate       # 활성화 (Windows)
pip install django            # 이 가상환경에만 설치
deactivate                    # 비활성화

# ═══ 방법 2: Poetry (추천!) ═══
pip install poetry
poetry init                   # pyproject.toml 생성
poetry add django             # 패키지 추가
poetry add -D pytest          # 개발 의존성
poetry install                # 전체 설치
poetry run python app.py      # 가상환경에서 실행
poetry shell                  # 가상환경 진입

# pyproject.toml 예시:
# [tool.poetry.dependencies]
# python = "^3.11"
# django = "^5.0"
# [tool.poetry.dev-dependencies]
# pytest = "^8.0"

# ═══ 방법 3: uv (2025 최신, 가장 빠름) ═══
pip install uv
uv venv                       # 가상환경 생성 (초고속)
uv pip install django         # 설치 (pip보다 10배 빠름)
uv run python app.py          # 실행

# ═══ .gitignore ═══
.venv/
venv/
__pycache__/
```

**선택 가이드:**
| 도구 | 추천 상황 |
|------|-----------|
| **Poetry** | 대부분의 프로젝트 (의존성 관리 + 가상환경) |
| **uv** | 속도 중시 (Poetry의 10배 빠름) |
| venv + pip | 간단한 스크립트 |

핵심: **프로젝트마다 별도 가상환경** = 의존성 충돌 방지!'''),

    m("파이썬 람다 함수 어떻게 쓰는거야?",
'''람다(lambda)는 한 줄짜리 익명 함수입니다.

```python
# ═══ 기본 ═══
# lambda 매개변수: 표현식
double = lambda x: x * 2
add = lambda x, y: x + y

double(5)     # 10
add(3, 4)     # 7

# ═══ 실무에서 쓰는 곳 ═══

# 1. 정렬 키
users = [{"name": "홍", "age": 28}, {"name": "김", "age": 25}]
users.sort(key=lambda u: u["age"])              # 나이순
users.sort(key=lambda u: u["name"])             # 이름순
users.sort(key=lambda u: -u["age"])             # 나이 역순

# 여러 기준
users.sort(key=lambda u: (u["role"], -u["age"]))

# 2. filter/map
numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
evens = list(filter(lambda x: x % 2 == 0, numbers))    # [2,4,6,8,10]
squared = list(map(lambda x: x**2, numbers))            # [1,4,9,16,...]

# 3. reduce
from functools import reduce
total = reduce(lambda acc, x: acc + x, numbers, 0)      # 55

# 4. 딕셔너리 정렬
scores = {"홍": 85, "김": 92, "이": 78}
sorted_scores = dict(sorted(scores.items(), key=lambda item: item[1], reverse=True))
# {"김": 92, "홍": 85, "이": 78}

# 5. 기본값 팩토리
from collections import defaultdict
counter = defaultdict(lambda: 0)

# ═══ 쓰지 말아야 할 때 ═══

# ❌ 복잡한 로직
process = lambda x: x.strip().lower().replace(" ", "_") if x else ""

# ✅ 일반 함수로 (가독성!)
def process(x: str) -> str:
    if not x:
        return ""
    return x.strip().lower().replace(" ", "_")

# ❌ 이름 붙인 람다 (의미 없음)
double = lambda x: x * 2  # 이럴 거면 def 쓰세요

# ✅
def double(x):
    return x * 2
```

규칙: **sort의 key, filter/map의 인자**처럼 "한 번 쓰고 버리는 간단한 함수"에만 lambda!'''),

    m("파이썬 enumerate zip 사용법",
'''enumerate와 zip은 반복문의 핵심 도구입니다.

```python
# ═══ enumerate: 인덱스 + 값 동시에 ═══
fruits = ["사과", "바나나", "딸기"]

# ❌ 인덱스 수동 관리
for i in range(len(fruits)):
    print(f"{i}. {fruits[i]}")

# ✅ enumerate 사용
for i, fruit in enumerate(fruits):
    print(f"{i}. {fruit}")

# 시작 번호 지정
for i, fruit in enumerate(fruits, start=1):
    print(f"{i}. {fruit}")
# 1. 사과
# 2. 바나나
# 3. 딸기

# 실무: 배치 처리 진행률
for i, item in enumerate(items, 1):
    process(item)
    if i % 100 == 0:
        print(f"진행: {i}/{len(items)} ({i/len(items)*100:.0f}%)")


# ═══ zip: 여러 리스트 동시 순회 ═══
names = ["홍길동", "김철수", "이영희"]
ages = [28, 32, 25]
emails = ["hong@test.com", "kim@test.com", "lee@test.com"]

# 동시 순회
for name, age, email in zip(names, ages, emails):
    print(f"{name} ({age}세) - {email}")

# 딕셔너리 만들기
user_ages = dict(zip(names, ages))
# {"홍길동": 28, "김철수": 32, "이영희": 25}

# 리스트 → 딕셔너리 리스트
keys = ["name", "age", "email"]
values = ["홍길동", 28, "hong@test.com"]
user = dict(zip(keys, values))
# {"name": "홍길동", "age": 28, "email": "hong@test.com"}

# zip_longest (길이 다를 때)
from itertools import zip_longest
for a, b in zip_longest([1,2,3], [10,20], fillvalue=0):
    print(a, b)  # (1,10), (2,20), (3,0)

# 전치 (행↔열)
matrix = [[1,2,3], [4,5,6], [7,8,9]]
transposed = list(zip(*matrix))
# [(1,4,7), (2,5,8), (3,6,9)]


# ═══ 조합 ═══
# enumerate + zip
for i, (name, age) in enumerate(zip(names, ages), 1):
    print(f"{i}. {name}: {age}세")
```

핵심:
- `enumerate` = "몇 번째인지 알고 싶을 때"
- `zip` = "여러 리스트를 나란히 쓸 때"
- 둘 다 **지연 평가**(lazy) → 메모리 효율적!'''),

    m("파이썬 *args **kwargs 설명해줘",
'''`*args`와 `**kwargs`는 가변 인자를 받는 방법입니다.

```python
# ═══ *args: 위치 인자를 튜플로 받기 ═══
def add(*args):
    return sum(args)

add(1, 2, 3)       # 6
add(1, 2, 3, 4, 5) # 15

# ═══ **kwargs: 키워드 인자를 딕셔너리로 받기 ═══
def create_user(**kwargs):
    print(kwargs)
    # {"name": "홍길동", "age": 28, "email": "hong@test.com"}

create_user(name="홍길동", age=28, email="hong@test.com")

# ═══ 조합 ═══
def flexible(required, *args, **kwargs):
    print(f"필수: {required}")
    print(f"추가 위치: {args}")
    print(f"추가 키워드: {kwargs}")

flexible("hello", 1, 2, 3, debug=True, verbose=False)
# 필수: hello
# 추가 위치: (1, 2, 3)
# 추가 키워드: {"debug": True, "verbose": False}

# ═══ 실무 활용 ═══

# 1. 데코레이터 (모든 함수에 적용 가능하게)
import functools

def log_calls(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print(f"호출: {func.__name__}({args}, {kwargs})")
        result = func(*args, **kwargs)
        print(f"결과: {result}")
        return result
    return wrapper

@log_calls
def any_function(x, y, z=10):
    return x + y + z

# 2. 함수 전달 (위임)
def make_request(method, url, **kwargs):
    # requests 라이브러리에 그대로 전달
    return requests.request(method, url, **kwargs)

make_request("GET", "/api/users", timeout=5, headers={"Auth": "token"})

# 3. 설정 오버라이드
def create_config(**overrides):
    defaults = {"host": "localhost", "port": 8000, "debug": False}
    return {**defaults, **overrides}

config = create_config(debug=True, port=3000)
# {"host": "localhost", "port": 3000, "debug": True}

# 4. 언패킹 (펼치기)
def greet(name, age, city):
    return f"{city}에 사는 {age}세 {name}"

user = {"name": "홍길동", "age": 28, "city": "서울"}
greet(**user)  # "서울에 사는 28세 홍길동"

numbers = [1, 2, 3]
add(*numbers)  # add(1, 2, 3) = 6
```

순서 규칙:
```python
def func(일반, *args, 키워드전용=기본값, **kwargs):
    pass
```'''),

    m("파이썬 문자열 메서드 총정리",
'''자주 쓰는 문자열 메서드입니다.

```python
s = "  Hello, World! 안녕하세요  "

# ═══ 공백 제거 ═══
s.strip()       # "Hello, World! 안녕하세요" (양쪽)
s.lstrip()      # "Hello, World! 안녕하세요  " (왼쪽)
s.rstrip()      # "  Hello, World! 안녕하세요" (오른쪽)

# ═══ 대소문자 ═══
"hello".upper()        # "HELLO"
"HELLO".lower()        # "hello"
"hello world".title()  # "Hello World"
"hello world".capitalize()  # "Hello world"

# ═══ 검색 ═══
"hello".startswith("he")   # True
"hello".endswith("lo")     # True
"hello world".find("world")  # 6 (인덱스, 없으면 -1)
"hello".count("l")         # 2
"hello" in "hello world"   # True (포함 여부)

# ═══ 변환 ═══
"hello".replace("l", "r")       # "herro"
"a,b,c".split(",")              # ["a", "b", "c"]
",".join(["a", "b", "c"])       # "a,b,c"
"  hello  world  ".split()      # ["hello", "world"] (연속 공백 처리)

# ═══ 검증 ═══
"123".isdigit()        # True (숫자만)
"abc".isalpha()        # True (문자만)
"abc123".isalnum()     # True (문자+숫자)
"  ".isspace()         # True (공백만)

# ═══ 포맷팅 ═══
name, age = "홍길동", 28
f"{name}님은 {age}세입니다"          # f-string (가장 추천)
"{}님은 {}세입니다".format(name, age)  # format()
"%-s님은 %d세입니다" % (name, age)    # % (레거시)

# ═══ 실무 패턴 ═══

# 이메일 검증 (간단)
def is_email(s: str) -> bool:
    return "@" in s and "." in s.split("@")[-1]

# slug 생성
def to_slug(title: str) -> str:
    return title.lower().strip().replace(" ", "-")

# 마스킹
def mask_email(email: str) -> str:
    name, domain = email.split("@")
    return f"{name[:2]}***@{domain}"
# "hong@test.com" → "ho***@test.com"

# 파일 확장자
filename = "document.pdf"
name, ext = filename.rsplit(".", 1)  # ("document", "pdf")

# 멀티라인
text = """
첫 번째 줄
두 번째 줄
""".strip()

# raw string (정규식에서)
import re
pattern = r"\d{3}-\d{4}-\d{4}"
```'''),

    m("파이썬 파일 입출력 총정리",
'''파일 읽기/쓰기 패턴입니다.

```python
from pathlib import Path

# ═══ 기본 읽기/쓰기 ═══

# 읽기
with open("data.txt", "r", encoding="utf-8") as f:
    content = f.read()        # 전체 문자열
    # 또는
    lines = f.readlines()     # 줄 리스트

# 쓰기
with open("output.txt", "w", encoding="utf-8") as f:
    f.write("안녕하세요\\n")
    f.write("화랑 AI입니다\\n")

# 추가 (append)
with open("log.txt", "a", encoding="utf-8") as f:
    f.write(f"[{datetime.now()}] 이벤트 발생\\n")

# ═══ 줄 단위 처리 (메모리 효율) ═══
with open("large_file.txt", encoding="utf-8") as f:
    for line in f:  # 한 줄씩 (메모리 절약!)
        process(line.strip())

# ═══ JSON ═══
import json

# 읽기
with open("config.json", encoding="utf-8") as f:
    data = json.load(f)

# 쓰기
with open("output.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# ═══ CSV ═══
import csv

# 읽기
with open("data.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        print(row["name"], row["age"])

# 쓰기
with open("output.csv", "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["name", "age"])
    writer.writeheader()
    writer.writerow({"name": "홍길동", "age": 28})

# ═══ pathlib (추천!) ═══
path = Path("data/output.txt")

# 디렉토리 생성
path.parent.mkdir(parents=True, exist_ok=True)

# 읽기/쓰기 (한 줄)
content = path.read_text(encoding="utf-8")
path.write_text("내용", encoding="utf-8")

# 바이너리
data = path.read_bytes()
path.write_bytes(b"\\x00\\x01")

# 파일 검색
for py_file in Path(".").rglob("*.py"):
    print(py_file)

# 파일 정보
path.exists()     # 존재 여부
path.is_file()    # 파일인지
path.is_dir()     # 디렉토리인지
path.suffix       # ".txt"
path.stem         # "output"
path.name         # "output.txt"
path.stat().st_size  # 크기 (바이트)
```

핵심:
- **항상 `with` 사용** (파일 자동 닫기)
- **항상 `encoding="utf-8"`** (한국어 깨짐 방지)
- **`pathlib.Path`** 사용 (os.path보다 현대적)'''),

    m("파이썬 데코레이터 만드는 법 실무에서",
'''데코레이터 만드는 실무 패턴입니다.

```python
import functools
import time
import logging

# ═══ 1. 기본 데코레이터 ═══
def log_call(func):
    @functools.wraps(func)  # 원본 함수 정보 보존 (필수!)
    def wrapper(*args, **kwargs):
        logging.info(f"호출: {func.__name__}")
        result = func(*args, **kwargs)
        logging.info(f"완료: {func.__name__} → {result}")
        return result
    return wrapper

@log_call
def add(a, b):
    return a + b

# ═══ 2. 인자 있는 데코레이터 ═══
def retry(max_attempts=3, delay=1.0):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts:
                        raise
                    logging.warning(f"재시도 {attempt}/{max_attempts}: {e}")
                    time.sleep(delay * attempt)
        return wrapper
    return decorator

@retry(max_attempts=5, delay=0.5)
def fetch_data(url):
    return requests.get(url, timeout=5).json()

# ═══ 3. 실행 시간 측정 ═══
def timer(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logging.info(f"{func.__name__}: {elapsed:.4f}초")
        return result
    return wrapper

@timer
def heavy_computation():
    ...

# ═══ 4. 캐시 (메모이제이션) ═══
def cache(ttl_seconds=300):
    def decorator(func):
        _cache = {}
        @functools.wraps(func)
        def wrapper(*args):
            now = time.time()
            if args in _cache:
                result, cached_at = _cache[args]
                if now - cached_at < ttl_seconds:
                    return result
            result = func(*args)
            _cache[args] = (result, now)
            return result
        return wrapper
    return decorator

@cache(ttl_seconds=60)
def get_user(user_id: int):
    return db.query(f"SELECT * FROM users WHERE id={user_id}")

# ═══ 5. 권한 체크 ═══
def require_role(*roles):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user.role not in roles:
                raise PermissionError(f"권한 부족: {user.role}")
            return func(*args, **kwargs)
        return wrapper
    return decorator

@require_role("admin", "editor")
def delete_post(post_id: int):
    ...

# ═══ 6. 비동기 데코레이터 ═══
def async_timer(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logging.info(f"{func.__name__}: {elapsed:.4f}초")
        return result
    return wrapper

@async_timer
async def fetch_users():
    return await db.users.find_many()
```

핵심:
- `@functools.wraps(func)` **필수** (함수 이름/문서 보존)
- 인자 없으면 2중, 인자 있으면 3중 중첩
- `*args, **kwargs`로 모든 함수에 적용 가능
- 비동기 함수는 `async def wrapper` 사용'''),

    m("파이썬 리스트 정렬 방법 총정리",
'''리스트 정렬 방법 총정리입니다.

```python
# ═══ 기본 ═══
numbers = [3, 1, 4, 1, 5, 9, 2, 6]

# sorted(): 새 리스트 반환 (원본 유지)
result = sorted(numbers)           # [1, 1, 2, 3, 4, 5, 6, 9]
result = sorted(numbers, reverse=True)  # 내림차순

# .sort(): 원본 변경 (None 반환)
numbers.sort()                     # numbers 자체가 변경됨

# ═══ key 함수 (정렬 기준) ═══
words = ["banana", "apple", "cherry", "date"]
sorted(words, key=len)             # 길이순
sorted(words, key=str.lower)       # 대소문자 무시

# ═══ 객체/딕셔너리 정렬 ═══
users = [
    {"name": "홍길동", "age": 28, "score": 85},
    {"name": "김철수", "age": 32, "score": 92},
    {"name": "이영희", "age": 25, "score": 78},
]

# 나이순
sorted(users, key=lambda u: u["age"])

# 점수 높은 순 (내림차순)
sorted(users, key=lambda u: u["score"], reverse=True)

# 여러 기준 (나이 오름차순 → 점수 내림차순)
sorted(users, key=lambda u: (u["age"], -u["score"]))

# ═══ operator 모듈 (더 빠름) ═══
from operator import itemgetter, attrgetter

# 딕셔너리
sorted(users, key=itemgetter("age"))
sorted(users, key=itemgetter("age", "name"))  # 다중 키

# 객체
sorted(user_objects, key=attrgetter("age"))

# ═══ 안정 정렬 (Stable Sort) ═══
# Python의 sort는 안정 정렬!
# → 같은 키의 원소는 원래 순서 유지

# 활용: 2단계 정렬
users.sort(key=lambda u: u["name"])   # 먼저 이름순
users.sort(key=lambda u: u["age"])    # 그 다음 나이순
# → 나이 같으면 이름순 유지!

# ═══ 실무 패턴 ═══

# Top N
top3 = sorted(users, key=lambda u: u["score"], reverse=True)[:3]

# 커스텀 순서
priority = {"긴급": 0, "높음": 1, "보통": 2, "낮음": 3}
sorted(tasks, key=lambda t: priority.get(t["priority"], 99))

# None 처리 (None을 맨 뒤로)
sorted(items, key=lambda x: (x is None, x))
```

핵심:
- `sorted()` = 새 리스트 (원본 보존) ← **기본으로 이거 쓰세요**
- `.sort()` = 원본 변경 (메모리 절약)
- `key=lambda` 또는 `key=itemgetter`로 정렬 기준
- Python sort는 **안정 정렬** (같은 키면 원래 순서)'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/lang_patterns_boost.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"프로그래밍 보강: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
