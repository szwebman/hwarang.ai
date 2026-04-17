"""오프라인 에이전트

인터넷 없이도 로컬 모델로 AI 사용.
인터넷 복구 시 학습 데이터/LoRA 자동 동기화.

동작:
  온라인 → 정상 모드 (마스터 통신)
  오프라인 감지 → 로컬 모드 전환 (로컬 모델만)
  온라인 복구 → 동기화 (오프라인 데이터 업로드, 새 LoRA 다운로드)
"""

import time, json, os, logging, socket

logger = logging.getLogger(__name__)


class OfflineAgentModule:
    def __init__(self, config=None):
        self.is_online = True
        self.offline_since: float | None = None
        self.offline_queue: list[dict] = []  # 오프라인 중 쌓인 데이터
        self.sync_pending = False
        self.local_model_path = ""
        self.data_path = os.path.expanduser("~/.hwarang/offline_queue")
        os.makedirs(self.data_path, exist_ok=True)

    def check_connectivity(self, master_url: str = "https://grid.hwarang.ai") -> bool:
        """인터넷 연결 상태 확인."""
        try:
            host = master_url.replace("https://", "").replace("http://", "").split("/")[0]
            socket.create_connection((host, 443), timeout=5)
            was_offline = not self.is_online
            self.is_online = True

            if was_offline:
                offline_duration = time.time() - (self.offline_since or time.time())
                logger.info(f"🌐 온라인 복구 (오프라인 {offline_duration/3600:.1f}시간)")
                self.sync_pending = True
                self.offline_since = None

            return True
        except (socket.timeout, OSError):
            if self.is_online:
                self.is_online = False
                self.offline_since = time.time()
                logger.info("📡 오프라인 감지 → 로컬 모드 전환")
            return False

    def queue_offline_data(self, data_type: str, data: dict):
        """오프라인 중 데이터 큐에 추가 (온라인 복구 시 동기화)."""
        entry = {"type": data_type, "data": data, "timestamp": time.time()}
        self.offline_queue.append(entry)

        # 파일로도 저장 (재시작 대비)
        queue_file = os.path.join(self.data_path, "queue.jsonl")
        with open(queue_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def sync_on_reconnect(self, master_url: str) -> dict:
        """온라인 복구 시 동기화."""
        if not self.sync_pending or not self.offline_queue:
            return {"synced": 0}

        logger.info(f"동기화 시작: {len(self.offline_queue)}건 대기")

        synced = 0
        for entry in self.offline_queue:
            try:
                import urllib.request
                req = urllib.request.Request(
                    f"{master_url}/api/agent/sync",
                    data=json.dumps(entry).encode(),
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=30)
                synced += 1
            except Exception:
                break

        if synced == len(self.offline_queue):
            self.offline_queue.clear()
            self.sync_pending = False
            # 큐 파일 삭제
            queue_file = os.path.join(self.data_path, "queue.jsonl")
            if os.path.exists(queue_file):
                os.remove(queue_file)

        logger.info(f"동기화 완료: {synced}/{len(self.offline_queue)}건")
        return {"synced": synced, "remaining": len(self.offline_queue)}

    def get_local_model_endpoint(self) -> str:
        """오프라인 시 사용할 로컬 모델 엔드포인트."""
        return "http://localhost:8000"  # 로컬 vLLM

    def get_stats(self) -> dict:
        return {
            "is_online": self.is_online,
            "offline_since": self.offline_since,
            "queue_size": len(self.offline_queue),
            "sync_pending": self.sync_pending,
        }
