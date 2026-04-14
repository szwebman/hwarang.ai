"""Protocol definitions for inter-server communication.

All messages between API server and Worker nodes use this protocol.
Serialized as JSON over Redis streams.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# Redis key constants
WORKER_REGISTRY = "hwarang:workers"
WORKER_TIMEOUT = 15  # seconds before a worker is considered dead


class WorkerStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    DRAINING = "draining"  # Finishing current work, not accepting new
    OFFLINE = "offline"


class WorkerInfo(BaseModel):
    """Registration info from a worker node."""

    worker_id: str
    host: str
    port: int
    models: list[str]  # Loaded model IDs
    gpu_count: int = 0
    gpu_memory_mb: int = 0
    max_batch_size: int = 8
    status: WorkerStatus = WorkerStatus.IDLE
    registered_at: float = Field(default_factory=time.time)
    last_heartbeat: float = Field(default_factory=time.time)


class InferenceRequest(BaseModel):
    """A request sent from API server to worker."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    model: str
    messages: list[dict[str, str]]
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 512
    stream: bool = False
    created_at: float = Field(default_factory=time.time)
    # Routing metadata
    priority: int = 0  # Higher = more urgent
    timeout_ms: int = 30_000


class InferenceResponse(BaseModel):
    """A response sent from worker back to API server."""

    request_id: str
    worker_id: str
    content: str | None = None
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


class StreamChunk(BaseModel):
    """A streaming chunk sent from worker to API server."""

    request_id: str
    worker_id: str
    content: str  # Partial text
    finish_reason: str | None = None  # None = more chunks coming
    index: int = 0  # Chunk sequence number
