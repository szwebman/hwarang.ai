"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM Sybil 방어
 * - 의심 플래그 목록 (severity 필터)
 * - 클러스터 시각화 (cluster_overview)
 * - 각 플래그: [정지 처리] [오탐 처리] [경고]
 * - 수동 스캔 + 일일 배치 스캔
 */

import { useCallback, useEffect, useState } from "react";
import StatCard from "../_components/StatCard";

interface SybilFlag {
  id: string;
  userId: string;
  type: string;
  severity: "low" | "medium" | "high" | "critical";
  resolved: boolean;
  evidence?: any;
  createdAt: string;
  note?: string | null;
}

interface ClusterRow {
  cluster_id: string;
  user_ids: string[];
  size: number;
  shared_ip?: string | null;
  max_severity?: string;
}

const SEVERITY_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  low: { label: "낮음", color: "#475569", bg: "#e2e8f0" },
  medium: { label: "중간", color: "#92400e", bg: "#fef3c7" },
  high: { label: "높음", color: "#7f1d1d", bg: "#fecaca" },
  critical: { label: "치명", color: "#ffffff", bg: "#b91c1c" },
};

export default function SybilPage() {
  const [flags, setFlags] = useState<SybilFlag[]>([]);
  const [clusters, setClusters] = useState<ClusterRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [severity, setSeverity] = useState<string>("");
  const [resolvedFilter, setResolvedFilter] = useState<string>("unresolved");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [scanUserId, setScanUserId] = useState("");
  const [suspendTarget, setSuspendTarget] = useState<SybilFlag | null>(null);
  const [suspendReason, setSuspendReason] = useState("");
  const [suspendDays, setSuspendDays] = useState<number>(7);

  const loadFlags = useCallback(async () => {
    const qs = new URLSearchParams({ limit: "200" });
    if (severity) qs.set("severity", severity);
    if (resolvedFilter === "unresolved") qs.set("resolved", "false");
    if (resolvedFilter === "resolved") qs.set("resolved", "true");
    const resp = await adminFetch(`/api/knowledge/sybil/flags?${qs}`);
    if (resp.ok) setFlags(await resp.json());
    else setFlags([]);
  }, [severity, resolvedFilter]);

  const loadClusters = useCallback(async () => {
    const resp = await adminFetch("/api/knowledge/sybil/clusters");
    if (resp.ok) setClusters(await resp.json());
    else setClusters([]);
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([loadFlags(), loadClusters()]);
    } finally {
      setLoading(false);
    }
  }, [loadFlags, loadClusters]);

  useEffect(() => {
    reload();
  }, [reload]);

  const runScan = async () => {
    const uid = scanUserId.trim();
    if (!uid) return;
    setBusy("scan");
    try {
      const resp = await adminFetch(`/api/knowledge/sybil/scan/${encodeURIComponent(uid)}`, {
        method: "POST",
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setMessage({ ok: true, text: `스캔 완료 — ${Array.isArray(data) ? data.length : 0}건 플래그` });
      setScanUserId("");
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "스캔 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runDailyScan = async () => {
    setBusy("daily");
    try {
      const resp = await adminFetch("/api/knowledge/sybil/daily-scan", { method: "POST" });
      const data = await resp.json();
      setMessage({ ok: true, text: `일일 스캔 완료: ${JSON.stringify(data)}` });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const resolveFlag = async (flagId: string, resolution: "confirmed" | "false_positive") => {
    setBusy(flagId);
    try {
      const resp = await adminFetch(`/api/knowledge/sybil/flags/${flagId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ resolution }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setMessage({ ok: true, text: "플래그 처리 완료" });
      loadFlags();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const openSuspend = (flag: SybilFlag) => {
    setSuspendTarget(flag);
    setSuspendReason("");
    setSuspendDays(7);
  };

  const submitSuspend = async () => {
    if (!suspendTarget) return;
    setBusy(suspendTarget.userId);
    try {
      const resp = await adminFetch(
        `/api/knowledge/sybil/suspend/${encodeURIComponent(suspendTarget.userId)}`,
        {
          method: "POST",
          body: JSON.stringify({
            reason: suspendReason || "Sybil 의심 자동 대응",
            duration_days: suspendDays,
          }),
        }
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setMessage({ ok: true, text: "계정 정지 완료" });
      setSuspendTarget(null);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const critical = flags.filter((f) => f.severity === "critical").length;
  const high = flags.filter((f) => f.severity === "high").length;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sybil 방어</h1>
          <p className="mt-1 text-sm text-gray-500">
            다중 계정 조작 / IP 클러스터 / 투표 담합 탐지.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={runDailyScan}
            disabled={busy !== null}
            className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb" }}
          >
            일일 배치 스캔
          </button>
          <button
            onClick={reload}
            disabled={loading}
            className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb" }}
          >
            새로고침
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="총 미처리 플래그" value={flags.filter((f) => !f.resolved).length} accent="danger" />
        <StatCard label="치명 등급" value={critical} accent="danger" hint="즉시 검토 필요" />
        <StatCard label="높음 등급" value={high} accent="warning" />
        <StatCard label="탐지된 클러스터" value={clusters.length} accent="neutral" />
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

      {/* 수동 스캔 */}
      <section className="rounded-xl border bg-white p-4" style={{ borderColor: "#e5e7eb" }}>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-900">수동 스캔</span>
          <input
            value={scanUserId}
            onChange={(e) => setScanUserId(e.target.value)}
            placeholder="user_id"
            className="flex-1 rounded-lg border px-3 py-1.5 text-sm"
            style={{ borderColor: "#e5e7eb" }}
          />
          <button
            onClick={runScan}
            disabled={busy !== null || !scanUserId.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy === "scan" ? "..." : "스캔 실행"}
          </button>
        </div>
      </section>

      {/* 필터 */}
      <section className="flex flex-wrap items-center gap-4 rounded-xl border bg-white p-3" style={{ borderColor: "#e5e7eb" }}>
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="rounded-lg border px-2 py-1 text-xs"
          style={{ borderColor: "#e5e7eb" }}
        >
          <option value="">전체 severity</option>
          <option value="low">낮음</option>
          <option value="medium">중간</option>
          <option value="high">높음</option>
          <option value="critical">치명</option>
        </select>
        <select
          value={resolvedFilter}
          onChange={(e) => setResolvedFilter(e.target.value)}
          className="rounded-lg border px-2 py-1 text-xs"
          style={{ borderColor: "#e5e7eb" }}
        >
          <option value="unresolved">미처리</option>
          <option value="resolved">처리됨</option>
          <option value="">전체</option>
        </select>
        <span className="ml-auto text-xs text-gray-500">{flags.length}건</span>
      </section>

      {/* 플래그 테이블 */}
      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
                <th className="px-4 py-2 text-left font-medium">Severity</th>
                <th className="px-4 py-2 text-left font-medium">유형</th>
                <th className="px-4 py-2 text-left font-medium">사용자</th>
                <th className="px-4 py-2 text-left font-medium">생성</th>
                <th className="px-4 py-2 text-right font-medium">액션</th>
              </tr>
            </thead>
            <tbody>
              {flags.length === 0 && !loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">
                    플래그 없음
                  </td>
                </tr>
              )}
              {flags.map((f) => {
                const s = SEVERITY_STYLE[f.severity] || SEVERITY_STYLE.low;
                return (
                  <tr key={f.id} className="border-b hover:bg-gray-50" style={{ borderColor: "#f3f4f6" }}>
                    <td className="px-4 py-3">
                      <span
                        className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                        style={{ color: s.color, background: s.bg }}
                      >
                        {s.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-700">{f.type}</td>
                    <td className="px-4 py-3 text-xs font-mono text-gray-600">{f.userId.slice(0, 14)}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {new Date(f.createdAt).toLocaleString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {!f.resolved && (
                        <div className="flex justify-end gap-1">
                          <button
                            onClick={() => openSuspend(f)}
                            disabled={busy !== null}
                            className="rounded-lg bg-red-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-red-700 disabled:opacity-60"
                          >
                            정지
                          </button>
                          <button
                            onClick={() => resolveFlag(f.id, "false_positive")}
                            disabled={busy !== null}
                            className="rounded-lg border px-2.5 py-1 text-[11px] hover:bg-gray-50 disabled:opacity-60"
                            style={{ borderColor: "#e5e7eb" }}
                          >
                            오탐
                          </button>
                          <button
                            onClick={() => resolveFlag(f.id, "confirmed")}
                            disabled={busy !== null}
                            className="rounded-lg border px-2.5 py-1 text-[11px] text-amber-700 hover:bg-amber-50 disabled:opacity-60"
                            style={{ borderColor: "#fde68a" }}
                          >
                            경고
                          </button>
                        </div>
                      )}
                      {f.resolved && <span className="text-[11px] text-gray-400">처리됨</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* 클러스터 시각화 */}
      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="border-b px-4 py-3" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="font-semibold text-gray-900">탐지된 클러스터</h2>
          <p className="mt-1 text-xs text-gray-500">동일 IP/행동 패턴을 공유하는 계정 군집</p>
        </div>
        <div className="divide-y" style={{ borderColor: "#f3f4f6" }}>
          {clusters.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-gray-400">
              클러스터 없음
            </div>
          )}
          {clusters.map((c) => (
            <article key={c.cluster_id} className="p-4">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-medium text-gray-500">#{c.cluster_id.slice(0, 8)}</span>
                <span
                  className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                  style={{
                    color: "#6d28d9",
                    background: "#ede9fe",
                  }}
                >
                  {c.size}개 계정
                </span>
                {c.shared_ip && (
                  <span className="text-[11px] font-mono text-gray-500">{c.shared_ip}</span>
                )}
                {c.max_severity && (
                  <span
                    className="ml-auto rounded px-1.5 py-0.5 text-[11px] font-medium"
                    style={{
                      color: SEVERITY_STYLE[c.max_severity]?.color || "#475569",
                      background: SEVERITY_STYLE[c.max_severity]?.bg || "#e2e8f0",
                    }}
                  >
                    {SEVERITY_STYLE[c.max_severity]?.label || c.max_severity}
                  </span>
                )}
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {c.user_ids.map((uid) => (
                  <span
                    key={uid}
                    className="rounded bg-gray-100 px-2 py-0.5 text-[11px] font-mono text-gray-700"
                  >
                    {uid.slice(0, 12)}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      {suspendTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(15,23,42,0.5)" }}
          onClick={() => setSuspendTarget(null)}
        >
          <div
            className="w-full max-w-md rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-bold text-gray-900">계정 정지</h2>
            <p className="mt-1 text-xs text-gray-500">
              <span className="font-mono">{suspendTarget.userId}</span> 정지 처리
            </p>
            <div className="mt-4 space-y-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">사유</label>
                <textarea
                  value={suspendReason}
                  onChange={(e) => setSuspendReason(e.target.value)}
                  rows={3}
                  className="w-full rounded-lg border p-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                  placeholder="Sybil 의심 계정..."
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">기간 (일)</label>
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={suspendDays}
                  onChange={(e) => setSuspendDays(parseInt(e.target.value) || 7)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setSuspendTarget(null)}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={submitSuspend}
                disabled={busy !== null}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                정지 처리
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
