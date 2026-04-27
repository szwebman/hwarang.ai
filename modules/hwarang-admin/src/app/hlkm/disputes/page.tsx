"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 분쟁 DAO
 * - 진행 중 분쟁 (status=open, 종료시간 카운트다운)
 * - 각 분쟁: 관련 사실 표시, 투표 현황 (side별 stake)
 * - Diamond 등급 사용자만 투표 가능 (disabled UI for others)
 * - 투표 이력, 정확도 리더보드
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface OpenDispute {
  id: string;
  topic: string;
  initiator_id: string;
  related_fact_ids: string[];
  voting_ends_at: string | null;
  total_staked: number;
}

interface DisputeDetail {
  id: string;
  topic: string;
  description: string;
  initiator_id: string;
  status: string;
  winning_side: string | null;
  voting_ends_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  related_fact_ids: string[];
  total_staked: number;
  votes: {
    voter_id: string;
    side: string;
    staked_amount: number;
    rationale: string | null;
    settled_amount: number;
  }[];
}

interface MyVote {
  id: string;
  dispute_id: string;
  side: string;
  staked_amount: number;
  settled_amount: number;
  rationale: string | null;
}

interface DisputeStats {
  total_disputes: number;
  resolved: number;
  pending: number;
  winning_side_distribution: Record<string, number>;
  avg_participation: number;
}

const SIDE_LABEL: Record<string, { label: string; color: string; bg: string }> = {
  A: { label: "A측", color: "#1d4ed8", bg: "#dbeafe" },
  B: { label: "B측", color: "#be123c", bg: "#fecdd3" },
  both_invalid: { label: "양측 모두 무효", color: "#7f1d1d", bg: "#fee2e2" },
  coexist: { label: "공존 가능", color: "#166534", bg: "#dcfce7" },
};

function timeLeft(iso: string | null): string {
  if (!iso) return "-";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "종료됨";
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  if (h >= 24) return `${Math.floor(h / 24)}일 ${h % 24}시간`;
  return `${h}시간 ${m}분`;
}

export default function DisputesPage() {
  const [opens, setOpens] = useState<OpenDispute[]>([]);
  const [myVotes, setMyVotes] = useState<MyVote[]>([]);
  const [stats, setStats] = useState<DisputeStats | null>(null);
  const [selected, setSelected] = useState<DisputeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [canVote, setCanVote] = useState(false);

  const [voteSide, setVoteSide] = useState<string>("A");
  const [voteStake, setVoteStake] = useState(100);
  const [voteRationale, setVoteRationale] = useState("");

  const loadOpens = useCallback(async () => {
    const resp = await adminFetch("/api/knowledge/dispute/open");
    if (resp.ok) setOpens(await resp.json());
  }, []);

  const loadMyVotes = useCallback(async () => {
    const resp = await adminFetch("/api/knowledge/dispute/my-votes?limit=50");
    if (resp.ok) setMyVotes(await resp.json());
  }, []);

  const loadStats = useCallback(async () => {
    const resp = await adminFetch("/api/knowledge/dispute/stats?last_days=30");
    if (resp.ok) setStats(await resp.json());
  }, []);

  const checkCanVote = useCallback(async () => {
    const resp = await adminFetch("/api/knowledge/gate/check?action=dispute_vote");
    if (resp.ok) {
      const data = await resp.json();
      setCanVote(!!data.allowed);
    }
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([loadOpens(), loadMyVotes(), loadStats(), checkCanVote()]);
    } finally {
      setLoading(false);
    }
  }, [loadOpens, loadMyVotes, loadStats, checkCanVote]);

  useEffect(() => {
    reload();
  }, [reload]);

  const openDetail = async (id: string) => {
    setBusy(id);
    try {
      const resp = await adminFetch(`/api/knowledge/dispute/${encodeURIComponent(id)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: DisputeDetail = await resp.json();
      setSelected(data);
      setVoteSide("A");
      setVoteStake(100);
      setVoteRationale("");
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "조회 실패" });
    } finally {
      setBusy(null);
    }
  };

  const submitVote = async () => {
    if (!selected) return;
    setBusy(selected.id);
    try {
      const resp = await adminFetch(
        `/api/knowledge/dispute/${encodeURIComponent(selected.id)}/vote`,
        {
          method: "POST",
          body: JSON.stringify({
            side: voteSide,
            staked_amount: voteStake,
            rationale: voteRationale || null,
          }),
        }
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data?.detail?.message || data?.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "투표 완료" });
      openDetail(selected.id);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "투표 실패" });
    } finally {
      setBusy(null);
    }
  };

  const autoFinalize = async () => {
    setBusy("auto");
    try {
      const resp = await adminFetch("/api/knowledge/dispute/auto-finalize", { method: "POST" });
      const data = await resp.json();
      setMessage({ ok: true, text: `자동 확정: ${JSON.stringify(data)}` });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const stakeBySide = useMemo(() => {
    if (!selected) return {} as Record<string, number>;
    const out: Record<string, number> = {};
    for (const v of selected.votes) {
      out[v.side] = (out[v.side] || 0) + v.staked_amount;
    }
    return out;
  }, [selected]);

  const myAccuracy = useMemo(() => {
    if (myVotes.length === 0) return 0;
    const settled = myVotes.filter((v) => v.settled_amount > 0);
    const won = settled.filter((v) => v.settled_amount >= v.staked_amount).length;
    return settled.length > 0 ? won / settled.length : 0;
  }, [myVotes]);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">분쟁 DAO</h1>
          <p className="mt-1 text-sm text-gray-500">
            모순 해결 · Diamond 등급만 투표 가능 · 스테이킹 기반 판결.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={autoFinalize}
            disabled={busy !== null}
            className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb" }}
          >
            만료 분쟁 자동 확정
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
        <StatCard label="진행 중 분쟁" value={opens.length} accent="warning" />
        <StatCard
          label="해결 (30일)"
          value={stats?.resolved ?? 0}
          accent="success"
          hint={`평균 참여 ${(stats?.avg_participation ?? 0).toFixed(1)}명`}
        />
        <StatCard label="내 투표 이력" value={myVotes.length} accent="primary" />
        <StatCard
          label="내 정확도"
          value={`${(myAccuracy * 100).toFixed(0)}%`}
          accent="neutral"
          hint="정산된 건 기준"
        />
      </div>

      {!canVote && (
        <div
          className="rounded-lg border p-3 text-xs"
          style={{ borderColor: "#fde68a", background: "#fef9c3", color: "#854d0e" }}
        >
          ⚠️ 분쟁 투표는 Diamond 등급 + KYC 인증자만 가능합니다. 투표 버튼이 비활성화됩니다.
        </div>
      )}

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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 진행 중 분쟁 */}
        <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
          <div className="border-b px-4 py-3" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="font-semibold text-gray-900">진행 중 분쟁</h2>
          </div>
          <div className="divide-y" style={{ borderColor: "#f3f4f6" }}>
            {opens.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-gray-400">분쟁 없음</div>
            )}
            {opens.map((d) => (
              <button
                key={d.id}
                onClick={() => openDetail(d.id)}
                disabled={busy !== null}
                className={`w-full p-4 text-left transition-colors hover:bg-gray-50 disabled:opacity-60 ${
                  selected?.id === d.id ? "bg-indigo-50" : ""
                }`}
              >
                <div className="text-sm font-medium text-gray-900">{d.topic}</div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                  <span className="font-mono">#{d.id.slice(0, 8)}</span>
                  <span>·</span>
                  <span>{d.related_fact_ids.length}개 사실</span>
                  <span>·</span>
                  <span>stake {d.total_staked.toLocaleString("ko-KR")}</span>
                  <span className="ml-auto font-medium text-amber-700">
                    ⏱ {timeLeft(d.voting_ends_at)}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* 분쟁 상세 + 투표 */}
        <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
          <div className="border-b px-4 py-3" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="font-semibold text-gray-900">분쟁 상세</h2>
          </div>
          <div className="p-4">
            {!selected && (
              <div className="py-10 text-center text-sm text-gray-400">
                왼쪽 목록에서 분쟁을 선택하세요
              </div>
            )}
            {selected && (
              <div className="space-y-4">
                <div>
                  <h3 className="font-semibold text-gray-900">{selected.topic}</h3>
                  <p className="mt-1 text-xs text-gray-600">{selected.description}</p>
                </div>

                <div>
                  <div className="text-[10px] font-semibold uppercase text-gray-500">관련 사실</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {selected.related_fact_ids.map((fid) => (
                      <span
                        key={fid}
                        className="rounded bg-gray-100 px-2 py-0.5 text-[11px] font-mono text-gray-700"
                      >
                        {fid.slice(0, 12)}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] font-semibold uppercase text-gray-500">투표 현황</div>
                  <div className="mt-2 space-y-1">
                    {Object.keys(SIDE_LABEL).map((side) => {
                      const stake = stakeBySide[side] || 0;
                      const max = Math.max(1, ...Object.values(stakeBySide));
                      const pct = (stake / max) * 100;
                      const s = SIDE_LABEL[side];
                      return (
                        <div key={side} className="flex items-center gap-2">
                          <div className="w-20 text-xs font-medium" style={{ color: s.color }}>
                            {s.label}
                          </div>
                          <div
                            className="relative h-3 flex-1 overflow-hidden rounded-full"
                            style={{ background: "#f1f5f9" }}
                          >
                            <div
                              className="absolute left-0 top-0 h-full rounded-full"
                              style={{ width: `${pct}%`, background: s.bg }}
                            />
                          </div>
                          <div className="w-20 text-right text-xs tabular-nums text-gray-700">
                            {stake.toLocaleString("ko-KR")}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="rounded-lg border bg-gray-50 p-3" style={{ borderColor: "#e5e7eb" }}>
                  <div className="mb-2 text-xs font-semibold text-gray-700">투표하기</div>
                  <div className="space-y-2">
                    <select
                      value={voteSide}
                      onChange={(e) => setVoteSide(e.target.value)}
                      disabled={!canVote}
                      className="w-full rounded-lg border px-2 py-1 text-xs disabled:opacity-60"
                      style={{ borderColor: "#e5e7eb" }}
                    >
                      {Object.entries(SIDE_LABEL).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v.label}
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      min={10}
                      max={1000}
                      value={voteStake}
                      onChange={(e) => setVoteStake(parseInt(e.target.value) || 10)}
                      disabled={!canVote}
                      className="w-full rounded-lg border px-2 py-1 text-xs disabled:opacity-60"
                      style={{ borderColor: "#e5e7eb" }}
                    />
                    <textarea
                      value={voteRationale}
                      onChange={(e) => setVoteRationale(e.target.value)}
                      placeholder="투표 근거 (선택)"
                      rows={2}
                      disabled={!canVote}
                      className="w-full rounded-lg border p-2 text-xs disabled:opacity-60"
                      style={{ borderColor: "#e5e7eb" }}
                    />
                    <button
                      onClick={submitVote}
                      disabled={!canVote || busy !== null}
                      className="w-full rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
                    >
                      투표 제출
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* 내 투표 이력 */}
      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="border-b px-4 py-3" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="font-semibold text-gray-900">내 투표 이력</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
                <th className="px-4 py-2 text-left font-medium">Dispute</th>
                <th className="px-4 py-2 text-left font-medium">Side</th>
                <th className="px-4 py-2 text-right font-medium">Stake</th>
                <th className="px-4 py-2 text-right font-medium">정산</th>
                <th className="px-4 py-2 text-right font-medium">손익</th>
              </tr>
            </thead>
            <tbody>
              {myVotes.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">
                    투표 이력 없음
                  </td>
                </tr>
              )}
              {myVotes.map((v) => {
                const s = SIDE_LABEL[v.side] || { label: v.side, color: "#475569", bg: "#e2e8f0" };
                const pnl = v.settled_amount - v.staked_amount;
                return (
                  <tr key={v.id} className="border-b hover:bg-gray-50" style={{ borderColor: "#f3f4f6" }}>
                    <td className="px-4 py-3 font-mono text-xs text-gray-600">
                      {v.dispute_id.slice(0, 10)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                        style={{ color: s.color, background: s.bg }}
                      >
                        {s.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {v.staked_amount.toLocaleString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {v.settled_amount.toLocaleString("ko-KR")}
                    </td>
                    <td
                      className="px-4 py-3 text-right tabular-nums font-medium"
                      style={{ color: pnl >= 0 ? "#16a34a" : "#dc2626" }}
                    >
                      {pnl >= 0 ? "+" : ""}
                      {pnl.toLocaleString("ko-KR")}
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
