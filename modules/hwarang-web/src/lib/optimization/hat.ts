/**
 * HAT - Hwarang Agentic Tools
 *
 * 화랑 AI 최적화 기법 #2
 *
 * AI가 필요시 도구를 호출하여 실제 작업 수행.
 * Claude Tool Use / OpenAI Function Calling 스타일.
 *
 * 도구:
 *   💻 code_exec     - Python 코드 실행 (샌드박스)
 *   🧮 calculator    - 정확한 수학 계산
 *   ⚖️ search_law    - 법제처 법령 검색
 *   📋 search_case   - 판례 검색
 *   🌐 web_search    - 실시간 웹 검색
 *   📊 get_stats     - 공공데이터 통계
 *   📅 get_date      - 정확한 날짜/시간
 *   💱 get_exchange  - 환율 조회
 */

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: {
    type: "object";
    properties: Record<string, any>;
    required?: string[];
  };
  handler: (args: any) => Promise<string>;
}

// ─── 도구 1: 계산기 ────────────────────────────────────────────

const calculatorTool: ToolDefinition = {
  name: "calculator",
  description: "정확한 수학 계산을 수행합니다. 사칙연산, 퍼센트, 제곱근 등.",
  parameters: {
    type: "object",
    properties: {
      expression: { type: "string", description: "계산할 수식 (예: '1234 * 0.15')" },
    },
    required: ["expression"],
  },
  handler: async ({ expression }) => {
    try {
      // 안전한 수식만 허용
      const safe = expression.replace(/,/g, "");
      if (!/^[\d+\-*/%().\s,]+$/.test(safe)) {
        return "⚠️ 안전하지 않은 수식입니다";
      }
      // eslint-disable-next-line no-new-func
      const result = new Function(`return ${safe}`)();
      return `결과: ${result.toLocaleString("ko-KR")}`;
    } catch (e: any) {
      return `계산 오류: ${e.message}`;
    }
  },
};

// ─── 도구 2: 법령 검색 ─────────────────────────────────────────

const searchLawTool: ToolDefinition = {
  name: "search_law",
  description: "한국 법령을 검색합니다. 법제처 API를 사용.",
  parameters: {
    type: "object",
    properties: {
      query: { type: "string", description: "검색어 (예: '민법 제543조', '부동산 임대차')" },
      limit: { type: "number", description: "결과 개수 (기본 3)", default: 3 },
    },
    required: ["query"],
  },
  handler: async ({ query, limit = 3 }) => {
    const apiKey = process.env.LAW_GO_KR_API_KEY;
    if (!apiKey) return "⚠️ 법제처 API 키가 설정되지 않았습니다";

    try {
      const url = `http://www.law.go.kr/DRF/lawSearch.do?OC=${apiKey}&target=law&type=JSON&query=${encodeURIComponent(query)}&display=${limit}`;
      const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (!resp.ok) return `API 오류: ${resp.status}`;

      const data = await resp.json();
      const laws = data.LawSearch?.law || [];

      if (laws.length === 0) return `"${query}"에 해당하는 법령을 찾을 수 없습니다`;

      return laws
        .map((law: any, i: number) =>
          `[${i + 1}] ${law.법령명한글} (${law.공포일자})\n   ID: ${law.법령ID}`
        )
        .join("\n\n");
    } catch (e: any) {
      return `검색 실패: ${e.message}`;
    }
  },
};

// ─── 도구 3: 판례 검색 ─────────────────────────────────────────

const searchCaseTool: ToolDefinition = {
  name: "search_case",
  description: "한국 판례를 검색합니다.",
  parameters: {
    type: "object",
    properties: {
      query: { type: "string" },
      limit: { type: "number", default: 3 },
    },
    required: ["query"],
  },
  handler: async ({ query, limit = 3 }) => {
    const apiKey = process.env.LAW_GO_KR_API_KEY;
    if (!apiKey) return "⚠️ API 키 없음";

    try {
      const url = `http://www.law.go.kr/DRF/lawSearch.do?OC=${apiKey}&target=prec&type=JSON&query=${encodeURIComponent(query)}&display=${limit}`;
      const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (!resp.ok) return `오류: ${resp.status}`;

      const data = await resp.json();
      const cases = data.PrecSearch?.prec || [];

      if (cases.length === 0) return "판례 없음";

      return cases
        .map((c: any, i: number) => `[${i + 1}] ${c.사건명}\n   ${c.법원명} ${c.사건번호} (${c.선고일자})`)
        .join("\n\n");
    } catch (e: any) {
      return `검색 실패: ${e.message}`;
    }
  },
};

// ─── 도구 4: 날짜/시간 ─────────────────────────────────────────

const getDateTool: ToolDefinition = {
  name: "get_date",
  description: "현재 한국 날짜와 시간을 가져옵니다.",
  parameters: {
    type: "object",
    properties: {
      format: { type: "string", description: "'korean' 또는 'iso'", default: "korean" },
    },
  },
  handler: async ({ format = "korean" }) => {
    const now = new Date();
    if (format === "iso") return now.toISOString();

    const weekdays = ["일", "월", "화", "수", "목", "금", "토"];
    return `${now.getFullYear()}년 ${now.getMonth() + 1}월 ${now.getDate()}일 ${weekdays[now.getDay()]}요일 ${now.getHours()}시 ${now.getMinutes()}분`;
  },
};

// ─── 도구 5: 코드 실행 (Python 샌드박스) ────────────────────────

const codeExecTool: ToolDefinition = {
  name: "code_exec",
  description: "Python 코드를 샌드박스에서 실행하고 결과를 반환합니다. (제한된 라이브러리)",
  parameters: {
    type: "object",
    properties: {
      code: { type: "string", description: "실행할 Python 코드" },
    },
    required: ["code"],
  },
  handler: async ({ code }) => {
    // 실제 구현은 Docker 샌드박스 또는 Python API 서버 필요
    // 여기선 stub
    try {
      const sandboxUrl = process.env.PYTHON_SANDBOX_URL;
      if (!sandboxUrl) return "⚠️ Python 샌드박스 미설정 (PYTHON_SANDBOX_URL)";

      const resp = await fetch(`${sandboxUrl}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, timeout: 10 }),
        signal: AbortSignal.timeout(15000),
      });

      if (!resp.ok) return `실행 실패: ${resp.status}`;
      const data = await resp.json();
      return data.output || data.error || "출력 없음";
    } catch (e: any) {
      return `실행 실패: ${e.message}`;
    }
  },
};

// ─── 도구 6: 웹 검색 ───────────────────────────────────────────

const webSearchTool: ToolDefinition = {
  name: "web_search",
  description: "실시간 웹 검색 (최신 정보).",
  parameters: {
    type: "object",
    properties: {
      query: { type: "string" },
      limit: { type: "number", default: 5 },
    },
    required: ["query"],
  },
  handler: async ({ query, limit = 5 }) => {
    // Google/Bing/Naver API 중 하나 사용
    const apiKey = process.env.SEARCH_API_KEY;
    if (!apiKey) return "⚠️ 검색 API 키 미설정";

    // Naver 검색 API (한국 특화)
    const clientId = process.env.NAVER_CLIENT_ID;
    const clientSecret = process.env.NAVER_CLIENT_SECRET;

    if (clientId && clientSecret) {
      try {
        const url = `https://openapi.naver.com/v1/search/webkr.json?query=${encodeURIComponent(query)}&display=${limit}`;
        const resp = await fetch(url, {
          headers: {
            "X-Naver-Client-Id": clientId,
            "X-Naver-Client-Secret": clientSecret,
          },
          signal: AbortSignal.timeout(5000),
        });
        if (!resp.ok) return `검색 실패: ${resp.status}`;
        const data = await resp.json();
        return (data.items || [])
          .map((item: any, i: number) =>
            `[${i + 1}] ${item.title.replace(/<[^>]*>/g, "")}\n   ${item.description.replace(/<[^>]*>/g, "").slice(0, 200)}\n   ${item.link}`
          )
          .join("\n\n");
      } catch (e: any) {
        return `검색 실패: ${e.message}`;
      }
    }

    return "검색 API가 설정되지 않았습니다";
  },
};

// ─── 도구 7: 환율 ──────────────────────────────────────────────

const getExchangeTool: ToolDefinition = {
  name: "get_exchange",
  description: "실시간 환율 정보.",
  parameters: {
    type: "object",
    properties: {
      from: { type: "string", description: "기준 통화 (USD, EUR, JPY, CNY 등)" },
      to: { type: "string", description: "대상 통화 (기본 KRW)", default: "KRW" },
    },
    required: ["from"],
  },
  handler: async ({ from, to = "KRW" }) => {
    try {
      // ExchangeRate API (공개)
      const url = `https://api.exchangerate-api.com/v4/latest/${from.toUpperCase()}`;
      const resp = await fetch(url, { signal: AbortSignal.timeout(3000) });
      if (!resp.ok) return `환율 API 오류: ${resp.status}`;
      const data = await resp.json();
      const rate = data.rates?.[to.toUpperCase()];
      if (!rate) return `${to} 환율을 찾을 수 없습니다`;
      return `1 ${from.toUpperCase()} = ${rate.toLocaleString("ko-KR")} ${to.toUpperCase()} (기준: ${data.date})`;
    } catch (e: any) {
      return `환율 조회 실패: ${e.message}`;
    }
  },
};

// ─── 전체 도구 레지스트리 ──────────────────────────────────────

export const HWARANG_TOOLS: ToolDefinition[] = [
  calculatorTool,
  searchLawTool,
  searchCaseTool,
  getDateTool,
  codeExecTool,
  webSearchTool,
  getExchangeTool,
];

export function getToolsForDomain(domain: string): ToolDefinition[] {
  const allTools = HWARANG_TOOLS;

  // 도메인별 관련 도구만 반환
  if (domain === "legal") {
    return [searchLawTool, searchCaseTool, webSearchTool, getDateTool];
  }
  if (domain === "tax") {
    return [calculatorTool, searchLawTool, webSearchTool, getDateTool, getExchangeTool];
  }
  if (domain === "coding") {
    return [codeExecTool, webSearchTool, calculatorTool];
  }
  if (domain === "finance") {
    return [calculatorTool, webSearchTool, getExchangeTool, getDateTool];
  }

  return allTools;  // 일반은 전부
}

// ─── OpenAI 호환 tool schema 생성 ─────────────────────────────

export function buildOpenAIToolsSchema(tools: ToolDefinition[]) {
  return tools.map((t) => ({
    type: "function",
    function: {
      name: t.name,
      description: t.description,
      parameters: t.parameters,
    },
  }));
}

// ─── 도구 실행 ─────────────────────────────────────────────────

export async function executeTool(name: string, args: any): Promise<string> {
  const tool = HWARANG_TOOLS.find((t) => t.name === name);
  if (!tool) return `⚠️ 알 수 없는 도구: ${name}`;

  try {
    return await tool.handler(args);
  } catch (e: any) {
    return `도구 실행 실패: ${e.message}`;
  }
}

// ─── Tool Use 루프 (AI가 도구 호출 요청 → 실행 → 결과 전달) ──

export async function runAgenticLoop(
  initialMessages: any[],
  domain: string,
  vllmEndpoint: string,
  model: string,
  maxIterations: number = 5
): Promise<{
  finalResponse: string;
  toolCalls: Array<{ name: string; args: any; result: string }>;
  iterations: number;
}> {
  const tools = getToolsForDomain(domain);
  const toolsSchema = buildOpenAIToolsSchema(tools);

  const messages = [...initialMessages];
  const toolCalls: Array<{ name: string; args: any; result: string }> = [];
  let iterations = 0;

  while (iterations < maxIterations) {
    iterations++;

    const resp = await fetch(`${vllmEndpoint}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        messages,
        tools: toolsSchema,
        tool_choice: "auto",
        max_tokens: 2048,
      }),
      signal: AbortSignal.timeout(60000),
    });

    if (!resp.ok) {
      return {
        finalResponse: `도구 사용 중 오류 (${resp.status})`,
        toolCalls,
        iterations,
      };
    }

    const data = await resp.json();
    const choice = data.choices?.[0];
    const message = choice?.message;

    if (!message) break;

    messages.push(message);

    // 도구 호출 있으면 실행
    if (message.tool_calls && message.tool_calls.length > 0) {
      for (const tc of message.tool_calls) {
        const name = tc.function?.name;
        const args = JSON.parse(tc.function?.arguments || "{}");
        const result = await executeTool(name, args);
        toolCalls.push({ name, args, result });

        messages.push({
          role: "tool",
          tool_call_id: tc.id,
          content: result,
        });
      }
      continue;  // 다시 LLM 호출
    }

    // 도구 호출 없으면 최종 답변
    return {
      finalResponse: message.content || "",
      toolCalls,
      iterations,
    };
  }

  return {
    finalResponse: "도구 사용 반복 한도 초과",
    toolCalls,
    iterations,
  };
}
