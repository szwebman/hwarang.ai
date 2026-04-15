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
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState("ADMIN");
  const [newPassword, setNewPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [currentRole, setCurrentRole] = useState("");
  const [currentUserId, setCurrentUserId] = useState("");
  const [search, setSearch] = useState("");

  // 비밀번호 초기화 모달
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [resetPassword, setResetPassword] = useState("");

  useEffect(() => {
    try {
      const raw = localStorage.getItem("admin_user");
      if (raw) {
        const u = JSON.parse(raw);
        setCurrentRole(u.role || "");
        setCurrentUserId(u.id || "");
      }
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
        body: JSON.stringify({ email: newEmail, name: newName, role: newRole, password: newPassword }),
      });
      if (resp.ok) {
        fetchAdmins();
        setShowAdd(false);
        setNewEmail("");
        setNewName("");
        setNewPassword("");
      } else {
        const data = await resp.json();
        alert(data.error || "추가 실패");
      }
    } catch {}
  };

  const handleChangeRole = async (userId: string, role: string) => {
    if (userId === currentUserId) {
      alert("본인의 역할은 변경할 수 없습니다");
      return;
    }
    try {
      const resp = await fetch("/api/admins", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ id: userId, role }),
      });
      if (!resp.ok) {
        const data = await resp.json();
        alert(data.error || "변경 실패");
      }
      fetchAdmins();
    } catch {}
  };

  const handleToggleActive = async (userId: string, isActive: boolean) => {
    try {
      const resp = await fetch("/api/admins", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ id: userId, isActive: !isActive }),
      });
      if (!resp.ok) {
        const data = await resp.json();
        alert(data.error || "변경 실패");
      }
      fetchAdmins();
    } catch {}
  };

  const handleResetPassword = async () => {
    if (!resetTarget || !resetPassword) return;
    try {
      const resp = await fetch("/api/admins", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ id: resetTarget.id, password: resetPassword }),
      });
      if (resp.ok) {
        alert("비밀번호가 초기화되었습니다");
        setResetTarget(null);
        setResetPassword("");
      } else {
        const data = await resp.json();
        alert(data.error || "초기화 실패");
      }
    } catch {}
  };

  const handleRemoveAdmin = async (userId: string) => {
    if (userId === currentUserId) {
      alert("본인의 권한은 제거할 수 없습니다");
      return;
    }
    if (!confirm("이 관리자의 권한을 제거하시겠습니까?\n(일반 유저로 변경됩니다)")) return;
    await handleChangeRole(userId, "USER");
  };

  const filtered = admins.filter(
    (a) => !search || a.email.includes(search) || (a.name && a.name.includes(search))
  );

  const superCount = admins.filter((a) => a.role === "SUPER_ADMIN").length;
  const adminCount = admins.filter((a) => a.role === "ADMIN").length;
  const activeCount = admins.filter((a) => a.isActive).length;

  return (
    <div className="p-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">관리자 계정 관리</h1>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>관리자 추가/제거, 비밀번호 초기화, 활성 상태 관리</p>
        </div>
        {currentRole === "SUPER_ADMIN" && (
          <button onClick={() => setShowAdd(!showAdd)}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white" style={{ background: "var(--primary)" }}>
            + 관리자 추가
          </button>
        )}
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold">{admins.length}</div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>전체 관리자</div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold" style={{ color: "#7c3aed" }}>{superCount}</div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>최고 관리자</div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold" style={{ color: "#2563eb" }}>{adminCount}</div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>관리자</div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold" style={{ color: "#16a34a" }}>{activeCount}</div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>활성 계정</div>
        </div>
      </div>

      {/* 관리자 추가 폼 */}
      {showAdd && (
        <div className="rounded-xl p-5 border mb-6" style={{ borderColor: "var(--primary)", background: "var(--background)" }}>
          <h3 className="font-semibold mb-3">관리자 추가</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium">이름</label>
              <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                placeholder="홍길동" />
            </div>
            <div>
              <label className="text-xs font-medium">이메일 *</label>
              <input type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                placeholder="admin@persismore.com" />
            </div>
            <div>
              <label className="text-xs font-medium">비밀번호 *</label>
              <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                placeholder="초기 비밀번호" />
            </div>
            <div>
              <label className="text-xs font-medium">역할</label>
              <select value={newRole} onChange={(e) => setNewRole(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}>
                <option value="ADMIN">관리자 (ADMIN)</option>
                <option value="SUPER_ADMIN">최고 관리자 (SUPER_ADMIN)</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2 mt-4 justify-end">
            <button onClick={() => setShowAdd(false)} className="px-4 py-1.5 rounded-lg text-sm border" style={{ borderColor: "var(--border)" }}>취소</button>
            <button onClick={handleAddAdmin} className="px-4 py-1.5 rounded-lg text-sm text-white" style={{ background: "var(--primary)" }}>추가</button>
          </div>
        </div>
      )}

      {/* 비밀번호 초기화 모달 */}
      {resetTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.4)" }}>
          <div className="rounded-xl p-6 w-full max-w-sm border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
            <h3 className="font-semibold mb-1">비밀번호 초기화</h3>
            <p className="text-xs mb-4" style={{ color: "var(--muted-foreground)" }}>{resetTarget.email}</p>
            <input type="password" value={resetPassword} onChange={(e) => setResetPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border text-sm mb-4" style={{ borderColor: "var(--border)" }}
              placeholder="새 비밀번호 입력" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => { setResetTarget(null); setResetPassword(""); }}
                className="px-4 py-1.5 rounded-lg text-sm border" style={{ borderColor: "var(--border)" }}>취소</button>
              <button onClick={handleResetPassword}
                className="px-4 py-1.5 rounded-lg text-sm text-white" style={{ background: "var(--primary)" }}>변경</button>
            </div>
          </div>
        </div>
      )}

      {/* 검색 */}
      <div className="mb-4">
        <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
          className="w-full max-w-xs px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
          placeholder="이름 또는 이메일로 검색" />
      </div>

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
            {loading ? (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>
                {search ? "검색 결과가 없습니다" : "등록된 관리자가 없습니다"}
              </td></tr>
            ) : (
              filtered.map((admin) => {
                const roleInfo = ROLE_LABELS[admin.role] || ROLE_LABELS.USER;
                const isMe = admin.id === currentUserId;
                return (
                  <tr key={admin.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2">
                        <div className="font-medium text-sm">
                          {admin.name || "이름 없음"}
                          {isMe && <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: "#dbeafe", color: "#2563eb" }}>나</span>}
                        </div>
                      </div>
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
                      {currentRole === "SUPER_ADMIN" && !isMe ? (
                        <button onClick={() => handleToggleActive(admin.id, admin.isActive)}
                          className="text-xs px-2 py-0.5 rounded-full cursor-pointer" style={{
                            background: admin.isActive ? "#dcfce7" : "#fee2e2",
                            color: admin.isActive ? "#166534" : "#991b1b",
                          }}>
                          {admin.isActive ? "활성" : "비활성"}
                        </button>
                      ) : (
                        <span className="text-xs px-2 py-0.5 rounded-full" style={{
                          background: admin.isActive ? "#dcfce7" : "#fee2e2",
                          color: admin.isActive ? "#166534" : "#991b1b",
                        }}>
                          {admin.isActive ? "활성" : "비활성"}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-4 text-right">
                      {currentRole === "SUPER_ADMIN" && !isMe ? (
                        <div className="flex items-center justify-end gap-1">
                          <select
                            value={admin.role}
                            onChange={(e) => handleChangeRole(admin.id, e.target.value)}
                            className="text-xs px-2 py-1 rounded-lg border" style={{ borderColor: "var(--border)" }}>
                            <option value="SUPER_ADMIN">최고 관리자</option>
                            <option value="ADMIN">관리자</option>
                          </select>
                          <button onClick={() => setResetTarget(admin)}
                            className="text-xs px-2 py-1 rounded-lg border" style={{ borderColor: "var(--border)" }}
                            title="비밀번호 초기화">
                            🔑
                          </button>
                          <button onClick={() => handleRemoveAdmin(admin.id)}
                            className="text-xs px-2 py-1" style={{ color: "var(--destructive)" }}
                            title="권한 제거">
                            제거
                          </button>
                        </div>
                      ) : isMe ? (
                        <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>본인</span>
                      ) : (
                        <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
