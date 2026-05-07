"use client";

/**
 * Scheduler 관리 페이지
 *
 * - 이 인스턴스의 leader 여부 + 잡별 last_run/last_error 표시
 * - 활성 분산 락 목록 (다른 인스턴스가 보유 중인 잡 식별)
 * - 락 강제 해제 (크래시한 인스턴스가 락 점유 시 운영자가 풀어줌)
 *
 * 백엔드: /api/scheduler/* (Next 프록시) → ${HWARANG_API_URL}/api/scheduler/*
 */

import { useCallback, useEffect, useState } from "react";
import { adminFetch } from "@/lib/auth";

interface JobInfo {
  name: string;
  last_run: string | null;
  last_result: any;
  last_error: string | null;
}

interface SchedulerStatus {
  host: string;
  is_leader_env: boolean;
  running: boolean;
  task_count: number;
  jobs: JobInfo[];
}

interface SchedulerLock {
  job_name: string;
  host: string;
  acquired_at: string;
  expires_at: string;
  ttl_seconds: number;
}

interface LocksResponse {
  host: string;
  locks: SchedulerLock[];
  count: number;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("ko-KR", { hour12: false });
  } catch {
    return iso;
  }
}

function formatTtl(seconds: number): string {
  if (seconds <= 0) return "만료됨";
  if (seconds < 60) return `${seconds}초`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분 ${seconds % 60}초`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}시간 ${m}분`;
}

export default function SchedulerPage() {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [locksData, setLocksData] = useState<LocksResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusResp, locksResp] = await Promise.all([
        adminFetch("/api/scheduler/status"),
        adminFetch("/api/scheduler/locks"),
      ]);
      if (!statusResp.ok) throw new Error(`status ${statusResp.status}`);
      if (!locksResp.ok) throw new Error(`locks ${locksResp.status}`);
      const s = (await statusResp.json()) as SchedulerStatus;
      const l = (await locksResp.json()) as LocksResponse;
      setStatus(s);
      setLocksData(l);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(fetchAll, 10_000);
    return () => clearInterval(t);
  }, [autoRefresh, fetchAll]);

  const handleRelease = async (jobName: string) => {
    if (!confirm(`'${jobName}' 락을 강제 해제하시겠습니까?\n실행 중인 잡이 있으면 다른 인스턴스가 즉시 takeover 할 수 있습니다.`)) {
      return;
    }
    setMessage(null);
    try {
      const resp = await adminFetch(
        `/api/scheduler/locks/${encodeURIComponent(jobName)}/release`,
        { method: "POST" },
      );
      const data = await resp.json();
      if (!resp.ok) {
        setMessage({ type: "error", text: data?.detail || data?.error || `해제 실패 (${resp.status})` });
        return;
      }
      setMessage({ type: "success", text: `'${jobName}' 락 해제됨 (by ${data.released_by})` });
      await fetchAll();
    } catch (e: any) {
      setMessage({ type: "error", text: e?.message || String(e) });
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 1200 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>스케줄러 관리</h1>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            10초 자동 새로고침
          </label>
          <button
            onClick={fetchAll}
            disabled={loading}
            style={{
              padding: "6px 12px",
              borderRadius: 6,
              border: "1px solid #d1d5db",
              background: "white",
              cursor: loading ? "wait" : "pointer",
              fontSize: 13,
            }}
          >
            {loading ? "로딩…" : "새로고침"}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: 12, marginBottom: 16, background: "#fee2e2", color: "#991b1b", borderRadius: 6 }}>
          오류: {error}
        </div>
      )}
      {message && (
        <div
          style={{
            padding: 12,
            marginBottom: 16,
            background: message.type === "success" ? "#dcfce7" : "#fee2e2",
            color: message.type === "success" ? "#166534" : "#991b1b",
            borderRadius: 6,
          }}
        >
          {message.text}
        </div>
      )}

      {/* 인스턴스 상태 카드 */}
      {status && (
        <div
          style={{
            padding: 16,
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            marginBottom: 24,
            background: "white",
          }}
        >
          <h2 style={{ fontSize: 16, fontWeight: 600, marginTop: 0, marginBottom: 12 }}>
            이 인스턴스 상태
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
            <Stat label="Host" value={status.host} />
            <Stat
              label="LEADER 환경변수"
              value={status.is_leader_env ? "✅ ON" : "❌ OFF"}
              color={status.is_leader_env ? "#16a34a" : "#6b7280"}
            />
            <Stat
              label="cron 동작 중"
              value={status.running ? "✅ 동작" : "⏸️ 정지"}
              color={status.running ? "#16a34a" : "#dc2626"}
            />
            <Stat label="등록된 잡 수" value={String(status.task_count)} />
          </div>
          {!status.is_leader_env && (
            <div
              style={{
                marginTop: 12,
                padding: 10,
                background: "#fef3c7",
                color: "#92400e",
                borderRadius: 6,
                fontSize: 13,
              }}
            >
              이 인스턴스는 leader 가 아닙니다 (HWARANG_SCHEDULER_LEADER=0). cron 잡이 실행되지 않습니다.
              상태 정보는 다른 leader 인스턴스에서 조회하세요.
            </div>
          )}
        </div>
      )}

      {/* 활성 분산 락 */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
          활성 분산 락 ({locksData?.count ?? 0}개)
        </h2>
        <div style={{ border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden", background: "white" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f9fafb", borderBottom: "1px solid #e5e7eb" }}>
                <th style={{ padding: "10px 12px", textAlign: "left" }}>잡 이름</th>
                <th style={{ padding: "10px 12px", textAlign: "left" }}>보유 host</th>
                <th style={{ padding: "10px 12px", textAlign: "left" }}>획득 시각</th>
                <th style={{ padding: "10px 12px", textAlign: "left" }}>만료까지 남은 시간</th>
                <th style={{ padding: "10px 12px", textAlign: "right" }}>작업</th>
              </tr>
            </thead>
            <tbody>
              {!locksData || locksData.locks.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: 24, textAlign: "center", color: "#9ca3af" }}>
                    현재 보유 중인 락이 없습니다.
                  </td>
                </tr>
              ) : (
                locksData.locks.map((lock) => {
                  const isMyHost = lock.host === locksData.host;
                  return (
                    <tr key={lock.job_name} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "10px 12px", fontFamily: "monospace" }}>{lock.job_name}</td>
                      <td style={{ padding: "10px 12px" }}>
                        <span
                          style={{
                            padding: "2px 8px",
                            borderRadius: 4,
                            background: isMyHost ? "#dbeafe" : "#f3f4f6",
                            color: isMyHost ? "#1e40af" : "#374151",
                            fontSize: 12,
                          }}
                        >
                          {lock.host}
                          {isMyHost ? " (나)" : ""}
                        </span>
                      </td>
                      <td style={{ padding: "10px 12px", color: "#6b7280" }}>
                        {formatDateTime(lock.acquired_at)}
                      </td>
                      <td style={{ padding: "10px 12px", color: "#6b7280" }}>
                        {formatTtl(lock.ttl_seconds)}
                      </td>
                      <td style={{ padding: "10px 12px", textAlign: "right" }}>
                        <button
                          onClick={() => handleRelease(lock.job_name)}
                          style={{
                            padding: "4px 10px",
                            borderRadius: 4,
                            border: "1px solid #fecaca",
                            background: "#fef2f2",
                            color: "#b91c1c",
                            cursor: "pointer",
                            fontSize: 12,
                          }}
                        >
                          강제 해제
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 잡별 마지막 실행 정보 */}
      <div>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>잡 실행 이력</h2>
        <div style={{ border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden", background: "white" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f9fafb", borderBottom: "1px solid #e5e7eb" }}>
                <th style={{ padding: "10px 12px", textAlign: "left" }}>잡 이름</th>
                <th style={{ padding: "10px 12px", textAlign: "left" }}>마지막 실행</th>
                <th style={{ padding: "10px 12px", textAlign: "left" }}>결과</th>
                <th style={{ padding: "10px 12px", textAlign: "left" }}>마지막 에러</th>
              </tr>
            </thead>
            <tbody>
              {!status || status.jobs.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ padding: 24, textAlign: "center", color: "#9ca3af" }}>
                    아직 실행된 잡이 없습니다.
                  </td>
                </tr>
              ) : (
                status.jobs.map((job) => (
                  <tr key={job.name} style={{ borderBottom: "1px solid #f3f4f6" }}>
                    <td style={{ padding: "10px 12px", fontFamily: "monospace" }}>{job.name}</td>
                    <td style={{ padding: "10px 12px", color: "#6b7280" }}>
                      {formatDateTime(job.last_run)}
                    </td>
                    <td style={{ padding: "10px 12px", color: "#6b7280" }}>
                      {job.last_result ? (
                        <details>
                          <summary style={{ cursor: "pointer", color: "#2563eb" }}>보기</summary>
                          <pre
                            style={{
                              background: "#f9fafb",
                              padding: 8,
                              borderRadius: 4,
                              fontSize: 11,
                              maxHeight: 240,
                              overflow: "auto",
                            }}
                          >
                            {JSON.stringify(job.last_result, null, 2)}
                          </pre>
                        </details>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td style={{ padding: "10px 12px", color: job.last_error ? "#b91c1c" : "#9ca3af" }}>
                      {job.last_error || "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 600, color: color || "#111827" }}>{value}</div>
    </div>
  );
}
