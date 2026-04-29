/**
 * Cross-source 검증 클라이언트
 *
 * - chat/route.ts 가 응답 직후 호출
 * - FastAPI /api/verify 엔드포인트와 통신
 * - 실패 시 null 반환 (타임아웃 / 네트워크 오류 등) — 채팅 응답에 영향 없음
 */

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";
const INTERNAL_KEY = process.env.HWARANG_INTERNAL_KEY || "";

export interface VerificationSource {
  source_name: string;
  source_url: string;
  trust_level: number;
  is_primary?: boolean;
  source_type?: string;
  excerpt?: string;
}

export interface VerificationResult {
  claim: string;
  confidence: number;             // 0.0 ~ 1.0
  supporting: VerificationSource[];
  contradicting: VerificationSource[];
  verdict?: "verified" | "disputed" | "unverified";
}

/**
 * 단일 주장에 대해 백엔드 cross-verifier 호출
 */
export async function verifyClaimWithSources(
  claim: string,
  domain: string
): Promise<VerificationResult | null> {
  if (!claim || claim.length < 10) return null;
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (INTERNAL_KEY) headers["X-API-Key"] = INTERNAL_KEY;

    const resp = await fetch(`${HWARANG_API_URL}/api/verify`, {
      method: "POST",
      headers,
      body: JSON.stringify({ claim, domain }),
      signal: AbortSignal.timeout(5000),
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    return {
      claim,
      confidence: typeof data.confidence === "number" ? data.confidence : 0,
      supporting: Array.isArray(data.supporting) ? data.supporting : [],
      contradicting: Array.isArray(data.contradicting) ? data.contradicting : [],
      verdict: data.verdict,
    };
  } catch {
    return null;
  }
}

/**
 * 응답 텍스트에서 핵심 주장 추출 (단순 휴리스틱)
 *
 * 우선순위:
 *   1. 숫자/날짜/법조항/비율 포함 문장
 *   2. 길이가 20자 이상
 *   3. 최대 2개
 */
export async function extractKeyClaims(response: string): Promise<string[]> {
  if (!response) return [];
  // 한국어/영어 문장 분리
  const sentences = response
    .split(/[.!?。\n]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 20 && s.length < 300);

  // 사실성 휴리스틱: 숫자, 법, 조, 항, 규정, %, 날짜
  const factualPattern = /\d|법|조|항|규정|시행|발효|비율|퍼센트|%|년|월|일/;

  const factual = sentences.filter((s) => factualPattern.test(s));

  return factual.slice(0, 2);
}

/**
 * confidence (0~1) 기반 색상 매핑
 *   0.8+ : 초록 (#10b981) — 강한 출처 다수 일치
 *   0.5+ : 노랑 (#ca8a04) — 부분적 근거
 *    그 외 : 빨강 (#dc2626) — 근거 부족 / 모순
 */
export function colorByConfidence(confidence: number | null | undefined): string {
  if (confidence == null) return "#64748b";
  if (confidence >= 0.8) return "#10b981";
  if (confidence >= 0.5) return "#ca8a04";
  return "#dc2626";
}
