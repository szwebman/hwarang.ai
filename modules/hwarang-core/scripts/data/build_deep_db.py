"""화랑 AI 데이터베이스 심화 학습 데이터

N+1 문제, 쿼리 플랜 분석, 파티셔닝, 레플리카, 커넥션 풀, 데드락 디버깅 등.

사용법:
    python scripts/data/build_deep_db.py --output data/sft/deep_db.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
DBA/백엔드 전문가 수준의 데이터베이스 어시스턴트입니다.
설명은 한국어로, SQL과 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("N+1 쿼리 문제 정확히 뭐고 어떻게 해결해?",
'''N+1 문제는 1번 쿼리로 N개 항목 조회 후, 각 항목마다 추가 쿼리가 발생하는 것입니다.

```python
# ═══ N+1 문제 예시 ═══

# ❌ N+1 발생! (사용자 100명 → 쿼리 101개)
users = await db.execute("SELECT * FROM users LIMIT 100")  # 1번 쿼리

for user in users:
    # 각 사용자마다 별도 쿼리! (100번)
    posts = await db.execute(
        "SELECT * FROM posts WHERE user_id = ?", user.id
    )
    user.posts = posts

# 실행된 쿼리:
# SELECT * FROM users LIMIT 100                    ← 1번
# SELECT * FROM posts WHERE user_id = 1            ← 100번
# SELECT * FROM posts WHERE user_id = 2
# ... (총 101번!)

# ═══ 해결 방법 ═══

# ✅ 1. JOIN (한 방 쿼리)
users_with_posts = await db.execute("""
    SELECT u.*, p.id as post_id, p.title, p.content
    FROM users u
    LEFT JOIN posts p ON p.user_id = u.id
    LIMIT 100
""")
# 쿼리 1번! 하지만 사용자 데이터가 중복됨 (정규화 필요)

# ✅ 2. IN 절 (2번 쿼리로 해결)
users = await db.execute("SELECT * FROM users LIMIT 100")
user_ids = [u.id for u in users]

posts = await db.execute(
    "SELECT * FROM posts WHERE user_id = ANY($1)",
    user_ids
)  # 2번 쿼리로 끝!

# 그룹핑
from collections import defaultdict
posts_by_user = defaultdict(list)
for post in posts:
    posts_by_user[post.user_id].append(post)

for user in users:
    user.posts = posts_by_user[user.id]

# ✅ 3. DataLoader 패턴 (GraphQL/API)
from aiodataloader import DataLoader

async def batch_load_posts(user_ids):
    """여러 user_id에 대한 posts를 한 번에 로딩."""
    posts = await db.execute(
        "SELECT * FROM posts WHERE user_id = ANY($1)", list(user_ids)
    )
    posts_map = defaultdict(list)
    for post in posts:
        posts_map[post.user_id].append(post)
    # user_ids 순서에 맞게 반환 (DataLoader 규칙)
    return [posts_map[uid] for uid in user_ids]

post_loader = DataLoader(batch_load_posts)

# 개별 호출해도 자동 배치됨!
posts_1 = await post_loader.load(1)  # ┐
posts_2 = await post_loader.load(2)  # ├→ 1번의 IN 쿼리로 배치!
posts_3 = await post_loader.load(3)  # ┘

# ✅ 4. ORM별 해결법

# SQLAlchemy: selectinload
from sqlalchemy.orm import selectinload

users = await session.execute(
    select(User)
    .options(selectinload(User.posts))  # SELECT ... WHERE user_id IN (...)
    .limit(100)
)

# joinedload vs selectinload
# joinedload: JOIN으로 한 쿼리 (1:1 관계에 적합)
# selectinload: IN 절로 2번 쿼리 (1:N 관계에 적합)
# subqueryload: 서브쿼리 (복잡한 관계)

users = await session.execute(
    select(User)
    .options(
        joinedload(User.profile),           # 1:1 → JOIN
        selectinload(User.posts),           # 1:N → IN
        selectinload(User.posts, Post.comments),  # 중첩
    )
)

# Prisma: include
const users = await prisma.user.findMany({
  take: 100,
  include: {
    posts: {
      take: 10,
      orderBy: { createdAt: "desc" },
    },
    profile: true,
    _count: { select: { posts: true } },
  },
});
// Prisma가 자동으로 2번 쿼리 (users + posts IN)

# Django: prefetch_related
users = User.objects.prefetch_related(
    Prefetch("posts", queryset=Post.objects.filter(published=True)[:10])
).all()[:100]
```

N+1 탐지 방법:
```python
# 1. 쿼리 로깅
import logging
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

# 2. Django: django-debug-toolbar
# 3. Prisma: prisma.$on("query") 이벤트
# 4. nplusone 라이브러리 (자동 탐지)
from nplusone.core import profiler
with profiler.Profiler():
    # N+1 발생 시 경고 출력
    process_users()
```

핵심 규칙:
- 1:1 관계 → `JOIN` (joinedload)
- 1:N 관계 → `IN` 절 (selectinload / prefetch)
- N:M 관계 → `IN` 절 + 중간 테이블
- 항상 **쿼리 수를 로깅**해서 확인'''),

    m("EXPLAIN ANALYZE 쿼리 실행 계획 분석하는 방법 알려줘",
'''EXPLAIN ANALYZE로 쿼리 성능을 정밀 분석합니다.

```sql
-- ═══ 기본 사용법 ═══
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT u.name, COUNT(p.id) as post_count
FROM users u
LEFT JOIN posts p ON p.user_id = u.id
WHERE u.status = 'active'
  AND u.created_at > '2025-01-01'
GROUP BY u.id, u.name
ORDER BY post_count DESC
LIMIT 20;

-- ═══ 결과 읽는 법 ═══
/*
Limit (cost=1234.56..1234.78 rows=20 width=40)
       (actual time=15.234..15.312 rows=20 loops=1)
  -> Sort (cost=1234.56..1245.67 rows=4450 width=40)
          (actual time=15.230..15.280 rows=20 loops=1)
        Sort Key: (count(p.id)) DESC
        Sort Method: top-N heapsort  Memory: 27kB
    -> HashAggregate (cost=1100.00..1145.00 rows=4450 width=40)
                     (actual time=14.500..14.800 rows=4450 loops=1)
          Group Key: u.id
      -> Hash Left Join (cost=100.00..900.00 rows=40000 width=36)
                        (actual time=1.200..10.500 rows=38000 loops=1)
            Hash Cond: (p.user_id = u.id)
            -> Seq Scan on posts p (cost=0..500.00 rows=50000 width=8)
                                   (actual time=0.01..3.50 rows=50000 loops=1)
            -> Hash (cost=80.00..80.00 rows=4450 width=36)
                    (actual time=1.100..1.100 rows=4450 loops=1)
                  Buckets: 8192  Memory Usage: 350kB
              -> Index Scan using idx_users_status_created on users u
                 (cost=0.29..80.00 rows=4450 width=36)
                 (actual time=0.020..0.800 rows=4450 loops=1)
                    Index Cond: ((status = 'active') AND (created_at > '2025-01-01'))
Planning Time: 0.234 ms
Execution Time: 15.456 ms
Buffers: shared hit=1234 read=56
*/

-- ═══ 핵심 용어 해설 ═══
-- cost=시작비용..총비용: 예상 비용 (상대적 단위)
-- actual time=시작..끝: 실제 실행 시간 (ms)
-- rows: 실제 처리된 행 수
-- loops: 반복 횟수 (Nested Loop에서 중요)
-- Buffers: shared hit(캐시) + read(디스크)

-- ═══ 노드 유형과 성능 ═══

-- 🟢 좋은 것 (빠름)
-- Index Scan: 인덱스 사용 (정확한 조건)
-- Index Only Scan: 인덱스만으로 조회 (테이블 안 읽음)
-- Bitmap Index Scan: 여러 인덱스 결합

-- 🟡 보통
-- Hash Join: 해시 테이블 기반 조인 (중간 크기)

-- 🔴 나쁜 것 (느림)
-- Seq Scan: 전체 테이블 스캔 (인덱스 없음)
-- Nested Loop: 큰 테이블 × 큰 테이블 (매우 느림)
-- Sort: 메모리 부족 시 디스크 정렬 (external merge)

-- ═══ 문제 패턴 & 해결 ═══

-- 문제 1: Seq Scan (인덱스 안 씀)
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'hong@test.com';
-- Seq Scan on users (actual time=0.01..25.00 rows=1 loops=1)
--   Filter: (email = 'hong@test.com')
--   Rows Removed by Filter: 99999

-- 해결: 인덱스 생성
CREATE INDEX idx_users_email ON users (email);
-- Index Scan using idx_users_email (actual time=0.02..0.03 rows=1 loops=1)

-- 문제 2: 예상 rows와 실제 rows 차이 (통계 부정확)
-- rows=100 (예상) vs rows=50000 (실제) → 잘못된 플랜 선택!
-- 해결:
ANALYZE users;  -- 통계 업데이트
-- 또는
ALTER TABLE users SET (autovacuum_analyze_scale_factor = 0.05);

-- 문제 3: Sort가 디스크 사용 (메모리 부족)
-- Sort Method: external merge  Disk: 15MB  ← 느림!
-- 해결:
SET work_mem = '256MB';  -- 세션 레벨
-- 또는 인덱스로 정렬 대체
CREATE INDEX idx_users_created_desc ON users (created_at DESC);

-- 문제 4: Hash Join 메모리 부족
-- Batches: 4 (디스크에 분할) ← 느림!
-- 해결:
SET work_mem = '512MB';

-- ═══ 실무 분석 프로세스 ═══
-- 1. EXPLAIN ANALYZE 실행
-- 2. actual time이 가장 큰 노드 찾기 (병목)
-- 3. 해당 노드가 Seq Scan이면 → 인덱스 추가
-- 4. rows 예상치가 크게 틀리면 → ANALYZE 실행
-- 5. Sort/Hash가 디스크 사용이면 → work_mem 증가
-- 6. Buffers read가 크면 → shared_buffers 증가 또는 인덱스

-- ═══ 유용한 쿼리 ═══

-- 느린 쿼리 Top 10
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- 인덱스 사용률
SELECT schemaname, tablename, indexname,
       idx_scan as "사용 횟수",
       pg_size_pretty(pg_relation_size(indexrelid)) as "크기"
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;  -- 사용 안 되는 인덱스 찾기

-- 테이블 캐시 히트율
SELECT relname,
       round(heap_blks_hit::numeric / (heap_blks_hit + heap_blks_read + 1) * 100, 1) as "캐시 히트율%"
FROM pg_statio_user_tables
WHERE heap_blks_hit + heap_blks_read > 100
ORDER BY "캐시 히트율%" ASC;
```

EXPLAIN 분석 체크리스트:
1. **Seq Scan** → 인덱스 필요?
2. **rows 예상 vs 실제** → ANALYZE 필요?
3. **Sort 디스크** → work_mem 또는 인덱스
4. **Nested Loop** → Hash Join으로 변경 (크기 확인)
5. **Buffers read 많음** → shared_buffers 또는 인덱스
6. **Planning Time 높음** → 쿼리 단순화'''),

    m("데이터베이스 파티셔닝 전략 심화 알려줘",
'''테이블 파티셔닝으로 대용량 데이터를 효율적으로 관리합니다.

```sql
-- ═══ 1. Range 파티셔닝 (시계열 데이터) ═══
-- 가장 흔한 패턴: 날짜별 분할

CREATE TABLE events (
    id          BIGSERIAL,
    user_id     BIGINT NOT NULL,
    event_type  VARCHAR(50) NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- 월별 파티션 생성
CREATE TABLE events_2025_01 PARTITION OF events
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE events_2025_02 PARTITION OF events
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
CREATE TABLE events_2025_03 PARTITION OF events
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');
-- ...

-- 기본 파티션 (범위 밖 데이터)
CREATE TABLE events_default PARTITION OF events DEFAULT;

-- 파티션별 인덱스 (자동 생성)
CREATE INDEX idx_events_user ON events (user_id, created_at);
-- → 각 파티션에 자동으로 로컬 인덱스 생성됨

-- 쿼리 시 PostgreSQL이 자동으로 해당 파티션만 스캔
EXPLAIN ANALYZE
SELECT * FROM events
WHERE created_at >= '2025-03-01' AND created_at < '2025-04-01';
-- Seq Scan on events_2025_03 (다른 파티션은 안 봄!)

-- 자동 파티션 생성 (pg_partman 확장)
CREATE EXTENSION pg_partman;

SELECT partman.create_parent(
    p_parent_table := 'public.events',
    p_control := 'created_at',
    p_type := 'native',
    p_interval := '1 month',
    p_premake := 3  -- 3개월 미리 생성
);

-- 오래된 파티션 삭제 (아카이브)
ALTER TABLE events DETACH PARTITION events_2024_01;
-- 필요 시 S3로 백업 후
DROP TABLE events_2024_01;

-- ═══ 2. List 파티셔닝 (카테고리별) ═══
CREATE TABLE orders (
    id          BIGSERIAL,
    user_id     BIGINT,
    status      VARCHAR(20),
    total       DECIMAL(10,2),
    created_at  TIMESTAMPTZ DEFAULT NOW()
) PARTITION BY LIST (status);

CREATE TABLE orders_pending PARTITION OF orders
    FOR VALUES IN ('pending', 'processing');
CREATE TABLE orders_completed PARTITION OF orders
    FOR VALUES IN ('completed', 'delivered');
CREATE TABLE orders_cancelled PARTITION OF orders
    FOR VALUES IN ('cancelled', 'refunded');

-- ═══ 3. Hash 파티셔닝 (균등 분배) ═══
CREATE TABLE sessions (
    id          UUID PRIMARY KEY,
    user_id     BIGINT,
    data        JSONB,
    expires_at  TIMESTAMPTZ
) PARTITION BY HASH (user_id);

-- 4개 파티션 (균등 분배)
CREATE TABLE sessions_0 PARTITION OF sessions
    FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE sessions_1 PARTITION OF sessions
    FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE sessions_2 PARTITION OF sessions
    FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE sessions_3 PARTITION OF sessions
    FOR VALUES WITH (MODULUS 4, REMAINDER 3);

-- ═══ 4. 파티션 관리 쿼리 ═══

-- 파티션 목록 확인
SELECT inhrelid::regclass AS partition_name,
       pg_size_pretty(pg_relation_size(inhrelid)) AS size,
       pg_stat_get_live_tuples(inhrelid) AS row_count
FROM pg_inherits
WHERE inhparent = 'events'::regclass
ORDER BY inhrelid::regclass::text;

-- 파티션별 쿼리 분포
SELECT schemaname, relname,
       seq_scan, seq_tup_read,
       idx_scan, idx_tup_fetch,
       n_live_tup
FROM pg_stat_user_tables
WHERE relname LIKE 'events_%'
ORDER BY relname;
```

파티셔닝 전략 선택:
| 데이터 유형 | 파티션 방식 | 파티션 키 |
|-------------|-------------|-----------|
| 로그/이벤트 | Range (월별) | created_at |
| 주문 (상태별) | List | status |
| 세션 (분산) | Hash | user_id |
| 지역별 데이터 | List | country |
| IoT 센서 | Range (일별) | timestamp |

파티셔닝 규칙:
- **100만 행 이상**부터 고려
- WHERE 조건에 **파티션 키 포함** 필수
- 파티션 수 **50개 이하** 유지 (너무 많으면 플래너 느림)
- 파티션 pruning이 작동하는지 EXPLAIN으로 확인'''),

    m("데이터베이스 데드락 원인이랑 해결법 심화 알려줘",
'''데드락은 두 트랜잭션이 서로 잠금을 기다리는 교착 상태입니다.

```sql
-- ═══ 데드락 발생 시나리오 ═══

-- 트랜잭션 A:
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;  -- id=1 잠금
-- (잠시 대기)
UPDATE accounts SET balance = balance + 100 WHERE id = 2;  -- id=2 대기 중...

-- 트랜잭션 B (동시에):
BEGIN;
UPDATE accounts SET balance = balance - 50 WHERE id = 2;   -- id=2 잠금
-- (잠시 대기)
UPDATE accounts SET balance = balance + 50 WHERE id = 1;   -- id=1 대기 중...

-- 결과: A는 B를, B는 A를 기다림 → 데드락!
-- PostgreSQL이 자동 감지 → 한쪽 트랜잭션 강제 롤백

-- ═══ 해결법 1: 잠금 순서 통일 ═══
-- 항상 같은 순서 (ID 오름차순)로 잠금

-- ✅ 안전한 이체 함수
CREATE OR REPLACE FUNCTION transfer(
    from_id INT, to_id INT, amount DECIMAL
) RETURNS VOID AS $$
DECLARE
    lock_id_1 INT := LEAST(from_id, to_id);    -- 작은 ID 먼저
    lock_id_2 INT := GREATEST(from_id, to_id); -- 큰 ID 나중
BEGIN
    -- 항상 작은 ID부터 잠금 → 데드락 불가!
    PERFORM * FROM accounts WHERE id = lock_id_1 FOR UPDATE;
    PERFORM * FROM accounts WHERE id = lock_id_2 FOR UPDATE;

    UPDATE accounts SET balance = balance - amount WHERE id = from_id;
    UPDATE accounts SET balance = balance + amount WHERE id = to_id;
END;
$$ LANGUAGE plpgsql;

-- ═══ 해결법 2: SKIP LOCKED (큐 패턴) ═══
-- 잠긴 행을 건너뛰고 다음 행 처리

BEGIN;
SELECT id, payload FROM job_queue
WHERE status = 'pending'
ORDER BY created_at
LIMIT 1
FOR UPDATE SKIP LOCKED;  -- 다른 워커가 처리 중인 행 건너뜀

UPDATE job_queue SET status = 'processing' WHERE id = ?;
COMMIT;

-- ═══ 해결법 3: Advisory Lock (앱 레벨 잠금) ═══

-- 특정 사용자에 대한 동시 작업 방지
SELECT pg_try_advisory_lock(hashtext('user_' || user_id::text));
-- true면 잠금 획득, false면 이미 처리 중

-- 작업 완료 후 해제
SELECT pg_advisory_unlock(hashtext('user_' || user_id::text));

-- ═══ 해결법 4: 낙관적 잠금 (Optimistic Locking) ═══

-- 버전 번호로 충돌 감지
ALTER TABLE products ADD COLUMN version INT DEFAULT 0;

-- 읽기
SELECT id, name, stock, version FROM products WHERE id = 1;
-- → stock=10, version=3

-- 쓰기 (버전 확인)
UPDATE products
SET stock = stock - 1, version = version + 1
WHERE id = 1 AND version = 3;  -- 버전이 다르면 0 rows!

-- 0 rows updated → 다른 트랜잭션이 먼저 수정 → 재시도!
```

```python
# Python에서 데드락 처리
from sqlalchemy.exc import OperationalError
import time

async def transfer_with_retry(from_id: int, to_id: int, amount: int, max_retries: int = 3):
    """데드락 발생 시 자동 재시도."""
    for attempt in range(1, max_retries + 1):
        try:
            async with db.begin() as session:
                # ID 정렬로 잠금 순서 통일
                ids = sorted([from_id, to_id])
                accounts = await session.execute(
                    select(Account)
                    .where(Account.id.in_(ids))
                    .order_by(Account.id)
                    .with_for_update()
                )
                accounts = {a.id: a for a in accounts.scalars()}

                if accounts[from_id].balance < amount:
                    raise ValueError("잔액 부족")

                accounts[from_id].balance -= amount
                accounts[to_id].balance += amount

                await session.commit()
                return  # 성공

        except OperationalError as e:
            if "deadlock" in str(e).lower() and attempt < max_retries:
                wait = 0.1 * (2 ** attempt)  # 지수 백오프
                logger.warning(f"데드락 감지, {wait}초 후 재시도 ({attempt}/{max_retries})")
                await asyncio.sleep(wait)
            else:
                raise

# 데드락 모니터링
SELECT blocked.pid AS blocked_pid,
       blocked_activity.usename AS blocked_user,
       blocking.pid AS blocking_pid,
       blocking_activity.usename AS blocking_user,
       blocked_activity.query AS blocked_query,
       blocking_activity.query AS blocking_query
FROM pg_catalog.pg_locks blocked
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked.pid = blocked_activity.pid
JOIN pg_catalog.pg_locks blocking ON blocking.locktype = blocked.locktype
    AND blocking.relation = blocked.relation
    AND blocking.pid != blocked.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking.pid = blocking_activity.pid
WHERE NOT blocked.granted;
```

데드락 방지 체크리스트:
1. **잠금 순서 통일**: 항상 같은 순서 (ID 오름차순)
2. **트랜잭션 짧게**: 잠금 시간 최소화
3. **SKIP LOCKED**: 큐/작업 분배 시
4. **낙관적 잠금**: 충돌 적은 경우 (version 컬럼)
5. **Advisory Lock**: 앱 레벨 동시성 제어
6. **재시도 로직**: 데드락 감지 시 지수 백오프'''),

    m("데이터베이스 읽기 복제본 구성이랑 읽기/쓰기 분리 알려줘",
'''읽기 복제본(Read Replica)으로 읽기 성능을 수평 확장합니다.

```
═══ 아키텍처 ═══

[앱 서버] ─── 쓰기 ──→ [Primary (Master)]
    │                         │
    │                    복제 (WAL)
    │                         │
    └─── 읽기 ──→ [Replica 1]  [Replica 2]  [Replica 3]
                  (읽기 전용)   (읽기 전용)   (읽기 전용)

- 쓰기: Primary에만
- 읽기: Replica에서 (부하 분산)
- 복제: 비동기 (약간의 지연 있음)
```

```python
# ═══ SQLAlchemy 읽기/쓰기 분리 ═══
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# 엔진 분리
write_engine = create_engine("postgresql://primary:5432/mydb")
read_engine = create_engine("postgresql://replica:5433/mydb")

# 라우팅 세션
class RoutingSession(Session):
    def get_bind(self, mapper=None, clause=None, **kwargs):
        # flush 중이거나 쓰기 작업이면 Primary
        if self._flushing or self.info.get("write"):
            return write_engine
        return read_engine

# 사용
from contextlib import contextmanager

@contextmanager
def read_session():
    session = RoutingSession()
    try:
        yield session
    finally:
        session.close()

@contextmanager
def write_session():
    session = RoutingSession()
    session.info["write"] = True
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

# 읽기 (Replica로)
with read_session() as session:
    users = session.query(User).filter(User.status == "active").all()

# 쓰기 (Primary로)
with write_session() as session:
    user = User(name="홍길동", email="hong@test.com")
    session.add(user)

# ═══ 복제 지연 (Replication Lag) 처리 ═══
# 문제: 쓰기 직후 읽기하면 Replica에 아직 반영 안 됨

# 해결 1: 쓰기 후 일정 시간은 Primary에서 읽기
class SmartRouter:
    def __init__(self):
        self.last_write = {}  # 테이블별 마지막 쓰기 시간

    def get_engine(self, table: str, is_write: bool):
        if is_write:
            self.last_write[table] = time.time()
            return write_engine

        # 쓰기 후 2초 이내면 Primary에서 읽기
        last = self.last_write.get(table, 0)
        if time.time() - last < 2.0:
            return write_engine  # 아직 복제 안 됐을 수 있음

        return read_engine

# 해결 2: 동기 복제 (성능 저하 있음)
# postgresql.conf (Primary):
# synchronous_commit = on
# synchronous_standby_names = 'replica1'
# → 최소 1개 Replica에 복제 완료 후 커밋 응답

# ═══ PgBouncer 커넥션 풀링 ═══
# 여러 Replica에 읽기 분산

# pgbouncer.ini
[databases]
mydb_write = host=primary port=5432 dbname=mydb
mydb_read = host=replica1 port=5432 dbname=mydb
            host=replica2 port=5432 dbname=mydb

[pgbouncer]
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 50
```

```typescript
// ═══ Prisma 읽기/쓰기 분리 ═══
// prisma/schema.prisma (Prisma 5.11+)

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")          // Primary
  directUrl = env("DIRECT_DATABASE_URL")  // 마이그레이션용
  // Read Replica는 확장으로 지원
}

// 코드에서 분리
import { PrismaClient } from "@prisma/client";
import { readReplicas } from "@prisma/extension-read-replicas";

const prisma = new PrismaClient().$extends(
  readReplicas({
    url: process.env.DATABASE_REPLICA_URL!,
  })
);

// 자동으로 읽기는 Replica, 쓰기는 Primary
const users = await prisma.user.findMany();  // → Replica
await prisma.user.create({ data: { ... } }); // → Primary

// 강제로 Primary에서 읽기
const user = await prisma.$primary().user.findUnique({
  where: { id: userId },
});
```

읽기 복제 핵심:
| 항목 | 설명 |
|------|------|
| 복제 방식 | 비동기 (기본) / 동기 (강일관성) |
| 복제 지연 | 보통 10-100ms (비동기) |
| 쓰기 직후 읽기 | Primary에서 읽기 (2초 유예) |
| 커넥션 풀 | PgBouncer (1000+ 연결 처리) |
| 페일오버 | Patroni / pg_auto_failover |'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/deep_db.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 데이터베이스 심화 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  DB 심화: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
