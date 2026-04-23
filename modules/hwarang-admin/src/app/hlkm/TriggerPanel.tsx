"use client";

/**
 * TriggerPanel — 수동 트리거 버튼 패널 (Client Component)
 * 대시보드에서 사용: 자가 검증 실행, HRAG 동기화, 반감기 재학습
 */

import { useState } from "react";
import { adminFetch } from "@/lib/auth";

type TriggerKey = "verify" | "hrag" | "halflife";

const TRIGGERS: { key: TriggerKey; label: string; path: string; icon: string; description: string }[] = [
  {
    key: "verify",
    label: "지금 자가 검증 실행",
    path: "/api/hlkm/admin/verify/run",
    icon: "🔍",
    description: "만료·노화된 사실을 즉시 재검증",
  },
  {
    key: "hrag",
    label: "HRAG 법률 동기화",
    path: "/api/hlkm/admin/hrag/sync",
    icon: "⚖️",
    description: "법률 조문 최신본을 HRAG로 동기화",
  },
  {
    key: "halflife",
    label: "반감기 모델 재학습",
    path: "/api/hlkm/admin/halflife/retrain",
    icon: "⏳",
    description: "도메인별 반감기 파라미터 재학습",
  },
];

export default function TriggerPanel() {
  const [running, setRunning] = useState<TriggerKey | null>(null);
  const [log, setLog] = useState<{ key: TriggerKey; ok: boolean; msg: string; at: number }[]>([]);

  const run = async (t: (typeof TRIGGERS)[number]) => {
    if (running) return;
    setRunning(t.key);
    try {
      const resp = await adminFetch(t.path, { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      const ok = resp.ok;
      setLog((l) => [
        { key: t.key, ok, msg: ok ? (data.message || "실행 완료") : (data.error || `HTTP ${resp.status}`), at: Date.now() },
        ...l,
      ].slice(0, 5));
    } catch (e: any) {
      setLog((l) => [
        { key: t.key, ok: false, msg: e?.message || "네트워크 오류", at: Date.now() },
        ...l,
      ].slice(0, 5));
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
      <h3 className="mb-3 text-sm font-semibold text-gray-900">수동 트리거</h3>
      <div className="flex flex-col gap-2">
        {TRIGGERS.map((t) => {
          const isRunning = running === t.key;
          return (
            <button
              key={t.key}
              onClick={() => run(t)}
              disabled={running !== null}
              className="flex items-start gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-gray-50 disabled:opacity-60"
              style={{ borderColor: "#e5e7eb" }}
            >
              <span className="text-lg">{t.icon}</span>
              <div className="flex-1">
                <div className="text-sm font-medium text-gray-900">
                  {isRunning ? "실행 중..." : t.label}
                </div>
                <div className="mt-0.5 text-xs text-gray-500">{t.description}</div>
              </div>
              {isRunning && (
                <span className="mt-0.5 inline-block h-3 w-3 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
              )}
            </button>
          );
        })}
      </div>

      {log.length > 0 && (
        <div className="mt-4 border-t pt-3" style={{ borderColor: "#e5e7eb" }}>
          <div className="mb-2 text-xs font-medium text-gray-500">실행 로그</div>
          <ul className="space-y-1 text-xs">
            {log.map((l, i) => (
              <li key={i} className="flex items-center gap-2">
                <span style={{ color: l.ok ? "#16a34a" : "#dc2626" }}>
                  {l.ok ? "✓" : "✗"}
                </span>
                <span className="text-gray-500">
                  {new Date(l.at).toLocaleTimeString("ko-KR")}
                </span>
                <span className="truncate text-gray-700">{l.msg}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
