"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 기여자 관리
 * - Tier 분포 통계
 * - 리더보드 (reputation/correctContribs/totalEarned 정렬)
 * - 각 user: tier 배지, KYC 여부, stakedBalance, 최근 활동
 * - 승급/강등 수동 버튼 (admin)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface ContributorRow {
  userId: string;
  tier: "SUSPENDED" | "BRONZE" | "SILVER" | "GOLD" | "DIAMOND";
  reputation: number;
  kycVerified?: boolean;
  stakedBalance?: number;
  correctContribs?: number;
  totalEarned?: number;
  expertTags?: string[];
  lastActiveAt?: string | null;
}

type OrderBy = "reputation" | "correctContribs" | "totalEarned";

const TIER_STYLE: Record<string, { label: string; color: string; bg: string; emoji: string }> = {
  SUSPENDED: { label: "정지", color: "#7f1d1d", bg: "#fecaca", emoji: "⛔" },
  BRONZE: { label: "Bronze", color: "#78350f", bg: "#fed7aa", emoji: "🥉" },
  SILVER: { label: "Silver", color: "#475569", bg: "#e2e8f0", emoji: "🥈" },
  GOLD: { label: "Gold", color: "#854d0e", bg: "#fef9c3", emoji: "🥇" },
  DIAMOND: { label: "Diamond", color: "#0c4a6e", bg: "#e0f2fe", emoji: "💎" },
};

export default function ContributorsPage() {
  const [contribs, setContribs] = useState<ContributorRow[]>([]);
  const [distribution, setDistribution] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [orderBy, setOrderBy] = useState<OrderBy>("reputation");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const loadLeaderboard = useCallback(async () => {
    const qs = new URLSearchParams({ by: orderBy, limit: "100" });
    const resp = await adminFetch(`/api/knowledge/tier/leaderboard?${qs}`);
    if (resp.ok) setContribs(await resp.json());
    else setContribs([]);
  }, [orderBy]);

  const loadDistribution = useCallback(async () => {
    const resp = await adminFetch("/api/knowledge/tier/distribution");
    if (resp.ok) setDistribution(await resp.json());
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([loadLeaderboard(), loadDistribution()]);
    } finally {
      setLoading(false);
    }
  }, [loadLeaderboard, loadDistribution]);

  useEffect(() => {
    reload();
  }, [reload]);

  const evaluate = async (userId: string) => {
    setBusy(userId);
    try {
      const resp = await adminFetch(`/api/knowledge/tier/evaluate/${encodeURIComponent(userId)}`, {
        method: "POST",
      });
      const data = await resp.json();
      setMessage({
        ok: true,
        text: `Tier 평가 완료 — ${data.new_tier ? `새 tier: ${data.new_tier}` : "변경 없음"}`,
      });
      loadLeaderboard();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const autoPromote = async () => {
    setBusy("auto");
    try {
      const resp = await adminFetch("/api/knowledge/tier/auto-promote", { method: "POST" });
      const data = await resp.json();
      setMessage({ ok: true, text: `자동 승급 완료: ${JSON.stringify(data)}` });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const totalCount = useMemo(
    () => Object.values(distribution).reduce((a, b) => a + b, 0),
    [distribution]
  );
  const diamondCount = distribution.DIAMOND || 0;
  const kycVerified = contribs.filter((c) => c.kycVerified).length;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">기여자 관리</h1>
          <p className="mt-1 text-sm text-gray-500">
            Tier 분포, 리더보드, 개별 기여자 tier 재평가.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={autoPromote}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy === "auto" ? "..." : "일괄 자동 승급"}
          </button>
          <button
            onClick={reload}
            disabled={loading}
            className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb" }}
          >
            새로고침
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="총 기여자" value={totalCount} accent="primary" />
        <StatCard label="Diamond" value={diamondCount} accent="success" hint="분쟁 투표 가능" />
        <StatCard label="KYC 인증 (상위)" value={kycVerified} accent="neutral" />
        <StatCard label="리더보드 상위" value={contribs.length} accent="neutral" />
      </div>

      {/* Tier 분포 바 */}
      <section className="rounded-xl border bg-white p-4" style={{ borderColor: "#e5e7eb" }}>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">Tier 분포</h2>
        <div className="space-y-2">
          {(["DIAMOND", "GOLD", "SILVER", "BRONZE", "SUSPENDED"] as const).map((tier) => {
            const count = distribution[tier] || 0;
            const pct = totalCount > 0 ? (count / totalCount) * 100 : 0;
            const s = TIER_STYLE[tier];
            return (
              <div key={tier} className="flex items-center gap-3">
                <div className="w-24 text-xs font-medium" style={{ color: s.color }}>
                  {s.emoji} {s.label}
                </div>
                <div className="relative h-4 flex-1 overflow-hidden rounded-full" style={{ background: "#f1f5f9" }}>
                  <div
                    className="absolute left-0 top-0 h-full rounded-full"
                    style={{ width: `${pct}%`, background: s.bg }}
                  />
                </div>
                <div className="w-16 text-right text-xs tabular-nums text-gray-700">
                  {count.toLocaleString("ko-KR")} ({pct.toFixed(1)}%)
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {message && (
        <div
          className="rounded-lg border p-3 text-sm"
          style={{
            borderColor: message.ok ? "#bbf7d0" : "#fecaca",
            background: message.ok ? "#f0fdf4" : "#fef2f2",
            color: message.ok ? "#166534" : "#991b1b",
          }}
        >
          {message.text}
        </div>
      )}

      {/* 필터 */}
      <section className="flex items-center gap-4 rounded-xl border bg-white p-3" style={{ borderColor: "#e5e7eb" }}>
        <label className="flex items-center gap-2">
          <span className="text-xs text-gray-600">정렬</span>
          <select
            value={orderBy}
            onChange={(e) => setOrderBy(e.target.value as OrderBy)}
            className="rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb" }}
          >
            <option value="reputation">평판순</option>
            <option value="correctContribs">정확 기여순</option>
            <option value="totalEarned">총 수익순</option>
          </select>
        </label>
        <span className="ml-auto text-xs text-gray-500">{contribs.length}명</span>
      </section>

      {/* 리더보드 테이블 */}
      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
                <th className="px-4 py-2 text-left font-medium">#</th>
                <th className="px-4 py-2 text-left font-medium">사용자</th>
                <th className="px-4 py-2 text-left font-medium">Tier</th>
                <th className="px-4 py-2 text-left font-medium">KYC</th>
                <th className="px-4 py-2 text-right font-medium">평판</th>
                <th className="px-4 py-2 text-right font-medium">정확 기여</th>
                <th className="px-4 py-2 text-right font-medium">총 수익</th>
                <th className="px-4 py-2 text-right font-medium">Stake</th>
                <th className="px-4 py-2 text-right font-medium">액션</th>
              </tr>
            </thead>
            <tbody>
              {contribs.length === 0 && !loading && (
                <tr>
                  <td colSpan={9} className="px-4 py-10 text-center text-sm text-gray-400">
                    기여자 없음
                  </td>
                </tr>
              )}
              {contribs.map((c, idx) => {
                const s = TIER_STYLE[c.tier] || TIER_STYLE.BRONZE;
                return (
                  <tr key={c.userId} className="border-b hover:bg-gray-50" style={{ borderColor: "#f3f4f6" }}>
                    <td className="px-4 py-3 text-xs text-gray-500">{idx + 1}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">{c.userId.slice(0, 14)}</td>
                    <td className="px-4 py-3">
                      <span
                        className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                        style={{ color: s.color, background: s.bg }}
                      >
                        {s.emoji} {s.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {c.kycVerified ? (
                        <span
                          className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                          style={{ color: "#166534", background: "#dcfce7" }}
                        >
                          ✓
                        </span>
                      ) : (
                        <span
                          className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                          style={{ color: "#991b1b", background: "#fee2e2" }}
                        >
                          ✗
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {(c.reputation ?? 0).toFixed(3)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-green-700">
                      {(c.correctContribs ?? 0).toLocaleString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-indigo-700">
                      {(c.totalEarned ?? 0).toLocaleString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-600">
                      {(c.stakedBalance ?? 0).toLocaleString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => evaluate(c.userId)}
                        disabled={busy !== null}
                        className="rounded-lg border px-2.5 py-1 text-[11px] hover:bg-gray-50 disabled:opacity-60"
                        style={{ borderColor: "#e5e7eb" }}
                      >
                        {busy === c.userId ? "..." : "재평가"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
