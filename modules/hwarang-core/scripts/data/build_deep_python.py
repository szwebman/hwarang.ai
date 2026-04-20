"""화랑 AI Python 심화 학습 데이터

메모리 관리, GIL, 메타클래스, 디스크립터, 성능최적화, 디버깅 등.

사용법:
    python scripts/data/build_deep_python.py --output data/sft/deep_python.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
파이썬 전문가 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("파이썬 GIL이 뭐야? 멀티스레딩이 왜 느려?",
'''GIL(Global Interpreter Lock)은 CPython에서 한 번에 하나의 스레드만 파이썬 바이트코드를 실행하게 하는 뮤텍스입니다.

```python
import threading
import time
import multiprocessing

# ═══ GIL의 영향 확인 ═══

# CPU 바운드 작업
def cpu_heavy(n):
    total = 0
    for i in range(n):
        total += i * i
    return total

# 1. 싱글 스레드
start = time.time()
cpu_heavy(10_000_000)
cpu_heavy(10_000_000)
print(f"싱글: {time.time() - start:.2f}초")  # ~2.5초

# 2. 멀티 스레드 (GIL 때문에 더 느릴 수 있음!)
start = time.time()
t1 = threading.Thread(target=cpu_heavy, args=(10_000_000,))
t2 = threading.Thread(target=cpu_heavy, args=(10_000_000,))
t1.start(); t2.start()
t1.join(); t2.join()
print(f"멀티스레드: {time.time() - start:.2f}초")  # ~2.8초 (오히려 느림!)

# 3. 멀티 프로세스 (GIL 우회 → 진짜 병렬)
start = time.time()
with multiprocessing.Pool(2) as pool:
    pool.map(cpu_heavy, [10_000_000, 10_000_000])
print(f"멀티프로세스: {time.time() - start:.2f}초")  # ~1.5초 (2배 빠름)

# ═══ GIL이 해제되는 경우 ═══
# I/O 작업 중에는 GIL이 해제됨 → 멀티스레딩 효과 있음

import requests

def fetch(url):
    return requests.get(url).status_code

# I/O 바운드 → 멀티스레딩 효과적
urls = ["https://example.com"] * 10

# 순차: ~5초
start = time.time()
for url in urls:
    fetch(url)
print(f"순차: {time.time() - start:.2f}초")

# 스레드: ~0.5초 (10배 빠름!)
from concurrent.futures import ThreadPoolExecutor
start = time.time()
with ThreadPoolExecutor(max_workers=10) as executor:
    list(executor.map(fetch, urls))
print(f"스레드: {time.time() - start:.2f}초")

# ═══ GIL 우회 전략 ═══

# 1. multiprocessing (CPU 바운드)
from concurrent.futures import ProcessPoolExecutor
with ProcessPoolExecutor() as executor:
    results = list(executor.map(cpu_heavy, data_chunks))

# 2. C 확장 (numpy, pandas는 GIL 해제)
import numpy as np
# numpy 연산은 내부적으로 GIL 해제 → 멀티코어 활용
arr = np.random.rand(10_000_000)
result = np.sum(arr ** 2)  # C 레벨에서 병렬 처리

# 3. asyncio (I/O 바운드)
import asyncio
import httpx

async def fetch_all(urls):
    async with httpx.AsyncClient() as client:
        tasks = [client.get(url) for url in urls]
        return await asyncio.gather(*tasks)

# 4. Python 3.13+ (Free-threaded Python / PEP 703)
# python3.13t (실험적) → GIL 비활성화 빌드
# 아직 실험 단계, 2026~2027 안정화 예정
```

GIL 요약:
| 작업 유형 | 해결책 | 이유 |
|-----------|--------|------|
| CPU 바운드 | `multiprocessing` | GIL 우회 (별도 프로세스) |
| I/O 바운드 | `threading` / `asyncio` | I/O 중 GIL 해제 |
| 숫자 연산 | `numpy` / `pandas` | C 레벨에서 GIL 해제 |
| 극한 성능 | Rust/C 확장 | GIL과 무관 |

핵심: **CPU 바운드 → 프로세스**, **I/O 바운드 → 스레드/async**'''),

    m("파이썬 메모리 관리 원리랑 메모리 누수 잡는 방법 알려줘",
'''CPython의 메모리 관리 원리와 메모리 누수 디버깅 방법입니다.

```python
import sys
import gc
import tracemalloc
import weakref
from memory_profiler import profile

# ═══ 1. 레퍼런스 카운팅 ═══
a = [1, 2, 3]
print(sys.getrefcount(a))  # 2 (a + getrefcount 인자)

b = a          # refcount: 3
c = a          # refcount: 4
del b          # refcount: 3
c = None       # refcount: 2

# refcount가 0이 되면 즉시 해제

# ═══ 2. 순환 참조 문제 ═══
class Node:
    def __init__(self, name):
        self.name = name
        self.parent = None
        self.children = []

    def add_child(self, child):
        self.children.append(child)
        child.parent = self  # 순환 참조!

# 순환 참조 → refcount가 0이 안 됨 → GC가 처리
parent = Node("부모")
child = Node("자식")
parent.add_child(child)
# parent → child, child → parent (순환!)

# 해결: weakref 사용
class SafeNode:
    def __init__(self, name):
        self.name = name
        self._parent = None  # weakref
        self.children = []

    @property
    def parent(self):
        return self._parent() if self._parent else None

    @parent.setter
    def parent(self, value):
        self._parent = weakref.ref(value) if value else None

    def add_child(self, child):
        self.children.append(child)
        child.parent = self  # weakref → 순환 참조 없음

# ═══ 3. 메모리 프로파일링 ═══

# tracemalloc (표준 라이브러리)
tracemalloc.start()

# 메모리 사용하는 코드
data = [list(range(10000)) for _ in range(100)]

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics("lineno")

print("메모리 사용 Top 10:")
for stat in top_stats[:10]:
    print(f"  {stat}")

# 두 시점 비교 (누수 탐지)
snapshot1 = tracemalloc.take_snapshot()
# ... 작업 수행 ...
snapshot2 = tracemalloc.take_snapshot()

diff = snapshot2.compare_to(snapshot1, "lineno")
print("\\n메모리 증가 Top 10:")
for stat in diff[:10]:
    print(f"  {stat}")

# ═══ 4. memory_profiler (라인별 분석) ═══
# pip install memory_profiler

@profile  # 데코레이터로 라인별 메모리 확인
def process_data():
    data = []                    # Mem: +0 MB
    for i in range(100000):
        data.append(i * i)       # Mem: +3.8 MB
    filtered = [x for x in data if x % 2 == 0]  # Mem: +1.9 MB
    del data                     # Mem: -3.8 MB
    return filtered

# 실행: python -m memory_profiler script.py

# ═══ 5. 흔한 메모리 누수 패턴 ═══

# ❌ 1. 무한 성장 캐시
cache = {}
def bad_cache(key, value):
    cache[key] = value  # 계속 증가!

# ✅ 해결: LRU 캐시 또는 TTL
from functools import lru_cache

@lru_cache(maxsize=1000)
def good_cache(key):
    return expensive_compute(key)

# ❌ 2. 이벤트 리스너 해제 안 함
class EventEmitter:
    _listeners = []  # 클래스 변수 → 모든 인스턴스 공유!

    def on(self, handler):
        self._listeners.append(handler)  # 해제 안 하면 누수

# ✅ 해결: weakref 또는 명시적 해제
class SafeEmitter:
    def __init__(self):
        self._listeners = []  # 인스턴스 변수

    def on(self, handler):
        self._listeners.append(weakref.ref(handler))

    def emit(self, *args):
        self._listeners = [ref for ref in self._listeners if ref() is not None]
        for ref in self._listeners:
            if ref():
                ref()(*args)

# ❌ 3. 대용량 데이터를 리스트로 보관
all_data = list(read_huge_file())  # 전체를 메모리에!

# ✅ 해결: 제너레이터
def read_huge_file():
    with open("huge.csv") as f:
        for line in f:
            yield process(line)  # 한 줄씩 처리

# ═══ 6. GC 수동 제어 ═══
gc.collect()                    # 수동 GC
gc.get_count()                  # (gen0, gen1, gen2) 카운트
gc.set_threshold(700, 10, 10)   # GC 빈도 조정

# 디버깅: 순환 참조 찾기
gc.set_debug(gc.DEBUG_SAVEALL)
gc.collect()
print(f"순환 참조 객체: {len(gc.garbage)}개")
for obj in gc.garbage[:5]:
    print(f"  {type(obj)}: {obj}")
```

메모리 관리 핵심:
1. **레퍼런스 카운팅**: 기본, 즉시 해제
2. **GC (세대별)**: 순환 참조 처리
3. **프로파일링**: `tracemalloc` → 전체, `memory_profiler` → 라인별
4. **누수 방지**: LRU 캐시, weakref, 제너레이터 활용
5. **`__slots__`**: 인스턴스 메모리 40% 절약'''),

    m("파이썬 메타클래스 실무에서 어떻게 쓰여?",
'''메타클래스는 "클래스를 만드는 클래스"입니다. 프레임워크에서 자주 씁니다.

```python
# ═══ 메타클래스 기초 ═══
# 모든 클래스는 type의 인스턴스
print(type(int))       # <class 'type'>
print(type(str))       # <class 'type'>

class MyClass:
    pass

print(type(MyClass))   # <class 'type'>
# MyClass = type("MyClass", (), {})  와 동일

# ═══ 1. 싱글톤 메타클래스 ═══
class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class Database(metaclass=SingletonMeta):
    def __init__(self, url="localhost"):
        self.url = url
        self.connected = True

db1 = Database("postgresql://localhost")
db2 = Database("다른 URL")
print(db1 is db2)  # True (같은 인스턴스)

# ═══ 2. 자동 등록 메타클래스 (플러그인 시스템) ═══
class PluginRegistry(type):
    plugins: dict[str, type] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 등록 로직은 __init__에서 처리

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        if bases:  # 베이스 클래스(Plugin) 자체는 제외
            PluginRegistry.plugins[name.lower()] = cls
        return cls

class Plugin(metaclass=PluginRegistry):
    def execute(self):
        raise NotImplementedError

class EmailPlugin(Plugin):
    def execute(self):
        return "이메일 발송"

class SlackPlugin(Plugin):
    def execute(self):
        return "슬랙 메시지"

# 자동 등록됨!
print(PluginRegistry.plugins)
# {'emailplugin': <class 'EmailPlugin'>, 'slackplugin': <class 'SlackPlugin'>}

# 이름으로 플러그인 생성
def create_plugin(name: str) -> Plugin:
    cls = PluginRegistry.plugins.get(name.lower())
    if not cls:
        raise ValueError(f"플러그인 없음: {name}")
    return cls()

plugin = create_plugin("email")
plugin.execute()  # "이메일 발송"

# ═══ 3. 필드 검증 메타클래스 (ORM 스타일) ═══
class Field:
    def __init__(self, field_type, required=False, default=None):
        self.field_type = field_type
        self.required = required
        self.default = default

class ModelMeta(type):
    def __new__(mcs, name, bases, namespace):
        fields = {}
        for key, value in namespace.items():
            if isinstance(value, Field):
                fields[key] = value

        namespace["_fields"] = fields
        cls = super().__new__(mcs, name, bases, namespace)
        return cls

class Model(metaclass=ModelMeta):
    def __init__(self, **kwargs):
        for name, field in self._fields.items():
            value = kwargs.get(name, field.default)
            if field.required and value is None:
                raise ValueError(f"{name}은(는) 필수입니다")
            if value is not None and not isinstance(value, field.field_type):
                raise TypeError(f"{name}: {field.field_type.__name__} 타입이어야 합니다")
            setattr(self, name, value)

    def to_dict(self):
        return {name: getattr(self, name) for name in self._fields}

# 사용 (Django/SQLAlchemy 느낌)
class User(Model):
    name = Field(str, required=True)
    email = Field(str, required=True)
    age = Field(int, default=0)
    role = Field(str, default="user")

user = User(name="홍길동", email="hong@test.com", age=28)
print(user.to_dict())
# {'name': '홍길동', 'email': 'hong@test.com', 'age': 28, 'role': 'user'}

# User(name="홍길동", email=123)  → TypeError!
# User(email="hong@test.com")    → ValueError! (name 필수)

# ═══ 4. 실무에서 더 좋은 대안 ═══
# 메타클래스 대신 __init_subclass__ (Python 3.6+)

class Plugin:
    _registry: dict[str, type] = {}

    def __init_subclass__(cls, name: str = None, **kwargs):
        super().__init_subclass__(**kwargs)
        plugin_name = name or cls.__name__.lower()
        Plugin._registry[plugin_name] = cls

    @classmethod
    def create(cls, name: str):
        return cls._registry[name]()

class EmailPlugin(Plugin, name="email"):
    def run(self): return "이메일"

class SlackPlugin(Plugin, name="slack"):
    def run(self): return "슬랙"

plugin = Plugin.create("email")

# 또는 데코레이터로 더 간단하게
registry = {}

def register(name):
    def decorator(cls):
        registry[name] = cls
        return cls
    return decorator

@register("email")
class EmailHandler:
    def handle(self): return "이메일 처리"
```

메타클래스 사용 기준:
| 상황 | 권장 방법 |
|------|-----------|
| 간단한 등록 | `__init_subclass__` 또는 데코레이터 |
| ORM 필드 정의 | 메타클래스 또는 디스크립터 |
| 싱글톤 | `__new__` 오버라이드 또는 모듈 레벨 |
| API 검증 | Pydantic (메타클래스 내부 사용) |
| 프레임워크 개발 | 메타클래스 (Django, SQLAlchemy 내부) |

실무 원칙: **메타클래스는 최후의 수단**. `__init_subclass__`, 데코레이터, 디스크립터로 충분하면 그쪽을 사용.'''),

    m("파이썬 디스크립터 프로토콜 알려줘 property 내부 원리",
'''디스크립터는 `property`, `classmethod`, `staticmethod`의 내부 원리입니다.

```python
# ═══ 디스크립터 프로토콜 ═══
# __get__, __set__, __delete__ 중 하나라도 구현하면 디스크립터

# 1. 데이터 디스크립터 (__get__ + __set__)
class TypedField:
    """타입을 검증하는 디스크립터."""

    def __init__(self, name: str, field_type: type, default=None):
        self.name = name
        self.field_type = field_type
        self.default = default

    def __set_name__(self, owner, name):
        """클래스에 할당될 때 호출 (Python 3.6+)."""
        self.name = name
        self.storage_name = f"_desc_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self  # 클래스에서 접근 시 디스크립터 자체 반환
        return getattr(obj, self.storage_name, self.default)

    def __set__(self, obj, value):
        if not isinstance(value, self.field_type):
            raise TypeError(
                f"{self.name}: {self.field_type.__name__} 타입이어야 합니다, "
                f"받은 값: {type(value).__name__}"
            )
        setattr(obj, self.storage_name, value)

    def __delete__(self, obj):
        delattr(obj, self.storage_name)

class User:
    name = TypedField("name", str)
    age = TypedField("age", int, default=0)
    email = TypedField("email", str)

user = User()
user.name = "홍길동"      # ✅ OK
user.age = 28              # ✅ OK
# user.age = "스물여덟"   # ❌ TypeError!

# 2. property의 실제 구현 (디스크립터)
class Property:
    """property 빌트인의 순수 파이썬 구현."""

    def __init__(self, fget=None, fset=None, fdel=None, doc=None):
        self.fget = fget
        self.fset = fset
        self.fdel = fdel
        self.__doc__ = doc or (fget.__doc__ if fget else None)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self.fget is None:
            raise AttributeError("읽기 불가")
        return self.fget(obj)

    def __set__(self, obj, value):
        if self.fset is None:
            raise AttributeError("쓰기 불가")
        self.fset(obj, value)

    def __delete__(self, obj):
        if self.fdel is None:
            raise AttributeError("삭제 불가")
        self.fdel(obj)

    def getter(self, fget):
        return type(self)(fget, self.fset, self.fdel, self.__doc__)

    def setter(self, fset):
        return type(self)(self.fget, fset, self.fdel, self.__doc__)

    def deleter(self, fdel):
        return type(self)(self.fget, self.fset, fdel, self.__doc__)

# 3. 범위 검증 디스크립터
class RangeField:
    def __init__(self, min_val=None, max_val=None):
        self.min_val = min_val
        self.max_val = max_val

    def __set_name__(self, owner, name):
        self.name = name
        self.storage = f"_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None: return self
        return getattr(obj, self.storage, None)

    def __set__(self, obj, value):
        if self.min_val is not None and value < self.min_val:
            raise ValueError(f"{self.name}: 최솟값 {self.min_val}")
        if self.max_val is not None and value > self.max_val:
            raise ValueError(f"{self.name}: 최댓값 {self.max_val}")
        setattr(obj, self.storage, value)

class Product:
    price = RangeField(min_val=0)
    quantity = RangeField(min_val=0, max_val=10000)
    discount = RangeField(min_val=0, max_val=100)

product = Product()
product.price = 10000      # ✅
product.discount = 50      # ✅
# product.price = -100     # ❌ ValueError!
# product.discount = 150   # ❌ ValueError!

# 4. 캐싱 디스크립터 (cached_property 구현)
class CachedProperty:
    """한 번 계산하면 캐시하는 디스크립터."""

    def __init__(self, func):
        self.func = func
        self.attrname = None
        self.__doc__ = func.__doc__

    def __set_name__(self, owner, name):
        self.attrname = name

    def __get__(self, obj, objtype=None):
        if obj is None: return self
        # 인스턴스 __dict__에 직접 저장 → 다음 접근은 디스크립터 안 거침
        value = self.func(obj)
        obj.__dict__[self.attrname] = value
        return value

class DataAnalysis:
    def __init__(self, data):
        self.data = data

    @CachedProperty
    def statistics(self):
        """무거운 계산 (한 번만 실행됨)."""
        print("통계 계산 중...")
        return {
            "mean": sum(self.data) / len(self.data),
            "max": max(self.data),
            "min": min(self.data),
        }

analysis = DataAnalysis([1, 2, 3, 4, 5])
print(analysis.statistics)  # "통계 계산 중..." 출력
print(analysis.statistics)  # 캐시 반환 (출력 없음)
```

디스크립터 우선순위:
1. **데이터 디스크립터** (`__get__` + `__set__`) → 인스턴스 `__dict__`보다 우선
2. **인스턴스 `__dict__`**
3. **비데이터 디스크립터** (`__get__`만) → `__dict__`보다 후순위

이것이 `property`가 인스턴스 변수보다 우선하는 이유이고, `cached_property`가 `__dict__`에 직접 저장해서 자신을 가리는 트릭을 쓰는 이유입니다.'''),

    m("파이썬 성능 최적화 실무 기법 알려줘 프로파일링 포함",
'''파이썬 성능 최적화와 프로파일링 실무 기법입니다.

```python
import time
import cProfile
import pstats
from functools import lru_cache
from collections import defaultdict

# ═══ 1. 프로파일링 ═══

# cProfile (함수 단위)
def profile_function():
    profiler = cProfile.Profile()
    profiler.enable()

    # 대상 코드
    result = heavy_computation()

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    stats.print_stats(20)  # 상위 20개

# 명령줄: python -m cProfile -o output.prof script.py
# 시각화: pip install snakeviz && snakeviz output.prof

# line_profiler (라인 단위 - 가장 정밀)
# pip install line_profiler
# kernprof -l -v script.py

@profile  # line_profiler 데코레이터
def process_data(items):
    result = []                          # Time: 0.0%
    for item in items:                   # Time: 1.2%
        if item.is_valid():              # Time: 15.3%  ← 병목!
            processed = transform(item)  # Time: 45.2%  ← 최대 병목!
            result.append(processed)     # Time: 2.1%
    return sorted(result)                # Time: 36.2%  ← 정렬도 느림

# ═══ 2. 자료구조 최적화 ═══

# ❌ 리스트에서 검색 O(n)
if item in large_list:  # 느림!
    pass

# ✅ set으로 검색 O(1)
large_set = set(large_list)
if item in large_set:  # 빠름!
    pass

# ❌ 딕셔너리 키 존재 확인 후 접근
if key in dictionary:
    value = dictionary[key]
else:
    value = default

# ✅ get() 또는 defaultdict
value = dictionary.get(key, default)

counts = defaultdict(int)
for item in items:
    counts[item] += 1  # KeyError 없음

# ═══ 3. 루프 최적화 ═══

# ❌ 느린 루프
result = []
for i in range(1000000):
    if i % 2 == 0:
        result.append(i * i)

# ✅ 리스트 컴프리헨션 (30-50% 빠름)
result = [i * i for i in range(1000000) if i % 2 == 0]

# ✅ 제너레이터 (메모리 절약)
result = sum(i * i for i in range(1000000) if i % 2 == 0)

# ❌ 반복된 속성 접근
for item in items:
    item.name.upper().strip()  # 매번 . 접근

# ✅ 로컬 변수에 바인딩
upper = str.upper
strip = str.strip
for item in items:
    strip(upper(item.name))

# ═══ 4. 문자열 최적화 ═══

# ❌ 문자열 연결 (O(n²))
result = ""
for s in strings:
    result += s  # 매번 새 문자열 생성!

# ✅ join (O(n))
result = "".join(strings)

# ✅ f-string (가장 빠른 포맷팅)
name = "홍길동"
msg = f"안녕하세요, {name}님"  # format()보다 빠름

# ═══ 5. I/O 최적화 ═══

# ❌ 한 줄씩 쓰기
for line in lines:
    f.write(line + "\\n")

# ✅ 한 번에 쓰기
f.write("\\n".join(lines))
# 또는
f.writelines(line + "\\n" for line in lines)

# 버퍼 크기 조정
with open("file", "r", buffering=8192*4) as f:  # 32KB 버퍼
    for line in f:
        process(line)

# ═══ 6. 캐싱 ═══

# functools.lru_cache
@lru_cache(maxsize=1024)
def fibonacci(n):
    if n < 2: return n
    return fibonacci(n-1) + fibonacci(n-2)

# 수동 캐시 (TTL 포함)
import time

class TTLCache:
    def __init__(self, ttl=300):
        self.ttl = ttl
        self.cache = {}

    def get(self, key):
        if key in self.cache:
            value, expiry = self.cache[key]
            if time.time() < expiry:
                return value
            del self.cache[key]
        return None

    def set(self, key, value):
        self.cache[key] = (value, time.time() + self.ttl)

# ═══ 7. __slots__ (메모리 40% 절약) ═══
class Point:
    __slots__ = ("x", "y")  # __dict__ 생성 안 함

    def __init__(self, x, y):
        self.x = x
        self.y = y

# 100만 개 생성 시:
# 일반 클래스: ~200MB
# __slots__:   ~120MB (40% 절약)

# ═══ 8. numpy로 벡터화 ═══
import numpy as np

# ❌ 파이썬 루프
result = [x**2 + 2*x + 1 for x in range(1000000)]

# ✅ numpy 벡터화 (100배 빠름)
x = np.arange(1000000)
result = x**2 + 2*x + 1
```

성능 최적화 체크리스트:
1. **먼저 프로파일링** (추측으로 최적화하지 말 것!)
2. **알고리즘/자료구조** 먼저 (O(n²) → O(n log n))
3. **파이썬 레벨**: 컴프리헨션, join, set 활용
4. **C 레벨**: numpy, pandas 벡터화
5. **I/O**: 비동기, 배치, 버퍼링
6. **최후 수단**: Cython, C 확장, Rust(PyO3)'''),

    m("파이썬 __init__ __new__ __call__ 차이 정확히 알려줘",
'''파이썬 객체 생성의 3단계를 정확히 설명합니다.

```python
# ═══ 객체 생성 과정 ═══
# MyClass(args) 호출 시:
# 1. MyClass.__new__(cls, args)  → 인스턴스 생성 (메모리 할당)
# 2. MyClass.__init__(self, args) → 인스턴스 초기화 (속성 설정)
# 3. instance(args) → __call__ 호출 (인스턴스를 함수처럼 사용)

class Lifecycle:
    def __new__(cls, *args, **kwargs):
        """인스턴스 생성 (메모리 할당). cls를 받음."""
        print(f"1. __new__: 인스턴스 생성 (cls={cls.__name__})")
        instance = super().__new__(cls)  # 실제 메모리 할당
        return instance  # 반드시 인스턴스 반환!

    def __init__(self, name):
        """인스턴스 초기화. self를 받음."""
        print(f"2. __init__: 초기화 (self={id(self)})")
        self.name = name

    def __call__(self, *args):
        """인스턴스를 함수처럼 호출."""
        print(f"3. __call__: 호출됨 (args={args})")
        return f"{self.name} 실행"

obj = Lifecycle("테스트")
# 출력:
# 1. __new__: 인스턴스 생성 (cls=Lifecycle)
# 2. __init__: 초기화 (self=140234567890)

result = obj("인자1", "인자2")
# 출력:
# 3. __call__: 호출됨 (args=('인자1', '인자2'))

# ═══ __new__의 실무 활용 ═══

# 1. 싱글톤
class Singleton:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, value=None):
        # 주의: 매 호출마다 실행됨!
        if not hasattr(self, "_initialized"):
            self.value = value
            self._initialized = True

s1 = Singleton("첫 번째")
s2 = Singleton("두 번째")
print(s1 is s2)       # True
print(s1.value)        # "첫 번째" (두 번째 호출에서 덮어쓰지 않음)

# 2. 불변 객체 (int, str, tuple은 __new__에서 값 설정)
class FrozenPoint(tuple):
    def __new__(cls, x, y):
        return super().__new__(cls, (x, y))

    @property
    def x(self): return self[0]

    @property
    def y(self): return self[1]

p = FrozenPoint(3, 4)
print(p.x, p.y)   # 3 4
# p[0] = 5  # ❌ TypeError! (tuple은 불변)

# 3. 팩토리 패턴 (다른 클래스 반환 가능!)
class Animal:
    def __new__(cls, species, name):
        if species == "dog":
            return super().__new__(Dog)
        elif species == "cat":
            return super().__new__(Cat)
        return super().__new__(cls)

class Dog(Animal):
    def speak(self): return "멍멍"

class Cat(Animal):
    def speak(self): return "야옹"

animal = Animal("dog", "바둑이")
print(type(animal))     # <class 'Dog'>
print(animal.speak())   # "멍멍"

# ═══ __call__의 실무 활용 ═══

# 1. 설정 가능한 데코레이터
class retry:
    def __init__(self, max_attempts=3, delay=1.0):
        self.max_attempts = max_attempts
        self.delay = delay

    def __call__(self, func):
        import functools, time
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, self.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == self.max_attempts:
                        raise
                    time.sleep(self.delay * attempt)
        return wrapper

@retry(max_attempts=5, delay=0.5)
def unstable_api_call():
    ...

# 2. 전략 패턴
class Validator:
    def __init__(self, rules: list):
        self.rules = rules

    def __call__(self, value):
        errors = []
        for rule in self.rules:
            error = rule(value)
            if error:
                errors.append(error)
        return errors if errors else None

# 규칙 정의
def min_length(n):
    def check(v):
        if len(v) < n: return f"{n}자 이상이어야 합니다"
    return check

def has_digit(v):
    if not any(c.isdigit() for c in v): return "숫자를 포함해야 합니다"

# 검증기 생성
validate_password = Validator([min_length(8), has_digit])
errors = validate_password("abc")
# ['8자 이상이어야 합니다', '숫자를 포함해야 합니다']
```

요약:
| 메서드 | 시점 | 인자 | 용도 |
|--------|------|------|------|
| `__new__` | 인스턴스 **생성** | `cls` | 싱글톤, 불변객체, 팩토리 |
| `__init__` | 인스턴스 **초기화** | `self` | 속성 설정 (가장 흔함) |
| `__call__` | 인스턴스 **호출** | `self` | 데코레이터, 전략패턴, 콜백 |'''),

    m("파이썬 컨텍스트 매니저 심화 알려줘 여러 패턴으로",
'''컨텍스트 매니저(`with`)의 심화 패턴입니다.

```python
from contextlib import contextmanager, asynccontextmanager, ExitStack
import time
import logging

# ═══ 1. 클래스 기반 컨텍스트 매니저 ═══
class DatabaseTransaction:
    """DB 트랜잭션을 자동 관리합니다."""

    def __init__(self, connection):
        self.conn = connection
        self.cursor = None

    def __enter__(self):
        self.cursor = self.conn.cursor()
        self.conn.begin()
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
            logging.info("트랜잭션 커밋")
        else:
            self.conn.rollback()
            logging.error(f"트랜잭션 롤백: {exc_val}")
        self.cursor.close()
        return False  # True 반환 시 예외 억제

# 사용
with DatabaseTransaction(conn) as cursor:
    cursor.execute("INSERT INTO users ...")
    cursor.execute("UPDATE accounts ...")
    # 예외 발생 시 자동 롤백

# ═══ 2. 데코레이터 기반 (가장 간결) ═══
@contextmanager
def timer(label: str = ""):
    """실행 시간을 측정합니다."""
    start = time.perf_counter()
    try:
        yield  # with 블록 실행
    finally:
        elapsed = time.perf_counter() - start
        print(f"[{label}] {elapsed:.4f}초")

with timer("데이터 처리"):
    process_large_data()

# 리소스 관리
@contextmanager
def temporary_directory():
    """임시 디렉토리를 생성하고 사용 후 삭제."""
    import tempfile, shutil
    path = tempfile.mkdtemp()
    try:
        yield path
    finally:
        shutil.rmtree(path)

with temporary_directory() as tmpdir:
    # tmpdir 사용
    pass
# 자동 삭제됨

# ═══ 3. 비동기 컨텍스트 매니저 ═══
@asynccontextmanager
async def db_session():
    """비동기 DB 세션 관리."""
    session = await create_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

async def create_user(data):
    async with db_session() as session:
        user = User(**data)
        session.add(user)
        return user

# ═══ 4. 중첩 컨텍스트 매니저 (ExitStack) ═══
from contextlib import ExitStack

def process_multiple_files(file_paths: list[str]):
    """여러 파일을 동시에 열어 처리."""
    with ExitStack() as stack:
        files = [
            stack.enter_context(open(path, "r"))
            for path in file_paths
        ]
        # 모든 파일이 열린 상태
        for f in files:
            data = f.read()
            process(data)
    # 모든 파일 자동 닫힘

# 동적 개수의 리소스 관리
def acquire_resources(resource_configs):
    with ExitStack() as stack:
        resources = []
        for config in resource_configs:
            resource = stack.enter_context(acquire(config))
            resources.append(resource)

        # 콜백 등록 (역순으로 실행됨)
        stack.callback(logging.info, "모든 리소스 해제 완료")

        return process_all(resources)

# ═══ 5. 환경 변경 후 복원 ═══
@contextmanager
def environment(**env_vars):
    """환경변수를 임시로 변경합니다."""
    import os
    old_env = {}
    for key, value in env_vars.items():
        old_env[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

with environment(DATABASE_URL="sqlite:///test.db", DEBUG="true"):
    # 테스트 환경으로 실행
    run_tests()
# 원래 환경변수 복원됨

# ═══ 6. 재진입 가능 / 재사용 가능 ═══
@contextmanager
def managed_resource():
    print("획득")
    try:
        yield "리소스"
    finally:
        print("해제")

# 재사용 가능 (매번 새로 생성)
cm_factory = managed_resource

with cm_factory() as r1:
    print(r1)

with cm_factory() as r2:
    print(r2)

# ═══ 7. suppress (특정 예외 무시) ═══
from contextlib import suppress

# ❌ try/except 장황
try:
    os.remove("temp.txt")
except FileNotFoundError:
    pass

# ✅ suppress 간결
with suppress(FileNotFoundError):
    os.remove("temp.txt")

# 여러 예외
with suppress(FileNotFoundError, PermissionError):
    os.remove("temp.txt")
```

컨텍스트 매니저 선택:
| 패턴 | 사용 시나리오 |
|------|-------------|
| `@contextmanager` | 간단한 setup/teardown |
| 클래스 (`__enter__/__exit__`) | 복잡한 상태 관리 |
| `@asynccontextmanager` | 비동기 리소스 |
| `ExitStack` | 동적 개수의 리소스 |
| `suppress` | 특정 예외 무시 |'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/deep_python.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI Python 심화 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  Python 심화: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
