"use client";

/**
 * Research Engine — 대시보드
 *
 * - 상단 4개 통계 카드 (어제 수집 / 이번 주 처리 / 평균 적용성 / 대기 중 application)
 * - 최근 7일 신규 paper 그래프 (간단 bar)
 * - 떠오르는 트렌드 top 10 카드 (PaperTrend.isEmerging=true)
 * - 검토 대기 applications top 5
 * - 빠른 액션: "지금 수집 트리거" / "지금 트렌드 분석" / "지금 적용 분석"
 *
 * 모든 데이터는 /api/research/* 프록시 → FastAPI Research Engine.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { adminFetch } from "@/lib/auth";

interface Paper {
  id: string;
  arxivId: string | null;
  title: string;
  authors: string[];
  status: string;
  applicabilityScore: number | null;
  applicableModules: string[];
  publishedAt: string;
  createdAt: string;
  koreanSummary: string | null;
}

interface Trend {
  id: string;
  weekStart: string;
  keyword: string;
  paperCount: number;
  velocityPct: number;
  isEmerging: boolean;
  topPapers: string[];
}

interface AppItem {
  id: string;
  paperId: string;
  module: string;
  description: string;
  status: string;
  createdAt: string;
  paper?: Paper;
}

export default function ResearchDashboardPage() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [trends, setTrends] = useState<Trend[]>([]);
  const [pendingApps, setPendingApps] = useState<AppItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionRunning, setActionRunning] = useState<string | null>(null);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pRes, tRes, aRes] = await Promise.all([
        adminFetch("/api/research/papers?limit=200"),
        adminFetch("/api/research/trends?weeks=4&only_emerging=false"),
        adminFetch("/api/research/applications?status=proposed&limit=5"),
      ]);
      const pData = pRes.ok ? await pRes.json() : { papers: [] };
      const tData = tRes.ok ? await tRes.json() : { trends: [] };
      const aData = aRes.ok ? await aRes.json() : { applications: [] };
      setPapers(pData.papers || []);
      setTrends(tData.trends || []);
      setPendingApps(aData.applications || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // ── 토스트 자동 사라짐 ──
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  const triggerAction = async (label: string, url: string) => {
    setActionRunning(label);
    try {
      const resp = await adminFetch(url, { method: "POST" });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(body.error || `HTTP ${resp.status}`);
      setToast({
        ok: true,
        text: `${label} 완료 — ${JSON.stringify(body).slice(0, 120)}`,
      });
      load();
    } catch (e: any) {
      setToast({ ok: false, text: `${label} 실패: ${e?.message || e}` });
    } finally {
      setActionRunning(null);
    }
  };

  // ── 통계 ─────────────────────────────────────────
  const stats = useMemo(() => {
    const dayAgo = Date.now() - 24 * 3600 * 1000;
    const weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
    const yesterday = papers.filter(
      (p) => new Date(p.createdAt).getTime() > dayAgo
    ).length;
    const thisWeek = papers.filter(
      (p) => new Date(p.createdAt).getTime() > weekAgo
    ).length;
    const scored = papers.filter((p) => p.applicabilityScore != null);
    const avgScore =
      scored.length === 0
        ? 0
        : scored.reduce((s, p) => s + (p.applicabilityScore || 0), 0) /
          scored.length;
    return {
      yesterday,
      thisWeek,
      avgScore,
      pendingApps: pendingApps.length,
    };
  }, [papers, pendingApps]);

  // ── 최근 7일 bar 데이터 ───────────────────────────
  const dailyBuckets = useMemo(() => {
    const out: { day: string; count: number }[] = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(Date.now() - i * 24 * 3600 * 1000);
      const key = d.toISOString().slice(0, 10);
      const label = `${d.getMonth() + 1}/${d.getDate()}`;
      const count = papers.filter(
        (p) => p.createdAt.slice(0, 10) === key
      ).length;
      out.push({ day: label, count });
    }
    return out;
  }, [papers]);

  const maxBucket = Math.max(1, ...dailyBuckets.map((b) => b.count));

  // ── 트렌드 정렬 (최신 주 + emerging 우선) ────────
  const topTrends = useMemo(() => {
    const sorted = [...trends].sort((a, b) => {
      if (a.isEmerging !== b.isEmerging) return a.isEmerging ? -1 : 1;
      return b.velocityPct - a.velocityPct;
    });
    return sorted.slice(0, 10);
  }, [trends]);

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1
            className="text-2xl font-bold"
            style={{ color: "var(--foreground)" }}
          >
            Research Engine
          </h1>
          <p
            className="text-sm mt-1"
            style={{ color: "var(--muted-foreground)" }}
          >
            arXiv → 한국어 요약 → 화랑 적용 자동 제안. 매일 06:00 KST 수집,
            매 6시간 적용 분석.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            href="/research/papers"
            className="px-3 py-2 rounded-lg text-sm"
            style={{ background: "var(--muted)", color: "var(--foreground)" }}
          >
            논문 목록 →
          </Link>
          <Link
            href="/research/applications"
            className="px-3 py-2 rounded-lg text-sm font-medium text-white"
            style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}
          >
            적용 검토 ({pendingApps.length}) →
          </Link>
        </div>
      </div>

      {/* 토스트 */}
      {toast && (
        <div
          className="mb-4 px-4 py-2.5 rounded-lg text-sm"
          style={{
            background: toast.ok ? "rgba(16,185,129,0.12)" : "rgba(220,38,38,0.12)",
            color: toast.ok ? "#10b981" : "#dc2626",
            border: `1px solid ${toast.ok ? "#10b98144" : "#dc262644"}`,
          }}
        >
          {toast.text}
        </div>
      )}

      {/* 통계 4박스 */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard
          label="어제 수집"
          value={stats.yesterday}
          color="#6366f1"
          unit="건"
        />
        <StatCard
          label="이번 주 처리"
          value={stats.thisWeek}
          color="#0891b2"
          unit="건"
        />
        <StatCard
          label="평균 적용성"
          value={`${(stats.avgScore * 100).toFixed(0)}`}
          color={
            stats.avgScore > 0.7
              ? "#10b981"
              : stats.avgScore > 0.4
                ? "#ca8a04"
                : "#dc2626"
          }
          unit="/ 100"
        />
        <StatCard
          label="대기 중 application"
          value={stats.pendingApps}
          color="#a855f7"
          unit="건"
        />
      </div>

      {/* 빠른 액션 */}
      <div
        className="rounded-xl p-4 mb-6 flex flex-wrap items-center gap-3"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
        }}
      >
        <span
          className="text-[11px] uppercase tracking-wider opacity-60 mr-2"
        >
          빠른 액션
        </span>
        <ActionButton
          label="요약 (parsed→summarized)"
          running={actionRunning === "요약"}
          onClick={() => triggerAction("요약", "/api/research/summarize")}
        />
        <ActionButton
          label="트렌드 분석"
          running={actionRunning === "트렌드 분석"}
          onClick={() =>
            triggerAction("트렌드 분석", "/api/research/trends/analyze")
          }
        />
        <ActionButton
          label="적용 분석"
          running={actionRunning === "적용 분석"}
          onClick={() =>
            triggerAction("적용 분석", "/api/research/applications/analyze")
          }
          highlight
        />
        <button
          onClick={load}
          className="ml-auto px-3 py-1.5 rounded text-xs"
          style={{ background: "var(--muted)", color: "var(--foreground)" }}
        >
          🔄 새로고침
        </button>
      </div>

      <div className="grid grid-cols-12 gap-4 mb-6">
        {/* 최근 7일 bar */}
        <div
          className="col-span-7 rounded-xl p-5"
          style={{
            background: "var(--card)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="flex items-center justify-between mb-4">
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--foreground)" }}
            >
              최근 7일 신규 논문
            </h3>
            <span className="text-[11px] opacity-60">
              총 {dailyBuckets.reduce((s, b) => s + b.count, 0)}건
            </span>
          </div>
          <div className="flex items-end gap-2 h-40">
            {dailyBuckets.map((b) => {
              const h = (b.count / maxBucket) * 100;
              return (
                <div
                  key={b.day}
                  className="flex-1 flex flex-col items-center gap-1"
                >
                  <div className="text-[10px] opacity-70">{b.count}</div>
                  <div
                    className="w-full rounded-t"
                    style={{
                      height: `${Math.max(2, h)}%`,
                      background:
                        "linear-gradient(180deg, #8b5cf6, #6366f1)",
                      minHeight: 2,
                    }}
                  />
                  <div className="text-[10px] opacity-60">{b.day}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 떠오르는 트렌드 */}
        <div
          className="col-span-5 rounded-xl p-5"
          style={{
            background: "var(--card)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="flex items-center justify-between mb-4">
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--foreground)" }}
            >
              떠오르는 키워드
            </h3>
            <span className="text-[11px] opacity-60">Top 10</span>
          </div>
          {loading ? (
            <div className="text-center py-8 opacity-60 text-xs">
              로딩 중...
            </div>
          ) : topTrends.length === 0 ? (
            <div className="text-center py-8 opacity-60 text-xs">
              아직 트렌드 데이터가 없습니다.
            </div>
          ) : (
            <ul className="space-y-1.5">
              {topTrends.map((t) => (
                <li
                  key={t.id}
                  className="flex items-center justify-between text-xs"
                >
                  <span className="flex items-center gap-1.5">
                    {t.isEmerging && (
                      <span
                        className="text-[9px] px-1 py-0.5 rounded font-bold"
                        style={{
                          background: "rgba(220,38,38,0.15)",
                          color: "#dc2626",
                        }}
                      >
                        HOT
                      </span>
                    )}
                    <span style={{ color: "var(--foreground)" }}>
                      {t.keyword}
                    </span>
                  </span>
                  <span
                    className="font-mono"
                    style={{
                      color:
                        t.velocityPct > 30
                          ? "#10b981"
                          : t.velocityPct > 0
                            ? "#0891b2"
                            : "var(--muted-foreground)",
                    }}
                  >
                    {t.paperCount}건 ·{" "}
                    {t.velocityPct >= 0 ? "+" : ""}
                    {t.velocityPct.toFixed(0)}%
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* 검토 대기 application top 5 */}
      <div
        className="rounded-xl p-5"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3
            className="text-sm font-semibold"
            style={{ color: "var(--foreground)" }}
          >
            검토 대기 적용 제안
          </h3>
          <Link
            href="/research/applications"
            className="text-xs"
            style={{ color: "#6366f1" }}
          >
            전체 보기 →
          </Link>
        </div>
        {loading ? (
          <div className="text-center py-8 opacity-60 text-xs">
            로딩 중...
          </div>
        ) : pendingApps.length === 0 ? (
          <div className="text-center py-8 opacity-60 text-xs">
            대기 중인 제안이 없습니다.
          </div>
        ) : (
          <div className="space-y-2">
            {pendingApps.map((a) => (
              <Link
                key={a.id}
                href="/research/applications"
                className="block rounded-lg p-3 hover:opacity-90"
                style={{
                  background: "var(--muted)",
                  border: "1px solid var(--border)",
                }}
              >
                <div className="flex items-start justify-between gap-3 mb-1">
                  <span
                    className="text-sm font-medium truncate"
                    style={{ color: "var(--foreground)" }}
                  >
                    {a.paper?.title || a.paperId}
                  </span>
                  <span
                    className="text-[10px] px-2 py-0.5 rounded shrink-0"
                    style={{
                      background: "rgba(99,102,241,0.15)",
                      color: "#6366f1",
                    }}
                  >
                    {a.module}
                  </span>
                </div>
                <p
                  className="text-xs line-clamp-2 opacity-75"
                  style={{ color: "var(--foreground)" }}
                >
                  {a.description}
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
  unit,
}: {
  label: string;
  value: number | string;
  color: string;
  unit?: string;
}) {
  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderLeft: `4px solid ${color}`,
      }}
    >
      <div className="text-[11px] uppercase tracking-wider opacity-60 mb-1.5">
        {label}
      </div>
      <div className="flex items-baseline gap-1.5">
        <div className="text-2xl font-bold" style={{ color }}>
          {value}
        </div>
        {unit && (
          <span
            className="text-[11px]"
            style={{ color: "var(--muted-foreground)" }}
          >
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}

function ActionButton({
  label,
  running,
  onClick,
  highlight,
}: {
  label: string;
  running: boolean;
  onClick: () => void;
  highlight?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={running}
      className="px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50"
      style={
        highlight
          ? {
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
              color: "#fff",
            }
          : {
              background: "rgba(99,102,241,0.12)",
              color: "#6366f1",
            }
      }
    >
      {running ? "실행 중..." : label}
    </button>
  );
}
