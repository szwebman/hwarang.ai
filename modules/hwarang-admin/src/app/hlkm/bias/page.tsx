"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 정치 편향 분석 (Political Bias Detection)
 * - 편향 라벨 분포 (progressive/centrist/conservative/mixed) horizontal bar
 * - 언론사 편향 프로필 (biasScore -1..+1 slider, factualityRating)
 * - 특정 entity 분석: find_balanced_perspective 시각화
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface BiasProfile {
  outlet: string;
  biasScore: number;
  biasLabel: string;
  factualityRating?: string | null;
  biasSource?: string | null;
  notes?: string | null;
}

interface BalancedPerspective {
  progressive: { fact_id: string; content: string; bias_score: number; bias_label: string; source: string }[];
  centrist: { fact_id: string; content: string; bias_score: number; bias_label: string; source: string }[];
  conservative: { fact_id: string; content: string; bias_score: number; bias_label: string; source: string }[];
  mixed: { fact_id: string; content: string; bias_score: number; bias_label: string; source: string }[];
}

const LABEL_META: Record<string, { ko: string; bg: string; color: string }> = {
  FAR_LEFT: { ko: "극좌", bg: "#bfdbfe", color: "#1e3a8a" },
  PROGRESSIVE: { ko: "진보", bg: "#dbeafe", color: "#1d4ed8" },
  CENTRIST: { ko: "중도", bg: "#e5e7eb", color: "#374151" },
  CONSERVATIVE: { ko: "보수", bg: "#fee2e2", color: "#b91c1c" },
  FAR_RIGHT: { ko: "극우", bg: "#fecaca", color: "#7f1d1d" },
  UNKNOWN: { ko: "미상", bg: "#f3f4f6", color: "#6b7280" },
  NON_POLITICAL: { ko: "비정치", bg: "#fef3c7", color: "#92400e" },
};

const FILTER_OPTIONS = [
  { key: "all", label: "전체" },
  { key: "FAR_LEFT", label: "극좌" },
  { key: "PROGRESSIVE", label: "진보" },
  { key: "CENTRIST", label: "중도" },
  { key: "CONSERVATIVE", label: "보수" },
  { key: "FAR_RIGHT", label: "극우" },
];

export default function BiasPage() {
  const [profiles, setProfiles] = useState<BiasProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [entity, setEntity] = useState("");
  const [entityLoading, setEntityLoading] = useState(false);
  const [balanced, setBalanced] = useState<BalancedPerspective | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await adminFetch("/api/hlkm/bias/profiles");
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setProfiles(Array.isArray(data.profiles) ? data.profiles : []);
    } catch (e: any) {
      setProfiles([]);
      setMessage({ ok: false, text: e?.message || "목록 조회 실패" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const filtered = useMemo(() => {
    if (filter === "all") return profiles;
    return profiles.filter((p) => p.biasLabel === filter);
  }, [profiles, filter]);

  const distribution = useMemo(() => {
    const buckets: Record<string, number> = {
      FAR_LEFT: 0,
      PROGRESSIVE: 0,
      CENTRIST: 0,
      CONSERVATIVE: 0,
      FAR_RIGHT: 0,
    };
    for (const p of profiles) {
      if (buckets[p.biasLabel] !== undefined) buckets[p.biasLabel]++;
    }
    const max = Math.max(1, ...Object.values(buckets));
    return { buckets, max, total: profiles.length };
  }, [profiles]);

  const runSeed = async () => {
    setBusy("seed");
    setMessage(null);
    try {
      const resp = await adminFetch("/api/hlkm/bias/seed-profiles", { method: "POST" });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `편향 프로필 시드 완료 (신규 ${(data.inserted ?? 0).toLocaleString("ko-KR")}건)`,
      });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "시드 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runBatch = async () => {
    setBusy("batch");
    setMessage(null);
    try {
      const resp = await adminFetch("/api/hlkm/bias/batch", {
        method: "POST",
        body: JSON.stringify({ domain: "politics", limit: 500 }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `배치 편향 감지 완료 (${(data.labeled ?? 0).toLocaleString("ko-KR")}/${(data.total ?? 0).toLocaleString("ko-KR")})`,
      });
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "배치 실패" });
    } finally {
      setBusy(null);
    }
  };

  const analyzeEntity = async () => {
    const q = entity.trim();
    if (!q) {
      setMessage({ ok: false, text: "엔티티를 입력하세요" });
      return;
    }
    setEntityLoading(true);
    setBalanced(null);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/bias/balanced-perspective?entity=${encodeURIComponent(q)}`
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setBalanced(data);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "엔티티 분석 실패" });
    } finally {
      setEntityLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">정치 편향 분석</h1>
          <p className="mt-1 text-sm text-gray-500">
            Political Bias Detection — 언론사 프로필 + 사실 편향 감지 + 균형 관점 시각화.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={runSeed}
            disabled={busy !== null}
            className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb", color: "#374151" }}
          >
            {busy === "seed" ? "시드 중..." : "프로필 시드"}
          </button>
          <button
            onClick={runBatch}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy === "batch" ? "감지 중..." : "배치 편향 감지"}
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
        <StatCard label="총 언론사 프로필" value={distribution.total} accent="primary" />
        <StatCard
          label="진보 계열"
          value={distribution.buckets.PROGRESSIVE + distribution.buckets.FAR_LEFT}
          accent="neutral"
        />
        <StatCard label="중도" value={distribution.buckets.CENTRIST} accent="success" />
        <StatCard
          label="보수 계열"
          value={distribution.buckets.CONSERVATIVE + distribution.buckets.FAR_RIGHT}
          accent="warning"
        />
      </div>

      {/* 편향 분포 가로 막대 */}
      <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">편향 라벨 분포</h2>
        <svg width="100%" height={180} viewBox="0 0 500 180" preserveAspectRatio="none">
          {Object.entries(distribution.buckets).map(([lbl, n], i) => {
            const meta = LABEL_META[lbl];
            const barW = (n / distribution.max) * 360;
            return (
              <g key={lbl} transform={`translate(0, ${10 + i * 32})`}>
                <text x={0} y={16} fontSize={12} fill="#374151">
                  {meta.ko}
                </text>
                <rect x={70} y={4} width={360} height={20} fill="#f3f4f6" rx={4} />
                <rect x={70} y={4} width={barW} height={20} fill={meta.color} rx={4} />
                <text x={440} y={18} fontSize={12} fill="#374151">
                  {n.toLocaleString("ko-KR")}
                </text>
              </g>
            );
          })}
        </svg>
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

      {/* 엔티티 균형 분석 */}
      <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">엔티티 균형 관점 분석</h2>
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            value={entity}
            onChange={(e) => setEntity(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && analyzeEntity()}
            placeholder="예: 윤석열, AI 규제법, 부동산 정책"
            className="flex-1 min-w-[240px] rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: "#e5e7eb" }}
          />
          <button
            onClick={analyzeEntity}
            disabled={entityLoading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {entityLoading ? "분석 중..." : "관점 분석"}
          </button>
        </div>
        {balanced && (
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
            {(["progressive", "centrist", "conservative", "mixed"] as const).map((bucket) => {
              const colors: Record<string, string> = {
                progressive: "#1d4ed8",
                centrist: "#374151",
                conservative: "#b91c1c",
                mixed: "#92400e",
              };
              const labels: Record<string, string> = {
                progressive: "진보",
                centrist: "중도",
                conservative: "보수",
                mixed: "혼재",
              };
              const items = balanced[bucket] || [];
              return (
                <div
                  key={bucket}
                  className="rounded-lg border p-3"
                  style={{ borderColor: "#e5e7eb", background: "#fafafa" }}
                >
                  <div
                    className="mb-2 flex items-center justify-between text-xs font-semibold"
                    style={{ color: colors[bucket] }}
                  >
                    <span>{labels[bucket]}</span>
                    <span>{items.length}</span>
                  </div>
                  <ul className="space-y-2">
                    {items.length === 0 && (
                      <li className="text-[11px] text-gray-400">데이터 없음</li>
                    )}
                    {items.map((it) => (
                      <li
                        key={it.fact_id}
                        className="rounded-md bg-white p-2 text-[11px]"
                        style={{ border: "1px solid #e5e7eb" }}
                      >
                        <div className="line-clamp-3 text-gray-800">{it.content}</div>
                        <div className="mt-1 flex items-center justify-between text-[10px] text-gray-500">
                          <span className="truncate" title={it.source}>
                            {it.source || "—"}
                          </span>
                          <span className="tabular-nums">
                            {it.bias_score >= 0 ? "+" : ""}
                            {it.bias_score.toFixed(2)}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 필터 + 테이블 */}
      <div
        className="flex flex-wrap items-center gap-2 rounded-xl border bg-white p-4"
        style={{ borderColor: "#e5e7eb" }}
      >
        <span className="text-xs text-gray-600">편향 필터:</span>
        {FILTER_OPTIONS.map((o) => (
          <button
            key={o.key}
            onClick={() => setFilter(o.key)}
            className="rounded-lg border px-3 py-1 text-xs"
            style={{
              borderColor: filter === o.key ? "#6366f1" : "#e5e7eb",
              background: filter === o.key ? "#eef2ff" : "white",
              color: filter === o.key ? "#4338ca" : "#374151",
            }}
          >
            {o.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-gray-500">
          {loading ? "불러오는 중..." : `${filtered.length.toLocaleString("ko-KR")}건`}
        </span>
      </div>

      <div className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr
                className="border-b bg-gray-50 text-xs text-gray-600"
                style={{ borderColor: "#e5e7eb" }}
              >
                <th className="px-4 py-2 text-left font-medium">언론사</th>
                <th className="px-4 py-2 text-left font-medium">편향 라벨</th>
                <th className="px-4 py-2 text-left font-medium">편향 점수 (-1 ~ +1)</th>
                <th className="px-4 py-2 text-left font-medium">사실성</th>
                <th className="px-4 py-2 text-left font-medium">근거 출처</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && !loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">
                    데이터가 없습니다 — &quot;프로필 시드&quot; 를 눌러 초기화하세요.
                  </td>
                </tr>
              )}
              {filtered.map((p) => {
                const meta = LABEL_META[p.biasLabel] || LABEL_META.UNKNOWN;
                return (
                  <tr
                    key={p.outlet}
                    className="border-b transition-colors hover:bg-gray-50"
                    style={{ borderColor: "#f3f4f6" }}
                  >
                    <td className="px-4 py-3 font-medium text-gray-900">{p.outlet}</td>
                    <td className="px-4 py-3">
                      <span
                        className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                        style={{ color: meta.color, background: meta.bg }}
                      >
                        {meta.ko}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <BiasSlider score={p.biasScore} />
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-700">
                      {p.factualityRating || "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {p.biasSource || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function BiasSlider({ score }: { score: number }) {
  const clamped = Math.max(-1, Math.min(1, score));
  const pct = ((clamped + 1) / 2) * 100;
  const color = clamped < -0.3 ? "#1d4ed8" : clamped > 0.3 ? "#b91c1c" : "#374151";
  return (
    <div className="flex items-center gap-2">
      <div
        className="relative h-2 w-40 overflow-hidden rounded-full"
        style={{
          background: "linear-gradient(to right, #dbeafe 0%, #f3f4f6 50%, #fee2e2 100%)",
        }}
      >
        <div
          className="absolute top-1/2 -translate-y-1/2 h-3 w-1"
          style={{ left: `${pct}%`, background: color }}
        />
      </div>
      <span className="tabular-nums text-xs font-semibold" style={{ color }}>
        {clamped >= 0 ? "+" : ""}
        {clamped.toFixed(2)}
      </span>
    </div>
  );
}
