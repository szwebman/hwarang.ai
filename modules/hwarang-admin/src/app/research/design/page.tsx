"use client";

/**
 * Research Engine — 디자인 패턴 라이브러리 (Group C)
 *
 * - 떠오르는 디자인 트렌드 (TechTrend, domain=design, isEmerging) 상단 배너
 * - DesignPattern 검색/필터 (layoutCategory, applicableTo, trendKeyword)
 * - 카드 그리드 (popularity 순)
 *
 * 데이터 흐름:
 *   GET /api/research/tech-trends?domain=design&weeks=4&only_emerging=true
 *   GET /api/research/design/patterns?layout=&trend=&applicable=
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { adminFetch } from "@/lib/auth";

interface DesignPattern {
  id: string;
  trendKeywords: string[];
  layoutCategory: string;
  colorMood: string | null;
  typographyStyle: string | null;
  summary: string;
  applicableTo: string[];
  sourceUrl: string | null;
  popularity: number;
  createdAt: string;
}

interface TechTrend {
  id: string;
  weekStart: string;
  domain: string;
  keyword: string;
  occurrences: number;
  velocityPct: number;
  isEmerging: boolean;
}

const LAYOUTS = [
  { value: "", label: "전체", icon: "🎨" },
  { value: "hero", label: "Hero", icon: "🦸" },
  { value: "grid", label: "Grid", icon: "▦" },
  { value: "split", label: "Split", icon: "◫" },
  { value: "asymmetric", label: "Asymmetric", icon: "▱" },
  { value: "magazine", label: "Magazine", icon: "📰" },
  { value: "fullscreen", label: "Fullscreen", icon: "🖼️" },
];

const APPLICABLE_TO = [
  "landing",
  "dashboard",
  "mobile_app",
  "marketing",
  "portfolio",
  "ecommerce",
];

const COLOR_MOOD_HEX: Record<string, string> = {
  warm: "#f59e0b",
  cool: "#3b82f6",
  monochrome: "#64748b",
  vibrant: "#ec4899",
  muted: "#94a3b8",
};

export default function DesignPatternsPage() {
  const [patterns, setPatterns] = useState<DesignPattern[]>([]);
  const [trends, setTrends] = useState<TechTrend[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({
    layout: "",
    applicable: "",
    trend: "",
    search: "",
  });

  const fetchPatterns = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (filter.layout) params.append("layout", filter.layout);
    if (filter.applicable) params.append("applicable", filter.applicable);
    if (filter.trend) params.append("trend", filter.trend);
    params.append("limit", "200");

    try {
      const resp = await adminFetch(`/api/research/design/patterns?${params}`);
      if (!resp.ok) {
        setPatterns([]);
        return;
      }
      const data = await resp.json();
      let list: DesignPattern[] = data.patterns || [];
      if (filter.search) {
        const q = filter.search.toLowerCase();
        list = list.filter(
          (p) =>
            (p.summary || "").toLowerCase().includes(q) ||
            (p.trendKeywords || []).some((k) =>
              (k || "").toLowerCase().includes(q)
            )
        );
      }
      setPatterns(list);
    } catch {
      setPatterns([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  const fetchTrends = useCallback(async () => {
    try {
      const resp = await adminFetch(
        `/api/research/tech-trends?domain=design&weeks=4&only_emerging=true`
      );
      if (!resp.ok) return;
      const data = await resp.json();
      setTrends((data.trends || []).slice(0, 10));
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    fetchPatterns();
  }, [fetchPatterns]);

  useEffect(() => {
    fetchTrends();
  }, [fetchTrends]);

  const stats = useMemo(() => {
    const byLayout: Record<string, number> = {};
    for (const p of patterns) {
      byLayout[p.layoutCategory] = (byLayout[p.layoutCategory] || 0) + 1;
    }
    return {
      total: patterns.length,
      byLayout,
    };
  }, [patterns]);

  return (
    <div className="p-6 lg:p-8 max-w-[1400px] mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold" style={{ color: "var(--foreground)" }}>
          🎨 디자인 패턴 라이브러리
        </h1>
        <p
          className="text-sm mt-1"
          style={{ color: "var(--muted-foreground)" }}
        >
          매 6시간 Awwwards / Smashing / CSS-Tricks / 한국 디자인 / shadcn 에서
          자동 수집한 시각 패턴 — LLM 분류 후 DesignPattern 으로 저장.
        </p>
      </div>

      {/* 떠오르는 트렌드 배너 */}
      {trends.length > 0 && (
        <div
          className="rounded-xl p-4 mb-6"
          style={{
            border: "1px solid #ec489966",
            background:
              "linear-gradient(135deg, rgba(236,72,153,0.08), rgba(168,85,247,0.06))",
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            <span className="text-base">✨</span>
            <span
              className="text-sm font-semibold"
              style={{ color: "var(--foreground)" }}
            >
              이번 주 떠오르는 디자인 트렌드
            </span>
            <span className="text-[10px] opacity-60">
              (4주 baseline 대비 +30%↑, 2건 이상)
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {trends.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() =>
                  setFilter({ ...filter, trend: t.keyword, search: "" })
                }
                className="text-xs px-3 py-1 rounded-full font-mono cursor-pointer hover:opacity-90"
                style={{
                  background:
                    "linear-gradient(135deg, #ec4899, #a855f7)",
                  color: "white",
                }}
                title={`Click to filter — ${t.occurrences} this week`}
              >
                {t.keyword} +{t.velocityPct.toFixed(0)}%
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 통계 4박스 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <SmallStat label="전체 패턴" value={stats.total} color="#ec4899" />
        <SmallStat
          label="Hero"
          value={stats.byLayout.hero || 0}
          color="#f59e0b"
        />
        <SmallStat
          label="Grid"
          value={stats.byLayout.grid || 0}
          color="#3b82f6"
        />
        <SmallStat
          label="Asymmetric"
          value={stats.byLayout.asymmetric || 0}
          color="#a855f7"
        />
      </div>

      {/* 필터 */}
      <div
        className="rounded-xl p-4 mb-6"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label
              className="text-xs"
              style={{ color: "var(--muted-foreground)" }}
            >
              레이아웃
            </label>
            <select
              value={filter.layout}
              onChange={(e) =>
                setFilter({ ...filter, layout: e.target.value })
              }
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
              style={{
                borderColor: "var(--border)",
                background: "var(--background)",
                color: "var(--foreground)",
              }}
            >
              {LAYOUTS.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.icon} {l.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              className="text-xs"
              style={{ color: "var(--muted-foreground)" }}
            >
              적용처
            </label>
            <select
              value={filter.applicable}
              onChange={(e) =>
                setFilter({ ...filter, applicable: e.target.value })
              }
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
              style={{
                borderColor: "var(--border)",
                background: "var(--background)",
                color: "var(--foreground)",
              }}
            >
              <option value="">전체</option>
              {APPLICABLE_TO.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              className="text-xs"
              style={{ color: "var(--muted-foreground)" }}
            >
              트렌드
            </label>
            <input
              type="text"
              value={filter.trend}
              onChange={(e) =>
                setFilter({ ...filter, trend: e.target.value })
              }
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
              style={{
                borderColor: "var(--border)",
                background: "var(--background)",
                color: "var(--foreground)",
              }}
              placeholder="minimalism, glassmorphism..."
            />
          </div>
          <div>
            <label
              className="text-xs"
              style={{ color: "var(--muted-foreground)" }}
            >
              검색
            </label>
            <input
              type="text"
              value={filter.search}
              onChange={(e) =>
                setFilter({ ...filter, search: e.target.value })
              }
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
              style={{
                borderColor: "var(--border)",
                background: "var(--background)",
                color: "var(--foreground)",
              }}
              placeholder="요약/키워드 검색..."
            />
          </div>
        </div>
      </div>

      {/* 패턴 카드 */}
      {loading ? (
        <div
          className="text-center py-12 text-sm"
          style={{ color: "var(--muted-foreground)" }}
        >
          로딩 중...
        </div>
      ) : patterns.length === 0 ? (
        <div
          className="text-center py-12 text-sm rounded-xl"
          style={{
            color: "var(--muted-foreground)",
            background: "var(--card)",
            border: "1px solid var(--border)",
          }}
        >
          조건에 맞는 디자인 패턴이 없습니다.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {patterns.map((p) => {
            const lay = LAYOUTS.find((l) => l.value === p.layoutCategory);
            const moodColor = p.colorMood
              ? COLOR_MOOD_HEX[p.colorMood] || "#94a3b8"
              : "#94a3b8";
            return (
              <div
                key={p.id}
                className="rounded-xl p-4 flex flex-col gap-2"
                style={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  borderTop: `3px solid ${moodColor}`,
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <h3
                    className="font-semibold text-sm"
                    style={{ color: "var(--foreground)" }}
                  >
                    {lay?.icon || "🎨"} {lay?.label || p.layoutCategory}
                  </h3>
                  {p.popularity > 0 && (
                    <span
                      className="text-[10px] px-2 py-0.5 rounded-full shrink-0 font-mono"
                      style={{
                        background: "rgba(245,158,11,0.15)",
                        color: "#d97706",
                      }}
                    >
                      ★ {p.popularity}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1">
                  {p.colorMood && (
                    <code
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        background: `${moodColor}22`,
                        color: moodColor,
                      }}
                    >
                      {p.colorMood}
                    </code>
                  )}
                  {p.typographyStyle && (
                    <code
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        background: "var(--muted)",
                        color: "var(--foreground)",
                      }}
                    >
                      {p.typographyStyle}
                    </code>
                  )}
                </div>
                {p.trendKeywords && p.trendKeywords.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {p.trendKeywords.slice(0, 4).map((k) => (
                      <span
                        key={k}
                        className="text-[10px] px-1.5 py-0.5 rounded-full"
                        style={{
                          background: "rgba(168,85,247,0.12)",
                          color: "#a855f7",
                        }}
                      >
                        #{k}
                      </span>
                    ))}
                  </div>
                )}
                <p
                  className="text-xs leading-relaxed"
                  style={{ color: "var(--muted-foreground)" }}
                >
                  {(p.summary || "").slice(0, 220)}
                  {(p.summary || "").length > 220 && "..."}
                </p>
                {p.applicableTo && p.applicableTo.length > 0 && (
                  <p
                    className="text-[11px] italic mt-auto pt-1"
                    style={{ color: "var(--muted-foreground)" }}
                  >
                    🎯 {p.applicableTo.slice(0, 3).join(", ")}
                  </p>
                )}
                {p.sourceUrl && (
                  <a
                    href={p.sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px]"
                    style={{ color: "#ec4899" }}
                  >
                    원본 보기 →
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SmallStat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div
      className="rounded-xl p-3"
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderLeft: `3px solid ${color}`,
      }}
    >
      <div
        className="text-[10px] uppercase tracking-wider opacity-60 mb-0.5"
        style={{ color: "var(--muted-foreground)" }}
      >
        {label}
      </div>
      <div className="text-xl font-bold" style={{ color }}>
        {value}
      </div>
    </div>
  );
}
