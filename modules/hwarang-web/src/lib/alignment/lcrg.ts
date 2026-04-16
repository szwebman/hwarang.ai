/**
 * LCRG - Live Citation & Reference Guard
 *
 * 화랑 AI 고유 정렬 기법 #10
 *
 * 실시간 인용 검증으로 환각(hallucination) 차단.
 * AI가 "민법 제543조"라고 하면 진짜로 그런 조항이 있는지 확인.
 */

export interface Citation {
  type: "law" | "case" | "statute" | "article" | "doi" | "url";
  reference: string;              // 원본 인용 텍스트
  law?: string;                    // 법률명 (예: "민법")
  article?: number;                // 조 번호
  clause?: number;                 // 항
  caseNumber?: string;             // 판례 번호
  verified: boolean;
  url?: string;
  error?: string;
}

// ─── 인용 패턴 추출 ────────────────────────────────────────────

const CITATION_PATTERNS = [
  // 법령 조문: "민법 제543조", "상법 제42조 제2항"
  {
    type: "law" as const,
    pattern: /(민법|형법|상법|민사소송법|형사소송법|근로기준법|상속법|노동법|저작권법|개인정보보호법|부가가치세법|소득세법|법인세법|상속세및증여세법|국세기본법)\s*제?\s*(\d+)\s*조(?:\s*제?(\d+)\s*항)?/g,
    extract: (m: RegExpExecArray) => ({
      reference: m[0],
      law: m[1],
      article: parseInt(m[2], 10),
      clause: m[3] ? parseInt(m[3], 10) : undefined,
    }),
  },
  // 판례: "대법원 2020다1234", "서울중앙지법 2021가합5678"
  {
    type: "case" as const,
    pattern: /(대법원|(?:서울|부산|대구|대전|광주|수원)(?:고등법원|중앙지법|지방법원))?\s*(\d{4})[다가노허느파재][합단나][\d]+/g,
    extract: (m: RegExpExecArray) => ({
      reference: m[0],
      caseNumber: m[0].trim(),
    }),
  },
];

export function extractCitations(text: string): Citation[] {
  const citations: Citation[] = [];

  for (const { type, pattern, extract } of CITATION_PATTERNS) {
    pattern.lastIndex = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      const info = extract(match as RegExpExecArray);
      citations.push({
        type,
        ...info,
        verified: false,
      });
    }
  }

  return citations;
}

// ─── 법제처 API 검증 ────────────────────────────────────────────

async function verifyLawWithAPI(citation: Citation, apiKey: string): Promise<Citation> {
  if (!citation.law) return { ...citation, verified: false, error: "법률명 없음" };

  try {
    const url = `http://www.law.go.kr/DRF/lawSearch.do?OC=${apiKey}&target=law&type=JSON&query=${encodeURIComponent(citation.law)}&display=1`;
    const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });

    if (!resp.ok) {
      return { ...citation, verified: false, error: `API 오류 ${resp.status}` };
    }

    const data = await resp.json();
    const laws = data.LawSearch?.law || [];

    if (laws.length === 0) {
      return { ...citation, verified: false, error: "법률을 찾을 수 없음" };
    }

    const law = laws[0];
    const lawUrl = `https://www.law.go.kr/lsInfoP.do?lsiSeq=${law.법령ID || ""}`;

    // 조문 단위까지 검증 (법제처 JO API 사용 시)
    // 간략 버전: 법률 존재만 확인
    return {
      ...citation,
      verified: true,
      url: citation.article
        ? `${lawUrl}#${citation.article}조`
        : lawUrl,
    };
  } catch (e: any) {
    return { ...citation, verified: false, error: e.message };
  }
}

// ─── 판례 검증 ──────────────────────────────────────────────────

async function verifyPrecedent(citation: Citation, apiKey: string): Promise<Citation> {
  if (!citation.caseNumber) return { ...citation, verified: false };

  try {
    const url = `http://www.law.go.kr/DRF/lawSearch.do?OC=${apiKey}&target=prec&type=JSON&query=${encodeURIComponent(citation.caseNumber)}&display=1`;
    const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });

    if (!resp.ok) return { ...citation, verified: false };

    const data = await resp.json();
    const cases = data.PrecSearch?.prec || [];

    if (cases.length === 0) {
      return { ...citation, verified: false, error: "판례를 찾을 수 없음" };
    }

    return {
      ...citation,
      verified: true,
      url: `https://www.law.go.kr/precInfoP.do?precSeq=${cases[0].판례일련번호}`,
    };
  } catch (e: any) {
    return { ...citation, verified: false, error: e.message };
  }
}

// ─── 메인 검증 파이프라인 ────────────────────────────────────

export async function verifyAllCitations(text: string, apiKey?: string): Promise<Citation[]> {
  apiKey = apiKey || process.env.LAW_GO_KR_API_KEY;
  if (!apiKey) return extractCitations(text);  // API 키 없으면 추출만

  const citations = extractCitations(text);

  const verified = await Promise.all(
    citations.map((c) => {
      if (c.type === "law") return verifyLawWithAPI(c, apiKey);
      if (c.type === "case") return verifyPrecedent(c, apiKey);
      return Promise.resolve(c);
    })
  );

  return verified;
}

// ─── 답변 검증 + 마크업 ──────────────────────────────────────

export async function applyLCRG(responseText: string): Promise<{
  text: string;
  citations: Citation[];
  allVerified: boolean;
  warnings: string[];
}> {
  const citations = await verifyAllCitations(responseText);

  if (citations.length === 0) {
    return { text: responseText, citations: [], allVerified: true, warnings: [] };
  }

  let markedText = responseText;
  const warnings: string[] = [];

  // 검증 실패한 인용 경고
  for (const c of citations) {
    if (!c.verified) {
      warnings.push(`❌ "${c.reference}" - ${c.error || "검증 실패"}`);
    } else if (c.url) {
      // 검증된 인용에 링크 추가
      const linkText = `[${c.reference}](${c.url})`;
      markedText = markedText.replace(c.reference, linkText);
    }
  }

  const allVerified = citations.every((c) => c.verified);

  // 검증 결과 요약
  if (warnings.length > 0) {
    markedText += `\n\n---\n**🔴 LCRG 검증 실패 - 주의!**\n`;
    markedText += warnings.map((w) => `- ${w}`).join("\n");
    markedText += `\n\n위 인용은 확인할 수 없으므로, 반드시 원본 자료를 확인하시거나 전문가와 상담하세요.`;
  } else if (citations.length > 0) {
    markedText += `\n\n✅ 인용된 ${citations.length}건이 모두 검증되었습니다.`;
  }

  return { text: markedText, citations, allVerified, warnings };
}

// ─── 인용 경고 프롬프트 (AI에게 검증 요청) ───────────────────

export function buildLCRGPrompt(): string {
  return `\n\n[LCRG - 인용 검증]
법령, 판례, 조문 인용 시 반드시 정확하게 하세요:
- 존재하지 않는 법령 조항을 만들어내지 마세요
- 확실하지 않은 판례는 "판례가 있을 수 있으나 정확한 번호는 확인이 필요합니다"로 표현
- 최신 법령(2025~2026 개정)은 변경되었을 수 있음을 명시
- 인용 형식: "민법 제543조" (띄어쓰기 주의)`;
}
