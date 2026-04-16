"use client";

import { useEffect, useState } from "react";

interface Plan {
  id: string;
  name: string;
  displayName: string;
  description: string | null;
  priceMonthly: number;
  priceYearly: number;
  tokensIncluded: number;
  dailyTokenLimit: number;
  maxTokensPerReq: number;
  concurrentReqs: number;
  apiKeysAllowed: number;
  allowOverage: boolean;
  features: string[];
  supportLevel: string;
  isActive: boolean;
  isPublic: boolean;
  userCount: number;
}

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function PlansPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Plan | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  useEffect(() => {
    fetchPlans();
  }, []);

  const fetchPlans = async () => {
    try {
      const resp = await fetch("/api/plans", { headers: authHeaders() });
      const data = await resp.json();
      setPlans((data || []).map((p: any) => ({
        id: p.id,
        name: p.name,
        displayName: p.displayName,
        description: p.description,
        priceMonthly: p.priceMonthly || 0,
        priceYearly: p.priceYearly || 0,
        tokensIncluded: p.tokensIncluded || 0,
        dailyTokenLimit: p.dailyTokenLimit || 0,
        maxTokensPerReq: p.maxTokensPerReq || 8192,
        concurrentReqs: p.concurrentReqs || 1,
        apiKeysAllowed: p.apiKeysAllowed || 1,
        allowOverage: p.allowOverage ?? false,
        features: p.features || [],
        supportLevel: p.supportLevel || "community",
        isActive: p.isActive ?? true,
        isPublic: p.isPublic ?? true,
        userCount: p._count?.users || 0,
      })));
    } catch {
      setPlans([]);
    }
    setLoading(false);
  };

  const handleSave = async (data: Partial<Plan>) => {
    try {
      const method = data.id ? "PUT" : "POST";
      const resp = await fetch("/api/plans", {
        method,
        headers: authHeaders(),
        body: JSON.stringify(data),
      });
      if (resp.ok) {
        fetchPlans();
        setEditing(null);
        setShowAdd(false);
      } else {
        alert("저장 실패");
      }
    } catch {
      alert("저장 실패");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("이 플랜을 삭제하시겠습니까? 사용 중인 유저가 있으면 삭제되지 않습니다.")) return;
    try {
      const resp = await fetch("/api/plans", {
        method: "DELETE",
        headers: authHeaders(),
        body: JSON.stringify({ id }),
      });
      if (resp.ok) fetchPlans();
      else {
        const data = await resp.json();
        alert(data.error || "삭제 실패");
      }
    } catch {}
  };

  const totalRevenue = plans.reduce((sum, p) => sum + (p.priceMonthly * p.userCount), 0);

  return (
    <div className="p-6 lg:p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">플랜 관리</h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted-foreground)" }}>
            토큰 패키지 및 구독 플랜. 모델 접근은 각 모델의 "최소 플랜" 설정으로 제어.
          </p>
        </div>
        <button onClick={() => setShowAdd(true)}
          className="px-4 py-2 rounded-lg text-sm font-medium text-white"
          style={{ background: "var(--primary)" }}>
          + 플랜 추가
        </button>
      </div>

      {/* 통계 */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold">{plans.length}</div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>전체 플랜</div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold">{plans.reduce((s, p) => s + p.userCount, 0)}</div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>총 가입자</div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold" style={{ color: "#10b981" }}>
            {(totalRevenue / 10000).toLocaleString()}만원
          </div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>예상 월 매출</div>
        </div>
      </div>

      {/* 편집 모달 */}
      {(editing || showAdd) && (
        <PlanEditor
          plan={editing}
          onSave={handleSave}
          onCancel={() => { setEditing(null); setShowAdd(false); }}
        />
      )}

      {/* 플랜 카드 목록 */}
      {loading ? (
        <div className="text-center py-12 text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {plans.map((plan) => (
            <div key={plan.id} className="rounded-xl p-5 border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
              <div className="flex items-start justify-between mb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-semibold">{plan.displayName}</h3>
                    <span className="text-[10px] px-2 py-0.5 rounded-full" style={{
                      background: plan.isActive ? "#dcfce7" : "#fee2e2",
                      color: plan.isActive ? "#166534" : "#991b1b",
                    }}>
                      {plan.isActive ? "활성" : "비활성"}
                    </span>
                    {!plan.isPublic && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: "var(--muted)", color: "var(--muted-foreground)" }}>
                        비공개
                      </span>
                    )}
                  </div>
                  <div className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>{plan.name}</div>
                  {plan.description && (
                    <p className="text-sm mt-2" style={{ color: "var(--muted-foreground)" }}>{plan.description}</p>
                  )}
                </div>
                <div className="flex gap-1">
                  <button onClick={() => setEditing(plan)}
                    className="text-xs px-3 py-1 rounded-lg border" style={{ borderColor: "var(--border)" }}>
                    수정
                  </button>
                  <button onClick={() => handleDelete(plan.id)}
                    className="text-xs px-2 py-1" style={{ color: "var(--destructive)" }}>
                    삭제
                  </button>
                </div>
              </div>

              {/* 가격 */}
              <div className="mb-4">
                <div className="text-2xl font-bold">
                  {plan.priceMonthly > 0 ? `₩${plan.priceMonthly.toLocaleString()}` : "무료"}
                  <span className="text-sm font-normal" style={{ color: "var(--muted-foreground)" }}>
                    {plan.priceMonthly > 0 ? "/월" : ""}
                  </span>
                </div>
                {plan.priceYearly > 0 && (
                  <div className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>
                    연 ₩{plan.priceYearly.toLocaleString()} ({((1 - plan.priceYearly / (plan.priceMonthly * 12)) * 100).toFixed(0)}% 할인)
                  </div>
                )}
              </div>

              {/* 핵심 정보 */}
              <div className="grid grid-cols-2 gap-3 text-sm mb-4">
                <div>
                  <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>월 토큰</div>
                  <div className="font-semibold">{plan.tokensIncluded.toLocaleString()}</div>
                </div>
                <div>
                  <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>일일 한도</div>
                  <div className="font-semibold">{plan.dailyTokenLimit.toLocaleString()}</div>
                </div>
                <div>
                  <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>동시 요청</div>
                  <div className="font-semibold">{plan.concurrentReqs}개</div>
                </div>
                <div>
                  <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>API 키</div>
                  <div className="font-semibold">{plan.apiKeysAllowed}개</div>
                </div>
              </div>

              {/* 기능 */}
              {plan.features.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-1">
                  {plan.features.map((f) => (
                    <span key={f} className="text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--accent)", color: "var(--accent-foreground)" }}>
                      {f}
                    </span>
                  ))}
                </div>
              )}

              {/* 하단 정보 */}
              <div className="pt-3 border-t flex items-center justify-between text-xs" style={{ borderColor: "var(--border)", color: "var(--muted-foreground)" }}>
                <span>가입자 {plan.userCount}명</span>
                <span>
                  월 매출 <strong className="text-base" style={{ color: "var(--foreground)" }}>
                    {plan.priceMonthly > 0 ? `${((plan.priceMonthly * plan.userCount) / 10000).toLocaleString()}만원` : "-"}
                  </strong>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// 플랜 편집 모달
// ═══════════════════════════════════════════════════════════

function PlanEditor({
  plan,
  onSave,
  onCancel,
}: {
  plan: Plan | null;
  onSave: (p: Partial<Plan>) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<Partial<Plan>>(
    plan || {
      name: "",
      displayName: "",
      description: "",
      priceMonthly: 0,
      priceYearly: 0,
      tokensIncluded: 10000,
      dailyTokenLimit: 3000,
      maxTokensPerReq: 8192,
      concurrentReqs: 1,
      apiKeysAllowed: 1,
      allowOverage: false,
      features: [],
      supportLevel: "community",
      isActive: true,
      isPublic: true,
    }
  );
  const [featureInput, setFeatureInput] = useState("");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.5)" }}>
      <div className="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl p-6 border"
        style={{ background: "var(--background)", borderColor: "var(--border)" }}>
        <h2 className="text-lg font-bold mb-4">{plan ? "플랜 수정" : "플랜 추가"}</h2>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium">플랜 ID *</label>
              <input type="text" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                placeholder="free, starter, pro..." />
            </div>
            <div>
              <label className="text-xs font-medium">표시 이름 *</label>
              <input type="text" value={form.displayName || ""} onChange={(e) => setForm({ ...form, displayName: e.target.value })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                placeholder="Free, Starter, Pro..." />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium">설명</label>
            <input type="text" value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium">월 가격 (원)</label>
              <input type="number" value={form.priceMonthly} onChange={(e) => setForm({ ...form, priceMonthly: parseInt(e.target.value) || 0 })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
            </div>
            <div>
              <label className="text-xs font-medium">연 가격 (원)</label>
              <input type="number" value={form.priceYearly} onChange={(e) => setForm({ ...form, priceYearly: parseInt(e.target.value) || 0 })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
            </div>
          </div>

          <div className="rounded-lg p-3 border-2" style={{ borderColor: "var(--primary)", background: "var(--accent)" }}>
            <div className="text-xs font-bold mb-2" style={{ color: "var(--primary)" }}>⭐ 토큰 설정</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium">월 토큰</label>
                <input type="number" value={form.tokensIncluded} onChange={(e) => setForm({ ...form, tokensIncluded: parseInt(e.target.value) || 0 })}
                  className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
              </div>
              <div>
                <label className="text-xs font-medium">일일 한도</label>
                <input type="number" value={form.dailyTokenLimit} onChange={(e) => setForm({ ...form, dailyTokenLimit: parseInt(e.target.value) || 0 })}
                  className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-medium">요청당 최대</label>
              <input type="number" value={form.maxTokensPerReq} onChange={(e) => setForm({ ...form, maxTokensPerReq: parseInt(e.target.value) || 8192 })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
            </div>
            <div>
              <label className="text-xs font-medium">동시 요청</label>
              <input type="number" value={form.concurrentReqs} onChange={(e) => setForm({ ...form, concurrentReqs: parseInt(e.target.value) || 1 })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
            </div>
            <div>
              <label className="text-xs font-medium">API 키 수</label>
              <input type="number" value={form.apiKeysAllowed} onChange={(e) => setForm({ ...form, apiKeysAllowed: parseInt(e.target.value) || 1 })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium">지원 수준</label>
            <select value={form.supportLevel} onChange={(e) => setForm({ ...form, supportLevel: e.target.value })}
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}>
              <option value="community">Community (커뮤니티)</option>
              <option value="email">Email (이메일 지원)</option>
              <option value="priority">Priority (우선 지원)</option>
              <option value="dedicated">Dedicated (전담 지원)</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-medium">기능 태그</label>
            <div className="flex gap-2 mt-1">
              <input type="text" value={featureInput} onChange={(e) => setFeatureInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && featureInput.trim()) {
                    e.preventDefault();
                    setForm({ ...form, features: [...(form.features || []), featureInput.trim()] });
                    setFeatureInput("");
                  }
                }}
                className="flex-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                placeholder="기능 입력 후 Enter (예: chat, api, code)" />
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
              {(form.features || []).map((f, i) => (
                <span key={i} className="text-xs px-2 py-0.5 rounded-full flex items-center gap-1" style={{ background: "var(--accent)", color: "var(--accent-foreground)" }}>
                  {f}
                  <button onClick={() => setForm({ ...form, features: form.features?.filter((x) => x !== f) })}
                    className="hover:text-red-500">×</button>
                </span>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-4 pt-2">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.allowOverage} onChange={(e) => setForm({ ...form, allowOverage: e.target.checked })} />
              초과 토큰 구매 허용
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.isActive} onChange={(e) => setForm({ ...form, isActive: e.target.checked })} />
              활성
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.isPublic} onChange={(e) => setForm({ ...form, isPublic: e.target.checked })} />
              공개
            </label>
          </div>
        </div>

        <div className="flex gap-2 mt-6 justify-end">
          <button onClick={onCancel} className="px-4 py-2 rounded-lg text-sm border" style={{ borderColor: "var(--border)" }}>
            취소
          </button>
          <button onClick={() => onSave(form)} disabled={!form.name || !form.displayName}
            className="px-4 py-2 rounded-lg text-sm text-white font-medium disabled:opacity-50"
            style={{ background: "var(--primary)" }}>
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
