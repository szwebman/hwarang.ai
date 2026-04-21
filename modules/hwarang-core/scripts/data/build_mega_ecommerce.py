"""화랑 AI 이커머스 추가 학습 데이터

이커머스 핵심 기능 6건:
  - 배송 추적 시스템
  - 상품 재고 관리 시스템
  - 장바구니 + 주문 내역 관리
  - 검색 자동완성 + 최근 검색어
  - 포인트/적립금 시스템
  - 회원 등급 + 혜택 시스템
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
프로젝트 요청 시 폴더 구조와 각 파일의 전체 코드를 작성합니다.
실무에서 바로 사용할 수 있는 프로덕션 수준의 코드를 생성합니다.
설명은 한국어로, 코드는 완전한 형태로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 1. 배송 추적 시스템 ═══
    m("Next.js로 배송 추적 시스템 만들어줘 전체 코드로",
'''배송 추적 시스템을 만들어 드릴게요. 주문 상태 Enum, 트래킹 타임라인, 상태 업데이트 API를 포함합니다.

## 폴더 구조

```
delivery-tracker/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       └── orders/
│           ├── route.ts
│           └── [id]/
│               ├── route.ts
│               └── tracking/route.ts
├── components/
│   ├── order-list.tsx
│   ├── tracking-timeline.tsx
│   ├── status-badge.tsx
│   └── update-status-modal.tsx
├── lib/
│   ├── db.ts
│   └── types.ts
├── prisma/
│   └── schema.prisma
└── package.json
```

## prisma/schema.prisma

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = "file:./dev.db"
}

enum OrderStatus {
  PENDING
  CONFIRMED
  SHIPPED
  DELIVERED
}

model Order {
  id            String          @id @default(cuid())
  orderNumber   String          @unique
  customerName  String
  customerEmail String
  address       String
  status        OrderStatus     @default(PENDING)
  totalAmount   Int
  trackingEvents TrackingEvent[]
  createdAt     DateTime        @default(now())
  updatedAt     DateTime        @updatedAt
}

model TrackingEvent {
  id          String      @id @default(cuid())
  orderId     String
  order       Order       @relation(fields: [orderId], references: [id], onDelete: Cascade)
  status      OrderStatus
  location    String?
  description String
  createdAt   DateTime    @default(now())
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/types.ts

```typescript
export const ORDER_STATUS = {
  PENDING: { label: "주문 접수", color: "bg-gray-500" },
  CONFIRMED: { label: "주문 확인", color: "bg-blue-500" },
  SHIPPED: { label: "배송 중", color: "bg-orange-500" },
  DELIVERED: { label: "배송 완료", color: "bg-green-500" },
} as const;

export type OrderStatusKey = keyof typeof ORDER_STATUS;

export const STATUS_FLOW: OrderStatusKey[] = ["PENDING", "CONFIRMED", "SHIPPED", "DELIVERED"];

export function getNextStatus(current: OrderStatusKey): OrderStatusKey | null {
  const idx = STATUS_FLOW.indexOf(current);
  return idx < STATUS_FLOW.length - 1 ? STATUS_FLOW[idx + 1] : null;
}
```

## app/api/orders/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

// 주문 목록 조회
export async function GET() {
  const orders = await prisma.order.findMany({
    include: { trackingEvents: { orderBy: { createdAt: "desc" } } },
    orderBy: { createdAt: "desc" },
  });
  return NextResponse.json(orders);
}

// 주문 생성
export async function POST(req: NextRequest) {
  const body = await req.json();
  const order = await prisma.order.create({
    data: {
      orderNumber: `ORD-${Date.now()}`,
      customerName: body.customerName,
      customerEmail: body.customerEmail,
      address: body.address,
      totalAmount: body.totalAmount,
      trackingEvents: {
        create: { status: "PENDING", description: "주문이 접수되었습니다." },
      },
    },
    include: { trackingEvents: true },
  });
  return NextResponse.json(order, { status: 201 });
}
```

## app/api/orders/[id]/tracking/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getNextStatus } from "@/lib/types";
import { OrderStatus } from "@prisma/client";

// 배송 상태 업데이트 + 트래킹 이벤트 추가
export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const { id } = params;
  const body = await req.json();

  const order = await prisma.order.findUnique({ where: { id } });
  if (!order) return NextResponse.json({ error: "주문을 찾을 수 없습니다." }, { status: 404 });

  const nextStatus = getNextStatus(order.status);
  if (!nextStatus) return NextResponse.json({ error: "이미 배송 완료된 주문입니다." }, { status: 400 });

  const updated = await prisma.order.update({
    where: { id },
    data: {
      status: nextStatus as OrderStatus,
      trackingEvents: {
        create: {
          status: nextStatus as OrderStatus,
          location: body.location || null,
          description: body.description,
        },
      },
    },
    include: { trackingEvents: { orderBy: { createdAt: "desc" } } },
  });

  return NextResponse.json(updated);
}
```

## components/status-badge.tsx

```tsx
"use client";

import { ORDER_STATUS, OrderStatusKey } from "@/lib/types";

export default function StatusBadge({ status }: { status: OrderStatusKey }) {
  const info = ORDER_STATUS[status];
  return (
    <span className={`${info.color} text-white text-xs font-semibold px-3 py-1 rounded-full`}>
      {info.label}
    </span>
  );
}
```

## components/tracking-timeline.tsx

```tsx
"use client";

import { ORDER_STATUS, OrderStatusKey } from "@/lib/types";

interface TrackingEvent {
  id: string;
  status: OrderStatusKey;
  location: string | null;
  description: string;
  createdAt: string;
}

export default function TrackingTimeline({ events }: { events: TrackingEvent[] }) {
  return (
    <div className="relative pl-8 space-y-6">
      <div className="absolute left-3 top-2 bottom-2 w-0.5 bg-gray-300" />
      {events.map((ev, i) => {
        const info = ORDER_STATUS[ev.status];
        return (
          <div key={ev.id} className="relative">
            <div className={`absolute -left-5 w-4 h-4 rounded-full border-2 border-white ${info.color}`} />
            <div className="bg-white rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-sm">{info.label}</span>
                <span className="text-xs text-gray-400">
                  {new Date(ev.createdAt).toLocaleString("ko-KR")}
                </span>
              </div>
              <p className="text-sm text-gray-600">{ev.description}</p>
              {ev.location && (
                <p className="text-xs text-gray-400 mt-1">📍 {ev.location}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

## components/update-status-modal.tsx

```tsx
"use client";

import { useState } from "react";
import { getNextStatus, ORDER_STATUS, OrderStatusKey } from "@/lib/types";

interface Props {
  orderId: string;
  currentStatus: OrderStatusKey;
  onUpdated: () => void;
}

export default function UpdateStatusModal({ orderId, currentStatus, onUpdated }: Props) {
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState("");
  const [loading, setLoading] = useState(false);
  const nextStatus = getNextStatus(currentStatus);

  if (!nextStatus) return null;

  const handleSubmit = async () => {
    setLoading(true);
    await fetch(`/api/orders/${orderId}/tracking`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description, location }),
    });
    setDescription("");
    setLocation("");
    setLoading(false);
    onUpdated();
  };

  return (
    <div className="bg-gray-50 rounded-lg p-4 mt-4 space-y-3">
      <p className="text-sm font-medium">
        다음 단계: <span className="text-blue-600">{ORDER_STATUS[nextStatus].label}</span>
      </p>
      <input
        className="w-full border rounded px-3 py-2 text-sm"
        placeholder="위치 (선택)"
        value={location}
        onChange={(e) => setLocation(e.target.value)}
      />
      <input
        className="w-full border rounded px-3 py-2 text-sm"
        placeholder="설명을 입력하세요"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <button
        onClick={handleSubmit}
        disabled={!description || loading}
        className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "처리 중..." : "상태 업데이트"}
      </button>
    </div>
  );
}
```

## app/page.tsx

```tsx
"use client";

import { useEffect, useState } from "react";
import StatusBadge from "@/components/status-badge";
import TrackingTimeline from "@/components/tracking-timeline";
import UpdateStatusModal from "@/components/update-status-modal";

export default function Home() {
  const [orders, setOrders] = useState<any[]>([]);
  const [selected, setSelected] = useState<string | null>(null);

  const fetchOrders = async () => {
    const res = await fetch("/api/orders");
    setOrders(await res.json());
  };

  useEffect(() => { fetchOrders(); }, []);

  const selectedOrder = orders.find((o) => o.id === selected);

  return (
    <main className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">배송 추적 시스템</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-3">
          <h2 className="font-semibold text-lg">주문 목록</h2>
          {orders.map((order) => (
            <div
              key={order.id}
              onClick={() => setSelected(order.id)}
              className={`p-4 rounded-lg border cursor-pointer transition ${
                selected === order.id ? "border-blue-500 bg-blue-50" : "hover:bg-gray-50"
              }`}
            >
              <div className="flex justify-between items-center">
                <span className="font-mono text-sm">{order.orderNumber}</span>
                <StatusBadge status={order.status} />
              </div>
              <p className="text-sm text-gray-600 mt-1">{order.customerName}</p>
            </div>
          ))}
        </div>
        <div>
          {selectedOrder ? (
            <>
              <h2 className="font-semibold text-lg mb-4">배송 현황</h2>
              <TrackingTimeline events={selectedOrder.trackingEvents} />
              <UpdateStatusModal
                orderId={selectedOrder.id}
                currentStatus={selectedOrder.status}
                onUpdated={fetchOrders}
              />
            </>
          ) : (
            <p className="text-gray-400 text-center mt-20">주문을 선택하세요</p>
          )}
        </div>
      </div>
    </main>
  );
}
```

Prisma 마이그레이션 후 바로 사용 가능합니다. `npx prisma migrate dev --name init`으로 DB를 생성하세요.'''),

    # ═══ 2. 상품 재고 관리 시스템 ═══
    m("Next.js로 상품 재고 관리 시스템 만들어줘 전체 코드로",
'''상품 재고 관리 시스템을 만들어 드릴게요. 입출고 이력, 재고 부족 알림, 대시보드를 포함합니다.

## 폴더 구조

```
inventory-system/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       ├── products/
│       │   ├── route.ts
│       │   └── [id]/route.ts
│       └── stock/
│           └── route.ts
├── components/
│   ├── product-table.tsx
│   ├── stock-modal.tsx
│   ├── low-stock-alert.tsx
│   ├── stock-history.tsx
│   └── dashboard-stats.tsx
├── lib/
│   ├── db.ts
│   └── types.ts
├── prisma/
│   └── schema.prisma
└── package.json
```

## prisma/schema.prisma

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = "file:./dev.db"
}

model Product {
  id          String        @id @default(cuid())
  name        String
  sku         String        @unique
  category    String
  price       Int
  stock       Int           @default(0)
  minStock    Int           @default(10)
  stockHistory StockHistory[]
  createdAt   DateTime      @default(now())
  updatedAt   DateTime      @updatedAt
}

model StockHistory {
  id        String   @id @default(cuid())
  productId String
  product   Product  @relation(fields: [productId], references: [id], onDelete: Cascade)
  type      String   // "IN" or "OUT"
  quantity  Int
  reason    String
  createdAt DateTime @default(now())
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/types.ts

```typescript
export interface StockUpdate {
  productId: string;
  type: "IN" | "OUT";
  quantity: number;
  reason: string;
}

export interface DashboardStats {
  totalProducts: number;
  totalStockValue: number;
  lowStockCount: number;
  recentActivity: number;
}
```

## app/api/products/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(req: NextRequest) {
  const search = req.nextUrl.searchParams.get("search") || "";
  const products = await prisma.product.findMany({
    where: search ? { name: { contains: search } } : undefined,
    include: { stockHistory: { orderBy: { createdAt: "desc" }, take: 5 } },
    orderBy: { updatedAt: "desc" },
  });
  return NextResponse.json(products);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const product = await prisma.product.create({
    data: {
      name: body.name,
      sku: body.sku,
      category: body.category,
      price: body.price,
      stock: body.stock || 0,
      minStock: body.minStock || 10,
    },
  });
  return NextResponse.json(product, { status: 201 });
}
```

## app/api/products/[id]/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function PUT(req: NextRequest, { params }: { params: { id: string } }) {
  const body = await req.json();
  const product = await prisma.product.update({
    where: { id: params.id },
    data: { name: body.name, category: body.category, price: body.price, minStock: body.minStock },
  });
  return NextResponse.json(product);
}

export async function DELETE(_: NextRequest, { params }: { params: { id: string } }) {
  await prisma.product.delete({ where: { id: params.id } });
  return NextResponse.json({ ok: true });
}
```

## app/api/stock/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

// 입출고 처리
export async function POST(req: NextRequest) {
  const { productId, type, quantity, reason } = await req.json();

  const product = await prisma.product.findUnique({ where: { id: productId } });
  if (!product) return NextResponse.json({ error: "상품 없음" }, { status: 404 });

  if (type === "OUT" && product.stock < quantity) {
    return NextResponse.json({ error: "재고 부족" }, { status: 400 });
  }

  const newStock = type === "IN" ? product.stock + quantity : product.stock - quantity;

  const [updated] = await prisma.$transaction([
    prisma.product.update({ where: { id: productId }, data: { stock: newStock } }),
    prisma.stockHistory.create({
      data: { productId, type, quantity, reason },
    }),
  ]);

  return NextResponse.json(updated);
}
```

## components/dashboard-stats.tsx

```tsx
"use client";

interface Stats {
  totalProducts: number;
  totalStockValue: number;
  lowStockCount: number;
}

export default function DashboardStats({ stats }: { stats: Stats }) {
  const cards = [
    { label: "전체 상품", value: stats.totalProducts, unit: "개", bg: "bg-blue-50 text-blue-700" },
    { label: "총 재고 가치", value: stats.totalStockValue.toLocaleString(), unit: "원", bg: "bg-green-50 text-green-700" },
    { label: "재고 부족", value: stats.lowStockCount, unit: "건", bg: "bg-red-50 text-red-700" },
  ];

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      {cards.map((c) => (
        <div key={c.label} className={`${c.bg} rounded-xl p-4`}>
          <p className="text-sm opacity-70">{c.label}</p>
          <p className="text-2xl font-bold">{c.value}<span className="text-sm ml-1">{c.unit}</span></p>
        </div>
      ))}
    </div>
  );
}
```

## components/low-stock-alert.tsx

```tsx
"use client";

interface Product { id: string; name: string; sku: string; stock: number; minStock: number; }

export default function LowStockAlert({ products }: { products: Product[] }) {
  const lowStock = products.filter((p) => p.stock <= p.minStock);
  if (lowStock.length === 0) return null;

  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
      <h3 className="text-red-700 font-semibold mb-2">⚠️ 재고 부족 알림 ({lowStock.length}건)</h3>
      <div className="space-y-1">
        {lowStock.map((p) => (
          <div key={p.id} className="flex justify-between text-sm">
            <span className="text-red-600">{p.name} ({p.sku})</span>
            <span className="font-mono text-red-700">{p.stock} / {p.minStock}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

## components/stock-modal.tsx

```tsx
"use client";

import { useState } from "react";

interface Props {
  productId: string;
  productName: string;
  onComplete: () => void;
  onClose: () => void;
}

export default function StockModal({ productId, productName, onComplete, onClose }: Props) {
  const [type, setType] = useState<"IN" | "OUT">("IN");
  const [quantity, setQuantity] = useState(1);
  const [reason, setReason] = useState("");

  const handleSubmit = async () => {
    await fetch("/api/stock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ productId, type, quantity, reason }),
    });
    onComplete();
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-96 space-y-4">
        <h3 className="font-bold text-lg">{productName} - 입출고</h3>
        <div className="flex gap-2">
          {(["IN", "OUT"] as const).map((t) => (
            <button key={t} onClick={() => setType(t)}
              className={`flex-1 py-2 rounded ${type === t ? (t === "IN" ? "bg-green-600 text-white" : "bg-red-600 text-white") : "bg-gray-100"}`}>
              {t === "IN" ? "입고" : "출고"}
            </button>
          ))}
        </div>
        <input type="number" min={1} value={quantity} onChange={(e) => setQuantity(+e.target.value)}
          className="w-full border rounded px-3 py-2" placeholder="수량" />
        <input value={reason} onChange={(e) => setReason(e.target.value)}
          className="w-full border rounded px-3 py-2" placeholder="사유" />
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-4 py-2 text-gray-500">취소</button>
          <button onClick={handleSubmit} disabled={!reason}
            className="px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-50">확인</button>
        </div>
      </div>
    </div>
  );
}
```

## app/page.tsx

```tsx
"use client";

import { useEffect, useState } from "react";
import DashboardStats from "@/components/dashboard-stats";
import LowStockAlert from "@/components/low-stock-alert";
import StockModal from "@/components/stock-modal";

export default function Home() {
  const [products, setProducts] = useState<any[]>([]);
  const [modal, setModal] = useState<{ id: string; name: string } | null>(null);

  const load = async () => {
    const res = await fetch("/api/products");
    setProducts(await res.json());
  };

  useEffect(() => { load(); }, []);

  const stats = {
    totalProducts: products.length,
    totalStockValue: products.reduce((s, p) => s + p.price * p.stock, 0),
    lowStockCount: products.filter((p) => p.stock <= p.minStock).length,
  };

  return (
    <main className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">재고 관리 시스템</h1>
      <DashboardStats stats={stats} />
      <LowStockAlert products={products} />
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b text-left">
            <th className="py-2">상품명</th><th>SKU</th><th>카테고리</th>
            <th className="text-right">단가</th><th className="text-right">재고</th><th></th>
          </tr>
        </thead>
        <tbody>
          {products.map((p) => (
            <tr key={p.id} className="border-b hover:bg-gray-50">
              <td className="py-2 font-medium">{p.name}</td>
              <td className="font-mono text-xs">{p.sku}</td>
              <td>{p.category}</td>
              <td className="text-right">{p.price.toLocaleString()}원</td>
              <td className={`text-right font-mono ${p.stock <= p.minStock ? "text-red-600 font-bold" : ""}`}>{p.stock}</td>
              <td className="text-right">
                <button onClick={() => setModal({ id: p.id, name: p.name })}
                  className="text-blue-600 hover:underline text-xs">입출고</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {modal && <StockModal productId={modal.id} productName={modal.name} onComplete={() => { setModal(null); load(); }} onClose={() => setModal(null)} />}
    </main>
  );
}
```

`npx prisma migrate dev --name init`으로 DB 초기화 후 사용하세요.'''),

    # ═══ 3. 장바구니 + 주문 내역 관리 ═══
    m("Next.js로 장바구니 + 주문 내역 관리 만들어줘 전체 코드로",
'''장바구니와 주문 내역 관리 시스템을 만들어 드릴게요. Zustand 기반 장바구니, 주문 API, 페이지네이션을 포함합니다.

## 폴더 구조

```
cart-orders/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── cart/page.tsx
│   ├── orders/page.tsx
│   ├── orders/[id]/page.tsx
│   └── api/
│       └── orders/
│           ├── route.ts
│           └── [id]/route.ts
├── components/
│   ├── cart-item.tsx
│   ├── cart-summary.tsx
│   ├── order-card.tsx
│   ├── pagination.tsx
│   └── navbar.tsx
├── store/
│   └── cart.ts
├── lib/
│   ├── db.ts
│   └── types.ts
├── prisma/
│   └── schema.prisma
└── package.json
```

## prisma/schema.prisma

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = "file:./dev.db"
}

model Order {
  id         String      @id @default(cuid())
  orderNumber String     @unique
  status     String      @default("PENDING")
  totalAmount Int
  items      OrderItem[]
  createdAt  DateTime    @default(now())
}

model OrderItem {
  id        String @id @default(cuid())
  orderId   String
  order     Order  @relation(fields: [orderId], references: [id], onDelete: Cascade)
  name      String
  price     Int
  quantity  Int
  image     String?
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## store/cart.ts

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface CartItem {
  id: string;
  name: string;
  price: number;
  quantity: number;
  image?: string;
}

interface CartStore {
  items: CartItem[];
  addItem: (item: Omit<CartItem, "quantity">) => void;
  removeItem: (id: string) => void;
  updateQuantity: (id: string, quantity: number) => void;
  clearCart: () => void;
  totalAmount: () => number;
  totalCount: () => number;
}

export const useCartStore = create<CartStore>()(
  persist(
    (set, get) => ({
      items: [],
      addItem: (item) => {
        const existing = get().items.find((i) => i.id === item.id);
        if (existing) {
          set({ items: get().items.map((i) => i.id === item.id ? { ...i, quantity: i.quantity + 1 } : i) });
        } else {
          set({ items: [...get().items, { ...item, quantity: 1 }] });
        }
      },
      removeItem: (id) => set({ items: get().items.filter((i) => i.id !== id) }),
      updateQuantity: (id, quantity) => {
        if (quantity <= 0) { get().removeItem(id); return; }
        set({ items: get().items.map((i) => i.id === id ? { ...i, quantity } : i) });
      },
      clearCart: () => set({ items: [] }),
      totalAmount: () => get().items.reduce((s, i) => s + i.price * i.quantity, 0),
      totalCount: () => get().items.reduce((s, i) => s + i.quantity, 0),
    }),
    { name: "cart-storage" }
  )
);
```

## app/api/orders/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(req: NextRequest) {
  const page = parseInt(req.nextUrl.searchParams.get("page") || "1");
  const limit = 10;
  const skip = (page - 1) * limit;

  const [orders, total] = await Promise.all([
    prisma.order.findMany({
      include: { items: true },
      orderBy: { createdAt: "desc" },
      skip,
      take: limit,
    }),
    prisma.order.count(),
  ]);

  return NextResponse.json({ orders, total, totalPages: Math.ceil(total / limit), page });
}

export async function POST(req: NextRequest) {
  const { items } = await req.json();
  const totalAmount = items.reduce((s: number, i: any) => s + i.price * i.quantity, 0);

  const order = await prisma.order.create({
    data: {
      orderNumber: `ORD-${Date.now()}`,
      totalAmount,
      items: { create: items.map((i: any) => ({ name: i.name, price: i.price, quantity: i.quantity, image: i.image })) },
    },
    include: { items: true },
  });

  return NextResponse.json(order, { status: 201 });
}
```

## app/api/orders/[id]/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(_: NextRequest, { params }: { params: { id: string } }) {
  const order = await prisma.order.findUnique({
    where: { id: params.id },
    include: { items: true },
  });
  if (!order) return NextResponse.json({ error: "주문 없음" }, { status: 404 });
  return NextResponse.json(order);
}
```

## components/cart-item.tsx

```tsx
"use client";

import { useCartStore, CartItem } from "@/store/cart";

export default function CartItemRow({ item }: { item: CartItem }) {
  const { updateQuantity, removeItem } = useCartStore();

  return (
    <div className="flex items-center gap-4 py-4 border-b">
      <div className="w-16 h-16 bg-gray-100 rounded flex items-center justify-center text-2xl">
        📦
      </div>
      <div className="flex-1">
        <p className="font-medium">{item.name}</p>
        <p className="text-sm text-gray-500">{item.price.toLocaleString()}원</p>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={() => updateQuantity(item.id, item.quantity - 1)}
          className="w-8 h-8 rounded border text-center">-</button>
        <span className="w-8 text-center font-mono">{item.quantity}</span>
        <button onClick={() => updateQuantity(item.id, item.quantity + 1)}
          className="w-8 h-8 rounded border text-center">+</button>
      </div>
      <p className="w-24 text-right font-semibold">{(item.price * item.quantity).toLocaleString()}원</p>
      <button onClick={() => removeItem(item.id)} className="text-red-500 text-sm">삭제</button>
    </div>
  );
}
```

## components/cart-summary.tsx

```tsx
"use client";

import { useCartStore } from "@/store/cart";
import { useRouter } from "next/navigation";

export default function CartSummary() {
  const { items, totalAmount, clearCart } = useCartStore();
  const router = useRouter();

  const handleOrder = async () => {
    if (items.length === 0) return;
    await fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    clearCart();
    router.push("/orders");
  };

  return (
    <div className="bg-gray-50 rounded-xl p-6 sticky top-6">
      <h2 className="font-bold text-lg mb-4">주문 요약</h2>
      <div className="space-y-2 text-sm">
        <div className="flex justify-between"><span>상품 합계</span><span>{totalAmount().toLocaleString()}원</span></div>
        <div className="flex justify-between"><span>배송비</span><span>{totalAmount() >= 50000 ? "무료" : "3,000원"}</span></div>
        <hr />
        <div className="flex justify-between font-bold text-lg">
          <span>총 결제금액</span>
          <span>{(totalAmount() + (totalAmount() >= 50000 ? 0 : 3000)).toLocaleString()}원</span>
        </div>
      </div>
      <button onClick={handleOrder} disabled={items.length === 0}
        className="w-full mt-4 bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 disabled:opacity-50">
        주문하기
      </button>
    </div>
  );
}
```

## components/pagination.tsx

```tsx
"use client";

interface Props {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ page, totalPages, onPageChange }: Props) {
  return (
    <div className="flex justify-center gap-2 mt-6">
      <button onClick={() => onPageChange(page - 1)} disabled={page <= 1}
        className="px-3 py-1 border rounded disabled:opacity-30">이전</button>
      {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
        <button key={p} onClick={() => onPageChange(p)}
          className={`px-3 py-1 rounded ${p === page ? "bg-blue-600 text-white" : "border hover:bg-gray-50"}`}>
          {p}
        </button>
      ))}
      <button onClick={() => onPageChange(page + 1)} disabled={page >= totalPages}
        className="px-3 py-1 border rounded disabled:opacity-30">다음</button>
    </div>
  );
}
```

## app/orders/page.tsx

```tsx
"use client";

import { useEffect, useState } from "react";
import Pagination from "@/components/pagination";
import Link from "next/link";

export default function OrdersPage() {
  const [data, setData] = useState<any>({ orders: [], total: 0, totalPages: 1, page: 1 });

  const load = async (page: number) => {
    const res = await fetch(`/api/orders?page=${page}`);
    setData(await res.json());
  };

  useEffect(() => { load(1); }, []);

  return (
    <main className="max-w-3xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">주문 내역</h1>
      <div className="space-y-4">
        {data.orders.map((order: any) => (
          <Link key={order.id} href={`/orders/${order.id}`}
            className="block p-4 border rounded-lg hover:bg-gray-50 transition">
            <div className="flex justify-between items-center">
              <div>
                <span className="font-mono text-sm">{order.orderNumber}</span>
                <p className="text-xs text-gray-400">{new Date(order.createdAt).toLocaleDateString("ko-KR")}</p>
              </div>
              <div className="text-right">
                <p className="font-bold">{order.totalAmount.toLocaleString()}원</p>
                <p className="text-xs text-gray-500">{order.items.length}개 상품</p>
              </div>
            </div>
          </Link>
        ))}
      </div>
      <Pagination page={data.page} totalPages={data.totalPages} onPageChange={load} />
    </main>
  );
}
```

Zustand `persist` 미들웨어로 새로고침해도 장바구니가 유지됩니다. `npm i zustand`를 설치하세요.'''),

    # ═══ 4. 검색 자동완성 + 최근 검색어 ═══
    m("Next.js로 이커머스 검색 자동완성 + 최근 검색어 만들어줘 전체 코드로",
'''이커머스 검색 자동완성과 최근 검색어 시스템을 만들어 드릴게요. Debounce 처리, 자동완성 드롭다운, localStorage 기반 최근 검색어를 포함합니다.

## 폴더 구조

```
search-autocomplete/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── search/page.tsx
│   └── api/
│       └── search/
│           ├── route.ts
│           └── suggestions/route.ts
├── components/
│   ├── search-bar.tsx
│   ├── autocomplete-dropdown.tsx
│   ├── recent-searches.tsx
│   ├── search-results.tsx
│   └── product-card.tsx
├── hooks/
│   └── use-debounce.ts
├── lib/
│   ├── db.ts
│   └── search-history.ts
├── prisma/
│   └── schema.prisma
└── package.json
```

## prisma/schema.prisma

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = "file:./dev.db"
}

model Product {
  id       String @id @default(cuid())
  name     String
  category String
  price    Int
  image    String?
  tags     String  @default("")
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/search-history.ts

```typescript
const STORAGE_KEY = "recent-searches";
const MAX_ITEMS = 10;

export function getRecentSearches(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

export function addRecentSearch(query: string): string[] {
  const searches = getRecentSearches().filter((s) => s !== query);
  const updated = [query, ...searches].slice(0, MAX_ITEMS);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  return updated;
}

export function removeRecentSearch(query: string): string[] {
  const updated = getRecentSearches().filter((s) => s !== query);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  return updated;
}

export function clearRecentSearches(): void {
  localStorage.removeItem(STORAGE_KEY);
}
```

## hooks/use-debounce.ts

```typescript
import { useState, useEffect } from "react";

export function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
```

## app/api/search/suggestions/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

// 자동완성 추천어 (상품명 기반)
export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q") || "";
  if (q.length < 2) return NextResponse.json([]);

  const products = await prisma.product.findMany({
    where: { name: { contains: q } },
    select: { name: true, category: true },
    take: 8,
  });

  const suggestions = products.map((p) => ({
    text: p.name,
    category: p.category,
  }));

  return NextResponse.json(suggestions);
}
```

## app/api/search/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q") || "";
  const category = req.nextUrl.searchParams.get("category") || "";
  const sort = req.nextUrl.searchParams.get("sort") || "relevance";
  const page = parseInt(req.nextUrl.searchParams.get("page") || "1");
  const limit = 12;

  const where: any = {};
  if (q) where.OR = [{ name: { contains: q } }, { tags: { contains: q } }];
  if (category) where.category = category;

  const orderBy = sort === "price_asc" ? { price: "asc" as const }
    : sort === "price_desc" ? { price: "desc" as const }
    : { id: "desc" as const };

  const [products, total] = await Promise.all([
    prisma.product.findMany({ where, orderBy, skip: (page - 1) * limit, take: limit }),
    prisma.product.count({ where }),
  ]);

  return NextResponse.json({ products, total, totalPages: Math.ceil(total / limit), page });
}
```

## components/autocomplete-dropdown.tsx

```tsx
"use client";

interface Suggestion { text: string; category: string; }

interface Props {
  suggestions: Suggestion[];
  visible: boolean;
  onSelect: (text: string) => void;
}

export default function AutocompleteDropdown({ suggestions, visible, onSelect }: Props) {
  if (!visible || suggestions.length === 0) return null;

  return (
    <div className="absolute top-full left-0 right-0 bg-white border rounded-b-lg shadow-lg z-50 max-h-72 overflow-y-auto">
      {suggestions.map((s, i) => (
        <button key={i} onClick={() => onSelect(s.text)}
          className="w-full text-left px-4 py-2 hover:bg-blue-50 flex justify-between items-center">
          <span className="text-sm">{s.text}</span>
          <span className="text-xs text-gray-400">{s.category}</span>
        </button>
      ))}
    </div>
  );
}
```

## components/recent-searches.tsx

```tsx
"use client";

import { getRecentSearches, removeRecentSearch, clearRecentSearches } from "@/lib/search-history";
import { useState, useEffect } from "react";

interface Props { onSelect: (query: string) => void; }

export default function RecentSearches({ onSelect }: Props) {
  const [searches, setSearches] = useState<string[]>([]);

  useEffect(() => { setSearches(getRecentSearches()); }, []);

  if (searches.length === 0) return null;

  return (
    <div className="mt-4">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-sm font-semibold text-gray-500">최근 검색어</h3>
        <button onClick={() => { clearRecentSearches(); setSearches([]); }}
          className="text-xs text-gray-400 hover:text-gray-600">전체 삭제</button>
      </div>
      <div className="flex flex-wrap gap-2">
        {searches.map((s) => (
          <div key={s} className="flex items-center bg-gray-100 rounded-full px-3 py-1 text-sm group">
            <button onClick={() => onSelect(s)} className="hover:text-blue-600">{s}</button>
            <button onClick={() => setSearches(removeRecentSearch(s))}
              className="ml-1 text-gray-400 hover:text-red-500 hidden group-hover:inline">×</button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

## components/search-bar.tsx

```tsx
"use client";

import { useState, useRef, useEffect } from "react";
import { useDebounce } from "@/hooks/use-debounce";
import { addRecentSearch } from "@/lib/search-history";
import AutocompleteDropdown from "./autocomplete-dropdown";
import { useRouter } from "next/navigation";

export default function SearchBar() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const debouncedQuery = useDebounce(query, 300);
  const router = useRouter();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (debouncedQuery.length < 2) { setSuggestions([]); return; }
    fetch(`/api/search/suggestions?q=${encodeURIComponent(debouncedQuery)}`)
      .then((r) => r.json())
      .then(setSuggestions);
  }, [debouncedQuery]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setShowDropdown(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSearch = (text: string) => {
    const q = text.trim();
    if (!q) return;
    addRecentSearch(q);
    setShowDropdown(false);
    router.push(`/search?q=${encodeURIComponent(q)}`);
  };

  return (
    <div ref={ref} className="relative w-full max-w-xl mx-auto">
      <div className="flex border-2 border-gray-300 rounded-lg focus-within:border-blue-500 transition">
        <input
          value={query}
          onChange={(e) => { setQuery(e.target.value); setShowDropdown(true); }}
          onFocus={() => setShowDropdown(true)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch(query)}
          placeholder="상품을 검색하세요..."
          className="flex-1 px-4 py-3 outline-none rounded-l-lg"
        />
        <button onClick={() => handleSearch(query)}
          className="px-6 bg-blue-600 text-white rounded-r-lg hover:bg-blue-700">검색</button>
      </div>
      <AutocompleteDropdown suggestions={suggestions} visible={showDropdown} onSelect={handleSearch} />
    </div>
  );
}
```

## components/product-card.tsx

```tsx
"use client";

interface Props { product: { id: string; name: string; price: number; category: string; image?: string } }

export default function ProductCard({ product }: Props) {
  return (
    <div className="border rounded-lg overflow-hidden hover:shadow-lg transition">
      <div className="h-40 bg-gray-100 flex items-center justify-center text-4xl">📦</div>
      <div className="p-3">
        <p className="text-xs text-gray-400">{product.category}</p>
        <p className="font-medium text-sm mt-1 line-clamp-2">{product.name}</p>
        <p className="font-bold mt-2">{product.price.toLocaleString()}원</p>
      </div>
    </div>
  );
}
```

## app/search/page.tsx

```tsx
"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import SearchBar from "@/components/search-bar";
import ProductCard from "@/components/product-card";

export default function SearchPage() {
  const searchParams = useSearchParams();
  const q = searchParams.get("q") || "";
  const [data, setData] = useState<any>({ products: [], total: 0 });
  const [sort, setSort] = useState("relevance");

  useEffect(() => {
    if (!q) return;
    fetch(`/api/search?q=${encodeURIComponent(q)}&sort=${sort}`).then((r) => r.json()).then(setData);
  }, [q, sort]);

  return (
    <main className="max-w-5xl mx-auto p-6">
      <SearchBar />
      <div className="mt-6 flex justify-between items-center">
        <p className="text-sm text-gray-500">&quot;{q}&quot; 검색 결과 {data.total}건</p>
        <select value={sort} onChange={(e) => setSort(e.target.value)}
          className="border rounded px-3 py-1 text-sm">
          <option value="relevance">관련순</option>
          <option value="price_asc">낮은가격순</option>
          <option value="price_desc">높은가격순</option>
        </select>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
        {data.products.map((p: any) => <ProductCard key={p.id} product={p} />)}
      </div>
    </main>
  );
}
```

300ms debounce로 타이핑 중 불필요한 API 호출을 방지합니다. 외부 클릭 시 드롭다운이 닫힙니다.'''),

    # ═══ 5. 포인트/적립금 시스템 ═══
    m("Next.js로 이커머스 포인트/적립금 시스템 만들어줘 전체 코드로",
'''이커머스 포인트/적립금 시스템을 만들어 드릴게요. 포인트 적립/사용, 이력 관리, 결제 시 적용 기능을 포함합니다.

## 폴더 구조

```
points-system/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── points/page.tsx
│   └── api/
│       ├── points/
│       │   ├── route.ts
│       │   └── history/route.ts
│       └── checkout/route.ts
├── components/
│   ├── points-summary.tsx
│   ├── points-history.tsx
│   ├── checkout-form.tsx
│   ├── points-apply.tsx
│   └── earn-badge.tsx
├── lib/
│   ├── db.ts
│   └── points.ts
├── prisma/
│   └── schema.prisma
└── package.json
```

## prisma/schema.prisma

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = "file:./dev.db"
}

model User {
  id           String             @id @default(cuid())
  name         String
  email        String             @unique
  points       Int                @default(0)
  transactions PointTransaction[]
  createdAt    DateTime           @default(now())
}

model PointTransaction {
  id          String   @id @default(cuid())
  userId      String
  user        User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  type        String   // "EARN" | "SPEND" | "EXPIRE"
  amount      Int
  balance     Int
  description String
  orderId     String?
  createdAt   DateTime @default(now())
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/points.ts

```typescript
import { prisma } from "./db";

// 포인트 적립률 (결제 금액의 3%)
export const EARN_RATE = 0.03;
// 최대 사용 비율 (결제 금액의 30%까지)
export const MAX_SPEND_RATIO = 0.3;

export async function earnPoints(userId: string, orderAmount: number, orderId: string) {
  const amount = Math.floor(orderAmount * EARN_RATE);
  if (amount <= 0) return null;

  const user = await prisma.user.findUnique({ where: { id: userId } });
  if (!user) throw new Error("사용자를 찾을 수 없습니다.");

  const newBalance = user.points + amount;

  const [updatedUser, transaction] = await prisma.$transaction([
    prisma.user.update({ where: { id: userId }, data: { points: newBalance } }),
    prisma.pointTransaction.create({
      data: { userId, type: "EARN", amount, balance: newBalance, description: `주문 적립 (${EARN_RATE * 100}%)`, orderId },
    }),
  ]);

  return { user: updatedUser, transaction };
}

export async function spendPoints(userId: string, amount: number, orderId: string) {
  const user = await prisma.user.findUnique({ where: { id: userId } });
  if (!user) throw new Error("사용자를 찾을 수 없습니다.");
  if (user.points < amount) throw new Error("포인트가 부족합니다.");

  const newBalance = user.points - amount;

  const [updatedUser, transaction] = await prisma.$transaction([
    prisma.user.update({ where: { id: userId }, data: { points: newBalance } }),
    prisma.pointTransaction.create({
      data: { userId, type: "SPEND", amount: -amount, balance: newBalance, description: "주문 사용", orderId },
    }),
  ]);

  return { user: updatedUser, transaction };
}

export function calculateMaxSpend(totalAmount: number, userPoints: number): number {
  const maxByRatio = Math.floor(totalAmount * MAX_SPEND_RATIO);
  return Math.min(maxByRatio, userPoints);
}
```

## app/api/points/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

// 사용자 포인트 조회
export async function GET(req: NextRequest) {
  const userId = req.nextUrl.searchParams.get("userId");
  if (!userId) return NextResponse.json({ error: "userId 필요" }, { status: 400 });

  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { id: true, name: true, points: true },
  });

  if (!user) return NextResponse.json({ error: "사용자 없음" }, { status: 404 });
  return NextResponse.json(user);
}
```

## app/api/points/history/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(req: NextRequest) {
  const userId = req.nextUrl.searchParams.get("userId");
  const page = parseInt(req.nextUrl.searchParams.get("page") || "1");
  const limit = 20;

  if (!userId) return NextResponse.json({ error: "userId 필요" }, { status: 400 });

  const [transactions, total] = await Promise.all([
    prisma.pointTransaction.findMany({
      where: { userId },
      orderBy: { createdAt: "desc" },
      skip: (page - 1) * limit,
      take: limit,
    }),
    prisma.pointTransaction.count({ where: { userId } }),
  ]);

  return NextResponse.json({ transactions, total, totalPages: Math.ceil(total / limit), page });
}
```

## app/api/checkout/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { earnPoints, spendPoints, calculateMaxSpend } from "@/lib/points";
import { prisma } from "@/lib/db";

export async function POST(req: NextRequest) {
  const { userId, totalAmount, usePoints } = await req.json();

  const user = await prisma.user.findUnique({ where: { id: userId } });
  if (!user) return NextResponse.json({ error: "사용자 없음" }, { status: 404 });

  const orderId = `ORD-${Date.now()}`;
  let finalAmount = totalAmount;

  // 포인트 사용
  if (usePoints > 0) {
    const maxSpend = calculateMaxSpend(totalAmount, user.points);
    const actualSpend = Math.min(usePoints, maxSpend);
    await spendPoints(userId, actualSpend, orderId);
    finalAmount -= actualSpend;
  }

  // 포인트 적립 (실결제 금액 기준)
  await earnPoints(userId, finalAmount, orderId);

  const updatedUser = await prisma.user.findUnique({ where: { id: userId } });

  return NextResponse.json({
    orderId,
    totalAmount,
    pointsUsed: usePoints,
    finalAmount,
    earnedPoints: Math.floor(finalAmount * 0.03),
    currentPoints: updatedUser?.points,
  });
}
```

## components/points-summary.tsx

```tsx
"use client";

interface Props { points: number; name: string; }

export default function PointsSummary({ points, name }: Props) {
  return (
    <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-xl p-6">
      <p className="text-sm opacity-80">{name}님의 적립금</p>
      <p className="text-3xl font-bold mt-1">{points.toLocaleString()}<span className="text-lg ml-1">P</span></p>
      <p className="text-xs mt-2 opacity-70">적립률 3% | 최대 사용 30%</p>
    </div>
  );
}
```

## components/points-history.tsx

```tsx
"use client";

interface Transaction {
  id: string;
  type: string;
  amount: number;
  balance: number;
  description: string;
  createdAt: string;
}

export default function PointsHistory({ transactions }: { transactions: Transaction[] }) {
  return (
    <div className="space-y-2">
      {transactions.map((t) => (
        <div key={t.id} className="flex justify-between items-center py-3 border-b">
          <div>
            <p className="text-sm font-medium">{t.description}</p>
            <p className="text-xs text-gray-400">{new Date(t.createdAt).toLocaleDateString("ko-KR")}</p>
          </div>
          <div className="text-right">
            <p className={`font-bold ${t.amount > 0 ? "text-blue-600" : "text-red-500"}`}>
              {t.amount > 0 ? "+" : ""}{t.amount.toLocaleString()}P
            </p>
            <p className="text-xs text-gray-400">잔액 {t.balance.toLocaleString()}P</p>
          </div>
        </div>
      ))}
    </div>
  );
}
```

## components/points-apply.tsx

```tsx
"use client";

import { useState } from "react";
import { EARN_RATE, MAX_SPEND_RATIO } from "@/lib/points";

interface Props {
  totalAmount: number;
  availablePoints: number;
  onApply: (points: number) => void;
}

export default function PointsApply({ totalAmount, availablePoints, onApply }: Props) {
  const maxSpend = Math.min(Math.floor(totalAmount * MAX_SPEND_RATIO), availablePoints);
  const [usePoints, setUsePoints] = useState(0);

  const handleMax = () => { setUsePoints(maxSpend); onApply(maxSpend); };
  const handleChange = (v: number) => {
    const clamped = Math.min(Math.max(0, v), maxSpend);
    setUsePoints(clamped);
    onApply(clamped);
  };

  const earnPreview = Math.floor((totalAmount - usePoints) * EARN_RATE);

  return (
    <div className="bg-gray-50 rounded-lg p-4 space-y-3">
      <div className="flex justify-between text-sm">
        <span>보유 적립금</span>
        <span className="font-semibold">{availablePoints.toLocaleString()}P</span>
      </div>
      <div className="flex gap-2">
        <input type="number" min={0} max={maxSpend} value={usePoints}
          onChange={(e) => handleChange(+e.target.value)}
          className="flex-1 border rounded px-3 py-2 text-sm" />
        <button onClick={handleMax}
          className="px-3 py-2 bg-gray-200 rounded text-sm hover:bg-gray-300">
          최대 사용 ({maxSpend.toLocaleString()}P)
        </button>
      </div>
      <div className="flex justify-between text-xs text-gray-500">
        <span>사용 후 결제금액: {(totalAmount - usePoints).toLocaleString()}원</span>
        <span>예상 적립: +{earnPreview.toLocaleString()}P</span>
      </div>
    </div>
  );
}
```

적립률과 최대 사용 비율은 `lib/points.ts` 상수에서 변경 가능합니다. 실결제 금액 기준으로 적립합니다.'''),

    # ═══ 6. 회원 등급 + 혜택 시스템 ═══
    m("Next.js로 회원 등급 + 혜택 시스템 만들어줘 전체 코드로",
'''회원 등급 및 혜택 시스템을 만들어 드릴게요. Bronze/Silver/Gold/VIP 등급, 누적 구매 기반 승급, 등급별 할인율을 포함합니다.

## 폴더 구조

```
membership-tier/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   └── api/
│       ├── member/
│       │   ├── route.ts
│       │   └── [id]/route.ts
│       └── tiers/route.ts
├── components/
│   ├── tier-card.tsx
│   ├── tier-progress.tsx
│   ├── benefits-table.tsx
│   ├── member-dashboard.tsx
│   └── upgrade-notice.tsx
├── lib/
│   ├── db.ts
│   └── tiers.ts
├── prisma/
│   └── schema.prisma
└── package.json
```

## prisma/schema.prisma

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = "file:./dev.db"
}

model Member {
  id             String   @id @default(cuid())
  name           String
  email          String   @unique
  tier           String   @default("BRONZE")
  totalSpending  Int      @default(0)
  monthlySpending Int     @default(0)
  discountRate   Int      @default(0)
  joinedAt       DateTime @default(now())
  tierUpdatedAt  DateTime @default(now())
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/tiers.ts

```typescript
export interface TierConfig {
  name: string;
  label: string;
  minSpending: number;
  discountRate: number;
  pointRate: number;
  freeShipping: boolean;
  color: string;
  bgColor: string;
  icon: string;
}

export const TIERS: Record<string, TierConfig> = {
  BRONZE: {
    name: "BRONZE", label: "브론즈", minSpending: 0,
    discountRate: 0, pointRate: 1, freeShipping: false,
    color: "text-orange-700", bgColor: "bg-orange-100", icon: "🥉",
  },
  SILVER: {
    name: "SILVER", label: "실버", minSpending: 300000,
    discountRate: 3, pointRate: 2, freeShipping: false,
    color: "text-gray-600", bgColor: "bg-gray-100", icon: "🥈",
  },
  GOLD: {
    name: "GOLD", label: "골드", minSpending: 1000000,
    discountRate: 5, pointRate: 3, freeShipping: true,
    color: "text-yellow-700", bgColor: "bg-yellow-100", icon: "🥇",
  },
  VIP: {
    name: "VIP", label: "VIP", minSpending: 3000000,
    discountRate: 10, pointRate: 5, freeShipping: true,
    color: "text-purple-700", bgColor: "bg-purple-100", icon: "👑",
  },
};

export const TIER_ORDER = ["BRONZE", "SILVER", "GOLD", "VIP"];

export function calculateTier(totalSpending: number): string {
  let result = "BRONZE";
  for (const tier of TIER_ORDER) {
    if (totalSpending >= TIERS[tier].minSpending) result = tier;
  }
  return result;
}

export function getNextTier(currentTier: string): TierConfig | null {
  const idx = TIER_ORDER.indexOf(currentTier);
  return idx < TIER_ORDER.length - 1 ? TIERS[TIER_ORDER[idx + 1]] : null;
}

export function getUpgradeProgress(totalSpending: number, currentTier: string): number {
  const next = getNextTier(currentTier);
  if (!next) return 100;
  const current = TIERS[currentTier];
  const range = next.minSpending - current.minSpending;
  const progress = totalSpending - current.minSpending;
  return Math.min(Math.round((progress / range) * 100), 100);
}
```

## app/api/member/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { calculateTier, TIERS } from "@/lib/tiers";

export async function GET(req: NextRequest) {
  const email = req.nextUrl.searchParams.get("email");
  if (!email) return NextResponse.json({ error: "email 필요" }, { status: 400 });

  const member = await prisma.member.findUnique({ where: { email } });
  if (!member) return NextResponse.json({ error: "회원 없음" }, { status: 404 });

  return NextResponse.json(member);
}

// 구매 후 누적 금액 업데이트 + 등급 재계산
export async function POST(req: NextRequest) {
  const { email, purchaseAmount } = await req.json();

  const member = await prisma.member.findUnique({ where: { email } });
  if (!member) return NextResponse.json({ error: "회원 없음" }, { status: 404 });

  const newTotal = member.totalSpending + purchaseAmount;
  const newTier = calculateTier(newTotal);
  const tierConfig = TIERS[newTier];

  const updated = await prisma.member.update({
    where: { email },
    data: {
      totalSpending: newTotal,
      monthlySpending: member.monthlySpending + purchaseAmount,
      tier: newTier,
      discountRate: tierConfig.discountRate,
      tierUpdatedAt: newTier !== member.tier ? new Date() : member.tierUpdatedAt,
    },
  });

  return NextResponse.json({
    member: updated,
    tierChanged: newTier !== member.tier,
    previousTier: member.tier,
    newTier,
  });
}
```

## app/api/tiers/route.ts

```typescript
import { NextResponse } from "next/server";
import { TIERS, TIER_ORDER } from "@/lib/tiers";

export async function GET() {
  const tiers = TIER_ORDER.map((key) => TIERS[key]);
  return NextResponse.json(tiers);
}
```

## components/tier-card.tsx

```tsx
"use client";

import { TIERS } from "@/lib/tiers";

interface Props { tier: string; name: string; totalSpending: number; }

export default function TierCard({ tier, name, totalSpending }: Props) {
  const config = TIERS[tier];

  return (
    <div className={`${config.bgColor} rounded-2xl p-6 relative overflow-hidden`}>
      <div className="absolute top-4 right-4 text-5xl opacity-30">{config.icon}</div>
      <p className="text-sm opacity-70">{name}님</p>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-3xl">{config.icon}</span>
        <span className={`text-2xl font-bold ${config.color}`}>{config.label}</span>
      </div>
      <div className="mt-4 space-y-1 text-sm">
        <p>누적 구매: {totalSpending.toLocaleString()}원</p>
        <p>할인율: {config.discountRate}%</p>
        <p>적립률: {config.pointRate}%</p>
        {config.freeShipping && <p className="text-green-600 font-medium">무료배송 혜택</p>}
      </div>
    </div>
  );
}
```

## components/tier-progress.tsx

```tsx
"use client";

import { getNextTier, getUpgradeProgress, TIERS } from "@/lib/tiers";

interface Props { tier: string; totalSpending: number; }

export default function TierProgress({ tier, totalSpending }: Props) {
  const nextTier = getNextTier(tier);
  const progress = getUpgradeProgress(totalSpending, tier);

  if (!nextTier) {
    return (
      <div className="bg-purple-50 rounded-lg p-4 text-center">
        <p className="text-purple-700 font-bold">최고 등급 달성! 👑</p>
        <p className="text-sm text-purple-500 mt-1">모든 혜택을 누리고 계십니다.</p>
      </div>
    );
  }

  const remaining = nextTier.minSpending - totalSpending;

  return (
    <div className="bg-white border rounded-lg p-4 space-y-3">
      <div className="flex justify-between text-sm">
        <span className="font-medium">{TIERS[tier].icon} {TIERS[tier].label}</span>
        <span className="font-medium">{nextTier.icon} {nextTier.label}</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-3">
        <div className="bg-gradient-to-r from-blue-500 to-purple-500 h-3 rounded-full transition-all"
          style={{ width: `${progress}%` }} />
      </div>
      <p className="text-xs text-center text-gray-500">
        다음 등급까지 <span className="font-bold text-blue-600">{remaining.toLocaleString()}원</span> 남았습니다.
      </p>
    </div>
  );
}
```

## components/benefits-table.tsx

```tsx
"use client";

import { TIERS, TIER_ORDER } from "@/lib/tiers";

export default function BenefitsTable({ currentTier }: { currentTier: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b">
            <th className="py-3 text-left">혜택</th>
            {TIER_ORDER.map((key) => (
              <th key={key} className={`py-3 text-center ${key === currentTier ? "bg-blue-50" : ""}`}>
                {TIERS[key].icon} {TIERS[key].label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b">
            <td className="py-3">누적 구매 기준</td>
            {TIER_ORDER.map((key) => (
              <td key={key} className={`py-3 text-center ${key === currentTier ? "bg-blue-50 font-bold" : ""}`}>
                {TIERS[key].minSpending.toLocaleString()}원
              </td>
            ))}
          </tr>
          <tr className="border-b">
            <td className="py-3">할인율</td>
            {TIER_ORDER.map((key) => (
              <td key={key} className={`py-3 text-center ${key === currentTier ? "bg-blue-50 font-bold" : ""}`}>
                {TIERS[key].discountRate}%
              </td>
            ))}
          </tr>
          <tr className="border-b">
            <td className="py-3">적립률</td>
            {TIER_ORDER.map((key) => (
              <td key={key} className={`py-3 text-center ${key === currentTier ? "bg-blue-50 font-bold" : ""}`}>
                {TIERS[key].pointRate}%
              </td>
            ))}
          </tr>
          <tr>
            <td className="py-3">무료배송</td>
            {TIER_ORDER.map((key) => (
              <td key={key} className={`py-3 text-center ${key === currentTier ? "bg-blue-50 font-bold" : ""}`}>
                {TIERS[key].freeShipping ? "✅" : "❌"}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
```

## app/page.tsx

```tsx
"use client";

import { useEffect, useState } from "react";
import TierCard from "@/components/tier-card";
import TierProgress from "@/components/tier-progress";
import BenefitsTable from "@/components/benefits-table";

export default function Home() {
  const [member, setMember] = useState<any>(null);

  useEffect(() => {
    fetch("/api/member?email=demo@example.com").then((r) => r.json()).then(setMember).catch(() => {});
  }, []);

  if (!member) return <p className="text-center mt-20 text-gray-400">로딩 중...</p>;

  return (
    <main className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">회원 등급 혜택</h1>
      <TierCard tier={member.tier} name={member.name} totalSpending={member.totalSpending} />
      <TierProgress tier={member.tier} totalSpending={member.totalSpending} />
      <div>
        <h2 className="font-bold text-lg mb-3">등급별 혜택 안내</h2>
        <BenefitsTable currentTier={member.tier} />
      </div>
    </main>
  );
}
```

등급 기준: Bronze(0원), Silver(30만원), Gold(100만원), VIP(300만원). `lib/tiers.ts`에서 기준 금액과 혜택을 조정할 수 있습니다.'''),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mega_ecommerce.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"이커머스 추가: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
