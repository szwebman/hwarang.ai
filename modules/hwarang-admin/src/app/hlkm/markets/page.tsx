"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 시장 (Bounty + Prediction Market 통합)
 * - 탭: [Bounty 현상금] [Prediction Market 예측 시장]
 * - Bounty: 공개 현상금 목록, 내 현상금, 내 제출
 * - Prediction: 활성 시장, 현재 odds, 내 베팅, calibration 리포트
 */

import { useCallback, useEffect, useState } from "react";
import StatCard from "../_components/StatCard";

type Tab = "bounty" | "market";

interface Bounty {
  id: string;
  creator_id: string;
  topic: string;
  description: string;
  domain: string;
  reward_amount: number;
  required_tier: string;
  deadline: string | null;
  status: string;
  winner_id: string | null;
  winner_fact_id: string | null;
  awarded_at: string | null;
}

interface BountySubmission {
  submission_id: string;
  bounty_id: string;
  fact_id: string;
  score: number;
  selected: boolean;
  submission_note: string | null;
}

interface Market {
  id: string;
  pending_fact_id: string;
  question: string;
  yes_pool: number;
  no_pool: number;
  betters_count: number;
  resolution_date: string | null;
  resolved: boolean;
  outcome: string | null;
  total_pool?: number;
}

interface MyBet {
  bet_id: string;
  market_id: string;
  side: string;
  amount: number;
  payoff: number;
  settled_at: string | null;
}

interface CalibrationReport {
  sample_size: number;
  buckets: {
    predicted_range: string;
    predicted_midpoint: number;
    empirical_yes_ratio: number;
    count: number;
  }[];
  expected_calibration_error: number;
  brier_score: number;
}

export default function MarketsPage() {
  const [tab, setTab] = useState<Tab>("bounty");

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">시장</h1>
          <p className="mt-1 text-sm text-gray-500">
            현상금 + 예측 시장 — 지식 수집과 확률 가격 형성.
          </p>
        </div>
      </header>

      <div className="flex gap-1 rounded-xl border bg-white p-1" style={{ borderColor: "#e5e7eb" }}>
        <button
          onClick={() => setTab("bounty")}
          className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            tab === "bounty" ? "bg-indigo-600 text-white" : "text-gray-600 hover:bg-gray-50"
          }`}
        >
          Bounty 현상금
        </button>
        <button
          onClick={() => setTab("market")}
          className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            tab === "market" ? "bg-indigo-600 text-white" : "text-gray-600 hover:bg-gray-50"
          }`}
        >
          Prediction Market 예측 시장
        </button>
      </div>

      {tab === "bounty" ? <BountyTab /> : <PredictionTab />}
    </div>
  );
}

function BountyTab() {
  const [openBounties, setOpenBounties] = useState<Bounty[]>([]);
  const [myBounties, setMyBounties] = useState<Bounty[]>([]);
  const [mySubs, setMySubs] = useState<BountySubmission[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [newTopic, setNewTopic] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newReward, setNewReward] = useState(100);
  const [newDays, setNewDays] = useState(14);
  const [newDomain, setNewDomain] = useState("general");
  const [newTier, setNewTier] = useState("SILVER");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [a, b, c] = await Promise.all([
        adminFetch("/api/knowledge/bounty/open"),
        adminFetch("/api/knowledge/bounty/my-bounties"),
        adminFetch("/api/knowledge/bounty/my-submissions"),
      ]);
      if (a.ok) setOpenBounties(await a.json());
      if (b.ok) setMyBounties(await b.json());
      if (c.ok) setMySubs(await c.json());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const create = async () => {
    if (!newTopic.trim()) {
      setMessage({ ok: false, text: "주제를 입력하세요" });
      return;
    }
    setBusy("create");
    try {
      const resp = await adminFetch("/api/knowledge/bounty/create", {
        method: "POST",
        body: JSON.stringify({
          topic: newTopic,
          description: newDesc,
          reward_amount: newReward,
          deadline_days: newDays,
          domain: newDomain,
          required_tier: newTier,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data?.detail?.message || data?.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: `Bounty 생성됨 (id: ${data.bounty_id})` });
      setCreateOpen(false);
      setNewTopic("");
      setNewDesc("");
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "생성 실패" });
    } finally {
      setBusy(null);
    }
  };

  const totalReward = openBounties.reduce((s, b) => s + b.reward_amount, 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="공개 현상금" value={openBounties.length} accent="primary" />
        <StatCard
          label="총 상금"
          value={totalReward}
          accent="success"
          hint={`평균 ${(openBounties.length > 0 ? totalReward / openBounties.length : 0).toFixed(0)}`}
        />
        <StatCard label="내 현상금" value={myBounties.length} accent="neutral" />
        <StatCard label="내 제출" value={mySubs.length} accent="warning" />
      </div>

      <div className="flex justify-end">
        <button
          onClick={() => setCreateOpen(true)}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          + 현상금 생성
        </button>
      </div>

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

      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="border-b px-4 py-3" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="font-semibold text-gray-900">공개 현상금</h2>
        </div>
        <div className="divide-y" style={{ borderColor: "#f3f4f6" }}>
          {openBounties.length === 0 && !loading && (
            <div className="px-4 py-10 text-center text-sm text-gray-400">열린 현상금 없음</div>
          )}
          {openBounties.map((b) => (
            <article key={b.id} className="p-4 hover:bg-gray-50">
              <div className="flex items-start gap-3">
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-gray-900">{b.topic}</h3>
                  <p className="mt-1 text-xs text-gray-600">{b.description || "(설명 없음)"}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                    <span className="rounded bg-indigo-100 px-1.5 py-0.5 font-medium text-indigo-700">
                      {b.domain}
                    </span>
                    <span className="rounded bg-gray-100 px-1.5 py-0.5">{b.required_tier}+</span>
                    <span className="ml-2 font-mono">#{b.id.slice(0, 8)}</span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-bold text-indigo-600">
                    {b.reward_amount.toLocaleString("ko-KR")}
                  </div>
                  <div className="text-[10px] text-gray-500">HWARANG</div>
                  <div className="mt-1 text-[10px] text-amber-700">
                    {b.deadline ? new Date(b.deadline).toLocaleDateString("ko-KR") : "-"}
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="border-b px-4 py-3" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="font-semibold text-gray-900">내 현상금 이력</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
                <th className="px-4 py-2 text-left font-medium">Topic</th>
                <th className="px-4 py-2 text-left font-medium">상태</th>
                <th className="px-4 py-2 text-right font-medium">상금</th>
                <th className="px-4 py-2 text-left font-medium">마감</th>
              </tr>
            </thead>
            <tbody>
              {myBounties.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-10 text-center text-sm text-gray-400">
                    이력 없음
                  </td>
                </tr>
              )}
              {myBounties.map((b) => (
                <tr key={b.id} className="border-b hover:bg-gray-50" style={{ borderColor: "#f3f4f6" }}>
                  <td className="px-4 py-3 text-sm">{b.topic}</td>
                  <td className="px-4 py-3">
                    <span
                      className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                      style={{
                        color:
                          b.status === "awarded"
                            ? "#166534"
                            : b.status === "open"
                              ? "#1d4ed8"
                              : "#475569",
                        background:
                          b.status === "awarded"
                            ? "#dcfce7"
                            : b.status === "open"
                              ? "#dbeafe"
                              : "#e2e8f0",
                      }}
                    >
                      {b.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {b.reward_amount.toLocaleString("ko-KR")}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {b.deadline ? new Date(b.deadline).toLocaleDateString("ko-KR") : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="border-b px-4 py-3" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="font-semibold text-gray-900">내 제출 이력</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
                <th className="px-4 py-2 text-left font-medium">Bounty</th>
                <th className="px-4 py-2 text-left font-medium">Fact</th>
                <th className="px-4 py-2 text-right font-medium">점수</th>
                <th className="px-4 py-2 text-left font-medium">당선</th>
              </tr>
            </thead>
            <tbody>
              {mySubs.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-10 text-center text-sm text-gray-400">
                    제출 이력 없음
                  </td>
                </tr>
              )}
              {mySubs.map((s) => (
                <tr key={s.submission_id} className="border-b hover:bg-gray-50" style={{ borderColor: "#f3f4f6" }}>
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">
                    {s.bounty_id.slice(0, 10)}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">
                    {s.fact_id.slice(0, 10)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{s.score.toFixed(2)}</td>
                  <td className="px-4 py-3">
                    {s.selected ? (
                      <span
                        className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                        style={{ color: "#166534", background: "#dcfce7" }}
                      >
                        🏆 당선
                      </span>
                    ) : (
                      <span className="text-[11px] text-gray-400">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {createOpen && (
        <ModalOverlay onClose={() => setCreateOpen(false)}>
          <div className="w-full max-w-md rounded-xl border bg-white p-6" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="text-lg font-bold text-gray-900">현상금 생성</h2>
            <div className="mt-4 space-y-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">주제</label>
                <input
                  value={newTopic}
                  onChange={(e) => setNewTopic(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">설명</label>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  rows={3}
                  className="w-full rounded-lg border p-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-gray-700">상금 (HWARANG)</label>
                  <input
                    type="number"
                    min={50}
                    value={newReward}
                    onChange={(e) => setNewReward(parseInt(e.target.value) || 50)}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    style={{ borderColor: "#e5e7eb" }}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-gray-700">마감 (일)</label>
                  <input
                    type="number"
                    min={1}
                    max={90}
                    value={newDays}
                    onChange={(e) => setNewDays(parseInt(e.target.value) || 14)}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    style={{ borderColor: "#e5e7eb" }}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-gray-700">도메인</label>
                  <input
                    value={newDomain}
                    onChange={(e) => setNewDomain(e.target.value)}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    style={{ borderColor: "#e5e7eb" }}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-gray-700">요구 등급</label>
                  <select
                    value={newTier}
                    onChange={(e) => setNewTier(e.target.value)}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    style={{ borderColor: "#e5e7eb" }}
                  >
                    <option value="BRONZE">BRONZE</option>
                    <option value="SILVER">SILVER</option>
                    <option value="GOLD">GOLD</option>
                    <option value="DIAMOND">DIAMOND</option>
                  </select>
                </div>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setCreateOpen(false)}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={create}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                생성
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function PredictionTab() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [myBets, setMyBets] = useState<MyBet[]>([]);
  const [calibration, setCalibration] = useState<CalibrationReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [betTarget, setBetTarget] = useState<Market | null>(null);
  const [betSide, setBetSide] = useState<"YES" | "NO">("YES");
  const [betAmount, setBetAmount] = useState(100);
  const [preview, setPreview] = useState<{ payoff: number; profit: number; roi: number } | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [a, b, c] = await Promise.all([
        adminFetch("/api/knowledge/market/active"),
        adminFetch("/api/knowledge/market/my-bets"),
        adminFetch("/api/knowledge/market/calibration?last_days=90"),
      ]);
      if (a.ok) setMarkets(await a.json());
      if (b.ok) setMyBets(await b.json());
      if (c.ok) setCalibration(await c.json());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const openBet = (m: Market) => {
    setBetTarget(m);
    setBetSide("YES");
    setBetAmount(100);
    setPreview(null);
  };

  const loadPreview = useCallback(async () => {
    if (!betTarget) return;
    const qs = new URLSearchParams({ side: betSide, amount: String(betAmount) });
    const resp = await adminFetch(
      `/api/knowledge/market/${encodeURIComponent(betTarget.id)}/payoff-preview?${qs}`
    );
    if (resp.ok) {
      setPreview(await resp.json());
    }
  }, [betTarget, betSide, betAmount]);

  useEffect(() => {
    if (betTarget) loadPreview();
  }, [betTarget, loadPreview]);

  const placeBet = async () => {
    if (!betTarget) return;
    setBusy(betTarget.id);
    try {
      const resp = await adminFetch(
        `/api/knowledge/market/${encodeURIComponent(betTarget.id)}/bet`,
        {
          method: "POST",
          body: JSON.stringify({ side: betSide, amount: betAmount }),
        }
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data?.detail?.message || data?.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "베팅 완료" });
      setBetTarget(null);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const autoResolve = async () => {
    setBusy("auto");
    try {
      const resp = await adminFetch("/api/knowledge/market/auto-resolve", { method: "POST" });
      const data = await resp.json();
      setMessage({ ok: true, text: `자동 정산: ${JSON.stringify(data)}` });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const totalPool = markets.reduce((s, m) => s + (m.total_pool ?? m.yes_pool + m.no_pool), 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="활성 시장" value={markets.length} accent="primary" />
        <StatCard label="총 풀" value={totalPool} accent="success" hint="YES+NO 합계" />
        <StatCard label="내 베팅" value={myBets.length} accent="neutral" />
        <StatCard
          label="캘리브레이션 오차"
          value={`${((calibration?.expected_calibration_error ?? 0) * 100).toFixed(1)}%`}
          accent="warning"
          hint={`Brier ${(calibration?.brier_score ?? 0).toFixed(3)}`}
        />
      </div>

      <div className="flex justify-end">
        <button
          onClick={autoResolve}
          disabled={busy !== null}
          className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
          style={{ borderColor: "#e5e7eb" }}
        >
          만료 시장 자동 정산
        </button>
      </div>

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

      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="border-b px-4 py-3" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="font-semibold text-gray-900">활성 시장</h2>
        </div>
        <div className="divide-y" style={{ borderColor: "#f3f4f6" }}>
          {markets.length === 0 && !loading && (
            <div className="px-4 py-10 text-center text-sm text-gray-400">활성 시장 없음</div>
          )}
          {markets.map((m) => {
            const total = m.total_pool ?? m.yes_pool + m.no_pool;
            const yesP = total > 0 ? m.yes_pool / total : 0.5;
            return (
              <article key={m.id} className="p-4 hover:bg-gray-50">
                <div className="flex items-start gap-3">
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-gray-900">{m.question}</h3>
                    <div className="mt-2 flex items-center gap-2">
                      <div
                        className="relative h-3 flex-1 overflow-hidden rounded-full"
                        style={{ background: "#fecdd3" }}
                      >
                        <div
                          className="absolute left-0 top-0 h-full rounded-full"
                          style={{ width: `${yesP * 100}%`, background: "#86efac" }}
                        />
                      </div>
                      <span className="text-xs font-medium tabular-nums text-green-700">
                        YES {(yesP * 100).toFixed(0)}%
                      </span>
                      <span className="text-xs font-medium tabular-nums text-red-700">
                        NO {((1 - yesP) * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                      <span>풀 {total.toLocaleString("ko-KR")}</span>
                      <span>·</span>
                      <span>{m.betters_count}명 참여</span>
                      <span>·</span>
                      <span>
                        정산{" "}
                        {m.resolution_date
                          ? new Date(m.resolution_date).toLocaleDateString("ko-KR")
                          : "-"}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => openBet(m)}
                    className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
                  >
                    베팅
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="border-b px-4 py-3" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="font-semibold text-gray-900">내 베팅</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
                <th className="px-4 py-2 text-left font-medium">시장</th>
                <th className="px-4 py-2 text-left font-medium">Side</th>
                <th className="px-4 py-2 text-right font-medium">금액</th>
                <th className="px-4 py-2 text-right font-medium">Payoff</th>
                <th className="px-4 py-2 text-left font-medium">정산</th>
              </tr>
            </thead>
            <tbody>
              {myBets.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">
                    베팅 이력 없음
                  </td>
                </tr>
              )}
              {myBets.map((b) => (
                <tr key={b.bet_id} className="border-b hover:bg-gray-50" style={{ borderColor: "#f3f4f6" }}>
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">
                    {b.market_id.slice(0, 10)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                      style={{
                        color: b.side === "YES" ? "#166534" : "#991b1b",
                        background: b.side === "YES" ? "#dcfce7" : "#fee2e2",
                      }}
                    >
                      {b.side}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {b.amount.toLocaleString("ko-KR")}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium" style={{ color: b.payoff > 0 ? "#16a34a" : "#475569" }}>
                    {b.payoff.toLocaleString("ko-KR")}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {b.settled_at ? new Date(b.settled_at).toLocaleDateString("ko-KR") : "미정산"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Calibration 리포트 */}
      {calibration && calibration.sample_size > 0 && (
        <section className="rounded-xl border bg-white p-4" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">
            캘리브레이션 리포트 (샘플 {calibration.sample_size}건)
          </h2>
          <div className="space-y-1">
            {calibration.buckets.map((b) => (
              <div key={b.predicted_range} className="flex items-center gap-3 text-xs">
                <div className="w-24 font-medium text-gray-700">{b.predicted_range}</div>
                <div
                  className="relative h-3 flex-1 overflow-hidden rounded-full"
                  style={{ background: "#f1f5f9" }}
                >
                  <div
                    className="absolute left-0 top-0 h-full rounded-full"
                    style={{
                      width: `${b.predicted_midpoint * 100}%`,
                      background: "#818cf8",
                    }}
                  />
                  <div
                    className="absolute left-0 top-0 h-full border-r-2 border-red-500"
                    style={{ width: `${b.empirical_yes_ratio * 100}%` }}
                  />
                </div>
                <div className="w-20 text-right tabular-nums text-gray-600">
                  실제 {(b.empirical_yes_ratio * 100).toFixed(0)}%
                </div>
                <div className="w-12 text-right tabular-nums text-gray-500">{b.count}</div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-gray-500">
            파란색: 시장 예측 · 빨간색: 실제 결과. 겹칠수록 시장이 잘 보정됨.
          </p>
        </section>
      )}

      {betTarget && (
        <ModalOverlay onClose={() => setBetTarget(null)}>
          <div className="w-full max-w-md rounded-xl border bg-white p-6" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="text-lg font-bold text-gray-900">베팅</h2>
            <p className="mt-1 text-sm text-gray-700">{betTarget.question}</p>
            <div className="mt-4 space-y-3">
              <div className="flex gap-2">
                <button
                  onClick={() => setBetSide("YES")}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium ${
                    betSide === "YES"
                      ? "bg-green-600 text-white"
                      : "border bg-white text-gray-700"
                  }`}
                  style={betSide !== "YES" ? { borderColor: "#e5e7eb" } : undefined}
                >
                  YES
                </button>
                <button
                  onClick={() => setBetSide("NO")}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium ${
                    betSide === "NO"
                      ? "bg-red-600 text-white"
                      : "border bg-white text-gray-700"
                  }`}
                  style={betSide !== "NO" ? { borderColor: "#e5e7eb" } : undefined}
                >
                  NO
                </button>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">금액</label>
                <input
                  type="number"
                  min={10}
                  value={betAmount}
                  onChange={(e) => setBetAmount(parseInt(e.target.value) || 10)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </div>
              {preview && (
                <div
                  className="rounded-lg border bg-gray-50 p-3 text-xs"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  <div className="flex justify-between">
                    <span className="text-gray-600">예상 payoff</span>
                    <span className="tabular-nums font-medium">
                      {preview.payoff.toLocaleString("ko-KR")}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">예상 이익</span>
                    <span
                      className="tabular-nums font-medium"
                      style={{ color: preview.profit >= 0 ? "#16a34a" : "#dc2626" }}
                    >
                      {preview.profit >= 0 ? "+" : ""}
                      {preview.profit.toLocaleString("ko-KR")}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">ROI</span>
                    <span
                      className="tabular-nums font-medium"
                      style={{ color: preview.roi >= 0 ? "#16a34a" : "#dc2626" }}
                    >
                      {(preview.roi * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
              )}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setBetTarget(null)}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={placeBet}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                베팅 실행
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function ModalOverlay({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(15,23,42,0.5)" }}
      onClick={onClose}
    >
      <div onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>
  );
}
