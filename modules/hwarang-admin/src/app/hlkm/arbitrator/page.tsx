"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 진실 판단 (Trust Arbitration)
 * - 사실 ID 입력 → 감사 실행
 * - 결과:
 *   · 종합 점수 + verdict 뱃지 (high/medium/low/contested)
 *   · 분해 차트 (hierarchy / reputation / stance / falsifiability / retracted / independence)
 *   · 권고사항, 설명 보기(markdown)
 * - 하단: 전체 배치 재계산 모달
 */

import { useCallback, useState } from "react";

interface Breakdown {
  base_confidence?: number;
  time_decay?: number;
  source_reputation?: number;
  hierarchy_authority?: number;
  hierarchy_tier?: string;
  source_trust?: number;
  independence_factor?: number;
  independence_term?: number;
  stance_multiplier?: number;
  retracted?: boolean;
  retracted_factor?: number;
  falsifiability?: string;
  falsifiability_trust?: number;
  raw_product?: number;
}

interface AuditResult {
  fact_id: string;
  arbitrated_score: number;
  hierarchy: { tier: string; authority: number };
  provenance: { type: string; original_id: string | null; independence_count: number };
  reputation: number;
  stance: string;
  falsifiability: string;
  retraction: { retracted: boolean; reason?: string | null };
  claim_decomposition: {
    id: string;
    content?: string;
    kind?: string;
    confidence: number;
  }[];
  counter_evidence_count: number;
  breakdown: Breakdown;
  verdict: "high" | "medium" | "low" | "contested";
  recommendations: string[];
  error?: string;
}

const VERDICT_STYLE: Record<
  string,
  { label: string; color: string; bg: string; border: string }
> = {
  high: { label: "신뢰도 높음", color: "#166534", bg: "#dcfce7", border: "#86efac" },
  medium: { label: "보통", color: "#854d0e", bg: "#fef9c3", border: "#fde047" },
  low: { label: "주의", color: "#991b1b", bg: "#fee2e2", border: "#fca5a5" },
  contested: { label: "논쟁 중", color: "#6d28d9", bg: "#ede9fe", border: "#c4b5fd" },
};

export default function ArbitratorPage() {
  const [factId, setFactId] = useState("");
  const [loading, setLoading] = useState(false);
  const [audit, setAudit] = useState<AuditResult | null>(null);
  const [explanation, setExplanation] = useState<string>("");
  const [showExplain, setShowExplain] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [batchOpen, setBatchOpen] = useState(false);
  const [batchDomain, setBatchDomain] = useState("");
  const [batchLimit, setBatchLimit] = useState(500);

  const runAudit = useCallback(async () => {
    const id = factId.trim();
    if (!id) {
      setMessage({ ok: false, text: "사실 ID를 입력하세요" });
      return;
    }
    setLoading(true);
    setMessage(null);
    setAudit(null);
    setExplanation("");
    setShowExplain(false);
    try {
      const resp = await adminFetch(`/api/hlkm/arbitrator/audit/${encodeURIComponent(id)}`);
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      }
      setAudit(data);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "감사 실행 실패" });
    } finally {
      setLoading(false);
    }
  }, [factId]);

  const recompute = async () => {
    if (!audit) return;
    setBusy("recompute");
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/arbitrator/compute/${encodeURIComponent(audit.fact_id)}`,
        { method: "POST" }
      );
      const data = await resp.json();
      if (!resp.ok)
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `점수 재계산 완료: ${Number(data.score || 0).toFixed(3)}`,
      });
      runAudit();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "재계산 실패" });
    } finally {
      setBusy(null);
    }
  };

  const loadExplanation = async () => {
    if (!audit) return;
    if (explanation) {
      setShowExplain(!showExplain);
      return;
    }
    setBusy("explain");
    try {
      const resp = await adminFetch(
        `/api/hlkm/arbitrator/explain/${encodeURIComponent(audit.fact_id)}`
      );
      const data = await resp.json();
      if (!resp.ok)
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      setExplanation(data.markdown || "");
      setShowExplain(true);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "설명 불러오기 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runBatch = async () => {
    setBusy("batch");
    setMessage(null);
    try {
      const body: any = { limit: batchLimit };
      if (batchDomain.trim()) body.domain = batchDomain.trim();
      const resp = await adminFetch(`/api/hlkm/arbitrator/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!resp.ok)
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `배치 완료: 처리 ${data.processed} / 갱신 ${data.updated} / 실패 ${data.failed} / 평균 ${Number(
          data.avg_score || 0
        ).toFixed(3)}`,
      });
      setBatchOpen(false);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "배치 실패" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            진실 판단 (Trust Arbitration)
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            출처 위계 / 평판 / 입장 / 반증가능성 / 독립성 / 철회 여부를 종합해
            한 사실의 신뢰도를 판정합니다.
          </p>
        </div>
        <button
          onClick={() => setBatchOpen(true)}
          disabled={busy !== null}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
        >
          전체 배치 재계산
        </button>
      </header>

      {/* 입력 */}
      <div
        className="flex flex-wrap items-center gap-2 rounded-xl border bg-white p-4"
        style={{ borderColor: "#e5e7eb" }}
      >
        <input
          value={factId}
          onChange={(e) => setFactId(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") runAudit();
          }}
          placeholder="사실 ID (예: ckzabc...)"
          className="flex-1 rounded-lg border px-3 py-2 font-mono text-sm"
          style={{ borderColor: "#e5e7eb", minWidth: 280 }}
        />
        <button
          onClick={runAudit}
          disabled={loading || !factId.trim()}
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-60"
        >
          {loading ? "감사 중..." : "감사 실행"}
        </button>
        {audit && (
          <>
            <button
              onClick={recompute}
              disabled={busy !== null}
              className="rounded-lg border px-3 py-2 text-xs hover:bg-gray-50 disabled:opacity-60"
              style={{ borderColor: "#e5e7eb" }}
            >
              점수 재계산
            </button>
            <button
              onClick={loadExplanation}
              disabled={busy !== null}
              className="rounded-lg border px-3 py-2 text-xs hover:bg-gray-50 disabled:opacity-60"
              style={{ borderColor: "#e5e7eb" }}
            >
              {showExplain ? "설명 숨기기" : "설명 보기"}
            </button>
          </>
        )}
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

      {audit && <AuditView audit={audit} />}

      {audit && showExplain && explanation && (
        <div
          className="rounded-xl border bg-white p-6"
          style={{ borderColor: "#e5e7eb" }}
        >
          <h3 className="mb-3 text-sm font-semibold text-gray-900">
            중재 계산 상세 (Markdown)
          </h3>
          <pre
            className="overflow-x-auto rounded-lg p-4 text-[12px] leading-relaxed"
            style={{
              background: "#0f172a",
              color: "#e2e8f0",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {explanation}
          </pre>
        </div>
      )}

      {/* 배치 모달 */}
      {batchOpen && (
        <ModalOverlay onClose={() => setBatchOpen(false)}>
          <div
            className="w-full max-w-md rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">전체 배치 재계산</h2>
            <p className="mt-1 text-xs text-gray-500">
              CONFIRMED 사실의 arbitrated_score 를 재계산합니다. 도메인 필터를
              지정해 범위를 좁힐 수 있습니다.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">
                  도메인 (비워두면 전체)
                </div>
                <input
                  value={batchDomain}
                  onChange={(e) => setBatchDomain(e.target.value)}
                  placeholder="law / medical / news ..."
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">
                  처리 상한
                </div>
                <input
                  type="number"
                  value={batchLimit}
                  onChange={(e) =>
                    setBatchLimit(Math.max(1, parseInt(e.target.value) || 500))
                  }
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                  min={1}
                  max={10000}
                />
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setBatchOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runBatch}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "batch" ? "실행 중..." : "재계산 실행"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function AuditView({ audit }: { audit: AuditResult }) {
  const verdict = VERDICT_STYLE[audit.verdict] || VERDICT_STYLE.medium;
  const score = Math.max(0, Math.min(1, audit.arbitrated_score || 0));
  const bd = audit.breakdown || {};

  // 기여도 차트 데이터
  const contributions: { label: string; value: number; color: string; hint?: string }[] = [
    {
      label: "위계 권위",
      value: Number(bd.hierarchy_authority ?? 0),
      color: "#4338ca",
      hint: bd.hierarchy_tier,
    },
    {
      label: "출처 평판",
      value: Number(bd.source_reputation ?? 0),
      color: "#0d9488",
    },
    {
      label: "입장 가중치",
      value: Number(bd.stance_multiplier ?? 1),
      color: "#b45309",
      hint: audit.stance,
    },
    {
      label: "반증가능성",
      value: Number(bd.falsifiability_trust ?? 0),
      color: "#7c3aed",
      hint: audit.falsifiability,
    },
    {
      label: "철회 보정",
      value: Number(bd.retracted_factor ?? 1),
      color: audit.retraction?.retracted ? "#dc2626" : "#64748b",
      hint: audit.retraction?.retracted ? "retracted" : "정상",
    },
    {
      label: "독립성",
      value: Math.min(1, (Number(bd.independence_factor ?? 1) - 1) / 5 + 0.2),
      color: "#0891b2",
      hint: `${audit.provenance?.independence_count || 1} 독립 출처`,
    },
    {
      label: "시간 감쇠",
      value: Number(bd.time_decay ?? 1),
      color: "#525252",
    },
  ];

  return (
    <div className="space-y-4">
      {/* 상단 verdict + 점수 */}
      <div
        className="rounded-xl border bg-white p-6"
        style={{ borderColor: "#e5e7eb" }}
      >
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <div className="text-xs text-gray-500">종합 신뢰도</div>
            <div
              className="text-6xl font-bold tabular-nums"
              style={{ color: verdict.color }}
            >
              {(score * 100).toFixed(1)}
              <span className="text-2xl text-gray-400">%</span>
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <span
              className="inline-flex items-center rounded-full border px-3 py-1 text-sm font-semibold"
              style={{
                color: verdict.color,
                background: verdict.bg,
                borderColor: verdict.border,
              }}
            >
              {verdict.label}
            </span>
            <div className="text-xs text-gray-500">
              verdict = <code>{audit.verdict}</code>
            </div>
          </div>
          <div className="ml-auto grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
            <MiniStat label="tier" value={audit.hierarchy?.tier || "-"} />
            <MiniStat
              label="authority"
              value={`${(Number(audit.hierarchy?.authority || 0) * 100).toFixed(0)}%`}
            />
            <MiniStat
              label="reputation"
              value={`${(Number(audit.reputation || 0) * 100).toFixed(0)}%`}
            />
            <MiniStat label="stance" value={audit.stance || "-"} />
            <MiniStat label="falsifiability" value={audit.falsifiability || "-"} />
            <MiniStat
              label="반대 증거"
              value={`${audit.counter_evidence_count || 0}건`}
            />
          </div>
        </div>
      </div>

      {/* 분해 차트 */}
      <div
        className="rounded-xl border bg-white p-6"
        style={{ borderColor: "#e5e7eb" }}
      >
        <h3 className="mb-4 text-sm font-semibold text-gray-900">
          요인별 기여도 (breakdown)
        </h3>
        <div className="space-y-2">
          {contributions.map((c) => (
            <div key={c.label} className="flex items-center gap-3">
              <div className="w-28 shrink-0 text-xs text-gray-600">{c.label}</div>
              <div
                className="relative h-3 flex-1 overflow-hidden rounded-full"
                style={{ background: "#f1f5f9" }}
              >
                <div
                  className="absolute left-0 top-0 h-full rounded-full"
                  style={{
                    width: `${Math.max(0, Math.min(1, c.value)) * 100}%`,
                    background: c.color,
                  }}
                />
              </div>
              <div className="w-20 shrink-0 text-right text-xs tabular-nums font-semibold text-gray-800">
                {c.value.toFixed(2)}
              </div>
              <div className="w-28 shrink-0 truncate text-[11px] text-gray-500">
                {c.hint || ""}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-lg bg-gray-50 p-3 text-[11px] text-gray-600">
          <div>
            <span className="font-semibold">공식</span>:
            base × decay × (reputation × 0.3 + authority × 0.7) × (1 +
            log2(max(1, independence)) × 0.2) × stance × retracted ×
            falsifiability
          </div>
          {bd.raw_product !== undefined && (
            <div className="mt-1">
              raw product = <code>{Number(bd.raw_product).toFixed(4)}</code>
            </div>
          )}
        </div>
      </div>

      {/* 권고사항 */}
      <div
        className="rounded-xl border bg-white p-6"
        style={{ borderColor: "#e5e7eb" }}
      >
        <h3 className="mb-3 text-sm font-semibold text-gray-900">권고사항</h3>
        {audit.recommendations && audit.recommendations.length > 0 ? (
          <ul className="space-y-2 text-sm text-gray-700">
            {audit.recommendations.map((r, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-0.5 text-amber-500">▸</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-gray-500">추가 권고사항 없음</div>
        )}
      </div>

      {/* provenance + claims */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div
          className="rounded-xl border bg-white p-6"
          style={{ borderColor: "#e5e7eb" }}
        >
          <h3 className="mb-3 text-sm font-semibold text-gray-900">출처 추적</h3>
          <dl className="space-y-2 text-xs">
            <Row label="type" value={audit.provenance?.type || "-"} />
            <Row
              label="원본 ID"
              value={audit.provenance?.original_id || "— (원본)"}
              mono
            />
            <Row
              label="독립 출처 수"
              value={String(audit.provenance?.independence_count || 1)}
            />
          </dl>
        </div>
        <div
          className="rounded-xl border bg-white p-6"
          style={{ borderColor: "#e5e7eb" }}
        >
          <h3 className="mb-3 text-sm font-semibold text-gray-900">
            원자 주장 ({audit.claim_decomposition?.length || 0})
          </h3>
          {audit.claim_decomposition && audit.claim_decomposition.length > 0 ? (
            <ul className="space-y-1 text-xs text-gray-700">
              {audit.claim_decomposition.slice(0, 5).map((c) => (
                <li key={c.id} className="flex items-start justify-between gap-2">
                  <span className="truncate">{c.content || c.kind || c.id}</span>
                  <span className="shrink-0 tabular-nums text-gray-500">
                    {(Number(c.confidence || 0) * 100).toFixed(0)}%
                  </span>
                </li>
              ))}
              {audit.claim_decomposition.length > 5 && (
                <li className="text-gray-400">
                  … 외 {audit.claim_decomposition.length - 5}개
                </li>
              )}
            </ul>
          ) : (
            <div className="text-xs text-gray-500">분해된 원자 주장이 없습니다.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="rounded-lg border px-2.5 py-1.5"
      style={{ borderColor: "#e5e7eb", background: "#f9fafb" }}
    >
      <div className="text-[10px] uppercase tracking-wider text-gray-500">
        {label}
      </div>
      <div className="mt-0.5 truncate text-[12px] font-semibold text-gray-900">
        {value}
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-gray-500">{label}</dt>
      <dd
        className={
          "max-w-[60%] truncate text-right text-gray-900 " +
          (mono ? "font-mono text-[11px]" : "")
        }
      >
        {value}
      </dd>
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
