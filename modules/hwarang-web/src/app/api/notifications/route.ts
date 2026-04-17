/**
 * 알림 시스템 API
 *
 * GET  /api/notifications     - 알림 목록
 * POST /api/notifications     - 알림 생성 (시스템)
 * PUT  /api/notifications     - 읽음 처리
 *
 * 알림 유형: token_low, plan_expire, model_update, security, promotion
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";

export async function GET(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return Response.json({ error: "로그인 필요" }, { status: 401 });

  // SystemSetting에서 유저별 알림 조회
  const key = `notifications_${session.user.id}`;
  const setting = await prisma.systemSetting.findUnique({ where: { key } });
  const notifications = setting ? JSON.parse(setting.value) : [];

  return Response.json({
    notifications: notifications.slice(0, 50),
    unreadCount: notifications.filter((n: any) => !n.read).length,
  });
}

export async function POST(request: NextRequest) {
  // 시스템 알림 생성 (내부 호출용)
  const { userId, type, title, message, link } = await request.json();

  const key = `notifications_${userId}`;
  const setting = await prisma.systemSetting.findUnique({ where: { key } });
  const notifications = setting ? JSON.parse(setting.value) : [];

  notifications.unshift({
    id: `notif_${Date.now()}`,
    type, title, message, link,
    read: false,
    createdAt: new Date().toISOString(),
  });

  // 최대 100개 유지
  const trimmed = notifications.slice(0, 100);

  await prisma.systemSetting.upsert({
    where: { key },
    update: { value: JSON.stringify(trimmed) },
    create: { key, value: JSON.stringify(trimmed) },
  });

  return Response.json({ success: true });
}

export async function PUT(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return Response.json({ error: "로그인 필요" }, { status: 401 });

  const { notificationId, markAllRead } = await request.json();
  const key = `notifications_${session.user.id}`;
  const setting = await prisma.systemSetting.findUnique({ where: { key } });
  if (!setting) return Response.json({ success: true });

  const notifications = JSON.parse(setting.value);

  if (markAllRead) {
    notifications.forEach((n: any) => n.read = true);
  } else if (notificationId) {
    const n = notifications.find((n: any) => n.id === notificationId);
    if (n) n.read = true;
  }

  await prisma.systemSetting.update({
    where: { key },
    data: { value: JSON.stringify(notifications) },
  });

  return Response.json({ success: true });
}
