"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 교차 언어 원본 추적 (Cross-lingual Provenance)
 * - 총 번역 링크 / 언어쌍 / method 분포
 * - 역번역 후보 리스트
 * - Entity 다국어 통합 뷰 (ko/en/ja/zh)
 * - 외신 전재 감지
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface TranslationStats {
  total_translations: number;
  by_lang_pair: Record<string, number>;
  by_method: Record<string, number>;
  potential_back_translations?: BackTranslationCandidate[];
}

interface BackTranslationCandidate {
  fact_id: string;
  language_path?: string[];
  original_fact_id?: string;
  semantic_drift?: number;
  content_preview?: string;
}

interface UnifiedEntity {
  primary_lang?: string;
  original_found?: boolean;
  [lang: string]: unknown;
}

interface WireOrigin {
  fact_id: string;
  is_foreign_wire: boolean;
  wire_agency?: string | null;
  method?: string;
  original_fact_id?: string | null;
}

const LANG_LABEL: Record<string, string> = {
  ko: "한국어",
  en: "영어",
  ja: "일본어",
  zh: "중국어",
  es: "스페인어",
  fr: "프랑스어",
  de: "독일어",
  ru: "러시아어",
  ar: "아랍어",
  mixed: "혼합",
};

export default function CrossLingualPage() {
  const [stats, setStats] = useState<TranslationStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [domain, setDomain] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [entity, setEntity] = useState("");
  const [unifiedLoading, setUnifiedLoading] = useState(false);
  const [unified, setUnified] = useState<UnifiedEntity | null>(null);

  const [wireFactId, setWireFactId] = useState("");
  const [wireLoading, setWireLoading] = useState(false);
  const [wireResults, setWireResults] = useState<WireOrigin[]>([]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (domain.trim()) qs.set("domain", domain.trim());
      const resp = await adminFetch(`/api/hlkm/xlingual/stats?${qs.toString()}`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setStats(data);
    } catch (e: any) {
      setStats(null);
      setMessage({ ok: false, text: e?.message || "통계 조회 실패" });
    } finally {
      setLoading(false);
    }
  }, [domain]);

  useEffect(() => {
    reload();
  }, [reload]);

  const pairEntries = useMemo(() => {
    if (!stats) return [] as [string, number][];
    return Object.entries(stats.by_lang_pair).sort((a, b) => b[1] - a[1]);
  }, [stats]);

  const methodEntries = useMemo(() => {
    if (!stats) return [] as [string, number][];
    return Object.entries(stats.by_method).sort((a, b) => b[1] - a[1]);
  }, [stats]);

  const maxPair = Math.max(1, ...pairEntries.map(([, n]) => n));
  const maxMethod = Math.max(1, ...methodEntries.map(([, n]) => n));

  const runUnified = async () => {
    const q = entity.trim();
    if (!q) {
      setMessage({ ok: false, text: "엔티티를 입력하세요" });
      return;
    }
    setUnifiedLoading(true);
    setUnified(null);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/xlingual/unified-entity?entity=${encodeURIComponent(q)}`
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setUnified(data);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "통합 조회 실패" });
    } finally {
      setUnifiedLoading(false);
    }
  };

  const runWire = async () => {
    const id = wireFactId.trim();
    if (!id) {
      setMessage({ ok: false, text: "Fact ID 를 입력하세요" });
      return;
    }
    setWireLoading(true);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/xlingual/wire-origin/${encodeURIComponent(id)}`,
        { method: "POST" }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setWireResults((prev) => [data, ...prev].slice(0, 20));
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "외신 감지 실패" });
    } finally {
      setWireLoading(false);
    }
  };

  const backCandidates = stats?.potential_back_translations || [];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">교차 언어 원본 추적</h1>
          <p className="mt-1 text-sm text-gray-500">
            Cross-lingual Provenance — 번역 링크 / 역번역 / 외신 전재 / 다국어 통합 뷰.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="도메인 필터 (선택)"
            className="rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: "#e5e7eb" }}
          />
          <button
            onClick={reload}
            disabled={loading}
            className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb" }}
          >
            {loading ? "불러오는 중..." : "새로고침"}
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="총 번역 링크"
          value={stats?.total_translations ?? 0}
          accent="primary"
        />
        <StatCard label="고유 언어쌍" value={pairEntries.length} accent="neutral" />
        <StatCard label="감지 방법 종류" value={methodEntries.length} accent="success" />
        <StatCard
          label="역번역 의심"
          value={backCandidates.length}
          accent="warning"
          hint="language_path 가 A-B-A"
        />
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

      {/* 언어쌍 / method 분포 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">언어쌍 분포 (원문 → 번역본)</h2>
          {pairEntries.length === 0 ? (
            <div className="py-8 text-center text-sm text-gray-400">데이터 없음</div>
          ) : (
            <ul className="space-y-2">
              {pairEntries.slice(0, 10).map(([pair, n]) => (
                <li key={pair} className="flex items-center gap-2 text-xs">
                  <span className="w-24 shrink-0 truncate font-mono text-gray-700">{pair}</span>
                  <div
                    className="relative h-4 flex-1 overflow-hidden rounded-full"
                    style={{ background: "#f3f4f6" }}
                  >
                    <div
                      className="absolute left-0 top-0 h-full rounded-full"
                      style={{
                        width: `${(n / maxPair) * 100}%`,
                        background: "#6366f1",
                      }}
                    />
                  </div>
                  <span className="w-12 shrink-0 text-right tabular-nums font-semibold">
                    {n.toLocaleString("ko-KR")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">감지 방법 분포</h2>
          {methodEntries.length === 0 ? (
            <div className="py-8 text-center text-sm text-gray-400">데이터 없음</div>
          ) : (
            <ul className="space-y-2">
              {methodEntries.map(([m, n]) => (
                <li key={m} className="flex items-center gap-2 text-xs">
                  <span className="w-24 shrink-0 truncate font-mono text-gray-700">{m}</span>
                  <div
                    className="relative h-4 flex-1 overflow-hidden rounded-full"
                    style={{ background: "#f3f4f6" }}
                  >
                    <div
                      className="absolute left-0 top-0 h-full rounded-full"
                      style={{
                        width: `${(n / maxMethod) * 100}%`,
                        background: "#10b981",
                      }}
                    />
                  </div>
                  <span className="w-12 shrink-0 text-right tabular-nums font-semibold">
                    {n.toLocaleString("ko-KR")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* 역번역 후보 */}
      <div className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="border-b px-5 py-3 text-sm font-semibold text-gray-900" style={{ borderColor: "#e5e7eb" }}>
          역번역 후보 (Back-translation)
        </div>
        <div className="divide-y" style={{ borderColor: "#f3f4f6" }}>
          {backCandidates.length === 0 && (
            <div className="px-5 py-8 text-center text-sm text-gray-400">
              역번역 의심 사례가 없습니다
            </div>
          )}
          {backCandidates.map((c, idx) => (
            <div key={`${c.fact_id}-${idx}`} className="px-5 py-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-gray-500">{c.fact_id.slice(0, 12)}...</span>
                  {c.language_path && (
                    <span className="flex items-center gap-0.5">
                      {c.language_path.map((l, i) => (
                        <span key={`${l}-${i}`} className="flex items-center gap-0.5">
                          {i > 0 && <span className="text-gray-400">→</span>}
                          <span
                            className="rounded px-1 py-0.5 text-[10px] font-medium"
                            style={{ color: "#4338ca", background: "#eef2ff" }}
                          >
                            {l}
                          </span>
                        </span>
                      ))}
                    </span>
                  )}
                </div>
                {c.semantic_drift !== undefined && (
                  <span
                    className="rounded px-1.5 py-0.5 text-[11px] font-semibold tabular-nums"
                    style={{
                      color: c.semantic_drift > 0.2 ? "#991b1b" : "#374151",
                      background: c.semantic_drift > 0.2 ? "#fee2e2" : "#f3f4f6",
                    }}
                  >
                    의미 왜곡 {(c.semantic_drift * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              {c.content_preview && (
                <div className="mt-1 line-clamp-2 text-xs text-gray-600">{c.content_preview}</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Entity 통합 뷰 */}
      <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">엔티티 다국어 통합 뷰</h2>
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            value={entity}
            onChange={(e) => setEntity(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runUnified()}
            placeholder="예: Samsung, 윤석열, 북한 미사일"
            className="flex-1 min-w-[240px] rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: "#e5e7eb" }}
          />
          <button
            onClick={runUnified}
            disabled={unifiedLoading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {unifiedLoading ? "분석 중..." : "통합 분석"}
          </button>
        </div>
        {unified && (
          <div className="mt-4">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
              <span className="text-gray-600">원본 언어:</span>
              <span
                className="rounded px-1.5 py-0.5 font-semibold"
                style={{ color: "#1d4ed8", background: "#dbeafe" }}
              >
                {unified.primary_lang
                  ? LANG_LABEL[unified.primary_lang] || unified.primary_lang
                  : "—"}
              </span>
              <span className="text-gray-600">
                원본 발견: {unified.original_found ? "O" : "X"}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
              {["ko", "en", "ja", "zh"].map((lang) => {
                const items = (unified[lang] as
                  | {
                      fact_id: string;
                      content: string;
                      source: string;
                      is_original?: boolean;
                    }[]
                  | undefined) || [];
                return (
                  <div
                    key={lang}
                    className="rounded-lg border p-3"
                    style={{ borderColor: "#e5e7eb", background: "#fafafa" }}
                  >
                    <div className="mb-2 flex items-center justify-between text-xs font-semibold text-gray-700">
                      <span>{LANG_LABEL[lang] || lang}</span>
                      <span>{items.length}</span>
                    </div>
                    <ul className="space-y-2">
                      {items.length === 0 && (
                        <li className="text-[11px] text-gray-400">데이터 없음</li>
                      )}
                      {items.slice(0, 6).map((it) => (
                        <li
                          key={it.fact_id}
                          className="rounded-md bg-white p-2 text-[11px]"
                          style={{ border: "1px solid #e5e7eb" }}
                        >
                          <div className="flex items-start justify-between gap-1">
                            <div className="line-clamp-3 flex-1 text-gray-800">{it.content}</div>
                            {it.is_original && (
                              <span
                                className="shrink-0 rounded px-1 py-0.5 text-[9px]"
                                style={{ color: "#065f46", background: "#d1fae5" }}
                              >
                                원본
                              </span>
                            )}
                          </div>
                          <div className="mt-1 truncate text-[10px] text-gray-500">
                            {it.source || "—"}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* 외신 전재 감지 */}
      <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">외신 전재 감지</h2>
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            value={wireFactId}
            onChange={(e) => setWireFactId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runWire()}
            placeholder="KnowledgeFact ID (한국어 기사)"
            className="flex-1 min-w-[280px] rounded-lg border px-3 py-2 text-sm font-mono"
            style={{ borderColor: "#e5e7eb" }}
          />
          <button
            onClick={runWire}
            disabled={wireLoading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {wireLoading ? "검사 중..." : "외신 감지"}
          </button>
        </div>
        {wireResults.length > 0 && (
          <ul className="mt-4 divide-y" style={{ borderColor: "#f3f4f6" }}>
            {wireResults.map((r, idx) => (
              <li key={`${r.fact_id}-${idx}`} className="flex flex-wrap items-center gap-2 py-2 text-xs">
                <span className="font-mono text-gray-500 truncate max-w-[180px]">
                  {r.fact_id}
                </span>
                <span
                  className="rounded px-1.5 py-0.5 font-semibold"
                  style={{
                    color: r.is_foreign_wire ? "#b91c1c" : "#374151",
                    background: r.is_foreign_wire ? "#fee2e2" : "#f3f4f6",
                  }}
                >
                  {r.is_foreign_wire ? "외신 전재" : "자체"}
                </span>
                {r.wire_agency && (
                  <span
                    className="rounded px-1.5 py-0.5"
                    style={{ color: "#1d4ed8", background: "#dbeafe" }}
                  >
                    {r.wire_agency.toUpperCase()}
                  </span>
                )}
                {r.method && <span className="text-gray-500">· {r.method}</span>}
                {r.original_fact_id && (
                  <span className="text-gray-400 truncate max-w-[160px]">
                    → {r.original_fact_id}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
