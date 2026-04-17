/**
 * HWARANG 토큰 이코노미 - 적응형 발행 + 소각
 *
 * 3중 균형 메커니즘:
 *   1. 고정 상한 (10억 HWR)
 *   2. 적응형 발행 (네트워크 상태 기반)
 *   3. 소각 (서비스 이용 시)
 *
 * Chat API, Grid 보상, 유저 대시보드에서 사용.
 */

// ─── 상수 ────────────────────────────────────────────────────

export const TOTAL_SUPPLY_CAP = 1_000_000_000;
export const BASE_REWARD_PER_HOUR = 10;

export const HALVING_MILESTONES = [
  100_000_000, 200_000_000, 300_000_000, 400_000_000,
];

export const BURN_RATES: Record<string, number> = {
  ai_usage: 0.30,
  api_call: 0.30,
  subscription: 0.20,
  purchase: 0.05,
  transfer: 0.01,
};

export const GPU_PERFORMANCE: Record<string, number> = {
  "RTX 4060": 0.15, "RTX 4070": 0.25, "RTX 4080": 0.45,
  "RTX 4090": 0.70, "RTX 5060": 0.30, "RTX 5070": 0.50,
  "RTX 5080": 0.65, "RTX 5090": 1.00, "A100": 1.20, "H100": 1.80,
};

export const TASK_MULTIPLIER: Record<string, number> = {
  serving: 1.0, training_sft: 2.0, training_dpo: 2.5,
  validation: 0.5, data_gen: 1.5,
};

// ─── 적응형 발행 계산 ────────────────────────────────────────

export function calculateHalvingFactor(totalEmitted: number): number {
  let factor = 1.0;
  for (const milestone of HALVING_MILESTONES) {
    if (totalEmitted >= milestone) factor *= 0.5;
  }
  return factor;
}

export function calculateSupplyFactor(gpuUtilization: number): number {
  if (gpuUtilization > 0.9) return 3.0;
  if (gpuUtilization > 0.8) return 1.5 + (gpuUtilization - 0.8) * 15;
  if (gpuUtilization > 0.4) return 1.0;
  if (gpuUtilization > 0.2) return 0.5 + (gpuUtilization - 0.2) * 2.5;
  return 0.3;
}

export function calculateDemandFactor(demandChange: number): number {
  return Math.max(0.5, Math.min(1.5, 1.0 + demandChange * 0.5));
}

export interface RewardResult {
  baseReward: number;
  supplyFactor: number;
  demandFactor: number;
  halvingFactor: number;
  taskMultiplier: number;
  streakBonus: number;
  finalReward: number;     // 시간당 HWR
  dailyReward: number;
  monthlyReward: number;
}

export function calculateReward(
  gpuName: string,
  taskType: string,
  gpuUtilization: number,
  demandChange: number,
  totalEmitted: number,
  streakDays: number = 0,
): RewardResult {
  const remaining = TOTAL_SUPPLY_CAP - totalEmitted;
  if (remaining <= 0) {
    return {
      baseReward: 0, supplyFactor: 0, demandFactor: 0,
      halvingFactor: 0, taskMultiplier: 0, streakBonus: 0,
      finalReward: 0, dailyReward: 0, monthlyReward: 0,
    };
  }

  const base = BASE_REWARD_PER_HOUR * (GPU_PERFORMANCE[gpuName] ?? 0.5);
  const supply = calculateSupplyFactor(gpuUtilization);
  const demand = calculateDemandFactor(demandChange);
  const halving = calculateHalvingFactor(totalEmitted);
  const task = TASK_MULTIPLIER[taskType] ?? 1.0;
  const streak = 1.0 + Math.min(streakDays * 0.05, 0.5);

  let final = base * supply * demand * halving * task * streak;
  final = Math.min(final, remaining);

  return {
    baseReward: Math.round(base * 100) / 100,
    supplyFactor: Math.round(supply * 1000) / 1000,
    demandFactor: Math.round(demand * 1000) / 1000,
    halvingFactor: Math.round(halving * 10000) / 10000,
    taskMultiplier: task,
    streakBonus: Math.round(streak * 100) / 100,
    finalReward: Math.round(final * 100) / 100,
    dailyReward: Math.round(final * 24 * 100) / 100,
    monthlyReward: Math.round(final * 24 * 30 * 100) / 100,
  };
}

// ─── 소각 계산 ───────────────────────────────────────────────

export interface BurnResult {
  action: string;
  amount: number;
  burnRate: number;
  burned: number;
  remaining: number;
}

export function calculateBurn(action: string, amount: number): BurnResult {
  const rate = BURN_RATES[action] ?? 0;
  const burned = amount * rate;
  return {
    action,
    amount,
    burnRate: rate,
    burned: Math.round(burned * 10000) / 10000,
    remaining: Math.round((amount - burned) * 10000) / 10000,
  };
}

// ─── 네트워크 상태 조회 (DB에서) ─────────────────────────────

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

export async function getNetworkStats(): Promise<{
  totalEmitted: number;
  totalBurned: number;
  circulating: number;
  gpuUtilization: number;
  demandChange: number;
}> {
  try {
    // SystemSetting에서 토큰 통계 조회
    const [emittedSetting, burnedSetting] = await Promise.all([
      prisma.systemSetting.findUnique({ where: { key: "hwr_total_emitted" } }),
      prisma.systemSetting.findUnique({ where: { key: "hwr_total_burned" } }),
    ]);

    const totalEmitted = emittedSetting ? parseInt(emittedSetting.value) : 0;
    const totalBurned = burnedSetting ? parseInt(burnedSetting.value) : 0;

    // GPU 사용률 (에이전트 상태에서)
    const gpuUtilization = 0.6; // TODO: 실제 에이전트 모니터링에서 가져오기

    // 수요 변화 (전주 대비 요청 수)
    const demandChange = 0.1; // TODO: 실제 UsageRecord에서 계산

    return {
      totalEmitted,
      totalBurned,
      circulating: Math.max(0, totalEmitted - totalBurned),
      gpuUtilization,
      demandChange,
    };
  } catch {
    return {
      totalEmitted: 0, totalBurned: 0, circulating: 0,
      gpuUtilization: 0.5, demandChange: 0,
    };
  }
}

// ─── 보상 지급 (DB 업데이트) ──────────────────────────────────

export async function emitReward(
  userId: string,
  gpuName: string,
  taskType: string,
  durationHours: number,
): Promise<{ rewarded: number; txId: string } | null> {
  try {
    const stats = await getNetworkStats();
    const reward = calculateReward(
      gpuName, taskType,
      stats.gpuUtilization, stats.demandChange,
      stats.totalEmitted,
    );

    const amount = Math.round(reward.finalReward * durationHours);
    if (amount <= 0) return null;

    // 토큰 잔액 증가
    await prisma.tokenBalance.upsert({
      where: { userId },
      update: {
        balance: { increment: amount },
        totalCharged: { increment: amount },
      },
      create: {
        userId,
        balance: amount,
        totalCharged: amount,
      },
    });

    // 거래 기록
    const tx = await prisma.tokenTransaction.create({
      data: {
        userId,
        type: "GRID_REWARD",
        amount,
        balance: 0, // 나중에 업데이트
        description: `GPU 보상: ${gpuName} ${taskType} ${durationHours}h (${reward.finalReward} HWR/h)`,
        metadata: {
          gpuName, taskType, durationHours,
          supplyFactor: reward.supplyFactor,
          halvingFactor: reward.halvingFactor,
          demandFactor: reward.demandFactor,
        },
      },
    });

    // 총 발행량 업데이트
    await prisma.systemSetting.upsert({
      where: { key: "hwr_total_emitted" },
      update: { value: String(stats.totalEmitted + amount) },
      create: { key: "hwr_total_emitted", value: String(amount) },
    });

    return { rewarded: amount, txId: tx.id };
  } catch (e) {
    console.error("보상 지급 실패:", e);
    return null;
  }
}

// ─── 소각 실행 (서비스 이용 시) ──────────────────────────────

export async function burnTokens(
  userId: string,
  action: string,
  amount: number,
): Promise<{ burned: number; remaining: number } | null> {
  try {
    const burn = calculateBurn(action, amount);

    // 소각 기록
    if (burn.burned > 0) {
      const stats = await getNetworkStats();
      await prisma.systemSetting.upsert({
        where: { key: "hwr_total_burned" },
        update: { value: String(stats.totalBurned + burn.burned) },
        create: { key: "hwr_total_burned", value: String(burn.burned) },
      });
    }

    return { burned: burn.burned, remaining: burn.remaining };
  } catch (e) {
    console.error("소각 실패:", e);
    return null;
  }
}
