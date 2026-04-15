"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function AdminLoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const resp = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        setError(data.error || "로그인 실패");
        return;
      }

      localStorage.setItem("admin_token", data.token);
      localStorage.setItem("admin_user", JSON.stringify(data.user));
      router.push("/");
    } catch {
      setError("서버 연결 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "#0f172a" }}>
      {/* Background gradient */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-80 h-80 rounded-full opacity-20" style={{ background: "radial-gradient(circle, #6366f1, transparent)" }} />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 rounded-full opacity-10" style={{ background: "radial-gradient(circle, #8b5cf6, transparent)" }} />
      </div>

      <div className="relative w-full max-w-[400px] mx-4">
        {/* Logo */}
        <div className="text-center mb-8">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4 text-white text-xl font-bold"
            style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)", boxShadow: "0 8px 30px rgba(99,102,241,0.3)" }}
          >
            H
          </div>
          <h1 className="text-2xl font-bold text-white">Hwarang AI</h1>
          <p className="text-sm mt-1" style={{ color: "#64748b" }}>Admin Console</p>
        </div>

        {/* Card */}
        <div
          className="rounded-2xl p-8"
          style={{
            background: "rgba(30, 41, 59, 0.5)",
            backdropFilter: "blur(20px)",
            border: "1px solid rgba(255,255,255,0.08)",
            boxShadow: "0 25px 50px rgba(0,0,0,0.25)",
          }}
        >
          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label className="text-xs font-medium" style={{ color: "#94a3b8" }}>이메일</label>
              <input
                type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                className="w-full mt-1.5 px-4 py-2.5 rounded-xl text-sm text-white placeholder-slate-500"
                style={{
                  background: "rgba(15, 23, 42, 0.6)",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
                placeholder="admin@persismore.com"
              />
            </div>
            <div>
              <label className="text-xs font-medium" style={{ color: "#94a3b8" }}>비밀번호</label>
              <input
                type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                className="w-full mt-1.5 px-4 py-2.5 rounded-xl text-sm text-white placeholder-slate-500"
                style={{
                  background: "rgba(15, 23, 42, 0.6)",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
                placeholder="비밀번호 입력"
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#f87171" }}>
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-xl text-sm font-semibold text-white disabled:opacity-50"
              style={{
                background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                boxShadow: "0 4px 15px rgba(99,102,241,0.3)",
              }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  로그인 중...
                </span>
              ) : (
                "로그인"
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-xs mt-6" style={{ color: "#475569" }}>
          Persismore Inc. All rights reserved.
        </p>
      </div>
    </div>
  );
}
