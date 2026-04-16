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
