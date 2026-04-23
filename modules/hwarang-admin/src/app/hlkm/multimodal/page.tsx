"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 미디어 사실 (Multimodal)
 * - 의심 미디어 (deepfakeScore ≥ 0.6) 카드 목록
 * - pHash 유사 검색 (해밍 거리 기반)
 * - 상단 통계: 총 미디어 / 딥페이크 의심 / OCR / 전사
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface SuspectMedia {
  media_fact_id: string;
  fact_id: string;
  mediaType: string;
  deepfakeScore: number;
  manipulationFlags: string[];
  fileUrl: string;
}

interface SimilarItem {
  media_fact_id: string;
  fact_id: string;
  distance: number;
  fileUrl?: string;
  phash?: string;
}

interface MediaSummary {
  fact_id: string;
  content: string;
  media?: {
    mediaType?: string | null;
    fileUrl?: string | null;
    thumbnailUrl?: string | null;
    perceptualHash?: string | null;
    simHash?: string | null;
    ocrText?: string | null;
    transcription?: string | null;
    deepfakeScore?: number;
    manipulationFlags?: string[];
    resolution?: string | null;
    duration?: number | null;
    originalSize?: number | null;
  } | null;
}

const MEDIA_ICON: Record<string, string> = {
  IMAGE: "🖼️",
  VIDEO: "🎬",
  AUDIO: "🎧",
  DOCUMENT: "📄",
};

export default function MultimodalPage() {
  const [suspects, setSuspects] = useState<SuspectMedia[]>([]);
  const [loading, setLoading] = useState(true);
  const [threshold, setThreshold] = useState(0.6);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [searchHash, setSearchHash] = useState("");
  const [searchDistance, setSearchDistance] = useState(10);
  const [searchResults, setSearchResults] = useState<SimilarItem[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);

  const [summaryFactId, setSummaryFactId] = useState("");
  const [summary, setSummary] = useState<MediaSummary | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      qs.set("min_deepfake_score", String(threshold));
      const resp = await adminFetch(`/api/hlkm/media/suspect?${qs.toString()}`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setSuspects(Array.isArray(data.items) ? data.items : []);
    } catch (e: any) {
      setSuspects([]);
      setMessage({ ok: false, text: e?.message || "목록 조회 실패" });
    } finally {
      setLoading(false);
    }
  }, [threshold]);

  useEffect(() => {
    reload();
  }, [reload]);

  const stats = useMemo(() => {
    const total = suspects.length;
    const highRisk = suspects.filter((s) => s.deepfakeScore >= 0.8).length;
    const byType: Record<string, number> = {};
    for (const s of suspects) {
      byType[s.mediaType] = (byType[s.mediaType] || 0) + 1;
    }
    const withFlags = suspects.filter((s) => (s.manipulationFlags || []).length > 0).length;
    return { total, highRisk, byType, withFlags };
  }, [suspects]);

  const runSearch = async () => {
    const h = searchHash.trim();
    if (!h) {
      setMessage({ ok: false, text: "pHash 를 입력하세요" });
      return;
    }
    setSearchLoading(true);
    setSearchResults(null);
    setMessage(null);
    try {
      const qs = new URLSearchParams();
      qs.set("max_distance", String(searchDistance));
      const resp = await adminFetch(
        `/api/hlkm/media/similar/${encodeURIComponent(h)}?${qs.toString()}`
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setSearchResults(Array.isArray(data.similar) ? data.similar : []);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "유사 검색 실패" });
    } finally {
      setSearchLoading(false);
    }
  };

  const loadSummary = async () => {
    const id = summaryFactId.trim();
    if (!id) {
      setMessage({ ok: false, text: "Fact ID 를 입력하세요" });
      return;
    }
    setBusy("summary");
    setSummary(null);
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/media/summary/${encodeURIComponent(id)}`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setSummary(data);
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "요약 조회 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runProcess = async (media_fact_id: string) => {
    setBusy(`process:${media_fact_id}`);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/media/process/${encodeURIComponent(media_fact_id)}`,
        { method: "POST" }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: "미디어 재처리 완료" });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "재처리 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runScanCopies = async (media_fact_id: string) => {
    setBusy(`scan:${media_fact_id}`);
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/hlkm/media/scan-copies/${encodeURIComponent(media_fact_id)}`,
        { method: "POST" }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `복사본 스캔 완료 (${(data.count ?? 0).toLocaleString("ko-KR")}건)`,
      });
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "복사본 스캔 실패" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">미디어 사실</h1>
          <p className="mt-1 text-sm text-gray-500">
            Multimodal — 이미지/영상/오디오/문서 사실의 perceptual hash · 딥페이크 점수 · OCR/전사.
          </p>
        </div>
        <div className="flex items-center gap-2">
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

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="의심 미디어" value={stats.total} accent="warning" />
        <StatCard label="고위험 (>=0.8)" value={stats.highRisk} accent="danger" />
        <StatCard label="변조 플래그" value={stats.withFlags} accent="neutral" />
        <StatCard
          label="이미지/영상/오디오"
          value={`${stats.byType.IMAGE ?? 0} / ${stats.byType.VIDEO ?? 0} / ${stats.byType.AUDIO ?? 0}`}
          accent="primary"
        />
      </div>

      <div
        className="flex flex-wrap items-center gap-4 rounded-xl border bg-white p-4"
        style={{ borderColor: "#e5e7eb" }}
      >
        <label className="flex items-center gap-2 text-xs text-gray-700">
          <span>딥페이크 점수 임계값</span>
          <input
            type="range"
            min={0.1}
            max={0.95}
            step={0.05}
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            className="w-40"
          />
          <span className="tabular-nums font-semibold">{threshold.toFixed(2)}</span>
        </label>
        <span className="ml-auto text-xs text-gray-500">
          {loading ? "불러오는 중..." : `${suspects.length.toLocaleString("ko-KR")}건`}
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

      {/* 의심 미디어 카드 그리드 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {suspects.length === 0 && !loading && (
          <div
            className="col-span-full rounded-xl border bg-white p-10 text-center text-sm text-gray-400"
            style={{ borderColor: "#e5e7eb" }}
          >
            임계값 이상의 미디어가 없습니다
          </div>
        )}
        {suspects.map((s) => (
          <MediaCard
            key={s.media_fact_id}
            item={s}
            busy={busy}
            onProcess={() => runProcess(s.media_fact_id)}
            onScanCopies={() => runScanCopies(s.media_fact_id)}
          />
        ))}
      </div>

      {/* pHash 유사 검색 */}
      <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">pHash 유사 미디어 검색</h2>
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            value={searchHash}
            onChange={(e) => setSearchHash(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
            placeholder="예: ff00ab12... (64bit hex)"
            className="flex-1 min-w-[280px] rounded-lg border px-3 py-2 text-sm font-mono"
            style={{ borderColor: "#e5e7eb" }}
          />
          <label className="flex items-center gap-2 text-xs text-gray-700">
            거리 ≤
            <input
              type="number"
              min={0}
              max={64}
              value={searchDistance}
              onChange={(e) => setSearchDistance(parseInt(e.target.value) || 10)}
              className="w-16 rounded-lg border px-2 py-1 text-xs"
              style={{ borderColor: "#e5e7eb" }}
            />
          </label>
          <button
            onClick={runSearch}
            disabled={searchLoading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {searchLoading ? "검색 중..." : "유사 검색"}
          </button>
        </div>
        {searchResults && (
          <div className="mt-4">
            {searchResults.length === 0 ? (
              <div className="text-sm text-gray-500">유사한 미디어가 없습니다</div>
            ) : (
              <ul className="divide-y" style={{ borderColor: "#f3f4f6" }}>
                {searchResults.map((r) => (
                  <li key={r.media_fact_id} className="flex items-center gap-3 py-2 text-xs">
                    <span
                      className="rounded px-1.5 py-0.5 font-semibold tabular-nums"
                      style={{ color: "#b91c1c", background: "#fee2e2" }}
                    >
                      d={r.distance}
                    </span>
                    <span className="font-mono text-[11px] text-gray-500 truncate max-w-[200px]">
                      {r.media_fact_id}
                    </span>
                    <span className="truncate text-gray-700 flex-1" title={r.fileUrl || ""}>
                      {r.fileUrl || "—"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* Fact ID → Summary */}
      <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">Fact ID 로 미디어 요약 조회</h2>
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            value={summaryFactId}
            onChange={(e) => setSummaryFactId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && loadSummary()}
            placeholder="KnowledgeFact ID"
            className="flex-1 min-w-[280px] rounded-lg border px-3 py-2 text-sm font-mono"
            style={{ borderColor: "#e5e7eb" }}
          />
          <button
            onClick={loadSummary}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy === "summary" ? "조회 중..." : "조회"}
          </button>
        </div>
        {summary && (
          <div className="mt-4 space-y-2 rounded-lg bg-gray-50 p-3 text-xs" style={{ border: "1px solid #e5e7eb" }}>
            <div>
              <span className="font-semibold text-gray-700">사실 내용: </span>
              <span className="text-gray-900">{summary.content || "—"}</span>
            </div>
            {summary.media && (
              <>
                <div>
                  <span className="font-semibold text-gray-700">타입: </span>
                  <span>{summary.media.mediaType || "—"}</span>
                </div>
                {summary.media.perceptualHash && (
                  <div className="font-mono">
                    <span className="font-semibold text-gray-700 font-sans">pHash: </span>
                    <span className="break-all">{summary.media.perceptualHash}</span>
                  </div>
                )}
                <div>
                  <span className="font-semibold text-gray-700">딥페이크 점수: </span>
                  <span className="tabular-nums">
                    {(summary.media.deepfakeScore ?? 0).toFixed(2)}
                  </span>
                </div>
                {summary.media.ocrText && (
                  <div>
                    <span className="font-semibold text-gray-700">OCR: </span>
                    <span className="line-clamp-3">{summary.media.ocrText}</span>
                  </div>
                )}
                {summary.media.transcription && (
                  <div>
                    <span className="font-semibold text-gray-700">전사: </span>
                    <span className="line-clamp-3">{summary.media.transcription}</span>
                  </div>
                )}
                {(summary.media.manipulationFlags || []).length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    <span className="font-semibold text-gray-700">변조 플래그: </span>
                    {(summary.media.manipulationFlags || []).map((f) => (
                      <span
                        key={f}
                        className="rounded px-1.5 py-0.5 text-[10px]"
                        style={{ color: "#b91c1c", background: "#fee2e2" }}
                      >
                        {f}
                      </span>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MediaCard({
  item,
  busy,
  onProcess,
  onScanCopies,
}: {
  item: SuspectMedia;
  busy: string | null;
  onProcess: () => void;
  onScanCopies: () => void;
}) {
  const isVisual = item.mediaType === "IMAGE" || item.mediaType === "VIDEO";
  const scoreColor =
    item.deepfakeScore >= 0.8 ? "#991b1b" : item.deepfakeScore >= 0.6 ? "#d97706" : "#16a34a";
  const scoreBg =
    item.deepfakeScore >= 0.8 ? "#fee2e2" : item.deepfakeScore >= 0.6 ? "#fef3c7" : "#dcfce7";
  return (
    <div
      className="overflow-hidden rounded-xl border bg-white"
      style={{ borderColor: "#e5e7eb" }}
    >
      <div
        className="flex h-40 items-center justify-center"
        style={{ background: "#f3f4f6" }}
      >
        {isVisual && item.fileUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.fileUrl}
            alt={item.media_fact_id}
            className="h-full w-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <span className="text-5xl opacity-40">
            {MEDIA_ICON[item.mediaType] || "📦"}
          </span>
        )}
      </div>
      <div className="p-3 text-xs">
        <div className="flex items-start justify-between gap-2">
          <span className="font-mono text-[10px] text-gray-500 break-all">
            {item.media_fact_id}
          </span>
          <span
            className="shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold tabular-nums"
            style={{ color: scoreColor, background: scoreBg }}
          >
            {item.deepfakeScore.toFixed(2)}
          </span>
        </div>
        <div className="mt-1 truncate text-[11px] text-gray-600" title={item.fileUrl}>
          {item.fileUrl}
        </div>
        {(item.manipulationFlags || []).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {(item.manipulationFlags || []).slice(0, 4).map((f) => (
              <span
                key={f}
                className="rounded px-1 py-0.5 text-[10px]"
                style={{ color: "#b91c1c", background: "#fee2e2" }}
              >
                {f}
              </span>
            ))}
          </div>
        )}
        <div className="mt-3 flex gap-1">
          <button
            onClick={onProcess}
            disabled={busy !== null}
            className="flex-1 rounded-lg border px-2 py-1 text-[11px] font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-40"
            style={{ borderColor: "#c7d2fe" }}
          >
            {busy === `process:${item.media_fact_id}` ? "처리..." : "재분석"}
          </button>
          <button
            onClick={onScanCopies}
            disabled={busy !== null}
            className="flex-1 rounded-lg border px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-50 disabled:opacity-40"
            style={{ borderColor: "#e5e7eb" }}
          >
            {busy === `scan:${item.media_fact_id}` ? "스캔..." : "복사본 스캔"}
          </button>
        </div>
      </div>
    </div>
  );
}
