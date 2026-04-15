/**
 * Chat API proxy route.
 * 브라우저 → Next.js → vLLM/Hwarang API
 *
 * 모델은 환경변수 HWARANG_DEFAULT_MODEL에서 가져옴.
 * 관리자가 변경하면 자동 반영.
 */

import { NextRequest } from "next/server";

const HWARANG_API_URL =
  process.env.HWARANG_API_URL || "http://localhost:8000";

const DEFAULT_MODEL =
  process.env.HWARANG_DEFAULT_MODEL || "";

export async function POST(request: NextRequest) {
  const body = await request.json();

  // 모델이 지정 안 되었으면 기본 모델 사용
  if (!body.model && DEFAULT_MODEL) {
    body.model = DEFAULT_MODEL;
  }

  // 모델이 아직도 없으면 vLLM에서 첫 번째 모델 자동 선택
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

  // 스트리밍
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
