/**
 * 화랑 AI 정렬 프레임워크 (Hwarang Alignment Framework)
 *
 * 10개의 독자 정렬 기법 통합
 *
 * 기본 (KCAI/GRPO/TACS): 모든 요청에 적용
 * 고급 (HRAG/NWNC/CoRD/VCoT/TADM/MMRM/LCRG): 조건부 적용
 */

export * from "./tacs";
export * from "./kcai";
export * from "./grpo";
export * from "./hrag";
export * from "./nwnc";
export * from "./cord";
export * from "./vcot";
export * from "./tadm";
export * from "./mmrm";
export * from "./lcrg";

import { applyTACS, applyTACSPostProcessing, type DomainInfo } from "./tacs";
import { buildConstitutionPrompt } from "./kcai";
import { applyHRAG } from "./hrag";
import { applyNWNC, type EmotionState } from "./nwnc";
import { applyTADM, type TemporalContext } from "./tadm";
import { applyMMRM } from "./mmrm";
import { applyLCRG } from "./lcrg";
import { buildVCoTPrompt } from "./vcot";
import { buildLCRGPrompt } from "./lcrg";

export interface AlignmentContext {
  userId?: string;
  userMessage: string;
  userPlan?: string;
  enableHRAG?: boolean;
  enableNWNC?: boolean;
  enableCoRD?: boolean;
  enableVCoT?: boolean;
  enableTADM?: boolean;
  enableMMRM?: boolean;
  enableLCRG?: boolean;
}

export interface AlignmentResult {
  systemPrompt: string;
  domainInfo: DomainInfo;
  emotion?: EmotionState;
  temporalContext?: TemporalContext;
  hragSources?: any[];
  profile?: any;
  // 후처리용
  postProcess: (response: string) => Promise<string>;
}

/**
 * 전체 정렬 프레임워크를 적용.
 * 사전 처리(시스템 프롬프트 생성) + 사후 처리(응답 검증).
 */
export async function applyFullAlignment(
  ctx: AlignmentContext
): Promise<AlignmentResult> {
  const parts: string[] = [];

  // ─── 기본 계층 (항상 적용) ───────────────────────────────
  parts.push(buildConstitutionPrompt(["language", "safety", "ethics"]));

  const { domainInfo, systemPrompt: tacsPrompt } = applyTACS(ctx.userMessage);
  parts.push(tacsPrompt);

  // ─── 고급 계층 (조건부) ───────────────────────────────────
  let emotion: EmotionState | undefined;
  let temporalContext: TemporalContext | undefined;
  let hragSources: any[] = [];
  let profile: any = undefined;

  // NWNC (기본 on)
  if (ctx.enableNWNC !== false) {
    const nwnc = applyNWNC(ctx.userMessage);
    emotion = nwnc.emotion;
    parts.push(nwnc.systemPrompt);
  }

  // TADM (기본 on)
  if (ctx.enableTADM !== false) {
    const tadm = applyTADM(ctx.userMessage);
    temporalContext = tadm.context;
    parts.push(tadm.systemPrompt);
  }

  // MMRM (로그인 유저만)
  if (ctx.enableMMRM !== false && ctx.userId) {
    try {
      const mmrm = await applyMMRM(ctx.userId, ctx.userMessage);
      profile = mmrm.profile;
      if (mmrm.systemPrompt) parts.push(mmrm.systemPrompt);
    } catch {}
  }

  // HRAG (법률/세무/날씨만)
  if (ctx.enableHRAG !== false) {
    try {
      const hrag = await applyHRAG(ctx.userMessage);
      hragSources = hrag.sources;
      if (hrag.context) parts.push(hrag.context);
    } catch {}
  }

  // VCoT (법률/세무/계산 도메인)
  if (ctx.enableVCoT !== false &&
      (domainInfo.domain === "legal" || domainInfo.domain === "tax")) {
    parts.push(buildVCoTPrompt());
  }

  // LCRG 안내 (법률 인용 정확성)
  if (ctx.enableLCRG !== false &&
      (domainInfo.domain === "legal" || domainInfo.domain === "tax")) {
    parts.push(buildLCRGPrompt());
  }

  const systemPrompt = parts.join("\n");

  // ─── 사후 처리 함수 ────────────────────────────────────────
  const postProcess = async (response: string): Promise<string> => {
    let result = response;

    // TACS: 면책조항 + 리소스
    result = applyTACSPostProcessing(result, domainInfo);

    // LCRG: 인용 검증
    if (ctx.enableLCRG !== false &&
        (domainInfo.domain === "legal" || domainInfo.domain === "tax")) {
      try {
        const lcrg = await applyLCRG(result);
        result = lcrg.text;
      } catch {}
    }

    return result;
  };

  return {
    systemPrompt,
    domainInfo,
    emotion,
    temporalContext,
    hragSources,
    profile,
    postProcess,
  };
}
