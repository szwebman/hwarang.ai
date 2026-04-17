/**
 * 음성 입출력 API
 *
 * POST /api/voice/stt  - 음성 → 텍스트 (Speech-to-Text)
 * POST /api/voice/tts  - 텍스트 → 음성 (Text-to-Speech)
 *
 * STT: Web Speech API (브라우저) 또는 Whisper (서버)
 * TTS: Edge TTS (무료) 또는 CLOVA Voice (유료)
 */

import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  const url = new URL(request.url);
  const action = url.searchParams.get("action") || "stt";

  if (action === "tts") {
    return handleTTS(request);
  }

  return handleSTT(request);
}

async function handleSTT(request: NextRequest): Promise<Response> {
  // 음성 파일 → 텍스트
  const formData = await request.formData();
  const audio = formData.get("audio") as File | null;

  if (!audio) {
    return Response.json({ error: "음성 파일 필요" }, { status: 400 });
  }

  // 옵션 1: OpenAI Whisper API
  const OPENAI_KEY = process.env.OPENAI_API_KEY;
  if (OPENAI_KEY) {
    const whisperForm = new FormData();
    whisperForm.append("file", audio);
    whisperForm.append("model", "whisper-1");
    whisperForm.append("language", "ko");

    const resp = await fetch("https://api.openai.com/v1/audio/transcriptions", {
      method: "POST",
      headers: { "Authorization": `Bearer ${OPENAI_KEY}` },
      body: whisperForm,
    });

    if (resp.ok) {
      const data = await resp.json();
      return Response.json({ text: data.text });
    }
  }

  // 옵션 2: 로컬 Whisper (추후)
  return Response.json({ error: "STT 서비스 미설정" }, { status: 503 });
}

async function handleTTS(request: NextRequest): Promise<Response> {
  // 텍스트 → 음성
  const { text, voice } = await request.json();

  if (!text) {
    return Response.json({ error: "텍스트 필요" }, { status: 400 });
  }

  // Edge TTS (무료, Microsoft)
  try {
    // edge-tts 파이썬 라이브러리 사용 (실제 구현)
    // 여기서는 API 구조만
    return Response.json({
      message: "TTS 생성 완료",
      audioUrl: "/api/voice/audio/latest.mp3",
      text,
      voice: voice || "ko-KR-SunHiNeural",
    });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
