/**
 * HNTL - Hwarang Neural Topic Lock
 *
 * 화랑 독자 혁신 기법 #1
 *
 * 주제별 전용 뉴런 경로(LoRA)를 학습 → 질문 도메인 감지 시 해당 LoRA만 활성화.
 * Mixture-of-LoRAs 스타일의 한국 도메인 라우터.
 *
 * 장점:
 *   - 속도 ↑ (관련 LoRA만 로드)
 *   - 정확도 ↑ (도메인 전용 가중치)
 *   - 확장성 ↑ (LoRA만 추가하면 새 도메인)
 */

import { prisma } from "@/lib/db";

export interface NeuralPath {
  domain: string;
  loraName: string;          // vLLM이 로드할 LoRA 이름 ("" 면 베이스만)
  backendId: string;          // 베이스 모델 vLLM ID
  modelName: string;          // AIModel.name (DB 키)
  description: string;
}

// 도메인 ↔ category 매핑 (TACS 도메인 명을 AIModel.category 로 변환)
const DOMAIN_TO_CATEGORY: Record<string, string> = {
  legal: "legal",
  tax: "tax",
  coding: "coding",
  code: "coding",
  medical: "medical",
  finance: "tax",   // 금융 도메인은 세무 라우트로 폴백 (없으면 별도 학습)
  general: "general",
};

// DB 조회 캐시 (60초)
let _routeCache: {
  map: Record<string, NeuralPath>;
  fallback: NeuralPath | null;
  expiresAt: number;
} | null = null;

async function loadRoutesFromDB(): Promise<{
  map: Record<string, NeuralPath>;
  fallback: NeuralPath | null;
}> {
  const now = Date.now();
  if (_routeCache && _routeCache.expiresAt > now) {
    return { map: _routeCache.map, fallback: _routeCache.fallback };
  }

  const map: Record<string, NeuralPath> = {};
  let fallback: NeuralPath | null = null;

  try {
    const models = await prisma.aIModel.findMany({
      where: { isActive: true },
      orderBy: [
        { isDomainDefault: "desc" },
        { isDefault: "desc" },
        { sortOrder: "asc" },
      ],
    });

    // 카테고리별로 첫 번째(우선순위 높은) 모델만 라우팅에 사용
    for (const m of models) {
      if (!map[m.category]) {
        map[m.category] = {
          domain: m.category,
          loraName: m.loraName || "",
          backendId: m.backendId,
          modelName: m.name,
          description: m.description || `${m.category} 도메인`,
        };
      }
    }

    // 전역 폴백: isDefault=true 모델 (없으면 첫 번째 활성 모델)
    const defaultModel = models.find((m) => m.isDefault) || models[0];
    if (defaultModel) {
      fallback = {
        domain: "fallback",
        loraName: "",  // 폴백은 항상 베이스 (LoRA 안 씀)
        backendId: defaultModel.backendId,
        modelName: defaultModel.name,
        description: `전역 기본 (${defaultModel.displayName})`,
      };
    }
  } catch (e) {
    console.warn("[HNTL] DB 조회 실패:", e);
  }

  _routeCache = { map, fallback, expiresAt: now + 60_000 };
  return { map, fallback };
}

export function clearRouteCache() {
  _routeCache = null;
}

// 폴백 체인: domain → category 매칭 → 전역 기본 (isDefault) → 빈 path
function _resolve(map: Record<string, NeuralPath>, fallback: NeuralPath | null, domain: string): NeuralPath {
  const category = DOMAIN_TO_CATEGORY[domain] || "general";
  return (
    map[category] ||
    fallback || {
      domain: "general",
      loraName: "",
      backendId: "",
      modelName: "",
      description: "라우팅 미설정 (관리자에서 모델 등록 + isDefault 체크 필요)",
    }
  );
}

/**
 * 도메인에 따라 적절한 뉴런 경로 선택 (DB 기반, 동기).
 * 캐시 데이터 사용 — 첫 호출 시엔 빈 결과 가능, 그 후엔 정확.
 */
export function selectNeuralPath(domain: string): NeuralPath {
  return _resolve(_routeCache?.map || {}, _routeCache?.fallback || null, domain);
}

/**
 * 도메인에 따라 적절한 뉴런 경로 선택 (비동기, DB 우선).
 * 캐시 미스 시 DB 조회.
 */
export async function selectNeuralPathAsync(domain: string): Promise<NeuralPath> {
  const { map, fallback } = await loadRoutesFromDB();
  return _resolve(map, fallback, domain);
}

// 라우팅 정보 디버그용 (관리자 UI 가 호출)
export async function getRoutingTable(): Promise<{
  map: Record<string, NeuralPath>;
  fallback: NeuralPath | null;
}> {
  return loadRoutesFromDB();
}

/**
 * 코딩 질문의 복잡도 감지 → 모델 선택.
 *
 * 하이브리드 방식 (정확도 85%):
 *   1. 키워드 매칭 (복잡/간단 패턴)
 *   2. 질문 길이/구조 분석
 *   3. 코드 블록 분석 (언어, 줄 수, 복잡도)
 *   4. 파일/모듈 언급 수
 *   5. 대화 턴 수 (context 기반)
 *   → 복합 점수 0~100 산출 → 임계값 50 이상이면 complex
 */

export interface ComplexityResult {
  level: "simple" | "complex";
  score: number;          // 0~100
  reasons: string[];      // 판단 근거
  recommendedModel: string;
}

export function detectCodingComplexity(
  userMessage: string,
  context?: {
    conversationTurns?: number;     // 이 대화의 총 턴 수
    previousMessages?: string[];    // 이전 메시지들 (선택)
    userPlan?: string;
  }
): ComplexityResult {
  const text = userMessage;
  const textLower = text.toLowerCase();
  let score = 0;
  const reasons: string[] = [];

  // ═══════════════════════════════════════════════
  // 1. 키워드 매칭 (가중치 부여)
  // ═══════════════════════════════════════════════

  // 복잡 키워드 (각각 가중치 다름)
  const complexKeywords: Array<{ pattern: RegExp; weight: number; reason: string }> = [
    // 프로젝트 규모 (높은 가중치)
    { pattern: /(전체|모든|full)\s*(프로젝트|project|codebase|레포|repository)/i, weight: 20, reason: "전체 프로젝트 대상" },
    { pattern: /(아키텍처|architecture)\s*(설계|design|변경|수정)/i, weight: 25, reason: "아키텍처 설계" },
    { pattern: /(마이그레이션|migrate|migration|업그레이드|upgrade)/i, weight: 20, reason: "마이그레이션/업그레이드" },

    // 복잡한 작업 (중간 가중치)
    { pattern: /(멀티|multi)\s*(파일|file|모듈|module)/i, weight: 15, reason: "멀티 파일 작업" },
    { pattern: /(리팩토링|refactor).*(전체|대규모|여러|multi|all|모든)/i, weight: 15, reason: "대규모 리팩토링" },
    { pattern: /(대규모|large[- ]?scale|enterprise)/i, weight: 15, reason: "대규모 시스템" },
    { pattern: /(복잡한|complex|sophisticated)\s*(알고리즘|로직|시스템|구조)/i, weight: 15, reason: "복잡한 구조/알고리즘" },
    { pattern: /(최적화|optimize|optimization|performance|성능)\s.*(시스템|system|database|DB|쿼리|query|서버|server)/i, weight: 15, reason: "시스템 최적화" },
    { pattern: /(분석|analyze|분석해|review).*(코드|code|project|전체|패턴|pattern)/i, weight: 12, reason: "코드 분석" },
    { pattern: /(보안|security|취약점|vulnerability|XSS|SQL.*injection)/i, weight: 15, reason: "보안 관련" },
    { pattern: /(테스트|test|testing)\s*(전략|strategy|커버리지|coverage|suite)/i, weight: 12, reason: "테스트 전략" },
    { pattern: /(CI\s*\/?\s*CD|배포|deploy|pipeline|파이프라인|kubernetes|k8s|docker.*compose)/i, weight: 12, reason: "배포/인프라" },
    { pattern: /(설계|design)\s*(패턴|pattern)/i, weight: 12, reason: "디자인 패턴" },

    // 낮은 가중치 (단독으로는 simple일 수도)
    { pattern: /(디버그|debug|디버깅).*(어려운|복잡|이상한|원인|모르겠)/i, weight: 8, reason: "복잡 디버깅" },
    { pattern: /(타입|type)\s*(시스템|system|추론|inference|generic)/i, weight: 8, reason: "타입 시스템" },
    { pattern: /(동시성|concurrency|병렬|parallel|async|비동기)\s*(처리|문제|이슈)/i, weight: 10, reason: "동시성 문제" },
  ];

  // 간단 키워드 (감점)
  const simpleKeywords: Array<{ pattern: RegExp; weight: number; reason: string }> = [
    { pattern: /(만들|만들어|짜줘|작성해?줘?|write|create)\s*(함수|function|코드|code|메서드|method)/i, weight: -10, reason: "단순 함수 요청" },
    { pattern: /(버그|bug|오류|error|에러)\s*.*(고쳐|fix|수정|해결)/i, weight: -8, reason: "단순 버그 수정" },
    { pattern: /(무엇|뭐야|뭔가|what\s*is|what\s*are)/i, weight: -12, reason: "개념 질문" },
    { pattern: /(설명|explain|알려줘|가르쳐)/i, weight: -8, reason: "설명 요청" },
    { pattern: /(예제|example|예시|샘플|sample)/i, weight: -5, reason: "예제 요청" },
    { pattern: /(형식|format|syntax|문법)/i, weight: -8, reason: "문법/형식 질문" },
    { pattern: /(변환|convert|transform)\s*(해줘|해)/i, weight: -5, reason: "단순 변환" },
  ];

  for (const { pattern, weight, reason } of complexKeywords) {
    if (pattern.test(text)) {
      score += weight;
      reasons.push(`+${weight} ${reason}`);
    }
  }

  for (const { pattern, weight, reason } of simpleKeywords) {
    if (pattern.test(text)) {
      score += weight; // weight가 음수
      reasons.push(`${weight} ${reason}`);
    }
  }

  // ═══════════════════════════════════════════════
  // 2. 질문 길이/구조 분석
  // ═══════════════════════════════════════════════

  const msgLength = text.length;

  if (msgLength < 50) {
    score -= 15;
    reasons.push("-15 짧은 질문 (<50자)");
  } else if (msgLength < 100) {
    score -= 5;
    reasons.push("-5 보통 길이 (<100자)");
  } else if (msgLength > 500) {
    score += 10;
    reasons.push("+10 긴 질문 (>500자)");
  } else if (msgLength > 1000) {
    score += 20;
    reasons.push("+20 매우 긴 질문 (>1000자)");
  }

  // 줄바꿈 수 (요구사항이 많으면 복잡)
  const lineCount = (text.match(/\n/g) || []).length;
  if (lineCount >= 10) {
    score += 10;
    reasons.push(`+10 다중 줄 요구사항 (${lineCount}줄)`);
  } else if (lineCount >= 5) {
    score += 5;
    reasons.push(`+5 여러 줄 (${lineCount}줄)`);
  }

  // 번호 목록 (요구사항 나열)
  const numberedItems = (text.match(/^\s*\d+[\.\)]/gm) || []).length;
  if (numberedItems >= 3) {
    score += 10;
    reasons.push(`+10 ${numberedItems}개 요구사항 나열`);
  }

  // ═══════════════════════════════════════════════
  // 3. 코드 블록 분석
  // ═══════════════════════════════════════════════

  const codeBlocks = text.match(/```[\s\S]*?```/g) || [];
  const totalCodeLines = codeBlocks.reduce((sum, block) => {
    return sum + (block.match(/\n/g) || []).length;
  }, 0);

  if (codeBlocks.length === 0) {
    // 코드 없음 - 중립
  } else if (codeBlocks.length === 1 && totalCodeLines < 20) {
    score += 3;
    reasons.push("+3 짧은 코드 블록 1개");
  } else if (codeBlocks.length === 1 && totalCodeLines >= 20) {
    score += 12;
    reasons.push(`+12 긴 코드 블록 (${totalCodeLines}줄)`);
  } else if (codeBlocks.length >= 2) {
    score += 15;
    reasons.push(`+15 코드 블록 ${codeBlocks.length}개 (${totalCodeLines}줄)`);
  }

  // 코드에 여러 파일 패턴 감지
  const filePatterns = text.match(/(?:\/[\w\-]+)+\.\w+/g) || [];       // /path/to/file.ts
  const importPatterns = text.match(/(?:import|from|require)\s/g) || [];

  if (filePatterns.length >= 3) {
    score += 12;
    reasons.push(`+12 ${filePatterns.length}개 파일 경로 언급`);
  } else if (filePatterns.length >= 1) {
    score += 5;
    reasons.push(`+5 ${filePatterns.length}개 파일 경로`);
  }

  if (importPatterns.length >= 5) {
    score += 8;
    reasons.push(`+8 ${importPatterns.length}개 import/require`);
  }

  // ═══════════════════════════════════════════════
  // 4. 파일/모듈 언급 수
  // ═══════════════════════════════════════════════

  const fileExtensions = text.match(/\.\w{1,5}\b/g) || [];
  const uniqueExtensions = new Set(fileExtensions.map((e) => e.toLowerCase()));

  // 여러 확장자 = 멀티파일 작업
  if (uniqueExtensions.size >= 3) {
    score += 10;
    reasons.push(`+10 ${uniqueExtensions.size}개 파일 타입 (${[...uniqueExtensions].join(", ")})`);
  }

  // 구체적 파일명 언급 수
  const fileNames = text.match(/[\w\-]+\.\w{1,5}/g) || [];
  if (fileNames.length >= 5) {
    score += 10;
    reasons.push(`+10 ${fileNames.length}개 파일명 언급`);
  } else if (fileNames.length >= 3) {
    score += 5;
    reasons.push(`+5 ${fileNames.length}개 파일명 언급`);
  }

  // ═══════════════════════════════════════════════
  // 5. 대화 맥락 (턴 수, 이전 메시지)
  // ═══════════════════════════════════════════════

  if (context?.conversationTurns) {
    // 긴 대화 = 복잡한 작업 진행 중
    if (context.conversationTurns >= 10) {
      score += 10;
      reasons.push(`+10 긴 대화 (${context.conversationTurns}턴)`);
    } else if (context.conversationTurns >= 5) {
      score += 5;
      reasons.push(`+5 진행 중 대화 (${context.conversationTurns}턴)`);
    }
  }

  // 이전 메시지에서 복잡 패턴 감지
  if (context?.previousMessages) {
    const prevText = context.previousMessages.join(" ");
    const prevCodeBlocks = (prevText.match(/```/g) || []).length / 2;
    if (prevCodeBlocks >= 5) {
      score += 8;
      reasons.push(`+8 이전 대화에 코드 블록 ${Math.floor(prevCodeBlocks)}개`);
    }
  }

  // ═══════════════════════════════════════════════
  // 6. 특수 패턴 감지
  // ═══════════════════════════════════════════════

  // 에러 로그/스택 트레이스 포함 → 복잡 디버깅
  if (/(?:Error|Exception|Traceback|at\s+[\w.]+\()/i.test(text) && msgLength > 200) {
    score += 10;
    reasons.push("+10 에러 로그/스택트레이스 포함");
  }

  // "왜" 질문 + 코드 = 깊은 분석 필요
  if (/왜.*(?:안|않|못|에러|오류|문제)/i.test(text) && codeBlocks.length > 0) {
    score += 8;
    reasons.push("+8 '왜 안 되는지' + 코드 분석");
  }

  // ═══════════════════════════════════════════════
  // 최종 판정 (0~100, 임계값 50)
  // ═══════════════════════════════════════════════

  // 점수 정규화 (0~100 범위로)
  score = Math.max(0, Math.min(100, score + 30)); // 기본 30에서 시작

  const level: "simple" | "complex" = score >= 50 ? "complex" : "simple";

  return {
    level,
    score,
    reasons,
    recommendedModel: level === "complex" ? "hwarang-pro" : "hwarang-coder",
  };
}

/**
 * 도메인 + 복잡도 + 플랜으로 최종 모델 선택.
 *
 * Returns: { model, complexity }
 */
export interface ModelSelection {
  model: string;            // DB의 AIModel.name
  complexity?: ComplexityResult;
  reason: string;
}

/**
 * DB 라우팅 테이블 기반으로 도메인별 모델 선택.
 * 동기 호환을 위해 캐시된 _routeCache 사용. 캐시 비어있으면 isDefault → general → 폴백 체인.
 *
 * 폴백 정책 (사용자 결정):
 *   1. 도메인에 매칭되는 활성 모델 있으면 그걸 사용
 *   2. 없으면 isDefault=true 인 전역 기본 모델 사용 (계속 그것만)
 */
export function selectModel(
  domain: string,
  userMessage: string,
  userPlan?: string,
  conversationContext?: {
    conversationTurns?: number;
    previousMessages?: string[];
  }
): ModelSelection {
  const path = selectNeuralPath(domain);

  // 코딩은 복잡도 정보를 제공 (UI 표시용 메타데이터)
  if (domain === "coding") {
    const complexity = detectCodingComplexity(userMessage, {
      conversationTurns: conversationContext?.conversationTurns,
      previousMessages: conversationContext?.previousMessages,
      userPlan,
    });
    return {
      model: path.modelName || "fallback",
      complexity,
      reason: path.modelName
        ? `코딩 도메인 (점수 ${complexity.score}/100) → ${path.description}`
        : "코딩 모델 미등록 → 전역 기본",
    };
  }

  // 그 외 도메인 — DB 매칭 결과 그대로
  return {
    model: path.modelName || "fallback",
    reason: path.modelName
      ? `${domain} 도메인 → ${path.description}`
      : `${domain} 모델 미등록 → 전역 기본 폴백`,
  };
}

/**
 * vLLM 요청에 LoRA 지정 주입.
 * vLLM은 --enable-lora 옵션으로 실행되어야 함.
 *
 * ⚠ 안전장치: 실제로 vLLM 에 로드된 모델/LoRA 만 사용.
 * 미로드 LoRA 가 지정되면 베이스 모델로 폴백.
 */

// vLLM 가용 모델 캐시 (60초)
let _modelsCache: { ids: Set<string>; expiresAt: number } | null = null;

async function getAvailableModels(endpoint: string): Promise<Set<string>> {
  const now = Date.now();
  if (_modelsCache && _modelsCache.expiresAt > now) {
    return _modelsCache.ids;
  }
  try {
    const url = endpoint.replace(/\/v1\/?$/, "") + "/v1/models";
    const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data: any = await res.json();
    const ids = new Set<string>(
      (data.data || []).map((m: any) => String(m.id))
    );
    _modelsCache = { ids, expiresAt: now + 60_000 };
    return ids;
  } catch {
    // 실패 시 빈 집합 — applyHNTL 이 폴백
    _modelsCache = { ids: new Set(), expiresAt: now + 10_000 };
    return _modelsCache.ids;
  }
}

export function clearModelsCache() {
  _modelsCache = null;
}

export async function applyHNTL(
  requestBody: any,
  domain: string,
  endpoint?: string
): Promise<any> {
  const path = await selectNeuralPathAsync(domain);

  if (!path.loraName) {
    return requestBody;  // 일반 도메인 또는 LoRA 미설정 — 베이스만 사용
  }

  // vLLM 에 LoRA 가 실제로 로드돼 있는지 확인
  if (endpoint) {
    const available = await getAvailableModels(endpoint);
    if (available.size > 0 && !available.has(path.loraName)) {
      // LoRA 미로드 → 베이스 모델 유지 + 메타 기록
      return {
        ...requestBody,
        _hwarang_path: {
          domain: path.domain,
          lora: path.loraName,
          fallback: "base_model",
          reason: "lora_not_loaded",
        },
      };
    }
  }

  return {
    ...requestBody,
    model: path.loraName,  // LoRA 이름으로 모델 지정
    _hwarang_path: {
      domain: path.domain,
      lora: path.loraName,
      modelName: path.modelName,
    },
  };
}

/**
 * LoRA 활성화 상태 확인.
 */
export async function verifyLoRALoaded(
  vllmEndpoint: string,
  loraName: string
): Promise<boolean> {
  try {
    const resp = await fetch(`${vllmEndpoint}/v1/models`);
    if (!resp.ok) return false;
    const data = await resp.json();
    const models = (data.data || []).map((m: any) => m.id);
    return models.includes(loraName);
  } catch {
    return false;
  }
}
