/**
 * Grid 커뮤니티 통계 API
 * GET /api/community/grid-stats
 *
 * 공개 API (로그인 불필요) - 커뮤니티 페이지에서 실시간 표시
 */

import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  // Hwarang API에서 실시간 데이터 가져오기
  const apiUrl = process.env.HWARANG_API_URL || "http://localhost:8000";

  try {
    // 클러스터 상태
    const clusterResp = await fetch(`${apiUrl}/admin/cluster/status`, {
      cache: "no-store",
    });
    const cluster = clusterResp.ok ? await clusterResp.json() : null;

    // Grid 상태 (Redis에서)
    // TODO: 실제 Grid API 구현 후 연결
    // const gridResp = await fetch(`${apiUrl}/grid/stats`);

    // 현재는 클러스터 정보 + 데모 데이터 혼합
    return Response.json({
      totalAgents: cluster?.workers?.total || 0,
      activeAgents: cluster?.workers?.idle + cluster?.workers?.busy || 0,
      totalGPUs: cluster?.total_gpus || 0,
      totalVRAM_TB: (cluster?.total_gpu_memory_mb || 0) / 1024 / 1024,
      networkTFLOPS: (cluster?.total_gpus || 0) * 120, // 대략 추정
      activeRequests: cluster?.workers?.busy || 0,
      tokensPerSecond: 0,
      requestsToday: 0,
      tokensProcessedToday: 0,
      totalTokensDistributed: 0,
      totalTokensDistributedToday: 0,
      averageRewardPerAgent: 0,
      gpuDistribution: [],
      recentContributors: [],
      topContributors: [],
    });
  } catch {
    // API 연결 전 빈 데이터
    return Response.json({
      totalAgents: 0,
      activeAgents: 0,
      totalGPUs: 0,
      totalVRAM_TB: 0,
      networkTFLOPS: 0,
      activeRequests: 0,
      tokensPerSecond: 0,
      requestsToday: 0,
      tokensProcessedToday: 0,
      totalTokensDistributed: 0,
      totalTokensDistributedToday: 0,
      averageRewardPerAgent: 0,
      gpuDistribution: [],
      recentContributors: [],
      topContributors: [],
    });
  }
}
