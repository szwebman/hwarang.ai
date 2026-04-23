"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 모순 관리 — 충돌하는 사실 쌍 해결
 * - 필터: open / resolved_A / resolved_B / coexist / escalated / all
 * - 카드: Fact A vs Fact B + LLM 모순 설명 + 해결 버튼
 */

import { useCallback, useEffect, useState } from "react";

type ConflictState = "open" | "resolved_A" | "resolved_B" | "coexist" | "escalated" | "all";

interface FactSide {
  id: string;
  statement: string;
  source_title?: string;
  source_url?: string;
  source_type?: string;
  observed_at?: string;
  quality_score?: number;
}

interface Conflict {
  id: string;
  state: ConflictState;
  domain: string;
  fact_a: FactSide;
  fact_b: FactSide;
  explanation?: string;  // LLM 생성 모순 설명
  severity?: "low" | "medium" | "high";
  created_at: string;
  resolved_at?: string;
  resolution?: string;
}

const FILTERS: { key: ConflictState; label: string }[] = [
  { key: "open", label: "미해결" },
  { key: "resolved_A", label: "A 채택" },
  { key: "resolved_B", label: "B 채택" },
  { key: "coexist", label: "공존" },
  { key: "escalated", label: "에스컬레이션" },
  { key: "all", label: "전체" },
];

type Resolution = "A" | "B" | "coexist" | "escalate";

export default function ConflictsPage() {
  const [filter, setFilter] = useState<ConflictState>("open");
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const q = filter === "all" ? "" : `?state=${filter}`;
      const resp = await adminFetch(`/api/hlkm/conflicts${q}`);
      if (resp.ok) {
        const data = await resp.json();
        const list: Conflict[] = Array.isArray(data) ? data : data.items || [];
        setConflicts(list);
      } else {
        setConflicts([]);
      }
    } catch {
      setConflicts([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    reload();
  }, [reload]);

  const resolve = async (id: string, resolution: Resolution) => {
    setBusy(id);
    setMessage(null);
    try {
      let reason: string | null = "";
      if (resolution === "escalate") {
        reason = prompt("에스컬레이션 사유를 입력하세요");
        if (reason === null) {
          setBusy(null);
          return;
        }
      }
      const resp = await adminFetch(`/api/hlkm/conflicts/${id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolution, reason }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "모순이 처리되었습니다" });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "처리 실패" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">모순 관리</h1>
        <p className="mt-1 text-sm text-gray-500">
          서로 충돌하는 사실 쌍을 검토하고 해결합니다. 모호한 경우는 에스컬레이션하세요.
        </p>
      </header>

      {/* 필터 탭 */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-white p-3" style={{ borderColor: "#e5e7eb" }}>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              filter === f.key
                ? "bg-blue-600 text-white"
                : "text-gray-700 hover:bg-gray-100"
            }`}
          >
            {f.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-gray-500">
          {loading ? "로딩 중…" : `${conflicts.length.toLocaleString("ko-KR")}건`}
        </span>
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

      {/* 모순 카드들 */}
      {conflicts.length === 0 && !loading ? (
        <div className="rounded-xl border bg-white p-10 text-center" style={{ borderColor: "#e5e7eb" }}>
          <div className="text-4xl">🎉</div>
          <div className="mt-3 text-sm text-gray-600">
            {filter === "open" ? "미해결 모순이 없습니다" : "해당 상태의 모순이 없습니다"}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {conflicts.map((c) => (
            <ConflictCard
              key={c.id}
              conflict={c}
              onResolve={(r) => resolve(c.id, r)}
              disabled={busy !== null}
              busy={busy === c.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ConflictCard({
  conflict,
  onResolve,
  disabled,
  busy,
}: {
  conflict: Conflict;
  onResolve: (r: Resolution) => void;
  disabled: boolean;
  busy: boolean;
}) {
  const sevColor =
    conflict.severity === "high" ? "#dc2626" :
    conflict.severity === "medium" ? "#d97706" : "#64748b";

  return (
    <article className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
      {/* 헤더 */}
      <header className="mb-4 flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded bg-gray-100 px-2 py-1 font-medium text-gray-700">{conflict.domain}</span>
        <span className="rounded bg-gray-100 px-2 py-1 text-gray-700">{conflict.state}</span>
        {conflict.severity && (
          <span
            className="rounded px-2 py-1 font-medium"
            style={{ color: sevColor, background: sevColor + "1a" }}
          >
            심각도 {conflict.severity}
          </span>
        )}
        <span className="ml-auto text-gray-500">
          감지: {new Date(conflict.created_at).toLocaleString("ko-KR")}
        </span>
      </header>

      {/* 사실 비교 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <FactSideView side="A" fact={conflict.fact_a} />
        <FactSideView side="B" fact={conflict.fact_b} />
      </div>

      {/* LLM 설명 */}
      {conflict.explanation && (
        <div
          className="mt-4 rounded-lg border p-3"
          style={{ borderColor: "#fde68a", background: "#fffbeb" }}
        >
          <div className="mb-1 text-xs font-semibold text-amber-800">⚡ 모순 설명 (LLM)</div>
          <div className="text-sm text-amber-900 whitespace-pre-wrap">{conflict.explanation}</div>
        </div>
      )}

      {/* 해결 버튼 */}
      {conflict.state === "open" ? (
        <div className="mt-4 flex flex-wrap gap-2 border-t pt-4" style={{ borderColor: "#e5e7eb" }}>
          <button
            onClick={() => onResolve("A")}
            disabled={disabled}
            className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            A 채택
          </button>
          <button
            onClick={() => onResolve("B")}
            disabled={disabled}
            className="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            B 채택
          </button>
          <button
            onClick={() => onResolve("coexist")}
            disabled={disabled}
            className="flex-1 rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb" }}
          >
            둘 다 유지
          </button>
          <button
            onClick={() => onResolve("escalate")}
            disabled={disabled}
            className="flex-1 rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-60"
          >
            에스컬레이션
          </button>
          {busy && <span className="text-xs text-gray-500">처리 중…</span>}
        </div>
      ) : (
        <div className="mt-4 rounded-lg bg-gray-50 p-3 text-xs text-gray-600">
          해결됨 · {conflict.resolved_at && new Date(conflict.resolved_at).toLocaleString("ko-KR")}
          {conflict.resolution && <span className="ml-2">· {conflict.resolution}</span>}
        </div>
      )}
    </article>
  );
}

function FactSideView({ side, fact }: { side: "A" | "B"; fact: FactSide }) {
  const border = side === "A" ? "#bfdbfe" : "#c7d2fe";
  const bg = side === "A" ? "#eff6ff" : "#eef2ff";
  const label = side === "A" ? "Fact A" : "Fact B";
  return (
    <div className="rounded-lg border p-4" style={{ borderColor: border, background: bg }}>
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="font-bold" style={{ color: side === "A" ? "#1d4ed8" : "#4338ca" }}>{label}</span>
        {fact.quality_score !== undefined && (
          <span className="tabular-nums text-gray-600">Q {Math.round(fact.quality_score * 100)}</span>
        )}
      </div>
      <div className="text-sm text-gray-900 whitespace-pre-wrap">{fact.statement}</div>
      <div className="mt-3 space-y-0.5 text-[11px] text-gray-600">
        <div>
          출처: <span className="font-medium">{fact.source_title || fact.source_type || "미상"}</span>
        </div>
        {fact.source_url && (
          <div className="truncate">
            <a href={fact.source_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
              {fact.source_url}
            </a>
          </div>
        )}
        {fact.observed_at && (
          <div>시점: {new Date(fact.observed_at).toLocaleString("ko-KR")}</div>
        )}
      </div>
    </div>
  );
}
