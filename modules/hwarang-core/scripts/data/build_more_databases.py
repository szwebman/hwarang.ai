"""화랑 AI 데이터베이스 확장 학습 데이터

MongoDB, Elasticsearch, ClickHouse, SQLite, Supabase, DynamoDB, 캐싱전략 등.

사용법:
    python scripts/data/build_more_databases.py \
        --output data/sft/more_databases.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
DBA/백엔드 시니어 수준의 데이터베이스 어시스턴트입니다.
설명은 한국어로, 코드와 쿼리는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("MongoDB 실무 사용법 알려줘",
'''MongoDB는 문서 기반 NoSQL 데이터베이스입니다.

```python
# ═══ Motor (비동기 MongoDB) ═══
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime

client = AsyncIOMotorClient("mongodb://localhost:27017")
db = client.hwarang
users = db.users  # 컬렉션

# ═══ 1. CRUD ═══
# 생성
user = await users.insert_one({
    "name": "홍길동",
    "email": "hong@test.com",
    "age": 28,
    "tags": ["developer", "python"],
    "profile": {
        "bio": "안녕하세요",
        "links": ["https://github.com/hong"],
    },
    "created_at": datetime.now(),
})
user_id = user.inserted_id  # ObjectId

# 조회
user = await users.find_one({"email": "hong@test.com"})
user = await users.find_one({"_id": ObjectId("507f1f77bcf86cd799439011")})

# 목록 조회 (필터 + 정렬 + 페이지네이션)
cursor = users.find(
    {"age": {"$gte": 20, "$lte": 30}},  # 20~30세
    {"name": 1, "email": 1, "_id": 0},   # 프로젝션 (필요한 필드만)
).sort("created_at", -1).skip(0).limit(20)

results = await cursor.to_list(length=20)

# 수정
await users.update_one(
    {"_id": user_id},
    {
        "$set": {"name": "홍길동2", "updated_at": datetime.now()},
        "$push": {"tags": "AI"},           # 배열에 추가
        "$inc": {"login_count": 1},         # 숫자 증가
    },
)

# 삭제
await users.delete_one({"_id": user_id})

# ═══ 2. 집계 (Aggregation) ═══
pipeline = [
    # 1단계: 필터
    {"$match": {"status": "active"}},

    # 2단계: 그룹핑
    {"$group": {
        "_id": "$role",
        "count": {"$sum": 1},
        "avg_age": {"$avg": "$age"},
        "users": {"$push": "$name"},
    }},

    # 3단계: 정렬
    {"$sort": {"count": -1}},

    # 4단계: Lookup (JOIN)
    {"$lookup": {
        "from": "orders",
        "localField": "_id",
        "foreignField": "user_id",
        "as": "orders",
    }},
]

results = await users.aggregate(pipeline).to_list(None)

# ═══ 3. 인덱스 ═══
# 단일 인덱스
await users.create_index("email", unique=True)

# 복합 인덱스
await users.create_index([("status", 1), ("created_at", -1)])

# 텍스트 검색 인덱스 (한국어)
await users.create_index([("name", "text"), ("bio", "text")])
results = await users.find({"$text": {"$search": "파이썬 개발자"}}).to_list(10)

# TTL 인덱스 (자동 삭제)
await db.sessions.create_index("expires_at", expireAfterSeconds=0)

# ═══ 4. 트랜잭션 ═══
async with await client.start_session() as session:
    async with session.start_transaction():
        await users.update_one(
            {"_id": sender_id},
            {"$inc": {"balance": -amount}},
            session=session,
        )
        await users.update_one(
            {"_id": receiver_id},
            {"$inc": {"balance": amount}},
            session=session,
        )
        # 예외 발생 시 자동 롤백
```

MongoDB vs PostgreSQL:
| 항목 | MongoDB | PostgreSQL |
|------|---------|------------|
| 스키마 | 유연 (schemaless) | 고정 스키마 |
| JOIN | `$lookup` (느림) | 네이티브 JOIN |
| 트랜잭션 | 4.0+ 지원 | 완벽 지원 |
| 검색 | 텍스트 인덱스 | 전문검색 강력 |
| 적합 | 로그, 이벤트, CMS | 관계형 데이터, 금융 |'''),

    m("Elasticsearch 검색 엔진 사용법 알려줘",
'''Elasticsearch는 전문 검색과 분석에 특화된 엔진입니다.

```python
# ═══ Elasticsearch 8.x ═══
from elasticsearch import AsyncElasticsearch

es = AsyncElasticsearch(
    "https://localhost:9200",
    api_key="xxx",
)

# ═══ 1. 인덱스 생성 (한국어 형태소 분석) ═══
await es.indices.create(
    index="posts",
    body={
        "settings": {
            "analysis": {
                "analyzer": {
                    "korean": {
                        "type": "custom",
                        "tokenizer": "nori_tokenizer",  # 한국어 형태소
                        "filter": [
                            "nori_part_of_speech",
                            "lowercase",
                        ],
                    },
                },
            },
        },
        "mappings": {
            "properties": {
                "title": {
                    "type": "text",
                    "analyzer": "korean",
                    "fields": {
                        "keyword": {"type": "keyword"},  # 정렬/집계용
                    },
                },
                "content": {"type": "text", "analyzer": "korean"},
                "tags": {"type": "keyword"},
                "author": {"type": "keyword"},
                "created_at": {"type": "date"},
                "view_count": {"type": "integer"},
                "embedding": {
                    "type": "dense_vector",  # 벡터 검색
                    "dims": 1024,
                    "index": True,
                    "similarity": "cosine",
                },
            },
        },
    },
)

# ═══ 2. 문서 색인 ═══
await es.index(
    index="posts",
    id="1",
    document={
        "title": "파이썬 비동기 프로그래밍",
        "content": "asyncio를 활용한 효율적인 서버 개발...",
        "tags": ["python", "asyncio"],
        "author": "홍길동",
        "created_at": "2025-04-20T10:00:00Z",
        "view_count": 150,
    },
)

# 벌크 색인 (대량)
from elasticsearch.helpers import async_bulk

actions = [
    {
        "_index": "posts",
        "_id": str(post["id"]),
        "_source": post,
    }
    for post in posts
]
await async_bulk(es, actions, chunk_size=500)

# ═══ 3. 검색 ═══
# 기본 검색
result = await es.search(
    index="posts",
    body={
        "query": {
            "multi_match": {
                "query": "파이썬 비동기",
                "fields": ["title^3", "content"],  # 제목 3배 가중치
                "type": "best_fields",
            },
        },
        "highlight": {
            "fields": {"title": {}, "content": {}},
            "pre_tags": ["<mark>"],
            "post_tags": ["</mark>"],
        },
        "sort": [
            {"_score": "desc"},
            {"created_at": "desc"},
        ],
        "from": 0,
        "size": 20,
    },
)

# 복합 쿼리 (bool)
result = await es.search(
    index="posts",
    body={
        "query": {
            "bool": {
                "must": [
                    {"multi_match": {"query": "파이썬", "fields": ["title", "content"]}},
                ],
                "filter": [
                    {"term": {"author": "홍길동"}},
                    {"range": {"created_at": {"gte": "2025-01-01"}}},
                    {"terms": {"tags": ["python", "asyncio"]}},
                ],
                "must_not": [
                    {"term": {"status": "deleted"}},
                ],
            },
        },
    },
)

# 자동완성 (Suggest)
result = await es.search(
    index="posts",
    body={
        "suggest": {
            "title_suggest": {
                "prefix": "파이",
                "completion": {
                    "field": "title.suggest",
                    "size": 5,
                    "fuzzy": {"fuzziness": "AUTO"},
                },
            },
        },
    },
)

# ═══ 4. 집계 (Analytics) ═══
result = await es.search(
    index="posts",
    body={
        "size": 0,  # 문서 안 가져옴 (집계만)
        "aggs": {
            "tags_count": {
                "terms": {"field": "tags", "size": 20},
            },
            "monthly_posts": {
                "date_histogram": {
                    "field": "created_at",
                    "calendar_interval": "month",
                },
            },
            "avg_views": {
                "avg": {"field": "view_count"},
            },
        },
    },
)
```

Elasticsearch 적합 사례:
- **전문 검색**: 블로그, 상품, 문서 검색
- **로그 분석**: ELK 스택 (Elasticsearch + Logstash + Kibana)
- **자동완성**: 실시간 검색어 제안
- **분석/집계**: 대시보드 통계'''),

    m("Supabase 사용법 알려줘 Firebase 대안으로",
'''Supabase는 오픈소스 Firebase 대안 (PostgreSQL 기반)입니다.

```typescript
// ═══ 1. Supabase 클라이언트 ═══
import { createClient } from "@supabase/supabase-js";
import type { Database } from "@/types/supabase";  // 자동 생성 타입

const supabase = createClient<Database>(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
);

// ═══ 2. CRUD ═══
// 조회
const { data: users, error } = await supabase
  .from("users")
  .select("id, name, email, profile:profiles(bio, avatar_url)")  // JOIN
  .eq("status", "active")
  .order("created_at", { ascending: false })
  .range(0, 19);  // 페이지네이션

// 단일 조회
const { data: user } = await supabase
  .from("users")
  .select("*")
  .eq("id", userId)
  .single();

// 생성
const { data, error } = await supabase
  .from("users")
  .insert({ name: "홍길동", email: "hong@test.com" })
  .select()
  .single();

// 수정
const { data } = await supabase
  .from("users")
  .update({ name: "홍길동2" })
  .eq("id", userId)
  .select()
  .single();

// 삭제
await supabase.from("users").delete().eq("id", userId);

// ═══ 3. 인증 ═══
// 회원가입
const { data, error } = await supabase.auth.signUp({
  email: "hong@test.com",
  password: "securepassword",
  options: {
    data: { name: "홍길동" },  // 사용자 메타데이터
  },
});

// 로그인
const { data } = await supabase.auth.signInWithPassword({
  email: "hong@test.com",
  password: "securepassword",
});

// 소셜 로그인
const { data } = await supabase.auth.signInWithOAuth({
  provider: "google",
  options: { redirectTo: `${location.origin}/auth/callback` },
});

// 현재 사용자
const { data: { user } } = await supabase.auth.getUser();

// 로그아웃
await supabase.auth.signOut();

// ═══ 4. 실시간 구독 ═══
const channel = supabase
  .channel("messages")
  .on(
    "postgres_changes",
    { event: "INSERT", schema: "public", table: "messages", filter: `room_id=eq.${roomId}` },
    (payload) => {
      console.log("새 메시지:", payload.new);
      setMessages((prev) => [...prev, payload.new]);
    },
  )
  .subscribe();

// 구독 해제
supabase.removeChannel(channel);

// ═══ 5. 파일 스토리지 ═══
// 업로드
const { data, error } = await supabase.storage
  .from("avatars")
  .upload(`users/${userId}/avatar.png`, file, {
    cacheControl: "3600",
    upsert: true,
  });

// 공개 URL
const { data: { publicUrl } } = supabase.storage
  .from("avatars")
  .getPublicUrl(`users/${userId}/avatar.png`);

// ═══ 6. Edge Functions ═══
// supabase/functions/hello/index.ts
import { serve } from "https://deno.land/std@0.177.0/http/server.ts";

serve(async (req) => {
  const { name } = await req.json();
  return new Response(
    JSON.stringify({ message: `안녕하세요, ${name}!` }),
    { headers: { "Content-Type": "application/json" } },
  );
});

// 호출
const { data } = await supabase.functions.invoke("hello", {
  body: { name: "홍길동" },
});

// ═══ 7. RLS (Row Level Security) ═══
-- SQL 정책
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;

-- 모든 사용자가 읽기 가능
CREATE POLICY "posts_read" ON posts FOR SELECT USING (true);

-- 본인 게시글만 수정/삭제
CREATE POLICY "posts_write" ON posts FOR ALL
  USING (auth.uid() = user_id);

-- 관리자는 모든 것 가능
CREATE POLICY "admin_all" ON posts FOR ALL
  USING (auth.jwt()->>'role' = 'admin');
```

Supabase vs Firebase:
| 항목 | Supabase | Firebase |
|------|----------|---------|
| DB | PostgreSQL (SQL) | Firestore (NoSQL) |
| 쿼리 | SQL (강력) | 제한적 |
| 오픈소스 | ✅ | ❌ |
| 셀프호스팅 | ✅ | ❌ |
| 실시간 | ✅ | ✅ |
| 인증 | ✅ | ✅ |
| 스토리지 | ✅ | ✅ |
| 가격 | 저렴 | 비쌈 |'''),

    m("SQLite 실무 활용법 알려줘 임베디드 용도로",
'''SQLite는 서버 없이 파일 하나로 동작하는 DB입니다.

```python
# ═══ 1. 기본 사용법 ═══
import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("data/app.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # dict처럼 접근
    conn.execute("PRAGMA journal_mode=WAL")     # WAL 모드 (동시성)
    conn.execute("PRAGMA foreign_keys=ON")       # FK 제약 활성화
    conn.execute("PRAGMA busy_timeout=5000")     # 잠금 대기 5초
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# 테이블 생성
with get_db() as db:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            model TEXT DEFAULT 'hwarang',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            metadata TEXT,  -- JSON
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conv
            ON messages(conversation_id, created_at);

        -- 전문 검색 (FTS5)
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content,
            content_rowid='id',
            tokenize='unicode61'
        );
    """)

# ═══ 2. CRUD ═══
import uuid

def create_conversation(title: str, model: str = "hwarang") -> str:
    conv_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            "INSERT INTO conversations (id, title, model) VALUES (?, ?, ?)",
            (conv_id, title, model),
        )
    return conv_id

def add_message(conv_id: str, role: str, content: str, metadata: dict | None = None):
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (conv_id, role, content, json.dumps(metadata) if metadata else None),
        )
        # FTS 업데이트
        db.execute(
            "INSERT INTO messages_fts (rowid, content) VALUES (?, ?)",
            (cursor.lastrowid, content),
        )
        # 대화 업데이트 시간
        db.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conv_id,),
        )

def search_messages(query: str, limit: int = 20) -> list[dict]:
    with get_db() as db:
        rows = db.execute("""
            SELECT m.*, c.title as conv_title,
                   highlight(messages_fts, 0, '<mark>', '</mark>') as highlighted
            FROM messages_fts
            JOIN messages m ON messages_fts.rowid = m.id
            JOIN conversations c ON m.conversation_id = c.id
            WHERE messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
    return [dict(r) for r in rows]

def get_history(conv_id: str, limit: int = 50) -> list[dict]:
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (conv_id, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]

# ═══ 3. 비동기 (aiosqlite) ═══
import aiosqlite

async def async_search(query: str) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM messages WHERE content LIKE ? LIMIT 20",
            (f"%{query}%",),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
```

SQLite 적합 사례:
- **CLI 도구**: 대화 히스토리, 설정 저장
- **모바일 앱**: 로컬 캐시, 오프라인 데이터
- **임베디드**: IoT, 데스크탑 앱
- **테스트**: 테스트 DB (인메모리 모드)
- **프로토타입**: 빠른 개발 후 PostgreSQL 전환

주의: 동시 쓰기가 많으면 PostgreSQL 사용!'''),

    m("DynamoDB 사용법 알려줘 서버리스 용도로",
'''AWS DynamoDB는 서버리스 NoSQL DB입니다.

```python
# ═══ boto3 (AWS SDK) ═══
import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime

dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-2")
table = dynamodb.Table("hwarang-users")

# ═══ 1. 테이블 설계 (단일 테이블 디자인) ═══
# PK: 파티션 키, SK: 정렬 키
#
# PK              | SK                  | 데이터
# USER#123        | PROFILE             | {name, email, ...}
# USER#123        | ORDER#2025-04-20#1  | {total, status, ...}
# USER#123        | ORDER#2025-04-19#2  | {total, status, ...}
# POST#456        | METADATA            | {title, author, ...}
# POST#456        | COMMENT#2025-04-20  | {content, user, ...}

# ═══ 2. CRUD ═══
# 생성
table.put_item(Item={
    "PK": f"USER#{user_id}",
    "SK": "PROFILE",
    "name": "홍길동",
    "email": "hong@test.com",
    "role": "user",
    "created_at": datetime.now().isoformat(),
    "GSI1PK": f"ROLE#user",       # GSI (역인덱스)
    "GSI1SK": f"USER#{user_id}",
})

# 조회 (단일)
response = table.get_item(Key={
    "PK": f"USER#{user_id}",
    "SK": "PROFILE",
})
user = response.get("Item")

# 쿼리 (파티션 내 범위)
response = table.query(
    KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("ORDER#"),
    ScanIndexForward=False,  # 최신순
    Limit=20,
)
orders = response["Items"]

# GSI 쿼리 (역방향 조회)
response = table.query(
    IndexName="GSI1",
    KeyConditionExpression=Key("GSI1PK").eq("ROLE#admin"),
)
admins = response["Items"]

# 수정
table.update_item(
    Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
    UpdateExpression="SET #name = :name, updated_at = :now",
    ExpressionAttributeNames={"#name": "name"},
    ExpressionAttributeValues={
        ":name": "홍길동2",
        ":now": datetime.now().isoformat(),
    },
)

# 조건부 쓰기 (낙관적 잠금)
table.put_item(
    Item={...},
    ConditionExpression="attribute_not_exists(PK)",  # PK가 없을 때만
)

# ═══ 3. 배치 (대량) ═══
with table.batch_writer() as batch:
    for item in items:
        batch.put_item(Item=item)

# ═══ 4. TTL (자동 삭제) ═══
# 세션, 캐시 등에 활용
table.put_item(Item={
    "PK": f"SESSION#{session_id}",
    "SK": "DATA",
    "user_id": user_id,
    "ttl": int((datetime.now() + timedelta(hours=24)).timestamp()),  # Unix timestamp
})
```

DynamoDB 핵심:
- **단일 테이블 디자인**: 하나의 테이블에 모든 엔티티
- **PK + SK**: 파티션 키 + 정렬 키 조합
- **GSI**: 역방향 조회용 글로벌 보조 인덱스
- **서버리스**: 자동 스케일링, 관리 불필요
- **가격**: 읽기/쓰기 용량 단위 과금'''),

    m("ClickHouse 분석용 데이터베이스 알려줘",
'''ClickHouse는 OLAP(분석)에 특화된 컬럼 지향 DB입니다.

```sql
-- ═══ 1. 테이블 생성 ═══
CREATE TABLE events (
    event_id UUID DEFAULT generateUUIDv4(),
    user_id UInt64,
    event_type LowCardinality(String),  -- 카디널리티 낮은 문자열 최적화
    page_url String,
    referrer String,
    country LowCardinality(String),
    device LowCardinality(String),
    properties String,  -- JSON 문자열
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)  -- 월별 파티션
ORDER BY (user_id, created_at)     -- 정렬 키 (쿼리 최적화)
TTL created_at + INTERVAL 1 YEAR;  -- 1년 후 자동 삭제

-- ═══ 2. 분석 쿼리 ═══

-- 일별 활성 사용자 (DAU)
SELECT
    toDate(created_at) AS date,
    uniqExact(user_id) AS dau
FROM events
WHERE created_at >= now() - INTERVAL 30 DAY
GROUP BY date
ORDER BY date;

-- 시간대별 이벤트 히트맵
SELECT
    toHour(created_at) AS hour,
    toDayOfWeek(created_at) AS day_of_week,
    count() AS events
FROM events
WHERE created_at >= now() - INTERVAL 7 DAY
GROUP BY hour, day_of_week
ORDER BY day_of_week, hour;

-- 퍼널 분석 (회원가입 → 로그인 → 구매)
SELECT
    level,
    count() AS users,
    round(count() * 100.0 / first_value(count()) OVER (ORDER BY level), 1) AS pct
FROM (
    SELECT user_id,
        windowFunnel(86400)(  -- 24시간 윈도우
            created_at,
            event_type = 'signup',
            event_type = 'login',
            event_type = 'purchase'
        ) AS level
    FROM events
    WHERE created_at >= now() - INTERVAL 30 DAY
    GROUP BY user_id
)
GROUP BY level
ORDER BY level;

-- 리텐션 분석 (코호트)
SELECT
    toStartOfWeek(first_visit) AS cohort_week,
    dateDiff('week', first_visit, created_at) AS weeks_since,
    uniqExact(user_id) AS users
FROM events
INNER JOIN (
    SELECT user_id, min(created_at) AS first_visit
    FROM events
    GROUP BY user_id
) USING (user_id)
WHERE created_at >= now() - INTERVAL 90 DAY
GROUP BY cohort_week, weeks_since
ORDER BY cohort_week, weeks_since;

-- ═══ 3. Materialized View (실시간 집계) ═══
-- 원본 데이터 삽입 시 자동으로 집계 테이블 업데이트

CREATE MATERIALIZED VIEW daily_stats
ENGINE = SummingMergeTree()
ORDER BY (date, event_type)
AS SELECT
    toDate(created_at) AS date,
    event_type,
    count() AS event_count,
    uniqExact(user_id) AS unique_users
FROM events
GROUP BY date, event_type;

-- 집계 테이블 조회 (즉시 응답)
SELECT * FROM daily_stats
WHERE date >= today() - 30
ORDER BY date, event_type;
```

```python
# Python에서 ClickHouse 사용
from clickhouse_driver import Client

client = Client(host="localhost", port=9000)

# 쿼리
rows = client.execute("""
    SELECT toDate(created_at) AS date, count() AS cnt
    FROM events
    WHERE created_at >= today() - 30
    GROUP BY date
    ORDER BY date
""")

# 벌크 삽입 (초당 수십만 행)
client.execute(
    "INSERT INTO events (user_id, event_type, page_url, created_at) VALUES",
    [(1, "pageview", "/home", datetime.now()) for _ in range(100000)],
)
```

ClickHouse 적합 사례:
| 사용 | 적합도 |
|------|--------|
| 로그 분석 | ⭐⭐⭐⭐⭐ |
| 사용자 행동 분석 | ⭐⭐⭐⭐⭐ |
| 실시간 대시보드 | ⭐⭐⭐⭐⭐ |
| 시계열 데이터 | ⭐⭐⭐⭐ |
| CRUD 앱 | ❌ (PostgreSQL 사용) |
| 트랜잭션 | ❌ (지원 안 함) |'''),

    m("Prisma ORM 고급 사용법 알려줘 최신으로",
'''Prisma ORM 고급 패턴입니다 (v6 기준).

```typescript
// ═══ 1. 스키마 설계 ═══
// prisma/schema.prisma

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model User {
  id            String   @id @default(cuid())
  email         String   @unique
  name          String
  role          Role     @default(USER)
  hashedPassword String?

  // 관계
  posts         Post[]
  comments      Comment[]
  profile       Profile?

  // 타임스탬프
  createdAt     DateTime @default(now())
  updatedAt     DateTime @updatedAt

  // 인덱스
  @@index([email])
  @@index([role, createdAt(sort: Desc)])
  @@map("users")
}

model Post {
  id        String   @id @default(cuid())
  title     String
  content   String
  published Boolean  @default(false)
  viewCount Int      @default(0)
  tags      String[]

  author    User     @relation(fields: [authorId], references: [id], onDelete: Cascade)
  authorId  String
  comments  Comment[]

  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  // 전문 검색 인덱스
  @@index([title, content])
  @@map("posts")
}

enum Role {
  USER
  ADMIN
  EDITOR
}

// ═══ 2. 고급 쿼리 ═══
import { PrismaClient, Prisma } from "@prisma/client";

const prisma = new PrismaClient({
  log: process.env.NODE_ENV === "development" ? ["query", "warn", "error"] : ["error"],
});

// 관계 포함 + 필터 + 정렬 + 페이지네이션
async function getUsers(params: {
  page: number;
  limit: number;
  search?: string;
  role?: Role;
}) {
  const where: Prisma.UserWhereInput = {
    ...(params.search && {
      OR: [
        { name: { contains: params.search, mode: "insensitive" } },
        { email: { contains: params.search, mode: "insensitive" } },
      ],
    }),
    ...(params.role && { role: params.role }),
  };

  const [users, total] = await prisma.$transaction([
    prisma.user.findMany({
      where,
      include: {
        profile: true,
        _count: { select: { posts: true, comments: true } },
      },
      orderBy: { createdAt: "desc" },
      skip: (params.page - 1) * params.limit,
      take: params.limit,
    }),
    prisma.user.count({ where }),
  ]);

  return { users, total, totalPages: Math.ceil(total / params.limit) };
}

// ═══ 3. 트랜잭션 ═══
// Interactive 트랜잭션 (복잡한 로직)
async function transferPoints(fromId: string, toId: string, amount: number) {
  return prisma.$transaction(async (tx) => {
    const sender = await tx.user.findUnique({ where: { id: fromId } });
    if (!sender || sender.points < amount) {
      throw new Error("포인트 부족");
    }

    await tx.user.update({
      where: { id: fromId },
      data: { points: { decrement: amount } },
    });

    await tx.user.update({
      where: { id: toId },
      data: { points: { increment: amount } },
    });

    await tx.pointHistory.create({
      data: { fromId, toId, amount, type: "TRANSFER" },
    });
  });
}

// ═══ 4. 원시 SQL (복잡한 쿼리) ═══
// 타입 안전한 원시 쿼리
const result = await prisma.$queryRaw<{ month: Date; count: bigint }[]>`
  SELECT
    DATE_TRUNC('month', created_at) AS month,
    COUNT(*) AS count
  FROM posts
  WHERE published = true
    AND created_at >= NOW() - INTERVAL '12 months'
  GROUP BY month
  ORDER BY month DESC
`;

// ═══ 5. Middleware (로깅, 소프트 삭제) ═══
// 소프트 삭제 미들웨어
prisma.$use(async (params, next) => {
  // DELETE → UPDATE (deleted_at 설정)
  if (params.action === "delete") {
    params.action = "update";
    params.args.data = { deletedAt: new Date() };
  }

  // findMany → 삭제된 항목 제외
  if (params.action === "findMany" || params.action === "findFirst") {
    if (!params.args.where) params.args.where = {};
    params.args.where.deletedAt = null;
  }

  return next(params);
});

// ═══ 6. 확장 (Extension) ═══
const xprisma = prisma.$extends({
  model: {
    user: {
      async findByEmail(email: string) {
        return prisma.user.findUnique({ where: { email } });
      },
      async softDelete(id: string) {
        return prisma.user.update({
          where: { id },
          data: { deletedAt: new Date() },
        });
      },
    },
  },
  query: {
    $allOperations({ operation, args, query }) {
      const start = performance.now();
      return query(args).finally(() => {
        const duration = performance.now() - start;
        if (duration > 1000) {
          console.warn(`느린 쿼리: ${operation} (${duration.toFixed(0)}ms)`);
        }
      });
    },
  },
});

// 사용
const user = await xprisma.user.findByEmail("hong@test.com");
await xprisma.user.softDelete("user_123");
```

Prisma 핵심:
- `$transaction` → 원자적 작업
- `include` / `select` → 관계 로딩
- `_count` → 관계 카운트 (서브쿼리 자동)
- Middleware → 공통 로직 (로깅, 소프트삭제)
- Extension → 커스텀 메서드 추가'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/more_databases.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 데이터베이스 확장 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  데이터베이스 확장: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
