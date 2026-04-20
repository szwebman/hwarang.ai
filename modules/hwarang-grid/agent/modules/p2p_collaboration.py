"""P2P 에이전트 협업 모듈

같은 네트워크(LAN)의 에이전트끼리 직접 통신하여:
  - 작업 분배 (내가 바쁘면 옆 PC에 위임)
  - 모델 샤딩 (큰 모델을 여러 PC로 분할)
  - LoRA 공유 (마스터 없이 P2P로)

통신 방식:
  - UDP 브로드캐스트로 피어 발견
  - HTTP로 실제 데이터 전송
  - 하트비트로 피어 상태 유지
"""

import json
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field, asdict
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

DISCOVERY_PORT = 19090
P2P_HTTP_PORT = 19091
BROADCAST_INTERVAL = 30
PEER_TIMEOUT = 90
MAGIC = b"HWARANG_P2P_V1"


@dataclass
class PeerInfo:
    agent_id: str
    ip: str
    port: int
    gpu_name: str
    vram_gb: float
    tier: str
    status: str = "idle"
    load_percent: float = 0.0
    lora_version: int = 0
    last_seen: float = field(default_factory=time.time)


class P2PCollaborationModule:
    """에이전트 간 P2P 통신 및 작업 협업."""

    def __init__(self, config=None):
        self.agent_id = ""
        self.gpu_name = "unknown"
        self.vram_gb = 0.0
        self.tier = "lite"
        self.peers: dict[str, PeerInfo] = {}
        self._running = False
        self._threads: list[threading.Thread] = []
        self._http_server: HTTPServer | None = None
        self._my_ip = self._get_local_ip()

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self, agent_id: str, gpu_name: str = "", vram_gb: float = 0, tier: str = "lite"):
        """P2P 모듈 시작."""
        self.agent_id = agent_id
        self.gpu_name = gpu_name
        self.vram_gb = vram_gb
        self.tier = tier
        self._running = True

        for name, target in [
            ("p2p-listen", self._udp_listener),
            ("p2p-broadcast", self._udp_broadcaster),
            ("p2p-http", self._start_http_server),
            ("p2p-cleanup", self._cleanup_loop),
        ]:
            t = threading.Thread(target=target, daemon=True, name=name)
            t.start()
            self._threads.append(t)

        logger.info(f"P2P 시작: {self._my_ip}:{P2P_HTTP_PORT}")

    def stop(self):
        self._running = False
        if self._http_server:
            self._http_server.shutdown()

    # ════════════════════════════════════════════════════════════
    # UDP 피어 발견
    # ════════════════════════════════════════════════════════════

    def _udp_broadcaster(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        while self._running:
            try:
                payload = json.dumps({
                    "agent_id": self.agent_id,
                    "ip": self._my_ip,
                    "port": P2P_HTTP_PORT,
                    "gpu_name": self.gpu_name,
                    "vram_gb": self.vram_gb,
                    "tier": self.tier,
                }).encode()
                sock.sendto(MAGIC + payload, ("255.255.255.255", DISCOVERY_PORT))
            except Exception:
                pass
            time.sleep(BROADCAST_INTERVAL)
        sock.close()

    def _udp_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        sock.bind(("", DISCOVERY_PORT))
        sock.settimeout(5)

        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
                if not data.startswith(MAGIC):
                    continue
                payload = json.loads(data[len(MAGIC):])
                aid = payload.get("agent_id", "")
                if aid == self.agent_id:
                    continue

                self.peers[aid] = PeerInfo(
                    agent_id=aid,
                    ip=payload.get("ip", addr[0]),
                    port=payload.get("port", P2P_HTTP_PORT),
                    gpu_name=payload.get("gpu_name", ""),
                    vram_gb=payload.get("vram_gb", 0),
                    tier=payload.get("tier", "lite"),
                    last_seen=time.time(),
                )
            except socket.timeout:
                continue
            except Exception:
                pass
        sock.close()

    def _cleanup_loop(self):
        while self._running:
            now = time.time()
            expired = [a for a, p in self.peers.items() if now - p.last_seen > PEER_TIMEOUT]
            for a in expired:
                del self.peers[a]
            time.sleep(30)

    # ════════════════════════════════════════════════════════════
    # HTTP 서버
    # ════════════════════════════════════════════════════════════

    def _start_http_server(self):
        module = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_GET(self):
                if self.path == "/p2p/status":
                    self._json_response(200, {
                        "agent_id": module.agent_id,
                        "gpu": module.gpu_name,
                        "vram_gb": module.vram_gb,
                        "peers": len(module.peers),
                    })
                elif self.path == "/p2p/peers":
                    self._json_response(200, [asdict(p) for p in module.peers.values()])
                else:
                    self._json_response(404, {"error": "not found"})

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(body) if body else {}

                if self.path == "/p2p/task":
                    result = module._handle_task(data)
                    self._json_response(200, result)
                elif self.path == "/p2p/lora":
                    save_dir = os.path.expanduser("~/.hwarang/p2p_loras")
                    os.makedirs(save_dir, exist_ok=True)
                    name = data.get("name", f"p2p_{int(time.time())}")
                    with open(os.path.join(save_dir, f"{name}.json"), "w") as f:
                        json.dump(data, f)
                    self._json_response(200, {"status": "received"})
                else:
                    self._json_response(404, {"error": "not found"})

            def _json_response(self, code, data):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

        try:
            self._http_server = HTTPServer(("0.0.0.0", P2P_HTTP_PORT), Handler)
            self._http_server.serve_forever()
        except OSError as e:
            logger.warning(f"P2P HTTP 포트 {P2P_HTTP_PORT} 사용 불가: {e}")

    # ════════════════════════════════════════════════════════════
    # 작업 위임/수신
    # ════════════════════════════════════════════════════════════

    def delegate_task(self, task_type: str, payload: dict) -> dict | None:
        """가용 피어에게 작업 위임."""
        peer = self._find_best_peer()
        if not peer:
            return None

        try:
            from urllib.request import urlopen, Request
            url = f"http://{peer.ip}:{peer.port}/p2p/task"
            req = Request(url,
                          data=json.dumps({"type": task_type, "from": self.agent_id, "payload": payload}).encode(),
                          headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                logger.info(f"작업 위임 성공: {task_type} → {peer.agent_id}")
                return result
        except Exception as e:
            logger.warning(f"위임 실패 → {peer.agent_id}: {e}")
            return None

    def _find_best_peer(self) -> PeerInfo | None:
        now = time.time()
        available = [p for p in self.peers.values()
                     if p.status == "idle" and p.load_percent < 80 and now - p.last_seen < PEER_TIMEOUT]
        if not available:
            return None
        available.sort(key=lambda p: (-p.vram_gb, p.load_percent))
        return available[0]

    def _handle_task(self, task: dict) -> dict:
        task_type = task.get("type", "")
        if task_type == "inference":
            return {"status": "completed", "agent_id": self.agent_id}
        elif task_type == "ping":
            return {"status": "pong", "agent_id": self.agent_id}
        return {"status": "unknown_task"}

    def share_lora_with_peers(self, lora_name: str, metadata: dict) -> int:
        """모든 피어에게 LoRA 공유."""
        count = 0
        for peer in self.peers.values():
            try:
                from urllib.request import urlopen, Request
                url = f"http://{peer.ip}:{peer.port}/p2p/lora"
                req = Request(url, data=json.dumps({"name": lora_name, **metadata}).encode(),
                              headers={"Content-Type": "application/json"})
                with urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        count += 1
            except Exception:
                pass
        return count

    def get_peers(self) -> list[dict]:
        now = time.time()
        return [{
            "agent_id": p.agent_id, "ip": p.ip, "gpu": p.gpu_name,
            "vram_gb": p.vram_gb, "tier": p.tier, "online": now - p.last_seen < PEER_TIMEOUT,
        } for p in self.peers.values()]

    def get_stats(self) -> dict:
        now = time.time()
        active = [p for p in self.peers.values() if now - p.last_seen < PEER_TIMEOUT]
        return {
            "my_ip": self._my_ip,
            "total_peers": len(self.peers),
            "active_peers": len(active),
            "total_vram_gb": sum(p.vram_gb for p in active),
        }
