"use client";

import { useEffect, useState } from "react";

interface Agent {
  agent_id: string;
  agent_name: string;
  user_id: string;
  gpu_name: string;
  vram_gb: number;
  tier: string;
  status: string;
  online: boolean;
  reputation: number;
  contributions: number;
  total_reward: number;
  last_heartbeat: number;
}

interface GridStatus {
  total_agents: number;
  active_agents: number;
  agents_by_tier: { lite: number; standard: number; full: number };
  total_vram_gb: number;
  current_lora_version: number;
  current_benchmark: number;
  completed_rounds: number;
  total_rewards_issued: number;
  current_round: any;
  agents: Agent[];
}

export default function GridDashboard() {
  const [status, setStatus] = useState<GridStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000); // 10초마다 갱신
    return () => clearInterval(interval);
  }, []);

  async function fetchStatus() {
    try {
      const res = await fetch("/api/grid/status");
      if (res.ok) setStatus(await res.json());
    } catch (e) {
      console.error("Grid 상태 로드 실패:", e);
    } finally {
      setLoading(false);
    }
  }

  async function startRound() {
    if (!confirm("새 HFL 학습 라운드를 시작할까요?")) return;
    const res = await fetch("/api/grid/hfl/round/start", { method: "POST" });
    const data = await res.json();
    alert(`라운드 시작: ${data.participants || 0}개 에이전트 참여`);
    fetchStatus();
  }

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 bg-gray-200 rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!status) return <div className="p-6">Grid 데이터를 불러올 수 없습니다.</div>;

  const now = Date.now() / 1000;

  return (
    <div className="p-6 space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Grid 에이전트 관리</h1>
          <p className="text-gray-500">HFL 연합 학습 네트워크 현황</p>
        </div>
        <button
          onClick={startRound}
          className="rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          새 학습 라운드 시작
        </button>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="전체 에이전트"
          value={status.total_agents}
          sub={`온라인: ${status.active_agents}`}
          color="blue"
        />
        <StatCard
          label="총 GPU VRAM"
          value={`${status.total_vram_gb.toFixed(0)}GB`}
          sub={`Lite ${status.agents_by_tier.lite} / Std ${status.agents_by_tier.standard} / Full ${status.agents_by_tier.full}`}
          color="green"
        />
        <StatCard
          label="LoRA 버전"
          value={`v${status.current_lora_version}`}
          sub={`벤치마크: ${status.current_benchmark.toFixed(2)}`}
          color="purple"
        />
        <StatCard
          label="총 리워드"
          value={`${status.total_rewards_issued.toLocaleString()} HWR`}
          sub={`완료 라운드: ${status.completed_rounds}회`}
          color="orange"
        />
      </div>

      {/* 현재 라운드 */}
      {status.current_round && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 dark:bg-blue-900/20 dark:border-blue-800">
          <div className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-blue-500 animate-pulse" />
            <span className="font-semibold">학습 라운드 진행 중</span>
          </div>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            라운드: {status.current_round.round_id} /
            상태: {status.current_round.status} /
            제출: {status.current_round.submissions?.length || 0}/{status.current_round.participants?.length || 0}
          </div>
        </div>
      )}

      {/* 에이전트 테이블 */}
      <div className="rounded-xl border bg-white dark:bg-gray-800 dark:border-gray-700">
        <div className="border-b p-4">
          <h3 className="font-semibold">에이전트 목록</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="p-3">상태</th>
                <th className="p-3">이름</th>
                <th className="p-3">GPU</th>
                <th className="p-3">VRAM</th>
                <th className="p-3">티어</th>
                <th className="p-3">평판</th>
                <th className="p-3">기여</th>
                <th className="p-3">리워드</th>
                <th className="p-3">유저</th>
                <th className="p-3">마지막 접속</th>
              </tr>
            </thead>
            <tbody>
              {status.agents
                .sort((a, b) => b.last_heartbeat - a.last_heartbeat)
                .map((agent) => {
                  const isOnline = now - agent.last_heartbeat < 60;
                  const lastSeen = new Date(agent.last_heartbeat * 1000);

                  return (
                    <tr key={agent.agent_id} className="border-b hover:bg-gray-50 dark:hover:bg-gray-700/50">
                      <td className="p-3">
                        <span className={`inline-block h-2.5 w-2.5 rounded-full ${
                          isOnline
                            ? agent.status === "training" ? "bg-yellow-400 animate-pulse" : "bg-green-400"
                            : "bg-gray-300"
                        }`} />
                      </td>
                      <td className="p-3 font-medium">{agent.agent_name || agent.agent_id.slice(0, 12)}</td>
                      <td className="p-3">{agent.gpu_name}</td>
                      <td className="p-3">{agent.vram_gb}GB</td>
                      <td className="p-3">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          agent.tier === "full" ? "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300"
                          : agent.tier === "standard" ? "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300"
                          : "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300"
                        }`}>
                          {agent.tier}
                        </span>
                      </td>
                      <td className="p-3">
                        <div className="flex items-center gap-1">
                          <div className="h-1.5 w-16 rounded-full bg-gray-200 dark:bg-gray-600">
                            <div
                              className="h-full rounded-full bg-green-500"
                              style={{ width: `${agent.reputation * 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500">{(agent.reputation * 100).toFixed(0)}%</span>
                        </div>
                      </td>
                      <td className="p-3">{agent.contributions}</td>
                      <td className="p-3 font-medium">{agent.total_reward.toLocaleString()} HWR</td>
                      <td className="p-3 text-gray-500 text-xs">{agent.user_id?.slice(0, 8) || "-"}</td>
                      <td className="p-3 text-gray-500 text-xs">
                        {isOnline ? (
                          <span className="text-green-600">온라인</span>
                        ) : (
                          lastSeen.toLocaleString("ko-KR")
                        )}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        {status.agents.length === 0 && (
          <div className="p-8 text-center text-gray-500">
            등록된 에이전트가 없습니다
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color }: {
  label: string; value: string | number; sub: string; color: string;
}) {
  const colors: Record<string, string> = {
    blue: "bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400",
    green: "bg-green-50 text-green-600 dark:bg-green-900/30 dark:text-green-400",
    purple: "bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400",
    orange: "bg-orange-50 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400",
  };

  return (
    <div className="rounded-xl border bg-white p-4 dark:bg-gray-800 dark:border-gray-700">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
      <p className="mt-1 text-xs text-gray-400">{sub}</p>
    </div>
  );
}
