/**
 * 화랑 하이브리드 서빙 (AI CDN)
 *
 * 서버군(메인) + Grid 에이전트(보조) 혼합 운용.
 *
 * 동작:
 *   평상시 (GPU <80%):  서버 직접 처리
 *   피크 (GPU >80%):    에이전트로 오버플로우 분배
 *   서버 점검/장애:      에이전트 전체 전환 (무중단)
 *   복잡 작업:          서버(검증) + 에이전트(부분 생성) 협력
 *   유휴:               에이전트는 HFL 학습에 투입
 */

export interface ServerNode {
  id: string;
  endpoint: string;         // http://server1:8000
  gpuUtilization: number;   // 0~1 (실시간)
  maxConcurrent: number;
  currentLoad: number;
  status: "online" | "maintenance" | "offline";
  lastCheck: number;
  avgResponseMs: number;
  totalRequests: number;
}

export interface GridAgent {
  id: string;
  endpoint: string;
  region: string;            // kr, us, jp
  gpuName: string;
  vramGb: number;
  tier: "small" | "medium" | "large";
  status: "idle" | "serving" | "learning" | "offline" | "quarantined";
  currentLoad: number;
  maxConcurrent: number;
  latencyMs: number;
  reliability: number;       // 0~1
  loraVersion: string;

  // ─── 불량 추적 ──────────────────────────────
  consecutiveFailures: number;    // 연속 실패 횟수
  totalFailures: number;          // 누적 실패
  totalSuccesses: number;         // 누적 성공
  failureRate: number;            // 실패율 (0~1)
  lastFailureAt: number;          // 마지막 실패 시간
  quarantinedUntil: number;       // 격리 해제 시간 (0이면 미격리)
  quarantineCount: number;        // 격리 횟수
}

export type ServingTarget =
  | { type: "server"; node: ServerNode }
  | { type: "agent"; agent: GridAgent }
  | { type: "hybrid"; server: ServerNode; agent: GridAgent; mode: "chunked" | "tiered" };

// ─── 서빙 매니저 ────────────────────────────────────────────

export class HybridServingManager {
  private servers: Map<string, ServerNode> = new Map();
  private agents: Map<string, GridAgent> = new Map();

  // 설정
  private overflowThreshold = 0.8;
  private emergencyThreshold = 0.95;
  private healthCheckInterval = 10000;

  // 불량 에이전트 관리 설정
  private maxConsecutiveFailures = 3;     // 연속 3회 실패 → 즉시 격리
  private maxFailureRate = 0.3;           // 실패율 30% 초과 → 격리
  private quarantineBaseMinutes = 5;      // 격리 기본 시간 (5분)
  private quarantineMaxMinutes = 1440;    // 격리 최대 시간 (24시간)
  private permanentBanThreshold = 10;     // 격리 10회 → 영구 제외

  // 통계
  private stats = {
    totalRequests: 0,
    serverHandled: 0,
    agentHandled: 0,
    hybridHandled: 0,
    failovers: 0,
  };

  // ─── 노드 등록 ──────────────────────────────────────

  registerServer(node: ServerNode): void {
    this.servers.set(node.id, node);
  }

  registerAgent(agent: GridAgent): void {
    // 불량 추적 기본값 설정
    agent.consecutiveFailures = agent.consecutiveFailures ?? 0;
    agent.totalFailures = agent.totalFailures ?? 0;
    agent.totalSuccesses = agent.totalSuccesses ?? 0;
    agent.failureRate = agent.failureRate ?? 0;
    agent.lastFailureAt = agent.lastFailureAt ?? 0;
    agent.quarantinedUntil = agent.quarantinedUntil ?? 0;
    agent.quarantineCount = agent.quarantineCount ?? 0;
    this.agents.set(agent.id, agent);
  }

  // ─── 에이전트 성공/실패 기록 ────────────────────────

  /**
   * 에이전트 응답 성공 기록.
   * 연속 실패 리셋 + 신뢰도 상승.
   */
  recordSuccess(agentId: string): void {
    const agent = this.agents.get(agentId);
    if (!agent) return;

    agent.consecutiveFailures = 0;
    agent.totalSuccesses++;
    agent.failureRate = agent.totalFailures / Math.max(agent.totalFailures + agent.totalSuccesses, 1);
    agent.reliability = Math.min(1.0, agent.reliability + 0.01);
  }

  /**
   * 에이전트 응답 실패 기록.
   * 연속 실패 누적 → 임계 초과 시 자동 격리.
   */
  recordFailure(agentId: string, reason: string = ""): void {
    const agent = this.agents.get(agentId);
    if (!agent) return;

    agent.consecutiveFailures++;
    agent.totalFailures++;
    agent.lastFailureAt = Date.now();
    agent.failureRate = agent.totalFailures / Math.max(agent.totalFailures + agent.totalSuccesses, 1);
    agent.reliability = Math.max(0, agent.reliability - 0.05);

    console.log(
      `[Agent Failure] ${agentId}: 연속 ${agent.consecutiveFailures}회, ` +
      `실패율 ${(agent.failureRate * 100).toFixed(1)}%, 사유: ${reason}`
    );

    // 자동 격리 판정
    if (agent.consecutiveFailures >= this.maxConsecutiveFailures) {
      this._quarantineAgent(agentId, `연속 ${agent.consecutiveFailures}회 실패`);
    } else if (agent.failureRate > this.maxFailureRate && (agent.totalFailures + agent.totalSuccesses) >= 10) {
      this._quarantineAgent(agentId, `실패율 ${(agent.failureRate * 100).toFixed(0)}% 초과`);
    }
  }

  /**
   * 에이전트 격리 (일정 시간 동안 선택 대상에서 제외).
   * 격리 횟수에 따라 시간 지수 증가 (5분 → 10분 → 20분 → ... → 최대 24시간).
   */
  private _quarantineAgent(agentId: string, reason: string): void {
    const agent = this.agents.get(agentId);
    if (!agent) return;

    agent.quarantineCount++;

    // 영구 제외 체크
    if (agent.quarantineCount >= this.permanentBanThreshold) {
      agent.status = "quarantined";
      agent.quarantinedUntil = Infinity;
      console.log(`🚫 [Agent BANNED] ${agentId}: 영구 제외 (격리 ${agent.quarantineCount}회)`);
      return;
    }

    // 격리 시간 지수 증가: 5분 × 2^(횟수-1)
    const minutes = Math.min(
      this.quarantineBaseMinutes * Math.pow(2, agent.quarantineCount - 1),
      this.quarantineMaxMinutes,
    );
    agent.status = "quarantined";
    agent.quarantinedUntil = Date.now() + minutes * 60 * 1000;
    agent.consecutiveFailures = 0; // 격리 시 리셋

    console.log(
      `⏸️ [Agent Quarantine] ${agentId}: ${minutes}분 격리 ` +
      `(${agent.quarantineCount}회차, 사유: ${reason})`
    );
  }

  /**
   * 격리 해제 체크. 시간 만료된 에이전트 자동 복귀.
   * 헬스체크 시 호출.
   */
  checkQuarantineExpiry(): string[] {
    const released: string[] = [];
    const now = Date.now();

    for (const [id, agent] of this.agents) {
      if (agent.status === "quarantined" && agent.quarantinedUntil <= now && agent.quarantinedUntil !== Infinity) {
        agent.status = "idle";
        agent.consecutiveFailures = 0;
        released.push(id);
        console.log(`✅ [Agent Released] ${id}: 격리 해제 (${agent.quarantineCount}회차)`);
      }
    }

    return released;
  }

  /**
   * 불량 에이전트 통계.
   */
  getAgentHealthStats(): {
    healthy: number;
    quarantined: number;
    banned: number;
    details: Array<{
      id: string;
      status: string;
      failureRate: number;
      consecutiveFailures: number;
      quarantineCount: number;
    }>;
  } {
    const agents = [...this.agents.values()];
    const quarantined = agents.filter((a) => a.status === "quarantined" && a.quarantinedUntil !== Infinity);
    const banned = agents.filter((a) => a.status === "quarantined" && a.quarantinedUntil === Infinity);
    const healthy = agents.filter((a) => a.status !== "quarantined" && a.status !== "offline");

    return {
      healthy: healthy.length,
      quarantined: quarantined.length,
      banned: banned.length,
      details: agents
        .filter((a) => a.totalFailures > 0 || a.status === "quarantined")
        .map((a) => ({
          id: a.id,
          status: a.status,
          failureRate: Math.round(a.failureRate * 100),
          consecutiveFailures: a.consecutiveFailures,
          quarantineCount: a.quarantineCount,
        })),
    };
  }

  // ─── GPU 사용률 업데이트 ────────────────────────────

  updateServerUtilization(serverId: string, utilization: number): void {
    const server = this.servers.get(serverId);
    if (server) {
      server.gpuUtilization = utilization;
      server.lastCheck = Date.now();
    }
  }

  // ─── 라우팅 결정 (핵심 로직) ────────────────────────

  selectTarget(options: {
    complexity?: "simple" | "complex";
    userRegion?: string;
    userPlan?: string;
    stream?: boolean;
  } = {}): ServingTarget | null {
    this.stats.totalRequests++;

    const onlineServers = [...this.servers.values()].filter(
      (s) => s.status === "online"
    );
    // 격리 해제 체크 (만료된 에이전트 자동 복귀)
    this.checkQuarantineExpiry();

    // 불량/격리/꽉찬 에이전트 완전 제외
    const availableAgents = [...this.agents.values()].filter(
      (a) => a.status !== "offline"
        && a.status !== "quarantined"           // 격리된 에이전트 제외
        && a.currentLoad < a.maxConcurrent      // 꽉 차면 제외
        && (a.status === "idle" || a.status === "serving")
    );

    // ─── Case 1: 서버 전부 오프라인 → 에이전트 전환 ──
    if (onlineServers.length === 0) {
      const agent = this._selectBestAgent(availableAgents, options.userRegion);
      if (agent) {
        this.stats.agentHandled++;
        this.stats.failovers++;
        return { type: "agent", agent };
      }
      return null;
    }

    // ─── Case 2: 평상시 (서버 여유) → 서버 직접 ──────
    const avgUtilization = onlineServers.reduce((s, n) => s + n.gpuUtilization, 0) / onlineServers.length;

    if (avgUtilization < this.overflowThreshold) {
      const server = this._selectBestServer(onlineServers);
      if (server) {
        this.stats.serverHandled++;
        return { type: "server", node: server };
      }
    }

    // ─── Case 3: 피크 (80~95%) → 에이전트 분배 ────────
    if (avgUtilization < this.emergencyThreshold) {
      // 유료 플랜 → 서버 우선
      if (options.userPlan && ["pro", "business", "enterprise"].includes(options.userPlan)) {
        const server = this._selectBestServer(onlineServers);
        if (server && server.currentLoad < server.maxConcurrent) {
          this.stats.serverHandled++;
          return { type: "server", node: server };
        }
      }

      // Free/Starter → 에이전트로
      const agent = this._selectBestAgent(availableAgents, options.userRegion);
      if (agent) {
        this.stats.agentHandled++;
        return { type: "agent", agent };
      }

      // 에이전트도 없으면 서버
      const server = this._selectBestServer(onlineServers);
      if (server) {
        this.stats.serverHandled++;
        return { type: "server", node: server };
      }
    }

    // ─── Case 4: 긴급 (95%+) → 에이전트 우선 ─────────
    const agent = this._selectBestAgent(availableAgents, options.userRegion);
    if (agent) {
      this.stats.agentHandled++;
      return { type: "agent", agent };
    }

    // 에이전트도 없으면 서버에 무조건 넣기
    const server = this._selectBestServer(onlineServers);
    if (server) {
      this.stats.serverHandled++;
      return { type: "server", node: server };
    }

    return null;
  }

  // ─── 복잡한 작업: 서버 + 에이전트 협력 ──────────────

  selectHybridTarget(options: {
    userRegion?: string;
    mode?: "chunked" | "tiered";
  } = {}): ServingTarget | null {
    const onlineServers = [...this.servers.values()].filter(
      (s) => s.status === "online"
    );
    const availableAgents = [...this.agents.values()].filter(
      (a) => a.status !== "offline"
    );

    const server = this._selectBestServer(onlineServers);
    const agent = this._selectBestAgent(availableAgents, options.userRegion);

    if (server && agent) {
      this.stats.hybridHandled++;
      return {
        type: "hybrid",
        server,
        agent,
        mode: options.mode || "tiered",
      };
    }

    // 한쪽만 있으면 단독
    if (server) return { type: "server", node: server };
    if (agent) return { type: "agent", agent };
    return null;
  }

  // ─── 서버 선택 (부하 낮은 것) ───────────────────────

  private _selectBestServer(servers: ServerNode[]): ServerNode | null {
    if (servers.length === 0) return null;

    return servers.sort((a, b) => {
      // 부하 낮은 것 우선
      const loadA = a.currentLoad / Math.max(a.maxConcurrent, 1);
      const loadB = b.currentLoad / Math.max(b.maxConcurrent, 1);
      if (loadA !== loadB) return loadA - loadB;
      // 응답 시간 빠른 것
      return a.avgResponseMs - b.avgResponseMs;
    })[0];
  }

  // ─── 에이전트 선택 (지역 + 신뢰도 + 여유) ───────────

  private _selectBestAgent(agents: GridAgent[], userRegion?: string): GridAgent | null {
    if (agents.length === 0) return null;

    // 완전 유휴(load=0) 에이전트 우선, 부분 사용 중은 후순위
    return agents.sort((a, b) => {
      // 유휴 우선 (load 0 > load 1 > load 2...)
      if (a.currentLoad !== b.currentLoad) return a.currentLoad - b.currentLoad;

      let scoreA = 0, scoreB = 0;

      // 같은 지역 보너스
      if (userRegion) {
        if (a.region === userRegion) scoreA += 100;
        if (b.region === userRegion) scoreB += 100;
      }

      // 여유도
      scoreA += (1 - a.currentLoad / Math.max(a.maxConcurrent, 1)) * 50;
      scoreB += (1 - b.currentLoad / Math.max(b.maxConcurrent, 1)) * 50;

      // 신뢰도
      scoreA += a.reliability * 30;
      scoreB += b.reliability * 30;

      // tier (큰 GPU 선호)
      const tierScore = { small: 0, medium: 10, large: 20 };
      scoreA += tierScore[a.tier] || 0;
      scoreB += tierScore[b.tier] || 0;

      return scoreB - scoreA;
    })[0];
  }

  // ─── 에이전트 상태 전환 (서빙 ↔ 학습) ───────────────

  switchAgentMode(agentId: string, mode: "serving" | "learning" | "idle"): void {
    const agent = this.agents.get(agentId);
    if (agent) {
      agent.status = mode;
    }
  }

  activateAgentsForServing(count: number): string[] {
    /**
     * 학습 중인 에이전트를 서빙으로 전환.
     * 피크 타임에 자동 호출.
     */
    const learningAgents = [...this.agents.values()]
      .filter((a) => a.status === "learning" || a.status === "idle")
      .sort((a, b) => b.reliability - a.reliability);

    const activated: string[] = [];
    for (const agent of learningAgents.slice(0, count)) {
      agent.status = "serving";
      activated.push(agent.id);
    }

    return activated;
  }

  releaseAgentsToLearning(): string[] {
    /**
     * 서빙 여유 생기면 에이전트를 학습으로 복귀.
     * 한산할 때 자동 호출.
     */
    const avgUtil = this._getAvgServerUtilization();
    if (avgUtil > 0.5) return []; // 아직 여유 없음

    const servingAgents = [...this.agents.values()]
      .filter((a) => a.status === "serving" && a.currentLoad === 0);

    const released: string[] = [];
    for (const agent of servingAgents) {
      agent.status = "learning";
      released.push(agent.id);
    }

    return released;
  }

  private _getAvgServerUtilization(): number {
    const online = [...this.servers.values()].filter((s) => s.status === "online");
    if (online.length === 0) return 1.0;
    return online.reduce((s, n) => s + n.gpuUtilization, 0) / online.length;
  }

  // ─── 헬스 체크 ──────────────────────────────────────

  async healthCheckAll(): Promise<{
    servers: Record<string, string>;
    agents: Record<string, string>;
  }> {
    const serverResults: Record<string, string> = {};
    const agentResults: Record<string, string> = {};

    // 서버 체크
    for (const [id, server] of this.servers) {
      try {
        const start = Date.now();
        const resp = await fetch(`${server.endpoint}/health`, {
          signal: AbortSignal.timeout(5000),
        });
        const latency = Date.now() - start;

        if (resp.ok) {
          server.status = "online";
          server.lastCheck = Date.now();
          serverResults[id] = `online (${latency}ms)`;

          // GPU 사용률도 가져오기
          try {
            const data = await resp.json();
            if (data.gpu_utilization !== undefined) {
              server.gpuUtilization = data.gpu_utilization;
            }
          } catch {}
        } else {
          server.status = "offline";
          serverResults[id] = `error (${resp.status})`;
        }
      } catch {
        server.status = "offline";
        serverResults[id] = "offline";
      }
    }

    // 에이전트 체크
    for (const [id, agent] of this.agents) {
      try {
        const start = Date.now();
        const resp = await fetch(`${agent.endpoint}/health`, {
          signal: AbortSignal.timeout(5000),
        });
        const latency = Date.now() - start;

        if (resp.ok) {
          if (agent.status === "offline") agent.status = "idle";
          agent.latencyMs = latency;
          agentResults[id] = `${agent.status} (${latency}ms)`;
        } else {
          agent.status = "offline";
          agentResults[id] = `error (${resp.status})`;
        }
      } catch {
        agent.status = "offline";
        agentResults[id] = "offline";
      }
    }

    // 자동 에이전트 전환 체크
    const avgUtil = this._getAvgServerUtilization();
    if (avgUtil > this.overflowThreshold) {
      const needed = Math.ceil(
        ([...this.servers.values()].reduce((s, n) => s + n.currentLoad, 0) -
          [...this.servers.values()].reduce((s, n) => s + n.maxConcurrent * this.overflowThreshold, 0))
      );
      if (needed > 0) {
        const activated = this.activateAgentsForServing(needed);
        if (activated.length > 0) {
          console.log(`[HybridServing] 피크 감지: ${activated.length}개 에이전트 서빙 전환`);
        }
      }
    } else if (avgUtil < 0.5) {
      const released = this.releaseAgentsToLearning();
      if (released.length > 0) {
        console.log(`[HybridServing] 한산: ${released.length}개 에이전트 학습 복귀`);
      }
    }

    return { servers: serverResults, agents: agentResults };
  }

  // ─── 통계 ────────────────────────────────────────────

  getStats() {
    const onlineServers = [...this.servers.values()].filter((s) => s.status === "online");
    const onlineAgents = [...this.agents.values()].filter((a) => a.status !== "offline");
    const servingAgents = [...this.agents.values()].filter((a) => a.status === "serving");
    const learningAgents = [...this.agents.values()].filter((a) => a.status === "learning");

    return {
      ...this.stats,
      serverUtilization: this._getAvgServerUtilization(),
      servers: {
        total: this.servers.size,
        online: onlineServers.length,
        avgLoad: onlineServers.reduce((s, n) => s + n.gpuUtilization, 0) / Math.max(onlineServers.length, 1),
      },
      agents: {
        total: this.agents.size,
        online: onlineAgents.length,
        serving: servingAgents.length,
        learning: learningAgents.length,
      },
      distribution: {
        serverPct: Math.round(this.stats.serverHandled / Math.max(this.stats.totalRequests, 1) * 100),
        agentPct: Math.round(this.stats.agentHandled / Math.max(this.stats.totalRequests, 1) * 100),
        hybridPct: Math.round(this.stats.hybridHandled / Math.max(this.stats.totalRequests, 1) * 100),
      },
    };
  }
}

// ─── 싱글턴 인스턴스 ────────────────────────────────────────

export const hybridServing = new HybridServingManager();
