"""Admin endpoints for model management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class LoadModelRequest(BaseModel):
    model_id: str
    model_path: str
    device: str = "auto"
    dtype: str = "bfloat16"


class UnloadModelRequest(BaseModel):
    model_id: str


@router.post("/models/load")
async def load_model(body: LoadModelRequest, request: Request):
    """Load a model into memory."""
    model_manager = request.app.state.model_manager
    try:
        info = await model_manager.load_model(
            model_id=body.model_id,
            model_path=body.model_path,
            device=body.device,
            dtype=body.dtype,
        )
        return {"status": "loaded", "model": info.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load model: {e}")


@router.post("/models/unload")
async def unload_model(body: UnloadModelRequest, request: Request):
    """Unload a model from memory."""
    model_manager = request.app.state.model_manager
    try:
        await model_manager.unload_model(body.model_id)
        return {"status": "unloaded", "model_id": body.model_id}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# 모델 소스 등록 (서브 서버가 자동 다운로드할 수 있도록)
# ============================================================

class RegisterModelSourceRequest(BaseModel):
    model_id: str
    source_type: str  # "rsync", "scp", "http", "nfs"
    host: str = ""    # 마스터 IP (rsync/scp)
    path: str = ""    # 마스터의 모델 경로
    url: str = ""     # HTTP URL (MinIO/S3)
    hf_repo: str = "" # Hugging Face repo (예: "persismore/hwarang-code-7b")


@router.post("/models/register-source")
async def register_model_source(body: RegisterModelSourceRequest, request: Request):
    """모델 소스 등록.

    마스터에서 이 API를 호출하면, 서브 서버가 Worker 시작 시
    자동으로 모델을 다운로드합니다.

    예시:
      # rsync 방식 (마스터에서 복사)
      curl -X POST http://localhost:8000/admin/models/register-source -d '{
        "model_id": "hwarang-code-30b",
        "source_type": "rsync",
        "host": "192.168.1.100",
        "path": "/mnt/nvme2/hwarang/models/hwarang-code-30b"
      }'

      # Hugging Face 방식
      curl -X POST http://localhost:8000/admin/models/register-source -d '{
        "model_id": "hwarang-code-7b",
        "source_type": "hf",
        "hf_repo": "persismore/hwarang-code-7b"
      }'
    """
    import json
    import redis.asyncio as aioredis

    settings = request.app.state.settings
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    source_info = {
        "type": body.source_type,
        "host": body.host,
        "path": body.path,
        "url": body.url,
    }

    await redis.hset("hwarang:model_sources", body.model_id, json.dumps(source_info))

    if body.hf_repo:
        await redis.hset("hwarang:model_hf_repos", body.model_id, body.hf_repo)

    await redis.close()

    return {
        "status": "registered",
        "model_id": body.model_id,
        "source": source_info,
    }


# ============================================================
# 모델 배포 (학습 완료 → 서브 서버 자동 업데이트)
# ============================================================

class DeployModelRequest(BaseModel):
    model_id: str
    version: str
    source_path: str
    source_host: str = ""


class RollbackRequest(BaseModel):
    model_id: str


@router.post("/models/deploy")
async def deploy_model(body: DeployModelRequest, request: Request):
    """학습 완료 → 모든 서브 서버에 무중단 배포.

    예시:
      curl -X POST http://마스터:8000/admin/models/deploy \\
        -H "Content-Type: application/json" \\
        -d '{"model_id":"hwarang-code-30b","version":"v2.1",
             "source_path":"/mnt/nvme2/hwarang/models/hwarang-code-30b-v2.1",
             "source_host":"192.168.1.100"}'
    """
    from hwarang_api.distributed.model_deploy import DeploymentManager, DeploymentEvent

    settings = request.app.state.settings
    manager = DeploymentManager(settings.redis_url)
    event = DeploymentEvent(
        model_id=body.model_id, version=body.version,
        source_type="rsync", source_host=body.source_host, source_path=body.source_path,
    )
    return await manager.deploy(event)


@router.get("/models/deploy/status")
async def deploy_status(request: Request, model_id: str = ""):
    """배포 상태 확인."""
    from hwarang_api.distributed.model_deploy import DeploymentManager
    settings = request.app.state.settings
    manager = DeploymentManager(settings.redis_url)
    return await manager.get_deploy_status(model_id or None)


@router.post("/models/rollback")
async def rollback_model(body: RollbackRequest, request: Request):
    """이전 버전으로 롤백."""
    from hwarang_api.distributed.model_deploy import DeploymentManager
    settings = request.app.state.settings
    manager = DeploymentManager(settings.redis_url)
    return await manager.rollback(body.model_id)


@router.get("/models/sources")
async def list_model_sources(request: Request):
    """등록된 모델 소스 목록."""
    import json
    import redis.asyncio as aioredis

    settings = request.app.state.settings
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    sources = await redis.hgetall("hwarang:model_sources")
    hf_repos = await redis.hgetall("hwarang:model_hf_repos")
    await redis.close()

    result = {}
    for model_id, raw in sources.items():
        info = json.loads(raw)
        info["hf_repo"] = hf_repos.get(model_id, "")
        result[model_id] = info

    return {"model_sources": result}
