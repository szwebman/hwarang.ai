"use client";

import { useEffect, useState } from "react";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface LogRow {
  id: string;
  userId: string;
  user: { name: string | null; email: string };
  model: string;
  endpoint: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  latencyMs: number;
  statusCode: number;
  domain: string | null;
  createdAt: string;
}

export default function LogsPage() {
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ model: "", status: "" });

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    try {
      const resp = await fetch("/api/logs", { headers: authHeaders() });
      if (resp.ok) setLogs(await resp.json());
    } catch {}
    setLoading(false);
  };

  const filtered = logs.filter((l) => {
    if (filter.model && !l.model.includes(filter.model)) return false;
    if (filter.status === "error" && l.statusCode < 400) return false;
    if (filter.status === "success" && l.statusCode >= 400) return false;
    return true;
  });

  const totalTokens = logs.reduce((s, l) => s + l.totalTokens, 0);
  const avgLatency = logs.length ? Math.round(logs.reduce((s, l) => s + l.latencyMs, 0) / logs.length) : 0;
  const errorCount = logs.filter((l) => l.statusCode >= 400).length;

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">요청 로그</h1>
        <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>API 요청 내역 및 토큰 사용량</p>
      </div>

      {/* 통계 */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {[
          { label: "총 요청 수", value: `${logs.length}건` },
          { label: "총 토큰 사용", value: `${totalTokens.toLocaleString()}` },
          { label: "평균 응답 시간", value: `${avgLatency}ms` },
          { label: "에러 수", value: `${errorCount}건`, color: errorCount > 0 ? "#dc2626" : undefined },
        ].map((card, i) => (
          <div key={i} className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
            <div className="text-xl font-bold" style={{ color: card.color || "var(--foreground)" }}>{card.value}</div>
            <div className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>{card.label}</div>
          </div>
        ))}
      </div>

      {/* 필터 */}
      <div className="flex gap-3 mb-4">
        <select value={filter.model} onChange={(e) => setFilter((f) => ({ ...f, model: e.target.value }))}
          className="px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}>
          <option value="">전체 모델</option>
          <option value="7b">7B</option>
          <option value="30b">30B</option>
          <option value="32b">32B</option>
        </select>
        <select value={filter.status} onChange={(e) => setFilter((f) => ({ ...f, status: e.target.value }))}
          className="px-3 py-2 rounded-lg border text-sm" style={{ borderColor: "var(--border)" }}>
          <option value="">전체 상태</option>
          <option value="success">성공 (2xx)</option>
          <option value="error">에러 (4xx/5xx)</option>
        </select>
      </div>

      {/* 테이블 */}
      <div className="rounded-xl overflow-hidden border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "var(--muted)" }}>
              <th className="text-left text-xs font-semibold px-5 py-3">유저</th>
              <th className="text-left text-xs font-semibold px-5 py-3">모델</th>
              <th className="text-right text-xs font-semibold px-5 py-3">토큰</th>
              <th className="text-right text-xs font-semibold px-5 py-3">응답시간</th>
              <th className="text-center text-xs font-semibold px-5 py-3">상태</th>
              <th className="text-left text-xs font-semibold px-5 py-3">도메인</th>
              <th className="text-left text-xs font-semibold px-5 py-3">일시</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="px-5 py-8 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={7} className="px-5 py-8 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>요청 로그가 없습니다</td></tr>
            ) : (
              filtered.map((log) => (
                <tr key={log.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="px-5 py-3">
                    <div className="text-sm">{log.user?.name || "—"}</div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>{log.user?.email}</div>
                  </td>
                  <td className="px-5 py-3">
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "#dbeafe", color: "#2563eb" }}>{log.model}</span>
                  </td>
                  <td className="px-5 py-3 text-sm text-right">
                    <span style={{ color: "var(--muted-foreground)" }}>{log.promptTokens}</span>
                    {" / "}
                    <span className="font-medium">{log.completionTokens}</span>
                  </td>
                  <td className="px-5 py-3 text-sm text-right" style={{
                    color: log.latencyMs > 3000 ? "#dc2626" : log.latencyMs > 1000 ? "#ca8a04" : "#16a34a",
                  }}>
                    {log.latencyMs}ms
                  </td>
                  <td className="px-5 py-3 text-center">
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{
                      background: log.statusCode < 400 ? "#dcfce7" : "#fee2e2",
                      color: log.statusCode < 400 ? "#166534" : "#991b1b",
                    }}>
                      {log.statusCode}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs" style={{ color: "var(--muted-foreground)" }}>{log.domain || "—"}</td>
                  <td className="px-5 py-3 text-xs" style={{ color: "var(--muted-foreground)" }}>
                    {log.createdAt?.replace("T", " ").slice(0, 19)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
