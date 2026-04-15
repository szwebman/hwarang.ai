/**
 * NextAuth 설정 - Google + Kakao 소셜 로그인
 *
 * 환경변수:
 *   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
 *   KAKAO_CLIENT_ID, KAKAO_CLIENT_SECRET
 *   NEXTAUTH_SECRET
 */

import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import Kakao from "next-auth/providers/kakao";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "./db";

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: PrismaAdapter(prisma),
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID || "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
    }),
    Kakao({
      clientId: process.env.KAKAO_CLIENT_ID || "",
      clientSecret: process.env.KAKAO_CLIENT_SECRET || "",
    }),
  ],
  callbacks: {
    async signIn({ user, account }) {
      // 첫 가입 시 Free 플랜 + 토큰 지급
      if (account && user.id) {
        try {
          const existingUser = await prisma.user.findUnique({
            where: { id: user.id },
            include: { tokenBalance: true, plan: true },
          });

          // 플랜이 없으면 Free 플랜 할당
          if (existingUser && !existingUser.planId) {
            const freePlan = await prisma.plan.findUnique({ where: { id: "free" } });
            if (freePlan) {
              await prisma.user.update({
                where: { id: user.id },
                data: { planId: freePlan.id },
              });
            }
          }

          // 토큰 잔액이 없으면 초기 토큰 지급
          if (existingUser && !existingUser.tokenBalance) {
            await prisma.tokenBalance.create({
              data: {
                userId: user.id,
                balance: 10000,      // Free 플랜: 10K 토큰
                dailyLimit: 3000,
                totalCharged: 10000,
              },
            });

            // 웰컴 토큰 거래 기록
            await prisma.tokenTransaction.create({
              data: {
                userId: user.id,
                type: "PLAN_CREDIT",
                amount: 10000,
                balance: 10000,
                description: "회원가입 웰컴 토큰 (Free 플랜)",
              },
            });
          }
        } catch (e) {
          console.error("SignIn callback error:", e);
        }
      }
      return true;
    },

    async session({ session, user }) {
      // 세션에 유저 ID, 역할, 플랜 추가
      if (session.user && user) {
        session.user.id = user.id;

        try {
          const fullUser = await prisma.user.findUnique({
            where: { id: user.id },
            include: {
              plan: { select: { name: true, displayName: true } },
              tokenBalance: { select: { balance: true, dailyUsed: true, dailyLimit: true } },
            },
          });

          if (fullUser) {
            (session.user as any).role = fullUser.role;
            (session.user as any).plan = fullUser.plan;
            (session.user as any).tokens = fullUser.tokenBalance;
          }
        } catch (e) {
          console.error("Session callback error:", e);
        }
      }
      return session;
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
  session: {
    strategy: "database",
  },
});
