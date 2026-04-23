"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 가설 관리 (Hypothesis Generation)
 * - 자동 생성 / 고신뢰 자동 채택
 * - 상태별 필터 + 신뢰도 임계치 필터
 * - 카드별 채택/반려 (note 입력)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

type Status = "pending" | "accepted" | "rejected";

interface Hypothesis {
  id: string;
  statement: string;
  relation: string;           // CAUSES / ENABLES / RELATED_TO ...
  path_fact_ids: string[];
  rationale?: string;
  confidence: number;         // 0..1
  status: Status;
  created_at: string;
  reviewed_at?: string;
  reviewer_note?: string;
}

const STATUS_FILTERS: { key: Status | "all"; label: string }[] = [
  { key: "pending", label: "대기" },
  { key: "accepted", label: "채택" },
  { key: "rejected", label: "반려" },
  { key: "all", label: "전체" },
];

const RELATION_COLORS: Record<string, { color: string; bg: string }> = {
  CAUSES: { color: "#b91c1c", bg: "#fee2e2" },
  ENABLES: { color: "#15803d", bg: "#dcfce7" },
  RELATED_TO: { color: "#1d4ed8", bg: "#dbeafe" },
  PRECEDES: { color: "#7c3aed", bg: "#ede9fe" },
  CONTRADICTS: { color: "#c2410c", bg: "#ffedd5" },
};

function relationStyle(rel: string) {
  return RELATION_COLORS[rel] || { color: "#475569", bg: "#e2e8f0" };
}

export default function HypothesesPage() {
  const [status, setStatus] = useState<Status | "all">("pending");
  const [minConfidence, setMinConfidence] = useState(0.5);
  const [items, setItems] = useState<Hypothesis[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [generateOpen, setGenerateOpen] = useState(false);
  const [genMaxCount, setGenMaxCount] = useState(10);
  const [genConfThreshold, setGenConfThreshold] = useState(0.5);

  const [autoAcceptOpen, setAutoAcceptOpen] = useState(false);
  const [autoThreshold, setAutoThreshold] = useState(0.85);

  const [reviewTarget, setReviewTarget] = useState<{ h: Hypothesis; decision: "accept" | "reject" } | null>(null);
  const [reviewNote, setReviewNote] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (status !== "all") qs.set("status", status);
      qs.set("min_confidence", String(minConfidence));
      const resp = await adminFetch(`/api/hlkm/hypotheses?${qs.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        const list: Hypothesis[] = Array.isArray(data) ? data : data.items || [];
        setItems(list);
      } else {
        setItems([]);
      }
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [status, minConfidence]);

  useEffect(() => { reload(); }, [reload]);

  // 상태별 요약 (전체 기준). 필터 상태와 무관하게 별도 fetch
  const [summary, setSummary] = useState({ pending: 0, accepted: 0, rejected: 0 });
  useEffect(() => {
    let alive = true;
    Promise.all(
      (["pending", "accepted", "rejected"] as Status[]).map((s) =>
        adminFetch(`/api/hlkm/hypotheses?status=${s}&min_confidence=0`)
          .then((r) => r.ok ? r.json() : null)
          .then((d) => {
            const list = Array.isArray(d) ? d : d?.items || [];
            return list.length;
          })
          .catch(() => 0)
      )
    ).then(([p, a, r]) => {
      if (alive) setSummary({ pending: p, accepted: a, rejected: r });
    });
    return () => { alive = false; };
  }, [items]);

  const filtered = useMemo(() => items, [items]);

  const runGenerate = async () => {
    setBusy("generate");
    setMessage(null);
    try {
      const resp = await adminFetch("/api/hlkm/hypotheses/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          max_count: genMaxCount,
          confidence_threshold: genConfThreshold,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      const cnt = data.created ?? data.count ?? 0;
      setMessage({ ok: true, text: `${cnt.toLocaleString("ko-KR")}건 생성 완료` });
      setGenerateOpen(false);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "생성 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runAutoAccept = async () => {
    setBusy("auto-accept");
    setMessage(null);
    try {
      const resp = await adminFetch("/api/hlkm/hypotheses/auto-accept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ threshold: autoThreshold }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      const cnt = data.accepted ?? data.count ?? 0;
      setMessage({ ok: true, text: `${cnt.toLocaleString("ko-KR")}건 자동 채택` });
      setAutoAcceptOpen(false);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "자동 채택 실패" });
    } finally {
      setBusy(null);
    }
  };

  const openReview = (h: Hypothesis, decision: "accept" | "reject") => {
    setReviewTarget({ h, decision });
    setReviewNote("");
  };

  const submitReview = async () => {
    if (!reviewTarget) return;
    setBusy(reviewTarget.h.id);
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/hypotheses/${reviewTarget.h.id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision: reviewTarget.decision,
          note: reviewNote,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: reviewTarget.decision === "accept" ? "채택 처리되었습니다" : "반려 처리되었습니다",
      });
      setReviewTarget(null);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "처리 실패" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">가설 관리</h1>
          <p className="mt-1 text-sm text-gray-500">
            Hypothesis Generation — 그래프 경로 기반으로 생성된 후보 가설을 검토하고 채택합니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setGenerateOpen(true)}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            자동 생성
          </button>
          <button
            onClick={() => setAutoAcceptOpen(true)}
            disabled={busy !== null}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
          >
            고신뢰 자동 채택
          </button>
        </div>
      </header>

      {/* 요약 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="대기" value={summary.pending} accent="warning" />
        <StatCard label="채택" value={summary.accepted} accent="success" />
        <StatCard label="반려" value={summary.rejected} accent="danger" />
      </div>

      {/* 필터 바 */}
      <div
        className="flex flex-wrap items-center gap-4 rounded-xl border bg-white p-4"
        style={{ borderColor: "#e5e7eb" }}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setStatus(f.key)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                status === f.key
                  ? "bg-blue-600 text-white"
                  : "text-gray-700 hover:bg-gray-100"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2">
          <span className="text-xs text-gray-600">
            최소 신뢰도 ({(minConfidence * 100).toFixed(0)}%)
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={minConfidence}
            onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
            className="w-32"
          />
        </label>
        <span className="ml-auto text-xs text-gray-500">
          {loading ? "불러오는 중..." : `${filtered.length.toLocaleString("ko-KR")}건`}
        </span>
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

      {/* 가설 카드 리스트 */}
      {filtered.length === 0 && !loading ? (
        <div
          className="rounded-xl border bg-white p-10 text-center"
          style={{ borderColor: "#e5e7eb" }}
        >
          <div className="text-sm text-gray-500">아직 데이터가 없습니다</div>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((h) => (
            <HypothesisCard
              key={h.id}
              h={h}
              onReview={openReview}
              busy={busy === h.id}
              disabled={busy !== null}
            />
          ))}
        </div>
      )}

      {/* 자동 생성 모달 */}
      {generateOpen && (
        <ModalOverlay onClose={() => setGenerateOpen(false)}>
          <div className="w-full max-w-md rounded-xl border bg-white p-6" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="text-lg font-bold text-gray-900">가설 자동 생성</h2>
            <p className="mt-1 text-xs text-gray-500">
              그래프 경로를 탐색하여 후보 가설을 생성합니다.
            </p>

            <div className="mt-4 space-y-4">
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">최대 생성 개수</label>
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={genMaxCount}
                  onChange={(e) => setGenMaxCount(parseInt(e.target.value) || 10)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">
                  신뢰도 임계치 ({(genConfThreshold * 100).toFixed(0)}%)
                </label>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={genConfThreshold}
                  onChange={(e) => setGenConfThreshold(parseFloat(e.target.value))}
                  className="w-full"
                />
                <div className="mt-1 text-[10px] text-gray-500">
                  이 값 미만의 후보는 저장되지 않습니다
                </div>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setGenerateOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runGenerate}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "generate" ? "생성 중..." : "생성 실행"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}

      {/* 자동 채택 모달 */}
      {autoAcceptOpen && (
        <ModalOverlay onClose={() => setAutoAcceptOpen(false)}>
          <div className="w-full max-w-md rounded-xl border bg-white p-6" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="text-lg font-bold text-gray-900">고신뢰 자동 채택</h2>
            <p className="mt-1 text-xs text-gray-500">
              임계치 이상의 신뢰도를 가진 대기 가설을 일괄 채택합니다.
            </p>

            <div className="mt-4">
              <label className="mb-1 block text-xs font-semibold text-gray-700">
                채택 임계치 ({(autoThreshold * 100).toFixed(0)}%)
              </label>
              <input
                type="range"
                min={0.5}
                max={1}
                step={0.01}
                value={autoThreshold}
                onChange={(e) => setAutoThreshold(parseFloat(e.target.value))}
                className="w-full"
              />
              <div className="mt-1 flex justify-between text-[10px] text-gray-500">
                <span>보수적 권장 0.85 이상</span>
                <span className="tabular-nums font-semibold">{autoThreshold.toFixed(2)}</span>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setAutoAcceptOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runAutoAccept}
                disabled={busy !== null}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
              >
                {busy === "auto-accept" ? "처리 중..." : "채택 실행"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}

      {/* 리뷰 모달 */}
      {reviewTarget && (
        <ModalOverlay onClose={() => setReviewTarget(null)}>
          <div className="w-full max-w-lg rounded-xl border bg-white p-6" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="text-lg font-bold text-gray-900">
              {reviewTarget.decision === "accept" ? "가설 채택" : "가설 반려"}
            </h2>
            <div className="mt-2 rounded-lg bg-gray-50 p-3 text-sm text-gray-800 whitespace-pre-wrap">
              {reviewTarget.h.statement}
            </div>

            <div className="mt-4">
              <label className="mb-1 block text-xs font-semibold text-gray-700">메모 (선택)</label>
              <textarea
                value={reviewNote}
                onChange={(e) => setReviewNote(e.target.value)}
                rows={3}
                placeholder="검토 의견 / 근거 / 조치 사항"
                className="w-full rounded-lg border p-2 text-sm"
                style={{ borderColor: "#e5e7eb" }}
              />
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setReviewTarget(null)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={submitReview}
                disabled={busy !== null}
                className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-60 ${
                  reviewTarget.decision === "accept"
                    ? "bg-green-600 hover:bg-green-700"
                    : "bg-red-600 hover:bg-red-700"
                }`}
              >
                {busy === reviewTarget.h.id
                  ? "처리 중..."
                  : reviewTarget.decision === "accept" ? "채택" : "반려"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function HypothesisCard({
  h,
  onReview,
  busy,
  disabled,
}: {
  h: Hypothesis;
  onReview: (h: Hypothesis, decision: "accept" | "reject") => void;
  busy: boolean;
  disabled: boolean;
}) {
  const rel = relationStyle(h.relation);
  const statusStyle =
    h.status === "accepted"
      ? { color: "#15803d", bg: "#dcfce7", label: "채택" }
      : h.status === "rejected"
      ? { color: "#b91c1c", bg: "#fee2e2", label: "반려" }
      : { color: "#b45309", bg: "#fef3c7", label: "대기" };

  return (
    <article
      className="rounded-xl border bg-white p-5"
      style={{ borderColor: "#e5e7eb" }}
    >
      <header className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span
          className="rounded px-2 py-1 font-medium"
          style={{ color: rel.color, background: rel.bg }}
        >
          {h.relation}
        </span>
        <span
          className="rounded px-2 py-1 font-medium"
          style={{ color: statusStyle.color, background: statusStyle.bg }}
        >
          {statusStyle.label}
        </span>
        <span className="ml-auto text-gray-500">
          생성: {new Date(h.created_at).toLocaleDateString("ko-KR")}
        </span>
      </header>

      <div className="text-sm text-gray-900 whitespace-pre-wrap">{h.statement}</div>

      {/* 신뢰도 바 */}
      <div className="mt-3 flex items-center gap-3">
        <div className="text-[11px] font-semibold text-gray-600">신뢰도</div>
        <ConfidenceBar score={h.confidence} />
      </div>

      {/* 경로 */}
      {h.path_fact_ids && h.path_fact_ids.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[11px] font-semibold text-gray-500">추론 경로</div>
          <div className="flex flex-wrap items-center gap-1.5">
            {h.path_fact_ids.map((fid, idx) => (
              <span key={fid + idx} className="flex items-center gap-1.5">
                <span
                  className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-700"
                  title={fid}
                >
                  {fid.slice(0, 8)}
                </span>
                {idx < h.path_fact_ids.length - 1 && (
                  <span className="text-gray-400">→</span>
                )}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 근거 */}
      {h.rationale && (
        <div className="mt-3 rounded-lg bg-gray-50 p-3 text-xs text-gray-700 whitespace-pre-wrap">
          <span className="font-semibold text-gray-600">근거 · </span>
          {h.rationale}
        </div>
      )}

      {/* 리뷰 메모 (이미 처리된 경우) */}
      {h.status !== "pending" && h.reviewer_note && (
        <div className="mt-3 rounded-lg border border-dashed p-3 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
          <span className="font-semibold">검토 메모 · </span>
          {h.reviewer_note}
          {h.reviewed_at && (
            <span className="ml-2 text-gray-400">
              ({new Date(h.reviewed_at).toLocaleString("ko-KR")})
            </span>
          )}
        </div>
      )}

      {/* 액션 */}
      {h.status === "pending" && (
        <div
          className="mt-4 flex flex-wrap gap-2 border-t pt-4"
          style={{ borderColor: "#e5e7eb" }}
        >
          <button
            onClick={() => onReview(h, "accept")}
            disabled={disabled}
            className="flex-1 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
          >
            채택
          </button>
          <button
            onClick={() => onReview(h, "reject")}
            disabled={disabled}
            className="flex-1 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
          >
            반려
          </button>
          {busy && <span className="text-xs text-gray-500">처리 중...</span>}
        </div>
      )}
    </article>
  );
}

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const color = score >= 0.85 ? "#16a34a" : score >= 0.6 ? "#2563eb" : score >= 0.4 ? "#d97706" : "#dc2626";
  return (
    <div className="flex flex-1 items-center gap-2">
      <div className="relative h-2 flex-1 overflow-hidden rounded-full" style={{ background: "#f1f5f9" }}>
        <div
          className="absolute left-0 top-0 h-full rounded-full"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="w-10 text-right text-xs tabular-nums font-semibold" style={{ color }}>
        {pct.toFixed(0)}%
      </span>
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
