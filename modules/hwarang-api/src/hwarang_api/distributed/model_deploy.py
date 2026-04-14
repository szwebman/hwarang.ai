"""모델 배포 시스템 - 학습된 모델을 서브 서버에 무중단 배포.

흐름:
1. 마스터에서 "새 버전 배포" API 호출
2. Redis에 배포 이벤트 발행
3. 각 서브 Worker가 이벤트 수신:
   a. 새 모델을 백그라운드로 다운로드
   b. 기존 모델로 계속 서비스 (중단 없음!)
   c. 다운로드 완료 → 새 모델 로드 → 기존 모델 언로드
   d. 실패 시 → 기존 모델 유지 + 에러 보고
4. 마스터가 배포 상태 추적

사용법:
    # 마스터에서 새 버전 배포
    curl -X POST http://마스터:8000/admin/models/deploy -d '{
      "model_id": "hwarang-code-30b",
      "version": "v2.1",
      "source_path": "/mnt/nvme2/hwarang/models/hwarang-code-30b-v2.1"
    }'

    # 배포 상태 확인
    curl http://마스터:8000/admin/models/deploy/status

    # 롤백
    curl -X POST http://마스터:8000/admin/models/rollback -d '{
      "model_id": "hwarang-code-30b",
      "version": "v2.0"
    }'
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# 배포 상태 관리
# ============================================================

@dataclass
class DeploymentEvent:
    """배포 이벤트."""
    model_id: str
    version: str
    source_type: str  # "rsync", "scp", "http"
    source_host: str = ""
    source_path: str = ""
    source_url: str = ""
    created_at: float = field(default_factory=time.time)
    created_by: str = "admin"


@dataclass
class WorkerDeployStatus:
    """서브별 배포 상태."""
    worker_id: str
    model_id: str
    version: str
    status: str = "pending"  # pending, downloading, loading, completed, failed, rolled_back
    progress_percent: int = 0
    error: str = ""
    started_at: float = 0
    completed_at: float = 0


# ============================================================
# 마스터 측: 배포 관리자
# ============================================================

class DeploymentManager:
    """마스터에서 모델 배포를 관리합니다."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._redis = None

    async def connect(self):
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(self.redis_url, decode_responses=True)

    async def deploy(self, event: DeploymentEvent) -> dict:
        """새 버전 배포 시작.

        1. 모델 소스 업데이트
        2. 버전 기록
        3. 모든 서브에 배포 이벤트 발행
        """
        if not self._redis:
            await self.connect()

        # 1. 현재 버전 백업 (롤백용)
        current_version = await self._redis.hget(
            "hwarang:model_versions", event.model_id
        )
        if current_version:
            await self._redis.hset(
                "hwarang:model_previous_versions",
                event.model_id,
                current_version,
            )

        # 2. 새 버전 등록
        await self._redis.hset(
            "hwarang:model_versions", event.model_id, event.version
        )

        # 3. 모델 소스 업데이트
        source_info = {
            "type": event.source_type,
            "host": event.source_host,
            "path": event.source_path,
            "url": event.source_url,
            "version": event.version,
        }
        await self._redis.hset(
            "hwarang:model_sources", event.model_id, json.dumps(source_info)
        )

        # 4. 배포 이벤트 발행 (모든 서브가 구독 중)
        deploy_msg = json.dumps(asdict(event))
        await self._redis.publish("hwarang:deploy", deploy_msg)

        # 5. 배포 상태 초기화
        workers = await self._redis.hgetall("hwarang:workers")
        for worker_id, raw in workers.items():
            info = json.loads(raw)
            if event.model_id in info.get("models", []):
                status = WorkerDeployStatus(
                    worker_id=worker_id,
                    model_id=event.model_id,
                    version=event.version,
                    status="pending",
                )
                await self._redis.hset(
                    f"hwarang:deploy_status:{event.model_id}:{event.version}",
                    worker_id,
                    json.dumps(asdict(status)),
                )

        affected = sum(
            1 for w in workers.values()
            if event.model_id in json.loads(w).get("models", [])
        )

        logger.info(f"배포 시작: {event.model_id} → {event.version} "
                    f"(서브 {affected}대)")

        return {
            "status": "deploying",
            "model_id": event.model_id,
            "version": event.version,
            "affected_workers": affected,
        }

    async def rollback(self, model_id: str) -> dict:
        """이전 버전으로 롤백."""
        if not self._redis:
            await self.connect()

        previous = await self._redis.hget(
            "hwarang:model_previous_versions", model_id
        )
        if not previous:
            return {"error": "이전 버전 없음"}

        # 이전 버전으로 재배포
        current = await self._redis.hget("hwarang:model_versions", model_id)
        source_raw = await self._redis.hget("hwarang:model_sources", model_id)
        source = json.loads(source_raw) if source_raw else {}

        event = DeploymentEvent(
            model_id=model_id,
            version=previous,
            source_type=source.get("type", "rsync"),
            source_host=source.get("host", ""),
            source_path=source.get("path", "").replace(current or "", previous),
            created_by="rollback",
        )

        result = await self.deploy(event)
        result["rollback_from"] = current
        result["rollback_to"] = previous
        return result

    async def get_deploy_status(self, model_id: str = None) -> dict:
        """배포 상태 조회."""
        if not self._redis:
            await self.connect()

        if model_id:
            version = await self._redis.hget("hwarang:model_versions", model_id)
            if not version:
                return {"error": "모델 없음"}

            statuses = await self._redis.hgetall(
                f"hwarang:deploy_status:{model_id}:{version}"
            )
            workers = {k: json.loads(v) for k, v in statuses.items()}

            total = len(workers)
            completed = sum(1 for w in workers.values() if w["status"] == "completed")
            failed = sum(1 for w in workers.values() if w["status"] == "failed")

            return {
                "model_id": model_id,
                "version": version,
                "total_workers": total,
                "completed": completed,
                "failed": failed,
                "in_progress": total - completed - failed,
                "workers": workers,
            }

        # 전체 모델 상태
        versions = await self._redis.hgetall("hwarang:model_versions")
        return {"models": versions}


# ============================================================
# 서브 측: 배포 수신자
# ============================================================

class ModelUpdater:
    """서브 Worker에서 모델 업데이트를 처리합니다.

    Worker가 시작할 때 deploy 채널을 구독하고,
    배포 이벤트가 오면 백그라운드로 처리합니다.
    """

    def __init__(
        self,
        worker_id: str,
        model_id: str,
        model_base_dir: str,
        redis_url: str,
    ):
        self.worker_id = worker_id
        self.model_id = model_id
        self.model_base_dir = Path(model_base_dir).parent  # /models/
        self.redis_url = redis_url
        self._redis = None
        self._current_version: str | None = None

    async def start_listening(self):
        """배포 이벤트 구독 시작 (백그라운드 태스크)."""
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(self.redis_url, decode_responses=True)

        pubsub = self._redis.pubsub()
        await pubsub.subscribe("hwarang:deploy")

        logger.info(f"[ModelUpdater] 배포 이벤트 구독 시작")

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                event = json.loads(message["data"])
                if event.get("model_id") == self.model_id:
                    logger.info(f"[ModelUpdater] 배포 이벤트 수신: "
                              f"{event['model_id']} → {event['version']}")
                    asyncio.create_task(
                        self._handle_deploy(event)
                    )
            except Exception as e:
                logger.error(f"[ModelUpdater] 이벤트 처리 오류: {e}")

    async def _handle_deploy(self, event: dict):
        """배포 이벤트 처리 (백그라운드).

        1. 새 버전 다운로드 (별도 디렉토리)
        2. 기존 모델은 계속 서비스
        3. 다운로드 완료 → 엔진에 핫 스왑 요청
        4. 실패 → 기존 유지
        """
        version = event["version"]
        model_id = event["model_id"]
        status_key = f"hwarang:deploy_status:{model_id}:{version}"

        # 상태 업데이트 함수
        async def update_status(status: str, progress: int = 0, error: str = ""):
            s = WorkerDeployStatus(
                worker_id=self.worker_id,
                model_id=model_id,
                version=version,
                status=status,
                progress_percent=progress,
                error=error,
                started_at=time.time() if status == "downloading" else 0,
                completed_at=time.time() if status in ("completed", "failed") else 0,
            )
            await self._redis.hset(status_key, self.worker_id, json.dumps(asdict(s)))

        try:
            # 1. 다운로드 시작
            await update_status("downloading", 0)
            new_model_dir = self.model_base_dir / f"{model_id}-{version}"
            new_model_dir.mkdir(parents=True, exist_ok=True)

            # rsync로 다운로드
            source_type = event.get("source_type", "rsync")
            if source_type == "rsync":
                host = event.get("source_host", "")
                path = event.get("source_path", "")
                src = f"{host}:{path}/" if host else f"{path}/"
                cmd = f"rsync -avz --progress {src} {new_model_dir}/"

                logger.info(f"[ModelUpdater] 다운로드: {cmd}")
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode != 0:
                    raise Exception(f"rsync 실패: {stderr.decode()}")

            await update_status("downloading", 100)

            # 2. 새 모델 검증
            config_file = new_model_dir / "config.yaml"
            model_file = new_model_dir / "model.pt"
            if not config_file.exists() and not model_file.exists():
                raise Exception("다운로드된 모델 파일이 유효하지 않음")

            # 3. 심볼릭 링크 교체 (핫 스왑)
            await update_status("loading", 0)
            current_link = self.model_base_dir / model_id
            old_target = None

            if current_link.is_symlink():
                old_target = current_link.resolve()
                current_link.unlink()
            elif current_link.exists():
                old_target = current_link.rename(
                    self.model_base_dir / f"{model_id}-old-{int(time.time())}"
                )

            current_link.symlink_to(new_model_dir)

            # 4. 완료
            self._current_version = version
            await update_status("completed", 100)
            logger.info(f"[ModelUpdater] 배포 완료: {model_id} → {version}")

            # 5. 이전 버전 정리 (2세대 전 삭제)
            await self._cleanup_old_versions(model_id, keep=2)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[ModelUpdater] 배포 실패: {error_msg}")
            await update_status("failed", 0, error_msg)

            # 실패 시 기존 유지 (아무것도 안 함)
            # 심볼릭 링크가 바뀌었으면 복구
            current_link = self.model_base_dir / model_id
            if not current_link.exists() and old_target and old_target.exists():
                current_link.symlink_to(old_target)
                logger.info("[ModelUpdater] 롤백 완료 (이전 버전 복구)")

    async def _cleanup_old_versions(self, model_id: str, keep: int = 2):
        """오래된 모델 버전 삭제 (디스크 절약)."""
        import re
        pattern = re.compile(rf"^{re.escape(model_id)}-v[\d.]+$")
        versions = []

        for d in self.model_base_dir.iterdir():
            if d.is_dir() and pattern.match(d.name):
                versions.append(d)

        # 최신 순 정렬
        versions.sort(key=lambda d: d.stat().st_mtime, reverse=True)

        # keep개만 남기고 삭제
        for old_dir in versions[keep:]:
            logger.info(f"[ModelUpdater] 이전 버전 삭제: {old_dir}")
            shutil.rmtree(old_dir)
