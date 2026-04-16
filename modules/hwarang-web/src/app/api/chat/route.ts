/**
 * Chat API proxy route.
 * 브라우저 → Next.js → vLLM/Hwarang API
 *
 * 기능:
 * - 인증 확인 (로그인 필수)
 * - 모델 선택 (요청 model 이름 or 기본 모델)
 * - AIModel 테이블에서 백엔드 ID + 토큰 배수 조회
 * - 토큰 잔액 확인 (부족하면 차단)
 * - 사용 후 토큰 차감 + UsageRecord 기록
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";

const SYSTEM_PROMPT = `You are Hwarang AI (화랑 AI), a helpful assistant created by Persismore.

IMPORTANT RULES:
- Always respond in the SAME LANGUAGE as the user's message.
- If the user writes in Korean, respond ONLY in Korean.
- If the user writes in English, respond ONLY in English.
- NEVER mix Chinese characters in your response unless explicitly asked.
- NEVER respond in Chinese unless the user writes in Chinese.
- You are a Korean AI assistant. Korean is your primary language.
- Be helpful, accurate, and concise.`;


export async function POST(request: NextRequest) {
  // ─── 1. 인증 확인 ─────────────────────────────────────
  const session = await auth();
  if (!session?.user?.id) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  const userId = session.user.id;
  const body = await request.json();

  // ─── 2. 모델 선택 ─────────────────────────────────────
  let aiModel;
  if (body.model) {
    // 요청한 모델 조회
    aiModel = await prisma.aIModel.findUnique({ where: { name: body.model } });
  }

  if (!aiModel) {
    // 기본 모델 fallback
    aiModel = await prisma.aIModel.findFirst({
      where: { isDefault: true, isActive: true },
    });
  }

  if (!aiModel) {
    // 마지막 fallback: 첫번째 활성 모델
    aiModel = await prisma.aIModel.findFirst({
      where: { isActive: true, isPublic: true },
      orderBy: { sortOrder: "asc" },
    });
  }

  if (!aiModel) {
    return Response.json({ error: "사용 가능한 AI 모델이 없습니다" }, { status: 503 });
  }

  // ─── 3. 유저 플랜 + 토큰 확인 ──────────────────────────
  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { plan: true, tokenBalance: true },
  });

  if (!user) {
    return Response.json({ error: "유저 정보를 찾을 수 없습니다" }, { status: 404 });
  }

  // 모델 최소 플랜 체크
  if (aiModel.minPlan) {
    const planTiers: Record<string, number> = {
      free: 0, starter: 1, pro: 2, business: 3, enterprise: 4,
    };
    const userTier = planTiers[user.plan?.name || "free"] ?? 0;
    const requiredTier = planTiers[aiModel.minPlan] ?? 0;
    if (userTier < requiredTier) {
      return Response.json({
        error: `이 모델은 ${aiModel.minPlan} 이상의 플랜에서만 사용 가능합니다`,
        upgradeRequired: aiModel.minPlan,
      }, { status: 403 });
    }
  }

  // 토큰 잔액 확인
  const balance = user.tokenBalance?.balance ?? 0;
  const dailyUsed = user.tokenBalance?.dailyUsed ?? 0;
  const dailyLimit = user.tokenBalance?.dailyLimit ?? 0;

  if (balance <= 0) {
    return Response.json({ error: "토큰이 부족합니다. 플랜을 업그레이드하거나 토큰을 충전하세요." }, { status: 402 });
  }
  if (dailyLimit > 0 && dailyUsed >= dailyLimit) {
    return Response.json({ error: "오늘 일일 사용 한도를 초과했습니다. 내일 다시 시도하세요." }, { status: 429 });
  }

  // ─── 4. 시스템 프롬프트 + 백엔드 모델 지정 ─────────────
  if (body.messages && body.messages.length > 0) {
    const hasSystem = body.messages[0]?.role === "system";
    if (!hasSystem) {
      body.messages = [
        { role: "system", content: SYSTEM_PROMPT },
        ...body.messages,
      ];
    }
  }

  // 실제 백엔드 모델 ID로 교체
  body.model = aiModel.backendId;

  // 플랜별 최대 토큰 제한
  const maxTokens = user.plan?.maxTokensPerReq || aiModel.maxOutputTokens;
  if (!body.max_tokens || body.max_tokens > maxTokens) {
    body.max_tokens = maxTokens;
  }

  // ─── 5. vLLM 호출 ────────────────────────────────────
  const apiResponse = await fetch(`${aiModel.endpoint}/v1/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!apiResponse.ok) {
    const errorText = await apiResponse.text();
    return Response.json(
      { error: `AI 서버 오류 (${apiResponse.status})`, detail: errorText },
      { status: apiResponse.status }
    );
  }

  // ─── 6. 스트리밍 처리 ──────────────────────────────────
  if (body.stream) {
    // 스트리밍: 토큰 계산은 클라이언트 측 or 별도 endpoint에서
    return new Response(apiResponse.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Model-Name": aiModel.name,
        "X-Input-Multiplier": String(aiModel.inputMultiplier),
        "X-Output-Multiplier": String(aiModel.outputMultiplier),
      },
    });
  }

  // ─── 7. 일반 응답 + 토큰 차감 ──────────────────────────
  const data = await apiResponse.json();

  const promptTokens = data.usage?.prompt_tokens || 0;
  const completionTokens = data.usage?.completion_tokens || 0;
  const totalTokens = data.usage?.total_tokens || 0;

  // 화랑 토큰 소비량 계산 (배수 적용)
  const chargedTokens = Math.ceil(
    promptTokens * aiModel.inputMultiplier +
    completionTokens * aiModel.outputMultiplier
  );

  // DB 업데이트 (비동기, 응답 지연 방지)
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
        latencyMs: 0,
        statusCode: 200,
        domain: aiModel.category,
      },
    }),
    prisma.tokenTransaction.create({
      data: {
        userId,
        type: "USAGE",
        amount: -chargedTokens,
        balance: balance - chargedTokens,
        description: `${aiModel.displayName} 사용 (${totalTokens}토큰)`,
        metadata: { model: aiModel.name, promptTokens, completionTokens },
      },
    }),
  ]).catch((e) => console.error("토큰 차감 실패:", e));

  // 응답에 모델 정보 포함
  data._meta = {
    model: aiModel.name,
    displayName: aiModel.displayName,
    chargedTokens,
  };

  return Response.json(data);
}
