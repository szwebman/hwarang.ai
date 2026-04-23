"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 출처 위계 (Source Hierarchy)
 * - 도메인 탭 (all/law/medical/politics/tech/general)
 * - 규칙 목록 테이블 (level, pattern, tier, authority, active)
 * - 추가/수정/비활성 모달 + 기본 위계 시드 버튼
 */

import { useCallback, useEffect, useMemo, useState } from "react";

type DomainKey = "all" | "law" | "medical" | "politics" | "tech" | "general";

interface HierarchyRule {
  id: string;
  domain: string;
  level: number;
  pattern: string;
  tier: string;
  authority: number;
  note?: string | null;
  active: boolean;
}

const DOMAIN_TABS: { key: DomainKey; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "law", label: "법률" },
  { key: "medical", label: "의료" },
  { key: "politics", label: "정치" },
  { key: "tech", label: "기술" },
  { key: "general", label: "일반" },
];

const TIER_OPTIONS = [
  "PRIMARY_OFFICIAL",
  "PEER_REVIEWED",
  "SPECIALIZED_MEDIA",
  "GENERAL_MEDIA",
  "USER_GENERATED",
  "UNKNOWN",
];

const TIER_COLOR: Record<string, { color: string; bg: string; label: string }> = {
  PRIMARY_OFFICIAL: { color: "#1d4ed8", bg: "#dbeafe", label: "1차 공식" },
  PEER_REVIEWED: { color: "#7c3aed", bg: "#ede9fe", label: "심사" },
  SPECIALIZED_MEDIA: { color: "#0891b2", bg: "#cffafe", label: "전문 매체" },
  GENERAL_MEDIA: { color: "#0f766e", bg: "#ccfbf1", label: "일반 매체" },
  USER_GENERATED: { color: "#b45309", bg: "#fef3c7", label: "사용자 제공" },
  UNKNOWN: { color: "#64748b", bg: "#e2e8f0", label: "미상" },
};

interface EditableRule {
  id?: string;
  domain: string;
  level: number;
  pattern: string;
  tier: string;
  authority: number;
  note: string;
  active: boolean;
}

const BLANK_RULE: EditableRule = {
  domain: "general",
  level: 100,
  pattern: "",
  tier: "GENERAL_MEDIA",
  authority: 0.6,
  note: "",
  active: true,
};

export default function HierarchyPage() {
  const [domain, setDomain] = useState<DomainKey>("all");
  const [rules, setRules] = useState<HierarchyRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [editor, setEditor] = useState<EditableRule | null>(null);
  const [editorMode, setEditorMode] = useState<"create" | "update">("create");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (domain !== "all") qs.set("domain", domain);
      const resp = await adminFetch(`/api/hlkm/hierarchy/rules?${qs.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        setRules(Array.isArray(data.rules) ? data.rules : []);
      } else {
        setRules([]);
      }
    } catch {
      setRules([]);
    } finally {
      setLoading(false);
    }
  }, [domain]);

  useEffect(() => {
    reload();
  }, [reload]);

  const stats = useMemo(() => {
    const total = rules.length;
    const byTier: Record<string, number> = {};
    for (const r of rules) byTier[r.tier] = (byTier[r.tier] || 0) + 1;
    const avgAuthority =
      total > 0 ? rules.reduce((s, r) => s + r.authority, 0) / total : 0;
    return { total, byTier, avgAuthority };
  }, [rules]);

  const openCreate = () => {
    setEditor({ ...BLANK_RULE, domain: domain === "all" ? "general" : domain });
    setEditorMode("create");
  };

  const openUpdate = (rule: HierarchyRule) => {
    setEditor({
      id: rule.id,
      domain: rule.domain,
      level: rule.level,
      pattern: rule.pattern,
      tier: rule.tier,
      authority: rule.authority,
      note: rule.note || "",
      active: rule.active,
    });
    setEditorMode("update");
  };

  const submitEditor = async () => {
    if (!editor) return;
    if (!editor.pattern.trim()) {
      setMessage({ ok: false, text: "패턴을 입력하세요" });
      return;
    }
    if (!editor.domain.trim()) {
      setMessage({ ok: false, text: "도메인을 입력하세요" });
      return;
    }
    setBusy(editor.id || "create");
    setMessage(null);
    try {
      const body = {
        domain: editor.domain,
        level: editor.level,
        pattern: editor.pattern,
        tier: editor.tier,
        authority: editor.authority,
        note: editor.note || null,
        ...(editorMode === "update" ? { active: editor.active } : {}),
      };
      const url =
        editorMode === "create"
          ? "/api/hlkm/hierarchy/rules"
          : `/api/hlkm/hierarchy/rules/${editor.id}`;
      const method = editorMode === "create" ? "POST" : "PATCH";
      const resp = await adminFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: editorMode === "create" ? "규칙이 추가되었습니다" : "규칙이 수정되었습니다",
      });
      setEditor(null);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "저장 실패" });
    } finally {
      setBusy(null);
    }
  };

  const deactivate = async (rule: HierarchyRule) => {
    if (!confirm(`"${rule.pattern}" 규칙을 비활성화할까요?`)) return;
    setBusy(rule.id);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/hierarchy/rules/${rule.id}/deactivate`,
        { method: "POST" }
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "규칙이 비활성화되었습니다" });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "비활성화 실패" });
    } finally {
      setBusy(null);
    }
  };

  const seedDefault = async () => {
    if (!confirm("기본 위계 규칙 세트를 시드합니다. 기존 규칙은 유지됩니다. 진행할까요?"))
      return;
    setBusy("seed");
    setMessage(null);
    try {
      const resp = await adminFetch("/api/hlkm/hierarchy/seed", { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      const created = data.created ?? 0;
      setMessage({
        ok: true,
        text: `기본 위계 ${Number(created).toLocaleString("ko-KR")}건이 추가되었습니다`,
      });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "시드 실패" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">출처 위계 (Source Hierarchy)</h1>
          <p className="mt-1 text-sm text-gray-500">
            도메인별 출처 규칙을 관리합니다. 패턴(regex)에 매칭되는 출처는
            지정된 tier/authority 값을 자동으로 부여받습니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={openCreate}
            disabled={busy !== null}
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-60"
          >
            + 규칙 추가
          </button>
          <button
            onClick={seedDefault}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy === "seed" ? "시드 중..." : "기본 위계 시드"}
          </button>
          <button
            onClick={reload}
            disabled={busy !== null}
            className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb" }}
          >
            새로고침
          </button>
        </div>
      </header>

      {/* 도메인 탭 */}
      <div
        className="flex flex-wrap items-center gap-1 rounded-xl border bg-white p-1"
        style={{ borderColor: "#e5e7eb" }}
      >
        {DOMAIN_TABS.map((tab) => {
          const active = tab.key === domain;
          return (
            <button
              key={tab.key}
              onClick={() => setDomain(tab.key)}
              className="rounded-lg px-4 py-2 text-sm font-medium transition-colors"
              style={{
                background: active ? "#eef2ff" : "transparent",
                color: active ? "#4338ca" : "#64748b",
              }}
            >
              {tab.label}
            </button>
          );
        })}
        <span className="ml-auto px-3 text-xs text-gray-500">
          {loading ? "불러오는 중..." : `${stats.total.toLocaleString("ko-KR")}건`}
        </span>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div
          className="rounded-xl border bg-white p-4"
          style={{ borderColor: "#e5e7eb" }}
        >
          <div className="text-xs text-gray-500">활성 규칙 수</div>
          <div className="mt-1 text-2xl font-bold text-gray-900">
            {stats.total.toLocaleString("ko-KR")}
          </div>
        </div>
        <div
          className="rounded-xl border bg-white p-4"
          style={{ borderColor: "#e5e7eb" }}
        >
          <div className="text-xs text-gray-500">평균 authority</div>
          <div className="mt-1 text-2xl font-bold text-gray-900">
            {(stats.avgAuthority * 100).toFixed(0)}%
          </div>
        </div>
        <div
          className="rounded-xl border bg-white p-4"
          style={{ borderColor: "#e5e7eb" }}
        >
          <div className="mb-1 text-xs text-gray-500">tier 분포</div>
          <div className="flex flex-wrap gap-1 pt-1">
            {Object.entries(stats.byTier).map(([tier, n]) => {
              const c = TIER_COLOR[tier] || TIER_COLOR.UNKNOWN;
              return (
                <span
                  key={tier}
                  className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                  style={{ color: c.color, background: c.bg }}
                >
                  {c.label} {n}
                </span>
              );
            })}
            {Object.keys(stats.byTier).length === 0 && (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>
        </div>
      </div>

      {message && (
        <div
          className="rounded-lg border p-3 text-sm"
          style={{
            borderColor: message.ok ? "#bbf7d0" : "#fecaca",
            background: message.ok ? "#f0fdf4" : "#fef2f2",
            color: message.ok ? "#166534" : "#991b1b",
          }}
        >
          {message.text}
        </div>
      )}

      {/* 테이블 */}
      <div
        className="rounded-xl border bg-white"
        style={{ borderColor: "#e5e7eb" }}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr
                className="border-b bg-gray-50 text-xs text-gray-600"
                style={{ borderColor: "#e5e7eb" }}
              >
                <th className="px-4 py-2 text-left font-medium">level</th>
                <th className="px-4 py-2 text-left font-medium">domain</th>
                <th className="px-4 py-2 text-left font-medium">pattern</th>
                <th className="px-4 py-2 text-left font-medium">tier</th>
                <th className="px-4 py-2 text-right font-medium">authority</th>
                <th className="px-4 py-2 text-left font-medium">note</th>
                <th className="px-4 py-2 text-right font-medium">액션</th>
              </tr>
            </thead>
            <tbody>
              {rules.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-gray-400">
                    규칙이 없습니다. 우측 상단 "기본 위계 시드"로 초기화하세요.
                  </td>
                </tr>
              )}
              {rules.map((r) => {
                const tierStyle = TIER_COLOR[r.tier] || TIER_COLOR.UNKNOWN;
                return (
                  <tr
                    key={r.id}
                    className="border-b transition-colors hover:bg-gray-50"
                    style={{ borderColor: "#f3f4f6" }}
                  >
                    <td className="px-4 py-3 text-xs tabular-nums text-gray-600">
                      {r.level}
                    </td>
                    <td className="px-4 py-3 text-xs font-medium text-gray-900">
                      {r.domain}
                    </td>
                    <td className="px-4 py-3">
                      <code
                        className="rounded px-1.5 py-0.5 text-[11px]"
                        style={{ background: "#f3f4f6", color: "#111827" }}
                      >
                        {r.pattern}
                      </code>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                        style={{
                          color: tierStyle.color,
                          background: tierStyle.bg,
                        }}
                      >
                        {tierStyle.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {(r.authority * 100).toFixed(0)}%
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      <span className="line-clamp-1" title={r.note || ""}>
                        {r.note || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => openUpdate(r)}
                          disabled={busy !== null}
                          className="rounded-lg border px-2.5 py-1 text-xs hover:bg-gray-50 disabled:opacity-60"
                          style={{ borderColor: "#e5e7eb" }}
                        >
                          수정
                        </button>
                        <button
                          onClick={() => deactivate(r)}
                          disabled={busy !== null}
                          className="rounded-lg border px-2.5 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-60"
                          style={{ borderColor: "#fecaca" }}
                        >
                          비활성
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 편집 모달 */}
      {editor && (
        <ModalOverlay onClose={() => setEditor(null)}>
          <div
            className="w-full max-w-lg rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">
              {editorMode === "create" ? "위계 규칙 추가" : "위계 규칙 수정"}
            </h2>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <label className="col-span-1">
                <div className="mb-1 text-xs font-semibold text-gray-700">도메인</div>
                <input
                  value={editor.domain}
                  onChange={(e) => setEditor({ ...editor, domain: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                  placeholder="law / medical / ..."
                />
              </label>
              <label className="col-span-1">
                <div className="mb-1 text-xs font-semibold text-gray-700">level (낮을수록 우선)</div>
                <input
                  type="number"
                  value={editor.level}
                  onChange={(e) =>
                    setEditor({ ...editor, level: parseInt(e.target.value) || 0 })
                  }
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="col-span-2">
                <div className="mb-1 text-xs font-semibold text-gray-700">pattern (regex)</div>
                <input
                  value={editor.pattern}
                  onChange={(e) => setEditor({ ...editor, pattern: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 font-mono text-xs"
                  style={{ borderColor: "#e5e7eb" }}
                  placeholder="(?i)law\\.go\\.kr"
                />
              </label>
              <label className="col-span-1">
                <div className="mb-1 text-xs font-semibold text-gray-700">tier</div>
                <select
                  value={editor.tier}
                  onChange={(e) => setEditor({ ...editor, tier: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  {TIER_OPTIONS.map((t) => (
                    <option key={t} value={t}>
                      {TIER_COLOR[t]?.label || t}
                    </option>
                  ))}
                </select>
              </label>
              <label className="col-span-1">
                <div className="mb-1 text-xs font-semibold text-gray-700">
                  authority ({(editor.authority * 100).toFixed(0)}%)
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={editor.authority}
                  onChange={(e) =>
                    setEditor({ ...editor, authority: parseFloat(e.target.value) })
                  }
                  className="w-full"
                />
              </label>
              <label className="col-span-2">
                <div className="mb-1 text-xs font-semibold text-gray-700">note (선택)</div>
                <input
                  value={editor.note}
                  onChange={(e) => setEditor({ ...editor, note: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                  placeholder="예: 법제처 국가법령정보센터"
                />
              </label>
              {editorMode === "update" && (
                <label className="col-span-2 flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={editor.active}
                    onChange={(e) => setEditor({ ...editor, active: e.target.checked })}
                  />
                  <span className="text-xs text-gray-700">활성 상태</span>
                </label>
              )}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setEditor(null)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={submitEditor}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === (editor.id || "create") ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function ModalOverlay({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(15,23,42,0.5)" }}
      onClick={onClose}
    >
      <div onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>
  );
}
