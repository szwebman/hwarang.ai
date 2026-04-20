/**
 * HQL - Hwarang Quantum Learning
 *
 * 화랑 독자 혁신 기법 #6
 *
 * 여러 LoRA를 동시 학습 (superposition) → 추론 시점에 가중 합성(측정).
 * Mixture-of-LoRAs의 발전형.
 *
 * 같은 데이터로 여러 페르소나(친근/전문/간결) 학습 가능.
 */

import { prisma } from "../db";

export interface LoRAMixture {
  adapterName: string;
  weight: number;              // 합성 가중치 (0~1, 합계 1)
  description?: string;
}

export interface QuantumState {
  mixtures: LoRAMixture[];
  preset: string;              // "friendly", "expert", "concise" 등
  contextFactors: {
    userLevel?: "beginner" | "intermediate" | "expert";
    urgency?: "relaxed" | "urgent";
    domain?: string;
  };
}

// 프리셋: 페르소나별 LoRA 혼합 비율
export const QUANTUM_PRESETS: Record<string, LoRAMixture[]> = {
  friendly: [
    { adapterName: "hwarang-base", weight: 0.5, description: "베이스" },
    { adapterName: "hwarang-casual", weight: 0.3, description: "친근 어투" },
    { adapterName: "hwarang-empathy", weight: 0.2, description: "공감 표현" },
  ],
  expert: [
    { adapterName: "hwarang-base", weight: 0.3 },
    { adapterName: "hwarang-technical", weight: 0.4 },
    { adapterName: "hwarang-precise", weight: 0.3 },
  ],
  concise: [
    { adapterName: "hwarang-base", weight: 0.6 },
    { adapterName: "hwarang-short", weight: 0.4 },
  ],
  creative: [
    { adapterName: "hwarang-base", weight: 0.4 },
    { adapterName: "hwarang-creative", weight: 0.4 },
    { adapterName: "hwarang-examples", weight: 0.2 },
  ],
  legal_formal: [
    { adapterName: "hwarang-legal", weight: 0.7 },
    { adapterName: "hwarang-formal", weight: 0.3 },
  ],
  code_detailed: [
    { adapterName: "hwarang-code", weight: 0.6 },
    { adapterName: "hwarang-examples", weight: 0.2 },
    { adapterName: "hwarang-technical", weight: 0.2 },
  ],
};

/**
 * 컨텍스트에 따라 LoRA 혼합 결정
 */
export function determineQuantumState(ctx: {
  userLevel?: "beginner" | "intermediate" | "expert";
  urgency?: "relaxed" | "urgent";
  domain?: string;
  tone?: string;
}): QuantumState {
  // 도메인 + 톤 조합으로 프리셋 선택
  let preset = "friendly";

  if (ctx.domain === "legal" || ctx.domain === "tax") {
    preset = "legal_formal";
  } else if (ctx.domain === "coding") {
    preset = "code_detailed";
  } else if (ctx.userLevel === "expert") {
    preset = "expert";
  } else if (ctx.urgency === "urgent") {
    preset = "concise";
  }

  return {
    mixtures: QUANTUM_PRESETS[preset] || QUANTUM_PRESETS.friendly,
    preset,
    contextFactors: {
      userLevel: ctx.userLevel,
      urgency: ctx.urgency,
      domain: ctx.domain,
    },
  };
}

/**
 * vLLM 요청에 LoRA 혼합 힌트 전달.
 * vLLM 최신 버전은 weighted LoRA 지원 (lora_request에 가중치)
 */
export function applyHQL(requestBody: any, state: QuantumState): any {
  const primary = state.mixtures[0];
  if (!primary) return requestBody;

  return {
    ...requestBody,
    // 모델명은 원본 유지 (LoRA 어댑터가 실제 로드된 경우에만 교체)
    // model: primary.adapterName,  // ← LoRA 미지원 시 모델명 덮어쓰기 방지
    // 추가 LoRA 힌트 (서버가 지원하면 참고)
    extra_body: {
      ...(requestBody.extra_body || {}),
      lora_mixture: state.mixtures.map((m) => ({
        name: m.adapterName,
        weight: m.weight,
      })),
      hwarang_preset: state.preset,
    },
  };
}

/**
 * 사용자 설정으로 프리셋 저장 (MMRM 연동)
 */
export async function saveUserQuantumPreset(userId: string, preset: string): Promise<void> {
  try {
    await prisma.systemSetting.upsert({
      where: { key: `hql_preset_${userId}` },
      update: { value: preset },
      create: { key: `hql_preset_${userId}`, value: preset },
    });
  } catch {}
}

export async function getUserQuantumPreset(userId: string): Promise<string | null> {
  try {
    const s = await prisma.systemSetting.findUnique({
      where: { key: `hql_preset_${userId}` },
    });
    return s?.value || null;
  } catch {
    return null;
  }
}
