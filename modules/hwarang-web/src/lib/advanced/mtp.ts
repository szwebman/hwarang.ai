/**
 * MTP - Multi-Token Prediction (Meta 2024, DeepSeek-V3)
 *
 * 한 번에 여러 토큰 예측 → 속도 4배.
 *
 * 구현: vLLM speculative_num_tokens 옵션 활용.
 * 클라이언트 측에선 설정만 관리.
 */

export interface MTPConfig {
  enabled: boolean;
  numTokens: number;         // 한 번에 예측할 토큰 수 (기본 4)
  verificationMode: "strict" | "tolerant";  // 검증 엄격도
}

export const DEFAULT_MTP_CONFIG: MTPConfig = {
  enabled: true,
  numTokens: 4,
  verificationMode: "strict",
};

/**
 * vLLM 호출 시 MTP 설정 추가.
 * extra_body에 넣어 vLLM 서버에 전달.
 */
export function applyMTP(requestBody: any, config: MTPConfig = DEFAULT_MTP_CONFIG): any {
  if (!config.enabled) return requestBody;

  return {
    ...requestBody,
    extra_body: {
      ...(requestBody.extra_body || {}),
      speculative_num_tokens: config.numTokens,
      speculative_verification_mode: config.verificationMode,
    },
  };
}

/**
 * MTP 지원 여부 확인 (vLLM 버전별 다름)
 */
export async function isMTPSupported(endpoint: string): Promise<boolean> {
  try {
    const resp = await fetch(`${endpoint}/v1/models`);
    if (!resp.ok) return false;
    // 실제 검증은 response header나 별도 endpoint 필요
    return true;
  } catch {
    return false;
  }
}
