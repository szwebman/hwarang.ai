"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 철회 알림 (Retraction Notifications)
 * - 사용자가 과거 답변의 근거로 사용한 사실이 철회되면 알림 생성
 * - 상단 stats: 미확인 / 전체 / 확인 완료 / 최근 7일
 * - 리스트: 알림 카드 (질문 · 철회된 사실 · 사유 · 시간)
 * - 액션: 확인 / 전체 확인
 * - admin 전용: 대기 알림 발송 / 철회 이벤트 트리거
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface Notification {
  id: string;
  retracted_fact_id: string;
  retraction_event_id: string | null;
  evidence_id: string | null;
  message: string;
  notified: boolean;
  notified_at: string | null;
  acknowledged: boolean;
  acknowledged_at: string | null;
  created_at: string | null;
}

interface StatsPayload {
  total: number;
  acknowledged: number;
  unread: number;
  recent_7d: number;
}

export default function NotificationsPage() {
  const [items, setItems] = useState<Notification[]>([]);
  const [stats, setStats] = useState<StatsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [onlyUnread, setOnlyUnread] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [dispatchOpen, setDispatchOpen] = useState(false);
  const [dispatchBatch, setDispatchBatch] = useState(100);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [triggerEventId, setTriggerEventId] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      qs.set("unacknowledged_only", onlyUnread ? "true" : "false");
      const [listResp, statsResp] = await Promise.all([
        adminFetch(`/api/hlkm/notifications?${qs.toString()}`),
        adminFetch(`/api/hlkm/notifications/stats`),
      ]);
      if (listResp.ok) {
        const data = await listResp.json();
        setItems(Array.isArray(data.notifications) ? data.notifications : []);
      } else {
        setItems([]);
      }
      if (statsResp.ok) {
        const sd = await statsResp.json();
        setStats(sd);
      }
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "로드 실패" });
    } finally {
      setLoading(false);
    }
  }, [onlyUnread]);

  useEffect(() => {
    reload();
  }, [reload]);

  const ackOne = async (id: string) => {
    setBusy(`ack:${id}`);
    try {
      const resp = await adminFetch(
        `/api/hlkm/notifications/${encodeURIComponent(id)}/ack`,
        { method: "POST" }
      );
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${resp.status}`);
      }
      setMessage({ ok: true, text: "확인 처리됨" });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "확인 실패" });
    } finally {
      setBusy(null);
    }
  };

  const ackAll = async () => {
    setBusy("ack-all");
    try {
      const resp = await adminFetch(`/api/hlkm/notifications/ack-all`, {
        method: "POST",
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({ ok: true, text: `${data.count ?? 0}건 일괄 확인 처리` });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "전체 확인 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runDispatch = async () => {
    setBusy("dispatch");
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/notifications/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_batch: dispatchBatch }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `발송 완료 — 성공 ${data.sent ?? 0} / 실패 ${data.failed ?? 0} / 스캔 ${data.scanned ?? 0}`,
      });
      setDispatchOpen(false);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "발송 실패" });
    } finally {
      setBusy(null);
    }
  };

  const runTrigger = async () => {
    if (!triggerEventId.trim()) {
      setMessage({ ok: false, text: "철회 이벤트 ID를 입력하세요" });
      return;
    }
    setBusy("trigger");
    setMessage(null);
    try {
      const resp = await adminFetch(`/api/hlkm/notifications/trigger-for-retraction`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ retraction_event_id: triggerEventId.trim() }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setMessage({
        ok: true,
        text: `알림 ${data.created ?? data.notifications_created ?? 0}건 생성됨`,
      });
      setTriggerOpen(false);
      setTriggerEventId("");
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "트리거 실패" });
    } finally {
      setBusy(null);
    }
  };

  const visibleItems = useMemo(() => items, [items]);

  return (
    <div className="space-y-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">철회 알림</h1>
          <p className="mt-1 text-sm text-gray-500">
            Retraction Notifications — 과거 답변의 근거 사실이 철회되면 해당 사용자에게 통지합니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setTriggerOpen(true)}
            disabled={busy !== null}
            className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
            style={{ borderColor: "#e5e7eb", color: "#374151" }}
          >
            철회 이벤트 트리거
          </button>
          <button
            onClick={() => setDispatchOpen(true)}
            disabled={busy !== null}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            대기 알림 발송
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

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="미확인" value={stats?.unread ?? 0} accent="warning" />
        <StatCard label="확인 완료" value={stats?.acknowledged ?? 0} accent="success" />
        <StatCard label="전체" value={stats?.total ?? 0} accent="primary" />
        <StatCard label="최근 7일" value={stats?.recent_7d ?? 0} accent="neutral" />
      </div>

      <div
        className="flex flex-wrap items-center gap-4 rounded-xl border bg-white p-4"
        style={{ borderColor: "#e5e7eb" }}
      >
        <label className="flex items-center gap-2 text-xs text-gray-700">
          <input
            type="checkbox"
            checked={onlyUnread}
            onChange={(e) => setOnlyUnread(e.target.checked)}
          />
          미확인만 보기
        </label>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-gray-500">
            {loading ? "불러오는 중..." : `${items.length.toLocaleString("ko-KR")}건`}
          </span>
          {visibleItems.length > 0 && (
            <button
              onClick={ackAll}
              disabled={busy !== null}
              className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
              style={{ borderColor: "#e5e7eb" }}
            >
              전체 확인
            </button>
          )}
        </div>
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

      <div className="space-y-3">
        {!loading && visibleItems.length === 0 && (
          <div
            className="rounded-xl border bg-white p-10 text-center text-sm text-gray-400"
            style={{ borderColor: "#e5e7eb" }}
          >
            알림이 없습니다.
          </div>
        )}
        {visibleItems.map((n) => (
          <div
            key={n.id}
            className="rounded-xl border bg-white p-4 transition-shadow hover:shadow-sm"
            style={{
              borderColor: n.acknowledged ? "#e5e7eb" : "#fecaca",
              background: n.acknowledged ? "#ffffff" : "#fef2f2",
            }}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center gap-2 text-xs text-gray-500">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ background: n.acknowledged ? "#9ca3af" : "#ef4444" }}
                  />
                  <span>
                    {n.acknowledged ? "확인 완료" : "미확인"}
                  </span>
                  <span>·</span>
                  <span>{n.created_at ? new Date(n.created_at).toLocaleString("ko-KR") : "—"}</span>
                  {n.notified && (
                    <>
                      <span>·</span>
                      <span className="text-[10px]" style={{ color: "#2563eb" }}>
                        발송됨
                      </span>
                    </>
                  )}
                </div>
                <div className="text-sm text-gray-900">{n.message}</div>
                <div className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-gray-500 sm:grid-cols-3">
                  <div className="truncate">
                    <span className="text-gray-400">철회된 사실:</span>{" "}
                    <code className="font-mono text-gray-700">{n.retracted_fact_id}</code>
                  </div>
                  {n.evidence_id && (
                    <div className="truncate">
                      <span className="text-gray-400">근거 ID:</span>{" "}
                      <code className="font-mono text-gray-700">{n.evidence_id}</code>
                    </div>
                  )}
                  {n.retraction_event_id && (
                    <div className="truncate">
                      <span className="text-gray-400">이벤트:</span>{" "}
                      <code className="font-mono text-gray-700">{n.retraction_event_id}</code>
                    </div>
                  )}
                </div>
              </div>
              {!n.acknowledged && (
                <button
                  onClick={() => ackOne(n.id)}
                  disabled={busy !== null}
                  className="shrink-0 rounded-lg border px-3 py-1.5 text-xs hover:bg-white disabled:opacity-60"
                  style={{ borderColor: "#e5e7eb", background: "#ffffff", color: "#374151" }}
                >
                  {busy === `ack:${n.id}` ? "처리 중..." : "확인"}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {dispatchOpen && (
        <ModalOverlay onClose={() => setDispatchOpen(false)}>
          <div
            className="w-full max-w-md rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">대기 알림 발송</h2>
            <p className="mt-1 text-xs text-gray-500">
              notified=False 인 알림을 배치로 push 전송합니다.
            </p>
            <label className="mt-4 block">
              <div className="mb-1 text-xs font-semibold text-gray-700">배치 크기</div>
              <input
                type="number"
                value={dispatchBatch}
                onChange={(e) =>
                  setDispatchBatch(Math.max(1, parseInt(e.target.value) || 100))
                }
                className="w-full rounded-lg border px-3 py-2 text-sm"
                style={{ borderColor: "#e5e7eb" }}
                min={1}
                max={5000}
              />
            </label>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setDispatchOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runDispatch}
                disabled={busy !== null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "dispatch" ? "발송 중..." : "발송 실행"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}

      {triggerOpen && (
        <ModalOverlay onClose={() => setTriggerOpen(false)}>
          <div
            className="w-full max-w-md rounded-xl border bg-white p-6"
            style={{ borderColor: "#e5e7eb" }}
          >
            <h2 className="text-lg font-bold text-gray-900">철회 이벤트 트리거</h2>
            <p className="mt-1 text-xs text-gray-500">
              RetractionEvent id 를 입력하면 영향받은 사용자들에게 알림을 생성합니다.
            </p>
            <label className="mt-4 block">
              <div className="mb-1 text-xs font-semibold text-gray-700">이벤트 ID</div>
              <input
                value={triggerEventId}
                onChange={(e) => setTriggerEventId(e.target.value)}
                placeholder="retract_xxx..."
                className="w-full rounded-lg border px-3 py-2 font-mono text-xs"
                style={{ borderColor: "#e5e7eb" }}
              />
            </label>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setTriggerOpen(false)}
                disabled={busy !== null}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={runTrigger}
                disabled={busy !== null || !triggerEventId.trim()}
                className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-60"
              >
                {busy === "trigger" ? "처리 중..." : "실행"}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
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
