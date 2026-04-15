"use client";

import { useEffect, useState } from "react";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface PaymentRow {
  id: string;
  userId: string;
  user: { name: string | null; email: string };
  amount: number;
  status: string;
  method: string | null;
  planName: string | null;
  billingType: string;
  paidAt: string | null;
  createdAt: string;
}

interface BillingStats {
  totalRevenue: number;
  monthRevenue: number;
  todayRevenue: number;
  totalPayments: number;
  paidCount: number;
  canceledCount: number;
}

const STATUS_STYLE: Record<string, { label: string; bg: string; color: string }> = {
  PAID: { label: "결제 완료", bg: "#dcfce7", color: "#166534" },
  PENDING: { label: "대기 중", bg: "#fef9c3", color: "#854d0e" },
  CANCELED: { label: "취소", bg: "#fee2e2", color: "#991b1b" },
  REFUNDED: { label: "환불", bg: "#e0e7ff", color: "#3730a3" },
  FAILED: { label: "실패", bg: "#fecaca", color: "#dc2626" },
};

export default function BillingPage() {
  const [payments, setPayments] = useState<PaymentRow[]>([]);
  const [stats, setStats] = useState<BillingStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [payResp, statsResp] = await Promise.all([
        fetch("/api/billing", { headers: authHeaders() }),
        fetch("/api/billing/stats", { headers: authHeaders() }),
      ]);
      if (payResp.ok) setPayments(await payResp.json());
      if (statsResp.ok) setStats(await statsResp.json());
    } catch {}
    setLoading(false);
  };

  const formatKRW = (n: number) => n.toLocaleString("ko-KR") + "원";

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">매출 현황</h1>
        <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>결제 내역 및 매출 통계</p>
      </div>

      {/* 매출 통계 */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {[
          { label: "총 매출", value: stats ? formatKRW(stats.totalRevenue) : "—", color: "var(--foreground)" },
          { label: "이번 달", value: stats ? formatKRW(stats.monthRevenue) : "—", color: "#2563eb" },
          { label: "오늘", value: stats ? formatKRW(stats.todayRevenue) : "—", color: "#16a34a" },
          { label: "전체 결제 건", value: stats ? `${stats.paidCount}건` : "—", color: "var(--foreground)" },
        ].map((card, i) => (
          <div key={i} className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
            <div className="text-xl font-bold" style={{ color: card.color }}>{card.value}</div>
            <div className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>{card.label}</div>
          </div>
        ))}
      </div>

      {/* 결제 내역 */}
      <div className="rounded-xl overflow-hidden border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "var(--muted)" }}>
              <th className="text-left text-xs font-semibold px-5 py-3">유저</th>
              <th className="text-left text-xs font-semibold px-5 py-3">상품</th>
              <th className="text-right text-xs font-semibold px-5 py-3">금액</th>
              <th className="text-center text-xs font-semibold px-5 py-3">상태</th>
              <th className="text-left text-xs font-semibold px-5 py-3">결제 방법</th>
              <th className="text-left text-xs font-semibold px-5 py-3">일시</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="px-5 py-8 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</td></tr>
            ) : payments.length === 0 ? (
              <tr><td colSpan={6} className="px-5 py-8 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>결제 내역이 없습니다</td></tr>
            ) : (
              payments.map((p) => {
                const st = STATUS_STYLE[p.status] || STATUS_STYLE.PENDING;
                return (
                  <tr key={p.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="px-5 py-3">
                      <div className="text-sm font-medium">{p.user?.name || "—"}</div>
                      <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>{p.user?.email}</div>
                    </td>
                    <td className="px-5 py-3 text-sm">{p.planName || "토큰 구매"}</td>
                    <td className="px-5 py-3 text-sm text-right font-medium">{formatKRW(p.amount)}</td>
                    <td className="px-5 py-3 text-center">
                      <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: st.bg, color: st.color }}>{st.label}</span>
                    </td>
                    <td className="px-5 py-3 text-sm" style={{ color: "var(--muted-foreground)" }}>{p.method || "—"}</td>
                    <td className="px-5 py-3 text-xs" style={{ color: "var(--muted-foreground)" }}>
                      {(p.paidAt || p.createdAt)?.replace("T", " ").slice(0, 16)}
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
