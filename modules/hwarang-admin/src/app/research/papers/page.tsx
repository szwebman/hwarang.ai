"use client";

/**
 * Research Papers — 논문 목록 페이지
 *
 * - 필터: status (pending/parsed/summarized/applied), 적용성 점수, 키워드
 * - 카드: 제목, 저자, arxivId, 한국어 요약, 적용성 점수 게이지,
 *         화랑 적용 모듈 태그, "PDF" 링크, "GitHub" 링크
 * - 클릭 시 상세 뷰 (모달)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { adminFetch } from "@/lib/auth";

interface Paper {
  id: string;
  arxivId: string | null;
  doi: string | null;
  source: string;
  title: string;
  authors: string[];
  affiliation: string | null;
  abstract: string;
  contribution: string | null;
  methodSummary: string | null;
  experimentalResults: any;
  codeUrl: string | null;
  categories: string[];
  keywords: string[];
  publishedAt: string;
  pdfUrl: string;
  citationCount: number;
  applicabilityScore: number | null;
  applicableModules: string[];
  difficulty: string | null;
  estimatedROI: string | null;
  koreanSummary: string | null;
  status: string;
  createdAt: string;
}

interface AppItem {
  id: string;
  module: string;
  description: string;
  status: string;
}

const STATUS_OPTIONS = [
  { value: "", label: "전체 상태" },
  { value: "pending", label: "대기 (파싱 전)" },
  { value: "parsed", label: "파싱 완료" },
  { value: "summarized", label: "요약 완료" },
  { value: "applied", label: "적용 분석 완료" },
  { value: "rejected", label: "거절" },
];

const STATUS_COLOR: Record<string, string> = {
  pending: "#94a3b8",
  parsed: "#0891b2",
  summarized: "#6366f1",
  applied: "#10b981",
  rejected: "#dc2626",
};

function statusColor(s: string) {
  return STATUS_COLOR[s] || "#64748b";
}

function scoreColor(score: number | null) {
  if (score == null) return "#64748b";
  if (score >= 0.7) return "#10b981";
  if (score >= 0.4) return "#ca8a04";
  return "#dc2626";
}

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

export default function ResearchPapersPage() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({
    status: "",
    minScore: 0,
    search: "",
  });
  const [detail, setDetail] = useState<Paper | null>(null);
  const [detailApps, setDetailApps] = useState<AppItem[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      qs.set("limit", "200");
      if (filter.status) qs.set("status", filter.status);
      if (filter.minScore > 0)
        qs.set("min_score", String(filter.minScore / 100));
      const resp = await adminFetch(`/api/research/papers?${qs.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        setPapers(data.papers || []);
      } else {
        setPapers([]);
      }
    } catch (e) {
      console.error(e);
      setPapers([]);
    } finally {
      setLoading(false);
    }
  }, [filter.status, filter.minScore]);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = async (paper: Paper) => {
    setDetail(paper);
    setDetailApps([]);
    try {
      const resp = await adminFetch(`/api/research/papers/${paper.id}`);
      if (resp.ok) {
        const data = await resp.json();
        setDetailApps(data.applications || []);
      }
    } catch {
      // ignore
    }
  };

  // ── 검색 필터 ─────────────────────────────────────
  const filtered = useMemo(() => {
    if (!filter.search) return papers;
    const q = filter.search.toLowerCase();
    return papers.filter((p) => {
      if (p.title.toLowerCase().includes(q)) return true;
      if ((p.arxivId || "").toLowerCase().includes(q)) return true;
      if (p.authors.some((a) => a.toLowerCase().includes(q))) return true;
      if (p.keywords.some((k) => k.toLowerCase().includes(q))) return true;
      return false;
    });
  }, [papers, filter.search]);

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1
            className="text-2xl font-bold"
            style={{ color: "var(--foreground)" }}
          >
            연구 논문 ({papers.length})
          </h1>
          <p
            className="text-sm mt-1"
            style={{ color: "var(--muted-foreground)" }}
          >
            arXiv / OpenReview / ACL Anthology 에서 매일 수집한 화랑 관련 논문.
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
            href="/research/applications"
            className="px-3 py-2 rounded-lg text-sm font-medium text-white"
            style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}
          >
            적용 검토 →
          </Link>
        </div>
      </div>

      {/* 필터 */}
      <div
        className="rounded-xl p-4 mb-6 grid grid-cols-12 gap-4 items-center"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
      >
        <div className="col-span-3">
          <label className="text-[11px] uppercase tracking-wider opacity-60 block mb-1">
            상태
          </label>
          <select
            value={filter.status}
            onChange={(e) =>
              setFilter({ ...filter, status: e.target.value })
            }
            className="w-full px-2.5 py-1.5 rounded text-sm"
            style={{
              background: "var(--input)",
              border: "1px solid var(--border)",
              color: "var(--foreground)",
            }}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div className="col-span-4">
          <label className="text-[11px] uppercase tracking-wider opacity-60 block mb-1">
            최소 적용성:{" "}
            <span style={{ color: scoreColor(filter.minScore / 100) }}>
              {filter.minScore}
            </span>
          </label>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={filter.minScore}
            onChange={(e) =>
              setFilter({ ...filter, minScore: Number(e.target.value) })
            }
            className="w-full"
          />
        </div>
        <div className="col-span-5">
          <label className="text-[11px] uppercase tracking-wider opacity-60 block mb-1">
            검색
          </label>
          <input
            type="text"
            placeholder="제목, 저자, arxivId, 키워드..."
            value={filter.search}
            onChange={(e) =>
              setFilter({ ...filter, search: e.target.value })
            }
            className="w-full px-2.5 py-1.5 rounded text-sm"
            style={{
              background: "var(--input)",
              border: "1px solid var(--border)",
              color: "var(--foreground)",
            }}
          />
        </div>
      </div>

      {/* 카드 리스트 */}
      {loading ? (
        <div className="text-center py-12 opacity-60">로딩 중...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 opacity-60">
          조건에 맞는 논문이 없습니다.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {filtered.map((p) => (
            <PaperCard key={p.id} paper={p} onClick={() => openDetail(p)} />
          ))}
        </div>
      )}

      {/* 상세 모달 */}
      {detail && (
        <PaperDetailModal
          paper={detail}
          apps={detailApps}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}

// ──────────────────────────────────────────────
// Paper 카드
// ──────────────────────────────────────────────
function PaperCard({ paper, onClick }: { paper: Paper; onClick: () => void }) {
  const sColor = statusColor(paper.status);
  const aScore = paper.applicabilityScore || 0;
  return (
    <div
      onClick={onClick}
      className="rounded-xl p-4 cursor-pointer hover:opacity-95 transition-opacity"
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderLeft: `4px solid ${scoreColor(paper.applicabilityScore)}`,
      }}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <h3
          className="text-sm font-semibold leading-snug line-clamp-2"
          style={{ color: "var(--foreground)" }}
        >
          {paper.title}
        </h3>
        <span
          className="text-[9px] px-1.5 py-0.5 rounded shrink-0"
          style={{ background: `${sColor}22`, color: sColor }}
        >
          {paper.status}
        </span>
      </div>

      <div className="text-[11px] opacity-70 mb-2 truncate">
        {paper.authors.slice(0, 3).join(", ")}
        {paper.authors.length > 3 && ` 외 ${paper.authors.length - 3}명`}
      </div>

      <div className="flex items-center gap-2 mb-3 text-[10px]">
        <span
          className="px-1.5 py-0.5 rounded font-mono"
          style={{ background: "var(--muted)", color: "var(--foreground)" }}
        >
          {paper.arxivId || paper.doi?.slice(0, 20) || paper.source}
        </span>
        <span className="opacity-60">{fmtDate(paper.publishedAt)}</span>
        {paper.citationCount > 0 && (
          <span className="opacity-60">📑 {paper.citationCount}</span>
        )}
      </div>

      {paper.koreanSummary && (
        <p
          className="text-xs line-clamp-3 mb-3 opacity-85"
          style={{ color: "var(--foreground)" }}
        >
          {paper.koreanSummary}
        </p>
      )}

      {/* 적용성 점수 게이지 */}
      <div className="mb-2">
        <div className="flex justify-between items-center mb-1">
          <span className="text-[10px] opacity-70">적용성</span>
          <span
            className="text-xs font-bold"
            style={{ color: scoreColor(paper.applicabilityScore) }}
          >
            {paper.applicabilityScore == null
              ? "—"
              : `${(aScore * 100).toFixed(0)}%`}
          </span>
        </div>
        <div
          className="h-1.5 rounded overflow-hidden"
          style={{ background: "var(--muted)" }}
        >
          <div
            className="h-full transition-all"
            style={{
              width: `${aScore * 100}%`,
              background: scoreColor(paper.applicabilityScore),
            }}
          />
        </div>
      </div>

      {/* 모듈 태그 */}
      {paper.applicableModules.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {paper.applicableModules.slice(0, 3).map((m) => (
            <span
              key={m}
              className="text-[9px] px-1.5 py-0.5 rounded"
              style={{
                background: "rgba(99,102,241,0.15)",
                color: "#a5b4fc",
              }}
            >
              {m}
            </span>
          ))}
          {paper.applicableModules.length > 3 && (
            <span className="text-[9px] opacity-60">
              +{paper.applicableModules.length - 3}
            </span>
          )}
        </div>
      )}

      {/* 외부 링크 */}
      <div
        className="flex gap-2 pt-2"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        {paper.pdfUrl && (
          <a
            href={paper.pdfUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-[11px] px-2 py-1 rounded"
            style={{ background: "var(--muted)", color: "var(--foreground)" }}
          >
            PDF
          </a>
        )}
        {paper.codeUrl && (
          <a
            href={paper.codeUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-[11px] px-2 py-1 rounded"
            style={{ background: "var(--muted)", color: "var(--foreground)" }}
          >
            GitHub
          </a>
        )}
        {paper.difficulty && (
          <span
            className="text-[10px] px-2 py-1 rounded ml-auto"
            style={{
              background: "var(--muted)",
              color: "var(--muted-foreground)",
            }}
          >
            {paper.difficulty} / {paper.estimatedROI || "—"}
          </span>
        )}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────
// Paper 상세 모달
// ──────────────────────────────────────────────
function PaperDetailModal({
  paper,
  apps,
  onClose,
}: {
  paper: Paper;
  apps: AppItem[];
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={onClose}
    >
      <div
        className="rounded-2xl p-6 max-w-3xl w-full max-h-[90vh] overflow-y-auto"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <h2
            className="text-lg font-bold leading-tight"
            style={{ color: "var(--foreground)" }}
          >
            {paper.title}
          </h2>
          <button
            onClick={onClose}
            className="opacity-60 hover:opacity-100 text-xl leading-none shrink-0"
          >
            ×
          </button>
        </div>

        <div className="text-xs opacity-75 mb-1">
          {paper.authors.join(", ")}
          {paper.affiliation && ` — ${paper.affiliation}`}
        </div>
        <div className="flex flex-wrap items-center gap-2 mb-5 text-[11px] opacity-70">
          <span className="font-mono">
            {paper.arxivId || paper.doi || paper.source}
          </span>
          <span>·</span>
          <span>{fmtDate(paper.publishedAt)}</span>
          {paper.citationCount > 0 && (
            <>
              <span>·</span>
              <span>인용 {paper.citationCount}회</span>
            </>
          )}
        </div>

        {paper.koreanSummary && (
          <Section label="한국어 요약">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">
              {paper.koreanSummary}
            </p>
          </Section>
        )}

        {paper.contribution && (
          <Section label="핵심 기여">
            <p className="text-sm">{paper.contribution}</p>
          </Section>
        )}

        {paper.methodSummary && (
          <Section label="방법 요약">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">
              {paper.methodSummary}
            </p>
          </Section>
        )}

        <Section label="초록">
          <p
            className="text-xs leading-relaxed opacity-80"
            style={{ color: "var(--foreground)" }}
          >
            {paper.abstract}
          </p>
        </Section>

        {/* 메타 그리드 */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          <Meta label="적용성">
            <span
              className="text-base font-bold"
              style={{ color: scoreColor(paper.applicabilityScore) }}
            >
              {paper.applicabilityScore == null
                ? "—"
                : `${(paper.applicabilityScore * 100).toFixed(0)}%`}
            </span>
          </Meta>
          <Meta label="난이도">
            <span className="text-sm">{paper.difficulty || "—"}</span>
          </Meta>
          <Meta label="ROI">
            <span className="text-sm">{paper.estimatedROI || "—"}</span>
          </Meta>
        </div>

        {paper.applicableModules.length > 0 && (
          <Section label="적용 가능 모듈">
            <div className="flex flex-wrap gap-1">
              {paper.applicableModules.map((m) => (
                <span
                  key={m}
                  className="text-[11px] px-2 py-0.5 rounded"
                  style={{
                    background: "rgba(99,102,241,0.15)",
                    color: "#a5b4fc",
                  }}
                >
                  {m}
                </span>
              ))}
            </div>
          </Section>
        )}

        {paper.keywords.length > 0 && (
          <Section label="키워드">
            <div className="flex flex-wrap gap-1">
              {paper.keywords.map((k) => (
                <span
                  key={k}
                  className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{ background: "var(--muted)" }}
                >
                  {k}
                </span>
              ))}
            </div>
          </Section>
        )}

        {/* 연결된 application */}
        {apps.length > 0 && (
          <Section label={`적용 제안 (${apps.length})`}>
            <div className="space-y-2">
              {apps.map((a) => (
                <div
                  key={a.id}
                  className="rounded-lg p-3"
                  style={{
                    background: "var(--muted)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className="text-xs font-semibold"
                      style={{ color: "#a5b4fc" }}
                    >
                      {a.module}
                    </span>
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        background:
                          a.status === "approved"
                            ? "rgba(16,185,129,0.15)"
                            : a.status === "rejected"
                              ? "rgba(220,38,38,0.15)"
                              : "rgba(99,102,241,0.15)",
                        color:
                          a.status === "approved"
                            ? "#10b981"
                            : a.status === "rejected"
                              ? "#dc2626"
                              : "#6366f1",
                      }}
                    >
                      {a.status}
                    </span>
                  </div>
                  <p className="text-xs opacity-80">{a.description}</p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* 외부 링크 */}
        <div
          className="flex gap-2 pt-4"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          {paper.pdfUrl && (
            <a
              href={paper.pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 rounded text-xs"
              style={{
                background: "var(--muted)",
                color: "var(--foreground)",
              }}
            >
              📄 PDF
            </a>
          )}
          {paper.codeUrl && (
            <a
              href={paper.codeUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 rounded text-xs"
              style={{
                background: "var(--muted)",
                color: "var(--foreground)",
              }}
            >
              💻 GitHub
            </a>
          )}
          {paper.arxivId && (
            <a
              href={`https://arxiv.org/abs/${paper.arxivId}`}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 rounded text-xs"
              style={{
                background: "var(--muted)",
                color: "var(--foreground)",
              }}
            >
              🔗 arXiv
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-4">
      <div className="text-[10px] uppercase tracking-wider opacity-60 mb-1.5">
        {label}
      </div>
      {children}
    </div>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div
      className="rounded-lg p-2.5"
      style={{ background: "var(--muted)", border: "1px solid var(--border)" }}
    >
      <div className="text-[9px] opacity-60 uppercase mb-0.5">{label}</div>
      {children}
    </div>
  );
}
