/**
 * AI 모델 + 플랜 초기 데이터 시드 스크립트
 *
 * 사용법:
 *   cd modules/hwarang-admin
 *   npx tsx scripts/seed-models.ts
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

// ─── AI 모델 기본 데이터 ──────────────────────────────────────
const DEFAULT_MODELS = [
  {
    name: "hwarang-v3",
    displayName: "Hwarang V3 (최강)",
    description: "DeepSeek-V3 기반. 코딩, 복잡한 추론, 고급 질문에 최적화. Claude Sonnet급 성능.",
    backendId: "/mnt/nvme2/hwarang/models/deepseek-v3",
    endpoint: "http://localhost:8000",
    inputMultiplier: 3.0,   // 입력 토큰당 3배 소비 (비싼 모델)
    outputMultiplier: 5.0,  // 출력 토큰당 5배 소비
    maxContextLength: 131072, // 128K
    maxOutputTokens: 8192,
    category: "general",
    tier: "flagship",
    tags: ["최강", "코딩", "추론"],
    minPlan: "starter",
    isPublic: true,
    isDefault: true,
    isActive: true,
    sortOrder: 1,
  },
  {
    name: "hwarang-coder",
    displayName: "Hwarang Coder",
    description: "Qwen3-Coder-30B-A3B (MoE) 기반. 코딩 전용. 3B 활성 파라미터로 3~5배 빠른 추론.",
    backendId: "/mnt/nvme2/hwarang/models/qwen3-coder-30b",
    endpoint: "http://localhost:8000",
    inputMultiplier: 1.2,   // MoE라 싸게 과금
    outputMultiplier: 2.0,
    maxContextLength: 131072,
    maxOutputTokens: 8192,
    category: "coding",
    tier: "premium",
    tags: ["코딩", "MoE", "빠름"],
    minPlan: null,
    isPublic: true,
    isDefault: false,
    isActive: false, // 학습 후 활성화
    sortOrder: 2,
  },
  {
    name: "hwarang-legal",
    displayName: "Hwarang Legal (법률/세무)",
    description: "EXAONE 3.5-32B 기반. 한국 법률/세무 특화. LG AI Research 모델.",
    backendId: "/mnt/nvme2/hwarang/models/exaone-3.5-32b",
    endpoint: "http://localhost:8000",
    inputMultiplier: 1.5,
    outputMultiplier: 2.5,
    maxContextLength: 32768,
    maxOutputTokens: 4096,
    category: "legal",
    tier: "premium",
    tags: ["법률", "세무", "한국어"],
    minPlan: "starter",
    isPublic: true,
    isDefault: false,
    isActive: false,
    sortOrder: 3,
  },
  {
    name: "hwarang-general",
    displayName: "Hwarang General (일반)",
    description: "Qwen2.5-32B 기반. 일반 대화용 경량 모델. Free 플랜 기본.",
    backendId: "/mnt/nvme2/hwarang/models/qwen2.5-32b-int4",
    endpoint: "http://localhost:8000",
    inputMultiplier: 1.0,  // 기본 단가
    outputMultiplier: 1.0,
    maxContextLength: 32768,
    maxOutputTokens: 4096,
    category: "general",
    tier: "standard",
    tags: ["일반", "빠름"],
    minPlan: null,  // 전체 플랜 사용 가능
    isPublic: true,
    isDefault: false,
    isActive: true,
    sortOrder: 4,
  },
];

// ─── 플랜 기본 데이터 ──────────────────────────────────────────
const DEFAULT_PLANS = [
  {
    name: "free",
    displayName: "Free",
    description: "가볍게 시작하기",
    priceMonthly: 0,
    priceYearly: 0,
    tokensIncluded: 10000,
    dailyTokenLimit: 3000,
    maxTokensPerReq: 4096,
    concurrentReqs: 1,
    apiKeysAllowed: 1,
    allowOverage: false,
    features: ["chat", "web"],
    supportLevel: "community",
    isActive: true,
    isPublic: true,
  },
  {
    name: "starter",
    displayName: "Starter",
    description: "개인 개발자 추천",
    priceMonthly: 9900,
    priceYearly: 99000,
    tokensIncluded: 100000,
    dailyTokenLimit: 15000,
    maxTokensPerReq: 8192,
    concurrentReqs: 2,
    apiKeysAllowed: 2,
    allowOverage: true,
    features: ["chat", "web", "api", "code"],
    supportLevel: "email",
    isActive: true,
    isPublic: true,
  },
  {
    name: "pro",
    displayName: "Pro",
    description: "전문가를 위한",
    priceMonthly: 29900,
    priceYearly: 299000,
    tokensIncluded: 500000,
    dailyTokenLimit: 50000,
    maxTokensPerReq: 16384,
    concurrentReqs: 5,
    apiKeysAllowed: 5,
    allowOverage: true,
    features: ["chat", "web", "api", "code", "legal", "tax", "priority_queue"],
    supportLevel: "priority",
    isActive: true,
    isPublic: true,
  },
  {
    name: "business",
    displayName: "Business",
    description: "팀/기업용",
    priceMonthly: 99000,
    priceYearly: 990000,
    tokensIncluded: 2000000,
    dailyTokenLimit: 200000,
    maxTokensPerReq: 32768,
    concurrentReqs: 20,
    apiKeysAllowed: 20,
    allowOverage: true,
    features: ["chat", "web", "api", "code", "legal", "tax", "priority_queue", "team"],
    supportLevel: "dedicated",
    isActive: true,
    isPublic: true,
  },
];

async function main() {
  console.log("=".repeat(60));
  console.log(" Hwarang - AI 모델 + 플랜 시드");
  console.log("=".repeat(60));

  // 플랜 생성/업데이트
  console.log("\n[1/2] 플랜 시드...");
  for (const plan of DEFAULT_PLANS) {
    const existing = await prisma.plan.findUnique({ where: { name: plan.name } });
    if (existing) {
      await prisma.plan.update({ where: { name: plan.name }, data: plan });
      console.log(`  ✓ 업데이트: ${plan.displayName}`);
    } else {
      await prisma.plan.create({ data: plan });
      console.log(`  + 생성: ${plan.displayName}`);
    }
  }

  // AIModel 생성/업데이트
  console.log("\n[2/2] AI 모델 시드...");
  for (const model of DEFAULT_MODELS) {
    const existing = await prisma.aIModel.findUnique({ where: { name: model.name } });
    if (existing) {
      await prisma.aIModel.update({ where: { name: model.name }, data: model });
      console.log(`  ✓ 업데이트: ${model.displayName}`);
    } else {
      await prisma.aIModel.create({ data: model });
      console.log(`  + 생성: ${model.displayName}`);
    }
  }

  console.log("\n" + "=".repeat(60));
  console.log(" 완료!");
  console.log("=".repeat(60));
  console.log("\n 참고:");
  console.log("  - hwarang-v3, hwarang-general은 활성화됨");
  console.log("  - hwarang-coder, hwarang-legal은 학습 후 수동 활성화");
  console.log("  - 관리자 페이지에서 토큰 단가/설정 조정 가능");
}

main()
  .catch((e) => {
    console.error("오류:", e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
