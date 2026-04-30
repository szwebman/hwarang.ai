"""화랑 AI Code Review v4 Part B — 깊은 코드 리뷰 500 샘플

5개 시나리오 × 100 = 500 샘플:
- R-5: Over-engineering 정리 (100)
- R-6: 에러 처리 결함 (100)
- R-7: 타입 안전성 (100)
- R-8: N+1 쿼리 (100)
- R-9: 자원 누수 (100)

각 시나리오는 10개 패턴 hardcoded → random.choice 로 100개 변형.
generator 함수 1개 (make_review_sample) 재사용.

7-turn 구조:
1. user: "[Active file: X]\n이 코드 리뷰해줘"
2. assistant: read_file tool_call
3. tool: 버기 코드
4. assistant: 근본 문제 + 해결 + edit_file tool_call
5. tool: File modified
6. assistant: 짧은 마무리
"""
import argparse
import json
import logging
import os
import random
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from build_tools_multiturn import (  # noqa: E402
    TOOLS_DESC,
    m,
    sys as _sys,
    user,
    assistant,
    tool,
    tc,
)


def syss():
    return _sys()


random.seed(2031)


# ============================================================
# R-5: Over-engineering 정리 (10 패턴)
# ============================================================

OVERENG_PATTERNS = [
    {
        "lang": "ts",
        "file": "src/services/UserService.ts",
        "label": "7개 abstract method 다중 상속",
        "buggy_code": (
            "abstract class BaseRepository<T> {\n"
            "  abstract create(): T;\n"
            "  abstract update(): T;\n"
            "  abstract delete(): void;\n"
            "  abstract validate(): boolean;\n"
            "  abstract serialize(): string;\n"
            "  abstract deserialize(s: string): T;\n"
            "  abstract authorize(): boolean;\n"
            "}\n"
            "class UserRepository extends BaseRepository<User> {\n"
            "  create() { /* ... */ return {} as User; }\n"
            "  update() { return {} as User; }\n"
            "  delete() {}\n"
            "  validate() { return true; }\n"
            "  serialize() { return ''; }\n"
            "  deserialize(s: string) { return {} as User; }\n"
            "  authorize() { return true; }\n"
            "}"
        ),
        "explanation": "7개 abstract method 강제. 실제 사용 클래스는 2개뿐인데 모든 method 가 의무. authorize/serialize 는 절반의 클래스에서 의미 없음. 상속 트리가 변경 비용을 폭발시킴.",
        "fix": "단순 함수 + composition. 필요한 동작만 export.",
        "fix_code": (
            "// services/user.ts\n"
            "import { db } from '../db';\n"
            "export async function createUser(data: UserInput): Promise<User> {\n"
            "  return db.user.create({ data });\n"
            "}\n"
            "export async function updateUser(id: string, data: Partial<User>) {\n"
            "  return db.user.update({ where: { id }, data });\n"
            "}\n"
            "export async function deleteUser(id: string) {\n"
            "  return db.user.delete({ where: { id } });\n"
            "}"
        ),
        "note": "abstract 계층 제거 — 함수가 더 단순하고 테스트도 쉬움.",
    },
    {
        "lang": "ts",
        "file": "src/factories/HandlerFactory.ts",
        "label": "Factory of Factory",
        "buggy_code": (
            "class HandlerFactoryFactory {\n"
            "  createFactory(type: string): HandlerFactory {\n"
            "    return new HandlerFactory(type);\n"
            "  }\n"
            "}\n"
            "class HandlerFactory {\n"
            "  constructor(private type: string) {}\n"
            "  create(): Handler {\n"
            "    if (this.type === 'http') return new HttpHandler();\n"
            "    return new DefaultHandler();\n"
            "  }\n"
            "}\n"
            "const handler = new HandlerFactoryFactory().createFactory('http').create();"
        ),
        "explanation": "Factory 의 Factory 는 거의 항상 over-engineering. type → handler 매핑이 전부인데 3단계 추상화. Java EE 의 잔재.",
        "fix": "단순 map lookup.",
        "fix_code": (
            "const HANDLERS: Record<string, () => Handler> = {\n"
            "  http: () => new HttpHandler(),\n"
            "  default: () => new DefaultHandler(),\n"
            "};\n"
            "export function getHandler(type: string): Handler {\n"
            "  return (HANDLERS[type] ?? HANDLERS.default)();\n"
            "}"
        ),
        "note": "1줄 lookup 으로 동일 동작. 등록도 쉬움.",
    },
    {
        "lang": "py",
        "file": "app/strategies.py",
        "label": "5단 inheritance",
        "buggy_code": (
            "class A:\n    def run(self): raise NotImplementedError\n"
            "class B(A):\n    def run(self): return self._step()\n    def _step(self): raise NotImplementedError\n"
            "class C(B):\n    def _step(self): return self._impl()\n    def _impl(self): raise NotImplementedError\n"
            "class D(C):\n    def _impl(self): return self._do()\n    def _do(self): raise NotImplementedError\n"
            "class E(D):\n    def _do(self): return 42"
        ),
        "explanation": "5단 상속. 결과는 그냥 42 반환. 각 단계가 의미 없는 위임. 디버거에서 stack 5단 타고 가야 한다.",
        "fix": "단일 함수.",
        "fix_code": (
            "def run() -> int:\n"
            "    return 42"
        ),
        "note": "동일 동작, 5단 상속 제거.",
    },
    {
        "lang": "ts",
        "file": "src/utils/EventBus.ts",
        "label": "Singleton + Observer + Pub/Sub 중복",
        "buggy_code": (
            "class EventBus {\n"
            "  private static instance: EventBus;\n"
            "  private observers: Observer[] = [];\n"
            "  private subscribers: Map<string, Function[]> = new Map();\n"
            "  static getInstance() {\n"
            "    if (!this.instance) this.instance = new EventBus();\n"
            "    return this.instance;\n"
            "  }\n"
            "  attach(o: Observer) { this.observers.push(o); }\n"
            "  subscribe(t: string, f: Function) {\n"
            "    if (!this.subscribers.has(t)) this.subscribers.set(t, []);\n"
            "    this.subscribers.get(t)!.push(f);\n"
            "  }\n"
            "  notify(t: string, data: any) {\n"
            "    this.observers.forEach(o => o.update(data));\n"
            "    this.subscribers.get(t)?.forEach(f => f(data));\n"
            "  }\n"
            "}"
        ),
        "explanation": "동일 기능을 Observer + Pub/Sub 두 번 구현. Singleton 까지 끼어 테스트 격리 불가능. 사용처는 subscribe 한 곳뿐.",
        "fix": "EventTarget(브라우저 표준) 또는 단순 emitter 1개로 통일.",
        "fix_code": (
            "type Listener = (data: unknown) => void;\n"
            "const bus = new Map<string, Set<Listener>>();\n"
            "export function on(event: string, fn: Listener) {\n"
            "  if (!bus.has(event)) bus.set(event, new Set());\n"
            "  bus.get(event)!.add(fn);\n"
            "  return () => bus.get(event)!.delete(fn);\n"
            "}\n"
            "export function emit(event: string, data: unknown) {\n"
            "  bus.get(event)?.forEach(fn => fn(data));\n"
            "}"
        ),
        "note": "Singleton 제거, dispose 함수 반환으로 cleanup 명시적.",
    },
    {
        "lang": "py",
        "file": "app/config.py",
        "label": "DI Container 자작",
        "buggy_code": (
            "class Container:\n"
            "    _services = {}\n"
            "    @classmethod\n"
            "    def register(cls, key, factory):\n"
            "        cls._services[key] = factory\n"
            "    @classmethod\n"
            "    def resolve(cls, key):\n"
            "        return cls._services[key]()\n"
            "Container.register('db', lambda: Database())\n"
            "Container.register('cache', lambda: Cache())\n"
            "db = Container.resolve('db')"
        ),
        "explanation": "Python 모듈 자체가 DI container. 직접 import 하면 끝. 자작 container 는 IDE 자동완성/타입체크 무력화.",
        "fix": "module-level 변수 + import.",
        "fix_code": (
            "# app/services.py\n"
            "from .database import Database\n"
            "from .cache import Cache\n"
            "db = Database()\n"
            "cache = Cache()\n"
            "# 사용처: from app.services import db, cache"
        ),
        "note": "타입 정보 살아있고 import 만으로 의존성 명확.",
    },
    {
        "lang": "ts",
        "file": "src/builder/QueryBuilder.ts",
        "label": "Builder pattern 남용 (간단 객체에)",
        "buggy_code": (
            "class QueryBuilder {\n"
            "  private q: any = {};\n"
            "  setTable(t: string) { this.q.table = t; return this; }\n"
            "  setLimit(n: number) { this.q.limit = n; return this; }\n"
            "  setOffset(n: number) { this.q.offset = n; return this; }\n"
            "  build() { return this.q; }\n"
            "}\n"
            "const q = new QueryBuilder().setTable('users').setLimit(10).setOffset(0).build();"
        ),
        "explanation": "Builder 의 효용은 복잡한 immutable 객체 단계 구성. 여기는 그냥 3-key 객체 리터럴이면 끝.",
        "fix": "객체 리터럴.",
        "fix_code": (
            "type Query = { table: string; limit?: number; offset?: number };\n"
            "const q: Query = { table: 'users', limit: 10, offset: 0 };"
        ),
        "note": "TypeScript 객체 리터럴이 builder 보다 안전하고 짧다.",
    },
    {
        "lang": "py",
        "file": "app/validators.py",
        "label": "Decorator chain 6중첩",
        "buggy_code": (
            "@cache\n@logged\n@retry(3)\n@validated\n@authorized\n@rate_limited\n"
            "def get_user(id: int):\n"
            "    return db.query(User).get(id)"
        ),
        "explanation": "6개 decorator. 호출 순서/실패 지점 추적 불가능. cache 가 먼저인지 retry 가 먼저인지 코드만 보고 알 수 없음. log 도 두 번 찍힘 (decorator 와 retry 안).",
        "fix": "필요한 것만 명시. 횡단 관심사는 middleware 로.",
        "fix_code": (
            "from functools import lru_cache\n"
            "@lru_cache(maxsize=1000)\n"
            "def get_user(id: int) -> User | None:\n"
            "    if not current_user.can_read('user', id):\n"
            "        raise PermissionDenied()\n"
            "    return db.query(User).get(id)"
        ),
        "note": "auth 는 명시적 호출, cache 는 lru_cache 로 단순화.",
    },
    {
        "lang": "ts",
        "file": "src/api/Endpoint.ts",
        "label": "Generic 과잉",
        "buggy_code": (
            "class Endpoint<\n"
            "  TReq extends Record<string, unknown>,\n"
            "  TRes extends Record<string, unknown>,\n"
            "  TErr extends Error,\n"
            "  TCtx extends { user?: unknown; req: unknown },\n"
            "  THandler extends (ctx: TCtx, req: TReq) => Promise<TRes>\n"
            "> {\n"
            "  constructor(private handler: THandler) {}\n"
            "  async call(ctx: TCtx, req: TReq): Promise<TRes> {\n"
            "    return this.handler(ctx, req);\n"
            "  }\n"
            "}"
        ),
        "explanation": "5개 generic 파라미터로 단순 함수 호출 wrap. 호출 측은 generic 5개 다 명시해야 한다. 추상화는 zero, 복잡도는 max.",
        "fix": "함수 그대로 export.",
        "fix_code": (
            "export type Handler<Req, Res> = (ctx: Ctx, req: Req) => Promise<Res>;\n"
            "// 사용: const getUser: Handler<{ id: string }, User> = async (ctx, req) => { ... };"
        ),
        "note": "type alias 1개로 동일 효과.",
    },
    {
        "lang": "py",
        "file": "app/state_machine.py",
        "label": "State machine for 2-state",
        "buggy_code": (
            "class State:\n    def handle(self, ctx): pass\n"
            "class OpenState(State):\n    def handle(self, ctx): ctx.state = ClosedState()\n"
            "class ClosedState(State):\n    def handle(self, ctx): ctx.state = OpenState()\n"
            "class Door:\n"
            "    def __init__(self): self.state = ClosedState()\n"
            "    def toggle(self): self.state.handle(self)"
        ),
        "explanation": "open/closed 2개 state 에 GoF state pattern. boolean 1개면 끝.",
        "fix": "boolean.",
        "fix_code": (
            "class Door:\n"
            "    def __init__(self) -> None:\n"
            "        self.is_open = False\n"
            "    def toggle(self) -> None:\n"
            "        self.is_open = not self.is_open"
        ),
        "note": "2-state 는 boolean. 3+ state 부터 enum 검토.",
    },
    {
        "lang": "ts",
        "file": "src/utils/Result.ts",
        "label": "Result monad 자작 + 표준 Promise 무시",
        "buggy_code": (
            "class Result<T, E> {\n"
            "  constructor(public ok: boolean, public value?: T, public error?: E) {}\n"
            "  static success<T>(v: T) { return new Result<T, never>(true, v); }\n"
            "  static fail<E>(e: E) { return new Result<never, E>(false, undefined, e); }\n"
            "  map<U>(f: (v: T) => U): Result<U, E> {\n"
            "    return this.ok ? Result.success(f(this.value!)) : (this as any);\n"
            "  }\n"
            "  flatMap<U>(f: (v: T) => Result<U, E>): Result<U, E> {\n"
            "    return this.ok ? f(this.value!) : (this as any);\n"
            "  }\n"
            "}\n"
            "function getUser(id: string): Result<User, Error> { ... }"
        ),
        "explanation": "TypeScript 에는 try/catch + Promise 가 표준. Rust 흉내내려고 monad 를 자작하면 모든 호출처가 .ok 분기/.map/.flatMap 으로 오염. async/await 와 안 섞임.",
        "fix": "표준 throw + try/catch 또는 discriminated union.",
        "fix_code": (
            "type Result<T> = { ok: true; value: T } | { ok: false; error: string };\n"
            "async function getUser(id: string): Promise<Result<User>> {\n"
            "  try {\n"
            "    const user = await db.user.findUnique({ where: { id } });\n"
            "    if (!user) return { ok: false, error: 'not_found' };\n"
            "    return { ok: true, value: user };\n"
            "  } catch (e) {\n"
            "    return { ok: false, error: 'db_error' };\n"
            "  }\n"
            "}"
        ),
        "note": "discriminated union 으로 narrowing 자동, monad 메서드 불필요.",
    },
]


# ============================================================
# R-6: 에러 처리 결함 (10 패턴)
# ============================================================

ERROR_PATTERNS = [
    {
        "lang": "ts",
        "file": "src/api.ts",
        "label": "empty catch — silent fail",
        "buggy_code": (
            "try {\n"
            "  await save(data);\n"
            "} catch (e) {}"
        ),
        "explanation": "empty catch — 모든 에러 silent fail. DB 다운, 네트워크 끊김, validation 실패 모두 사용자에게 '저장됨' 으로 표시. 디버깅 지옥.",
        "fix": "명시적 분기 + 로깅 + 재던지기.",
        "fix_code": (
            "try {\n"
            "  await save(data);\n"
            "} catch (e) {\n"
            "  if (e instanceof DBError) {\n"
            "    logger.error('DB save failed', { e, data });\n"
            "    throw new ApiError(500, 'Save failed');\n"
            "  }\n"
            "  throw e;\n"
            "}"
        ),
        "note": "예상한 에러만 잡고 나머진 재던지기.",
    },
    {
        "lang": "py",
        "file": "app/runner.py",
        "label": "bare except + console.log only",
        "buggy_code": (
            "try:\n"
            "    result = compute(data)\n"
            "except Exception as e:\n"
            "    print(e)"
        ),
        "explanation": "bare except + print. KeyboardInterrupt 까지 잡힘. stack trace 사라짐. 호출자는 None 받고 진행 → 후속 에러가 진짜 원인을 가린다.",
        "fix": "특정 예외 + logger.exception 으로 trace 보존 + 재던지기.",
        "fix_code": (
            "try:\n"
            "    result = compute(data)\n"
            "except (ValueError, KeyError) as e:\n"
            "    logger.exception('compute failed: data=%s', data)\n"
            "    raise ComputeError('invalid input') from e"
        ),
        "note": "logger.exception 은 traceback 자동 포함, raise from 으로 원인 chain.",
    },
    {
        "lang": "ts",
        "file": "src/upload.ts",
        "label": "generic try wrap (특정 에러만 잡아야)",
        "buggy_code": (
            "async function upload(file: File) {\n"
            "  try {\n"
            "    const url = await getSignedUrl();\n"
            "    const res = await fetch(url, { method: 'PUT', body: file });\n"
            "    return await res.json();\n"
            "  } catch (e) {\n"
            "    return null;\n"
            "  }\n"
            "}"
        ),
        "explanation": "전체 try wrap → null 반환. getSignedUrl 실패/네트워크 에러/JSON 파싱 실패 모두 동일 처리. 호출자는 왜 실패했는지 모른다.",
        "fix": "단계별 분리 + Result type.",
        "fix_code": (
            "async function upload(file: File): Promise<{ ok: true; data: any } | { ok: false; reason: string }> {\n"
            "  let url: string;\n"
            "  try { url = await getSignedUrl(); }\n"
            "  catch { return { ok: false, reason: 'signed_url_failed' }; }\n"
            "  const res = await fetch(url, { method: 'PUT', body: file });\n"
            "  if (!res.ok) return { ok: false, reason: `http_${res.status}` };\n"
            "  try { return { ok: true, data: await res.json() }; }\n"
            "  catch { return { ok: false, reason: 'parse_failed' }; }\n"
            "}"
        ),
        "note": "실패 사유가 호출자에게 명확히 전달.",
    },
    {
        "lang": "ts",
        "file": "src/jobs/worker.ts",
        "label": "async/await 에러 propagation 누락",
        "buggy_code": (
            "function processJob(job: Job) {\n"
            "  doWork(job).then(r => job.markDone(r));\n"
            "  return 'queued';\n"
            "}"
        ),
        "explanation": ".then 만 있고 .catch 없음. doWork 거부 시 unhandledRejection. processJob 호출자는 'queued' 받고 끝났다고 생각. 작업이 실패해도 추적 불가.",
        "fix": "async/await + try/catch + 실패 마킹.",
        "fix_code": (
            "async function processJob(job: Job): Promise<'done' | 'failed'> {\n"
            "  try {\n"
            "    const r = await doWork(job);\n"
            "    await job.markDone(r);\n"
            "    return 'done';\n"
            "  } catch (e) {\n"
            "    await job.markFailed(e instanceof Error ? e.message : String(e));\n"
            "    logger.error('job failed', { jobId: job.id, e });\n"
            "    return 'failed';\n"
            "  }\n"
            "}"
        ),
        "note": "실패 시 명시적으로 markFailed → 재시도/모니터링 가능.",
    },
    {
        "lang": "py",
        "file": "app/io_utils.py",
        "label": "에러 swallow + 리턴값으로만 표시",
        "buggy_code": (
            "def load_config(path):\n"
            "    try:\n"
            "        with open(path) as f:\n"
            "            return json.load(f)\n"
            "    except:\n"
            "        return {}"
        ),
        "explanation": "파일 없음/JSON 파싱 실패 모두 빈 dict 반환. 호출자는 'config 가 비어있나' 와 '읽기 실패인가' 구분 불가. 빈 설정으로 prod 가동되는 사고 패턴.",
        "fix": "예외 분리 + 명시적 default.",
        "fix_code": (
            "def load_config(path: str) -> dict:\n"
            "    try:\n"
            "        with open(path, encoding='utf-8') as f:\n"
            "            return json.load(f)\n"
            "    except FileNotFoundError:\n"
            "        logger.warning('config not found: %s — using defaults', path)\n"
            "        return DEFAULT_CONFIG.copy()\n"
            "    except json.JSONDecodeError as e:\n"
            "        raise ConfigError(f'invalid JSON in {path}: {e}') from e"
        ),
        "note": "파싱 실패는 fail-fast, 파일 없음만 default 로 처리.",
    },
    {
        "lang": "ts",
        "file": "src/api/handler.ts",
        "label": "에러를 string 으로 throw",
        "buggy_code": (
            "function validate(input: any) {\n"
            "  if (!input.email) throw 'email required';\n"
            "  if (!input.email.includes('@')) throw 'invalid email';\n"
            "}"
        ),
        "explanation": "string throw — stack trace 없음. instanceof 체크 불가. 상위 catch 에서 error.message 가 undefined.",
        "fix": "Error subclass.",
        "fix_code": (
            "export class ValidationError extends Error {\n"
            "  constructor(public field: string, message: string) {\n"
            "    super(message);\n"
            "    this.name = 'ValidationError';\n"
            "  }\n"
            "}\n"
            "function validate(input: { email?: string }) {\n"
            "  if (!input.email) throw new ValidationError('email', 'email required');\n"
            "  if (!input.email.includes('@')) throw new ValidationError('email', 'invalid email');\n"
            "}"
        ),
        "note": "instanceof ValidationError 로 422 응답, 그 외엔 500 분리.",
    },
    {
        "lang": "py",
        "file": "app/payment.py",
        "label": "재시도 무한 — 영구 실패도 재시도",
        "buggy_code": (
            "def charge(card, amount):\n"
            "    while True:\n"
            "        try:\n"
            "            return stripe.charge(card, amount)\n"
            "        except Exception:\n"
            "            time.sleep(1)"
        ),
        "explanation": "카드 거절(영구) 도 무한 재시도. 호출 thread 영원히 block. CPU 100%. 비용은 Stripe 가 청구.",
        "fix": "지수 backoff + 횟수 제한 + 일시 에러만 재시도.",
        "fix_code": (
            "def charge(card, amount, max_retries: int = 3):\n"
            "    for attempt in range(max_retries):\n"
            "        try:\n"
            "            return stripe.charge(card, amount)\n"
            "        except stripe.error.RateLimitError:\n"
            "            time.sleep(2 ** attempt)\n"
            "        except stripe.error.CardError as e:\n"
            "            raise PaymentDeclined(e.user_message) from e\n"
            "    raise PaymentRetryExhausted()"
        ),
        "note": "거절은 즉시 fail, rate limit 만 backoff 재시도.",
    },
    {
        "lang": "ts",
        "file": "src/io/parser.ts",
        "label": "JSON.parse 검증 없이 바로 사용",
        "buggy_code": (
            "function readUser(raw: string): User {\n"
            "  const data = JSON.parse(raw);\n"
            "  return data;\n"
            "}"
        ),
        "explanation": "JSON.parse 실패 시 SyntaxError 그대로 호출자에게. 파싱 성공해도 User shape 보장 X. 'as User' 캐스팅으로 런타임에 .name.toLowerCase() 같은 호출이 crash.",
        "fix": "try/catch + zod 검증.",
        "fix_code": (
            "import { z } from 'zod';\n"
            "const UserSchema = z.object({ id: z.string(), name: z.string(), email: z.string().email() });\n"
            "export function readUser(raw: string): User {\n"
            "  let data: unknown;\n"
            "  try { data = JSON.parse(raw); }\n"
            "  catch (e) { throw new ParseError('invalid JSON', { cause: e }); }\n"
            "  const result = UserSchema.safeParse(data);\n"
            "  if (!result.success) throw new ParseError('invalid user shape: ' + result.error.message);\n"
            "  return result.data;\n"
            "}"
        ),
        "note": "shape 검증으로 type-safe 보장.",
    },
    {
        "lang": "py",
        "file": "app/cli.py",
        "label": "sys.exit(1) — message 없이",
        "buggy_code": (
            "def main():\n"
            "    if not check_env():\n"
            "        sys.exit(1)\n"
            "    if not check_db():\n"
            "        sys.exit(1)\n"
            "    run_app()"
        ),
        "explanation": "exit(1) 두 번. 사용자는 종료 후 무엇이 잘못됐는지 모른다. CI 로그에서도 추적 불가.",
        "fix": "stderr 메시지 + 차별 exit code.",
        "fix_code": (
            "def main() -> int:\n"
            "    if not check_env():\n"
            "        print('error: required env vars missing — see ENV.md', file=sys.stderr)\n"
            "        return 2\n"
            "    if not check_db():\n"
            "        print('error: cannot reach database — check DATABASE_URL', file=sys.stderr)\n"
            "        return 3\n"
            "    return run_app()\n"
            "if __name__ == '__main__':\n"
            "    sys.exit(main())"
        ),
        "note": "exit code 별로 자동화 분기 가능.",
    },
    {
        "lang": "ts",
        "file": "src/server/middleware.ts",
        "label": "throw 안에 비즈니스 로직 분기",
        "buggy_code": (
            "app.use(async (req, res, next) => {\n"
            "  try {\n"
            "    await next();\n"
            "  } catch (e: any) {\n"
            "    if (e.message === 'not found') return res.status(404).end();\n"
            "    if (e.message === 'forbidden') return res.status(403).end();\n"
            "    if (e.message === 'invalid') return res.status(400).end();\n"
            "    res.status(500).end();\n"
            "  }\n"
            "});"
        ),
        "explanation": "에러 메시지 문자열로 분기. 메시지 오타/번역 시 모두 500. 정보 손실 (no body, no log).",
        "fix": "Error subclass + 인스턴스 검사.",
        "fix_code": (
            "class HttpError extends Error {\n"
            "  constructor(public status: number, message: string) { super(message); }\n"
            "}\n"
            "export const NotFound = (m='not found') => new HttpError(404, m);\n"
            "export const Forbidden = (m='forbidden') => new HttpError(403, m);\n"
            "app.use(async (req, res, next) => {\n"
            "  try { await next(); }\n"
            "  catch (e) {\n"
            "    if (e instanceof HttpError) return res.status(e.status).json({ error: e.message });\n"
            "    logger.error('unhandled', { e, path: req.path });\n"
            "    res.status(500).json({ error: 'internal' });\n"
            "  }\n"
            "});"
        ),
        "note": "타입 기반 분기 + 사용자 친화 body.",
    },
]


# ============================================================
# R-7: 타입 안전성 (10 패턴)
# ============================================================

TYPE_PATTERNS = [
    {
        "lang": "ts",
        "file": "src/parse.ts",
        "label": "any 남용 + as 캐스팅",
        "buggy_code": (
            "function parse(data: any) {\n"
            "  return (data as any).items.map((x: any) => x.name);\n"
            "}"
        ),
        "explanation": "any 3개 + as any cast. data 가 null/undefined/items 없는 객체면 런타임 crash. TS 의 안전망 완전 우회.",
        "fix": "제네릭 + 가드.",
        "fix_code": (
            "function parse<T extends { name?: string }>(\n"
            "  data: { items?: T[] } | null | undefined\n"
            "): string[] {\n"
            "  if (!data?.items) return [];\n"
            "  return data.items.map(x => x?.name).filter((n): n is string => Boolean(n));\n"
            "}"
        ),
        "note": "type predicate 로 string[] 정확히 narrowing.",
    },
    {
        "lang": "ts",
        "file": "src/utils/cast.ts",
        "label": "non-null assertion (!) 남용",
        "buggy_code": (
            "function getUser(id: string) {\n"
            "  const cached = cache.get(id)!;\n"
            "  return cached.profile!.email!;\n"
            "}"
        ),
        "explanation": "! 3개 — cache miss / no profile / no email 모두 런타임 crash. 컴파일러는 보호 못함.",
        "fix": "optional chaining + 명시적 fallback/throw.",
        "fix_code": (
            "function getUser(id: string): string {\n"
            "  const cached = cache.get(id);\n"
            "  if (!cached) throw new Error(`user not in cache: ${id}`);\n"
            "  const email = cached.profile?.email;\n"
            "  if (!email) throw new Error(`user ${id} has no email`);\n"
            "  return email;\n"
            "}"
        ),
        "note": "어디서 실패하는지 메시지로 명확.",
    },
    {
        "lang": "ts",
        "file": "src/api/types.ts",
        "label": "object literal 대신 any",
        "buggy_code": (
            "function send(payload: any): Promise<any> {\n"
            "  return fetch('/api', { method: 'POST', body: JSON.stringify(payload) }).then(r => r.json());\n"
            "}"
        ),
        "explanation": "input/output any. 호출자 측에서 typo 도 잡히지 않음. response 의 .data.user 가 .data.usr 인지 모름.",
        "fix": "제네릭으로 양쪽 타입 명시.",
        "fix_code": (
            "export async function send<TReq, TRes>(payload: TReq): Promise<TRes> {\n"
            "  const r = await fetch('/api', {\n"
            "    method: 'POST',\n"
            "    headers: { 'content-type': 'application/json' },\n"
            "    body: JSON.stringify(payload),\n"
            "  });\n"
            "  if (!r.ok) throw new Error(`HTTP ${r.status}`);\n"
            "  return r.json() as Promise<TRes>;\n"
            "}"
        ),
        "note": "send<CreateUserReq, User>(...) 로 호출 → 양쪽 타입 체크.",
    },
    {
        "lang": "py",
        "file": "app/handler.py",
        "label": "타입 힌트 부재",
        "buggy_code": (
            "def process(data, options=None):\n"
            "    if options:\n"
            "        for key in options:\n"
            "            data[key] = options[key]\n"
            "    return data"
        ),
        "explanation": "타입 힌트 없음. options 가 list 면 for key in 동작은 다름. data 가 dict 가정인데 호출처는 list 넘길 수 있음.",
        "fix": "명시적 hint + Mapping/Mutable 분리.",
        "fix_code": (
            "from typing import Mapping, MutableMapping\n"
            "def process(\n"
            "    data: MutableMapping[str, object],\n"
            "    options: Mapping[str, object] | None = None,\n"
            ") -> MutableMapping[str, object]:\n"
            "    if options:\n"
            "        data.update(options)\n"
            "    return data"
        ),
        "note": "mypy --strict 통과, 호출자도 IDE 보호 받음.",
    },
    {
        "lang": "ts",
        "file": "src/utils/json.ts",
        "label": "unknown 대신 any",
        "buggy_code": (
            "function safeParse(s: string): any {\n"
            "  try { return JSON.parse(s); } catch { return null; }\n"
            "}\n"
            "const x = safeParse(input);\n"
            "x.foo.bar();  // 컴파일 통과 — 실제론 crash"
        ),
        "explanation": "any 반환 → 호출처가 .foo.bar() 마음대로 접근. unknown 이면 컴파일러가 가드 강제.",
        "fix": "unknown + 사용처 narrowing.",
        "fix_code": (
            "export function safeParse(s: string): unknown {\n"
            "  try { return JSON.parse(s); } catch { return null; }\n"
            "}\n"
            "const x = safeParse(input);\n"
            "if (x && typeof x === 'object' && 'foo' in x) {\n"
            "  // narrow further with zod or instanceof checks\n"
            "}"
        ),
        "note": "unknown 은 작업 강제, any 는 작업 무력화.",
    },
    {
        "lang": "ts",
        "file": "src/state/store.ts",
        "label": "discriminated union 없는 상태",
        "buggy_code": (
            "type State = {\n"
            "  loading: boolean;\n"
            "  data: User | null;\n"
            "  error: string | null;\n"
            "};\n"
            "// 호출처: state.loading && state.data — 동시에 둘 다 가능?"
        ),
        "explanation": "boolean+null 조합으로 상태 표현. loading=true & data!=null 같은 모순 상태 표현 가능. 분기 시 null 체크 의무 누락.",
        "fix": "discriminated union.",
        "fix_code": (
            "type State =\n"
            "  | { tag: 'idle' }\n"
            "  | { tag: 'loading' }\n"
            "  | { tag: 'success'; data: User }\n"
            "  | { tag: 'error'; message: string };\n"
            "// 호출처: switch (state.tag) — exhaustive check 가능"
        ),
        "note": "switch 빠뜨리면 컴파일 에러로 잡힘.",
    },
    {
        "lang": "py",
        "file": "app/models.py",
        "label": "Optional 안 쓰고 None 반환",
        "buggy_code": (
            "def find_user(id: int) -> User:\n"
            "    row = db.query(...)\n"
            "    if row:\n"
            "        return User(**row)\n"
            "    return None"
        ),
        "explanation": "선언은 User, 실제는 None 반환. mypy 무시. 호출처는 .name 접근 시 AttributeError.",
        "fix": "Optional 명시.",
        "fix_code": (
            "from typing import Optional\n"
            "def find_user(id: int) -> Optional[User]:\n"
            "    row = db.query(...)\n"
            "    return User(**row) if row else None"
        ),
        "note": "호출처: if user is None: ... 강제.",
    },
    {
        "lang": "ts",
        "file": "src/enum.ts",
        "label": "string union vs enum 혼용",
        "buggy_code": (
            "enum Status { Active = 0, Inactive = 1 }\n"
            "function setStatus(s: Status) { ... }\n"
            "setStatus(0);  // 통과 — 의도 불명\n"
            "setStatus(99 as Status);  // 통과"
        ),
        "explanation": "numeric enum 은 0/1/99 같은 임의 number 통과. tree-shaking 도 안됨 (TS 컴파일러 객체 생성). string union 이 더 안전.",
        "fix": "as const + literal union.",
        "fix_code": (
            "export const STATUS = ['active', 'inactive'] as const;\n"
            "export type Status = typeof STATUS[number];\n"
            "function setStatus(s: Status) { ... }\n"
            "setStatus('active');  // OK\n"
            "setStatus('foo');  // 컴파일 에러"
        ),
        "note": "string literal union 이 enum 보다 안전+가벼움.",
    },
    {
        "lang": "ts",
        "file": "src/api/list.ts",
        "label": "array index access nullable 미고려",
        "buggy_code": (
            "function first<T>(arr: T[]): T {\n"
            "  return arr[0];\n"
            "}\n"
            "const x: string = first<string>([]);\n"
            "x.toLowerCase();  // 런타임 crash"
        ),
        "explanation": "tsconfig 의 noUncheckedIndexedAccess 꺼져있어 arr[0] 이 T 로 추론. 빈 배열이면 undefined 인데 컴파일러 허용.",
        "fix": "T | undefined 명시.",
        "fix_code": (
            "function first<T>(arr: T[]): T | undefined {\n"
            "  return arr[0];\n"
            "}\n"
            "// 또는 tsconfig.json 에 \"noUncheckedIndexedAccess\": true"
        ),
        "note": "tsconfig 옵션 켜는 것이 근본 해결.",
    },
    {
        "lang": "py",
        "file": "app/serializer.py",
        "label": "dict[str, Any] 남용",
        "buggy_code": (
            "def to_payload(user) -> dict:\n"
            "    return {\n"
            "        'id': user.id,\n"
            "        'name': user.name,\n"
            "        'created': user.created_at.isoformat(),\n"
            "    }"
        ),
        "explanation": "리턴 dict 무엇이 들어있는지 호출자가 알 수 없음. 필드 추가/삭제 시 호출처 silent breakage.",
        "fix": "TypedDict 또는 Pydantic.",
        "fix_code": (
            "from typing import TypedDict\n"
            "class UserPayload(TypedDict):\n"
            "    id: int\n"
            "    name: str\n"
            "    created: str\n"
            "def to_payload(user: User) -> UserPayload:\n"
            "    return {\n"
            "        'id': user.id,\n"
            "        'name': user.name,\n"
            "        'created': user.created_at.isoformat(),\n"
            "    }"
        ),
        "note": "필드 누락 시 mypy 가 잡음.",
    },
]


# ============================================================
# R-8: N+1 쿼리 (10 패턴)
# ============================================================

N1_PATTERNS = [
    {
        "lang": "ts",
        "file": "src/posts.ts",
        "label": "for + findUnique — 1+N 쿼리",
        "buggy_code": (
            "const posts = await db.post.findMany();\n"
            "for (const p of posts) {\n"
            "  p.author = await db.user.findUnique({ where: { id: p.authorId } });\n"
            "}"
        ),
        "explanation": "1000 posts → 1001 쿼리. DB latency 5ms × 1000 = 5초. p2p network 라면 망함.",
        "fix": "include 로 join.",
        "fix_code": (
            "const posts = await db.post.findMany({\n"
            "  include: { author: true }\n"
            "});"
        ),
        "note": "Prisma include 또는 SQL JOIN — 단일 쿼리.",
    },
    {
        "lang": "py",
        "file": "app/views.py",
        "label": "Django select_related 누락",
        "buggy_code": (
            "posts = Post.objects.all()\n"
            "for p in posts:\n"
            "    print(p.author.name)"
        ),
        "explanation": "p.author 접근 시마다 SELECT user. 1+N. ORM 의 가장 흔한 함정.",
        "fix": "select_related (1:1/FK) / prefetch_related (M:N).",
        "fix_code": (
            "posts = Post.objects.select_related('author').all()\n"
            "for p in posts:\n"
            "    print(p.author.name)"
        ),
        "note": "select_related 는 JOIN, prefetch_related 는 IN 쿼리.",
    },
    {
        "lang": "ts",
        "file": "src/checkout.ts",
        "label": "sequential await — 병렬 가능",
        "buggy_code": (
            "const user = await getUser(id);\n"
            "const cart = await getCart(id);\n"
            "const promo = await getPromo(id);\n"
            "return { user, cart, promo };"
        ),
        "explanation": "3개 독립 쿼리 sequential. 각 100ms = 300ms. 의존성 없으면 병렬 가능.",
        "fix": "Promise.all.",
        "fix_code": (
            "const [user, cart, promo] = await Promise.all([\n"
            "  getUser(id),\n"
            "  getCart(id),\n"
            "  getPromo(id),\n"
            "]);\n"
            "return { user, cart, promo };"
        ),
        "note": "100ms (max) 로 3배 빠름.",
    },
    {
        "lang": "py",
        "file": "app/orm.py",
        "label": "SQLAlchemy lazy loading default",
        "buggy_code": (
            "users = session.query(User).all()\n"
            "for u in users:\n"
            "    print(len(u.orders))  # lazy load — 매번 SELECT"
        ),
        "explanation": "default lazy='select' 로 u.orders 접근마다 SELECT. 1000 users → 1001 쿼리.",
        "fix": "joinedload / selectinload.",
        "fix_code": (
            "from sqlalchemy.orm import selectinload\n"
            "users = session.query(User).options(selectinload(User.orders)).all()\n"
            "for u in users:\n"
            "    print(len(u.orders))"
        ),
        "note": "selectinload 는 IN 쿼리 1번, joinedload 는 LEFT JOIN.",
    },
    {
        "lang": "ts",
        "file": "src/graphql/resolver.ts",
        "label": "GraphQL N+1 — DataLoader 미사용",
        "buggy_code": (
            "const resolvers = {\n"
            "  Post: {\n"
            "    author: (post) => db.user.findUnique({ where: { id: post.authorId } })\n"
            "  }\n"
            "};"
        ),
        "explanation": "GraphQL 쿼리 { posts { author { name } } } 시 post 마다 author 쿼리. DataLoader 없으면 N+1.",
        "fix": "DataLoader 로 batching.",
        "fix_code": (
            "import DataLoader from 'dataloader';\n"
            "const userLoader = new DataLoader<string, User>(async (ids) => {\n"
            "  const users = await db.user.findMany({ where: { id: { in: [...ids] } } });\n"
            "  const map = new Map(users.map(u => [u.id, u]));\n"
            "  return ids.map(id => map.get(id)!);\n"
            "});\n"
            "const resolvers = {\n"
            "  Post: { author: (post) => userLoader.load(post.authorId) }\n"
            "};"
        ),
        "note": "DataLoader 가 동일 tick 의 load 호출을 batch.",
    },
    {
        "lang": "ts",
        "file": "src/orders.ts",
        "label": "loop 안 forEach + DB call",
        "buggy_code": (
            "items.forEach(async (item) => {\n"
            "  await db.order.create({ data: item });\n"
            "});\n"
            "console.log('done');"
        ),
        "explanation": "두 가지 문제: (1) forEach + async — 'done' 이 모든 insert 전에 출력. (2) 1000 items = 1000 round-trip.",
        "fix": "createMany 로 batch insert.",
        "fix_code": (
            "await db.order.createMany({ data: items });\n"
            "console.log('done');"
        ),
        "note": "DB 라운드트립 1번, await 도 정상 동작.",
    },
    {
        "lang": "py",
        "file": "app/report.py",
        "label": "in-loop count 쿼리",
        "buggy_code": (
            "for category in Category.objects.all():\n"
            "    print(category.name, Product.objects.filter(category=category).count())"
        ),
        "explanation": "각 category 마다 COUNT 쿼리. 100 categories = 101 쿼리.",
        "fix": "annotate + Count.",
        "fix_code": (
            "from django.db.models import Count\n"
            "qs = Category.objects.annotate(product_count=Count('product'))\n"
            "for c in qs:\n"
            "    print(c.name, c.product_count)"
        ),
        "note": "단일 GROUP BY 쿼리.",
    },
    {
        "lang": "ts",
        "file": "src/cart.ts",
        "label": "Promise.all 안 lookup loop",
        "buggy_code": (
            "const products = await Promise.all(\n"
            "  cart.items.map(async (item) => {\n"
            "    const p = await db.product.findUnique({ where: { id: item.productId } });\n"
            "    const stock = await db.stock.findUnique({ where: { productId: item.productId } });\n"
            "    return { ...p, stock };\n"
            "  })\n"
            ");"
        ),
        "explanation": "Promise.all 로 동시성은 있으나 여전히 2N 쿼리. 100 items = 200 쿼리. DB connection pool 고갈.",
        "fix": "IN 쿼리 + Map join.",
        "fix_code": (
            "const ids = cart.items.map(i => i.productId);\n"
            "const [products, stocks] = await Promise.all([\n"
            "  db.product.findMany({ where: { id: { in: ids } } }),\n"
            "  db.stock.findMany({ where: { productId: { in: ids } } }),\n"
            "]);\n"
            "const stockMap = new Map(stocks.map(s => [s.productId, s]));\n"
            "const result = products.map(p => ({ ...p, stock: stockMap.get(p.id) }));"
        ),
        "note": "쿼리 2개로 N 항목 처리.",
    },
    {
        "lang": "py",
        "file": "app/feed.py",
        "label": "M:N 관계 lazy load",
        "buggy_code": (
            "users = User.query.all()\n"
            "for u in users:\n"
            "    tags = [t.name for t in u.tags]"
        ),
        "explanation": "users.tags 는 M:N. 각 user 마다 association table SELECT. 1000 users = 1001 쿼리.",
        "fix": "subqueryload / selectinload.",
        "fix_code": (
            "from sqlalchemy.orm import selectinload\n"
            "users = User.query.options(selectinload(User.tags)).all()\n"
            "for u in users:\n"
            "    tags = [t.name for t in u.tags]"
        ),
        "note": "M:N 은 selectinload 가 통상 더 빠름.",
    },
    {
        "lang": "ts",
        "file": "src/permissions.ts",
        "label": "hasPermission 매 호출마다 DB",
        "buggy_code": (
            "for (const item of items) {\n"
            "  if (await hasPermission(user, item.id)) {\n"
            "    visible.push(item);\n"
            "  }\n"
            "}\n"
            "// hasPermission 내부에서 db.permission.findMany"
        ),
        "explanation": "hasPermission 매번 DB. 1000 items × 1 쿼리 = 1000.",
        "fix": "한 번 로드 → in-memory 검사.",
        "fix_code": (
            "const allowedIds = new Set(\n"
            "  (await db.permission.findMany({\n"
            "    where: { userId: user.id, resourceId: { in: items.map(i => i.id) } },\n"
            "    select: { resourceId: true },\n"
            "  })).map(p => p.resourceId)\n"
            ");\n"
            "const visible = items.filter(i => allowedIds.has(i.id));"
        ),
        "note": "권한 1쿼리 + Set 조회는 O(1).",
    },
]


# ============================================================
# R-9: 자원 누수 (10 패턴)
# ============================================================

RESOURCE_PATTERNS = [
    {
        "lang": "py",
        "file": "app/processor.py",
        "label": "파일 핸들 close 누락",
        "buggy_code": (
            "def process(path):\n"
            "    f = open(path)\n"
            "    data = f.read()\n"
            "    return parse(data)"
        ),
        "explanation": "f.close() 없음. parse 가 예외 던지면 핸들 누수. CPython 은 GC 가 close 하지만 보장 X. PyPy/Jython 은 큰 누수.",
        "fix": "with 문.",
        "fix_code": (
            "def process(path: str):\n"
            "    with open(path, encoding='utf-8') as f:\n"
            "        data = f.read()\n"
            "    return parse(data)"
        ),
        "note": "with 가 예외에도 close 보장.",
    },
    {
        "lang": "py",
        "file": "app/db.py",
        "label": "DB connection leak",
        "buggy_code": (
            "def get_user(id):\n"
            "    conn = pool.get_connection()\n"
            "    cur = conn.cursor()\n"
            "    cur.execute('SELECT * FROM users WHERE id=%s', (id,))\n"
            "    return cur.fetchone()"
        ),
        "explanation": "conn.close() / cur.close() 없음. 호출 누적되면 pool 고갈 → 새 요청 hang.",
        "fix": "context manager + try/finally.",
        "fix_code": (
            "def get_user(id: int):\n"
            "    with pool.get_connection() as conn:\n"
            "        with conn.cursor() as cur:\n"
            "            cur.execute('SELECT * FROM users WHERE id=%s', (id,))\n"
            "            return cur.fetchone()"
        ),
        "note": "context manager 가 모든 경로에서 release 보장.",
    },
    {
        "lang": "py",
        "file": "app/spawner.py",
        "label": "subprocess wait 안 함 — zombie",
        "buggy_code": (
            "def run_job(cmd):\n"
            "    p = subprocess.Popen(cmd, shell=True)\n"
            "    return p.pid"
        ),
        "explanation": "wait/communicate 호출 안 함 → 자식 종료 후 zombie. PID table 누적. 부모는 SIGCHLD 핸들 X.",
        "fix": "context manager 또는 명시적 wait.",
        "fix_code": (
            "import subprocess\n"
            "def run_job(cmd: list[str], timeout: float = 60) -> int:\n"
            "    with subprocess.Popen(cmd) as p:\n"
            "        try:\n"
            "            return p.wait(timeout=timeout)\n"
            "        except subprocess.TimeoutExpired:\n"
            "            p.kill()\n"
            "            p.wait()\n"
            "            raise"
        ),
        "note": "with 가 자동 wait, timeout 으로 hang 방지.",
    },
    {
        "lang": "py",
        "file": "app/api_client.py",
        "label": "requests session 누수",
        "buggy_code": (
            "def fetch_all(urls):\n"
            "    results = []\n"
            "    for url in urls:\n"
            "        s = requests.Session()\n"
            "        results.append(s.get(url).json())\n"
            "    return results"
        ),
        "explanation": "URL 마다 Session 생성. close 안 함. socket FD 누수 + connection pooling 무력화.",
        "fix": "Session 1개 with.",
        "fix_code": (
            "def fetch_all(urls: list[str]) -> list:\n"
            "    with requests.Session() as s:\n"
            "        return [s.get(url).json() for url in urls]"
        ),
        "note": "Session 재사용으로 keep-alive 도 작동 → 빠르고 누수 없음.",
    },
    {
        "lang": "ts",
        "file": "src/upload.ts",
        "label": "stream 미해제",
        "buggy_code": (
            "import fs from 'fs';\n"
            "function copy(src: string, dst: string) {\n"
            "  const r = fs.createReadStream(src);\n"
            "  const w = fs.createWriteStream(dst);\n"
            "  r.pipe(w);\n"
            "}"
        ),
        "explanation": "에러 시 stream 닫히지 않음. FD 누수. error 이벤트 처리 없음.",
        "fix": "pipeline + error 처리.",
        "fix_code": (
            "import { pipeline } from 'stream/promises';\n"
            "import fs from 'fs';\n"
            "export async function copy(src: string, dst: string) {\n"
            "  await pipeline(\n"
            "    fs.createReadStream(src),\n"
            "    fs.createWriteStream(dst),\n"
            "  );\n"
            "}"
        ),
        "note": "pipeline 이 에러 시 자동 destroy 호출.",
    },
    {
        "lang": "ts",
        "file": "src/listener.ts",
        "label": "addEventListener removeEventListener 미호출",
        "buggy_code": (
            "function setup() {\n"
            "  window.addEventListener('resize', onResize);\n"
            "  window.addEventListener('scroll', onScroll);\n"
            "}\n"
            "// component unmount 시 remove 안 됨"
        ),
        "explanation": "리스너 누적 → 메모리 누수, onResize 가 unmount 된 컴포넌트 ref 잡고 있어 detached node 도 GC 안됨.",
        "fix": "cleanup 반환.",
        "fix_code": (
            "function setup(): () => void {\n"
            "  window.addEventListener('resize', onResize);\n"
            "  window.addEventListener('scroll', onScroll);\n"
            "  return () => {\n"
            "    window.removeEventListener('resize', onResize);\n"
            "    window.removeEventListener('scroll', onScroll);\n"
            "  };\n"
            "}\n"
            "// React: useEffect(() => setup(), []);"
        ),
        "note": "cleanup 함수 반환 패턴 — React/Vue 모두 호환.",
    },
    {
        "lang": "ts",
        "file": "src/timer.ts",
        "label": "setInterval clear 누락",
        "buggy_code": (
            "function startPolling() {\n"
            "  setInterval(async () => {\n"
            "    const data = await fetch('/api/status').then(r => r.json());\n"
            "    update(data);\n"
            "  }, 1000);\n"
            "}"
        ),
        "explanation": "clearInterval 호출처 없음. 페이지 이동/탭 전환 후에도 계속 fetch. 메모리+네트워크 누수.",
        "fix": "id 반환 + cleanup.",
        "fix_code": (
            "export function startPolling(): () => void {\n"
            "  const id = setInterval(async () => {\n"
            "    try {\n"
            "      const data = await fetch('/api/status').then(r => r.json());\n"
            "      update(data);\n"
            "    } catch (e) { console.warn('poll failed', e); }\n"
            "  }, 1000);\n"
            "  return () => clearInterval(id);\n"
            "}"
        ),
        "note": "cleanup 호출자 책임으로 명시.",
    },
    {
        "lang": "ts",
        "file": "src/socket.ts",
        "label": "WebSocket close 누락",
        "buggy_code": (
            "function connect() {\n"
            "  const ws = new WebSocket('wss://example.com');\n"
            "  ws.onmessage = (e) => handle(e.data);\n"
            "}"
        ),
        "explanation": "ws.close() 호출처 없음. 라우트 전환마다 새 connection. 서버는 유효한 connection 유지 → FD 폭증.",
        "fix": "cleanup + onerror 핸들링.",
        "fix_code": (
            "export function connect(): () => void {\n"
            "  const ws = new WebSocket('wss://example.com');\n"
            "  ws.onmessage = (e) => handle(e.data);\n"
            "  ws.onerror = (e) => console.error('ws error', e);\n"
            "  return () => {\n"
            "    if (ws.readyState === WebSocket.OPEN) ws.close(1000, 'client cleanup');\n"
            "  };\n"
            "}"
        ),
        "note": "정상 종료 코드 1000 + cleanup 함수.",
    },
    {
        "lang": "py",
        "file": "app/lock.py",
        "label": "threading.Lock acquire/release 비대칭",
        "buggy_code": (
            "lock = threading.Lock()\n"
            "def critical():\n"
            "    lock.acquire()\n"
            "    do_work()  # 예외 시 lock 영구 소유\n"
            "    lock.release()"
        ),
        "explanation": "do_work 예외 시 release 미실행 → deadlock. 다음 호출자 영원히 wait.",
        "fix": "with 문.",
        "fix_code": (
            "lock = threading.Lock()\n"
            "def critical() -> None:\n"
            "    with lock:\n"
            "        do_work()"
        ),
        "note": "with 는 예외에도 release 보장.",
    },
    {
        "lang": "py",
        "file": "app/temp.py",
        "label": "tempfile 수동 + 정리 누락",
        "buggy_code": (
            "def make_temp():\n"
            "    path = '/tmp/' + uuid.uuid4().hex\n"
            "    with open(path, 'w') as f:\n"
            "        f.write(generate())\n"
            "    return path"
        ),
        "explanation": "/tmp 에 파일 누적. 호출자가 삭제 책임 알 수 없음. /tmp 풀 가득 차면 시스템 영향.",
        "fix": "tempfile.NamedTemporaryFile + 명시적 lifecycle.",
        "fix_code": (
            "import tempfile\n"
            "from contextlib import contextmanager\n"
            "@contextmanager\n"
            "def make_temp():\n"
            "    with tempfile.NamedTemporaryFile(\n"
            "        mode='w', delete=True, suffix='.tmp', encoding='utf-8'\n"
            "    ) as f:\n"
            "        f.write(generate())\n"
            "        f.flush()\n"
            "        yield f.name"
        ),
        "note": "with 블록 종료 시 자동 삭제, 호출자 책임 명확.",
    },
]


# ============================================================
# Generator: 7-turn review sample
# ============================================================

def make_review_sample(p: dict) -> dict:
    """7-turn 코드 리뷰 샘플 생성.

    1. user: [Active file] + 리뷰 요청
    2. assistant: read_file tool_call
    3. tool: 버기 코드
    4. assistant: 근본 문제 + 진짜 해결 + edit_file tool_call
    5. tool: File modified
    6. assistant: 짧은 마무리
    """
    # old_string: 버기 코드 첫 60자 (edit_file 의 식별자)
    buggy_snippet = p["buggy_code"][:60]
    label = p.get("label", "안티패턴")

    review_text = (
        f"**근본 문제: {label}**\n\n"
        f"```{p['lang']}\n{p['buggy_code']}\n```\n\n"
        f"{p['explanation']}\n\n"
        f"**진짜 해결**: {p['fix']}\n\n"
        "적용:\n\n"
        + tc("edit_file", {
            "path": p["file"],
            "oldString": buggy_snippet,
            "newString": p["fix_code"],
        })
    )

    closing = "개선 완료. " + p.get("note", "안티패턴 제거했습니다.")

    return m([
        syss(),
        user(f"[Active file: {p['file']}]\n이 코드 리뷰해줘"),
        assistant(tc("read_file", {"path": p["file"]})),
        tool(p["buggy_code"]),
        assistant(review_text),
        tool("File modified"),
        assistant(closing),
    ])


# ============================================================
# 시나리오별 100 샘플 생성 — random.choice 로 패턴 변형
# ============================================================

def _generate(patterns: list, count: int = 100) -> list:
    return [make_review_sample(random.choice(patterns)) for _ in range(count)]


SCENARIO_R5 = _generate(OVERENG_PATTERNS, 100)
SCENARIO_R6 = _generate(ERROR_PATTERNS, 100)
SCENARIO_R7 = _generate(TYPE_PATTERNS, 100)
SCENARIO_R8 = _generate(N1_PATTERNS, 100)
SCENARIO_R9 = _generate(RESOURCE_PATTERNS, 100)


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/review_v4_b.jsonl")
    args = parser.parse_args()

    all_data = SCENARIO_R5 + SCENARIO_R6 + SCENARIO_R7 + SCENARIO_R8 + SCENARIO_R9
    assert len(all_data) == 500, f"expected 500, got {len(all_data)}"

    out_path = args.output
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("작성 완료: %s — %d 샘플", out_path, len(all_data))
    logger.info(
        "R-5: %d, R-6: %d, R-7: %d, R-8: %d, R-9: %d",
        len(SCENARIO_R5), len(SCENARIO_R6), len(SCENARIO_R7),
        len(SCENARIO_R8), len(SCENARIO_R9),
    )
    logger.info(
        "패턴: OVERENG=%d ERROR=%d TYPE=%d N1=%d RESOURCE=%d",
        len(OVERENG_PATTERNS), len(ERROR_PATTERNS), len(TYPE_PATTERNS),
        len(N1_PATTERNS), len(RESOURCE_PATTERNS),
    )


if __name__ == "__main__":
    main()
