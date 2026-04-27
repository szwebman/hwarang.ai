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
async function fetchVllmModels(endpoint: string): Promise<any[]> {
  try {
    const url = endpoint.replace(/\/+$/, "") + "/v1/models";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    const resp = await fetch(url, { cache: "no-store", signal: controller.signal });
    clearTimeout(timeout);
    if (!resp.ok) return [];
    const data = await resp.json();
    return (data.data || []).map((m: any) => ({ ...m, endpoint }));
  } catch {
    return [];
  }
}

export async function GET(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || (auth.role !== "ADMIN" && auth.role !== "SUPER_ADMIN")) {
    return Response.json({ error: "관리자 권한이 필요합니다" }, { status: 403 });
  }

  let models;
  try {
    models = await prisma.aIModel.findMany({
      orderBy: [{ sortOrder: "asc" }, { createdAt: "desc" }],
    });
  } catch (e: any) {
    console.error("AI 모델 조회 실패:", e?.message);
    return Response.json(
      { error: "DB 연결 오류 — AI 모델 조회 실패", detail: e?.message },
      { status: 500 }
    );
  }

  // 등록된 모델들의 endpoint 들을 모아서 각각 확인 (+ 전역 기본 endpoint)
  const endpoints = new Set<string>();
  endpoints.add(HWARANG_API_URL);
  for (const m of models) {
    if (m.endpoint) endpoints.add(m.endpoint);
  }

  // 모든 endpoint 병렬 조회
  const all = await Promise.all([...endpoints].map(fetchVllmModels));
  const vllmModels = all.flat();

  // 등록된 모델의 상태 업데이트 — backendId + endpoint 둘 다 일치해야 ready
  await Promise.all(
    models.map(async (model) => {
      const found = vllmModels.some(
        (v) => v.id === model.backendId && v.endpoint === (model.endpoint || HWARANG_API_URL)
      );
      const newStatus = found ? "ready" : "offline";
      if (model.status !== newStatus) {
        await prisma.aIModel
          .update({
            where: { id: model.id },
            data: { status: newStatus, lastCheckAt: new Date() },
          })
          .catch(() => {});
        model.status = newStatus;
      }
    })
  );

  return Response.json({
    models,
    vllmModels,
    endpoints: [...endpoints],
    diagnostics: {
      modelsRegistered: models.length,
      vllmDetected: vllmModels.length,
      endpointsChecked: endpoints.size,
    },
  });
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

    // 전역 기본 모델은 1개만
    if (body.isDefault) {
      await prisma.aIModel.updateMany({
        where: { isDefault: true },
        data: { isDefault: false },
      });
    }

    // 같은 카테고리의 도메인 기본도 1개만
    if (body.isDomainDefault) {
      await prisma.aIModel.updateMany({
        where: { category: body.category || "general", isDomainDefault: true },
        data: { isDomainDefault: false },
      });
    }

    const model = await prisma.aIModel.create({
      data: {
        name: body.name,
        displayName: body.displayName,
        description: body.description || null,
        backendId: body.backendId,
        loraName: body.loraName || null,
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
        isDomainDefault: body.isDomainDefault ?? false,
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

    // 전역 기본 모델로 설정 시 — 다른 모델의 isDefault 해제
    if (data.isDefault === true) {
      await prisma.aIModel.updateMany({
        where: { isDefault: true, NOT: { id } },
        data: { isDefault: false },
      });
    }

    // 도메인 기본으로 설정 시 — 같은 카테고리 다른 모델의 isDomainDefault 해제
    if (data.isDomainDefault === true) {
      const target = await prisma.aIModel.findUnique({
        where: { id },
        select: { category: true },
      });
      const cat = data.category || target?.category || "general";
      await prisma.aIModel.updateMany({
        where: { category: cat, isDomainDefault: true, NOT: { id } },
        data: { isDomainDefault: false },
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
