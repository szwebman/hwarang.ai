"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM KYC 게이트 대시보드
 * - 상단 통계 카드: 24h 차단 건수, PII 감지, 학습 로그 수, 검증 대기
 * - 최근 차단 로그 (reason 필터)
 * - 학습 로그 검토 큐 (approve / reject)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface DenialRow {
  id: string;
  userId: string | null;
  sessionId: string | null;
  attemptedAction: string;
  reason: string;
  createdAt: string;
}

interface DenialStats {
  total: number;
  by_reason: Record<string, number>;
  top_users: [string, number][];
}

interface TrainingLogRow {
  id: string;
  userId: string | null;
  userIsVerified: boolean;
  userMessage: string;
  assistantReply: string;
  model: string | null;
  domain: string | null;
  feedbackRating: string | null;
  containsPII: boolean;
  containsHarmful: boolean;
  qualityScore: number | null;
  reviewedForTraining: boolean;
  approvedForTraining: boolean;
  createdAt: string;
  expiresAt: string | null;
}

interface TrainingStats {
  total: number;
  verified_users: number;
  unverified_users: number;
  pending_review: number;
  approved_for_training: number;
}

const REASON_LABEL: Record<string, { label: string; color: string; bg: string }> = {
  not_authenticated: { label: "미로그인", color: "#0c4a6e", bg: "#e0f2fe" },
  kyc_required: { label: "KYC 필요", color: "#991b1b", bg: "#fee2e2" },
  suspended: { label: "정지 계정", color: "#7f1d1d", bg: "#fecaca" },
  tier_insufficient: { label: "등급 부족", color: "#854d0e", bg: "#fef9c3" },
  quota_exceeded: { label: "한도 초과", color: "#92400e", bg: "#fef3c7" },
  sybil_flagged: { label: "Sybil 의심", color: "#6d28d9", bg: "#ede9fe" },
};

export default function GatePage() {
  const [denials, setDenials] = useState<DenialRow[]>([]);
  const [denialStats, setDenialStats] = useState<DenialStats | null>(null);
  const [trainingLogs, setTrainingLogs] = useState<TrainingLogRow[]>([]);
  const [trainingStats, setTrainingStats] = useState<TrainingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [reasonFilter, setReasonFilter] = useState<string>("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);

  const loadDenials = useCallback(async () => {
    const qs = new URLSearchParams({ limit: "100" });
    if (reasonFilter) qs.set("reason", reasonFilter);
    const resp = await adminFetch(`/api/knowledge/gate/denials?${qs}`);
    if (resp.ok) setDenials(await resp.json());
  }, [reasonFilter]);

  const loadStats = useCallback(async () => {
    const [d, t] = await Promise.all([
      adminFetch("/api/knowledge/gate/denials/stats?last_hours=24"),
      adminFetch("/api/knowledge/gate/training-logs/stats"),
    ]);
    if (d.ok) setDenialStats(await d.json());
    if (t.ok) setTrainingStats(await t.json());
  }, []);

  const loadTrainingLogs = useCallback(async () => {
    const qs = new URLSearchParams({ limit: "50" });
    if (verifiedOnly) qs.set("verified_only", "true");
    const resp = await adminFetch(`/api/knowledge/gate/training-logs/pending?${qs}`);
    if (resp.ok) setTrainingLogs(await resp.json());
  }, [verifiedOnly]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([loadDenials(), loadStats(), loadTrainingLogs()]);
    } finally {
      setLoading(false);
    }
  }, [loadDenials, loadStats, loadTrainingLogs]);

  useEffect(() => {
    reload();
  }, [reload]);

  const approve = async (id: string) => {
    setBusy(id);
    try {
      const resp = await adminFetch(`/api/knowledge/gate/training-logs/${id}/approve`, {
        method: "POST",
        body: JSON.stringify({ quality_score: 0.8 }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setMessage({ ok: true, text: "학습 로그 승인 완료" });
      loadTrainingLogs();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "승인 실패" });
    } finally {
      setBusy(null);
    }
  };

  const reject = async (id: string) => {
    setBusy(id);
    try {
      const resp = await adminFetch(`/api/knowledge/gate/training-logs/${id}/reject`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setMessage({ ok: true, text: "학습 로그 반려 처리" });
      loadTrainingLogs();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "반려 실패" });
    } finally {
      setBusy(null);
    }
  };

  const purgeExpired = async () => {
    if (!confirm("만료된 미인증 사용자 로그를 일괄 삭제하시겠습니까?")) return;
    setBusy("purge");
    try {
      const resp = await adminFetch("/api/knowledge/gate/training-logs/purge-expired", {
        method: "POST",
      });
      const data = await resp.json();
      setMessage({ ok: true, text: `${data.purged ?? 0}건 삭제됨` });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "삭제 실패" });
    } finally {
      setBusy(null);
    }
  };

  const piiCount = useMemo(
    () => trainingLogs.filter((x) => x.containsPII).length,
    [trainingLogs]
  );

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">KYC 게이트</h1>
          <p className="mt-1 text-sm text-gray-500">
            지식 기여 쓰기 차단 로그 + 미인증 사용자 대화의 학습 로그 검토.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={purgeExpired}
            disabled={busy !== null}
            className="rounded-lg border px-3 py-1.5 text-xs text-red-700 hover:bg-red-50 disabled:opacity-60"
            style={{ borderColor: "#fecaca" }}
          >
            만료 로그 삭제
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
        <StatCard
          label="24시간 차단 건수"
          value={denialStats?.total ?? 0}
          accent="danger"
          hint="ContributionGateDenial"
        />
        <StatCard
          label="PII 감지된 로그"
          value={piiCount}
          accent="warning"
          hint="자동 스캔 결과"
        />
        <StatCard
          label="학습 로그 총 수"
          value={trainingStats?.total ?? 0}
          accent="primary"
          hint={`${trainingStats?.verified_users ?? 0}건 인증됨`}
        />
        <StatCard
          label="검토 대기"
          value={trainingStats?.pending_review ?? 0}
          accent="neutral"
          hint={`승인됨 ${trainingStats?.approved_for_training ?? 0}`}
        />
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

      {/* 차단 로그 */}
      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div
          className="flex items-center gap-3 border-b px-4 py-3"
          style={{ borderColor: "#e5e7eb" }}
        >
          <h2 className="font-semibold text-gray-900">최근 차단 로그</h2>
          <select
            value={reasonFilter}
            onChange={(e) => setReasonFilter(e.target.value)}
            className="ml-auto rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb" }}
          >
            <option value="">전체 사유</option>
            {Object.entries(REASON_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
                <th className="px-4 py-2 text-left font-medium">사유</th>
                <th className="px-4 py-2 text-left font-medium">Action</th>
                <th className="px-4 py-2 text-left font-medium">사용자</th>
                <th className="px-4 py-2 text-left font-medium">세션</th>
                <th className="px-4 py-2 text-left font-medium">시간</th>
              </tr>
            </thead>
            <tbody>
              {denials.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-sm text-gray-400">
                    차단 이력이 없습니다
                  </td>
                </tr>
              )}
              {denials.map((d) => {
                const r = REASON_LABEL[d.reason] || {
                  label: d.reason,
                  color: "#475569",
                  bg: "#e2e8f0",
                };
                return (
                  <tr key={d.id} className="border-b hover:bg-gray-50" style={{ borderColor: "#f3f4f6" }}>
                    <td className="px-4 py-3">
                      <span
                        className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                        style={{ color: r.color, background: r.bg }}
                      >
                        {r.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-700">{d.attemptedAction}</td>
                    <td className="px-4 py-3 text-xs font-mono text-gray-600">
                      {d.userId ? d.userId.slice(0, 12) : "-"}
                    </td>
                    <td className="px-4 py-3 text-xs font-mono text-gray-600">
                      {d.sessionId ? d.sessionId.slice(0, 8) : "-"}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {new Date(d.createdAt).toLocaleString("ko-KR")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* 학습 로그 큐 */}
      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div
          className="flex items-center gap-3 border-b px-4 py-3"
          style={{ borderColor: "#e5e7eb" }}
        >
          <h2 className="font-semibold text-gray-900">학습 로그 검토 큐</h2>
          <label className="ml-auto flex items-center gap-2 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={verifiedOnly}
              onChange={(e) => setVerifiedOnly(e.target.checked)}
            />
            인증 사용자만
          </label>
        </div>
        <div className="divide-y" style={{ borderColor: "#f3f4f6" }}>
          {trainingLogs.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-gray-400">
              검토 대기 로그 없음
            </div>
          )}
          {trainingLogs.map((log) => (
            <article key={log.id} className="p-4 hover:bg-gray-50">
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span
                  className="rounded px-1.5 py-0.5 font-medium"
                  style={{
                    color: log.userIsVerified ? "#166534" : "#991b1b",
                    background: log.userIsVerified ? "#dcfce7" : "#fee2e2",
                  }}
                >
                  {log.userIsVerified ? "인증됨" : "미인증"}
                </span>
                {log.containsPII && (
                  <span
                    className="rounded px-1.5 py-0.5 font-medium"
                    style={{ color: "#92400e", background: "#fef3c7" }}
                  >
                    PII
                  </span>
                )}
                {log.containsHarmful && (
                  <span
                    className="rounded px-1.5 py-0.5 font-medium"
                    style={{ color: "#7f1d1d", background: "#fecaca" }}
                  >
                    유해
                  </span>
                )}
                <span className="text-gray-500">
                  {log.userId ? log.userId.slice(0, 10) : "anon"}
                </span>
                <span className="text-gray-400">{log.domain || "general"}</span>
                <span className="ml-auto text-gray-500">
                  {new Date(log.createdAt).toLocaleString("ko-KR")}
                </span>
              </div>
              <div className="mt-3 space-y-2">
                <div>
                  <div className="text-[10px] font-semibold text-gray-500">사용자</div>
                  <div className="text-sm text-gray-800">{log.userMessage}</div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold text-gray-500">어시스턴트</div>
                  <div className="text-sm text-gray-700">{log.assistantReply}</div>
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => approve(log.id)}
                  disabled={busy === log.id}
                  className="rounded-lg bg-green-600 px-3 py-1 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-60"
                >
                  {busy === log.id ? "..." : "승인"}
                </button>
                <button
                  onClick={() => reject(log.id)}
                  disabled={busy === log.id}
                  className="rounded-lg border px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                  style={{ borderColor: "#fecaca" }}
                >
                  반려
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
