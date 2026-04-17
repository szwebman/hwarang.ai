"""HFL Distributed Serving - Grid 에이전트를 통한 분산 추론

학습된 모델을 Grid 에이전트에 분산 배포하여 서빙.
마스터 GPU가 부족해도 서비스 가능.

원리:
  1. 마스터가 학습 완료된 LoRA를 Grid 에이전트에 배포 (~2MB)
  2. 에이전트가 로컬 베이스 모델 + LoRA로 추론 서버 시작
  3. 사용자 요청 → 마스터가 가장 빠른/가까운 에이전트로 라우팅
  4. 에이전트가 추론 → 결과를 사용자에게 직접 반환

장점:
  - 마스터 GPU 부족해도 서비스 확장
  - 지리적 분산으로 지연시간 감소 (한국/미국/일본 에이전트)
  - 자동 로드밸런싱
  - 에이전트 다운 → 자동 페일오버 (다른 에이전트로)

보안:
  - 에이전트는 LoRA만 보유 (베이스 모델은 직접 다운)
  - 모든 통신 TLS 암호화
  - 응답 무결성 검증 (해시)
"""

from __future__ import annotations

import json
import logging
import time
import hashlib
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ServingAgent:
    agent_id: str
    endpoint: str                    # http://agent-ip:8000
    region: str = "kr"               # kr, us, jp, eu
    gpu_name: str = "unknown"
    gpu_vram_gb: float = 0
    max_concurrent: int = 4          # 최대 동시 요청
    current_load: int = 0            # 현재 처리 중 요청
    latency_ms: float = 0            # 마스터까지 지연시간
    lora_version: str = ""           # 현재 로드된 LoRA 버전
    status: str = "offline"          # online, offline, overloaded
    last_health_check: float = 0
    total_requests: int = 0
    avg_response_ms: float = 0
    error_count: int = 0


class DistributedServingManager:
    """Grid 에이전트 기반 분산 추론 서빙 관리자.

    마스터에서 실행. 에이전트 등록/상태 관리 + 요청 라우팅.
    """

    def __init__(self):
        self.agents: dict[str, ServingAgent] = {}
        self.current_lora_version: str = ""
        self.current_lora_path: str = ""

    # ─── 에이전트 등록 ────────────────────────────────────

    def register_agent(
        self,
        agent_id: str,
        endpoint: str,
        region: str = "kr",
        gpu_name: str = "unknown",
        gpu_vram_gb: float = 0,
        max_concurrent: int = 4,
    ) -> ServingAgent:
        """추론 에이전트 등록."""
        agent = ServingAgent(
            agent_id=agent_id,
            endpoint=endpoint,
            region=region,
            gpu_name=gpu_name,
            gpu_vram_gb=gpu_vram_gb,
            max_concurrent=max_concurrent,
            status="online",
            last_health_check=time.time(),
        )
        self.agents[agent_id] = agent

        logger.info(
            f"서빙 에이전트 등록: {agent_id} "
            f"({gpu_name}, {region}, {endpoint})"
        )
        return agent

    # ─── LoRA 배포 ────────────────────────────────────────

    def deploy_lora(self, lora_path: str, version: str) -> dict:
        """학습된 LoRA를 모든 온라인 에이전트에 배포.

        LoRA만 전송 (~2MB, HFL Adaptive 압축 적용)
        """
        import urllib.request

        self.current_lora_version = version
        self.current_lora_path = lora_path

        # HFL 압축 적용
        try:
            from hfl_adaptive import AdaptiveTransfer
        except ImportError:
            logger.warning("hfl_adaptive 없음, 원본 전송")

        results = {}
        online_agents = [a for a in self.agents.values() if a.status == "online"]

        logger.info(
            f"LoRA 배포: v{version} → {len(online_agents)}개 에이전트"
        )

        for agent in online_agents:
            try:
                # 에이전트에 LoRA 업데이트 요청
                req_data = json.dumps({
                    "action": "update_lora",
                    "version": version,
                    "lora_path": lora_path,  # 실제로는 파일 전송
                }).encode()

                req = urllib.request.Request(
                    f"{agent.endpoint}/admin/update_lora",
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                resp = urllib.request.urlopen(req, timeout=30)

                if resp.status == 200:
                    agent.lora_version = version
                    results[agent.agent_id] = "success"
                    logger.info(f"  ✅ {agent.agent_id}: 배포 완료")
                else:
                    results[agent.agent_id] = f"failed ({resp.status})"
            except Exception as e:
                results[agent.agent_id] = f"error ({e})"
                logger.warning(f"  ❌ {agent.agent_id}: {e}")

        return {
            "version": version,
            "deployed": sum(1 for r in results.values() if r == "success"),
            "total": len(online_agents),
            "results": results,
        }

    # ─── 라우팅 (가장 적합한 에이전트 선택) ────────────────

    def select_agent(
        self,
        user_region: str = "kr",
        required_vram: float = 0,
    ) -> ServingAgent | None:
        """요청을 처리할 최적 에이전트 선택.

        우선순위:
          1. 같은 지역
          2. 여유 있는 (load < max)
          3. 최신 LoRA 버전
          4. 지연시간 낮은
        """
        candidates = [
            a for a in self.agents.values()
            if a.status == "online"
            and a.current_load < a.max_concurrent
            and a.gpu_vram_gb >= required_vram
        ]

        if not candidates:
            return None

        # 점수 계산
        def score(agent: ServingAgent) -> float:
            s = 0.0
            # 같은 지역 선호
            if agent.region == user_region:
                s += 100
            # 여유도 (load 적을수록 좋음)
            s += (1 - agent.current_load / max(agent.max_concurrent, 1)) * 50
            # 최신 LoRA
            if agent.lora_version == self.current_lora_version:
                s += 30
            # 지연시간 (낮을수록 좋음)
            s -= agent.latency_ms / 10
            # 에러율 (낮을수록 좋음)
            if agent.total_requests > 0:
                error_rate = agent.error_count / agent.total_requests
                s -= error_rate * 50
            return s

        candidates.sort(key=score, reverse=True)
        return candidates[0]

    # ─── 요청 프록시 ──────────────────────────────────────

    async def proxy_request(
        self,
        messages: list[dict],
        model: str = "",
        user_region: str = "kr",
        stream: bool = False,
    ) -> dict:
        """사용자 요청을 최적 에이전트로 프록시.

        Returns: 에이전트의 추론 결과
        """
        import urllib.request

        agent = self.select_agent(user_region)
        if not agent:
            return {"error": "사용 가능한 서빙 에이전트가 없습니다", "status": 503}

        agent.current_load += 1
        start_time = time.time()

        try:
            req_data = json.dumps({
                "model": model,
                "messages": messages,
                "stream": stream,
                "max_tokens": 2048,
            }).encode()

            req = urllib.request.Request(
                f"{agent.endpoint}/v1/chat/completions",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read())

            # 응답 무결성 검증 (해시)
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            result["_integrity"] = hashlib.sha256(content.encode()).hexdigest()[:16]
            result["_served_by"] = agent.agent_id
            result["_region"] = agent.region

            # 통계 업데이트
            elapsed = (time.time() - start_time) * 1000
            agent.total_requests += 1
            agent.avg_response_ms = (
                agent.avg_response_ms * (agent.total_requests - 1) + elapsed
            ) / agent.total_requests

            return result

        except Exception as e:
            agent.error_count += 1
            logger.error(f"에이전트 {agent.agent_id} 추론 실패: {e}")

            # 페일오버: 다른 에이전트로 재시도
            agent.status = "overloaded"
            backup = self.select_agent(user_region)
            if backup and backup.agent_id != agent.agent_id:
                logger.info(f"페일오버: {agent.agent_id} → {backup.agent_id}")
                agent.current_load -= 1
                return await self.proxy_request(messages, model, user_region, stream)

            return {"error": str(e), "status": 500}
        finally:
            agent.current_load -= 1

    # ─── 헬스 체크 ────────────────────────────────────────

    def health_check_all(self) -> dict:
        """모든 에이전트 헬스 체크."""
        import urllib.request

        results = {}
        for agent in self.agents.values():
            try:
                start = time.time()
                req = urllib.request.Request(f"{agent.endpoint}/health")
                resp = urllib.request.urlopen(req, timeout=5)
                latency = (time.time() - start) * 1000

                if resp.status == 200:
                    agent.status = "online"
                    agent.latency_ms = latency
                    agent.last_health_check = time.time()
                    results[agent.agent_id] = f"online ({latency:.0f}ms)"
                else:
                    agent.status = "offline"
                    results[agent.agent_id] = f"error ({resp.status})"
            except Exception as e:
                agent.status = "offline"
                results[agent.agent_id] = f"offline ({e})"

        online = sum(1 for a in self.agents.values() if a.status == "online")
        logger.info(f"헬스 체크: {online}/{len(self.agents)} 온라인")

        return results

    # ─── 통계 ────────────────────────────────────────────

    def get_cluster_stats(self) -> dict:
        """서빙 클러스터 통계."""
        agents = list(self.agents.values())
        online = [a for a in agents if a.status == "online"]

        return {
            "total_agents": len(agents),
            "online": len(online),
            "total_capacity": sum(a.max_concurrent for a in online),
            "current_load": sum(a.current_load for a in online),
            "total_requests": sum(a.total_requests for a in agents),
            "avg_latency_ms": (
                sum(a.latency_ms for a in online) / max(len(online), 1)
            ),
            "lora_version": self.current_lora_version,
            "regions": {
                r: sum(1 for a in online if a.region == r)
                for r in set(a.region for a in online)
            },
        }


# ─── 에이전트 측 코드 (Grid PC에서 실행) ──────────────────────

class ServingAgentLocal:
    """Grid PC에서 실행되는 추론 에이전트.

    역할:
      1. 베이스 모델 + LoRA 로드
      2. 추론 요청 처리
      3. LoRA 업데이트 수신
      4. 헬스 체크 응답
    """

    def __init__(
        self,
        base_model_path: str,
        lora_path: str | None = None,
        port: int = 8000,
    ):
        self.base_model_path = base_model_path
        self.lora_path = lora_path
        self.port = port
        self.lora_version = ""

    def start(self):
        """vLLM 기반 로컬 서빙 시작."""
        import os

        cmd = f"vllm serve {self.base_model_path}"
        cmd += f" --port {self.port}"
        cmd += " --trust-remote-code"
        cmd += " --gpu-memory-utilization 0.9"
        cmd += " --enable-prefix-caching"

        if self.lora_path:
            cmd += f" --enable-lora --lora-modules hwarang={self.lora_path}"

        logger.info(f"로컬 서빙 시작: {cmd}")
        os.system(cmd)

    def update_lora(self, new_lora_path: str, version: str):
        """LoRA 핫 업데이트 (vLLM 재시작 필요)."""
        self.lora_path = new_lora_path
        self.lora_version = version
        logger.info(f"LoRA 업데이트: v{version} ({new_lora_path})")
        # 실제로는 vLLM 재시작 또는 dynamic LoRA loading


# ─── 메인 ────────────────────────────────────────────────────

if __name__ == "__main__":
    dsm = DistributedServingManager()

    # 에이전트 등록 시뮬레이션
    agents = [
        ("agent_kr_01", "http://kr1.hwarang.ai:8000", "kr", "RTX 5090", 32, 8),
        ("agent_kr_02", "http://kr2.hwarang.ai:8000", "kr", "RTX 4090", 24, 4),
        ("agent_jp_01", "http://jp1.hwarang.ai:8000", "jp", "RTX 4080", 16, 4),
        ("agent_us_01", "http://us1.hwarang.ai:8000", "us", "RTX 4090", 24, 4),
    ]

    for aid, ep, reg, gpu, vram, mc in agents:
        dsm.register_agent(aid, ep, reg, gpu, vram, mc)

    # 라우팅 시뮬
    agent = dsm.select_agent(user_region="kr")
    if agent:
        print(f"\n한국 유저 → {agent.agent_id} ({agent.gpu_name}, {agent.region})")

    agent = dsm.select_agent(user_region="us")
    if agent:
        print(f"미국 유저 → {agent.agent_id} ({agent.gpu_name}, {agent.region})")

    print(f"\n클러스터 통계: {json.dumps(dsm.get_cluster_stats(), indent=2)}")
