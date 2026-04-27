"use client";

import { useEffect, useState } from "react";

interface AIModel {
  id: string;
  name: string;
  displayName: string;
  description: string | null;
  backendId: string;
  loraName: string | null;
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
  isDomainDefault: boolean;
  isActive: boolean;
  status: string;
  sortOrder: number;
}

interface RoutingEntry {
  domain: string;
  selected: {
    id: string;
    name: string;
    displayName: string;
    backendId: string;
    loraName: string | null;
    isDomainDefault: boolean;
    status: string;
  } | null;
  candidateCount: number;
  usedFallback: boolean;
}

interface VLLMModel {
  id: string;
  object: string;
  created: number;
  owned_by: string;
}

const CATEGORY_OPTIONS = [
  { value: "general", label: "일반", icon: "💬" },
  { value: "coding", label: "코딩", icon: "💻" },
  { value: "legal", label: "법률", icon: "⚖️" },
  { value: "tax", label: "세무", icon: "💰" },
  { value: "medical", label: "의료", icon: "🏥" },
  { value: "reasoning", label: "추론", icon: "🧠" },
];

const DOMAIN_LABELS: Record<string, { label: string; icon: string; description: string }> = {
  general: { label: "일반 대화", icon: "💬", description: "도메인 매칭 안 되는 모든 질문" },
  coding: { label: "코딩", icon: "💻", description: "프로그래밍 / 코드 작성 질문" },
  legal: { label: "법률", icon: "⚖️", description: "법률 자문, 판례, 민/형사" },
  tax: { label: "세무", icon: "💰", description: "세금, 신고, 회계" },
  medical: { label: "의료", icon: "🏥", description: "의학, 증상, 진단 (참고용)" },
  reasoning: { label: "추론", icon: "🧠", description: "복잡한 논리 문제" },
};

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
  const [endpoints, setEndpoints] = useState<string[]>([]);
  const [routingTable, setRoutingTable] = useState<RoutingEntry[]>([]);
  const [globalDefault, setGlobalDefault] = useState<{ name: string; displayName: string; backendId: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<AIModel | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    fetchModels();
  }, []);

  const fetchModels = async () => {
    setFetchError(null);
    try {
      const [modelsResp, routingResp] = await Promise.all([
        fetch("/api/models", { headers: authHeaders() }),
        fetch("/api/models/routing", { headers: authHeaders() }),
      ]);
      const data = await modelsResp.json().catch(() => ({}));
      if (!modelsResp.ok) {
        const msg =
          modelsResp.status === 401
            ? "인증 만료 — 다시 로그인해 주세요."
            : modelsResp.status === 403
            ? "관리자 권한이 필요합니다."
            : data.error || `요청 실패 (${modelsResp.status})`;
        setFetchError(msg);
      } else {
        setModels(data.models || []);
        setVllmModels(data.vllmModels || []);
        setEndpoints(data.endpoints || []);
      }
      if (routingResp.ok) {
        const r = await routingResp.json();
        setRoutingTable(r.routingTable || []);
        setGlobalDefault(r.globalDefault || null);
      }
    } catch (e: any) {
      setFetchError(`네트워크 오류: ${e?.message || e}`);
    }
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

      {/* 도메인 라우팅 테이블 (이게 핵심) */}
      {!loading && routingTable.length > 0 && (
        <div className="rounded-xl p-5 mb-6 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="font-semibold text-base">🚦 도메인 라우팅</h2>
              <p className="text-xs mt-0.5" style={{ color: "var(--muted-foreground)" }}>
                질문이 어떤 도메인으로 분류되면 어떤 모델/LoRA 가 사용되는지. <strong>category</strong> 필드 + <strong>도메인 기본</strong> 체크박스로 결정됨.
              </p>
            </div>
            {globalDefault && (
              <div className="text-right">
                <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>전역 기본</div>
                <code className="text-xs font-bold">{globalDefault.displayName}</code>
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
            {routingTable.map((entry) => {
              const meta = DOMAIN_LABELS[entry.domain] || { label: entry.domain, icon: "📦", description: "" };
              const isFallback = entry.usedFallback;
              const noModel = !entry.selected;
              return (
                <div
                  key={entry.domain}
                  className="rounded-lg p-3 border"
                  style={{
                    borderColor: noModel ? "#dc2626" : isFallback ? "#fbbf24" : "var(--border)",
                    background: noModel ? "#fee2e2" : isFallback ? "#fef3c7" : "var(--muted)",
                  }}
                >
                  <div className="flex items-start gap-2">
                    <span className="text-lg leading-none">{meta.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold flex items-center gap-1">
                        {meta.label}
                        {isFallback && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded text-white" style={{ background: "#f59e0b" }}>
                            폴백
                          </span>
                        )}
                      </div>
                      <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>{meta.description}</div>
                      {entry.selected ? (
                        <div className="mt-2 space-y-0.5">
                          <div className="text-xs">
                            <span style={{ color: "var(--muted-foreground)" }}>모델: </span>
                            <strong>{entry.selected.displayName}</strong>
                          </div>
                          <div className="text-[10px] font-mono" style={{ color: "var(--muted-foreground)" }}>
                            backend: <code>{entry.selected.backendId}</code>
                          </div>
                          {entry.selected.loraName && (
                            <div className="text-[10px] font-mono" style={{ color: "#7c3aed" }}>
                              LoRA: <code>{entry.selected.loraName}</code>
                            </div>
                          )}
                          <div className="text-[10px]" style={{ color: entry.selected.status === "ready" ? "#10b981" : "#ef4444" }}>
                            {entry.selected.status === "ready" ? "🟢 서빙중" : "🔴 " + entry.selected.status}
                          </div>
                          {isFallback && (
                            <div className="text-[10px] mt-1" style={{ color: "#92400e" }}>
                              {meta.label} 전용 모델 없음 → 전역 기본으로 동작 중
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="mt-2 text-xs" style={{ color: "#991b1b" }}>
                          ⚠ 모델 없음 + 전역 기본도 없음 — 등록 + 기본 체크 필요
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="text-[10px] mt-3 pt-3 border-t" style={{ color: "var(--muted-foreground)", borderColor: "var(--border)" }}>
            💡 카테고리 별로 활성 모델 중 <strong>도메인 기본 → 전역 기본 → 정렬순서</strong> 순으로 1개 자동 선택. 변경 후 60초 내 반영.
          </div>
        </div>
      )}

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

      {/* 에러 배너 */}
      {fetchError && (
        <div className="rounded-xl p-4 mb-4 border-2" style={{ borderColor: "#dc2626", background: "#fee2e2" }}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-medium text-sm" style={{ color: "#991b1b" }}>모델 목록 로드 실패</div>
              <div className="text-xs mt-1" style={{ color: "#7f1d1d" }}>{fetchError}</div>
            </div>
            <button
              onClick={fetchModels}
              className="text-xs px-3 py-1.5 rounded-lg text-white font-medium"
              style={{ background: "#dc2626" }}
            >
              재시도
            </button>
          </div>
        </div>
      )}

      {/* 진단 정보 (vLLM 감지 0개일 때) */}
      {!loading && !fetchError && vllmModels.length === 0 && endpoints.length > 0 && (
        <div className="rounded-xl p-3 mb-4 border" style={{ borderColor: "#f59e0b", background: "#fef3c7" }}>
          <div className="text-sm font-medium" style={{ color: "#92400e" }}>
            ⚠ vLLM 서버에서 모델이 감지되지 않습니다
          </div>
          <div className="text-xs mt-1" style={{ color: "#78350f" }}>
            확인된 endpoint: {endpoints.map((e) => <code key={e} className="mx-1 px-1.5 py-0.5 rounded" style={{ background: "rgba(0,0,0,0.05)" }}>{e}</code>)}
            <br />
            vLLM 이 실제로 실행 중인지, <code>HWARANG_API_URL</code> 환경변수가 올바른지 확인하세요. 모델의 endpoint 필드가 비어있으면 기본 endpoint 가 사용됩니다.
          </div>
        </div>
      )}

      {/* 모델 카드 목록 */}
      {loading ? (
        <div className="text-center py-12 text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</div>
      ) : models.length === 0 ? (
        <div className="rounded-xl p-12 text-center border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
          <p className="text-lg mb-2">등록된 AI 모델이 없습니다</p>
          <p className="text-sm mb-4" style={{ color: "var(--muted-foreground)" }}>상단 "모델 추가" 버튼으로 등록하거나 시드 스크립트를 실행하세요</p>
          <code className="text-xs px-3 py-2 rounded inline-block" style={{ background: "var(--muted)" }}>
            cd modules/hwarang-admin && pnpm seed:models
          </code>
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
                          ⭐⭐ 전역 기본
                        </span>
                      )}
                      {model.isDomainDefault && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full text-white font-medium" style={{ background: "#7c3aed" }}>
                          ⭐ {CATEGORY_OPTIONS.find(c => c.value === model.category)?.label || model.category} 기본
                        </span>
                      )}
                      {model.loraName && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-mono font-medium" style={{ background: "#ddd6fe", color: "#5b21b6" }}>
                          🔌 {model.loraName}
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
      loraName: null,
      endpoint: "http://localhost:8001",
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
      isDomainDefault: false,
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
            <label className="text-xs font-medium">백엔드 모델 ID * (vLLM 베이스 모델)</label>
            <input type="text" value={form.backendId || ""} onChange={(e) => setForm({ ...form, backendId: e.target.value })}
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm font-mono" style={{ borderColor: "var(--border)" }}
              placeholder="hwarang-v5-awq" list="vllm-models" />
            <datalist id="vllm-models">
              {vllmModels.map((m) => <option key={m.id} value={m.id} />)}
            </datalist>
            <p className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
              vLLM 의 `--served-model-name` 값. 감지된 모델: {vllmModels.length}개
            </p>
          </div>

          <div>
            <label className="text-xs font-medium flex items-center gap-1">
              LoRA 이름 <span style={{ color: "var(--muted-foreground)" }}>(선택 — 도메인 특화 시)</span>
            </label>
            <input
              type="text"
              value={form.loraName || ""}
              onChange={(e) => setForm({ ...form, loraName: e.target.value || null })}
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm font-mono"
              style={{ borderColor: "var(--border)" }}
              placeholder="hwarang-code-lora (vLLM --lora-modules 의 별칭)"
            />
            <p className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
              vLLM 시작 시 등록한 LoRA 이름. 비워두면 베이스 모델만 사용. 예: <code>hwarang-code-lora=/path/to/adapter</code> 등록했다면 여기에 <code>hwarang-code-lora</code>
            </p>
          </div>

          <div>
            <label className="text-xs font-medium">vLLM 엔드포인트</label>
            <input
              type="text"
              value={form.endpoint || ""}
              onChange={(e) => setForm({ ...form, endpoint: e.target.value })}
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm font-mono"
              style={{ borderColor: "var(--border)" }}
              placeholder="http://localhost:8001"
            />
            <p className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
              모델이 서빙되는 vLLM 서버 주소. 모델별로 다를 수 있음.
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

          <div className="rounded-lg p-3 border" style={{ borderColor: "var(--border)", background: "var(--muted)" }}>
            <div className="text-xs font-bold mb-2">🚦 라우팅 설정</div>
            <div className="space-y-2">
              <label className="flex items-start gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={form.isActive} onChange={(e) => setForm({ ...form, isActive: e.target.checked })} className="mt-1" />
                <div>
                  <div className="font-medium">활성 (서빙 가능)</div>
                  <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>비활성이면 라우팅 대상에서 제외됨</div>
                </div>
              </label>
              <label className="flex items-start gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={form.isPublic} onChange={(e) => setForm({ ...form, isPublic: e.target.checked })} className="mt-1" />
                <div>
                  <div className="font-medium">공개 (유저에게 표시)</div>
                  <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>유저 모델 선택 메뉴에 노출 여부</div>
                </div>
              </label>
              <label className="flex items-start gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={form.isDomainDefault} onChange={(e) => setForm({ ...form, isDomainDefault: e.target.checked })} className="mt-1" />
                <div>
                  <div className="font-medium">⭐ {CATEGORY_OPTIONS.find(c => c.value === form.category)?.label || "도메인"} 기본</div>
                  <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>같은 카테고리에 여러 모델이 있을 때 이 모델 우선 사용</div>
                </div>
              </label>
              <label className="flex items-start gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={form.isDefault} onChange={(e) => setForm({ ...form, isDefault: e.target.checked })} className="mt-1" />
                <div>
                  <div className="font-medium">⭐⭐ 전역 기본 (가장 중요)</div>
                  <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>도메인 매칭 안 될 때 폴백 — 전체에서 1개만 체크. 도메인 모델 없어도 이게 있으면 항상 동작.</div>
                </div>
              </label>
            </div>
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
