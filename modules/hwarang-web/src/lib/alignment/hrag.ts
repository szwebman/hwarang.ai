/**
 * HRAG - Hwarang Retrieval-Augmented Generation
 *
 * 화랑 AI 고유 정렬 기법 #4
 *
 * 한국 공식 데이터베이스 실시간 검색 후 답변 생성.
 * Claude/GPT의 학습 데이터 시점 한계 극복.
 *
 * 통합 대상:
 *   - 법제처 Open API (최신 법령)
 *   - 국가법령정보센터 (판례)
 *   - 국세청 홈택스 (세법)
 *   - 공공데이터포털 (통계)
 *   - 기상청 API (실시간)
 */

export interface HRAGSource {
  name: string;
  type: "legal" | "tax" | "weather" | "stats" | "government";
  url: string;
  title: string;
  snippet: string;
  fetchedAt: Date;
}

export interface HRAGResult {
  query: string;
  sources: HRAGSource[];
  context: string;  // 프롬프트에 주입할 컨텍스트
}

// ─── 키워드 추출 ────────────────────────────────────────────────

const LEGAL_KEYWORDS = [
  "민법", "형법", "상법", "노동법", "상속법", "부동산", "임대차",
  "계약", "손해배상", "해지", "해제", "손해", "배상",
  "저작권", "상표", "특허",
];

const TAX_KEYWORDS = [
  "종합소득세", "부가가치세", "부가세", "양도소득세", "양도세",
  "법인세", "원천징수", "연말정산", "세무", "세금",
  "4대보험", "건강보험료", "국민연금",
];

const WEATHER_KEYWORDS = ["날씨", "기온", "비", "눈", "미세먼지", "습도"];

function extractQuery(text: string): { type: HRAGSource["type"] | null; keywords: string[] } {
  const keywords: string[] = [];

  for (const kw of LEGAL_KEYWORDS) {
    if (text.includes(kw)) keywords.push(kw);
  }
  if (keywords.length > 0) return { type: "legal", keywords };

  for (const kw of TAX_KEYWORDS) {
    if (text.includes(kw)) keywords.push(kw);
  }
  if (keywords.length > 0) return { type: "tax", keywords };

  for (const kw of WEATHER_KEYWORDS) {
    if (text.includes(kw)) keywords.push(kw);
  }
  if (keywords.length > 0) return { type: "weather", keywords };

  return { type: null, keywords: [] };
}

// ─── 법제처 Open API ────────────────────────────────────────────

async function searchLawDB(keyword: string, apiKey?: string): Promise<HRAGSource[]> {
  if (!apiKey) apiKey = process.env.LAW_GO_KR_API_KEY;
  if (!apiKey) return [];

  try {
    const url = `http://www.law.go.kr/DRF/lawSearch.do?OC=${apiKey}&target=law&type=JSON&query=${encodeURIComponent(keyword)}&display=5`;
    const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) return [];

    const data = await resp.json();
    const laws = data.LawSearch?.law || [];

    return laws.slice(0, 5).map((law: any) => ({
      name: "법제처",
      type: "legal" as const,
      url: `https://www.law.go.kr/lsInfoP.do?lsiSeq=${law.법령ID || ""}`,
      title: law.법령명한글 || "",
      snippet: `${law.법령명한글 || ""} (${law.공포일자 || ""})`,
      fetchedAt: new Date(),
    }));
  } catch {
    return [];
  }
}

// ─── 판례 검색 ──────────────────────────────────────────────────

async function searchPrecedents(keyword: string, apiKey?: string): Promise<HRAGSource[]> {
  if (!apiKey) apiKey = process.env.LAW_GO_KR_API_KEY;
  if (!apiKey) return [];

  try {
    const url = `http://www.law.go.kr/DRF/lawSearch.do?OC=${apiKey}&target=prec&type=JSON&query=${encodeURIComponent(keyword)}&display=3`;
    const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) return [];

    const data = await resp.json();
    const cases = data.PrecSearch?.prec || [];

    return cases.slice(0, 3).map((c: any) => ({
      name: "대법원 판례",
      type: "legal" as const,
      url: `https://www.law.go.kr/precInfoP.do?precSeq=${c.판례일련번호 || ""}`,
      title: c.사건명 || "",
      snippet: `[${c.법원명}] ${c.사건번호} (${c.선고일자})`,
      fetchedAt: new Date(),
    }));
  } catch {
    return [];
  }
}

// ─── 기상청 API ────────────────────────────────────────────────

async function fetchWeather(): Promise<HRAGSource[]> {
  // 기상청 단기예보 API (실제 구현 시 nx/ny 좌표 변환 필요)
  const apiKey = process.env.WEATHER_API_KEY;
  if (!apiKey) return [];

  try {
    // 간략 구현 - 실제는 좌표별 호출
    return [{
      name: "기상청",
      type: "weather",
      url: "https://www.weather.go.kr",
      title: "현재 날씨",
      snippet: "기상청 API 연동 필요 (좌표 기반)",
      fetchedAt: new Date(),
    }];
  } catch {
    return [];
  }
}

// ─── 메인 파이프라인 ────────────────────────────────────────────

export async function applyHRAG(userMessage: string): Promise<HRAGResult> {
  const { type, keywords } = extractQuery(userMessage);

  if (!type || keywords.length === 0) {
    return { query: userMessage, sources: [], context: "" };
  }

  const sources: HRAGSource[] = [];

  // 병렬로 여러 소스 검색
  if (type === "legal") {
    const [laws, precedents] = await Promise.all([
      searchLawDB(keywords[0]),
      searchPrecedents(keywords[0]),
    ]);
    sources.push(...laws, ...precedents);
  } else if (type === "tax") {
    const laws = await searchLawDB(keywords[0]);
    sources.push(...laws);
  } else if (type === "weather") {
    const weather = await fetchWeather();
    sources.push(...weather);
  }

  // 프롬프트 컨텍스트 생성
  let context = "";
  if (sources.length > 0) {
    context = `\n\n[HRAG - 실시간 검색 결과]\n다음 공식 자료를 참고하여 답변하세요:\n`;
    sources.forEach((s, i) => {
      context += `\n[${i + 1}] ${s.name}: ${s.title}\n   ${s.snippet}\n   출처: ${s.url}\n`;
    });
    context += `\n⚠️ 인용 시 반드시 위 출처를 명시하세요.`;
  }

  return { query: userMessage, sources, context };
}
