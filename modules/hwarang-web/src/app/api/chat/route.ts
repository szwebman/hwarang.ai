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
import { verifyClaimWithSources, extractKeyClaims } from "@/lib/verification";

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
    return Response.json(
      { error: "로그인이 필요합니다", code: "AUTH_REQUIRED" },
      { status: 401 }
    );
  }
  let body = await request.json();

  // ─── 2. 유저 먼저 로드 (플랜 필요) ──────────────────
  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { plan: true, tokenBalance: true },
  });

  if (!user) {
    return Response.json(
      { error: "사용자 정보를 찾을 수 없습니다", code: "USER_NOT_FOUND" },
      { status: 404 }
    );
  }

  // ─── 2.5. Conversation 영속화 (좌측 채팅 리스트 표시용) ──
  // 클라이언트가 UUID 를 보내면 그걸로 upsert (reverse proxy 가 헤더 잘라도 ID 유지).
  const lastUserMessage = [...(body.messages || [])]
    .reverse()
    .find((m: any) => m.role === "user");
  let conversationId: string | null = body.conversationId ?? null;
  if (lastUserMessage?.content) {
    const titleSeed = String(lastUserMessage.content).slice(0, 40).replace(/\s+/g, " ").trim() || "새 대화";

    if (conversationId) {
      // 클라이언트 제공 ID 로 upsert — 본인 소유 검증 포함
      const existing = await prisma.conversation.findUnique({
        where: { id: conversationId },
        select: { id: true, userId: true },
      });
      if (existing && existing.userId !== userId) {
        // 다른 사람 대화 ID 위조 시도 — 무시하고 새로 생성
        conversationId = null;
      } else if (!existing) {
        await prisma.conversation.create({
          data: {
            id: conversationId,
            userId,
            title: titleSeed,
            model: body.model || "auto",
          },
        });
      }
    }
    if (!conversationId) {
      const created = await prisma.conversation.create({
        data: { userId, title: titleSeed, model: body.model || "auto" },
        select: { id: true },
      });
      conversationId = created.id;
    }
    // 옵션 후속(continueOptionId) 호출이면 user 메시지를 다시 저장하지 않음
    // (첫 턴에서 이미 저장됨 — 중복 user 행 방지).
    if (!body.continueOptionId) {
      await prisma.message.create({
        data: { conversationId, role: "user", content: String(lastUserMessage.content) },
      }).catch(() => {});
    }
  }

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
    return Response.json(
      {
        error: "사용 가능한 AI 모델이 없습니다. 잠시 후 다시 시도해 주세요.",
        code: "NO_MODEL_AVAILABLE",
      },
      { status: 503 }
    );
  }

  // 플랜 제한 체크
  if (aiModel.minPlan) {
    const planTiers: Record<string, number> = {
      free: 0, starter: 1, pro: 2, business: 3, enterprise: 4,
    };
    const userTier = planTiers[user.plan?.name || "free"] ?? 0;
    const requiredTier = planTiers[aiModel.minPlan] ?? 0;
    if (userTier < requiredTier) {
      return Response.json(
        {
          error: `이 모델은 ${aiModel.minPlan.toUpperCase()} 이상 플랜에서만 사용 가능합니다. 플랜을 업그레이드해 주세요.`,
          code: "PLAN_UPGRADE_REQUIRED",
          upgradeRequired: aiModel.minPlan,
          detail: `userTier=${user.plan?.name || "free"} required=${aiModel.minPlan}`,
        },
        { status: 403 }
      );
    }
  }

  const balance = user.tokenBalance?.balance ?? 0;
  const dailyUsed = user.tokenBalance?.dailyUsed ?? 0;
  const dailyLimit = user.tokenBalance?.dailyLimit ?? 0;

  if (balance <= 0) {
    return Response.json(
      {
        error: "토큰이 부족합니다. 대시보드에서 충전하거나 플랜을 업그레이드해 주세요.",
        code: "INSUFFICIENT_TOKENS",
        detail: `balance=${balance}`,
      },
      { status: 402 }
    );
  }
  if (dailyLimit > 0 && dailyUsed >= dailyLimit) {
    return Response.json(
      {
        error: "오늘 토큰 한도를 모두 사용했습니다. 자정에 자동 리셋됩니다.",
        code: "DAILY_LIMIT_EXCEEDED",
        detail: `dailyUsed=${dailyUsed} dailyLimit=${dailyLimit}`,
      },
      { status: 429 }
    );
  }

  // ─── 4. 정렬 프레임워크 적용 ─────────────────────────
  const lastUserMsg = [...(body.messages || [])].reverse().find((m: any) => m.role === "user");
  const userMessage = lastUserMsg?.content || "";

  // ─── 4.-2 Vision-to-Code: 이미지 첨부 시 VLM 분석 → system prompt 주입 ──
  // 마지막 user 메시지에 images 배열이 있으면 hwarang-api 의 /api/vision/analyze 호출.
  // 30초 타임아웃 + 실패 무시 (VLM 다운 시 이미지 없이 답변).
  let visionMeta: { used: boolean; description: string; image_count: number; mode?: string } | undefined;
  const lastUserImages: string[] = Array.isArray(lastUserMsg?.images) ? lastUserMsg.images : [];
  if (lastUserImages.length > 0) {
    try {
      const HWARANG_API_URL_V = process.env.HWARANG_API_URL || "http://localhost:8000";
      const INTERNAL_KEY_V = process.env.HWARANG_INTERNAL_KEY || "";
      const visionResp = await fetch(`${HWARANG_API_URL_V}/api/vision/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(INTERNAL_KEY_V ? { Authorization: `Bearer ${INTERNAL_KEY_V}` } : {}),
        },
        body: JSON.stringify({
          images: lastUserImages,
          instruction: userMessage,
        }),
        signal: AbortSignal.timeout(30000),
      });

      if (visionResp.ok) {
        const vd = await visionResp.json();
        if (vd?.description) {
          const visionContext = String(vd.description);
          visionMeta = {
            used: true,
            description: visionContext,
            image_count: lastUserImages.length,
            mode: vd.mode,
          };
          // system message 로 주입 — body.messages 의 마지막 user 직전에 삽입
          const lastUserIdx = body.messages
            .map((m: any, i: number) => ({ m, i }))
            .reverse()
            .find(({ m }: any) => m.role === "user")?.i;
          if (typeof lastUserIdx === "number") {
            body.messages.splice(lastUserIdx, 0, {
              role: "system",
              content: `[이미지 분석 결과 (Qwen2.5-VL)]\n${visionContext}\n\n위 이미지 분석을 참고해서 사용자 요청을 처리하세요. 이미지에 보이는 디자인/UI 요소를 코드로 충실히 재현하세요.`,
            });
          }
          // vLLM 텍스트 모델은 images 필드를 모르므로 정리
          for (const m of body.messages) {
            if ("images" in m) delete (m as any).images;
          }
        }
      } else {
        console.warn("[chat] vision analyze HTTP", visionResp.status);
      }
    } catch (e) {
      console.warn("[chat] vision analyze failed (무시):", e);
    }
  }
  // images 필드 제거 (VLM 호출 안 했어도 텍스트 모델로 누수되면 안 됨)
  if (Array.isArray(body.messages)) {
    for (const m of body.messages) {
      if (m && "images" in m) delete (m as any).images;
    }
  }

  // ─── 4.-0.4 옵션 후속 (인라인 continue) ──
  // 클라이언트가 옵션 카드를 클릭하면 같은 메시지에 답변을 이어붙이기 위해
  // continueOptionId/Title/Keywords 를 보냄. 옵션 감지를 우회하고 (skipOptions=true 동반)
  // 선택 컨텍스트를 system prompt 로 주입해서 LLM 이 그 스타일로 답변하게 만듦.
  const isOptionContinuation = !!body.continueOptionId;
  if (isOptionContinuation) {
    const continueTitle = String(body.continueOptionTitle || "").slice(0, 200);
    const continueKeywords: string[] = Array.isArray(body.continueOptionKeywords)
      ? body.continueOptionKeywords.map((k: any) => String(k)).slice(0, 10)
      : [];
    const continueContext =
      `사용자가 이전 응답의 옵션 중 "${continueTitle}" 을(를) 선택했습니다.` +
      (continueKeywords.length > 0
        ? ` 키워드: ${continueKeywords.join(", ")}.`
        : "") +
      ` 이 스타일/방향에 맞춰 곧바로 결과물(코드/문서 등)을 만들어 주세요. ` +
      `옵션을 다시 제시하지 말고, "다음 중 선택" 같은 안내 문구도 넣지 마세요.`;
    body.messages = [
      { role: "system", content: continueContext },
      ...(Array.isArray(body.messages) ? body.messages : []),
    ];
    // 클라이언트가 안 보냈더라도 안전하게 옵션 감지 우회 강제
    body.skipOptions = true;
  }

  // ─── 4.-0.5 옵션 제시 모드 (Claude-style) ──
  // 사용자가 "만들어줘" / "디자인해줘" 류 모호한 요청 → vLLM 호출 전에 2~4 옵션 카드 표시.
  // body.skipOptions === true 이면 우회 (옵션 클릭 후 후속 메시지). body.stream === false 도 지원.
  let optionsResponse: { deliverable: string; options: any[] } | null = null;
  if (body.skipOptions !== true && !isOptionContinuation) {
    try {
      const HWARANG_API_URL_OPT =
        process.env.HWARANG_API_URL || "http://localhost:8000";
      const INTERNAL_KEY_OPT = process.env.HWARANG_INTERNAL_KEY || "";
      const optHeaders: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (INTERNAL_KEY_OPT) optHeaders.Authorization = `Bearer ${INTERNAL_KEY_OPT}`;

      const detect = await fetch(`${HWARANG_API_URL_OPT}/api/options/detect`, {
        method: "POST",
        headers: optHeaders,
        body: JSON.stringify({
          message: userMessage,
          has_image: lastUserImages.length > 0,
        }),
        signal: AbortSignal.timeout(2000),
      })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);

      if (detect?.needs_options) {
        const generate = await fetch(`${HWARANG_API_URL_OPT}/api/options/generate`, {
          method: "POST",
          headers: optHeaders,
          body: JSON.stringify({
            message: userMessage,
            deliverable: detect.deliverable,
            has_image: lastUserImages.length > 0,
            image_description: visionMeta?.description || null,
          }),
          signal: AbortSignal.timeout(8000),
        })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null);

        if (generate?.options?.length >= 2) {
          optionsResponse = {
            deliverable: detect.deliverable,
            options: generate.options,
          };
        }
      }
    } catch (e) {
      console.warn("[chat] options detect/generate failed (무시):", e);
    }
  }

  // 옵션 응답 — vLLM 호출 안 하고 즉시 SSE 또는 JSON 으로 옵션 리스트 반환.
  // 토큰 차감 없음 (옵션 카드 표시만 함).
  if (optionsResponse) {
    const introMessage = `다음 ${optionsResponse.options.length}가지 중 선택해 주세요:`;

    // assistant 메시지 영속화 (옵션 카드 텍스트만)
    if (conversationId) {
      prisma.message
        .create({
          data: {
            conversationId,
            role: "assistant",
            content: introMessage,
          },
        })
        .catch(() => {});
    }

    if (body.stream) {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({
                choices: [{ delta: { content: introMessage } }],
              })}\n\n`,
            ),
          );
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({ _meta: { options: optionsResponse } })}\n\n`,
            ),
          );
          controller.enqueue(encoder.encode(`data: [DONE]\n\n`));
          controller.close();
        },
      });

      return new Response(stream, {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
          "X-Conversation-Id": conversationId || "",
          "X-Options-Mode": "1",
        },
      });
    }

    // 비스트림
    return Response.json({
      choices: [
        { message: { role: "assistant", content: introMessage }, finish_reason: "stop" },
      ],
      _meta: { options: optionsResponse, conversationId },
    });
  }

  // ─── 4.-1 실시간 웹 검색 (시간민감 질문 자동 감지) ──
  // "현재/지금/오늘/최신..." + 변동 주제(대통령/환율/날씨 등) 시 Naver+Wikipedia 검색.
  // body.realtime === false 면 스킵. 검색 결과를 system message 로 주입.
  let realtimeContext: string | null = null;
  let realtimeSources: any[] = [];
  if (body.realtime !== false && userMessage) {
    try {
      const HWARANG_API_URL_RT =
        process.env.HWARANG_API_URL || "http://localhost:8000";
      const INTERNAL_KEY_RT = process.env.HWARANG_INTERNAL_KEY || "";
      const rtHeaders: Record<string, string> = { "Content-Type": "application/json" };
      if (INTERNAL_KEY_RT) rtHeaders.Authorization = `Bearer ${INTERNAL_KEY_RT}`;

      const detect = await fetch(`${HWARANG_API_URL_RT}/api/realtime/detect`, {
        method: "POST",
        headers: rtHeaders,
        body: JSON.stringify({ message: userMessage }),
        signal: AbortSignal.timeout(2000),
      })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);

      if (detect?.needs_realtime && Array.isArray(detect.suggested_queries)) {
        const search = await fetch(`${HWARANG_API_URL_RT}/api/realtime/search`, {
          method: "POST",
          headers: rtHeaders,
          body: JSON.stringify({ queries: detect.suggested_queries, top_k: 5 }),
          signal: AbortSignal.timeout(8000),
        })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null);

        if (search?.results?.length) {
          const top = search.results.slice(0, 5);
          realtimeContext =
            "다음은 실시간 웹 검색 결과입니다. 답변 시 이 정보를 우선 사용하고 출처를 명시하세요:\n\n" +
            top
              .map(
                (r: any, i: number) =>
                  `[${i + 1}] ${r.title} (${r.source}, 신뢰도 ${r.trust_score})\n${r.snippet}\n출처: ${r.url}`
              )
              .join("\n\n");
          realtimeSources = top;
        }
      }
    } catch (e) {
      console.warn("[chat] realtime search failed (무시):", e);
    }
  }

  // ─── 4.0 Federated (Multi-Agent Synthesis) — HSEE Phase 5 ─
  // 다도메인 질문 자동 감지 시 도메인 전문 에이전트들에게 동시 질의 후 합성.
  // body.federated === false 면 우회. body.stream === true 면 스트리밍 호환 X 라 우회.
  if (
    body.federated !== false &&
    !body.stream &&
    userMessage.length > 20  // 너무 짧으면 단일 도메인일 확률 높음
  ) {
    try {
      const HWARANG_API_URL =
        process.env.HWARANG_API_URL || "http://localhost:8001";
      const internalKey = process.env.HWARANG_INTERNAL_KEY || "";
      const fedResp = await fetch(`${HWARANG_API_URL}/api/learning/federated`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(internalKey ? { Authorization: `Bearer ${internalKey}` } : {}),
        },
        body: JSON.stringify({ question: userMessage, max_rounds: 2 }),
        // Next.js 의 fetch 는 별도 timeout 옵션 없음 — AbortController 로
        signal: AbortSignal.timeout(60_000),
      });
      if (fedResp.ok) {
        const fedResult = await fedResp.json();
        if (fedResult.synthesized && !fedResult.skip) {
          // assistant 메시지 영속화
          if (conversationId) {
            await prisma.message
              .create({
                data: {
                  conversationId,
                  role: "assistant",
                  content: String(fedResult.synthesized),
                },
              })
              .catch(() => {});
          }
          return Response.json({
            choices: [
              {
                message: {
                  role: "assistant",
                  content: fedResult.synthesized,
                },
                finish_reason: "stop",
              },
            ],
            _meta: {
              federated: true,
              domains: fedResult.domains,
              expert_chains: fedResult.expert_chains,
              contradictions: fedResult.contradictions,
              debate_rounds: fedResult.debate_rounds,
            },
          });
        }
        // skip / insufficient_experts / failed_experts → 기존 single-model 흐름
      }
    } catch (err) {
      // federated 실패 시 조용히 fallback
      console.warn("[chat] federated_inference fallback:", err);
    }
  }

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

  // 통합 시스템 프롬프트 — 실시간 검색 결과를 최상단에 두어 LLM 이 우선 참조
  const fullSystemPrompt = [
    realtimeContext,
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
  body = await innovation.requestBodyTransform(body);

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
        {
          error: "AI 모델이 잠시 응답하지 못합니다. 다른 모델로 시도해 보세요.",
          code: "AI_BACKEND_UNAVAILABLE",
          detail: "서버와 에이전트 모두 응답 없음",
        },
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

    // 404 + model 에러 → 모델 미로드 상태. 관리자에게 명확한 메시지.
    if (apiResponse.status === 404 && /model.*not.*exist|does not exist/i.test(errorText)) {
      const m = errorText.match(/`([^`]+)`/);
      const missing = m?.[1] || body.model || "(unknown)";
      return Response.json(
        {
          error: "선택된 AI 모델이 서버에 로드되어 있지 않습니다. 관리자에게 문의해 주세요.",
          code: "MODEL_NOT_LOADED",
          detail: `vLLM 에 모델/LoRA "${missing}" 미존재. AIModel.backendId 또는 LoRA 로딩 확인 필요.`,
        },
        { status: 503 }
      );
    }

    return Response.json(
      {
        error: "AI 서버 응답 오류입니다. 잠시 후 다시 시도해 주세요.",
        code: "AI_BACKEND_ERROR",
        detail: `HTTP ${apiResponse.status}: ${errorText.slice(0, 300)}`,
      },
      { status: apiResponse.status }
    );
  }

  // ─── 6. 스트리밍 ───────────────────────────────────
  if (body.stream) {
    let assembled = "";
    const encoder = new TextEncoder();

    // 핵심 주장 추출 + cross-source 검증 (실패해도 스트림에 영향 X)
    async function buildVerificationEvent(content: string): Promise<string | null> {
      if (!content || body.verify === false) return null;
      try {
        const claims = await extractKeyClaims(content);
        if (claims.length === 0) return null;
        const verifications = await Promise.all(
          claims.map((c) => verifyClaimWithSources(c, alignment.domainInfo.domain))
        );
        const valid = verifications.filter((v): v is NonNullable<typeof v> => v !== null);
        if (valid.length === 0) return null;
        const overall =
          valid.reduce((sum, v) => sum + (v.confidence || 0), 0) / valid.length;
        const verificationMeta = {
          claims: valid.map((v) => ({
            text: v.claim,
            confidence: v.confidence,
            verdict: v.verdict,
            sourceCount: v.supporting.length,
            contradictionCount: v.contradicting.length,
            primarySources: v.supporting
              .filter((s: any) => s.is_primary)
              .slice(0, 3)
              .map((s: any) => ({
                name: s.source_name,
                url: s.source_url,
                trust: s.trust_level,
                type: s.source_type,
              })),
          })),
          overallConfidence: overall,
        };
        // OpenAI 호환 형식 확장 — 클라이언트 stream-parser 가 _meta 를 읽도록
        return `data: ${JSON.stringify({ _meta: { verification: verificationMeta } })}\n\n`;
      } catch {
        return null;
      }
    }

    const tap = new TransformStream({
      transform(chunk, controller) {
        try {
          const text = new TextDecoder().decode(chunk);
          // [DONE] 가 이번 청크에 포함된 경우, [DONE] 직전에 verification 이벤트 삽입.
          if (text.includes("[DONE]")) {
            const idx = text.indexOf("data: [DONE]");
            const before = idx >= 0 ? text.slice(0, idx) : text;
            const done = idx >= 0 ? text.slice(idx) : "";

            // 본문 누적
            for (const line of before.split("\n")) {
              const m = line.match(/^data:\s*(.+)$/);
              if (!m) continue;
              try {
                const j = JSON.parse(m[1]);
                const delta = j.choices?.[0]?.delta?.content;
                if (delta) assembled += delta;
              } catch {}
            }
            if (before) controller.enqueue(encoder.encode(before));

            // 비동기 검증 결과를 대기 후 done 직전에 삽입
            return buildVerificationEvent(assembled)
              .then((evt) => {
                if (evt) controller.enqueue(encoder.encode(evt));
                if (done) controller.enqueue(encoder.encode(done));
              })
              .catch(() => {
                if (done) controller.enqueue(encoder.encode(done));
              });
          }

          for (const line of text.split("\n")) {
            const m = line.match(/^data:\s*(.+)$/);
            if (!m || m[1] === "[DONE]") continue;
            try {
              const j = JSON.parse(m[1]);
              const delta = j.choices?.[0]?.delta?.content;
              if (delta) assembled += delta;
            } catch {}
          }
        } catch {}
        controller.enqueue(chunk);
      },
      flush() {
        if (conversationId && assembled) {
          (async () => {
            // 옵션 후속(continueOptionId)이면 기존 assistant 메시지에 append.
            // 그 외에는 새 assistant 행 생성.
            let created: { id: string } | null = null;
            if (isOptionContinuation) {
              const recent = await prisma.message
                .findFirst({
                  where: { conversationId, role: "assistant" },
                  orderBy: { createdAt: "desc" },
                  select: { id: true, content: true },
                })
                .catch(() => null);
              if (recent) {
                await prisma.message
                  .update({
                    where: { id: recent.id },
                    data: { content: `${recent.content}\n\n${assembled}` },
                  })
                  .catch(() => null);
                created = { id: recent.id };
              } else {
                created = await prisma.message
                  .create({
                    data: { conversationId, role: "assistant", content: assembled },
                    select: { id: true },
                  })
                  .catch(() => null);
              }
            } else {
              created = await prisma.message
                .create({
                  data: { conversationId, role: "assistant", content: assembled },
                  select: { id: true },
                })
                .catch(() => null);
            }
            prisma.conversation
              .update({
                where: { id: conversationId },
                data: { updatedAt: new Date() },
              })
              .catch(() => {});

            // HSEE 복리 루프 트리거 (스트리밍)
            try {
              const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";
              const INTERNAL_KEY = process.env.HWARANG_INTERNAL_KEY || "";
              const headers: Record<string, string> = { "Content-Type": "application/json" };
              if (INTERNAL_KEY) headers.Authorization = `Bearer ${INTERNAL_KEY}`;
              fetch(`${HWARANG_API_URL}/api/learning/on-chat`, {
                method: "POST",
                headers,
                body: JSON.stringify({
                  user_id: userId,
                  conversation_id: conversationId,
                  message_id: created?.id || null,
                  user_message: String(lastUserMessage?.content || ""),
                  response: assembled,
                  domain: alignment.domainInfo.domain,
                  model_name: aiModel.name,
                  lora_name: (aiModel as any).loraName ?? null,
                  latency_ms: Date.now() - startedAt,
                  quality_score: null,
                  is_kyc_verified: !!(user as any).kycVerified,
                }),
              }).catch(() => {});
            } catch {}
          })().catch(() => {});
        }
      },
    });
    let upstream: ReadableStream<Uint8Array> = apiResponse.body!.pipeThrough(tap);

    // VLM 분석 결과가 있으면 스트림 시작 시 _meta 이벤트로 클라이언트에 전달
    if (visionMeta) {
      const visionEvent = `data: ${JSON.stringify({ _meta: { vision: visionMeta } })}\n\n`;
      const prefix = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(visionEvent));
          controller.close();
        },
      });
      // 두 스트림 이어붙이기
      const combined = new ReadableStream<Uint8Array>({
        async start(controller) {
          for (const s of [prefix, upstream]) {
            const reader = s.getReader();
            try {
              while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                controller.enqueue(value);
              }
            } catch (e) {
              controller.error(e);
              return;
            } finally {
              reader.releaseLock();
            }
          }
          controller.close();
        },
      });
      upstream = combined;
    }

    return new Response(upstream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Model-Name": aiModel.name,
        "X-Domain": alignment.domainInfo.domain,
        "X-Risk-Level": alignment.domainInfo.riskLevel,
        "X-Conversation-Id": conversationId || "",
        ...(visionMeta ? { "X-Vision-Used": "1" } : {}),
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
    ...(conversationId && data.choices?.[0]?.message?.content
      ? [
          prisma.message.create({
            data: {
              conversationId,
              role: "assistant",
              content: String(data.choices[0].message.content),
              tokenCount: completionTokens,
            },
          }),
          prisma.conversation.update({
            where: { id: conversationId },
            data: { updatedAt: new Date(), model: aiModel.name },
          }),
        ]
      : []),
  ]).catch((e) => console.error("DB 업데이트 실패:", e));

  // ─── 7.5. HSEE 복리 루프 트리거 (fire-and-forget) ──
  // 4개 자기개선 루프 (RLHF / HLKM / Routing / HFL) 를 백엔드 학습 API 로 위임.
  // 실패해도 채팅 응답에는 영향 없음.
  try {
    const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";
    const INTERNAL_KEY = process.env.HWARANG_INTERNAL_KEY || "";
    const assistantContent = data.choices?.[0]?.message?.content || "";
    const lastUserContent = String(lastUserMessage?.content || "");

    if (assistantContent && lastUserContent) {
      // 마지막 assistant 메시지 ID 를 가져오기 위해 가장 최근 행 조회 (이미 위에서 create 된 것)
      const recentAssistant = conversationId
        ? await prisma.message.findFirst({
            where: { conversationId, role: "assistant" },
            orderBy: { createdAt: "desc" },
            select: { id: true },
          }).catch(() => null)
        : null;

      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (INTERNAL_KEY) headers.Authorization = `Bearer ${INTERNAL_KEY}`;

      fetch(`${HWARANG_API_URL}/api/learning/on-chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          user_id: userId,
          conversation_id: conversationId,
          message_id: recentAssistant?.id || null,
          user_message: lastUserContent,
          response: assistantContent,
          domain: alignment.domainInfo.domain,
          model_name: aiModel.name,
          lora_name: (aiModel as any).loraName ?? null,
          latency_ms: latencyMs,
          quality_score: responseWeight?.totalScore ?? null,
          is_kyc_verified: !!(user as any).kycVerified,
        }),
      }).catch(() => {});
    }
  } catch (e) {
    // 학습 트리거 실패해도 응답은 정상 반환
    console.warn("[chat] HSEE 트리거 실패(무시):", e);
  }

  // ─── 7.6. Cross-source 검증 (출처 첨부) ──
  // 응답 본문에서 핵심 주장 1~2개 추출 → /api/verify 호출 → _meta.verification 에 첨부.
  // 실패해도 응답은 정상 반환. body.verify === false 면 스킵.
  let verificationMeta: any = undefined;
  try {
    const assistantContentForVerify = data.choices?.[0]?.message?.content || "";
    if (assistantContentForVerify && body.verify !== false) {
      const claims = await extractKeyClaims(assistantContentForVerify);
      if (claims.length > 0) {
        const verifications = await Promise.all(
          claims.map((c) => verifyClaimWithSources(c, alignment.domainInfo.domain))
        );
        const valid = verifications.filter((v): v is NonNullable<typeof v> => v !== null);
        if (valid.length > 0) {
          const overall =
            valid.reduce((sum, v) => sum + (v.confidence || 0), 0) / valid.length;
          verificationMeta = {
            claims: valid.map((v) => ({
              text: v.claim,
              confidence: v.confidence,
              verdict: v.verdict,
              sourceCount: v.supporting.length,
              contradictionCount: v.contradicting.length,
              primarySources: v.supporting
                .filter((s: any) => s.is_primary)
                .slice(0, 3)
                .map((s: any) => ({
                  name: s.source_name,
                  url: s.source_url,
                  trust: s.trust_level,
                  type: s.source_type,
                })),
            })),
            overallConfidence: overall,
          };
        }
      }
    }
  } catch (e) {
    console.warn("[chat] verify 실패(무시):", e);
  }

  // ─── 7.7. 인과 체인 (HSEE Phase 5) ──
  // "왜?" 류 질문이면 hwarang-api 의 causal-explain 호출 → _meta.causalChain 첨부.
  // 3초 타임아웃 + 실패 무시.
  let causalChainMeta: any = undefined;
  try {
    if (/(왜|어째서|어떻게|because|why)/i.test(userMessage)) {
      const HWARANG_API_URL_C = process.env.HWARANG_API_URL || "http://localhost:8000";
      const INTERNAL_KEY_C = process.env.HWARANG_INTERNAL_KEY || "";
      const causal = await fetch(`${HWARANG_API_URL_C}/api/knowledge/causal-explain`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": INTERNAL_KEY_C,
        },
        body: JSON.stringify({ question: userMessage }),
        signal: AbortSignal.timeout(3000),
      })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
      if (causal && causal.explanation) {
        causalChainMeta = causal;
      }
    }
  } catch (e) {
    // 무시
  }

  // ─── 7.8. 반사실 추론 ("만약 X 였다면?") ──
  // 한국어 가정형 어미 또는 영어 wouldn't 패턴 → counterfactual 엔드포인트 호출.
  // 8초 타임아웃 (LLM 두 번 호출 — 추출 + 추론). 실패 무시.
  let counterfactualMeta: any = undefined;
  try {
    if (/(만약|만일|if).*?([았었였했]으면|[았었였했]다면|wouldn't|would not|hadn't|had not)/i.test(userMessage)) {
      const HWARANG_API_URL_CF = process.env.HWARANG_API_URL || "http://localhost:8000";
      const INTERNAL_KEY_CF = process.env.HWARANG_INTERNAL_KEY || "";
      const whatIf = await fetch(
        `${HWARANG_API_URL_CF}/api/knowledge/causal/explain-what-if`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": INTERNAL_KEY_CF,
          },
          body: JSON.stringify({ question: userMessage }),
          signal: AbortSignal.timeout(8000),
        },
      )
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
      if (whatIf && !whatIf.error) {
        counterfactualMeta = whatIf;
      }
    }
  } catch (e) {
    // 무시
  }

  // ─── 7.9. Constitutional AI — 자기 비판 + 자동 수정 ──
  // HWARANG_AUTO_CRITIQUE === "true" 일 때만 활성. 8초 타임아웃 + 실패 무시.
  // critical 위반 발견 시 응답 내용 자동 교체.
  let constitutionMeta: any = undefined;
  try {
    if (
      process.env.HWARANG_AUTO_CRITIQUE === "true" &&
      data.choices?.[0]?.message?.content
    ) {
      const HWARANG_API_URL_CON =
        process.env.HWARANG_API_URL || "http://localhost:8000";
      const INTERNAL_KEY_CON = process.env.HWARANG_INTERNAL_KEY || "";
      const conHeaders: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (INTERNAL_KEY_CON) conHeaders.Authorization = `Bearer ${INTERNAL_KEY_CON}`;

      const critique = await fetch(
        `${HWARANG_API_URL_CON}/api/cognitive/constitution/critique`,
        {
          method: "POST",
          headers: conHeaders,
          body: JSON.stringify({
            question: userMessage,
            response: data.choices[0].message.content,
          }),
          signal: AbortSignal.timeout(8000),
        },
      )
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);

      if (critique?.revised && critique.had_critical && critique.revised_response) {
        // critical 위반 발견 — 응답 교체
        data.choices[0].message.content = critique.revised_response;
        constitutionMeta = {
          autoRevised: true,
          hadCritical: true,
          violations: critique.violations || [],
        };
      } else if (critique?.violations?.length) {
        // 마이너 위반 — 메타에만 표시
        constitutionMeta = {
          autoRevised: false,
          hadCritical: false,
          violations: critique.violations,
        };
      }
    }
  } catch (e) {
    console.warn("[chat] constitution critique 실패(무시):", e);
  }

  // 메타데이터
  data._meta = {
    conversationId,
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
    verification: verificationMeta,
    causalChain: causalChainMeta,
    counterfactual: counterfactualMeta,
    constitution: constitutionMeta,
    realtime:
      realtimeSources.length > 0
        ? {
            used: true,
            sources: realtimeSources.map((r: any) => ({
              title: r.title,
              url: r.url,
              source: r.source,
              trust: r.trust_score,
            })),
          }
        : undefined,
    vision: visionMeta,
    ...buildResponseWeightMeta(responseWeight),
  };

  return Response.json(data);
}
