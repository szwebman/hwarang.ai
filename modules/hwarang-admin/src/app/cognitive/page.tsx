"use client";

/**
 * 화랑 HCL Phase 6 — Cognitive Layer 관리자 대시보드.
 *
 * 마스터/에이전트 자율 사고 사이클 모니터링 + 수동 제어.
 *  • 건강도 / 평균 점수 / 액션 다양성 / LLM 토큰 비용 (4 박스)
 *  • 즉시 사이클 트리거 + 비상 비활성/활성 토글
 *  • 최근 20 사이클 (관찰 / 추론 / 결정 / 결과 / 교훈)
 *  • 타임라인 / 토론 / 결정 통계 페이지로 이동
 *
 * 데이터: /api/cognitive/* (Next.js 프록시 → FastAPI)
 */

import { useEffect, useState } from "react";
import Link from "next/link";

interface CognitiveHealth {
  healthy: boolean;
  failure_rate: number;
  avg_outcome_score: number;
  action_diversity: number;
  most_common_action: string;
  cycles_24h: number;
}

interface CognitiveCost {
  estimated_tokens_today: number;
  limit: number;
  usage_pct: number;
  exceeded: boolean;
}

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

export default function CognitiveDashboard() {
  const [health, setHealth] = useState<CognitiveHealth | null>(null);
  const [cost, setCost] = useState<CognitiveCost | null>(null);
  const [enabled, setEnabled] = useState<boolean>(true);
  const [recent, setRecent] = useState<Memory[]>([]);
  const [actor, setActor] = useState<"master" | "inter_agent_debate">("master");
  const [triggering, setTriggering] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actor]);

  const fetchAll = async () => {
    setError(null);
    try {
      const healthResp = await fetch(`/api/cognitive/health?actor=${actor}`, {
        headers: authHeaders(),
        cache: "no-store",
      });
      if (healthResp.ok) {
        const healthData = await healthResp.json();
        setHealth(healthData.health || null);
        setCost(healthData.cost || null);
        if (typeof healthData.enabled === "boolean") setEnabled(healthData.enabled);
      }

      const memResp = await fetch(`/api/cognitive/memories?actor=${actor}&hours=24&limit=20`, {
        headers: authHeaders(),
        cache: "no-store",
      });
      if (memResp.ok) {
        const memData = await memResp.json();
        setRecent(memData.memories || []);
      }
    } catch (e: any) {
      setError(e?.message || "fetch 실패");
    } finally {
      setLoading(false);
    }
  };

  const triggerCycle = async () => {
    setTriggering(true);
    try {
      const resp = await fetch("/api/cognitive/cycle", {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || "사이클 트리거 실패");
      alert(
        `사이클 실행됨\n결정: ${data.decisions_made ?? data.decisions ?? 0}개\n실행: ${
          data.actions_executed ?? data.actions ?? 0
        }개`,
      );
      fetchAll();
    } catch (e: any) {
      alert(`실행 실패: ${e?.message || e}`);
    } finally {
      setTriggering(false);
    }
  };

  const toggleCognitive = async () => {
    const action = enabled ? "disable" : "enable";
    if (action === "disable" && !confirm("Cognitive 비활성화? 자동 사고가 멈춥니다.")) return;
    try {
      const resp = await fetch(`/api/cognitive/${action}?actor=${actor}`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ reason: "manual_toggle" }),
      });
      if (!resp.ok) throw new Error("토글 실패");
      setEnabled(!enabled);
      fetchAll();
    } catch (e: any) {
      alert(`토글 실패: ${e?.message || e}`);
    }
  };

  const scoreColor = (s: number | null | undefined) =>
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
          <h1 className="text-2xl font-bold">Cognitive Layer</h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted-foreground)" }}>
            마스터/에이전트 자율 사고 이력 + 모니터링
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <select
            value={actor}
            onChange={(e) => setActor(e.target.value as any)}
            className="px-3 py-2 rounded-lg border text-sm"
            style={{ borderColor: "var(--border)", background: "var(--background)" }}
          >
            <option value="master">Master</option>
            <option value="inter_agent_debate">Inter-Agent</option>
          </select>
          <button
            onClick={triggerCycle}
            disabled={triggering}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50"
            style={{ background: "var(--primary, #6366f1)" }}
          >
            {triggering ? "실행 중..." : "▶ 즉시 실행"}
          </button>
          <button
            onClick={toggleCognitive}
            className="px-4 py-2 rounded-lg text-sm font-medium"
            style={{ background: enabled ? "#10b981" : "#ef4444", color: "white" }}
          >
            {enabled ? "● 활성" : "● 비활성"}
          </button>
        </div>
      </div>

      {error && (
        <div
          className="mb-4 px-4 py-2 rounded-lg text-sm"
          style={{ background: "#fef2f2", color: "#991b1b", border: "1px solid #fecaca" }}
        >
          {error}
        </div>
      )}

      {/* 상단 4 박스: 건강 / 평균 점수 / 다양성 / 비용 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-6">
        <div
          className="rounded-xl p-4 border"
          style={{
            borderColor: health?.healthy ? "#10b981" : "#ef4444",
            background: "var(--background)",
          }}
        >
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>건강도</div>
          <div
            className="text-2xl font-bold"
            style={{ color: health?.healthy ? "#10b981" : "#ef4444" }}
          >
            {health == null ? "—" : health.healthy ? "● 정상" : "● 이상"}
          </div>
          <div className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
            실패율 {health == null ? "—" : `${(health.failure_rate * 100).toFixed(0)}%`}
          </div>
        </div>

        <div
          className="rounded-xl p-4 border"
          style={{ borderColor: "var(--border)", background: "var(--background)" }}
        >
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>평균 점수 (24h)</div>
          <div
            className="text-2xl font-bold"
            style={{ color: scoreColor(health?.avg_outcome_score ?? null) }}
          >
            {health == null ? "—" : health.avg_outcome_score.toFixed(2)}
          </div>
          <div className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
            {health == null ? "—" : `${health.cycles_24h} 사이클`}
          </div>
        </div>

        <div
          className="rounded-xl p-4 border"
          style={{ borderColor: "var(--border)", background: "var(--background)" }}
        >
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>액션 다양성</div>
          <div className="text-2xl font-bold">
            {health == null ? "—" : `${(health.action_diversity * 100).toFixed(0)}%`}
          </div>
          <div className="text-[10px] mt-1 truncate" style={{ color: "var(--muted-foreground)" }}>
            주요: {health?.most_common_action ? health.most_common_action.slice(0, 25) : "—"}
          </div>
        </div>

        <div
          className="rounded-xl p-4 border"
          style={{
            borderColor: cost?.exceeded ? "#ef4444" : "var(--border)",
            background: "var(--background)",
          }}
        >
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>LLM 토큰 (오늘)</div>
          <div
            className="text-2xl font-bold"
            style={{
              color:
                cost == null
                  ? undefined
                  : cost.usage_pct > 0.8
                  ? "#ef4444"
                  : cost.usage_pct > 0.5
                  ? "#f59e0b"
                  : "#10b981",
            }}
          >
            {cost == null ? "—" : `${(cost.estimated_tokens_today / 1000).toFixed(0)}K`}
          </div>
          <div className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
            {cost == null
              ? "—"
              : `${(cost.usage_pct * 100).toFixed(0)}% / ${(cost.limit / 1_000_000).toFixed(1)}M`}
          </div>
        </div>
      </div>

      {/* 빠른 링크 */}
      <div className="flex gap-2 mb-6 flex-wrap">
        <Link
          href="/cognitive/timeline"
          className="px-4 py-2 rounded-lg border text-sm hover:opacity-80"
          style={{ borderColor: "var(--border)", background: "var(--background)" }}
        >
          전체 타임라인
        </Link>
        <Link
          href="/cognitive/debates"
          className="px-4 py-2 rounded-lg border text-sm hover:opacity-80"
          style={{ borderColor: "var(--border)", background: "var(--background)" }}
        >
          토론 이력
        </Link>
        <Link
          href="/cognitive/decisions"
          className="px-4 py-2 rounded-lg border text-sm hover:opacity-80"
          style={{ borderColor: "var(--border)", background: "var(--background)" }}
        >
          결정 통계
        </Link>
      </div>

      {/* 최근 사이클 */}
      <div
        className="rounded-xl p-5 border"
        style={{ borderColor: "var(--border)", background: "var(--background)" }}
      >
        <h2 className="font-semibold mb-3">최근 사고 사이클 (20)</h2>
        {loading ? (
          <p className="text-sm text-center py-8" style={{ color: "var(--muted-foreground)" }}>
            불러오는 중...
          </p>
        ) : recent.length === 0 ? (
          <p className="text-sm text-center py-8" style={{ color: "var(--muted-foreground)" }}>
            아직 사이클 이력 없음.{" "}
            <button onClick={triggerCycle} className="underline">
              즉시 시작
            </button>
          </p>
        ) : (
          <div className="space-y-2">
            {recent.map((m) => (
              <details
                key={m.id}
                className="rounded-lg border p-3"
                style={{ borderColor: "var(--border)" }}
              >
                <summary className="cursor-pointer flex items-center gap-2">
                  <span
                    className="text-xs whitespace-nowrap"
                    style={{ color: "var(--muted-foreground)" }}
                  >
                    {new Date(m.timestamp).toLocaleString("ko-KR")}
                  </span>
                  {m.outcomeScore !== null && m.outcomeScore !== undefined && (
                    <span
                      className="text-xs px-2 py-0.5 rounded font-mono"
                      style={{
                        background:
                          m.outcomeScore > 0.7
                            ? "#dcfce7"
                            : m.outcomeScore > 0.4
                            ? "#fef3c7"
                            : "#fee2e2",
                        color:
                          m.outcomeScore > 0.7
                            ? "#166534"
                            : m.outcomeScore > 0.4
                            ? "#92400e"
                            : "#991b1b",
                      }}
                    >
                      {m.outcomeScore.toFixed(2)}
                    </span>
                  )}
                  <span className="text-sm flex-1 truncate">
                    {(m.actionTaken || "(no action)").slice(0, 100)}
                  </span>
                </summary>
                <div
                  className="mt-3 text-xs space-y-2"
                  style={{ color: "var(--muted-foreground)" }}
                >
                  <div>
                    <strong>관찰:</strong>
                    <pre
                      className="text-[10px] mt-1 p-2 rounded overflow-x-auto"
                      style={{ background: "var(--muted)" }}
                    >
                      {JSON.stringify(m.observed, null, 2).slice(0, 500)}
                    </pre>
                  </div>
                  <div>
                    <strong>추론:</strong> {(m.reasoning || "").slice(0, 600)}
                  </div>
                  <div>
                    <strong>결정:</strong> {(m.decision || "").slice(0, 600)}
                  </div>
                  {m.outcome && (
                    <div>
                      <strong>결과:</strong> {m.outcome.slice(0, 400)}
                    </div>
                  )}
                  {m.lesson && (
                    <div>
                      <strong>교훈:</strong> {m.lesson}
                    </div>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
