"use client";

import { useEffect, useState } from "react";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function SettingsPage() {
  const [user, setUser] = useState<any>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("admin_user");
      if (raw) setUser(JSON.parse(raw));
    } catch {}
  }, []);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);

    if (!currentPassword || !newPassword) {
      setMessage({ type: "error", text: "모든 필드를 입력하세요" });
      return;
    }

    if (newPassword.length < 6) {
      setMessage({ type: "error", text: "새 비밀번호는 6자 이상이어야 합니다" });
      return;
    }

    if (newPassword !== confirmPassword) {
      setMessage({ type: "error", text: "새 비밀번호가 일치하지 않습니다" });
      return;
    }

    setLoading(true);
    try {
      const resp = await fetch("/api/auth/password", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ currentPassword, newPassword }),
      });

      if (resp.ok) {
        setMessage({ type: "success", text: "비밀번호가 변경되었습니다" });
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
      } else {
        const data = await resp.json();
        setMessage({ type: "error", text: data.error || "변경 실패" });
      }
    } catch {
      setMessage({ type: "error", text: "서버 연결 실패" });
    }
    setLoading(false);
  };

  const roleLabel = user?.role === "SUPER_ADMIN" ? "최고 관리자" : "관리자";

  return (
    <div className="p-6 lg:p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">내 설정</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--muted-foreground)" }}>계정 정보 및 비밀번호 변경</p>
      </div>

      <div className="max-w-lg space-y-6">
        {/* 내 정보 */}
        <div className="rounded-xl border p-5" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
          <h2 className="font-semibold mb-4">내 정보</h2>
          <div className="flex items-center gap-4 mb-4">
            <div className="w-14 h-14 rounded-full flex items-center justify-center text-lg font-bold text-white shrink-0"
              style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}>
              {user?.name?.charAt(0) || user?.email?.charAt(0) || "?"}
            </div>
            <div>
              <div className="font-semibold">{user?.name || "이름 없음"}</div>
              <div className="text-sm" style={{ color: "var(--muted-foreground)" }}>{user?.email}</div>
              <div className="flex items-center gap-1.5 mt-1">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: user?.role === "SUPER_ADMIN" ? "#a78bfa" : "#60a5fa" }} />
                <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>{roleLabel}</span>
              </div>
            </div>
          </div>
        </div>

        {/* 비밀번호 변경 */}
        <div className="rounded-xl border p-5" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
          <h2 className="font-semibold mb-4">비밀번호 변경</h2>
          <form onSubmit={handleChangePassword} className="space-y-4">
            <div>
              <label className="text-xs font-medium">현재 비밀번호</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
                style={{ borderColor: "var(--border)" }}
                placeholder="현재 비밀번호 입력"
                required
              />
            </div>
            <div>
              <label className="text-xs font-medium">새 비밀번호</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
                style={{ borderColor: "var(--border)" }}
                placeholder="6자 이상"
                required
              />
            </div>
            <div>
              <label className="text-xs font-medium">새 비밀번호 확인</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
                style={{ borderColor: "var(--border)" }}
                placeholder="새 비밀번호 다시 입력"
                required
              />
            </div>

            {message && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs" style={{
                background: message.type === "success" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
                color: message.type === "success" ? "#10b981" : "#ef4444",
              }}>
                {message.type === "success" ? "✓" : "!"} {message.text}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg text-sm font-medium text-white disabled:opacity-50"
              style={{ background: "var(--primary)" }}
            >
              {loading ? "변경 중..." : "비밀번호 변경"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
