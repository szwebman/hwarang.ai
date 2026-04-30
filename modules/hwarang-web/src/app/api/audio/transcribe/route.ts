/**
 * 음성 STT proxy → hwarang-api 의 /api/audio/transcribe 로 전달.
 *
 * 흐름:
 *   1. 클라이언트 (브라우저) 가 multipart/form-data 로 음성 파일 POST
 *   2. NextAuth 세션 검증 (로그인 필수)
 *   3. hwarang-api 의 /api/audio/transcribe 로 그대로 forward
 *   4. 결과 JSON 반환
 *
 * 토큰 차감 없음 — STT 는 짧고 가볍기 때문에 무료. 추후 정책 변경 가능.
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";
const INTERNAL_KEY = process.env.HWARANG_INTERNAL_KEY || "";
const MAX_AUDIO_BYTES = 50 * 1024 * 1024; // 50MB

export async function POST(request: NextRequest) {
  // 1. 세션 검증
  const session = await auth();
  if (!session?.user?.id) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  // 2. 파일 읽기
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch (e) {
    return Response.json({ error: "잘못된 multipart 요청" }, { status: 400 });
  }

  const file = formData.get("file");
  if (!file || !(file instanceof Blob)) {
    return Response.json({ error: "음성 파일이 없습니다" }, { status: 400 });
  }
  if (file.size > MAX_AUDIO_BYTES) {
    return Response.json({ error: "파일이 너무 큽니다 (최대 50MB)" }, { status: 413 });
  }

  // 3. hwarang-api 로 forward
  const upstream = new FormData();
  upstream.append("file", file, (file as any).name || "audio");
  const language = formData.get("language");
  if (typeof language === "string" && language) {
    upstream.append("language", language);
  } else {
    upstream.append("language", "ko");
  }
  const prompt = formData.get("prompt");
  if (typeof prompt === "string" && prompt) {
    upstream.append("prompt", prompt);
  }

  const headers: Record<string, string> = {};
  if (INTERNAL_KEY) {
    headers["Authorization"] = `Bearer ${INTERNAL_KEY}`;
  }

  try {
    const resp = await fetch(`${HWARANG_API_URL}/api/audio/transcribe`, {
      method: "POST",
      headers,
      body: upstream,
      // 음성 변환은 길어질 수 있음 (large-v3 + 긴 파일)
      signal: AbortSignal.timeout(120_000),
    });

    if (!resp.ok) {
      const errText = await resp.text().catch(() => "");
      let msg = `요청 실패 (HTTP ${resp.status})`;
      try {
        const j = JSON.parse(errText);
        msg = j.error || j.detail || j.message || msg;
      } catch {
        if (errText) msg = errText.slice(0, 200);
      }
      return Response.json({ error: msg }, { status: resp.status });
    }

    const data = await resp.json();
    return Response.json(data);
  } catch (e: any) {
    console.error("[/api/audio/transcribe] forward 실패:", e?.message || e);
    return Response.json(
      { error: "음성 변환 서버에 연결할 수 없습니다" },
      { status: 502 },
    );
  }
}
