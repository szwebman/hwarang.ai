"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 정정/철회 관리 (Retraction Tracking)
 * - 탭: 대기 중 (pending) / 확인됨 (verified) / 철회된 사실 (retracted)
 * - 액션: 검증(true/false), 되돌리기, 전체 재스캔
 * - 상단 stats: 철회 사실 수, 대기 정정 수, 자동 감지 성공률
 */

import { useCallback, useEffect, useMemo, useState } from "react";

type TabKey = "pending" | "verified" | "retracted";

interface PendingRetraction {
  id: string;
  fact_id: string;
  retracted_by: string;
  retraction_url?: string | null;
  retraction_type: string;
  reason: string;
  detected_at?: string;
  detected_by?: string;
}

interface RetractedFact {
  id: string;
  content: string;
  domain: string;
  source: string;
  retracted_at?: string;
  retraction_reason?: string;
  retraction_source?: string;
}

const TABS: { key: TabKey; label: string }[] = [
  { key: "pending", label: "대기 중" },
  { key: "verified", label: "확인됨" },
  { key: "retracted", label: "철회된 사실" },
];

const TYPE_COLOR: Record<string, { color: string; bg: string; label: string }> = {
  correction: { color: "#b45309", bg: "#fef3c7", label: "정정" },
  retraction: { color: "#991b1b", bg: "#fee2e2", label: "철회" },
  cascade: { color: "#3730a3", bg: "#e0e7ff", label: "cascade" },
  undo: { color: "#166534", bg: "#dcfce7", label: "되돌림" },
  manual: { color: "#6b21a8", bg: "#f3e8ff", label: "수동" },
};

export default function RetractionsPage() {
  const [tab, setTab] = useState<TabKey>("pending");
  const [pending, setPending] = useState<PendingRetraction[]>([]);
  const [retracted, setRetracted] = useState<RetractedFact[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [undoTarget, setUndoTarget] = useState<RetractedFact | null>(null);
  const [undoReason, setUndoReason] = useState("");
  const [domainFilter, setDomainFilter] = useState("");

  const reloadPending = useCallback(async () => {
    const resp = await adminFetch(`/api/hlkm/retraction/pending?limit=200`);
    if (resp.ok) {
      const data = await resp.json();
      setPending(Array.isArray(data.pending) ? data.pending : []);
    } else {
      setPending([]);
    }
  }, []);

  const reloadRetracted = useCallback(async () => {
    const qs = new URLSearchParams();
    if (domainFilter) qs.set("domain", domainFilter);
    qs.set("limit", "200");
    const resp = await adminFetch(`/api/hlkm/retraction/list?${qs.toString()}`);
    if (resp.ok) {
      const data = await resp.json();
      setRetracted(Array.isArray(data.retracted) ? data.retracted : []);
    } else {
      setRetracted([]);
    }
  }, [domainFilter]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([reloadPending(), reloadRetracted()]);
    } finally {
      setLoading(false);
    }
  }, [reloadPending, reloadRetracted]);

  useEffect(() => {
    reload();
  }, [reload]);

  const stats = useMemo(() => {
    const retractedCount = retracted.length;
    const pendingCount = pending.length;
    const autoDetected = pending.filter((p) => p.detected_by === "auto").length;
    const detectionRate =
      pendingCount > 0 ? Math.round((autoDetected / pendingCount) * 100) : 0;
    return { retractedCount, pendingCount, autoDetected, detectionRate };
  }, [pending, retracted]);

  const verify = async (id: string, is_valid: boolean) => {
    setBusy(id);
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/retraction/verify/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_valid }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: is_valid ? "정정이 승인되었습니다" : "정정이 롤백되었습니다",
      });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "검증 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runScanBatch = async () => {
    if (
      !confirm(
        "최근 7일 이상된 CONFIRMED 사실을 대상으로 정정 자동 스캔을 실행합니다. 진행할까요?"
      )
    )
      return;
    setBusy("scan");
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/retraction/scan-batch?batch=100`, {
        method: "POST",
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `스캔 완료: ${data.scanned ?? 0}건 검사 / ${data.detected ?? 0}건 감지 / ${data.cascaded ?? 0}건 cascade`,
      });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "스캔 실패" });
    } finally {
      setBusy(null);
    }
  };

  const openUndo = (rf: RetractedFact) => {
    setUndoTarget(rf);
    setUndoReason("");
  };

  const submitUndo = async () => {
    if (!undoTarget) return;
    if (!undoReason.trim()) {
      setMessage({ ok: false, text: "되돌리기 사유를 입력하세요" });
      return;
    }
    setBusy(undoTarget.id);
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/retraction/undo/${undoTarget.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: undoReason }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "정정이 되돌려졌습니다" });
      setUndoTarget(null);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "되돌리기 실패" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            정정/철회 관리 (Retraction Tracking)
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            자동 감지된 정정 사실을 검증하고, 잘못된 정정은 되돌립니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={runScanBatch}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy === "scan" ? "스캔 중..." : "전체 재스캔 실행"}
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

      {/* 통계 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatBox label="철회된 사실" value={stats.retractedCount} accent="#dc2626" />
        <StatBox
          label="대기 중 정정"
          value={stats.pendingCount}
          accent="#d97706"
        />
        <StatBox
          label="자동 감지 비율"
          value={`${stats.detectionRate}%`}
          accent="#4f46e5"
          hint={`자동 ${stats.autoDetected} / 전체 ${stats.pendingCount}`}
        />
      </div>

      {/* 탭 */}
      <div
        className="flex items-center gap-1 rounded-xl border bg-white p-1"
        style={{ borderColor: "#e5e7eb" }}
      >
        {TABS.map((t) => {
          const active = t.key === tab;
          const n =
            t.key === "pending"
              ? pending.length
              : t.key === "retracted"
                ? retracted.length
                : 0;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
              style={{
                background: active ? "#eef2ff" : "transparent",
                color: active ? "#4338ca" : "#64748b",
              }}
            >
              <span>{t.label}</span>
              <span
                className="rounded-full px-2 text-[10px] font-semibold"
                style={{
                  background: active ? "#c7d2fe" : "#e2e8f0",
                  color: active ? "#3730a3" : "#475569",
                }}
              >
                {n.toLocaleString("ko-KR")}
              </span>
            </button>
          );
        })}
        {tab === "retracted" && (
          <input
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            placeholder="도메인 필터 (예: law)"
            className="ml-auto rounded-lg border px-3 py-1.5 text-xs"
            style={{ borderColor: "#e5e7eb" }}
          />
        )}
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
      {tab === "pending" && (
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
                  <th className="px-4 py-2 text-left font-medium">사실 ID</th>
                  <th className="px-4 py-2 text-left font-medium">type</th>
                  <th className="px-4 py-2 text-left font-medium">사유</th>
                  <th className="px-4 py-2 text-left font-medium">출처</th>
                  <th className="px-4 py-2 text-left font-medium">감지</th>
                  <th className="px-4 py-2 text-right font-medium">액션</th>
                </tr>
              </thead>
              <tbody>
                {pending.length === 0 && !loading && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-10 text-center text-sm text-gray-400"
                    >
                      검증 대기 중인 정정이 없습니다
                    </td>
                  </tr>
                )}
                {pending.map((p) => {
                  const typeStyle = TYPE_COLOR[p.retraction_type] || TYPE_COLOR.correction;
                  return (
                    <tr
                      key={p.id}
                      className="border-b"
                      style={{ borderColor: "#f3f4f6" }}
                    >
                      <td className="px-4 py-3 align-top font-mono text-[11px] text-gray-700">
                        {p.fact_id}
                      </td>
                      <td className="px-4 py-3 align-top">
                        <span
                          className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                          style={{ color: typeStyle.color, background: typeStyle.bg }}
                        >
                          {typeStyle.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 align-top text-xs text-gray-700">
                        <div className="max-w-lg whitespace-pre-wrap">{p.reason}</div>
                      </td>
                      <td className="px-4 py-3 align-top text-xs text-gray-600">
                        {p.retraction_url ? (
                          <a
                            href={p.retraction_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-indigo-600 hover:underline"
                          >
                            {p.retraction_url.slice(0, 40)}…
                          </a>
                        ) : (
                          <span>{p.retracted_by}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 align-top text-[11px] text-gray-500">
                        <div>{p.detected_by || "—"}</div>
                        <div>
                          {p.detected_at
                            ? new Date(p.detected_at).toLocaleString("ko-KR")
                            : ""}
                        </div>
                      </td>
                      <td className="px-4 py-3 align-top text-right">
                        <div className="flex justify-end gap-1">
                          <button
                            onClick={() => verify(p.id, true)}
                            disabled={busy !== null}
                            className="rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
                          >
                            승인
                          </button>
                          <button
                            onClick={() => verify(p.id, false)}
                            disabled={busy !== null}
                            className="rounded-lg border px-2.5 py-1 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                            style={{ borderColor: "#e5e7eb" }}
                          >
                            롤백
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
      )}

      {tab === "verified" && (
        <div
          className="rounded-xl border bg-white p-10 text-center text-sm text-gray-500"
          style={{ borderColor: "#e5e7eb" }}
        >
          확인된 정정은 "철회된 사실" 탭에서 조회할 수 있습니다.
        </div>
      )}

      {tab === "retracted" && (
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
                  <th className="px-4 py-2 text-left font-medium">사실 ID</th>
                  <th className="px-4 py-2 text-left font-medium">내용</th>
                  <th className="px-4 py-2 text-left font-medium">도메인</th>
                  <th className="px-4 py-2 text-left font-medium">출처</th>
                  <th className="px-4 py-2 text-left font-medium">사유</th>
                  <th className="px-4 py-2 text-left font-medium">철회일</th>
                  <th className="px-4 py-2 text-right font-medium">액션</th>
                </tr>
              </thead>
              <tbody>
                {retracted.length === 0 && !loading && (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-10 text-center text-sm text-gray-400"
                    >
                      철회된 사실이 없습니다
                    </td>
                  </tr>
                )}
                {retracted.map((rf) => (
                  <tr
                    key={rf.id}
                    className="border-b"
                    style={{ borderColor: "#f3f4f6" }}
                  >
                    <td className="px-4 py-3 align-top font-mono text-[11px] text-gray-700">
                      {rf.id}
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-gray-900">
                      <div className="max-w-md line-clamp-2">{rf.content}</div>
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-gray-600">
                      {rf.domain}
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-gray-600">
                      {rf.source}
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-gray-700">
                      <div className="max-w-sm line-clamp-2">
                        {rf.retraction_reason || "—"}
                      </div>
                    </td>
                    <td className="px-4 py-3 align-top text-[11px] text-gray-500">
                      {rf.retracted_at
                        ? new Date(rf.retracted_at).toLocaleDateString("ko-KR")
                        : "—"}
                    </td>
                    <td className="px-4 py-3 align-top text-right">
                      <button
                        onClick={() => openUndo(rf)}
                        disabled={busy !== null}
                        className="rounded-lg border px-2.5 py-1 text-xs text-amber-700 hover:bg-amber-50 disabled:opacity-60"
                        style={{ borderColor: "#fde68a" }}
                      >
                        되돌리기
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 되돌리기 모달 */}
      {undoTarget && (
        <ModalOverlay onClose={() => setUndoTarget(null)}>
          <div
            className="w-full max-w-md rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">정정 되돌리기</h2>
            <p className="mt-1 text-xs text-gray-500">
              사실 <span className="font-mono">{undoTarget.id}</span> 의 철회 상태를
              해제하고 CONFIRMED 로 복구합니다.
            </p>
            <div className="mt-4">
              <label className="mb-1 block text-xs font-semibold text-gray-700">
                사유
              </label>
              <textarea
                value={undoReason}
                onChange={(e) => setUndoReason(e.target.value)}
                rows={3}
                placeholder="예: 정정 자체가 오류였음 - 원 기사가 복원됨"
                className="w-full rounded-lg border p-2 text-sm"
                style={{ borderColor: "#e5e7eb" }}
              />
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setUndoTarget(null)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={submitUndo}
                disabled={busy !== null}
                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-60"
              >
                {busy === undoTarget.id ? "처리 중..." : "되돌리기"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function StatBox({
  label,
  value,
  accent,
  hint,
}: {
  label: string;
  value: number | string;
  accent: string;
  hint?: string;
}) {
  return (
    <div
      className="rounded-xl border bg-white p-4"
      style={{ borderColor: "#e5e7eb" }}
    >
      <div className="text-xs text-gray-500">{label}</div>
      <div
        className="mt-1 text-2xl font-bold tabular-nums"
        style={{ color: accent }}
      >
        {typeof value === "number" ? value.toLocaleString("ko-KR") : value}
      </div>
      {hint && <div className="mt-0.5 text-[11px] text-gray-500">{hint}</div>}
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
