"use client";

/**
 * Inter-Agent 토론 이력.
 *
 * actor = "inter_agent_debate" 메모리만 표시.
 * 각 메모리의 observed/reasoning/decision 안에 multi-round 토론 결과가 들어있다.
 * 라운드/도메인/합의 여부를 풀어 시각화.
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

interface RoundOpinion {
  agent_id?: string;
  domain?: string;
  round_num?: number;
  confidence?: number;
  changed_from?: string | null;
}

function parseRounds(observed: any): RoundOpinion[][] {
  if (!observed) return [];
  // 다양한 직렬화 형태를 시도
  const candidates = [
    observed?.history,
    observed?.rounds,
    observed?.debate?.history,
    observed?.debate?.rounds,
  ];
  for (const c of candidates) {
    if (Array.isArray(c)) return c as RoundOpinion[][];
  }
  return [];
}

export default function CognitiveDebatesPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [hours, setHours] = useState<number>(168);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hours]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const r = await fetch(
        `/api/cognitive/memories?actor=inter_agent_debate&hours=${hours}&limit=100`,
        { headers: authHeaders(), cache: "no-store" },
      );
      const data = await r.json();
      setMemories(data.memories || []);
    } catch {
      setMemories([]);
    }
    setLoading(false);
  };

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
          <h1 className="text-2xl font-bold mt-1">Inter-Agent 토론</h1>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            도메인 전문가 에이전트 다회차 토론 이력. 라운드별 의견과 합의 여부.
          </p>
        </div>
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

      {loading ? (
        <p className="text-sm text-center py-12" style={{ color: "var(--muted-foreground)" }}>
          불러오는 중...
        </p>
      ) : memories.length === 0 ? (
        <p className="text-sm text-center py-12" style={{ color: "var(--muted-foreground)" }}>
          {hours}시간 내 토론 이력 없음.
        </p>
      ) : (
        <div className="space-y-3">
          {memories.map((m) => {
            const rounds = parseRounds(m.observed);
            const question =
              m.observed?.question ||
              m.observed?.debate?.question ||
              "(질문 미기록)";
            const consensus =
              m.observed?.consensus_reached ?? m.observed?.debate?.consensus_reached;
            const isOpen = expanded === m.id;

            return (
              <div
                key={m.id}
                className="rounded-xl border"
                style={{ borderColor: "var(--border)", background: "var(--background)" }}
              >
                <button
                  onClick={() => setExpanded(isOpen ? null : m.id)}
                  className="w-full text-left p-4 flex items-center gap-3"
                >
                  <span
                    className="text-xs px-2 py-0.5 rounded font-mono"
                    style={{
                      background: consensus ? "#dcfce7" : "#fef3c7",
                      color: consensus ? "#166534" : "#92400e",
                    }}
                  >
                    {consensus ? "합의" : "미합의"}
                  </span>
                  <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                    {new Date(m.timestamp).toLocaleString("ko-KR")}
                  </span>
                  <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                    {rounds.length} 라운드
                  </span>
                  <span className="text-sm flex-1 truncate font-medium">
                    {String(question).slice(0, 120)}
                  </span>
                  <span style={{ color: "var(--muted-foreground)" }}>{isOpen ? "−" : "+"}</span>
                </button>

                {isOpen && (
                  <div
                    className="px-4 pb-4 border-t pt-4 space-y-4"
                    style={{ borderColor: "var(--border)" }}
                  >
                    <div className="text-sm">
                      <strong>질문:</strong> {String(question)}
                    </div>

                    {/* 라운드 트리 */}
                    {rounds.length > 0 ? (
                      <div className="space-y-3">
                        {rounds.map((roundOps, rIdx) => (
                          <div key={rIdx}>
                            <div
                              className="text-xs font-semibold mb-2"
                              style={{ color: "var(--muted-foreground)" }}
                            >
                              라운드 {rIdx + 1}
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                              {roundOps.map((op, idx) => {
                                const conf = op.confidence ?? 0;
                                const confColor =
                                  conf > 0.7
                                    ? "#10b981"
                                    : conf > 0.4
                                    ? "#f59e0b"
                                    : "#ef4444";
                                return (
                                  <div
                                    key={idx}
                                    className="rounded-lg p-3 text-xs"
                                    style={{
                                      background: "var(--muted)",
                                      borderLeft: `3px solid ${confColor}`,
                                    }}
                                  >
                                    <div className="flex items-center justify-between mb-1">
                                      <strong>{op.agent_id || "agent_?"}</strong>
                                      <span
                                        className="font-mono"
                                        style={{ color: confColor }}
                                      >
                                        {(conf * 100).toFixed(0)}%
                                      </span>
                                    </div>
                                    <div style={{ color: "var(--muted-foreground)" }}>
                                      도메인: {op.domain || "—"}
                                    </div>
                                    {op.changed_from && (
                                      <div
                                        className="mt-1 text-[10px]"
                                        style={{ color: "var(--muted-foreground)" }}
                                      >
                                        ← 변경: {op.changed_from}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div
                        className="text-xs italic"
                        style={{ color: "var(--muted-foreground)" }}
                      >
                        라운드 상세 미기록.
                      </div>
                    )}

                    {/* 추론 / 결정 / 교훈 */}
                    <div className="space-y-2 text-xs">
                      <div>
                        <strong>요약/추론:</strong>
                        <p
                          className="mt-1 whitespace-pre-wrap"
                          style={{ color: "var(--muted-foreground)" }}
                        >
                          {(m.reasoning || "").slice(0, 800)}
                        </p>
                      </div>
                      <div>
                        <strong>결정:</strong>
                        <p
                          className="mt-1 whitespace-pre-wrap"
                          style={{ color: "var(--muted-foreground)" }}
                        >
                          {(m.decision || "").slice(0, 800)}
                        </p>
                      </div>
                      {m.lesson && (
                        <div>
                          <strong>교훈:</strong>
                          <p className="mt-1" style={{ color: "var(--muted-foreground)" }}>
                            {m.lesson}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
