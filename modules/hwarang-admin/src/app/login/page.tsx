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

      // 세션 저장
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
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--muted)" }}>
      <div className="w-full max-w-sm p-8 rounded-2xl border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-3 text-white font-bold" style={{ background: "var(--primary)" }}>H</div>
          <h1 className="text-xl font-bold">화랑 AI 관리자</h1>
          <p className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>관리자 계정으로 로그인하세요</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="text-xs font-medium">이메일</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
              placeholder="admin@persismore.com" />
          </div>
          <div>
            <label className="text-xs font-medium">비밀번호</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
              placeholder="비밀번호 입력" />
          </div>

          {error && <p className="text-xs" style={{ color: "var(--destructive)" }}>{error}</p>}

          <button type="submit" disabled={loading}
            className="w-full py-2.5 rounded-lg text-sm font-medium text-white disabled:opacity-50"
            style={{ background: "var(--primary)" }}>
            {loading ? "로그인 중..." : "로그인"}
          </button>
        </form>
      </div>
    </div>
  );
}
