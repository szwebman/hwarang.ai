"use client";

import { useEffect, useState } from "react";

interface User {
  id: string;
  name: string;
  email: string;
  plan: string;
  role: string;
  requestsThisMonth: number;
  tokensThisMonth: number;
  apiKeys: number;
  isActive: boolean;
  createdAt: string;
  lastActiveAt: string;
}

export default function UsersPage() {
  const [search, setSearch] = useState("");
  const [planFilter, setPlanFilter] = useState("all");

  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchUsers();
  }, [search, planFilter]);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (planFilter !== "all") params.set("plan", planFilter);

      const resp = await fetch(`/api/admin/users?${params}`);
      const data = await resp.json();

      setUsers((data.users || []).map((u: any) => ({
        id: u.id,
        name: u.name || "이름 없음",
        email: u.email,
        plan: u.plan?.displayName || "Free",
        role: u.role,
        requestsThisMonth: u._count?.usageRecords || 0,
        tokensThisMonth: u.tokenBalance?.totalUsed || 0,
        apiKeys: u._count?.apiKeys || 0,
        isActive: u.isActive,
        createdAt: u.createdAt?.split("T")[0] || "",
        lastActiveAt: u.updatedAt?.split("T")[0] || "",
      })));
      setTotal(data.pagination?.total || 0);
    } catch {
      setUsers([]);
    }
    setLoading(false);
  };

  const filteredUsers = users.filter((u) => {
    const matchSearch = !search || u.name.includes(search) || u.email.includes(search);
    const matchPlan = planFilter === "all" || u.plan.toLowerCase() === planFilter;
    return matchSearch && matchPlan;
  });

  return (
    <div className="min-h-screen" style={{ background: "var(--muted)" }}>
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">유저 관리</h1>
            <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
              전체 {total}명 · 활성 {users.filter(u => u.isActive).length}명
            </p>
          </div>
        </div>

        {/* 필터 */}
        <div className="flex gap-3 mb-6">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="이름 또는 이메일 검색..."
            className="flex-1 max-w-sm px-4 py-2 rounded-xl border text-sm"
            style={{ borderColor: "var(--border)", background: "var(--background)" }}
          />
          <select
            value={planFilter}
            onChange={(e) => setPlanFilter(e.target.value)}
            className="px-4 py-2 rounded-xl border text-sm"
            style={{ borderColor: "var(--border)", background: "var(--background)" }}
          >
            <option value="all">모든 플랜</option>
            <option value="free">Free</option>
            <option value="pro">Pro</option>
            <option value="business">Business</option>
            <option value="enterprise">Enterprise</option>
          </select>
        </div>

        {/* 테이블 */}
        <div className="rounded-2xl overflow-hidden" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
          <table className="w-full">
            <thead>
              <tr style={{ background: "var(--muted)" }}>
                <th className="text-left text-xs font-semibold px-5 py-3">사용자</th>
                <th className="text-left text-xs font-semibold px-5 py-3">플랜</th>
                <th className="text-right text-xs font-semibold px-5 py-3">이번 달 요청</th>
                <th className="text-right text-xs font-semibold px-5 py-3">토큰 사용</th>
                <th className="text-center text-xs font-semibold px-5 py-3">API 키</th>
                <th className="text-center text-xs font-semibold px-5 py-3">상태</th>
                <th className="text-left text-xs font-semibold px-5 py-3">마지막 활동</th>
                <th className="text-right text-xs font-semibold px-5 py-3">액션</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((user) => (
                <tr key={user.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="px-5 py-4">
                    <div className="font-medium text-sm">{user.name}</div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>{user.email}</div>
                  </td>
                  <td className="px-5 py-4">
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{
                      background: user.plan === "Business" ? "#ede9fe" : user.plan === "Pro" ? "#eef2ff" : "var(--muted)",
                      color: user.plan === "Business" ? "#5b21b6" : user.plan === "Pro" ? "#4338ca" : "var(--muted-foreground)",
                    }}>
                      {user.plan}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right text-sm font-mono">{user.requestsThisMonth.toLocaleString()}</td>
                  <td className="px-5 py-4 text-right text-sm font-mono">{(user.tokensThisMonth / 1000).toFixed(0)}K</td>
                  <td className="px-5 py-4 text-center text-sm">{user.apiKeys}</td>
                  <td className="px-5 py-4 text-center">
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{
                      background: user.isActive ? "#dcfce7" : "#fee2e2",
                      color: user.isActive ? "#166534" : "#991b1b",
                    }}>
                      {user.isActive ? "활성" : "비활성"}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--muted-foreground)" }}>{user.lastActiveAt}</td>
                  <td className="px-5 py-4 text-right">
                    <button className="text-xs px-3 py-1 rounded-lg border" style={{ borderColor: "var(--border)" }}>
                      상세
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
