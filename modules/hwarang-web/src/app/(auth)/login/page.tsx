"use client";

import { signIn } from "next-auth/react";
import Link from "next/link";

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--muted)" }}>
      <div className="w-full max-w-md p-8 rounded-2xl border"
        style={{ background: "var(--background)", borderColor: "var(--border)" }}>

        {/* 로고 */}
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl gradient-bg flex items-center justify-center mx-auto mb-4">
            <span className="text-white text-2xl font-bold">H</span>
          </div>
          <h1 className="text-2xl font-bold">
            <span className="gradient-text">Hwarang AI</span>
          </h1>
          <p className="mt-2 text-sm" style={{ color: "var(--muted-foreground)" }}>
            로그인하고 AI를 시작하세요
          </p>
        </div>

        {/* 소셜 로그인 */}
        <div className="space-y-3">
          {/* Google */}
          <button
            onClick={() => signIn("google", { callbackUrl: "/dashboard" })}
            className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl border text-sm font-medium transition-colors hover:bg-gray-50"
            style={{ borderColor: "var(--border)" }}
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Google로 로그인
          </button>

          {/* Kakao */}
          <button
            onClick={() => signIn("kakao", { callbackUrl: "/dashboard" })}
            className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors hover:opacity-90"
            style={{ background: "#FEE500", color: "#000000" }}
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="#000000">
              <path d="M12 3C6.48 3 2 6.36 2 10.44c0 2.61 1.74 4.91 4.36 6.22-.14.53-.92 3.41-.95 3.63 0 0-.02.17.09.24.11.06.24.01.24.01.32-.04 3.7-2.44 4.28-2.86.63.09 1.28.14 1.98.14 5.52 0 10-3.36 10-7.44C22 6.36 17.52 3 12 3z"/>
            </svg>
            카카오로 로그인
          </button>
        </div>

        {/* 구분선 */}
        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t" style={{ borderColor: "var(--border)" }}></div>
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="px-2" style={{ background: "var(--background)", color: "var(--muted-foreground)" }}>
              소셜 계정으로 간편하게
            </span>
          </div>
        </div>

        {/* 안내 */}
        <div className="text-center text-xs space-y-2" style={{ color: "var(--muted-foreground)" }}>
          <p>로그인 시 <strong>Free 플랜 (10,000 토큰)</strong>이 자동 적용됩니다.</p>
          <p>
            계속 진행하면{" "}
            <a href="#" style={{ color: "var(--primary)" }}>이용약관</a> 및{" "}
            <a href="#" style={{ color: "var(--primary)" }}>개인정보처리방침</a>에 동의하는 것으로 간주합니다.
          </p>
        </div>
      </div>
    </div>
  );
}
