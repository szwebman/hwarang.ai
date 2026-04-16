/**
 * TACS - Trust-Aware Chain-of-Safety
 *
 * 화랑 AI 고유 정렬 기법 #1
 *
 * 동작:
 *   1. 질문에서 도메인 감지 (코딩/법률/세무/의료/금융/일반)
 *   2. 도메인별 위험도 계산 (사실 오류의 치명도)
 *   3. 신뢰도 임계치 이하면 안전 체인 발동
 *      - 면책 조항 자동 추가
 *      - 한국 공식 리소스 연결
 *      - 전문가 상담 권고
 */

export type Domain =
  | "general"
  | "coding"
  | "legal"
  | "tax"
  | "medical"
  | "finance"
  | "education";

export interface DomainInfo {
  domain: Domain;
  confidence: number;       // 0~1, 도메인 감지 신뢰도
  riskLevel: "low" | "medium" | "high" | "critical";
  requiresDisclaimer: boolean;
  resources: Resource[];    // 한국 공식 리소스
}

export interface Resource {
  name: string;
  description: string;
  contact: string;
  url?: string;
}

// ─── 도메인별 위험도 & 리소스 (한국 특화) ───────────────────────

const DOMAIN_CONFIG: Record<Domain, {
  riskLevel: DomainInfo["riskLevel"];
  requiresDisclaimer: boolean;
  resources: Resource[];
  disclaimer: string;
}> = {
  general: {
    riskLevel: "low",
    requiresDisclaimer: false,
    resources: [],
    disclaimer: "",
  },
  coding: {
    riskLevel: "low",
    requiresDisclaimer: false,
    resources: [
      { name: "Stack Overflow", description: "프로그래밍 Q&A", contact: "", url: "https://stackoverflow.com" },
      { name: "GitHub", description: "오픈소스 저장소", contact: "", url: "https://github.com" },
    ],
    disclaimer: "",
  },
  legal: {
    riskLevel: "critical",
    requiresDisclaimer: true,
    resources: [
      { name: "대한법률구조공단", description: "무료 법률 상담", contact: "132", url: "https://www.klac.or.kr" },
      { name: "대한변호사협회", description: "변호사 찾기", contact: "02-3476-4000", url: "https://www.koreanbar.or.kr" },
      { name: "법제처 국가법령정보", description: "법령 검색", contact: "", url: "https://www.law.go.kr" },
      { name: "찾기 쉬운 생활법령정보", description: "생활 법률 가이드", contact: "", url: "https://easylaw.go.kr" },
    ],
    disclaimer: "⚠️ 본 답변은 일반 정보 제공 목적이며, 법적 자문이 아닙니다. 구체적인 사안은 반드시 변호사와 상담하시기 바랍니다.",
  },
  tax: {
    riskLevel: "critical",
    requiresDisclaimer: true,
    resources: [
      { name: "국세청 국세상담센터", description: "세무 상담", contact: "126", url: "https://www.hometax.go.kr" },
      { name: "한국세무사회", description: "세무사 찾기", contact: "02-521-9451", url: "https://www.kacpta.or.kr" },
      { name: "홈택스", description: "전자 세무 서비스", contact: "", url: "https://hometax.go.kr" },
    ],
    disclaimer: "⚠️ 본 답변은 일반 정보 제공 목적이며, 구체적인 세무 상담이 아닙니다. 정확한 세무 처리는 세무사와 상담하시기 바랍니다.",
  },
  medical: {
    riskLevel: "critical",
    requiresDisclaimer: true,
    resources: [
      { name: "건강보험심사평가원", description: "병원 찾기", contact: "1644-2000", url: "https://www.hira.or.kr" },
      { name: "응급의료정보센터", description: "응급실 위치", contact: "1339", url: "https://www.e-gen.or.kr" },
      { name: "질병관리청", description: "질병 정보", contact: "1339", url: "https://www.kdca.go.kr" },
    ],
    disclaimer: "⚠️ 본 답변은 일반 건강 정보이며 의학적 진단이 아닙니다. 증상이 있으시면 반드시 의료 전문가와 상담하세요.",
  },
  finance: {
    riskLevel: "high",
    requiresDisclaimer: true,
    resources: [
      { name: "금융감독원 금융소비자정보포털", description: "금융 상담", contact: "1332", url: "https://www.fss.or.kr" },
      { name: "한국금융투자자보호재단", description: "투자자 보호", contact: "1577-2500", url: "" },
    ],
    disclaimer: "⚠️ 본 답변은 일반 금융 정보이며 투자 자문이 아닙니다. 투자 결정은 반드시 본인 책임 하에 전문가 상담 후 진행하세요.",
  },
  education: {
    riskLevel: "low",
    requiresDisclaimer: false,
    resources: [],
    disclaimer: "",
  },
};

// ─── 도메인 감지 (키워드 기반) ─────────────────────────────────

const DOMAIN_KEYWORDS: Record<Domain, RegExp[]> = {
  legal: [
    /계약(서)?|해지|해제|위약금|손해배상/,
    /민법|형법|상법|노동법|상속|유산/,
    /소송|재판|판결|변호사|법무|법원/,
    /내용증명|고소|고발|기소/,
    /임대차|전세|보증금|월세(사기)?/,
    /부당해고|해고|징계|근로기준법/,
    /저작권|상표권|특허|지적재산/,
  ],
  tax: [
    /세금|세무|세법/,
    /부가(가치)?세|부가세/,
    /종합소득세|근로소득세|소득세/,
    /법인세|양도소득세|양도세/,
    /연말정산|원천징수|신고/,
    /홈택스|국세청|세무서/,
    /4대\s*보험|건강보험|국민연금/,
  ],
  medical: [
    /증상|진단|병명|질환|병원/,
    /약(?:물|품)|처방|부작용/,
    /수술|치료|검사/,
    /아프|통증|열나|두통/,
  ],
  finance: [
    /주식|펀드|ETF|채권/,
    /투자|투자금|수익률/,
    /대출|이자(율)?|예금|적금/,
    /코스피|코스닥|나스닥/,
    /비트코인|암호화폐|코인/,
  ],
  coding: [
    /코드|프로그래밍|개발|디버그|디버깅/i,
    /Python|JavaScript|TypeScript|Java|Go|Rust|C\+\+|React|Vue|Next\.?js/i,
    /API|REST|GraphQL|데이터베이스|SQL|NoSQL/i,
    /함수|변수|클래스|객체|메서드|알고리즘/,
    /버그|에러|오류|예외|exception/i,
    /git|docker|kubernetes|npm|pnpm|pip/i,
  ],
  education: [
    /공부|학습|수학|과학|역사|영어/,
    /대학|수능|입시|시험|자격증/,
    /강의|교재|문제집/,
  ],
  general: [],
};

export function detectDomain(text: string): DomainInfo {
  const scores: Record<Domain, number> = {
    general: 0, coding: 0, legal: 0, tax: 0, medical: 0, finance: 0, education: 0,
  };

  // 각 도메인별 키워드 매칭 점수
  for (const [domain, patterns] of Object.entries(DOMAIN_KEYWORDS) as [Domain, RegExp[]][]) {
    for (const pattern of patterns) {
      const matches = text.match(pattern);
      if (matches) {
        scores[domain] += matches.length;
      }
    }
  }

  // 최고 점수 도메인 선택
  let bestDomain: Domain = "general";
  let bestScore = 0;
  for (const [domain, score] of Object.entries(scores) as [Domain, number][]) {
    if (score > bestScore) {
      bestScore = score;
      bestDomain = domain;
    }
  }

  // 신뢰도 = 최고 점수 / 전체 점수
  const totalScore = Object.values(scores).reduce((a, b) => a + b, 0);
  const confidence = totalScore > 0 ? bestScore / totalScore : 0;

  const config = DOMAIN_CONFIG[bestDomain];

  return {
    domain: bestDomain,
    confidence,
    riskLevel: config.riskLevel,
    requiresDisclaimer: config.requiresDisclaimer,
    resources: config.resources,
  };
}

// ─── 시스템 프롬프트 주입 ───────────────────────────────────────

export function buildTACSSystemPrompt(domainInfo: DomainInfo): string {
  const config = DOMAIN_CONFIG[domainInfo.domain];

  let prompt = `당신은 화랑 AI입니다. 한국어 사용자를 위한 AI 어시스턴트입니다.

[TACS: 신뢰 기반 안전 정렬]
- 감지된 도메인: ${domainInfo.domain}
- 위험도: ${domainInfo.riskLevel}
- 신뢰도: ${(domainInfo.confidence * 100).toFixed(0)}%

[응답 규칙]
1. 항상 사용자와 같은 언어로 답변합니다 (한국어 질문 → 한국어 답변).
2. 중국어/일본어를 섞지 마세요.
3. 정확하지 않은 정보는 "확실하지 않습니다"라고 밝히세요.`;

  // 도메인별 추가 지침
  if (domainInfo.domain === "legal") {
    prompt += `

[법률 도메인 지침]
- 구체적인 사건에 대한 법적 판단을 단정적으로 내리지 마세요.
- 일반적인 법률 정보는 제공하되, "참고용"임을 명시하세요.
- 답변 마지막에 변호사 상담을 권유하세요.
- 한국 법령(민법, 형법 등)에 근거해 답변하세요.`;
  } else if (domainInfo.domain === "tax") {
    prompt += `

[세무 도메인 지침]
- 세금 계산은 일반 원칙만 제시하고, 구체적 사안은 세무사 상담 권유.
- 최신 세법 개정사항을 알지 못할 수 있음을 알립니다.
- 홈택스, 국세청 126 상담센터 등 공식 채널을 안내하세요.`;
  } else if (domainInfo.domain === "medical") {
    prompt += `

[의료 도메인 지침]
- 진단이나 처방을 절대 하지 마세요.
- 일반 건강 정보만 제공하고 의료 전문가 상담을 권유하세요.
- 응급 증상 의심 시 119 또는 응급실 안내.`;
  } else if (domainInfo.domain === "finance") {
    prompt += `

[금융 도메인 지침]
- 구체적 투자 추천은 하지 마세요.
- 일반 금융 지식만 제공하세요.
- "투자는 본인 책임" 원칙을 강조하세요.`;
  } else if (domainInfo.domain === "coding") {
    prompt += `

[코딩 도메인 지침]
- 코드에는 한국어 주석을 달아주세요.
- 에러 처리, 테스트, 모범 사례를 포함하세요.
- 보안 취약점을 일으킬 코드는 거부하세요.`;
  }

  return prompt;
}

// ─── 응답 후처리 (면책조항 + 리소스 추가) ─────────────────────

export function applyTACSPostProcessing(
  response: string,
  domainInfo: DomainInfo
): string {
  const config = DOMAIN_CONFIG[domainInfo.domain];

  if (!config.requiresDisclaimer) return response;

  // 이미 면책조항이 있으면 추가하지 않음
  if (response.includes("⚠️") || response.includes("변호사") || response.includes("세무사") || response.includes("의료")) {
    // 이미 자체 면책조항 있음
    return appendResources(response, config.resources);
  }

  let appended = response + "\n\n---\n\n" + config.disclaimer;

  if (config.resources.length > 0) {
    appended = appendResources(appended, config.resources);
  }

  return appended;
}

function appendResources(response: string, resources: Resource[]): string {
  if (resources.length === 0) return response;

  // 이미 리소스 링크가 있으면 추가하지 않음
  if (response.includes("📞 관련 기관")) return response;

  let appended = response + "\n\n**📞 관련 기관**";
  for (const r of resources.slice(0, 3)) {
    appended += `\n- **${r.name}** - ${r.description}`;
    if (r.contact) appended += ` (${r.contact})`;
    if (r.url) appended += ` · ${r.url}`;
  }

  return appended;
}

// ─── 메인 파이프라인 ────────────────────────────────────────────

export function applyTACS(userMessage: string): {
  domainInfo: DomainInfo;
  systemPrompt: string;
} {
  const domainInfo = detectDomain(userMessage);
  const systemPrompt = buildTACSSystemPrompt(domainInfo);
  return { domainInfo, systemPrompt };
}
