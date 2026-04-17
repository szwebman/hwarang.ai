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

export interface NeuralPath {
  domain: string;
  loraName: string;          // vLLM이 로드할 LoRA 이름
  adapter: string;            // 어댑터 경로
  description: string;
  priority: number;
}

// 도메인별 전용 경로
export const NEURAL_PATHS: Record<string, NeuralPath> = {
  legal: {
    domain: "legal",
    loraName: "hwarang-legal-lora",
    adapter: "/mnt/nvme2/hwarang/lora_adapters/legal-v1",
    description: "한국 법률 전문 뉴런 경로",
    priority: 10,
  },
  tax: {
    domain: "tax",
    loraName: "hwarang-tax-lora",
    adapter: "/mnt/nvme2/hwarang/lora_adapters/tax-v1",
    description: "한국 세무 전문 뉴런 경로",
    priority: 10,
  },
  coding: {
    domain: "coding",
    loraName: "hwarang-code-lora",
    adapter: "/mnt/nvme2/hwarang/lora_adapters/code-v1",
    description: "코딩 전문 뉴런 경로",
    priority: 8,
  },
  medical: {
    domain: "medical",
    loraName: "hwarang-medical-lora",
    adapter: "/mnt/nvme2/hwarang/lora_adapters/medical-v1",
    description: "한국 의료 전문 뉴런 경로",
    priority: 10,
  },
  finance: {
    domain: "finance",
    loraName: "hwarang-finance-lora",
    adapter: "/mnt/nvme2/hwarang/lora_adapters/finance-v1",
    description: "한국 금융 전문 뉴런 경로",
    priority: 9,
  },
  general: {
    domain: "general",
    loraName: "",  // 베이스 모델만 사용
    adapter: "",
    description: "일반 대화 (베이스 모델)",
    priority: 1,
  },
};

/**
 * 도메인에 따라 적절한 뉴런 경로 선택.
 */
export function selectNeuralPath(domain: string): NeuralPath {
  return NEURAL_PATHS[domain] || NEURAL_PATHS.general;
}

/**
 * 코딩 질문의 복잡도 감지 → 모델 선택.
 *
 * 복잡한 코딩 (Pro+ 모델 사용):
 *   - 멀티파일 리팩토링
 *   - 아키텍처 설계
 *   - 프레임워크 마이그레이션
 *   - 복잡한 알고리즘
 *   - 긴 컨텍스트 필요
 *
 * 간단한 코딩 (Coder 모델 사용):
 *   - 함수 작성
 *   - 버그 수정
 *   - 단순 리팩토링
 *   - 간단한 설명
 */
export function detectCodingComplexity(userMessage: string): "simple" | "complex" {
  const text = userMessage.toLowerCase();

  // 복잡 지표
  const complexIndicators = [
    /(전체|모든|full)\s*(프로젝트|project|codebase|레포|repository)/i,
    /(아키텍처|architecture|설계|design)/i,
    /(마이그레이션|migrate|migration)/i,
    /(리팩토링|refactor).*(여러|multi|전체|all)/i,
    /(멀티|multi)\s*(파일|file)/i,
    /(대규모|large[- ]?scale)/i,
    /(복잡한|complex|sophisticated)/i,
    /(최적화|optimize|optimization).*(시스템|system|database|쿼리|query)/i,
    /(분석|analyze).*(코드|code|project)/i,
    /(디버그|debug).*(복잡|complex|어려운)/i,
    // 긴 질문 = 복잡
    /^.{500,}$/,
  ];

  // 간단 지표
  const simpleIndicators = [
    /^.{0,80}$/,                          // 짧은 질문
    /(만들|만들어|짜줘|작성|write|create)\s*(함수|function|코드|code)/i,
    /(버그|bug|오류|error).*(고쳐|fix|수정)/i,
    /(무엇|what is|뭐야)/i,
    /(설명|explain).*(간단|simple|briefly)/i,
    /(형식|format|syntax)/i,
  ];

  const complexCount = complexIndicators.filter((p) => p.test(text)).length;
  const simpleCount = simpleIndicators.filter((p) => p.test(text)).length;

  // 코드 블록 포함 + 길이 → 복잡
  const hasCodeBlock = text.includes("```");
  const isLong = text.length > 300;

  if (complexCount >= 2 || (complexCount >= 1 && hasCodeBlock && isLong)) {
    return "complex";
  }
  if (simpleCount >= 1 && complexCount === 0) {
    return "simple";
  }
  return isLong || hasCodeBlock ? "complex" : "simple";
}

/**
 * 도메인 + 복잡도 + 플랜으로 최종 모델 선택.
 *
 * Returns: DB의 AIModel.name
 */
export function selectModel(
  domain: string,
  userMessage: string,
  userPlan?: string
): string {
  const isPaidPlan = userPlan && ["starter", "pro", "business", "enterprise"].includes(userPlan);

  // 법률/세무 도메인
  if (domain === "legal" || domain === "tax") {
    return isPaidPlan ? "hwarang-legal" : "hwarang-coder";
  }

  // 코딩 도메인: 복잡도로 분기
  if (domain === "coding") {
    const complexity = detectCodingComplexity(userMessage);

    // 복잡한 코딩 + 유료 플랜 → DeepSeek V3
    if (complexity === "complex" && isPaidPlan) {
      return "hwarang-pro";
    }

    // 간단한 코딩 또는 Free 플랜 → Qwen3-Coder
    return "hwarang-coder";
  }

  // 일반 대화
  return "hwarang-general";
}

/**
 * vLLM 요청에 LoRA 지정 주입.
 * vLLM은 --enable-lora 옵션으로 실행되어야 함.
 */
export function applyHNTL(requestBody: any, domain: string): any {
  const path = selectNeuralPath(domain);

  if (!path.loraName) {
    return requestBody;  // 일반 도메인은 베이스만 사용
  }

  return {
    ...requestBody,
    model: path.loraName,  // LoRA 이름으로 모델 지정
    _hwarang_path: {
      domain: path.domain,
      lora: path.loraName,
      adapter: path.adapter,
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
