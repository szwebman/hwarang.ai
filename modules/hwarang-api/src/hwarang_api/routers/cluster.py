"""Cluster management endpoints for distributed mode."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/cluster/status")
async def cluster_status(request: Request):
    """Get the status of all worker nodes in the cluster."""
    lb = getattr(request.app.state, "load_balancer", None)
    if not lb:
        return {"mode": "local", "distributed": False, "message": "Running in local mode (single server)"}

    status = await lb.get_cluster_status()
    status["mode"] = "distributed"
    status["distributed"] = True
    return status


@router.get("/cluster/workers")
async def list_workers(request: Request):
    """List all registered worker nodes."""
    lb = getattr(request.app.state, "load_balancer", None)
    if not lb:
        raise HTTPException(status_code=400, detail="Not running in distributed mode")

    workers = await lb.get_workers()
    return {
        "count": len(workers),
        "workers": [w.model_dump() for w in workers],
    }


@router.get("/cluster/models")
async def cluster_models(request: Request):
    """List models available across the cluster."""
    lb = getattr(request.app.state, "load_balancer", None)
    if not lb:
        raise HTTPException(status_code=400, detail="Not running in distributed mode")

    workers = await lb.get_workers()
    models: dict[str, list[str]] = {}
    for w in workers:
        for m in w.models:
            if m not in models:
                models[m] = []
            models[m].append(w.worker_id)

    return {
        "models": [
            {"model_id": m, "worker_count": len(ws), "workers": ws}
            for m, ws in models.items()
        ]
    }
