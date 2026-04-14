/**
 * Admin 통계 API
 * GET /api/admin/stats - 대시보드 전체 현황
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(request: NextRequest) {
  try {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);

    const [
      totalUsers,
      newUsersToday,
      activeUsers,
      requestsToday,
      requestsThisMonth,
      planDistribution,
      revenueThisMonth,
    ] = await Promise.all([
      prisma.user.count(),
      prisma.user.count({ where: { createdAt: { gte: todayStart } } }),
      prisma.user.count({ where: { isActive: true } }),
      prisma.usageRecord.count({ where: { createdAt: { gte: todayStart } } }),
      prisma.usageRecord.count({ where: { createdAt: { gte: monthStart } } }),
      prisma.user.groupBy({
        by: ["planId"],
        _count: true,
        where: { isActive: true },
      }),
      prisma.payment.aggregate({
        _sum: { amount: true },
        where: { status: "PAID", createdAt: { gte: monthStart } },
      }),
    ]);

    // 서버 상태 (Hwarang API에서 가져오기)
    let clusterStatus = null;
    try {
      const apiUrl = process.env.HWARANG_API_URL || "http://localhost:8000";
      const resp = await fetch(`${apiUrl}/admin/cluster/status`, { cache: "no-store" });
      if (resp.ok) clusterStatus = await resp.json();
    } catch {}

    return Response.json({
      users: {
        total: totalUsers,
        active: activeUsers,
        newToday: newUsersToday,
      },
      requests: {
        today: requestsToday,
        thisMonth: requestsThisMonth,
      },
      revenue: {
        thisMonth: revenueThisMonth._sum.amount || 0,
      },
      planDistribution,
      cluster: clusterStatus,
    });
  } catch (error) {
    // DB 연결 전 데모 데이터
    return Response.json(getDemoStats());
  }
}

function getDemoStats() {
  return {
    users: { total: 1234, active: 567, newToday: 23 },
    requests: { today: 3456, thisMonth: 89012 },
    revenue: { thisMonth: 12340000 },
    planDistribution: [
      { planId: "free", _count: 890 },
      { planId: "pro", _count: 280 },
      { planId: "business", _count: 52 },
      { planId: "enterprise", _count: 12 },
    ],
    cluster: {
      mode: "distributed",
      workers: { total: 3, idle: 2, busy: 1 },
      total_gpus: 4,
      models: { "hwarang-code-7b": 2, "hwarang-code-30b": 1 },
    },
  };
}
