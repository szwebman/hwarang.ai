/**
 * 관리자 계정 관리 API
 *
 * GET  - 관리자 목록 조회 (ADMIN, SUPER_ADMIN)
 * POST - 관리자 추가 (SUPER_ADMIN만)
 * PUT  - 역할 변경 / 활성 토글 / 비밀번호 초기화 (SUPER_ADMIN만)
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { verifyToken } from "@/lib/auth";
import crypto from "crypto";

function hashPassword(password: string): string {
  return crypto.createHash("sha256").update(password).digest("hex");
}

function authenticate(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const token = authHeader?.replace("Bearer ", "") || "";
  return verifyToken(token);
}

// ─── GET: 관리자 목록 ───────────────────────────────────────────
export async function GET(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || (auth.role !== "ADMIN" && auth.role !== "SUPER_ADMIN")) {
    return Response.json({ error: "권한 없음" }, { status: 403 });
  }

  try {
    const admins = await prisma.user.findMany({
      where: { role: { in: ["ADMIN", "SUPER_ADMIN"] } },
      select: {
        id: true,
        name: true,
        email: true,
        role: true,
        isActive: true,
        createdAt: true,
      },
      orderBy: { createdAt: "desc" },
    });

    return Response.json(admins);
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

// ─── POST: 관리자 추가 ──────────────────────────────────────────
export async function POST(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 추가 가능합니다" }, { status: 403 });
  }

  try {
    const { email, name, password, role } = await request.json();

    if (!email || !password) {
      return Response.json({ error: "이메일과 비밀번호를 입력하세요" }, { status: 400 });
    }

    if (role !== "ADMIN" && role !== "SUPER_ADMIN") {
      return Response.json({ error: "유효하지 않은 역할입니다" }, { status: 400 });
    }

    const existing = await prisma.user.findUnique({ where: { email } });

    if (existing) {
      const updated = await prisma.user.update({
        where: { email },
        data: {
          role: role,
          hashedPassword: hashPassword(password),
          ...(name ? { name } : {}),
        },
        select: { id: true, name: true, email: true, role: true },
      });
      return Response.json(updated);
    }

    const user = await prisma.user.create({
      data: {
        email,
        name: name || email.split("@")[0],
        hashedPassword: hashPassword(password),
        role: role,
        isActive: true,
      },
      select: { id: true, name: true, email: true, role: true },
    });

    return Response.json(user, { status: 201 });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

// ─── PUT: 관리자 수정 (역할/활성/비밀번호) ───────────────────────
export async function PUT(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 수정할 수 있습니다" }, { status: 403 });
  }

  try {
    const { id, role, isActive, password } = await request.json();

    if (!id) {
      return Response.json({ error: "ID를 입력하세요" }, { status: 400 });
    }

    // 자기 자신 변경 방지 (역할/활성)
    if (id === auth.userId && (role !== undefined || isActive !== undefined)) {
      return Response.json({ error: "본인의 정보는 변경할 수 없습니다" }, { status: 400 });
    }

    const data: any = {};

    // 역할 변경
    if (role !== undefined) {
      if (!["USER", "ADMIN", "SUPER_ADMIN"].includes(role)) {
        return Response.json({ error: "유효하지 않은 역할입니다" }, { status: 400 });
      }
      data.role = role;
    }

    // 활성/비활성 토글
    if (isActive !== undefined) {
      data.isActive = isActive;
    }

    // 비밀번호 초기화
    if (password) {
      data.hashedPassword = hashPassword(password);
    }

    if (Object.keys(data).length === 0) {
      return Response.json({ error: "변경할 내용이 없습니다" }, { status: 400 });
    }

    const updated = await prisma.user.update({
      where: { id },
      data,
      select: { id: true, name: true, email: true, role: true, isActive: true },
    });

    return Response.json(updated);
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
