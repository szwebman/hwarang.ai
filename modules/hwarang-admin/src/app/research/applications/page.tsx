"use client";

/**
 * Research Applications — 적용 검토 페이지
 *
 * - 탭: proposed / approved / rejected
 * - 카드: 어떤 논문, 어느 모듈, 변경 outline, effort, risk, 예상 효과
 * - "승인" / "거절" 버튼
 *   - 승인 시 → GrowthDecision approved → 백엔드가 실제 패치 작업 큐
 *   - 거절 시 → reason 입력 모달
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { adminFetch, getAdminUser } from "@/lib/auth";

interface Paper {
  id: string;
  arxivId: string | null;
  title: string;
  authors: string[];
  applicabilityScore: number | null;
  pdfUrl: string;
  codeUrl: string | null;
}

interface GrowthDecision {
  id: string;
  status: string;
  proposalJson: any;
}

interface AppItem {
  id: string;
  paperId: string;
  module: string;
  description: string;
  status: string;
  growthDecisionId: string | null;
  createdAt: string;
  reviewedAt: string | null;
  reviewedBy: string | null;
  paper?: Paper;
  growthDecision?: GrowthDecision;
}

const STATUS_TABS: { value: string; label: string; color: string }[] = [
  { value: "proposed", label: "검토 대기", color: "#6366f1" },
  { value: "approved", label: "승인됨", color: "#10b981" },
  { value: "implementing", label: "구현 중", color: "#0891b2" },
  { value: "done", label: "완료", color: "#a855f7" },
  { value: "rejected", label: "거절됨", color: "#dc2626" },
];

function riskColor(risk: string) {
  switch ((risk || "").toLowerCase()) {
    case "low":
      return "#10b981";
    case "medium":
      return "#ca8a04";
    case "high":
      return "#dc2626";
    default:
      return "#64748b";
  }
}

function fmtRel(iso: string | null) {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "—";
  const diffMs = Date.now() - t;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "방금";
  if (mins < 60) return `${mins}분 전`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}시간 전`;
  const days = Math.floor(hrs / 24);
  return `${days}일 전`;
}

export default function ResearchApplicationsPage() {
  const [tab, setTab] = useState("proposed");
  const [items, setItems] = useState<AppItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<AppItem | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await adminFetch(
        `/api/research/applications?status=${tab}&limit=200`
      );
      if (resp.ok) {
        const data = await resp.json();
        setItems(data.applications || []);
      } else {
        setItems([]);
      }
    } catch (e) {
      console.error(e);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    load();
  }, [load]);

  // ── 토스트 ─────────────────────────────────────
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  const handleApprove = async (app: AppItem) => {
    if (!confirm(`이 적용 제안을 승인하시겠습니까?\n\n[${app.module}]\n→ GrowthDecision 도 자동 승인되어 백엔드 패치 큐에 들어갑니다.`)) return;
    setActionId(app.id);
    try {
      const user = getAdminUser();
      const reviewer = user?.email || user?.name || "admin";
      const resp = await adminFetch(
        `/api/research/applications/${app.id}/approve`,
        {
          method: "POST",
          body: JSON.stringify({ reviewer }),
        }
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${resp.status}`);
      }
      setToast({ ok: true, text: `[${app.module}] 승인 완료` });
      load();
    } catch (e: any) {
      setToast({ ok: false, text: `승인 실패: ${e?.message || e}` });
    } finally {
      setActionId(null);
    }
  };

  const handleReject = async () => {
    if (!rejecting) return;
    if (!rejectReason.trim()) {
      setToast({ ok: false, text: "거절 사유를 입력하세요" });
      return;
    }
    setActionId(rejecting.id);
    try {
      const user = getAdminUser();
      const reviewer = user?.email || user?.name || "admin";
      const resp = await adminFetch(
        `/api/research/applications/${rejecting.id}/reject`,
        {
          method: "POST",
          body: JSON.stringify({ reason: rejectReason, reviewer }),
        }
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${resp.status}`);
      }
      setToast({ ok: true, text: `[${rejecting.module}] 거절 완료` });
      setRejecting(null);
      setRejectReason("");
      load();
    } catch (e: any) {
      setToast({ ok: false, text: `거절 실패: ${e?.message || e}` });
    } finally {
      setActionId(null);
    }
  };

  // ── 통계 ─────────────────────────────────────
  const stats = useMemo(() => {
    return {
      count: items.length,
      avgEffort:
        items.length === 0
          ? 0
          : items.reduce(
              (s, a) =>
                s + (Number(a.growthDecision?.proposalJson?.estimated_effort_hours) || 0),
              0
            ) / items.length,
      lowRisk: items.filter(
        (a) => (a.growthDecision?.proposalJson?.risk || "").toLowerCase() === "low"
      ).length,
      highRisk: items.filter(
        (a) => (a.growthDecision?.proposalJson?.risk || "").toLowerCase() === "high"
      ).length,
    };
  }, [items]);

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1
            className="text-2xl font-bold"
            style={{ color: "var(--foreground)" }}
          >
            적용 검토 (PaperApplication)
          </h1>
          <p
            className="text-sm mt-1"
            style={{ color: "var(--muted-foreground)" }}
          >
            화랑 적용성 0.7+ 논문 → LLM 이 자동 제안한 패치 outline. 승인 시
            GrowthDecision 으로 자동 연동.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            href="/research"
            className="px-3 py-2 rounded-lg text-sm"
            style={{ background: "var(--muted)", color: "var(--foreground)" }}
          >
            ← 대시보드
          </Link>
          <Link
            href="/research/papers"
            className="px-3 py-2 rounded-lg text-sm"
            style={{ background: "var(--muted)", color: "var(--foreground)" }}
          >
            논문 목록
          </Link>
        </div>
      </div>

      {/* 토스트 */}
      {toast && (
        <div
          className="mb-4 px-4 py-2.5 rounded-lg text-sm"
          style={{
            background: toast.ok
              ? "rgba(16,185,129,0.12)"
              : "rgba(220,38,38,0.12)",
            color: toast.ok ? "#10b981" : "#dc2626",
            border: `1px solid ${toast.ok ? "#10b98144" : "#dc262644"}`,
          }}
        >
          {toast.text}
        </div>
      )}

      {/* 탭 */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {STATUS_TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className="px-3.5 py-1.5 rounded-lg text-sm font-medium transition-colors"
            style={{
              background: tab === t.value ? `${t.color}22` : "var(--muted)",
              color: tab === t.value ? t.color : "var(--muted-foreground)",
              border: `1px solid ${tab === t.value ? `${t.color}66` : "var(--border)"}`,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 통계 4박스 (proposed 탭일 때만) */}
      {tab === "proposed" && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <SimpleStat label="대기 중" value={stats.count} color="#6366f1" />
          <SimpleStat
            label="평균 effort"
            value={`${stats.avgEffort.toFixed(0)}h`}
            color="#0891b2"
          />
          <SimpleStat
            label="저위험"
            value={stats.lowRisk}
            color="#10b981"
          />
          <SimpleStat
            label="고위험"
            value={stats.highRisk}
            color="#dc2626"
          />
        </div>
      )}

      {/* 리스트 */}
      {loading ? (
        <div className="text-center py-12 opacity-60">로딩 중...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 opacity-60">
          {tab === "proposed"
            ? "검토 대기 중인 제안이 없습니다."
            : `${tab} 상태의 항목이 없습니다.`}
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((a) => (
            <ApplicationCard
              key={a.id}
              app={a}
              onApprove={() => handleApprove(a)}
              onReject={() => {
                setRejecting(a);
                setRejectReason("");
              }}
              busy={actionId === a.id}
              showActions={tab === "proposed"}
            />
          ))}
        </div>
      )}

      {/* 거절 모달 */}
      {rejecting && (
        <RejectModal
          app={rejecting}
          reason={rejectReason}
          onChange={setRejectReason}
          onClose={() => {
            setRejecting(null);
            setRejectReason("");
          }}
          onSubmit={handleReject}
          submitting={actionId === rejecting.id}
        />
      )}
    </div>
  );
}

// ──────────────────────────────────────────────
// Application 카드
// ──────────────────────────────────────────────
function ApplicationCard({
  app,
  onApprove,
  onReject,
  busy,
  showActions,
}: {
  app: AppItem;
  onApprove: () => void;
  onReject: () => void;
  busy: boolean;
  showActions: boolean;
}) {
  const proposal = app.growthDecision?.proposalJson || {};
  const risk = String(proposal.risk || "—");
  const effort = proposal.estimated_effort_hours;
  const patchOutline = String(proposal.patch_outline || "");
  const expectedImprovement = String(proposal.expected_improvement || "");
  const rColor = riskColor(risk);

  return (
    <div
      className="rounded-xl p-5"
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderLeft: `4px solid ${rColor}`,
      }}
    >
      <div className="grid grid-cols-12 gap-4">
        {/* 왼쪽: 논문 + 모듈 + 설명 */}
        <div className="col-span-8">
          <div className="flex items-center gap-2 mb-2">
            <span
              className="text-[10px] px-2 py-0.5 rounded font-semibold"
              style={{
                background: "rgba(99,102,241,0.15)",
                color: "#a5b4fc",
              }}
            >
              {app.module}
            </span>
            <span className="text-[10px] opacity-60">
              {fmtRel(app.createdAt)}
            </span>
            {app.reviewedBy && (
              <span className="text-[10px] opacity-60">
                · 검토: {app.reviewedBy}
              </span>
            )}
          </div>

          {app.paper && (
            <div className="mb-2">
              <div
                className="text-sm font-semibold leading-snug"
                style={{ color: "var(--foreground)" }}
              >
                📄 {app.paper.title}
              </div>
              <div className="text-[11px] opacity-70 mt-0.5">
                {app.paper.authors.slice(0, 3).join(", ")}
                {app.paper.applicabilityScore != null && (
                  <span className="ml-2">
                    적용성{" "}
                    <span
                      style={{
                        color:
                          app.paper.applicabilityScore >= 0.7
                            ? "#10b981"
                            : "#ca8a04",
                      }}
                    >
                      {(app.paper.applicabilityScore * 100).toFixed(0)}%
                    </span>
                  </span>
                )}
              </div>
            </div>
          )}

          <div className="mb-3">
            <div className="text-[10px] uppercase tracking-wider opacity-60 mb-1">
              제안 내용
            </div>
            <p
              className="text-sm leading-relaxed whitespace-pre-wrap"
              style={{ color: "var(--foreground)" }}
            >
              {app.description}
            </p>
          </div>

          {patchOutline && (
            <div className="mb-3">
              <div className="text-[10px] uppercase tracking-wider opacity-60 mb-1">
                패치 outline
              </div>
              <pre
                className="text-[11px] font-mono p-2.5 rounded whitespace-pre-wrap"
                style={{
                  background: "var(--muted)",
                  border: "1px solid var(--border)",
                  color: "var(--foreground)",
                }}
              >
                {patchOutline}
              </pre>
            </div>
          )}

          {expectedImprovement && (
            <div>
              <div className="text-[10px] uppercase tracking-wider opacity-60 mb-1">
                예상 효과
              </div>
              <p
                className="text-xs"
                style={{ color: "var(--foreground)" }}
              >
                {expectedImprovement}
              </p>
            </div>
          )}
        </div>

        {/* 오른쪽: 메타 + 액션 */}
        <div className="col-span-4 flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2">
            <MetaBox label="effort" color="#0891b2">
              <span className="text-base font-bold">
                {effort != null ? `${effort}h` : "—"}
              </span>
            </MetaBox>
            <MetaBox label="risk" color={rColor}>
              <span className="text-base font-bold uppercase">{risk}</span>
            </MetaBox>
          </div>

          {app.paper && (
            <div className="flex flex-wrap gap-1.5">
              {app.paper.pdfUrl && (
                <a
                  href={app.paper.pdfUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] px-2 py-1 rounded"
                  style={{
                    background: "var(--muted)",
                    color: "var(--foreground)",
                  }}
                >
                  📄 PDF
                </a>
              )}
              {app.paper.codeUrl && (
                <a
                  href={app.paper.codeUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] px-2 py-1 rounded"
                  style={{
                    background: "var(--muted)",
                    color: "var(--foreground)",
                  }}
                >
                  💻 GitHub
                </a>
              )}
              {app.paper.arxivId && (
                <a
                  href={`https://arxiv.org/abs/${app.paper.arxivId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] px-2 py-1 rounded"
                  style={{
                    background: "var(--muted)",
                    color: "var(--foreground)",
                  }}
                >
                  🔗 arXiv
                </a>
              )}
              {app.growthDecisionId && (
                <span
                  className="text-[10px] px-2 py-1 rounded font-mono"
                  style={{
                    background: "rgba(168,85,247,0.12)",
                    color: "#a855f7",
                  }}
                  title="GrowthDecision id"
                >
                  GD: {app.growthDecisionId.slice(0, 6)}
                </span>
              )}
            </div>
          )}

          {showActions && (
            <div className="flex gap-2 mt-auto">
              <button
                onClick={onApprove}
                disabled={busy}
                className="flex-1 px-3 py-2 rounded text-xs font-bold disabled:opacity-50"
                style={{
                  background: "linear-gradient(135deg, #10b981, #059669)",
                  color: "#fff",
                }}
              >
                {busy ? "..." : "✓ 승인"}
              </button>
              <button
                onClick={onReject}
                disabled={busy}
                className="flex-1 px-3 py-2 rounded text-xs font-bold disabled:opacity-50"
                style={{
                  background: "rgba(220,38,38,0.12)",
                  color: "#dc2626",
                }}
              >
                ✗ 거절
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SimpleStat({
  label,
  value,
  color,
}: {
  label: string;
  value: number | string;
  color: string;
}) {
  return (
    <div
      className="rounded-xl p-3"
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderLeft: `3px solid ${color}`,
      }}
    >
      <div className="text-[10px] uppercase tracking-wider opacity-60 mb-1">
        {label}
      </div>
      <div className="text-xl font-bold" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

function MetaBox({
  label,
  color,
  children,
}: {
  label: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-lg p-2.5"
      style={{
        background: "var(--muted)",
        border: "1px solid var(--border)",
      }}
    >
      <div
        className="text-[9px] uppercase tracking-wider mb-0.5"
        style={{ color }}
      >
        {label}
      </div>
      <div style={{ color: "var(--foreground)" }}>{children}</div>
    </div>
  );
}

// ──────────────────────────────────────────────
// 거절 모달
// ──────────────────────────────────────────────
function RejectModal({
  app,
  reason,
  onChange,
  onClose,
  onSubmit,
  submitting,
}: {
  app: AppItem;
  reason: string;
  onChange: (v: string) => void;
  onClose: () => void;
  onSubmit: () => void;
  submitting: boolean;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={onClose}
    >
      <div
        className="rounded-2xl p-6 max-w-lg w-full"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          className="text-base font-bold mb-2"
          style={{ color: "var(--foreground)" }}
        >
          제안 거절
        </h2>
        <p className="text-xs opacity-75 mb-4">
          [{app.module}] {app.paper?.title || app.paperId}
        </p>

        <label className="text-[11px] uppercase tracking-wider opacity-60 block mb-1">
          거절 사유 *
        </label>
        <textarea
          value={reason}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          placeholder="예: 화랑 아키텍처와 호환되지 않음 / 효과 대비 effort 과다 / 이미 유사 기능 구현됨"
          className="w-full px-2.5 py-2 rounded text-sm mb-4"
          style={{
            background: "var(--input)",
            border: "1px solid var(--border)",
            color: "var(--foreground)",
          }}
          autoFocus
        />

        <div
          className="flex justify-end gap-2 pt-3"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-3 py-1.5 rounded text-sm"
            style={{
              background: "var(--muted)",
              color: "var(--foreground)",
            }}
          >
            취소
          </button>
          <button
            onClick={onSubmit}
            disabled={submitting || !reason.trim()}
            className="px-4 py-1.5 rounded text-sm font-medium text-white disabled:opacity-50"
            style={{
              background: "linear-gradient(135deg, #dc2626, #b91c1c)",
            }}
          >
            {submitting ? "거절 중..." : "거절 확정"}
          </button>
        </div>
      </div>
    </div>
  );
}
