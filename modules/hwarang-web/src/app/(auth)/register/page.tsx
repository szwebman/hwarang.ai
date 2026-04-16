"use client";

import { useState, type FormEvent } from "react";
import { signIn } from "next-auth/react";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (password.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다");
      return;
    }

    if (password !== confirmPassword) {
      setError("비밀번호가 일치하지 않습니다");
      return;
    }

    setLoading(true);
    try {
      const resp = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, name }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        setError(data.error || "회원가입에 실패했습니다");
        return;
      }

      // 회원가입 성공 → 자동 로그인
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
      });

      if (result?.error) {
        // 로그인 실패 시 로그인 페이지로
        router.push("/login");
      } else {
        router.push("/dashboard");
      }
    } catch {
      setError("회원가입 중 오류가 발생했습니다");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--muted)" }}>
      <div
        className="w-full max-w-md p-8 rounded-2xl border"
        style={{ background: "var(--background)", borderColor: "var(--border)" }}
      >
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4 text-white text-2xl font-bold"
            style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}>H</div>
          <h1 className="text-2xl font-bold">Hwarang AI</h1>
          <p className="mt-2 text-sm" style={{ color: "var(--muted-foreground)" }}>
            새 계정을 만들어 시작하세요
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">이름</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full px-3 py-2.5 rounded-lg border text-sm"
              style={{ borderColor: "var(--border)", background: "var(--background)" }}
              placeholder="이름을 입력하세요"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">이메일</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2.5 rounded-lg border text-sm"
              style={{ borderColor: "var(--border)", background: "var(--background)" }}
              placeholder="example@email.com"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className="w-full px-3 py-2.5 rounded-lg border text-sm"
              style={{ borderColor: "var(--border)", background: "var(--background)" }}
              placeholder="8자 이상 입력"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">비밀번호 확인</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={8}
              className="w-full px-3 py-2.5 rounded-lg border text-sm"
              style={{ borderColor: "var(--border)", background: "var(--background)" }}
              placeholder="비밀번호 재입력"
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
            className="w-full py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            style={{ background: "var(--primary)", color: "var(--primary-foreground)" }}
          >
            {loading ? "가입 중..." : "회원가입"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>
          이미 계정이 있으신가요?{" "}
          <Link href="/login" className="underline" style={{ color: "var(--primary)" }}>
            로그인
          </Link>
        </p>

        <p className="mt-4 text-center text-xs" style={{ color: "var(--muted-foreground)" }}>
          가입 시 <strong>Free 플랜 (10,000 토큰)</strong>이 자동 적용됩니다.
        </p>
      </div>
    </div>
  );
}
