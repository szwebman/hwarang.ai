"use client";

/**
 * Trusted Sources 관리 페이지
 *
 * - 22개 한국 출처 (정부 / 학술 / 메이저언론 / 팩트체커 / 의료 / 금융) 관리
 * - 신뢰도 슬라이더 (실시간 PUT, 500ms debounce)
 * - 즉시 크롤 트리거
 * - 추가 / 수정 / 삭제 모달
 *
 * 백엔드 API: /api/trusted-sources (Next 프록시) → ${HWARANG_API_URL}/api/sources
 */

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { adminFetch } from "@/lib/auth";

interface TrustedSource {
  id: string;
  domain: string;
  displayName: string;
  type: string;
  trustLevel: number;
  isWhitelisted: boolean;
  isPrimarySource: boolean;
  domains: string[];
  crawlSchedule: string;
  crawlMethod: string;
  rssUrl: string | null;
  selectors?: any;
  totalCrawled: number;
  totalFacts: number;
  successRate: number;
  lastCrawledAt: string | null;
  contradictionCount: number;
  notes: string | null;
}

const TYPE_OPTIONS = [
  { value: "government", label: "정부", color: "#1d4ed8" },
  { value: "academic", label: "학술", color: "#7c3aed" },
  { value: "news_major", label: "메이저 언론", color: "#0891b2" },
  { value: "news_minor", label: "소규모 언론", color: "#64748b" },
  { value: "fact_checker", label: "팩트체커", color: "#10b981" },
  { value: "medical", label: "의료", color: "#dc2626" },
  { value: "financial", label: "금융", color: "#ca8a04" },
];

const TRUST_BANDS = [
  { min: 90, label: "1차 출처 (90+)", color: "#10b981" },
  { min: 70, label: "고신뢰 (70~89)", color: "#0891b2" },
  { min: 50, label: "중신뢰 (50~69)", color: "#ca8a04" },
  { min: 0, label: "저신뢰 (0~49)", color: "#dc2626" },
];

const CRAWL_METHODS = ["rss", "api", "sitemap", "custom"];
const SCHEDULE_PRESETS = [
  { value: "0 */1 * * *", label: "매시간" },
  { value: "0 */6 * * *", label: "6시간마다" },
  { value: "0 0 */1 * *", label: "매일 자정" },
  { value: "0 0 */7 * *", label: "주 1회" },
];

function trustColor(level: number): string {
  for (const band of TRUST_BANDS) {
    if (level >= band.min) return band.color;
  }
  return "#dc2626";
}

function trustLabel(level: number): string {
  for (const band of TRUST_BANDS) {
    if (level >= band.min) return band.label;
  }
  return "저신뢰";
}

function typeMeta(type: string) {
  return TYPE_OPTIONS.find((t) => t.value === type) || { value: type, label: type, color: "#64748b" };
}

function fmtRel(iso: string | null): string {
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

interface EditFormState {
  id?: string;
  domain: string;
  displayName: string;
  type: string;
  trustLevel: number;
  isWhitelisted: boolean;
  isPrimarySource: boolean;
  domains: string[];
  crawlSchedule: string;
  crawlMethod: string;
  rssUrl: string;
  selectorsJson: string;
  notes: string;
}

const blankForm: EditFormState = {
  domain: "",
  displayName: "",
  type: "news_major",
  trustLevel: 70,
  isWhitelisted: true,
  isPrimarySource: false,
  domains: [],
  crawlSchedule: "0 */6 * * *",
  crawlMethod: "rss",
  rssUrl: "",
  selectorsJson: "{}",
  notes: "",
};

export default function TrustedSourcesPage() {
  const [sources, setSources] = useState<TrustedSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<EditFormState | null>(null);
  const [crawlingId, setCrawlingId] = useState<string | null>(null);
  const [filter, setFilter] = useState({ type: "", minTrust: 0, search: "" });
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  const debouncers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await adminFetch("/api/trusted-sources");
      if (resp.ok) {
        const data = await resp.json();
        const list = Array.isArray(data) ? data : data.sources || data.items || [];
        setSources(list);
      } else {
        setSources([]);
      }
    } catch (e) {
      console.error(e);
      setSources([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // ── 신뢰도 슬라이더: 즉시 UI 반영 + 500ms debounce 후 PUT ──
  const handleTrustChange = (id: string, newTrust: number) => {
    setSources((prev) => prev.map((s) => (s.id === id ? { ...s, trustLevel: newTrust } : s)));
    if (debouncers.current[id]) clearTimeout(debouncers.current[id]);
    debouncers.current[id] = setTimeout(async () => {
      try {
        await adminFetch(`/api/trusted-sources/${id}`, {
          method: "PUT",
          body: JSON.stringify({ trustLevel: newTrust }),
        });
      } catch {}
    }, 500);
  };

  const handleToggle = async (id: string, key: "isWhitelisted" | "isPrimarySource", value: boolean) => {
    setSources((prev) => prev.map((s) => (s.id === id ? { ...s, [key]: value } : s)));
    try {
      await adminFetch(`/api/trusted-sources/${id}`, {
        method: "PUT",
        body: JSON.stringify({ [key]: value }),
      });
    } catch {}
  };

  const handleSave = async (form: EditFormState) => {
    let parsedSelectors: any = {};
    try {
      parsedSelectors = JSON.parse(form.selectorsJson || "{}");
    } catch {
      setToast({ ok: false, text: "셀렉터 JSON 형식이 잘못되었습니다" });
      return;
    }
    const payload: any = {
      domain: form.domain,
      displayName: form.displayName,
      type: form.type,
      trustLevel: form.trustLevel,
      isWhitelisted: form.isWhitelisted,
      isPrimarySource: form.isPrimarySource,
      domains: form.domains,
      crawlSchedule: form.crawlSchedule,
      crawlMethod: form.crawlMethod,
      rssUrl: form.rssUrl || null,
      selectors: parsedSelectors,
      notes: form.notes || null,
    };
    const method = form.id ? "PUT" : "POST";
    const url = form.id ? `/api/trusted-sources/${form.id}` : "/api/trusted-sources";
    try {
      const resp = await adminFetch(url, { method, body: JSON.stringify(payload) });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setToast({ ok: false, text: err.error || `저장 실패 (${resp.status})` });
        return;
      }
      setToast({ ok: true, text: form.id ? "수정 완료" : "추가 완료" });
      setEditing(null);
      reload();
    } catch (e: any) {
      setToast({ ok: false, text: e?.message || "저장 실패" });
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`"${name}" 출처를 삭제하시겠습니까?\n(이미 수집된 사실은 유지됩니다)`)) return;
    try {
      const resp = await adminFetch(`/api/trusted-sources/${id}`, { method: "DELETE" });
      if (!resp.ok) {
        setToast({ ok: false, text: "삭제 실패" });
        return;
      }
      setToast({ ok: true, text: "삭제 완료" });
      reload();
    } catch {
      setToast({ ok: false, text: "삭제 실패" });
    }
  };

  const handleCrawl = async (id: string, name: string) => {
    setCrawlingId(id);
    try {
      const resp = await adminFetch(`/api/trusted-sources/${id}/crawl`, { method: "POST" });
      const result = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(result.error || `HTTP ${resp.status}`);
      setToast({
        ok: true,
        text: `[${name}] 크롤링 완료 — 수집 ${result.crawled || 0}건 / 새 사실 ${result.ingested || 0}건`,
      });
      reload();
    } catch (e: any) {
      setToast({ ok: false, text: `[${name}] 크롤 실패: ${e?.message || e}` });
    } finally {
      setCrawlingId(null);
    }
  };

  // ── 필터링 ──
  const filtered = useMemo(() => {
    return sources.filter((s) => {
      if (filter.type && s.type !== filter.type) return false;
      if (s.trustLevel < filter.minTrust) return false;
      if (filter.search) {
        const q = filter.search.toLowerCase();
        if (!s.displayName.toLowerCase().includes(q) && !s.domain.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [sources, filter]);

  // ── 통계 ──
  const stats = useMemo(() => {
    const total = sources.length;
    const whitelisted = sources.filter((s) => s.isWhitelisted).length;
    const primary = sources.filter((s) => s.isPrimarySource).length;
    const dayAgo = Date.now() - 24 * 3600 * 1000;
    const recent = sources.filter((s) => s.lastCrawledAt && new Date(s.lastCrawledAt).getTime() > dayAgo).length;
    return { total, whitelisted, primary, recent };
  }, [sources]);

  // ── 토스트 자동 사라짐 ──
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--foreground)" }}>
            신뢰 출처 (Trusted Sources)
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--muted-foreground)" }}>
            화랑 AI 가 인용하는 1차 출처. 신뢰도가 응답 가중치에 영향을 줍니다.
          </p>
        </div>
        <button
          onClick={() => setEditing({ ...blankForm })}
          className="px-4 py-2 rounded-lg text-sm font-medium text-white"
          style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}
        >
          + 출처 추가
        </button>
      </div>

      {/* 통계 4박스 */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatBox label="전체" value={stats.total} color="#6366f1" />
        <StatBox label="화이트리스트" value={stats.whitelisted} color="#0891b2" />
        <StatBox label="1차 출처" value={stats.primary} color="#10b981" />
        <StatBox label="24h 내 크롤됨" value={stats.recent} color="#ca8a04" />
      </div>

      {/* 필터 바 */}
      <div className="rounded-xl p-4 mb-6 grid grid-cols-12 gap-4 items-center"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
        <div className="col-span-3">
          <label className="text-[11px] uppercase tracking-wider opacity-60 block mb-1">타입</label>
          <select
            value={filter.type}
            onChange={(e) => setFilter({ ...filter, type: e.target.value })}
            className="w-full px-2.5 py-1.5 rounded text-sm"
            style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
          >
            <option value="">전체 타입</option>
            {TYPE_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        <div className="col-span-4">
          <label className="text-[11px] uppercase tracking-wider opacity-60 block mb-1">
            최소 신뢰도: <span style={{ color: trustColor(filter.minTrust) }}>{filter.minTrust}</span>
          </label>
          <input
            type="range"
            min={0}
            max={100}
            value={filter.minTrust}
            onChange={(e) => setFilter({ ...filter, minTrust: Number(e.target.value) })}
            className="w-full"
          />
        </div>

        <div className="col-span-5">
          <label className="text-[11px] uppercase tracking-wider opacity-60 block mb-1">검색</label>
          <input
            type="text"
            placeholder="도메인 또는 표시이름..."
            value={filter.search}
            onChange={(e) => setFilter({ ...filter, search: e.target.value })}
            className="w-full px-2.5 py-1.5 rounded text-sm"
            style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
          />
        </div>
      </div>

      {/* 토스트 */}
      {toast && (
        <div
          className="mb-4 px-4 py-2.5 rounded-lg text-sm"
          style={{
            background: toast.ok ? "rgba(16,185,129,0.12)" : "rgba(220,38,38,0.12)",
            color: toast.ok ? "#10b981" : "#dc2626",
            border: `1px solid ${toast.ok ? "#10b98144" : "#dc262644"}`,
          }}
        >
          {toast.text}
        </div>
      )}

      {/* 카드 리스트 */}
      {loading ? (
        <div className="text-center py-12 opacity-60">로딩 중...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 opacity-60">출처가 없습니다.</div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {filtered.map((s) => (
            <SourceCard
              key={s.id}
              source={s}
              onTrustChange={(v) => handleTrustChange(s.id, v)}
              onToggle={(k, v) => handleToggle(s.id, k, v)}
              onCrawl={() => handleCrawl(s.id, s.displayName)}
              onEdit={() =>
                setEditing({
                  id: s.id,
                  domain: s.domain,
                  displayName: s.displayName,
                  type: s.type,
                  trustLevel: s.trustLevel,
                  isWhitelisted: s.isWhitelisted,
                  isPrimarySource: s.isPrimarySource,
                  domains: s.domains || [],
                  crawlSchedule: s.crawlSchedule || "0 */6 * * *",
                  crawlMethod: s.crawlMethod || "rss",
                  rssUrl: s.rssUrl || "",
                  selectorsJson: JSON.stringify(s.selectors || {}, null, 2),
                  notes: s.notes || "",
                })
              }
              onDelete={() => handleDelete(s.id, s.displayName)}
              crawling={crawlingId === s.id}
            />
          ))}
        </div>
      )}

      {/* 편집 모달 */}
      {editing && (
        <EditModal
          form={editing}
          onChange={setEditing}
          onClose={() => setEditing(null)}
          onSave={() => handleSave(editing)}
        />
      )}
    </div>
  );
}

// ──────────────────────────────────────────────
// 통계 박스
// ──────────────────────────────────────────────
function StatBox({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div
      className="rounded-xl p-4"
      style={{ background: "var(--card)", border: "1px solid var(--border)" }}
    >
      <div className="text-[11px] uppercase tracking-wider opacity-60 mb-1.5">{label}</div>
      <div className="text-2xl font-bold" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────
// 출처 카드
// ──────────────────────────────────────────────
interface SourceCardProps {
  source: TrustedSource;
  onTrustChange: (v: number) => void;
  onToggle: (key: "isWhitelisted" | "isPrimarySource", value: boolean) => void;
  onCrawl: () => void;
  onEdit: () => void;
  onDelete: () => void;
  crawling: boolean;
}

function SourceCard({ source, onTrustChange, onToggle, onCrawl, onEdit, onDelete, crawling }: SourceCardProps) {
  const t = typeMeta(source.type);
  const tColor = trustColor(source.trustLevel);

  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--card)",
        border: `1px solid var(--border)`,
        borderLeft: `4px solid ${tColor}`,
      }}
    >
      {/* 상단: 이름 + 타입 배지 */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="font-semibold truncate" style={{ color: "var(--foreground)" }}>
              {source.displayName}
            </span>
            {source.isPrimarySource && (
              <span className="text-[9px] px-1.5 py-0.5 rounded font-bold"
                style={{ background: "rgba(16,185,129,0.18)", color: "#10b981" }}>
                1차
              </span>
            )}
          </div>
          <div className="text-xs truncate" style={{ color: "var(--muted-foreground)" }}>
            {source.domain}
          </div>
        </div>
        <span
          className="text-[10px] px-2 py-0.5 rounded shrink-0"
          style={{ background: `${t.color}22`, color: t.color }}
        >
          {t.label}
        </span>
      </div>

      {/* 신뢰도 슬라이더 */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] opacity-70">신뢰도</span>
          <span className="text-sm font-bold" style={{ color: tColor }}>
            {source.trustLevel} <span className="text-[10px] opacity-70">({trustLabel(source.trustLevel)})</span>
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          value={source.trustLevel}
          onChange={(e) => onTrustChange(Number(e.target.value))}
          className="w-full"
          style={{ accentColor: tColor }}
        />
      </div>

      {/* 토글 */}
      <div className="flex gap-3 mb-3 text-xs">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={source.isWhitelisted}
            onChange={(e) => onToggle("isWhitelisted", e.target.checked)}
          />
          <span>활성</span>
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={source.isPrimarySource}
            onChange={(e) => onToggle("isPrimarySource", e.target.checked)}
          />
          <span>1차 출처</span>
        </label>
      </div>

      {/* 통계 */}
      <div className="grid grid-cols-4 gap-2 mb-3 pt-3" style={{ borderTop: "1px solid var(--border)" }}>
        <StatMini label="수집" value={source.totalCrawled} />
        <StatMini label="사실" value={source.totalFacts} />
        <StatMini
          label="성공률"
          value={`${(source.successRate * 100).toFixed(0)}%`}
          color={source.successRate > 0.8 ? "#10b981" : source.successRate > 0.5 ? "#ca8a04" : "#dc2626"}
        />
        <StatMini label="마지막" value={fmtRel(source.lastCrawledAt)} />
      </div>

      {source.contradictionCount > 0 && (
        <div className="mb-3 text-[11px] px-2 py-1 rounded"
          style={{ background: "rgba(220,38,38,0.1)", color: "#dc2626" }}>
          ⚠ 모순 {source.contradictionCount}건
        </div>
      )}

      {/* 액션 버튼 */}
      <div className="flex gap-2">
        <button
          onClick={onCrawl}
          disabled={crawling}
          className="flex-1 px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50"
          style={{
            background: crawling ? "rgba(99,102,241,0.1)" : "rgba(99,102,241,0.15)",
            color: "#6366f1",
          }}
        >
          {crawling ? "크롤링 중..." : "🧪 즉시 크롤"}
        </button>
        <button
          onClick={onEdit}
          className="px-3 py-1.5 rounded text-xs"
          style={{ background: "var(--muted)", color: "var(--foreground)" }}
        >
          수정
        </button>
        <button
          onClick={onDelete}
          className="px-3 py-1.5 rounded text-xs"
          style={{ background: "rgba(220,38,38,0.1)", color: "#dc2626" }}
        >
          삭제
        </button>
      </div>
    </div>
  );
}

function StatMini({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div>
      <div className="text-[9px] opacity-60 uppercase">{label}</div>
      <div className="text-xs font-medium" style={{ color: color || "var(--foreground)" }}>
        {value}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────
// 추가/수정 모달
// ──────────────────────────────────────────────
interface EditModalProps {
  form: EditFormState;
  onChange: (form: EditFormState) => void;
  onClose: () => void;
  onSave: () => void;
}

function EditModal({ form, onChange, onClose, onSave }: EditModalProps) {
  const isNew = !form.id;
  const [domainInput, setDomainInput] = useState("");

  const addDomain = () => {
    const d = domainInput.trim();
    if (!d) return;
    if (form.domains.includes(d)) return;
    onChange({ ...form, domains: [...form.domains, d] });
    setDomainInput("");
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={onClose}
    >
      <div
        className="rounded-2xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold" style={{ color: "var(--foreground)" }}>
            {isNew ? "출처 추가" : "출처 수정"}
          </h2>
          <button onClick={onClose} className="opacity-60 hover:opacity-100 text-xl leading-none">
            ×
          </button>
        </div>

        <div className="space-y-4">
          {/* 도메인 + 표시이름 */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="대표 도메인 *">
              <input
                type="text"
                value={form.domain}
                placeholder="law.go.kr"
                onChange={(e) => onChange({ ...form, domain: e.target.value })}
                className="w-full px-2.5 py-1.5 rounded text-sm"
                style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
              />
            </Field>
            <Field label="표시 이름 *">
              <input
                type="text"
                value={form.displayName}
                placeholder="국가법령정보센터"
                onChange={(e) => onChange({ ...form, displayName: e.target.value })}
                className="w-full px-2.5 py-1.5 rounded text-sm"
                style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
              />
            </Field>
          </div>

          {/* 타입 + 신뢰도 */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="타입">
              <select
                value={form.type}
                onChange={(e) => onChange({ ...form, type: e.target.value })}
                className="w-full px-2.5 py-1.5 rounded text-sm"
                style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
              >
                {TYPE_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </Field>
            <Field label={`신뢰도: ${form.trustLevel} (${trustLabel(form.trustLevel)})`}>
              <input
                type="range"
                min={0}
                max={100}
                value={form.trustLevel}
                onChange={(e) => onChange({ ...form, trustLevel: Number(e.target.value) })}
                className="w-full"
                style={{ accentColor: trustColor(form.trustLevel) }}
              />
            </Field>
          </div>

          {/* 토글 */}
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.isWhitelisted}
                onChange={(e) => onChange({ ...form, isWhitelisted: e.target.checked })}
              />
              화이트리스트 (활성)
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.isPrimarySource}
                onChange={(e) => onChange({ ...form, isPrimarySource: e.target.checked })}
              />
              1차 출처로 지정
            </label>
          </div>

          {/* 추가 도메인 멀티 */}
          <Field label="추가 도메인 (선택)">
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={domainInput}
                placeholder="예: m.law.go.kr"
                onChange={(e) => setDomainInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addDomain();
                  }
                }}
                className="flex-1 px-2.5 py-1.5 rounded text-sm"
                style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
              />
              <button
                type="button"
                onClick={addDomain}
                className="px-3 py-1.5 rounded text-xs"
                style={{ background: "var(--muted)", color: "var(--foreground)" }}
              >
                추가
              </button>
            </div>
            {form.domains.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {form.domains.map((d) => (
                  <span
                    key={d}
                    className="text-[11px] px-2 py-0.5 rounded flex items-center gap-1"
                    style={{ background: "rgba(99,102,241,0.15)", color: "#6366f1" }}
                  >
                    {d}
                    <button
                      type="button"
                      onClick={() => onChange({ ...form, domains: form.domains.filter((x) => x !== d) })}
                      className="opacity-60 hover:opacity-100"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </Field>

          {/* 크롤 메서드 + 스케줄 */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="크롤 방법">
              <select
                value={form.crawlMethod}
                onChange={(e) => onChange({ ...form, crawlMethod: e.target.value })}
                className="w-full px-2.5 py-1.5 rounded text-sm"
                style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
              >
                {CRAWL_METHODS.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </Field>
            <Field label="스케줄 (cron)">
              <select
                value={form.crawlSchedule}
                onChange={(e) => onChange({ ...form, crawlSchedule: e.target.value })}
                className="w-full px-2.5 py-1.5 rounded text-sm"
                style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
              >
                {SCHEDULE_PRESETS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label} ({p.value})</option>
                ))}
              </select>
            </Field>
          </div>

          {/* RSS URL */}
          {form.crawlMethod === "rss" && (
            <Field label="RSS URL">
              <input
                type="text"
                value={form.rssUrl}
                placeholder="https://example.com/rss.xml"
                onChange={(e) => onChange({ ...form, rssUrl: e.target.value })}
                className="w-full px-2.5 py-1.5 rounded text-sm"
                style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
              />
            </Field>
          )}

          {/* 셀렉터 JSON */}
          {(form.crawlMethod === "custom" || form.crawlMethod === "sitemap") && (
            <Field label="셀렉터 JSON">
              <textarea
                value={form.selectorsJson}
                onChange={(e) => onChange({ ...form, selectorsJson: e.target.value })}
                rows={5}
                className="w-full px-2.5 py-1.5 rounded text-sm font-mono"
                style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                placeholder={'{\n  "title": ".article-title",\n  "body": ".article-body"\n}'}
              />
            </Field>
          )}

          {/* 메모 */}
          <Field label="메모">
            <textarea
              value={form.notes}
              onChange={(e) => onChange({ ...form, notes: e.target.value })}
              rows={2}
              className="w-full px-2.5 py-1.5 rounded text-sm"
              style={{ background: "var(--input)", border: "1px solid var(--border)", color: "var(--foreground)" }}
            />
          </Field>
        </div>

        {/* 액션 버튼 */}
        <div className="flex justify-end gap-2 mt-6 pt-4" style={{ borderTop: "1px solid var(--border)" }}>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded text-sm"
            style={{ background: "var(--muted)", color: "var(--foreground)" }}
          >
            취소
          </button>
          <button
            onClick={onSave}
            disabled={!form.domain || !form.displayName}
            className="px-4 py-2 rounded text-sm font-medium text-white disabled:opacity-50"
            style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}
          >
            {isNew ? "추가" : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] uppercase tracking-wider opacity-60 block mb-1">{label}</label>
      {children}
    </div>
  );
}
