"use client";

import { useEffect, useState } from "react";

interface Worker {
  id: string;
  host: string;
  port: number;
  status: "idle" | "busy" | "draining" | "offline";
  type: string;
  models: string[];
  gpuCount: number;
  gpuMemoryMb: number;
  gpuUsagePercent: number;
  activeRequests: number;
  totalProcessed: number;
  uptime: string;
  lastHeartbeat: number;
}

export default function ServersPage() {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchWorkers = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_HWARANG_API_URL || "http://localhost:8000";
      const resp = await fetch(`/api/admin/stats`);
      const data = await resp.json();

      if (data.cluster?.workers) {
        // 실제 클러스터 API에서 상세 정보 가져오기
        const clusterResp = await fetch(`${apiUrl}/admin/cluster/workers`).catch(() => null);
        const clusterData = clusterResp?.ok ? await clusterResp.json() : null;

        if (clusterData?.workers) {
          setWorkers(clusterData.workers.map((w: any) => ({
            id: w.worker_id || w.id,
            host: w.host || "unknown",
            port: w.port || 50051,
            status: w.status || "offline",
            type: w.models?.length > 1 ? "Speculative" : "Fast",
            models: w.models || [],
            gpuCount: w.gpu_count || 0,
            gpuMemoryMb: w.gpu_memory_mb || 0,
            gpuUsagePercent: 0,
            activeRequests: 0,
            totalProcessed: 0,
            uptime: "N/A",
            lastHeartbeat: w.last_heartbeat || 0,
          })));
        }
      }
    } catch {}
    setLoading(false);
  };

  useEffect(() => {
    fetchWorkers();
    const interval = setInterval(fetchWorkers, 5000); // 5초마다 갱신
    return () => clearInterval(interval);
  }, []);

  const statusColor = (status: string) => {
    switch (status) {
      case "idle": return { bg: "#dcfce7", text: "#166534", label: "대기" };
      case "busy": return { bg: "#fef3c7", text: "#92400e", label: "처리중" };
      case "draining": return { bg: "#fde68a", text: "#78350f", label: "종료중" };
      case "offline": return { bg: "#fee2e2", text: "#991b1b", label: "오프라인" };
      default: return { bg: "var(--muted)", text: "var(--muted-foreground)", label: status };
    }
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--muted)" }}>
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">서버 모니터링</h1>
            <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
              마스터 + 서브 서버 실시간 상태
            </p>
          </div>
          <div className="flex gap-2">
            <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
              자동 갱신: 5초
            </span>
          </div>
        </div>

        {/* 마스터 서버 상태 */}
        <div className="rounded-2xl p-5 mb-6" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
          <div className="flex items-center gap-3 mb-3">
            <span className="text-lg">🖥️</span>
            <h2 className="font-semibold">마스터 서버</h2>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "#dcfce7", color: "#166534" }}>정상</span>
          </div>
          <div className="grid grid-cols-4 gap-4 text-sm">
            <div><span style={{ color: "var(--muted-foreground)" }}>Redis:</span> <span style={{ color: "#22c55e" }}>연결됨</span></div>
            <div><span style={{ color: "var(--muted-foreground)" }}>PostgreSQL:</span> <span style={{ color: "#22c55e" }}>연결됨</span></div>
            <div><span style={{ color: "var(--muted-foreground)" }}>API 서버:</span> <span style={{ color: "#22c55e" }}>실행중 (port 8000)</span></div>
            <div><span style={{ color: "var(--muted-foreground)" }}>Web UI:</span> <span style={{ color: "#22c55e" }}>실행중 (port 3000)</span></div>
          </div>
        </div>

        {/* 서브 서버 목록 */}
        <h2 className="font-semibold mb-4">서브 서버 ({workers.length}대)</h2>
        <div className="space-y-4">
          {workers.map((worker) => {
            const sc = statusColor(worker.status);
            const heartbeatAgo = Math.round(Date.now() / 1000 - worker.lastHeartbeat);

            return (
              <div
                key={worker.id}
                className="rounded-2xl p-5"
                style={{
                  background: "var(--background)",
                  border: `1px solid ${worker.status === "offline" ? "#fca5a5" : "var(--border)"}`,
                  opacity: worker.status === "offline" ? 0.7 : 1,
                }}
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <span className="text-lg">{worker.status === "offline" ? "🔴" : worker.status === "busy" ? "🟡" : "🟢"}</span>
                    <div>
                      <span className="font-mono text-sm font-semibold">{worker.id}</span>
                      <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                        {worker.host}:{worker.port} · {worker.type}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2.5 py-1 rounded-full font-medium" style={{ background: sc.bg, color: sc.text }}>
                      {sc.label}
                    </span>
                    {worker.status !== "offline" && (
                      <button className="text-xs px-3 py-1 rounded-lg border" style={{ borderColor: "var(--border)" }}>
                        종료
                      </button>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-6 gap-4 text-sm">
                  {/* GPU 사용률 */}
                  <div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>GPU 사용률</div>
                    <div className="flex items-center gap-2 mt-1">
                      <div className="flex-1 h-2 rounded-full" style={{ background: "var(--muted)" }}>
                        <div className="h-2 rounded-full" style={{
                          width: `${worker.gpuUsagePercent}%`,
                          background: worker.gpuUsagePercent > 80 ? "#ef4444" : worker.gpuUsagePercent > 50 ? "#f59e0b" : "#22c55e",
                        }} />
                      </div>
                      <span className="text-xs font-mono">{worker.gpuUsagePercent}%</span>
                    </div>
                  </div>

                  {/* GPU 메모리 */}
                  <div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>VRAM</div>
                    <div className="font-medium mt-1">{(worker.gpuMemoryMb / 1024).toFixed(0)}GB</div>
                  </div>

                  {/* 현재 요청 */}
                  <div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>현재 요청</div>
                    <div className="font-medium mt-1">{worker.activeRequests}</div>
                  </div>

                  {/* 처리 총 수 */}
                  <div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>총 처리</div>
                    <div className="font-medium mt-1">{worker.totalProcessed.toLocaleString()}</div>
                  </div>

                  {/* 가동 시간 */}
                  <div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>가동 시간</div>
                    <div className="font-medium mt-1">{worker.uptime}</div>
                  </div>

                  {/* 하트비트 */}
                  <div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>마지막 하트비트</div>
                    <div className="font-medium mt-1" style={{ color: heartbeatAgo > 15 ? "#ef4444" : "var(--foreground)" }}>
                      {heartbeatAgo}초 전
                    </div>
                  </div>
                </div>

                {/* 로드된 모델 */}
                <div className="flex gap-2 mt-3">
                  {worker.models.map((m) => (
                    <span key={m} className="text-xs px-2 py-0.5 rounded" style={{ background: "var(--muted)" }}>
                      {m}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
