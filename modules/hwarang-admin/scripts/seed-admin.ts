/**
 * 초기 SUPER_ADMIN 계정 생성 스크립트
 *
 * 사용법:
 *   cd modules/hwarang-admin
 *   npx tsx scripts/seed-admin.ts
 *
 * 환경변수:
 *   ADMIN_EMAIL    - 관리자 이메일 (기본: admin@persismore.com)
 *   ADMIN_PASSWORD - 관리자 비밀번호 (기본: admin1234!)
 */

import { PrismaClient } from "@prisma/client";
import crypto from "crypto";

const prisma = new PrismaClient();

function hashPassword(password: string): string {
  return crypto.createHash("sha256").update(password).digest("hex");
}

async function main() {
  const email = process.env.ADMIN_EMAIL || "admin@persismore.com";
  const password = process.env.ADMIN_PASSWORD || "admin1234!";

  console.log("=".repeat(50));
  console.log("Hwarang Admin - SUPER_ADMIN 계정 생성");
  console.log("=".repeat(50));
  console.log(`  이메일: ${email}`);
  console.log(`  비밀번호: ${password}`);
  console.log();

  const existing = await prisma.user.findUnique({ where: { email } });

  if (existing) {
    // 이미 존재하면 역할 + 비밀번호 업데이트
    const updated = await prisma.user.update({
      where: { email },
      data: {
        role: "SUPER_ADMIN",
        hashedPassword: hashPassword(password),
        isActive: true,
      },
    });
    console.log(`기존 계정을 SUPER_ADMIN으로 업그레이드했습니다. (id: ${updated.id})`);
  } else {
    // 새로 생성
    const user = await prisma.user.create({
      data: {
        email,
        name: "최고 관리자",
        hashedPassword: hashPassword(password),
        role: "SUPER_ADMIN",
        isActive: true,
      },
    });
    console.log(`SUPER_ADMIN 계정 생성 완료! (id: ${user.id})`);
  }

  console.log();
  console.log("로그인: admin.hwarang.ai/login");
  console.log("=".repeat(50));
}

main()
  .catch((e) => {
    console.error("오류:", e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
