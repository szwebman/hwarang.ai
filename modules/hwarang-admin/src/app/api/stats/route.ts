/**
 * 관리자 대시보드 통계 - 실제 DB + vLLM 서버
 */

import { prisma, HWARANG_API_URL } from "@/lib/db";

export async function GET() {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);

  let dbStats = {
    totalUsers: 0, newUsersToday: 0, activeUsers: 0,
    requestsToday: 0, requestsThisMonth: 0, revenueThisMonth: 0,
    planDistribution: [] as any[],
  };

  try {
    const [totalUsers, newUsersToday, activeUsers, requestsToday, requestsThisMonth, revenue, planDist] =
      await Promise.all([
        prisma.user.count(),
        prisma.user.count({ where: { createdAt: { gte: todayStart } } }),
        prisma.user.count({ where: { isActive: true } }),
        prisma.usageRecord.count({ where: { createdAt: { gte: todayStart } } }),
        prisma.usageRecord.count({ where: { createdAt: { gte: monthStart } } }),
        prisma.payment.aggregate({ _sum: { amount: true }, where: { status: "PAID", createdAt: { gte: monthStart } } }),
        prisma.plan.findMany({ include: { _count: { select: { users: true } } }, where: { isActive: true } }),
      ]);

    dbStats = {
      totalUsers, newUsersToday, activeUsers, requestsToday, requestsThisMonth,
      revenueThisMonth: revenue._sum.amount || 0,
      planDistribution: planDist.map((p: any) => ({
        name: p.name, displayName: p.displayName,
        userCount: p._count.users, priceMonthly: p.priceMonthly,
      })),
    };
  } catch (e) {
    console.error("DB 조회 실패:", e);
  }

  let cluster = null;
  try {
    const resp = await fetch(`${HWARANG_API_URL}/v1/models`, { cache: "no-store" });
    if (resp.ok) {
      const data = await resp.json();
      cluster = { status: "running", models: data.data?.map((m: any) => m.id) || [], modelCount: data.data?.length || 0 };
    }
  } catch {
    cluster = { status: "offline", models: [], modelCount: 0 };
  }

  return Response.json({
    users: { total: dbStats.totalUsers, active: dbStats.activeUsers, newToday: dbStats.newUsersToday },
    requests: { today: dbStats.requestsToday, thisMonth: dbStats.requestsThisMonth },
    revenue: { thisMonth: dbStats.revenueThisMonth },
    planDistribution: dbStats.planDistribution,
    cluster,
  });
}
