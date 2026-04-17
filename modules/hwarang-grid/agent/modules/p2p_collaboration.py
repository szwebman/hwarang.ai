"""P2P 에이전트 간 협력

마스터 없이 에이전트끼리 직접 통신/협력.
한 에이전트가 처리 못 하는 요청 → 이웃 에이전트에 위임.

프로토콜:
  1. 에이전트 발견 (mDNS/DHT로 로컬 네트워크 스캔)
  2. 능력 교환 ("나는 코딩 특화, 너는?")
  3. 요청 위임 ("법률 질문인데 처리 가능?")
  4. 보상 분배 (요청자 40%, 처리자 60%)
"""

import json, time, logging, socket, threading
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    agent_id: str
    address: str              # IP:Port
    capabilities: list[str]   # ["coding", "legal", "serving"]
    gpu_name: str
    tier: str                 # small, medium, large
    load: float               # 0~1
    reputation: float         # 0~1
    last_seen: float


class P2PCollaborationModule:
    def __init__(self, config=None):
        self.my_id = ""
        self.my_capabilities = []
        self.peers: dict[str, PeerInfo] = {}
        self.port = 9100
        self.collaborations = 0

    def discover_peers(self, broadcast_port: int = 9100) -> list[PeerInfo]:
        """로컬 네트워크에서 에이전트 탐색 (UDP 브로드캐스트)."""
        discovered = []
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(3)

            # 브로드캐스트 전송
            msg = json.dumps({
                "type": "discover",
                "agent_id": self.my_id,
                "capabilities": self.my_capabilities,
            }).encode()
            sock.sendto(msg, ("<broadcast>", broadcast_port))

            # 응답 수신
            while True:
                try:
                    data, addr = sock.recvfrom(4096)
                    peer_info = json.loads(data.decode())
                    if peer_info.get("agent_id") != self.my_id:
                        peer = PeerInfo(
                            agent_id=peer_info["agent_id"],
                            address=f"{addr[0]}:{broadcast_port}",
                            capabilities=peer_info.get("capabilities", []),
                            gpu_name=peer_info.get("gpu_name", "unknown"),
                            tier=peer_info.get("tier", "medium"),
                            load=peer_info.get("load", 0.5),
                            reputation=peer_info.get("reputation", 0.8),
                            last_seen=time.time(),
                        )
                        self.peers[peer.agent_id] = peer
                        discovered.append(peer)
                except socket.timeout:
                    break

            sock.close()
        except Exception as e:
            logger.warning(f"P2P 탐색 실패: {e}")

        logger.info(f"P2P 탐색: {len(discovered)}개 에이전트 발견")
        return discovered

    def request_collaboration(self, domain: str, question: str) -> dict | None:
        """능력이 맞는 피어에게 요청 위임."""
        # 해당 도메인 가능한 피어 찾기
        candidates = [
            p for p in self.peers.values()
            if domain in p.capabilities and p.load < 0.8 and p.reputation > 0.5
        ]

        if not candidates:
            return None

        # 평판 + 여유 순으로 정렬
        candidates.sort(key=lambda p: (p.reputation, 1 - p.load), reverse=True)
        best = candidates[0]

        logger.info(f"P2P 위임: {domain} → {best.agent_id} ({best.gpu_name})")

        # 실제 HTTP 요청
        try:
            import urllib.request
            req = urllib.request.Request(
                f"http://{best.address}/v1/chat/completions",
                data=json.dumps({
                    "messages": [{"role": "user", "content": question}],
                    "max_tokens": 2048,
                    "p2p_from": self.my_id,
                }).encode(),
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read())
            self.collaborations += 1

            return {
                "response": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "served_by": best.agent_id,
                "reward_split": {"requester": 0.4, "provider": 0.6},
            }
        except Exception as e:
            logger.warning(f"P2P 요청 실패: {e}")
            return None

    def get_stats(self) -> dict:
        return {
            "known_peers": len(self.peers),
            "collaborations": self.collaborations,
            "peers": [
                {"id": p.agent_id, "caps": p.capabilities, "gpu": p.gpu_name}
                for p in self.peers.values()
            ],
        }
