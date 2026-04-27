"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 적대적 테스트 (Adversarial Testing)
 * - AdversarialTestCase 시드 / 목록 / 실행 / 회귀 감지
 * - 테이블: 이름 · 카테고리 · 최근 결과 · 최근 실행 · 액션
 * - 카테고리 필터 · 활성 전용 토글
 * - 클릭 시 실행 이력 + 회귀 상세 패널
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

type CaseResult = "passed" | "failed" | "inconclusive" | null;

interface TestCase {
  id: string;
  name: string;
  description?: string;
  category: string;
  injection: Record<string, unknown>;
  expected_detection: string;
  active: boolean;
  last_run_at: string | null;
  last_result: CaseResult;
}

interface HistoryEntry {
  run_at: string;
  result: CaseResult;
  detected?: boolean;
  details?: Record<string, unknown>;
}

interface RegressionInfo {
  regression: boolean;
  consecutive_passed?: number;
  previous_result?: string;
  current_result?: string;
  last_pass_at?: string | null;
  reason?: string;
}

const RESULT_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  passed: { label: "통과", color: "#166534", bg: "#dcfce7" },
  failed: { label: "실패", color: "#991b1b", bg: "#fee2e2" },
  inconclusive: { label: "판정 불가", color: "#854d0e", bg: "#fef9c3" },
  none: { label: "미실행", color: "#64748b", bg: "#f1f5f9" },
};

export default function AdversarialPage() {
  const [items, setItems] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("");
  const [activeOnly, setActiveOnly] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [selected, setSelected] = useState<TestCase | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [regression, setRegression] = useState<RegressionInfo | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (category.trim()) qs.set("category", category.trim());
      qs.set("active_only", activeOnly ? "true" : "false");
      const resp = await adminFetch(`/api/hlkm/adversarial/cases?${qs.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        setItems(Array.isArray(data.cases) ? data.cases : []);
      } else {
        setItems([]);
      }
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [category, activeOnly]);

  useEffect(() => {
    reload();
  }, [reload]);

  const stats = useMemo(() => {
    const total = items.length;
    const passed = items.filter((x) => x.last_result === "passed").length;
    const failed = items.filter((x) => x.last_result === "failed").length;
    const neverRun = items.filter((x) => !x.last_run_at).length;
    return { total, passed, failed, neverRun };
  }, [items]);

  const runSeed = async () => {
    setBusy("seed");
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/adversarial/seed`, { method: "POST" });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `기본 케이스 시드 완료 — 신규 ${data.inserted ?? 0}건 (기본 ${data.default_cases ?? 0})`,
      });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "시드 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runAll = async () => {
    setBusy("run-all");
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/adversarial/run-all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cleanup: true }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `전체 실행 완료 — 통과 ${data.passed ?? 0} / 실패 ${data.failed ?? 0} / 판정불가 ${data.inconclusive ?? 0}`,
      });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "전체 실행 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runOne = async (id: string) => {
    setBusy(`run:${id}`);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/adversarial/cases/${encodeURIComponent(id)}/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cleanup: true }),
        }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      const verdict = data.result || data.verdict || "unknown";
      setMessage({ ok: true, text: `실행 완료 → ${verdict}` });
      reload();
      if (selected && selected.id === id) loadDetail(id);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실행 실패" });
    } finally {
      setBusy(null);
    }
  };

  const deactivate = async (id: string) => {
    if (!confirm("이 테스트 케이스를 비활성화할까요?")) return;
    setBusy(`deact:${id}`);
    try {
      const resp = await adminFetch(
        `/api/hlkm/adversarial/cases/${encodeURIComponent(id)}/deactivate`,
        { method: "POST" }
      );
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${resp.status}`);
      }
      setMessage({ ok: true, text: "비활성화 완료" });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "비활성화 실패" });
    } finally {
      setBusy(null);
    }
  };

  const loadDetail = async (id: string) => {
    setDetailLoading(true);
    try {
      const [histResp, regResp] = await Promise.all([
        adminFetch(`/api/hlkm/adversarial/cases/${encodeURIComponent(id)}/history`),
        adminFetch(`/api/hlkm/adversarial/cases/${encodeURIComponent(id)}/regression`),
      ]);
      if (histResp.ok) {
        const d = await histResp.json();
        setHistory(Array.isArray(d.history) ? d.history : []);
      }
      if (regResp.ok) {
        const d = await regResp.json();
        setRegression(d as RegressionInfo);
      }
    } finally {
      setDetailLoading(false);
    }
  };

  const openDetail = (tc: TestCase) => {
    setSelected(tc);
    setHistory([]);
    setRegression(null);
    loadDetail(tc.id);
  };

  return (
    <div className="space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">적대적 테스트</h1>
          <p className="mt-1 text-sm text-gray-500">
            Adversarial Testing — 복사 스팸, 오역, 편향 주입 등의 공격 시나리오를 주기적으로 검증합니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={runSeed}
            disabled={busy !== null}
            className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb", color: "#374151" }}
          >
            {busy === "seed" ? "시드 중..." : "기본 케이스 시드"}
          </button>
          <button
            onClick={runAll}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy === "run-all" ? "실행 중..." : "전체 실행"}
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
        <StatCard label="총 케이스" value={stats.total} accent="primary" />
        <StatCard label="최근 통과" value={stats.passed} accent="success" />
        <StatCard label="최근 실패" value={stats.failed} accent="danger" />
        <StatCard label="미실행" value={stats.neverRun} accent="warning" />
      </div>

      <div
        className="flex flex-wrap items-center gap-4 rounded-xl border bg-white p-4"
        style={{ borderColor: "#e5e7eb" }}
      >
        <label className="flex items-center gap-2 text-xs text-gray-700">
          <span>카테고리</span>
          <input
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="copy_spam / translation / bias ..."
            className="rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb", minWidth: 200 }}
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-gray-700">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
          />
          활성 전용
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr
                  className="border-b bg-gray-50 text-xs text-gray-600"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  <th className="px-4 py-2 text-left font-medium">이름</th>
                  <th className="px-4 py-2 text-left font-medium">카테고리</th>
                  <th className="px-4 py-2 text-center font-medium">최근 결과</th>
                  <th className="px-4 py-2 text-left font-medium">최근 실행</th>
                  <th className="px-4 py-2 text-right font-medium">액션</th>
                </tr>
              </thead>
              <tbody>
                {!loading && items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">
                      테스트 케이스가 없습니다 — 상단의 &quot;기본 케이스 시드&quot;를 눌러 시작하세요.
                    </td>
                  </tr>
                )}
                {items.map((tc) => {
                  const key = (tc.last_result as string) || "none";
                  const style = RESULT_STYLE[key] || RESULT_STYLE.none;
                  const isSelected = selected?.id === tc.id;
                  return (
                    <tr
                      key={tc.id}
                      className="border-b transition-colors hover:bg-gray-50"
                      style={{
                        borderColor: "#f3f4f6",
                        background: isSelected ? "#eef2ff" : undefined,
                      }}
                      onClick={() => openDetail(tc)}
                    >
                      <td className="cursor-pointer px-4 py-3 font-medium text-gray-900">
                        <div className="truncate" title={tc.description || tc.name}>
                          {tc.name}
                        </div>
                        {!tc.active && (
                          <span className="mt-0.5 inline-block rounded px-1.5 py-0.5 text-[10px]" style={{ color: "#64748b", background: "#e2e8f0" }}>
                            비활성
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                          style={{ color: "#4338ca", background: "#e0e7ff" }}
                        >
                          {tc.category}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span
                          className="inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium"
                          style={{ color: style.color, background: style.bg }}
                        >
                          {style.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-600">
                        {tc.last_run_at
                          ? new Date(tc.last_run_at).toLocaleString("ko-KR")
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              runOne(tc.id);
                            }}
                            disabled={busy !== null}
                            className="rounded-lg border px-2.5 py-1 text-[11px] hover:bg-gray-50 disabled:opacity-60"
                            style={{ borderColor: "#e5e7eb" }}
                          >
                            {busy === `run:${tc.id}` ? "실행..." : "실행"}
                          </button>
                          {tc.active && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                deactivate(tc.id);
                              }}
                              disabled={busy !== null}
                              className="rounded-lg border px-2.5 py-1 text-[11px] text-red-600 hover:bg-red-50 disabled:opacity-60"
                              style={{ borderColor: "#fecaca" }}
                            >
                              비활성
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* 상세 패널 */}
        <div
          className="rounded-xl border bg-white p-4"
          style={{ borderColor: "#e5e7eb", minHeight: 320 }}
        >
          {!selected && (
            <div className="py-20 text-center text-xs text-gray-400">
              테스트 케이스를 선택하면 실행 이력과 회귀 정보가 표시됩니다.
            </div>
          )}
          {selected && (
            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">{selected.name}</h3>
                <p className="mt-1 text-xs text-gray-500">{selected.description || "설명 없음"}</p>
                <div className="mt-2 text-[11px] text-gray-500">
                  expected: <code className="font-mono">{selected.expected_detection}</code>
                </div>
              </div>

              <div>
                <div className="mb-1 text-xs font-semibold text-gray-700">회귀 감지</div>
                {regression ? (
                  <div
                    className="rounded-lg border p-2 text-xs"
                    style={{
                      borderColor: regression.regression ? "#fecaca" : "#bbf7d0",
                      background: regression.regression ? "#fef2f2" : "#f0fdf4",
                      color: regression.regression ? "#991b1b" : "#166534",
                    }}
                  >
                    {regression.regression
                      ? `회귀 발생 — ${regression.previous_result ?? "?"} → ${regression.current_result ?? "?"}`
                      : "회귀 없음 (안정적)"}
                    {regression.reason && (
                      <div className="mt-1 text-[11px]" style={{ color: "#64748b" }}>
                        {regression.reason}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs text-gray-400">—</div>
                )}
              </div>

              <div>
                <div className="mb-1 text-xs font-semibold text-gray-700">
                  실행 이력 {detailLoading ? "(로드 중...)" : ""}
                </div>
                <div className="space-y-1.5">
                  {history.length === 0 && !detailLoading && (
                    <div className="text-xs text-gray-400">이력이 없습니다.</div>
                  )}
                  {history.map((h, i) => {
                    const key = (h.result as string) || "none";
                    const style = RESULT_STYLE[key] || RESULT_STYLE.none;
                    return (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-lg border p-2 text-xs"
                        style={{ borderColor: "#e5e7eb" }}
                      >
                        <div className="text-gray-500">
                          {h.run_at ? new Date(h.run_at).toLocaleString("ko-KR") : "—"}
                        </div>
                        <span
                          className="inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium"
                          style={{ color: style.color, background: style.bg }}
                        >
                          {style.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
