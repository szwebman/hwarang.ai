/**
 * 화랑 AI 최적화 프레임워크
 *
 * 7개 최적화 기법 통합
 */

export * from "./hpc";
export * from "./hat";

import { applyHPC } from "./hpc";
import { getToolsForDomain, runAgenticLoop, buildOpenAIToolsSchema } from "./hat";

export interface OptimizationContext {
  domain: string;
  userPlan?: string;
  enableHPC?: boolean;
  enableHAT?: boolean;
}

/**
 * 최적화 프레임워크 적용.
 * HPC (prompt cache), HAT (agentic tools)을 조건부 활성화.
 */
export async function applyOptimization(
  messages: any[],
  ctx: OptimizationContext
): Promise<{
  messages: any[];
  cacheKey?: string;
  cacheHit?: boolean;
  headers: Record<string, string>;
  useTools: boolean;
  tools?: any[];
}> {
  const headers: Record<string, string> = {};

  // HPC: 프롬프트 캐시
  let cacheKey: string | undefined;
  let cacheHit: boolean | undefined;
  if (ctx.enableHPC !== false) {
    const result = await applyHPC(messages);
    cacheKey = result.cacheKey;
    cacheHit = result.cacheHit;
    Object.assign(headers, result.headers);
  }

  // HAT: 에이전트 도구 (Pro+ 플랜)
  const eligiblePlans = ["pro", "business", "enterprise"];
  const useTools = ctx.enableHAT !== false &&
                   (ctx.userPlan ? eligiblePlans.includes(ctx.userPlan) : false);

  let tools: any[] | undefined;
  if (useTools) {
    const toolDefs = getToolsForDomain(ctx.domain);
    tools = buildOpenAIToolsSchema(toolDefs);
  }

  return {
    messages,
    cacheKey,
    cacheHit,
    headers,
    useTools,
    tools,
  };
}
