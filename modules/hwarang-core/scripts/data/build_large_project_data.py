"""화랑 AI 대형 프로젝트 학습 데이터

실제 서비스 수준의 대규모 프로젝트 설계 + 구현.
아키텍처 설계 → 전체 구조 → 핵심 모듈별 코드 → 배포까지.

프로젝트:
  1. SaaS 풀스택 (인증+결제+대시보드+관리자)
  2. 이커머스 (상품+장바구니+결제+배송추적)
  3. 마이크로서비스 아키텍처
  4. 모바일 앱 (React Native)
  5. DevOps 파이프라인 (Docker+K8s+CI/CD)
  6. 데이터 파이프라인 (ETL+분석+시각화)

사용법:
    python scripts/data/build_large_project_data.py \
        --output data/sft/large_projects.jsonl
"""

import json
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SYSTEM = """당신은 화랑 AI입니다. 10년차 시니어 풀스택 개발자 수준의 AI 어시스턴트입니다.
대규모 프로젝트의 아키텍처 설계부터 구현, 배포까지 안내합니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다.
프로젝트 구조 → 핵심 설계 → 모듈별 코드 → 배포 순서로 답변합니다."""


def make(q, a):
    return {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": q},
        {"role": "assistant", "content": a},
    ]}


# ═══════════════════════════════════════════════════════════════
# 1. SaaS 풀스택
# ═══════════════════════════════════════════════════════════════

SAAS = [
    make("SaaS 서비스를 처음부터 만들고 싶어. 인증, 결제, 대시보드, 관리자 패널 다 포함해서 전체 아키텍처 설계해줘",
'''SaaS 서비스 전체 아키텍처를 설계하겠습니다.

## 기술 스택

```
프론트:  Next.js 15 + TypeScript + Tailwind CSS
백엔드:  Next.js API Routes (또는 별도 FastAPI)
DB:      PostgreSQL + Prisma ORM
인증:    NextAuth.js (Google/Kakao/이메일)
결제:    토스페이먼츠
배포:    Docker + Nginx + Let's Encrypt
모니터링: Sentry + Grafana
```

## 프로젝트 구조

```
saas-app/
├── prisma/
│   └── schema.prisma              # 전체 DB 스키마
├── src/
│   ├── app/
│   │   ├── (marketing)/           # 랜딩, 가격, 소개
│   │   │   ├── page.tsx           # 랜딩 페이지
│   │   │   └── pricing/page.tsx   # 가격 페이지
│   │   ├── (auth)/                # 인증
│   │   │   ├── login/page.tsx
│   │   │   └── register/page.tsx
│   │   ├── (dashboard)/           # 유저 대시보드
│   │   │   ├── layout.tsx         # 사이드바 레이아웃
│   │   │   ├── page.tsx           # 메인 대시보드
│   │   │   ├── settings/page.tsx
│   │   │   └── billing/page.tsx
│   │   ├── admin/                 # 관리자 패널
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx           # 관리자 대시보드
│   │   │   ├── users/page.tsx
│   │   │   └── plans/page.tsx
│   │   └── api/
│   │       ├── auth/[...nextauth]/route.ts
│   │       ├── payment/
│   │       │   ├── route.ts       # 결제 요청
│   │       │   └── webhook/route.ts # 토스 웹훅
│   │       ├── users/
│   │       │   └── route.ts
│   │       └── admin/
│   │           └── route.ts
│   ├── components/
│   │   ├── ui/                    # 공통 UI (버튼, 카드 등)
│   │   ├── dashboard/             # 대시보드 전용
│   │   └── admin/                 # 관리자 전용
│   ├── lib/
│   │   ├── auth.ts                # 인증 설정
│   │   ├── db.ts                  # Prisma 클라이언트
│   │   ├── payment.ts             # 결제 유틸
│   │   └── email.ts               # 이메일 발송
│   └── middleware.ts              # 인증 + 역할 체크
├── docker-compose.yml
├── Dockerfile
└── .env
```

## DB 스키마 (핵심)

```prisma
// prisma/schema.prisma
model User {
  id             String    @id @default(cuid())
  email          String    @unique
  name           String?
  hashedPassword String?
  image          String?
  role           Role      @default(USER)

  // 구독
  plan           Plan?     @relation(fields: [planId], references: [id])
  planId         String?
  subscription   Subscription?

  // 관계
  accounts       Account[]
  sessions       Session[]
  payments       Payment[]

  createdAt      DateTime  @default(now())
  updatedAt      DateTime  @updatedAt
}

enum Role {
  USER
  ADMIN
  SUPER_ADMIN
}

model Plan {
  id             String    @id @default(cuid())
  name           String    @unique   // free, starter, pro, business
  displayName    String
  priceMonthly   Int       @default(0)
  features       String[]
  users          User[]
}

model Subscription {
  id             String    @id @default(cuid())
  userId         String    @unique
  user           User      @relation(fields: [userId], references: [id])
  planId         String
  status         String    @default("active") // active, canceled, expired
  currentPeriodStart DateTime
  currentPeriodEnd   DateTime
  canceledAt     DateTime?
}

model Payment {
  id             String    @id @default(cuid())
  userId         String
  user           User      @relation(fields: [userId], references: [id])
  amount         Int
  status         String    @default("pending") // pending, paid, failed, refunded
  pgOrderId      String    @unique
  pgPaymentKey   String?
  paidAt         DateTime?
  createdAt      DateTime  @default(now())
}
```

## 인증 미들웨어

```typescript
// src/middleware.ts
import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

export async function middleware(request: NextRequest) {
  const token = await getToken({ req: request });
  const { pathname } = request.nextUrl;

  // 대시보드: 로그인 필수
  if (pathname.startsWith("/dashboard") && !token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // 관리자: ADMIN 이상만
  if (pathname.startsWith("/admin")) {
    if (!token || !["ADMIN", "SUPER_ADMIN"].includes(token.role as string)) {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/admin/:path*"],
};
```

## 결제 연동 (토스페이먼츠)

```typescript
// src/lib/payment.ts
const TOSS_SECRET = process.env.TOSS_SECRET_KEY!;

export async function 결제승인(paymentKey: string, orderId: string, amount: number) {
  const 인증 = Buffer.from(`${TOSS_SECRET}:`).toString("base64");

  const 응답 = await fetch("https://api.tosspayments.com/v1/payments/confirm", {
    method: "POST",
    headers: {
      Authorization: `Basic ${인증}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ paymentKey, orderId, amount }),
  });

  if (!응답.ok) {
    const 오류 = await 응답.json();
    throw new Error(오류.message || "결제 승인 실패");
  }

  return 응답.json();
}

export async function 구독처리(userId: string, planName: string) {
  // 1. 플랜 조회
  const plan = await prisma.plan.findUnique({ where: { name: planName } });
  if (!plan) throw new Error("플랜 없음");

  // 2. 유저 플랜 변경
  await prisma.user.update({
    where: { id: userId },
    data: { planId: plan.id },
  });

  // 3. 구독 생성/갱신
  const now = new Date();
  const endDate = new Date(now.getFullYear(), now.getMonth() + 1, now.getDate());

  await prisma.subscription.upsert({
    where: { userId },
    update: {
      planId: plan.id,
      status: "active",
      currentPeriodStart: now,
      currentPeriodEnd: endDate,
    },
    create: {
      userId,
      planId: plan.id,
      currentPeriodStart: now,
      currentPeriodEnd: endDate,
    },
  });
}
```

## Docker 배포

```yaml
# docker-compose.yml
version: "3.9"
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: saas
      POSTGRES_USER: saas
      POSTGRES_PASSWORD: $DB_PASSWORD
    volumes:
      - db_data:/var/lib/postgresql/data

  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://saas:$DB_PASSWORD@db:5432/saas
      NEXTAUTH_URL: https://내도메인.com
      NEXTAUTH_SECRET: $AUTH_SECRET
      TOSS_SECRET_KEY: $TOSS_KEY
    depends_on:
      - db

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - certbot_data:/etc/letsencrypt

volumes:
  db_data:
  certbot_data:
```

## 런칭 체크리스트

```
[ ] DB 마이그레이션 (prisma db push)
[ ] 관리자 계정 생성
[ ] 플랜 데이터 시드 (Free, Starter, Pro)
[ ] 토스페이먼츠 테스트 연동
[ ] 도메인 + SSL 설정
[ ] 이메일 발송 설정 (회원가입 인증)
[ ] Sentry 에러 모니터링
[ ] 백업 크론잡 설정
```

이 구조로 시작하면 확장 가능한 SaaS를 만들 수 있습니다. 어떤 부분부터 자세히 구현할까요?'''),

    # ─── 이커머스 ────────────────────────────────────────
    make("이커머스 쇼핑몰 전체 아키텍처 설계해줘. 상품관리, 장바구니, 결제, 배송추적까지",
'''이커머스 쇼핑몰 전체 아키텍처입니다.

## 기술 스택

```
프론트:    Next.js 15 + TypeScript + Tailwind
백엔드:    Next.js API Routes
DB:        PostgreSQL + Prisma
결제:      토스페이먼츠
파일저장:  AWS S3 (상품 이미지)
검색:      Elasticsearch (상품 검색)
캐시:      Redis (장바구니, 세션)
```

## 핵심 DB 스키마

```prisma
// 상품
model Product {
  id          String   @id @default(cuid())
  name        String
  description String   @db.Text
  price       Int                          // 원 단위
  salePrice   Int?                         // 할인가
  stock       Int      @default(0)
  images      String[]                     // S3 URL들
  category    Category @relation(fields: [categoryId], references: [id])
  categoryId  String
  isActive    Boolean  @default(true)
  options     ProductOption[]
  orderItems  OrderItem[]
  reviews     Review[]
  createdAt   DateTime @default(now())
}

model Category {
  id       String    @id @default(cuid())
  name     String    @unique
  slug     String    @unique
  products Product[]
}

model ProductOption {
  id        String  @id @default(cuid())
  productId String
  product   Product @relation(fields: [productId], references: [id])
  name      String               // "색상", "사이즈"
  values    String[]             // ["빨강", "파랑"]
  priceAdd  Int     @default(0)  // 추가 금액
}

// 주문
model Order {
  id            String      @id @default(cuid())
  userId        String
  user          User        @relation(fields: [userId], references: [id])
  items         OrderItem[]
  totalAmount   Int
  status        OrderStatus @default(PENDING)
  // 배송
  shippingName    String
  shippingPhone   String
  shippingAddress String
  shippingMemo    String?
  trackingNumber  String?
  trackingCompany String?
  // 결제
  paymentId     String?
  paidAt        DateTime?
  createdAt     DateTime    @default(now())
}

enum OrderStatus {
  PENDING        // 결제 대기
  PAID           // 결제 완료
  PREPARING      // 상품 준비
  SHIPPED        // 배송 중
  DELIVERED      // 배송 완료
  CANCELED       // 취소
  REFUNDED       // 환불
}

model OrderItem {
  id        String  @id @default(cuid())
  orderId   String
  order     Order   @relation(fields: [orderId], references: [id])
  productId String
  product   Product @relation(fields: [productId], references: [id])
  quantity  Int
  price     Int     // 구매 시점 가격
  options   Json?   // 선택한 옵션
}

// 리뷰
model Review {
  id        String  @id @default(cuid())
  userId    String
  productId String
  product   Product @relation(fields: [productId], references: [id])
  rating    Int               // 1~5
  content   String
  images    String[]
  createdAt DateTime @default(now())
}
```

## 장바구니 (Redis)

```typescript
// src/lib/cart.ts
import Redis from "ioredis";

const redis = new Redis(process.env.REDIS_URL);

interface 장바구니아이템 {
  productId: string;
  quantity: number;
  options?: Record<string, string>;
}

export async function 장바구니_조회(userId: string): Promise<장바구니아이템[]> {
  const 데이터 = await redis.get(`cart:${userId}`);
  return 데이터 ? JSON.parse(데이터) : [];
}

export async function 장바구니_추가(userId: string, 아이템: 장바구니아이템) {
  const 장바구니 = await 장바구니_조회(userId);

  // 같은 상품 있으면 수량 증가
  const 기존 = 장바구니.find(i => i.productId === 아이템.productId);
  if (기존) {
    기존.quantity += 아이템.quantity;
  } else {
    장바구니.push(아이템);
  }

  await redis.set(`cart:${userId}`, JSON.stringify(장바구니), "EX", 86400 * 7); // 7일
}

export async function 장바구니_삭제(userId: string, productId: string) {
  const 장바구니 = await 장바구니_조회(userId);
  const 필터 = 장바구니.filter(i => i.productId !== productId);
  await redis.set(`cart:${userId}`, JSON.stringify(필터), "EX", 86400 * 7);
}

export async function 장바구니_비우기(userId: string) {
  await redis.del(`cart:${userId}`);
}
```

## 주문 처리 API

```typescript
// src/app/api/orders/route.ts
export async function POST(request: Request) {
  const session = await auth();
  if (!session?.user?.id) return Response.json({ error: "로그인 필요" }, { status: 401 });

  const { shippingName, shippingPhone, shippingAddress, shippingMemo } = await request.json();

  // 1. 장바구니 조회
  const 장바구니 = await 장바구니_조회(session.user.id);
  if (장바구니.length === 0) return Response.json({ error: "장바구니 비어있음" }, { status: 400 });

  // 2. 상품 정보 + 재고 확인
  const 상품들 = await prisma.product.findMany({
    where: { id: { in: 장바구니.map(i => i.productId) } },
  });

  // 재고 확인
  for (const item of 장바구니) {
    const 상품 = 상품들.find(p => p.id === item.productId);
    if (!상품 || 상품.stock < item.quantity) {
      return Response.json({ error: `${상품?.name || "상품"} 재고 부족` }, { status: 400 });
    }
  }

  // 3. 총액 계산
  const 총액 = 장바구니.reduce((합, item) => {
    const 상품 = 상품들.find(p => p.id === item.productId)!;
    return 합 + (상품.salePrice || 상품.price) * item.quantity;
  }, 0);

  // 4. 주문 생성 (트랜잭션)
  const 주문 = await prisma.$transaction(async (tx) => {
    // 주문 생성
    const order = await tx.order.create({
      data: {
        userId: session.user.id,
        totalAmount: 총액,
        shippingName, shippingPhone, shippingAddress, shippingMemo,
        items: {
          create: 장바구니.map(item => {
            const 상품 = 상품들.find(p => p.id === item.productId)!;
            return {
              productId: item.productId,
              quantity: item.quantity,
              price: 상품.salePrice || 상품.price,
              options: item.options,
            };
          }),
        },
      },
    });

    // 재고 차감
    for (const item of 장바구니) {
      await tx.product.update({
        where: { id: item.productId },
        data: { stock: { decrement: item.quantity } },
      });
    }

    return order;
  });

  // 5. 장바구니 비우기
  await 장바구니_비우기(session.user.id);

  return Response.json({ orderId: 주문.id, amount: 총액 });
}
```

## 배송 추적

```typescript
// src/app/api/orders/[id]/tracking/route.ts
export async function PUT(request: Request, { params }: { params: { id: string } }) {
  const { trackingNumber, trackingCompany } = await request.json();

  const 주문 = await prisma.order.update({
    where: { id: params.id },
    data: {
      trackingNumber,
      trackingCompany,
      status: "SHIPPED",
    },
  });

  // 배송 알림 (이메일/푸시)
  await 알림전송(주문.userId, {
    제목: "상품이 발송되었습니다",
    내용: `운송장번호: ${trackingNumber} (${trackingCompany})`,
  });

  return Response.json(주문);
}
```

## 배포

```bash
# Docker
docker compose up -d

# DB 초기화
npx prisma db push
npx prisma db seed  # 카테고리, 테스트 상품

# SSL
certbot --nginx -d shop.example.com
```

이 구조로 확장 가능한 이커머스를 만들 수 있습니다.'''),

    # ─── 마이크로서비스 ──────────────────────────────────
    make("마이크로서비스 아키텍처로 대규모 서비스 설계하는 방법 알려줘",
'''마이크로서비스 아키텍처 설계 가이드입니다.

## 모놀리식 vs 마이크로서비스

```
모놀리식:  하나의 앱에 모든 기능
  장점: 간단, 배포 쉬움, 초기 개발 빠름
  단점: 커지면 복잡, 한 부분 수정 = 전체 배포

마이크로서비스:  기능별 독립 서비스
  장점: 독립 배포, 팀별 개발, 기술 자유
  단점: 복잡, 네트워크 비용, 데이터 일관성
```

## 예시: 이커머스 마이크로서비스

```
┌─────────────────────────────────────────────────┐
│                  API Gateway                     │
│              (Nginx / Kong / Traefik)            │
├─────────────────────────────────────────────────┤
│                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ 유저     │ │ 상품     │ │ 주문     │         │
│  │ 서비스   │ │ 서비스   │ │ 서비스   │         │
│  │ :3001    │ │ :3002    │ │ :3003    │         │
│  │ (Auth)   │ │ (Catalog)│ │ (Order)  │         │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘         │
│       │            │            │                │
│  ┌────┴────┐  ┌────┴────┐  ┌────┴────┐          │
│  │ User DB │  │ Prod DB │  │ Order DB│          │
│  │ (PG)    │  │ (PG)    │  │ (PG)    │          │
│  └─────────┘  └─────────┘  └─────────┘          │
│                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ 결제     │ │ 배송     │ │ 알림     │         │
│  │ 서비스   │ │ 서비스   │ │ 서비스   │         │
│  │ :3004    │ │ :3005    │ │ :3006    │         │
│  └──────────┘ └──────────┘ └──────────┘         │
│                                                   │
│  ┌──────────────────────────────────────┐        │
│  │     메시지 큐 (RabbitMQ / Kafka)      │        │
│  └──────────────────────────────────────┘        │
└─────────────────────────────────────────────────┘
```

## 서비스 간 통신

```python
# 1. 동기 통신 (REST) - 즉시 응답 필요할 때
# 주문 서비스 → 상품 서비스 (재고 확인)
import httpx

async def 재고확인(product_id: str, quantity: int) -> bool:
    async with httpx.AsyncClient() as client:
        응답 = await client.get(
            f"http://product-service:3002/api/products/{product_id}/stock",
            params={"quantity": quantity},
        )
        return 응답.json()["available"]

# 2. 비동기 통신 (메시지 큐) - 느슨한 결합
# 주문 완료 → 이벤트 발행 → 여러 서비스가 구독
import pika

def 이벤트_발행(이벤트명: str, 데이터: dict):
    connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = connection.channel()
    channel.exchange_declare(exchange="events", exchange_type="topic")
    channel.basic_publish(
        exchange="events",
        routing_key=이벤트명,
        body=json.dumps(데이터),
    )
    connection.close()

# 주문 완료 시
이벤트_발행("order.completed", {
    "orderId": "abc123",
    "userId": "user456",
    "amount": 50000,
})

# 결제 서비스가 구독 → 결제 처리
# 알림 서비스가 구독 → 이메일 발송
# 배송 서비스가 구독 → 배송 준비
```

## Docker Compose (전체 스택)

```yaml
version: "3.9"
services:
  # API Gateway
  gateway:
    image: nginx:alpine
    ports: ["80:80"]
    volumes: ["./nginx.conf:/etc/nginx/conf.d/default.conf"]

  # 각 서비스
  user-service:
    build: ./services/user
    environment:
      DATABASE_URL: postgresql://user:pass@user-db:5432/users

  product-service:
    build: ./services/product
    environment:
      DATABASE_URL: postgresql://user:pass@product-db:5432/products

  order-service:
    build: ./services/order
    environment:
      DATABASE_URL: postgresql://user:pass@order-db:5432/orders
      RABBITMQ_URL: amqp://rabbitmq:5672

  # DB (서비스별 독립)
  user-db:
    image: postgres:16-alpine
  product-db:
    image: postgres:16-alpine
  order-db:
    image: postgres:16-alpine

  # 메시지 큐
  rabbitmq:
    image: rabbitmq:3-management
    ports: ["15672:15672"]  # 관리 UI

  # 모니터링
  prometheus:
    image: prom/prometheus
  grafana:
    image: grafana/grafana
```

## 핵심 원칙

```
1. 서비스당 DB 1개 (데이터 독립)
2. API Gateway로 외부 접근 통제
3. 서비스 간 통신: REST (동기) + 메시지 큐 (비동기)
4. 각 서비스 독립 배포 가능
5. 장애 격리: 한 서비스 장애가 전체에 영향 안 줌
6. 서비스 디스커버리: Docker DNS 또는 Consul
```

**주의**: 서비스가 5개 미만이면 모놀리식이 더 낫습니다. 마이크로서비스는 복잡도가 높으니 팀과 규모가 클 때 도입하세요.'''),

    # ─── DevOps ──────────────────────────────────────────
    make("CI/CD 파이프라인 전체를 구축해줘. GitHub Actions + Docker + 자동 배포",
'''CI/CD 파이프라인 전체 구축 가이드입니다.

## 전체 흐름

```
개발자 → Git Push → GitHub Actions →
  1. 린트 + 타입 체크
  2. 테스트
  3. Docker 이미지 빌드
  4. 이미지 레지스트리 Push
  5. 서버 배포 (SSH)
  6. 헬스 체크
  7. Slack 알림
```

## GitHub Actions 워크플로우

```yaml
# .github/workflows/deploy.yml
name: 배포 파이프라인

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # ───── 1단계: 검증 ─────
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Node.js 설정
        uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - name: 의존성 설치
        run: pnpm install --frozen-lockfile

      - name: 린트
        run: pnpm lint

      - name: 타입 체크
        run: pnpm tsc --noEmit

      - name: 테스트
        run: pnpm test
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports: ["5432:5432"]

  # ───── 2단계: 빌드 + 푸시 ─────
  build:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Docker 로그인
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: 이미지 빌드 + 푸시
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}

  # ───── 3단계: 배포 ─────
  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: 서버 배포
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /home/app
            docker compose pull
            docker compose up -d --remove-orphans

            # 헬스 체크 (30초 대기)
            for i in $(seq 1 30); do
              if curl -f http://localhost:3000/api/health > /dev/null 2>&1; then
                echo "배포 성공!"
                exit 0
              fi
              echo "대기 중... ($i/30)"
              sleep 1
            done
            echo "헬스 체크 실패!"
            docker compose logs --tail 50
            exit 1

      - name: Slack 알림
        if: always()
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: |
            배포 ${{ job.status == 'success' && '성공 ✅' || '실패 ❌' }}
            커밋: ${{ github.event.head_commit.message }}
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

## Dockerfile (멀티스테이지)

```dockerfile
# ── 빌드 단계 ──
FROM node:22-alpine AS builder
WORKDIR /app
RUN npm install -g pnpm

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# ── 실행 단계 (최소 이미지) ──
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# 필요한 파일만 복사
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
```

## 롤백 전략

```bash
# 배포 실패 시 이전 버전으로 롤백
# docker-compose.yml에서 이미지 태그를 이전 SHA로 변경
docker compose pull
docker compose up -d

# 또는 GitHub Actions에서 이전 빌드 재배포
gh workflow run deploy.yml --ref 이전커밋SHA
```

이 파이프라인으로 **코드 푸시만 하면 자동 테스트 → 빌드 → 배포**가 됩니다.'''),
]


# ═══════════════════════════════════════════════════════════════
# 5. 소셜미디어
# ═══════════════════════════════════════════════════════════════

SOCIAL = [
    make("소셜미디어 앱 설계해줘. 피드, 팔로우, 좋아요, 댓글, DM 포함",
'''소셜미디어 앱 전체 설계입니다.

## DB 스키마

```prisma
model User {
  id         String   @id @default(cuid())
  username   String   @unique
  displayName String
  bio        String?
  avatarUrl  String?
  posts      Post[]
  likes      Like[]
  comments   Comment[]
  followers  Follow[] @relation("following")
  following  Follow[] @relation("follower")
  sentDMs    DirectMessage[] @relation("sender")
  receivedDMs DirectMessage[] @relation("receiver")
  createdAt  DateTime @default(now())
}

model Post {
  id        String    @id @default(cuid())
  content   String    @db.Text
  images    String[]
  author    User      @relation(fields: [authorId], references: [id])
  authorId  String
  likes     Like[]
  comments  Comment[]
  isPublic  Boolean   @default(true)
  createdAt DateTime  @default(now())
  @@index([authorId, createdAt(sort: Desc)])
}

model Follow {
  id          String @id @default(cuid())
  follower    User   @relation("follower", fields: [followerId], references: [id])
  followerId  String
  following   User   @relation("following", fields: [followingId], references: [id])
  followingId String
  createdAt   DateTime @default(now())
  @@unique([followerId, followingId])
}

model Like {
  id      String @id @default(cuid())
  userId  String
  user    User   @relation(fields: [userId], references: [id])
  postId  String
  post    Post   @relation(fields: [postId], references: [id], onDelete: Cascade)
  @@unique([userId, postId])
}

model Comment {
  id       String   @id @default(cuid())
  content  String
  userId   String
  user     User     @relation(fields: [userId], references: [id])
  postId   String
  post     Post     @relation(fields: [postId], references: [id], onDelete: Cascade)
  createdAt DateTime @default(now())
}

model DirectMessage {
  id         String   @id @default(cuid())
  content    String
  senderId   String
  sender     User     @relation("sender", fields: [senderId], references: [id])
  receiverId String
  receiver   User     @relation("receiver", fields: [receiverId], references: [id])
  readAt     DateTime?
  createdAt  DateTime @default(now())
  @@index([senderId, receiverId, createdAt])
}
```

## 피드 API (타임라인)

```typescript
// app/api/feed/route.ts
export async function GET(request: Request) {
  const session = await auth();
  if (!session?.user?.id) return Response.json({ error: "로그인 필요" }, { status: 401 });

  // 내가 팔로우한 사람들의 게시글
  const 팔로잉목록 = await prisma.follow.findMany({
    where: { followerId: session.user.id },
    select: { followingId: true },
  });
  const 팔로잉IDs = 팔로잉목록.map(f => f.followingId);
  팔로잉IDs.push(session.user.id); // 내 글도 포함

  const 피드 = await prisma.post.findMany({
    where: { authorId: { in: 팔로잉IDs }, isPublic: true },
    include: {
      author: { select: { username: true, displayName: true, avatarUrl: true } },
      _count: { select: { likes: true, comments: true } },
      likes: { where: { userId: session.user.id }, select: { id: true } },
    },
    orderBy: { createdAt: "desc" },
    take: 20,
  });

  return Response.json(피드.map(p => ({
    ...p,
    isLiked: p.likes.length > 0,
    likeCount: p._count.likes,
    commentCount: p._count.comments,
  })));
}
```

## 팔로우/언팔로우

```typescript
// app/api/follow/route.ts
export async function POST(request: Request) {
  const session = await auth();
  const { targetUserId } = await request.json();

  // 이미 팔로우 중인지 확인
  const 기존 = await prisma.follow.findUnique({
    where: { followerId_followingId: {
      followerId: session.user.id,
      followingId: targetUserId,
    }},
  });

  if (기존) {
    // 언팔로우
    await prisma.follow.delete({ where: { id: 기존.id } });
    return Response.json({ followed: false });
  } else {
    // 팔로우
    await prisma.follow.create({
      data: { followerId: session.user.id, followingId: targetUserId },
    });
    return Response.json({ followed: true });
  }
}
```

## 실시간 DM (WebSocket)

```typescript
// app/api/dm/route.ts
export async function POST(request: Request) {
  const session = await auth();
  const { receiverId, content } = await request.json();

  const 메시지 = await prisma.directMessage.create({
    data: {
      senderId: session.user.id,
      receiverId,
      content,
    },
  });

  // WebSocket으로 실시간 전달 (별도 WS 서버)
  // pusher.trigger(`dm-${receiverId}`, "new-message", 메시지);

  return Response.json(메시지);
}

// DM 목록 (대화 상대별)
export async function GET(request: Request) {
  const session = await auth();

  const 대화들 = await prisma.directMessage.findMany({
    where: {
      OR: [
        { senderId: session.user.id },
        { receiverId: session.user.id },
      ],
    },
    include: {
      sender: { select: { username: true, avatarUrl: true } },
      receiver: { select: { username: true, avatarUrl: true } },
    },
    orderBy: { createdAt: "desc" },
    take: 50,
  });

  return Response.json(대화들);
}
```

이 구조로 Instagram/Twitter 같은 소셜미디어를 만들 수 있습니다.'''),
]

# ═══════════════════════════════════════════════════════════════
# 6. React Native 모바일 앱
# ═══════════════════════════════════════════════════════════════

MOBILE = [
    make("React Native로 모바일 앱 만드는 전체 과정 알려줘",
'''React Native(Expo) 모바일 앱 개발 가이드입니다.

## 프로젝트 생성

```bash
npx create-expo-app 내앱 --template blank-typescript
cd 내앱
npx expo install expo-router expo-linking expo-constants expo-status-bar
```

## 프로젝트 구조

```
내앱/
├── app/
│   ├── _layout.tsx          # 루트 레이아웃
│   ├── index.tsx             # 홈 화면
│   ├── login.tsx             # 로그인
│   ├── (tabs)/
│   │   ├── _layout.tsx       # 탭 네비게이션
│   │   ├── home.tsx          # 홈 탭
│   │   ├── search.tsx        # 검색 탭
│   │   └── profile.tsx       # 프로필 탭
│   └── post/[id].tsx         # 게시글 상세
├── components/
│   ├── PostCard.tsx
│   ├── Avatar.tsx
│   └── Button.tsx
├── hooks/
│   └── useAuth.ts
├── lib/
│   └── api.ts                # API 클라이언트
└── app.json
```

## 탭 네비게이션

```tsx
// app/(tabs)/_layout.tsx
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

export default function TabLayout() {
  return (
    <Tabs screenOptions={{
      tabBarActiveTintColor: "#6366f1",
      headerShown: false,
    }}>
      <Tabs.Screen name="home" options={{
        title: "홈",
        tabBarIcon: ({ color }) => <Ionicons name="home" size={24} color={color} />,
      }} />
      <Tabs.Screen name="search" options={{
        title: "검색",
        tabBarIcon: ({ color }) => <Ionicons name="search" size={24} color={color} />,
      }} />
      <Tabs.Screen name="profile" options={{
        title: "내 정보",
        tabBarIcon: ({ color }) => <Ionicons name="person" size={24} color={color} />,
      }} />
    </Tabs>
  );
}
```

## API 클라이언트

```typescript
// lib/api.ts
const BASE_URL = "https://api.내서비스.com";

class API {
  private token: string | null = null;

  setToken(token: string) { this.token = token; }

  private async request(path: string, options: RequestInit = {}) {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;

    const 응답 = await fetch(`${BASE_URL}${path}`, { ...options, headers });
    if (!응답.ok) throw new Error(`API 오류: ${응답.status}`);
    return 응답.json();
  }

  // 인증
  async 로그인(이메일: string, 비밀번호: string) {
    return this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ 이메일, 비밀번호 }),
    });
  }

  // 피드
  async 피드가져오기(page = 1) {
    return this.request(`/feed?page=${page}`);
  }

  // 게시글
  async 게시글작성(내용: string) {
    return this.request("/posts", {
      method: "POST",
      body: JSON.stringify({ content: 내용 }),
    });
  }
}

export const api = new API();
```

## 무한 스크롤 피드

```tsx
// app/(tabs)/home.tsx
import { useState, useEffect, useCallback } from "react";
import { FlatList, View, Text, RefreshControl, StyleSheet } from "react-native";
import { api } from "@/lib/api";
import { PostCard } from "@/components/PostCard";

export default function HomeScreen() {
  const [게시글들, 게시글설정] = useState([]);
  const [새로고침중, 새로고침설정] = useState(false);
  const [페이지, 페이지설정] = useState(1);

  const 불러오기 = useCallback(async (page = 1) => {
    try {
      const 데이터 = await api.피드가져오기(page);
      if (page === 1) {
        게시글설정(데이터);
      } else {
        게시글설정(이전 => [...이전, ...데이터]);
      }
    } catch (오류) {
      console.error("피드 로드 실패:", 오류);
    }
  }, []);

  useEffect(() => { 불러오기(); }, []);

  const 새로고침 = async () => {
    새로고침설정(true);
    페이지설정(1);
    await 불러오기(1);
    새로고침설정(false);
  };

  const 더불러오기 = () => {
    const 다음 = 페이지 + 1;
    페이지설정(다음);
    불러오기(다음);
  };

  return (
    <FlatList
      data={게시글들}
      renderItem={({ item }) => <PostCard post={item} />}
      keyExtractor={item => item.id}
      onEndReached={더불러오기}
      onEndReachedThreshold={0.5}
      refreshControl={
        <RefreshControl refreshing={새로고침중} onRefresh={새로고침} />
      }
      ListEmptyComponent={
        <View style={styles.empty}>
          <Text>게시글이 없습니다</Text>
        </View>
      }
    />
  );
}

const styles = StyleSheet.create({
  empty: { flex: 1, justifyContent: "center", alignItems: "center", padding: 40 },
});
```

## 빌드 + 배포

```bash
# 개발
npx expo start

# iOS 빌드
eas build --platform ios

# Android 빌드
eas build --platform android

# 스토어 제출
eas submit --platform ios
eas submit --platform android
```

Expo로 시작하면 iOS/Android 동시 개발이 가능합니다.'''),
]

# ═══════════════════════════════════════════════════════════════
# 7. GraphQL API
# ═══════════════════════════════════════════════════════════════

GRAPHQL = [
    make("GraphQL API 서버를 만들어줘. 스키마 설계부터 리졸버까지",
'''GraphQL API 서버 전체 구현입니다.

## 기술 스택

```
서버:    Apollo Server + Express
DB:      Prisma + PostgreSQL
인증:    JWT
```

## GraphQL 스키마

```graphql
# schema.graphql
type Query {
  me: User
  user(id: ID!): User
  users(limit: Int = 20, offset: Int = 0): [User!]!
  post(id: ID!): Post
  feed(limit: Int = 20, cursor: String): FeedConnection!
}

type Mutation {
  register(input: RegisterInput!): AuthPayload!
  login(email: String!, password: String!): AuthPayload!
  createPost(content: String!, images: [String!]): Post!
  likePost(postId: ID!): Post!
  addComment(postId: ID!, content: String!): Comment!
  followUser(userId: ID!): User!
}

type User {
  id: ID!
  username: String!
  displayName: String!
  bio: String
  avatarUrl: String
  posts: [Post!]!
  followerCount: Int!
  followingCount: Int!
  isFollowing: Boolean!
}

type Post {
  id: ID!
  content: String!
  images: [String!]!
  author: User!
  likeCount: Int!
  isLiked: Boolean!
  comments: [Comment!]!
  createdAt: String!
}

type Comment {
  id: ID!
  content: String!
  author: User!
  createdAt: String!
}

type AuthPayload {
  token: String!
  user: User!
}

type FeedConnection {
  edges: [Post!]!
  pageInfo: PageInfo!
}

type PageInfo {
  hasNextPage: Boolean!
  endCursor: String
}

input RegisterInput {
  username: String!
  email: String!
  password: String!
  displayName: String!
}
```

## 리졸버

```typescript
// resolvers/user.ts
export const userResolvers = {
  Query: {
    me: async (_, __, { userId, prisma }) => {
      if (!userId) throw new Error("로그인 필요");
      return prisma.user.findUnique({ where: { id: userId } });
    },

    users: async (_, { limit, offset }, { prisma }) => {
      return prisma.user.findMany({ take: limit, skip: offset });
    },
  },

  User: {
    posts: (user, _, { prisma }) =>
      prisma.post.findMany({ where: { authorId: user.id } }),

    followerCount: (user, _, { prisma }) =>
      prisma.follow.count({ where: { followingId: user.id } }),

    followingCount: (user, _, { prisma }) =>
      prisma.follow.count({ where: { followerId: user.id } }),

    isFollowing: async (user, _, { userId, prisma }) => {
      if (!userId) return false;
      const follow = await prisma.follow.findUnique({
        where: { followerId_followingId: { followerId: userId, followingId: user.id } },
      });
      return !!follow;
    },
  },

  Mutation: {
    createPost: async (_, { content, images }, { userId, prisma }) => {
      if (!userId) throw new Error("로그인 필요");
      return prisma.post.create({
        data: { content, images: images || [], authorId: userId },
      });
    },

    likePost: async (_, { postId }, { userId, prisma }) => {
      const existing = await prisma.like.findUnique({
        where: { userId_postId: { userId, postId } },
      });

      if (existing) {
        await prisma.like.delete({ where: { id: existing.id } });
      } else {
        await prisma.like.create({ data: { userId, postId } });
      }

      return prisma.post.findUnique({ where: { id: postId } });
    },
  },
};
```

## 서버 실행

```typescript
// server.ts
import { ApolloServer } from "@apollo/server";
import { expressMiddleware } from "@apollo/server/express4";
import express from "express";
import { PrismaClient } from "@prisma/client";
import { readFileSync } from "fs";
import { userResolvers } from "./resolvers/user";
import { verifyToken } from "./utils/auth";

const prisma = new PrismaClient();
const typeDefs = readFileSync("schema.graphql", "utf-8");

const server = new ApolloServer({ typeDefs, resolvers: userResolvers });

async function main() {
  await server.start();
  const app = express();

  app.use("/graphql", express.json(), expressMiddleware(server, {
    context: async ({ req }) => {
      const token = req.headers.authorization?.replace("Bearer ", "");
      const userId = token ? verifyToken(token) : null;
      return { userId, prisma };
    },
  }));

  app.listen(4000, () => console.log("GraphQL: http://localhost:4000/graphql"));
}

main();
```

REST 대비 GraphQL은 클라이언트가 필요한 데이터만 요청할 수 있어 효율적입니다.'''),
]

# ═══════════════════════════════════════════════════════════════
# 8. 실시간 대시보드
# ═══════════════════════════════════════════════════════════════

DASHBOARD = [
    make("실시간 모니터링 대시보드 만들어줘. WebSocket + 차트 포함",
'''실시간 대시보드 구현입니다.

## 핵심: Server-Sent Events(SSE) + 차트

```tsx
// app/dashboard/page.tsx
"use client";
import { useState, useEffect } from "react";

interface 메트릭 {
  cpu: number;
  memory: number;
  requests: number;
  errors: number;
  responseTime: number;
  timestamp: string;
}

export default function 대시보드() {
  const [메트릭들, 메트릭설정] = useState<메트릭[]>([]);
  const [현재, 현재설정] = useState<메트릭 | null>(null);

  useEffect(() => {
    // SSE 연결 (실시간 데이터 수신)
    const eventSource = new EventSource("/api/metrics/stream");

    eventSource.onmessage = (event) => {
      const 데이터: 메트릭 = JSON.parse(event.data);
      현재설정(데이터);
      메트릭설정(이전 => [...이전.slice(-59), 데이터]); // 최근 60개
    };

    return () => eventSource.close();
  }, []);

  if (!현재) return <div className="p-8 text-center">연결 중...</div>;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">실시간 모니터링</h1>

      {/* 핵심 지표 카드 */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard title="CPU" value={`${현재.cpu}%`}
          color={현재.cpu > 80 ? "red" : 현재.cpu > 50 ? "yellow" : "green"} />
        <MetricCard title="메모리" value={`${현재.memory}%`}
          color={현재.memory > 80 ? "red" : "green"} />
        <MetricCard title="요청/초" value={현재.requests.toString()} color="blue" />
        <MetricCard title="응답시간" value={`${현재.responseTime}ms`}
          color={현재.responseTime > 1000 ? "red" : "green"} />
      </div>

      {/* 실시간 차트 (최근 60초) */}
      <div className="bg-white rounded-xl border p-4">
        <h3 className="font-semibold mb-4">CPU / 메모리 추이 (60초)</h3>
        <div className="h-64 flex items-end gap-1">
          {메트릭들.map((m, i) => (
            <div key={i} className="flex-1 flex flex-col gap-1">
              <div
                className="bg-blue-500 rounded-t"
                style={{ height: `${m.cpu * 2}px` }}
                title={`CPU ${m.cpu}%`}
              />
              <div
                className="bg-green-500 rounded-t"
                style={{ height: `${m.memory * 2}px` }}
                title={`MEM ${m.memory}%`}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ title, value, color }: { title: string; value: string; color: string }) {
  const colors = {
    red: "border-red-500 text-red-600",
    yellow: "border-yellow-500 text-yellow-600",
    green: "border-green-500 text-green-600",
    blue: "border-blue-500 text-blue-600",
  };
  return (
    <div className={`rounded-xl border-2 p-4 ${colors[color]}`}>
      <div className="text-sm opacity-70">{title}</div>
      <div className="text-3xl font-bold">{value}</div>
    </div>
  );
}
```

## SSE 엔드포인트

```typescript
// app/api/metrics/stream/route.ts
export async function GET() {
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      const interval = setInterval(() => {
        const 메트릭 = {
          cpu: Math.round(Math.random() * 100),
          memory: Math.round(50 + Math.random() * 40),
          requests: Math.round(Math.random() * 500),
          errors: Math.round(Math.random() * 5),
          responseTime: Math.round(50 + Math.random() * 200),
          timestamp: new Date().toISOString(),
        };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(메트릭)}\\n\\n`));
      }, 1000); // 1초마다

      // 정리
      setTimeout(() => {
        clearInterval(interval);
        controller.close();
      }, 3600000); // 1시간 후 종료
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
```

SSE는 WebSocket보다 간단하고, 서버→클라이언트 단방향 실시간 데이터에 적합합니다.'''),
]

# ═══════════════════════════════════════════════════════════════
# 9. ETL 데이터 파이프라인
# ═══════════════════════════════════════════════════════════════

DATA_PIPELINE = [
    make("데이터 파이프라인(ETL) 만들어줘. 수집→변환→저장→시각화",
'''ETL 데이터 파이프라인입니다.

## 구조

```
pipeline/
├── extract/           # 데이터 수집
│   ├── api_fetcher.py
│   ├── db_reader.py
│   └── file_reader.py
├── transform/         # 데이터 변환
│   ├── cleaner.py
│   └── aggregator.py
├── load/              # 데이터 저장
│   ├── db_writer.py
│   └── file_writer.py
├── pipeline.py        # 메인 파이프라인
└── scheduler.py       # 자동 실행 (cron)
```

## 메인 파이프라인

```python
# pipeline.py
import asyncio
import logging
from datetime import datetime
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class 파이프라인결과:
    수집건수: int
    변환건수: int
    저장건수: int
    실패건수: int
    소요시간: float


class 데이터파이프라인:
    """ETL 파이프라인: 수집 → 정제 → 변환 → 저장"""

    def __init__(self):
        self.원본데이터 = []
        self.변환데이터 = []

    # ─── Extract (수집) ─────────────────────
    async def 수집(self, 소스들: list[dict]) -> list[dict]:
        """여러 소스에서 데이터 수집"""
        결과 = []
        for 소스 in 소스들:
            if 소스["type"] == "api":
                데이터 = await self._API수집(소스["url"])
            elif 소스["type"] == "csv":
                데이터 = self._CSV수집(소스["path"])
            elif 소스["type"] == "db":
                데이터 = await self._DB수집(소스["query"])
            else:
                continue
            결과.extend(데이터)
            logger.info(f"  수집: {소스['name']} → {len(데이터)}건")

        self.원본데이터 = 결과
        return 결과

    async def _API수집(self, url: str) -> list[dict]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as 응답:
                return await 응답.json()

    def _CSV수집(self, path: str) -> list[dict]:
        import csv
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))

    # ─── Transform (변환) ───────────────────
    def 변환(self, 데이터: list[dict]) -> list[dict]:
        """데이터 정제 + 변환"""
        결과 = []
        for row in 데이터:
            try:
                정제됨 = self._정제(row)
                if 정제됨:
                    변환됨 = self._변환(정제됨)
                    결과.append(변환됨)
            except Exception as e:
                logger.warning(f"변환 실패: {e}")

        self.변환데이터 = 결과
        logger.info(f"  변환: {len(데이터)} → {len(결과)}건 (탈락 {len(데이터)-len(결과)})")
        return 결과

    def _정제(self, row: dict) -> dict | None:
        """빈 값 제거, 타입 변환"""
        if not row: return None
        정제 = {}
        for k, v in row.items():
            if v is None or v == "": continue
            if isinstance(v, str): v = v.strip()
            정제[k] = v
        return 정제 if 정제 else None

    def _변환(self, row: dict) -> dict:
        """비즈니스 로직 적용"""
        row["처리일시"] = datetime.now().isoformat()
        return row

    # ─── Load (저장) ────────────────────────
    async def 저장(self, 데이터: list[dict], 대상: str = "json"):
        """변환된 데이터 저장"""
        if 대상 == "json":
            import json
            with open("output/결과.json", "w", encoding="utf-8") as f:
                json.dump(데이터, f, ensure_ascii=False, indent=2)
        elif 대상 == "csv":
            import csv
            if 데이터:
                with open("output/결과.csv", "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=데이터[0].keys())
                    writer.writeheader()
                    writer.writerows(데이터)

        logger.info(f"  저장: {len(데이터)}건 → output/")

    # ─── 실행 ───────────────────────────────
    async def 실행(self, 소스들: list[dict]) -> 파이프라인결과:
        """전체 파이프라인 실행"""
        시작 = datetime.now()
        logger.info("=" * 50)
        logger.info(" ETL 파이프라인 시작")
        logger.info("=" * 50)

        # Extract
        원본 = await self.수집(소스들)

        # Transform
        변환 = self.변환(원본)

        # Load
        await self.저장(변환)

        소요 = (datetime.now() - 시작).total_seconds()
        결과 = 파이프라인결과(
            수집건수=len(원본), 변환건수=len(변환),
            저장건수=len(변환), 실패건수=len(원본)-len(변환),
            소요시간=소요,
        )

        logger.info(f"  완료: {결과.소요시간:.1f}초")
        return 결과

# 사용
async def main():
    pipeline = 데이터파이프라인()
    await pipeline.실행([
        {"name": "유저 API", "type": "api", "url": "https://api.example.com/users"},
        {"name": "매출 CSV", "type": "csv", "path": "data/sales.csv"},
    ])

if __name__ == "__main__":
    asyncio.run(main())
```

## 자동 스케줄링

```python
# scheduler.py (매일 새벽 3시 실행)
import schedule
import time

def 파이프라인실행():
    import asyncio
    asyncio.run(main())

schedule.every().day.at("03:00").do(파이프라인실행)

while True:
    schedule.run_pending()
    time.sleep(60)
```

이 구조로 데이터 수집 자동화를 구축할 수 있습니다.'''),
]

# ═══════════════════════════════════════════════════════════════
# 10. Kubernetes 배포
# ═══════════════════════════════════════════════════════════════

K8S = [
    make("Kubernetes로 앱을 배포하는 전체 과정 알려줘",
'''Kubernetes 배포 전체 가이드입니다.

## 핵심 리소스

```yaml
# 1. Deployment (앱 배포)
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hwarang-web
  labels:
    app: hwarang-web
spec:
  replicas: 3                    # 3개 Pod
  selector:
    matchLabels:
      app: hwarang-web
  template:
    metadata:
      labels:
        app: hwarang-web
    spec:
      containers:
        - name: web
          image: ghcr.io/persismore/hwarang-web:latest
          ports:
            - containerPort: 3000
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: hwarang-secrets
                  key: database-url
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /api/health
              port: 3000
            initialDelaySeconds: 15
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /api/health
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 5
---
# 2. Service (내부 통신)
apiVersion: v1
kind: Service
metadata:
  name: hwarang-web
spec:
  selector:
    app: hwarang-web
  ports:
    - port: 80
      targetPort: 3000
---
# 3. Ingress (외부 접근 + SSL)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hwarang-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
spec:
  tls:
    - hosts: ["hwarang.ai"]
      secretName: hwarang-tls
  rules:
    - host: hwarang.ai
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: hwarang-web
                port:
                  number: 80
---
# 4. HPA (오토스케일링)
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: hwarang-web-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: hwarang-web
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

## 배포 명령어

```bash
# 네임스페이스 생성
kubectl create namespace hwarang

# Secret 생성
kubectl create secret generic hwarang-secrets \\
  --from-literal=database-url="postgresql://..." \\
  -n hwarang

# 배포
kubectl apply -f k8s/ -n hwarang

# 상태 확인
kubectl get pods -n hwarang
kubectl get services -n hwarang
kubectl get ingress -n hwarang

# 로그
kubectl logs -f deployment/hwarang-web -n hwarang

# 스케일링
kubectl scale deployment hwarang-web --replicas=5 -n hwarang

# 롤백
kubectl rollout undo deployment/hwarang-web -n hwarang
```

Pod 3개 → 하나 죽어도 서비스 유지, CPU 70% 넘으면 자동 확장(최대 10개)됩니다.'''),
]

def build_large_project_data(output_path):
    all_data = SAAS + SOCIAL + MOBILE + GRAPHQL + DASHBOARD + DATA_PIPELINE + K8S

    logger.info(f"  대형 프로젝트: {len(all_data)}건")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"\n총 {len(all_data)}건 → {output_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/large_projects.jsonl")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" 화랑 AI 대형 프로젝트 학습 데이터")
    logger.info("=" * 60)
    build_large_project_data(args.output)
