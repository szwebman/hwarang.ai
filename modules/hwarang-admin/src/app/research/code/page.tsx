"use client";

/**
 * Research Engine — 코드 패턴 라이브러리 (Group C)
 *
 * - 떠오르는 기술 트렌드 (TechTrend, domain=code, isEmerging=true) 상단 배너
 * - CodePattern 검색/필터 (category, language, free-text)
 * - 카드 그리드 (popularity 순)
 *
 * 데이터 흐름:
 *   GET /api/research/tech-trends?domain=code&weeks=4&only_emerging=true
 *   GET /api/research/code/patterns?category=&language=
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { adminFetch } from "@/lib/auth";

interface CodePattern {
  id: string;
  patternName: string;
  category: string;
  language: string | null;
  framework: string | null;
  summary: string;
  useCase: string | null;
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

const CATEGORIES = [
  { value: "", label: "전체", icon: "📚" },
  { value: "hook", label: "Hook", icon: "🪝" },
  { value: "utility", label: "Utility", icon: "🛠️" },
  { value: "architecture", label: "Architecture", icon: "🏛️" },
  { value: "antipattern", label: "Anti-pattern", icon: "⚠️" },
  { value: "optimization", label: "Optimization", icon: "⚡" },
  { value: "design_pattern", label: "Design Pattern", icon: "📐" },
];

const LANGUAGES = [
  "javascript",
  "typescript",
  "python",
  "rust",
  "go",
  "java",
  "kotlin",
  "swift",
];

export default function CodePatternsPage() {
  const [patterns, setPatterns] = useState<CodePattern[]>([]);
  const [trends, setTrends] = useState<TechTrend[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({
    category: "",
    language: "",
    search: "",
  });

  const fetchPatterns = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (filter.category) params.append("category", filter.category);
    if (filter.language) params.append("language", filter.language);
    params.append("limit", "200");

    try {
      const resp = await adminFetch(`/api/research/code/patterns?${params}`);
      if (!resp.ok) {
        setPatterns([]);
        return;
      }
      const data = await resp.json();
      let list: CodePattern[] = data.patterns || [];
      if (filter.search) {
        const q = filter.search.toLowerCase();
        list = list.filter(
          (p) =>
            p.patternName.toLowerCase().includes(q) ||
            (p.summary || "").toLowerCase().includes(q) ||
            (p.useCase || "").toLowerCase().includes(q)
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
        `/api/research/tech-trends?domain=code&weeks=4&only_emerging=true`
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
    const byCategory: Record<string, number> = {};
    for (const p of patterns) {
      byCategory[p.category] = (byCategory[p.category] || 0) + 1;
    }
    return {
      total: patterns.length,
      byCategory,
    };
  }, [patterns]);

  return (
    <div className="p-6 lg:p-8 max-w-[1400px] mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold" style={{ color: "var(--foreground)" }}>
          💻 코드 패턴 라이브러리
        </h1>
        <p
          className="text-sm mt-1"
          style={{ color: "var(--muted-foreground)" }}
        >
          매시간 GitHub / Hacker News / Stack Overflow / 한국 tech 블로그에서
          자동 수집한 재사용 패턴 — LLM 분류 후 CodePattern 으로 저장.
        </p>
      </div>

      {/* 떠오르는 기술 배너 */}
      {trends.length > 0 && (
        <div
          className="rounded-xl p-4 mb-6"
          style={{
            border: "1px solid #10b98166",
            background:
              "linear-gradient(135deg, rgba(16,185,129,0.08), rgba(99,102,241,0.06))",
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            <span className="text-base">🚀</span>
            <span
              className="text-sm font-semibold"
              style={{ color: "var(--foreground)" }}
            >
              이번 주 떠오르는 기술
            </span>
            <span className="text-[10px] opacity-60">
              (4주 baseline 대비 +30%↑, 3건 이상)
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {trends.map((t) => (
              <span
                key={t.id}
                className="text-xs px-3 py-1 rounded-full font-mono"
                style={{
                  background:
                    "linear-gradient(135deg, #10b981, #0891b2)",
                  color: "white",
                }}
                title={`${t.occurrences} occurrences this week`}
              >
                {t.keyword} +{t.velocityPct.toFixed(0)}%
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 통계 4박스 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <SmallStat label="전체 패턴" value={stats.total} color="#6366f1" />
        <SmallStat
          label="Hook"
          value={stats.byCategory.hook || 0}
          color="#0891b2"
        />
        <SmallStat
          label="Utility"
          value={stats.byCategory.utility || 0}
          color="#10b981"
        />
        <SmallStat
          label="Architecture"
          value={stats.byCategory.architecture || 0}
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
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label
              className="text-xs"
              style={{ color: "var(--muted-foreground)" }}
            >
              카테고리
            </label>
            <select
              value={filter.category}
              onChange={(e) =>
                setFilter({ ...filter, category: e.target.value })
              }
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
              style={{
                borderColor: "var(--border)",
                background: "var(--background)",
                color: "var(--foreground)",
              }}
            >
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.icon} {c.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              className="text-xs"
              style={{ color: "var(--muted-foreground)" }}
            >
              언어
            </label>
            <select
              value={filter.language}
              onChange={(e) =>
                setFilter({ ...filter, language: e.target.value })
              }
              className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
              style={{
                borderColor: "var(--border)",
                background: "var(--background)",
                color: "var(--foreground)",
              }}
            >
              <option value="">전체</option>
              {LANGUAGES.map((l) => (
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
              placeholder="패턴 이름, 요약, useCase..."
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
          조건에 맞는 코드 패턴이 없습니다.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {patterns.map((p) => {
            const cat = CATEGORIES.find((c) => c.value === p.category);
            return (
              <div
                key={p.id}
                className="rounded-xl p-4 flex flex-col gap-2"
                style={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <h3
                    className="font-semibold text-sm leading-tight"
                    style={{ color: "var(--foreground)" }}
                  >
                    {cat?.icon} {p.patternName}
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
                  {p.language && (
                    <code
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        background: "var(--muted)",
                        color: "var(--foreground)",
                      }}
                    >
                      {p.language}
                    </code>
                  )}
                  {p.framework && (
                    <code
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        background: "rgba(99,102,241,0.12)",
                        color: "#6366f1",
                      }}
                    >
                      {p.framework}
                    </code>
                  )}
                </div>
                <p
                  className="text-xs leading-relaxed"
                  style={{ color: "var(--muted-foreground)" }}
                >
                  {(p.summary || "").slice(0, 220)}
                  {(p.summary || "").length > 220 && "..."}
                </p>
                {p.useCase && (
                  <p
                    className="text-[11px] italic mt-auto pt-1"
                    style={{ color: "var(--muted-foreground)" }}
                  >
                    🎯 {p.useCase}
                  </p>
                )}
                {p.sourceUrl && (
                  <a
                    href={p.sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px]"
                    style={{ color: "#6366f1" }}
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
