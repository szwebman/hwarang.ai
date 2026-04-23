"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 지식 커뮤니티 (Community Detection)
 * - 좌: 커뮤니티 목록 (크기순, 도메인 필터)
 * - 우: 선택된 커뮤니티 상세 (요약 / 구성원 / 관련 / 타임라인)
 * - 상단: 탐지 실행 (알고리즘, 도메인, 최소 크기)
 */

import { useCallback, useEffect, useState } from "react";

const DOMAINS = ["전체", "law", "tax", "code", "medical", "general"];
const ALGORITHMS: { key: string; label: string }[] = [
  { key: "louvain", label: "Louvain" },
  { key: "label_propagation", label: "Label Propagation" },
  { key: "leiden", label: "Leiden" },
];

interface Community {
  id: string;
  name?: string;
  domain: string;
  size: number;
  cohesion: number;       // 0..1 결합도
  representative?: string;
  summary?: string;
  member_fact_ids?: string[];
  created_at?: string;
}

interface FactItem {
  id: string;
  statement: string;
  domain?: string;
  valid_from?: string;
  quality_score?: number;
  source_title?: string;
}

interface CommunityDetail extends Community {
  members?: FactItem[];
}

interface RelatedCommunity {
  id: string;
  name?: string;
  size: number;
  similarity: number;
}

interface TimelineEvent {
  fact_id: string;
  statement: string;
  valid_from: string;
  source_title?: string;
}

export default function CommunitiesPage() {
  const [domain, setDomain] = useState("전체");
  const [list, setList] = useState<Community[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CommunityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [related, setRelated] = useState<RelatedCommunity[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [detectOpen, setDetectOpen] = useState(false);
  const [detectAlgo, setDetectAlgo] = useState("louvain");
  const [detectDomain, setDetectDomain] = useState("전체");
  const [detectMinSize, setDetectMinSize] = useState(3);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (domain !== "전체") qs.set("domain", domain);
      const resp = await adminFetch(`/api/hlkm/communities?${qs.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        const items: Community[] = Array.isArray(data) ? data : data.items || [];
        // 크기 내림차순 정렬
        items.sort((a, b) => b.size - a.size);
        setList(items);
        if (items.length > 0 && !items.find((c) => c.id === selectedId)) {
          setSelectedId(items[0].id);
        }
      } else {
        setList([]);
      }
    } catch {
      setList([]);
    } finally {
      setLoading(false);
    }
  }, [domain, selectedId]);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setRelated([]);
      setTimeline([]);
      return;
    }
    let alive = true;
    setDetailLoading(true);

    Promise.all([
      adminFetch(`/api/hlkm/communities/${selectedId}`).then((r) => r.ok ? r.json() : null),
      adminFetch(`/api/hlkm/communities/${selectedId}/related`).then((r) => r.ok ? r.json() : null),
      adminFetch(`/api/hlkm/communities/${selectedId}/timeline`).then((r) => r.ok ? r.json() : null),
    ])
      .then(([d, rel, tl]) => {
        if (!alive) return;
        setDetail(d || null);
        const relList: RelatedCommunity[] = Array.isArray(rel) ? rel : rel?.items || [];
        setRelated(relList);
        const tlList: TimelineEvent[] = Array.isArray(tl) ? tl : tl?.items || [];
        tlList.sort((a, b) => {
          const ta = new Date(a.valid_from).getTime();
          const tb = new Date(b.valid_from).getTime();
          return ta - tb;
        });
        setTimeline(tlList);
      })
      .catch(() => {
        if (alive) {
          setDetail(null);
          setRelated([]);
          setTimeline([]);
        }
      })
      .finally(() => {
        if (alive) setDetailLoading(false);
      });
    return () => { alive = false; };
  }, [selectedId]);

  const runDetect = async () => {
    setBusy("detect");
    setMessage(null);
    try {
      const body: any = { algorithm: detectAlgo, min_size: detectMinSize };
      if (detectDomain !== "전체") body.domain = detectDomain;
      const resp = await adminFetch("/api/hlkm/communities/detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      const cnt = data.created ?? data.count ?? data.total ?? 0;
      setMessage({ ok: true, text: `탐지 완료 (${cnt.toLocaleString("ko-KR")}개 커뮤니티)` });
      setDetectOpen(false);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "탐지 실패" });
    } finally {
      setBusy(null);
    }
  };

  const summarize = async () => {
    if (!selectedId) return;
    setBusy("summarize");
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/communities/${selectedId}/summarize`, {
        method: "POST",
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "요약이 생성되었습니다" });
      // 상세 재로드
      const r = await adminFetch(`/api/hlkm/communities/${selectedId}`);
      if (r.ok) setDetail(await r.json());
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "요약 생성 실패" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">지식 커뮤니티</h1>
          <p className="mt-1 text-sm text-gray-500">
            Community Detection — 의미·관계 기반으로 사실 군집을 탐지하고 요약합니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2">
            <span className="text-xs text-gray-600">도메인</span>
            <select
              value={domain}
              onChange={(e) => { setDomain(e.target.value); setSelectedId(null); }}
              className="rounded-lg border px-2 py-1 text-xs"
              style={{ borderColor: "#e5e7eb" }}
            >
              {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </label>
          <button
            onClick={() => setDetectOpen(true)}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            커뮤니티 탐지 실행
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* 커뮤니티 목록 */}
        <aside className="rounded-xl border bg-white lg:col-span-2" style={{ borderColor: "#e5e7eb" }}>
          <div className="border-b px-4 py-3 text-xs font-semibold text-gray-700" style={{ borderColor: "#e5e7eb" }}>
            커뮤니티 목록 {loading && <span className="ml-2 text-gray-400">불러오는 중...</span>}
            <span className="ml-auto float-right text-gray-500">{list.length.toLocaleString("ko-KR")}개</span>
          </div>
          <ul className="max-h-[640px] overflow-y-auto">
            {list.length === 0 && !loading && (
              <li className="p-6 text-center text-sm text-gray-400">
                아직 데이터가 없습니다
              </li>
            )}
            {list.map((c) => (
              <li
                key={c.id}
                onClick={() => setSelectedId(c.id)}
                className={`cursor-pointer border-b px-4 py-3 transition-colors ${
                  selectedId === c.id ? "bg-indigo-50" : "hover:bg-gray-50"
                }`}
                style={{ borderColor: "#f3f4f6" }}
              >
                <div className="flex items-center gap-2 text-[11px] text-gray-500">
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 font-medium text-gray-700">
                    {c.domain}
                  </span>
                  <span className="tabular-nums">크기 {c.size.toLocaleString("ko-KR")}</span>
                  <span className="ml-auto tabular-nums">결합도 {(c.cohesion * 100).toFixed(0)}</span>
                </div>
                <div className="mt-1 text-sm font-semibold text-gray-900">
                  {c.name || `커뮤니티 #${c.id.slice(0, 8)}`}
                </div>
                {c.representative && (
                  <div className="mt-1 line-clamp-2 text-xs text-gray-600">
                    {c.representative}
                  </div>
                )}
                <CohesionBar score={c.cohesion} />
              </li>
            ))}
          </ul>
        </aside>

        {/* 상세 */}
        <section className="rounded-xl border bg-white p-5 lg:col-span-3" style={{ borderColor: "#e5e7eb" }}>
          {!selectedId ? (
            <div className="flex h-full min-h-[400px] items-center justify-center text-sm text-gray-400">
              좌측 목록에서 커뮤니티를 선택하세요
            </div>
          ) : detailLoading ? (
            <div className="flex h-full min-h-[400px] items-center justify-center text-sm text-gray-400">
              불러오는 중...
            </div>
          ) : !detail ? (
            <div className="text-sm text-gray-500">상세 정보를 불러올 수 없습니다</div>
          ) : (
            <div className="space-y-5">
              {/* 헤더 */}
              <div>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <span className="rounded bg-gray-100 px-2 py-1 font-medium text-gray-700">{detail.domain}</span>
                  <span className="tabular-nums">크기 {detail.size.toLocaleString("ko-KR")}</span>
                  <span className="tabular-nums">결합도 {(detail.cohesion * 100).toFixed(0)}%</span>
                </div>
                <h2 className="mt-2 text-lg font-bold text-gray-900">
                  {detail.name || `커뮤니티 #${detail.id.slice(0, 8)}`}
                </h2>
              </div>

              {/* LLM 요약 */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-xs font-semibold text-gray-500">LLM 요약</div>
                  {!detail.summary && (
                    <button
                      onClick={summarize}
                      disabled={busy !== null}
                      className="rounded-lg bg-amber-500 px-3 py-1 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-60"
                    >
                      {busy === "summarize" ? "생성 중..." : "요약 생성"}
                    </button>
                  )}
                </div>
                {detail.summary ? (
                  <div
                    className="rounded-lg border p-3 text-sm text-gray-800 whitespace-pre-wrap"
                    style={{ borderColor: "#fde68a", background: "#fffbeb" }}
                  >
                    {detail.summary}
                  </div>
                ) : (
                  <div className="rounded-lg bg-gray-50 p-4 text-center text-xs text-gray-400">
                    아직 요약이 없습니다
                  </div>
                )}
              </div>

              {/* 구성원 사실 */}
              <div>
                <div className="mb-2 text-xs font-semibold text-gray-500">
                  구성원 사실 ({detail.members?.length ?? 0})
                </div>
                {!detail.members || detail.members.length === 0 ? (
                  <div className="rounded-lg bg-gray-50 p-4 text-center text-xs text-gray-400">
                    구성원이 없습니다
                  </div>
                ) : (
                  <ul className="max-h-60 space-y-2 overflow-y-auto">
                    {detail.members.map((m) => (
                      <li key={m.id} className="rounded-lg bg-gray-50 p-3 text-xs">
                        <div className="flex items-center gap-2 text-[10px] text-gray-500">
                          {m.domain && (
                            <span className="rounded bg-white px-1.5 py-0.5 text-gray-700">{m.domain}</span>
                          )}
                          {m.source_title && <span>{m.source_title}</span>}
                          {m.quality_score !== undefined && (
                            <span className="ml-auto tabular-nums">Q {Math.round(m.quality_score * 100)}</span>
                          )}
                        </div>
                        <div className="mt-1 text-gray-800">{m.statement}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* 관련 커뮤니티 */}
              <div>
                <div className="mb-2 text-xs font-semibold text-gray-500">
                  관련 커뮤니티 ({related.length})
                </div>
                {related.length === 0 ? (
                  <div className="rounded-lg bg-gray-50 p-3 text-center text-xs text-gray-400">
                    관련 커뮤니티가 없습니다
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {related.map((r) => (
                      <button
                        key={r.id}
                        onClick={() => setSelectedId(r.id)}
                        className="rounded-lg border p-3 text-left text-xs transition-colors hover:bg-indigo-50"
                        style={{ borderColor: "#e5e7eb" }}
                      >
                        <div className="font-semibold text-gray-900">
                          {r.name || `#${r.id.slice(0, 8)}`}
                        </div>
                        <div className="mt-1 flex items-center justify-between text-[10px] text-gray-500">
                          <span>크기 {r.size}</span>
                          <span className="tabular-nums" style={{ color: "#7c3aed" }}>
                            유사도 {(r.similarity * 100).toFixed(0)}%
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* 타임라인 */}
              <div>
                <div className="mb-2 text-xs font-semibold text-gray-500">
                  타임라인 ({timeline.length})
                </div>
                {timeline.length === 0 ? (
                  <div className="rounded-lg bg-gray-50 p-3 text-center text-xs text-gray-400">
                    타임라인 데이터가 없습니다
                  </div>
                ) : (
                  <ol className="relative border-l-2 pl-4" style={{ borderColor: "#e5e7eb" }}>
                    {timeline.map((t) => (
                      <li key={t.fact_id} className="mb-3 last:mb-0">
                        <div className="absolute -left-[5px] mt-1 h-2 w-2 rounded-full bg-indigo-500" />
                        <div className="text-[10px] text-gray-500">
                          {new Date(t.valid_from).toLocaleDateString("ko-KR")}
                          {t.source_title && <span className="ml-2">· {t.source_title}</span>}
                        </div>
                        <div className="mt-0.5 text-xs text-gray-800">{t.statement}</div>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
          )}
        </section>
      </div>

      {/* 탐지 모달 */}
      {detectOpen && (
        <ModalOverlay onClose={() => setDetectOpen(false)}>
          <div className="w-full max-w-md rounded-xl border bg-white p-6" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="text-lg font-bold text-gray-900">커뮤니티 탐지 실행</h2>
            <p className="mt-1 text-xs text-gray-500">
              그래프 기반 커뮤니티 탐지를 실행합니다. 결과는 기존 커뮤니티를 갱신합니다.
            </p>

            <div className="mt-4 space-y-4">
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">알고리즘</label>
                <select
                  value={detectAlgo}
                  onChange={(e) => setDetectAlgo(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  {ALGORITHMS.map((a) => (
                    <option key={a.key} value={a.key}>{a.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">대상 도메인</label>
                <select
                  value={detectDomain}
                  onChange={(e) => setDetectDomain(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                >
                  {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-700">최소 크기</label>
                <input
                  type="number"
                  min={2}
                  value={detectMinSize}
                  onChange={(e) => setDetectMinSize(parseInt(e.target.value) || 2)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  style={{ borderColor: "#e5e7eb" }}
                />
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setDetectOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runDetect}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "detect" ? "탐지 중..." : "실행"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function CohesionBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const color = score >= 0.7 ? "#7c3aed" : score >= 0.4 ? "#0891b2" : "#94a3b8";
  return (
    <div className="mt-2 h-1.5 overflow-hidden rounded-full" style={{ background: "#f1f5f9" }}>
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${pct}%`, background: color }}
      />
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
