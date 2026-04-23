"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 지식 공백 — 답변 실패 topic 추적 & 채우기
 * - 테이블: topic, 도메인, 실패 횟수, 처음/마지막 감지, 상태, 조치
 * - 조치: 자동 탐색 / 수동 추가 / 무시
 * - 차트: 도메인별 공백 개수
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import DomainBar from "../_components/DomainBar";

interface Gap {
  id: string;
  topic: string;
  domain: string;
  fail_count: number;
  first_seen: string;
  last_seen: string;
  status: "open" | "searching" | "filled" | "ignored";
  sample_query?: string;
}

export default function GapsPage() {
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await adminFetch("/api/hlkm/stats/gaps");
      if (resp.ok) {
        const data = await resp.json();
        const list: Gap[] = Array.isArray(data) ? data : data.items || [];
        setGaps(list);
      } else {
        setGaps([]);
      }
    } catch {
      setGaps([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const filtered = useMemo(
    () => statusFilter === "all" ? gaps : gaps.filter((g) => g.status === statusFilter),
    [gaps, statusFilter]
  );

  const byDomain = useMemo(() => {
    const m = new Map<string, number>();
    for (const g of gaps) m.set(g.domain, (m.get(g.domain) || 0) + 1);
    return Array.from(m.entries())
      .map(([label, value]) => ({ label, value }))
      .sort((a, b) => b.value - a.value);
  }, [gaps]);

  const doAction = async (gap: Gap, action: "search" | "ignore") => {
    setBusy(gap.id + ":" + action);
    setMessage(null);
    try {
      const path =
        action === "search"
          ? `/api/hlkm/admin/gaps/${gap.id}/search`
          : `/api/hlkm/admin/gaps/${gap.id}/ignore`;
      const resp = await fetch(path, { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: action === "search" ? "자동 탐색이 시작되었습니다" : "무시 처리됨" });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "처리 실패" });
    } finally {
      setBusy(null);
    }
  };

  const manualAdd = async (gap: Gap) => {
    const statement = prompt(`"${gap.topic}"에 대한 사실을 입력하세요`);
    if (!statement) return;
    setBusy(gap.id + ":manual");
    try {
      const resp = await adminFetch(`/api/hlkm/admin/gaps/${gap.id}/fill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ statement }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setMessage({ ok: true, text: "수동으로 채워졌습니다" });
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
        <h1 className="text-2xl font-bold text-gray-900">지식 공백</h1>
        <p className="mt-1 text-sm text-gray-500">
          답변에 실패한 주제를 추적합니다. 반복되는 실패는 우선적으로 채워야 합니다.
        </p>
      </header>

      {/* 상단 요약 + 차트 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
          <div className="text-xs text-gray-500">전체 공백</div>
          <div className="mt-2 text-3xl font-bold tabular-nums" style={{ color: "#dc2626" }}>
            {gaps.length.toLocaleString("ko-KR")}
          </div>
          <div className="mt-1 text-xs text-gray-500">미해결 포함</div>
        </div>
        <div className="lg:col-span-2">
          <DomainBar
            title="도메인별 공백 개수"
            items={byDomain}
            orientation="horizontal"
            emptyMessage="아직 감지된 공백이 없습니다"
          />
        </div>
      </div>

      {/* 필터 + 목록 */}
      <div className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="flex items-center gap-2 border-b p-3" style={{ borderColor: "#e5e7eb" }}>
          <span className="text-xs text-gray-600">상태:</span>
          {["all", "open", "searching", "filled", "ignored"].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-lg px-3 py-1 text-xs ${
                statusFilter === s ? "bg-blue-600 text-white" : "text-gray-700 hover:bg-gray-100"
              }`}
            >
              {s === "all" ? "전체" : s === "open" ? "미해결" : s === "searching" ? "탐색 중" : s === "filled" ? "채워짐" : "무시됨"}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-500">
            {loading ? "로딩 중…" : `${filtered.length.toLocaleString("ko-KR")}건`}
          </span>
        </div>

        {message && (
          <div
            className="border-b p-3 text-sm"
            style={{
              borderColor: message.ok ? "#bbf7d0" : "#fecaca",
              background: message.ok ? "#f0fdf4" : "#fef2f2",
              color: message.ok ? "#166534" : "#991b1b",
            }}
          >
            {message.text}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
                <th className="px-4 py-2 text-left font-medium">주제</th>
                <th className="px-4 py-2 text-left font-medium">도메인</th>
                <th className="px-4 py-2 text-right font-medium">실패</th>
                <th className="px-4 py-2 text-left font-medium">처음 감지</th>
                <th className="px-4 py-2 text-left font-medium">마지막 감지</th>
                <th className="px-4 py-2 text-left font-medium">상태</th>
                <th className="px-4 py-2 text-right font-medium">조치</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-gray-400">
                    아직 데이터가 없습니다
                  </td>
                </tr>
              )}
              {filtered.map((g) => (
                <tr key={g.id} className="border-b hover:bg-gray-50" style={{ borderColor: "#f3f4f6" }}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{g.topic}</div>
                    {g.sample_query && (
                      <div className="mt-0.5 line-clamp-1 text-xs text-gray-500">
                        예: {g.sample_query}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700">{g.domain}</span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium text-red-600">
                    {g.fail_count.toLocaleString("ko-KR")}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-600">
                    {new Date(g.first_seen).toLocaleDateString("ko-KR")}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-600">
                    {new Date(g.last_seen).toLocaleDateString("ko-KR")}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={g.status} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <button
                        onClick={() => doAction(g, "search")}
                        disabled={busy !== null || g.status !== "open"}
                        className="rounded-md border px-2 py-1 text-xs hover:bg-blue-50 disabled:opacity-40"
                        style={{ borderColor: "#bfdbfe", color: "#1d4ed8" }}
                        title="자동 탐색 시도"
                      >
                        🔍
                      </button>
                      <button
                        onClick={() => manualAdd(g)}
                        disabled={busy !== null || g.status === "filled"}
                        className="rounded-md border px-2 py-1 text-xs hover:bg-green-50 disabled:opacity-40"
                        style={{ borderColor: "#bbf7d0", color: "#16a34a" }}
                        title="수동 추가"
                      >
                        ✏️
                      </button>
                      <button
                        onClick={() => doAction(g, "ignore")}
                        disabled={busy !== null || g.status === "ignored"}
                        className="rounded-md border px-2 py-1 text-xs hover:bg-gray-100 disabled:opacity-40"
                        style={{ borderColor: "#e5e7eb", color: "#6b7280" }}
                        title="무시"
                      >
                        📦
                      </button>
                    </div>
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

function StatusBadge({ status }: { status: Gap["status"] }) {
  const map = {
    open: { label: "미해결", color: "#dc2626", bg: "#fef2f2" },
    searching: { label: "탐색 중", color: "#2563eb", bg: "#eff6ff" },
    filled: { label: "채워짐", color: "#16a34a", bg: "#f0fdf4" },
    ignored: { label: "무시됨", color: "#64748b", bg: "#f8fafc" },
  };
  const v = map[status];
  return (
    <span
      className="inline-block rounded px-2 py-0.5 text-[11px] font-medium"
      style={{ color: v.color, background: v.bg }}
    >
      {v.label}
    </span>
  );
}
