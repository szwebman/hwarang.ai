"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 국가별 출처 위계 (Country Hierarchy)
 * - 국가 탭 (KR/US/JP/EU/CN/GLOBAL)
 * - 각 탭: 해당 국가의 위계 규칙 테이블 (domain별 그룹)
 * - 액션: 국가별 시드 (드롭다운), 전체 fact에 적용
 * - 비교 도구: 두 출처 입력 → 국가별 권위 비교
 */

import { useCallback, useEffect, useMemo, useState } from "react";

const DEFAULT_TABS = ["KR", "US", "JP", "EU", "CN", "GLOBAL"];

interface Rule {
  id: string;
  country: string;
  domain: string;
  level: number;
  pattern: string;
  tier: string;
  authority: number;
  note?: string | null;
  active: boolean;
}

interface ComparisonResult {
  a: {
    source: string;
    country: string;
    country_name: string;
    tier: string;
    authority: number;
  };
  b: {
    source: string;
    country: string;
    country_name: string;
    tier: string;
    authority: number;
  };
  domain: string;
  winner: "a" | "b" | "tie";
}

export default function CountryPage() {
  const [countries, setCountries] = useState<Record<string, string>>({});
  const [available, setAvailable] = useState<string[]>(DEFAULT_TABS);
  const [tab, setTab] = useState("KR");
  const [domainFilter, setDomainFilter] = useState("");
  const [rulesByDomain, setRulesByDomain] = useState<Record<string, Rule[]>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [seedCountries, setSeedCountries] = useState<string[]>([]);
  const [seedOpen, setSeedOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkCountry, setBulkCountry] = useState("");
  const [bulkLimit, setBulkLimit] = useState(500);

  const [compareA, setCompareA] = useState("");
  const [compareB, setCompareB] = useState("");
  const [compareDomain, setCompareDomain] = useState("general");
  const [compareResult, setCompareResult] = useState<ComparisonResult | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const resp = await adminFetch(`/api/hlkm/country/countries`);
        if (resp.ok) {
          const data = await resp.json();
          setCountries(data.countries || {});
          const avail = Array.isArray(data.available_in_hierarchy)
            ? data.available_in_hierarchy
            : [];
          const tabs = DEFAULT_TABS.filter((c) => avail.includes(c) || c === "KR");
          if (tabs.length === 0) tabs.push("KR");
          setAvailable(tabs.length ? tabs : DEFAULT_TABS);
        }
      } catch {
        /* noop */
      }
    })();
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (domainFilter.trim()) qs.set("domain", domainFilter.trim());
      const resp = await adminFetch(
        `/api/hlkm/country/rules/${encodeURIComponent(tab)}?${qs.toString()}`
      );
      if (resp.ok) {
        const data = await resp.json();
        setRulesByDomain(data.by_domain || {});
      } else {
        setRulesByDomain({});
      }
    } catch {
      setRulesByDomain({});
    } finally {
      setLoading(false);
    }
  }, [tab, domainFilter]);

  useEffect(() => {
    reload();
  }, [reload]);

  const totalRules = useMemo(() => {
    return Object.values(rulesByDomain).reduce((s, arr) => s + arr.length, 0);
  }, [rulesByDomain]);

  const runSeed = async () => {
    setBusy("seed");
    setMessage(null);
    try {
      const body: Record<string, unknown> = {};
      if (seedCountries.length > 0) body.countries = seedCountries;
      const resp = await adminFetch(`/api/hlkm/country/seed`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `시드 완료 — 신규 ${data.inserted ?? 0}건 (${(data.countries || ["전체"]).join(", ")})`,
      });
      setSeedOpen(false);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "시드 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runBulk = async () => {
    setBusy("bulk");
    setMessage(null);
    try {
      const body: Record<string, unknown> = { limit: bulkLimit };
      if (bulkCountry.trim()) body.country = bulkCountry.trim();
      const resp = await adminFetch(`/api/hlkm/country/bulk-apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `일괄 적용 완료 — 처리 ${data.processed ?? 0} / 갱신 ${data.updated ?? 0} / 스킵 ${data.skipped ?? 0}`,
      });
      setBulkOpen(false);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "일괄 적용 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runCompare = async () => {
    if (!compareA.trim() || !compareB.trim()) {
      setMessage({ ok: false, text: "두 출처를 모두 입력하세요" });
      return;
    }
    setCompareLoading(true);
    setCompareResult(null);
    try {
      const resp = await adminFetch(`/api/hlkm/country/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_a: compareA.trim(),
          source_b: compareB.trim(),
          domain: compareDomain.trim() || "general",
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setCompareResult(data as ComparisonResult);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "비교 실패" });
    } finally {
      setCompareLoading(false);
    }
  };

  return (
    <div className="space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">국가별 출처 위계</h1>
          <p className="mt-1 text-sm text-gray-500">
            Country Hierarchy — 국가마다 서로 다른 공식/학계/언론 위계를 적용하여 권위를 평가합니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setSeedOpen(true)}
            disabled={busy !== null}
            className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb", color: "#374151" }}
          >
            국가별 시드
          </button>
          <button
            onClick={() => setBulkOpen(true)}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            전체 fact에 적용
          </button>
          <button
            onClick={reload}
            disabled={busy !== null}
            className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb" }}
          >
            새로고침
          </button>
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

      {/* 국가 탭 */}
      <div
        className="flex flex-wrap items-center gap-2 rounded-xl border bg-white p-2"
        style={{ borderColor: "#e5e7eb" }}
      >
        {available.map((c) => {
          const isActive = c === tab;
          return (
            <button
              key={c}
              onClick={() => setTab(c)}
              className="rounded-lg px-4 py-1.5 text-sm"
              style={{
                background: isActive ? "#4338ca" : "#ffffff",
                color: isActive ? "#ffffff" : "#374151",
                border: isActive ? "1px solid #4338ca" : "1px solid #e5e7eb",
              }}
            >
              <span className="font-medium">{c}</span>
              <span className="ml-1 text-[10px] opacity-80">
                {countries[c] || c}
              </span>
            </button>
          );
        })}
        <label className="ml-auto flex items-center gap-2 text-xs text-gray-700">
          <span>도메인</span>
          <input
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            placeholder="law / medical / all"
            className="rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb", minWidth: 150 }}
          />
        </label>
      </div>

      {/* 규칙 테이블 */}
      <div
        className="rounded-xl border bg-white p-4"
        style={{ borderColor: "#e5e7eb" }}
      >
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-semibold text-gray-900">
            {tab} — {countries[tab] || tab}
          </div>
          <div className="text-xs text-gray-500">
            {loading ? "불러오는 중..." : `총 ${totalRules.toLocaleString("ko-KR")}개 규칙`}
          </div>
        </div>

        {!loading && totalRules === 0 && (
          <div className="py-10 text-center text-sm text-gray-400">
            이 국가의 위계 규칙이 없습니다 — 상단의 &quot;국가별 시드&quot;로 초기화하세요.
          </div>
        )}

        <div className="space-y-4">
          {Object.entries(rulesByDomain).map(([domain, rules]) => (
            <div key={domain}>
              <div className="mb-2 flex items-baseline gap-2 border-b pb-1" style={{ borderColor: "#e5e7eb" }}>
                <span className="text-sm font-semibold text-gray-900">{domain}</span>
                <span className="text-[11px] text-gray-500">
                  ({rules.length.toLocaleString("ko-KR")})
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr
                      className="border-b bg-gray-50 text-xs text-gray-600"
                      style={{ borderColor: "#e5e7eb" }}
                    >
                      <th className="px-3 py-1.5 text-left font-medium">레벨</th>
                      <th className="px-3 py-1.5 text-left font-medium">패턴</th>
                      <th className="px-3 py-1.5 text-left font-medium">티어</th>
                      <th className="px-3 py-1.5 text-right font-medium">권위</th>
                      <th className="px-3 py-1.5 text-left font-medium">비고</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((r) => (
                      <tr
                        key={r.id}
                        className="border-b transition-colors hover:bg-gray-50"
                        style={{ borderColor: "#f3f4f6" }}
                      >
                        <td className="px-3 py-2 tabular-nums">{r.level}</td>
                        <td className="px-3 py-2">
                          <code className="font-mono text-[11px] text-gray-700">
                            {r.pattern}
                          </code>
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                            style={{ color: "#1d4ed8", background: "#dbeafe" }}
                          >
                            {r.tier}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          <span className="font-semibold" style={{ color: "#4338ca" }}>
                            {(r.authority * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td className="px-3 py-2 text-[11px] text-gray-500">
                          {r.note || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 비교 도구 */}
      <div
        className="rounded-xl border bg-white p-5"
        style={{ borderColor: "#e5e7eb" }}
      >
        <h3 className="mb-3 text-sm font-semibold text-gray-900">출처 비교 도구</h3>
        <p className="mb-3 text-xs text-gray-500">
          두 출처를 각각의 국가 위계에서 평가하여 어느 쪽이 더 공식적인지 판정합니다.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-5">
          <input
            value={compareA}
            onChange={(e) => setCompareA(e.target.value)}
            placeholder="출처 A (예: https://cdc.gov/...)"
            className="rounded-lg border px-3 py-2 text-sm sm:col-span-2"
            style={{ borderColor: "#e5e7eb" }}
          />
          <input
            value={compareB}
            onChange={(e) => setCompareB(e.target.value)}
            placeholder="출처 B (예: https://kdca.go.kr/...)"
            className="rounded-lg border px-3 py-2 text-sm sm:col-span-2"
            style={{ borderColor: "#e5e7eb" }}
          />
          <input
            value={compareDomain}
            onChange={(e) => setCompareDomain(e.target.value)}
            placeholder="도메인"
            className="rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: "#e5e7eb" }}
          />
        </div>
        <div className="mt-3 flex justify-end">
          <button
            onClick={runCompare}
            disabled={compareLoading}
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-60"
          >
            {compareLoading ? "비교 중..." : "비교 실행"}
          </button>
        </div>

        {compareResult && (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <ComparisonCard
              label="출처 A"
              winner={compareResult.winner === "a"}
              data={compareResult.a}
            />
            <div className="flex items-center justify-center">
              <div className="text-center">
                <div className="text-xs text-gray-500">판정</div>
                <div className="mt-1 text-2xl font-bold" style={{
                  color:
                    compareResult.winner === "tie"
                      ? "#64748b"
                      : "#4338ca",
                }}>
                  {compareResult.winner === "tie" ? "동등" : compareResult.winner === "a" ? "A" : "B"}
                </div>
                <div className="mt-1 text-[11px] text-gray-500">
                  도메인: {compareResult.domain}
                </div>
              </div>
            </div>
            <ComparisonCard
              label="출처 B"
              winner={compareResult.winner === "b"}
              data={compareResult.b}
            />
          </div>
        )}
      </div>

      {/* 시드 모달 */}
      {seedOpen && (
        <ModalOverlay onClose={() => setSeedOpen(false)}>
          <div
            className="w-full max-w-md rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">국가별 위계 시드</h2>
            <p className="mt-1 text-xs text-gray-500">
              체크한 국가만 시드합니다. 하나도 선택하지 않으면 전체 국가 시드.
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2">
              {available.map((c) => {
                const checked = seedCountries.includes(c);
                return (
                  <label
                    key={c}
                    className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm"
                    style={{
                      borderColor: checked ? "#a5b4fc" : "#e5e7eb",
                      background: checked ? "#eef2ff" : "#ffffff",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSeedCountries([...seedCountries, c]);
                        } else {
                          setSeedCountries(seedCountries.filter((x) => x !== c));
                        }
                      }}
                    />
                    <span className="font-medium">{c}</span>
                    <span className="text-[10px] text-gray-500">
                      {countries[c] || ""}
                    </span>
                  </label>
                );
              })}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setSeedOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runSeed}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "seed" ? "시드 중..." : "시드 실행"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}

      {/* 일괄 적용 모달 */}
      {bulkOpen && (
        <ModalOverlay onClose={() => setBulkOpen(false)}>
          <div
            className="w-full max-w-md rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">전체 fact에 적용</h2>
            <p className="mt-1 text-xs text-gray-500">
              출처에서 국가를 추정하여 sourceTier/sourceAuthority 를 재계산합니다.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">국가 (선택)</div>
                <select
                  value={bulkCountry}
                  onChange={(e) => setBulkCountry(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  <option value="">전체</option>
                  {available.map((c) => (
                    <option key={c} value={c}>
                      {c} — {countries[c] || c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold text-gray-700">처리 상한</div>
                <input
                  type="number"
                  value={bulkLimit}
                  onChange={(e) =>
                    setBulkLimit(Math.max(1, parseInt(e.target.value) || 500))
                  }
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                  min={1}
                  max={5000}
                />
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setBulkOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runBulk}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "bulk" ? "적용 중..." : "적용 실행"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function ComparisonCard({
  label,
  winner,
  data,
}: {
  label: string;
  winner: boolean;
  data: ComparisonResult["a"];
}) {
  return (
    <div
      className="rounded-xl border p-4"
      style={{
        borderColor: winner ? "#a5b4fc" : "#e5e7eb",
        background: winner ? "#eef2ff" : "#f9fafb",
      }}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-700">{label}</span>
        {winner && (
          <span
            className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
            style={{ color: "#4338ca", background: "#e0e7ff" }}
          >
            우세
          </span>
        )}
      </div>
      <div className="mt-2 truncate text-[11px] text-gray-600" title={data.source}>
        {data.source}
      </div>
      <div className="mt-2 text-[11px] text-gray-500">
        {data.country_name} ({data.country})
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span
          className="rounded px-1.5 py-0.5 text-[11px] font-medium"
          style={{ color: "#1d4ed8", background: "#dbeafe" }}
        >
          {data.tier}
        </span>
        <span className="text-lg font-bold tabular-nums" style={{ color: "#4338ca" }}>
          {(data.authority * 100).toFixed(0)}%
        </span>
      </div>
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
