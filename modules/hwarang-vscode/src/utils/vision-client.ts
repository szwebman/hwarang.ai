/**
 * Vision Client - 화랑 Vision API (Qwen2.5-VL) 호출 helper.
 *
 * 흐름:
 *   1. 사용자가 채팅창에 이미지 첨부 (drag/drop 또는 클립보드 paste)
 *   2. base64 인코딩된 이미지를 `/api/vision/analyze` 로 POST
 *   3. VLM 이 description (필요 시 components) 반환
 *   4. 메인 chat 호출 시 사용자 메시지 앞에 description 을 prepend 하여 코드 생성 유도.
 *
 * 서버는 RTX 3090 의 hwarang-vl (port 8002) 을 게이트웨이가 8000 으로 노출.
 */

export interface VisionRequest {
  /** base64 인코딩된 이미지 (data URL prefix 가 있어도 허용 — 내부에서 strip). */
  imageBase64: string;
  /** 사용자가 추가한 프롬프트 (예: "이걸 React 컴포넌트로"). */
  instruction?: string;
}

export interface VisionResponse {
  /** VLM 이 분석한 이미지 설명 텍스트. */
  description: string;
  /** UI 컴포넌트 목록 (옵션, 서버가 반환 시). */
  detectedComponents?: string[];
}

const DEFAULT_INSTRUCTION =
  "이미지를 자세히 분석하고 코드/UI 컴포넌트로 변환할 수 있게 묘사해라.";

/**
 * 화랑 Vision API client. apiUrl 은 게이트웨이 base URL (예: https://hwarang.ai),
 * apiKey 는 AuthManager 가 발급한 Bearer 토큰.
 */
export class VisionClient {
  constructor(
    private readonly apiUrl: string,
    private readonly apiKey: string
  ) {}

  /**
   * 단일 이미지 분석. data URL prefix (`data:image/...;base64,`) 가 있으면 자동 제거.
   */
  async analyzeImage(req: VisionRequest): Promise<VisionResponse> {
    const url = `${this.apiUrl.replace(/\/$/, "")}/api/vision/analyze`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.apiKey) {
      headers["Authorization"] = `Bearer ${this.apiKey}`;
    }

    const stripped = stripDataUrlPrefix(req.imageBase64);
    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        image_base64: stripped,
        instruction: req.instruction || DEFAULT_INSTRUCTION,
      }),
    });

    if (!resp.ok) {
      const errText = await resp.text().catch(() => "");
      throw new Error(`Vision API ${resp.status}: ${errText}`);
    }

    const data = (await resp.json()) as Record<string, unknown>;
    return {
      description:
        (data.description as string) ||
        (data.content as string) ||
        (data.text as string) ||
        "",
      detectedComponents: (data.components as string[]) || undefined,
    };
  }

  /**
   * 여러 이미지를 순차 분석하고 description 을 모아서 prepend 용 텍스트로 합쳐 반환.
   */
  async analyzeMany(
    images: { base64: string; name?: string }[],
    instruction?: string
  ): Promise<string> {
    if (!images.length) return "";
    const parts: string[] = [];
    for (let i = 0; i < images.length; i++) {
      const img = images[i];
      try {
        const r = await this.analyzeImage({
          imageBase64: img.base64,
          instruction,
        });
        const label = img.name ? `${img.name}` : `이미지 #${i + 1}`;
        parts.push(`[${label}]\n${r.description}`);
      } catch (e: any) {
        parts.push(`[이미지 #${i + 1}] (분석 실패: ${e?.message || e})`);
      }
    }
    return parts.join("\n\n");
  }
}

/** `data:image/png;base64,XXXX` → `XXXX`. prefix 가 없으면 그대로 반환. */
function stripDataUrlPrefix(s: string): string {
  if (!s) return s;
  const idx = s.indexOf("base64,");
  if (idx >= 0) return s.slice(idx + "base64,".length);
  return s;
}
