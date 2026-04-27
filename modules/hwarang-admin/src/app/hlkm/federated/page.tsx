"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 연합 팩트체크 (Federated Fact Check)
 * - 등록된 HLKM 인스턴스 목록
 * - 액션: 추가, 핸드셰이크, 교차 검증, 발산 탐지, 연합 합의 집계
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface Instance {
  instance_id: string;
  name: string;
  api_url: string;
  organization?: string | null;
  trust_level: number;
  active: boolean;
  last_handshake_at: string | null;
  syncs_completed: number;
}

interface CrossVerifyResult {
  verified?: boolean;
  error?: string;
  available?: number;
  required?: number;
  agreement_avg?: number;
  confirming?: Array<{ instance_id: string; name?: string; agreement: number; trust_level?: number }>;
  dissenting?: Array<{ instance_id: string; name?: string; agreement: number; trust_level?: number }>;
}

interface DivergentRow {
  instance_id: string;
  name?: string;
  agreement: number;
  verdict?: string;
  flagged_for_review?: boolean;
}

export default function FederatedPage() {
  const [items, setItems] = useState<Instance[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeOnly, setActiveOnly] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  // 추가 모달
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({
    instance_id: "",
    name: "",
    api_url: "",
    public_key: "",
    organization: "",
    trust_level: 0.5,
  });

  // 교차 검증
  const [crossFactId, setCrossFactId] = useState("");
  const [crossMin, setCrossMin] = useState(2);
  const [crossResult, setCrossResult] = useState<CrossVerifyResult | null>(null);
  const [crossLoading, setCrossLoading] = useState(false);

  // 발산
  const [divergentFactId, setDivergentFactId] = useState("");
  const [divergent, setDivergent] = useState<DivergentRow[]>([]);
  const [divergentLoading, setDivergentLoading] = useState(false);

  // 합의
  const [aggregateEntity, setAggregateEntity] = useState("");
  const [aggregate, setAggregate] = useState<any | null>(null);
  const [aggregateLoading, setAggregateLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      qs.set("active_only", activeOnly ? "true" : "false");
      const resp = await adminFetch(`/api/hlkm/federated/instances?${qs.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        setItems(Array.isArray(data.instances) ? data.instances : []);
      } else {
        setItems([]);
      }
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [activeOnly]);

  useEffect(() => {
    reload();
  }, [reload]);

  const stats = useMemo(() => {
    const total = items.length;
    const active = items.filter((x) => x.active).length;
    const avgTrust =
      total > 0 ? items.reduce((s, x) => s + (x.trust_level || 0), 0) / total : 0;
    const handshakedRecently = items.filter((x) => {
      if (!x.last_handshake_at) return false;
      const t = new Date(x.last_handshake_at).getTime();
      return !isNaN(t) && t >= Date.now() - 24 * 60 * 60 * 1000;
    }).length;
    return { total, active, avgTrust, handshakedRecently };
  }, [items]);

  const runAdd = async () => {
    if (!form.instance_id.trim() || !form.api_url.trim() || !form.public_key.trim()) {
      setMessage({ ok: false, text: "instance_id, api_url, public_key 는 필수입니다" });
      return;
    }
    setBusy("add");
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/federated/instances`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instance_id: form.instance_id.trim(),
          name: form.name.trim() || form.instance_id.trim(),
          api_url: form.api_url.trim(),
          public_key: form.public_key.trim(),
          organization: form.organization.trim() || null,
          trust_level: form.trust_level,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: `인스턴스 등록 완료 (${data.instance_id})` });
      setAddOpen(false);
      setForm({
        instance_id: "",
        name: "",
        api_url: "",
        public_key: "",
        organization: "",
        trust_level: 0.5,
      });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "등록 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runHandshake = async (id: string) => {
    setBusy(`hs:${id}`);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/federated/instances/${encodeURIComponent(id)}/handshake`,
        { method: "POST" }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: data.ok,
        text: data.ok
          ? `핸드셰이크 성공 (ver=${data.their_version || "?"}, trust=${(data.trust_level * 100).toFixed(0)}%)`
          : `핸드셰이크 실패: ${data.error || "검증 불가"}`,
      });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "핸드셰이크 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runCrossVerify = async () => {
    if (!crossFactId.trim()) {
      setMessage({ ok: false, text: "fact_id 를 입력하세요" });
      return;
    }
    setCrossLoading(true);
    setCrossResult(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/federated/cross-verify/${encodeURIComponent(crossFactId.trim())}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ min_instances: crossMin }),
        }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setCrossResult(data as CrossVerifyResult);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "교차 검증 실패" });
    } finally {
      setCrossLoading(false);
    }
  };

  const runDivergent = async () => {
    if (!divergentFactId.trim()) {
      setMessage({ ok: false, text: "fact_id 를 입력하세요" });
      return;
    }
    setDivergentLoading(true);
    setDivergent([]);
    try {
      const resp = await adminFetch(
        `/api/hlkm/federated/divergent/${encodeURIComponent(divergentFactId.trim())}`
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setDivergent(Array.isArray(data.divergent) ? data.divergent : []);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "발산 탐지 실패" });
    } finally {
      setDivergentLoading(false);
    }
  };

  const runAggregate = async () => {
    if (!aggregateEntity.trim()) {
      setMessage({ ok: false, text: "entity 를 입력하세요" });
      return;
    }
    setAggregateLoading(true);
    setAggregate(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/federated/aggregate?entity=${encodeURIComponent(aggregateEntity.trim())}`
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setAggregate(data);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "합의 집계 실패" });
    } finally {
      setAggregateLoading(false);
    }
  };

  return (
    <div className="space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">연합 팩트체크</h1>
          <p className="mt-1 text-sm text-gray-500">
            Federated Fact Check — 여러 HLKM 인스턴스가 서명 기반으로 사실을 교차 검증합니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAddOpen(true)}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            인스턴스 추가
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
        <StatCard label="총 인스턴스" value={stats.total} accent="primary" />
        <StatCard label="활성" value={stats.active} accent="success" />
        <StatCard
          label="평균 신뢰도"
          value={`${(stats.avgTrust * 100).toFixed(0)}%`}
          accent="neutral"
        />
        <StatCard label="24h 핸드셰이크" value={stats.handshakedRecently} accent="warning" />
      </div>

      <div
        className="flex flex-wrap items-center gap-3 rounded-xl border bg-white p-3"
        style={{ borderColor: "#e5e7eb" }}
      >
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

      <div className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr
                className="border-b bg-gray-50 text-xs text-gray-600"
                style={{ borderColor: "#e5e7eb" }}
              >
                <th className="px-4 py-2 text-left font-medium">이름 / ID</th>
                <th className="px-4 py-2 text-left font-medium">API URL</th>
                <th className="px-4 py-2 text-left font-medium">조직</th>
                <th className="px-4 py-2 text-center font-medium">신뢰도</th>
                <th className="px-4 py-2 text-left font-medium">마지막 핸드셰이크</th>
                <th className="px-4 py-2 text-center font-medium">활성</th>
                <th className="px-4 py-2 text-right font-medium">액션</th>
              </tr>
            </thead>
            <tbody>
              {!loading && items.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-gray-400">
                    등록된 연합 인스턴스가 없습니다.
                  </td>
                </tr>
              )}
              {items.map((inst) => {
                const tPct = Math.round((inst.trust_level || 0) * 100);
                const tColor =
                  tPct >= 70 ? "#16a34a" : tPct >= 40 ? "#d97706" : "#dc2626";
                return (
                  <tr
                    key={inst.instance_id}
                    className="border-b transition-colors hover:bg-gray-50"
                    style={{ borderColor: "#f3f4f6" }}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900">{inst.name}</div>
                      <div className="mt-0.5 text-[10px] text-gray-500">
                        <code className="font-mono">{inst.instance_id}</code>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="max-w-[250px] truncate text-[11px] text-gray-600" title={inst.api_url}>
                        {inst.api_url}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[11px] text-gray-600">
                      {inst.organization || "—"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-gray-100">
                          <div
                            className="h-full rounded-full"
                            style={{ width: `${tPct}%`, background: tColor }}
                          />
                        </div>
                        <span className="text-[11px] tabular-nums" style={{ color: tColor }}>
                          {tPct}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      {inst.last_handshake_at
                        ? new Date(inst.last_handshake_at).toLocaleString("ko-KR")
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className="inline-block h-2 w-2 rounded-full"
                        style={{ background: inst.active ? "#16a34a" : "#9ca3af" }}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => runHandshake(inst.instance_id)}
                          disabled={busy !== null}
                          className="rounded-lg border px-2 py-1 text-[11px] hover:bg-gray-50 disabled:opacity-60"
                          style={{ borderColor: "#e5e7eb" }}
                        >
                          {busy === `hs:${inst.instance_id}` ? "..." : "핸드셰이크"}
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

      {/* 교차 검증 */}
      <div
        className="rounded-xl border bg-white p-5"
        style={{ borderColor: "#e5e7eb" }}
      >
        <h3 className="mb-3 text-sm font-semibold text-gray-900">교차 검증</h3>
        <p className="mb-3 text-xs text-gray-500">
          하나의 사실을 모든 활성 연합 인스턴스에 질의하여 agreement 분포를 확인합니다.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={crossFactId}
            onChange={(e) => setCrossFactId(e.target.value)}
            placeholder="fact_id"
            className="flex-1 rounded-lg border px-3 py-2 font-mono text-sm"
            style={{ borderColor: "#e5e7eb", minWidth: 260 }}
          />
          <label className="flex items-center gap-1 text-xs text-gray-600">
            최소 인스턴스
            <input
              type="number"
              value={crossMin}
              onChange={(e) => setCrossMin(Math.max(1, parseInt(e.target.value) || 2))}
              className="w-16 rounded-lg border px-2 py-1 text-xs"
              style={{ borderColor: "#e5e7eb" }}
              min={1}
              max={50}
            />
          </label>
          <button
            onClick={runCrossVerify}
            disabled={crossLoading || !crossFactId.trim()}
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-60"
          >
            {crossLoading ? "검증 중..." : "검증 실행"}
          </button>
        </div>

        {crossResult && (
          <div className="mt-4 space-y-3">
            {crossResult.error && (
              <div className="rounded-lg border p-2 text-xs" style={{ borderColor: "#fecaca", background: "#fef2f2", color: "#991b1b" }}>
                {crossResult.error} (사용 가능 {crossResult.available ?? 0} / 필요 {crossResult.required ?? 0})
              </div>
            )}
            {crossResult.agreement_avg !== undefined && (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div
                  className="rounded-lg border p-3"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  <div className="text-[10px] uppercase text-gray-500">평균 agreement</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums" style={{ color: "#4338ca" }}>
                    {(crossResult.agreement_avg * 100).toFixed(1)}%
                  </div>
                </div>
                <div
                  className="rounded-lg border p-3"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  <div className="text-[10px] uppercase text-gray-500">confirming</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums" style={{ color: "#16a34a" }}>
                    {crossResult.confirming?.length ?? 0}
                  </div>
                </div>
                <div
                  className="rounded-lg border p-3"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  <div className="text-[10px] uppercase text-gray-500">dissenting</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums" style={{ color: "#dc2626" }}>
                    {crossResult.dissenting?.length ?? 0}
                  </div>
                </div>
              </div>
            )}
            {crossResult.confirming && crossResult.confirming.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-semibold text-gray-700">동의 인스턴스</div>
                <div className="space-y-1">
                  {crossResult.confirming.map((c) => (
                    <div
                      key={c.instance_id}
                      className="flex items-center justify-between rounded-lg border p-2 text-xs"
                      style={{ borderColor: "#bbf7d0", background: "#f0fdf4" }}
                    >
                      <span className="font-medium">{c.name || c.instance_id}</span>
                      <span style={{ color: "#166534" }}>
                        {(c.agreement * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {crossResult.dissenting && crossResult.dissenting.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-semibold text-gray-700">반대 인스턴스</div>
                <div className="space-y-1">
                  {crossResult.dissenting.map((c) => (
                    <div
                      key={c.instance_id}
                      className="flex items-center justify-between rounded-lg border p-2 text-xs"
                      style={{ borderColor: "#fecaca", background: "#fef2f2" }}
                    >
                      <span className="font-medium">{c.name || c.instance_id}</span>
                      <span style={{ color: "#991b1b" }}>
                        {(c.agreement * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 발산 탐지 */}
      <div
        className="rounded-xl border bg-white p-5"
        style={{ borderColor: "#e5e7eb" }}
      >
        <h3 className="mb-3 text-sm font-semibold text-gray-900">발산 탐지</h3>
        <p className="mb-3 text-xs text-gray-500">
          agreement 가 30% 미만인 인스턴스를 감사 대상으로 표시합니다.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={divergentFactId}
            onChange={(e) => setDivergentFactId(e.target.value)}
            placeholder="fact_id"
            className="flex-1 rounded-lg border px-3 py-2 font-mono text-sm"
            style={{ borderColor: "#e5e7eb", minWidth: 260 }}
          />
          <button
            onClick={runDivergent}
            disabled={divergentLoading || !divergentFactId.trim()}
            className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb" }}
          >
            {divergentLoading ? "탐지 중..." : "탐지 실행"}
          </button>
        </div>
        {divergent.length > 0 && (
          <div className="mt-3 space-y-1">
            {divergent.map((d) => (
              <div
                key={d.instance_id}
                className="flex items-center justify-between rounded-lg border p-2 text-xs"
                style={{ borderColor: "#fed7aa", background: "#fff7ed" }}
              >
                <span className="font-medium">{d.name || d.instance_id}</span>
                <span style={{ color: "#9a3412" }}>
                  {(d.agreement * 100).toFixed(0)}% ({d.verdict || "-"})
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 합의 집계 */}
      <div
        className="rounded-xl border bg-white p-5"
        style={{ borderColor: "#e5e7eb" }}
      >
        <h3 className="mb-3 text-sm font-semibold text-gray-900">연합 합의 집계</h3>
        <p className="mb-3 text-xs text-gray-500">
          동일 entity 에 대한 모든 인스턴스의 응답을 모아 consensus_strength 를 계산합니다.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={aggregateEntity}
            onChange={(e) => setAggregateEntity(e.target.value)}
            placeholder="entity 키"
            className="flex-1 rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: "#e5e7eb", minWidth: 260 }}
          />
          <button
            onClick={runAggregate}
            disabled={aggregateLoading || !aggregateEntity.trim()}
            className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb" }}
          >
            {aggregateLoading ? "집계 중..." : "집계 실행"}
          </button>
        </div>
        {aggregate && (
          <div className="mt-3 rounded-lg border p-3 text-xs" style={{ borderColor: "#e5e7eb", background: "#f9fafb" }}>
            <div className="mb-1">
              entity: <code className="font-mono">{aggregate.entity}</code>
            </div>
            <div>instances: {aggregate.instance_count}</div>
            <div>
              consensus_strength:{" "}
              <span className="font-semibold" style={{ color: "#4338ca" }}>
                {((aggregate.consensus_strength || 0) * 100).toFixed(1)}%
              </span>
            </div>
            {aggregate.top_claim_support && aggregate.top_claim_support.length > 0 && (
              <div className="mt-2 text-[11px] text-gray-500">
                최다 지지 해시: {aggregate.top_claim_support
                  .slice(0, 3)
                  .map((c: [string, number]) => `${c[0].slice(0, 10)}…(${c[1]})`)
                  .join(", ")}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 추가 모달 */}
      {addOpen && (
        <ModalOverlay onClose={() => setAddOpen(false)}>
          <div
            className="w-full max-w-lg rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">연합 인스턴스 추가</h2>
            <p className="mt-1 text-xs text-gray-500">
              상대 HLKM 인스턴스의 메타를 등록합니다. 기존 ID 가 있으면 갱신됩니다.
            </p>
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">instance_id</div>
                <input
                  value={form.instance_id}
                  onChange={(e) => setForm({ ...form, instance_id: e.target.value })}
                  placeholder="hlkm-kr-gov"
                  className="w-full rounded-lg border px-3 py-2 font-mono text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">name</div>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="KR Government HLKM"
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="block sm:col-span-2">
                <div className="mb-1 text-xs font-semibold text-gray-700">api_url</div>
                <input
                  value={form.api_url}
                  onChange={(e) => setForm({ ...form, api_url: e.target.value })}
                  placeholder="https://hlkm.example.gov.kr"
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="block sm:col-span-2">
                <div className="mb-1 text-xs font-semibold text-gray-700">public_key (base64)</div>
                <textarea
                  value={form.public_key}
                  onChange={(e) => setForm({ ...form, public_key: e.target.value })}
                  placeholder="AAAA..."
                  rows={3}
                  className="w-full rounded-lg border px-3 py-2 font-mono text-xs"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">organization</div>
                <input
                  value={form.organization}
                  onChange={(e) => setForm({ ...form, organization: e.target.value })}
                  placeholder="정부/기관"
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">
                  초기 trust_level ({(form.trust_level * 100).toFixed(0)}%)
                </div>
                <input
                  type="range"
                  value={form.trust_level}
                  onChange={(e) =>
                    setForm({ ...form, trust_level: parseFloat(e.target.value) })
                  }
                  min={0}
                  max={1}
                  step={0.05}
                  className="w-full"
                />
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setAddOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runAdd}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "add" ? "등록 중..." : "등록"}
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
