"""화랑 AI 아키텍처/설계 학습 데이터

클린아키텍처, DDD, 마이크로서비스, API 설계, 시스템 디자인 등.

사용법:
    python scripts/data/build_architecture_data.py \
        --output data/sft/architecture.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 소프트웨어 아키텍트 수준의 설계 어시스턴트입니다.
설명은 한국어로, 코드와 다이어그램은 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 클린 아키텍처 ═══
    m("클린 아키텍처 실무 적용 방법 알려줘",
'''클린 아키텍처의 핵심은 의존성 방향을 안쪽으로 향하게 하는 것입니다.

```
바깥쪽 → 안쪽 (의존성 방향)

[인프라/프레임워크] → [인터페이스 어댑터] → [유스케이스] → [엔티티]
 (DB, Web, API)       (컨트롤러, 리포)      (비즈니스)     (도메인)
```

```python
# ═══ 프로젝트 구조 ═══
# app/
# ├── domain/           # 엔티티 (가장 안쪽, 의존성 없음)
# │   ├── entities/
# │   └── value_objects/
# ├── application/      # 유스케이스 (도메인만 의존)
# │   ├── use_cases/
# │   ├── ports/        # 인터페이스 (추상)
# │   └── dto/
# ├── infrastructure/   # 구현체 (바깥쪽)
# │   ├── repositories/
# │   ├── external_apis/
# │   └── messaging/
# └── presentation/     # API 컨트롤러
#     └── api/

# ═══ 1. 도메인 엔티티 (핵심, 의존성 없음) ═══
# domain/entities/order.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

@dataclass
class OrderItem:
    product_id: int
    product_name: str
    price: int
    quantity: int

    @property
    def subtotal(self) -> int:
        return self.price * self.quantity

@dataclass
class Order:
    id: int | None
    customer_id: int
    items: list[OrderItem]
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def total(self) -> int:
        return sum(item.subtotal for item in self.items)

    def confirm(self) -> None:
        if self.status != OrderStatus.PENDING:
            raise ValueError(f"주문 확인 불가 상태: {self.status}")
        self.status = OrderStatus.CONFIRMED

    def cancel(self) -> None:
        if self.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise ValueError("배송 시작 후에는 취소할 수 없습니다")
        self.status = OrderStatus.CANCELLED

    def can_cancel(self) -> bool:
        return self.status in (OrderStatus.PENDING, OrderStatus.CONFIRMED)

# ═══ 2. 포트 (인터페이스 - 추상) ═══
# application/ports/order_repository.py
from abc import ABC, abstractmethod

class OrderRepository(ABC):
    @abstractmethod
    async def find_by_id(self, order_id: int) -> Order | None: ...

    @abstractmethod
    async def save(self, order: Order) -> Order: ...

    @abstractmethod
    async def find_by_customer(self, customer_id: int) -> list[Order]: ...

class PaymentGateway(ABC):
    @abstractmethod
    async def charge(self, amount: int, customer_id: int) -> str: ...

    @abstractmethod
    async def refund(self, transaction_id: str) -> bool: ...

class NotificationService(ABC):
    @abstractmethod
    async def send(self, to: str, title: str, body: str) -> None: ...

# ═══ 3. 유스케이스 (비즈니스 로직) ═══
# application/use_cases/create_order.py
@dataclass
class CreateOrderInput:
    customer_id: int
    items: list[dict]

@dataclass
class CreateOrderOutput:
    order_id: int
    total: int
    status: str

class CreateOrderUseCase:
    def __init__(
        self,
        order_repo: OrderRepository,      # 포트 (추상)
        payment: PaymentGateway,           # 포트 (추상)
        notification: NotificationService, # 포트 (추상)
    ):
        self._order_repo = order_repo
        self._payment = payment
        self._notification = notification

    async def execute(self, input: CreateOrderInput) -> CreateOrderOutput:
        # 1. 주문 엔티티 생성
        items = [
            OrderItem(
                product_id=i["product_id"],
                product_name=i["name"],
                price=i["price"],
                quantity=i["quantity"],
            )
            for i in input.items
        ]
        order = Order(id=None, customer_id=input.customer_id, items=items)

        # 2. 결제
        tx_id = await self._payment.charge(order.total, order.customer_id)

        # 3. 주문 확정
        order.confirm()

        # 4. 저장
        saved = await self._order_repo.save(order)

        # 5. 알림
        await self._notification.send(
            to=str(input.customer_id),
            title="주문 완료",
            body=f"주문 #{saved.id}이 확정되었습니다. 총액: {order.total}원",
        )

        return CreateOrderOutput(
            order_id=saved.id,
            total=order.total,
            status=order.status.value,
        )

# ═══ 4. 인프라 (구현체) ═══
# infrastructure/repositories/sqlalchemy_order_repo.py
class SQLAlchemyOrderRepository(OrderRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_by_id(self, order_id: int) -> Order | None:
        result = await self._session.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def save(self, order: Order) -> Order:
        model = self._to_model(order)
        self._session.add(model)
        await self._session.flush()
        order.id = model.id
        return order

# ═══ 5. 의존성 주입 (조립) ═══
# presentation/api/dependencies.py
from fastapi import Depends

async def get_create_order_use_case(
    session: AsyncSession = Depends(get_session),
) -> CreateOrderUseCase:
    return CreateOrderUseCase(
        order_repo=SQLAlchemyOrderRepository(session),
        payment=StripePaymentGateway(),
        notification=SlackNotificationService(),
    )

# presentation/api/orders.py
@router.post("/orders")
async def create_order(
    body: CreateOrderRequest,
    use_case: CreateOrderUseCase = Depends(get_create_order_use_case),
):
    result = await use_case.execute(CreateOrderInput(
        customer_id=body.customer_id,
        items=body.items,
    ))
    return result
```

클린 아키텍처 장점:
- **테스트 용이**: 유스케이스를 DB 없이 테스트 가능
- **프레임워크 독립**: FastAPI → Django 변경 시 도메인 코드 변경 없음
- **유지보수**: 비즈니스 로직이 한 곳에 집중'''),

    # ═══ 마이크로서비스 ═══
    m("마이크로서비스 아키텍처 설계 방법 알려줘",
'''마이크로서비스 설계의 핵심 패턴입니다.

```
═══ 서비스 분리 예시 (이커머스) ═══

[API Gateway]
     │
     ├── 사용자 서비스  (User Service)
     ├── 상품 서비스    (Product Service)
     ├── 주문 서비스    (Order Service)
     ├── 결제 서비스    (Payment Service)
     └── 알림 서비스    (Notification Service)

각 서비스: 독립 DB + 독립 배포 + 독립 스케일링
```

```python
# ═══ 1. API Gateway 패턴 ═══
# gateway/main.py
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

SERVICES = {
    "users": "http://user-service:8001",
    "products": "http://product-service:8002",
    "orders": "http://order-service:8003",
}

@app.api_route("/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(service: str, path: str, request: Request):
    if service not in SERVICES:
        return {"error": "서비스 없음"}, 404

    url = f"{SERVICES[service]}/{path}"
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=url,
            headers=dict(request.headers),
            content=await request.body(),
            params=dict(request.query_params),
        )
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers),
    )

# ═══ 2. 이벤트 기반 통신 (비동기) ═══
# 서비스 간 직접 호출 대신 이벤트 발행/구독

import aio_pika
import json

class EventBus:
    def __init__(self, url: str = "amqp://rabbitmq"):
        self.url = url

    async def publish(self, event_type: str, data: dict):
        """이벤트 발행."""
        connection = await aio_pika.connect(self.url)
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange("events", "topic")
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps({
                        "type": event_type,
                        "data": data,
                        "timestamp": datetime.now().isoformat(),
                    }).encode()
                ),
                routing_key=event_type,
            )

    async def subscribe(self, event_type: str, handler):
        """이벤트 구독."""
        connection = await aio_pika.connect(self.url)
        channel = await connection.channel()
        exchange = await channel.declare_exchange("events", "topic")
        queue = await channel.declare_queue(f"{event_type}_queue")
        await queue.bind(exchange, routing_key=event_type)

        async for message in queue:
            async with message.process():
                event = json.loads(message.body.decode())
                await handler(event)

# 주문 서비스에서 이벤트 발행
event_bus = EventBus()

async def create_order(order_data):
    order = await save_order(order_data)
    # 이벤트 발행 → 다른 서비스가 반응
    await event_bus.publish("order.created", {
        "order_id": order.id,
        "customer_id": order.customer_id,
        "total": order.total,
    })
    return order

# 결제 서비스에서 구독
async def handle_order_created(event):
    """주문 생성 이벤트 → 결제 처리."""
    order_data = event["data"]
    await process_payment(order_data["order_id"], order_data["total"])

await event_bus.subscribe("order.created", handle_order_created)

# ═══ 3. Saga 패턴 (분산 트랜잭션) ═══
class OrderSaga:
    """주문 생성 사가 (보상 트랜잭션)."""

    async def execute(self, order_data: dict):
        try:
            # Step 1: 재고 차감
            reservation = await inventory_service.reserve(order_data["items"])

            # Step 2: 결제
            payment = await payment_service.charge(order_data["total"])

            # Step 3: 주문 확정
            order = await order_service.confirm(order_data)

            return order
        except PaymentError:
            # 보상: 재고 복구
            await inventory_service.release(reservation.id)
            raise
        except OrderError:
            # 보상: 결제 취소 + 재고 복구
            await payment_service.refund(payment.transaction_id)
            await inventory_service.release(reservation.id)
            raise

# ═══ 4. 서킷 브레이커 (장애 전파 방지) ═══
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"       # 정상
    OPEN = "open"           # 차단 (장애)
    HALF_OPEN = "half_open" # 시험 중

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout: float = 30):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = 0

    async def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError("서비스 일시 중단")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
```

마이크로서비스 핵심 원칙:
1. **서비스 당 하나의 DB** (데이터 독립성)
2. **API 또는 이벤트로만 통신** (직접 DB 접근 금지)
3. **서킷 브레이커** (장애 전파 방지)
4. **Saga 패턴** (분산 트랜잭션 대체)
5. **각 서비스 독립 배포 가능**'''),

    # ═══ 시스템 디자인 ═══
    m("대규모 시스템 설계 면접 팁 알려줘 URL 단축 서비스 예시로",
'''URL 단축 서비스(bit.ly) 시스템 설계 예시입니다.

```
═══ 1. 요구사항 정리 ═══

기능 요구사항:
- 긴 URL → 짧은 URL 생성
- 짧은 URL → 원본 URL 리다이렉트
- (선택) 클릭 통계, 만료 설정, 커스텀 별칭

비기능 요구사항:
- 월 1억 URL 생성, 읽기:쓰기 = 100:1
- 읽기 QPS: ~40,000 (1억 × 100 / 30일 / 86400초)
- 쓰기 QPS: ~400
- 99.9% 가용성
- 리다이렉트 지연: < 100ms
- 5년간 저장: 약 60억 URL

═══ 2. API 설계 ═══

POST /api/shorten
  Body: { "long_url": "https://...", "custom_alias": "my-link", "expires_at": "..." }
  Response: { "short_url": "https://hwr.ng/abc123" }

GET /{short_code}
  → 301 Redirect (영구) 또는 302 (임시, 통계용)

GET /api/stats/{short_code}
  → { "clicks": 12345, "created_at": "...", "top_referrers": [...] }

═══ 3. 단축 코드 생성 전략 ═══

방법 1: Base62 인코딩 (추천)
- [a-zA-Z0-9] = 62자
- 7자리 → 62^7 = 3.5조 조합 (충분)
- 자동 증가 ID → Base62 변환

방법 2: 해시 기반
- MD5(URL) → 처음 7자
- 충돌 시 카운터 추가

방법 3: 사전 생성
- 키를 미리 생성해두고 할당
- 동시성 문제 없음 (가장 안전)

═══ 4. 아키텍처 ═══

[Client] → [Load Balancer]
                 │
         [API Servers (Stateless)]
                 │
    ┌────────────┼────────────┐
    │            │            │
[Redis Cache] [PostgreSQL] [Analytics DB]
 (읽기 캐시)   (URL 저장)   (클릭 통계)

구성요소:
- Load Balancer: 트래픽 분산
- API Server: Stateless, 수평 확장
- Redis: 인기 URL 캐시 (읽기의 80%)
- PostgreSQL: URL 매핑 저장 (샤딩)
- Analytics: 클릭 이벤트 (Kafka → ClickHouse)

═══ 5. 데이터베이스 설계 ═══

urls 테이블:
  id: BIGINT (PK, auto_increment)
  short_code: VARCHAR(10) (UNIQUE INDEX)
  long_url: TEXT
  user_id: BIGINT (nullable)
  created_at: TIMESTAMP
  expires_at: TIMESTAMP (nullable)
  click_count: INT (비정규화, 빠른 조회)

샤딩 키: short_code의 첫 2자 (62 × 62 = 3,844 샤드)

═══ 6. 캐시 전략 ═══

LRU 캐시 (Redis):
- 전체 URL의 20%가 80%의 트래픽 (파레토)
- 캐시 크기: 60억 × 20% × 500B = 600GB → 여러 Redis 노드
- TTL: 24시간

조회 흐름:
1. Redis 확인 → 있으면 바로 리다이렉트
2. DB 조회 → 있으면 Redis에 저장 + 리다이렉트
3. 404 반환

═══ 7. 확장 고려 ═══

- 읽기 확장: Redis 클러스터 + Read Replica
- 쓰기 확장: ID 생성기 분산 (Snowflake ID)
- 지역 분산: CDN + 지역별 리다이렉트
- 보안: Rate Limiting, 악성 URL 필터링
```

시스템 디자인 면접 순서:
1. 요구사항 명확화 (5분)
2. 대략적 추정 (QPS, 저장량)
3. 고수준 설계 (다이어그램)
4. 핵심 컴포넌트 상세 설계
5. 확장성/장애 대응 논의'''),

    # ═══ API 설계 원칙 ═══
    m("REST API 설계 베스트 프랙티스 알려줘",
'''실무에서 쓰는 REST API 설계 원칙입니다.

```
═══ URL 설계 ═══

✅ 좋은 예:
GET    /api/v1/users              # 목록 조회
GET    /api/v1/users/123          # 단일 조회
POST   /api/v1/users              # 생성
PATCH  /api/v1/users/123          # 부분 수정
DELETE /api/v1/users/123          # 삭제
GET    /api/v1/users/123/orders   # 관계 조회

❌ 나쁜 예:
GET    /api/getUser?id=123        # 동사 사용
POST   /api/deleteUser            # POST로 삭제
GET    /api/user_list             # 단수/복수 혼용

═══ 쿼리 파라미터 ═══

# 페이지네이션
GET /api/v1/users?page=1&limit=20

# 필터링
GET /api/v1/users?status=active&role=admin

# 정렬
GET /api/v1/users?sort=-created_at,name  # - = 내림차순

# 검색
GET /api/v1/users?q=홍길동

# 필드 선택
GET /api/v1/users?fields=id,name,email

═══ 응답 형식 ═══

# 성공 (200 OK)
{
  "data": [
    { "id": 1, "name": "홍길동", "email": "hong@test.com" }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 150,
    "total_pages": 8
  }
}

# 단일 항목 (200 OK)
{
  "data": { "id": 1, "name": "홍길동" }
}

# 생성 (201 Created)
{
  "data": { "id": 123, "name": "홍길동" }
}

# 에러 (4xx/5xx)
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "입력값이 올바르지 않습니다",
    "details": [
      { "field": "email", "message": "올바른 이메일 형식이 아닙니다" },
      { "field": "name", "message": "이름은 2자 이상이어야 합니다" }
    ]
  }
}
```

```python
# FastAPI 구현 예시
from fastapi import FastAPI, Query, Path, HTTPException
from pydantic import BaseModel

# 응답 모델
class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: Pagination

# 엔드포인트
@router.get("/users", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, pattern="^(active|inactive)$"),
    q: str | None = Query(None, min_length=1),
    sort: str = Query("-created_at"),
):
    ...
```

HTTP 상태 코드:
| 코드 | 의미 | 사용 |
|------|------|------|
| 200 | 성공 | 조회, 수정 |
| 201 | 생성됨 | POST 성공 |
| 204 | 내용 없음 | DELETE 성공 |
| 400 | 잘못된 요청 | 파라미터 오류 |
| 401 | 인증 필요 | 로그인 안 함 |
| 403 | 권한 없음 | 권한 부족 |
| 404 | 없음 | 리소스 없음 |
| 409 | 충돌 | 중복 생성 |
| 422 | 검증 실패 | 입력값 오류 |
| 429 | 요청 과다 | Rate Limit |
| 500 | 서버 오류 | 내부 오류 |

API 버전 관리: URL에 `/v1/` 포함 (가장 명확).'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/architecture.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 아키텍처/설계 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  아키텍처: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
