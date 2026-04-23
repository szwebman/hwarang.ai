"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 출처 신뢰도 관리 (Source Reputation)
 * - 출처별 신뢰도/사실 수/확정·수정·무효 카운트 테이블
 * - 감점(penalize) 액션: 사유 + 크기 입력
 * - 전체 재계산(bulk-update): 최근 N일 데이터 기반
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

type SourceType = "official" | "peer" | "community" | "unknown";
type OrderBy = "reputation" | "totalFacts" | "lastUpdated";

interface SourceRep {
  source: string;
  source_type: SourceType;
  reputation: number;          // 0..1
  total_facts: number;
  confirmed_count: number;
  amended_count: number;
  invalidated_count: number;
  last_updated: string;        // ISO
}

const ORDER_OPTIONS: { key: OrderBy; label: string }[] = [
  { key: "reputation", label: "신뢰도순" },
  { key: "totalFacts", label: "사실 수순" },
  { key: "lastUpdated", label: "최근 업데이트순" },
];

const TYPE_LABEL: Record<SourceType, { label: string; color: string; bg: string }> = {
  official: { label: "공식", color: "#1d4ed8", bg: "#dbeafe" },
  peer: { label: "심사", color: "#7c3aed", bg: "#ede9fe" },
  community: { label: "커뮤니티", color: "#0891b2", bg: "#cffafe" },
  unknown: { label: "미상", color: "#64748b", bg: "#e2e8f0" },
};

export default function ReputationPage() {
  const [items, setItems] = useState<SourceRep[]>([]);
  const [loading, setLoading] = useState(true);
  const [minFacts, setMinFacts] = useState(5);
  const [orderBy, setOrderBy] = useState<OrderBy>("reputation");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [penalizeTarget, setPenalizeTarget] = useState<SourceRep | null>(null);
  const [penalizeReason, setPenalizeReason] = useState("");
  const [penalizeMagnitude, setPenalizeMagnitude] = useState(0.1);

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkDays, setBulkDays] = useState(30);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      qs.set("min_facts", String(minFacts));
      qs.set("order_by", orderBy);
      const resp = await adminFetch(`/api/hlkm/reputation?${qs.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        const list: SourceRep[] = Array.isArray(data) ? data : data.items || [];
        setItems(list);
      } else {
        setItems([]);
      }
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [minFacts, orderBy]);

  useEffect(() => { reload(); }, [reload]);

  const stats = useMemo(() => {
    const total = items.length;
    const avg = total > 0 ? items.reduce((s, x) => s + x.reputation, 0) / total : 0;
    const below = items.filter((x) => x.reputation < 0.5).length;
    const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
    const recent = items.filter((x) => {
      const t = new Date(x.last_updated).getTime();
      return !isNaN(t) && t >= weekAgo;
    }).length;
    return { total, avg, below, recent };
  }, [items]);

  const openPenalize = (src: SourceRep) => {
    setPenalizeTarget(src);
    setPenalizeReason("");
    setPenalizeMagnitude(0.1);
  };

  const submitPenalize = async () => {
    if (!penalizeTarget) return;
    if (!penalizeReason.trim()) {
      setMessage({ ok: false, text: "감점 사유를 입력하세요" });
      return;
    }
    setBusy(penalizeTarget.source);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/reputation/${encodeURIComponent(penalizeTarget.source)}/penalize`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            reason: penalizeReason,
            magnitude: penalizeMagnitude,
          }),
        }
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "감점이 적용되었습니다" });
      setPenalizeTarget(null);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "감점 실패" });
    } finally {
      setBusy(null);
    }
  };

  const submitBulkUpdate = async () => {
    setBusy("bulk");
    setMessage(null);
    try {
      const resp = await adminFetch("/api/hlkm/reputation/bulk-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days: bulkDays }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      const updated = data.updated ?? data.count ?? 0;
      setMessage({ ok: true, text: `재계산 완료 (${updated.toLocaleString("ko-KR")}건 갱신)` });
      setBulkOpen(false);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "재계산 실패" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">출처 신뢰도 관리</h1>
          <p className="mt-1 text-sm text-gray-500">
            Source Reputation — 출처별 누적 확정/수정/무효 이력을 바탕으로 신뢰도를 산출합니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setBulkOpen(true)}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            전체 재계산
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

      {/* 통계 카드 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="총 출처 수" value={stats.total} accent="primary" />
        <StatCard
          label="평균 신뢰도"
          value={`${Math.round(stats.avg * 100)}%`}
          hint="0 ~ 100"
          accent="success"
        />
        <StatCard
          label="신뢰도 0.5 미만"
          value={stats.below}
          accent="danger"
          hint="재검토 권장"
        />
        <StatCard
          label="최근 7일 업데이트"
          value={stats.recent}
          accent="neutral"
        />
      </div>

      {/* 필터 바 */}
      <div
        className="flex flex-wrap items-center gap-4 rounded-xl border bg-white p-4"
        style={{ borderColor: "#e5e7eb" }}
      >
        <label className="flex items-center gap-2">
          <span className="text-xs text-gray-600">최소 사실 수</span>
          <input
            type="number"
            min={0}
            value={minFacts}
            onChange={(e) => setMinFacts(parseInt(e.target.value) || 0)}
            className="w-20 rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb" }}
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-xs text-gray-600">정렬</span>
          <select
            value={orderBy}
            onChange={(e) => setOrderBy(e.target.value as OrderBy)}
            className="rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb" }}
          >
            {ORDER_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </select>
        </label>
        <span className="ml-auto text-xs text-gray-500">
          {loading ? "불러오는 중..." : `${items.length.toLocaleString("ko-KR")}건`}
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
                <th className="px-4 py-2 text-left font-medium">출처</th>
                <th className="px-4 py-2 text-left font-medium">타입</th>
                <th className="px-4 py-2 text-left font-medium">신뢰도</th>
                <th className="px-4 py-2 text-right font-medium">총 사실</th>
                <th className="px-4 py-2 text-right font-medium">확정</th>
                <th className="px-4 py-2 text-right font-medium">수정</th>
                <th className="px-4 py-2 text-right font-medium">무효</th>
                <th className="px-4 py-2 text-left font-medium">최종 업데이트</th>
                <th className="px-4 py-2 text-right font-medium">액션</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && !loading && (
                <tr>
                  <td colSpan={9} className="px-4 py-10 text-center text-sm text-gray-400">
                    아직 데이터가 없습니다
                  </td>
                </tr>
              )}
              {items.map((s) => {
                const t = TYPE_LABEL[s.source_type] || TYPE_LABEL.unknown;
                return (
                  <tr
                    key={s.source}
                    className="border-b transition-colors hover:bg-gray-50"
                    style={{ borderColor: "#f3f4f6" }}
                  >
                    <td className="px-4 py-3">
                      <div className="max-w-[260px] truncate font-medium text-gray-900" title={s.source}>
                        {s.source}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                        style={{ color: t.color, background: t.bg }}
                      >
                        {t.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <ReputationBar score={s.reputation} />
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {s.total_facts.toLocaleString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums" style={{ color: "#16a34a" }}>
                      {s.confirmed_count.toLocaleString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums" style={{ color: "#d97706" }}>
                      {s.amended_count.toLocaleString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums" style={{ color: "#dc2626" }}>
                      {s.invalidated_count.toLocaleString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      {new Date(s.last_updated).toLocaleDateString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => openPenalize(s)}
                        disabled={busy !== null}
                        className="rounded-lg border px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                        style={{ borderColor: "#fecaca" }}
                      >
                        감점
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 감점 모달 */}
      {penalizeTarget && (
        <ModalOverlay onClose={() => setPenalizeTarget(null)}>
          <div className="w-full max-w-md rounded-xl border bg-white p-6" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="text-lg font-bold text-gray-900">출처 감점</h2>
            <p className="mt-1 text-xs text-gray-500">
              <span className="font-medium text-gray-800">{penalizeTarget.source}</span> 의 신뢰도를 수동으로 감점합니다.
            </p>

            <div className="mt-4 space-y-4">
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">사유</label>
                <textarea
                  value={penalizeReason}
                  onChange={(e) => setPenalizeReason(e.target.value)}
                  rows={3}
                  placeholder="예: 반복적인 허위 사실 업로드"
                  className="w-full rounded-lg border p-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">
                  감점 크기 ({penalizeMagnitude.toFixed(2)})
                </label>
                <input
                  type="range"
                  min={0.05}
                  max={0.5}
                  step={0.05}
                  value={penalizeMagnitude}
                  onChange={(e) => setPenalizeMagnitude(parseFloat(e.target.value))}
                  className="w-full"
                />
                <div className="mt-1 flex justify-between text-[10px] text-gray-500">
                  <span>경미 (0.05)</span>
                  <span>심각 (0.50)</span>
                </div>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setPenalizeTarget(null)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={submitPenalize}
                disabled={busy !== null}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                {busy === penalizeTarget.source ? "처리 중..." : "감점 적용"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}

      {/* 전체 재계산 모달 */}
      {bulkOpen && (
        <ModalOverlay onClose={() => setBulkOpen(false)}>
          <div className="w-full max-w-md rounded-xl border bg-white p-6" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="text-lg font-bold text-gray-900">신뢰도 전체 재계산</h2>
            <p className="mt-1 text-xs text-gray-500">
              최근 N일간의 확정/수정/무효 이력을 기반으로 모든 출처의 신뢰도를 다시 계산합니다.
            </p>

            <div className="mt-4">
              <label className="mb-1 block text-xs font-semibold text-gray-700">기간 (일)</label>
              <select
                value={bulkDays}
                onChange={(e) => setBulkDays(parseInt(e.target.value))}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                style={{ borderColor: "#e5e7eb" }}
              >
                <option value={7}>최근 7일</option>
                <option value={30}>최근 30일</option>
                <option value={90}>최근 90일</option>
                <option value={180}>최근 180일</option>
                <option value={365}>최근 1년</option>
              </select>
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setBulkOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={submitBulkUpdate}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "bulk" ? "처리 중..." : "재계산 실행"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function ReputationBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const color = score >= 0.8 ? "#16a34a" : score >= 0.5 ? "#d97706" : "#dc2626";
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 w-32 overflow-hidden rounded-full" style={{ background: "#f1f5f9" }}>
        <div
          className="absolute left-0 top-0 h-full rounded-full"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-xs tabular-nums font-semibold" style={{ color }}>
        {pct.toFixed(0)}%
      </span>
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
