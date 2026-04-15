"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface Stats {
  totalUsers: number;
  activeUsers: number;
  totalRequests: number;
  totalRevenue: number;
  requestsToday: number;
  newUsersToday: number;
}

interface ClusterStatus {
  totalWorkers: number;
  idleWorkers: number;
  busyWorkers: number;
  totalGpus: number;
  models: Record<string, number>;
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

  const parseStats = (data: any) => {
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
  };

  useEffect(() => {
    fetch("/api/stats")
      .then((r) => r.json())
      .then((data) => { parseStats(data); setLoading(false); })
      .catch(() => setLoading(false));

    const interval = setInterval(() => {
      fetch("/api/stats").then((r) => r.json()).then(parseStats).catch(() => {});
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const activeRate = stats.totalUsers > 0 ? (stats.activeUsers / stats.totalUsers * 100).toFixed(0) : "0";

  return (
    <div className="p-6 lg:p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">대시보드</h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted-foreground)" }}>
            Hwarang AI 시스템 전체 현황
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium"
            style={{ background: "rgba(16,185,129,0.1)", color: "#10b981" }}>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            시스템 정상
          </div>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          {
            label: "전체 사용자",
            value: stats.totalUsers.toLocaleString(),
            sub: `+${stats.newUsersToday} 오늘`,
            icon: (<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>),
            gradient: "linear-gradient(135deg, #6366f1, #8b5cf6)",
          },
          {
            label: "오늘 요청",
            value: stats.requestsToday.toLocaleString(),
            sub: `월 ${stats.totalRequests.toLocaleString()}건`,
            icon: (<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>),
            gradient: "linear-gradient(135deg, #8b5cf6, #a78bfa)",
          },
          {
            label: "이번 달 매출",
            value: stats.totalRevenue > 0 ? `${(stats.totalRevenue / 10000).toFixed(0)}만원` : "0원",
            sub: "전월 대비",
            icon: (<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" x2="12" y1="2" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>),
            gradient: "linear-gradient(135deg, #06b6d4, #22d3ee)",
          },
          {
            label: "활성 사용자",
            value: stats.activeUsers.toLocaleString(),
            sub: `활성률 ${activeRate}%`,
            icon: (<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="m9 12 2 2 4-4"/></svg>),
            gradient: "linear-gradient(135deg, #10b981, #34d399)",
          },
        ].map((card) => (
          <div key={card.label} className="p-5 relative overflow-hidden rounded-xl border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
            <div className="flex items-start justify-between">
              <div>
                <div className="text-xs font-medium mb-2" style={{ color: "var(--muted-foreground)" }}>{card.label}</div>
                <div className="text-2xl font-bold tracking-tight">{card.value}</div>
                <div className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>{card.sub}</div>
              </div>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white" style={{ background: card.gradient }}>
                {card.icon}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Server Cluster */}
        <div className="p-6 rounded-xl border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
          <div className="flex items-center justify-between mb-5">
            <h2 className="font-semibold">서버 클러스터</h2>
            <Link href="/servers" className="text-xs font-medium" style={{ color: "var(--primary)" }}>상세 보기 &rarr;</Link>
          </div>
          <div className="grid grid-cols-2 gap-3 mb-5">
            <div className="rounded-xl p-4" style={{ background: "var(--muted)" }}>
              <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>서브 서버</div>
              <div className="text-xl font-bold mt-1">{cluster.totalWorkers}대</div>
              <div className="flex items-center gap-3 mt-2 text-xs">
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full" style={{ background: "#10b981" }} />{cluster.idleWorkers} 대기</span>
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full" style={{ background: "#f59e0b" }} />{cluster.busyWorkers} 처리중</span>
              </div>
            </div>
            <div className="rounded-xl p-4" style={{ background: "var(--muted)" }}>
              <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>GPU</div>
              <div className="text-xl font-bold mt-1">{cluster.totalGpus}장</div>
              <div className="text-xs mt-2" style={{ color: "var(--muted-foreground)" }}>RTX 5090 32GB</div>
            </div>
          </div>
          <div>
            <div className="text-xs font-medium mb-3" style={{ color: "var(--muted-foreground)" }}>로드된 모델</div>
            {Object.keys(cluster.models).length === 0 ? (
              <div className="text-xs py-3 text-center" style={{ color: "var(--muted-foreground)" }}>모델 없음</div>
            ) : (
              Object.entries(cluster.models).map(([model, count]) => (
                <div key={model} className="flex items-center justify-between py-2 border-b last:border-0" style={{ borderColor: "var(--border)" }}>
                  <code className="text-xs px-2 py-1 rounded-md" style={{ background: "var(--muted)" }}>{model}</code>
                  <span className="text-xs font-medium">{count}개 인스턴스</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Quick Links */}
        <div className="p-6 rounded-xl border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
          <h2 className="font-semibold mb-5">빠른 메뉴</h2>
          <div className="grid grid-cols-3 gap-3">
            {[
              { href: "/users", label: "유저 관리", icon: (<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>), color: "#6366f1" },
              { href: "/plans", label: "플랜 관리", icon: (<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3h12l4 6-10 13L2 9Z"/></svg>), color: "#8b5cf6" },
              { href: "/models", label: "모델 관리", icon: (<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48 2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48 2.83-2.83"/></svg>), color: "#06b6d4" },
              { href: "/billing", label: "매출 현황", icon: (<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" x2="12" y1="2" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>), color: "#10b981" },
              { href: "/admins", label: "관리자 계정", icon: (<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/></svg>), color: "#f59e0b" },
              { href: "/roles", label: "롤 관리", icon: (<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/></svg>), color: "#ef4444" },
            ].map((link) => (
              <Link key={link.href} href={link.href}
                className="flex flex-col items-center gap-2 p-4 rounded-xl text-center hover:shadow-md transition-all"
                style={{ background: "var(--muted)" }}>
                <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: `${link.color}15`, color: link.color }}>
                  {link.icon}
                </div>
                <span className="text-xs font-medium">{link.label}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
