/**
 * AI 모델 관리 API (DB + vLLM)
 *
 * GET    - AIModel 목록 + vLLM 감지 목록
 * POST   - 새 모델 등록
 * PUT    - 모델 수정
 * DELETE - 모델 삭제
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { verifyToken } from "@/lib/auth";

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";

function authenticate(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const token = authHeader?.replace("Bearer ", "") || "";
  return verifyToken(token);
}

// ─── GET ─────────────────────────────────────────────────────────
export async function GET(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || (auth.role !== "ADMIN" && auth.role !== "SUPER_ADMIN")) {
    return Response.json({ error: "권한 없음" }, { status: 403 });
  }

  // DB에서 등록된 모델
  const models = await prisma.aIModel.findMany({
    orderBy: [{ sortOrder: "asc" }, { createdAt: "desc" }],
  });

  // vLLM에서 실시간 감지
  let vllmModels: any[] = [];
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    const resp = await fetch(`${HWARANG_API_URL}/v1/models`, {
      cache: "no-store",
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (resp.ok) {
      const data = await resp.json();
      vllmModels = data.data || [];
    }
  } catch {}

  // 등록된 모델의 상태 업데이트
  for (const model of models) {
    const found = vllmModels.find((v) => v.id === model.backendId);
    const newStatus = found ? "ready" : "offline";
    if (model.status !== newStatus) {
      await prisma.aIModel.update({
        where: { id: model.id },
        data: { status: newStatus, lastCheckAt: new Date() },
      });
      model.status = newStatus;
    }
  }

  return Response.json({ models, vllmModels });
}

// ─── POST (새 모델 등록) ─────────────────────────────────────────
export async function POST(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 추가 가능합니다" }, { status: 403 });
  }

  try {
    const body = await request.json();

    if (!body.name || !body.displayName || !body.backendId) {
      return Response.json({ error: "필수 필드 누락 (name, displayName, backendId)" }, { status: 400 });
    }

    // 기본 모델은 1개만
    if (body.isDefault) {
      await prisma.aIModel.updateMany({
        where: { isDefault: true },
        data: { isDefault: false },
      });
    }

    const model = await prisma.aIModel.create({
      data: {
        name: body.name,
        displayName: body.displayName,
        description: body.description || null,
        backendId: body.backendId,
        endpoint: body.endpoint || HWARANG_API_URL,
        inputMultiplier: body.inputMultiplier ?? 1.0,
        outputMultiplier: body.outputMultiplier ?? 1.0,
        maxContextLength: body.maxContextLength ?? 32768,
        maxOutputTokens: body.maxOutputTokens ?? 4096,
        category: body.category || "general",
        tier: body.tier || "standard",
        tags: body.tags || [],
        minPlan: body.minPlan || null,
        isPublic: body.isPublic ?? true,
        isDefault: body.isDefault ?? false,
        isActive: body.isActive ?? true,
        sortOrder: body.sortOrder ?? 0,
      },
    });

    return Response.json(model, { status: 201 });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

// ─── PUT (수정) ──────────────────────────────────────────────────
export async function PUT(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 수정 가능합니다" }, { status: 403 });
  }

  try {
    const body = await request.json();
    if (!body.id) {
      return Response.json({ error: "ID 필수" }, { status: 400 });
    }

    const { id, ...data } = body;

    // 기본 모델로 설정 시, 다른 모델의 isDefault 해제
    if (data.isDefault === true) {
      await prisma.aIModel.updateMany({
        where: { isDefault: true, NOT: { id } },
        data: { isDefault: false },
      });
    }

    const model = await prisma.aIModel.update({
      where: { id },
      data,
    });

    return Response.json(model);
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

// ─── DELETE ──────────────────────────────────────────────────────
export async function DELETE(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 삭제 가능합니다" }, { status: 403 });
  }

  try {
    const { id } = await request.json();
    if (!id) return Response.json({ error: "ID 필수" }, { status: 400 });

    await prisma.aIModel.delete({ where: { id } });
    return Response.json({ success: true });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
