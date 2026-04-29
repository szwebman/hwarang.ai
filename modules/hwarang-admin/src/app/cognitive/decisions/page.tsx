"use client";

/**
 * 결정 통계 — 클라이언트 측 집계로 시각화.
 *  • 액션 종류별 빈도 (bar chart)
 *  • 액션별 평균 outcome score (bar chart)
 *  • 시간대별 결정 빈도 (24h heatmap)
 *  • 자주 배운 lesson top 10
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

interface Memory {
  id: string;
  actor: string;
  timestamp: string;
  observed: any;
  reasoning: string;
  decision: string;
  actionTaken: string | null;
  outcome: string | null;
  outcomeScore: number | null;
  lesson: string | null;
}

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function normalizeAction(a: string | null | undefined): string {
  if (!a) return "(no_action)";
  // 첫 토큰 / 콜론 / 공백 앞부분만 — 종류 분리
  const head = a.split(/[\s:({]/)[0];
  return head.slice(0, 40) || "(no_action)";
}

export default function CognitiveDecisionsPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [hours, setHours] = useState<number>(168);
  const [actor, setActor] = useState<string>("master");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hours, actor]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const r = await fetch(
        `/api/cognitive/memories?actor=${actor}&hours=${hours}&limit=500`,
        { headers: authHeaders(), cache: "no-store" },
      );
      const data = await r.json();
      setMemories(data.memories || []);
    } catch {
      setMemories([]);
    }
    setLoading(false);
  };

  // ───────── 집계 ─────────
  const actionStats = useMemo(() => {
    const counts: Record<string, { count: number; sum: number; n: number }> = {};
    for (const m of memories) {
      const k = normalizeAction(m.actionTaken);
      if (!counts[k]) counts[k] = { count: 0, sum: 0, n: 0 };
      counts[k].count += 1;
      if (m.outcomeScore != null) {
        counts[k].sum += m.outcomeScore;
        counts[k].n += 1;
      }
    }
    return Object.entries(counts)
      .map(([k, v]) => ({
        action: k,
        count: v.count,
        avgScore: v.n > 0 ? v.sum / v.n : null,
      }))
      .sort((a, b) => b.count - a.count);
  }, [memories]);

  const maxCount = actionStats.reduce((mx, s) => Math.max(mx, s.count), 1);

  const hourHeatmap = useMemo(() => {
    const counts = new Array(24).fill(0);
    for (const m of memories) {
      const h = new Date(m.timestamp).getHours();
      counts[h] += 1;
    }
    const max = Math.max(...counts, 1);
    return { counts, max };
  }, [memories]);

  const topLessons = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of memories) {
      if (!m.lesson) continue;
      const key = m.lesson.trim().slice(0, 200);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
  }, [memories]);

  const scoreColor = (s: number | null) =>
    s == null
      ? "#94a3b8"
      : s > 0.7
      ? "#10b981"
      : s > 0.4
      ? "#f59e0b"
      : "#ef4444";

  return (
    <div className="p-6 lg:p-8">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <Link
            href="/cognitive"
            className="text-xs"
            style={{ color: "var(--muted-foreground)" }}
          >
            ← Cognitive 대시보드
          </Link>
          <h1 className="text-2xl font-bold mt-1">결정 통계</h1>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            액션별 빈도/점수, 시간대 분포, 자주 배운 교훈.
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <select
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            className="px-3 py-2 rounded-lg border text-sm"
            style={{ borderColor: "var(--border)", background: "var(--background)" }}
          >
            <option value="master">Master</option>
            <option value="inter_agent_debate">Inter-Agent</option>
          </select>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="px-3 py-2 rounded-lg border text-sm"
            style={{ borderColor: "var(--border)", background: "var(--background)" }}
          >
            <option value={24}>24시간</option>
            <option value={72}>3일</option>
            <option value={168}>7일</option>
            <option value={720}>30일</option>
          </select>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-center py-12" style={{ color: "var(--muted-foreground)" }}>
          불러오는 중...
        </p>
      ) : memories.length === 0 ? (
        <p className="text-sm text-center py-12" style={{ color: "var(--muted-foreground)" }}>
          {hours}시간 내 결정 없음.
        </p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* 액션별 빈도 + 평균 점수 */}
          <div
            className="rounded-xl p-5 border"
            style={{ borderColor: "var(--border)", background: "var(--background)" }}
          >
            <h2 className="font-semibold mb-3">액션 종류별 빈도 / 평균 점수</h2>
            <div className="space-y-2">
              {actionStats.slice(0, 15).map((s) => (
                <div key={s.action} className="text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono truncate flex-1 mr-2">{s.action}</span>
                    <span style={{ color: "var(--muted-foreground)" }}>
                      {s.count}회{" "}
                      {s.avgScore != null && (
                        <span
                          className="font-mono ml-2"
                          style={{ color: scoreColor(s.avgScore) }}
                        >
                          {s.avgScore.toFixed(2)}
                        </span>
                      )}
                    </span>
                  </div>
                  <div
                    className="h-1.5 rounded-full overflow-hidden"
                    style={{ background: "var(--muted)" }}
                  >
                    <div
                      className="h-full"
                      style={{
                        width: `${(s.count / maxCount) * 100}%`,
                        background: scoreColor(s.avgScore),
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 시간대별 heatmap */}
          <div
            className="rounded-xl p-5 border"
            style={{ borderColor: "var(--border)", background: "var(--background)" }}
          >
            <h2 className="font-semibold mb-3">시간대별 결정 빈도 (0–23시)</h2>
            <div className="grid grid-cols-12 gap-1">
              {hourHeatmap.counts.map((c, h) => {
                const intensity = c / hourHeatmap.max;
                return (
                  <div
                    key={h}
                    className="rounded text-center text-[10px] py-2"
                    style={{
                      background: `rgba(99, 102, 241, ${0.1 + intensity * 0.9})`,
                      color: intensity > 0.5 ? "white" : "var(--muted-foreground)",
                    }}
                    title={`${h}시: ${c}건`}
                  >
                    <div className="font-mono">{h}</div>
                    <div className="font-bold">{c}</div>
                  </div>
                );
              })}
            </div>
            <div
              className="text-[10px] mt-2"
              style={{ color: "var(--muted-foreground)" }}
            >
              총 {memories.length}건 / {hours}시간. 색이 진할수록 많음.
            </div>
          </div>

          {/* 자주 배운 교훈 top 10 */}
          <div
            className="rounded-xl p-5 border lg:col-span-2"
            style={{ borderColor: "var(--border)", background: "var(--background)" }}
          >
            <h2 className="font-semibold mb-3">자주 배운 교훈 Top 10</h2>
            {topLessons.length === 0 ? (
              <p
                className="text-xs text-center py-6"
                style={{ color: "var(--muted-foreground)" }}
              >
                아직 교훈 기록 없음.
              </p>
            ) : (
              <ol className="space-y-2 text-sm">
                {topLessons.map(([lesson, count], idx) => (
                  <li
                    key={idx}
                    className="flex items-start gap-3 p-2 rounded"
                    style={{ background: "var(--muted)" }}
                  >
                    <span
                      className="text-xs px-2 py-0.5 rounded font-mono shrink-0"
                      style={{ background: "var(--background)" }}
                    >
                      {count}회
                    </span>
                    <span className="flex-1">{lesson}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
