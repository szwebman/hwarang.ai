/**
 * Plans API - 플랜 CRUD
 * GET: 공개 플랜 목록 (유저 사이트용)
 * POST: 플랜 생성 (관리자)
 * PUT: 플랜 수정 (관리자)
 * DELETE: 플랜 삭제 (관리자)
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

// GET /api/plans - 플랜 목록 조회
export async function GET() {
  try {
    const plans = await prisma.plan.findMany({
      where: { isActive: true, isPublic: true },
      orderBy: { priceMonthly: "asc" },
      include: { _count: { select: { users: true } } },
    });

    return Response.json(plans);
  } catch (error) {
    // DB 연결 전에는 기본 플랜 반환
    return Response.json(getDefaultPlans());
  }
}

// POST /api/plans - 플랜 생성 (관리자)
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const plan = await prisma.plan.create({
      data: {
        name: body.name,
        displayName: body.displayName,
        description: body.description,
        priceMonthly: body.priceMonthly || 0,
        priceYearly: body.priceYearly || 0,
        tokensIncluded: body.tokensIncluded || 10000,
        dailyTokenLimit: body.dailyTokenLimit || 5000,
        maxTokensPerReq: body.maxTokensPerReq || 2048,
        concurrentReqs: body.concurrentReqs || 1,
        apiKeysAllowed: body.apiKeysAllowed || 1,
        overagePrice7b: body.overagePrice7b || 0,
        overagePrice30b: body.overagePrice30b || 0,
        models: body.models || [],
        features: body.features || [],
        supportLevel: body.supportLevel || "community",
      },
    });

    return Response.json(plan, { status: 201 });
  } catch (error: any) {
    return Response.json({ error: error.message }, { status: 500 });
  }
}

// PUT /api/plans - 플랜 수정 (관리자)
export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { id, ...data } = body;

    const plan = await prisma.plan.update({
      where: { id },
      data,
    });

    return Response.json(plan);
  } catch (error: any) {
    return Response.json({ error: error.message }, { status: 500 });
  }
}

// DB 연결 전 기본 플랜 (fallback)
function getDefaultPlans() {
  return [
    {
      id: "default-free", name: "free", displayName: "Free",
      priceMonthly: 0, priceYearly: 0,
      tokensIncluded: 10000, dailyTokenLimit: 3000, maxTokensPerReq: 1024,
      models: ["7B"], features: ["AI 채팅", "7B 모델"],
      apiKeysAllowed: 1, overagePrice7b: 0, overagePrice30b: 0,
      _count: { users: 0 },
    },
    {
      id: "default-starter", name: "starter", displayName: "Starter",
      priceMonthly: 9900, priceYearly: 99000,
      tokensIncluded: 100000, dailyTokenLimit: 20000, maxTokensPerReq: 2048,
      models: ["7B"], features: ["AI 채팅", "7B 모델", "API 키 발급", "이메일 지원"],
      apiKeysAllowed: 2, overagePrice7b: 10, overagePrice30b: 0,
      _count: { users: 0 },
    },
    {
      id: "default-pro", name: "pro", displayName: "Pro",
      priceMonthly: 29000, priceYearly: 290000,
      tokensIncluded: 500000, dailyTokenLimit: 50000, maxTokensPerReq: 4096,
      models: ["7B", "30B"], features: ["AI 채팅", "7B + 30B 모델", "코드/법률/세무", "VS Code Pro", "API 키", "우선 지원"],
      apiKeysAllowed: 5, overagePrice7b: 8, overagePrice30b: 25,
      _count: { users: 0 },
    },
    {
      id: "default-business", name: "business", displayName: "Business",
      priceMonthly: 99000, priceYearly: 990000,
      tokensIncluded: 2000000, dailyTokenLimit: 200000, maxTokensPerReq: 8192,
      models: ["7B", "30B"], features: ["모든 Pro 기능", "팀 멤버 관리", "온프레미스 옵션", "전용 파인튜닝", "SLA 보장", "전담 지원"],
      apiKeysAllowed: 20, overagePrice7b: 5, overagePrice30b: 15,
      _count: { users: 0 },
    },
  ];
}
