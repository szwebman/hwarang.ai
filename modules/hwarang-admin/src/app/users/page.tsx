"use client";

import { useEffect, useState } from "react";

interface User {
  id: string;
  name: string;
  email: string;
  image: string | null;
  plan: string;
  planId: string | null;
  role: string;
  requestsThisMonth: number;
  tokensThisMonth: number;
  tokenBalance: number;
  apiKeys: number;
  isActive: boolean;
  createdAt: string;
  lastActiveAt: string;
}

interface UserDetail {
  id: string;
  name: string | null;
  email: string;
  image: string | null;
  role: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  plan: { id: string; displayName: string; name: string } | null;
  tokenBalance: { balance: number; totalUsed: number; totalCharged: number; dailyUsed: number; dailyLimit: number } | null;
  apiKeys: { id: string; name: string; keyPrefix: string; isActive: boolean; lastUsedAt: string | null; createdAt: string }[];
  _count: { usageRecords: number; conversations: number; payments: number };
}

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function UsersPage() {
  const [search, setSearch] = useState("");
  const [planFilter, setPlanFilter] = useState("all");
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  // 상세 모달
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 토큰 조정 모달
  const [adjustTarget, setAdjustTarget] = useState<UserDetail | null>(null);
  const [adjustAmount, setAdjustAmount] = useState("");
  const [adjustReason, setAdjustReason] = useState("");

  // 플랜 목록 (변경 dropdown 용)
  const [plans, setPlans] = useState<{ id: string; name: string; displayName: string }[]>([]);

  useEffect(() => {
    fetchUsers();
  }, [search, planFilter]);

  useEffect(() => {
    // 플랜 목록 1회 로드
    fetch(`/api/plans`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setPlans(data.map((p: any) => ({ id: p.id, name: p.name, displayName: p.displayName })));
        }
      })
      .catch(() => {});
  }, []);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (planFilter !== "all") params.set("plan", planFilter);

      const resp = await fetch(`/api/users?${params}`, { headers: authHeaders() });
      const data = await resp.json();

      setUsers((data.users || []).map((u: any) => ({
        id: u.id,
        name: u.name || "이름 없음",
        email: u.email,
        image: u.image,
        plan: u.plan?.displayName || "Free",
        planId: u.planId,
        role: u.role,
        requestsThisMonth: u._count?.usageRecords || 0,
        tokensThisMonth: u.tokenBalance?.totalUsed || 0,
        tokenBalance: u.tokenBalance?.balance || 0,
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

  const openDetail = async (userId: string) => {
    setDetailLoading(true);
    setDetail(null);
    try {
      const resp = await fetch(`/api/users/${userId}`, { headers: authHeaders() });
      if (resp.ok) {
        setDetail(await resp.json());
      }
    } catch {}
    setDetailLoading(false);
  };

  const closeDetail = () => {
    setDetail(null);
    setDetailLoading(false);
  };

  const handleToggleActive = async (userId: string, currentActive: boolean) => {
    try {
      await fetch(`/api/users/${userId}`, {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ isActive: !currentActive }),
      });
      fetchUsers();
      if (detail?.id === userId) openDetail(userId);
    } catch {}
  };

  const handleChangeRole = async (userId: string, role: string) => {
    try {
      await fetch(`/api/users/${userId}`, {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ role }),
      });
      fetchUsers();
      if (detail?.id === userId) openDetail(userId);
    } catch {}
  };

  const handleChangePlan = async (userId: string, planId: string | null) => {
    try {
      const resp = await fetch(`/api/users/${userId}`, {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ planId }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        alert("플랜 변경 실패: " + (data.error || resp.statusText));
        return;
      }
      fetchUsers();
      if (detail?.id === userId) openDetail(userId);
    } catch (e: any) {
      alert("플랜 변경 실패: " + (e?.message || e));
    }
  };

  const handleAdjustTokens = async () => {
    if (!adjustTarget || !adjustAmount) return;
    try {
      const resp = await fetch(`/api/users/${adjustTarget.id}/tokens`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ amount: parseInt(adjustAmount), reason: adjustReason || "관리자 수동 조정" }),
      });
      if (resp.ok) {
        setAdjustTarget(null);
        setAdjustAmount("");
        setAdjustReason("");
        fetchUsers();
        if (detail?.id === adjustTarget.id) openDetail(adjustTarget.id);
      } else {
        const data = await resp.json();
        alert(data.error || "조정 실패");
      }
    } catch {}
  };

  const filteredUsers = users;

  return (
    <div className="p-6 lg:p-8">
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
          <option value="starter">Starter</option>
          <option value="pro">Pro</option>
          <option value="business">Business</option>
        </select>
      </div>

      {/* 테이블 */}
      <div className="rounded-xl overflow-hidden border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "var(--muted)" }}>
              <th className="text-left text-xs font-semibold px-5 py-3">사용자</th>
              <th className="text-left text-xs font-semibold px-5 py-3">플랜</th>
              <th className="text-right text-xs font-semibold px-5 py-3">토큰 잔액</th>
              <th className="text-right text-xs font-semibold px-5 py-3">요청 수</th>
              <th className="text-center text-xs font-semibold px-5 py-3">상태</th>
              <th className="text-left text-xs font-semibold px-5 py-3">가입일</th>
              <th className="text-right text-xs font-semibold px-5 py-3">액션</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="px-5 py-8 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</td></tr>
            ) : filteredUsers.length === 0 ? (
              <tr><td colSpan={7} className="px-5 py-8 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>
                {search ? "검색 결과가 없습니다" : "등록된 유저가 없습니다"}
              </td></tr>
            ) : (
              filteredUsers.map((user) => (
                <tr key={user.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium text-white shrink-0"
                        style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}>
                        {user.name?.charAt(0) || "?"}
                      </div>
                      <div>
                        <div className="font-medium text-sm">{user.name}</div>
                        <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>{user.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{
                      background: user.plan === "Business" ? "#ede9fe" : user.plan === "Pro" ? "#eef2ff" : user.plan === "Starter" ? "#fef3c7" : "var(--muted)",
                      color: user.plan === "Business" ? "#5b21b6" : user.plan === "Pro" ? "#4338ca" : user.plan === "Starter" ? "#92400e" : "var(--muted-foreground)",
                    }}>
                      {user.plan}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right text-sm font-mono">{user.tokenBalance.toLocaleString()}</td>
                  <td className="px-5 py-4 text-right text-sm font-mono">{user.requestsThisMonth.toLocaleString()}</td>
                  <td className="px-5 py-4 text-center">
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{
                      background: user.isActive ? "#dcfce7" : "#fee2e2",
                      color: user.isActive ? "#166534" : "#991b1b",
                    }}>
                      {user.isActive ? "활성" : "비활성"}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--muted-foreground)" }}>{user.createdAt}</td>
                  <td className="px-5 py-4 text-right">
                    <button
                      onClick={() => openDetail(user.id)}
                      className="text-xs px-3 py-1.5 rounded-lg border font-medium"
                      style={{ borderColor: "var(--border)", color: "var(--primary)" }}
                    >
                      상세
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* ─── 유저 상세 모달 ─── */}
      {(detail || detailLoading) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.5)" }} onClick={closeDetail}>
          <div className="w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-2xl border p-6"
            style={{ background: "var(--background)", borderColor: "var(--border)" }}
            onClick={(e) => e.stopPropagation()}>

            {detailLoading && !detail ? (
              <div className="py-12 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</div>
            ) : detail ? (
              <>
                {/* 헤더 */}
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-lg font-bold">유저 상세</h2>
                  <button onClick={closeDetail} className="w-8 h-8 flex items-center justify-center rounded-lg"
                    style={{ color: "var(--muted-foreground)" }}>
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" x2="6" y1="6" y2="18"/><line x1="6" x2="18" y1="6" y2="18"/></svg>
                  </button>
                </div>

                {/* 프로필 */}
                <div className="flex items-center gap-4 mb-6">
                  <div className="w-14 h-14 rounded-full flex items-center justify-center text-lg font-bold text-white shrink-0"
                    style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}>
                    {detail.name?.charAt(0) || "?"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-base">{detail.name || "이름 없음"}</div>
                    <div className="text-sm" style={{ color: "var(--muted-foreground)" }}>{detail.email}</div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs px-2 py-0.5 rounded-full" style={{
                        background: detail.isActive ? "#dcfce7" : "#fee2e2",
                        color: detail.isActive ? "#166534" : "#991b1b",
                      }}>
                        {detail.isActive ? "활성" : "비활성"}
                      </span>
                      <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                        가입: {detail.createdAt?.split("T")[0]}
                      </span>
                    </div>
                  </div>
                </div>

                {/* 정보 그리드 */}
                <div className="grid grid-cols-2 gap-3 mb-5">
                  <div className="rounded-xl p-3" style={{ background: "var(--muted)" }}>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>플랜</div>
                    <select
                      className="text-sm font-semibold mt-0.5 w-full bg-transparent outline-none cursor-pointer"
                      style={{ background: "transparent", color: "var(--foreground)" }}
                      value={detail.plan?.id || ""}
                      onChange={(e) => handleChangePlan(detail.id, e.target.value || null)}
                    >
                      <option value="">Free (플랜 없음)</option>
                      {plans.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.displayName} ({p.name})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="rounded-xl p-3" style={{ background: "var(--muted)" }}>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>역할</div>
                    <div className="text-sm font-semibold mt-0.5">
                      <select value={detail.role}
                        onChange={(e) => handleChangeRole(detail.id, e.target.value)}
                        className="text-sm font-semibold border-none bg-transparent p-0 cursor-pointer">
                        <option value="USER">일반 유저</option>
                        <option value="ADMIN">관리자</option>
                        <option value="SUPER_ADMIN">최고 관리자</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* 토큰 */}
                <div className="rounded-xl p-4 mb-5" style={{ background: "var(--muted)" }}>
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-sm font-semibold">토큰 현황</div>
                    <button onClick={() => setAdjustTarget(detail)}
                      className="text-xs px-2 py-1 rounded-lg font-medium"
                      style={{ background: "var(--accent)", color: "var(--accent-foreground)" }}>
                      토큰 조정
                    </button>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>잔액</div>
                      <div className="text-lg font-bold" style={{ color: "var(--primary)" }}>
                        {(detail.tokenBalance?.balance || 0).toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>누적 사용</div>
                      <div className="text-lg font-bold">{(detail.tokenBalance?.totalUsed || 0).toLocaleString()}</div>
                    </div>
                    <div>
                      <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>오늘 사용</div>
                      <div className="text-lg font-bold">
                        {(detail.tokenBalance?.dailyUsed || 0).toLocaleString()}
                        <span className="text-xs font-normal" style={{ color: "var(--muted-foreground)" }}>
                          /{(detail.tokenBalance?.dailyLimit || 0).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 통계 */}
                <div className="grid grid-cols-3 gap-3 mb-5">
                  <div className="text-center rounded-xl p-3" style={{ background: "var(--muted)" }}>
                    <div className="text-lg font-bold">{detail._count?.usageRecords || 0}</div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>API 요청</div>
                  </div>
                  <div className="text-center rounded-xl p-3" style={{ background: "var(--muted)" }}>
                    <div className="text-lg font-bold">{detail._count?.conversations || 0}</div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>대화</div>
                  </div>
                  <div className="text-center rounded-xl p-3" style={{ background: "var(--muted)" }}>
                    <div className="text-lg font-bold">{detail._count?.payments || 0}</div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>결제</div>
                  </div>
                </div>

                {/* API 키 */}
                {detail.apiKeys && detail.apiKeys.length > 0 && (
                  <div className="mb-5">
                    <div className="text-sm font-semibold mb-2">API 키</div>
                    {detail.apiKeys.map((key) => (
                      <div key={key.id} className="flex items-center justify-between py-2 border-b" style={{ borderColor: "var(--border)" }}>
                        <div>
                          <span className="text-sm font-medium">{key.name}</span>
                          <span className="text-xs ml-2 font-mono" style={{ color: "var(--muted-foreground)" }}>{key.keyPrefix}...</span>
                        </div>
                        <span className="text-xs px-2 py-0.5 rounded-full" style={{
                          background: key.isActive ? "#dcfce7" : "#fee2e2",
                          color: key.isActive ? "#166534" : "#991b1b",
                        }}>
                          {key.isActive ? "활성" : "비활성"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* 액션 버튼 */}
                <div className="flex gap-2">
                  <button
                    onClick={() => handleToggleActive(detail.id, detail.isActive)}
                    className="flex-1 py-2 rounded-xl text-sm font-medium border"
                    style={{
                      borderColor: detail.isActive ? "var(--destructive)" : "var(--success)",
                      color: detail.isActive ? "var(--destructive)" : "var(--success)",
                    }}>
                    {detail.isActive ? "계정 비활성화" : "계정 활성화"}
                  </button>
                  <button onClick={closeDetail}
                    className="flex-1 py-2 rounded-xl text-sm font-medium border"
                    style={{ borderColor: "var(--border)" }}>
                    닫기
                  </button>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}

      {/* ─── 토큰 조정 모달 ─── */}
      {adjustTarget && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.5)" }}>
          <div className="w-full max-w-sm rounded-2xl border p-6"
            style={{ background: "var(--background)", borderColor: "var(--border)" }}
            onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold mb-1">토큰 수동 조정</h3>
            <p className="text-xs mb-4" style={{ color: "var(--muted-foreground)" }}>
              {adjustTarget.name || adjustTarget.email} · 현재 잔액: {(adjustTarget.tokenBalance?.balance || 0).toLocaleString()}
            </p>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium">토큰 수</label>
                <input type="number" value={adjustAmount} onChange={(e) => setAdjustAmount(e.target.value)}
                  className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                  placeholder="양수: 충전, 음수: 차감 (예: 1000, -500)" />
              </div>
              <div>
                <label className="text-xs font-medium">사유</label>
                <input type="text" value={adjustReason} onChange={(e) => setAdjustReason(e.target.value)}
                  className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                  placeholder="관리자 수동 조정" />
              </div>
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => { setAdjustTarget(null); setAdjustAmount(""); setAdjustReason(""); }}
                className="px-4 py-1.5 rounded-lg text-sm border" style={{ borderColor: "var(--border)" }}>취소</button>
              <button onClick={handleAdjustTokens}
                className="px-4 py-1.5 rounded-lg text-sm text-white font-medium" style={{ background: "var(--primary)" }}>조정</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
