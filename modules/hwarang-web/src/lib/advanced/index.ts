/**
 * 화랑 AI 고급 추론 기법 (2025~2026)
 *
 * 최첨단 학계/산업계 기법을 화랑에 적용
 */

export * from "./ttt";
export * from "./coa";
export * from "./reasoning_scaling";
export * from "./act";
export * from "./mtp";
export * from "./quiet_star";

import { applyTTT } from "./ttt";
import { applyReasoningScaling, needsDeepReasoning, extractThinking } from "./reasoning_scaling";
import { applyACT, type ACTConfig } from "./act";
import { applyMTP } from "./mtp";
import { applyQuietSTaR } from "./quiet_star";

export interface AdvancedContext {
  userMessage: string;
  domain: string;
  enableTTT?: boolean;
  enableReasoning?: boolean;
  enableMTP?: boolean;
  enableQuietSTaR?: boolean;
  enableACT?: boolean;
}

export interface AdvancedResult {
  systemPrompt: string;
  fewShotMessages: any[];
  actConfig: ACTConfig;
  requestBodyTransform: (body: any) => any;
  postProcess: (response: string) => string;
}

export function applyAdvanced(ctx: AdvancedContext): AdvancedResult {
  const parts: string[] = [];
  let fewShotMessages: any[] = [];
  const transformers: Array<(body: any) => any> = [];

  // ACT: 난이도 평가 먼저
  const actConfig = ctx.enableACT !== false
    ? applyACT(ctx.userMessage)
    : {
        difficulty: "medium" as const,
        maxTokens: 2048,
        useReasoning: false,
        useTTT: false,
        useCoRD: false,
        temperature: 0.7,
      };

  // TTT: 어려운 질문에 few-shot 주입
  if (ctx.enableTTT !== false && actConfig.useTTT) {
    const ttt = applyTTT(ctx.userMessage, ctx.domain, { steps: 2 });
    parts.push(ttt.systemPrompt);
    fewShotMessages = ttt.enrichedMessages;
  }

  // Reasoning Scaling: 깊은 추론 필요 시
  const useReasoning =
    ctx.enableReasoning !== false &&
    (actConfig.useReasoning || needsDeepReasoning(ctx.userMessage));

  if (useReasoning) {
    const rs = applyReasoningScaling();
    parts.push(rs.systemPrompt);
  }

  // Quiet-STaR
  if (ctx.enableQuietSTaR !== false) {
    parts.push(applyQuietSTaR());
  }

  // MTP (vLLM에서 자동 적용되지만, extra_body 추가)
  if (ctx.enableMTP !== false) {
    transformers.push((body) => applyMTP(body));
  }

  // ACT 결과로 temperature/max_tokens 조정
  transformers.push((body) => ({
    ...body,
    temperature: body.temperature ?? actConfig.temperature,
    max_tokens: body.max_tokens
      ? Math.min(body.max_tokens, actConfig.maxTokens)
      : actConfig.maxTokens,
  }));

  const requestBodyTransform = (body: any) =>
    transformers.reduce((b, t) => t(b), body);

  const postProcess = (response: string) => {
    if (useReasoning) {
      const { answer } = extractThinking(response, false);
      return answer;
    }
    return response;
  };

  return {
    systemPrompt: parts.join("\n"),
    fewShotMessages,
    actConfig,
    requestBodyTransform,
    postProcess,
  };
}
