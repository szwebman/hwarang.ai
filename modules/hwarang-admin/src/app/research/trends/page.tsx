"use client";

/**
 * Research Engine — 통합 기술 트렌드 (Group C)
 *
 * - 코드 + 디자인 도메인 TechTrend 통합 보드
 * - 도메인 토글 + emerging 토글
 * - "지금 분석" 버튼 (POST /api/research/tech-trends/analyze)
 *
 * 데이터 흐름:
 *   GET  /api/research/tech-trends?domain=&weeks=&only_emerging=
 *   POST /api/research/tech-trends/analyze
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { adminFetch } from "@/lib/auth";

interface TechTrend {
  id: string;
  weekStart: string;
  domain: string;
  keyword: string;
  occurrences: number;
  velocityPct: number;
  isEmerging: boolean;
  createdAt: string;
}

export default function TechTrendsPage() {
  const [trends, setTrends] = useState<TechTrend[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(
    null
  );
  const [filter, setFilter] = useState({
    domain: "" as "" | "code" | "design",
    weeks: 4,
    onlyEmerging: false,
  });

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (filter.domain) params.append("domain", filter.domain);
    params.append("weeks", String(filter.weeks));
    if (filter.onlyEmerging) params.append("only_emerging", "true");

    try {
      const resp = await adminFetch(`/api/research/tech-trends?${params}`);
      if (!resp.ok) {
        setTrends([]);
        return;
      }
      const data = await resp.json();
      setTrends(data.trends || []);
    } catch {
      setTrends([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  const triggerAnalyze = async () => {
    setRunning(true);
    try {
      const resp = await adminFetch(`/api/research/tech-trends/analyze`, {
        method: "POST",
      });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok)
        throw new Error(body.error || `HTTP ${resp.status}`);
      setToast({
        ok: true,
        text: `분석 완료 — ${JSON.stringify(body).slice(0, 140)}`,
      });
      load();
    } catch (e: any) {
      setToast({ ok: false, text: `분석 실패: ${e?.message || e}` });
    } finally {
      setRunning(false);
    }
  };

  const grouped = useMemo(() => {
    const code: TechTrend[] = [];
    const design: TechTrend[] = [];
    for (const t of trends) {
      if (t.domain === "code") code.push(t);
      else if (t.domain === "design") design.push(t);
    }
    code.sort((a, b) => b.velocityPct - a.velocityPct);
    design.sort((a, b) => b.velocityPct - a.velocityPct);
    return { code, design };
  }, [trends]);

  return (
    <div className="p-6 lg:p-8 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1
            className="text-2xl font-bold"
            style={{ color: "var(--foreground)" }}
          >
            📈 기술 트렌드
          </h1>
          <p
            className="text-sm mt-1"
            style={{ color: "var(--muted-foreground)" }}
          >
            매주 일요일 22:00 KST — 4주 baseline 대비 키워드 빈도 +30%↑ 자동
            감지. emerging 5+ (코드) / 3+ (디자인) 시 LoRA 재학습 GrowthDecision
            자동 생성.
          </p>
        </div>
        <button
          onClick={triggerAnalyze}
          disabled={running}
          className="px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50"
          style={{
            background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
          }}
        >
          {running ? "분석 중..." : "지금 분석"}
        </button>
      </div>

      {toast && (
        <div
          className="mb-4 px-4 py-2.5 rounded-lg text-sm"
          style={{
            background: toast.ok
              ? "rgba(16,185,129,0.12)"
              : "rgba(220,38,38,0.12)",
            color: toast.ok ? "#10b981" : "#dc2626",
            border: `1px solid ${toast.ok ? "#10b98144" : "#dc262644"}`,
          }}
        >
          {toast.text}
        </div>
      )}

      {/* 필터 */}
      <div
        className="rounded-xl p-4 mb-6 flex flex-wrap items-center gap-3"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex gap-1 rounded-lg p-1" style={{ background: "var(--muted)" }}>
          {(["", "code", "design"] as const).map((d) => (
            <button
              key={d || "all"}
              onClick={() => setFilter({ ...filter, domain: d })}
              className="px-3 py-1.5 rounded-md text-xs font-medium"
              style={{
                background:
                  filter.domain === d ? "var(--background)" : "transparent",
                color:
                  filter.domain === d
                    ? "var(--foreground)"
                    : "var(--muted-foreground)",
              }}
            >
              {d === "" ? "전체" : d === "code" ? "💻 코드" : "🎨 디자인"}
            </button>
          ))}
        </div>
        <select
          value={filter.weeks}
          onChange={(e) =>
            setFilter({ ...filter, weeks: parseInt(e.target.value, 10) })
          }
          className="px-3 py-1.5 rounded-lg border text-xs"
          style={{
            borderColor: "var(--border)",
            background: "var(--background)",
            color: "var(--foreground)",
          }}
        >
          <option value={1}>1주</option>
          <option value={4}>4주</option>
          <option value={12}>12주</option>
          <option value={26}>26주</option>
          <option value={52}>52주</option>
        </select>
        <label
          className="flex items-center gap-2 text-xs cursor-pointer"
          style={{ color: "var(--foreground)" }}
        >
          <input
            type="checkbox"
            checked={filter.onlyEmerging}
            onChange={(e) =>
              setFilter({ ...filter, onlyEmerging: e.target.checked })
            }
          />
          emerging 만
        </label>
        <button
          onClick={load}
          className="ml-auto px-3 py-1.5 rounded text-xs"
          style={{
            background: "var(--muted)",
            color: "var(--foreground)",
          }}
        >
          🔄 새로고침
        </button>
      </div>

      {loading ? (
        <div
          className="text-center py-12 text-sm"
          style={{ color: "var(--muted-foreground)" }}
        >
          로딩 중...
        </div>
      ) : trends.length === 0 ? (
        <div
          className="text-center py-12 text-sm rounded-xl"
          style={{
            color: "var(--muted-foreground)",
            background: "var(--card)",
            border: "1px solid var(--border)",
          }}
        >
          아직 트렌드 데이터가 없습니다. 일요일 22:00 KST cron 또는 "지금
          분석" 버튼을 눌러 분석을 시작하세요.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(filter.domain === "" || filter.domain === "code") && (
            <TrendColumn
              title="💻 코드 트렌드"
              items={grouped.code}
              accent="#6366f1"
            />
          )}
          {(filter.domain === "" || filter.domain === "design") && (
            <TrendColumn
              title="🎨 디자인 트렌드"
              items={grouped.design}
              accent="#ec4899"
            />
          )}
        </div>
      )}
    </div>
  );
}

function TrendColumn({
  title,
  items,
  accent,
}: {
  title: string;
  items: TechTrend[];
  accent: string;
}) {
  if (items.length === 0) {
    return (
      <div
        className="rounded-xl p-5"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
        }}
      >
        <h3
          className="text-sm font-semibold mb-3"
          style={{ color: "var(--foreground)" }}
        >
          {title}
        </h3>
        <p
          className="text-xs"
          style={{ color: "var(--muted-foreground)" }}
        >
          데이터 없음
        </p>
      </div>
    );
  }

  return (
    <div
      className="rounded-xl p-5"
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderTop: `3px solid ${accent}`,
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <h3
          className="text-sm font-semibold"
          style={{ color: "var(--foreground)" }}
        >
          {title}
        </h3>
        <span
          className="text-[10px] opacity-60"
          style={{ color: "var(--muted-foreground)" }}
        >
          {items.length}건
        </span>
      </div>
      <ul className="space-y-1.5">
        {items.slice(0, 30).map((t) => (
          <li
            key={t.id}
            className="flex items-center justify-between gap-2 text-xs py-1"
          >
            <span className="flex items-center gap-2 min-w-0">
              {t.isEmerging && (
                <span
                  className="text-[9px] px-1 py-0.5 rounded font-bold shrink-0"
                  style={{
                    background: "rgba(220,38,38,0.15)",
                    color: "#dc2626",
                  }}
                >
                  HOT
                </span>
              )}
              <span
                className="font-mono truncate"
                style={{ color: "var(--foreground)" }}
              >
                {t.keyword}
              </span>
              <span
                className="text-[10px] opacity-50 shrink-0"
                style={{ color: "var(--muted-foreground)" }}
              >
                {new Date(t.weekStart).toLocaleDateString("ko-KR", {
                  month: "short",
                  day: "numeric",
                })}
              </span>
            </span>
            <span
              className="font-mono shrink-0"
              style={{
                color:
                  t.velocityPct > 30
                    ? "#10b981"
                    : t.velocityPct > 0
                      ? "#0891b2"
                      : "var(--muted-foreground)",
              }}
            >
              {t.occurrences}건 · {t.velocityPct >= 0 ? "+" : ""}
              {t.velocityPct.toFixed(0)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
