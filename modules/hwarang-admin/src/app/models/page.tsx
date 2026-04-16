"use client";

import { useEffect, useState } from "react";

interface AIModel {
  id: string;
  name: string;
  displayName: string;
  description: string | null;
  backendId: string;
  endpoint: string;
  inputMultiplier: number;
  outputMultiplier: number;
  maxContextLength: number;
  maxOutputTokens: number;
  category: string;
  tier: string;
  tags: string[];
  minPlan: string | null;
  isPublic: boolean;
  isDefault: boolean;
  isActive: boolean;
  status: string;
  sortOrder: number;
}

interface VLLMModel {
  id: string;
  object: string;
  created: number;
  owned_by: string;
}

const CATEGORY_OPTIONS = [
  { value: "general", label: "일반" },
  { value: "coding", label: "코딩" },
  { value: "legal", label: "법률" },
  { value: "tax", label: "세무" },
  { value: "reasoning", label: "추론" },
];

const TIER_OPTIONS = [
  { value: "basic", label: "Basic", color: "#6b7280" },
  { value: "standard", label: "Standard", color: "#2563eb" },
  { value: "premium", label: "Premium", color: "#7c3aed" },
  { value: "flagship", label: "Flagship", color: "#ec4899" },
];

const PLAN_OPTIONS = [
  { value: "", label: "제한 없음" },
  { value: "free", label: "Free 이상" },
  { value: "starter", label: "Starter 이상" },
  { value: "pro", label: "Pro 이상" },
  { value: "business", label: "Business 이상" },
];

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function ModelsPage() {
  const [models, setModels] = useState<AIModel[]>([]);
  const [vllmModels, setVllmModels] = useState<VLLMModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<AIModel | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  useEffect(() => {
    fetchModels();
  }, []);

  const fetchModels = async () => {
    try {
      const resp = await fetch("/api/models", { headers: authHeaders() });
      if (resp.ok) {
        const data = await resp.json();
        setModels(data.models || []);
        setVllmModels(data.vllmModels || []);
      }
    } catch {}
    setLoading(false);
  };

  const handleSave = async (model: Partial<AIModel>) => {
    setSaving(true);
    try {
      const method = model.id ? "PUT" : "POST";
      const resp = await fetch("/api/models", {
        method,
        headers: authHeaders(),
        body: JSON.stringify(model),
      });
      if (resp.ok) {
        await fetchModels();
        setEditing(null);
        setShowAdd(false);
      } else {
        const data = await resp.json();
        alert(data.error || "저장 실패");
      }
    } catch {
      alert("저장 중 오류");
    }
    setSaving(false);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("이 모델을 삭제하시겠습니까?")) return;
    try {
      await fetch("/api/models", {
        method: "DELETE",
        headers: authHeaders(),
        body: JSON.stringify({ id }),
      });
      fetchModels();
    } catch {}
  };

  const handleToggle = async (model: AIModel, field: "isActive" | "isPublic" | "isDefault") => {
    const updated: any = { id: model.id };
    updated[field] = !model[field];
    // isDefault는 1개만 가능하게 (다른 default 해제)
    await handleSave(updated);
  };

  const handleTestModel = async (backendId: string) => {
    try {
      const resp = await fetch("/api/models/test", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ backendId, message: "안녕하세요, 간단히 자기소개 해주세요." }),
      });
      const data = await resp.json();
      if (data.response) {
        alert(`✅ 응답 (${data.tokens}토큰):\n\n${data.response.slice(0, 300)}`);
      } else {
        alert(`❌ 오류: ${data.error || "응답 없음"}`);
      }
    } catch (e: any) {
      alert(`❌ 연결 실패: ${e.message}`);
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">AI 모델 관리</h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted-foreground)" }}>
            모델별 토큰 단가, 접근 권한, 서빙 상태 관리
          </p>
        </div>
        <button onClick={() => setShowAdd(true)}
          className="px-4 py-2 rounded-lg text-sm font-medium text-white"
          style={{ background: "var(--primary)" }}>
          + 모델 추가
        </button>
      </div>

      {/* 통계 */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold">{models.length}</div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>전체 모델</div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold" style={{ color: "#10b981" }}>
            {models.filter((m) => m.isActive).length}
          </div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>활성 모델</div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold" style={{ color: "#2563eb" }}>
            {vllmModels.length}
          </div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>vLLM 감지</div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="text-2xl font-bold" style={{ color: "#7c3aed" }}>
            {models.filter((m) => m.isDefault).length}
          </div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>기본 모델</div>
        </div>
      </div>

      {/* 모델 편집/추가 모달 */}
      {(editing || showAdd) && (
        <ModelEditor
          model={editing}
          vllmModels={vllmModels}
          onSave={handleSave}
          onCancel={() => { setEditing(null); setShowAdd(false); }}
          saving={saving}
        />
      )}

      {/* 모델 카드 목록 */}
      {loading ? (
        <div className="text-center py-12 text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</div>
      ) : models.length === 0 ? (
        <div className="rounded-xl p-12 text-center border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
          <p className="text-lg mb-2">등록된 AI 모델이 없습니다</p>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>상단 "모델 추가" 버튼으로 등록하세요</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {models.map((model) => {
            const tier = TIER_OPTIONS.find((t) => t.value === model.tier) || TIER_OPTIONS[1];
            const category = CATEGORY_OPTIONS.find((c) => c.value === model.category)?.label || model.category;
            return (
              <div key={model.id} className="rounded-xl border p-5" style={{
                background: "var(--background)",
                borderColor: model.isDefault ? "var(--primary)" : "var(--border)",
                borderWidth: model.isDefault ? 2 : 1,
              }}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold text-lg">{model.displayName}</h3>
                      {model.isDefault && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full text-white font-medium" style={{ background: "var(--primary)" }}>
                          기본
                        </span>
                      )}
                      <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ background: `${tier.color}15`, color: tier.color }}>
                        {tier.label}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: "var(--muted)", color: "var(--muted-foreground)" }}>
                        {category}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full" style={{
                        background: model.status === "ready" ? "#dcfce7" : model.status === "error" ? "#fee2e2" : "#fef3c7",
                        color: model.status === "ready" ? "#166534" : model.status === "error" ? "#991b1b" : "#92400e",
                      }}>
                        {model.status === "ready" ? "🟢 서빙중" : model.status === "error" ? "🔴 오류" : "🟡 " + model.status}
                      </span>
                    </div>
                    <div className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>
                      {model.name} · <code>{model.backendId}</code>
                    </div>
                    {model.description && (
                      <p className="text-sm mt-2" style={{ color: "var(--muted-foreground)" }}>{model.description}</p>
                    )}
                  </div>

                  <div className="flex gap-1">
                    <button onClick={() => handleTestModel(model.backendId)}
                      className="text-xs px-3 py-1.5 rounded-lg border" style={{ borderColor: "var(--border)" }}>
                      🧪 테스트
                    </button>
                    <button onClick={() => setEditing(model)}
                      className="text-xs px-3 py-1.5 rounded-lg border" style={{ borderColor: "var(--border)" }}>
                      수정
                    </button>
                    <button onClick={() => handleDelete(model.id)}
                      className="text-xs px-3 py-1.5 rounded-lg" style={{ color: "var(--destructive)" }}>
                      삭제
                    </button>
                  </div>
                </div>

                {/* 토큰 단가 & 스펙 */}
                <div className="grid grid-cols-5 gap-3 mt-3 pt-3 border-t" style={{ borderColor: "var(--border)" }}>
                  <div>
                    <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>입력 토큰 단가</div>
                    <div className="text-sm font-bold" style={{ color: "#2563eb" }}>×{model.inputMultiplier}</div>
                  </div>
                  <div>
                    <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>출력 토큰 단가</div>
                    <div className="text-sm font-bold" style={{ color: "#7c3aed" }}>×{model.outputMultiplier}</div>
                  </div>
                  <div>
                    <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>컨텍스트</div>
                    <div className="text-sm font-bold">{(model.maxContextLength / 1024).toFixed(0)}K</div>
                  </div>
                  <div>
                    <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>최소 플랜</div>
                    <div className="text-sm font-bold">{model.minPlan || "전체"}</div>
                  </div>
                  <div className="flex items-center gap-2 justify-end">
                    <label className="text-xs flex items-center gap-1 cursor-pointer">
                      <input type="checkbox" checked={model.isActive} onChange={() => handleToggle(model, "isActive")} />
                      활성
                    </label>
                    <label className="text-xs flex items-center gap-1 cursor-pointer">
                      <input type="checkbox" checked={model.isPublic} onChange={() => handleToggle(model, "isPublic")} />
                      공개
                    </label>
                    {!model.isDefault && (
                      <button onClick={() => handleToggle(model, "isDefault")}
                        className="text-xs" style={{ color: "var(--primary)" }}>
                        기본 설정
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* vLLM 감지된 모델 (등록 가이드) */}
      {vllmModels.length > 0 && (
        <div className="mt-6 rounded-xl p-5 border" style={{ borderColor: "var(--border)", background: "var(--muted)" }}>
          <h3 className="font-semibold mb-2 text-sm">🔍 vLLM에서 감지된 모델</h3>
          <p className="text-xs mb-3" style={{ color: "var(--muted-foreground)" }}>
            아래 모델들이 vLLM에서 서빙 중입니다. 등록되지 않은 모델은 "모델 추가" 버튼으로 등록하세요.
          </p>
          <div className="space-y-1">
            {vllmModels.map((vm) => {
              const registered = models.find((m) => m.backendId === vm.id);
              return (
                <div key={vm.id} className="flex items-center justify-between py-1.5 text-xs">
                  <code className="px-2 py-0.5 rounded" style={{ background: "var(--background)" }}>{vm.id}</code>
                  {registered ? (
                    <span style={{ color: "#10b981" }}>✓ {registered.displayName}</span>
                  ) : (
                    <span style={{ color: "#f59e0b" }}>미등록</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// 모델 편집 모달
// ═══════════════════════════════════════════════════════════

function ModelEditor({
  model,
  vllmModels,
  onSave,
  onCancel,
  saving,
}: {
  model: AIModel | null;
  vllmModels: VLLMModel[];
  onSave: (m: Partial<AIModel>) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<Partial<AIModel>>(
    model || {
      name: "",
      displayName: "",
      description: "",
      backendId: "",
      endpoint: "http://localhost:8000",
      inputMultiplier: 1.0,
      outputMultiplier: 1.0,
      maxContextLength: 32768,
      maxOutputTokens: 4096,
      category: "general",
      tier: "standard",
      tags: [],
      minPlan: null,
      isPublic: true,
      isDefault: false,
      isActive: true,
      sortOrder: 0,
    }
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.5)" }}>
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl p-6 border"
        style={{ background: "var(--background)", borderColor: "var(--border)" }}>
        <h2 className="text-lg font-bold mb-4">{model ? "모델 수정" : "모델 추가"}</h2>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium">모델 ID (내부용) *</label>
              <input type="text" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                placeholder="hwarang-v3" />
            </div>
            <div>
              <label className="text-xs font-medium">표시 이름 *</label>
              <input type="text" value={form.displayName || ""} onChange={(e) => setForm({ ...form, displayName: e.target.value })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
                placeholder="Hwarang V3 (최강)" />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium">설명</label>
            <textarea value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}
              rows={2} placeholder="코딩, 복잡한 추론에 최적화된 최강급 모델" />
          </div>

          <div>
            <label className="text-xs font-medium">백엔드 모델 ID * (vLLM 경로)</label>
            <input type="text" value={form.backendId || ""} onChange={(e) => setForm({ ...form, backendId: e.target.value })}
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm font-mono" style={{ borderColor: "var(--border)" }}
              placeholder="/mnt/nvme2/hwarang/models/deepseek-v3" list="vllm-models" />
            <datalist id="vllm-models">
              {vllmModels.map((m) => <option key={m.id} value={m.id} />)}
            </datalist>
            <p className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
              vLLM 서빙 경로. 감지된 모델: {vllmModels.length}개
            </p>
          </div>

          {/* ⭐ 토큰 단가 (가장 중요) */}
          <div className="rounded-lg p-3 border-2" style={{ borderColor: "var(--primary)", background: "var(--accent)" }}>
            <div className="text-xs font-bold mb-2" style={{ color: "var(--primary)" }}>⭐ 토큰 단가 (핵심 설정)</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium">입력 토큰 배수</label>
                <input type="number" step="0.1" min="0.1" max="100"
                  value={form.inputMultiplier} onChange={(e) => setForm({ ...form, inputMultiplier: parseFloat(e.target.value) || 1 })}
                  className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
                <p className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
                  실제 토큰 1개당 화랑 토큰 {form.inputMultiplier}개 차감
                </p>
              </div>
              <div>
                <label className="text-xs font-medium">출력 토큰 배수</label>
                <input type="number" step="0.1" min="0.1" max="100"
                  value={form.outputMultiplier} onChange={(e) => setForm({ ...form, outputMultiplier: parseFloat(e.target.value) || 1 })}
                  className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
                <p className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
                  예: 3.0 → 출력 토큰 1개 = 화랑 토큰 3개 소비
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium">최대 컨텍스트 (토큰)</label>
              <input type="number" value={form.maxContextLength} onChange={(e) => setForm({ ...form, maxContextLength: parseInt(e.target.value) || 32768 })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
            </div>
            <div>
              <label className="text-xs font-medium">최대 출력 (토큰)</label>
              <input type="number" value={form.maxOutputTokens} onChange={(e) => setForm({ ...form, maxOutputTokens: parseInt(e.target.value) || 4096 })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-medium">카테고리</label>
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}>
                {CATEGORY_OPTIONS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium">티어</label>
              <select value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}>
                {TIER_OPTIONS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium">최소 플랜</label>
              <select value={form.minPlan || ""} onChange={(e) => setForm({ ...form, minPlan: e.target.value || null })}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}>
                {PLAN_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </div>
          </div>

          <div className="flex items-center gap-4 pt-2">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.isActive} onChange={(e) => setForm({ ...form, isActive: e.target.checked })} />
              활성 (서빙 가능)
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.isPublic} onChange={(e) => setForm({ ...form, isPublic: e.target.checked })} />
              공개 (유저에게 표시)
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.isDefault} onChange={(e) => setForm({ ...form, isDefault: e.target.checked })} />
              기본 모델
            </label>
          </div>
        </div>

        <div className="flex gap-2 mt-6 justify-end">
          <button onClick={onCancel} className="px-4 py-2 rounded-lg text-sm border" style={{ borderColor: "var(--border)" }}>
            취소
          </button>
          <button onClick={() => onSave(form)} disabled={saving || !form.name || !form.displayName || !form.backendId}
            className="px-4 py-2 rounded-lg text-sm text-white font-medium disabled:opacity-50"
            style={{ background: "var(--primary)" }}>
            {saving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
