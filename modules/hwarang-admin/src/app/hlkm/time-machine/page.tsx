"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 타임머신 — 스냅샷 (Time Machine)
 * - 스냅샷 생성 / 목록 / 검증 / 비교 / 롤백 / 만료 정리
 * - Timeline Diff (entity + 날짜 구간)
 * - 비교 모드: 두 스냅샷 선택 → 차이점
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface Snapshot {
  id: string;
  name: string;
  snapshot_at: string | null;
  scope: string;
  scope_value: string | null;
  fact_count: number;
  merkle_root?: string;
  size_bytes: number;
  compression?: string;
  created_by?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
}

interface CompareResult {
  added?: Array<{ id: string; content?: string }>;
  removed?: Array<{ id: string; content?: string }>;
  modified?: Array<{ id: string; before_content?: string; after_content?: string }>;
  retracted_since?: Array<{ id: string }>;
}

interface TimelineEvent {
  type: "snapshot" | "audit";
  at: string | null;
  snapshot_id?: string;
  event_type?: string;
  fact_count?: number;
  sample_contents?: string[];
  target_id?: string;
  actor_id?: string;
}

const SCOPE_LABEL: Record<string, string> = {
  full: "전체",
  domain: "도메인",
  entity: "엔티티",
};

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let val = bytes;
  let idx = 0;
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx++;
  }
  return `${val.toFixed(val < 10 ? 1 : 0)} ${units[idx]}`;
}

export default function TimeMachinePage() {
  const [items, setItems] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [scopeFilter, setScopeFilter] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createScope, setCreateScope] = useState<"full" | "domain" | "entity">("full");
  const [createScopeValue, setCreateScopeValue] = useState("");

  const [selectedForCompare, setSelectedForCompare] = useState<string[]>([]);
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null);

  const [rollbackTarget, setRollbackTarget] = useState<Snapshot | null>(null);
  const [rollbackIds, setRollbackIds] = useState("");

  const [verifyResult, setVerifyResult] = useState<{ id: string; data: any } | null>(null);

  const [timelineEntity, setTimelineEntity] = useState("");
  const [timelineStart, setTimelineStart] = useState("");
  const [timelineEnd, setTimelineEnd] = useState("");
  const [timelineEvents, setTimelineEvents] = useState<TimelineEvent[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (scopeFilter) qs.set("scope", scopeFilter);
      const resp = await adminFetch(`/api/hlkm/snapshots?${qs.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        setItems(Array.isArray(data.snapshots) ? data.snapshots : []);
      } else {
        setItems([]);
      }
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [scopeFilter]);

  useEffect(() => {
    reload();
  }, [reload]);

  const stats = useMemo(() => {
    const total = items.length;
    const totalFacts = items.reduce((s, x) => s + (x.fact_count || 0), 0);
    const totalSize = items.reduce((s, x) => s + (x.size_bytes || 0), 0);
    const expired = items.filter(
      (x) => x.expires_at && new Date(x.expires_at).getTime() < Date.now()
    ).length;
    return { total, totalFacts, totalSize, expired };
  }, [items]);

  const runCreate = async () => {
    if (!createName.trim()) {
      setMessage({ ok: false, text: "스냅샷 이름을 입력하세요" });
      return;
    }
    setBusy("create");
    setMessage(null);
    try {
      const body: Record<string, unknown> = {
        name: createName.trim(),
        scope: createScope,
      };
      if (createScope !== "full") body.scope_value = createScopeValue.trim() || null;
      const resp = await adminFetch(`/api/hlkm/snapshots/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: `스냅샷 생성 완료 (${data.id})` });
      setCreateOpen(false);
      setCreateName("");
      setCreateScopeValue("");
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "생성 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runVerify = async (id: string) => {
    setBusy(`verify:${id}`);
    try {
      const resp = await adminFetch(`/api/hlkm/snapshots/${encodeURIComponent(id)}`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setVerifyResult({ id, data });
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "검증 실패" });
    } finally {
      setBusy(null);
    }
  };

  const toggleCompareSelection = (id: string) => {
    setCompareResult(null);
    if (selectedForCompare.includes(id)) {
      setSelectedForCompare(selectedForCompare.filter((x) => x !== id));
    } else if (selectedForCompare.length < 2) {
      setSelectedForCompare([...selectedForCompare, id]);
    } else {
      setSelectedForCompare([selectedForCompare[1], id]);
    }
  };

  const runCompare = async () => {
    if (selectedForCompare.length !== 2) {
      setMessage({ ok: false, text: "두 개의 스냅샷을 선택하세요" });
      return;
    }
    setBusy("compare");
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/snapshots/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          snap_a: selectedForCompare[0],
          snap_b: selectedForCompare[1],
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setCompareResult(data as CompareResult);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "비교 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runRollback = async () => {
    if (!rollbackTarget) return;
    const ids = rollbackIds
      .split(/[\s,\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (ids.length === 0) {
      setMessage({ ok: false, text: "되돌릴 fact_id 를 입력하세요" });
      return;
    }
    if (!confirm(`정말로 ${ids.length}개 사실을 스냅샷 시점으로 되돌릴까요? 백업 스냅샷이 자동 생성됩니다.`)) {
      return;
    }
    setBusy("rollback");
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/snapshots/${encodeURIComponent(rollbackTarget.id)}/rollback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_fact_ids: ids, confirm: true }),
        }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `롤백 완료 — 복원 ${data.restored ?? 0}건, 백업 스냅샷 ${data.backup_snapshot_id || "-"}`,
      });
      setRollbackTarget(null);
      setRollbackIds("");
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "롤백 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runCleanup = async () => {
    if (!confirm("만료된 스냅샷의 파일과 레코드를 삭제합니다. 계속할까요?")) return;
    setBusy("cleanup");
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/snapshots/cleanup-expired`, {
        method: "POST",
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: `만료 ${data.removed ?? 0}건 정리` });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "정리 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runTimeline = async () => {
    if (!timelineEntity.trim() || !timelineStart || !timelineEnd) {
      setMessage({ ok: false, text: "entity/시작/끝을 모두 입력하세요" });
      return;
    }
    setTimelineLoading(true);
    setTimelineEvents([]);
    try {
      const resp = await adminFetch(`/api/hlkm/snapshots/diff-timeline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          entity: timelineEntity.trim(),
          start_date: new Date(timelineStart).toISOString(),
          end_date: new Date(timelineEnd).toISOString(),
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setTimelineEvents(Array.isArray(data.events) ? data.events : []);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "타임라인 조회 실패" });
    } finally {
      setTimelineLoading(false);
    }
  };

  return (
    <div className="space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">타임머신 — 스냅샷</h1>
          <p className="mt-1 text-sm text-gray-500">
            Time Machine — 지식 상태를 시점별로 보존하고, 필요 시 특정 사실들을 과거로 되돌립니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCreateOpen(true)}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            스냅샷 생성
          </button>
          <button
            onClick={runCleanup}
            disabled={busy !== null}
            className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb", color: "#374151" }}
          >
            {busy === "cleanup" ? "정리 중..." : "만료 정리"}
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
        <StatCard label="스냅샷 수" value={stats.total} accent="primary" />
        <StatCard label="총 사실 수" value={stats.totalFacts} accent="neutral" />
        <StatCard label="총 용량" value={formatBytes(stats.totalSize)} accent="success" />
        <StatCard label="만료 대상" value={stats.expired} accent="warning" />
      </div>

      <div
        className="flex flex-wrap items-center gap-3 rounded-xl border bg-white p-3"
        style={{ borderColor: "#e5e7eb" }}
      >
        <label className="flex items-center gap-2 text-xs text-gray-700">
          <span>scope</span>
          <select
            value={scopeFilter}
            onChange={(e) => setScopeFilter(e.target.value)}
            className="rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb" }}
          >
            <option value="">전체</option>
            <option value="full">전체</option>
            <option value="domain">도메인</option>
            <option value="entity">엔티티</option>
          </select>
        </label>
        {selectedForCompare.length > 0 && (
          <div className="flex items-center gap-2 text-xs text-gray-700">
            <span>비교 선택: {selectedForCompare.length}/2</span>
            {selectedForCompare.length === 2 && (
              <button
                onClick={runCompare}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-3 py-1 text-[11px] text-white hover:bg-indigo-700"
              >
                비교 실행
              </button>
            )}
            <button
              onClick={() => {
                setSelectedForCompare([]);
                setCompareResult(null);
              }}
              className="rounded-lg border px-2 py-1 text-[11px] hover:bg-gray-50"
              style={{ borderColor: "#e5e7eb" }}
            >
              초기화
            </button>
          </div>
        )}
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

      {compareResult && (
        <div
          className="rounded-xl border bg-white p-4"
          style={{ borderColor: "#a5b4fc" }}
        >
          <h3 className="mb-3 text-sm font-semibold text-gray-900">스냅샷 비교 결과</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <DiffStat
              label="추가됨"
              count={compareResult.added?.length || 0}
              color="#16a34a"
            />
            <DiffStat
              label="삭제됨"
              count={compareResult.removed?.length || 0}
              color="#dc2626"
            />
            <DiffStat
              label="변경됨"
              count={compareResult.modified?.length || 0}
              color="#d97706"
            />
            <DiffStat
              label="이후 철회"
              count={compareResult.retracted_since?.length || 0}
              color="#7c3aed"
            />
          </div>
          {compareResult.modified && compareResult.modified.length > 0 && (
            <div className="mt-4 space-y-2">
              <div className="text-xs font-semibold text-gray-700">변경된 사실 (최대 10건)</div>
              {compareResult.modified.slice(0, 10).map((m) => (
                <div
                  key={m.id}
                  className="rounded-lg border p-2 text-[11px]"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  <code className="font-mono text-gray-700">{m.id}</code>
                  {m.before_content && (
                    <div className="mt-1 text-gray-500">
                      <span className="text-red-500">- </span>
                      {m.before_content.slice(0, 200)}
                    </div>
                  )}
                  {m.after_content && (
                    <div className="mt-1 text-gray-500">
                      <span className="text-green-600">+ </span>
                      {m.after_content.slice(0, 200)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr
                className="border-b bg-gray-50 text-xs text-gray-600"
                style={{ borderColor: "#e5e7eb" }}
              >
                <th className="px-3 py-2 text-left font-medium">선택</th>
                <th className="px-3 py-2 text-left font-medium">이름</th>
                <th className="px-3 py-2 text-left font-medium">scope</th>
                <th className="px-3 py-2 text-left font-medium">시점</th>
                <th className="px-3 py-2 text-right font-medium">사실 수</th>
                <th className="px-3 py-2 text-right font-medium">용량</th>
                <th className="px-3 py-2 text-left font-medium">만료</th>
                <th className="px-3 py-2 text-right font-medium">액션</th>
              </tr>
            </thead>
            <tbody>
              {!loading && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-sm text-gray-400">
                    스냅샷이 없습니다 — 상단의 &quot;스냅샷 생성&quot;을 눌러 시작하세요.
                  </td>
                </tr>
              )}
              {items.map((s) => {
                const isExpired = s.expires_at && new Date(s.expires_at).getTime() < Date.now();
                const isSelected = selectedForCompare.includes(s.id);
                return (
                  <tr
                    key={s.id}
                    className="border-b transition-colors hover:bg-gray-50"
                    style={{
                      borderColor: "#f3f4f6",
                      background: isSelected ? "#eef2ff" : undefined,
                    }}
                  >
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleCompareSelection(s.id)}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium text-gray-900">{s.name}</div>
                      <div className="mt-0.5 text-[10px] text-gray-500">
                        <code className="font-mono">{s.id}</code>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                        style={{ color: "#4338ca", background: "#e0e7ff" }}
                      >
                        {SCOPE_LABEL[s.scope] || s.scope}
                      </span>
                      {s.scope_value && (
                        <span className="ml-2 text-[10px] text-gray-500">{s.scope_value}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-600">
                      {s.snapshot_at ? new Date(s.snapshot_at).toLocaleString("ko-KR") : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {s.fact_count.toLocaleString("ko-KR")}
                    </td>
                    <td className="px-3 py-2 text-right text-xs text-gray-600">
                      {formatBytes(s.size_bytes)}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {s.expires_at ? (
                        <span style={{ color: isExpired ? "#dc2626" : "#64748b" }}>
                          {new Date(s.expires_at).toLocaleDateString("ko-KR")}
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => runVerify(s.id)}
                          disabled={busy !== null}
                          className="rounded-lg border px-2 py-1 text-[10px] hover:bg-gray-50 disabled:opacity-60"
                          style={{ borderColor: "#e5e7eb" }}
                        >
                          검증
                        </button>
                        <button
                          onClick={() => {
                            setRollbackTarget(s);
                            setRollbackIds("");
                          }}
                          disabled={busy !== null}
                          className="rounded-lg border px-2 py-1 text-[10px] text-orange-600 hover:bg-orange-50 disabled:opacity-60"
                          style={{ borderColor: "#fed7aa" }}
                        >
                          되돌리기
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

      {verifyResult && (
        <div
          className="rounded-xl border bg-white p-4"
          style={{ borderColor: "#e5e7eb" }}
        >
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">스냅샷 검증 결과</h3>
            <button
              onClick={() => setVerifyResult(null)}
              className="text-xs text-gray-500 hover:text-gray-700"
            >
              닫기
            </button>
          </div>
          <div className="text-[10px] text-gray-500 mb-2">
            <code className="font-mono">{verifyResult.id}</code>
          </div>
          <pre
            className="overflow-x-auto rounded-lg p-3 text-[11px] leading-relaxed"
            style={{
              background: "#0f172a",
              color: "#e2e8f0",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              maxHeight: 320,
            }}
          >
            {JSON.stringify(verifyResult.data, null, 2)}
          </pre>
        </div>
      )}

      {/* Timeline Diff 섹션 */}
      <div
        className="rounded-xl border bg-white p-5"
        style={{ borderColor: "#e5e7eb" }}
      >
        <h3 className="mb-3 text-sm font-semibold text-gray-900">타임라인 Diff</h3>
        <p className="mb-3 text-xs text-gray-500">
          특정 entity 가 지정 구간 동안 어떻게 변했는지 스냅샷 + 감사 이벤트 기반으로 조회합니다.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <input
            value={timelineEntity}
            onChange={(e) => setTimelineEntity(e.target.value)}
            placeholder="entity (예: covid-19-vaccine)"
            className="rounded-lg border px-3 py-2 text-sm sm:col-span-2"
            style={{ borderColor: "#e5e7eb" }}
          />
          <input
            type="datetime-local"
            value={timelineStart}
            onChange={(e) => setTimelineStart(e.target.value)}
            className="rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: "#e5e7eb" }}
          />
          <input
            type="datetime-local"
            value={timelineEnd}
            onChange={(e) => setTimelineEnd(e.target.value)}
            className="rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: "#e5e7eb" }}
          />
        </div>
        <div className="mt-3 flex justify-end">
          <button
            onClick={runTimeline}
            disabled={timelineLoading}
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-60"
          >
            {timelineLoading ? "조회 중..." : "타임라인 조회"}
          </button>
        </div>

        {timelineEvents.length > 0 && (
          <div className="mt-4 space-y-2">
            {timelineEvents.map((ev, i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-lg border p-2 text-xs"
                style={{ borderColor: "#e5e7eb" }}
              >
                <span
                  className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{
                    background: ev.type === "snapshot" ? "#4338ca" : "#d97706",
                  }}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className="rounded px-1.5 py-0.5 text-[10px] font-medium"
                      style={{
                        color: ev.type === "snapshot" ? "#4338ca" : "#854d0e",
                        background: ev.type === "snapshot" ? "#e0e7ff" : "#fef9c3",
                      }}
                    >
                      {ev.type === "snapshot" ? "스냅샷" : ev.event_type || "감사"}
                    </span>
                    <span className="text-gray-500">
                      {ev.at ? new Date(ev.at).toLocaleString("ko-KR") : "—"}
                    </span>
                  </div>
                  {ev.type === "snapshot" && (
                    <div className="mt-1 text-[11px] text-gray-600">
                      {ev.fact_count} 건 보관
                      {ev.sample_contents && ev.sample_contents.length > 0 && (
                        <div className="mt-0.5 text-gray-500 line-clamp-2">
                          {ev.sample_contents[0]?.slice(0, 100)}
                        </div>
                      )}
                    </div>
                  )}
                  {ev.type === "audit" && ev.target_id && (
                    <div className="mt-1 text-[11px] text-gray-500">
                      target=<code className="font-mono">{ev.target_id}</code>{" "}
                      actor={ev.actor_id || "—"}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 생성 모달 */}
      {createOpen && (
        <ModalOverlay onClose={() => setCreateOpen(false)}>
          <div
            className="w-full max-w-md rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">스냅샷 생성</h2>
            <div className="mt-4 space-y-3">
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">이름</div>
                <input
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="예: pre_release_v1"
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">scope</div>
                <select
                  value={createScope}
                  onChange={(e) => setCreateScope(e.target.value as any)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  <option value="full">전체 (full)</option>
                  <option value="domain">도메인 (domain)</option>
                  <option value="entity">엔티티 (entity)</option>
                </select>
              </label>
              {createScope !== "full" && (
                <label className="block">
                  <div className="mb-1 text-xs font-semibold text-gray-700">
                    {createScope === "domain" ? "도메인 이름" : "엔티티 키"}
                  </div>
                  <input
                    value={createScopeValue}
                    onChange={(e) => setCreateScopeValue(e.target.value)}
                    placeholder={createScope === "domain" ? "예: law" : "예: covid-19-vaccine"}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    style={{ borderColor: "#e5e7eb" }}
                  />
                </label>
              )}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setCreateOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runCreate}
                disabled={busy !== null || !createName.trim()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "create" ? "생성 중..." : "생성"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}

      {/* 롤백 모달 */}
      {rollbackTarget && (
        <ModalOverlay onClose={() => setRollbackTarget(null)}>
          <div
            className="w-full max-w-lg rounded-xl border bg-white p-6"
            style={{ borderColor: "#fecaca" }}
          >
            <h2 className="text-lg font-bold" style={{ color: "#991b1b" }}>
              ⚠ 스냅샷 되돌리기
            </h2>
            <p className="mt-1 text-xs text-gray-500">
              <span className="font-semibold">{rollbackTarget.name}</span> (
              {rollbackTarget.snapshot_at ? new Date(rollbackTarget.snapshot_at).toLocaleString("ko-KR") : "—"}
              ) 시점으로 지정 사실들을 되돌립니다. 실행 전에 자동으로 백업 스냅샷이 만들어집니다.
            </p>
            <label className="mt-4 block">
              <div className="mb-1 text-xs font-semibold text-gray-700">
                대상 fact_id (줄바꿈 또는 쉼표 구분)
              </div>
              <textarea
                value={rollbackIds}
                onChange={(e) => setRollbackIds(e.target.value)}
                placeholder="ckz1..., ckz2..."
                rows={5}
                className="w-full rounded-lg border px-3 py-2 font-mono text-xs"
                style={{ borderColor: "#e5e7eb" }}
              />
            </label>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setRollbackTarget(null)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runRollback}
                disabled={busy !== null || !rollbackIds.trim()}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                {busy === "rollback" ? "롤백 중..." : "롤백 실행"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function DiffStat({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: string;
}) {
  return (
    <div
      className="rounded-lg border p-3 text-center"
      style={{ borderColor: "#e5e7eb", background: "#f9fafb" }}
    >
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums" style={{ color }}>
        {count.toLocaleString("ko-KR")}
      </div>
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
