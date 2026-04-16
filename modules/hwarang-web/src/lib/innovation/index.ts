/**
 * 화랑 AI 독자 혁신 기법
 *
 * 세계 최초 6가지 기법:
 *   HNTL - Neural Topic Lock
 *   HCE  - Community Evolution
 *   HRL  - Reality Lock
 *   HCP  - Confidence Pruning
 *   HML  - Memory Ladder
 *   HQL  - Quantum Learning
 */

export * from "./hntl";
export * from "./hce";
export * from "./hrl";
export * from "./hcp";
export * from "./hml";
export * from "./hql";

import { applyHNTL } from "./hntl";
import { applyHCE } from "./hce";
import { applyHRL } from "./hrl";
import { applyHML, shouldUseHML } from "./hml";
import { applyHQL, determineQuantumState } from "./hql";

export interface InnovationContext {
  userMessage: string;
  domain: string;
  userId?: string;
  vllmEndpoint: string;
  model: string;
  enableHNTL?: boolean;
  enableHCE?: boolean;
  enableHRL?: boolean;
  enableHML?: boolean;
  enableHQL?: boolean;
}

export interface InnovationResult {
  systemPrompt: string;
  requestBodyTransform: (body: any) => any;
  postProcess: (response: string) => Promise<string>;
  metadata: any;
}

export async function applyInnovation(ctx: InnovationContext): Promise<InnovationResult> {
  const parts: string[] = [];
  const transformers: Array<(body: any) => any> = [];
  const postProcessors: Array<(r: string) => Promise<string>> = [];
  const metadata: any = {};

  // HCE: 커뮤니티 진화 트렌드 (전역)
  if (ctx.enableHCE !== false) {
    const hcePrompt = await applyHCE();
    if (hcePrompt) parts.push(hcePrompt);
    metadata.hce = "applied";
  }

  // HML: 법률/세무 계단식 검색
  if (ctx.enableHML !== false && shouldUseHML(ctx.userMessage, ctx.domain)) {
    try {
      const hml = await applyHML(ctx.userMessage, ctx.vllmEndpoint, ctx.model);
      parts.push(hml.finalContext);
      metadata.hml = {
        steps: hml.steps.length,
        sources: hml.totalSources,
      };
    } catch {}
  }

  // HNTL: 도메인별 LoRA 라우팅
  if (ctx.enableHNTL !== false) {
    transformers.push((body) => applyHNTL(body, ctx.domain));
    metadata.hntl = { domain: ctx.domain };
  }

  // HQL: 페르소나 LoRA 혼합
  if (ctx.enableHQL !== false) {
    const state = determineQuantumState({ domain: ctx.domain });
    // HNTL과 충돌할 수 있으므로 도메인 특화가 없을 때만
    if (ctx.domain === "general") {
      transformers.push((body) => applyHQL(body, state));
    }
    metadata.hql = { preset: state.preset };
  }

  // HRL: 응답 후 실시간 팩트 체크
  if (ctx.enableHRL !== false && (ctx.domain === "legal" || ctx.domain === "tax")) {
    postProcessors.push(async (response) => {
      try {
        const hrl = await applyHRL(response);
        metadata.hrl = {
          confidence: hrl.overallConfidence,
          verified: hrl.verifiedCount,
          total: hrl.totalStatements,
        };
        return hrl.markedResponse;
      } catch {
        return response;
      }
    });
  }

  const requestBodyTransform = (body: any) =>
    transformers.reduce((b, t) => t(b), body);

  const postProcess = async (response: string) => {
    let result = response;
    for (const p of postProcessors) {
      result = await p(result);
    }
    return result;
  };

  return {
    systemPrompt: parts.join("\n"),
    requestBodyTransform,
    postProcess,
    metadata,
  };
}
