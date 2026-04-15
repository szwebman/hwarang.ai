/**
 * 모델 관리 API - vLLM 서버에서 실제 데이터
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";

async function getDefaultModel(): Promise<string> {
  try {
    const setting = await prisma.systemSetting.findUnique({ where: { key: "default_model" } });
    return setting?.value || process.env.HWARANG_DEFAULT_MODEL || "";
  } catch {
    return process.env.HWARANG_DEFAULT_MODEL || "";
  }
}

async function saveDefaultModel(modelId: string) {
  try {
    await prisma.systemSetting.upsert({
      where: { key: "default_model" },
      update: { value: modelId },
      create: { key: "default_model", value: modelId },
    });
  } catch {}
  process.env.HWARANG_DEFAULT_MODEL = modelId;
}

export async function GET() {
  const defaultModel = await getDefaultModel();
  let availableModels: any[] = [];

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    const resp = await fetch(`${HWARANG_API_URL}/v1/models`, {
      cache: "no-store",
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (resp.ok) {
      const data = await resp.json();
      availableModels = data.data || [];
    }
  } catch {}

  // 기본 모델이 없으면 첫 번째 모델로 설정
  if (!defaultModel && availableModels.length > 0) {
    await saveDefaultModel(availableModels[0].id);
    return Response.json({ defaultModel: availableModels[0].id, availableModels, vllmUrl: HWARANG_API_URL });
  }

  return Response.json({ defaultModel, availableModels, vllmUrl: HWARANG_API_URL });
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    if (!body.defaultModel) {
      return Response.json({ error: "defaultModel 필수" }, { status: 400 });
    }
    await saveDefaultModel(body.defaultModel);
    return Response.json({ status: "updated", defaultModel: body.defaultModel });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
