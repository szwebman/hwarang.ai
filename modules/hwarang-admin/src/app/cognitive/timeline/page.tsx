"use client";

/**
 * Cognitive 타임라인 — 시간별 그룹 시각화.
 *
 * 가로축 = 시간(시간 단위), 세로축 = 시간 블록.
 * 각 점 = 결정 1개. 색상 = outcome_score (녹/황/적/회).
 * 호버: actor + decision 미리보기, 클릭: 모달.
 */

import { useEffect, useState } from "react";
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

const ACTORS = [
  { value: "master", label: "Master" },
  { value: "inter_agent_debate", label: "Inter-Agent" },
];

export default function CognitiveTimelinePage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [hours, setHours] = useState<number>(24);
  const [actor, setActor] = useState<string>("master");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Memory | null>(null);

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

  // 시간(hour) 단위 그룹화
  const grouped: Record<string, Memory[]> = {};
  memories.forEach((m) => {
    const date = new Date(m.timestamp);
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
      date.getDate(),
    ).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:00`;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(m);
  });

  const sortedKeys = Object.keys(grouped).sort().reverse();

  const dotColor = (s: number | null) =>
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
          <h1 className="text-2xl font-bold mt-1">Cognitive 타임라인</h1>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            시간별 결정 흐름. 색 = outcome score (녹 ≥ 0.7, 황 ≥ 0.4, 적 &lt; 0.4, 회 = 미평가).
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <select
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            className="px-3 py-2 rounded-lg border text-sm"
            style={{ borderColor: "var(--border)", background: "var(--background)" }}
          >
            {ACTORS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="px-3 py-2 rounded-lg border text-sm"
            style={{ borderColor: "var(--border)", background: "var(--background)" }}
          >
            <option value={6}>6시간</option>
            <option value={24}>24시간</option>
            <option value={72}>3일</option>
            <option value={168}>7일</option>
          </select>
        </div>
      </div>

      {/* 범례 */}
      <div className="flex gap-3 text-xs mb-4">
        {[
          ["#10b981", "좋음 (≥ 0.7)"],
          ["#f59e0b", "보통 (≥ 0.4)"],
          ["#ef4444", "나쁨 (< 0.4)"],
          ["#94a3b8", "미평가"],
        ].map(([c, l]) => (
          <div key={l} className="flex items-center gap-1.5">
            <span
              className="w-3 h-3 rounded-full inline-block"
              style={{ background: c }}
            />
            <span style={{ color: "var(--muted-foreground)" }}>{l}</span>
          </div>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-center py-12" style={{ color: "var(--muted-foreground)" }}>
          불러오는 중...
        </p>
      ) : sortedKeys.length === 0 ? (
        <p className="text-sm text-center py-12" style={{ color: "var(--muted-foreground)" }}>
          {hours}시간 내 사고 사이클 없음.
        </p>
      ) : (
        <div className="space-y-2">
          {sortedKeys.map((hour) => {
            const items = grouped[hour];
            return (
              <div
                key={hour}
                className="rounded-xl p-3 border"
                style={{ borderColor: "var(--border)", background: "var(--background)" }}
              >
                <div
                  className="flex items-center justify-between mb-2"
                  style={{ color: "var(--muted-foreground)" }}
                >
                  <div className="text-xs font-medium font-mono">{hour}</div>
                  <div className="text-[10px]">{items.length}건</div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {items.map((m) => {
                    const c = dotColor(m.outcomeScore ?? null);
                    return (
                      <button
                        key={m.id}
                        onClick={() => setSelected(m)}
                        className="text-[10px] px-2 py-1 rounded font-mono cursor-pointer hover:opacity-80 transition-opacity"
                        style={{
                          background: `${c}20`,
                          color: c,
                          border: `1px solid ${c}40`,
                        }}
                        title={`${m.actor}\n${(m.decision || "").slice(0, 200)}`}
                      >
                        {m.actor.slice(0, 10)} ·{" "}
                        {(m.actionTaken || "no_action").slice(0, 30)}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 상세 모달 */}
      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.5)" }}
          onClick={() => setSelected(null)}
        >
          <div
            className="rounded-xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto"
            style={{ background: "var(--background)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                  {new Date(selected.timestamp).toLocaleString("ko-KR")} · {selected.actor}
                </div>
                <div className="text-lg font-semibold mt-1">
                  {selected.actionTaken || "(no action)"}
                </div>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-2xl leading-none px-2"
                style={{ color: "var(--muted-foreground)" }}
              >
                ×
              </button>
            </div>
            <div className="space-y-3 text-sm">
              {selected.outcomeScore != null && (
                <div>
                  <strong>점수:</strong>{" "}
                  <span
                    className="px-2 py-0.5 rounded font-mono"
                    style={{
                      background: `${dotColor(selected.outcomeScore)}20`,
                      color: dotColor(selected.outcomeScore),
                    }}
                  >
                    {selected.outcomeScore.toFixed(2)}
                  </span>
                </div>
              )}
              <div>
                <strong>관찰:</strong>
                <pre
                  className="text-xs mt-1 p-3 rounded overflow-x-auto"
                  style={{ background: "var(--muted)" }}
                >
                  {JSON.stringify(selected.observed, null, 2)}
                </pre>
              </div>
              <div>
                <strong>추론:</strong>
                <p className="mt-1 whitespace-pre-wrap">{selected.reasoning}</p>
              </div>
              <div>
                <strong>결정:</strong>
                <p className="mt-1 whitespace-pre-wrap">{selected.decision}</p>
              </div>
              {selected.outcome && (
                <div>
                  <strong>결과:</strong>
                  <p className="mt-1 whitespace-pre-wrap">{selected.outcome}</p>
                </div>
              )}
              {selected.lesson && (
                <div>
                  <strong>교훈:</strong>
                  <p className="mt-1 whitespace-pre-wrap">{selected.lesson}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
