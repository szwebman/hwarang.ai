"use client";

import { useEffect, useState } from "react";

interface GridStats {
  // 전체 네트워크
  totalAgents: number;
  activeAgents: number;
  totalGPUs: number;
  totalVRAM_TB: number;
  networkTFLOPS: number;

  // 실시간 처리
  activeRequests: number;
  tokensPerSecond: number;
  requestsToday: number;
  tokensProcessedToday: number;

  // 토큰 경제
  totalTokensDistributed: number;
  totalTokensDistributedToday: number;
  averageRewardPerAgent: number;

  // GPU 분포
  gpuDistribution: { name: string; count: number; percent: number }[];

  // 최근 기여자 (익명)
  recentContributors: {
    id: string;
    gpu: string;
    tokensEarned: number;
    uptime: string;
    region: string;
  }[];

  // 리더보드
  topContributors: {
    rank: number;
    name: string;
    tokensThisMonth: number;
    gpu: string;
    streak: number;
  }[];
}

function formatNumber(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1e3).toFixed(1)}K`;
  return n.toLocaleString();
}

export default function CommunityPage() {
  const [stats, setStats] = useState<GridStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 5000); // 5초마다 갱신
    return () => clearInterval(interval);
  }, []);

  const fetchStats = async () => {
    try {
      const resp = await fetch("/api/community/grid-stats");
      if (resp.ok) {
        setStats(await resp.json());
      }
    } catch {}
    setLoading(false);
  };

  // 데모 데이터 (API 연결 전)
  const data: GridStats = stats || {
    totalAgents: 1247,
    activeAgents: 834,
    totalGPUs: 1312,
    totalVRAM_TB: 21.8,
    networkTFLOPS: 485.2,
    activeRequests: 127,
    tokensPerSecond: 45_230,
    requestsToday: 89_432,
    tokensProcessedToday: 234_500_000,
    totalTokensDistributed: 12_450_000_000,
    totalTokensDistributedToday: 45_230_000,
    averageRewardPerAgent: 54_280,
    gpuDistribution: [
      { name: "RTX 3060", count: 342, percent: 26 },
      { name: "RTX 4060/Ti", count: 287, percent: 22 },
      { name: "RTX 4070/Ti", count: 234, percent: 18 },
      { name: "RTX 3070/Ti", count: 178, percent: 14 },
      { name: "RTX 4080/90", count: 156, percent: 12 },
      { name: "RTX 5000+", count: 50, percent: 4 },
      { name: "기타", count: 65, percent: 4 },
    ],
    recentContributors: [
      { id: "agent-a1b2", gpu: "RTX 4070", tokensEarned: 342, uptime: "4h 23m", region: "서울" },
      { id: "agent-c3d4", gpu: "RTX 3060", tokensEarned: 128, uptime: "12h 05m", region: "부산" },
      { id: "agent-e5f6", gpu: "RTX 4090", tokensEarned: 891, uptime: "2h 15m", region: "대전" },
      { id: "agent-g7h8", gpu: "RTX 5090", tokensEarned: 1205, uptime: "1h 45m", region: "인천" },
      { id: "agent-i9j0", gpu: "RTX 4060 Ti", tokensEarned: 234, uptime: "8h 30m", region: "대구" },
    ],
    topContributors: [
      { rank: 1, name: "GPU마스터", tokensThisMonth: 892_340, gpu: "RTX 4090 ×2", streak: 45 },
      { rank: 2, name: "코딩왕", tokensThisMonth: 654_210, gpu: "RTX 5090", streak: 30 },
      { rank: 3, name: "AI파머", tokensThisMonth: 543_120, gpu: "RTX 4080", streak: 62 },
      { rank: 4, name: "새벽작업", tokensThisMonth: 432_100, gpu: "RTX 4070 Ti", streak: 28 },
      { rank: 5, name: "토큰부자", tokensThisMonth: 321_450, gpu: "RTX 4070", streak: 15 },
    ],
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      <div className="max-w-7xl mx-auto px-4 py-8">

        {/* Hero */}
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold mb-2">
            <span className="gradient-text">함께 만드는 AI</span>
          </h1>
          <p style={{ color: "var(--muted-foreground)" }}>
            지금 이 순간에도 {data.activeAgents.toLocaleString()}명이 GPU를 나누고 있습니다
          </p>
        </div>

        {/* 핵심 지표 카드 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {[
            { label: "활성 에이전트", value: data.activeAgents.toLocaleString(), sub: `/ ${data.totalAgents.toLocaleString()} 전체`, icon: "🟢", color: "#22c55e" },
            { label: "네트워크 GPU", value: `${data.totalGPUs.toLocaleString()}장`, sub: `${data.totalVRAM_TB.toFixed(1)}TB VRAM`, icon: "🖥️", color: "#6366f1" },
            { label: "실시간 처리", value: `${formatNumber(data.tokensPerSecond)} tok/s`, sub: `${data.activeRequests} 요청 처리 중`, icon: "⚡", color: "#f59e0b" },
            { label: "오늘 분배 토큰", value: formatNumber(data.totalTokensDistributedToday), sub: `누적 ${formatNumber(data.totalTokensDistributed)}`, icon: "🪙", color: "#8b5cf6" },
          ].map((card) => (
            <div key={card.label} className="rounded-2xl p-5 border" style={{ borderColor: "var(--border)" }}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>{card.label}</span>
                <span className="text-lg">{card.icon}</span>
              </div>
              <div className="text-2xl font-bold" style={{ color: card.color }}>{card.value}</div>
              <div className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>{card.sub}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* 실시간 기여 피드 */}
          <div className="lg:col-span-2 rounded-2xl border p-5" style={{ borderColor: "var(--border)" }}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold">실시간 기여 현황</h2>
              <span className="text-xs animate-pulse" style={{ color: "#22c55e" }}>● LIVE</span>
            </div>

            <div className="space-y-3">
              {data.recentContributors.map((c) => (
                <div key={c.id} className="flex items-center justify-between py-2 border-b last:border-0 animate-fade-in"
                  style={{ borderColor: "var(--border)" }}>
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold"
                      style={{ background: "var(--accent)", color: "var(--primary)" }}>
                      {c.region[0]}
                    </div>
                    <div>
                      <div className="text-sm font-medium">{c.id}</div>
                      <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                        {c.gpu} · {c.region} · 가동 {c.uptime}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-bold" style={{ color: "var(--primary)" }}>+{c.tokensEarned.toLocaleString()}</div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>토큰</div>
                  </div>
                </div>
              ))}
            </div>

            {/* 오늘 통계 */}
            <div className="mt-4 pt-4 border-t grid grid-cols-3 gap-4" style={{ borderColor: "var(--border)" }}>
              <div className="text-center">
                <div className="text-lg font-bold">{data.requestsToday.toLocaleString()}</div>
                <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>오늘 요청 처리</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold">{formatNumber(data.tokensProcessedToday)}</div>
                <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>오늘 처리 토큰</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold">{formatNumber(data.averageRewardPerAgent)}</div>
                <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>인당 평균 적립</div>
              </div>
            </div>
          </div>

          {/* GPU 분포 + 리더보드 */}
          <div className="space-y-6">

            {/* GPU 분포 */}
            <div className="rounded-2xl border p-5" style={{ borderColor: "var(--border)" }}>
              <h2 className="font-semibold mb-4">GPU 분포</h2>
              <div className="space-y-2">
                {data.gpuDistribution.map((gpu) => (
                  <div key={gpu.name}>
                    <div className="flex justify-between text-xs mb-1">
                      <span>{gpu.name}</span>
                      <span style={{ color: "var(--muted-foreground)" }}>{gpu.count}대 ({gpu.percent}%)</span>
                    </div>
                    <div className="h-2 rounded-full" style={{ background: "var(--muted)" }}>
                      <div className="h-2 rounded-full" style={{
                        width: `${gpu.percent}%`,
                        background: "var(--primary)",
                        opacity: 0.5 + gpu.percent / 60,
                      }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 월간 리더보드 */}
            <div className="rounded-2xl border p-5" style={{ borderColor: "var(--border)" }}>
              <h2 className="font-semibold mb-4">이번 달 Top 기여자</h2>
              <div className="space-y-3">
                {data.topContributors.map((c) => (
                  <div key={c.rank} className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{
                        background: c.rank <= 3 ? ["#fbbf24", "#d1d5db", "#cd7c2f"][c.rank - 1] : "var(--muted)",
                        color: c.rank <= 3 ? "#1a1a1a" : "var(--muted-foreground)",
                      }}>
                      {c.rank}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{c.name}</div>
                      <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                        {c.gpu} · 연속 {c.streak}일
                      </div>
                    </div>
                    <div className="text-sm font-bold" style={{ color: "var(--primary)" }}>
                      {formatNumber(c.tokensThisMonth)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* 네트워크 파워 */}
        <div className="mt-8 rounded-2xl p-8 text-center" style={{ background: "var(--muted)" }}>
          <h2 className="text-2xl font-bold mb-2">
            네트워크 총 연산력: <span style={{ color: "var(--primary)" }}>{data.networkTFLOPS.toFixed(0)} TFLOPS</span>
          </h2>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            {data.activeAgents.toLocaleString()}명의 GPU가 합쳐져 만드는 힘.
            이것은 H100 {Math.round(data.networkTFLOPS / 990)}대의 AI 연산력에 해당합니다.
          </p>
          <div className="mt-4">
            <button className="px-6 py-3 rounded-xl text-sm font-medium text-white gradient-bg hover:shadow-lg transition-all">
              나도 참여하기 →
            </button>
          </div>
        </div>

        {/* 메시지 */}
        <div className="mt-8 text-center">
          <p className="text-lg font-semibold mb-2">혼자서는 무리입니다.</p>
          <p style={{ color: "var(--muted-foreground)" }}>
            하지만 함께라면, 한국에서 진짜 쓸만한 AI를 만들 수 있습니다.
          </p>
        </div>
      </div>
    </div>
  );
}
