"""화랑 LoRA v4 학습 데이터 — 깊은 코드 리뷰 500 샘플 (Part 1).

시나리오 4개 × 125 = 500 샘플:
- R-1: Race condition (125)
- R-2: Memory leak (125)
- R-3: O(n²) → O(n) (125)
- R-4: 보안 취약점 (125)

각 시나리오는 패턴 list (10+개) × 변형 generator 로 생성. 모든 샘플 7-turn:
1. user: "[Active file: X]\n이 코드 리뷰해줘"
2. assistant: read_file tool_call
3. tool: 버기 코드
4. assistant: 근본 문제 + 표면 fix 가 안 되는 이유 + 진짜 해결 + edit_file
5. tool: File modified
6. assistant: 짧은 마무리
"""
import random
import json
import os
import argparse

from build_tools_multiturn import (
    m,
    sys as _sys,
    user,
    assistant,
    tool,
    tc,
    TOOLS_DESC,  # noqa: F401 (import 검증용)
)


def syss():
    return _sys()


random.seed(2030)


# ============================================================
# 변형용 한국어 보조 표현 풀 (모든 시나리오 공통)
# ============================================================

REVIEW_OPENERS = [
    "이 코드 리뷰해줘",
    "이 파일 한번 봐줘 — 뭔가 이상해",
    "동작은 하는 것 같은데 코드 리뷰 부탁",
    "PR 올리기 전에 검토 부탁해",
    "이 코드 문제 있을까?",
    "왠지 불안한데 봐줄 수 있어?",
    "코드 리뷰 좀 해주세요",
    "이거 운영 배포해도 되는지 봐줘",
    "테스트는 통과하는데 한번 봐줘",
    "리뷰어 입장에서 봐줘",
    "버그 의심된다 — 검토 부탁",
    "이 함수 안전한지 봐줘",
    "프로덕션에 올려도 되겠어?",
]

CLOSING_LINES = [
    "근본 원인을 제거했으니 동시 요청 / 부하 상황에서도 안전합니다.",
    "표면 증상이 아니라 원인을 잡았습니다. 회귀 테스트도 추가 권장.",
    "수정 완료. 동일 패턴이 다른 파일에도 있을 수 있으니 grep 한번 돌려보세요.",
    "이걸로 해당 클래스의 버그는 막았습니다. CI 에 lint rule 추가도 고려.",
    "fix 적용. 단위 테스트로 race / leak / 성능 회귀를 잡아두세요.",
    "패치 완료. 코드 리뷰 체크리스트에 같은 패턴을 추가해두면 재발 방지에 도움.",
    "수정했습니다. 운영 배포 전에 staging 에서 부하 테스트 한번 권장.",
    "근본 fix 적용. 같은 안티패턴이 codebase 전반에 없는지 한번 훑어보세요.",
]


def pick(lst):
    return random.choice(lst)


# ============================================================
# 공용 generator: 6-turn 리뷰 샘플
# ============================================================

def make_review_sample(p, root_label, surface_fix_reason, closing=None):
    """공용 리뷰 샘플 generator.

    p: 패턴 dict — file, lang, buggy_code, explanation, fix, fix_code, (cvss optional)
    root_label: "Race condition" / "Memory leak" / "O(n²) 알고리즘" / "보안 취약점 (XSS)"
    surface_fix_reason: 표면 fix 가 안 되는 이유 한 문장
    """
    opener = pick(REVIEW_OPENERS)
    close = closing or pick(CLOSING_LINES)

    cvss_line = ""
    if "cvss" in p:
        cvss_line = f"\n\n**CVSS 추정**: {p['cvss']}"

    # edit_file 의 oldString 은 buggy_code 의 앞 80자 정도만 사용 (안정성)
    old_snippet = p["buggy_code"][:80]

    asst_main = (
        f"**근본 문제: {root_label}**\n\n"
        f"```{p['lang']}\n{p['buggy_code']}\n```\n\n"
        f"{p['explanation']}{cvss_line}\n\n"
        f"**표면 fix 가 안 되는 이유**: {surface_fix_reason}\n\n"
        f"**진짜 해결**:\n"
        f"1. {p['fix']} (추천)\n"
        f"2. 차선책 — 동시성 / 라이프사이클 / 알고리즘 자체를 바꾸지 않으면 운빨에 의존하므로 비추.\n\n"
        f"적용:\n"
        + tc("edit_file", {"path": p["file"], "oldString": old_snippet, "newString": p["fix_code"]})
    )

    return m([
        syss(),
        user(f"[Active file: {p['file']}]\n{opener}"),
        assistant(tc("read_file", {"path": p["file"]})),
        tool(p["buggy_code"]),
        assistant(asst_main),
        tool("File modified"),
        assistant(close),
    ])


# ============================================================
# R-1: Race condition (125)
# ============================================================

RACE_PATTERNS = [
    {
        "lang": "ts", "file": "src/counter.ts",
        "buggy_code": "let count = 0;\nasync function increment() {\n  const current = await readCount();\n  count = current + 1;\n  await writeCount(count);\n}",
        "explanation": "current 읽기 → +1 → 쓰기 사이에 다른 동시 요청이 같은 current 값을 읽으면 둘 다 같은 값에 +1 → 카운트 손실 (lost update).",
        "fix": "DB atomic increment 사용",
        "fix_code": "async function increment() {\n  await db.counter.update({ data: { count: { increment: 1 } } });\n}",
    },
    {
        "lang": "py", "file": "app/cache.py",
        "buggy_code": "if key not in cache:\n    cache[key] = compute()\n    return cache[key]\nreturn cache[key]",
        "explanation": "check-then-act 패턴 race — 두 코루틴이 모두 not in 으로 보고 둘 다 compute() 실행 → 중복 비용 + 후속 write 가 서로 덮어씀.",
        "fix": "asyncio.Lock 으로 single-flight 보장",
        "fix_code": "async with cache_lock:\n    if key not in cache:\n        cache[key] = await compute()\nreturn cache[key]",
    },
    {
        "lang": "go", "file": "server.go",
        "buggy_code": "if !exists(id) {\n    create(id)\n}",
        "explanation": "동시 두 요청이 모두 not exists 보고 둘 다 create() 호출 → duplicate row 또는 unique violation panic.",
        "fix": "DB unique constraint + INSERT ... ON CONFLICT DO NOTHING",
        "fix_code": "_, err := db.Exec(`INSERT INTO items (id) VALUES ($1) ON CONFLICT (id) DO NOTHING`, id)",
    },
    {
        "lang": "java", "file": "src/main/java/Wallet.java",
        "buggy_code": "public void transfer(long amount) {\n    long b = balance;\n    if (b < amount) throw new InsufficientFundsException();\n    balance = b - amount;\n}",
        "explanation": "TOCTOU — 잔액 검사와 차감 사이에 다른 스레드가 같은 b 를 읽고 차감하면 마이너스 잔액 가능.",
        "fix": "synchronized 또는 DB 트랜잭션 + row lock (SELECT ... FOR UPDATE)",
        "fix_code": "public synchronized void transfer(long amount) {\n    if (balance < amount) throw new InsufficientFundsException();\n    balance -= amount;\n}",
    },
    {
        "lang": "py", "file": "app/queue_worker.py",
        "buggy_code": "task = next_pending_task()\nif task:\n    process(task)\n    mark_done(task.id)",
        "explanation": "worker N개 동시 실행 시 모두 같은 task 를 pending 으로 보고 동시 처리 → 중복 실행, 부작용 두 번.",
        "fix": "DB UPDATE ... WHERE status='pending' RETURNING * 로 atomic claim",
        "fix_code": "row = db.execute(\"UPDATE tasks SET status='processing' WHERE id=(SELECT id FROM tasks WHERE status='pending' LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *\")\nif row:\n    process(row); mark_done(row.id)",
    },
    {
        "lang": "ts", "file": "src/rate_limit.ts",
        "buggy_code": "const used = await redis.get(key);\nif (Number(used) < limit) {\n  await redis.set(key, Number(used) + 1);\n  next();\n}",
        "explanation": "GET → SET 사이에 다른 요청이 같은 used 를 읽으면 한도 초과 통과 발생 — rate limit 무력화.",
        "fix": "Redis INCR (원자적) + EXPIRE 사용",
        "fix_code": "const n = await redis.incr(key);\nif (n === 1) await redis.expire(key, 60);\nif (n > limit) return res.status(429).end();\nnext();",
    },
    {
        "lang": "py", "file": "billing/charge.py",
        "buggy_code": "if not already_charged(order_id):\n    charge_card(order)\n    mark_charged(order_id)",
        "explanation": "결제 멱등성 race — webhook 중복 또는 retry 시 두 번째 호출이 mark 전에 들어오면 이중 결제.",
        "fix": "idempotency_key 를 DB unique 키로 INSERT 먼저, 충돌 시 skip",
        "fix_code": "try:\n    db.execute(\"INSERT INTO charges (idempotency_key, order_id) VALUES (%s, %s)\", (key, order_id))\nexcept UniqueViolation:\n    return  # 이미 결제됨\ncharge_card(order)\ndb.execute(\"UPDATE charges SET status='done' WHERE idempotency_key=%s\", (key,))",
    },
    {
        "lang": "js", "file": "src/inventory.js",
        "buggy_code": "const stock = await getStock(sku);\nif (stock > 0) {\n  await setStock(sku, stock - 1);\n  await ship(sku);\n}",
        "explanation": "재고 1개 남았을 때 동시 두 주문이 모두 stock>0 보고 둘 다 ship → 음수 재고 + 배송 사고.",
        "fix": "조건부 UPDATE (UPDATE ... SET stock=stock-1 WHERE stock>0) 후 affectedRows 확인",
        "fix_code": "const r = await db.query(\"UPDATE inventory SET stock=stock-1 WHERE sku=? AND stock>0\", [sku]);\nif (r.affectedRows === 0) throw new OutOfStockError();\nawait ship(sku);",
    },
    {
        "lang": "rs", "file": "src/session.rs",
        "buggy_code": "if !sessions.contains_key(&id) {\n    sessions.insert(id, Session::new());\n}",
        "explanation": "HashMap 동시 접근 — 두 스레드가 모두 contains_key=false 보고 둘 다 insert → 늦은 쪽이 첫 세션을 덮어씀.",
        "fix": "DashMap entry().or_insert_with() 또는 RwLock + 더블체크",
        "fix_code": "sessions.entry(id).or_insert_with(Session::new);",
    },
    {
        "lang": "py", "file": "app/lazy_init.py",
        "buggy_code": "_client = None\ndef get_client():\n    global _client\n    if _client is None:\n        _client = build_client()\n    return _client",
        "explanation": "lazy singleton race — 첫 호출 두 스레드가 동시 None 보고 둘 다 build_client() → 비싼 초기화 두 번 + 싱글톤 보장 깨짐.",
        "fix": "threading.Lock 으로 double-checked locking, 또는 functools.lru_cache 활용",
        "fix_code": "from functools import lru_cache\n@lru_cache(maxsize=1)\ndef get_client():\n    return build_client()",
    },
    {
        "lang": "go", "file": "metrics.go",
        "buggy_code": "var counter int\nfunc Inc() {\n    counter++\n}",
        "explanation": "Goroutine 동시 ++는 read-modify-write 비원자 → 일부 증가가 손실 (data race, -race 플래그로 감지 가능).",
        "fix": "sync/atomic.AddInt64 또는 sync.Mutex 사용",
        "fix_code": "var counter int64\nfunc Inc() { atomic.AddInt64(&counter, 1) }",
    },
    {
        "lang": "ts", "file": "src/feature_flag.ts",
        "buggy_code": "if (!flags[user.id]) {\n  flags[user.id] = await fetchFlags(user.id);\n}\nreturn flags[user.id];",
        "explanation": "캐시 stampede — 한 사용자에 대한 첫 요청들이 동시에 fetchFlags 호출 → 백엔드 부하 폭증.",
        "fix": "in-flight Promise 캐싱 (single-flight)",
        "fix_code": "if (!flagsP[user.id]) flagsP[user.id] = fetchFlags(user.id);\nreturn flagsP[user.id];",
    },
    {
        "lang": "py", "file": "app/file_write.py",
        "buggy_code": "with open(path, 'r') as f: data = json.load(f)\ndata['count'] += 1\nwith open(path, 'w') as f: json.dump(data, f)",
        "explanation": "파일 read → modify → write 비원자 — 다른 프로세스가 사이에 쓰면 한 쪽 변경 손실.",
        "fix": "fcntl.flock 으로 advisory lock, 또는 atomic rename (write to tmp + os.replace)",
        "fix_code": "import fcntl, os, tempfile, json\nwith open(path, 'r+') as f:\n    fcntl.flock(f, fcntl.LOCK_EX)\n    data = json.load(f)\n    data['count'] += 1\n    f.seek(0); f.truncate(); json.dump(data, f)",
    },
]

# 변형: 다양한 표면 fix 거부 이유
RACE_SURFACE_REASONS = [
    "lock 없이 ordering 만 바꾸는 건 운빨에 의존. 동시성 자체를 직렬화하거나 atomic 연산으로 바꿔야 안전.",
    "재시도 / 예외 캐치로 가리는 건 증상 완화일 뿐. 한 번이라도 race 가 발생하면 데이터가 깨짐.",
    "sleep() 으로 타이밍 조정하는 건 부하 상황에서 즉시 무너짐. 진짜 동기화 primitive 가 필요.",
    "if 분기 추가로는 race window 가 줄어들 뿐 사라지지 않음 — 구조적 fix 필요.",
    "프로세스 1개로 운영하는 건 확장성을 포기하는 것. 분산 환경에서도 안전해야 진짜 fix.",
]


def gen_race():
    p = random.choice(RACE_PATTERNS)
    reason = random.choice(RACE_SURFACE_REASONS)
    return make_review_sample(p, "Race condition", reason)


SCENARIO_R1 = [gen_race() for _ in range(125)]


# ============================================================
# R-2: Memory leak (125)
# ============================================================

LEAK_PATTERNS = [
    {
        "lang": "tsx", "file": "src/Chart.tsx",
        "buggy_code": "useEffect(() => {\n  const id = setInterval(refresh, 1000);\n}, []);",
        "explanation": "컴포넌트 unmount 후에도 interval 이 살아있어 setState 호출 → 'Cannot update unmounted component' 경고 + 메모리 누수.",
        "fix": "cleanup 함수에서 clearInterval",
        "fix_code": "useEffect(() => {\n  const id = setInterval(refresh, 1000);\n  return () => clearInterval(id);\n}, []);",
    },
    {
        "lang": "tsx", "file": "src/Live.tsx",
        "buggy_code": "useEffect(() => {\n  const ws = new WebSocket(url);\n  ws.onmessage = (e) => setData(JSON.parse(e.data));\n}, [url]);",
        "explanation": "url 바뀌거나 unmount 시 이전 WebSocket 이 close 되지 않음 → 연결 누적, 메시지가 stale state 에 쓰임.",
        "fix": "cleanup 에서 ws.close() 호출",
        "fix_code": "useEffect(() => {\n  const ws = new WebSocket(url);\n  ws.onmessage = (e) => setData(JSON.parse(e.data));\n  return () => ws.close();\n}, [url]);",
    },
    {
        "lang": "tsx", "file": "src/Search.tsx",
        "buggy_code": "useEffect(() => {\n  window.addEventListener('resize', onResize);\n}, []);",
        "explanation": "리스너 등록만 하고 제거 안 함 — 컴포넌트 unmount 후에도 onResize 가 호출됨, mount/unmount 반복 시 리스너 무한 누적.",
        "fix": "removeEventListener 를 cleanup 에",
        "fix_code": "useEffect(() => {\n  window.addEventListener('resize', onResize);\n  return () => window.removeEventListener('resize', onResize);\n}, []);",
    },
    {
        "lang": "ts", "file": "src/api/client.ts",
        "buggy_code": "export async function fetchUser(id: string) {\n  const res = await fetch(`/api/users/${id}`);\n  return res.json();\n}",
        "explanation": "AbortController 가 없어 사용자가 화면을 빨리 전환해도 이전 요청이 끝까지 진행 → 메모리 + 네트워크 + race 가능.",
        "fix": "AbortController 받아서 fetch 의 signal 옵션으로 전달",
        "fix_code": "export async function fetchUser(id: string, signal?: AbortSignal) {\n  const res = await fetch(`/api/users/${id}`, { signal });\n  return res.json();\n}",
    },
    {
        "lang": "py", "file": "app/cache.py",
        "buggy_code": "_cache = {}\ndef get(key):\n    if key not in _cache:\n        _cache[key] = expensive(key)\n    return _cache[key]",
        "explanation": "TTL / max size 없는 dict 캐시 — 키 종류가 무한대(예: user id) 면 메모리가 단조 증가, OOM 까지.",
        "fix": "functools.lru_cache(maxsize=...) 또는 cachetools.TTLCache",
        "fix_code": "from functools import lru_cache\n@lru_cache(maxsize=10000)\ndef get(key):\n    return expensive(key)",
    },
    {
        "lang": "py", "file": "app/worker.py",
        "buggy_code": "async def main():\n    for item in items:\n        asyncio.create_task(process(item))",
        "explanation": "create_task 결과를 어디에도 잡지 않으면 GC 가 task 를 거둬가서 silent 실패 + 'Task was destroyed but it is pending' 경고. 또는 task 가 strong ref 없으면 메모리에서 사라지며 결과 손실.",
        "fix": "task 를 set 에 보관 후 done callback 으로 제거, 또는 asyncio.gather 사용",
        "fix_code": "async def main():\n    tasks = [asyncio.create_task(process(i)) for i in items]\n    await asyncio.gather(*tasks)",
    },
    {
        "lang": "js", "file": "src/server.js",
        "buggy_code": "const sessions = {};\napp.use((req, res, next) => {\n  sessions[req.ip] = sessions[req.ip] || { hits: 0 };\n  sessions[req.ip].hits++;\n  next();\n});",
        "explanation": "process-local 객체에 무제한 ip 키를 적재 → 장기 가동 시 메모리 단조 증가 + 재시작 시 데이터 손실.",
        "fix": "Redis / lru-cache 등 외부 저장 + TTL",
        "fix_code": "const LRU = require('lru-cache');\nconst sessions = new LRU({ max: 50000, ttl: 1000 * 60 * 30 });\napp.use((req, res, next) => {\n  const s = sessions.get(req.ip) || { hits: 0 };\n  s.hits++;\n  sessions.set(req.ip, s);\n  next();\n});",
    },
    {
        "lang": "java", "file": "src/main/java/Listener.java",
        "buggy_code": "public class Bus {\n  static List<Listener> listeners = new ArrayList<>();\n  public static void register(Listener l) { listeners.add(l); }\n}",
        "explanation": "static 컬렉션이 listener 의 strong reference 를 영구 보유 → listener 의 outer class 까지 GC 불가, classic Java leak.",
        "fix": "WeakReference 또는 명시적 unregister API 제공",
        "fix_code": "public class Bus {\n  static List<WeakReference<Listener>> listeners = new ArrayList<>();\n  public static void register(Listener l) { listeners.add(new WeakReference<>(l)); }\n  public static void fire(Event e) {\n    listeners.removeIf(r -> r.get() == null);\n    for (var r : listeners) { var l = r.get(); if (l != null) l.on(e); }\n  }\n}",
    },
    {
        "lang": "py", "file": "app/db.py",
        "buggy_code": "def query(sql):\n    conn = psycopg2.connect(DSN)\n    cur = conn.cursor()\n    cur.execute(sql)\n    return cur.fetchall()",
        "explanation": "connection / cursor 를 close 하지 않아 매 호출마다 새 connection 누적 → DB 의 max_connections 초과로 장애.",
        "fix": "context manager (with) + connection pool",
        "fix_code": "from contextlib import contextmanager\nfrom psycopg2.pool import SimpleConnectionPool\npool = SimpleConnectionPool(1, 20, dsn=DSN)\n@contextmanager\ndef get_conn():\n    c = pool.getconn()\n    try: yield c\n    finally: pool.putconn(c)\ndef query(sql):\n    with get_conn() as conn, conn.cursor() as cur:\n        cur.execute(sql); return cur.fetchall()",
    },
    {
        "lang": "go", "file": "fetcher.go",
        "buggy_code": "resp, _ := http.Get(url)\nbody, _ := io.ReadAll(resp.Body)\nreturn body",
        "explanation": "resp.Body.Close() 호출이 없어 HTTP keep-alive connection 이 풀에 반환되지 않음 → fd leak, eventually 'too many open files'.",
        "fix": "defer resp.Body.Close() 추가 + 에러 체크",
        "fix_code": "resp, err := http.Get(url)\nif err != nil { return nil, err }\ndefer resp.Body.Close()\nreturn io.ReadAll(resp.Body)",
    },
    {
        "lang": "ts", "file": "src/state/store.ts",
        "buggy_code": "store.subscribe(() => {\n  console.log('changed', store.getState());\n});",
        "explanation": "subscribe 가 unsubscribe 함수를 반환하는데 무시 → 모듈/컴포넌트가 사라져도 콜백이 계속 실행되어 누수.",
        "fix": "반환된 unsubscribe 를 보관하고 lifecycle 종료 시 호출",
        "fix_code": "const unsub = store.subscribe(() => {\n  console.log('changed', store.getState());\n});\n// onDestroy / cleanup 에서 unsub();",
    },
    {
        "lang": "tsx", "file": "src/Modal.tsx",
        "buggy_code": "useEffect(() => {\n  const t = setTimeout(() => setOpen(false), 5000);\n}, []);",
        "explanation": "Modal 이 unmount 되어도 setTimeout 이 살아있어 5초 뒤 unmounted 컴포넌트 setState — leak + 경고.",
        "fix": "cleanup 에서 clearTimeout",
        "fix_code": "useEffect(() => {\n  const t = setTimeout(() => setOpen(false), 5000);\n  return () => clearTimeout(t);\n}, []);",
    },
]

LEAK_SURFACE_REASONS = [
    "ref 만 늘려서 가리는 건 leak 을 deferred 시킬 뿐. cleanup 라이프사이클 자체를 추가해야 함.",
    "process 를 주기적으로 재시작하는 건 운영 회피. 코드 수준에서 자원을 회수해야 진짜 fix.",
    "max heap 만 늘리는 건 시간만 벌 뿐 — 누수 자체를 막아야 장기 안정.",
    "GC 가 알아서 해주리라 기대하는 건 위험 — 외부 자원(소켓/타이머/파일 fd) 은 GC 영역 밖.",
    "에러 무시 / try-catch 로 감추는 건 leak 을 보이지 않게 만들 뿐 더 빠르게 늘림.",
]


def gen_leak():
    p = random.choice(LEAK_PATTERNS)
    reason = random.choice(LEAK_SURFACE_REASONS)
    return make_review_sample(p, "Memory leak", reason)


SCENARIO_R2 = [gen_leak() for _ in range(125)]


# ============================================================
# R-3: O(n²) → O(n) (125)
# ============================================================

N2_PATTERNS = [
    {
        "lang": "ts", "file": "src/users.ts",
        "buggy_code": "users.forEach(u => {\n  if (admins.includes(u.id)) u.role = 'admin';\n});",
        "explanation": "Array.includes() 는 O(n) → 전체 O(n×m). users / admins 가 1만 개면 10억 비교.",
        "fix": "admins 를 Set 으로 변환하면 has() 가 O(1) → 전체 O(n+m)",
        "fix_code": "const adminSet = new Set(admins);\nusers.forEach(u => {\n  if (adminSet.has(u.id)) u.role = 'admin';\n});",
    },
    {
        "lang": "py", "file": "app/dedupe.py",
        "buggy_code": "result = []\nfor x in items:\n    if x not in result:\n        result.append(x)",
        "explanation": "list 의 'in' 은 O(n) → 전체 O(n²). 100k items 면 10^10 연산.",
        "fix": "set 으로 seen 추적 (O(1) lookup), 순서 유지 필요시 dict.fromkeys",
        "fix_code": "seen = set()\nresult = []\nfor x in items:\n    if x not in seen:\n        seen.add(x); result.append(x)",
    },
    {
        "lang": "py", "file": "app/merge_df.py",
        "buggy_code": "for i, row in df_a.iterrows():\n    match = df_b[df_b['id'] == row['id']]\n    df_a.at[i, 'val'] = match['val'].iloc[0]",
        "explanation": "iterrows + boolean indexing → 매 행마다 df_b 전체 스캔, O(n×m). 또한 iterrows 자체가 매우 느림.",
        "fix": "pandas merge / map 사용 (해시 기반 join, 사실상 O(n+m))",
        "fix_code": "df_a = df_a.merge(df_b[['id', 'val']], on='id', how='left')",
    },
    {
        "lang": "ts", "file": "src/diff.ts",
        "buggy_code": "const removed = oldList.filter(o => !newList.find(n => n.id === o.id));",
        "explanation": "filter 안에서 find — 외부 n × 내부 m = O(n×m). 큰 리스트에서 UI freeze 의 단골 원인.",
        "fix": "newList 의 id 를 Set 으로 미리 변환",
        "fix_code": "const newIds = new Set(newList.map(n => n.id));\nconst removed = oldList.filter(o => !newIds.has(o.id));",
    },
    {
        "lang": "py", "file": "app/group.py",
        "buggy_code": "groups = {}\nfor item in items:\n    key = item['cat']\n    if key not in groups:\n        groups[key] = []\n    if item not in groups[key]:\n        groups[key].append(item)",
        "explanation": "그룹별 'item not in list' 가 O(평균 그룹 크기) → 큰 그룹에서 O(n²) 로 폭발.",
        "fix": "set 또는 dict 로 dedupe 키만 추적",
        "fix_code": "from collections import defaultdict\ngroups = defaultdict(list)\nseen = set()\nfor item in items:\n    k = (item['cat'], item['id'])\n    if k not in seen:\n        seen.add(k); groups[item['cat']].append(item)",
    },
    {
        "lang": "js", "file": "src/sort_search.js",
        "buggy_code": "for (let i = 0; i < arr.length; i++) {\n  for (let j = 0; j < arr.length; j++) {\n    if (i !== j && arr[i].key === arr[j].key) duplicates.push(arr[i]);\n  }\n}",
        "explanation": "이중 for 로 모든 쌍 비교 — 전형적 O(n²). 1만개면 10^8 연산, JS 메인 스레드 블록.",
        "fix": "key 별 count 를 Map 으로 한 번 순회",
        "fix_code": "const cnt = new Map();\nfor (const a of arr) cnt.set(a.key, (cnt.get(a.key) || 0) + 1);\nconst duplicates = arr.filter(a => cnt.get(a.key) > 1);",
    },
    {
        "lang": "py", "file": "app/score.py",
        "buggy_code": "for u in users:\n    u['rank'] = sum(1 for o in users if o['score'] > u['score']) + 1",
        "explanation": "각 사용자마다 전체 사용자 비교 → O(n²). 10만 명이면 10^10 연산.",
        "fix": "정렬 한 번 후 인덱스로 rank 부여 → O(n log n)",
        "fix_code": "users.sort(key=lambda x: -x['score'])\nfor i, u in enumerate(users):\n    u['rank'] = i + 1",
    },
    {
        "lang": "ts", "file": "src/intersect.ts",
        "buggy_code": "const common = a.filter(x => b.includes(x));",
        "explanation": "filter × includes = O(n×m). 두 배열이 각 10만이면 10^10 비교.",
        "fix": "한 쪽을 Set 으로",
        "fix_code": "const bs = new Set(b);\nconst common = a.filter(x => bs.has(x));",
    },
    {
        "lang": "py", "file": "app/levenshtein.py",
        "buggy_code": "results = []\nfor q in queries:\n    for d in docs:\n        if levenshtein(q, d.text) < 3:\n            results.append((q, d))",
        "explanation": "edit distance 자체가 O(L²) 인데 그 위에 다시 O(n×m) 중첩 → 사실상 O(n×m×L²). 수만 건이면 분 단위.",
        "fix": "BK-tree / FAISS / 사전 토크나이즈 후 inverted index",
        "fix_code": "from rapidfuzz import process, fuzz\ndoc_texts = [d.text for d in docs]\nresults = []\nfor q in queries:\n    for text, score, idx in process.extract(q, doc_texts, scorer=fuzz.ratio, limit=10):\n        results.append((q, docs[idx]))",
    },
    {
        "lang": "java", "file": "src/main/java/Match.java",
        "buggy_code": "for (User u : users) {\n  for (Order o : orders) {\n    if (o.getUserId().equals(u.getId())) u.addOrder(o);\n  }\n}",
        "explanation": "users × orders 중첩 — n×m. 10k×100k 면 10^9 비교.",
        "fix": "orders 를 userId 로 그룹핑 (HashMap) 한 번 만들고 lookup",
        "fix_code": "Map<Long, List<Order>> byUser = orders.stream().collect(Collectors.groupingBy(Order::getUserId));\nfor (User u : users) u.setOrders(byUser.getOrDefault(u.getId(), List.of()));",
    },
    {
        "lang": "py", "file": "app/window.py",
        "buggy_code": "for i in range(len(arr)):\n    s = sum(arr[i:i+k])\n    out.append(s)",
        "explanation": "매 i 마다 sum(arr[i:i+k]) 가 O(k) → 전체 O(n×k). 슬라이딩 윈도우 클래식 안티패턴.",
        "fix": "running sum (window sum 갱신만) → O(n)",
        "fix_code": "s = sum(arr[:k]); out = [s]\nfor i in range(k, len(arr)):\n    s += arr[i] - arr[i - k]\n    out.append(s)",
    },
    {
        "lang": "ts", "file": "src/closest_pair.ts",
        "buggy_code": "let best = Infinity;\nfor (let i = 0; i < pts.length; i++)\n  for (let j = i + 1; j < pts.length; j++)\n    best = Math.min(best, dist(pts[i], pts[j]));",
        "explanation": "모든 점 쌍 거리 계산 — O(n²). 1만 점이면 5천만 비교.",
        "fix": "k-d tree / spatial hashing / divide-and-conquer 으로 O(n log n)",
        "fix_code": "// 공간 해싱: 그리드 셀 단위로 후보만 비교\nconst grid = new Map<string, Point[]>();\nconst cell = (p: Point) => `${Math.floor(p.x / D)},${Math.floor(p.y / D)}`;\nfor (const p of pts) {\n  const k = cell(p);\n  if (!grid.has(k)) grid.set(k, []);\n  grid.get(k)!.push(p);\n}\n// 인접 9칸만 비교 → 평균 O(n)",
    },
]

N2_SURFACE_REASONS = [
    "loop 안쪽을 미세 최적화해도 점근복잡도가 그대로면 입력이 커지면 즉시 무너짐.",
    "병렬화 / 스레드로 가속하는 건 상수 배 개선일 뿐 — 알고리즘 자체를 바꿔야 함.",
    "cache 추가는 동일 입력 재호출에만 의미. 이번 입력 자체에서 O(n²) 면 효과 없음.",
    "samples 줄여서 빠르게 보이는 건 임시방편. 본 데이터 크기에서 필연적으로 느려짐.",
    "lazy 화 / pagination 도 단일 batch 안에서의 O(n²) 를 못 막음 — 자료구조 교체 필요.",
]


def gen_n2():
    p = random.choice(N2_PATTERNS)
    reason = random.choice(N2_SURFACE_REASONS)
    return make_review_sample(p, "O(n²) 알고리즘", reason)


SCENARIO_R3 = [gen_n2() for _ in range(125)]


# ============================================================
# R-4: 보안 취약점 (125)
# ============================================================

SECURITY_PATTERNS = [
    {
        "lang": "js", "file": "public/render.js",
        "buggy_code": "document.getElementById('msg').innerHTML = userInput;",
        "explanation": "XSS — userInput 에 `<img src=x onerror=alert(1)>` 또는 `<script>` 가 있으면 즉시 임의 JS 실행. 세션 탈취/CSRF 까지 연쇄.",
        "fix": "textContent 사용 (또는 DOMPurify.sanitize)",
        "fix_code": "document.getElementById('msg').textContent = userInput;",
        "cvss": "6.1 (Reflected XSS)",
    },
    {
        "lang": "py", "file": "app/db.py",
        "buggy_code": "cur.execute(\"SELECT * FROM users WHERE name = '\" + name + \"'\")",
        "explanation": "SQL Injection — name 에 `' OR '1'='1` 또는 `'; DROP TABLE users;--` 으로 임의 쿼리 실행, 데이터 유출/파괴.",
        "fix": "parameterized query (placeholder 사용)",
        "fix_code": "cur.execute(\"SELECT * FROM users WHERE name = %s\", (name,))",
        "cvss": "9.8 (SQLi)",
    },
    {
        "lang": "py", "file": "app/files.py",
        "buggy_code": "with open(os.path.join(UPLOAD_DIR, filename), 'rb') as f:\n    return f.read()",
        "explanation": "Path Traversal — filename 이 `../../etc/passwd` 면 임의 파일 read. os.path.join 은 절대경로/상대경로 escape 막아주지 않음.",
        "fix": "Path.resolve() 후 UPLOAD_DIR 의 자손인지 확인",
        "fix_code": "from pathlib import Path\nbase = Path(UPLOAD_DIR).resolve()\ntarget = (base / filename).resolve()\nif not target.is_relative_to(base):\n    raise PermissionError('path traversal')\nreturn target.read_bytes()",
        "cvss": "7.5 (Path Traversal)",
    },
    {
        "lang": "py", "file": "app/calc.py",
        "buggy_code": "result = eval(user_expression)",
        "explanation": "RCE — eval 은 임의 Python 실행. `__import__('os').system('rm -rf /')` 한 줄로 서버 장악.",
        "fix": "ast.literal_eval (literal 만 허용) 또는 simpleeval / 자체 파서",
        "fix_code": "import ast\ntry:\n    result = ast.literal_eval(user_expression)\nexcept (ValueError, SyntaxError):\n    raise ValueError('invalid expression')",
        "cvss": "9.8 (RCE)",
    },
    {
        "lang": "ts", "file": "src/auth.ts",
        "buggy_code": "const decoded = jwt.decode(token);\nreq.user = decoded;",
        "explanation": "JWT decode 만 함 — 서명 검증 없음. 공격자가 헤더의 alg 를 'none' 으로 바꾸거나 임의 payload 로 조작 가능 → 인증 우회.",
        "fix": "jwt.verify(token, SECRET, { algorithms: ['HS256'] }) 사용",
        "fix_code": "try {\n  const decoded = jwt.verify(token, process.env.JWT_SECRET!, { algorithms: ['HS256'] });\n  req.user = decoded;\n} catch {\n  return res.status(401).end();\n}",
        "cvss": "9.1 (Auth bypass)",
    },
    {
        "lang": "py", "file": "app/exec.py",
        "buggy_code": "os.system(f\"convert {input_path} {output_path}\")",
        "explanation": "OS Command Injection — input_path 에 `; rm -rf ~` 가 있으면 셸이 실행. f-string + os.system 은 항상 위험.",
        "fix": "subprocess.run([...], shell=False) 인자 분리",
        "fix_code": "import subprocess\nsubprocess.run(['convert', input_path, output_path], check=True)",
        "cvss": "9.8 (Command Injection)",
    },
    {
        "lang": "ts", "file": "src/login.ts",
        "buggy_code": "if (user.password === inputPassword) { return signIn(user); }",
        "explanation": "평문 비밀번호 비교 + 타이밍 공격 가능 (== 가 짧은 prefix 에서 빨리 끝남) + DB 에 평문 저장 가정.",
        "fix": "bcrypt/argon2 해시 + constant-time compare (bcrypt.compare 자체가 타이밍 안전)",
        "fix_code": "import bcrypt from 'bcrypt';\nconst ok = await bcrypt.compare(inputPassword, user.passwordHash);\nif (ok) return signIn(user);",
        "cvss": "8.1 (Credential exposure)",
    },
    {
        "lang": "py", "file": "app/upload.py",
        "buggy_code": "filename = request.files['file'].filename\nrequest.files['file'].save('/var/www/uploads/' + filename)",
        "explanation": "사용자 제공 filename 그대로 저장 — `../../../etc/cron.d/x` 또는 `shell.php` 업로드로 RCE / overwrite 가능.",
        "fix": "secure_filename + UUID + 확장자 화이트리스트 + 별도 비실행 디렉토리",
        "fix_code": "from werkzeug.utils import secure_filename\nimport uuid, os\nALLOWED = {'png', 'jpg', 'jpeg', 'pdf'}\nname = secure_filename(request.files['file'].filename)\next = name.rsplit('.', 1)[-1].lower()\nif ext not in ALLOWED: abort(400)\nsafe = f\"{uuid.uuid4()}.{ext}\"\nrequest.files['file'].save(os.path.join('/var/uploads', safe))",
        "cvss": "8.8 (Unrestricted Upload)",
    },
    {
        "lang": "tsx", "file": "src/Comment.tsx",
        "buggy_code": "<div dangerouslySetInnerHTML={{ __html: comment.body }} />",
        "explanation": "Stored XSS — DB 의 comment.body 에 악성 스크립트가 있으면 모든 조회자에게 실행. React 가 dangerouslySetInnerHTML 이라고 경고하는 이유.",
        "fix": "DOMPurify.sanitize 거치거나 markdown-only renderer (react-markdown) 사용",
        "fix_code": "import DOMPurify from 'dompurify';\n<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(comment.body) }} />",
        "cvss": "7.4 (Stored XSS)",
    },
    {
        "lang": "py", "file": "app/redirect.py",
        "buggy_code": "@app.get('/go')\ndef go():\n    return redirect(request.args.get('url'))",
        "explanation": "Open Redirect — `/go?url=https://evil.com` 으로 사용자를 피싱 사이트로 리디렉션. 자사 도메인 신뢰를 악용.",
        "fix": "허용 호스트 화이트리스트 또는 상대경로만 허용",
        "fix_code": "from urllib.parse import urlparse\nALLOWED = {'app.example.com', 'example.com'}\ntarget = request.args.get('url', '/')\nu = urlparse(target)\nif u.netloc and u.netloc not in ALLOWED:\n    abort(400)\nreturn redirect(target)",
        "cvss": "6.1 (Open Redirect)",
    },
    {
        "lang": "ts", "file": "src/api/admin.ts",
        "buggy_code": "router.post('/admin/delete', async (req, res) => {\n  await db.user.delete({ where: { id: req.body.id } });\n  res.json({ ok: true });\n});",
        "explanation": "권한 검사 부재 (BFLA — Broken Function Level Authorization). 누구나 admin 엔드포인트 호출로 사용자 삭제 가능.",
        "fix": "auth middleware + role 검사, CSRF 토큰",
        "fix_code": "router.post('/admin/delete', requireAuth, requireRole('admin'), csrfProtect, async (req, res) => {\n  await db.user.delete({ where: { id: req.body.id } });\n  res.json({ ok: true });\n});",
        "cvss": "9.1 (Privilege Escalation)",
    },
    {
        "lang": "py", "file": "app/rng.py",
        "buggy_code": "import random\ntoken = ''.join(random.choices(string.ascii_letters + string.digits, k=32))",
        "explanation": "random 모듈은 PRNG (Mersenne Twister) 로 cryptographically secure 하지 않음 — 시드 추정으로 토큰 재현 가능. 세션/리셋/CSRF 토큰에 부적합.",
        "fix": "secrets.token_urlsafe / token_hex 사용 (CSPRNG)",
        "fix_code": "import secrets\ntoken = secrets.token_urlsafe(32)",
        "cvss": "7.5 (Insecure Random)",
    },
]

SECURITY_SURFACE_REASONS = [
    "입력 길이 / 문자 블랙리스트로 막는 건 우회가 너무 쉬움. 화이트리스트 / 안전 API 로 대체해야 함.",
    "WAF 규칙 추가는 보조 방어선일 뿐 — 코드 자체에서 안전한 함수를 써야 진짜 fix.",
    "JS 단에서 검증해도 서버는 임의 페이로드를 받음. 서버 측 안전한 처리가 필수.",
    "에러 메시지 숨기기 / 난독화는 보안이 아님. 공격 표면을 그대로 둔 채 가린 것.",
    "로그/모니터링 추가는 사후 탐지일 뿐 — 취약점 자체를 닫아야 함.",
]


def gen_security():
    p = random.choice(SECURITY_PATTERNS)
    reason = random.choice(SECURITY_SURFACE_REASONS)
    # root_label 에 패턴별 카테고리 힌트 포함
    root_map = {
        "render.js": "보안 취약점 (XSS)",
        "db.py": "보안 취약점 (SQL Injection)",
        "files.py": "보안 취약점 (Path Traversal)",
        "calc.py": "보안 취약점 (RCE via eval)",
        "auth.ts": "보안 취약점 (JWT 검증 부재)",
        "exec.py": "보안 취약점 (Command Injection)",
        "login.ts": "보안 취약점 (평문 비밀번호 + 타이밍 공격)",
        "upload.py": "보안 취약점 (Unrestricted Upload)",
        "Comment.tsx": "보안 취약점 (Stored XSS)",
        "redirect.py": "보안 취약점 (Open Redirect)",
        "admin.ts": "보안 취약점 (Broken Authorization)",
        "rng.py": "보안 취약점 (Insecure Randomness)",
    }
    fname = os.path.basename(p["file"])
    label = root_map.get(fname, "보안 취약점")
    return make_review_sample(p, label, reason)


SCENARIO_R4 = [gen_security() for _ in range(125)]


# ============================================================
# 출력
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/review_v4_a.jsonl")
    args = parser.parse_args()

    all_data = SCENARIO_R1 + SCENARIO_R2 + SCENARIO_R3 + SCENARIO_R4
    assert len(all_data) == 500, f"expected 500, got {len(all_data)}"

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[OK] {len(all_data)} 샘플 → {args.output}")
    print(f"  R-1 Race condition : {len(SCENARIO_R1)}")
    print(f"  R-2 Memory leak    : {len(SCENARIO_R2)}")
    print(f"  R-3 O(n²)          : {len(SCENARIO_R3)}")
    print(f"  R-4 Security       : {len(SCENARIO_R4)}")
    print(f"  Patterns: race={len(RACE_PATTERNS)} leak={len(LEAK_PATTERNS)} n2={len(N2_PATTERNS)} sec={len(SECURITY_PATTERNS)}")
