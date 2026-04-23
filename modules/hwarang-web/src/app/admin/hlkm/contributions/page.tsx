"use client";

/**
 * HLKM 기여자 랭킹 — 기간별 기여 사실 + 보상 내역
 * - 드롭다운: 7일 / 30일 / 90일 / 전체
 * - 테이블: 순위, 사용자, 기여 수, 총 보상, 평균 품질
 * - 행 클릭 → 상세 패널 (기여 사실 목록, 코인 내역)
 */

import { useCallback, useEffect, useMemo, useState } from "react";

interface LeaderEntry {
  user_id: string;
  user_name?: string;
  user_email?: string;
  fact_count: number;
  total_reward: number;      // HWARANG 토큰
  avg_quality: number;       // 0..1
  approved_count?: number;
  rejected_count?: number;
}

interface ContributionDetail {
  user: {
    id: string;
    name?: string;
    email?: string;
  };
  facts: {
    id: string;
    statement: string;
    domain: string;
    quality_score: number;
    created_at: string;
    state: string;
    reward?: number;
  }[];
  rewards: {
    id: string;
    amount: number;
    reason: string;
    created_at: string;
    tx_hash?: string;
  }[];
}

const PERIODS: { key: string; label: string; days: number }[] = [
  { key: "7", label: "최근 7일", days: 7 },
  { key: "30", label: "최근 30일", days: 30 },
  { key: "90", label: "최근 90일", days: 90 },
  { key: "all", label: "전체", days: 0 },
];

export default function ContributionsPage() {
  const [period, setPeriod] = useState("30");
  const [entries, setEntries] = useState<LeaderEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [detail, setDetail] = useState<ContributionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const p = PERIODS.find((x) => x.key === period)!;
      const q = p.days > 0 ? `?days=${p.days}` : "";
      const resp = await fetch(`/api/admin/hlkm/contributions/leaderboard${q}`);
      if (resp.ok) {
        const data = await resp.json();
        const list: LeaderEntry[] = Array.isArray(data) ? data : data.items || [];
        setEntries(list);
      } else {
        setEntries([]);
      }
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    if (!selectedUser) { setDetail(null); return; }
    let alive = true;
    setDetailLoading(true);
    fetch(`/api/admin/hlkm/contributions/user/${selectedUser}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (alive) setDetail(d); })
      .catch(() => { if (alive) setDetail(null); })
      .finally(() => { if (alive) setDetailLoading(false); });
    return () => { alive = false; };
  }, [selectedUser]);

  const totals = useMemo(
    () => ({
      users: entries.length,
      facts: entries.reduce((s, e) => s + e.fact_count, 0),
      reward: entries.reduce((s, e) => s + e.total_reward, 0),
    }),
    [entries]
  );

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">기여자 랭킹</h1>
          <p className="mt-1 text-sm text-gray-500">
            사실 기여 품질에 따른 HWARANG 보상 현황입니다.
          </p>
        </div>
        <select
          value={period}
          onChange={(e) => { setPeriod(e.target.value); setSelectedUser(null); }}
          className="rounded-lg border px-3 py-1.5 text-sm"
          style={{ borderColor: "#e5e7eb" }}
        >
          {PERIODS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
        </select>
      </header>

      {/* 요약 */}
      <div className="grid grid-cols-3 gap-4">
        <SummaryBox label="기여자 수" value={totals.users} />
        <SummaryBox label="승인된 사실" value={totals.facts} />
        <SummaryBox label="총 보상 (HWA)" value={totals.reward} accent="#f59e0b" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* 랭킹 테이블 */}
        <div className="rounded-xl border bg-white lg:col-span-3" style={{ borderColor: "#e5e7eb" }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-gray-50 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
                  <th className="px-4 py-2 text-left font-medium">순위</th>
                  <th className="px-4 py-2 text-left font-medium">사용자</th>
                  <th className="px-4 py-2 text-right font-medium">기여</th>
                  <th className="px-4 py-2 text-right font-medium">보상 (HWA)</th>
                  <th className="px-4 py-2 text-right font-medium">평균 품질</th>
                </tr>
              </thead>
              <tbody>
                {entries.length === 0 && !loading && (
                  <tr>
                    <td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">
                      기간 내 기여 내역이 없습니다
                    </td>
                  </tr>
                )}
                {entries.map((e, idx) => {
                  const rank = idx + 1;
                  const medal = rank === 1 ? "🥇" : rank === 2 ? "🥈" : rank === 3 ? "🥉" : null;
                  return (
                    <tr
                      key={e.user_id}
                      onClick={() => setSelectedUser(e.user_id)}
                      className={`cursor-pointer border-b transition-colors ${
                        selectedUser === e.user_id ? "bg-blue-50" : "hover:bg-gray-50"
                      }`}
                      style={{ borderColor: "#f3f4f6" }}
                    >
                      <td className="px-4 py-3 font-bold tabular-nums">
                        {medal ? <span className="mr-1">{medal}</span> : null}
                        {rank}
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-gray-900">{e.user_name || e.user_email || e.user_id}</div>
                        {e.user_email && e.user_name && (
                          <div className="text-xs text-gray-500">{e.user_email}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {e.fact_count.toLocaleString("ko-KR")}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums font-semibold" style={{ color: "#f59e0b" }}>
                        {e.total_reward.toLocaleString("ko-KR")}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        <QualityPill score={e.avg_quality} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* 상세 */}
        <aside className="rounded-xl border bg-white p-5 lg:col-span-2" style={{ borderColor: "#e5e7eb" }}>
          {!selectedUser ? (
            <div className="flex h-full min-h-[300px] items-center justify-center text-sm text-gray-400">
              랭킹 행을 클릭하면 상세가 표시됩니다
            </div>
          ) : detailLoading ? (
            <div className="flex h-full min-h-[300px] items-center justify-center text-sm text-gray-400">
              로딩 중…
            </div>
          ) : !detail ? (
            <div className="text-sm text-gray-500">상세 정보를 불러올 수 없습니다</div>
          ) : (
            <div className="space-y-4">
              <div>
                <div className="text-xs text-gray-500">사용자</div>
                <div className="text-sm font-semibold text-gray-900">
                  {detail.user.name || detail.user.email || detail.user.id}
                </div>
                {detail.user.email && detail.user.name && (
                  <div className="text-xs text-gray-500">{detail.user.email}</div>
                )}
              </div>

              <div>
                <div className="mb-2 text-xs font-semibold text-gray-500">최근 기여 사실</div>
                {detail.facts.length === 0 ? (
                  <div className="text-xs text-gray-400">기여 사실이 없습니다</div>
                ) : (
                  <ul className="max-h-60 space-y-2 overflow-y-auto">
                    {detail.facts.slice(0, 10).map((f) => (
                      <li key={f.id} className="rounded-lg bg-gray-50 p-2 text-xs">
                        <div className="flex items-center gap-1">
                          <span className="rounded bg-white px-1.5 py-0.5 text-[10px] text-gray-600">{f.domain}</span>
                          <span className="text-[10px] text-gray-500">{new Date(f.created_at).toLocaleDateString("ko-KR")}</span>
                          <span className="ml-auto text-[10px] tabular-nums text-gray-600">Q {Math.round(f.quality_score * 100)}</span>
                        </div>
                        <div className="mt-1 line-clamp-2 text-gray-800">{f.statement}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <div className="mb-2 text-xs font-semibold text-gray-500">코인 내역</div>
                {detail.rewards.length === 0 ? (
                  <div className="text-xs text-gray-400">지급 내역이 없습니다</div>
                ) : (
                  <ul className="max-h-48 space-y-1 overflow-y-auto">
                    {detail.rewards.slice(0, 20).map((r) => (
                      <li key={r.id} className="flex items-center justify-between text-xs">
                        <div>
                          <div className="text-gray-800">{r.reason}</div>
                          <div className="text-[10px] text-gray-500">{new Date(r.created_at).toLocaleString("ko-KR")}</div>
                        </div>
                        <div className="tabular-nums font-semibold" style={{ color: "#f59e0b" }}>
                          +{r.amount.toLocaleString("ko-KR")}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function SummaryBox({ label, value, accent = "#2563eb" }: { label: string; value: number; accent?: string }) {
  return (
    <div className="rounded-xl border bg-white p-4" style={{ borderColor: "#e5e7eb" }}>
      <div className="text-xs text-gray-500">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums" style={{ color: accent }}>
        {value.toLocaleString("ko-KR")}
      </div>
    </div>
  );
}

function QualityPill({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.8 ? "#16a34a" : score >= 0.5 ? "#d97706" : "#dc2626";
  return (
    <span className="font-semibold" style={{ color }}>{pct}</span>
  );
}
