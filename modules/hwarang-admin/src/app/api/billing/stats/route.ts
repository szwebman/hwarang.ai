import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { verifyToken } from "@/lib/auth";

function authenticate(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const token = authHeader?.replace("Bearer ", "") || "";
  return verifyToken(token);
}

export async function GET(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || (auth.role !== "ADMIN" && auth.role !== "SUPER_ADMIN")) {
    return Response.json({ error: "권한 없음" }, { status: 403 });
  }

  try {
    const now = new Date();
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    const [allPaid, monthPaid, todayPaid, totalPayments, canceledCount] = await Promise.all([
      prisma.payment.aggregate({ where: { status: "PAID" }, _sum: { amount: true } }),
      prisma.payment.aggregate({ where: { status: "PAID", paidAt: { gte: startOfMonth } }, _sum: { amount: true } }),
      prisma.payment.aggregate({ where: { status: "PAID", paidAt: { gte: startOfDay } }, _sum: { amount: true } }),
      prisma.payment.count(),
      prisma.payment.count({ where: { status: "CANCELED" } }),
    ]);

    const paidCount = await prisma.payment.count({ where: { status: "PAID" } });

    return Response.json({
      totalRevenue: allPaid._sum.amount || 0,
      monthRevenue: monthPaid._sum.amount || 0,
      todayRevenue: todayPaid._sum.amount || 0,
      totalPayments,
      paidCount,
      canceledCount,
    });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
