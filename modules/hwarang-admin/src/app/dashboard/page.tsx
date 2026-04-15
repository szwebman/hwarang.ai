"use client";

import { useEffect, useState } from "react";

interface ClusterStatus {
  totalWorkers: number;
  idleWorkers: number;
  busyWorkers: number;
  totalGpus: number;
  models: Record<string, number>;
}

interface Stats {
  totalUsers: number;
  activeUsers: number;
  totalRequests: number;
  totalRevenue: number;
  requestsToday: number;
  newUsersToday: number;
}

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<Stats>({
    totalUsers: 0, activeUsers: 0, totalRequests: 0,
    totalRevenue: 0, requestsToday: 0, newUsersToday: 0,
  });
  const [cluster, setCluster] = useState<ClusterStatus>({
    totalWorkers: 0, idleWorkers: 0, busyWorkers: 0, totalGpus: 0, models: {},
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/stats")
      .then((r) => r.json())
      .then((data) => {
        setStats({
          totalUsers: data.users?.total || 0,
          activeUsers: data.users?.active || 0,
          newUsersToday: data.users?.newToday || 0,
          requestsToday: data.requests?.today || 0,
          totalRequests: data.requests?.thisMonth || 0,
          totalRevenue: data.revenue?.thisMonth || 0,
        });
        if (data.cluster) {
          setCluster({
            totalWorkers: data.cluster.workers?.total || 0,
            idleWorkers: data.cluster.workers?.idle || 0,
            busyWorkers: data.cluster.workers?.busy || 0,
            totalGpus: data.cluster.total_gpus || 0,
            models: data.cluster.models || {},
          });
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));

    // 10초마다 갱신
    const interval = setInterval(() => {
      fetch("/api/stats").then((r) => r.json()).then((data) => {
        setStats({
          totalUsers: data.users?.total || 0,
          activeUsers: data.users?.active || 0,
          newUsersToday: data.users?.newToday || 0,
          requestsToday: data.requests?.today || 0,
          totalRequests: data.requests?.thisMonth || 0,
          totalRevenue: data.revenue?.thisMonth || 0,
        });
      }).catch(() => {});
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen" style={{ background: "var(--muted)" }}>
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">관리자 대시보드</h1>
            <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
              Hwarang AI 시스템 전체 현황
            </p>
          </div>
          <div className="flex gap-2">
            <span className="px-3 py-1.5 rounded-full text-xs font-medium" style={{ background: "#dcfce7", color: "#166534" }}>
              시스템 정상
            </span>
          </div>
        </div>

        {/* 핵심 지표 카드 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {[
            { label: "전체 사용자", value: stats.totalUsers.toLocaleString(), change: `+${stats.newUsersToday} 오늘`, icon: "👥", color: "#6366f1" },
            { label: "오늘 요청", value: stats.requestsToday.toLocaleString(), change: "전일 대비 +12%", icon: "📊", color: "#8b5cf6" },
            { label: "이번 달 매출", value: `${(stats.totalRevenue / 10000).toFixed(0)}만원`, change: "전월 대비 +25%", icon: "💰", color: "#06b6d4" },
            { label: "활성 사용자", value: stats.activeUsers.toLocaleString(), change: `${(stats.activeUsers / stats.totalUsers * 100).toFixed(0)}% 활성률`, icon: "🟢", color: "#22c55e" },
          ].map((card) => (
            <div
              key={card.label}
              className="rounded-2xl p-5"
              style={{ background: "var(--background)", border: "1px solid var(--border)" }}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm" style={{ color: "var(--muted-foreground)" }}>{card.label}</span>
                <span className="text-xl">{card.icon}</span>
              </div>
              <div className="text-2xl font-bold">{card.value}</div>
              <div className="text-xs mt-1" style={{ color: card.color }}>{card.change}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 서버 클러스터 상태 */}
          <div className="rounded-2xl p-6" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">서버 클러스터</h2>
              <a href="/servers" className="text-xs" style={{ color: "var(--primary)" }}>상세 보기 →</a>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="rounded-xl p-4" style={{ background: "var(--muted)" }}>
                <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>서브 서버</div>
                <div className="text-xl font-bold mt-1">{cluster.totalWorkers}대</div>
                <div className="text-xs mt-1">
                  <span style={{ color: "#22c55e" }}>● {cluster.idleWorkers} 대기</span>
                  {" "}
                  <span style={{ color: "#f59e0b" }}>● {cluster.busyWorkers} 처리중</span>
                </div>
              </div>
              <div className="rounded-xl p-4" style={{ background: "var(--muted)" }}>
                <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>GPU</div>
                <div className="text-xl font-bold mt-1">{cluster.totalGpus}장</div>
                <div className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>RTX 5090</div>
              </div>
            </div>

            <div>
              <div className="text-xs font-semibold mb-2" style={{ color: "var(--muted-foreground)" }}>로드된 모델</div>
              {Object.entries(cluster.models).map(([model, count]) => (
                <div key={model} className="flex items-center justify-between py-1.5 text-sm">
                  <code className="text-xs px-2 py-0.5 rounded" style={{ background: "var(--muted)" }}>{model}</code>
                  <span>{count}개 서브</span>
                </div>
              ))}
            </div>
          </div>

          {/* 플랜별 사용자 */}
          <div className="rounded-2xl p-6" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">플랜별 사용자</h2>
              <a href="/plans" className="text-xs" style={{ color: "var(--primary)" }}>관리 →</a>
            </div>

            {[
              { plan: "Free", users: 890, revenue: 0, color: "#a3a3a3" },
              { plan: "Pro", users: 280, revenue: 8_120_000, color: "#6366f1" },
              { plan: "Business", users: 52, revenue: 5_148_000, color: "#8b5cf6" },
              { plan: "Enterprise", users: 12, revenue: 0, color: "#06b6d4" },
            ].map((item) => (
              <div key={item.plan} className="flex items-center justify-between py-3 border-b last:border-0" style={{ borderColor: "var(--border)" }}>
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full" style={{ background: item.color }} />
                  <span className="text-sm font-medium">{item.plan}</span>
                </div>
                <div className="flex items-center gap-6">
                  <span className="text-sm">{item.users}명</span>
                  <span className="text-sm font-medium" style={{ color: item.revenue > 0 ? "var(--foreground)" : "var(--muted-foreground)" }}>
                    {item.revenue > 0 ? `${(item.revenue / 10000).toFixed(0)}만원/월` : "무료"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 빠른 링크 */}
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3 mt-6">
          {[
            { href: "/servers", label: "서버 관리", icon: "🖥️" },
            { href: "/users", label: "유저 관리", icon: "👥" },
            { href: "/plans", label: "플랜 관리", icon: "💎" },
            { href: "/billing", label: "매출 현황", icon: "💳" },
            { href: "/models", label: "모델 관리", icon: "🧠" },
            { href: "/logs", label: "요청 로그", icon: "📋" },
          ].map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded-xl p-4 text-center hover:shadow-md transition-all"
              style={{ background: "var(--background)", border: "1px solid var(--border)" }}
            >
              <span className="text-2xl">{link.icon}</span>
              <div className="text-xs font-medium mt-2">{link.label}</div>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
