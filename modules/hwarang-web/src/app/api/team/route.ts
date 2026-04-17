/**
 * 팀 협업 API
 *
 * GET    /api/team          - 팀 목록
 * POST   /api/team          - 팀 생성
 * POST   /api/team/invite   - 멤버 초대
 * GET    /api/team/shared    - 팀 공유 대화
 *
 * Business 플랜 이상에서 사용 가능.
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";

export async function GET(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return Response.json({ error: "로그인 필요" }, { status: 401 });

  // 유저가 속한 팀 조회
  const key = `team_memberships_${session.user.id}`;
  const setting = await prisma.systemSetting.findUnique({ where: { key } });
  const teams = setting ? JSON.parse(setting.value) : [];

  return Response.json({ teams });
}

export async function POST(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return Response.json({ error: "로그인 필요" }, { status: 401 });

  const { name, description } = await request.json();
  if (!name) return Response.json({ error: "팀 이름 필요" }, { status: 400 });

  const teamId = `team_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const team = {
    id: teamId,
    name,
    description: description || "",
    ownerId: session.user.id,
    members: [{ userId: session.user.id, role: "owner", joinedAt: new Date().toISOString() }],
    createdAt: new Date().toISOString(),
    sharedTokenPool: 0,
  };

  // 팀 저장
  await prisma.systemSetting.create({
    data: { key: `team_${teamId}`, value: JSON.stringify(team) },
  });

  // 멤버십 업데이트
  const memberKey = `team_memberships_${session.user.id}`;
  const existing = await prisma.systemSetting.findUnique({ where: { key: memberKey } });
  const memberships = existing ? JSON.parse(existing.value) : [];
  memberships.push({ teamId, teamName: name, role: "owner" });

  await prisma.systemSetting.upsert({
    where: { key: memberKey },
    update: { value: JSON.stringify(memberships) },
    create: { key: memberKey, value: JSON.stringify(memberships) },
  });

  return Response.json({ success: true, team });
}
