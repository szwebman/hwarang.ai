/**
 * HLKM 대시보드 — 전체 현황
 * - 4 StatCards (총 사실 / 오늘 업데이트 / 모순 대기 / 지식 공백)
 * - 도메인별 / 상태별 분포
 * - 최근 7일 검증 결과 (스택 막대)
 * - 시스템 헬스 + 수동 트리거
 *
 * Client Component (admin_token 사용 목적).
 */

"use client";

import { useEffect, useState } from "react";
import { adminFetch } from "@/lib/auth";
import StatCard from "./_components/StatCard";
import DomainBar from "./_components/DomainBar";
import TriggerPanel from "./TriggerPanel";

interface Overview {
  total_facts: number;
  facts_today: number;
  conflicts_open: number;
  gaps_open: number;
  growth?: { last_7d: number; last_30d: number };
  by_domain?: { domain: string; count: number }[];
  by_state?: { state: string; count: number }[];
}
interface Verification {
  days?: { date: string; unchanged: number; updated: number; invalidated: number; source_gone: number }[];
}
interface Health {
  aging_facts: number;
  broken_sources: number;
  scheduler_running: boolean;
  last_verify_run?: string;
  last_hrag_sync?: string;
  last_halflife_train?: string;
}

const STATE_LABEL: Record<string, string> = {
  CONFIRMED: "확정",
  PENDING: "대기",
  PREDICTED: "예측",
  EXPIRED: "만료",
  DISPUTED: "이의",
};

export default function HLKMDashboardPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [ov, ver, hl] = await Promise.all([
          adminFetch("/api/hlkm/stats/overview").then((r) => (r.ok ? r.json() : null)),
          adminFetch("/api/hlkm/stats/verification").then((r) => (r.ok ? r.json() : null)),
          adminFetch("/api/hlkm/stats/health").then((r) => (r.ok ? r.json() : null)),
        ]);
        setOverview(ov);
        setVerification(ver);
        setHealth(hl);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const ov = overview || { total_facts: 0, facts_today: 0, conflicts_open: 0, gaps_open: 0 };

  const domainItems = (ov.by_domain || []).map((d) => ({ label: d.domain, value: d.count }));
  const stateItems = (ov.by_state || []).map((s) => ({
    label: STATE_LABEL[s.state] || s.state,
    value: s.count,
    color:
      s.state === "CONFIRMED" ? "#16a34a" :
      s.state === "PENDING" ? "#d97706" :
      s.state === "PREDICTED" ? "#7c3aed" :
      s.state === "EXPIRED" ? "#64748b" :
      s.state === "DISPUTED" ? "#dc2626" : "#475569",
  }));
  const verDays = verification?.days || [];

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">HLKM 대시보드</h1>
          <p className="mt-1 text-sm text-gray-500">
            Living Knowledge Mesh 실시간 운영 현황 · {new Date().toLocaleDateString("ko-KR")}
          </p>
        </div>
        {loading && <span className="text-xs text-gray-400">불러오는 중...</span>}
      </header>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon="📚" label="총 사실 수" value={ov.total_facts} hint={ov.growth ? `지난 30일 +${ov.growth.last_30d.toLocaleString("ko-KR")}` : "누적"} accent="primary" delta={ov.growth?.last_7d} trend="up" />
        <StatCard icon="✨" label="오늘 업데이트" value={ov.facts_today} hint="금일 추가·갱신된 사실" accent="success" />
        <StatCard icon="⚡" label="모순 대기" value={ov.conflicts_open} hint="관리자 해결 필요" accent="warning" />
        <StatCard icon="🕳️" label="지식 공백" value={ov.gaps_open} hint="답변 실패 감지" accent="danger" />
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DomainBar title="도메인별 사실 분포" items={domainItems} orientation="horizontal" emptyMessage="아직 등록된 사실이 없습니다" />
        <DomainBar title="상태별 분포" items={stateItems} orientation="horizontal" emptyMessage="상태 데이터가 없습니다" />
      </section>

      <section className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">최근 7일 검증 결과</h3>
          <div className="flex items-center gap-3 text-xs text-gray-600">
            <span className="flex items-center gap-1"><i className="inline-block h-2 w-2 rounded-sm" style={{ background: "#16a34a" }} />유지</span>
            <span className="flex items-center gap-1"><i className="inline-block h-2 w-2 rounded-sm" style={{ background: "#2563eb" }} />갱신</span>
            <span className="flex items-center gap-1"><i className="inline-block h-2 w-2 rounded-sm" style={{ background: "#dc2626" }} />무효</span>
            <span className="flex items-center gap-1"><i className="inline-block h-2 w-2 rounded-sm" style={{ background: "#64748b" }} />출처 소실</span>
          </div>
        </div>
        {verDays.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-gray-400">아직 검증 결과가 없습니다</div>
        ) : (
          <VerificationStack days={verDays} />
        )}
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-xl border bg-white p-5 lg:col-span-2" style={{ borderColor: "#e5e7eb" }}>
          <h3 className="mb-4 text-sm font-semibold text-gray-900">시스템 헬스</h3>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
            <HealthStat label="노화된 사실" value={health?.aging_facts ?? 0} unit="건" />
            <HealthStat label="깨진 출처" value={health?.broken_sources ?? 0} unit="건" />
            <HealthStat label="스케줄러" value={health?.scheduler_running ? "가동 중" : "정지"} ok={health?.scheduler_running} />
          </div>
          <div className="mt-4 grid grid-cols-1 gap-2 text-xs text-gray-600 md:grid-cols-3">
            <Line label="마지막 자가 검증" value={health?.last_verify_run} />
            <Line label="마지막 HRAG 동기화" value={health?.last_hrag_sync} />
            <Line label="마지막 반감기 재학습" value={health?.last_halflife_train} />
          </div>
        </div>
        <TriggerPanel />
      </section>
    </div>
  );
}

function VerificationStack({ days }: { days: { date: string; unchanged: number; updated: number; invalidated: number; source_gone: number }[] }) {
  const width = 640;
  const height = 200;
  const barW = Math.max(24, width / days.length - 12);
  const max = Math.max(1, ...days.map((d) => d.unchanged + d.updated + d.invalidated + d.source_gone));

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height + 40}`} className="block">
      {days.map((d, idx) => {
        const x = idx * (barW + 12) + 8;
        const scale = height / max;
        let y = height;
        const segments = [
          { v: d.unchanged, c: "#16a34a" },
          { v: d.updated, c: "#2563eb" },
          { v: d.invalidated, c: "#dc2626" },
          { v: d.source_gone, c: "#64748b" },
        ];
        return (
          <g key={d.date}>
            {segments.map((s, i) => {
              const h = s.v * scale;
              y -= h;
              return <rect key={i} x={x} y={y} width={barW} height={h} fill={s.c} />;
            })}
            <text x={x + barW / 2} y={height + 18} textAnchor="middle" fontSize={10} fill="#64748b">
              {d.date.slice(5)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function HealthStat({ label, value, unit, ok }: { label: string; value: string | number; unit?: string; ok?: boolean }) {
  return (
    <div className="rounded-lg border p-3" style={{ borderColor: "#e5e7eb" }}>
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${ok === false ? "text-red-600" : ok === true ? "text-green-700" : "text-gray-900"}`}>
        {typeof value === "number" ? value.toLocaleString("ko-KR") : value}
        {unit && <span className="ml-1 text-xs text-gray-400">{unit}</span>}
      </div>
    </div>
  );
}

function Line({ label, value }: { label: string; value?: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-gray-500">{label}</span>
      <span className="font-mono text-gray-700">{value ? new Date(value).toLocaleString("ko-KR") : "—"}</span>
    </div>
  );
}
