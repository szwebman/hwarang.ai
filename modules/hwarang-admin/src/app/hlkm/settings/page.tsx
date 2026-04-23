"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 설정 — HLKMSettings 전체 편집
 * - 모순 감지 임계값
 * - 자동 승인 기준
 * - 반감기 오버라이드 (도메인별)
 * - 스케줄러 토글
 * - 보상 설정 (도메인별 base)
 * - 한계 설정 (요청 한도 등)
 * - 프라이버시 (PII/암호화)
 *
 * 저장 시 현재값 vs 수정값 diff 미리보기
 */

import { useCallback, useEffect, useMemo, useState } from "react";

type DomainMap = Record<string, number>;

interface HLKMSettings {
  // 모순
  conflict_detect_threshold: number;    // 0..1
  conflict_auto_resolve_threshold: number;
  // 자동 승인
  auto_approve_min_quality: number;     // 0..1
  auto_approve_min_sources: number;
  // 반감기 (일)
  halflife_days_by_domain: DomainMap;
  // 스케줄러
  scheduler_verify_enabled: boolean;
  scheduler_hrag_sync_enabled: boolean;
  scheduler_halflife_train_enabled: boolean;
  scheduler_gap_scan_enabled: boolean;
  // 보상 (HWA 기본값)
  reward_base_by_domain: DomainMap;
  // 한계
  max_facts_per_user_per_day: number;
  max_conflict_queue_size: number;
  // 프라이버시
  pii_auto_redact: boolean;
  encrypt_at_rest: boolean;
}

const DEFAULT_SETTINGS: HLKMSettings = {
  conflict_detect_threshold: 0.7,
  conflict_auto_resolve_threshold: 0.95,
  auto_approve_min_quality: 0.8,
  auto_approve_min_sources: 2,
  halflife_days_by_domain: { law: 365, tax: 180, code: 30, medical: 180, general: 90 },
  scheduler_verify_enabled: true,
  scheduler_hrag_sync_enabled: true,
  scheduler_halflife_train_enabled: false,
  scheduler_gap_scan_enabled: true,
  reward_base_by_domain: { law: 100, tax: 80, code: 50, medical: 100, general: 20 },
  max_facts_per_user_per_day: 50,
  max_conflict_queue_size: 500,
  pii_auto_redact: true,
  encrypt_at_rest: true,
};

export default function SettingsPage() {
  const [original, setOriginal] = useState<HLKMSettings | null>(null);
  const [draft, setDraft] = useState<HLKMSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await adminFetch("/api/hlkm/settings");
      if (resp.ok) {
        const data = (await resp.json()) as Partial<HLKMSettings>;
        const merged: HLKMSettings = { ...DEFAULT_SETTINGS, ...data };
        setOriginal(merged);
        setDraft(merged);
      } else {
        setOriginal(DEFAULT_SETTINGS);
        setDraft(DEFAULT_SETTINGS);
      }
    } catch {
      setOriginal(DEFAULT_SETTINGS);
      setDraft(DEFAULT_SETTINGS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const diff = useMemo(() => computeDiff(original, draft), [original, draft]);

  const update = <K extends keyof HLKMSettings>(key: K, value: HLKMSettings[K]) => {
    setDraft((d) => ({ ...d, [key]: value }));
  };

  const updateDomain = (field: "halflife_days_by_domain" | "reward_base_by_domain", domain: string, value: number) => {
    setDraft((d) => ({ ...d, [field]: { ...d[field], [domain]: value } }));
  };

  const save = async () => {
    if (diff.length === 0) {
      setMessage({ ok: false, text: "변경된 항목이 없습니다" });
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const resp = await adminFetch("/api/hlkm/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      setOriginal(draft);
      setMessage({ ok: true, text: "설정이 저장되었습니다" });
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "저장 실패" });
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    if (!original) return;
    setDraft(original);
    setMessage(null);
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-gray-400">
        설정을 불러오는 중…
      </div>
    );
  }

  const domainKeys = Array.from(
    new Set([...Object.keys(draft.halflife_days_by_domain), ...Object.keys(draft.reward_base_by_domain)])
  );

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">HLKM 설정</h1>
          <p className="mt-1 text-sm text-gray-500">
            임계값, 스케줄러, 보상, 프라이버시 옵션을 관리합니다.
          </p>
        </div>
      </header>

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

      <Section title="모순 감지 임계값" hint="값이 낮을수록 더 많은 모순이 감지됩니다">
        <NumberField
          label="모순 감지 임계값"
          hint="0~1, 유사도 기반"
          value={draft.conflict_detect_threshold}
          onChange={(v) => update("conflict_detect_threshold", v)}
          min={0} max={1} step={0.01}
        />
        <NumberField
          label="자동 해결 임계값"
          hint="이 이상일 때 시스템이 자동 해결"
          value={draft.conflict_auto_resolve_threshold}
          onChange={(v) => update("conflict_auto_resolve_threshold", v)}
          min={0} max={1} step={0.01}
        />
      </Section>

      <Section title="자동 승인 기준" hint="두 조건 모두 충족 시 자동 승인">
        <NumberField
          label="최소 품질 점수"
          hint="0~1"
          value={draft.auto_approve_min_quality}
          onChange={(v) => update("auto_approve_min_quality", v)}
          min={0} max={1} step={0.05}
        />
        <NumberField
          label="최소 교차 출처 수"
          hint="같은 사실을 뒷받침하는 독립 출처 개수"
          value={draft.auto_approve_min_sources}
          onChange={(v) => update("auto_approve_min_sources", v)}
          min={1} max={10} step={1}
        />
      </Section>

      <Section title="반감기 오버라이드 (도메인별, 일)" hint="지식의 신선도가 절반이 되는 기간">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          {domainKeys.map((d) => (
            <NumberField
              key={"hl-" + d}
              label={d}
              value={draft.halflife_days_by_domain[d] ?? 0}
              onChange={(v) => updateDomain("halflife_days_by_domain", d, v)}
              min={1} max={3650} step={1}
              suffix="일"
            />
          ))}
        </div>
      </Section>

      <Section title="스케줄러" hint="정기 작업 on/off">
        <Toggle
          label="자가 검증"
          hint="만료된 사실을 주기적으로 재검증"
          checked={draft.scheduler_verify_enabled}
          onChange={(v) => update("scheduler_verify_enabled", v)}
        />
        <Toggle
          label="HRAG 법률 동기화"
          hint="법령 최신본을 자동으로 동기화"
          checked={draft.scheduler_hrag_sync_enabled}
          onChange={(v) => update("scheduler_hrag_sync_enabled", v)}
        />
        <Toggle
          label="반감기 모델 재학습"
          hint="도메인별 반감기 파라미터 자동 갱신"
          checked={draft.scheduler_halflife_train_enabled}
          onChange={(v) => update("scheduler_halflife_train_enabled", v)}
        />
        <Toggle
          label="지식 공백 스캔"
          hint="답변 실패 패턴 자동 감지"
          checked={draft.scheduler_gap_scan_enabled}
          onChange={(v) => update("scheduler_gap_scan_enabled", v)}
        />
      </Section>

      <Section title="보상 (도메인별 base, HWA)" hint="승인된 사실 1건당 기본 지급 HWARANG 토큰">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          {domainKeys.map((d) => (
            <NumberField
              key={"rw-" + d}
              label={d}
              value={draft.reward_base_by_domain[d] ?? 0}
              onChange={(v) => updateDomain("reward_base_by_domain", d, v)}
              min={0} max={100000} step={1}
              suffix="HWA"
            />
          ))}
        </div>
      </Section>

      <Section title="한계" hint="남용 방지 한도">
        <NumberField
          label="사용자당 1일 사실 제출 한도"
          value={draft.max_facts_per_user_per_day}
          onChange={(v) => update("max_facts_per_user_per_day", v)}
          min={1} max={10000} step={1}
          suffix="건"
        />
        <NumberField
          label="모순 큐 최대 크기"
          hint="초과 시 오래된 항목부터 드롭"
          value={draft.max_conflict_queue_size}
          onChange={(v) => update("max_conflict_queue_size", v)}
          min={10} max={100000} step={10}
          suffix="건"
        />
      </Section>

      <Section title="프라이버시">
        <Toggle
          label="PII 자동 제거"
          hint="이름·주소·주민번호 등을 저장 전 마스킹"
          checked={draft.pii_auto_redact}
          onChange={(v) => update("pii_auto_redact", v)}
        />
        <Toggle
          label="Rest-at-암호화"
          hint="DB 레벨 암호화 (성능 영향 있음)"
          checked={draft.encrypt_at_rest}
          onChange={(v) => update("encrypt_at_rest", v)}
        />
      </Section>

      {/* Diff 미리보기 */}
      <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
        <h3 className="mb-2 text-sm font-semibold text-gray-900">변경 미리보기</h3>
        {diff.length === 0 ? (
          <div className="text-xs text-gray-500">아직 변경된 항목이 없습니다</div>
        ) : (
          <ul className="space-y-1 font-mono text-xs">
            {diff.map((d, i) => (
              <li key={i} className="rounded bg-gray-50 px-2 py-1">
                <span className="text-gray-500">{d.path}</span>
                <span className="mx-2 text-red-600">{formatValue(d.before)}</span>
                <span className="text-gray-400">→</span>
                <span className="ml-2 text-green-600">{formatValue(d.after)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 하단 저장 바 */}
      <div className="sticky bottom-0 flex items-center justify-end gap-2 rounded-xl border bg-white/90 p-3 backdrop-blur" style={{ borderColor: "#e5e7eb" }}>
        <span className="mr-auto text-xs text-gray-500">
          {diff.length === 0 ? "저장할 변경사항이 없습니다" : `${diff.length}개 항목이 변경됩니다`}
        </span>
        <button
          onClick={reset}
          disabled={saving || diff.length === 0}
          className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
          style={{ borderColor: "#e5e7eb" }}
        >
          초기화
        </button>
        <button
          onClick={save}
          disabled={saving || diff.length === 0}
          className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
      <header className="mb-3">
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        {hint && <p className="mt-0.5 text-xs text-gray-500">{hint}</p>}
      </header>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function NumberField({
  label, hint, value, onChange, min, max, step, suffix,
}: {
  label: string; hint?: string; value: number; onChange: (v: number) => void;
  min?: number; max?: number; step?: number; suffix?: string;
}) {
  return (
    <label className="flex items-center justify-between gap-3">
      <div>
        <div className="text-sm font-medium text-gray-900">{label}</div>
        {hint && <div className="text-[11px] text-gray-500">{hint}</div>}
      </div>
      <div className="flex items-center gap-1">
        <input
          type="number"
          value={Number.isFinite(value) ? value : 0}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          min={min} max={max} step={step}
          className="w-28 rounded-lg border px-2 py-1 text-right text-sm tabular-nums"
          style={{ borderColor: "#e5e7eb" }}
        />
        {suffix && <span className="text-xs text-gray-500">{suffix}</span>}
      </div>
    </label>
  );
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3">
      <div>
        <div className="text-sm font-medium text-gray-900">{label}</div>
        {hint && <div className="text-[11px] text-gray-500">{hint}</div>}
      </div>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className="relative h-6 w-11 rounded-full transition-colors"
        style={{ background: checked ? "#2563eb" : "#cbd5e1" }}
        aria-pressed={checked}
      >
        <span
          className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform"
          style={{ transform: checked ? "translateX(22px)" : "translateX(2px)" }}
        />
      </button>
    </label>
  );
}

// ── Diff ─────────────────────────────────────────────────────────────

interface DiffEntry { path: string; before: any; after: any }

function computeDiff(a: HLKMSettings | null, b: HLKMSettings): DiffEntry[] {
  if (!a) return [];
  const out: DiffEntry[] = [];
  const walk = (av: any, bv: any, path: string) => {
    if (av !== null && bv !== null && typeof av === "object" && typeof bv === "object" && !Array.isArray(av)) {
      const keys = new Set([...Object.keys(av), ...Object.keys(bv)]);
      for (const k of keys) walk(av[k], bv[k], path ? `${path}.${k}` : k);
    } else if (av !== bv) {
      out.push({ path, before: av, after: bv });
    }
  };
  walk(a, b, "");
  return out;
}

function formatValue(v: any): string {
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return v.toLocaleString("ko-KR");
  if (v === undefined) return "—";
  return String(v);
}
