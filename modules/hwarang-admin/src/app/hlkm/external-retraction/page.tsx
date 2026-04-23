"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 외부 정정 DB 연동 (External Retraction)
 * - Retraction Watch / Snopes / SNU FactCheck 등 외부 제공자 관리
 * - 제공자 목록 테이블 (동기화 간격/최종 동기화 시각/활성 토글)
 * - 액션: [지금 동기화] / [비활성] / [전체 동기화] / [기본 제공자 시드]
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface Provider {
  provider_name: string;
  base_url: string;
  domain: string;
  active: boolean;
  sync_interval_hours: number;
  last_sync_at: string | null;
}

export default function ExternalRetractionPage() {
  const [items, setItems] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInactive, setShowInactive] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [editTarget, setEditTarget] = useState<Provider | null>(null);
  const [editInterval, setEditInterval] = useState(24);
  const [editDomain, setEditDomain] = useState("general");
  const [editBaseUrl, setEditBaseUrl] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      qs.set("active_only", showInactive ? "false" : "true");
      const resp = await adminFetch(`/api/hlkm/external-retraction/providers?${qs.toString()}`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      setItems(Array.isArray(data.providers) ? data.providers : []);
    } catch (e: any) {
      setItems([]);
      setMessage({ ok: false, text: e?.message || "목록 조회 실패" });
    } finally {
      setLoading(false);
    }
  }, [showInactive]);

  useEffect(() => {
    reload();
  }, [reload]);

  const stats = useMemo(() => {
    const total = items.length;
    const active = items.filter((x) => x.active).length;
    const recent24h = items.filter((x) => {
      if (!x.last_sync_at) return false;
      const t = new Date(x.last_sync_at).getTime();
      return !isNaN(t) && t >= Date.now() - 24 * 60 * 60 * 1000;
    }).length;
    const neverSynced = items.filter((x) => !x.last_sync_at).length;
    return { total, active, recent24h, neverSynced };
  }, [items]);

  const runSeed = async () => {
    setBusy("seed");
    setMessage(null);
    try {
      const resp = await adminFetch("/api/hlkm/external-retraction/providers/seed", {
        method: "POST",
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `기본 제공자 시드 완료 (신규 ${(data.inserted ?? 0).toLocaleString("ko-KR")}건)`,
      });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "시드 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runSyncAll = async () => {
    setBusy("sync-all");
    setMessage(null);
    try {
      const resp = await adminFetch("/api/hlkm/external-retraction/sync-all", {
        method: "POST",
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "전체 동기화 완료" });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "전체 동기화 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runSync = async (name: string) => {
    setBusy(`sync:${name}`);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/external-retraction/sync/${encodeURIComponent(name)}`,
        { method: "POST" }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      const matched = data.matched ?? data.recorded ?? 0;
      setMessage({
        ok: true,
        text: `${name} 동기화 완료 (매칭 ${matched.toLocaleString("ko-KR")}건)`,
      });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || `${name} 동기화 실패` });
    } finally {
      setBusy(null);
    }
  };

  const runDeactivate = async (name: string) => {
    setBusy(`deact:${name}`);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/external-retraction/providers/${encodeURIComponent(name)}/deactivate`,
        { method: "POST" }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: `${name} 비활성 처리 완료` });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "비활성 실패" });
    } finally {
      setBusy(null);
    }
  };

  const openEdit = (p: Provider) => {
    setEditTarget(p);
    setEditInterval(p.sync_interval_hours);
    setEditDomain(p.domain);
    setEditBaseUrl(p.base_url);
  };

  const submitEdit = async () => {
    if (!editTarget) return;
    setBusy(`edit:${editTarget.provider_name}`);
    setMessage(null);
    try {
      const body: Record<string, unknown> = {};
      if (editInterval !== editTarget.sync_interval_hours) body.syncIntervalHours = editInterval;
      if (editDomain !== editTarget.domain) body.domain = editDomain;
      if (editBaseUrl !== editTarget.base_url) body.baseUrl = editBaseUrl;
      if (Object.keys(body).length === 0) {
        setMessage({ ok: false, text: "변경된 필드가 없습니다" });
        setBusy(null);
        return;
      }
      const resp = await adminFetch(
        `/api/hlkm/external-retraction/providers/${encodeURIComponent(
          editTarget.provider_name
        )}/update`,
        { method: "POST", body: JSON.stringify(body) }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "업데이트 완료" });
      setEditTarget(null);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "업데이트 실패" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">외부 정정 DB 연동</h1>
          <p className="mt-1 text-sm text-gray-500">
            Retraction Watch · Snopes · SNU FactCheck 등 외부 팩트체크 제공자 관리.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={runSeed}
            disabled={busy !== null}
            className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb", color: "#374151" }}
          >
            {busy === "seed" ? "시드 중..." : "기본 제공자 시드"}
          </button>
          <button
            onClick={runSyncAll}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy === "sync-all" ? "동기화 중..." : "전체 동기화"}
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
        <StatCard label="총 제공자" value={stats.total} accent="primary" />
        <StatCard label="활성" value={stats.active} accent="success" />
        <StatCard label="최근 24시간 동기화" value={stats.recent24h} accent="neutral" />
        <StatCard label="미동기화" value={stats.neverSynced} accent="warning" />
      </div>

      <div
        className="flex flex-wrap items-center gap-4 rounded-xl border bg-white p-4"
        style={{ borderColor: "#e5e7eb" }}
      >
        <label className="flex items-center gap-2 text-xs text-gray-700">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          비활성 제공자 포함
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

      <div className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr
                className="border-b bg-gray-50 text-xs text-gray-600"
                style={{ borderColor: "#e5e7eb" }}
              >
                <th className="px-4 py-2 text-left font-medium">제공자</th>
                <th className="px-4 py-2 text-left font-medium">도메인</th>
                <th className="px-4 py-2 text-left font-medium">Base URL</th>
                <th className="px-4 py-2 text-right font-medium">동기화 간격(h)</th>
                <th className="px-4 py-2 text-left font-medium">최종 동기화</th>
                <th className="px-4 py-2 text-center font-medium">활성</th>
                <th className="px-4 py-2 text-right font-medium">액션</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-gray-400">
                    아직 데이터가 없습니다 — 상단의 &quot;기본 제공자 시드&quot; 를 눌러 초기화하세요.
                  </td>
                </tr>
              )}
              {items.map((p) => (
                <tr
                  key={p.provider_name}
                  className="border-b transition-colors hover:bg-gray-50"
                  style={{ borderColor: "#f3f4f6" }}
                >
                  <td className="px-4 py-3 font-medium text-gray-900">{p.provider_name}</td>
                  <td className="px-4 py-3">
                    <span
                      className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                      style={{ color: "#1d4ed8", background: "#dbeafe" }}
                    >
                      {p.domain}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="max-w-[280px] truncate text-xs text-gray-600" title={p.base_url}>
                      {p.base_url}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {p.sync_interval_hours.toLocaleString("ko-KR")}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-600">
                    {p.last_sync_at
                      ? new Date(p.last_sync_at).toLocaleString("ko-KR")
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ background: p.active ? "#16a34a" : "#9ca3af" }}
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-1">
                      <button
                        onClick={() => runSync(p.provider_name)}
                        disabled={busy !== null || !p.active}
                        className="rounded-lg border px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-40"
                        style={{ borderColor: "#c7d2fe" }}
                      >
                        {busy === `sync:${p.provider_name}` ? "동기화…" : "지금 동기화"}
                      </button>
                      <button
                        onClick={() => openEdit(p)}
                        disabled={busy !== null}
                        className="rounded-lg border px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                        style={{ borderColor: "#e5e7eb" }}
                      >
                        수정
                      </button>
                      {p.active && (
                        <button
                          onClick={() => runDeactivate(p.provider_name)}
                          disabled={busy !== null}
                          className="rounded-lg border px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-40"
                          style={{ borderColor: "#fecaca" }}
                        >
                          비활성
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {editTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(15,23,42,0.5)" }}
          onClick={() => setEditTarget(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">제공자 수정</h2>
            <p className="mt-1 text-xs text-gray-500">
              <span className="font-medium text-gray-800">{editTarget.provider_name}</span>
            </p>
            <div className="mt-4 space-y-3">
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-gray-700">Base URL</span>
                <input
                  type="text"
                  value={editBaseUrl}
                  onChange={(e) => setEditBaseUrl(e.target.value)}
                  className="w-full rounded-lg border px-2 py-1.5 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-gray-700">도메인</span>
                <input
                  type="text"
                  value={editDomain}
                  onChange={(e) => setEditDomain(e.target.value)}
                  className="w-full rounded-lg border px-2 py-1.5 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-gray-700">
                  동기화 간격 (시간)
                </span>
                <input
                  type="number"
                  min={1}
                  max={720}
                  value={editInterval}
                  onChange={(e) => setEditInterval(parseInt(e.target.value) || 24)}
                  className="w-full rounded-lg border px-2 py-1.5 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setEditTarget(null)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={submitEdit}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                저장
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
