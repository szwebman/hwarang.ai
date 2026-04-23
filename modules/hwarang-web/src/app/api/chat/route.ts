/**
 * Chat API - 전체 정렬 프레임워크 통합
 *
 * 적용 기법:
 *   ✅ KCAI  - 한국형 헌법
 *   ✅ TACS  - 도메인별 안전 체인
 *   ✅ GRPO  - 피드백 수집 (별도 엔드포인트)
 *   ✅ HRAG  - 한국 공식 DB 실시간 검색
 *   ✅ NWNC  - 눈치 기반 대화
 *   ✅ VCoT  - 검증된 추론 (법률/세무)
 *   ✅ TADM  - 시점 인식
 *   ✅ MMRM  - 계층적 메모리
 *   ✅ LCRG  - 인용 검증
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";
import crypto from "crypto";
import { applyFullAlignment } from "@/lib/alignment";
import { detectDomain } from "@/lib/alignment/tacs";
import { applyOptimization } from "@/lib/optimization";
import { runAgenticLoop } from "@/lib/optimization/hat";
import { applyAdvanced } from "@/lib/advanced";
import { applyInnovation } from "@/lib/innovation";
import { selectModel } from "@/lib/innovation/hntl";
import { hybridServing } from "@/lib/serving/hybrid-serving";
import { calculateResponseWeight, enrichResponseWithWeight, buildResponseWeightMeta } from "@/lib/serving/response-weight";

async function resolveUserId(request: NextRequest): Promise<string | null> {
  // Bearer API 키 (VS Code 확장팩 등)
  const authHeader = request.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const rawKey = authHeader.slice(7).trim();
    if (rawKey) {
      const keyHash = crypto.createHash("sha256").update(rawKey).digest("hex");
      const apiKey = await prisma.apiKey.findFirst({
        where: { keyHash, isActive: true },
        select: { userId: true, id: true },
      });
      if (apiKey) {
        prisma.apiKey
          .update({ where: { id: apiKey.id }, data: { lastUsedAt: new Date() } })
          .catch(() => {});
        return apiKey.userId;
      }
    }
  }
  // NextAuth 세션
  const session = await auth();
  return session?.user?.id || null;
}

export async function POST(request: NextRequest) {
  // ─── 1. 인증 (세션 또는 API 키) ────────────────────────
  const userId = await resolveUserId(request);
  if (!userId) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }
  let body = await request.json();

  // ─── 2. 유저 먼저 로드 (플랜 필요) ──────────────────
  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { plan: true, tokenBalance: true },
  });

  if (!user) return Response.json({ error: "유저 없음" }, { status: 404 });

  // ─── 3. 자동 모델 선택 (도메인 + 복잡도 + 플랜 기반) ──
  // 유저가 명시적으로 model을 지정하면 그것 사용, 아니면 자동 선택
  let aiModel = body.model
    ? await prisma.aIModel.findUnique({ where: { name: body.model } })
    : null;

  let modelSelection: any = null;

  if (!aiModel) {
    // 마지막 user 메시지에서 도메인 + 복잡도 감지
    const lastUserMsgForRouting = [...(body.messages || [])]
      .reverse()
      .find((m: any) => m.role === "user");
    const routingMessage = lastUserMsgForRouting?.content || "";

    // 대화 턴 수 (맥락 기반)
    const userMessages = (body.messages || []).filter((m: any) => m.role === "user");
    const previousMsgs = userMessages.slice(0, -1).map((m: any) => m.content);

    const routingDomain = detectDomain(routingMessage).domain;
    modelSelection = selectModel(
      routingDomain,
      routingMessage,
      user.plan?.name,
      {
        conversationTurns: body.messages?.length || 0,
        previousMessages: previousMsgs,
      }
    );

    aiModel = await prisma.aIModel.findUnique({
      where: { name: modelSelection.model },
    });

    // 라우팅된 모델이 비활성이면 폴백
    if (!aiModel || !aiModel.isActive) {
      aiModel = await prisma.aIModel.findFirst({
        where: { isDefault: true, isActive: true },
      });
    }
  }

  // 최종 폴백: 아무 활성 모델
  if (!aiModel) {
    aiModel = await prisma.aIModel.findFirst({
      where: { isActive: true, isPublic: true },
      orderBy: { sortOrder: "asc" },
    });
  }
  if (!aiModel) {
    return Response.json({ error: "사용 가능한 AI 모델이 없습니다" }, { status: 503 });
  }

  // 플랜 제한 체크
  if (aiModel.minPlan) {
    const planTiers: Record<string, number> = {
      free: 0, starter: 1, pro: 2, business: 3, enterprise: 4,
    };
    const userTier = planTiers[user.plan?.name || "free"] ?? 0;
    const requiredTier = planTiers[aiModel.minPlan] ?? 0;
    if (userTier < requiredTier) {
      return Response.json({
        error: `이 모델은 ${aiModel.minPlan} 이상 플랜에서만 사용 가능합니다`,
        upgradeRequired: aiModel.minPlan,
      }, { status: 403 });
    }
  }

  const balance = user.tokenBalance?.balance ?? 0;
  const dailyUsed = user.tokenBalance?.dailyUsed ?? 0;
  const dailyLimit = user.tokenBalance?.dailyLimit ?? 0;

  if (balance <= 0) {
    return Response.json({ error: "토큰이 부족합니다" }, { status: 402 });
  }
  if (dailyLimit > 0 && dailyUsed >= dailyLimit) {
    return Response.json({ error: "일일 사용 한도 초과" }, { status: 429 });
  }

  // ─── 4. 정렬 프레임워크 적용 ─────────────────────────
  const lastUserMsg = [...(body.messages || [])].reverse().find((m: any) => m.role === "user");
  const userMessage = lastUserMsg?.content || "";

  const alignment = await applyFullAlignment({
    userId,
    userMessage,
    userPlan: user.plan?.name,
    enableHRAG: true,
    enableNWNC: true,
    enableVCoT: true,
    enableTADM: true,
    enableMMRM: true,
    enableLCRG: true,
  });

  // ─── 4.2 고급 추론 기법 (TTT, Reasoning, ACT, MTP, Quiet-STaR) ─
  const advanced = applyAdvanced({
    userMessage,
    domain: alignment.domainInfo.domain,
    enableTTT: true,
    enableReasoning: true,
    enableMTP: true,
    enableQuietSTaR: true,
    enableACT: true,
  });

  // ─── 4.3 혁신 기법 (HNTL, HCE, HRL, HCP, HML, HQL) ───────────
  const innovation = await applyInnovation({
    userMessage,
    domain: alignment.domainInfo.domain,
    userId,
    vllmEndpoint: aiModel.endpoint,
    model: aiModel.backendId,
    enableHNTL: true,
    enableHCE: true,
    enableHRL: true,
    enableHML: true,
    enableHQL: true,
  });

  // 통합 시스템 프롬프트
  const fullSystemPrompt = [
    alignment.systemPrompt,
    advanced.systemPrompt,
    innovation.systemPrompt,
  ]
    .filter((p) => p && p.trim().length > 0)
    .join("\n");

  // 시스템 프롬프트 주입
  if (body.messages && body.messages.length > 0) {
    const hasSystem = body.messages[0]?.role === "system";
    if (!hasSystem) {
      body.messages = [
        { role: "system", content: fullSystemPrompt },
        ...body.messages,
      ];
    } else {
      body.messages[0].content = `${fullSystemPrompt}\n\n${body.messages[0].content}`;
    }
  }

  // TTT few-shot 예제 주입 (마지막 user 메시지 직전에)
  if (advanced.fewShotMessages.length > 0) {
    const lastIdx = body.messages.length - 1;
    if (body.messages[lastIdx]?.role === "user") {
      body.messages.splice(lastIdx, 0, ...advanced.fewShotMessages);
    }
  }

  // 백엔드 모델로 교체
  body.model = aiModel.backendId;
  const maxTokens = user.plan?.maxTokensPerReq || aiModel.maxOutputTokens;
  if (!body.max_tokens || body.max_tokens > maxTokens) {
    body.max_tokens = maxTokens;
  }

  // 고급/혁신 기법의 request body transform 적용
  body = advanced.requestBodyTransform(body);
  body = innovation.requestBodyTransform(body);

  // ─── 4.5 최적화 프레임워크 적용 (HPC + HAT) ─────────
  const optimization = await applyOptimization(body.messages, {
    domain: alignment.domainInfo.domain,
    userPlan: user.plan?.name,
    enableHPC: true,
    enableHAT: true,
  });

  // 에이전트 도구 사용 모드 (Pro+ 플랜)
  if (optimization.useTools && optimization.tools && !body.stream) {
    const startedAt = Date.now();
    const agentResult = await runAgenticLoop(
      body.messages,
      alignment.domainInfo.domain,
      aiModel.endpoint,
      aiModel.backendId,
      5
    );

    const enhanced = await alignment.postProcess(agentResult.finalResponse);

    // 토큰 사용량 (도구 호출 포함)
    const totalTokens = Math.ceil(enhanced.length / 4);  // 대략
    const chargedTokens = Math.ceil(totalTokens * aiModel.outputMultiplier);

    prisma.tokenBalance.update({
      where: { userId },
      data: {
        balance: { decrement: chargedTokens },
        totalUsed: { increment: chargedTokens },
        dailyUsed: { increment: chargedTokens },
      },
    }).catch(() => {});

    return Response.json({
      choices: [{ message: { role: "assistant", content: enhanced } }],
      usage: { total_tokens: totalTokens },
      _meta: {
        model: aiModel.name,
        displayName: aiModel.displayName,
        chargedTokens,
        latencyMs: Date.now() - startedAt,
        alignment: {
          tacs: {
            domain: alignment.domainInfo.domain,
            riskLevel: alignment.domainInfo.riskLevel,
          },
        },
        optimization: {
          hat: {
            toolsUsed: agentResult.toolCalls.map((t) => t.name),
            iterations: agentResult.iterations,
          },
        },
      },
    });
  }

  // ─── 5. 하이브리드 서빙 (서버 + Grid 에이전트) ─────
  // 서버 GPU 상황에 따라 서버 또는 에이전트로 라우팅
  const servingTarget = hybridServing.selectTarget({
    complexity: modelSelection?.complexity?.level,
    userRegion: "kr",
    userPlan: user.plan?.name,
    stream: body.stream,
  });

  // 실제 호출할 엔드포인트 결정
  let servingEndpoint = aiModel.endpoint;
  let servedBy = "server";

  if (servingTarget) {
    if (servingTarget.type === "agent") {
      servingEndpoint = servingTarget.agent.endpoint;
      servedBy = `agent:${servingTarget.agent.id}`;
      servingTarget.agent.currentLoad++;
    } else if (servingTarget.type === "server") {
      servingEndpoint = servingTarget.node.endpoint || aiModel.endpoint;
      servedBy = `server:${servingTarget.node.id}`;
      servingTarget.node.currentLoad++;
    } else if (servingTarget.type === "hybrid") {
      // 복잡 작업: 서버가 메인, 에이전트가 보조
      servingEndpoint = servingTarget.server.endpoint || aiModel.endpoint;
      servedBy = `hybrid:${servingTarget.server.id}+${servingTarget.agent.id}`;
    }
  }

  const startedAt = Date.now();
  let apiResponse: Response;

  // 디버그: vLLM으로 가는 요청 로그
  console.log(`[chat] → vLLM ${servingEndpoint}`, {
    model: body.model,
    msg_count: body.messages?.length,
    has_tools: !!body.tools?.length,
    tool_choice: body.tool_choice,
    stream: body.stream,
  });

  try {
    apiResponse = await fetch(`${servingEndpoint}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120000),
    });
  } catch (fetchError: any) {
    // 서빙 실패 → 불량 기록 + 페일오버
    console.error(`[HybridServing] ${servedBy} 실패, 페일오버 시도:`, fetchError.message);

    // 실패 기록 → 연속 실패 시 자동 격리
    if (servingTarget?.type === "agent") {
      hybridServing.recordFailure(servingTarget.agent.id, fetchError.message);
      servingTarget.agent.currentLoad--;
    } else if (servingTarget?.type === "server") {
      servingTarget.node.status = "offline";
      servingTarget.node.currentLoad--;
    }

    // 재시도: 원래 서버 엔드포인트로
    try {
      apiResponse = await fetch(`${aiModel.endpoint}/v1/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(120000),
      });
      servedBy = "server:fallback";
    } catch {
      return Response.json(
        { error: "AI 서버와 에이전트 모두 응답 없음" },
        { status: 503 }
      );
    }
  }

  // 에이전트 로드 해제
  if (servingTarget?.type === "agent") {
    servingTarget.agent.currentLoad--;
  } else if (servingTarget?.type === "server") {
    servingTarget.node.currentLoad--;
  }

  if (!apiResponse.ok) {
    // 응답 에러도 실패로 기록
    if (servingTarget?.type === "agent") {
      hybridServing.recordFailure(servingTarget.agent.id, `HTTP ${apiResponse.status}`);
    }
    const errorText = await apiResponse.text();
    return Response.json(
      { error: `AI 서버 오류 (${apiResponse.status})`, detail: errorText },
      { status: apiResponse.status }
    );
  }

  // ─── 6. 스트리밍 ───────────────────────────────────
  if (body.stream) {
    return new Response(apiResponse.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Model-Name": aiModel.name,
        "X-Domain": alignment.domainInfo.domain,
        "X-Risk-Level": alignment.domainInfo.riskLevel,
      },
    });
  }

  // ─── 7. 일반 응답 + 사후 처리 + 토큰 차감 ──────────
  const data = await apiResponse.json();

  // 디버그: vLLM 응답 로그
  console.log(`[chat] ← vLLM`, {
    has_content: !!data.choices?.[0]?.message?.content,
    has_tool_calls: !!data.choices?.[0]?.message?.tool_calls?.length,
    tool_call_count: data.choices?.[0]?.message?.tool_calls?.length || 0,
    finish_reason: data.choices?.[0]?.finish_reason,
  });

  let responseWeight = calculateResponseWeight({ agentId: servedBy, response: "", requestDomain: alignment.domainInfo.domain });

  if (data.choices?.[0]?.message?.content) {
    let content = data.choices[0].message.content;
    // 고급 기법 후처리 (Reasoning <thinking> 태그 제거 등)
    content = advanced.postProcess(content);
    // 정렬 프레임워크 후처리 (TACS 면책조항, LCRG 인용 검증)
    content = await alignment.postProcess(content);
    // 혁신 기법 후처리 (HRL 팩트 체크)
    content = await innovation.postProcess(content);

    // 응답 가중치 계산 (에이전트 품질 평가)
    const responseMeta = {
      agentId: servedBy,
      response: content,
      avgLogprob: data.choices?.[0]?.logprobs?.content?.[0]?.logprob,
      requestDomain: alignment.domainInfo.domain,
    };
    const responseWeight = calculateResponseWeight(responseMeta);

    // 낮은 신뢰도 → 면책조항 자동 추가
    content = enrichResponseWithWeight(content, responseWeight);

    data.choices[0].message.content = content;
  }

  // 에이전트 성공 기록
  if (servingTarget?.type === "agent") {
    hybridServing.recordSuccess(servingTarget.agent.id);
  }

  const promptTokens = data.usage?.prompt_tokens || 0;
  const completionTokens = data.usage?.completion_tokens || 0;
  const totalTokens = data.usage?.total_tokens || 0;
  const latencyMs = Date.now() - startedAt;

  const chargedTokens = Math.ceil(
    promptTokens * aiModel.inputMultiplier +
    completionTokens * aiModel.outputMultiplier
  );

  // 비동기 DB 업데이트 + 토큰 소각
  // HWARANG 코인: 서비스 이용 시 30% 소각
  import("@/lib/blockchain/token-economy").then(({ burnTokens }) => {
    burnTokens(userId, "ai_usage", chargedTokens).catch(() => {});
  }).catch(() => {});

  Promise.all([
    prisma.tokenBalance.update({
      where: { userId },
      data: {
        balance: { decrement: chargedTokens },
        totalUsed: { increment: chargedTokens },
        dailyUsed: { increment: chargedTokens },
      },
    }),
    prisma.usageRecord.create({
      data: {
        userId,
        model: aiModel.name,
        endpoint: "/v1/chat/completions",
        promptTokens,
        completionTokens,
        totalTokens,
        chargedTokens,
        inputMultiplier: aiModel.inputMultiplier,
        outputMultiplier: aiModel.outputMultiplier,
        latencyMs,
        statusCode: 200,
        domain: alignment.domainInfo.domain,
      },
    }),
    prisma.tokenTransaction.create({
      data: {
        userId,
        type: "USAGE",
        amount: -chargedTokens,
        balance: balance - chargedTokens,
        description: `${aiModel.displayName} (${alignment.domainInfo.domain})`,
        metadata: {
          model: aiModel.name,
          promptTokens,
          completionTokens,
          domain: alignment.domainInfo.domain,
          riskLevel: alignment.domainInfo.riskLevel,
        },
      },
    }),
  ]).catch((e) => console.error("DB 업데이트 실패:", e));

  // 메타데이터
  data._meta = {
    model: aiModel.name,
    displayName: aiModel.displayName,
    tier: aiModel.tier,
    autoRouted: !body.model,
    routing: modelSelection ? {
      reason: modelSelection.reason,
      complexityScore: modelSelection.complexity?.score,
      complexityLevel: modelSelection.complexity?.level,
      reasons: modelSelection.complexity?.reasons?.slice(0, 5),
    } : undefined,
    chargedTokens,
    latencyMs,
    serving: {
      servedBy,
      endpoint: servingEndpoint,
    },
    alignment: {
      tacs: {
        domain: alignment.domainInfo.domain,
        riskLevel: alignment.domainInfo.riskLevel,
        confidence: alignment.domainInfo.confidence,
      },
      nwnc: alignment.emotion
        ? { emotion: alignment.emotion.primary, formality: alignment.emotion.formalityLevel }
        : undefined,
      tadm: alignment.temporalContext
        ? { date: alignment.temporalContext.now.toISOString().split("T")[0] }
        : undefined,
      hrag: {
        sourcesFound: alignment.hragSources?.length || 0,
      },
      mmrm: {
        hasProfile: !!alignment.profile,
      },
    },
    optimization: {
      hpc: {
        cacheHit: optimization.cacheHit,
        cacheKey: optimization.cacheKey?.slice(0, 16),
      },
      hat: {
        eligible: optimization.useTools,
      },
    },
    advanced: {
      act: {
        difficulty: advanced.actConfig.difficulty,
      },
      ttt: {
        fewShots: advanced.fewShotMessages.length / 2,
      },
      reasoning: advanced.actConfig.useReasoning,
      mtp: true,
      quietStar: true,
    },
    innovation: innovation.metadata,
    ...buildResponseWeightMeta(responseWeight),
  };

  return Response.json(data);
}
