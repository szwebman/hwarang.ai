/**
 * Chat API proxy route.
 * 브라우저 → Next.js → vLLM/Hwarang API
 *
 * 모델 선택 우선순위:
 * 1. 요청에 model 지정 → 그 모델 사용
 * 2. 관리자 설정 (.model-config.json) → 기본 모델
 * 3. 환경변수 HWARANG_DEFAULT_MODEL
 * 4. vLLM의 첫 번째 모델 자동 선택
 */

import { NextRequest } from "next/server";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const HWARANG_API_URL =
  process.env.HWARANG_API_URL || "http://localhost:8000";

function getDefaultModel(): string {
  // 1. 관리자 설정 파일
  try {
    const configPath = join(process.cwd(), ".model-config.json");
    if (existsSync(configPath)) {
      const config = JSON.parse(readFileSync(configPath, "utf-8"));
      if (config.defaultModel) return config.defaultModel;
    }
  } catch {}

  // 2. 환경변수
  return process.env.HWARANG_DEFAULT_MODEL || "";
}

const SYSTEM_PROMPT = `You are Hwarang AI (화랑 AI), a helpful assistant created by Persismore.

IMPORTANT RULES:
- Always respond in the SAME LANGUAGE as the user's message.
- If the user writes in Korean, respond ONLY in Korean.
- If the user writes in English, respond ONLY in English.
- NEVER mix Chinese characters in your response unless explicitly asked.
- NEVER respond in Chinese unless the user writes in Chinese.
- You are a Korean AI assistant. Korean is your primary language.
- Be helpful, accurate, and concise.`;

export async function POST(request: NextRequest) {
  const body = await request.json();

  // 시스템 프롬프트 주입 (중국어 방지 + 언어 매칭)
  if (body.messages && body.messages.length > 0) {
    const hasSystem = body.messages[0]?.role === "system";
    if (!hasSystem) {
      body.messages = [
        { role: "system", content: SYSTEM_PROMPT },
        ...body.messages,
      ];
    }
  }

  // 모델 자동 선택
  if (!body.model) {
    body.model = getDefaultModel();
  }

  // 여전히 없으면 vLLM에서 자동 선택
  if (!body.model) {
    try {
      const modelsResp = await fetch(`${HWARANG_API_URL}/v1/models`);
      if (modelsResp.ok) {
        const modelsData = await modelsResp.json();
        if (modelsData.data?.length > 0) {
          body.model = modelsData.data[0].id;
        }
      }
    } catch {}
  }

  const apiResponse = await fetch(
    `${HWARANG_API_URL}/v1/chat/completions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );

  if (!apiResponse.ok) {
    const errorText = await apiResponse.text();
    return new Response(
      JSON.stringify({ error: `API error: ${apiResponse.status}`, detail: errorText }),
      { status: apiResponse.status }
    );
  }

  if (body.stream) {
    return new Response(apiResponse.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }

  const data = await apiResponse.json();
  return Response.json(data);
}
