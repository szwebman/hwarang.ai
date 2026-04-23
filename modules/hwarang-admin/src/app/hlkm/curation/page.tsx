"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 큐레이션 — 대기 중 사실 승인/반려
 * - 좌: 대기 사실 목록 (필터 + 일괄 선택)
 * - 우: 선택된 사실 상세 + 승인/반려/수정 버튼
 * - 상단: domain, source_type, quality score range 필터
 * - 일괄 작업: 품질 ≥ 0.8 자동 승인
 */

import { useEffect, useMemo, useState, useCallback } from "react";

interface PendingFact {
  id: string;
  domain: string;
  statement: string;
  source_type: string;
  source_url?: string;
  source_title?: string;
  quality_score: number;
  created_at: string;
  suggested_by?: string;
  context?: string;
  raw?: any;
}

const DOMAINS = ["전체", "law", "tax", "code", "medical", "general"];
const SOURCE_TYPES = ["전체", "official", "news", "user", "agent", "document"];

export default function CurationPage() {
  const [facts, setFacts] = useState<PendingFact[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterDomain, setFilterDomain] = useState("전체");
  const [filterSource, setFilterSource] = useState("전체");
  const [minQuality, setMinQuality] = useState(0);
  const [maxQuality, setMaxQuality] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editedStatement, setEditedStatement] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await adminFetch("/api/hlkm/facts/pending");
      if (resp.ok) {
        const data = await resp.json();
        const list: PendingFact[] = Array.isArray(data) ? data : data.items || [];
        setFacts(list);
        if (list.length > 0 && !selectedId) setSelectedId(list[0].id);
      }
    } catch {
      setFacts([]);
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const filtered = useMemo(
    () =>
      facts.filter((f) => {
        if (filterDomain !== "전체" && f.domain !== filterDomain) return false;
        if (filterSource !== "전체" && f.source_type !== filterSource) return false;
        if (f.quality_score < minQuality || f.quality_score > maxQuality) return false;
        return true;
      }),
    [facts, filterDomain, filterSource, minQuality, maxQuality]
  );

  const selected = facts.find((f) => f.id === selectedId) || null;

  const act = async (id: string, action: "approve" | "reject", body?: any) => {
    setBusy(id + ":" + action);
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/facts/${id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      setFacts((arr) => arr.filter((f) => f.id !== id));
      setMessage({ ok: true, text: action === "approve" ? "승인되었습니다" : "반려되었습니다" });
      setEditMode(false);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "처리 실패" });
    } finally {
      setBusy(null);
    }
  };

  const bulkApproveHighQuality = async () => {
    const targets = filtered.filter((f) => f.quality_score >= 0.8);
    if (targets.length === 0) {
      setMessage({ ok: false, text: "품질 ≥ 0.8 인 사실이 없습니다" });
      return;
    }
    if (!confirm(`품질 ≥ 0.8 인 ${targets.length}건을 일괄 승인합니다. 계속할까요?`)) return;
    setBusy("bulk");
    let okCount = 0;
    for (const f of targets) {
      try {
        const resp = await adminFetch(`/api/hlkm/facts/${f.id}/approve`, { method: "POST" });
        if (resp.ok) okCount++;
      } catch {}
    }
    setBusy(null);
    setMessage({ ok: true, text: `${okCount}/${targets.length} 건 승인 완료` });
    reload();
  };

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">큐레이션</h1>
        <p className="mt-1 text-sm text-gray-500">
          대기 중인 사실을 검토하고 승인·반려합니다. 품질 점수가 높은 사실부터 우선 처리하세요.
        </p>
      </header>

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-white p-4" style={{ borderColor: "#e5e7eb" }}>
        <Select label="도메인" value={filterDomain} onChange={setFilterDomain} options={DOMAINS} />
        <Select label="출처 유형" value={filterSource} onChange={setFilterSource} options={SOURCE_TYPES} />
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-600">품질 범위</span>
          <input
            type="number" step="0.05" min={0} max={1}
            value={minQuality}
            onChange={(e) => setMinQuality(parseFloat(e.target.value) || 0)}
            className="w-20 rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb" }}
          />
          <span className="text-xs">~</span>
          <input
            type="number" step="0.05" min={0} max={1}
            value={maxQuality}
            onChange={(e) => setMaxQuality(parseFloat(e.target.value) || 1)}
            className="w-20 rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb" }}
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-gray-500">
            총 {filtered.length.toLocaleString("ko-KR")}건
          </span>
          <button
            onClick={bulkApproveHighQuality}
            disabled={busy !== null}
            className="rounded-lg border px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-60"
            style={{ borderColor: "#bfdbfe" }}
          >
            품질 ≥ 0.8 일괄 승인
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

      {/* 목록 + 상세 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <aside className="rounded-xl border bg-white lg:col-span-2" style={{ borderColor: "#e5e7eb" }}>
          <div className="border-b px-4 py-3 text-xs font-semibold text-gray-700" style={{ borderColor: "#e5e7eb" }}>
            대기 목록 {loading && <span className="ml-2 text-gray-400">로딩 중…</span>}
          </div>
          <ul className="max-h-[560px] overflow-y-auto">
            {filtered.length === 0 && !loading && (
              <li className="p-6 text-center text-sm text-gray-400">
                아직 대기 중인 사실이 없습니다
              </li>
            )}
            {filtered.map((f) => (
              <li
                key={f.id}
                onClick={() => { setSelectedId(f.id); setEditMode(false); }}
                className={`cursor-pointer border-b px-4 py-3 transition-colors ${
                  selectedId === f.id ? "bg-blue-50" : "hover:bg-gray-50"
                }`}
                style={{ borderColor: "#f3f4f6" }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 text-[11px] text-gray-500">
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 font-medium text-gray-700">
                        {f.domain}
                      </span>
                      <span>{f.source_type}</span>
                      <span>·</span>
                      <span>{new Date(f.created_at).toLocaleDateString("ko-KR")}</span>
                    </div>
                    <div className="mt-1 line-clamp-2 text-sm text-gray-900">
                      {f.statement}
                    </div>
                  </div>
                  <QualityBadge score={f.quality_score} />
                </div>
              </li>
            ))}
          </ul>
        </aside>

        <section className="rounded-xl border bg-white p-5 lg:col-span-3" style={{ borderColor: "#e5e7eb" }}>
          {!selected ? (
            <div className="flex h-full min-h-[400px] items-center justify-center text-sm text-gray-400">
              좌측 목록에서 검토할 사실을 선택하세요
            </div>
          ) : (
            <div className="flex h-full flex-col">
              <div className="mb-3 flex items-center gap-2 text-xs">
                <span className="rounded bg-gray-100 px-2 py-1 font-medium text-gray-700">{selected.domain}</span>
                <span className="rounded bg-gray-100 px-2 py-1 text-gray-700">{selected.source_type}</span>
                <QualityBadge score={selected.quality_score} />
                <span className="ml-auto text-gray-500">
                  제안: {selected.suggested_by || "시스템"} · {new Date(selected.created_at).toLocaleString("ko-KR")}
                </span>
              </div>

              <div className="mb-3">
                <div className="mb-1 text-xs font-semibold text-gray-500">사실 내용</div>
                {editMode ? (
                  <textarea
                    value={editedStatement}
                    onChange={(e) => setEditedStatement(e.target.value)}
                    rows={6}
                    className="w-full rounded-lg border p-3 text-sm"
                    style={{ borderColor: "#e5e7eb" }}
                  />
                ) : (
                  <div className="rounded-lg bg-gray-50 p-4 text-sm text-gray-900 whitespace-pre-wrap">
                    {selected.statement}
                  </div>
                )}
              </div>

              {selected.context && (
                <div className="mb-3">
                  <div className="mb-1 text-xs font-semibold text-gray-500">컨텍스트</div>
                  <div className="rounded-lg bg-gray-50 p-3 text-xs text-gray-700 whitespace-pre-wrap">
                    {selected.context}
                  </div>
                </div>
              )}

              <div className="mb-3">
                <div className="mb-1 text-xs font-semibold text-gray-500">출처</div>
                <div className="rounded-lg bg-gray-50 p-3 text-xs text-gray-700">
                  <div className="font-medium">{selected.source_title || selected.source_type}</div>
                  {selected.source_url && (
                    <a
                      href={selected.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="break-all text-blue-600 hover:underline"
                    >
                      {selected.source_url}
                    </a>
                  )}
                </div>
              </div>

              <div className="mt-auto flex flex-wrap gap-2 border-t pt-4" style={{ borderColor: "#e5e7eb" }}>
                <button
                  onClick={() => act(selected.id, "approve")}
                  disabled={busy !== null}
                  className="flex-1 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
                >
                  ✅ 승인
                </button>
                <button
                  onClick={() => {
                    const reason = prompt("반려 사유를 입력하세요");
                    if (reason === null) return;
                    act(selected.id, "reject", { reason });
                  }}
                  disabled={busy !== null}
                  className="flex-1 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                >
                  ❌ 반려
                </button>
                {editMode ? (
                  <button
                    onClick={() => act(selected.id, "approve", { statement: editedStatement })}
                    disabled={busy !== null}
                    className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
                  >
                    💾 수정 후 승인
                  </button>
                ) : (
                  <button
                    onClick={() => { setEditedStatement(selected.statement); setEditMode(true); }}
                    disabled={busy !== null}
                    className="flex-1 rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
                    style={{ borderColor: "#e5e7eb" }}
                  >
                    🔀 수정
                  </button>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <label className="flex items-center gap-2">
      <span className="text-xs text-gray-600">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border px-2 py-1 text-xs"
        style={{ borderColor: "#e5e7eb" }}
      >
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </label>
  );
}

function QualityBadge({ score }: { score: number }) {
  const s = Math.round(score * 100);
  const color = score >= 0.8 ? "#16a34a" : score >= 0.5 ? "#d97706" : "#dc2626";
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[11px] font-bold tabular-nums"
      style={{ color, background: color + "1a" }}
    >
      Q {s}
    </span>
  );
}
