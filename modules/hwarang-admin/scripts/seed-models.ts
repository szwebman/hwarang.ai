/**
 * AI 모델 + 플랜 초기 데이터 시드 스크립트
 *
 * 사용법:
 *   cd modules/hwarang-admin
 *   npx tsx scripts/seed-models.ts
 *
 * ⭐ 최신 모델 전략 (2026-04):
 *   - 복잡한 코딩 / 복잡한 질문  → DeepSeek V3 (Claude 80%급)
 *   - 간단 코딩 / 일반 대화       → Qwen3-Coder-Next (경량)
 *   - 법률/세무                   → EXAONE 3.5-32B
 *   - Free 플랜 기본              → Qwen2.5-32B (현재 학습 중)
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

// ─── AI 모델 기본 데이터 ──────────────────────────────────────
const DEFAULT_MODELS = [
  // ═══════════════════════════════════════════════
  // 🏆 플래그십: 복잡한 코딩 + 추론 = DeepSeek V3
  // ═══════════════════════════════════════════════
  {
    name: "hwarang-pro",
    displayName: "Hwarang Pro (DeepSeek V3)",
    description:
      "DeepSeek-V3 (671B MoE) 기반. 복잡한 코딩, 대규모 리팩토링, 고급 추론 전용. " +
      "Claude Sonnet 80% 수준. 멀티파일 수정/아키텍처 설계가 필요한 작업에 최적.",
    backendId: "/mnt/nvme2/hwarang/models/deepseek-v3",
    endpoint: "http://localhost:8000",
    inputMultiplier: 3.0, // 비싼 모델 (화랑 토큰 ×3 차감)
    outputMultiplier: 5.0, // 출력은 ×5 (계산 많음)
    maxContextLength: 163840, // 160K
    maxOutputTokens: 8192,
    category: "coding", // ⭐ 코딩 도메인으로 설정 (라우팅 위해)
    tier: "flagship",
    tags: ["최강", "코딩", "복잡한 작업", "Claude급"],
    minPlan: "starter", // Starter 이상만 접근
    isPublic: true,
    isDefault: false, // 기본은 Qwen-Coder가 함
    isActive: true,
    sortOrder: 1,
  },

  // ═══════════════════════════════════════════════
  // ⚡ 경량 코딩: 간단한 코딩 = Qwen3-Coder-Next
  // ═══════════════════════════════════════════════
  {
    name: "hwarang-coder",
    displayName: "Hwarang Coder (Qwen3 30B MoE)",
    description:
      "Qwen3-Coder-30B-A3B (MoE 3B 활성) 기반. 간단한 함수 작성, 리팩토링, 버그 수정 등 일상 코딩 작업에 최적. " +
      "매우 빠른 응답 (100~150 tok/s). 복잡한 작업은 Pro 모델 (DeepSeek V3) 권장.",
    backendId: "/mnt/nvme2/hwarang/models/qwen3-coder-30b",
    endpoint: "http://localhost:8000",
    inputMultiplier: 1.0, // 저렴 (기본 단가)
    outputMultiplier: 1.5,
    maxContextLength: 131072, // 128K
    maxOutputTokens: 8192,
    category: "coding",
    tier: "standard",
    tags: ["코딩", "빠름", "간단한 작업"],
    minPlan: null, // 전체 플랜 사용 가능
    isPublic: true,
    isDefault: true, // ⭐ 코딩 질문 기본 모델
    isActive: false, // 다운로드 후 수동 활성화
    sortOrder: 2,
  },

  // ═══════════════════════════════════════════════
  // ⚖️ 법률/세무: EXAONE 4.5 (2026 최신, 멀티모달)
  // ═══════════════════════════════════════════════
  {
    name: "hwarang-legal",
    displayName: "Hwarang Legal (EXAONE 4.5)",
    description:
      "EXAONE 4.5-33B (2026 최신) 기반. 한국 법률/세무 특화. LG AI Research. " +
      "멀티모달 (이미지 분석) + 6개 언어 (ko, en, es, de, ja, vi). " +
      "민법/형법/상법/세법 등 한국 법령 학습 완료.",
    backendId: "/mnt/nvme2/hwarang/models/exaone-4.5-33b",
    endpoint: "http://localhost:8000",
    inputMultiplier: 1.5,
    outputMultiplier: 2.5,
    maxContextLength: 32768,
    maxOutputTokens: 4096,
    category: "legal",
    tier: "premium",
    tags: ["법률", "세무", "한국어", "멀티모달"],
    minPlan: "starter",
    isPublic: true,
    isDefault: false,
    isActive: false, // EXAONE 다운로드 후 활성화
    sortOrder: 4,
  },

  // ═══════════════════════════════════════════════
  // 💬 일반 대화: Qwen2.5-32B (현재 학습 중)
  // ═══════════════════════════════════════════════
  {
    name: "hwarang-general",
    displayName: "Hwarang General (일반 대화)",
    description:
      "Qwen2.5-32B 기반 + 한국어 SFT. 일반 대화, 질문 답변, 글쓰기. " +
      "Free 플랜 기본 모델.",
    backendId: "/mnt/nvme2/hwarang/models/qwen2.5-32b-int4",
    endpoint: "http://localhost:8000",
    inputMultiplier: 1.0,
    outputMultiplier: 1.0,
    maxContextLength: 32768,
    maxOutputTokens: 4096,
    category: "general",
    tier: "standard",
    tags: ["일반", "한국어", "빠름"],
    minPlan: null,
    isPublic: true,
    isDefault: false,
    isActive: true,
    sortOrder: 5,
  },
];

// ─── 플랜 기본 데이터 ──────────────────────────────────────────
const DEFAULT_PLANS = [
  {
    name: "free",
    displayName: "Free",
    description: "가볍게 시작하기 (간단 코딩 + 일반 대화)",
    priceMonthly: 0,
    priceYearly: 0,
    tokensIncluded: 10000,
    dailyTokenLimit: 3000,
    maxTokensPerReq: 4096,
    concurrentReqs: 1,
    apiKeysAllowed: 1,
    allowOverage: false,
    features: ["chat", "web", "coder_lite"],
    supportLevel: "community",
    isActive: true,
    isPublic: true,
  },
  {
    name: "starter",
    displayName: "Starter",
    description: "개인 개발자 추천 (DeepSeek V3 포함)",
    priceMonthly: 9900,
    priceYearly: 99000,
    tokensIncluded: 100000,
    dailyTokenLimit: 15000,
    maxTokensPerReq: 8192,
    concurrentReqs: 2,
    apiKeysAllowed: 2,
    allowOverage: true,
    features: ["chat", "web", "api", "code", "pro_model"],
    supportLevel: "email",
    isActive: true,
    isPublic: true,
  },
  {
    name: "pro",
    displayName: "Pro",
    description: "전문가를 위한 (무제한 DeepSeek V3)",
    priceMonthly: 29900,
    priceYearly: 299000,
    tokensIncluded: 500000,
    dailyTokenLimit: 50000,
    maxTokensPerReq: 16384,
    concurrentReqs: 5,
    apiKeysAllowed: 5,
    allowOverage: true,
    features: [
      "chat",
      "web",
      "api",
      "code",
      "legal",
      "tax",
      "pro_model",
      "priority_queue",
    ],
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
    features: [
      "chat",
      "web",
      "api",
      "code",
      "legal",
      "tax",
      "pro_model",
      "priority_queue",
      "team",
    ],
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
  console.log("\n 라우팅 전략:");
  console.log("  [복잡 코딩]  → hwarang-pro (DeepSeek V3)");
  console.log("  [간단 코딩]  → hwarang-coder (Qwen3-Coder-Next)");
  console.log("  [법률/세무]  → hwarang-legal (EXAONE)");
  console.log("  [일반 대화]  → hwarang-general (Qwen2.5)");
  console.log("\n 참고:");
  console.log("  - 다운로드 완료 후 isActive=true로 수동 활성화 필요");
  console.log("  - 관리자 페이지에서 토큰 단가/설정 조정 가능");
}

main()
  .catch((e) => {
    console.error("오류:", e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
