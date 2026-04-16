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
import Credentials from "next-auth/providers/credentials";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "./db";
import crypto from "crypto";

function hashPassword(password: string): string {
  return crypto.createHash("sha256").update(password).digest("hex");
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: PrismaAdapter(prisma),
  providers: [
    Credentials({
      name: "credentials",
      credentials: {
        email: { label: "이메일", type: "email" },
        password: { label: "비밀번호", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          return null;
        }

        const user = await prisma.user.findUnique({
          where: { email: credentials.email as string },
        });

        if (!user || !user.hashedPassword) {
          return null;
        }

        const hashed = hashPassword(credentials.password as string);
        if (user.hashedPassword !== hashed) {
          return null;
        }

        if (!user.isActive) {
          return null;
        }

        return {
          id: user.id,
          email: user.email,
          name: user.name,
          image: user.image,
        };
      },
    }),
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

    async jwt({ token, user }) {
      // 최초 로그인 시 user가 있음 → 토큰에 정보 저장
      if (user) {
        token.id = user.id;
      }
      return token;
    },

    async session({ session, token, user }) {
      // JWT 모드: token 사용, Database 모드: user 사용
      const userId = (token?.id as string) || user?.id;

      if (session.user && userId) {
        session.user.id = userId;

        try {
          const fullUser = await prisma.user.findUnique({
            where: { id: userId },
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
    // Credentials Provider는 JWT 모드 필수
    strategy: "jwt",
  },
});
