/**
 * 모델 추론 테스트 API
 * POST /api/models/test
 */

import { NextRequest } from "next/server";
import { verifyToken } from "@/lib/auth";

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const token = authHeader?.replace("Bearer ", "") || "";
  const auth = verifyToken(token);

  if (!auth || (auth.role !== "ADMIN" && auth.role !== "SUPER_ADMIN")) {
    return Response.json({ error: "권한 없음" }, { status: 403 });
  }

  try {
    const { backendId, message } = await request.json();

    if (!backendId) {
      return Response.json({ error: "backendId 필수" }, { status: 400 });
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

    const resp = await fetch(`${HWARANG_API_URL}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: backendId,
        messages: [{ role: "user", content: message || "안녕하세요" }],
        max_tokens: 150,
        temperature: 0.7,
      }),
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!resp.ok) {
      return Response.json({ error: `vLLM 오류 ${resp.status}` }, { status: 500 });
    }

    const data = await resp.json();
    return Response.json({
      response: data.choices?.[0]?.message?.content || "응답 없음",
      tokens: data.usage?.total_tokens || 0,
      promptTokens: data.usage?.prompt_tokens || 0,
      completionTokens: data.usage?.completion_tokens || 0,
    });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
