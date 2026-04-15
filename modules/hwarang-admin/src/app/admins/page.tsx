"use client";

import { useEffect, useState } from "react";

interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: string;
  createdAt: string;
  isActive: boolean;
}

const ROLE_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  SUPER_ADMIN: { label: "최고 관리자", color: "#7c3aed", bg: "#ede9fe" },
  ADMIN: { label: "관리자", color: "#2563eb", bg: "#dbeafe" },
  USER: { label: "일반 유저", color: "#6b7280", bg: "#f3f4f6" },
};

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function AdminsPage() {
  const [admins, setAdmins] = useState<AdminUser[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState("ADMIN");
  const [newPassword, setNewPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [currentRole, setCurrentRole] = useState("");

  useEffect(() => {
    try {
      const raw = localStorage.getItem("admin_user");
      if (raw) setCurrentRole(JSON.parse(raw).role || "");
    } catch {}
    fetchAdmins();
  }, []);

  const fetchAdmins = async () => {
    try {
      const resp = await fetch("/api/admins", { headers: authHeaders() });
      if (resp.ok) setAdmins(await resp.json());
    } catch {}
    setLoading(false);
  };

  const handleAddAdmin = async () => {
    if (!newEmail || !newPassword) return;
    try {
      const resp = await fetch("/api/admins", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ email: newEmail, role: newRole, password: newPassword }),
      });
      if (resp.ok) {
        fetchAdmins();
        setShowAdd(false);
        setNewEmail("");
        setNewPassword("");
      } else {
        const data = await resp.json();
        alert(data.error || "추가 실패");
      }
    } catch {}
  };

  const handleChangeRole = async (userId: string, newRole: string) => {
    try {
      const resp = await fetch("/api/admins", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ id: userId, role: newRole }),
      });
      if (!resp.ok) {
        const data = await resp.json();
        alert(data.error || "변경 실패");
      }
      fetchAdmins();
    } catch {}
  };

  const handleRemoveAdmin = async (userId: string) => {
    if (!confirm("이 관리자의 권한을 제거하시겠습니까?")) return;
    await handleChangeRole(userId, "USER");
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">관리자 계정</h1>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>관리자 추가/제거, 역할(Role) 관리</p>
        </div>
        {currentRole === "SUPER_ADMIN" && (
          <button onClick={() => setShowAdd(!showAdd)}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white" style={{ background: "var(--primary)" }}>
            + 관리자 추가
          </button>
        )}
      </div>

      {/* 역할 설명 */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-sm font-semibold mb-1" style={{ color: "#7c3aed" }}>최고 관리자 (SUPER_ADMIN)</div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>모든 권한. 관리자 추가/제거, 시스템 설정</div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-sm font-semibold mb-1" style={{ color: "#2563eb" }}>관리자 (ADMIN)</div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>유저/플랜/모델 관리. 시스템 설정 제외</div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-sm font-semibold mb-1" style={{ color: "#6b7280" }}>일반 유저 (USER)</div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>관리자 패널 접근 불가</div>
        </div>
      </div>

      {/* 관리자 추가 폼 */}
      {showAdd && (
        <div className="rounded-xl p-5 border mb-6" style={{ borderColor: "var(--primary)", background: "var(--background)" }}>
          <h3 className="font-semibold mb-3">관리자 추가</h3>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-medium">이메일</label>
              <input type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                placeholder="admin@persismore.com" />
            </div>
            <div>
              <label className="text-xs font-medium">비밀번호</label>
              <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                placeholder="초기 비밀번호" />
            </div>
            <div>
              <label className="text-xs font-medium">역할</label>
              <select value={newRole} onChange={(e) => setNewRole(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}>
                <option value="ADMIN">관리자</option>
                <option value="SUPER_ADMIN">최고 관리자</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2 mt-3 justify-end">
            <button onClick={() => setShowAdd(false)} className="px-4 py-1.5 rounded-lg text-sm border" style={{ borderColor: "var(--border)" }}>취소</button>
            <button onClick={handleAddAdmin} className="px-4 py-1.5 rounded-lg text-sm text-white" style={{ background: "var(--primary)" }}>추가</button>
          </div>
        </div>
      )}

      {/* 관리자 목록 */}
      <div className="rounded-xl overflow-hidden border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "var(--muted)" }}>
              <th className="text-left text-xs font-semibold px-5 py-3">관리자</th>
              <th className="text-left text-xs font-semibold px-5 py-3">역할</th>
              <th className="text-left text-xs font-semibold px-5 py-3">등록일</th>
              <th className="text-center text-xs font-semibold px-5 py-3">상태</th>
              <th className="text-right text-xs font-semibold px-5 py-3">액션</th>
            </tr>
          </thead>
          <tbody>
            {admins.map((admin) => {
              const roleInfo = ROLE_LABELS[admin.role] || ROLE_LABELS.USER;
              return (
                <tr key={admin.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="px-5 py-4">
                    <div className="font-medium text-sm">{admin.name || "이름 없음"}</div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>{admin.email}</div>
                  </td>
                  <td className="px-5 py-4">
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: roleInfo.bg, color: roleInfo.color }}>
                      {roleInfo.label}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--muted-foreground)" }}>
                    {admin.createdAt?.split("T")[0]}
                  </td>
                  <td className="px-5 py-4 text-center">
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{
                      background: admin.isActive ? "#dcfce7" : "#fee2e2",
                      color: admin.isActive ? "#166534" : "#991b1b",
                    }}>
                      {admin.isActive ? "활성" : "비활성"}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    {currentRole === "SUPER_ADMIN" ? (
                      <>
                        <select
                          value={admin.role}
                          onChange={(e) => handleChangeRole(admin.id, e.target.value)}
                          className="text-xs px-2 py-1 rounded-lg border mr-2" style={{ borderColor: "var(--border)" }}>
                          <option value="SUPER_ADMIN">최고 관리자</option>
                          <option value="ADMIN">관리자</option>
                          <option value="USER">권한 제거</option>
                        </select>
                        <button onClick={() => handleRemoveAdmin(admin.id)}
                          className="text-xs px-2 py-1" style={{ color: "var(--destructive)" }}>제거</button>
                      </>
                    ) : (
                      <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>—</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {admins.length === 0 && (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>등록된 관리자가 없습니다</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
