"""화랑 AI 데이터베이스 심화 학습 데이터

PostgreSQL, Redis, 인덱싱, 트랜잭션, 쿼리 최적화 등.

사용법:
    python scripts/data/build_database_data.py \
        --output data/sft/database.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
DBA/백엔드 시니어 수준의 데이터베이스 어시스턴트입니다.
설명은 한국어로, SQL과 설정은 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ PostgreSQL 고급 ═══
    m("PostgreSQL 인덱스 전략 알려줘",
'''인덱스는 쿼리 성능의 핵심입니다. 상황별 인덱스 전략입니다.

```sql
-- 1. B-Tree 인덱스 (기본, 등호/범위 검색)
CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_orders_created ON orders (created_at DESC);

-- 복합 인덱스 (왼쪽부터 사용)
-- WHERE status = 'active' AND created_at > '2025-01-01' 에 최적
CREATE INDEX idx_orders_status_created
    ON orders (status, created_at DESC);

-- 2. 부분 인덱스 (조건부 - 인덱스 크기 절감)
-- 활성 사용자만 인덱싱 (전체의 10%라면 90% 절약)
CREATE INDEX idx_users_active_email
    ON users (email)
    WHERE status = 'active';

-- 미처리 주문만
CREATE INDEX idx_orders_pending
    ON orders (created_at)
    WHERE status = 'pending';

-- 3. GIN 인덱스 (배열, JSONB, 전문검색)
-- JSONB 검색
CREATE INDEX idx_products_metadata
    ON products USING GIN (metadata jsonb_path_ops);

-- 전문 검색 (한국어)
CREATE INDEX idx_posts_search
    ON posts USING GIN (
        to_tsvector('simple', title || ' ' || content)
    );

-- 배열 검색
CREATE INDEX idx_posts_tags
    ON posts USING GIN (tags);

-- 4. BRIN 인덱스 (시계열 데이터 - 아주 작은 인덱스)
-- 시간순으로 INSERT되는 로그 테이블에 최적
CREATE INDEX idx_logs_created
    ON logs USING BRIN (created_at)
    WITH (pages_per_range = 128);

-- 5. 커버링 인덱스 (INCLUDE)
-- 인덱스만으로 쿼리 완료 (테이블 액세스 불필요)
CREATE INDEX idx_users_email_include
    ON users (email)
    INCLUDE (name, avatar_url);

-- SELECT name, avatar_url FROM users WHERE email = ?
-- → Index Only Scan (테이블 안 읽음)

-- 6. 동시성을 위한 인덱스 생성
CREATE INDEX CONCURRENTLY idx_big_table_col
    ON big_table (column_name);
-- CONCURRENTLY: 테이블 락 없이 인덱스 생성 (프로덕션 필수)
```

인덱스 분석:
```sql
-- 쿼리 실행 계획 분석
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders
WHERE status = 'pending'
  AND created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC
LIMIT 20;

-- 사용되지 않는 인덱스 찾기
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;

-- 인덱스 크기 확인
SELECT indexname,
       pg_size_pretty(pg_relation_size(indexname::regclass)) AS size
FROM pg_indexes
WHERE tablename = 'orders'
ORDER BY pg_relation_size(indexname::regclass) DESC;
```

인덱스 규칙:
- WHERE 절에 자주 나오는 컬럼 → 인덱스
- JOIN 키 → 인덱스
- ORDER BY + LIMIT → 인덱스 (정렬 피하기)
- 선택도 높은 컬럼 먼저 (cardinality가 높은 것)
- 쓰기 많은 테이블 → 인덱스 최소화'''),

    m("PostgreSQL 트랜잭션과 락 관리 알려줘",
'''트랜잭션과 락은 데이터 정합성의 핵심입니다.

```sql
-- 1. 트랜잭션 격리 수준
-- READ COMMITTED (기본) - 커밋된 데이터만 읽음
-- REPEATABLE READ - 트랜잭션 내 같은 쿼리 = 같은 결과
-- SERIALIZABLE - 완전 직렬화 (가장 안전, 가장 느림)

BEGIN ISOLATION LEVEL REPEATABLE READ;
    SELECT balance FROM accounts WHERE id = 1;  -- 10000
    UPDATE accounts SET balance = balance - 5000 WHERE id = 1;
    UPDATE accounts SET balance = balance + 5000 WHERE id = 2;
COMMIT;

-- 2. SELECT FOR UPDATE (행 잠금)
-- 재고 차감 시 동시성 문제 방지
BEGIN;
    SELECT stock FROM products WHERE id = 100 FOR UPDATE;
    -- 다른 트랜잭션은 이 행을 수정할 수 없음
    UPDATE products SET stock = stock - 1 WHERE id = 100;
COMMIT;

-- FOR UPDATE SKIP LOCKED (큐 패턴)
-- 워커가 작업을 가져갈 때 (처리 중인 것 건너뛰기)
BEGIN;
    SELECT id, payload FROM job_queue
    WHERE status = 'pending'
    ORDER BY created_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED;

    UPDATE job_queue SET status = 'processing' WHERE id = ?;
COMMIT;

-- 3. Advisory Lock (애플리케이션 수준 잠금)
-- 특정 작업의 동시 실행 방지
SELECT pg_try_advisory_lock(hashtext('daily_report'));
-- true면 잠금 획득, false면 이미 실행 중
-- 작업 완료 후:
SELECT pg_advisory_unlock(hashtext('daily_report'));

-- 4. 데드락 방지
-- ❌ 데드락 발생 가능 (A→B, B→A 순서)
-- TX1: UPDATE accounts SET ... WHERE id = 1; UPDATE ... WHERE id = 2;
-- TX2: UPDATE accounts SET ... WHERE id = 2; UPDATE ... WHERE id = 1;

-- ✅ 항상 같은 순서로 잠금
BEGIN;
    SELECT * FROM accounts WHERE id IN (1, 2) ORDER BY id FOR UPDATE;
    UPDATE accounts SET balance = balance - 5000 WHERE id = 1;
    UPDATE accounts SET balance = balance + 5000 WHERE id = 2;
COMMIT;
```

```python
# SQLAlchemy에서의 트랜잭션 관리
from sqlalchemy.ext.asyncio import AsyncSession

async def transfer_money(
    session: AsyncSession,
    from_id: int,
    to_id: int,
    amount: int
):
    """계좌 이체 (트랜잭션 + 행 잠금)."""
    # 정렬된 순서로 잠금 (데드락 방지)
    ids = sorted([from_id, to_id])

    accounts = await session.execute(
        select(Account)
        .where(Account.id.in_(ids))
        .order_by(Account.id)
        .with_for_update()  # SELECT FOR UPDATE
    )
    accounts = {a.id: a for a in accounts.scalars()}

    sender = accounts[from_id]
    receiver = accounts[to_id]

    if sender.balance < amount:
        raise ValueError("잔액 부족")

    sender.balance -= amount
    receiver.balance += amount

    # 이체 기록
    session.add(Transfer(
        from_id=from_id,
        to_id=to_id,
        amount=amount,
    ))

    await session.commit()
```

핵심:
- `FOR UPDATE` → 동시 수정 방지
- `SKIP LOCKED` → 큐/작업 분배 패턴
- 데드락 방지 → 항상 같은 순서로 잠금
- Advisory Lock → 배치 작업 중복 실행 방지'''),

    m("PostgreSQL 성능 튜닝 설정 알려줘",
'''프로덕션 PostgreSQL 성능 최적화 설정입니다.

```ini
# postgresql.conf - 128GB RAM, NVMe SSD 기준

# ═══ 메모리 ═══
shared_buffers = 32GB              # RAM의 25% (디스크 캐시)
effective_cache_size = 96GB        # RAM의 75% (OS 캐시 포함)
work_mem = 256MB                   # 정렬/해시 작업당 메모리
maintenance_work_mem = 2GB         # VACUUM, CREATE INDEX 시

# ═══ WAL (Write-Ahead Log) ═══
wal_buffers = 64MB
checkpoint_timeout = 15min
max_wal_size = 8GB
min_wal_size = 2GB
checkpoint_completion_target = 0.9

# ═══ 플래너 ═══
random_page_cost = 1.1             # SSD는 1.1 (HDD는 4.0)
effective_io_concurrency = 200     # SSD는 200 (HDD는 2)
default_statistics_target = 200    # 통계 정밀도 (기본 100)

# ═══ 커넥션 ═══
max_connections = 200
# PgBouncer 사용 권장 (커넥션 풀링)

# ═══ 병렬 쿼리 ═══
max_parallel_workers_per_gather = 4
max_parallel_workers = 8
max_worker_processes = 16
parallel_tuple_cost = 0.01

# ═══ VACUUM ═══
autovacuum = on
autovacuum_max_workers = 4
autovacuum_vacuum_cost_delay = 2ms
```

```sql
-- 느린 쿼리 로깅
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- 1초 이상
ALTER SYSTEM SET log_statement = 'none';  -- DDL만 로깅하려면 'ddl'
SELECT pg_reload_conf();

-- 테이블 통계 업데이트
ANALYZE orders;
ANALYZE VERBOSE;  -- 전체

-- 테이블 블로트 확인 & 정리
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total,
       n_dead_tup as dead_rows,
       n_live_tup as live_rows,
       round(n_dead_tup::numeric / greatest(n_live_tup, 1) * 100, 1) as dead_pct
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;

-- 수동 VACUUM (큰 테이블)
VACUUM (VERBOSE, ANALYZE) orders;

-- 연결 상태 확인
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;

-- 현재 실행 중인 느린 쿼리
SELECT pid, now() - pg_stat_activity.query_start AS duration,
       query, state
FROM pg_stat_activity
WHERE state != 'idle'
  AND now() - pg_stat_activity.query_start > interval '5 seconds'
ORDER BY duration DESC;

-- 느린 쿼리 강제 종료
SELECT pg_cancel_backend(pid);    -- 부드럽게
SELECT pg_terminate_backend(pid); -- 강제
```

PgBouncer 설정 (커넥션 풀링):
```ini
# pgbouncer.ini
[databases]
hwarang = host=localhost port=5432 dbname=hwarang

[pgbouncer]
listen_port = 6432
pool_mode = transaction    # 트랜잭션 단위 풀링 (가장 효율적)
max_client_conn = 1000
default_pool_size = 50
min_pool_size = 10
reserve_pool_size = 5
```'''),

    # ═══ Redis ═══
    m("Redis 실무 활용 패턴 알려줘",
'''Redis의 실무 활용 패턴입니다.

```python
import redis.asyncio as redis
import json
from datetime import timedelta

r = redis.from_url("redis://localhost:6379/0")

# ═══ 1. 캐싱 ═══
async def get_user_cached(user_id: int) -> dict:
    """DB 결과를 Redis에 캐싱합니다."""
    cache_key = f"user:{user_id}"

    # 캐시 확인
    cached = await r.get(cache_key)
    if cached:
        return json.loads(cached)

    # DB 조회
    user = await db.get_user(user_id)
    if user:
        await r.setex(cache_key, timedelta(minutes=5), json.dumps(user))
    return user

# 캐시 무효화
async def update_user(user_id: int, data: dict):
    await db.update_user(user_id, data)
    await r.delete(f"user:{user_id}")  # 캐시 삭제

# ═══ 2. Rate Limiting (슬라이딩 윈도우) ═══
async def check_rate_limit(
    user_id: str, max_requests: int = 30, window_sec: int = 60
) -> bool:
    """슬라이딩 윈도우 rate limiting."""
    key = f"rate:{user_id}"
    now = time.time()

    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - window_sec)  # 윈도우 밖 제거
    pipe.zadd(key, {str(now): now})                   # 현재 요청 추가
    pipe.zcard(key)                                    # 요청 수 확인
    pipe.expire(key, window_sec)                       # TTL 설정
    results = await pipe.execute()

    request_count = results[2]
    return request_count <= max_requests

# ═══ 3. 세션 저장소 ═══
async def create_session(user_id: int) -> str:
    """사용자 세션을 생성합니다."""
    session_id = str(uuid.uuid4())
    session_data = {
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
    }
    await r.setex(
        f"session:{session_id}",
        timedelta(hours=24),
        json.dumps(session_data),
    )
    return session_id

# ═══ 4. 분산 락 (Distributed Lock) ═══
async def acquire_lock(key: str, ttl: int = 10) -> str | None:
    """분산 환경에서 안전한 잠금 획득."""
    lock_id = str(uuid.uuid4())
    acquired = await r.set(
        f"lock:{key}", lock_id,
        nx=True,  # 키가 없을 때만 설정
        ex=ttl,   # 자동 만료 (데드락 방지)
    )
    return lock_id if acquired else None

async def release_lock(key: str, lock_id: str):
    """본인이 획득한 잠금만 해제."""
    # Lua 스크립트로 원자적 확인+삭제
    script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    await r.eval(script, 1, f"lock:{key}", lock_id)

# ═══ 5. 리더보드 (Sorted Set) ═══
async def update_score(user_id: str, score: float):
    """점수 업데이트."""
    await r.zadd("leaderboard", {user_id: score})

async def get_top_10() -> list[tuple[str, float]]:
    """상위 10명 조회."""
    return await r.zrevrange("leaderboard", 0, 9, withscores=True)

async def get_rank(user_id: str) -> int | None:
    """순위 조회 (0부터 시작)."""
    rank = await r.zrevrank("leaderboard", user_id)
    return rank + 1 if rank is not None else None

# ═══ 6. Pub/Sub (실시간 알림) ═══
async def publish_notification(channel: str, message: dict):
    await r.publish(channel, json.dumps(message))

async def subscribe_notifications(channel: str):
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            await handle_notification(data)
```

Redis 메모리 관리:
```
# redis.conf
maxmemory 4gb
maxmemory-policy allkeys-lru   # 가장 오래된 키 삭제

# 메모리 사용량 확인
redis-cli INFO memory
```

핵심:
- 캐싱: `setex` (TTL 포함) + 캐시 무효화 전략
- Rate Limiting: Sorted Set + 슬라이딩 윈도우
- 분산 락: `SET NX EX` + Lua 스크립트
- 리더보드: Sorted Set (`ZADD`, `ZREVRANGE`)'''),

    m("데이터베이스 마이그레이션 전략 알려줘",
'''무중단 데이터베이스 마이그레이션 전략입니다.

```sql
-- ═══ 안전한 마이그레이션 원칙 ═══

-- 1. 컬럼 추가 (안전 - 테이블 락 없음)
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- 2. 컬럼 삭제 (3단계로 안전하게)
-- Step 1: 코드에서 컬럼 사용 중지 (배포)
-- Step 2: 컬럼을 nullable로 변경
ALTER TABLE users ALTER COLUMN old_column DROP NOT NULL;
-- Step 3: 다음 배포에서 실제 삭제
ALTER TABLE users DROP COLUMN old_column;

-- 3. 컬럼 이름 변경 (위험! 2단계로)
-- Step 1: 새 컬럼 추가 + 데이터 복사
ALTER TABLE users ADD COLUMN full_name VARCHAR(100);
UPDATE users SET full_name = name;
-- Step 2: 코드 변경 배포 후 이전 컬럼 삭제

-- 4. NOT NULL 추가 (대용량 테이블에서 주의)
-- ❌ 위험: 전체 테이블 스캔
ALTER TABLE orders ALTER COLUMN status SET NOT NULL;

-- ✅ 안전: 제약조건을 NOT VALID로 먼저 추가
ALTER TABLE orders
    ADD CONSTRAINT orders_status_not_null
    CHECK (status IS NOT NULL) NOT VALID;
-- 백그라운드에서 검증 (락 없음)
ALTER TABLE orders VALIDATE CONSTRAINT orders_status_not_null;

-- 5. 인덱스 생성 (프로덕션)
-- ❌ 위험: 테이블 락
CREATE INDEX idx_orders_user ON orders (user_id);

-- ✅ 안전: CONCURRENTLY
CREATE INDEX CONCURRENTLY idx_orders_user ON orders (user_id);

-- 6. 대용량 데이터 마이그레이션 (배치 처리)
DO $$
DECLARE
    batch_size INT := 10000;
    total INT;
    processed INT := 0;
BEGIN
    SELECT count(*) INTO total FROM orders WHERE new_status IS NULL;
    RAISE NOTICE '총 %건 처리 예정', total;

    LOOP
        UPDATE orders
        SET new_status = CASE status
            WHEN 'P' THEN 'pending'
            WHEN 'A' THEN 'active'
            WHEN 'C' THEN 'completed'
        END
        WHERE id IN (
            SELECT id FROM orders
            WHERE new_status IS NULL
            LIMIT batch_size
            FOR UPDATE SKIP LOCKED
        );

        GET DIAGNOSTICS processed = ROW_COUNT;
        EXIT WHEN processed = 0;

        RAISE NOTICE '% 건 처리 완료', processed;
        PERFORM pg_sleep(0.1);  -- DB 부하 분산
        COMMIT;
    END LOOP;
END $$;
```

```python
# Alembic 마이그레이션 (Python)
# alembic revision --autogenerate -m "add phone column"

from alembic import op
import sqlalchemy as sa

def upgrade():
    # 안전한 마이그레이션
    op.add_column("users", sa.Column("phone", sa.String(20), nullable=True))
    op.create_index(
        "idx_users_phone",
        "users",
        ["phone"],
        postgresql_concurrently=True,  # 무중단 인덱스
    )

def downgrade():
    op.drop_index("idx_users_phone")
    op.drop_column("users", "phone")
```

마이그레이션 체크리스트:
- [ ] 프로덕션 데이터 크기 확인 (수백만 행이면 배치 처리)
- [ ] `CONCURRENTLY` 사용 여부 확인
- [ ] 롤백 계획 수립
- [ ] 새벽 시간대 실행 (트래픽 낮을 때)
- [ ] 마이그레이션 전 백업 확인'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/database.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 데이터베이스 심화 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  데이터베이스: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
