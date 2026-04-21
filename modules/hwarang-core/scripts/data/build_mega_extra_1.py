"""화랑 AI 추가 학습 데이터 (이커머스/대시보드 보강)

이커머스/대시보드 보강 10건:
  - 셀러 상품 등록/관리
  - 배너/프로모션 관리
  - 이메일 템플릿 관리
  - 대시보드 알림 센터
  - 대시보드 다국어(i18n)
  - 데이터 내보내기(CSV/Excel)
  - FAQ/고객지원 관리
  - 인증 시스템(JWT + OAuth)
  - 실시간 대시보드 WebSocket API
  - 블로그 CMS
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
    # ═══ 1. 셀러 상품 등록/관리 ═══
    m("Next.js로 셀러 상품 등록/관리 페이지 만들어줘 전체 코드로",
'''셀러용 상품 등록/관리 시스템을 만들어 드릴게요. 상품 등록 폼(이름, 가격, 설명, 카테고리, 이미지), 옵션 변형(사이즈/컬러), 상품 목록에서 상태 토글, 수정/삭제 기능을 모두 포함합니다.

## 폴더 구조

```
seller-product-manager/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       └── products/
│           ├── route.ts
│           └── [id]/
│               └── route.ts
├── components/
│   ├── product-form.tsx
│   ├── product-list.tsx
│   ├── variant-manager.tsx
│   ├── image-uploader.tsx
│   ├── status-toggle.tsx
│   └── delete-confirm-modal.tsx
├── lib/
│   ├── types.ts
│   └── store.ts
└── package.json
```

## lib/types.ts

```typescript
export interface ProductVariant {
  id: string;
  size: string;
  color: string;
  sku: string;
  stock: number;
  priceAdjustment: number;
}

export interface ProductImage {
  id: string;
  url: string;
  alt: string;
  isPrimary: boolean;
}

export type ProductStatus = "draft" | "active" | "inactive" | "soldout";

export interface Product {
  id: string;
  name: string;
  price: number;
  description: string;
  category: string;
  status: ProductStatus;
  images: ProductImage[];
  variants: ProductVariant[];
  createdAt: string;
  updatedAt: string;
}

export interface ProductFormData {
  name: string;
  price: number;
  description: string;
  category: string;
  images: ProductImage[];
  variants: ProductVariant[];
}

export const CATEGORIES = [
  "의류", "전자기기", "식품", "뷰티", "가구", "스포츠", "도서", "기타"
];
```

## lib/store.ts

```typescript
import { Product, ProductFormData, ProductStatus } from "./types";

let products: Product[] = [
  {
    id: "prod-1",
    name: "프리미엄 코튼 티셔츠",
    price: 39000,
    description: "100% 오가닉 코튼 소재의 프리미엄 티셔츠",
    category: "의류",
    status: "active",
    images: [{ id: "img-1", url: "/images/tshirt.jpg", alt: "티셔츠", isPrimary: true }],
    variants: [
      { id: "v-1", size: "S", color: "화이트", sku: "TSH-WH-S", stock: 50, priceAdjustment: 0 },
      { id: "v-2", size: "M", color: "화이트", sku: "TSH-WH-M", stock: 80, priceAdjustment: 0 },
      { id: "v-3", size: "L", color: "블랙", sku: "TSH-BK-L", stock: 30, priceAdjustment: 2000 },
    ],
    createdAt: "2025-01-10T09:00:00Z",
    updatedAt: "2025-01-10T09:00:00Z",
  },
];

export function getProducts(): Product[] {
  return products;
}

export function getProduct(id: string): Product | undefined {
  return products.find((p) => p.id === id);
}

export function createProduct(data: ProductFormData): Product {
  const now = new Date().toISOString();
  const product: Product = {
    id: `prod-${Date.now()}`,
    ...data,
    status: "draft",
    createdAt: now,
    updatedAt: now,
  };
  products.push(product);
  return product;
}

export function updateProduct(id: string, data: Partial<ProductFormData & { status: ProductStatus }>): Product | null {
  const idx = products.findIndex((p) => p.id === id);
  if (idx === -1) return null;
  products[idx] = { ...products[idx], ...data, updatedAt: new Date().toISOString() };
  return products[idx];
}

export function deleteProduct(id: string): boolean {
  const len = products.length;
  products = products.filter((p) => p.id !== id);
  return products.length < len;
}
```

## app/api/products/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { getProducts, createProduct } from "@/lib/store";
import { ProductFormData } from "@/lib/types";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  let items = getProducts();
  const status = searchParams.get("status");
  const category = searchParams.get("category");
  const q = searchParams.get("q");
  if (status) items = items.filter((p) => p.status === status);
  if (category) items = items.filter((p) => p.category === category);
  if (q) items = items.filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));
  return NextResponse.json({ products: items, total: items.length });
}

export async function POST(req: NextRequest) {
  const body: ProductFormData = await req.json();
  if (!body.name || body.price == null) {
    return NextResponse.json({ error: "이름과 가격은 필수입니다" }, { status: 400 });
  }
  const product = createProduct(body);
  return NextResponse.json(product, { status: 201 });
}
```

## app/api/products/[id]/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { getProduct, updateProduct, deleteProduct } from "@/lib/store";

export async function GET(_: NextRequest, { params }: { params: { id: string } }) {
  const product = getProduct(params.id);
  if (!product) return NextResponse.json({ error: "상품을 찾을 수 없습니다" }, { status: 404 });
  return NextResponse.json(product);
}

export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const body = await req.json();
  const updated = updateProduct(params.id, body);
  if (!updated) return NextResponse.json({ error: "상품을 찾을 수 없습니다" }, { status: 404 });
  return NextResponse.json(updated);
}

export async function DELETE(_: NextRequest, { params }: { params: { id: string } }) {
  const ok = deleteProduct(params.id);
  if (!ok) return NextResponse.json({ error: "상품을 찾을 수 없습니다" }, { status: 404 });
  return NextResponse.json({ message: "삭제 완료" });
}
```

## components/product-form.tsx

```tsx
"use client";
import { useState } from "react";
import { ProductFormData, CATEGORIES, ProductVariant, ProductImage } from "@/lib/types";
import VariantManager from "./variant-manager";
import ImageUploader from "./image-uploader";

interface Props {
  initial?: ProductFormData;
  onSubmit: (data: ProductFormData) => void;
  onCancel: () => void;
}

export default function ProductForm({ initial, onSubmit, onCancel }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [price, setPrice] = useState(initial?.price ?? 0);
  const [description, setDescription] = useState(initial?.description ?? "");
  const [category, setCategory] = useState(initial?.category ?? CATEGORIES[0]);
  const [images, setImages] = useState<ProductImage[]>(initial?.images ?? []);
  const [variants, setVariants] = useState<ProductVariant[]>(initial?.variants ?? []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ name, price, description, category, images, variants });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6 bg-white p-6 rounded-xl shadow">
      <h2 className="text-xl font-bold">{initial ? "상품 수정" : "상품 등록"}</h2>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">상품명 *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required
            className="w-full border rounded-lg px-3 py-2" placeholder="상품명 입력" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">가격 (원) *</label>
          <input type="number" value={price} onChange={(e) => setPrice(Number(e.target.value))} required min={0}
            className="w-full border rounded-lg px-3 py-2" />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">카테고리</label>
        <select value={category} onChange={(e) => setCategory(e.target.value)}
          className="w-full border rounded-lg px-3 py-2">
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">상품 설명</label>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4}
          className="w-full border rounded-lg px-3 py-2" placeholder="상품 설명을 입력하세요" />
      </div>
      <ImageUploader images={images} onChange={setImages} />
      <VariantManager variants={variants} onChange={setVariants} />
      <div className="flex gap-3 justify-end">
        <button type="button" onClick={onCancel} className="px-4 py-2 border rounded-lg hover:bg-gray-50">취소</button>
        <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          {initial ? "수정 완료" : "등록하기"}
        </button>
      </div>
    </form>
  );
}
```

## components/variant-manager.tsx

```tsx
"use client";
import { useState } from "react";
import { ProductVariant } from "@/lib/types";

interface Props { variants: ProductVariant[]; onChange: (v: ProductVariant[]) => void; }

const SIZES = ["XS", "S", "M", "L", "XL", "XXL"];
const COLORS = ["화이트", "블랙", "네이비", "그레이", "레드", "블루"];

export default function VariantManager({ variants, onChange }: Props) {
  const addVariant = () => {
    const v: ProductVariant = {
      id: `var-${Date.now()}`, size: "M", color: "화이트",
      sku: "", stock: 0, priceAdjustment: 0,
    };
    onChange([...variants, v]);
  };
  const update = (idx: number, field: keyof ProductVariant, val: string | number) => {
    const copy = [...variants];
    copy[idx] = { ...copy[idx], [field]: val };
    onChange(copy);
  };
  const remove = (idx: number) => onChange(variants.filter((_, i) => i !== idx));

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">옵션 변형 (사이즈/컬러)</h3>
        <button type="button" onClick={addVariant} className="text-sm text-blue-600 hover:underline">+ 옵션 추가</button>
      </div>
      {variants.map((v, i) => (
        <div key={v.id} className="grid grid-cols-6 gap-2 items-end border p-3 rounded-lg">
          <div>
            <label className="text-xs">사이즈</label>
            <select value={v.size} onChange={(e) => update(i, "size", e.target.value)} className="w-full border rounded px-2 py-1 text-sm">
              {SIZES.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs">컬러</label>
            <select value={v.color} onChange={(e) => update(i, "color", e.target.value)} className="w-full border rounded px-2 py-1 text-sm">
              {COLORS.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs">SKU</label>
            <input value={v.sku} onChange={(e) => update(i, "sku", e.target.value)} className="w-full border rounded px-2 py-1 text-sm" />
          </div>
          <div>
            <label className="text-xs">재고</label>
            <input type="number" value={v.stock} onChange={(e) => update(i, "stock", Number(e.target.value))} className="w-full border rounded px-2 py-1 text-sm" />
          </div>
          <div>
            <label className="text-xs">추가금</label>
            <input type="number" value={v.priceAdjustment} onChange={(e) => update(i, "priceAdjustment", Number(e.target.value))} className="w-full border rounded px-2 py-1 text-sm" />
          </div>
          <button type="button" onClick={() => remove(i)} className="text-red-500 text-sm hover:underline pb-1">삭제</button>
        </div>
      ))}
    </div>
  );
}
```

## components/image-uploader.tsx

```tsx
"use client";
import { ProductImage } from "@/lib/types";

interface Props { images: ProductImage[]; onChange: (imgs: ProductImage[]) => void; }

export default function ImageUploader({ images, onChange }: Props) {
  const addImage = () => {
    const url = prompt("이미지 URL을 입력하세요");
    if (!url) return;
    const img: ProductImage = { id: `img-${Date.now()}`, url, alt: "", isPrimary: images.length === 0 };
    onChange([...images, img]);
  };
  const setPrimary = (id: string) => {
    onChange(images.map((img) => ({ ...img, isPrimary: img.id === id })));
  };
  const remove = (id: string) => {
    const filtered = images.filter((img) => img.id !== id);
    if (filtered.length > 0 && !filtered.some((img) => img.isPrimary)) {
      filtered[0].isPrimary = true;
    }
    onChange(filtered);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">상품 이미지</h3>
        <button type="button" onClick={addImage} className="text-sm text-blue-600 hover:underline">+ 이미지 추가</button>
      </div>
      <div className="flex gap-3 flex-wrap">
        {images.map((img) => (
          <div key={img.id} className={`relative w-24 h-24 border-2 rounded-lg overflow-hidden ${img.isPrimary ? "border-blue-500" : "border-gray-200"}`}>
            <img src={img.url} alt={img.alt} className="w-full h-full object-cover" />
            <div className="absolute bottom-0 left-0 right-0 bg-black/60 flex justify-between px-1">
              <button type="button" onClick={() => setPrimary(img.id)} className="text-[10px] text-white">대표</button>
              <button type="button" onClick={() => remove(img.id)} className="text-[10px] text-red-300">삭제</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

## components/product-list.tsx

```tsx
"use client";
import { Product, ProductStatus } from "@/lib/types";
import StatusToggle from "./status-toggle";

interface Props {
  products: Product[];
  onEdit: (p: Product) => void;
  onDelete: (id: string) => void;
  onStatusChange: (id: string, status: ProductStatus) => void;
}

export default function ProductList({ products, onEdit, onDelete, onStatusChange }: Props) {
  return (
    <div className="bg-white rounded-xl shadow overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="text-left px-4 py-3">상품명</th>
            <th className="text-left px-4 py-3">카테고리</th>
            <th className="text-right px-4 py-3">가격</th>
            <th className="text-center px-4 py-3">옵션수</th>
            <th className="text-center px-4 py-3">상태</th>
            <th className="text-center px-4 py-3">관리</th>
          </tr>
        </thead>
        <tbody>
          {products.map((p) => (
            <tr key={p.id} className="border-t hover:bg-gray-50">
              <td className="px-4 py-3 font-medium">{p.name}</td>
              <td className="px-4 py-3">{p.category}</td>
              <td className="px-4 py-3 text-right">{p.price.toLocaleString()}원</td>
              <td className="px-4 py-3 text-center">{p.variants.length}</td>
              <td className="px-4 py-3 text-center">
                <StatusToggle status={p.status} onChange={(s) => onStatusChange(p.id, s)} />
              </td>
              <td className="px-4 py-3 text-center space-x-2">
                <button onClick={() => onEdit(p)} className="text-blue-600 hover:underline">수정</button>
                <button onClick={() => onDelete(p.id)} className="text-red-600 hover:underline">삭제</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

## components/status-toggle.tsx

```tsx
"use client";
import { ProductStatus } from "@/lib/types";

const STATUS_MAP: Record<ProductStatus, { label: string; color: string }> = {
  draft: { label: "임시저장", color: "bg-gray-100 text-gray-600" },
  active: { label: "판매중", color: "bg-green-100 text-green-700" },
  inactive: { label: "판매중지", color: "bg-yellow-100 text-yellow-700" },
  soldout: { label: "품절", color: "bg-red-100 text-red-700" },
};

const CYCLE: ProductStatus[] = ["draft", "active", "inactive", "soldout"];

export default function StatusToggle({ status, onChange }: { status: ProductStatus; onChange: (s: ProductStatus) => void }) {
  const next = () => {
    const idx = CYCLE.indexOf(status);
    onChange(CYCLE[(idx + 1) % CYCLE.length]);
  };
  const { label, color } = STATUS_MAP[status];
  return (
    <button onClick={next} className={`px-3 py-1 rounded-full text-xs font-medium ${color}`}>
      {label}
    </button>
  );
}
```

이 시스템은 셀러가 상품을 등록하고 옵션(사이즈/컬러) 변형을 관리하며, 상품 목록에서 상태를 순환 토글하고 수정/삭제할 수 있습니다.'''),

    # ═══ 2. 배너/프로모션 관리 ═══
    m("Next.js 이커머스 배너/프로모션 관리 만들어줘 전체 코드로",
'''배너 캐러셀 및 프로모션 관리 시스템을 만들어 드릴게요. 자동 슬라이드 배너, 프로모션 CRUD(시작/종료일), 플래시 세일 카운트다운, 활성/비활성 토글을 포함합니다.

## 폴더 구조

```
banner-promo-manager/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       ├── banners/
│       │   └── route.ts
│       └── promotions/
│           ├── route.ts
│           └── [id]/route.ts
├── components/
│   ├── banner-carousel.tsx
│   ├── banner-form.tsx
│   ├── promotion-list.tsx
│   ├── promotion-form.tsx
│   ├── countdown-timer.tsx
│   └── active-toggle.tsx
├── lib/
│   ├── types.ts
│   └── store.ts
└── package.json
```

## lib/types.ts

```typescript
export interface Banner {
  id: string;
  title: string;
  subtitle: string;
  imageUrl: string;
  linkUrl: string;
  order: number;
  isActive: boolean;
  createdAt: string;
}

export interface Promotion {
  id: string;
  name: string;
  description: string;
  discountType: "percent" | "fixed";
  discountValue: number;
  startDate: string;
  endDate: string;
  isActive: boolean;
  isFlashSale: boolean;
  createdAt: string;
}
```

## lib/store.ts

```typescript
import { Banner, Promotion } from "./types";

let banners: Banner[] = [
  { id: "b-1", title: "여름 세일 최대 50%", subtitle: "7월 한정 특가", imageUrl: "/banners/summer.jpg", linkUrl: "/sale/summer", order: 1, isActive: true, createdAt: "2025-06-01T00:00:00Z" },
  { id: "b-2", title: "신상품 입고", subtitle: "2025 FW 컬렉션", imageUrl: "/banners/new.jpg", linkUrl: "/new-arrivals", order: 2, isActive: true, createdAt: "2025-06-10T00:00:00Z" },
  { id: "b-3", title: "무료배송 이벤트", subtitle: "5만원 이상 구매 시", imageUrl: "/banners/shipping.jpg", linkUrl: "/event/shipping", order: 3, isActive: false, createdAt: "2025-06-15T00:00:00Z" },
];

let promotions: Promotion[] = [
  { id: "p-1", name: "여름 특가 세일", description: "전 상품 20% 할인", discountType: "percent", discountValue: 20, startDate: "2025-07-01T00:00:00Z", endDate: "2025-07-31T23:59:59Z", isActive: true, isFlashSale: false, createdAt: "2025-06-20T00:00:00Z" },
  { id: "p-2", name: "플래시 세일", description: "한정 수량 50% 할인", discountType: "percent", discountValue: 50, startDate: "2025-07-15T10:00:00Z", endDate: "2025-07-15T22:00:00Z", isActive: true, isFlashSale: true, createdAt: "2025-07-10T00:00:00Z" },
];

export const getBanners = () => banners.sort((a, b) => a.order - b.order);
export const createBanner = (data: Omit<Banner, "id" | "createdAt">) => {
  const b: Banner = { ...data, id: `b-${Date.now()}`, createdAt: new Date().toISOString() };
  banners.push(b);
  return b;
};
export const toggleBanner = (id: string) => {
  const b = banners.find((x) => x.id === id);
  if (b) b.isActive = !b.isActive;
  return b;
};

export const getPromotions = () => promotions;
export const createPromotion = (data: Omit<Promotion, "id" | "createdAt">) => {
  const p: Promotion = { ...data, id: `p-${Date.now()}`, createdAt: new Date().toISOString() };
  promotions.push(p);
  return p;
};
export const updatePromotion = (id: string, data: Partial<Promotion>) => {
  const idx = promotions.findIndex((p) => p.id === id);
  if (idx === -1) return null;
  promotions[idx] = { ...promotions[idx], ...data };
  return promotions[idx];
};
export const deletePromotion = (id: string) => {
  const len = promotions.length;
  promotions = promotions.filter((p) => p.id !== id);
  return promotions.length < len;
};
```

## components/banner-carousel.tsx

```tsx
"use client";
import { useState, useEffect, useCallback } from "react";
import { Banner } from "@/lib/types";

export default function BannerCarousel({ banners }: { banners: Banner[] }) {
  const active = banners.filter((b) => b.isActive);
  const [current, setCurrent] = useState(0);

  const next = useCallback(() => setCurrent((c) => (c + 1) % active.length), [active.length]);
  const prev = () => setCurrent((c) => (c - 1 + active.length) % active.length);

  useEffect(() => {
    if (active.length <= 1) return;
    const timer = setInterval(next, 4000);
    return () => clearInterval(timer);
  }, [active.length, next]);

  if (active.length === 0) return <div className="h-64 bg-gray-100 rounded-xl flex items-center justify-center text-gray-400">활성 배너가 없습니다</div>;

  const slide = active[current];
  return (
    <div className="relative h-64 rounded-xl overflow-hidden group">
      <div className="absolute inset-0 bg-gradient-to-r from-black/50 to-transparent z-10" />
      <img src={slide.imageUrl} alt={slide.title} className="w-full h-full object-cover" />
      <div className="absolute bottom-6 left-6 z-20 text-white">
        <h2 className="text-2xl font-bold">{slide.title}</h2>
        <p className="text-sm opacity-80">{slide.subtitle}</p>
      </div>
      <button onClick={prev} className="absolute left-2 top-1/2 -translate-y-1/2 z-20 w-8 h-8 bg-white/70 rounded-full opacity-0 group-hover:opacity-100 transition">&#8249;</button>
      <button onClick={next} className="absolute right-2 top-1/2 -translate-y-1/2 z-20 w-8 h-8 bg-white/70 rounded-full opacity-0 group-hover:opacity-100 transition">&#8250;</button>
      <div className="absolute bottom-2 right-4 z-20 flex gap-1">
        {active.map((_, i) => (
          <span key={i} onClick={() => setCurrent(i)}
            className={`w-2 h-2 rounded-full cursor-pointer ${i === current ? "bg-white" : "bg-white/40"}`} />
        ))}
      </div>
    </div>
  );
}
```

## components/countdown-timer.tsx

```tsx
"use client";
import { useState, useEffect } from "react";

function pad(n: number) { return String(n).padStart(2, "0"); }

export default function CountdownTimer({ endDate }: { endDate: string }) {
  const [remaining, setRemaining] = useState({ d: 0, h: 0, m: 0, s: 0, expired: false });

  useEffect(() => {
    const calc = () => {
      const diff = new Date(endDate).getTime() - Date.now();
      if (diff <= 0) return { d: 0, h: 0, m: 0, s: 0, expired: true };
      const s = Math.floor(diff / 1000);
      return { d: Math.floor(s / 86400), h: Math.floor((s % 86400) / 3600), m: Math.floor((s % 3600) / 60), s: s % 60, expired: false };
    };
    setRemaining(calc());
    const timer = setInterval(() => setRemaining(calc()), 1000);
    return () => clearInterval(timer);
  }, [endDate]);

  if (remaining.expired) return <span className="text-red-500 font-bold text-sm">종료됨</span>;

  return (
    <div className="flex gap-1 text-sm font-mono">
      <span className="bg-red-600 text-white px-2 py-1 rounded">{pad(remaining.d)}일</span>
      <span className="bg-red-600 text-white px-2 py-1 rounded">{pad(remaining.h)}시</span>
      <span className="bg-red-600 text-white px-2 py-1 rounded">{pad(remaining.m)}분</span>
      <span className="bg-red-600 text-white px-2 py-1 rounded">{pad(remaining.s)}초</span>
    </div>
  );
}
```

## components/promotion-list.tsx

```tsx
"use client";
import { Promotion } from "@/lib/types";
import CountdownTimer from "./countdown-timer";

interface Props {
  promotions: Promotion[];
  onEdit: (p: Promotion) => void;
  onDelete: (id: string) => void;
  onToggle: (id: string) => void;
}

export default function PromotionList({ promotions, onEdit, onDelete, onToggle }: Props) {
  return (
    <div className="space-y-3">
      {promotions.map((p) => (
        <div key={p.id} className="bg-white rounded-xl shadow p-4 flex items-center justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h3 className="font-bold">{p.name}</h3>
              {p.isFlashSale && <span className="bg-red-100 text-red-600 text-xs px-2 py-0.5 rounded-full">FLASH</span>}
              <span className={`text-xs px-2 py-0.5 rounded-full ${p.isActive ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                {p.isActive ? "활성" : "비활성"}
              </span>
            </div>
            <p className="text-sm text-gray-500 mt-1">{p.description}</p>
            <p className="text-xs text-gray-400 mt-1">
              {new Date(p.startDate).toLocaleDateString("ko")} ~ {new Date(p.endDate).toLocaleDateString("ko")}
              {" | "}{p.discountType === "percent" ? `${p.discountValue}% 할인` : `${p.discountValue.toLocaleString()}원 할인`}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {p.isFlashSale && p.isActive && <CountdownTimer endDate={p.endDate} />}
            <button onClick={() => onToggle(p.id)} className="text-sm text-yellow-600 hover:underline">{p.isActive ? "비활성화" : "활성화"}</button>
            <button onClick={() => onEdit(p)} className="text-sm text-blue-600 hover:underline">수정</button>
            <button onClick={() => onDelete(p.id)} className="text-sm text-red-600 hover:underline">삭제</button>
          </div>
        </div>
      ))}
    </div>
  );
}
```

## components/active-toggle.tsx

```tsx
"use client";

export default function ActiveToggle({ isActive, onToggle }: { isActive: boolean; onToggle: () => void }) {
  return (
    <button onClick={onToggle}
      className={`relative w-11 h-6 rounded-full transition-colors ${isActive ? "bg-green-500" : "bg-gray-300"}`}>
      <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${isActive ? "left-[22px]" : "left-0.5"}`} />
    </button>
  );
}
```

이 시스템은 자동 슬라이드 배너 캐러셀, 프로모션 생성/수정/삭제, 플래시 세일 카운트다운 타이머, 활성/비활성 토글을 모두 포함합니다.'''),

    # ═══ 3. 이메일 템플릿 관리 ═══
    m("Next.js로 이메일 템플릿 관리 시스템 만들어줘 전체 코드로",
'''이메일 템플릿 관리 시스템을 만들어 드릴게요. 리치 텍스트 편집, 변수 플레이스홀더({{name}}), 샘플 데이터로 미리보기, 테스트 전송 API, 템플릿 카테고리를 포함합니다.

## 폴더 구조

```
email-template-manager/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       ├── templates/
│       │   ├── route.ts
│       │   └── [id]/
│       │       ├── route.ts
│       │       └── preview/route.ts
│       └── send-test/route.ts
├── components/
│   ├── template-list.tsx
│   ├── template-editor.tsx
│   ├── template-preview.tsx
│   ├── variable-inserter.tsx
│   ├── category-filter.tsx
│   └── test-send-modal.tsx
├── lib/
│   ├── types.ts
│   └── store.ts
└── package.json
```

## lib/types.ts

```typescript
export type TemplateCategory = "주문확인" | "배송알림" | "마케팅" | "회원가입" | "비밀번호" | "기타";

export interface EmailTemplate {
  id: string;
  name: string;
  subject: string;
  category: TemplateCategory;
  htmlBody: string;
  variables: string[];
  createdAt: string;
  updatedAt: string;
}

export interface SampleData {
  [key: string]: string;
}

export const DEFAULT_VARIABLES: Record<string, SampleData> = {
  주문확인: { name: "김철수", orderNumber: "ORD-2025-001", totalAmount: "89,000원", orderDate: "2025-07-15" },
  배송알림: { name: "이영희", trackingNumber: "CJ1234567890", deliveryDate: "2025-07-18", carrier: "CJ대한통운" },
  마케팅: { name: "박지민", couponCode: "SUMMER50", discount: "50%", expiryDate: "2025-07-31" },
  회원가입: { name: "최수진", email: "user@example.com", verifyLink: "https://example.com/verify/abc123" },
  비밀번호: { name: "정민호", resetLink: "https://example.com/reset/xyz789", expiryMinutes: "30" },
  기타: { name: "홍길동" },
};
```

## lib/store.ts

```typescript
import { EmailTemplate, TemplateCategory } from "./types";

let templates: EmailTemplate[] = [
  {
    id: "tpl-1", name: "주문 확인 메일", subject: "{{name}}님, 주문이 완료되었습니다",
    category: "주문확인",
    htmlBody: `<div style="font-family:sans-serif;max-width:600px;margin:0 auto">
<h1 style="color:#2563eb">주문 확인</h1>
<p>안녕하세요, <strong>{{name}}</strong>님!</p>
<p>주문번호 <strong>{{orderNumber}}</strong>이 정상적으로 접수되었습니다.</p>
<table style="width:100%;border-collapse:collapse;margin:16px 0">
<tr style="background:#f3f4f6"><td style="padding:8px;border:1px solid #e5e7eb">주문일</td><td style="padding:8px;border:1px solid #e5e7eb">{{orderDate}}</td></tr>
<tr><td style="padding:8px;border:1px solid #e5e7eb">총 결제금액</td><td style="padding:8px;border:1px solid #e5e7eb">{{totalAmount}}</td></tr>
</table>
<p>감사합니다.</p></div>`,
    variables: ["name", "orderNumber", "orderDate", "totalAmount"],
    createdAt: "2025-06-01T00:00:00Z", updatedAt: "2025-06-01T00:00:00Z",
  },
  {
    id: "tpl-2", name: "배송 시작 알림", subject: "{{name}}님, 상품이 발송되었습니다",
    category: "배송알림",
    htmlBody: `<div style="font-family:sans-serif;max-width:600px;margin:0 auto">
<h1 style="color:#16a34a">배송 시작</h1>
<p>안녕하세요, <strong>{{name}}</strong>님!</p>
<p>운송장번호: <strong>{{trackingNumber}}</strong> ({{carrier}})</p>
<p>예상 도착일: <strong>{{deliveryDate}}</strong></p>
</div>`,
    variables: ["name", "trackingNumber", "carrier", "deliveryDate"],
    createdAt: "2025-06-05T00:00:00Z", updatedAt: "2025-06-05T00:00:00Z",
  },
];

export const getTemplates = (category?: TemplateCategory) =>
  category ? templates.filter((t) => t.category === category) : templates;
export const getTemplate = (id: string) => templates.find((t) => t.id === id);
export const createTemplate = (data: Omit<EmailTemplate, "id" | "createdAt" | "updatedAt">) => {
  const now = new Date().toISOString();
  const t: EmailTemplate = { ...data, id: `tpl-${Date.now()}`, createdAt: now, updatedAt: now };
  templates.push(t);
  return t;
};
export const updateTemplate = (id: string, data: Partial<EmailTemplate>) => {
  const idx = templates.findIndex((t) => t.id === id);
  if (idx === -1) return null;
  templates[idx] = { ...templates[idx], ...data, updatedAt: new Date().toISOString() };
  return templates[idx];
};
export const deleteTemplate = (id: string) => {
  const len = templates.length;
  templates = templates.filter((t) => t.id !== id);
  return templates.length < len;
};
```

## components/template-editor.tsx

```tsx
"use client";
import { useState } from "react";
import { EmailTemplate, TemplateCategory } from "@/lib/types";
import VariableInserter from "./variable-inserter";

const CATEGORIES: TemplateCategory[] = ["주문확인", "배송알림", "마케팅", "회원가입", "비밀번호", "기타"];

interface Props {
  initial?: EmailTemplate;
  onSave: (data: Omit<EmailTemplate, "id" | "createdAt" | "updatedAt">) => void;
  onCancel: () => void;
}

export default function TemplateEditor({ initial, onSave, onCancel }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [subject, setSubject] = useState(initial?.subject ?? "");
  const [category, setCategory] = useState<TemplateCategory>(initial?.category ?? "기타");
  const [htmlBody, setHtmlBody] = useState(initial?.htmlBody ?? "");

  const extractVars = (text: string): string[] => {
    const matches = text.match(/\{\{(\w+)\}\}/g) || [];
    return [...new Set(matches.map((m) => m.replace(/\{|\}/g, "")))];
  };

  const insertVariable = (varName: string) => {
    setHtmlBody((prev) => prev + `{{${varName}}}`);
  };

  const handleSave = () => {
    const variables = extractVars(subject + htmlBody);
    onSave({ name, subject, category, htmlBody, variables });
  };

  return (
    <div className="bg-white rounded-xl shadow p-6 space-y-4">
      <h2 className="text-xl font-bold">{initial ? "템플릿 수정" : "새 템플릿"}</h2>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">템플릿 이름</label>
          <input value={name} onChange={(e) => setName(e.target.value)} className="w-full border rounded-lg px-3 py-2" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">카테고리</label>
          <select value={category} onChange={(e) => setCategory(e.target.value as TemplateCategory)} className="w-full border rounded-lg px-3 py-2">
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">제목 (변수 사용 가능)</label>
        <input value={subject} onChange={(e) => setSubject(e.target.value)} className="w-full border rounded-lg px-3 py-2"
          placeholder="{{name}}님, 주문이 완료되었습니다" />
      </div>
      <VariableInserter onInsert={insertVariable} />
      <div>
        <label className="block text-sm font-medium mb-1">HTML 본문</label>
        <textarea value={htmlBody} onChange={(e) => setHtmlBody(e.target.value)} rows={12}
          className="w-full border rounded-lg px-3 py-2 font-mono text-sm" />
      </div>
      <p className="text-xs text-gray-400">감지된 변수: {extractVars(subject + htmlBody).join(", ") || "없음"}</p>
      <div className="flex gap-3 justify-end">
        <button onClick={onCancel} className="px-4 py-2 border rounded-lg hover:bg-gray-50">취소</button>
        <button onClick={handleSave} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">저장</button>
      </div>
    </div>
  );
}
```

## components/variable-inserter.tsx

```tsx
"use client";

const COMMON_VARS = ["name", "email", "orderNumber", "totalAmount", "trackingNumber", "couponCode", "link"];

export default function VariableInserter({ onInsert }: { onInsert: (v: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      <span className="text-sm text-gray-500">변수 삽입:</span>
      {COMMON_VARS.map((v) => (
        <button key={v} type="button" onClick={() => onInsert(v)}
          className="text-xs bg-blue-50 text-blue-600 px-2 py-1 rounded hover:bg-blue-100">
          {`{{${v}}}`}
        </button>
      ))}
    </div>
  );
}
```

## components/template-preview.tsx

```tsx
"use client";
import { useState } from "react";
import { EmailTemplate, SampleData, DEFAULT_VARIABLES } from "@/lib/types";

export default function TemplatePreview({ template }: { template: EmailTemplate }) {
  const defaults = DEFAULT_VARIABLES[template.category] || {};
  const [sampleData, setSampleData] = useState<SampleData>(defaults);

  const renderHtml = (html: string) => {
    let result = html;
    Object.entries(sampleData).forEach(([key, val]) => {
      result = result.replace(new RegExp(`\\{\\{${key}\\}\\}`, "g"), val);
    });
    return result;
  };

  const renderedSubject = Object.entries(sampleData).reduce(
    (s, [k, v]) => s.replace(new RegExp(`\\{\\{${k}\\}\\}`, "g"), v), template.subject
  );

  return (
    <div className="space-y-4">
      <h3 className="font-bold">미리보기</h3>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <p className="text-sm font-medium">샘플 데이터</p>
          {template.variables.map((v) => (
            <div key={v} className="flex gap-2 items-center">
              <label className="text-xs w-28 text-right text-gray-500">{`{{${v}}}`}</label>
              <input value={sampleData[v] ?? ""} onChange={(e) => setSampleData({ ...sampleData, [v]: e.target.value })}
                className="flex-1 border rounded px-2 py-1 text-sm" />
            </div>
          ))}
        </div>
        <div className="border rounded-lg p-4 bg-gray-50">
          <p className="text-xs text-gray-400 mb-1">제목</p>
          <p className="font-medium mb-3">{renderedSubject}</p>
          <p className="text-xs text-gray-400 mb-1">본문</p>
          <div className="bg-white p-3 rounded border" dangerouslySetInnerHTML={{ __html: renderHtml(template.htmlBody) }} />
        </div>
      </div>
    </div>
  );
}
```

## app/api/send-test/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { getTemplate } from "@/lib/store";

export async function POST(req: NextRequest) {
  const { templateId, recipientEmail, sampleData } = await req.json();
  const template = getTemplate(templateId);
  if (!template) return NextResponse.json({ error: "템플릿을 찾을 수 없습니다" }, { status: 404 });
  if (!recipientEmail) return NextResponse.json({ error: "수신 이메일 필수" }, { status: 400 });

  let html = template.htmlBody;
  let subject = template.subject;
  Object.entries(sampleData || {}).forEach(([key, val]) => {
    const regex = new RegExp(`\\{\\{${key}\\}\\}`, "g");
    html = html.replace(regex, val as string);
    subject = subject.replace(regex, val as string);
  });

  // 실제 환경에서는 nodemailer 등으로 발송
  console.log(`[TEST SEND] To: ${recipientEmail}, Subject: ${subject}`);
  return NextResponse.json({ success: true, message: `${recipientEmail}로 테스트 메일 발송 완료 (시뮬레이션)` });
}
```

이 시스템은 이메일 템플릿 CRUD, {{변수}} 플레이스홀더 자동 감지, 샘플 데이터로 실시간 미리보기, 테스트 발송 API를 지원합니다.'''),

    # ═══ 4. 대시보드 알림 센터 ═══
    m("Next.js로 대시보드 알림 센터 만들어줘 전체 코드로",
'''대시보드 알림 센터를 만들어 드릴게요. 알림 유형(info/warning/error), 읽음/안읽음 토글, 카테고리별 알림 설정, 뱃지 카운트, 드롭다운 패널을 포함합니다.

## 폴더 구조

```
notification-center/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       └── notifications/
│           ├── route.ts
│           └── [id]/route.ts
├── components/
│   ├── notification-bell.tsx
│   ├── notification-dropdown.tsx
│   ├── notification-item.tsx
│   ├── notification-page.tsx
│   ├── notification-preferences.tsx
│   └── badge.tsx
├── lib/
│   ├── types.ts
│   ├── store.ts
│   └── notification-context.tsx
└── package.json
```

## lib/types.ts

```typescript
export type NotificationType = "info" | "warning" | "error" | "success";
export type NotificationCategory = "order" | "system" | "marketing" | "security" | "inventory";

export interface Notification {
  id: string;
  type: NotificationType;
  category: NotificationCategory;
  title: string;
  message: string;
  isRead: boolean;
  link?: string;
  createdAt: string;
}

export interface NotificationPreference {
  category: NotificationCategory;
  label: string;
  email: boolean;
  push: boolean;
  inApp: boolean;
}
```

## lib/store.ts

```typescript
import { Notification, NotificationPreference, NotificationCategory } from "./types";

let notifications: Notification[] = [
  { id: "n-1", type: "info", category: "order", title: "새 주문 접수", message: "주문번호 ORD-2025-042가 접수되었습니다.", isRead: false, link: "/orders/ORD-2025-042", createdAt: "2025-07-15T14:30:00Z" },
  { id: "n-2", type: "warning", category: "inventory", title: "재고 부족 경고", message: "프리미엄 코튼 티셔츠 (M/화이트) 재고 5개 미만", isRead: false, createdAt: "2025-07-15T13:00:00Z" },
  { id: "n-3", type: "error", category: "system", title: "결제 시스템 오류", message: "PG사 결제 모듈 응답 지연 발생", isRead: false, createdAt: "2025-07-15T12:00:00Z" },
  { id: "n-4", type: "success", category: "order", title: "배송 완료", message: "주문번호 ORD-2025-038 배송이 완료되었습니다.", isRead: true, createdAt: "2025-07-14T18:00:00Z" },
  { id: "n-5", type: "info", category: "marketing", title: "이벤트 종료 임박", message: "여름 특가 세일이 3일 후 종료됩니다.", isRead: true, createdAt: "2025-07-14T09:00:00Z" },
  { id: "n-6", type: "warning", category: "security", title: "비정상 로그인 시도", message: "IP 203.0.113.45에서 반복적인 로그인 실패가 감지되었습니다.", isRead: false, createdAt: "2025-07-15T10:30:00Z" },
];

let preferences: NotificationPreference[] = [
  { category: "order", label: "주문 알림", email: true, push: true, inApp: true },
  { category: "system", label: "시스템 알림", email: true, push: false, inApp: true },
  { category: "marketing", label: "마케팅 알림", email: false, push: false, inApp: true },
  { category: "security", label: "보안 알림", email: true, push: true, inApp: true },
  { category: "inventory", label: "재고 알림", email: true, push: true, inApp: true },
];

export const getNotifications = () => notifications.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
export const getUnreadCount = () => notifications.filter((n) => !n.isRead).length;
export const markRead = (id: string) => {
  const n = notifications.find((x) => x.id === id);
  if (n) n.isRead = true;
  return n;
};
export const markAllRead = () => { notifications.forEach((n) => (n.isRead = true)); };
export const toggleRead = (id: string) => {
  const n = notifications.find((x) => x.id === id);
  if (n) n.isRead = !n.isRead;
  return n;
};
export const getPreferences = () => preferences;
export const updatePreference = (category: NotificationCategory, data: Partial<NotificationPreference>) => {
  const idx = preferences.findIndex((p) => p.category === category);
  if (idx === -1) return null;
  preferences[idx] = { ...preferences[idx], ...data };
  return preferences[idx];
};
```

## lib/notification-context.tsx

```tsx
"use client";
import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { Notification, NotificationPreference } from "./types";

interface NotificationContextType {
  notifications: Notification[];
  unreadCount: number;
  refresh: () => Promise<void>;
  markAsRead: (id: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;
  toggleReadStatus: (id: string) => Promise<void>;
}

const NotificationContext = createContext<NotificationContextType | null>(null);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const unreadCount = notifications.filter((n) => !n.isRead).length;

  const refresh = useCallback(async () => {
    const res = await fetch("/api/notifications");
    const data = await res.json();
    setNotifications(data.notifications);
  }, []);

  const markAsRead = async (id: string) => {
    await fetch(`/api/notifications/${id}`, { method: "PATCH", body: JSON.stringify({ isRead: true }), headers: { "Content-Type": "application/json" } });
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, isRead: true } : n)));
  };

  const markAllAsRead = async () => {
    await fetch("/api/notifications", { method: "PATCH" });
    setNotifications((prev) => prev.map((n) => ({ ...n, isRead: true })));
  };

  const toggleReadStatus = async (id: string) => {
    const target = notifications.find((n) => n.id === id);
    if (!target) return;
    await fetch(`/api/notifications/${id}`, { method: "PATCH", body: JSON.stringify({ isRead: !target.isRead }), headers: { "Content-Type": "application/json" } });
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, isRead: !n.isRead } : n)));
  };

  return (
    <NotificationContext.Provider value={{ notifications, unreadCount, refresh, markAsRead, markAllAsRead, toggleReadStatus }}>
      {children}
    </NotificationContext.Provider>
  );
}

export const useNotifications = () => {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error("NotificationProvider 필요");
  return ctx;
};
```

## components/notification-bell.tsx

```tsx
"use client";
import { useState, useEffect, useRef } from "react";
import { useNotifications } from "@/lib/notification-context";
import NotificationDropdown from "./notification-dropdown";
import Badge from "./badge";

export default function NotificationBell() {
  const { unreadCount, refresh } = useNotifications();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(!open)} className="relative p-2 rounded-lg hover:bg-gray-100">
        <svg className="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unreadCount > 0 && <Badge count={unreadCount} />}
      </button>
      {open && <NotificationDropdown onClose={() => setOpen(false)} />}
    </div>
  );
}
```

## components/notification-dropdown.tsx

```tsx
"use client";
import { useNotifications } from "@/lib/notification-context";
import NotificationItem from "./notification-item";

export default function NotificationDropdown({ onClose }: { onClose: () => void }) {
  const { notifications, markAllAsRead } = useNotifications();
  const recent = notifications.slice(0, 5);

  return (
    <div className="absolute right-0 top-12 w-96 bg-white rounded-xl shadow-xl border z-50">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <h3 className="font-bold">알림</h3>
        <button onClick={markAllAsRead} className="text-xs text-blue-600 hover:underline">모두 읽음</button>
      </div>
      <div className="max-h-80 overflow-y-auto">
        {recent.length === 0 ? (
          <p className="text-center py-8 text-gray-400 text-sm">알림이 없습니다</p>
        ) : (
          recent.map((n) => <NotificationItem key={n.id} notification={n} />)
        )}
      </div>
      <div className="border-t px-4 py-2 text-center">
        <button onClick={onClose} className="text-sm text-blue-600 hover:underline">전체 보기</button>
      </div>
    </div>
  );
}
```

## components/notification-item.tsx

```tsx
"use client";
import { Notification, NotificationType } from "@/lib/types";
import { useNotifications } from "@/lib/notification-context";

const TYPE_STYLES: Record<NotificationType, { icon: string; color: string }> = {
  info: { icon: "ℹ️", color: "bg-blue-50 border-blue-200" },
  warning: { icon: "⚠️", color: "bg-yellow-50 border-yellow-200" },
  error: { icon: "🔴", color: "bg-red-50 border-red-200" },
  success: { icon: "✅", color: "bg-green-50 border-green-200" },
};

export default function NotificationItem({ notification: n }: { notification: Notification }) {
  const { toggleReadStatus } = useNotifications();
  const style = TYPE_STYLES[n.type];
  const timeAgo = getTimeAgo(n.createdAt);

  return (
    <div onClick={() => toggleReadStatus(n.id)}
      className={`px-4 py-3 border-b cursor-pointer hover:bg-gray-50 flex gap-3 ${n.isRead ? "opacity-60" : ""}`}>
      <span className="text-lg">{style.icon}</span>
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium ${n.isRead ? "text-gray-500" : "text-gray-900"}`}>{n.title}</p>
        <p className="text-xs text-gray-400 truncate">{n.message}</p>
        <p className="text-[10px] text-gray-300 mt-1">{timeAgo}</p>
      </div>
      {!n.isRead && <span className="w-2 h-2 rounded-full bg-blue-500 mt-2 flex-shrink-0" />}
    </div>
  );
}

function getTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}
```

## components/badge.tsx

```tsx
export default function Badge({ count }: { count: number }) {
  const display = count > 99 ? "99+" : String(count);
  return (
    <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
      {display}
    </span>
  );
}
```

이 시스템은 알림 타입별 아이콘/스타일, 읽음/안읽음 토글, 모두 읽음 처리, 뱃지 카운트, 드롭다운 패널, 카테고리별 알림 설정 기능을 지원합니다.'''),

    # ═══ 5. 대시보드 다국어(i18n) ═══
    m("Next.js로 대시보드 다국어(i18n) 시스템 만들어줘 전체 코드로",
'''대시보드 다국어 시스템을 만들어 드릴게요. 언어 Context Provider, 번역 JSON(ko/en/ja), useTranslation 훅, 언어 전환 드롭다운, 동적 로케일 라우팅을 포함합니다.

## 폴더 구조

```
dashboard-i18n/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── [locale]/
│       ├── layout.tsx
│       ├── page.tsx
│       └── settings/page.tsx
├── components/
│   ├── language-switcher.tsx
│   ├── dashboard-header.tsx
│   ├── dashboard-sidebar.tsx
│   ├── stats-cards.tsx
│   └── locale-link.tsx
├── lib/
│   ├── i18n-context.tsx
│   ├── use-translation.ts
│   ├── locales.ts
│   └── translations/
│       ├── ko.json
│       ├── en.json
│       └── ja.json
└── package.json
```

## lib/translations/ko.json

```json
{
  "common": {
    "dashboard": "대시보드",
    "settings": "설정",
    "logout": "로그아웃",
    "search": "검색...",
    "save": "저장",
    "cancel": "취소",
    "language": "언어"
  },
  "sidebar": {
    "home": "홈",
    "orders": "주문 관리",
    "products": "상품 관리",
    "customers": "고객 관리",
    "analytics": "분석",
    "settings": "설정"
  },
  "stats": {
    "totalSales": "총 매출",
    "newOrders": "신규 주문",
    "visitors": "방문자",
    "conversionRate": "전환율"
  },
  "settings": {
    "title": "환경설정",
    "language": "언어 설정",
    "languageDesc": "대시보드 표시 언어를 선택하세요",
    "theme": "테마 설정",
    "themeDesc": "라이트 또는 다크 모드를 선택하세요"
  }
}
```

## lib/translations/en.json

```json
{
  "common": {
    "dashboard": "Dashboard",
    "settings": "Settings",
    "logout": "Logout",
    "search": "Search...",
    "save": "Save",
    "cancel": "Cancel",
    "language": "Language"
  },
  "sidebar": {
    "home": "Home",
    "orders": "Orders",
    "products": "Products",
    "customers": "Customers",
    "analytics": "Analytics",
    "settings": "Settings"
  },
  "stats": {
    "totalSales": "Total Sales",
    "newOrders": "New Orders",
    "visitors": "Visitors",
    "conversionRate": "Conversion Rate"
  },
  "settings": {
    "title": "Settings",
    "language": "Language",
    "languageDesc": "Select your preferred language",
    "theme": "Theme",
    "themeDesc": "Choose light or dark mode"
  }
}
```

## lib/translations/ja.json

```json
{
  "common": {
    "dashboard": "ダッシュボード",
    "settings": "設定",
    "logout": "ログアウト",
    "search": "検索...",
    "save": "保存",
    "cancel": "キャンセル",
    "language": "言語"
  },
  "sidebar": {
    "home": "ホーム",
    "orders": "注文管理",
    "products": "商品管理",
    "customers": "顧客管理",
    "analytics": "分析",
    "settings": "設定"
  },
  "stats": {
    "totalSales": "総売上",
    "newOrders": "新規注文",
    "visitors": "訪問者",
    "conversionRate": "コンバージョン率"
  },
  "settings": {
    "title": "設定",
    "language": "言語設定",
    "languageDesc": "ダッシュボードの表示言語を選択してください",
    "theme": "テーマ設定",
    "themeDesc": "ライトまたはダークモードを選択してください"
  }
}
```

## lib/locales.ts

```typescript
export const LOCALES = ["ko", "en", "ja"] as const;
export type Locale = (typeof LOCALES)[number];

export const LOCALE_LABELS: Record<Locale, string> = {
  ko: "한국어",
  en: "English",
  ja: "日本語",
};

export const DEFAULT_LOCALE: Locale = "ko";

export function isValidLocale(locale: string): locale is Locale {
  return LOCALES.includes(locale as Locale);
}
```

## lib/i18n-context.tsx

```tsx
"use client";
import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { Locale, DEFAULT_LOCALE, LOCALES } from "./locales";
import ko from "./translations/ko.json";
import en from "./translations/en.json";
import ja from "./translations/ja.json";

type TranslationMap = Record<string, Record<string, string>>;
const TRANSLATIONS: Record<Locale, TranslationMap> = { ko, en, ja };

interface I18nContextType {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextType | null>(null);

export function I18nProvider({ children, initialLocale }: { children: ReactNode; initialLocale?: Locale }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale ?? DEFAULT_LOCALE);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    document.documentElement.lang = l;
    localStorage.setItem("locale", l);
  }, []);

  const t = useCallback((key: string): string => {
    const [ns, k] = key.split(".");
    const translation = TRANSLATIONS[locale];
    return translation?.[ns]?.[k] ?? key;
  }, [locale]);

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export const useI18n = () => {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("I18nProvider 필요");
  return ctx;
};
```

## lib/use-translation.ts

```typescript
import { useI18n } from "./i18n-context";

export function useTranslation(namespace?: string) {
  const { t, locale, setLocale } = useI18n();

  const scopedT = (key: string) => {
    const fullKey = namespace ? `${namespace}.${key}` : key;
    return t(fullKey);
  };

  return { t: scopedT, locale, setLocale };
}
```

## components/language-switcher.tsx

```tsx
"use client";
import { useState, useRef, useEffect } from "react";
import { useI18n } from "@/lib/i18n-context";
import { LOCALES, LOCALE_LABELS, Locale } from "@/lib/locales";

export default function LanguageSwitcher() {
  const { locale, setLocale } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 border rounded-lg text-sm hover:bg-gray-50">
        <span>🌐</span>
        <span>{LOCALE_LABELS[locale]}</span>
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-10 bg-white border rounded-lg shadow-lg z-50 min-w-[120px]">
          {LOCALES.map((l) => (
            <button key={l} onClick={() => { setLocale(l); setOpen(false); }}
              className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${l === locale ? "font-bold text-blue-600" : ""}`}>
              {LOCALE_LABELS[l]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
```

## components/stats-cards.tsx

```tsx
"use client";
import { useTranslation } from "@/lib/use-translation";

const STATS = [
  { key: "totalSales", value: "₩12,450,000", change: "+12.5%" },
  { key: "newOrders", value: "148", change: "+8.2%" },
  { key: "visitors", value: "3,240", change: "+15.1%" },
  { key: "conversionRate", value: "4.56%", change: "+0.8%" },
];

export default function StatsCards() {
  const { t } = useTranslation("stats");

  return (
    <div className="grid grid-cols-4 gap-4">
      {STATS.map((s) => (
        <div key={s.key} className="bg-white rounded-xl shadow p-4">
          <p className="text-sm text-gray-500">{t(s.key)}</p>
          <p className="text-2xl font-bold mt-1">{s.value}</p>
          <p className="text-xs text-green-600 mt-1">{s.change}</p>
        </div>
      ))}
    </div>
  );
}
```

이 시스템은 I18nProvider로 전역 언어 상태를 관리하고, useTranslation 훅으로 네임스페이스 기반 번역을 지원하며, 언어 전환 드롭다운과 동적 로케일 라우팅을 제공합니다.'''),

    # ═══ 6. 데이터 내보내기(CSV/Excel) ═══
    m("Next.js로 대시보드 데이터 내보내기(CSV/Excel) 만들어줘 전체 코드로",
'''대시보드 데이터 내보내기 시스템을 만들어 드릴게요. CSV 생성, Excel(xlsx) 생성, 다운로드 API, 내보내기 설정 모달(날짜 범위, 컬럼 선택), 진행 표시기를 포함합니다.

## 폴더 구조

```
data-export/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       └── export/
│           ├── csv/route.ts
│           ├── excel/route.ts
│           └── status/route.ts
├── components/
│   ├── export-button.tsx
│   ├── export-modal.tsx
│   ├── column-selector.tsx
│   ├── date-range-picker.tsx
│   ├── progress-indicator.tsx
│   └── export-history.tsx
├── lib/
│   ├── types.ts
│   ├── csv-generator.ts
│   ├── excel-generator.ts
│   └── sample-data.ts
└── package.json
```

## lib/types.ts

```typescript
export interface ExportColumn {
  key: string;
  label: string;
  selected: boolean;
}

export interface ExportSettings {
  format: "csv" | "excel";
  startDate: string;
  endDate: string;
  columns: ExportColumn[];
}

export interface ExportJob {
  id: string;
  format: "csv" | "excel";
  status: "pending" | "processing" | "completed" | "failed";
  progress: number;
  fileName?: string;
  createdAt: string;
  completedAt?: string;
  rowCount?: number;
}

export interface OrderData {
  id: string;
  orderNumber: string;
  customerName: string;
  email: string;
  product: string;
  quantity: number;
  unitPrice: number;
  totalAmount: number;
  status: string;
  orderDate: string;
  shippingAddress: string;
}

export const DEFAULT_COLUMNS: ExportColumn[] = [
  { key: "orderNumber", label: "주문번호", selected: true },
  { key: "customerName", label: "고객명", selected: true },
  { key: "email", label: "이메일", selected: true },
  { key: "product", label: "상품", selected: true },
  { key: "quantity", label: "수량", selected: true },
  { key: "unitPrice", label: "단가", selected: true },
  { key: "totalAmount", label: "합계", selected: true },
  { key: "status", label: "상태", selected: true },
  { key: "orderDate", label: "주문일", selected: true },
  { key: "shippingAddress", label: "배송지", selected: false },
];
```

## lib/sample-data.ts

```typescript
import { OrderData } from "./types";

export const sampleOrders: OrderData[] = Array.from({ length: 50 }, (_, i) => ({
  id: `ord-${i + 1}`,
  orderNumber: `ORD-2025-${String(i + 1).padStart(4, "0")}`,
  customerName: ["김철수", "이영희", "박지민", "최수진", "정민호"][i % 5],
  email: `user${i + 1}@example.com`,
  product: ["프리미엄 코튼 티셔츠", "슬림핏 청바지", "캐시미어 니트", "리넨 셔츠", "울 코트"][i % 5],
  quantity: (i % 3) + 1,
  unitPrice: [39000, 59000, 89000, 45000, 199000][i % 5],
  totalAmount: [39000, 59000, 89000, 45000, 199000][i % 5] * ((i % 3) + 1),
  status: ["completed", "shipped", "processing", "pending", "cancelled"][i % 5],
  orderDate: new Date(2025, 6, 15 - (i % 30)).toISOString().split("T")[0],
  shippingAddress: `서울시 강남구 테헤란로 ${100 + i}`,
}));
```

## lib/csv-generator.ts

```typescript
import { OrderData, ExportColumn } from "./types";

export function generateCSV(data: OrderData[], columns: ExportColumn[]): string {
  const selected = columns.filter((c) => c.selected);
  const header = selected.map((c) => c.label).join(",");
  const rows = data.map((row) =>
    selected.map((col) => {
      const val = String(row[col.key as keyof OrderData] ?? "");
      return val.includes(",") || val.includes('"') || val.includes("\\n")
        ? `"${val.replace(/"/g, '""')}"` : val;
    }).join(",")
  );
  const bom = "\\uFEFF";
  return bom + [header, ...rows].join("\\n");
}
```

## lib/excel-generator.ts

```typescript
import { OrderData, ExportColumn } from "./types";

export function generateExcelXML(data: OrderData[], columns: ExportColumn[]): string {
  const selected = columns.filter((c) => c.selected);

  let xml = `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
  xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Styles>
    <Style ss:ID="header"><Font ss:Bold="1" ss:Size="11"/><Interior ss:Color="#F3F4F6" ss:Pattern="Solid"/></Style>
    <Style ss:ID="number"><NumberFormat ss:Format="#,##0"/></Style>
  </Styles>
  <Worksheet ss:Name="주문내역">
    <Table>`;

  xml += "\\n      <Row>";
  selected.forEach((col) => {
    xml += `<Cell ss:StyleID="header"><Data ss:Type="String">${col.label}</Data></Cell>`;
  });
  xml += "</Row>";

  data.forEach((row) => {
    xml += "\\n      <Row>";
    selected.forEach((col) => {
      const val = row[col.key as keyof OrderData];
      const isNum = typeof val === "number";
      xml += `<Cell${isNum ? ' ss:StyleID="number"' : ""}><Data ss:Type="${isNum ? "Number" : "String"}">${val}</Data></Cell>`;
    });
    xml += "</Row>";
  });

  xml += `\\n    </Table>\\n  </Worksheet>\\n</Workbook>`;
  return xml;
}
```

## app/api/export/csv/route.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { sampleOrders } from "@/lib/sample-data";
import { generateCSV } from "@/lib/csv-generator";
import { ExportColumn, DEFAULT_COLUMNS } from "@/lib/types";

export async function POST(req: NextRequest) {
  const { startDate, endDate, columns } = await req.json() as {
    startDate?: string; endDate?: string; columns?: ExportColumn[];
  };

  let data = sampleOrders;
  if (startDate) data = data.filter((d) => d.orderDate >= startDate);
  if (endDate) data = data.filter((d) => d.orderDate <= endDate);

  const csv = generateCSV(data, columns ?? DEFAULT_COLUMNS);
  return new NextResponse(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="orders_${new Date().toISOString().split("T")[0]}.csv"`,
    },
  });
}
```

## components/export-modal.tsx

```tsx
"use client";
import { useState } from "react";
import { ExportSettings, DEFAULT_COLUMNS, ExportColumn } from "@/lib/types";
import ColumnSelector from "./column-selector";
import DateRangePicker from "./date-range-picker";
import ProgressIndicator from "./progress-indicator";

interface Props { onClose: () => void; }

export default function ExportModal({ onClose }: Props) {
  const [format, setFormat] = useState<"csv" | "excel">("csv");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [columns, setColumns] = useState<ExportColumn[]>(DEFAULT_COLUMNS);
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleExport = async () => {
    setExporting(true);
    setProgress(10);
    const endpoint = format === "csv" ? "/api/export/csv" : "/api/export/excel";
    setProgress(30);
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ startDate, endDate, columns }),
    });
    setProgress(80);
    const blob = await res.blob();
    const ext = format === "csv" ? "csv" : "xml";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `export_${new Date().toISOString().split("T")[0]}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
    setProgress(100);
    setTimeout(() => { setExporting(false); onClose(); }, 500);
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-[540px] max-h-[80vh] overflow-y-auto">
        <h2 className="text-lg font-bold mb-4">데이터 내보내기</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">파일 형식</label>
            <div className="flex gap-3">
              {(["csv", "excel"] as const).map((f) => (
                <button key={f} onClick={() => setFormat(f)}
                  className={`px-4 py-2 rounded-lg border text-sm ${format === f ? "bg-blue-600 text-white border-blue-600" : "hover:bg-gray-50"}`}>
                  {f === "csv" ? "CSV (.csv)" : "Excel (.xml)"}
                </button>
              ))}
            </div>
          </div>
          <DateRangePicker startDate={startDate} endDate={endDate} onStartChange={setStartDate} onEndChange={setEndDate} />
          <ColumnSelector columns={columns} onChange={setColumns} />
          {exporting && <ProgressIndicator progress={progress} />}
        </div>
        <div className="flex gap-3 justify-end mt-6">
          <button onClick={onClose} className="px-4 py-2 border rounded-lg hover:bg-gray-50">취소</button>
          <button onClick={handleExport} disabled={exporting}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {exporting ? "내보내는 중..." : "내보내기"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

## components/column-selector.tsx

```tsx
"use client";
import { ExportColumn } from "@/lib/types";

interface Props { columns: ExportColumn[]; onChange: (cols: ExportColumn[]) => void; }

export default function ColumnSelector({ columns, onChange }: Props) {
  const toggle = (key: string) => {
    onChange(columns.map((c) => (c.key === key ? { ...c, selected: !c.selected } : c)));
  };
  const selectAll = () => onChange(columns.map((c) => ({ ...c, selected: true })));
  const deselectAll = () => onChange(columns.map((c) => ({ ...c, selected: false })));

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-sm font-medium">내보낼 컬럼</label>
        <div className="flex gap-2 text-xs">
          <button onClick={selectAll} className="text-blue-600 hover:underline">전체 선택</button>
          <button onClick={deselectAll} className="text-gray-400 hover:underline">전체 해제</button>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {columns.map((col) => (
          <label key={col.key} className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={col.selected} onChange={() => toggle(col.key)} className="rounded" />
            {col.label}
          </label>
        ))}
      </div>
    </div>
  );
}
```

## components/progress-indicator.tsx

```tsx
"use client";

export default function ProgressIndicator({ progress }: { progress: number }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-500">
        <span>내보내기 진행 중...</span>
        <span>{progress}%</span>
      </div>
      <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className="h-full bg-blue-600 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}
```

이 시스템은 CSV/Excel 형식으로 데이터를 내보내며, 날짜 범위와 컬럼을 선택할 수 있는 모달과 진행 표시기를 제공합니다.'''),

    # ═══ 7. FAQ/고객지원 관리 ═══
    m("Next.js로 FAQ/고객지원 관리 시스템 만들어줘 전체 코드로",
'''FAQ 및 고객지원 관리 시스템을 만들어 드릴게요. FAQ CRUD(카테고리별), 아코디언 표시, 검색, 고객 문의 목록(상태: open/in-progress/resolved), 답변 기능을 포함합니다.

## 폴더 구조

```
faq-support/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       ├── faqs/
│       │   ├── route.ts
│       │   └── [id]/route.ts
│       └── inquiries/
│           ├── route.ts
│           └── [id]/
│               ├── route.ts
│               └── reply/route.ts
├── components/
│   ├── faq-accordion.tsx
│   ├── faq-form.tsx
│   ├── faq-search.tsx
│   ├── inquiry-list.tsx
│   ├── inquiry-detail.tsx
│   ├── reply-form.tsx
│   └── status-badge.tsx
├── lib/
│   ├── types.ts
│   └── store.ts
└── package.json
```

## lib/types.ts

```typescript
export type FaqCategory = "배송" | "결제" | "교환/환불" | "회원" | "상품" | "기타";
export type InquiryStatus = "open" | "in-progress" | "resolved";

export interface Faq {
  id: string;
  question: string;
  answer: string;
  category: FaqCategory;
  order: number;
  createdAt: string;
}

export interface InquiryReply {
  id: string;
  content: string;
  isAdmin: boolean;
  createdAt: string;
}

export interface Inquiry {
  id: string;
  customerName: string;
  customerEmail: string;
  subject: string;
  content: string;
  category: FaqCategory;
  status: InquiryStatus;
  replies: InquiryReply[];
  createdAt: string;
  updatedAt: string;
}
```

## lib/store.ts

```typescript
import { Faq, Inquiry, InquiryReply, InquiryStatus, FaqCategory } from "./types";

let faqs: Faq[] = [
  { id: "faq-1", question: "배송 기간은 얼마나 걸리나요?", answer: "일반 배송은 2-3일, 제주/도서산간은 5-7일 소요됩니다. 당일 오후 2시 이전 주문 시 당일 출고됩니다.", category: "배송", order: 1, createdAt: "2025-01-01T00:00:00Z" },
  { id: "faq-2", question: "교환/환불은 어떻게 하나요?", answer: "수령 후 7일 이내 교환/환불 신청 가능합니다. 마이페이지 > 주문내역에서 신청하시거나 고객센터로 연락해주세요. 단순 변심은 배송비 고객 부담입니다.", category: "교환/환불", order: 1, createdAt: "2025-01-01T00:00:00Z" },
  { id: "faq-3", question: "결제 수단은 무엇이 있나요?", answer: "신용카드, 체크카드, 계좌이체, 무통장입금, 카카오페이, 네이버페이, 토스를 지원합니다.", category: "결제", order: 1, createdAt: "2025-01-01T00:00:00Z" },
  { id: "faq-4", question: "회원 등급 혜택은 무엇인가요?", answer: "실버(5% 적립), 골드(7% 적립 + 무료배송), VIP(10% 적립 + 무료배송 + 전용 쿠폰) 등급이 있습니다.", category: "회원", order: 1, createdAt: "2025-01-01T00:00:00Z" },
];

let inquiries: Inquiry[] = [
  {
    id: "inq-1", customerName: "김철수", customerEmail: "kim@example.com",
    subject: "주문한 상품이 아직 안 왔어요", content: "5일 전에 주문했는데 배송 조회가 안 됩니다. 주문번호 ORD-2025-042 입니다.",
    category: "배송", status: "open", replies: [], createdAt: "2025-07-14T10:00:00Z", updatedAt: "2025-07-14T10:00:00Z",
  },
  {
    id: "inq-2", customerName: "이영희", customerEmail: "lee@example.com",
    subject: "색상이 다르게 왔어요", content: "네이비 색상을 주문했는데 블랙이 왔습니다. 교환 부탁드립니다.",
    category: "교환/환불", status: "in-progress",
    replies: [{ id: "r-1", content: "확인 중입니다. 내일까지 교환 절차 안내드리겠습니다.", isAdmin: true, createdAt: "2025-07-13T15:00:00Z" }],
    createdAt: "2025-07-13T09:00:00Z", updatedAt: "2025-07-13T15:00:00Z",
  },
];

export const getFaqs = (category?: FaqCategory) => category ? faqs.filter((f) => f.category === category) : faqs;
export const createFaq = (data: Omit<Faq, "id" | "createdAt">) => {
  const f: Faq = { ...data, id: `faq-${Date.now()}`, createdAt: new Date().toISOString() };
  faqs.push(f);
  return f;
};
export const updateFaq = (id: string, data: Partial<Faq>) => {
  const idx = faqs.findIndex((f) => f.id === id);
  if (idx === -1) return null;
  faqs[idx] = { ...faqs[idx], ...data };
  return faqs[idx];
};
export const deleteFaq = (id: string) => {
  const len = faqs.length;
  faqs = faqs.filter((f) => f.id !== id);
  return faqs.length < len;
};

export const getInquiries = (status?: InquiryStatus) => status ? inquiries.filter((i) => i.status === status) : inquiries;
export const getInquiry = (id: string) => inquiries.find((i) => i.id === id);
export const updateInquiryStatus = (id: string, status: InquiryStatus) => {
  const inq = inquiries.find((i) => i.id === id);
  if (!inq) return null;
  inq.status = status;
  inq.updatedAt = new Date().toISOString();
  return inq;
};
export const addReply = (id: string, content: string, isAdmin: boolean) => {
  const inq = inquiries.find((i) => i.id === id);
  if (!inq) return null;
  const reply: InquiryReply = { id: `r-${Date.now()}`, content, isAdmin, createdAt: new Date().toISOString() };
  inq.replies.push(reply);
  inq.updatedAt = reply.createdAt;
  if (isAdmin && inq.status === "open") inq.status = "in-progress";
  return reply;
};
```

## components/faq-accordion.tsx

```tsx
"use client";
import { useState } from "react";
import { Faq } from "@/lib/types";

interface Props {
  faqs: Faq[];
  onEdit?: (faq: Faq) => void;
  onDelete?: (id: string) => void;
  isAdmin?: boolean;
}

export default function FaqAccordion({ faqs, onEdit, onDelete, isAdmin }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="space-y-2">
      {faqs.map((faq) => (
        <div key={faq.id} className="border rounded-lg overflow-hidden">
          <button
            onClick={() => setOpenId(openId === faq.id ? null : faq.id)}
            className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 text-left"
          >
            <div className="flex items-center gap-2">
              <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded">{faq.category}</span>
              <span className="font-medium text-sm">{faq.question}</span>
            </div>
            <svg className={`w-5 h-5 transition-transform ${openId === faq.id ? "rotate-180" : ""}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {openId === faq.id && (
            <div className="px-4 py-3 text-sm text-gray-600 bg-white">
              <p className="whitespace-pre-line">{faq.answer}</p>
              {isAdmin && (
                <div className="flex gap-2 mt-3 pt-3 border-t">
                  <button onClick={() => onEdit?.(faq)} className="text-xs text-blue-600 hover:underline">수정</button>
                  <button onClick={() => onDelete?.(faq.id)} className="text-xs text-red-600 hover:underline">삭제</button>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

## components/faq-search.tsx

```tsx
"use client";

interface Props {
  query: string;
  onChange: (q: string) => void;
  category: string;
  onCategoryChange: (c: string) => void;
}

const CATEGORIES = ["전체", "배송", "결제", "교환/환불", "회원", "상품", "기타"];

export default function FaqSearch({ query, onChange, category, onCategoryChange }: Props) {
  return (
    <div className="flex gap-3 items-center">
      <input value={query} onChange={(e) => onChange(e.target.value)} placeholder="FAQ 검색..."
        className="flex-1 border rounded-lg px-3 py-2 text-sm" />
      <select value={category} onChange={(e) => onCategoryChange(e.target.value)}
        className="border rounded-lg px-3 py-2 text-sm">
        {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    </div>
  );
}
```

## components/inquiry-list.tsx

```tsx
"use client";
import { Inquiry, InquiryStatus } from "@/lib/types";
import StatusBadge from "./status-badge";

interface Props {
  inquiries: Inquiry[];
  onSelect: (inq: Inquiry) => void;
  statusFilter: string;
  onStatusFilter: (s: string) => void;
}

export default function InquiryList({ inquiries, onSelect, statusFilter, onStatusFilter }: Props) {
  const filtered = statusFilter === "all" ? inquiries : inquiries.filter((i) => i.status === statusFilter);

  return (
    <div>
      <div className="flex gap-2 mb-4">
        {["all", "open", "in-progress", "resolved"].map((s) => (
          <button key={s} onClick={() => onStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-xs ${statusFilter === s ? "bg-blue-600 text-white" : "bg-gray-100"}`}>
            {s === "all" ? "전체" : s === "open" ? "대기중" : s === "in-progress" ? "처리중" : "완료"}
          </button>
        ))}
      </div>
      <div className="space-y-2">
        {filtered.map((inq) => (
          <div key={inq.id} onClick={() => onSelect(inq)}
            className="border rounded-lg p-4 cursor-pointer hover:bg-gray-50 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <StatusBadge status={inq.status} />
                <span className="text-xs text-gray-400">{inq.category}</span>
              </div>
              <p className="font-medium text-sm mt-1">{inq.subject}</p>
              <p className="text-xs text-gray-400 mt-1">{inq.customerName} | {new Date(inq.createdAt).toLocaleDateString("ko")}</p>
            </div>
            <div className="text-xs text-gray-400">
              답변 {inq.replies.length}건
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

## components/status-badge.tsx

```tsx
import { InquiryStatus } from "@/lib/types";

const STYLES: Record<InquiryStatus, { label: string; color: string }> = {
  open: { label: "대기중", color: "bg-orange-100 text-orange-700" },
  "in-progress": { label: "처리중", color: "bg-blue-100 text-blue-700" },
  resolved: { label: "완료", color: "bg-green-100 text-green-700" },
};

export default function StatusBadge({ status }: { status: InquiryStatus }) {
  const { label, color } = STYLES[status];
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${color}`}>{label}</span>;
}
```

## components/reply-form.tsx

```tsx
"use client";
import { useState } from "react";

interface Props { onSubmit: (content: string) => void; }

export default function ReplyForm({ onSubmit }: Props) {
  const [content, setContent] = useState("");
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    onSubmit(content);
    setContent("");
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 mt-4">
      <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={2}
        className="flex-1 border rounded-lg px-3 py-2 text-sm" placeholder="답변을 입력하세요..." />
      <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 self-end">답변</button>
    </form>
  );
}
```

이 시스템은 FAQ 카테고리별 아코디언 표시, 검색, 관리자 CRUD, 고객 문의 상태별 필터링, 답변 기능을 모두 제공합니다.'''),

    # ═══ 8. 인증 시스템(JWT + OAuth) ═══
    m("FastAPI로 인증 시스템(JWT + OAuth) 만들어줘 전체 코드로",
'''FastAPI 기반 JWT + OAuth 인증 시스템을 만들어 드릴게요. Access/Refresh 토큰, 로그인/회원가입/토큰 갱신 엔드포인트, Google OAuth, bcrypt 해싱, 보호 라우트 데코레이터를 포함합니다.

## 폴더 구조

```
auth-system/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── jwt_handler.py
│   │   ├── password.py
│   │   ├── dependencies.py
│   │   └── oauth_google.py
│   └── routers/
│       ├── __init__.py
│       └── auth_router.py
├── requirements.txt
└── .env.example
```

## requirements.txt

```
fastapi==0.104.1
uvicorn==0.24.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6
httpx==0.25.2
pydantic-settings==2.1.0
sqlalchemy==2.0.23
```

## app/config.py

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Auth System"
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DATABASE_URL: str = "sqlite:///./auth.db"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    class Config:
        env_file = ".env"


settings = Settings()
```

## app/database.py

```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

## app/models.py

```python
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base
import uuid


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)  # None for OAuth users
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    oauth_provider = Column(String, nullable=True)
    oauth_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

## app/schemas.py

```python
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    is_active: bool
    is_admin: bool
    oauth_provider: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefresh(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    message: str
```

## app/auth/password.py

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
```

## app/auth/jwt_handler.py

```python
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from app.config import settings


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def create_token_pair(user_id: str, email: str) -> dict:
    data = {"sub": user_id, "email": email}
    access = create_access_token(data)
    refresh = create_refresh_token(data)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
```

## app/auth/dependencies.py

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.auth.jwt_handler import decode_token

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다")

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="비활성화된 계정입니다")

    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 필요합니다")
    return user
```

## app/auth/oauth_google.py

```python
import httpx
from app.config import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def get_google_auth_url() -> str:
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query}"


async def exchange_code_for_token(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        })
        return resp.json()


async def get_google_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        return resp.json()
```

## app/routers/auth_router.py

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserLogin, TokenResponse, TokenRefresh, UserResponse, MessageResponse
from app.auth.password import hash_password, verify_password
from app.auth.jwt_handler import create_token_pair, decode_token
from app.auth.dependencies import get_current_user
from app.auth.oauth_google import get_google_auth_url, exchange_code_for_token, get_google_user_info

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 사용자명입니다")

    user = User(email=data.email, username=data.username, hashed_password=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return create_token_pair(user.id, user.email)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not user.hashed_password or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다")
    return create_token_pair(user.id, user.email)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: TokenRefresh, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="유효하지 않은 리프레시 토큰입니다")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")
    return create_token_pair(user.id, user.email)


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.get("/google/login")
async def google_login():
    return {"auth_url": get_google_auth_url()}


@router.get("/google/callback", response_model=TokenResponse)
async def google_callback(code: str, db: Session = Depends(get_db)):
    token_data = await exchange_code_for_token(code)
    if "error" in token_data:
        raise HTTPException(status_code=400, detail="Google 인증 실패")

    user_info = await get_google_user_info(token_data["access_token"])
    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="이메일 정보를 가져올 수 없습니다")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            username=user_info.get("name", email.split("@")[0]),
            oauth_provider="google",
            oauth_id=user_info.get("id"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return create_token_pair(user.id, user.email)
```

## app/main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers.auth_router import router as auth_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Auth System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/")
async def root():
    return {"message": "Auth System API", "docs": "/docs"}
```

이 시스템은 JWT Access/Refresh 토큰 기반 인증, bcrypt 비밀번호 해싱, Google OAuth 연동, 보호 라우트 데코레이터(Depends)를 모두 지원합니다.'''),

    # ═══ 9. 실시간 대시보드 WebSocket API ═══
    m("FastAPI + WebSocket으로 실시간 대시보드 API 만들어줘 전체 코드로",
'''FastAPI + WebSocket 기반 실시간 대시보드 API를 만들어 드릴게요. REST 엔드포인트, WebSocket 실시간 업데이트, 백그라운드 데이터 생성, 연결 매니저, 클라이언트 브로드캐스트를 포함합니다.

## 폴더 구조

```
realtime-dashboard-api/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── connection_manager.py
│   │   └── router.py
│   ├── routers/
│   │   ├── __init__.py
│   │   └── dashboard_router.py
│   └── services/
│       ├── __init__.py
│       ├── data_generator.py
│       └── metrics_service.py
├── requirements.txt
└── static/
    └── index.html
```

## requirements.txt

```
fastapi==0.104.1
uvicorn==0.24.0
websockets==12.0
```

## app/config.py

```python
from dataclasses import dataclass


@dataclass
class Config:
    APP_NAME: str = "Realtime Dashboard API"
    WS_HEARTBEAT_INTERVAL: int = 30
    DATA_UPDATE_INTERVAL: int = 3
    MAX_CONNECTIONS: int = 100


config = Config()
```

## app/models.py

```python
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class MetricData(BaseModel):
    label: str
    value: float
    change: float
    unit: str = ""


class TimeSeriesPoint(BaseModel):
    timestamp: str
    value: float


class DashboardSnapshot(BaseModel):
    metrics: List[MetricData]
    timeSeries: List[TimeSeriesPoint]
    topProducts: List[dict]
    recentOrders: List[dict]
    timestamp: str


class WSMessage(BaseModel):
    type: str  # "snapshot" | "metric_update" | "new_order" | "alert"
    data: dict
    timestamp: str


class WSClientMessage(BaseModel):
    action: str  # "subscribe" | "unsubscribe" | "ping"
    channel: Optional[str] = None
```

## app/websocket/connection_manager.py

```python
import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}
        self._channels: Dict[str, Set[str]] = {
            "metrics": set(),
            "orders": set(),
            "alerts": set(),
            "all": set(),
        }

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self._connections[client_id] = websocket
        self._channels["all"].add(client_id)
        logger.info(f"Client connected: {client_id} (total: {self.active_count})")

    def disconnect(self, client_id: str):
        self._connections.pop(client_id, None)
        for channel in self._channels.values():
            channel.discard(client_id)
        logger.info(f"Client disconnected: {client_id} (total: {self.active_count})")

    def subscribe(self, client_id: str, channel: str):
        if channel in self._channels:
            self._channels[channel].add(client_id)

    def unsubscribe(self, client_id: str, channel: str):
        if channel in self._channels:
            self._channels[channel].discard(client_id)

    async def send_personal(self, client_id: str, message: dict):
        ws = self._connections.get(client_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(client_id)

    async def broadcast(self, message: dict, channel: str = "all"):
        targets = self._channels.get(channel, set())
        disconnected = []
        for client_id in targets:
            ws = self._connections.get(client_id)
            if ws:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(client_id)
        for cid in disconnected:
            self.disconnect(cid)

    async def broadcast_all(self, message: dict):
        await self.broadcast(message, "all")


manager = ConnectionManager()
```

## app/services/data_generator.py

```python
import random
import asyncio
from datetime import datetime, timezone
from app.websocket.connection_manager import manager


class DataGenerator:
    def __init__(self):
        self._running = False
        self._base_revenue = 12450000
        self._base_orders = 148
        self._base_visitors = 3240

    async def start(self, interval: int = 3):
        self._running = True
        while self._running:
            await self._generate_metric_update()
            if random.random() < 0.3:
                await self._generate_new_order()
            if random.random() < 0.1:
                await self._generate_alert()
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False

    async def _generate_metric_update(self):
        self._base_revenue += random.randint(-50000, 200000)
        self._base_orders += random.randint(0, 3)
        self._base_visitors += random.randint(-10, 30)

        message = {
            "type": "metric_update",
            "data": {
                "revenue": self._base_revenue,
                "orders": self._base_orders,
                "visitors": self._base_visitors,
                "conversionRate": round(random.uniform(3.5, 5.5), 2),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await manager.broadcast(message, "metrics")
        await manager.broadcast(message, "all")

    async def _generate_new_order(self):
        products = ["프리미엄 코튼 티셔츠", "슬림핏 청바지", "캐시미어 니트", "리넨 셔츠", "울 코트"]
        customers = ["김철수", "이영희", "박지민", "최수진", "정민호"]
        message = {
            "type": "new_order",
            "data": {
                "orderId": f"ORD-{random.randint(1000, 9999)}",
                "customer": random.choice(customers),
                "product": random.choice(products),
                "amount": random.choice([39000, 59000, 89000, 45000, 199000]),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await manager.broadcast(message, "orders")
        await manager.broadcast(message, "all")

    async def _generate_alert(self):
        alerts = [
            {"level": "warning", "message": "재고 부족: 프리미엄 코튼 티셔츠 (M)"},
            {"level": "info", "message": "일 매출 목표 80% 달성"},
            {"level": "error", "message": "결제 모듈 응답 지연 (2초 초과)"},
        ]
        alert = random.choice(alerts)
        message = {
            "type": "alert",
            "data": alert,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await manager.broadcast(message, "alerts")
        await manager.broadcast(message, "all")


data_generator = DataGenerator()
```

## app/services/metrics_service.py

```python
from datetime import datetime, timedelta, timezone
import random


def get_dashboard_snapshot() -> dict:
    now = datetime.now(timezone.utc)
    time_series = []
    for i in range(24):
        ts = now - timedelta(hours=23 - i)
        time_series.append({
            "timestamp": ts.strftime("%H:00"),
            "value": random.randint(200000, 800000),
        })

    return {
        "metrics": [
            {"label": "총 매출", "value": 12450000, "change": 12.5, "unit": "원"},
            {"label": "신규 주문", "value": 148, "change": 8.2, "unit": "건"},
            {"label": "방문자", "value": 3240, "change": 15.1, "unit": "명"},
            {"label": "전환율", "value": 4.56, "change": 0.8, "unit": "%"},
        ],
        "timeSeries": time_series,
        "topProducts": [
            {"name": "프리미엄 코튼 티셔츠", "sales": 342, "revenue": 13338000},
            {"name": "슬림핏 청바지", "sales": 218, "revenue": 12862000},
            {"name": "캐시미어 니트", "sales": 156, "revenue": 13884000},
        ],
        "recentOrders": [
            {"id": "ORD-2025-0148", "customer": "김철수", "amount": 89000, "status": "completed"},
            {"id": "ORD-2025-0147", "customer": "이영희", "amount": 59000, "status": "shipped"},
            {"id": "ORD-2025-0146", "customer": "박지민", "amount": 199000, "status": "processing"},
        ],
        "timestamp": now.isoformat(),
    }
```

## app/websocket/router.py

```python
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.connection_manager import manager

router = APIRouter()


@router.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    client_id = str(uuid.uuid4())[:8]
    await manager.connect(websocket, client_id)

    await manager.send_personal(client_id, {
        "type": "connected",
        "data": {"clientId": client_id, "activeConnections": manager.active_count},
        "timestamp": "",
    })

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "subscribe":
                manager.subscribe(client_id, data.get("channel", "all"))
                await manager.send_personal(client_id, {"type": "subscribed", "data": {"channel": data.get("channel")}, "timestamp": ""})
            elif action == "unsubscribe":
                manager.unsubscribe(client_id, data.get("channel", ""))
            elif action == "ping":
                await manager.send_personal(client_id, {"type": "pong", "data": {}, "timestamp": ""})
    except WebSocketDisconnect:
        manager.disconnect(client_id)
```

## app/routers/dashboard_router.py

```python
from fastapi import APIRouter
from app.services.metrics_service import get_dashboard_snapshot
from app.websocket.connection_manager import manager

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/snapshot")
async def get_snapshot():
    return get_dashboard_snapshot()


@router.get("/connections")
async def get_connections():
    return {"activeConnections": manager.active_count}
```

## app/main.py

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routers.dashboard_router import router as dashboard_router
from app.websocket.router import router as ws_router
from app.services.data_generator import data_generator
from app.config import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(data_generator.start(config.DATA_UPDATE_INTERVAL))
    yield
    data_generator.stop()
    task.cancel()


app = FastAPI(title=config.APP_NAME, version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(dashboard_router)
app.include_router(ws_router)
app.mount("/static", StaticFiles(directory="static"), name="static")
```

이 시스템은 REST API로 초기 스냅샷을 제공하고, WebSocket으로 채널 기반 실시간 업데이트를 브로드캐스트하며, 백그라운드 태스크로 데이터를 자동 생성합니다.'''),

    # ═══ 10. 블로그 CMS ═══
    m("Next.js로 블로그 CMS 만들어줘 전체 코드로",
'''블로그 CMS를 만들어 드릴게요. 마크다운 에디터가 있는 포스트 CRUD, 카테고리/태그 시스템, 임시저장/발행 상태, 대표 이미지, SEO 메타 필드, 검색/필터가 있는 포스트 목록을 포함합니다.

## 폴더 구조

```
blog-cms/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       ├── posts/
│       │   ├── route.ts
│       │   └── [slug]/route.ts
│       ├── categories/route.ts
│       └── tags/route.ts
├── components/
│   ├── post-list.tsx
│   ├── post-editor.tsx
│   ├── markdown-preview.tsx
│   ├── category-tag-selector.tsx
│   ├── seo-fields.tsx
│   ├── featured-image.tsx
│   ├── post-filters.tsx
│   └── status-selector.tsx
├── lib/
│   ├── types.ts
│   ├── store.ts
│   └── markdown.ts
└── package.json
```

## lib/types.ts

```typescript
export type PostStatus = "draft" | "published" | "archived";

export interface Category {
  id: string;
  name: string;
  slug: string;
  postCount: number;
}

export interface Tag {
  id: string;
  name: string;
  slug: string;
}

export interface SEOMeta {
  title: string;
  description: string;
  keywords: string[];
  ogImage: string;
}

export interface Post {
  id: string;
  title: string;
  slug: string;
  content: string;
  excerpt: string;
  featuredImage: string;
  category: string;
  tags: string[];
  status: PostStatus;
  seo: SEOMeta;
  author: string;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string;
}

export interface PostFormData {
  title: string;
  content: string;
  excerpt: string;
  featuredImage: string;
  category: string;
  tags: string[];
  status: PostStatus;
  seo: SEOMeta;
}
```

## lib/store.ts

```typescript
import { Post, PostFormData, Category, Tag, PostStatus } from "./types";

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9가-힣]+/g, "-").replace(/^-|-$/g, "");
}

let categories: Category[] = [
  { id: "cat-1", name: "개발", slug: "development", postCount: 2 },
  { id: "cat-2", name: "디자인", slug: "design", postCount: 1 },
  { id: "cat-3", name: "마케팅", slug: "marketing", postCount: 0 },
  { id: "cat-4", name: "비즈니스", slug: "business", postCount: 0 },
];

let tags: Tag[] = [
  { id: "tag-1", name: "React", slug: "react" },
  { id: "tag-2", name: "Next.js", slug: "nextjs" },
  { id: "tag-3", name: "TypeScript", slug: "typescript" },
  { id: "tag-4", name: "CSS", slug: "css" },
  { id: "tag-5", name: "SEO", slug: "seo" },
];

let posts: Post[] = [
  {
    id: "post-1", title: "Next.js 15에서 달라진 점", slug: "nextjs-15-changes",
    content: "# Next.js 15 주요 변경사항\\n\\nNext.js 15에서는 여러 가지 중요한 변경사항이 있습니다.\\n\\n## React 19 지원\\n\\n서버 컴포넌트가 기본값이 되었습니다.\\n\\n## Turbopack 안정화\\n\\n개발 서버 속도가 크게 향상되었습니다.\\n\\n```typescript\\n// app/page.tsx\\nexport default async function Page() {\\n  const data = await fetch(\\'https://api.example.com/data\\');\\n  return <div>{JSON.stringify(data)}</div>;\\n}\\n```\\n\\n## 캐싱 전략 변경\\n\\nfetch의 기본 캐싱 동작이 변경되었습니다.",
    excerpt: "Next.js 15의 주요 변경사항을 살펴봅니다.",
    featuredImage: "/images/nextjs15.jpg", category: "개발", tags: ["Next.js", "React"],
    status: "published",
    seo: { title: "Next.js 15 변경사항 | 개발 블로그", description: "Next.js 15에서 달라진 점을 자세히 살펴봅니다.", keywords: ["Next.js", "React", "웹개발"], ogImage: "/images/nextjs15.jpg" },
    author: "관리자", createdAt: "2025-07-01T09:00:00Z", updatedAt: "2025-07-01T09:00:00Z", publishedAt: "2025-07-01T09:00:00Z",
  },
  {
    id: "post-2", title: "TypeScript 팁 모음", slug: "typescript-tips",
    content: "# TypeScript 실전 팁\\n\\n## 유틸리티 타입 활용\\n\\n```typescript\\ntype ReadonlyUser = Readonly<User>;\\ntype PartialConfig = Partial<Config>;\\ntype PickedUser = Pick<User, \\'name\\' | \\'email\\'>;\\n```\\n\\n## 타입 가드\\n\\n```typescript\\nfunction isString(value: unknown): value is string {\\n  return typeof value === \\'string\\';\\n}\\n```",
    excerpt: "실전에서 유용한 TypeScript 팁들을 모았습니다.",
    featuredImage: "/images/typescript.jpg", category: "개발", tags: ["TypeScript"],
    status: "draft",
    seo: { title: "TypeScript 팁 | 개발 블로그", description: "TypeScript 실전 팁 모음", keywords: ["TypeScript", "프로그래밍"], ogImage: "" },
    author: "관리자", createdAt: "2025-07-10T09:00:00Z", updatedAt: "2025-07-10T09:00:00Z",
  },
];

export const getCategories = () => categories;
export const getTags = () => tags;

export const getPosts = (filters?: { status?: PostStatus; category?: string; tag?: string; q?: string }) => {
  let result = posts;
  if (filters?.status) result = result.filter((p) => p.status === filters.status);
  if (filters?.category) result = result.filter((p) => p.category === filters.category);
  if (filters?.tag) result = result.filter((p) => p.tags.includes(filters.tag));
  if (filters?.q) {
    const q = filters.q.toLowerCase();
    result = result.filter((p) => p.title.toLowerCase().includes(q) || p.content.toLowerCase().includes(q));
  }
  return result.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
};

export const getPost = (slug: string) => posts.find((p) => p.slug === slug);

export const createPost = (data: PostFormData): Post => {
  const now = new Date().toISOString();
  const post: Post = {
    id: `post-${Date.now()}`,
    ...data,
    slug: slugify(data.title),
    author: "관리자",
    createdAt: now,
    updatedAt: now,
    publishedAt: data.status === "published" ? now : undefined,
  };
  posts.push(post);
  return post;
};

export const updatePost = (slug: string, data: Partial<PostFormData>): Post | null => {
  const idx = posts.findIndex((p) => p.slug === slug);
  if (idx === -1) return null;
  const now = new Date().toISOString();
  posts[idx] = {
    ...posts[idx],
    ...data,
    updatedAt: now,
    publishedAt: data.status === "published" && !posts[idx].publishedAt ? now : posts[idx].publishedAt,
  };
  if (data.title) posts[idx].slug = slugify(data.title);
  return posts[idx];
};

export const deletePost = (slug: string): boolean => {
  const len = posts.length;
  posts = posts.filter((p) => p.slug !== slug);
  return posts.length < len;
};
```

## lib/markdown.ts

```typescript
export function parseMarkdown(md: string): string {
  let html = md;
  // Headers
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  // Bold & italic
  html = html.replace(/\\*\\*(.+?)\\*\\*/g, "<strong>$1</strong>");
  html = html.replace(/\\*(.+?)\\*/g, "<em>$1</em>");
  // Code blocks
  html = html.replace(/```(\\w*)\\n([\\s\\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
  // Inline code
  html = html.replace(/`(.+?)`/g, "<code>$1</code>");
  // Links
  html = html.replace(/\\[(.+?)\\]\\((.+?)\\)/g, '<a href="$2">$1</a>');
  // Line breaks
  html = html.replace(/\\n\\n/g, "</p><p>");
  html = `<p>${html}</p>`;
  return html;
}
```

## components/post-editor.tsx

```tsx
"use client";
import { useState } from "react";
import { PostFormData, PostStatus, SEOMeta } from "@/lib/types";
import MarkdownPreview from "./markdown-preview";
import CategoryTagSelector from "./category-tag-selector";
import SeoFields from "./seo-fields";
import FeaturedImage from "./featured-image";
import StatusSelector from "./status-selector";

interface Props {
  initial?: PostFormData & { slug?: string };
  onSave: (data: PostFormData) => void;
  onCancel: () => void;
}

export default function PostEditor({ initial, onSave, onCancel }: Props) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [content, setContent] = useState(initial?.content ?? "");
  const [excerpt, setExcerpt] = useState(initial?.excerpt ?? "");
  const [featuredImage, setFeaturedImage] = useState(initial?.featuredImage ?? "");
  const [category, setCategory] = useState(initial?.category ?? "");
  const [tags, setTags] = useState<string[]>(initial?.tags ?? []);
  const [status, setStatus] = useState<PostStatus>(initial?.status ?? "draft");
  const [seo, setSeo] = useState<SEOMeta>(initial?.seo ?? { title: "", description: "", keywords: [], ogImage: "" });
  const [showPreview, setShowPreview] = useState(false);

  const handleSave = () => {
    onSave({ title, content, excerpt, featuredImage, category, tags, status, seo });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">{initial ? "포스트 수정" : "새 포스트"}</h2>
        <div className="flex gap-2">
          <button onClick={() => setShowPreview(!showPreview)}
            className="px-3 py-1.5 text-sm border rounded-lg hover:bg-gray-50">
            {showPreview ? "에디터" : "미리보기"}
          </button>
          <StatusSelector status={status} onChange={setStatus} />
        </div>
      </div>

      <div>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="포스트 제목"
          className="w-full text-2xl font-bold border-0 border-b-2 pb-2 focus:outline-none focus:border-blue-500" />
      </div>

      <div>
        <input value={excerpt} onChange={(e) => setExcerpt(e.target.value)} placeholder="요약 (미리보기에 표시됩니다)"
          className="w-full border rounded-lg px-3 py-2 text-sm" />
      </div>

      {showPreview ? (
        <MarkdownPreview content={content} />
      ) : (
        <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={20}
          className="w-full border rounded-lg px-4 py-3 font-mono text-sm resize-y"
          placeholder="마크다운으로 작성하세요..." />
      )}

      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-4">
          <FeaturedImage url={featuredImage} onChange={setFeaturedImage} />
          <CategoryTagSelector category={category} tags={tags} onCategoryChange={setCategory} onTagsChange={setTags} />
        </div>
        <SeoFields seo={seo} onChange={setSeo} title={title} />
      </div>

      <div className="flex gap-3 justify-end">
        <button onClick={onCancel} className="px-4 py-2 border rounded-lg hover:bg-gray-50">취소</button>
        <button onClick={handleSave} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          {status === "published" ? "발행하기" : "저장하기"}
        </button>
      </div>
    </div>
  );
}
```

## components/markdown-preview.tsx

```tsx
"use client";
import { parseMarkdown } from "@/lib/markdown";

export default function MarkdownPreview({ content }: { content: string }) {
  const html = parseMarkdown(content);
  return (
    <div className="prose prose-sm max-w-none border rounded-lg p-6 bg-white min-h-[400px]"
      dangerouslySetInnerHTML={{ __html: html }} />
  );
}
```

## components/category-tag-selector.tsx

```tsx
"use client";
import { useState, useEffect } from "react";
import { Category, Tag } from "@/lib/types";

interface Props {
  category: string;
  tags: string[];
  onCategoryChange: (c: string) => void;
  onTagsChange: (t: string[]) => void;
}

export default function CategoryTagSelector({ category, tags, onCategoryChange, onTagsChange }: Props) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [availableTags, setAvailableTags] = useState<Tag[]>([]);

  useEffect(() => {
    fetch("/api/categories").then((r) => r.json()).then((d) => setCategories(d.categories || []));
    fetch("/api/tags").then((r) => r.json()).then((d) => setAvailableTags(d.tags || []));
  }, []);

  const toggleTag = (tagName: string) => {
    if (tags.includes(tagName)) onTagsChange(tags.filter((t) => t !== tagName));
    else onTagsChange([...tags, tagName]);
  };

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-sm font-medium mb-1">카테고리</label>
        <select value={category} onChange={(e) => onCategoryChange(e.target.value)}
          className="w-full border rounded-lg px-3 py-2 text-sm">
          <option value="">선택안함</option>
          {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">태그</label>
        <div className="flex flex-wrap gap-2">
          {availableTags.map((t) => (
            <button key={t.id} type="button" onClick={() => toggleTag(t.name)}
              className={`px-3 py-1 rounded-full text-xs border ${tags.includes(t.name) ? "bg-blue-600 text-white border-blue-600" : "hover:bg-gray-50"}`}>
              {t.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
```

## components/seo-fields.tsx

```tsx
"use client";
import { SEOMeta } from "@/lib/types";

interface Props {
  seo: SEOMeta;
  onChange: (s: SEOMeta) => void;
  title: string;
}

export default function SeoFields({ seo, onChange, title }: Props) {
  const autoFill = () => {
    onChange({
      ...seo,
      title: seo.title || `${title} | 블로그`,
      description: seo.description || title,
    });
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium">SEO 설정</label>
        <button type="button" onClick={autoFill} className="text-xs text-blue-600 hover:underline">자동 채우기</button>
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">메타 제목</label>
        <input value={seo.title} onChange={(e) => onChange({ ...seo, title: e.target.value })}
          className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="검색 결과에 표시될 제목" />
        <p className="text-[10px] text-gray-400 mt-1">{seo.title.length}/60자</p>
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">메타 설명</label>
        <textarea value={seo.description} onChange={(e) => onChange({ ...seo, description: e.target.value })} rows={2}
          className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="검색 결과에 표시될 설명" />
        <p className="text-[10px] text-gray-400 mt-1">{seo.description.length}/160자</p>
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">키워드 (쉼표 구분)</label>
        <input value={seo.keywords.join(", ")} onChange={(e) => onChange({ ...seo, keywords: e.target.value.split(",").map((k) => k.trim()).filter(Boolean) })}
          className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Next.js, React, 웹개발" />
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">OG 이미지 URL</label>
        <input value={seo.ogImage} onChange={(e) => onChange({ ...seo, ogImage: e.target.value })}
          className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="소셜 미디어 공유 시 표시될 이미지" />
      </div>
      {/* SEO 미리보기 */}
      <div className="border rounded-lg p-3 bg-gray-50">
        <p className="text-xs text-gray-400 mb-1">검색 결과 미리보기</p>
        <p className="text-blue-700 text-sm font-medium truncate">{seo.title || "제목 없음"}</p>
        <p className="text-green-700 text-xs">https://example.com/blog/post-slug</p>
        <p className="text-xs text-gray-500 line-clamp-2">{seo.description || "설명 없음"}</p>
      </div>
    </div>
  );
}
```

## components/post-list.tsx

```tsx
"use client";
import { Post, PostStatus } from "@/lib/types";

interface Props {
  posts: Post[];
  onEdit: (slug: string) => void;
  onDelete: (slug: string) => void;
}

const STATUS_STYLES: Record<PostStatus, string> = {
  draft: "bg-yellow-100 text-yellow-700",
  published: "bg-green-100 text-green-700",
  archived: "bg-gray-100 text-gray-500",
};

const STATUS_LABELS: Record<PostStatus, string> = {
  draft: "임시저장",
  published: "발행됨",
  archived: "보관됨",
};

export default function PostList({ posts, onEdit, onDelete }: Props) {
  return (
    <div className="bg-white rounded-xl shadow overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="text-left px-4 py-3">제목</th>
            <th className="text-left px-4 py-3">카테고리</th>
            <th className="text-center px-4 py-3">상태</th>
            <th className="text-left px-4 py-3">작성일</th>
            <th className="text-center px-4 py-3">관리</th>
          </tr>
        </thead>
        <tbody>
          {posts.map((p) => (
            <tr key={p.id} className="border-t hover:bg-gray-50">
              <td className="px-4 py-3">
                <p className="font-medium">{p.title}</p>
                <p className="text-xs text-gray-400 mt-0.5">{p.tags.map((t) => `#${t}`).join(" ")}</p>
              </td>
              <td className="px-4 py-3 text-gray-500">{p.category}</td>
              <td className="px-4 py-3 text-center">
                <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLES[p.status]}`}>
                  {STATUS_LABELS[p.status]}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-400 text-xs">{new Date(p.createdAt).toLocaleDateString("ko")}</td>
              <td className="px-4 py-3 text-center space-x-2">
                <button onClick={() => onEdit(p.slug)} className="text-blue-600 hover:underline text-xs">수정</button>
                <button onClick={() => onDelete(p.slug)} className="text-red-600 hover:underline text-xs">삭제</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

## components/featured-image.tsx

```tsx
"use client";

interface Props { url: string; onChange: (url: string) => void; }

export default function FeaturedImage({ url, onChange }: Props) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">대표 이미지</label>
      <input value={url} onChange={(e) => onChange(e.target.value)}
        className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="이미지 URL" />
      {url && (
        <div className="mt-2 relative w-full h-32 rounded-lg overflow-hidden border">
          <img src={url} alt="대표 이미지" className="w-full h-full object-cover" />
          <button onClick={() => onChange("")}
            className="absolute top-1 right-1 bg-black/50 text-white w-6 h-6 rounded-full text-xs">X</button>
        </div>
      )}
    </div>
  );
}
```

이 블로그 CMS는 마크다운 에디터/미리보기, 카테고리/태그 선택, SEO 메타 필드(제목/설명/키워드/OG이미지), 대표 이미지 관리, 임시저장/발행 상태 전환을 모두 지원합니다.'''),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mega_extra_1.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"추가 데이터 1: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
