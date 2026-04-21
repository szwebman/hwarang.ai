"use client";

import { signIn } from "next-auth/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, Suspense } from "react";

function LoginInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") || "/dashboard";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleCredentialsLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
      });

      if (result?.error) {
        setError("이메일 또는 비밀번호가 올바르지 않습니다");
      } else {
        router.push(callbackUrl);
      }
    } catch {
      setError("로그인 중 오류가 발생했습니다");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--muted)" }}>
      <div className="w-full max-w-md p-8 rounded-2xl border"
        style={{ background: "var(--background)", borderColor: "var(--border)" }}>

        {/* 로고 */}
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}>
            <span className="text-white text-2xl font-bold">H</span>
          </div>
          <h1 className="text-2xl font-bold">Hwarang AI</h1>
          <p className="mt-2 text-sm" style={{ color: "var(--muted-foreground)" }}>
            로그인하고 AI를 시작하세요
          </p>
        </div>

        {/* 이메일/비밀번호 로그인 */}
        <form onSubmit={handleCredentialsLogin} className="space-y-3">
          <div>
            <label className="text-xs font-medium">이메일</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full mt-1 px-3 py-2.5 rounded-xl border text-sm"
              style={{ borderColor: "var(--border)" }}
              placeholder="example@email.com"
            />
          </div>
          <div>
            <label className="text-xs font-medium">비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full mt-1 px-3 py-2.5 rounded-xl border text-sm"
              style={{ borderColor: "var(--border)" }}
              placeholder="비밀번호 입력"
            />
          </div>

          {error && (
            <p className="text-xs px-3 py-2 rounded-lg" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444" }}>
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-xl text-sm font-medium text-white disabled:opacity-50"
            style={{ background: "var(--primary)" }}
          >
            {loading ? "로그인 중..." : "로그인"}
          </button>
        </form>

        <div className="flex items-center justify-between mt-3 text-xs">
          <Link href="/register" style={{ color: "var(--primary)" }}>회원가입</Link>
          <Link href="/forgot-password" style={{ color: "var(--muted-foreground)" }}>비밀번호 찾기</Link>
        </div>

        {/* 구분선 */}
        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t" style={{ borderColor: "var(--border)" }}></div>
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="px-2" style={{ background: "var(--background)", color: "var(--muted-foreground)" }}>
              또는 소셜 로그인
            </span>
          </div>
        </div>

        {/* 소셜 로그인 */}
        <div className="space-y-2">
          <button
            onClick={() => signIn("google", { callbackUrl })}
            className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-xl border text-sm font-medium"
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

          <button
            onClick={() => signIn("kakao", { callbackUrl })}
            className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium"
            style={{ background: "#FEE500", color: "#000000" }}
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="#000000">
              <path d="M12 3C6.48 3 2 6.36 2 10.44c0 2.61 1.74 4.91 4.36 6.22-.14.53-.92 3.41-.95 3.63 0 0-.02.17.09.24.11.06.24.01.24.01.32-.04 3.7-2.44 4.28-2.86.63.09 1.28.14 1.98.14 5.52 0 10-3.36 10-7.44C22 6.36 17.52 3 12 3z"/>
            </svg>
            카카오로 로그인
          </button>
        </div>

        {/* 안내 */}
        <div className="text-center text-xs mt-6 space-y-1" style={{ color: "var(--muted-foreground)" }}>
          <p>가입 시 <strong>Free 플랜 (10,000 토큰)</strong>이 자동 적용됩니다.</p>
          <p>
            계속 진행하면{" "}
            <a href="/terms" style={{ color: "var(--primary)" }}>이용약관</a> 및{" "}
            <a href="/privacy" style={{ color: "var(--primary)" }}>개인정보처리방침</a>에 동의하는 것으로 간주합니다.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginInner />
    </Suspense>
  );
}
