"""화랑 AI Python 고급 학습 데이터

데코레이터, 제너레이터, asyncio, typing, 메타클래스, 컨텍스트매니저 등.

사용법:
    python scripts/data/build_advanced_python.py \
        --output data/sft/advanced_python.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 파이썬 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 데코레이터 ═══
    m("파이썬 데코레이터 실무 패턴 알려줘",
'''데코레이터는 함수를 감싸서 기능을 추가하는 패턴입니다.

```python
import functools
import time
import logging
from typing import Callable, Any

# 1. 실행 시간 측정 데코레이터
def timer(func: Callable) -> Callable:
    """함수 실행 시간을 측정합니다."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logging.info(f"{func.__name__} 실행 시간: {elapsed:.4f}초")
        return result
    return wrapper

# 2. 재시도 데코레이터 (인자 있는 데코레이터)
def retry(max_attempts: int = 3, delay: float = 1.0):
    """실패 시 자동 재시도합니다."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    logging.warning(
                        f"{func.__name__} 시도 {attempt}/{max_attempts} 실패: {e}"
                    )
                    if attempt < max_attempts:
                        time.sleep(delay * attempt)  # 지수 백오프
            raise last_error
        return wrapper
    return decorator

# 3. 캐시 데코레이터 (TTL 포함)
def cache_with_ttl(ttl_seconds: int = 300):
    """결과를 TTL 기반으로 캐시합니다."""
    def decorator(func: Callable) -> Callable:
        cache: dict[str, tuple[Any, float]] = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            key = str(args) + str(kwargs)
            now = time.time()
            if key in cache:
                result, cached_at = cache[key]
                if now - cached_at < ttl_seconds:
                    return result
            result = func(*args, **kwargs)
            cache[key] = (result, now)
            return result
        return wrapper
    return decorator

# 4. 권한 체크 데코레이터
def require_role(*roles: str):
    """특정 역할이 필요한 엔드포인트에 사용합니다."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # request 객체에서 사용자 역할 확인
            request = kwargs.get("request") or (args[0] if args else None)
            user_role = getattr(request, "user_role", None)
            if user_role not in roles:
                raise PermissionError(
                    f"권한 부족: {user_role} (필요: {', '.join(roles)})"
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator

# 5. 사용 예시
@timer
@retry(max_attempts=3, delay=0.5)
@cache_with_ttl(ttl_seconds=60)
def fetch_user_data(user_id: int) -> dict:
    """외부 API에서 사용자 데이터를 가져옵니다."""
    import httpx
    response = httpx.get(f"https://api.example.com/users/{user_id}")
    response.raise_for_status()
    return response.json()

# 클래스 데코레이터
def singleton(cls):
    """싱글톤 패턴을 데코레이터로 구현합니다."""
    instances = {}
    @functools.wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance

@singleton
class DatabaseConnection:
    def __init__(self, url: str):
        self.url = url
        self.connected = True
```

데코레이터를 쌓을 때 순서가 중요합니다. 아래에서 위로 실행됩니다.
`@functools.wraps`를 항상 사용해서 원본 함수의 메타데이터를 보존하세요.'''),

    # ═══ 제너레이터 & 이터레이터 ═══
    m("파이썬 제너레이터 실무 활용법 알려줘",
'''제너레이터는 메모리 효율적인 데이터 처리에 핵심입니다.

```python
from typing import Generator, Iterator
import csv
from pathlib import Path

# 1. 대용량 파일 처리 (메모리 절약)
def read_large_file(path: str, chunk_size: int = 8192) -> Generator[str, None, None]:
    """대용량 파일을 줄 단위로 읽습니다."""
    with open(path, "r", encoding="utf-8") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

# 2. CSV 스트리밍 처리
def process_csv_stream(path: str) -> Generator[dict, None, None]:
    """CSV를 한 행씩 처리합니다 (수백만 행도 OK)."""
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 필터링/변환 후 yield
            if row.get("status") == "active":
                yield {
                    "id": int(row["id"]),
                    "name": row["name"].strip(),
                    "score": float(row["score"]),
                }

# 3. 파이프라인 패턴
def pipeline_example():
    """제너레이터 체이닝으로 데이터 파이프라인 구성."""
    # 각 단계가 제너레이터 → 메모리 O(1)
    raw_data = read_lines("data.txt")
    parsed = (json.loads(line) for line in raw_data)
    filtered = (item for item in parsed if item["score"] > 80)
    transformed = (
        {**item, "grade": "A" if item["score"] >= 90 else "B"}
        for item in filtered
    )

    # 최종 소비
    for item in transformed:
        save_to_db(item)

# 4. send()를 활용한 코루틴 패턴
def running_average() -> Generator[float, float, None]:
    """실시간 이동 평균 계산기."""
    total = 0.0
    count = 0
    average = 0.0
    while True:
        value = yield average
        total += value
        count += 1
        average = total / count

# 사용법
avg = running_average()
next(avg)  # 초기화
print(avg.send(10))   # 10.0
print(avg.send(20))   # 15.0
print(avg.send(30))   # 20.0

# 5. 무한 시퀀스
def fibonacci() -> Generator[int, None, None]:
    """무한 피보나치 수열."""
    a, b = 0, 1
    while True:
        yield a
        a, b = b, a + b

# itertools와 조합
from itertools import islice, takewhile
fib_10 = list(islice(fibonacci(), 10))           # 처음 10개
fib_under_100 = list(takewhile(lambda x: x < 100, fibonacci()))

# 6. 컨텍스트 매니저 + 제너레이터
from contextlib import contextmanager

@contextmanager
def db_transaction(conn):
    """트랜잭션을 컨텍스트 매니저로 관리합니다."""
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()

# 사용법
with db_transaction(connection) as cursor:
    cursor.execute("INSERT INTO users ...")
```

핵심 규칙:
- 대용량 데이터 → 리스트 대신 제너레이터
- `yield` = 한 번에 하나씩 반환 (메모리 절약)
- 제너레이터 표현식 `(x for x in items)` 적극 활용'''),

    # ═══ asyncio ═══
    m("파이썬 asyncio 비동기 프로그래밍 알려줘",
'''asyncio는 I/O 바운드 작업(네트워크, DB, 파일)을 효율적으로 처리합니다.

```python
import asyncio
import httpx
from typing import Any
import time

# 1. 기본 비동기 함수
async def fetch_url(client: httpx.AsyncClient, url: str) -> dict:
    """URL에서 데이터를 비동기로 가져옵니다."""
    response = await client.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

# 2. 동시 요청 (핵심!)
async def fetch_all_users(user_ids: list[int]) -> list[dict]:
    """여러 사용자 데이터를 동시에 가져옵니다."""
    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_url(client, f"https://api.example.com/users/{uid}")
            for uid in user_ids
        ]
        # 모든 태스크 동시 실행
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 에러 필터링
    users = []
    for r in results:
        if isinstance(r, Exception):
            logging.error(f"요청 실패: {r}")
        else:
            users.append(r)
    return users

# 3. 세마포어로 동시성 제한
async def rate_limited_fetch(urls: list[str], max_concurrent: int = 10):
    """동시 요청 수를 제한합니다 (API rate limit 대응)."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_with_limit(url: str) -> dict:
        async with semaphore:  # 최대 max_concurrent개만 동시 실행
            async with httpx.AsyncClient() as client:
                return await fetch_url(client, url)

    return await asyncio.gather(*[fetch_with_limit(url) for url in urls])

# 4. 타임아웃 처리
async def fetch_with_timeout(url: str, timeout: float = 5.0) -> dict | None:
    """타임아웃이 있는 요청."""
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient() as client:
                return await fetch_url(client, url)
    except asyncio.TimeoutError:
        logging.warning(f"타임아웃: {url}")
        return None

# 5. 비동기 큐 (생산자-소비자 패턴)
async def producer(queue: asyncio.Queue, items: list):
    """데이터를 큐에 넣습니다."""
    for item in items:
        await queue.put(item)
    await queue.put(None)  # 종료 신호

async def consumer(queue: asyncio.Queue, worker_id: int):
    """큐에서 데이터를 꺼내 처리합니다."""
    while True:
        item = await queue.get()
        if item is None:
            await queue.put(None)  # 다른 소비자에게 전파
            break
        # 처리
        await process_item(item)
        queue.task_done()

async def run_pipeline(items: list, num_workers: int = 5):
    """생산자-소비자 파이프라인."""
    queue = asyncio.Queue(maxsize=100)
    producer_task = asyncio.create_task(producer(queue, items))
    consumer_tasks = [
        asyncio.create_task(consumer(queue, i))
        for i in range(num_workers)
    ]
    await asyncio.gather(producer_task, *consumer_tasks)

# 6. FastAPI에서의 비동기 활용
from fastapi import FastAPI
app = FastAPI()

@app.get("/dashboard")
async def get_dashboard():
    """여러 서비스에서 동시에 데이터를 가져옵니다."""
    users, orders, stats = await asyncio.gather(
        fetch_users(),
        fetch_orders(),
        fetch_stats(),
    )
    return {"users": users, "orders": orders, "stats": stats}

# 실행
if __name__ == "__main__":
    asyncio.run(fetch_all_users([1, 2, 3, 4, 5]))
```

주의사항:
- `await`는 `async def` 안에서만 사용 가능
- CPU 바운드 작업은 `asyncio`로 빨라지지 않음 → `multiprocessing` 사용
- `asyncio.gather`로 동시 실행, `asyncio.Semaphore`로 동시성 제한
- 동기 라이브러리와 섞으면 블로킹됨 → `httpx` 대신 `requests` 쓰면 안 됨'''),

    # ═══ 타입 힌트 고급 ═══
    m("파이썬 타입 힌트 고급 패턴 알려줘",
'''Python 3.10+ 기준 고급 타입 힌트 패턴입니다.

```python
from typing import (
    TypeVar, Generic, Protocol, TypeAlias,
    Literal, TypeGuard, overload, Self,
    Annotated, TypedDict, Unpack,
)
from dataclasses import dataclass
from collections.abc import Callable, Sequence

# 1. 제네릭
T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

class Repository(Generic[T]):
    """제네릭 리포지토리 패턴."""
    def __init__(self, model_class: type[T]):
        self._model = model_class
        self._items: dict[int, T] = {}

    def get(self, id: int) -> T | None:
        return self._items.get(id)

    def save(self, id: int, item: T) -> T:
        self._items[id] = item
        return item

    def find_all(self) -> list[T]:
        return list(self._items.values())

# 사용
user_repo = Repository(User)     # Repository[User]
post_repo = Repository(Post)     # Repository[Post]

# 2. 프로토콜 (구조적 서브타이핑 / 덕 타이핑)
class Renderable(Protocol):
    """render() 메서드가 있으면 Renderable."""
    def render(self) -> str: ...

class Sizeable(Protocol):
    """__len__이 있으면 Sizeable."""
    def __len__(self) -> int: ...

def render_all(items: Sequence[Renderable]) -> str:
    """Renderable 프로토콜을 구현한 모든 객체 렌더링."""
    return "\\n".join(item.render() for item in items)

# 상속 없이 프로토콜 충족
class Button:
    def render(self) -> str:
        return "<button>Click</button>"

render_all([Button()])  # ✅ OK (Protocol 충족)

# 3. TypedDict
class UserCreate(TypedDict):
    name: str
    email: str
    age: int | None

class UserResponse(TypedDict):
    id: int
    name: str
    email: str
    created_at: str

# 4. Literal 타입
def set_log_level(level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]) -> None:
    ...

# 5. TypeGuard (타입 좁히기)
def is_string_list(val: list[object]) -> TypeGuard[list[str]]:
    return all(isinstance(x, str) for x in val)

def process(data: list[object]):
    if is_string_list(data):
        # 여기서 data는 list[str]로 추론됨
        print(", ".join(data))

# 6. overload (함수 오버로딩)
@overload
def get_item(id: int) -> User: ...
@overload
def get_item(id: str) -> User: ...

def get_item(id: int | str) -> User:
    if isinstance(id, int):
        return db.get_by_id(id)
    return db.get_by_username(id)

# 7. Annotated (메타데이터)
from pydantic import Field
UserId = Annotated[int, Field(gt=0, description="사용자 ID")]
Email = Annotated[str, Field(pattern=r"^[\\w.-]+@[\\w.-]+\\.\\w+$")]

@dataclass
class CreateUser:
    name: Annotated[str, Field(min_length=2, max_length=50)]
    email: Email
    user_id: UserId
```

타입 힌트 핵심:
- `X | None` → `Optional[X]` 대체 (3.10+)
- `list[int]` → `List[int]` 대체 (3.9+)
- Protocol → ABC 대신 구조적 타이핑
- TypeGuard → 커스텀 타입 가드'''),

    # ═══ dataclass & Pydantic ═══
    m("파이썬 dataclass랑 Pydantic 비교해줘",
'''두 가지 모두 데이터 모델링에 사용하지만, 목적이 다릅니다.

```python
# ═══ dataclass: 내부 데이터 구조 ═══
from dataclasses import dataclass, field, asdict
from datetime import datetime

@dataclass
class User:
    """내부에서 사용하는 데이터 클래스."""
    name: str
    email: str
    age: int = 0
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.email})"

# 불변 객체
@dataclass(frozen=True)
class Point:
    x: float
    y: float

# 슬롯 (메모리 절약)
@dataclass(slots=True)
class FastPoint:
    x: float
    y: float

# 비교/정렬 자동
@dataclass(order=True)
class Priority:
    priority: int
    name: str = field(compare=False)  # 비교에서 제외

# ═══ Pydantic: 외부 데이터 검증 ═══
from pydantic import BaseModel, Field, field_validator, model_validator

class UserCreate(BaseModel):
    """API 입력 검증용 모델."""
    name: str = Field(min_length=2, max_length=50)
    email: str = Field(pattern=r"^[\w.-]+@[\w.-]+\.\w+$")
    age: int = Field(ge=0, le=150)
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("이름은 공백만으로 구성할 수 없습니다")
        return v.strip()

    @model_validator(mode="after")
    def check_consistency(self) -> "UserCreate":
        if self.age < 14 and "adult" in self.tags:
            raise ValueError("14세 미만은 adult 태그 불가")
        return self

class UserResponse(BaseModel):
    """API 응답 직렬화 모델."""
    id: int
    name: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}  # ORM 모드

# 사용법 비교
# dataclass: 내부 로직
user = User(name="홍길동", email="hong@test.com", age=25)
user_dict = asdict(user)

# Pydantic: 외부 입력 검증
try:
    user = UserCreate(name="", email="invalid", age=-1)
except ValidationError as e:
    print(e.errors())  # 자세한 에러 목록

# JSON 직렬화
user = UserCreate(name="홍길동", email="hong@test.com", age=25)
json_str = user.model_dump_json()
user2 = UserCreate.model_validate_json(json_str)
```

**선택 기준:**
| 상황 | 선택 |
|------|------|
| 내부 데이터 구조 | `dataclass` |
| API 입출력 검증 | `Pydantic` |
| ORM 모델 변환 | `Pydantic` |
| 설정 파일 로딩 | `Pydantic Settings` |
| 성능 중시 (내부) | `dataclass(slots=True)` |
| JSON 직렬화 | `Pydantic` |'''),

    # ═══ 테스팅 고급 ═══
    m("파이썬 pytest 고급 패턴 알려줘",
'''pytest의 고급 패턴으로 효율적인 테스트를 작성합니다.

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient
from datetime import datetime

# 1. Fixture 계층화
@pytest.fixture(scope="session")
def db_engine():
    """세션 전체에서 1번만 생성."""
    engine = create_engine("sqlite:///test.db")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture(scope="function")
def db_session(db_engine):
    """각 테스트마다 새 세션 + 롤백."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def sample_user(db_session) -> User:
    """테스트용 사용자."""
    user = User(name="테스트", email="test@example.com")
    db_session.add(user)
    db_session.flush()
    return user

# 2. 파라미터화 테스트
@pytest.mark.parametrize("input_val,expected", [
    ("hello@test.com", True),
    ("invalid-email", False),
    ("user@domain.co.kr", True),
    ("", False),
    ("user@.com", False),
])
def test_validate_email(input_val: str, expected: bool):
    assert validate_email(input_val) == expected

# 3. 비동기 테스트
@pytest.mark.asyncio
async def test_fetch_user():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/users/1")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "테스트"

# 4. Mock 활용
@pytest.mark.asyncio
async def test_send_notification():
    with patch("app.services.email.send_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"status": "sent"}

        result = await notify_user(user_id=1, message="안녕하세요")

        mock_send.assert_called_once_with(
            to="test@example.com",
            subject="알림",
            body="안녕하세요",
        )
        assert result["status"] == "sent"

# 5. 예외 테스트
def test_divide_by_zero():
    with pytest.raises(ZeroDivisionError, match="division by zero"):
        divide(10, 0)

def test_invalid_user():
    with pytest.raises(ValueError) as exc_info:
        create_user(name="", email="invalid")
    assert "이름" in str(exc_info.value)

# 6. 시간 고정 (freezegun)
from freezegun import freeze_time

@freeze_time("2025-01-15 10:00:00")
def test_subscription_expiry():
    sub = create_subscription(days=30)
    assert sub.expires_at == datetime(2025, 2, 14, 10, 0, 0)

# 7. conftest.py 활용
# conftest.py
@pytest.fixture(autouse=True)
def reset_cache():
    """모든 테스트 전에 캐시 초기화."""
    cache.clear()
    yield
    cache.clear()

# 8. 커스텀 마커
# pytest.ini: markers = slow: 느린 테스트

@pytest.mark.slow
def test_heavy_computation():
    result = compute_large_dataset()
    assert result.accuracy > 0.95

# 실행: pytest -m "not slow"  (느린 테스트 제외)
```

pytest 실무 팁:
- `conftest.py` 계층 활용 (프로젝트/앱/테스트 디렉토리별)
- `scope="session"` → DB 연결 등 무거운 리소스
- `autouse=True` → 모든 테스트에 자동 적용
- `-x` 옵션: 첫 실패에서 중단
- `--tb=short` 옵션: 짧은 트레이스백'''),

    # ═══ 에러 처리 패턴 ═══
    m("파이썬 에러 처리 실무 패턴 알려줘",
'''실무에서 쓰는 체계적인 에러 처리 패턴입니다.

```python
from __future__ import annotations
import logging
import traceback
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar, Generic

logger = logging.getLogger(__name__)
T = TypeVar("T")

# 1. 커스텀 예외 계층
class AppError(Exception):
    """애플리케이션 기본 예외."""
    def __init__(self, message: str, code: str = "UNKNOWN"):
        super().__init__(message)
        self.code = code

class NotFoundError(AppError):
    def __init__(self, resource: str, id: int | str):
        super().__init__(f"{resource} #{id}을(를) 찾을 수 없습니다", "NOT_FOUND")

class ValidationError(AppError):
    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}", "VALIDATION_ERROR")
        self.field = field

class AuthenticationError(AppError):
    def __init__(self, message: str = "인증이 필요합니다"):
        super().__init__(message, "UNAUTHORIZED")

class PermissionError(AppError):
    def __init__(self, action: str):
        super().__init__(f"권한 부족: {action}", "FORBIDDEN")

# 2. Result 패턴 (예외 대신 반환값)
@dataclass
class Result(Generic[T]):
    """성공/실패를 명시적으로 반환합니다."""
    success: bool
    data: T | None = None
    error: str | None = None
    code: str | None = None

    @classmethod
    def ok(cls, data: T) -> Result[T]:
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, code: str = "ERROR") -> Result[T]:
        return cls(success=False, error=error, code=code)

# 사용법
def create_user(name: str, email: str) -> Result[User]:
    if not name:
        return Result.fail("이름은 필수입니다", "VALIDATION")
    if User.exists(email=email):
        return Result.fail("이미 가입된 이메일입니다", "DUPLICATE")
    user = User.create(name=name, email=email)
    return Result.ok(user)

# 3. FastAPI 글로벌 에러 핸들러
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    status_map = {
        "NOT_FOUND": 404,
        "VALIDATION_ERROR": 422,
        "UNAUTHORIZED": 401,
        "FORBIDDEN": 403,
    }
    return JSONResponse(
        status_code=status_map.get(exc.code, 500),
        content={
            "error": {"code": exc.code, "message": str(exc)},
        },
    )

@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error(f"처리되지 않은 에러: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL", "message": "서버 오류가 발생했습니다"}},
    )

# 4. 서비스 레이어에서 사용
async def get_user(user_id: int) -> User:
    user = await user_repo.find_by_id(user_id)
    if not user:
        raise NotFoundError("사용자", user_id)
    return user

async def update_user(user_id: int, data: dict, requester: User) -> User:
    user = await get_user(user_id)
    if user.id != requester.id and requester.role != "admin":
        raise PermissionError("다른 사용자 정보 수정")
    return await user_repo.update(user, data)
```

에러 처리 원칙:
- 비즈니스 로직 → 커스텀 예외 (NotFoundError 등)
- 외부 연동 → try/except + 로깅 + 래핑
- API 경계 → 글로벌 핸들러로 일관된 응답 형식
- 내부 함수 → 예외를 잡지 말고 위로 전파'''),

    # ═══ 멀티프로세싱 ═══
    m("파이썬 멀티프로세싱 실무 활용법 알려줘",
'''CPU 바운드 작업에는 멀티프로세싱을 사용합니다 (GIL 우회).

```python
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
import os

# 1. ProcessPoolExecutor (가장 간단)
def process_image(path: str, resize_to: tuple[int, int]) -> str:
    """이미지를 리사이즈합니다 (CPU 바운드)."""
    from PIL import Image
    img = Image.open(path)
    img = img.resize(resize_to)
    output = path.replace(".jpg", "_thumb.jpg")
    img.save(output)
    return output

def batch_resize(image_paths: list[str]) -> list[str]:
    """여러 이미지를 병렬로 리사이즈합니다."""
    resize_fn = partial(process_image, resize_to=(256, 256))
    results = []

    # CPU 코어 수만큼 워커 사용
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = {
            executor.submit(resize_fn, path): path
            for path in image_paths
        }

        for future in as_completed(futures):
            path = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"실패: {path} - {e}")

    return results

# 2. Pool.map (순서 보장)
def compute_hash(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()

def parallel_hash(data_list: list[bytes]) -> list[str]:
    with mp.Pool(processes=4) as pool:
        return pool.map(compute_hash, data_list)

# 3. 공유 상태 (Manager)
def worker(counter, lock, task_id: int):
    """공유 카운터를 안전하게 증가."""
    # 무거운 작업
    result = heavy_computation(task_id)
    with lock:
        counter.value += 1

def parallel_with_shared_state(tasks: list[int]):
    manager = mp.Manager()
    counter = manager.Value("i", 0)
    lock = manager.Lock()

    with mp.Pool(4) as pool:
        pool.starmap(worker, [(counter, lock, t) for t in tasks])

    print(f"완료: {counter.value}건")

# 4. 대용량 데이터 처리 (청크 분할)
def process_chunk(chunk: list[dict]) -> list[dict]:
    """데이터 청크를 처리합니다."""
    return [transform(item) for item in chunk]

def parallel_data_processing(data: list[dict], chunk_size: int = 1000):
    """대용량 데이터를 청크로 나눠 병렬 처리."""
    chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]

    with ProcessPoolExecutor() as executor:
        results = list(executor.map(process_chunk, chunks))

    # 평탄화
    return [item for chunk in results for item in chunk]
```

asyncio vs multiprocessing:
| 작업 유형 | 선택 |
|-----------|------|
| 네트워크 I/O (API 호출) | `asyncio` |
| 파일 I/O | `asyncio` 또는 `threading` |
| 이미지/영상 처리 | `multiprocessing` |
| 데이터 연산 | `multiprocessing` |
| 머신러닝 학습 | `multiprocessing` + GPU |'''),

    # ═══ 로깅 실무 ═══
    m("파이썬 로깅 실무 설정 알려줘",
'''프로덕션 환경의 로깅 설정입니다.

```python
import logging
import logging.config
import json
import sys
from datetime import datetime
from pathlib import Path

# 1. 구조화된 JSON 로거
class JSONFormatter(logging.Formatter):
    """JSON 형태로 로그를 출력합니다 (ELK 스택 연동)."""
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        # 추가 컨텍스트
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)

# 2. 딕셔너리 기반 설정
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        },
        "json": {
            "()": "app.logging.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "json",
            "filename": "logs/app.log",
            "maxBytes": 10_485_760,  # 10MB
            "backupCount": 5,
            "encoding": "utf-8",
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": "json",
            "filename": "logs/error.log",
            "maxBytes": 10_485_760,
            "backupCount": 10,
        },
    },
    "loggers": {
        "app": {"level": "DEBUG", "handlers": ["console", "file"], "propagate": False},
        "app.api": {"level": "INFO", "handlers": ["console", "file"]},
        "uvicorn": {"level": "INFO", "handlers": ["console"]},
    },
    "root": {
        "level": "WARNING",
        "handlers": ["console", "error_file"],
    },
}

# 적용
logging.config.dictConfig(LOGGING_CONFIG)

# 3. 컨텍스트가 있는 로깅
logger = logging.getLogger("app.api")

def log_with_context(logger, level, message, **kwargs):
    """추가 컨텍스트와 함께 로깅."""
    extra = {k: v for k, v in kwargs.items()}
    logger.log(level, message, extra=extra)

# FastAPI 미들웨어로 요청 로깅
import uuid

@app.middleware("http")
async def request_logging(request, call_next):
    request_id = str(uuid.uuid4())[:8]
    logger.info(
        f"요청 시작: {request.method} {request.url.path}",
        extra={"request_id": request_id},
    )
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    logger.info(
        f"요청 완료: {response.status_code} ({elapsed:.3f}s)",
        extra={"request_id": request_id, "duration": elapsed},
    )
    return response
```

로깅 원칙:
- DEBUG: 개발 중 디버깅용
- INFO: 정상 동작 기록 (요청, 처리 결과)
- WARNING: 잠재적 문제 (재시도, 폴백)
- ERROR: 실제 오류 (예외 발생)
- CRITICAL: 시스템 중단 수준 (DB 연결 불가)'''),

    # ═══ 환경변수 & 설정 관리 ═══
    m("파이썬 환경변수 설정 관리 베스트 프랙티스 알려줘",
'''Pydantic Settings로 타입 안전한 설정을 관리합니다.

```python
from pydantic_settings import BaseSettings
from pydantic import Field, SecretStr
from functools import lru_cache
from pathlib import Path

class DatabaseSettings(BaseSettings):
    host: str = "localhost"
    port: int = 5432
    name: str = "myapp"
    user: str = "postgres"
    password: SecretStr = Field(default=SecretStr(""))  # 로그에 노출 안 됨
    pool_size: int = 10
    pool_overflow: int = 20

    @property
    def url(self) -> str:
        pwd = self.password.get_secret_value()
        return f"postgresql+asyncpg://{self.user}:{pwd}@{self.host}:{self.port}/{self.name}"

    model_config = {"env_prefix": "DB_"}  # DB_HOST, DB_PORT 등

class RedisSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: SecretStr | None = None

    @property
    def url(self) -> str:
        if self.password:
            return f"redis://:{self.password.get_secret_value()}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"

    model_config = {"env_prefix": "REDIS_"}

class Settings(BaseSettings):
    # 앱 기본
    app_name: str = "화랑 API"
    debug: bool = False
    environment: str = "development"  # development, staging, production

    # 보안
    secret_key: SecretStr = Field(default=SecretStr("change-me"))
    api_key: SecretStr | None = None
    cors_origins: list[str] = ["http://localhost:3000"]

    # 외부 서비스
    openai_api_key: SecretStr | None = None

    # 하위 설정
    db: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_nested_delimiter": "__",  # DB__HOST=localhost
    }

# 싱글톤 패턴
@lru_cache
def get_settings() -> Settings:
    return Settings()

# 사용법
settings = get_settings()
print(settings.app_name)          # "화랑 API"
print(settings.db.url)            # DB URL
print(settings.secret_key)        # SecretStr('**********') ← 마스킹됨
```

`.env` 파일:
```
# .env
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=super-secret-key-here
DB_HOST=db.example.com
DB_PASSWORD=secure-password
REDIS_HOST=redis.example.com
OPENAI_API_KEY=sk-xxxxx
```

`.env.example` (커밋용):
```
ENVIRONMENT=development
DEBUG=true
SECRET_KEY=change-me-in-production
DB_HOST=localhost
DB_PASSWORD=
```

핵심:
- `.env` 파일은 절대 git에 커밋하지 않음 (`.gitignore`에 추가)
- `SecretStr`로 비밀값 보호 (로그/repr에 마스킹)
- `@lru_cache`로 설정 객체 재사용
- 환경별로 `.env.development`, `.env.production` 분리'''),

    # ═══ 파일/경로 처리 ═══
    m("파이썬 파일 처리 실무 패턴 알려줘",
'''pathlib과 실무 파일 처리 패턴입니다.

```python
from pathlib import Path
import shutil
import tempfile
import hashlib
import mimetypes

# 1. pathlib 기본 (os.path 대체)
base = Path(__file__).parent  # 현재 파일 기준
project_root = Path(__file__).parent.parent
data_dir = project_root / "data"
config_file = project_root / "config" / "settings.yaml"

# 디렉토리 생성 (중첩 OK, 이미 있어도 OK)
data_dir.mkdir(parents=True, exist_ok=True)

# 파일 목록
py_files = list(project_root.rglob("*.py"))       # 재귀 검색
json_files = list(data_dir.glob("**/*.json"))      # 하위 포함

# 파일 정보
if config_file.exists():
    size = config_file.stat().st_size
    modified = config_file.stat().st_mtime

# 2. 안전한 파일 쓰기 (원자적 쓰기)
def safe_write(path: Path, content: str) -> None:
    """원자적 파일 쓰기 (중간에 실패해도 원본 보존)."""
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)  # 원자적 이동
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

# 3. 임시 파일/디렉토리
def process_upload(data: bytes) -> Path:
    """업로드된 파일을 임시 디렉토리에서 처리."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "upload.bin"
        tmp_path.write_bytes(data)

        # 처리
        result = transform_file(tmp_path)

        # 최종 위치로 이동
        final_path = Path("uploads") / f"{hashlib.md5(data).hexdigest()}.bin"
        shutil.move(str(result), str(final_path))
        return final_path
    # tmp_dir은 자동 삭제됨

# 4. 파일 해시 (대용량 지원)
def file_hash(path: Path, algorithm: str = "sha256") -> str:
    """대용량 파일의 해시를 계산합니다."""
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

# 5. MIME 타입 감지
def get_content_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type or "application/octet-stream"

# 6. 디렉토리 복사/정리
def backup_directory(src: Path, backup_dir: Path) -> Path:
    """디렉토리를 날짜별로 백업합니다."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"backup_{timestamp}"
    shutil.copytree(src, dest)
    return dest

def cleanup_old_backups(backup_dir: Path, keep: int = 5):
    """오래된 백업을 정리합니다."""
    backups = sorted(backup_dir.iterdir(), key=lambda p: p.stat().st_mtime)
    for old in backups[:-keep]:
        shutil.rmtree(old)
```

핵심:
- `os.path` 대신 `pathlib.Path` 사용
- `/` 연산자로 경로 조합: `base / "data" / "file.json"`
- `rglob` → 재귀 검색, `glob` → 현재 디렉토리
- 원자적 쓰기 → 데이터 손실 방지'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/advanced_python.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI Python 고급 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  Python 고급: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
