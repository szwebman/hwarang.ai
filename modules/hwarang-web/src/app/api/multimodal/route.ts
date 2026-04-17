/**
 * 멀티모달 API (이미지 입력)
 *
 * POST /api/multimodal - 이미지 + 텍스트 → AI 분석
 *
 * EXAONE 4.5가 이미지 지원하므로, 이미지 질문은 EXAONE으로 라우팅.
 *
 * 사용 사례:
 *   - 계약서 스캔 분석
 *   - 세금 고지서 해석
 *   - 스크린샷 → 코드
 *   - 에러 스크린샷 → 디버깅
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";

export async function POST(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return Response.json({ error: "로그인 필요" }, { status: 401 });

  const formData = await request.formData();
  const image = formData.get("image") as File | null;
  const text = formData.get("text") as string || "이 이미지를 분석해주세요";

  if (!image) {
    return Response.json({ error: "이미지 필요" }, { status: 400 });
  }

  // 이미지를 base64로 변환
  const imageBuffer = await image.arrayBuffer();
  const base64 = Buffer.from(imageBuffer).toString("base64");
  const mimeType = image.type || "image/png";

  // EXAONE 4.5 (멀티모달) 엔드포인트로 라우팅
  const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";

  try {
    const resp = await fetch(`${HWARANG_API_URL}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "exaone-4.5-33b",
        messages: [
          {
            role: "user",
            content: [
              { type: "image_url", image_url: { url: `data:${mimeType};base64,${base64}` } },
              { type: "text", text },
            ],
          },
        ],
        max_tokens: 2048,
      }),
    });

    if (!resp.ok) {
      return Response.json({ error: `AI 서버 오류 (${resp.status})` }, { status: resp.status });
    }

    const data = await resp.json();
    return Response.json(data);
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
