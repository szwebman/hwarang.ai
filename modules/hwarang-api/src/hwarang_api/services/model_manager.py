"""Model lifecycle management."""

from __future__ import annotations

import asyncio
import logging

from hwarang_core.inference.engine import InferenceEngine
from hwarang_shared.schemas.models import ModelInfo

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages loading, unloading, and accessing inference engines."""

    def __init__(self):
        self._engines: dict[str, InferenceEngine] = {}
        self._lock = asyncio.Lock()

    async def load_model(
        self,
        model_id: str,
        model_path: str,
        device: str = "auto",
        dtype: str = "bfloat16",
    ) -> ModelInfo:
        """Load a model into memory."""
        async with self._lock:
            if model_id in self._engines:
                logger.info(f"Model {model_id} already loaded")
                return self._get_model_info(model_id)

            engine = InferenceEngine(
                model_path=model_path,
                device=device,
                dtype=dtype,
            )
            self._engines[model_id] = engine
            logger.info(f"Model {model_id} loaded from {model_path}")
            return self._get_model_info(model_id)

    async def unload_model(self, model_id: str) -> None:
        """Unload a model from memory."""
        async with self._lock:
            if model_id not in self._engines:
                raise KeyError(f"Model {model_id} not found")
            del self._engines[model_id]
            # Free GPU memory
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            logger.info(f"Model {model_id} unloaded")

    async def unload_all(self) -> None:
        """Unload all models."""
        async with self._lock:
            self._engines.clear()

    def get_engine(self, model_id: str) -> InferenceEngine:
        """Get an inference engine by model ID."""
        if model_id not in self._engines:
            raise KeyError(f"Model '{model_id}' not loaded. Available: {list(self._engines.keys())}")
        return self._engines[model_id]

    def list_models(self) -> list[ModelInfo]:
        """List all loaded models."""
        return [self._get_model_info(mid) for mid in self._engines]

    def _get_model_info(self, model_id: str) -> ModelInfo:
        engine = self._engines[model_id]
        return ModelInfo(
            id=model_id,
            max_context_length=engine.model.config.max_position_embeddings,
        )

    @property
    def num_loaded(self) -> int:
        return len(self._engines)
