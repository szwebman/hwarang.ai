"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 논리 무결성 (Logic Integrity)
 * - LogicalInconsistency 관리
 * - 탭: 미해결 / 해결됨
 * - severity 분포 (high/medium/low)
 * - 액션: 해결안 제안 (LLM) / 해결 기록
 * - 상단: 전체 스캔 실행 (domain + limit 모달)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

type Severity = "high" | "medium" | "low";

interface Inconsistency {
  id: string;
  fact_ids: string[];
  inconsistency_type: string;
  explanation: string;
  severity: Severity | string;
  detection_method?: string;
  resolved: boolean;
  resolution?: string | null;
  detected_at?: string | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
}

const SEVERITY_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  high: { label: "높음", color: "#991b1b", bg: "#fee2e2" },
  medium: { label: "중간", color: "#854d0e", bg: "#fef9c3" },
  low: { label: "낮음", color: "#1e40af", bg: "#dbeafe" },
};

const TYPE_LABEL: Record<string, string> = {
  direct_contradiction: "직접 모순",
  syllogism_violation: "삼단논법 위반",
  quantifier_mismatch: "양화사 충돌",
  transitivity_break: "추이성 단절",
};

type Tab = "open" | "resolved";

export default function LogicPage() {
  const [tab, setTab] = useState<Tab>("open");
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [items, setItems] = useState<Inconsistency[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [resolveTarget, setResolveTarget] = useState<Inconsistency | null>(null);
  const [resolveText, setResolveText] = useState("");
  const [suggestLoading, setSuggestLoading] = useState(false);

  const [scanOpen, setScanOpen] = useState(false);
  const [scanDomain, setScanDomain] = useState("");
  const [scanLimit, setScanLimit] = useState(100);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      qs.set("resolved", tab === "resolved" ? "true" : "false");
      if (severityFilter) qs.set("severity", severityFilter);
      const resp = await adminFetch(`/api/hlkm/logic/inconsistencies?${qs.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        setItems(Array.isArray(data.inconsistencies) ? data.inconsistencies : []);
      } else {
        setItems([]);
      }
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [tab, severityFilter]);

  useEffect(() => {
    reload();
  }, [reload]);

  const stats = useMemo(() => {
    const total = items.length;
    const high = items.filter((x) => x.severity === "high").length;
    const medium = items.filter((x) => x.severity === "medium").length;
    const low = items.filter((x) => x.severity === "low").length;
    return { total, high, medium, low };
  }, [items]);

  const runScan = async () => {
    setBusy("scan");
    setMessage(null);
    try {
      const body: Record<string, unknown> = { limit: scanLimit };
      if (scanDomain.trim()) body.domain = scanDomain.trim();
      const resp = await adminFetch(`/api/hlkm/logic/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `스캔 완료 — entity ${data.entities_scanned ?? 0} / pair ${data.pairs_checked ?? 0} / 발견 ${data.found ?? 0}`,
      });
      setScanOpen(false);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "스캔 실패" });
    } finally {
      setBusy(null);
    }
  };

  const openResolve = async (inc: Inconsistency) => {
    setResolveTarget(inc);
    setResolveText("");
  };

  const loadSuggestion = async () => {
    if (!resolveTarget) return;
    setSuggestLoading(true);
    try {
      const resp = await adminFetch(
        `/api/hlkm/logic/inconsistencies/${encodeURIComponent(resolveTarget.id)}/suggest-resolution`
      );
      if (resp.ok) {
        const data = await resp.json();
        if (data.suggestion) {
          setResolveText(data.suggestion);
        } else {
          setMessage({ ok: false, text: "제안을 가져오지 못했습니다" });
        }
      }
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "제안 로드 실패" });
    } finally {
      setSuggestLoading(false);
    }
  };

  const submitResolve = async () => {
    if (!resolveTarget || !resolveText.trim()) {
      setMessage({ ok: false, text: "해결 내용을 입력하세요" });
      return;
    }
    setBusy(`resolve:${resolveTarget.id}`);
    try {
      const resp = await adminFetch(
        `/api/hlkm/logic/inconsistencies/${encodeURIComponent(resolveTarget.id)}/resolve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ resolution: resolveText }),
        }
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "해결 처리됨" });
      setResolveTarget(null);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "해결 기록 실패" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">논리 무결성</h1>
          <p className="mt-1 text-sm text-gray-500">
            Logic Integrity — 직접 모순, 삼단논법 위반, 양화사 충돌, 추이성 단절을 자동 감지합니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setScanOpen(true)}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            전체 스캔
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

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={tab === "open" ? "미해결 전체" : "해결 전체"}
          value={stats.total}
          accent={tab === "open" ? "warning" : "success"}
        />
        <StatCard label="심각도: 높음" value={stats.high} accent="danger" />
        <StatCard label="심각도: 중간" value={stats.medium} accent="warning" />
        <StatCard label="심각도: 낮음" value={stats.low} accent="primary" />
      </div>

      <div
        className="flex flex-wrap items-center gap-3 rounded-xl border bg-white p-3"
        style={{ borderColor: "#e5e7eb" }}
      >
        <div className="flex overflow-hidden rounded-lg border" style={{ borderColor: "#e5e7eb" }}>
          <button
            onClick={() => setTab("open")}
            className="px-4 py-1.5 text-sm"
            style={{
              background: tab === "open" ? "#4338ca" : "#ffffff",
              color: tab === "open" ? "#ffffff" : "#374151",
            }}
          >
            미해결
          </button>
          <button
            onClick={() => setTab("resolved")}
            className="px-4 py-1.5 text-sm"
            style={{
              background: tab === "resolved" ? "#16a34a" : "#ffffff",
              color: tab === "resolved" ? "#ffffff" : "#374151",
            }}
          >
            해결됨
          </button>
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-700">
          <span>심각도</span>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb" }}
          >
            <option value="">전체</option>
            <option value="high">높음</option>
            <option value="medium">중간</option>
            <option value="low">낮음</option>
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

      <div className="space-y-3">
        {!loading && items.length === 0 && (
          <div
            className="rounded-xl border bg-white p-10 text-center text-sm text-gray-400"
            style={{ borderColor: "#e5e7eb" }}
          >
            {tab === "open" ? "미해결 논리 불일치가 없습니다." : "해결된 불일치가 없습니다."}
          </div>
        )}
        {items.map((inc) => {
          const sev = SEVERITY_STYLE[inc.severity as string] || SEVERITY_STYLE.medium;
          return (
            <div
              key={inc.id}
              className="rounded-xl border bg-white p-4"
              style={{ borderColor: "#e5e7eb" }}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span
                      className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                      style={{ color: sev.color, background: sev.bg }}
                    >
                      {sev.label}
                    </span>
                    <span
                      className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                      style={{ color: "#4338ca", background: "#e0e7ff" }}
                    >
                      {TYPE_LABEL[inc.inconsistency_type] || inc.inconsistency_type}
                    </span>
                    {inc.detection_method && (
                      <span className="text-[11px] text-gray-500">
                        ({inc.detection_method})
                      </span>
                    )}
                    <span className="ml-2 text-[11px] text-gray-500">
                      {inc.detected_at ? new Date(inc.detected_at).toLocaleString("ko-KR") : "—"}
                    </span>
                  </div>
                  <div className="text-sm text-gray-900">{inc.explanation}</div>
                  {inc.fact_ids && inc.fact_ids.length > 0 && (
                    <div className="mt-2 text-[11px] text-gray-500">
                      <span className="text-gray-400">연관 사실:</span>{" "}
                      {inc.fact_ids.map((fid, i) => (
                        <span key={fid}>
                          <code className="font-mono text-gray-700">{fid}</code>
                          {i < inc.fact_ids.length - 1 ? ", " : ""}
                        </span>
                      ))}
                    </div>
                  )}
                  {inc.resolved && inc.resolution && (
                    <div
                      className="mt-2 rounded-lg border p-2 text-[12px]"
                      style={{ borderColor: "#bbf7d0", background: "#f0fdf4", color: "#166534" }}
                    >
                      <span className="font-semibold">해결: </span>
                      {inc.resolution}
                      <div className="mt-1 text-[10px] text-gray-500">
                        {inc.resolved_at ? new Date(inc.resolved_at).toLocaleString("ko-KR") : ""}
                        {inc.resolved_by ? ` · ${inc.resolved_by}` : ""}
                      </div>
                    </div>
                  )}
                </div>
                {!inc.resolved && (
                  <button
                    onClick={() => openResolve(inc)}
                    disabled={busy !== null}
                    className="shrink-0 rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
                    style={{ borderColor: "#e5e7eb" }}
                  >
                    해결 기록
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 해결 모달 */}
      {resolveTarget && (
        <ModalOverlay onClose={() => setResolveTarget(null)}>
          <div
            className="w-full max-w-xl rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">논리 불일치 해결</h2>
            <p className="mt-1 text-xs text-gray-500">
              {TYPE_LABEL[resolveTarget.inconsistency_type] || resolveTarget.inconsistency_type} · {resolveTarget.severity}
            </p>
            <div className="mt-3 rounded-lg border p-3 text-[12px]" style={{ borderColor: "#e5e7eb", background: "#f9fafb" }}>
              {resolveTarget.explanation}
            </div>
            <label className="mt-4 block">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-700">해결 내용</span>
                <button
                  onClick={loadSuggestion}
                  disabled={suggestLoading}
                  className="rounded-lg border px-2 py-1 text-[11px] hover:bg-gray-50 disabled:opacity-60"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  {suggestLoading ? "생성 중..." : "LLM 제안 불러오기"}
                </button>
              </div>
              <textarea
                value={resolveText}
                onChange={(e) => setResolveText(e.target.value)}
                placeholder="예: 사실 A는 도메인 변경으로 더 이상 유효하지 않음."
                rows={5}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                style={{ borderColor: "#e5e7eb" }}
              />
            </label>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setResolveTarget(null)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={submitResolve}
                disabled={busy !== null || !resolveText.trim()}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
              >
                {busy?.startsWith("resolve:") ? "처리 중..." : "해결 기록"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}

      {/* 스캔 모달 */}
      {scanOpen && (
        <ModalOverlay onClose={() => setScanOpen(false)}>
          <div
            className="w-full max-w-md rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">전체 일관성 스캔</h2>
            <p className="mt-1 text-xs text-gray-500">
              entity 단위로 묶어 pairwise 모순 검사를 수행합니다. 도메인 필터로 범위를 좁힐 수 있습니다.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">
                  도메인 (비워두면 전체)
                </div>
                <input
                  value={scanDomain}
                  onChange={(e) => setScanDomain(e.target.value)}
                  placeholder="law / medical / news ..."
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">사실 수 상한</div>
                <input
                  type="number"
                  value={scanLimit}
                  onChange={(e) =>
                    setScanLimit(Math.max(1, parseInt(e.target.value) || 100))
                  }
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                  min={1}
                  max={2000}
                />
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setScanOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runScan}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "scan" ? "스캔 중..." : "스캔 실행"}
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
