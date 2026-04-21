"""화랑 AI 대규모 프로젝트 학습 데이터 (80건+)

"프로젝트 만들어줘" → 폴더 구조 + 각 파일 전체 코드.
클로드 수준의 프로젝트 생성 능력 학습.

카테고리:
  - 이커머스 풀스택 (Next.js + Prisma) (15건)
  - 실시간 채팅 앱 (WebSocket) (12건)
  - 관리자 대시보드 풀 프로젝트 (15건)
  - React 컴포넌트 라이브러리 (12건)
  - Docker + CI/CD 구성 (12건)
  - 모바일 앱 (React Native) (14건)
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

# ════════════════════════════════════════════
# 1. 이커머스 풀스택 (Next.js + Prisma)
# ════════════════════════════════════════════

m("Next.js + Prisma로 이커머스 쇼핑몰 만들어줘 전체 코드로",
'''이커머스 쇼핑몰을 만들어 드릴게요.

## 폴더 구조

```
shop/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   ├── products/
│   │   ├── page.tsx
│   │   └── [id]/page.tsx
│   ├── cart/
│   │   └── page.tsx
│   ├── checkout/
│   │   └── page.tsx
│   └── api/
│       ├── products/
│       │   ├── route.ts
│       │   └── [id]/route.ts
│       ├── cart/
│       │   └── route.ts
│       └── orders/
│           └── route.ts
├── components/
│   ├── header.tsx
│   ├── product-card.tsx
│   ├── cart-sidebar.tsx
│   ├── checkout-form.tsx
│   └── product-gallery.tsx
├── lib/
│   ├── db.ts
│   ├── cart-store.ts
│   └── utils.ts
├── prisma/
│   └── schema.prisma
├── package.json
└── .env.local
```

## prisma/schema.prisma

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model Product {
  id          String   @id @default(cuid())
  name        String
  description String
  price       Int
  image       String
  category    String
  stock       Int      @default(0)
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
  orderItems  OrderItem[]
}

model Order {
  id         String      @id @default(cuid())
  email      String
  name       String
  address    String
  phone      String
  total      Int
  status     OrderStatus @default(PENDING)
  items      OrderItem[]
  createdAt  DateTime    @default(now())
}

model OrderItem {
  id        String  @id @default(cuid())
  quantity  Int
  price     Int
  product   Product @relation(fields: [productId], references: [id])
  productId String
  order     Order   @relation(fields: [orderId], references: [id])
  orderId   String
}

enum OrderStatus {
  PENDING
  CONFIRMED
  SHIPPED
  DELIVERED
  CANCELLED
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/utils.ts

```typescript
export function formatPrice(price: number): string {
  return new Intl.NumberFormat("ko-KR").format(price) + "원";
}

export function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
```

## lib/cart-store.ts

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface CartItem {
  id: string;
  name: string;
  price: number;
  image: string;
  quantity: number;
}

interface CartStore {
  items: CartItem[];
  addItem: (item: Omit<CartItem, "quantity">) => void;
  removeItem: (id: string) => void;
  updateQuantity: (id: string, quantity: number) => void;
  clearCart: () => void;
  total: () => number;
  count: () => number;
}

export const useCartStore = create<CartStore>()(
  persist(
    (set, get) => ({
      items: [],

      addItem: (item) =>
        set((state) => {
          const existing = state.items.find((i) => i.id === item.id);
          if (existing) {
            return {
              items: state.items.map((i) =>
                i.id === item.id ? { ...i, quantity: i.quantity + 1 } : i
              ),
            };
          }
          return { items: [...state.items, { ...item, quantity: 1 }] };
        }),

      removeItem: (id) =>
        set((state) => ({
          items: state.items.filter((i) => i.id !== id),
        })),

      updateQuantity: (id, quantity) =>
        set((state) => ({
          items: quantity <= 0
            ? state.items.filter((i) => i.id !== id)
            : state.items.map((i) => (i.id === id ? { ...i, quantity } : i)),
        })),

      clearCart: () => set({ items: [] }),

      total: () => get().items.reduce((sum, i) => sum + i.price * i.quantity, 0),

      count: () => get().items.reduce((sum, i) => sum + i.quantity, 0),
    }),
    { name: "cart-storage" }
  )
);
```

## app/api/products/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const category = searchParams.get("category");
  const search = searchParams.get("search");
  const page = parseInt(searchParams.get("page") || "1");
  const limit = 12;

  const where: any = {};
  if (category) where.category = category;
  if (search) {
    where.OR = [
      { name: { contains: search, mode: "insensitive" } },
      { description: { contains: search, mode: "insensitive" } },
    ];
  }

  const [products, total] = await Promise.all([
    prisma.product.findMany({
      where,
      skip: (page - 1) * limit,
      take: limit,
      orderBy: { createdAt: "desc" },
    }),
    prisma.product.count({ where }),
  ]);

  return NextResponse.json({
    products,
    total,
    pages: Math.ceil(total / limit),
    page,
  });
}
```

## app/api/products/[id]/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const product = await prisma.product.findUnique({ where: { id } });

  if (!product) {
    return NextResponse.json({ error: "상품을 찾을 수 없습니다" }, { status: 404 });
  }

  return NextResponse.json(product);
}
```

## app/api/orders/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const { email, name, address, phone, items } = await request.json();

  if (!items?.length) {
    return NextResponse.json({ error: "장바구니가 비어있습니다" }, { status: 400 });
  }

  const productIds = items.map((i: any) => i.id);
  const products = await prisma.product.findMany({
    where: { id: { in: productIds } },
  });

  const total = items.reduce((sum: number, item: any) => {
    const product = products.find((p) => p.id === item.id);
    return sum + (product?.price || 0) * item.quantity;
  }, 0);

  const order = await prisma.order.create({
    data: {
      email,
      name,
      address,
      phone,
      total,
      items: {
        create: items.map((item: any) => {
          const product = products.find((p) => p.id === item.id)!;
          return {
            productId: item.id,
            quantity: item.quantity,
            price: product.price,
          };
        }),
      },
    },
    include: { items: true },
  });

  // 재고 차감
  for (const item of items) {
    await prisma.product.update({
      where: { id: item.id },
      data: { stock: { decrement: item.quantity } },
    });
  }

  return NextResponse.json(order, { status: 201 });
}
```

## components/product-card.tsx

```tsx
"use client";

import Image from "next/image";
import Link from "next/link";
import { useCartStore } from "@/lib/cart-store";
import { formatPrice } from "@/lib/utils";

interface Product {
  id: string;
  name: string;
  price: number;
  image: string;
  category: string;
}

export function ProductCard({ product }: { product: Product }) {
  const addItem = useCartStore((s) => s.addItem);

  return (
    <div className="group bg-white rounded-2xl border border-gray-100 overflow-hidden hover:shadow-lg transition-shadow">
      <Link href={`/products/${product.id}`}>
        <div className="relative aspect-square bg-gray-50">
          <Image
            src={product.image}
            alt={product.name}
            fill
            className="object-cover group-hover:scale-105 transition-transform"
          />
        </div>
      </Link>

      <div className="p-4 space-y-2">
        <span className="text-xs text-blue-600 font-medium">{product.category}</span>
        <h3 className="font-semibold text-gray-900 line-clamp-1">{product.name}</h3>
        <p className="text-lg font-bold text-gray-900">{formatPrice(product.price)}</p>

        <button
          onClick={() => addItem(product)}
          className="w-full py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition"
        >
          장바구니 담기
        </button>
      </div>
    </div>
  );
}
```

## components/header.tsx

```tsx
"use client";

import Link from "next/link";
import { useCartStore } from "@/lib/cart-store";

export function Header() {
  const count = useCartStore((s) => s.count());

  return (
    <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-100">
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link href="/" className="text-xl font-bold text-gray-900">
          🛒 화랑스토어
        </Link>

        <nav className="flex items-center gap-6">
          <Link href="/products" className="text-gray-600 hover:text-gray-900">
            상품
          </Link>
          <Link href="/cart" className="relative text-gray-600 hover:text-gray-900">
            장바구니
            {count > 0 && (
              <span className="absolute -top-2 -right-4 w-5 h-5 bg-blue-600 text-white text-xs rounded-full flex items-center justify-center">
                {count}
              </span>
            )}
          </Link>
        </nav>
      </div>
    </header>
  );
}
```

## components/cart-sidebar.tsx

```tsx
"use client";

import { useCartStore } from "@/lib/cart-store";
import { formatPrice } from "@/lib/utils";
import Link from "next/link";

export function CartPage() {
  const { items, removeItem, updateQuantity, total } = useCartStore();

  if (items.length === 0) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-400 text-lg mb-4">장바구니가 비어있습니다</p>
        <Link href="/products" className="text-blue-600 hover:underline">
          쇼핑하러 가기 →
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="space-y-4">
        {items.map((item) => (
          <div key={item.id} className="flex items-center gap-4 p-4 bg-white rounded-xl border border-gray-100">
            <img src={item.image} alt={item.name} className="w-20 h-20 object-cover rounded-lg" />

            <div className="flex-1">
              <h3 className="font-semibold">{item.name}</h3>
              <p className="text-gray-500">{formatPrice(item.price)}</p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => updateQuantity(item.id, item.quantity - 1)}
                className="w-8 h-8 rounded-lg border text-gray-500 hover:bg-gray-50"
              >
                −
              </button>
              <span className="w-8 text-center">{item.quantity}</span>
              <button
                onClick={() => updateQuantity(item.id, item.quantity + 1)}
                className="w-8 h-8 rounded-lg border text-gray-500 hover:bg-gray-50"
              >
                +
              </button>
            </div>

            <p className="font-bold w-28 text-right">{formatPrice(item.price * item.quantity)}</p>

            <button
              onClick={() => removeItem(item.id)}
              className="text-red-400 hover:text-red-600"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="mt-8 p-6 bg-gray-50 rounded-xl flex items-center justify-between">
        <span className="text-lg font-semibold">총 결제금액</span>
        <span className="text-2xl font-bold text-blue-600">{formatPrice(total())}</span>
      </div>

      <Link
        href="/checkout"
        className="mt-4 block text-center py-4 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition"
      >
        주문하기
      </Link>
    </div>
  );
}
```

## components/checkout-form.tsx

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useCartStore } from "@/lib/cart-store";
import { formatPrice } from "@/lib/utils";

export function CheckoutForm() {
  const router = useRouter();
  const { items, total, clearCart } = useCartStore();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", address: "" });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, items }),
      });

      if (!res.ok) throw new Error("주문 실패");

      clearCart();
      router.push("/");
      alert("주문이 완료되었습니다!");
    } catch (err) {
      alert("주문 처리 중 오류가 발생했습니다");
    } finally {
      setLoading(false);
    }
  };

  const fields = [
    { key: "name", label: "이름", type: "text", placeholder: "홍길동" },
    { key: "email", label: "이메일", type: "email", placeholder: "hong@example.com" },
    { key: "phone", label: "전화번호", type: "tel", placeholder: "010-1234-5678" },
    { key: "address", label: "배송지", type: "text", placeholder: "서울시 강남구..." },
  ] as const;

  return (
    <form onSubmit={handleSubmit} className="max-w-lg mx-auto space-y-6">
      {fields.map(({ key, label, type, placeholder }) => (
        <div key={key}>
          <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
          <input
            type={type}
            required
            placeholder={placeholder}
            value={form[key]}
            onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none"
          />
        </div>
      ))}

      <div className="p-4 bg-gray-50 rounded-xl">
        <p className="text-sm text-gray-500">결제 금액</p>
        <p className="text-2xl font-bold">{formatPrice(total())}</p>
      </div>

      <button
        type="submit"
        disabled={loading || items.length === 0}
        className="w-full py-4 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 disabled:opacity-50 transition"
      >
        {loading ? "처리중..." : "결제하기"}
      </button>
    </form>
  );
}
```

## app/page.tsx

```tsx
import { prisma } from "@/lib/db";
import { ProductCard } from "@/components/product-card";
import Link from "next/link";

export default async function Home() {
  const products = await prisma.product.findMany({
    take: 8,
    orderBy: { createdAt: "desc" },
  });

  return (
    <main className="max-w-7xl mx-auto px-4 py-12">
      <section className="text-center mb-16">
        <h1 className="text-4xl font-bold mb-4">화랑스토어</h1>
        <p className="text-gray-500 text-lg">최고의 상품을 만나보세요</p>
      </section>

      <section>
        <div className="flex items-center justify-between mb-8">
          <h2 className="text-2xl font-bold">신상품</h2>
          <Link href="/products" className="text-blue-600 hover:underline">전체보기 →</Link>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      </section>
    </main>
  );
}
```

## app/layout.tsx

```tsx
import type { Metadata } from "next";
import { Header } from "@/components/header";
import "./globals.css";

export const metadata: Metadata = {
  title: "화랑스토어",
  description: "Next.js 이커머스 쇼핑몰",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="bg-gray-50">
        <Header />
        {children}
      </body>
    </html>
  );
}
```

## package.json

```json
{
  "name": "hwarang-shop",
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "db:push": "prisma db push",
    "db:seed": "tsx prisma/seed.ts"
  },
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@prisma/client": "^6.0.0",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "prisma": "^6.0.0",
    "typescript": "^5.0.0",
    "@types/react": "^19.0.0",
    "tailwindcss": "^4.0.0",
    "tsx": "^4.0.0"
  }
}
```

## 실행 방법

```bash
pnpm install
# .env.local에 DATABASE_URL 설정
pnpm db:push
pnpm db:seed    # 샘플 데이터
pnpm dev        # http://localhost:3000
```

Zustand 장바구니 + Prisma ORM + Next.js 15 App Router 기반 풀스택 이커머스!'''),

m("Next.js로 상품 리뷰/평점 시스템 만들어줘 전체 코드로",
'''상품 리뷰/평점 시스템을 만들어 드릴게요.

## 폴더 구조

```
review-system/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── api/
│   │   └── reviews/
│   │       ├── route.ts
│   │       └── [id]/route.ts
│   └── products/
│       └── [id]/page.tsx
├── components/
│   ├── star-rating.tsx
│   ├── review-form.tsx
│   ├── review-list.tsx
│   └── rating-summary.tsx
├── lib/
│   └── db.ts
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
  id      String   @id @default(cuid())
  name    String
  image   String
  reviews Review[]
}

model Review {
  id        String   @id @default(cuid())
  rating    Int
  title     String
  content   String
  author    String
  product   Product  @relation(fields: [productId], references: [id])
  productId String
  helpful   Int      @default(0)
  createdAt DateTime @default(now())
}
```

## components/star-rating.tsx

```tsx
"use client";

import { useState } from "react";

interface StarRatingProps {
  value: number;
  onChange?: (value: number) => void;
  readonly?: boolean;
  size?: "sm" | "md" | "lg";
}

const sizes = { sm: "text-sm", md: "text-xl", lg: "text-3xl" };

export function StarRating({ value, onChange, readonly = false, size = "md" }: StarRatingProps) {
  const [hover, setHover] = useState(0);

  return (
    <div className={`flex gap-0.5 ${sizes[size]}`}>
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={readonly}
          onClick={() => onChange?.(star)}
          onMouseEnter={() => !readonly && setHover(star)}
          onMouseLeave={() => setHover(0)}
          className={`transition ${readonly ? "cursor-default" : "cursor-pointer hover:scale-110"}`}
        >
          {star <= (hover || value) ? "★" : "☆"}
        </button>
      ))}
    </div>
  );
}
```

## components/review-form.tsx

```tsx
"use client";

import { useState } from "react";
import { StarRating } from "./star-rating";

interface ReviewFormProps {
  productId: string;
  onSubmit: () => void;
}

export function ReviewForm({ productId, onSubmit }: ReviewFormProps) {
  const [rating, setRating] = useState(0);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [author, setAuthor] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (rating === 0) return alert("별점을 선택해주세요");

    setLoading(true);
    await fetch("/api/reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ productId, rating, title, content, author }),
    });
    setRating(0);
    setTitle("");
    setContent("");
    setAuthor("");
    setLoading(false);
    onSubmit();
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-6 bg-white rounded-xl border">
      <h3 className="font-bold text-lg">리뷰 작성</h3>

      <div>
        <label className="block text-sm text-gray-600 mb-1">별점</label>
        <StarRating value={rating} onChange={setRating} size="lg" />
      </div>

      <input
        type="text"
        placeholder="작성자"
        value={author}
        onChange={(e) => setAuthor(e.target.value)}
        required
        className="w-full px-4 py-2 border rounded-lg outline-none focus:border-blue-500"
      />

      <input
        type="text"
        placeholder="리뷰 제목"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        required
        className="w-full px-4 py-2 border rounded-lg outline-none focus:border-blue-500"
      />

      <textarea
        placeholder="리뷰 내용을 작성해주세요..."
        value={content}
        onChange={(e) => setContent(e.target.value)}
        required
        rows={4}
        className="w-full px-4 py-2 border rounded-lg outline-none focus:border-blue-500 resize-none"
      />

      <button
        type="submit"
        disabled={loading}
        className="w-full py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 disabled:opacity-50 transition"
      >
        {loading ? "등록중..." : "리뷰 등록"}
      </button>
    </form>
  );
}
```

## components/rating-summary.tsx

```tsx
interface RatingSummaryProps {
  reviews: { rating: number }[];
}

export function RatingSummary({ reviews }: RatingSummaryProps) {
  if (reviews.length === 0) return null;

  const avg = reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length;
  const counts = [5, 4, 3, 2, 1].map((star) => ({
    star,
    count: reviews.filter((r) => r.rating === star).length,
    pct: (reviews.filter((r) => r.rating === star).length / reviews.length) * 100,
  }));

  return (
    <div className="flex gap-8 p-6 bg-white rounded-xl border">
      <div className="text-center">
        <div className="text-5xl font-bold">{avg.toFixed(1)}</div>
        <div className="text-yellow-500 text-2xl mt-1">
          {"★".repeat(Math.round(avg))}{"☆".repeat(5 - Math.round(avg))}
        </div>
        <div className="text-sm text-gray-500 mt-1">{reviews.length}개 리뷰</div>
      </div>

      <div className="flex-1 space-y-1">
        {counts.map(({ star, count, pct }) => (
          <div key={star} className="flex items-center gap-2 text-sm">
            <span className="w-8">{star}점</span>
            <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full bg-yellow-400 rounded-full" style={{ width: `${pct}%` }} />
            </div>
            <span className="w-8 text-gray-500">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

## components/review-list.tsx

```tsx
import { StarRating } from "./star-rating";

interface Review {
  id: string;
  rating: number;
  title: string;
  content: string;
  author: string;
  helpful: number;
  createdAt: string;
}

export function ReviewList({ reviews }: { reviews: Review[] }) {
  const handleHelpful = async (id: string) => {
    await fetch(`/api/reviews/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ helpful: true }),
    });
  };

  return (
    <div className="space-y-4">
      {reviews.map((review) => (
        <div key={review.id} className="p-5 bg-white rounded-xl border">
          <div className="flex items-center gap-3 mb-2">
            <StarRating value={review.rating} readonly size="sm" />
            <span className="font-semibold">{review.author}</span>
            <span className="text-sm text-gray-400">
              {new Date(review.createdAt).toLocaleDateString("ko-KR")}
            </span>
          </div>

          <h4 className="font-semibold mb-1">{review.title}</h4>
          <p className="text-gray-600 text-sm">{review.content}</p>

          <button
            onClick={() => handleHelpful(review.id)}
            className="mt-3 text-sm text-gray-400 hover:text-blue-600 transition"
          >
            도움이 돼요 ({review.helpful})
          </button>
        </div>
      ))}
    </div>
  );
}
```

## app/api/reviews/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const productId = request.nextUrl.searchParams.get("productId");
  if (!productId) {
    return NextResponse.json({ error: "productId 필수" }, { status: 400 });
  }

  const reviews = await prisma.review.findMany({
    where: { productId },
    orderBy: { createdAt: "desc" },
  });

  return NextResponse.json(reviews);
}

export async function POST(request: Request) {
  const { productId, rating, title, content, author } = await request.json();

  if (!rating || rating < 1 || rating > 5) {
    return NextResponse.json({ error: "별점은 1-5 사이" }, { status: 400 });
  }

  const review = await prisma.review.create({
    data: { productId, rating, title, content, author },
  });

  return NextResponse.json(review, { status: 201 });
}
```

## app/api/reviews/[id]/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await request.json();

  if (body.helpful) {
    const review = await prisma.review.update({
      where: { id },
      data: { helpful: { increment: 1 } },
    });
    return NextResponse.json(review);
  }

  return NextResponse.json({ error: "잘못된 요청" }, { status: 400 });
}
```

완전한 리뷰/평점 시스템! 별점 입력 + 분포 차트 + 도움이 돼요 기능 포함!'''),

m("Next.js로 위시리스트 + 상품 비교 기능 만들어줘",
'''위시리스트와 상품 비교 기능을 만들어 드릴게요.

## 폴더 구조

```
wishlist-compare/
├── app/
│   ├── layout.tsx
│   ├── wishlist/page.tsx
│   ├── compare/page.tsx
│   └── api/wishlist/route.ts
├── components/
│   ├── wishlist-button.tsx
│   ├── compare-button.tsx
│   ├── compare-table.tsx
│   └── wishlist-grid.tsx
├── lib/
│   ├── wishlist-store.ts
│   └── compare-store.ts
└── package.json
```

## lib/wishlist-store.ts

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface Product {
  id: string;
  name: string;
  price: number;
  image: string;
  category: string;
  specs?: Record<string, string>;
}

interface WishlistStore {
  items: Product[];
  toggle: (product: Product) => void;
  has: (id: string) => boolean;
  clear: () => void;
}

export const useWishlistStore = create<WishlistStore>()(
  persist(
    (set, get) => ({
      items: [],
      toggle: (product) =>
        set((state) => {
          const exists = state.items.some((i) => i.id === product.id);
          return {
            items: exists
              ? state.items.filter((i) => i.id !== product.id)
              : [...state.items, product],
          };
        }),
      has: (id) => get().items.some((i) => i.id === id),
      clear: () => set({ items: [] }),
    }),
    { name: "wishlist" }
  )
);
```

## lib/compare-store.ts

```typescript
import { create } from "zustand";

interface Product {
  id: string;
  name: string;
  price: number;
  image: string;
  category: string;
  specs: Record<string, string>;
}

interface CompareStore {
  items: Product[];
  add: (product: Product) => void;
  remove: (id: string) => void;
  has: (id: string) => boolean;
  clear: () => void;
}

export const useCompareStore = create<CompareStore>((set, get) => ({
  items: [],
  add: (product) =>
    set((state) => {
      if (state.items.length >= 4) {
        alert("최대 4개까지 비교 가능합니다");
        return state;
      }
      if (state.items.some((i) => i.id === product.id)) return state;
      return { items: [...state.items, product] };
    }),
  remove: (id) => set((state) => ({ items: state.items.filter((i) => i.id !== id) })),
  has: (id) => get().items.some((i) => i.id === id),
  clear: () => set({ items: [] }),
}));
```

## components/wishlist-button.tsx

```tsx
"use client";

import { useWishlistStore } from "@/lib/wishlist-store";

interface Product {
  id: string;
  name: string;
  price: number;
  image: string;
  category: string;
}

export function WishlistButton({ product }: { product: Product }) {
  const { toggle, has } = useWishlistStore();
  const isWished = has(product.id);

  return (
    <button
      onClick={() => toggle(product)}
      className={`p-2 rounded-full transition ${
        isWished ? "text-red-500 bg-red-50" : "text-gray-400 hover:text-red-500 hover:bg-red-50"
      }`}
    >
      {isWished ? "♥" : "♡"}
    </button>
  );
}
```

## components/compare-button.tsx

```tsx
"use client";

import { useCompareStore } from "@/lib/compare-store";

interface Product {
  id: string;
  name: string;
  price: number;
  image: string;
  category: string;
  specs: Record<string, string>;
}

export function CompareButton({ product }: { product: Product }) {
  const { add, remove, has } = useCompareStore();
  const isComparing = has(product.id);

  return (
    <button
      onClick={() => (isComparing ? remove(product.id) : add(product))}
      className={`px-3 py-1.5 text-sm rounded-lg border transition ${
        isComparing
          ? "border-blue-500 bg-blue-50 text-blue-700"
          : "border-gray-200 text-gray-500 hover:border-blue-300"
      }`}
    >
      {isComparing ? "✓ 비교중" : "비교하기"}
    </button>
  );
}
```

## components/compare-table.tsx

```tsx
"use client";

import { useCompareStore } from "@/lib/compare-store";

export function CompareTable() {
  const { items, remove } = useCompareStore();

  if (items.length < 2) {
    return <p className="text-center text-gray-400 py-20">2개 이상의 상품을 추가해주세요</p>;
  }

  const allSpecs = [...new Set(items.flatMap((p) => Object.keys(p.specs || {})))];

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className="p-4 text-left bg-gray-50 w-40">항목</th>
            {items.map((product) => (
              <th key={product.id} className="p-4 bg-gray-50 text-center min-w-[200px]">
                <img src={product.image} alt={product.name} className="w-24 h-24 object-cover mx-auto rounded-lg mb-2" />
                <div className="font-semibold">{product.name}</div>
                <button onClick={() => remove(product.id)} className="text-xs text-red-400 hover:text-red-600 mt-1">
                  제거
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-t">
            <td className="p-4 font-medium text-gray-600">가격</td>
            {items.map((p) => (
              <td key={p.id} className="p-4 text-center font-bold text-blue-600">
                {new Intl.NumberFormat("ko-KR").format(p.price)}원
              </td>
            ))}
          </tr>
          <tr className="border-t">
            <td className="p-4 font-medium text-gray-600">카테고리</td>
            {items.map((p) => (
              <td key={p.id} className="p-4 text-center">{p.category}</td>
            ))}
          </tr>
          {allSpecs.map((spec) => (
            <tr key={spec} className="border-t">
              <td className="p-4 font-medium text-gray-600">{spec}</td>
              {items.map((p) => (
                <td key={p.id} className="p-4 text-center">
                  {p.specs?.[spec] || "-"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

## components/wishlist-grid.tsx

```tsx
"use client";

import { useWishlistStore } from "@/lib/wishlist-store";
import { WishlistButton } from "./wishlist-button";

export function WishlistGrid() {
  const { items } = useWishlistStore();

  if (items.length === 0) {
    return <p className="text-center text-gray-400 py-20">위시리스트가 비어있습니다</p>;
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
      {items.map((product) => (
        <div key={product.id} className="bg-white rounded-xl border p-4">
          <div className="relative">
            <img src={product.image} alt={product.name} className="w-full aspect-square object-cover rounded-lg" />
            <div className="absolute top-2 right-2">
              <WishlistButton product={product} />
            </div>
          </div>
          <h3 className="font-semibold mt-3">{product.name}</h3>
          <p className="font-bold text-blue-600">
            {new Intl.NumberFormat("ko-KR").format(product.price)}원
          </p>
        </div>
      ))}
    </div>
  );
}
```

위시리스트 + 최대 4개 비교 테이블! Zustand persist로 새로고침해도 유지!'''),

m("Next.js로 쿠폰/할인 시스템 만들어줘",
'''쿠폰/할인 시스템을 만들어 드릴게요.

## 폴더 구조

```
coupon-system/
├── app/api/
│   ├── coupons/
│   │   ├── route.ts
│   │   └── validate/route.ts
│   └── orders/route.ts
├── components/
│   ├── coupon-input.tsx
│   ├── price-breakdown.tsx
│   └── coupon-badge.tsx
├── lib/
│   ├── db.ts
│   └── coupon-utils.ts
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

model Coupon {
  id           String     @id @default(cuid())
  code         String     @unique
  type         CouponType
  value        Int
  minAmount    Int        @default(0)
  maxDiscount  Int?
  usageLimit   Int        @default(0)
  usedCount    Int        @default(0)
  expiresAt    DateTime?
  isActive     Boolean    @default(true)
  createdAt    DateTime   @default(now())
}

enum CouponType {
  PERCENT
  FIXED
  FREE_SHIPPING
}
```

## lib/coupon-utils.ts

```typescript
interface Coupon {
  id: string;
  code: string;
  type: "PERCENT" | "FIXED" | "FREE_SHIPPING";
  value: number;
  minAmount: number;
  maxDiscount: number | null;
  usageLimit: number;
  usedCount: number;
  expiresAt: string | null;
  isActive: boolean;
}

interface DiscountResult {
  discount: number;
  shippingFree: boolean;
  error?: string;
}

export function calculateDiscount(coupon: Coupon, subtotal: number, shippingFee: number): DiscountResult {
  // 유효성 검사
  if (!coupon.isActive) return { discount: 0, shippingFree: false, error: "비활성 쿠폰입니다" };
  if (coupon.expiresAt && new Date(coupon.expiresAt) < new Date()) {
    return { discount: 0, shippingFree: false, error: "만료된 쿠폰입니다" };
  }
  if (coupon.usageLimit > 0 && coupon.usedCount >= coupon.usageLimit) {
    return { discount: 0, shippingFree: false, error: "사용 한도를 초과했습니다" };
  }
  if (subtotal < coupon.minAmount) {
    return { discount: 0, shippingFree: false, error: `최소 주문 금액은 ${coupon.minAmount.toLocaleString()}원입니다` };
  }

  switch (coupon.type) {
    case "PERCENT": {
      let discount = Math.floor(subtotal * (coupon.value / 100));
      if (coupon.maxDiscount) discount = Math.min(discount, coupon.maxDiscount);
      return { discount, shippingFree: false };
    }
    case "FIXED":
      return { discount: Math.min(coupon.value, subtotal), shippingFree: false };
    case "FREE_SHIPPING":
      return { discount: 0, shippingFree: true };
    default:
      return { discount: 0, shippingFree: false };
  }
}
```

## app/api/coupons/validate/route.ts

```typescript
import { prisma } from "@/lib/db";
import { calculateDiscount } from "@/lib/coupon-utils";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const { code, subtotal, shippingFee = 3000 } = await request.json();

  const coupon = await prisma.coupon.findUnique({ where: { code: code.toUpperCase() } });

  if (!coupon) {
    return NextResponse.json({ error: "존재하지 않는 쿠폰입니다" }, { status: 404 });
  }

  const result = calculateDiscount(coupon as any, subtotal, shippingFee);

  if (result.error) {
    return NextResponse.json({ error: result.error }, { status: 400 });
  }

  return NextResponse.json({
    coupon: { id: coupon.id, code: coupon.code, type: coupon.type, value: coupon.value },
    discount: result.discount,
    shippingFree: result.shippingFree,
  });
}
```

## components/coupon-input.tsx

```tsx
"use client";

import { useState } from "react";

interface CouponInputProps {
  subtotal: number;
  onApply: (result: { couponId: string; discount: number; shippingFree: boolean }) => void;
  onRemove: () => void;
  applied?: { code: string; discount: number };
}

export function CouponInput({ subtotal, onApply, onRemove, applied }: CouponInputProps) {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleApply = async () => {
    if (!code.trim()) return;
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/coupons/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: code.trim(), subtotal }),
      });
      const data = await res.json();

      if (!res.ok) {
        setError(data.error);
        return;
      }

      onApply({
        couponId: data.coupon.id,
        discount: data.discount,
        shippingFree: data.shippingFree,
      });
      setCode("");
    } catch {
      setError("쿠폰 적용에 실패했습니다");
    } finally {
      setLoading(false);
    }
  };

  if (applied) {
    return (
      <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-xl">
        <div>
          <span className="text-green-700 font-medium">🎟 {applied.code}</span>
          <span className="text-green-600 text-sm ml-2">
            -{applied.discount.toLocaleString()}원
          </span>
        </div>
        <button onClick={onRemove} className="text-sm text-red-400 hover:text-red-600">
          제거
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="flex gap-2">
        <input
          type="text"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="쿠폰 코드 입력"
          className="flex-1 px-4 py-2 border rounded-xl outline-none focus:border-blue-500 uppercase"
        />
        <button
          onClick={handleApply}
          disabled={loading || !code.trim()}
          className="px-4 py-2 bg-gray-900 text-white rounded-xl font-medium hover:bg-gray-800 disabled:opacity-50 transition"
        >
          {loading ? "..." : "적용"}
        </button>
      </div>
      {error && <p className="text-sm text-red-500 mt-1">{error}</p>}
    </div>
  );
}
```

## components/price-breakdown.tsx

```tsx
interface PriceBreakdownProps {
  subtotal: number;
  discount: number;
  shippingFee: number;
  shippingFree: boolean;
}

export function PriceBreakdown({ subtotal, discount, shippingFee, shippingFree }: PriceBreakdownProps) {
  const shipping = shippingFree ? 0 : shippingFee;
  const total = subtotal - discount + shipping;

  const fmt = (n: number) => n.toLocaleString("ko-KR") + "원";

  return (
    <div className="space-y-3 p-5 bg-gray-50 rounded-xl">
      <div className="flex justify-between text-gray-600">
        <span>상품 금액</span>
        <span>{fmt(subtotal)}</span>
      </div>

      {discount > 0 && (
        <div className="flex justify-between text-red-500">
          <span>쿠폰 할인</span>
          <span>-{fmt(discount)}</span>
        </div>
      )}

      <div className="flex justify-between text-gray-600">
        <span>배송비</span>
        <span>{shippingFree ? <s className="text-gray-400">{fmt(shippingFee)}</s> : fmt(shippingFee)}</span>
      </div>

      {shippingFree && (
        <div className="text-green-600 text-sm text-right">무료배송 적용!</div>
      )}

      <div className="border-t pt-3 flex justify-between font-bold text-lg">
        <span>결제 금액</span>
        <span className="text-blue-600">{fmt(total)}</span>
      </div>
    </div>
  );
}
```

퍼센트/정액/무료배송 3가지 쿠폰 타입 + 유효성 검사 + 실시간 적용!'''),

m("Next.js 이커머스 상품 검색 + 필터 + 정렬 전체 코드",
'''상품 검색/필터/정렬 시스템을 만들어 드릴게요.

## 폴더 구조

```
product-filter/
├── app/
│   ├── products/page.tsx
│   └── api/products/route.ts
├── components/
│   ├── search-bar.tsx
│   ├── filter-sidebar.tsx
│   ├── sort-dropdown.tsx
│   ├── product-grid.tsx
│   ├── price-range-slider.tsx
│   └── active-filters.tsx
├── lib/
│   └── use-product-filters.ts
└── package.json
```

## lib/use-product-filters.ts

```typescript
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

export interface Filters {
  search: string;
  category: string;
  minPrice: number;
  maxPrice: number;
  sort: string;
  page: number;
}

export function useProductFilters(): [Filters, (updates: Partial<Filters>) => void] {
  const router = useRouter();
  const searchParams = useSearchParams();

  const filters: Filters = {
    search: searchParams.get("search") || "",
    category: searchParams.get("category") || "",
    minPrice: parseInt(searchParams.get("minPrice") || "0"),
    maxPrice: parseInt(searchParams.get("maxPrice") || "0"),
    sort: searchParams.get("sort") || "newest",
    page: parseInt(searchParams.get("page") || "1"),
  };

  const setFilters = useCallback(
    (updates: Partial<Filters>) => {
      const params = new URLSearchParams(searchParams.toString());

      Object.entries({ ...filters, ...updates, page: updates.page || 1 }).forEach(
        ([key, value]) => {
          if (value && value !== 0) {
            params.set(key, String(value));
          } else {
            params.delete(key);
          }
        }
      );

      router.push(`/products?${params.toString()}`);
    },
    [searchParams, router, filters]
  );

  return [filters, setFilters];
}
```

## components/search-bar.tsx

```tsx
"use client";

import { useState, useEffect } from "react";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
}

export function SearchBar({ value, onChange }: SearchBarProps) {
  const [input, setInput] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (input !== value) onChange(input);
    }, 300);
    return () => clearTimeout(timer);
  }, [input, value, onChange]);

  return (
    <div className="relative">
      <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="상품명으로 검색..."
        className="w-full pl-12 pr-4 py-3 bg-white border border-gray-200 rounded-xl outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition"
      />
      {input && (
        <button
          onClick={() => { setInput(""); onChange(""); }}
          className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
        >
          ✕
        </button>
      )}
    </div>
  );
}
```

## components/filter-sidebar.tsx

```tsx
"use client";

interface FilterSidebarProps {
  category: string;
  onCategoryChange: (category: string) => void;
  minPrice: number;
  maxPrice: number;
  onPriceChange: (min: number, max: number) => void;
}

const CATEGORIES = ["전자기기", "의류", "식품", "도서", "가구", "스포츠"];
const PRICE_RANGES = [
  { label: "전체", min: 0, max: 0 },
  { label: "1만원 이하", min: 0, max: 10000 },
  { label: "1~5만원", min: 10000, max: 50000 },
  { label: "5~10만원", min: 50000, max: 100000 },
  { label: "10~50만원", min: 100000, max: 500000 },
  { label: "50만원 이상", min: 500000, max: 0 },
];

export function FilterSidebar({ category, onCategoryChange, minPrice, maxPrice, onPriceChange }: FilterSidebarProps) {
  return (
    <aside className="w-64 space-y-8">
      <div>
        <h3 className="font-bold text-gray-900 mb-3">카테고리</h3>
        <div className="space-y-1">
          <button
            onClick={() => onCategoryChange("")}
            className={`block w-full text-left px-3 py-2 rounded-lg text-sm transition ${
              !category ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-600 hover:bg-gray-50"
            }`}
          >
            전체
          </button>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => onCategoryChange(cat)}
              className={`block w-full text-left px-3 py-2 rounded-lg text-sm transition ${
                category === cat ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      <div>
        <h3 className="font-bold text-gray-900 mb-3">가격대</h3>
        <div className="space-y-1">
          {PRICE_RANGES.map((range) => (
            <button
              key={range.label}
              onClick={() => onPriceChange(range.min, range.max)}
              className={`block w-full text-left px-3 py-2 rounded-lg text-sm transition ${
                minPrice === range.min && maxPrice === range.max
                  ? "bg-blue-50 text-blue-700 font-medium"
                  : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
```

## components/sort-dropdown.tsx

```tsx
"use client";

interface SortDropdownProps {
  value: string;
  onChange: (sort: string) => void;
}

const OPTIONS = [
  { value: "newest", label: "최신순" },
  { value: "price_asc", label: "가격 낮은순" },
  { value: "price_desc", label: "가격 높은순" },
  { value: "name_asc", label: "이름순" },
  { value: "popular", label: "인기순" },
];

export function SortDropdown({ value, onChange }: SortDropdownProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-4 py-2 border border-gray-200 rounded-xl bg-white outline-none focus:border-blue-500 text-sm"
    >
      {OPTIONS.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
```

## components/active-filters.tsx

```tsx
"use client";

interface ActiveFiltersProps {
  filters: {
    search: string;
    category: string;
    minPrice: number;
    maxPrice: number;
  };
  onRemove: (key: string) => void;
  onClearAll: () => void;
}

export function ActiveFilters({ filters, onRemove, onClearAll }: ActiveFiltersProps) {
  const tags: { key: string; label: string }[] = [];

  if (filters.search) tags.push({ key: "search", label: `"${filters.search}"` });
  if (filters.category) tags.push({ key: "category", label: filters.category });
  if (filters.minPrice || filters.maxPrice) {
    const min = filters.minPrice ? `${(filters.minPrice / 10000).toFixed(0)}만` : "";
    const max = filters.maxPrice ? `${(filters.maxPrice / 10000).toFixed(0)}만` : "";
    tags.push({ key: "price", label: `${min}~${max}원` });
  }

  if (tags.length === 0) return null;

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {tags.map((tag) => (
        <span key={tag.key} className="inline-flex items-center gap-1 px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-sm">
          {tag.label}
          <button onClick={() => onRemove(tag.key)} className="hover:text-blue-900">✕</button>
        </span>
      ))}
      <button onClick={onClearAll} className="text-sm text-gray-400 hover:text-gray-600">
        전체 해제
      </button>
    </div>
  );
}
```

## app/api/products/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const sp = request.nextUrl.searchParams;
  const search = sp.get("search");
  const category = sp.get("category");
  const minPrice = parseInt(sp.get("minPrice") || "0");
  const maxPrice = parseInt(sp.get("maxPrice") || "0");
  const sort = sp.get("sort") || "newest";
  const page = parseInt(sp.get("page") || "1");
  const limit = 12;

  const where: any = {};

  if (search) {
    where.OR = [
      { name: { contains: search, mode: "insensitive" } },
      { description: { contains: search, mode: "insensitive" } },
    ];
  }
  if (category) where.category = category;
  if (minPrice > 0) where.price = { ...where.price, gte: minPrice };
  if (maxPrice > 0) where.price = { ...where.price, lte: maxPrice };

  const orderBy: any = {
    newest: { createdAt: "desc" },
    price_asc: { price: "asc" },
    price_desc: { price: "desc" },
    name_asc: { name: "asc" },
    popular: { viewCount: "desc" },
  }[sort] || { createdAt: "desc" };

  const [products, total] = await Promise.all([
    prisma.product.findMany({
      where,
      orderBy,
      skip: (page - 1) * limit,
      take: limit,
    }),
    prisma.product.count({ where }),
  ]);

  return NextResponse.json({
    products,
    total,
    pages: Math.ceil(total / limit),
    page,
  });
}
```

URL 기반 필터 → SEO 친화적 + 뒤로가기 지원 + 300ms 디바운스 검색!'''),

# ════════════════════════════════════════════
# 2. 실시간 채팅 앱 (WebSocket)
# ════════════════════════════════════════════

m("Node.js + Socket.IO로 실시간 채팅 앱 만들어줘 전체 코드로",
'''실시간 채팅 앱을 만들어 드릴게요.

## 폴더 구조

```
chat-app/
├── server/
│   ├── index.ts
│   ├── socket-handler.ts
│   ├── room-manager.ts
│   └── types.ts
├── client/
│   ├── index.html
│   ├── app.ts
│   ├── components/
│   │   ├── chat-room.ts
│   │   ├── message-list.ts
│   │   ├── user-list.ts
│   │   └── room-selector.ts
│   └── styles.css
├── package.json
└── tsconfig.json
```

## server/types.ts

```typescript
export interface User {
  id: string;
  name: string;
  room: string;
  avatar: string;
}

export interface Message {
  id: string;
  userId: string;
  userName: string;
  content: string;
  type: "text" | "system" | "image";
  room: string;
  timestamp: number;
}

export interface Room {
  id: string;
  name: string;
  users: Map<string, User>;
  messages: Message[];
}
```

## server/room-manager.ts

```typescript
import { Room, User, Message } from "./types";

export class RoomManager {
  private rooms = new Map<string, Room>();

  constructor() {
    // 기본 채팅방
    this.createRoom("general", "일반");
    this.createRoom("tech", "기술");
    this.createRoom("random", "잡담");
  }

  createRoom(id: string, name: string): Room {
    const room: Room = { id, name, users: new Map(), messages: [] };
    this.rooms.set(id, room);
    return room;
  }

  getRoom(id: string): Room | undefined {
    return this.rooms.get(id);
  }

  getRoomList(): { id: string; name: string; userCount: number }[] {
    return Array.from(this.rooms.values()).map((r) => ({
      id: r.id,
      name: r.name,
      userCount: r.users.size,
    }));
  }

  joinRoom(roomId: string, user: User): void {
    const room = this.rooms.get(roomId);
    if (!room) return;
    room.users.set(user.id, user);
  }

  leaveRoom(roomId: string, userId: string): void {
    const room = this.rooms.get(roomId);
    if (!room) return;
    room.users.delete(userId);
  }

  addMessage(roomId: string, message: Message): void {
    const room = this.rooms.get(roomId);
    if (!room) return;
    room.messages.push(message);
    // 최근 200개만 유지
    if (room.messages.length > 200) {
      room.messages = room.messages.slice(-200);
    }
  }

  getRoomUsers(roomId: string): User[] {
    const room = this.rooms.get(roomId);
    return room ? Array.from(room.users.values()) : [];
  }

  getRecentMessages(roomId: string, limit = 50): Message[] {
    const room = this.rooms.get(roomId);
    return room ? room.messages.slice(-limit) : [];
  }
}
```

## server/socket-handler.ts

```typescript
import { Server, Socket } from "socket.io";
import { RoomManager } from "./room-manager";
import { Message, User } from "./types";
import { randomUUID } from "crypto";

export function setupSocketHandlers(io: Server, roomManager: RoomManager) {
  io.on("connection", (socket: Socket) => {
    console.log(`접속: ${socket.id}`);
    let currentUser: User | null = null;

    // 로그인
    socket.on("login", (name: string, callback: Function) => {
      currentUser = {
        id: socket.id,
        name,
        room: "",
        avatar: `https://api.dicebear.com/7.x/thumbs/svg?seed=${name}`,
      };
      socket.emit("rooms", roomManager.getRoomList());
      callback({ success: true, user: currentUser });
    });

    // 방 입장
    socket.on("join-room", (roomId: string) => {
      if (!currentUser) return;

      // 이전 방 퇴장
      if (currentUser.room) {
        socket.leave(currentUser.room);
        roomManager.leaveRoom(currentUser.room, currentUser.id);
        io.to(currentUser.room).emit("user-left", currentUser);
        io.to(currentUser.room).emit("users", roomManager.getRoomUsers(currentUser.room));
      }

      // 새 방 입장
      currentUser.room = roomId;
      socket.join(roomId);
      roomManager.joinRoom(roomId, currentUser);

      // 시스템 메시지
      const sysMsg: Message = {
        id: randomUUID(),
        userId: "system",
        userName: "시스템",
        content: `${currentUser.name}님이 입장했습니다`,
        type: "system",
        room: roomId,
        timestamp: Date.now(),
      };
      roomManager.addMessage(roomId, sysMsg);

      // 이벤트 전송
      socket.emit("messages", roomManager.getRecentMessages(roomId));
      io.to(roomId).emit("users", roomManager.getRoomUsers(roomId));
      io.to(roomId).emit("new-message", sysMsg);
      io.emit("rooms", roomManager.getRoomList());
    });

    // 메시지 전송
    socket.on("send-message", (content: string) => {
      if (!currentUser || !currentUser.room) return;

      const message: Message = {
        id: randomUUID(),
        userId: currentUser.id,
        userName: currentUser.name,
        content,
        type: "text",
        room: currentUser.room,
        timestamp: Date.now(),
      };

      roomManager.addMessage(currentUser.room, message);
      io.to(currentUser.room).emit("new-message", message);
    });

    // 타이핑 표시
    socket.on("typing", () => {
      if (!currentUser || !currentUser.room) return;
      socket.to(currentUser.room).emit("user-typing", currentUser.name);
    });

    // 연결 해제
    socket.on("disconnect", () => {
      if (!currentUser) return;

      if (currentUser.room) {
        roomManager.leaveRoom(currentUser.room, currentUser.id);

        const sysMsg: Message = {
          id: randomUUID(),
          userId: "system",
          userName: "시스템",
          content: `${currentUser.name}님이 퇴장했습니다`,
          type: "system",
          room: currentUser.room,
          timestamp: Date.now(),
        };
        roomManager.addMessage(currentUser.room, sysMsg);
        io.to(currentUser.room).emit("new-message", sysMsg);
        io.to(currentUser.room).emit("users", roomManager.getRoomUsers(currentUser.room));
      }

      io.emit("rooms", roomManager.getRoomList());
      console.log(`퇴장: ${currentUser.name}`);
    });
  });
}
```

## server/index.ts

```typescript
import express from "express";
import { createServer } from "http";
import { Server } from "socket.io";
import path from "path";
import { RoomManager } from "./room-manager";
import { setupSocketHandlers } from "./socket-handler";

const app = express();
const server = createServer(app);
const io = new Server(server, {
  cors: { origin: "*" },
});

app.use(express.static(path.join(__dirname, "../client")));

const roomManager = new RoomManager();
setupSocketHandlers(io, roomManager);

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`채팅 서버 실행: http://localhost:${PORT}`);
});
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>화랑 채팅</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <!-- 로그인 -->
  <div id="login-screen" class="screen active">
    <div class="login-box">
      <h1>💬 화랑 채팅</h1>
      <input type="text" id="name-input" placeholder="닉네임을 입력하세요" maxlength="20">
      <button id="login-btn">입장</button>
    </div>
  </div>

  <!-- 채팅 -->
  <div id="chat-screen" class="screen">
    <div class="chat-layout">
      <!-- 사이드바 -->
      <aside class="sidebar">
        <h2>채팅방</h2>
        <div id="room-list"></div>
        <hr>
        <h3>접속자</h3>
        <div id="user-list"></div>
      </aside>

      <!-- 메인 -->
      <main class="chat-main">
        <header id="room-header">
          <h2 id="room-name">방을 선택하세요</h2>
          <span id="room-count"></span>
        </header>

        <div id="messages" class="messages"></div>

        <div id="typing-indicator" class="typing hidden"></div>

        <form id="message-form" class="message-form">
          <input type="text" id="message-input" placeholder="메시지를 입력하세요..." disabled>
          <button type="submit" disabled>전송</button>
        </form>
      </main>
    </div>
  </div>

  <script src="/socket.io/socket.io.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/app.ts

```typescript
const socket = io();

// DOM
const loginScreen = document.getElementById("login-screen")!;
const chatScreen = document.getElementById("chat-screen")!;
const nameInput = document.getElementById("name-input") as HTMLInputElement;
const loginBtn = document.getElementById("login-btn")!;
const roomList = document.getElementById("room-list")!;
const userList = document.getElementById("user-list")!;
const messages = document.getElementById("messages")!;
const messageForm = document.getElementById("message-form") as HTMLFormElement;
const messageInput = document.getElementById("message-input") as HTMLInputElement;
const roomName = document.getElementById("room-name")!;
const roomCount = document.getElementById("room-count")!;
const typingIndicator = document.getElementById("typing-indicator")!;

let currentUser: any = null;
let typingTimeout: number | null = null;

// 로그인
loginBtn.addEventListener("click", () => {
  const name = nameInput.value.trim();
  if (!name) return;

  socket.emit("login", name, (res: any) => {
    if (res.success) {
      currentUser = res.user;
      loginScreen.classList.remove("active");
      chatScreen.classList.add("active");
    }
  });
});

nameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") loginBtn.click();
});

// 방 목록
socket.on("rooms", (rooms: any[]) => {
  roomList.innerHTML = rooms
    .map(
      (r) => `
    <div class="room-item ${currentUser?.room === r.id ? "active" : ""}" data-id="${r.id}">
      <span class="room-name"># ${r.name}</span>
      <span class="room-users">${r.userCount}</span>
    </div>
  `
    )
    .join("");

  roomList.querySelectorAll(".room-item").forEach((el) => {
    el.addEventListener("click", () => {
      const roomId = (el as HTMLElement).dataset.id!;
      socket.emit("join-room", roomId);
      roomName.textContent = `# ${el.querySelector(".room-name")!.textContent}`;
      messageInput.disabled = false;
      messageInput.focus();
      (messageForm.querySelector("button") as HTMLButtonElement).disabled = false;
    });
  });
});

// 사용자 목록
socket.on("users", (users: any[]) => {
  roomCount.textContent = `${users.length}명`;
  userList.innerHTML = users
    .map(
      (u) => `
    <div class="user-item">
      <img src="${u.avatar}" class="avatar" alt="${u.name}">
      <span>${u.name}</span>
    </div>
  `
    )
    .join("");
});

// 메시지 목록
socket.on("messages", (msgs: any[]) => {
  messages.innerHTML = "";
  msgs.forEach(renderMessage);
  messages.scrollTop = messages.scrollHeight;
});

// 새 메시지
socket.on("new-message", (msg: any) => {
  renderMessage(msg);
  messages.scrollTop = messages.scrollHeight;
});

function renderMessage(msg: any) {
  const div = document.createElement("div");
  const time = new Date(msg.timestamp).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });

  if (msg.type === "system") {
    div.className = "message system";
    div.textContent = msg.content;
  } else {
    const isMe = msg.userId === socket.id;
    div.className = `message ${isMe ? "mine" : "other"}`;
    div.innerHTML = `
      ${!isMe ? `<strong class="msg-author">${msg.userName}</strong>` : ""}
      <div class="msg-bubble">${escapeHtml(msg.content)}</div>
      <span class="msg-time">${time}</span>
    `;
  }

  messages.appendChild(div);
}

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// 메시지 전송
messageForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const content = messageInput.value.trim();
  if (!content) return;

  socket.emit("send-message", content);
  messageInput.value = "";
});

// 타이핑 표시
messageInput.addEventListener("input", () => {
  socket.emit("typing");
});

socket.on("user-typing", (name: string) => {
  typingIndicator.textContent = `${name}님이 입력중...`;
  typingIndicator.classList.remove("hidden");

  if (typingTimeout) clearTimeout(typingTimeout);
  typingTimeout = window.setTimeout(() => {
    typingIndicator.classList.add("hidden");
  }, 2000);
});
```

## client/styles.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f0f2f5; height: 100vh; }

.screen { display: none; height: 100vh; }
.screen.active { display: flex; }

/* 로그인 */
.login-box {
  margin: auto; text-align: center; padding: 3rem; background: white;
  border-radius: 1.5rem; box-shadow: 0 4px 24px rgba(0,0,0,0.08);
}
.login-box h1 { font-size: 2rem; margin-bottom: 1.5rem; }
.login-box input {
  display: block; width: 280px; padding: 0.75rem 1rem; border: 1px solid #ddd;
  border-radius: 0.75rem; font-size: 1rem; outline: none; margin-bottom: 1rem;
}
.login-box input:focus { border-color: #3b82f6; }
.login-box button {
  width: 280px; padding: 0.75rem; background: #3b82f6; color: white;
  border: none; border-radius: 0.75rem; font-size: 1rem; font-weight: 600; cursor: pointer;
}

/* 채팅 레이아웃 */
.chat-layout { display: flex; width: 100%; height: 100vh; }

.sidebar {
  width: 260px; background: #1e293b; color: white; padding: 1.5rem;
  overflow-y: auto; flex-shrink: 0;
}
.sidebar h2 { font-size: 1.1rem; margin-bottom: 1rem; color: #94a3b8; }
.sidebar h3 { font-size: 0.9rem; margin-bottom: 0.5rem; color: #64748b; }
.sidebar hr { border: none; border-top: 1px solid #334155; margin: 1rem 0; }

.room-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0.5rem 0.75rem; border-radius: 0.5rem; cursor: pointer;
  margin-bottom: 0.25rem; transition: background 0.15s;
}
.room-item:hover { background: #334155; }
.room-item.active { background: #3b82f6; }
.room-users { font-size: 0.75rem; background: #475569; padding: 0.1rem 0.5rem; border-radius: 1rem; }

.user-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0; font-size: 0.9rem; }
.avatar { width: 28px; height: 28px; border-radius: 50%; }

/* 메인 */
.chat-main { flex: 1; display: flex; flex-direction: column; background: white; }

header { padding: 1rem 1.5rem; border-bottom: 1px solid #e5e7eb; display: flex; align-items: center; gap: 1rem; }
header h2 { font-size: 1.1rem; }

.messages { flex: 1; overflow-y: auto; padding: 1rem 1.5rem; }

.message { margin-bottom: 0.75rem; }
.message.system { text-align: center; color: #9ca3af; font-size: 0.85rem; padding: 0.5rem; }
.message.mine { text-align: right; }
.msg-author { font-size: 0.8rem; color: #6b7280; display: block; margin-bottom: 0.2rem; }
.msg-bubble {
  display: inline-block; max-width: 70%; padding: 0.6rem 1rem;
  border-radius: 1rem; font-size: 0.95rem; word-break: break-word;
}
.message.mine .msg-bubble { background: #3b82f6; color: white; border-bottom-right-radius: 0.25rem; }
.message.other .msg-bubble { background: #f1f5f9; color: #1e293b; border-bottom-left-radius: 0.25rem; }
.msg-time { font-size: 0.7rem; color: #9ca3af; margin-top: 0.2rem; display: block; }

.typing { padding: 0.5rem 1.5rem; color: #9ca3af; font-size: 0.85rem; }
.hidden { display: none; }

.message-form { display: flex; gap: 0.5rem; padding: 1rem 1.5rem; border-top: 1px solid #e5e7eb; }
.message-form input {
  flex: 1; padding: 0.75rem 1rem; border: 1px solid #e5e7eb;
  border-radius: 0.75rem; outline: none; font-size: 1rem;
}
.message-form button {
  padding: 0.75rem 1.5rem; background: #3b82f6; color: white;
  border: none; border-radius: 0.75rem; font-weight: 600; cursor: pointer;
}
.message-form button:disabled { opacity: 0.5; cursor: not-allowed; }
```

## package.json

```json
{
  "name": "chat-app",
  "version": "1.0.0",
  "scripts": {
    "dev": "tsx watch server/index.ts",
    "build": "tsc",
    "start": "node dist/server/index.js"
  },
  "dependencies": {
    "express": "^4.21.0",
    "socket.io": "^4.8.0"
  },
  "devDependencies": {
    "@types/express": "^5.0.0",
    "tsx": "^4.0.0",
    "typescript": "^5.0.0"
  }
}
```

## 실행

```bash
pnpm install
pnpm dev    # http://localhost:3000
```

Socket.IO 기반 실시간 채팅! 방 시스템 + 타이핑 표시 + 시스템 메시지 + 접속자 목록!'''),

m("WebSocket으로 실시간 알림 시스템 만들어줘 전체 코드로",
'''실시간 알림 시스템을 만들어 드릴게요.

## 폴더 구조

```
notification-system/
├── server/
│   ├── index.ts
│   ├── notification-service.ts
│   └── types.ts
├── client/
│   ├── hooks/
│   │   └── use-notifications.ts
│   └── components/
│       ├── notification-bell.tsx
│       ├── notification-dropdown.tsx
│       ├── notification-item.tsx
│       └── notification-toast.tsx
├── package.json
└── tsconfig.json
```

## server/types.ts

```typescript
export type NotificationType = "info" | "success" | "warning" | "error" | "message" | "order";

export interface Notification {
  id: string;
  userId: string;
  type: NotificationType;
  title: string;
  message: string;
  link?: string;
  read: boolean;
  createdAt: number;
}
```

## server/notification-service.ts

```typescript
import { Server } from "socket.io";
import { Notification, NotificationType } from "./types";
import { randomUUID } from "crypto";

export class NotificationService {
  private io: Server;
  private notifications = new Map<string, Notification[]>();

  constructor(io: Server) {
    this.io = io;
  }

  send(userId: string, type: NotificationType, title: string, message: string, link?: string) {
    const notification: Notification = {
      id: randomUUID(),
      userId,
      type,
      title,
      message,
      link,
      read: false,
      createdAt: Date.now(),
    };

    // 저장
    const userNotifs = this.notifications.get(userId) || [];
    userNotifs.unshift(notification);
    if (userNotifs.length > 100) userNotifs.pop();
    this.notifications.set(userId, userNotifs);

    // 실시간 전송
    this.io.to(`user:${userId}`).emit("notification", notification);
    this.io.to(`user:${userId}`).emit("unread-count", this.getUnreadCount(userId));

    return notification;
  }

  broadcast(type: NotificationType, title: string, message: string) {
    const notification: Notification = {
      id: randomUUID(),
      userId: "all",
      type,
      title,
      message,
      read: false,
      createdAt: Date.now(),
    };
    this.io.emit("notification", notification);
  }

  getNotifications(userId: string, limit = 20): Notification[] {
    return (this.notifications.get(userId) || []).slice(0, limit);
  }

  getUnreadCount(userId: string): number {
    return (this.notifications.get(userId) || []).filter((n) => !n.read).length;
  }

  markAsRead(userId: string, notificationId: string) {
    const notifs = this.notifications.get(userId) || [];
    const notif = notifs.find((n) => n.id === notificationId);
    if (notif) notif.read = true;
  }

  markAllAsRead(userId: string) {
    const notifs = this.notifications.get(userId) || [];
    notifs.forEach((n) => (n.read = true));
  }
}
```

## server/index.ts

```typescript
import express from "express";
import { createServer } from "http";
import { Server } from "socket.io";
import { NotificationService } from "./notification-service";

const app = express();
const server = createServer(app);
const io = new Server(server, { cors: { origin: "*" } });

app.use(express.json());

const notifService = new NotificationService(io);

io.on("connection", (socket) => {
  const userId = socket.handshake.query.userId as string;
  if (!userId) return socket.disconnect();

  socket.join(`user:${userId}`);
  console.log(`접속: ${userId}`);

  // 초기 데이터
  socket.emit("notifications", notifService.getNotifications(userId));
  socket.emit("unread-count", notifService.getUnreadCount(userId));

  socket.on("mark-read", (id: string) => {
    notifService.markAsRead(userId, id);
    socket.emit("unread-count", notifService.getUnreadCount(userId));
  });

  socket.on("mark-all-read", () => {
    notifService.markAllAsRead(userId);
    socket.emit("unread-count", 0);
  });

  socket.on("disconnect", () => {
    console.log(`퇴장: ${userId}`);
  });
});

// REST API: 알림 전송 (서버 간 통신용)
app.post("/api/notify", (req, res) => {
  const { userId, type, title, message, link } = req.body;
  const notif = notifService.send(userId, type, title, message, link);
  res.json(notif);
});

app.post("/api/broadcast", (req, res) => {
  const { type, title, message } = req.body;
  notifService.broadcast(type, title, message);
  res.json({ success: true });
});

server.listen(3001, () => console.log("알림 서버: http://localhost:3001"));
```

## client/hooks/use-notifications.ts

```typescript
import { useEffect, useState, useCallback } from "react";
import { io, Socket } from "socket.io-client";

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  link?: string;
  read: boolean;
  createdAt: number;
}

export function useNotifications(userId: string) {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [latestNotif, setLatestNotif] = useState<Notification | null>(null);

  useEffect(() => {
    const s = io("http://localhost:3001", { query: { userId } });

    s.on("notifications", setNotifications);
    s.on("unread-count", setUnreadCount);

    s.on("notification", (notif: Notification) => {
      setNotifications((prev) => [notif, ...prev]);
      setLatestNotif(notif);
      // 토스트 3초 후 제거
      setTimeout(() => setLatestNotif(null), 4000);
    });

    setSocket(s);
    return () => { s.disconnect(); };
  }, [userId]);

  const markAsRead = useCallback(
    (id: string) => {
      socket?.emit("mark-read", id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    },
    [socket]
  );

  const markAllAsRead = useCallback(() => {
    socket?.emit("mark-all-read");
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnreadCount(0);
  }, [socket]);

  return { notifications, unreadCount, latestNotif, markAsRead, markAllAsRead };
}
```

## client/components/notification-bell.tsx

```tsx
"use client";

interface NotificationBellProps {
  count: number;
  onClick: () => void;
}

export function NotificationBell({ count, onClick }: NotificationBellProps) {
  return (
    <button onClick={onClick} className="relative p-2 rounded-full hover:bg-gray-100 transition">
      <svg className="w-6 h-6 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
      </svg>
      {count > 0 && (
        <span className="absolute -top-1 -right-1 min-w-[20px] h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center font-bold px-1">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </button>
  );
}
```

## client/components/notification-toast.tsx

```tsx
"use client";

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
}

const typeIcons: Record<string, string> = {
  info: "ℹ️",
  success: "✅",
  warning: "⚠️",
  error: "❌",
  message: "💬",
  order: "📦",
};

export function NotificationToast({ notification }: { notification: Notification | null }) {
  if (!notification) return null;

  return (
    <div className="fixed top-4 right-4 z-50 animate-slide-in">
      <div className="bg-white rounded-xl shadow-xl border p-4 max-w-sm flex gap-3">
        <span className="text-2xl">{typeIcons[notification.type] || "🔔"}</span>
        <div>
          <p className="font-semibold text-sm">{notification.title}</p>
          <p className="text-gray-500 text-sm">{notification.message}</p>
        </div>
      </div>
    </div>
  );
}
```

## client/components/notification-dropdown.tsx

```tsx
"use client";

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  read: boolean;
  createdAt: number;
}

interface NotificationDropdownProps {
  notifications: Notification[];
  onMarkRead: (id: string) => void;
  onMarkAllRead: () => void;
  onClose: () => void;
}

export function NotificationDropdown({ notifications, onMarkRead, onMarkAllRead, onClose }: NotificationDropdownProps) {
  const typeIcons: Record<string, string> = {
    info: "ℹ️", success: "✅", warning: "⚠️", error: "❌", message: "💬", order: "📦",
  };

  return (
    <div className="absolute top-full right-0 mt-2 w-96 bg-white rounded-xl shadow-2xl border overflow-hidden z-50">
      <div className="flex items-center justify-between p-4 border-b">
        <h3 className="font-bold">알림</h3>
        <button onClick={onMarkAllRead} className="text-sm text-blue-600 hover:underline">
          모두 읽음
        </button>
      </div>

      <div className="max-h-96 overflow-y-auto">
        {notifications.length === 0 ? (
          <div className="p-8 text-center text-gray-400">알림이 없습니다</div>
        ) : (
          notifications.map((n) => (
            <div
              key={n.id}
              onClick={() => onMarkRead(n.id)}
              className={`flex gap-3 p-4 border-b cursor-pointer hover:bg-gray-50 transition ${
                !n.read ? "bg-blue-50/50" : ""
              }`}
            >
              <span className="text-xl">{typeIcons[n.type] || "🔔"}</span>
              <div className="flex-1 min-w-0">
                <p className={`text-sm ${!n.read ? "font-semibold" : "text-gray-600"}`}>{n.title}</p>
                <p className="text-xs text-gray-400 truncate">{n.message}</p>
                <p className="text-xs text-gray-300 mt-1">
                  {new Date(n.createdAt).toLocaleString("ko-KR")}
                </p>
              </div>
              {!n.read && <div className="w-2 h-2 bg-blue-500 rounded-full mt-2" />}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
```

Socket.IO 실시간 알림! 벨 아이콘 + 드롭다운 + 토스트 + REST API 연동!'''),

m("WebSocket으로 실시간 협업 문서 편집기 만들어줘",
'''실시간 협업 문서 편집기를 만들어 드릴게요.

## 폴더 구조

```
collab-editor/
├── server/
│   ├── index.ts
│   ├── document-store.ts
│   └── types.ts
├── client/
│   ├── components/
│   │   ├── editor.tsx
│   │   ├── cursor-overlay.tsx
│   │   ├── user-presence.tsx
│   │   └── document-list.tsx
│   └── hooks/
│       └── use-collab.ts
├── package.json
└── tsconfig.json
```

## server/types.ts

```typescript
export interface Document {
  id: string;
  title: string;
  content: string;
  version: number;
  lastModified: number;
}

export interface CursorPosition {
  userId: string;
  userName: string;
  color: string;
  line: number;
  column: number;
}

export interface EditOperation {
  type: "insert" | "delete" | "replace";
  position: number;
  text?: string;
  length?: number;
  userId: string;
  version: number;
}
```

## server/document-store.ts

```typescript
import { Document, EditOperation } from "./types";

export class DocumentStore {
  private documents = new Map<string, Document>();

  constructor() {
    this.create("welcome", "환영합니다", "# 화랑 협업 에디터\\n\\n여러 사용자가 동시에 편집할 수 있습니다.\\n\\n자유롭게 작성해보세요!");
  }

  create(id: string, title: string, content = ""): Document {
    const doc: Document = { id, title, content, version: 0, lastModified: Date.now() };
    this.documents.set(id, doc);
    return doc;
  }

  get(id: string): Document | undefined {
    return this.documents.get(id);
  }

  list(): { id: string; title: string; lastModified: number }[] {
    return Array.from(this.documents.values()).map((d) => ({
      id: d.id,
      title: d.title,
      lastModified: d.lastModified,
    }));
  }

  applyOperation(docId: string, op: EditOperation): Document | null {
    const doc = this.documents.get(docId);
    if (!doc) return null;

    switch (op.type) {
      case "insert":
        doc.content =
          doc.content.slice(0, op.position) + (op.text || "") + doc.content.slice(op.position);
        break;
      case "delete":
        doc.content =
          doc.content.slice(0, op.position) + doc.content.slice(op.position + (op.length || 0));
        break;
      case "replace":
        doc.content = op.text || "";
        break;
    }

    doc.version++;
    doc.lastModified = Date.now();
    return doc;
  }

  updateContent(docId: string, content: string): Document | null {
    const doc = this.documents.get(docId);
    if (!doc) return null;
    doc.content = content;
    doc.version++;
    doc.lastModified = Date.now();
    return doc;
  }
}
```

## server/index.ts

```typescript
import express from "express";
import { createServer } from "http";
import { Server } from "socket.io";
import { DocumentStore } from "./document-store";
import { CursorPosition } from "./types";

const app = express();
const server = createServer(app);
const io = new Server(server, { cors: { origin: "*" } });

const store = new DocumentStore();
const COLORS = ["#ef4444", "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899"];
let colorIndex = 0;

io.on("connection", (socket) => {
  const userName = (socket.handshake.query.name as string) || "익명";
  const userColor = COLORS[colorIndex++ % COLORS.length];
  let currentDocId: string | null = null;

  console.log(`접속: ${userName}`);

  // 문서 목록
  socket.emit("documents", store.list());

  // 문서 열기
  socket.on("open-document", (docId: string) => {
    if (currentDocId) socket.leave(`doc:${currentDocId}`);

    currentDocId = docId;
    socket.join(`doc:${docId}`);

    const doc = store.get(docId);
    if (doc) {
      socket.emit("document-content", doc);
    }

    // 접속 알림
    socket.to(`doc:${docId}`).emit("user-joined", { id: socket.id, name: userName, color: userColor });
  });

  // 내용 변경
  socket.on("content-change", (data: { content: string; docId: string }) => {
    const doc = store.updateContent(data.docId, data.content);
    if (doc) {
      socket.to(`doc:${data.docId}`).emit("remote-change", {
        content: data.content,
        userId: socket.id,
        version: doc.version,
      });
    }
  });

  // 커서 이동
  socket.on("cursor-move", (cursor: { line: number; column: number }) => {
    if (!currentDocId) return;
    const pos: CursorPosition = {
      userId: socket.id,
      userName,
      color: userColor,
      ...cursor,
    };
    socket.to(`doc:${currentDocId}`).emit("remote-cursor", pos);
  });

  // 새 문서 생성
  socket.on("create-document", (title: string, callback: Function) => {
    const id = `doc_${Date.now()}`;
    const doc = store.create(id, title);
    io.emit("documents", store.list());
    callback(doc);
  });

  socket.on("disconnect", () => {
    if (currentDocId) {
      socket.to(`doc:${currentDocId}`).emit("user-left", socket.id);
    }
  });
});

server.listen(3002, () => console.log("협업 에디터 서버: http://localhost:3002"));
```

## client/hooks/use-collab.ts

```typescript
import { useEffect, useState, useRef, useCallback } from "react";
import { io, Socket } from "socket.io-client";

interface CursorPosition {
  userId: string;
  userName: string;
  color: string;
  line: number;
  column: number;
}

interface Document {
  id: string;
  title: string;
  content: string;
  version: number;
}

export function useCollab(userName: string) {
  const socketRef = useRef<Socket | null>(null);
  const [documents, setDocuments] = useState<{ id: string; title: string }[]>([]);
  const [currentDoc, setCurrentDoc] = useState<Document | null>(null);
  const [cursors, setCursors] = useState<Map<string, CursorPosition>>(new Map());
  const [users, setUsers] = useState<{ id: string; name: string; color: string }[]>([]);

  useEffect(() => {
    const s = io("http://localhost:3002", { query: { name: userName } });
    socketRef.current = s;

    s.on("documents", setDocuments);

    s.on("document-content", (doc: Document) => {
      setCurrentDoc(doc);
    });

    s.on("remote-change", (data: { content: string; userId: string }) => {
      setCurrentDoc((prev) => prev ? { ...prev, content: data.content } : null);
    });

    s.on("remote-cursor", (cursor: CursorPosition) => {
      setCursors((prev) => new Map(prev).set(cursor.userId, cursor));
    });

    s.on("user-joined", (user: { id: string; name: string; color: string }) => {
      setUsers((prev) => [...prev.filter((u) => u.id !== user.id), user]);
    });

    s.on("user-left", (userId: string) => {
      setUsers((prev) => prev.filter((u) => u.id !== userId));
      setCursors((prev) => { const m = new Map(prev); m.delete(userId); return m; });
    });

    return () => { s.disconnect(); };
  }, [userName]);

  const openDocument = useCallback((docId: string) => {
    socketRef.current?.emit("open-document", docId);
  }, []);

  const updateContent = useCallback((content: string) => {
    if (!currentDoc) return;
    setCurrentDoc((prev) => prev ? { ...prev, content } : null);
    socketRef.current?.emit("content-change", { content, docId: currentDoc.id });
  }, [currentDoc]);

  const moveCursor = useCallback((line: number, column: number) => {
    socketRef.current?.emit("cursor-move", { line, column });
  }, []);

  const createDocument = useCallback((title: string) => {
    return new Promise<Document>((resolve) => {
      socketRef.current?.emit("create-document", title, resolve);
    });
  }, []);

  return { documents, currentDoc, cursors, users, openDocument, updateContent, moveCursor, createDocument };
}
```

## client/components/editor.tsx

```tsx
"use client";

import { useRef, useCallback } from "react";

interface EditorProps {
  content: string;
  onChange: (content: string) => void;
  onCursorMove: (line: number, column: number) => void;
}

export function Editor({ content, onChange, onCursorMove }: EditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onChange(e.target.value);
    },
    [onChange]
  );

  const handleSelect = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;

    const pos = el.selectionStart;
    const lines = el.value.substring(0, pos).split("\\n");
    const line = lines.length;
    const column = lines[lines.length - 1].length + 1;

    onCursorMove(line, column);
  }, [onCursorMove]);

  return (
    <div className="flex-1 relative">
      <textarea
        ref={textareaRef}
        value={content}
        onChange={handleChange}
        onSelect={handleSelect}
        onClick={handleSelect}
        onKeyUp={handleSelect}
        className="w-full h-full p-6 font-mono text-sm leading-relaxed resize-none outline-none bg-gray-900 text-gray-100"
        spellCheck={false}
      />
    </div>
  );
}
```

## client/components/user-presence.tsx

```tsx
interface User {
  id: string;
  name: string;
  color: string;
}

export function UserPresence({ users }: { users: User[] }) {
  return (
    <div className="flex items-center gap-1">
      {users.map((user) => (
        <div
          key={user.id}
          title={user.name}
          className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold border-2 border-white"
          style={{ backgroundColor: user.color }}
        >
          {user.name[0]}
        </div>
      ))}
      {users.length > 0 && (
        <span className="text-xs text-gray-400 ml-1">{users.length}명 접속중</span>
      )}
    </div>
  );
}
```

실시간 협업 에디터! 다중 커서 + 접속자 표시 + 문서 관리!'''),

# ════════════════════════════════════════════
# 3. 관리자 대시보드
# ════════════════════════════════════════════

m("React + Tailwind로 관리자 대시보드 만들어줘 전체 코드로",
'''관리자 대시보드를 만들어 드릴게요.

## 폴더 구조

```
admin-dashboard/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── users/page.tsx
│   ├── orders/page.tsx
│   └── analytics/page.tsx
├── components/
│   ├── layout/
│   │   ├── sidebar.tsx
│   │   ├── topbar.tsx
│   │   └── breadcrumb.tsx
│   ├── dashboard/
│   │   ├── stat-card.tsx
│   │   ├── chart-card.tsx
│   │   ├── recent-orders.tsx
│   │   └── top-products.tsx
│   ├── ui/
│   │   ├── data-table.tsx
│   │   ├── badge.tsx
│   │   ├── pagination.tsx
│   │   └── modal.tsx
│   └── charts/
│       ├── line-chart.tsx
│       └── bar-chart.tsx
├── lib/
│   ├── utils.ts
│   └── mock-data.ts
├── package.json
└── tailwind.config.ts
```

## components/layout/sidebar.tsx

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const MENU = [
  { href: "/", icon: "📊", label: "대시보드" },
  { href: "/users", icon: "👥", label: "사용자" },
  { href: "/orders", icon: "📦", label: "주문" },
  { href: "/analytics", icon: "📈", label: "분석" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-gray-900 text-white min-h-screen p-4 flex flex-col">
      <div className="text-xl font-bold px-4 py-6">
        ⚡ 화랑 Admin
      </div>

      <nav className="flex-1 space-y-1">
        {MENU.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition ${
                active
                  ? "bg-blue-600 text-white font-medium"
                  : "text-gray-400 hover:bg-gray-800 hover:text-white"
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-4 border-t border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-blue-600 rounded-full flex items-center justify-center text-sm font-bold">
            관
          </div>
          <div>
            <p className="text-sm font-medium">관리자</p>
            <p className="text-xs text-gray-500">admin@hwarang.ai</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
```

## components/layout/topbar.tsx

```tsx
export function Topbar({ title }: { title: string }) {
  return (
    <header className="h-16 border-b bg-white px-6 flex items-center justify-between">
      <h1 className="text-lg font-bold text-gray-900">{title}</h1>
      <div className="flex items-center gap-4">
        <button className="relative p-2 rounded-lg hover:bg-gray-100">
          🔔
          <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" />
        </button>
        <input
          type="search"
          placeholder="검색..."
          className="px-4 py-2 bg-gray-50 border border-gray-200 rounded-xl text-sm outline-none focus:border-blue-500 w-64"
        />
      </div>
    </header>
  );
}
```

## components/dashboard/stat-card.tsx

```tsx
interface StatCardProps {
  title: string;
  value: string;
  change: number;
  icon: string;
}

export function StatCard({ title, value, change, icon }: StatCardProps) {
  const isPositive = change >= 0;

  return (
    <div className="bg-white p-6 rounded-2xl border border-gray-100">
      <div className="flex items-center justify-between mb-4">
        <span className="text-2xl">{icon}</span>
        <span
          className={`text-sm font-medium px-2 py-0.5 rounded-full ${
            isPositive ? "bg-green-50 text-green-600" : "bg-red-50 text-red-600"
          }`}
        >
          {isPositive ? "+" : ""}{change}%
        </span>
      </div>
      <p className="text-sm text-gray-500 mb-1">{title}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
```

## components/dashboard/recent-orders.tsx

```tsx
interface Order {
  id: string;
  customer: string;
  product: string;
  amount: number;
  status: "pending" | "confirmed" | "shipped" | "delivered";
  date: string;
}

const STATUS_MAP = {
  pending: { label: "대기", color: "bg-yellow-50 text-yellow-700" },
  confirmed: { label: "확인", color: "bg-blue-50 text-blue-700" },
  shipped: { label: "배송중", color: "bg-purple-50 text-purple-700" },
  delivered: { label: "완료", color: "bg-green-50 text-green-700" },
};

export function RecentOrders({ orders }: { orders: Order[] }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
      <div className="p-6 border-b">
        <h2 className="font-bold text-gray-900">최근 주문</h2>
      </div>
      <table className="w-full">
        <thead>
          <tr className="bg-gray-50 text-left text-sm text-gray-500">
            <th className="px-6 py-3">주문번호</th>
            <th className="px-6 py-3">고객</th>
            <th className="px-6 py-3">상품</th>
            <th className="px-6 py-3">금액</th>
            <th className="px-6 py-3">상태</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.id} className="border-t hover:bg-gray-50 transition">
              <td className="px-6 py-4 text-sm font-mono">{order.id}</td>
              <td className="px-6 py-4 text-sm">{order.customer}</td>
              <td className="px-6 py-4 text-sm">{order.product}</td>
              <td className="px-6 py-4 text-sm font-medium">
                {order.amount.toLocaleString()}원
              </td>
              <td className="px-6 py-4">
                <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${STATUS_MAP[order.status].color}`}>
                  {STATUS_MAP[order.status].label}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

## components/ui/data-table.tsx

```tsx
"use client";

import { useState, useMemo } from "react";

interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
  sortable?: boolean;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  pageSize?: number;
  searchable?: boolean;
  searchKeys?: string[];
}

export function DataTable<T extends Record<string, any>>({
  data,
  columns,
  pageSize = 10,
  searchable = true,
  searchKeys = [],
}: DataTableProps<T>) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const filtered = useMemo(() => {
    let result = data;

    if (search && searchKeys.length) {
      const q = search.toLowerCase();
      result = result.filter((row) =>
        searchKeys.some((key) => String(row[key]).toLowerCase().includes(q))
      );
    }

    if (sortKey) {
      result = [...result].sort((a, b) => {
        const av = a[sortKey], bv = b[sortKey];
        const cmp = av < bv ? -1 : av > bv ? 1 : 0;
        return sortDir === "asc" ? cmp : -cmp;
      });
    }

    return result;
  }, [data, search, searchKeys, sortKey, sortDir]);

  const totalPages = Math.ceil(filtered.length / pageSize);
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  return (
    <div className="bg-white rounded-2xl border overflow-hidden">
      {searchable && (
        <div className="p-4 border-b">
          <input
            type="search"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder="검색..."
            className="px-4 py-2 border rounded-xl w-64 outline-none focus:border-blue-500 text-sm"
          />
        </div>
      )}

      <table className="w-full">
        <thead>
          <tr className="bg-gray-50 text-left text-sm text-gray-500">
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => col.sortable && handleSort(col.key)}
                className={`px-6 py-3 ${col.sortable ? "cursor-pointer hover:text-gray-700" : ""}`}
              >
                {col.label}
                {sortKey === col.key && (sortDir === "asc" ? " ↑" : " ↓")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {paged.map((row, i) => (
            <tr key={i} className="border-t hover:bg-gray-50 transition">
              {columns.map((col) => (
                <td key={col.key} className="px-6 py-4 text-sm">
                  {col.render ? col.render(row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className="flex items-center justify-between px-6 py-4 border-t text-sm">
          <span className="text-gray-500">
            {filtered.length}건 중 {(page - 1) * pageSize + 1}-{Math.min(page * pageSize, filtered.length)}
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 rounded-lg border disabled:opacity-50 hover:bg-gray-50"
            >
              이전
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((p) => Math.abs(p - page) <= 2)
              .map((p) => (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={`px-3 py-1 rounded-lg ${
                    p === page ? "bg-blue-600 text-white" : "border hover:bg-gray-50"
                  }`}
                >
                  {p}
                </button>
              ))}
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1 rounded-lg border disabled:opacity-50 hover:bg-gray-50"
            >
              다음
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

## components/ui/modal.tsx

```tsx
"use client";

import { useEffect, useRef } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export function Modal({ open, onClose, title, children }: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (open) document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      onClick={(e) => e.target === overlayRef.current && onClose()}
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
    >
      <div className="bg-white rounded-2xl w-full max-w-lg shadow-xl">
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-lg font-bold">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}
```

## app/page.tsx

```tsx
import { StatCard } from "@/components/dashboard/stat-card";
import { RecentOrders } from "@/components/dashboard/recent-orders";

const STATS = [
  { title: "총 매출", value: "₩12,450,000", change: 12.5, icon: "💰" },
  { title: "주문 수", value: "1,234", change: 8.2, icon: "📦" },
  { title: "신규 사용자", value: "456", change: -3.1, icon: "👥" },
  { title: "전환율", value: "3.2%", change: 0.8, icon: "📈" },
];

const ORDERS = [
  { id: "ORD-001", customer: "홍길동", product: "맥북 프로", amount: 2490000, status: "shipped" as const, date: "2025-01-15" },
  { id: "ORD-002", customer: "김철수", product: "아이패드", amount: 899000, status: "confirmed" as const, date: "2025-01-15" },
  { id: "ORD-003", customer: "이영희", product: "에어팟", amount: 249000, status: "pending" as const, date: "2025-01-14" },
  { id: "ORD-004", customer: "박민수", product: "맥 미니", amount: 990000, status: "delivered" as const, date: "2025-01-14" },
  { id: "ORD-005", customer: "최유진", product: "매직 키보드", amount: 159000, status: "pending" as const, date: "2025-01-13" },
];

export default function Dashboard() {
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-4 gap-6">
        {STATS.map((stat) => (
          <StatCard key={stat.title} {...stat} />
        ))}
      </div>
      <RecentOrders orders={ORDERS} />
    </div>
  );
}
```

## app/layout.tsx

```tsx
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="bg-gray-50">
        <div className="flex">
          <Sidebar />
          <div className="flex-1 flex flex-col">
            <Topbar title="대시보드" />
            <main className="p-6 flex-1">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
```

## package.json

```json
{
  "name": "admin-dashboard",
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build"
  },
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "@types/react": "^19.0.0",
    "tailwindcss": "^4.0.0"
  }
}
```

관리자 대시보드! 사이드바 + 통계카드 + 주문테이블 + 범용 DataTable + 모달!'''),

m("React로 사용자 관리 CRUD 페이지 만들어줘 전체 코드로",
'''사용자 관리 CRUD 페이지를 만들어 드릴게요.

## 폴더 구조

```
user-management/
├── app/
│   ├── users/
│   │   └── page.tsx
│   └── api/users/
│       ├── route.ts
│       └── [id]/route.ts
├── components/
│   ├── user-table.tsx
│   ├── user-form-modal.tsx
│   ├── delete-confirm-modal.tsx
│   └── user-filters.tsx
├── lib/
│   ├── db.ts
│   └── types.ts
└── package.json
```

## lib/types.ts

```typescript
export interface User {
  id: string;
  name: string;
  email: string;
  role: "admin" | "editor" | "viewer";
  status: "active" | "inactive" | "banned";
  createdAt: string;
}

export type UserCreate = Omit<User, "id" | "createdAt">;
export type UserUpdate = Partial<UserCreate>;
```

## components/user-table.tsx

```tsx
"use client";

import { User } from "@/lib/types";

interface UserTableProps {
  users: User[];
  onEdit: (user: User) => void;
  onDelete: (user: User) => void;
}

const ROLE_BADGE: Record<string, string> = {
  admin: "bg-purple-50 text-purple-700",
  editor: "bg-blue-50 text-blue-700",
  viewer: "bg-gray-50 text-gray-700",
};

const STATUS_BADGE: Record<string, string> = {
  active: "bg-green-50 text-green-700",
  inactive: "bg-yellow-50 text-yellow-700",
  banned: "bg-red-50 text-red-700",
};

const ROLE_LABEL: Record<string, string> = { admin: "관리자", editor: "편집자", viewer: "뷰어" };
const STATUS_LABEL: Record<string, string> = { active: "활성", inactive: "비활성", banned: "차단" };

export function UserTable({ users, onEdit, onDelete }: UserTableProps) {
  return (
    <div className="bg-white rounded-2xl border overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="bg-gray-50 text-left text-sm text-gray-500">
            <th className="px-6 py-3">이름</th>
            <th className="px-6 py-3">이메일</th>
            <th className="px-6 py-3">역할</th>
            <th className="px-6 py-3">상태</th>
            <th className="px-6 py-3">가입일</th>
            <th className="px-6 py-3">액션</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id} className="border-t hover:bg-gray-50 transition">
              <td className="px-6 py-4 font-medium">{user.name}</td>
              <td className="px-6 py-4 text-sm text-gray-500">{user.email}</td>
              <td className="px-6 py-4">
                <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${ROLE_BADGE[user.role]}`}>
                  {ROLE_LABEL[user.role]}
                </span>
              </td>
              <td className="px-6 py-4">
                <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${STATUS_BADGE[user.status]}`}>
                  {STATUS_LABEL[user.status]}
                </span>
              </td>
              <td className="px-6 py-4 text-sm text-gray-500">
                {new Date(user.createdAt).toLocaleDateString("ko-KR")}
              </td>
              <td className="px-6 py-4">
                <div className="flex gap-2">
                  <button onClick={() => onEdit(user)} className="text-sm text-blue-600 hover:underline">
                    수정
                  </button>
                  <button onClick={() => onDelete(user)} className="text-sm text-red-500 hover:underline">
                    삭제
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

## components/user-form-modal.tsx

```tsx
"use client";

import { useState, useEffect } from "react";
import { User, UserCreate } from "@/lib/types";

interface UserFormModalProps {
  open: boolean;
  user?: User | null;
  onClose: () => void;
  onSubmit: (data: UserCreate) => void;
}

export function UserFormModal({ open, user, onClose, onSubmit }: UserFormModalProps) {
  const [form, setForm] = useState<UserCreate>({
    name: "",
    email: "",
    role: "viewer",
    status: "active",
  });

  useEffect(() => {
    if (user) {
      setForm({ name: user.name, email: user.email, role: user.role, status: user.status });
    } else {
      setForm({ name: "", email: "", role: "viewer", status: "active" });
    }
  }, [user, open]);

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(form);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl w-full max-w-md shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-lg font-bold">{user ? "사용자 수정" : "사용자 추가"}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">이름</label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="w-full px-4 py-2 border rounded-xl outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">이메일</label>
            <input
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              className="w-full px-4 py-2 border rounded-xl outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">역할</label>
            <select
              value={form.role}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value as any }))}
              className="w-full px-4 py-2 border rounded-xl outline-none focus:border-blue-500"
            >
              <option value="admin">관리자</option>
              <option value="editor">편집자</option>
              <option value="viewer">뷰어</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">상태</label>
            <select
              value={form.status}
              onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as any }))}
              className="w-full px-4 py-2 border rounded-xl outline-none focus:border-blue-500"
            >
              <option value="active">활성</option>
              <option value="inactive">비활성</option>
              <option value="banned">차단</option>
            </select>
          </div>

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 py-3 border rounded-xl font-medium hover:bg-gray-50">
              취소
            </button>
            <button type="submit" className="flex-1 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700">
              {user ? "수정" : "추가"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

## components/delete-confirm-modal.tsx

```tsx
"use client";

interface DeleteConfirmProps {
  open: boolean;
  name: string;
  onClose: () => void;
  onConfirm: () => void;
}

export function DeleteConfirmModal({ open, name, onClose, onConfirm }: DeleteConfirmProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl p-6 text-center">
        <div className="text-4xl mb-4">⚠️</div>
        <h2 className="text-lg font-bold mb-2">삭제 확인</h2>
        <p className="text-gray-500 mb-6">
          <strong>{name}</strong>을(를) 삭제하시겠습니까?<br />
          이 작업은 되돌릴 수 없습니다.
        </p>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 py-3 border rounded-xl font-medium hover:bg-gray-50">
            취소
          </button>
          <button onClick={onConfirm} className="flex-1 py-3 bg-red-600 text-white rounded-xl font-medium hover:bg-red-700">
            삭제
          </button>
        </div>
      </div>
    </div>
  );
}
```

## app/users/page.tsx

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { UserTable } from "@/components/user-table";
import { UserFormModal } from "@/components/user-form-modal";
import { DeleteConfirmModal } from "@/components/delete-confirm-modal";
import { User, UserCreate } from "@/lib/types";

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [deleting, setDeleting] = useState<User | null>(null);

  const fetchUsers = useCallback(async () => {
    const res = await fetch("/api/users");
    setUsers(await res.json());
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleCreate = () => { setEditing(null); setFormOpen(true); };

  const handleEdit = (user: User) => { setEditing(user); setFormOpen(true); };

  const handleDelete = (user: User) => { setDeleting(user); setDeleteOpen(true); };

  const handleSubmit = async (data: UserCreate) => {
    if (editing) {
      await fetch(`/api/users/${editing.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
    } else {
      await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
    }
    setFormOpen(false);
    fetchUsers();
  };

  const handleConfirmDelete = async () => {
    if (!deleting) return;
    await fetch(`/api/users/${deleting.id}`, { method: "DELETE" });
    setDeleteOpen(false);
    setDeleting(null);
    fetchUsers();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">사용자 관리</h1>
        <button
          onClick={handleCreate}
          className="px-4 py-2 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700"
        >
          + 사용자 추가
        </button>
      </div>

      <UserTable users={users} onEdit={handleEdit} onDelete={handleDelete} />

      <UserFormModal
        open={formOpen}
        user={editing}
        onClose={() => setFormOpen(false)}
        onSubmit={handleSubmit}
      />

      <DeleteConfirmModal
        open={deleteOpen}
        name={deleting?.name || ""}
        onClose={() => setDeleteOpen(false)}
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}
```

완전한 사용자 CRUD! 테이블 + 폼 모달 + 삭제 확인 + 역할/상태 뱃지!'''),

# ════════════════════════════════════════════
# 4. React 컴포넌트 라이브러리
# ════════════════════════════════════════════

m("React + TypeScript 컴포넌트 라이브러리 만들어줘 Button, Input, Select, Toast 전체 코드로",
'''React UI 컴포넌트 라이브러리를 만들어 드릴게요.

## 폴더 구조

```
hwarang-ui/
├── src/
│   ├── index.ts
│   ├── components/
│   │   ├── button.tsx
│   │   ├── input.tsx
│   │   ├── select.tsx
│   │   ├── toast/
│   │   │   ├── toast.tsx
│   │   │   ├── toast-provider.tsx
│   │   │   └── use-toast.ts
│   │   └── index.ts
│   └── utils/
│       └── cn.ts
├── package.json
└── tsconfig.json
```

## src/utils/cn.ts

```typescript
type ClassValue = string | false | undefined | null;

export function cn(...classes: ClassValue[]): string {
  return classes.filter(Boolean).join(" ");
}
```

## src/components/button.tsx

```tsx
import { forwardRef, ButtonHTMLAttributes } from "react";
import { cn } from "../utils/cn";

type Variant = "primary" | "secondary" | "outline" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: React.ReactNode;
}

const variantStyles: Record<Variant, string> = {
  primary: "bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800",
  secondary: "bg-gray-100 text-gray-900 hover:bg-gray-200 active:bg-gray-300",
  outline: "border border-gray-300 text-gray-700 hover:bg-gray-50 active:bg-gray-100",
  ghost: "text-gray-700 hover:bg-gray-100 active:bg-gray-200",
  danger: "bg-red-600 text-white hover:bg-red-700 active:bg-red-800",
};

const sizeStyles: Record<Size, string> = {
  sm: "h-8 px-3 text-sm gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-12 px-6 text-base gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading, icon, disabled, children, className, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center rounded-xl font-medium transition-colors",
          "disabled:opacity-50 disabled:pointer-events-none",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      >
        {loading && (
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        )}
        {!loading && icon}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
```

## src/components/input.tsx

```tsx
import { forwardRef, InputHTMLAttributes } from "react";
import { cn } from "../utils/cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  icon?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, icon, className, ...props }, ref) => {
    return (
      <div className="space-y-1.5">
        {label && (
          <label className="block text-sm font-medium text-gray-700">
            {label}
            {props.required && <span className="text-red-500 ml-0.5">*</span>}
          </label>
        )}

        <div className="relative">
          {icon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
              {icon}
            </div>
          )}

          <input
            ref={ref}
            className={cn(
              "w-full px-4 py-2.5 border rounded-xl text-sm transition-colors outline-none",
              "placeholder:text-gray-400",
              "focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20",
              error ? "border-red-500 focus:border-red-500 focus:ring-red-500/20" : "border-gray-300",
              icon && "pl-10",
              className
            )}
            {...props}
          />
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}
        {hint && !error && <p className="text-sm text-gray-400">{hint}</p>}
      </div>
    );
  }
);

Input.displayName = "Input";
```

## src/components/select.tsx

```tsx
import { forwardRef, SelectHTMLAttributes } from "react";
import { cn } from "../utils/cn";

interface Option {
  value: string;
  label: string;
  disabled?: boolean;
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  label?: string;
  error?: string;
  options: Option[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, options, placeholder, className, ...props }, ref) => {
    return (
      <div className="space-y-1.5">
        {label && (
          <label className="block text-sm font-medium text-gray-700">
            {label}
            {props.required && <span className="text-red-500 ml-0.5">*</span>}
          </label>
        )}

        <select
          ref={ref}
          className={cn(
            "w-full px-4 py-2.5 border rounded-xl text-sm transition-colors outline-none appearance-none",
            "bg-white bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2220%22%20height%3D%2220%22%20viewBox%3D%220%200%2020%2020%22%20fill%3D%22%236b7280%22%3E%3Cpath%20d%3D%22M7%207l3%203%203-3%22%20stroke%3D%22%236b7280%22%20stroke-width%3D%221.5%22%20fill%3D%22none%22%20stroke-linecap%3D%22round%22%2F%3E%3C%2Fsvg%3E')] bg-no-repeat bg-[center_right_0.75rem]",
            "focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20",
            error ? "border-red-500" : "border-gray-300",
            className
          )}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>
              {opt.label}
            </option>
          ))}
        </select>

        {error && <p className="text-sm text-red-500">{error}</p>}
      </div>
    );
  }
);

Select.displayName = "Select";
```

## src/components/toast/use-toast.ts

```typescript
import { useState, useCallback, useRef } from "react";

export type ToastType = "success" | "error" | "warning" | "info";

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
}

let toastId = 0;

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const addToast = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = `toast-${++toastId}`;
      const newToast = { ...toast, id };
      setToasts((prev) => [...prev, newToast]);

      const duration = toast.duration ?? 4000;
      if (duration > 0) {
        const timer = setTimeout(() => removeToast(id), duration);
        timersRef.current.set(id, timer);
      }

      return id;
    },
    [removeToast]
  );

  const toast = {
    success: (title: string, message?: string) => addToast({ type: "success", title, message }),
    error: (title: string, message?: string) => addToast({ type: "error", title, message }),
    warning: (title: string, message?: string) => addToast({ type: "warning", title, message }),
    info: (title: string, message?: string) => addToast({ type: "info", title, message }),
  };

  return { toasts, toast, removeToast };
}
```

## src/components/toast/toast.tsx

```tsx
import { Toast as ToastType } from "./use-toast";
import { cn } from "../../utils/cn";

const typeStyles: Record<string, { bg: string; icon: string }> = {
  success: { bg: "bg-green-50 border-green-200", icon: "✅" },
  error: { bg: "bg-red-50 border-red-200", icon: "❌" },
  warning: { bg: "bg-yellow-50 border-yellow-200", icon: "⚠️" },
  info: { bg: "bg-blue-50 border-blue-200", icon: "ℹ️" },
};

interface ToastProps {
  toast: ToastType;
  onDismiss: (id: string) => void;
}

export function ToastItem({ toast, onDismiss }: ToastProps) {
  const style = typeStyles[toast.type];

  return (
    <div
      className={cn(
        "flex items-start gap-3 p-4 rounded-xl border shadow-lg animate-slide-in max-w-sm",
        style.bg
      )}
    >
      <span className="text-lg">{style.icon}</span>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-sm text-gray-900">{toast.title}</p>
        {toast.message && <p className="text-sm text-gray-600 mt-0.5">{toast.message}</p>}
      </div>
      <button onClick={() => onDismiss(toast.id)} className="text-gray-400 hover:text-gray-600 text-sm">
        ✕
      </button>
    </div>
  );
}
```

## src/components/toast/toast-provider.tsx

```tsx
"use client";

import { createContext, useContext, ReactNode } from "react";
import { useToast, Toast } from "./use-toast";
import { ToastItem } from "./toast";

interface ToastContextValue {
  toast: ReturnType<typeof useToast>["toast"];
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const { toasts, toast, removeToast } = useToast();

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 space-y-2">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToastContext() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("ToastProvider 내부에서 사용해주세요");
  return ctx;
}
```

## src/components/index.ts

```typescript
export { Button } from "./button";
export { Input } from "./input";
export { Select } from "./select";
export { ToastProvider, useToastContext } from "./toast/toast-provider";
export type { Toast, ToastType } from "./toast/use-toast";
```

## src/index.ts

```typescript
export * from "./components";
export { cn } from "./utils/cn";
```

## package.json

```json
{
  "name": "@hwarang/ui",
  "version": "1.0.0",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "peerDependencies": {
    "react": ">=18",
    "react-dom": ">=18"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "@types/react": "^19.0.0"
  }
}
```

## 사용 예시

```tsx
import { Button, Input, Select, ToastProvider, useToastContext } from "@hwarang/ui";

function App() {
  const { toast } = useToastContext();

  return (
    <div className="space-y-4 p-8">
      <Input label="이름" placeholder="홍길동" required />
      <Input label="이메일" type="email" error="올바른 이메일을 입력하세요" />

      <Select
        label="역할"
        placeholder="선택하세요"
        options={[
          { value: "admin", label: "관리자" },
          { value: "user", label: "사용자" },
        ]}
      />

      <div className="flex gap-2">
        <Button onClick={() => toast.success("저장 완료!")}>저장</Button>
        <Button variant="outline">취소</Button>
        <Button variant="danger" onClick={() => toast.error("삭제됨", "되돌릴 수 없습니다")}>삭제</Button>
        <Button loading>처리중</Button>
      </div>
    </div>
  );
}

// App을 ToastProvider로 감싸기
<ToastProvider><App /></ToastProvider>
```

완전한 UI 라이브러리! Button(5 variant) + Input(아이콘/에러) + Select + Toast 시스템!'''),

# ════════════════════════════════════════════
# 5. Docker + CI/CD
# ════════════════════════════════════════════

m("Docker + Docker Compose + CI/CD로 Next.js 앱 배포 구성 만들어줘 전체 코드로",
'''Next.js 앱 Docker 배포 전체 구성을 만들어 드릴게요.

## 폴더 구조

```
deploy-setup/
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── .dockerignore
├── nginx/
│   ├── nginx.conf
│   └── default.conf
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── scripts/
│   ├── deploy.sh
│   └── health-check.sh
└── .env.example
```

## Dockerfile

```dockerfile
# ═══ 1단계: 의존성 설치 ═══
FROM node:22-alpine AS deps
WORKDIR /app

# pnpm 설치
RUN corepack enable && corepack prepare pnpm@latest --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# ═══ 2단계: 빌드 ═══
FROM node:22-alpine AS builder
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@latest --activate

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Prisma 생성
RUN npx prisma generate

# 빌드
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ═══ 3단계: 프로덕션 ═══
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# 보안: 비루트 사용자
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# 필요한 파일만 복사
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/node_modules/.prisma ./node_modules/.prisma

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# 헬스체크
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1

CMD ["node", "server.js"]
```

## docker-compose.yml

```yaml
version: "3.9"

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/myapp
      - REDIS_URL=redis://redis:6379
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: myapp
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

## docker-compose.prod.yml

```yaml
version: "3.9"

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - NODE_ENV=production
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: always
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 512M
          cpus: "0.5"

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
      - ./certbot/conf:/etc/letsencrypt:ro
    depends_on:
      - app
    restart: always

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: always

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: always

volumes:
  postgres_data:
  redis_data:
```

## nginx/nginx.conf

```nginx
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # 로그
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent"';
    access_log /var/log/nginx/access.log main;

    # 성능
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;

    # 보안
    server_tokens off;
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    # 업스트림
    upstream app {
        least_conn;
        server app:3000;
    }

    include /etc/nginx/conf.d/*.conf;
}
```

## nginx/default.conf

```nginx
# HTTP → HTTPS 리다이렉트
server {
    listen 80;
    server_name _;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # 정적 파일 캐시
    location /_next/static/ {
        proxy_pass http://app;
        expires 365d;
        add_header Cache-Control "public, immutable";
    }

    # API
    location /api/ {
        proxy_pass http://app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 타임아웃
        proxy_connect_timeout 30s;
        proxy_read_timeout 30s;
    }

    # 기본
    location / {
        proxy_pass http://app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## .github/workflows/ci.yml

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm type-check
      - run: pnpm test
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          tags: myapp:test
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

## .github/workflows/deploy.yml

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Docker 이미지 빌드 & 푸시
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

      # 서버 배포
      - name: Deploy to server
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /app
            docker compose -f docker-compose.prod.yml pull
            docker compose -f docker-compose.prod.yml up -d --remove-orphans
            docker system prune -f
```

## scripts/deploy.sh

```bash
#!/bin/bash
set -euo pipefail

echo "🚀 배포 시작..."

# 이미지 빌드
docker compose -f docker-compose.prod.yml build --no-cache

# DB 마이그레이션
docker compose -f docker-compose.prod.yml run --rm app npx prisma migrate deploy

# 롤링 업데이트
docker compose -f docker-compose.prod.yml up -d --remove-orphans

# 헬스체크
echo "⏳ 헬스체크 대기..."
for i in $(seq 1 30); do
  if curl -sf http://localhost/api/health > /dev/null 2>&1; then
    echo "✅ 배포 성공!"
    exit 0
  fi
  sleep 2
done

echo "❌ 헬스체크 실패!"
docker compose -f docker-compose.prod.yml logs app --tail 50
exit 1
```

## .dockerignore

```
node_modules
.next
.git
*.md
.env*
!.env.example
```

## .env.example

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/myapp
REDIS_URL=redis://localhost:6379
DB_USER=postgres
DB_PASSWORD=change-me
DB_NAME=myapp
REDIS_PASSWORD=change-me
```

멀티스테이지 Docker + Compose(dev/prod) + Nginx + GitHub Actions CI/CD 완전 구성!'''),

# ════════════════════════════════════════════
# 6. 모바일 앱 (React Native)
# ════════════════════════════════════════════

m("React Native + Expo로 할일 앱 만들어줘 전체 코드로",
'''React Native 할일 앱을 만들어 드릴게요.

## 폴더 구조

```
todo-mobile/
├── app/
│   ├── _layout.tsx
│   ├── index.tsx
│   └── (tabs)/
│       ├── _layout.tsx
│       ├── index.tsx
│       └── settings.tsx
├── components/
│   ├── TodoItem.tsx
│   ├── AddTodo.tsx
│   ├── FilterBar.tsx
│   └── EmptyState.tsx
├── store/
│   └── todo-store.ts
├── types/
│   └── index.ts
├── app.json
├── package.json
└── tsconfig.json
```

## types/index.ts

```typescript
export interface Todo {
  id: string;
  title: string;
  completed: boolean;
  priority: "high" | "medium" | "low";
  createdAt: number;
}

export type FilterType = "all" | "active" | "completed";
```

## store/todo-store.ts

```typescript
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Todo, FilterType } from "../types";

interface TodoStore {
  todos: Todo[];
  filter: FilterType;
  addTodo: (title: string, priority: Todo["priority"]) => void;
  toggleTodo: (id: string) => void;
  deleteTodo: (id: string) => void;
  setFilter: (filter: FilterType) => void;
  filtered: () => Todo[];
  stats: () => { total: number; active: number; completed: number };
}

export const useTodoStore = create<TodoStore>()(
  persist(
    (set, get) => ({
      todos: [],
      filter: "all",

      addTodo: (title, priority) =>
        set((state) => ({
          todos: [
            {
              id: Date.now().toString(),
              title,
              completed: false,
              priority,
              createdAt: Date.now(),
            },
            ...state.todos,
          ],
        })),

      toggleTodo: (id) =>
        set((state) => ({
          todos: state.todos.map((t) =>
            t.id === id ? { ...t, completed: !t.completed } : t
          ),
        })),

      deleteTodo: (id) =>
        set((state) => ({
          todos: state.todos.filter((t) => t.id !== id),
        })),

      setFilter: (filter) => set({ filter }),

      filtered: () => {
        const { todos, filter } = get();
        switch (filter) {
          case "active":
            return todos.filter((t) => !t.completed);
          case "completed":
            return todos.filter((t) => t.completed);
          default:
            return todos;
        }
      },

      stats: () => {
        const { todos } = get();
        return {
          total: todos.length,
          active: todos.filter((t) => !t.completed).length,
          completed: todos.filter((t) => t.completed).length,
        };
      },
    }),
    {
      name: "todo-storage",
      storage: createJSONStorage(() => AsyncStorage),
    }
  )
);
```

## components/AddTodo.tsx

```tsx
import { useState } from "react";
import { View, TextInput, TouchableOpacity, Text, StyleSheet } from "react-native";
import { useTodoStore } from "../store/todo-store";
import { Todo } from "../types";

const PRIORITIES: { value: Todo["priority"]; label: string; color: string }[] = [
  { value: "high", label: "높음", color: "#ef4444" },
  { value: "medium", label: "보통", color: "#f59e0b" },
  { value: "low", label: "낮음", color: "#10b981" },
];

export function AddTodo() {
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<Todo["priority"]>("medium");
  const addTodo = useTodoStore((s) => s.addTodo);

  const handleAdd = () => {
    if (!title.trim()) return;
    addTodo(title.trim(), priority);
    setTitle("");
  };

  return (
    <View style={styles.container}>
      <View style={styles.inputRow}>
        <TextInput
          value={title}
          onChangeText={setTitle}
          placeholder="할 일을 입력하세요..."
          placeholderTextColor="#9ca3af"
          style={styles.input}
          onSubmitEditing={handleAdd}
          returnKeyType="done"
        />
        <TouchableOpacity
          onPress={handleAdd}
          style={[styles.addBtn, !title.trim() && styles.addBtnDisabled]}
          disabled={!title.trim()}
        >
          <Text style={styles.addBtnText}>추가</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.priorities}>
        {PRIORITIES.map((p) => (
          <TouchableOpacity
            key={p.value}
            onPress={() => setPriority(p.value)}
            style={[
              styles.priorityBtn,
              priority === p.value && { backgroundColor: p.color + "20", borderColor: p.color },
            ]}
          >
            <View style={[styles.priorityDot, { backgroundColor: p.color }]} />
            <Text style={[styles.priorityText, priority === p.value && { color: p.color }]}>
              {p.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, gap: 12 },
  inputRow: { flexDirection: "row", gap: 8 },
  input: {
    flex: 1, height: 48, paddingHorizontal: 16, backgroundColor: "#f9fafb",
    borderRadius: 12, borderWidth: 1, borderColor: "#e5e7eb", fontSize: 16,
  },
  addBtn: {
    height: 48, paddingHorizontal: 20, backgroundColor: "#3b82f6",
    borderRadius: 12, justifyContent: "center", alignItems: "center",
  },
  addBtnDisabled: { opacity: 0.5 },
  addBtnText: { color: "#fff", fontWeight: "600", fontSize: 15 },
  priorities: { flexDirection: "row", gap: 8 },
  priorityBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20,
    borderWidth: 1, borderColor: "#e5e7eb",
  },
  priorityDot: { width: 8, height: 8, borderRadius: 4 },
  priorityText: { fontSize: 13, color: "#6b7280" },
});
```

## components/TodoItem.tsx

```tsx
import { View, Text, TouchableOpacity, StyleSheet, Animated } from "react-native";
import { useRef } from "react";
import { Todo } from "../types";
import { useTodoStore } from "../store/todo-store";

const PRIORITY_COLORS = { high: "#ef4444", medium: "#f59e0b", low: "#10b981" };

export function TodoItem({ todo }: { todo: Todo }) {
  const { toggleTodo, deleteTodo } = useTodoStore();
  const fadeAnim = useRef(new Animated.Value(1)).current;

  const handleDelete = () => {
    Animated.timing(fadeAnim, {
      toValue: 0,
      duration: 200,
      useNativeDriver: true,
    }).start(() => deleteTodo(todo.id));
  };

  return (
    <Animated.View style={[styles.container, { opacity: fadeAnim }]}>
      <TouchableOpacity onPress={() => toggleTodo(todo.id)} style={styles.checkBtn}>
        <View
          style={[
            styles.checkbox,
            todo.completed && { backgroundColor: "#3b82f6", borderColor: "#3b82f6" },
          ]}
        >
          {todo.completed && <Text style={styles.checkmark}>✓</Text>}
        </View>
      </TouchableOpacity>

      <View style={styles.content}>
        <View style={styles.titleRow}>
          <View style={[styles.priorityDot, { backgroundColor: PRIORITY_COLORS[todo.priority] }]} />
          <Text style={[styles.title, todo.completed && styles.titleCompleted]}>
            {todo.title}
          </Text>
        </View>
        <Text style={styles.date}>
          {new Date(todo.createdAt).toLocaleDateString("ko-KR")}
        </Text>
      </View>

      <TouchableOpacity onPress={handleDelete} style={styles.deleteBtn}>
        <Text style={styles.deleteText}>삭제</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row", alignItems: "center", padding: 16,
    backgroundColor: "#fff", borderRadius: 12, marginHorizontal: 16,
    marginBottom: 8, borderWidth: 1, borderColor: "#f3f4f6",
  },
  checkBtn: { marginRight: 12 },
  checkbox: {
    width: 24, height: 24, borderRadius: 12, borderWidth: 2,
    borderColor: "#d1d5db", justifyContent: "center", alignItems: "center",
  },
  checkmark: { color: "#fff", fontSize: 14, fontWeight: "bold" },
  content: { flex: 1 },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  priorityDot: { width: 6, height: 6, borderRadius: 3 },
  title: { fontSize: 16, color: "#1f2937" },
  titleCompleted: { textDecorationLine: "line-through", color: "#9ca3af" },
  date: { fontSize: 12, color: "#9ca3af", marginTop: 4 },
  deleteBtn: { padding: 8 },
  deleteText: { color: "#ef4444", fontSize: 13 },
});
```

## components/FilterBar.tsx

```tsx
import { View, TouchableOpacity, Text, StyleSheet } from "react-native";
import { useTodoStore } from "../store/todo-store";
import { FilterType } from "../types";

const FILTERS: { value: FilterType; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "active", label: "진행중" },
  { value: "completed", label: "완료" },
];

export function FilterBar() {
  const { filter, setFilter, stats } = useTodoStore();
  const { total, active, completed } = stats();

  const counts: Record<FilterType, number> = { all: total, active, completed };

  return (
    <View style={styles.container}>
      {FILTERS.map((f) => (
        <TouchableOpacity
          key={f.value}
          onPress={() => setFilter(f.value)}
          style={[styles.btn, filter === f.value && styles.btnActive]}
        >
          <Text style={[styles.label, filter === f.value && styles.labelActive]}>
            {f.label} ({counts[f.value]})
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row", gap: 8, paddingHorizontal: 16, paddingVertical: 12,
  },
  btn: {
    paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20,
    backgroundColor: "#f3f4f6",
  },
  btnActive: { backgroundColor: "#3b82f6" },
  label: { fontSize: 14, color: "#6b7280", fontWeight: "500" },
  labelActive: { color: "#fff" },
});
```

## components/EmptyState.tsx

```tsx
import { View, Text, StyleSheet } from "react-native";

export function EmptyState() {
  return (
    <View style={styles.container}>
      <Text style={styles.emoji}>📝</Text>
      <Text style={styles.title}>할 일이 없습니다</Text>
      <Text style={styles.subtitle}>위에서 새로운 할 일을 추가해보세요!</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", alignItems: "center", paddingVertical: 80 },
  emoji: { fontSize: 48, marginBottom: 16 },
  title: { fontSize: 18, fontWeight: "600", color: "#374151" },
  subtitle: { fontSize: 14, color: "#9ca3af", marginTop: 4 },
});
```

## app/(tabs)/index.tsx

```tsx
import { FlatList, View, Text, StyleSheet } from "react-native";
import { useTodoStore } from "../../store/todo-store";
import { AddTodo } from "../../components/AddTodo";
import { TodoItem } from "../../components/TodoItem";
import { FilterBar } from "../../components/FilterBar";
import { EmptyState } from "../../components/EmptyState";

export default function TodoScreen() {
  const filtered = useTodoStore((s) => s.filtered());

  return (
    <View style={styles.container}>
      <AddTodo />
      <FilterBar />
      <FlatList
        data={filtered}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <TodoItem todo={item} />}
        ListEmptyComponent={<EmptyState />}
        contentContainerStyle={styles.list}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f9fafb" },
  list: { paddingBottom: 20 },
});
```

## app/(tabs)/_layout.tsx

```tsx
import { Tabs } from "expo-router";

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: "#fff" },
        headerTitleStyle: { fontWeight: "bold" },
        tabBarActiveTintColor: "#3b82f6",
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: "할 일", tabBarIcon: () => <></> }}
      />
      <Tabs.Screen
        name="settings"
        options={{ title: "설정", tabBarIcon: () => <></> }}
      />
    </Tabs>
  );
}
```

## package.json

```json
{
  "name": "todo-mobile",
  "version": "1.0.0",
  "scripts": {
    "start": "expo start",
    "android": "expo start --android",
    "ios": "expo start --ios"
  },
  "dependencies": {
    "expo": "~52.0.0",
    "expo-router": "~4.0.0",
    "react": "^19.0.0",
    "react-native": "^0.76.0",
    "zustand": "^5.0.0",
    "@react-native-async-storage/async-storage": "^2.0.0"
  }
}
```

## 실행

```bash
npx create-expo-app todo-mobile
cd todo-mobile
npx expo start
```

Expo Router + Zustand + AsyncStorage 기반 모바일 할일 앱! 우선순위 + 필터 + 애니메이션 삭제!'''),

]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mega_projects.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"메가 프로젝트: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
