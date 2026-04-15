/**
 * Admin Models API
 * GET: vLLM에서 모델 목록 + 현재 기본 모델
 * PUT: 기본 모델 변경
 */

import { NextRequest } from "next/server";
import { readFileSync, writeFileSync, existsSync } from "fs";
import { join } from "path";

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";
const CONFIG_PATH = join(process.cwd(), ".model-config.json");

function getConfig(): { defaultModel: string } {
  try {
    if (existsSync(CONFIG_PATH)) {
      return JSON.parse(readFileSync(CONFIG_PATH, "utf-8"));
    }
  } catch {}
  // 환경변수에서
  return { defaultModel: process.env.HWARANG_DEFAULT_MODEL || "" };
}

function saveConfig(config: { defaultModel: string }) {
  writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
  // 환경변수도 업데이트 (런타임)
  process.env.HWARANG_DEFAULT_MODEL = config.defaultModel;
}

// GET /api/admin/models
export async function GET() {
  const config = getConfig();

  // vLLM에서 모델 목록 가져오기
  let availableModels: any[] = [];
  try {
    const resp = await fetch(`${HWARANG_API_URL}/v1/models`, { cache: "no-store" });
    if (resp.ok) {
      const data = await resp.json();
      availableModels = data.data || [];
    }
  } catch {}

  // 기본 모델이 설정 안 되어있으면 첫 번째 모델 자동 선택
  if (!config.defaultModel && availableModels.length > 0) {
    config.defaultModel = availableModels[0].id;
    saveConfig(config);
  }

  return Response.json({
    defaultModel: config.defaultModel,
    availableModels,
    vllmUrl: HWARANG_API_URL,
  });
}

// PUT /api/admin/models - 기본 모델 변경
export async function PUT(request: NextRequest) {
  const body = await request.json();
  const { defaultModel } = body;

  if (!defaultModel) {
    return Response.json({ error: "defaultModel is required" }, { status: 400 });
  }

  const config = { defaultModel };
  saveConfig(config);

  return Response.json({
    status: "updated",
    defaultModel,
    message: `기본 모델이 ${defaultModel}로 변경되었습니다`,
  });
}
