"""Inference engine for serving Hwarang models."""

from __future__ import annotations

import logging
import time
import uuid
from typing import AsyncIterator

import torch

from hwarang_core.inference.sampler import sample_next_token
from hwarang_core.model.config import HwarangConfig
from hwarang_core.model.transformer import HwarangForCausalLM
from hwarang_core.tokenizer.tokenizer import HwarangTokenizer
from hwarang_shared.protocols.inference import InferenceProtocol
from hwarang_shared.schemas.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ChunkChoice,
    DeltaContent,
    Role,
    Usage,
)

logger = logging.getLogger(__name__)


class InferenceEngine(InferenceProtocol):
    """Main inference engine for Hwarang models.

    Handles model loading, tokenization, generation, and response formatting.
    """

    def __init__(
        self,
        model_path: str,
        device: str = "auto",
        dtype: str = "bfloat16",
    ):
        self.model_path = model_path
        self.device = self._resolve_device(device)
        self.dtype = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}[dtype]

        logger.info(f"Loading model from {model_path} on {self.device} ({dtype})")

        # Load tokenizer
        self.tokenizer = HwarangTokenizer(f"{model_path}/tokenizer")

        # Load model
        self.model = HwarangForCausalLM.from_pretrained(model_path)
        self.model = self.model.to(device=self.device, dtype=self.dtype)
        self.model.eval()

        self.model_id = model_path.split("/")[-1]
        logger.info(f"Model loaded: {self.model_id} ({self.model.num_parameters():,} params)")

    @staticmethod
    def _resolve_device(device: str) -> torch.device:
        if device == "auto":
            if torch.cuda.is_available():
                return torch.device("cuda")
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return torch.device("mps")
            return torch.device("cpu")
        return torch.device(device)

    def _format_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        """Convert ChatMessage objects to dicts for tokenizer."""
        return [{"role": m.role.value, "content": m.content or ""} for m in messages]

    @torch.no_grad()
    def _generate(
        self,
        input_ids: torch.Tensor,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 50,
        stop_tokens: list[int] | None = None,
    ) -> tuple[list[int], int]:
        """Generate tokens autoregressively.

        Returns:
            Tuple of (generated token IDs, number of tokens generated)
        """
        if stop_tokens is None:
            stop_tokens = [self.tokenizer.eos_token_id]

        generated: list[int] = []
        past_key_values = None
        current_ids = input_ids

        for _ in range(max_new_tokens):
            with torch.amp.autocast(device_type=self.device.type, dtype=self.dtype):
                output = self.model(
                    input_ids=current_ids,
                    past_key_values=past_key_values,
                    use_cache=True,
                )

            logits = output.logits[:, -1, :]  # (batch=1, vocab)
            past_key_values = output.past_key_values

            # Sample next token
            next_token = sample_next_token(
                logits,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                input_ids=input_ids if len(generated) > 0 else None,
            )

            token_id = next_token.item()

            if token_id in stop_tokens:
                break

            generated.append(token_id)
            current_ids = next_token

        return generated, len(generated)

    async def generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Generate a complete response."""
        messages = self._format_messages(request.messages)
        input_ids_list = self.tokenizer.encode_chat(messages)
        input_ids = torch.tensor([input_ids_list], dtype=torch.long, device=self.device)
        prompt_tokens = len(input_ids_list)

        max_tokens = request.max_tokens or 512

        generated_ids, completion_tokens = self._generate(
            input_ids,
            max_new_tokens=max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )

        response_text = self.tokenizer.decode(generated_ids)

        return ChatCompletionResponse(
            model=request.model,
            choices=[
                Choice(
                    index=0,
                    message=ChatMessage(role=Role.ASSISTANT, content=response_text),
                    finish_reason="stop" if len(generated_ids) < max_tokens else "length",
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    async def generate_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Generate a streaming response, yielding chunks."""
        messages = self._format_messages(request.messages)
        input_ids_list = self.tokenizer.encode_chat(messages)
        input_ids = torch.tensor([input_ids_list], dtype=torch.long, device=self.device)

        max_tokens = request.max_tokens or 512
        stop_tokens = [self.tokenizer.eos_token_id]
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())

        # First chunk: role
        yield ChatCompletionChunk(
            id=chunk_id,
            created=created,
            model=request.model,
            choices=[
                ChunkChoice(
                    index=0,
                    delta=DeltaContent(role=Role.ASSISTANT),
                )
            ],
        )

        past_key_values = None
        current_ids = input_ids

        for i in range(max_tokens):
            with torch.amp.autocast(device_type=self.device.type, dtype=self.dtype):
                output = self.model(
                    input_ids=current_ids,
                    past_key_values=past_key_values,
                    use_cache=True,
                )

            logits = output.logits[:, -1, :]
            past_key_values = output.past_key_values

            next_token = sample_next_token(
                logits,
                temperature=request.temperature,
                top_p=request.top_p,
            )

            token_id = next_token.item()

            if token_id in stop_tokens:
                yield ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=request.model,
                    choices=[
                        ChunkChoice(
                            index=0,
                            delta=DeltaContent(),
                            finish_reason="stop",
                        )
                    ],
                )
                break

            token_text = self.tokenizer.decode([token_id])

            yield ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=request.model,
                choices=[
                    ChunkChoice(
                        index=0,
                        delta=DeltaContent(content=token_text),
                    )
                ],
            )

            current_ids = next_token

    async def is_ready(self) -> bool:
        """Check if the engine is ready."""
        return self.model is not None
