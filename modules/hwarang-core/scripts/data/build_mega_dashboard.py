"""화랑 AI 관리자 대시보드 추가 학습 데이터"""
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
    # ═══ 1. RBAC 권한 관리 시스템 ═══
    m("Next.js로 권한 관리(RBAC) 시스템 만들어줘 전체 코드로",
'''RBAC(Role-Based Access Control) 시스템을 만들어 드릴게요. 역할 정의, 권한 매트릭스, 역할 배정 API, 인증 미들웨어까지 포함합니다.

## 폴더 구조

```
rbac-system/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       ├── roles/
│       │   ├── route.ts
│       │   └── [id]/route.ts
│       └── users/
│           └── [id]/roles/route.ts
├── components/
│   ├── role-manager.tsx
│   ├── permission-matrix.tsx
│   └── user-role-assign.tsx
├── lib/
│   ├── db.ts
│   ├── permissions.ts
│   └── with-auth.ts
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
  provider = "sqlite"
  url      = "file:./dev.db"
}

model User {
  id        String     @id @default(cuid())
  email     String     @unique
  name      String
  roles     UserRole[]
  createdAt DateTime   @default(now())
}

model Role {
  id          String           @id @default(cuid())
  name        String           @unique
  description String?
  permissions RolePermission[]
  users       UserRole[]
  createdAt   DateTime         @default(now())
}

model Permission {
  id          String           @id @default(cuid())
  resource    String
  action      String
  description String?
  roles       RolePermission[]
  @@unique([resource, action])
}

model RolePermission {
  roleId       String
  permissionId String
  role         Role       @relation(fields: [roleId], references: [id], onDelete: Cascade)
  permission   Permission @relation(fields: [permissionId], references: [id], onDelete: Cascade)
  @@id([roleId, permissionId])
}

model UserRole {
  userId String
  roleId String
  user   User   @relation(fields: [userId], references: [id], onDelete: Cascade)
  role   Role   @relation(fields: [roleId], references: [id], onDelete: Cascade)
  @@id([userId, roleId])
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/permissions.ts

```typescript
// 역할별 기본 권한 정의
export const DEFAULT_ROLES = {
  admin: {
    description: "전체 시스템 관리자",
    permissions: [
      { resource: "users", action: "create" },
      { resource: "users", action: "read" },
      { resource: "users", action: "update" },
      { resource: "users", action: "delete" },
      { resource: "roles", action: "create" },
      { resource: "roles", action: "read" },
      { resource: "roles", action: "update" },
      { resource: "roles", action: "delete" },
      { resource: "posts", action: "create" },
      { resource: "posts", action: "read" },
      { resource: "posts", action: "update" },
      { resource: "posts", action: "delete" },
      { resource: "settings", action: "read" },
      { resource: "settings", action: "update" },
    ],
  },
  editor: {
    description: "콘텐츠 편집자",
    permissions: [
      { resource: "posts", action: "create" },
      { resource: "posts", action: "read" },
      { resource: "posts", action: "update" },
      { resource: "users", action: "read" },
    ],
  },
  viewer: {
    description: "읽기 전용 사용자",
    permissions: [
      { resource: "posts", action: "read" },
      { resource: "users", action: "read" },
    ],
  },
} as const;

export type RoleName = keyof typeof DEFAULT_ROLES;

// 권한 검증 유틸
export function hasPermission(
  userPermissions: { resource: string; action: string }[],
  resource: string,
  action: string
): boolean {
  return userPermissions.some(
    (p) => p.resource === resource && p.action === action
  );
}
```

## lib/with-auth.ts

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "./db";
import { hasPermission } from "./permissions";

interface AuthOptions {
  resource: string;
  action: string;
}

// 미들웨어: 요청에서 사용자 권한 확인
export function withAuth(handler: Function, options: AuthOptions) {
  return async (request: NextRequest, context?: any) => {
    const userId = request.headers.get("x-user-id");

    if (!userId) {
      return NextResponse.json({ error: "인증이 필요합니다" }, { status: 401 });
    }

    const user = await prisma.user.findUnique({
      where: { id: userId },
      include: {
        roles: {
          include: {
            role: {
              include: {
                permissions: { include: { permission: true } },
              },
            },
          },
        },
      },
    });

    if (!user) {
      return NextResponse.json({ error: "사용자를 찾을 수 없습니다" }, { status: 404 });
    }

    // 사용자의 모든 권한 수집
    const permissions = user.roles.flatMap((ur) =>
      ur.role.permissions.map((rp) => ({
        resource: rp.permission.resource,
        action: rp.permission.action,
      }))
    );

    if (!hasPermission(permissions, options.resource, options.action)) {
      return NextResponse.json({ error: "권한이 없습니다" }, { status: 403 });
    }

    return handler(request, context, { user, permissions });
  };
}
```

## app/api/roles/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

export async function GET() {
  const roles = await prisma.role.findMany({
    include: {
      permissions: { include: { permission: true } },
      _count: { select: { users: true } },
    },
  });
  return NextResponse.json(roles);
}

export async function POST(request: Request) {
  const { name, description, permissionIds } = await request.json();

  if (!name) {
    return NextResponse.json({ error: "역할 이름은 필수입니다" }, { status: 400 });
  }

  const role = await prisma.role.create({
    data: {
      name,
      description,
      permissions: {
        create: (permissionIds || []).map((pid: string) => ({
          permissionId: pid,
        })),
      },
    },
    include: { permissions: { include: { permission: true } } },
  });

  return NextResponse.json(role, { status: 201 });
}
```

## app/api/users/[id]/roles/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

// 사용자에게 역할 배정
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const { roleId } = await request.json();

  const existing = await prisma.userRole.findUnique({
    where: { userId_roleId: { userId: id, roleId } },
  });

  if (existing) {
    return NextResponse.json({ error: "이미 배정된 역할입니다" }, { status: 409 });
  }

  const assignment = await prisma.userRole.create({
    data: { userId: id, roleId },
    include: { role: true },
  });

  return NextResponse.json(assignment, { status: 201 });
}

// 사용자의 역할 제거
export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const { roleId } = await request.json();

  await prisma.userRole.delete({
    where: { userId_roleId: { userId: id, roleId } },
  });

  return new Response(null, { status: 204 });
}
```

## components/permission-matrix.tsx

```tsx
"use client";

import { useState, useEffect } from "react";

interface Permission { id: string; resource: string; action: string; }
interface Role { id: string; name: string; permissions: { permission: Permission }[]; }

export function PermissionMatrix() {
  const [roles, setRoles] = useState<Role[]>([]);
  const resources = ["users", "posts", "roles", "settings"];
  const actions = ["create", "read", "update", "delete"];

  useEffect(() => {
    fetch("/api/roles").then((r) => r.json()).then(setRoles);
  }, []);

  const hasPermission = (role: Role, resource: string, action: string) =>
    role.permissions.some(
      (p) => p.permission.resource === resource && p.permission.action === action
    );

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-gray-50">
            <th className="p-3 text-left font-semibold">리소스/액션</th>
            {roles.map((role) => (
              <th key={role.id} className="p-3 text-center font-semibold capitalize">
                {role.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {resources.flatMap((resource) =>
            actions.map((action) => (
              <tr key={`${resource}-${action}`} className="border-t hover:bg-gray-50">
                <td className="p-3 font-mono text-xs">{resource}.{action}</td>
                {roles.map((role) => (
                  <td key={role.id} className="p-3 text-center">
                    {hasPermission(role, resource, action) ? (
                      <span className="inline-block w-5 h-5 bg-green-500 rounded-full" />
                    ) : (
                      <span className="inline-block w-5 h-5 bg-gray-200 rounded-full" />
                    )}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
```

## components/role-manager.tsx

```tsx
"use client";

import { useState, useEffect } from "react";

interface Role { id: string; name: string; description: string; _count: { users: number }; }

export function RoleManager() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const fetchRoles = () => fetch("/api/roles").then((r) => r.json()).then(setRoles);

  useEffect(() => { fetchRoles(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await fetch("/api/roles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim(), description }),
    });
    setName("");
    setDescription("");
    fetchRoles();
  };

  return (
    <div className="space-y-6">
      <form onSubmit={handleCreate} className="flex gap-3">
        <input value={name} onChange={(e) => setName(e.target.value)}
          placeholder="역할 이름" className="px-4 py-2 border rounded-lg flex-1" />
        <input value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder="설명" className="px-4 py-2 border rounded-lg flex-1" />
        <button type="submit" className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          추가
        </button>
      </form>
      <div className="grid gap-3">
        {roles.map((role) => (
          <div key={role.id} className="flex items-center justify-between p-4 bg-white border rounded-xl">
            <div>
              <h3 className="font-semibold">{role.name}</h3>
              <p className="text-sm text-gray-500">{role.description}</p>
            </div>
            <span className="text-sm text-gray-400">{role._count?.users || 0}명 배정됨</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

역할(admin/editor/viewer) 정의, 권한 매트릭스 시각화, 사용자 역할 배정 API, withAuth 미들웨어가 모두 포함된 완전한 RBAC 시스템입니다.'''),

    # ═══ 2. 감사 로그(Audit Log) 시스템 ═══
    m("Next.js로 감사 로그(Audit Log) 시스템 만들어줘 전체 코드로",
'''감사 로그(Audit Log) 시스템을 만들어 드릴게요. 모든 액션을 기록하고, 필터/검색/CSV 내보내기까지 지원합니다.

## 폴더 구조

```
audit-log-system/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       ├── audit-logs/
│       │   ├── route.ts
│       │   └── [id]/route.ts
│       └── audit-logs/export/route.ts
├── components/
│   ├── audit-log-table.tsx
│   ├── audit-log-filters.tsx
│   └── audit-log-detail.tsx
├── lib/
│   ├── db.ts
│   └── audit.ts
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
  provider = "sqlite"
  url      = "file:./dev.db"
}

model AuditLog {
  id         String   @id @default(cuid())
  action     String   // CREATE, UPDATE, DELETE, LOGIN, LOGOUT
  resource   String   // users, posts, settings 등
  resourceId String?
  userId     String
  userName   String
  userEmail  String
  ip         String?
  userAgent  String?
  oldData    String?  // JSON string
  newData    String?  // JSON string
  metadata   String?  // JSON string - 추가 정보
  createdAt  DateTime @default(now())

  @@index([action])
  @@index([resource])
  @@index([userId])
  @@index([createdAt])
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/audit.ts

```typescript
import { prisma } from "./db";

interface AuditEntry {
  action: "CREATE" | "UPDATE" | "DELETE" | "LOGIN" | "LOGOUT";
  resource: string;
  resourceId?: string;
  userId: string;
  userName: string;
  userEmail: string;
  ip?: string;
  userAgent?: string;
  oldData?: Record<string, any>;
  newData?: Record<string, any>;
  metadata?: Record<string, any>;
}

// 감사 로그 기록 유틸
export async function logAudit(entry: AuditEntry) {
  return prisma.auditLog.create({
    data: {
      action: entry.action,
      resource: entry.resource,
      resourceId: entry.resourceId,
      userId: entry.userId,
      userName: entry.userName,
      userEmail: entry.userEmail,
      ip: entry.ip,
      userAgent: entry.userAgent,
      oldData: entry.oldData ? JSON.stringify(entry.oldData) : null,
      newData: entry.newData ? JSON.stringify(entry.newData) : null,
      metadata: entry.metadata ? JSON.stringify(entry.metadata) : null,
    },
  });
}

// 변경 사항 비교 유틸
export function diffObjects(
  oldObj: Record<string, any>,
  newObj: Record<string, any>
): Record<string, { old: any; new: any }> {
  const diff: Record<string, { old: any; new: any }> = {};
  const allKeys = new Set([...Object.keys(oldObj), ...Object.keys(newObj)]);

  for (const key of allKeys) {
    if (JSON.stringify(oldObj[key]) !== JSON.stringify(newObj[key])) {
      diff[key] = { old: oldObj[key], new: newObj[key] };
    }
  }
  return diff;
}
```

## app/api/audit-logs/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const page = parseInt(searchParams.get("page") || "1");
  const limit = parseInt(searchParams.get("limit") || "20");
  const action = searchParams.get("action");
  const resource = searchParams.get("resource");
  const userId = searchParams.get("userId");
  const startDate = searchParams.get("startDate");
  const endDate = searchParams.get("endDate");
  const search = searchParams.get("search");

  // 필터 조건 구성
  const where: any = {};
  if (action) where.action = action;
  if (resource) where.resource = resource;
  if (userId) where.userId = userId;
  if (startDate || endDate) {
    where.createdAt = {};
    if (startDate) where.createdAt.gte = new Date(startDate);
    if (endDate) where.createdAt.lte = new Date(endDate);
  }
  if (search) {
    where.OR = [
      { userName: { contains: search } },
      { userEmail: { contains: search } },
      { resource: { contains: search } },
    ];
  }

  const [logs, total] = await Promise.all([
    prisma.auditLog.findMany({
      where,
      orderBy: { createdAt: "desc" },
      skip: (page - 1) * limit,
      take: limit,
    }),
    prisma.auditLog.count({ where }),
  ]);

  return NextResponse.json({
    data: logs,
    pagination: { page, limit, total, totalPages: Math.ceil(total / limit) },
  });
}
```

## app/api/audit-logs/[id]/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const log = await prisma.auditLog.findUnique({ where: { id } });

  if (!log) {
    return NextResponse.json({ error: "로그를 찾을 수 없습니다" }, { status: 404 });
  }

  // JSON 문자열을 객체로 파싱
  return NextResponse.json({
    ...log,
    oldData: log.oldData ? JSON.parse(log.oldData) : null,
    newData: log.newData ? JSON.parse(log.newData) : null,
    metadata: log.metadata ? JSON.parse(log.metadata) : null,
  });
}
```

## app/api/audit-logs/export/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const action = searchParams.get("action");
  const resource = searchParams.get("resource");
  const startDate = searchParams.get("startDate");
  const endDate = searchParams.get("endDate");

  const where: any = {};
  if (action) where.action = action;
  if (resource) where.resource = resource;
  if (startDate || endDate) {
    where.createdAt = {};
    if (startDate) where.createdAt.gte = new Date(startDate);
    if (endDate) where.createdAt.lte = new Date(endDate);
  }

  const logs = await prisma.auditLog.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 10000, // CSV 최대 1만건
  });

  // CSV 생성
  const header = "일시,액션,리소스,리소스ID,사용자,이메일,IP\\n";
  const rows = logs.map((log) =>
    [
      log.createdAt.toISOString(),
      log.action,
      log.resource,
      log.resourceId || "",
      log.userName,
      log.userEmail,
      log.ip || "",
    ].join(",")
  ).join("\\n");

  const csv = header + rows;

  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename=audit-logs-${Date.now()}.csv`,
    },
  });
}
```

## components/audit-log-filters.tsx

```tsx
"use client";

import { useState } from "react";

interface FilterProps {
  onFilter: (filters: Record<string, string>) => void;
  onExport: () => void;
}

export function AuditLogFilters({ onFilter, onExport }: FilterProps) {
  const [action, setAction] = useState("");
  const [resource, setResource] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [search, setSearch] = useState("");

  const handleFilter = () => {
    const filters: Record<string, string> = {};
    if (action) filters.action = action;
    if (resource) filters.resource = resource;
    if (startDate) filters.startDate = startDate;
    if (endDate) filters.endDate = endDate;
    if (search) filters.search = search;
    onFilter(filters);
  };

  return (
    <div className="space-y-3 p-4 bg-gray-50 rounded-xl">
      <div className="flex flex-wrap gap-3">
        <select value={action} onChange={(e) => setAction(e.target.value)}
          className="px-3 py-2 border rounded-lg text-sm">
          <option value="">전체 액션</option>
          <option value="CREATE">CREATE</option>
          <option value="UPDATE">UPDATE</option>
          <option value="DELETE">DELETE</option>
          <option value="LOGIN">LOGIN</option>
          <option value="LOGOUT">LOGOUT</option>
        </select>
        <input type="text" value={resource} onChange={(e) => setResource(e.target.value)}
          placeholder="리소스" className="px-3 py-2 border rounded-lg text-sm" />
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
          className="px-3 py-2 border rounded-lg text-sm" />
        <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
          className="px-3 py-2 border rounded-lg text-sm" />
        <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="사용자 검색..." className="px-3 py-2 border rounded-lg text-sm flex-1" />
        <button onClick={handleFilter}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
          검색
        </button>
        <button onClick={onExport}
          className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700">
          CSV 내보내기
        </button>
      </div>
    </div>
  );
}
```

## components/audit-log-table.tsx

```tsx
"use client";

import { useState, useEffect } from "react";

interface AuditLog {
  id: string;
  action: string;
  resource: string;
  resourceId?: string;
  userName: string;
  userEmail: string;
  createdAt: string;
}

const ACTION_COLORS: Record<string, string> = {
  CREATE: "bg-green-100 text-green-800",
  UPDATE: "bg-blue-100 text-blue-800",
  DELETE: "bg-red-100 text-red-800",
  LOGIN: "bg-purple-100 text-purple-800",
  LOGOUT: "bg-gray-100 text-gray-800",
};

export function AuditLogTable({ filters }: { filters: Record<string, string> }) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);

  useEffect(() => {
    const params = new URLSearchParams({ page: String(page), limit: "20", ...filters });
    fetch(`/api/audit-logs?${params}`)
      .then((r) => r.json())
      .then((res) => { setLogs(res.data); setTotalPages(res.pagination.totalPages); });
  }, [page, filters]);

  const viewDetail = async (id: string) => {
    const res = await fetch(`/api/audit-logs/${id}`);
    setDetail(await res.json());
    setSelectedId(id);
  };

  return (
    <div className="space-y-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-gray-50">
            <th className="p-3 text-left">일시</th>
            <th className="p-3 text-left">액션</th>
            <th className="p-3 text-left">리소스</th>
            <th className="p-3 text-left">사용자</th>
            <th className="p-3 text-left">상세</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id} className="border-b hover:bg-gray-50">
              <td className="p-3 text-xs text-gray-500">
                {new Date(log.createdAt).toLocaleString("ko-KR")}
              </td>
              <td className="p-3">
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${ACTION_COLORS[log.action] || ""}`}>
                  {log.action}
                </span>
              </td>
              <td className="p-3 font-mono text-xs">{log.resource}{log.resourceId ? `/${log.resourceId}` : ""}</td>
              <td className="p-3">{log.userName}</td>
              <td className="p-3">
                <button onClick={() => viewDetail(log.id)}
                  className="text-blue-600 hover:underline text-xs">보기</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex justify-center gap-2">
        <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}
          className="px-3 py-1 border rounded disabled:opacity-40">이전</button>
        <span className="px-3 py-1 text-sm">{page} / {totalPages}</span>
        <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
          className="px-3 py-1 border rounded disabled:opacity-40">다음</button>
      </div>

      {selectedId && detail && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={() => setSelectedId(null)}>
          <div className="bg-white rounded-2xl p-6 max-w-lg w-full mx-4 max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="font-bold text-lg mb-4">로그 상세</h3>
            <dl className="space-y-2 text-sm">
              <div><dt className="font-medium text-gray-500">액션</dt><dd>{detail.action}</dd></div>
              <div><dt className="font-medium text-gray-500">리소스</dt><dd>{detail.resource}</dd></div>
              <div><dt className="font-medium text-gray-500">사용자</dt><dd>{detail.userName} ({detail.userEmail})</dd></div>
              <div><dt className="font-medium text-gray-500">IP</dt><dd>{detail.ip || "-"}</dd></div>
              {detail.oldData && (
                <div><dt className="font-medium text-gray-500">변경 전</dt>
                  <dd><pre className="bg-gray-50 p-2 rounded text-xs overflow-auto">{JSON.stringify(detail.oldData, null, 2)}</pre></dd>
                </div>
              )}
              {detail.newData && (
                <div><dt className="font-medium text-gray-500">변경 후</dt>
                  <dd><pre className="bg-gray-50 p-2 rounded text-xs overflow-auto">{JSON.stringify(detail.newData, null, 2)}</pre></dd>
                </div>
              )}
            </dl>
            <button onClick={() => setSelectedId(null)}
              className="mt-4 w-full py-2 bg-gray-100 rounded-lg hover:bg-gray-200">닫기</button>
          </div>
        </div>
      )}
    </div>
  );
}
```

모든 액션 자동 기록, 날짜/사용자/액션 필터 검색, 로그 상세 뷰, CSV 내보내기까지 완전한 감사 로그 시스템입니다.'''),

    # ═══ 3. 파일 매니저 ═══
    m("Next.js로 파일 매니저(파일 업로드/관리) 만들어줘 전체 코드로",
'''파일 매니저를 만들어 드릴게요. 파일 업로드, 폴더 탐색, 파일 미리보기, 드래그 앤 드롭까지 포함합니다.

## 폴더 구조

```
file-manager/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       ├── files/
│       │   ├── route.ts
│       │   └── [id]/route.ts
│       ├── files/upload/route.ts
│       └── folders/route.ts
├── components/
│   ├── file-manager.tsx
│   ├── folder-tree.tsx
│   ├── file-grid.tsx
│   ├── file-preview.tsx
│   └── drop-zone.tsx
├── lib/
│   ├── db.ts
│   └── file-utils.ts
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
  provider = "sqlite"
  url      = "file:./dev.db"
}

model Folder {
  id        String   @id @default(cuid())
  name      String
  parentId  String?
  parent    Folder?  @relation("FolderTree", fields: [parentId], references: [id])
  children  Folder[] @relation("FolderTree")
  files     File[]
  createdAt DateTime @default(now())
}

model File {
  id        String   @id @default(cuid())
  name      String
  mimeType  String
  size      Int
  path      String   // 서버 저장 경로
  folderId  String?
  folder    Folder?  @relation(fields: [folderId], references: [id])
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/file-utils.ts

```typescript
import path from "path";
import fs from "fs/promises";

const UPLOAD_DIR = path.join(process.cwd(), "uploads");

// 업로드 디렉토리 확보
export async function ensureUploadDir() {
  await fs.mkdir(UPLOAD_DIR, { recursive: true });
  return UPLOAD_DIR;
}

// 고유 파일명 생성
export function uniqueFileName(originalName: string): string {
  const ext = path.extname(originalName);
  const base = path.basename(originalName, ext);
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(2, 8);
  return `${base}-${timestamp}-${random}${ext}`;
}

// 파일 크기 포맷
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

// 미리보기 가능 여부 확인
export function isPreviewable(mimeType: string): boolean {
  return mimeType.startsWith("image/") || mimeType === "application/pdf";
}
```

## app/api/files/upload/route.ts

```typescript
import { prisma } from "@/lib/db";
import { ensureUploadDir, uniqueFileName } from "@/lib/file-utils";
import { NextResponse } from "next/server";
import path from "path";
import fs from "fs/promises";

export async function POST(request: Request) {
  const formData = await request.formData();
  const files = formData.getAll("files") as File[];
  const folderId = formData.get("folderId") as string | null;

  if (!files.length) {
    return NextResponse.json({ error: "파일을 선택하세요" }, { status: 400 });
  }

  const uploadDir = await ensureUploadDir();
  const results = [];

  for (const file of files) {
    const fileName = uniqueFileName(file.name);
    const filePath = path.join(uploadDir, fileName);
    const buffer = Buffer.from(await file.arrayBuffer());

    await fs.writeFile(filePath, buffer);

    const record = await prisma.file.create({
      data: {
        name: file.name,
        mimeType: file.type || "application/octet-stream",
        size: file.size,
        path: `/uploads/${fileName}`,
        folderId: folderId || null,
      },
    });
    results.push(record);
  }

  return NextResponse.json(results, { status: 201 });
}
```

## app/api/files/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const folderId = request.nextUrl.searchParams.get("folderId");

  const files = await prisma.file.findMany({
    where: { folderId: folderId || null },
    orderBy: { createdAt: "desc" },
  });

  return NextResponse.json(files);
}
```

## app/api/files/[id]/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";
import fs from "fs/promises";
import path from "path";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const file = await prisma.file.findUnique({ where: { id } });

  if (!file) {
    return NextResponse.json({ error: "파일을 찾을 수 없습니다" }, { status: 404 });
  }
  return NextResponse.json(file);
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const file = await prisma.file.findUnique({ where: { id } });

  if (!file) {
    return NextResponse.json({ error: "파일을 찾을 수 없습니다" }, { status: 404 });
  }

  // 실제 파일 삭제
  const fullPath = path.join(process.cwd(), file.path);
  try { await fs.unlink(fullPath); } catch {}

  await prisma.file.delete({ where: { id } });
  return new Response(null, { status: 204 });
}
```

## app/api/folders/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const parentId = request.nextUrl.searchParams.get("parentId");

  const folders = await prisma.folder.findMany({
    where: { parentId: parentId || null },
    include: { _count: { select: { children: true, files: true } } },
    orderBy: { name: "asc" },
  });

  return NextResponse.json(folders);
}

export async function POST(request: Request) {
  const { name, parentId } = await request.json();

  if (!name || !name.trim()) {
    return NextResponse.json({ error: "폴더 이름을 입력하세요" }, { status: 400 });
  }

  const folder = await prisma.folder.create({
    data: { name: name.trim(), parentId: parentId || null },
  });

  return NextResponse.json(folder, { status: 201 });
}
```

## components/drop-zone.tsx

```tsx
"use client";

import { useState, useRef, useCallback } from "react";

interface DropZoneProps {
  folderId?: string | null;
  onUploadComplete: () => void;
}

export function DropZone({ folderId, onUploadComplete }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const uploadFiles = async (files: FileList | File[]) => {
    setUploading(true);
    setProgress(0);
    const formData = new FormData();
    Array.from(files).forEach((f) => formData.append("files", f));
    if (folderId) formData.append("folderId", folderId);

    await fetch("/api/files/upload", { method: "POST", body: formData });
    setUploading(false);
    setProgress(100);
    onUploadComplete();
  };

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      await uploadFiles(e.dataTransfer.files);
    }
  }, [folderId]);

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
        isDragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400"
      }`}
    >
      <input ref={inputRef} type="file" multiple hidden
        onChange={(e) => e.target.files && uploadFiles(e.target.files)} />
      {uploading ? (
        <div className="space-y-2">
          <p className="text-sm text-gray-500">업로드 중...</p>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div className="bg-blue-600 h-2 rounded-full transition-all" style={{ width: `${progress}%` }} />
          </div>
        </div>
      ) : (
        <div>
          <p className="text-gray-500 font-medium">파일을 드래그하거나 클릭하여 업로드</p>
          <p className="text-xs text-gray-400 mt-1">이미지, PDF, 문서 등</p>
        </div>
      )}
    </div>
  );
}
```

## components/folder-tree.tsx

```tsx
"use client";

import { useState, useEffect } from "react";

interface Folder {
  id: string;
  name: string;
  _count: { children: number; files: number };
}

interface FolderTreeProps {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export function FolderTree({ selectedId, onSelect }: FolderTreeProps) {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [newName, setNewName] = useState("");

  const fetchFolders = () => {
    fetch("/api/folders").then((r) => r.json()).then(setFolders);
  };

  useEffect(() => { fetchFolders(); }, []);

  const createFolder = async () => {
    if (!newName.trim()) return;
    await fetch("/api/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName.trim() }),
    });
    setNewName("");
    fetchFolders();
  };

  return (
    <div className="w-64 border-r h-full p-4 space-y-3">
      <div
        onClick={() => onSelect(null)}
        className={`p-2 rounded-lg cursor-pointer text-sm font-medium ${
          selectedId === null ? "bg-blue-100 text-blue-700" : "hover:bg-gray-100"
        }`}
      >
        전체 파일
      </div>
      {folders.map((folder) => (
        <div
          key={folder.id}
          onClick={() => onSelect(folder.id)}
          className={`p-2 rounded-lg cursor-pointer text-sm flex justify-between ${
            selectedId === folder.id ? "bg-blue-100 text-blue-700" : "hover:bg-gray-100"
          }`}
        >
          <span>{folder.name}</span>
          <span className="text-xs text-gray-400">{folder._count.files}</span>
        </div>
      ))}
      <div className="flex gap-2 pt-2 border-t">
        <input value={newName} onChange={(e) => setNewName(e.target.value)}
          placeholder="새 폴더" className="flex-1 px-2 py-1 text-sm border rounded" />
        <button onClick={createFolder} className="px-2 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200">+</button>
      </div>
    </div>
  );
}
```

## components/file-grid.tsx

```tsx
"use client";

import { useState, useEffect } from "react";

interface FileItem {
  id: string;
  name: string;
  mimeType: string;
  size: number;
  path: string;
  createdAt: string;
}

interface FileGridProps {
  folderId: string | null;
  refreshKey: number;
  onPreview: (file: FileItem) => void;
}

export function FileGrid({ folderId, refreshKey, onPreview }: FileGridProps) {
  const [files, setFiles] = useState<FileItem[]>([]);

  useEffect(() => {
    const params = folderId ? `?folderId=${folderId}` : "";
    fetch(`/api/files${params}`).then((r) => r.json()).then(setFiles);
  }, [folderId, refreshKey]);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  const deleteFile = async (id: string) => {
    if (!confirm("삭제하시겠습니까?")) return;
    await fetch(`/api/files/${id}`, { method: "DELETE" });
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const isImage = (mime: string) => mime.startsWith("image/");

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
      {files.map((file) => (
        <div key={file.id}
          className="group border rounded-xl p-3 hover:shadow-md transition cursor-pointer"
          onClick={() => onPreview(file)}>
          <div className="aspect-square bg-gray-100 rounded-lg flex items-center justify-center mb-2 overflow-hidden">
            {isImage(file.mimeType) ? (
              <img src={file.path} alt={file.name} className="w-full h-full object-cover" />
            ) : (
              <span className="text-2xl text-gray-400">
                {file.mimeType.includes("pdf") ? "PDF" : "FILE"}
              </span>
            )}
          </div>
          <p className="text-xs font-medium truncate">{file.name}</p>
          <p className="text-xs text-gray-400">{formatSize(file.size)}</p>
          <button onClick={(e) => { e.stopPropagation(); deleteFile(file.id); }}
            className="text-xs text-red-500 opacity-0 group-hover:opacity-100 transition mt-1">
            삭제
          </button>
        </div>
      ))}
      {files.length === 0 && (
        <div className="col-span-full text-center py-12 text-gray-400">파일이 없습니다</div>
      )}
    </div>
  );
}
```

파일 업로드 API, 폴더 트리 탐색, 이미지/PDF 미리보기, 드래그 앤 드롭 UI, 파일 메타데이터 관리가 모두 포함된 완전한 파일 매니저입니다.'''),

    # ═══ 4. 예약/일정 관리 캘린더 ═══
    m("Next.js로 예약/일정 관리 캘린더 만들어줘 전체 코드로",
'''예약/일정 관리 캘린더를 만들어 드릴게요. 월/주/일 뷰 전환, 이벤트 CRUD, 드래그 일정 변경, 카테고리 색상 구분까지 포함합니다.

## 폴더 구조

```
calendar-app/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       └── events/
│           ├── route.ts
│           └── [id]/route.ts
├── components/
│   ├── calendar.tsx
│   ├── month-view.tsx
│   ├── week-view.tsx
│   ├── day-view.tsx
│   ├── event-modal.tsx
│   └── view-toggle.tsx
├── lib/
│   ├── db.ts
│   ├── date-utils.ts
│   └── categories.ts
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
  provider = "sqlite"
  url      = "file:./dev.db"
}

model Event {
  id          String   @id @default(cuid())
  title       String
  description String?
  startAt     DateTime
  endAt       DateTime
  allDay      Boolean  @default(false)
  category    String   @default("default") // work, personal, meeting, etc.
  color       String   @default("#3B82F6")
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt

  @@index([startAt])
  @@index([endAt])
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/categories.ts

```typescript
export const CATEGORIES = [
  { id: "work", label: "업무", color: "#3B82F6" },
  { id: "personal", label: "개인", color: "#10B981" },
  { id: "meeting", label: "회의", color: "#F59E0B" },
  { id: "holiday", label: "휴일", color: "#EF4444" },
  { id: "reminder", label: "알림", color: "#8B5CF6" },
  { id: "default", label: "기본", color: "#6B7280" },
] as const;

export function getCategoryColor(category: string): string {
  return CATEGORIES.find((c) => c.id === category)?.color || "#6B7280";
}
```

## lib/date-utils.ts

```typescript
export function getMonthDays(year: number, month: number): Date[] {
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const startOffset = firstDay.getDay(); // 0=일요일

  const days: Date[] = [];

  // 이전 달 날짜로 채움
  for (let i = startOffset - 1; i >= 0; i--) {
    days.push(new Date(year, month, -i));
  }

  // 현재 달
  for (let d = 1; d <= lastDay.getDate(); d++) {
    days.push(new Date(year, month, d));
  }

  // 다음 달로 6주 채움
  while (days.length < 42) {
    const nextDate = new Date(days[days.length - 1]);
    nextDate.setDate(nextDate.getDate() + 1);
    days.push(nextDate);
  }

  return days;
}

export function getWeekDays(date: Date): Date[] {
  const start = new Date(date);
  start.setDate(start.getDate() - start.getDay());
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    return d;
  });
}

export function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();
}

export function formatTime(date: Date): string {
  return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}
```

## app/api/events/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const start = request.nextUrl.searchParams.get("start");
  const end = request.nextUrl.searchParams.get("end");

  const where: any = {};
  if (start && end) {
    where.OR = [
      { startAt: { gte: new Date(start), lte: new Date(end) } },
      { endAt: { gte: new Date(start), lte: new Date(end) } },
      { AND: [{ startAt: { lte: new Date(start) } }, { endAt: { gte: new Date(end) } }] },
    ];
  }

  const events = await prisma.event.findMany({
    where,
    orderBy: { startAt: "asc" },
  });

  return NextResponse.json(events);
}

export async function POST(request: Request) {
  const body = await request.json();
  const { title, description, startAt, endAt, allDay, category, color } = body;

  if (!title || !startAt || !endAt) {
    return NextResponse.json({ error: "제목, 시작일, 종료일은 필수입니다" }, { status: 400 });
  }

  const event = await prisma.event.create({
    data: {
      title,
      description,
      startAt: new Date(startAt),
      endAt: new Date(endAt),
      allDay: allDay || false,
      category: category || "default",
      color: color || "#3B82F6",
    },
  });

  return NextResponse.json(event, { status: 201 });
}
```

## app/api/events/[id]/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await request.json();

  // 날짜 필드 변환
  if (body.startAt) body.startAt = new Date(body.startAt);
  if (body.endAt) body.endAt = new Date(body.endAt);

  const event = await prisma.event.update({
    where: { id },
    data: body,
  });

  return NextResponse.json(event);
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  await prisma.event.delete({ where: { id } });
  return new Response(null, { status: 204 });
}
```

## components/event-modal.tsx

```tsx
"use client";

import { useState, useEffect } from "react";
import { CATEGORIES } from "@/lib/categories";

interface EventData {
  id?: string;
  title: string;
  description: string;
  startAt: string;
  endAt: string;
  allDay: boolean;
  category: string;
  color: string;
}

interface EventModalProps {
  event: EventData | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (event: EventData) => void;
  onDelete?: (id: string) => void;
}

export function EventModal({ event, isOpen, onClose, onSave, onDelete }: EventModalProps) {
  const [form, setForm] = useState<EventData>({
    title: "", description: "", startAt: "", endAt: "",
    allDay: false, category: "default", color: "#3B82F6",
  });

  useEffect(() => {
    if (event) setForm(event);
    else setForm({
      title: "", description: "", startAt: "", endAt: "",
      allDay: false, category: "default", color: "#3B82F6",
    });
  }, [event]);

  if (!isOpen) return null;

  const handleCategoryChange = (categoryId: string) => {
    const cat = CATEGORIES.find((c) => c.id === categoryId);
    setForm({ ...form, category: categoryId, color: cat?.color || "#3B82F6" });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(form);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-2xl p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">{event?.id ? "일정 수정" : "새 일정"}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="제목" required className="w-full px-3 py-2 border rounded-lg" />
          <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="설명 (선택)" rows={2} className="w-full px-3 py-2 border rounded-lg" />
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500">시작</label>
              <input type="datetime-local" value={form.startAt}
                onChange={(e) => setForm({ ...form, startAt: e.target.value })}
                required className="w-full px-3 py-2 border rounded-lg text-sm" />
            </div>
            <div>
              <label className="text-xs text-gray-500">종료</label>
              <input type="datetime-local" value={form.endAt}
                onChange={(e) => setForm({ ...form, endAt: e.target.value })}
                required className="w-full px-3 py-2 border rounded-lg text-sm" />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.allDay}
              onChange={(e) => setForm({ ...form, allDay: e.target.checked })} />
            종일 이벤트
          </label>
          <div>
            <label className="text-xs text-gray-500 block mb-1">카테고리</label>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map((cat) => (
                <button key={cat.id} type="button" onClick={() => handleCategoryChange(cat.id)}
                  className={`px-3 py-1 rounded-full text-xs font-medium border transition ${
                    form.category === cat.id ? "ring-2 ring-offset-1" : ""
                  }`}
                  style={{ backgroundColor: cat.color + "20", color: cat.color, borderColor: cat.color }}>
                  {cat.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="flex-1 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              저장
            </button>
            {event?.id && onDelete && (
              <button type="button" onClick={() => onDelete(event.id!)}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700">삭제</button>
            )}
            <button type="button" onClick={onClose}
              className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200">취소</button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

## components/view-toggle.tsx

```tsx
"use client";

type ViewType = "month" | "week" | "day";

interface ViewToggleProps {
  current: ViewType;
  onChange: (view: ViewType) => void;
}

export function ViewToggle({ current, onChange }: ViewToggleProps) {
  const views: { key: ViewType; label: string }[] = [
    { key: "month", label: "월" },
    { key: "week", label: "주" },
    { key: "day", label: "일" },
  ];

  return (
    <div className="flex rounded-lg border overflow-hidden">
      {views.map(({ key, label }) => (
        <button key={key} onClick={() => onChange(key)}
          className={`px-4 py-2 text-sm font-medium transition ${
            current === key ? "bg-blue-600 text-white" : "bg-white hover:bg-gray-50"
          }`}>
          {label}
        </button>
      ))}
    </div>
  );
}
```

## components/month-view.tsx

```tsx
"use client";

import { getMonthDays, isSameDay } from "@/lib/date-utils";

interface Event {
  id: string;
  title: string;
  startAt: string;
  color: string;
}

interface MonthViewProps {
  year: number;
  month: number;
  events: Event[];
  onDateClick: (date: Date) => void;
  onEventClick: (event: Event) => void;
}

export function MonthView({ year, month, events, onDateClick, onEventClick }: MonthViewProps) {
  const days = getMonthDays(year, month);
  const today = new Date();
  const weekdays = ["일", "월", "화", "수", "목", "금", "토"];

  const getEventsForDay = (date: Date) =>
    events.filter((e) => isSameDay(new Date(e.startAt), date));

  return (
    <div>
      <div className="grid grid-cols-7 gap-px bg-gray-200">
        {weekdays.map((d) => (
          <div key={d} className="bg-gray-50 p-2 text-center text-xs font-semibold text-gray-500">{d}</div>
        ))}
        {days.map((date, i) => {
          const isCurrentMonth = date.getMonth() === month;
          const isToday = isSameDay(date, today);
          const dayEvents = getEventsForDay(date);

          return (
            <div key={i}
              onClick={() => onDateClick(date)}
              className={`bg-white min-h-[100px] p-1 cursor-pointer hover:bg-gray-50 transition ${
                !isCurrentMonth ? "opacity-40" : ""
              }`}>
              <span className={`inline-flex w-7 h-7 items-center justify-center text-sm rounded-full ${
                isToday ? "bg-blue-600 text-white font-bold" : ""
              }`}>
                {date.getDate()}
              </span>
              <div className="space-y-1 mt-1">
                {dayEvents.slice(0, 3).map((evt) => (
                  <div key={evt.id}
                    onClick={(e) => { e.stopPropagation(); onEventClick(evt); }}
                    className="text-xs px-1 py-0.5 rounded truncate text-white cursor-pointer"
                    style={{ backgroundColor: evt.color }}>
                    {evt.title}
                  </div>
                ))}
                {dayEvents.length > 3 && (
                  <span className="text-xs text-gray-400">+{dayEvents.length - 3}개</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

월/주/일 뷰 전환, 이벤트 CRUD 모달, 카테고리별 색상 구분, 드래그 일정 변경(PATCH API)이 포함된 완전한 캘린더 시스템입니다.'''),

    # ═══ 5. 대시보드 테마(다크모드) 시스템 ═══
    m("Next.js로 대시보드 테마(다크모드) 시스템 만들어줘 전체 코드로",
'''대시보드 테마(다크모드) 시스템을 만들어 드릴게요. ThemeProvider, CSS 변수 방식, localStorage 저장, 부드러운 전환 효과까지 포함합니다.

## 폴더 구조

```
theme-system/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   └── globals.css
├── components/
│   ├── theme-provider.tsx
│   ├── theme-toggle.tsx
│   ├── theme-selector.tsx
│   ├── dashboard-layout.tsx
│   ├── sidebar.tsx
│   └── sample-card.tsx
├── hooks/
│   └── use-theme.ts
├── lib/
│   └── theme-config.ts
├── package.json
└── .env.local
```

## lib/theme-config.ts

```typescript
export type ThemeMode = "light" | "dark" | "system";

export const THEME_KEY = "app-theme";

export const lightTheme = {
  "--bg-primary": "#ffffff",
  "--bg-secondary": "#f8fafc",
  "--bg-tertiary": "#f1f5f9",
  "--text-primary": "#0f172a",
  "--text-secondary": "#475569",
  "--text-muted": "#94a3b8",
  "--border": "#e2e8f0",
  "--border-hover": "#cbd5e1",
  "--accent": "#3b82f6",
  "--accent-hover": "#2563eb",
  "--surface": "#ffffff",
  "--surface-hover": "#f8fafc",
  "--shadow": "0 1px 3px rgba(0,0,0,0.1)",
  "--shadow-lg": "0 10px 25px rgba(0,0,0,0.1)",
} as const;

export const darkTheme = {
  "--bg-primary": "#0f172a",
  "--bg-secondary": "#1e293b",
  "--bg-tertiary": "#334155",
  "--text-primary": "#f8fafc",
  "--text-secondary": "#cbd5e1",
  "--text-muted": "#64748b",
  "--border": "#334155",
  "--border-hover": "#475569",
  "--accent": "#60a5fa",
  "--accent-hover": "#3b82f6",
  "--surface": "#1e293b",
  "--surface-hover": "#334155",
  "--shadow": "0 1px 3px rgba(0,0,0,0.3)",
  "--shadow-lg": "0 10px 25px rgba(0,0,0,0.4)",
} as const;

// 시스템 다크모드 감지
export function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
```

## components/theme-provider.tsx

```tsx
"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { ThemeMode, THEME_KEY, lightTheme, darkTheme, getSystemTheme } from "@/lib/theme-config";

interface ThemeContextType {
  mode: ThemeMode;
  resolved: "light" | "dark"; // 실제 적용된 테마
  setMode: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  mode: "system",
  resolved: "light",
  setMode: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>("system");
  const [resolved, setResolved] = useState<"light" | "dark">("light");

  // CSS 변수 적용
  const applyTheme = useCallback((theme: "light" | "dark") => {
    const vars = theme === "dark" ? darkTheme : lightTheme;
    const root = document.documentElement;

    Object.entries(vars).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });

    root.classList.remove("light", "dark");
    root.classList.add(theme);
    setResolved(theme);
  }, []);

  // 모드 변경
  const setMode = useCallback((newMode: ThemeMode) => {
    setModeState(newMode);
    localStorage.setItem(THEME_KEY, newMode);

    const effectiveTheme = newMode === "system" ? getSystemTheme() : newMode;
    applyTheme(effectiveTheme);
  }, [applyTheme]);

  // 초기 로드: localStorage에서 복원
  useEffect(() => {
    const saved = localStorage.getItem(THEME_KEY) as ThemeMode | null;
    const initial = saved || "system";
    setModeState(initial);

    const effectiveTheme = initial === "system" ? getSystemTheme() : initial;
    applyTheme(effectiveTheme);
  }, [applyTheme]);

  // 시스템 테마 변경 감지
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      if (mode === "system") {
        applyTheme(mq.matches ? "dark" : "light");
      }
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [mode, applyTheme]);

  return (
    <ThemeContext.Provider value={{ mode, resolved, setMode }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
```

## hooks/use-theme.ts

```typescript
"use client";

import { useTheme as useThemeContext } from "@/components/theme-provider";

// 편의 훅: 테마 관련 유틸
export function useThemeUtils() {
  const { mode, resolved, setMode } = useThemeContext();

  const isDark = resolved === "dark";
  const isLight = resolved === "light";

  const toggle = () => {
    if (resolved === "dark") setMode("light");
    else setMode("dark");
  };

  const cycle = () => {
    const order: ("light" | "dark" | "system")[] = ["light", "dark", "system"];
    const idx = order.indexOf(mode);
    setMode(order[(idx + 1) % order.length]);
  };

  return { mode, resolved, isDark, isLight, setMode, toggle, cycle };
}
```

## app/globals.css

```css
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

/* 테마 전환 애니메이션 */
:root {
  --transition-speed: 0.2s;
}

body {
  background-color: var(--bg-primary);
  color: var(--text-primary);
  transition:
    background-color var(--transition-speed) ease,
    color var(--transition-speed) ease;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

/* 모든 요소에 부드러운 전환 */
.theme-transition,
.theme-transition *,
.theme-transition *::before,
.theme-transition *::after {
  transition:
    background-color var(--transition-speed) ease,
    border-color var(--transition-speed) ease,
    color var(--transition-speed) ease,
    box-shadow var(--transition-speed) ease !important;
}
```

## components/theme-toggle.tsx

```tsx
"use client";

import { useTheme } from "./theme-provider";

export function ThemeToggle() {
  const { mode, resolved, setMode } = useTheme();

  const icons: Record<string, string> = { light: "sun", dark: "moon", system: "monitor" };
  const labels: Record<string, string> = { light: "라이트", dark: "다크", system: "시스템" };

  const cycle = () => {
    const order: ("light" | "dark" | "system")[] = ["light", "dark", "system"];
    const idx = order.indexOf(mode);
    setMode(order[(idx + 1) % order.length]);
  };

  return (
    <button
      onClick={cycle}
      className="flex items-center gap-2 px-3 py-2 rounded-lg transition-colors"
      style={{
        backgroundColor: "var(--surface-hover)",
        color: "var(--text-primary)",
        border: "1px solid var(--border)",
      }}
      aria-label={`현재: ${labels[mode]}. 클릭하여 전환`}
    >
      <span className="text-lg">
        {resolved === "dark" ? "🌙" : "☀️"}
      </span>
      <span className="text-sm font-medium">{labels[mode]}</span>
    </button>
  );
}
```

## components/theme-selector.tsx

```tsx
"use client";

import { useTheme } from "./theme-provider";
import type { ThemeMode } from "@/lib/theme-config";

export function ThemeSelector() {
  const { mode, setMode } = useTheme();

  const options: { value: ThemeMode; label: string; desc: string }[] = [
    { value: "light", label: "라이트", desc: "밝은 테마" },
    { value: "dark", label: "다크", desc: "어두운 테마" },
    { value: "system", label: "시스템", desc: "OS 설정 따름" },
  ];

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        테마 설정
      </h3>
      <div className="grid grid-cols-3 gap-3">
        {options.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setMode(opt.value)}
            className="p-3 rounded-xl text-center transition-all"
            style={{
              backgroundColor: mode === opt.value ? "var(--accent)" : "var(--surface)",
              color: mode === opt.value ? "#ffffff" : "var(--text-primary)",
              border: `2px solid ${mode === opt.value ? "var(--accent)" : "var(--border)"}`,
            }}
          >
            <div className="font-medium text-sm">{opt.label}</div>
            <div className="text-xs mt-1 opacity-70">{opt.desc}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
```

## app/layout.tsx

```tsx
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body className="theme-transition">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
```

## components/sample-card.tsx

```tsx
"use client";

export function SampleCard({ title, value, change }: { title: string; value: string; change: string }) {
  const isPositive = change.startsWith("+");

  return (
    <div
      className="p-5 rounded-xl transition-all hover:translate-y-[-2px]"
      style={{
        backgroundColor: "var(--surface)",
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow)",
      }}
    >
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>{title}</p>
      <p className="text-2xl font-bold mt-1" style={{ color: "var(--text-primary)" }}>{value}</p>
      <p className={`text-sm mt-2 ${isPositive ? "text-green-500" : "text-red-500"}`}>
        {change} 전월 대비
      </p>
    </div>
  );
}
```

ThemeProvider(Context), dark/light/system 3단 전환, CSS 변수 기반 스타일링, localStorage 영속화, 부드러운 전환 애니메이션이 포함된 완전한 테마 시스템입니다.'''),

    # ═══ 6. API 키 관리 시스템 ═══
    m("Next.js로 API 키 관리 시스템 만들어줘 전체 코드로",
'''API 키 관리 시스템을 만들어 드릴게요. 키 생성, 마스킹 표시, 권한 스코프, 사용량 추적, 만료일, 폐기 기능까지 포함합니다.

## 폴더 구조

```
api-key-manager/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       ├── keys/
│       │   ├── route.ts
│       │   └── [id]/
│       │       ├── route.ts
│       │       └── revoke/route.ts
│       └── keys/verify/route.ts
├── components/
│   ├── key-list.tsx
│   ├── create-key-modal.tsx
│   ├── key-usage-chart.tsx
│   └── scope-selector.tsx
├── lib/
│   ├── db.ts
│   ├── key-utils.ts
│   └── scopes.ts
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
  provider = "sqlite"
  url      = "file:./dev.db"
}

model ApiKey {
  id          String    @id @default(cuid())
  name        String
  keyHash     String    @unique  // SHA-256 해시 저장
  keyPrefix   String              // "sk_live_xxxx" 앞부분만 표시용
  scopes      String              // JSON array: ["read:users", "write:posts"]
  usageCount  Int       @default(0)
  lastUsedAt  DateTime?
  expiresAt   DateTime?
  revokedAt   DateTime?
  createdAt   DateTime  @default(now())

  usageLogs   ApiKeyUsage[]

  @@index([keyHash])
}

model ApiKeyUsage {
  id        String   @id @default(cuid())
  keyId     String
  key       ApiKey   @relation(fields: [keyId], references: [id], onDelete: Cascade)
  endpoint  String
  method    String
  status    Int
  ip        String?
  createdAt DateTime @default(now())

  @@index([keyId])
  @@index([createdAt])
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## lib/key-utils.ts

```typescript
import { randomBytes, createHash } from "crypto";

const PREFIX = "sk_live_";

// API 키 생성 (평문 + 해시)
export function generateApiKey(): { key: string; hash: string; prefix: string } {
  const raw = randomBytes(32).toString("hex"); // 64자 랜덤
  const key = `${PREFIX}${raw}`;
  const hash = hashKey(key);
  const prefix = `${PREFIX}${raw.substring(0, 8)}...${raw.substring(raw.length - 4)}`;

  return { key, hash, prefix };
}

// 키 해싱 (SHA-256)
export function hashKey(key: string): string {
  return createHash("sha256").update(key).digest("hex");
}

// 키 마스킹: sk_live_abcd1234...wxyz
export function maskKey(prefix: string): string {
  return prefix; // prefix가 이미 마스킹됨
}

// 만료 확인
export function isExpired(expiresAt: Date | null): boolean {
  if (!expiresAt) return false;
  return new Date() > expiresAt;
}

// 만료일 옵션 생성
export function getExpirationDate(days: number): Date {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date;
}
```

## lib/scopes.ts

```typescript
export const AVAILABLE_SCOPES = [
  { id: "read:users", label: "사용자 조회", group: "사용자" },
  { id: "write:users", label: "사용자 수정", group: "사용자" },
  { id: "read:posts", label: "게시물 조회", group: "게시물" },
  { id: "write:posts", label: "게시물 수정", group: "게시물" },
  { id: "read:analytics", label: "분석 조회", group: "분석" },
  { id: "read:files", label: "파일 조회", group: "파일" },
  { id: "write:files", label: "파일 업로드", group: "파일" },
  { id: "admin", label: "관리자 전체", group: "관리" },
] as const;

export type Scope = typeof AVAILABLE_SCOPES[number]["id"];

// 스코프 검증
export function hasScope(keyScopes: string[], required: string): boolean {
  if (keyScopes.includes("admin")) return true;
  return keyScopes.includes(required);
}

// 그룹별 정리
export function groupedScopes() {
  const groups: Record<string, typeof AVAILABLE_SCOPES[number][]> = {};
  for (const scope of AVAILABLE_SCOPES) {
    if (!groups[scope.group]) groups[scope.group] = [];
    groups[scope.group].push(scope);
  }
  return groups;
}
```

## app/api/keys/route.ts

```typescript
import { prisma } from "@/lib/db";
import { generateApiKey } from "@/lib/key-utils";
import { NextResponse } from "next/server";

// 키 목록 조회
export async function GET() {
  const keys = await prisma.apiKey.findMany({
    orderBy: { createdAt: "desc" },
    select: {
      id: true,
      name: true,
      keyPrefix: true,
      scopes: true,
      usageCount: true,
      lastUsedAt: true,
      expiresAt: true,
      revokedAt: true,
      createdAt: true,
    },
  });

  return NextResponse.json(
    keys.map((k) => ({ ...k, scopes: JSON.parse(k.scopes) }))
  );
}

// 새 키 생성
export async function POST(request: Request) {
  const { name, scopes, expiresInDays } = await request.json();

  if (!name || !scopes?.length) {
    return NextResponse.json({ error: "이름과 권한 스코프는 필수입니다" }, { status: 400 });
  }

  const { key, hash, prefix } = generateApiKey();

  let expiresAt = null;
  if (expiresInDays) {
    expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + expiresInDays);
  }

  const record = await prisma.apiKey.create({
    data: {
      name,
      keyHash: hash,
      keyPrefix: prefix,
      scopes: JSON.stringify(scopes),
      expiresAt,
    },
  });

  // 주의: 평문 키는 생성 시 한 번만 보여줌
  return NextResponse.json({
    id: record.id,
    name: record.name,
    key, // 이것만 평문 반환 (이후에는 해시만 저장됨)
    prefix,
    scopes,
    expiresAt,
    message: "이 키는 다시 표시되지 않습니다. 안전하게 보관하세요.",
  }, { status: 201 });
}
```

## app/api/keys/[id]/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

// 키 상세 + 사용량 조회
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const key = await prisma.apiKey.findUnique({
    where: { id },
    include: {
      usageLogs: {
        orderBy: { createdAt: "desc" },
        take: 50,
      },
    },
  });

  if (!key) {
    return NextResponse.json({ error: "키를 찾을 수 없습니다" }, { status: 404 });
  }

  return NextResponse.json({
    ...key,
    scopes: JSON.parse(key.scopes),
    keyHash: undefined, // 해시는 노출 안 함
  });
}

// 키 삭제
export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  await prisma.apiKey.delete({ where: { id } });
  return new Response(null, { status: 204 });
}
```

## app/api/keys/[id]/revoke/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

// 키 폐기 (삭제하지 않고 비활성화)
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const key = await prisma.apiKey.update({
    where: { id },
    data: { revokedAt: new Date() },
  });

  return NextResponse.json({ id: key.id, revokedAt: key.revokedAt });
}
```

## app/api/keys/verify/route.ts

```typescript
import { prisma } from "@/lib/db";
import { hashKey, isExpired } from "@/lib/key-utils";
import { hasScope } from "@/lib/scopes";
import { NextRequest, NextResponse } from "next/server";

// API 키 검증 엔드포인트
export async function POST(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "API 키가 필요합니다" }, { status: 401 });
  }

  const apiKey = authHeader.substring(7);
  const hash = hashKey(apiKey);

  const key = await prisma.apiKey.findUnique({ where: { keyHash: hash } });

  if (!key) {
    return NextResponse.json({ error: "유효하지 않은 API 키입니다" }, { status: 401 });
  }

  if (key.revokedAt) {
    return NextResponse.json({ error: "폐기된 API 키입니다" }, { status: 403 });
  }

  if (isExpired(key.expiresAt)) {
    return NextResponse.json({ error: "만료된 API 키입니다" }, { status: 403 });
  }

  const { requiredScope } = await request.json();
  const scopes = JSON.parse(key.scopes);

  if (requiredScope && !hasScope(scopes, requiredScope)) {
    return NextResponse.json({ error: "권한이 부족합니다" }, { status: 403 });
  }

  // 사용량 기록
  await prisma.apiKey.update({
    where: { id: key.id },
    data: { usageCount: { increment: 1 }, lastUsedAt: new Date() },
  });

  await prisma.apiKeyUsage.create({
    data: {
      keyId: key.id,
      endpoint: request.nextUrl.pathname,
      method: request.method,
      status: 200,
      ip: request.headers.get("x-forwarded-for") || "unknown",
    },
  });

  return NextResponse.json({ valid: true, scopes, keyId: key.id });
}
```

## components/scope-selector.tsx

```tsx
"use client";

import { AVAILABLE_SCOPES, groupedScopes } from "@/lib/scopes";

interface ScopeSelectorProps {
  selected: string[];
  onChange: (scopes: string[]) => void;
}

export function ScopeSelector({ selected, onChange }: ScopeSelectorProps) {
  const groups = groupedScopes();

  const toggle = (scopeId: string) => {
    if (selected.includes(scopeId)) {
      onChange(selected.filter((s) => s !== scopeId));
    } else {
      onChange([...selected, scopeId]);
    }
  };

  return (
    <div className="space-y-4">
      {Object.entries(groups).map(([group, scopes]) => (
        <div key={group}>
          <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">{group}</h4>
          <div className="flex flex-wrap gap-2">
            {scopes.map((scope) => (
              <button
                key={scope.id}
                type="button"
                onClick={() => toggle(scope.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
                  selected.includes(scope.id)
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white text-gray-700 border-gray-200 hover:border-gray-400"
                }`}
              >
                {scope.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

## components/create-key-modal.tsx

```tsx
"use client";

import { useState } from "react";
import { ScopeSelector } from "./scope-selector";

interface CreateKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function CreateKeyModal({ isOpen, onClose, onCreated }: CreateKeyModalProps) {
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>([]);
  const [expiresInDays, setExpiresInDays] = useState<number | null>(90);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleCreate = async () => {
    if (!name.trim() || scopes.length === 0) return;
    setLoading(true);

    const res = await fetch("/api/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, scopes, expiresInDays }),
    });
    const data = await res.json();
    setCreatedKey(data.key);
    setLoading(false);
    onCreated();
  };

  const handleClose = () => {
    setName("");
    setScopes([]);
    setCreatedKey(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={handleClose}>
      <div className="bg-white rounded-2xl p-6 w-full max-w-lg mx-4 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}>

        {createdKey ? (
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-green-600">키가 생성되었습니다!</h2>
            <p className="text-sm text-red-600 font-medium">이 키는 다시 표시되지 않습니다. 지금 복사하세요.</p>
            <div className="bg-gray-900 text-green-400 p-4 rounded-xl font-mono text-sm break-all">
              {createdKey}
            </div>
            <button
              onClick={() => { navigator.clipboard.writeText(createdKey); }}
              className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              클립보드에 복사
            </button>
            <button onClick={handleClose} className="w-full py-2 bg-gray-100 rounded-lg hover:bg-gray-200">
              닫기
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <h2 className="text-lg font-bold">새 API 키 생성</h2>
            <div>
              <label className="text-sm font-medium block mb-1">이름</label>
              <input value={name} onChange={(e) => setName(e.target.value)}
                placeholder="예: 프로덕션 서버" className="w-full px-3 py-2 border rounded-lg" />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">만료</label>
              <select value={expiresInDays || ""} onChange={(e) => setExpiresInDays(e.target.value ? Number(e.target.value) : null)}
                className="w-full px-3 py-2 border rounded-lg">
                <option value="30">30일</option>
                <option value="90">90일</option>
                <option value="180">180일</option>
                <option value="365">1년</option>
                <option value="">만료 없음</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">권한 스코프</label>
              <ScopeSelector selected={scopes} onChange={setScopes} />
            </div>
            <div className="flex gap-2">
              <button onClick={handleCreate} disabled={!name.trim() || scopes.length === 0 || loading}
                className="flex-1 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40">
                {loading ? "생성 중..." : "생성"}
              </button>
              <button onClick={handleClose} className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200">
                취소
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

## components/key-list.tsx

```tsx
"use client";

import { useState, useEffect } from "react";

interface ApiKeyItem {
  id: string;
  name: string;
  keyPrefix: string;
  scopes: string[];
  usageCount: number;
  lastUsedAt: string | null;
  expiresAt: string | null;
  revokedAt: string | null;
  createdAt: string;
}

interface KeyListProps {
  refreshKey: number;
  onCreateClick: () => void;
}

export function KeyList({ refreshKey, onCreateClick }: KeyListProps) {
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);

  const fetchKeys = () => fetch("/api/keys").then((r) => r.json()).then(setKeys);

  useEffect(() => { fetchKeys(); }, [refreshKey]);

  const revokeKey = async (id: string) => {
    if (!confirm("이 키를 폐기하시겠습니까? 이 작업은 되돌릴 수 없습니다.")) return;
    await fetch(`/api/keys/${id}/revoke`, { method: "POST" });
    fetchKeys();
  };

  const deleteKey = async (id: string) => {
    if (!confirm("이 키를 완전히 삭제하시겠습니까?")) return;
    await fetch(`/api/keys/${id}`, { method: "DELETE" });
    fetchKeys();
  };

  const isExpired = (date: string | null) => date && new Date(date) < new Date();

  const getStatus = (key: ApiKeyItem) => {
    if (key.revokedAt) return { label: "폐기됨", color: "bg-red-100 text-red-800" };
    if (isExpired(key.expiresAt)) return { label: "만료됨", color: "bg-yellow-100 text-yellow-800" };
    return { label: "활성", color: "bg-green-100 text-green-800" };
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold">API 키 관리</h2>
        <button onClick={onCreateClick}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">
          + 새 키 생성
        </button>
      </div>

      <div className="space-y-3">
        {keys.map((key) => {
          const status = getStatus(key);
          return (
            <div key={key.id} className="border rounded-xl p-4 hover:shadow-sm transition">
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">{key.name}</h3>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${status.color}`}>
                      {status.label}
                    </span>
                  </div>
                  <p className="font-mono text-sm text-gray-500 bg-gray-50 px-2 py-1 rounded">
                    {key.keyPrefix}
                  </p>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {key.scopes.map((scope) => (
                      <span key={scope} className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">
                        {scope}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="text-right text-xs text-gray-400 space-y-1">
                  <p>사용: {key.usageCount}회</p>
                  <p>마지막: {key.lastUsedAt ? new Date(key.lastUsedAt).toLocaleDateString("ko-KR") : "없음"}</p>
                  {key.expiresAt && <p>만료: {new Date(key.expiresAt).toLocaleDateString("ko-KR")}</p>}
                </div>
              </div>
              <div className="flex gap-2 mt-3 pt-3 border-t">
                {!key.revokedAt && (
                  <button onClick={() => revokeKey(key.id)}
                    className="text-xs text-orange-600 hover:underline">폐기</button>
                )}
                <button onClick={() => deleteKey(key.id)}
                  className="text-xs text-red-600 hover:underline">삭제</button>
              </div>
            </div>
          );
        })}

        {keys.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            <p>생성된 API 키가 없습니다</p>
            <button onClick={onCreateClick} className="text-blue-600 hover:underline mt-2">
              첫 번째 키 만들기
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

API 키 생성(crypto), 마스킹 표시, 권한 스코프 선택, 사용량 추적, 만료일 설정, 폐기(revoke) 기능이 모두 포함된 완전한 API 키 관리 시스템입니다.'''),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mega_dashboard.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"대시보드 추가: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
