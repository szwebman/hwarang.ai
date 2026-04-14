"use client";

import { useEffect, useState } from "react";

interface Plan {
  id: string;
  name: string;
  displayName: string;
  priceMonthly: number;
  requestsPerDay: number;
  tokensPerMonth: number;
  models: string[];
  features: string[];
  userCount: number;
  isActive: boolean;
}

export default function PlansPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPlans();
  }, []);

  const fetchPlans = async () => {
    try {
      const resp = await fetch("/api/plans");
      const data = await resp.json();
      setPlans(data.map((p: any) => ({
        id: p.id,
        name: p.name,
        displayName: p.displayName,
        priceMonthly: p.priceMonthly,
        requestsPerDay: p.dailyTokenLimit || 0,
        tokensPerMonth: p.tokensIncluded || 0,
        models: p.models || [],
        features: p.features || [],
        userCount: p._count?.users || 0,
        isActive: p.isActive ?? true,
      })));
    } catch {
      setPlans([]);
    }
    setLoading(false);
  };

  const handleSavePlan = async (planId: string, data: Partial<Plan>) => {
    try {
      await fetch("/api/plans", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: planId, ...data }),
      });
      fetchPlans(); // 새로고침
      setEditingPlan(null);
    } catch (e) {
      alert("저장 실패");
    }
  };

  const [editingPlan, setEditingPlan] = useState<string | null>(null);

  return (
    <div className="min-h-screen" style={{ background: "var(--muted)" }}>
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">플랜 관리</h1>
            <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
              구독 플랜 생성, 수정, 가격 변경
            </p>
          </div>
          <button className="px-4 py-2 rounded-xl text-sm font-medium text-white" style={{ background: "var(--primary)" }}>
            + 새 플랜 만들기
          </button>
        </div>

        {/* 플랜 카드 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {plans.map((plan) => (
            <div
              key={plan.id}
              className="rounded-2xl p-6"
              style={{ background: "var(--background)", border: "1px solid var(--border)" }}
            >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-semibold">{plan.displayName}</h3>
                  <span className={`text-xs px-2 py-0.5 rounded-full`} style={{
                    background: plan.isActive ? "#dcfce7" : "#fee2e2",
                    color: plan.isActive ? "#166534" : "#991b1b",
                  }}>
                    {plan.isActive ? "활성" : "비활성"}
                  </span>
                </div>
                <button
                  onClick={() => setEditingPlan(editingPlan === plan.id ? null : plan.id)}
                  className="text-xs px-3 py-1.5 rounded-lg border"
                  style={{ borderColor: "var(--border)" }}
                >
                  {editingPlan === plan.id ? "닫기" : "수정"}
                </button>
              </div>

              {/* 핵심 정보 */}
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span style={{ color: "var(--muted-foreground)" }}>가격: </span>
                  <span className="font-semibold">
                    {plan.priceMonthly > 0 ? `${plan.priceMonthly.toLocaleString()}원/월` : plan.name === "enterprise" ? "맞춤" : "무료"}
                  </span>
                </div>
                <div>
                  <span style={{ color: "var(--muted-foreground)" }}>사용자: </span>
                  <span className="font-semibold">{plan.userCount}명</span>
                </div>
                <div>
                  <span style={{ color: "var(--muted-foreground)" }}>일일 요청: </span>
                  <span className="font-semibold">{plan.requestsPerDay === -1 ? "무제한" : plan.requestsPerDay}</span>
                </div>
                <div>
                  <span style={{ color: "var(--muted-foreground)" }}>월 토큰: </span>
                  <span className="font-semibold">{plan.tokensPerMonth === -1 ? "무제한" : `${(plan.tokensPerMonth / 1000000).toFixed(0)}M`}</span>
                </div>
              </div>

              {/* 모델 + 기능 */}
              <div className="mt-3 flex flex-wrap gap-1">
                {plan.models.map((m) => (
                  <span key={m} className="text-xs px-2 py-0.5 rounded" style={{ background: "var(--accent)", color: "var(--primary)" }}>{m}</span>
                ))}
                {plan.features.map((f) => (
                  <span key={f} className="text-xs px-2 py-0.5 rounded" style={{ background: "var(--muted)" }}>{f}</span>
                ))}
              </div>

              {/* 매출 */}
              <div className="mt-4 pt-3 border-t text-sm" style={{ borderColor: "var(--border)" }}>
                <span style={{ color: "var(--muted-foreground)" }}>예상 월 매출: </span>
                <span className="font-semibold">
                  {plan.priceMonthly > 0
                    ? `${((plan.priceMonthly * plan.userCount) / 10000).toLocaleString()}만원`
                    : "-"}
                </span>
              </div>

              {/* 수정 폼 */}
              {editingPlan === plan.id && (
                <div className="mt-4 pt-4 border-t space-y-3" style={{ borderColor: "var(--border)" }}>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium">월 가격 (원)</label>
                      <input type="number" defaultValue={plan.priceMonthly} className="w-full mt-1 px-3 py-1.5 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
                    </div>
                    <div>
                      <label className="text-xs font-medium">일일 요청 한도</label>
                      <input type="number" defaultValue={plan.requestsPerDay} className="w-full mt-1 px-3 py-1.5 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
                    </div>
                    <div>
                      <label className="text-xs font-medium">월 토큰 한도</label>
                      <input type="number" defaultValue={plan.tokensPerMonth} className="w-full mt-1 px-3 py-1.5 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
                    </div>
                    <div>
                      <label className="text-xs font-medium">동시 요청 수</label>
                      <input type="number" defaultValue={1} className="w-full mt-1 px-3 py-1.5 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
                    </div>
                  </div>
                  <div className="flex gap-2 justify-end">
                    <button className="px-4 py-1.5 rounded-lg text-sm border" style={{ borderColor: "var(--border)" }}>취소</button>
                    <button className="px-4 py-1.5 rounded-lg text-sm text-white" style={{ background: "var(--primary)" }}>저장</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
