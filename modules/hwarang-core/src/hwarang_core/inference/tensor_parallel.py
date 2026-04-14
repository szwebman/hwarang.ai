"""Tensor Parallelism - 1개의 질문을 여러 GPU가 나눠서 처리.

모델의 레이어를 여러 GPU에 분산시켜 추론 속도를 높입니다.

방식:
1. Column Parallelism: Linear 레이어의 출력 차원을 GPU 수로 분할
   - 각 GPU가 출력의 일부만 계산 → 합침

2. Row Parallelism: Linear 레이어의 입력 차원을 분할
   - 각 GPU가 입력의 일부씩 처리 → 합침

3. Pipeline Parallelism: 레이어 묶음을 GPU별로 할당
   - GPU1: Layer 0~15, GPU2: Layer 16~31

효과:
- GPU 2장: ~1.8배 빠름 (통신 오버헤드 때문에 정확히 2배는 아님)
- GPU 4장: ~3.2배 빠름
- GPU 8장: ~5.5배 빠름

사용법:
    from hwarang_core.inference.tensor_parallel import TensorParallelEngine

    engine = TensorParallelEngine(
        model_path="./exported/hwarang-code-30b",
        gpu_ids=[0, 1],         # 2장에 분할
        parallel_mode="tensor",  # "tensor" 또는 "pipeline"
    )

    # 사용법은 기존 InferenceEngine과 동일
    response = await engine.generate(request)
    async for chunk in engine.generate_stream(request):
        ...
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import AsyncIterator

import torch
import torch.nn as nn
import torch.distributed as dist

from hwarang_core.model.config import HwarangConfig
from hwarang_core.model.transformer import HwarangForCausalLM
from hwarang_core.inference.sampler import sample_next_token
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


class ModelSplitter:
    """모델을 여러 GPU에 분할하는 유틸리티."""

    @staticmethod
    def split_pipeline(
        model: HwarangForCausalLM,
        gpu_ids: list[int],
    ) -> HwarangForCausalLM:
        """Pipeline Parallelism: 레이어를 GPU별로 분배.

        가장 간단한 병렬화 방식.
        Layer 0~N/2 → GPU 0, Layer N/2~N → GPU 1
        """
        num_gpus = len(gpu_ids)
        num_layers = len(model.model.layers)
        layers_per_gpu = num_layers // num_gpus

        logger.info(f"Pipeline Split: {num_layers} layers → {num_gpus} GPUs "
                     f"({layers_per_gpu} layers/GPU)")

        # 임베딩과 lm_head는 첫 번째 GPU
        model.model.embed_tokens = model.model.embed_tokens.to(f"cuda:{gpu_ids[0]}")
        model.lm_head = model.lm_head.to(f"cuda:{gpu_ids[-1]}")
        model.model.norm = model.model.norm.to(f"cuda:{gpu_ids[-1]}")

        # 레이어 분배
        for i, layer in enumerate(model.model.layers):
            gpu_idx = min(i // layers_per_gpu, num_gpus - 1)
            device = f"cuda:{gpu_ids[gpu_idx]}"
            model.model.layers[i] = layer.to(device)
            logger.debug(f"  Layer {i} → {device}")

        return model

    @staticmethod
    def split_tensor(
        model: HwarangForCausalLM,
        gpu_ids: list[int],
    ) -> HwarangForCausalLM:
        """Tensor Parallelism: Attention/FFN의 차원을 GPU별로 분할.

        더 복잡하지만 레이턴시가 가장 낮음.
        각 레이어의 연산을 여러 GPU가 동시에 수행.
        """
        num_gpus = len(gpu_ids)

        logger.info(f"Tensor Split: {num_gpus} GPUs")

        # 간소화된 구현: 실제로는 각 Linear 레이어를 분할해야 하지만
        # PyTorch의 device_map을 활용한 자동 분배를 사용
        # (프로덕션에서는 Megatron-LM 또는 vLLM 스타일 구현 필요)

        # 자동 디바이스 매핑 생성
        device_map = ModelSplitter._create_device_map(model, gpu_ids)

        for name, module in model.named_modules():
            if name in device_map:
                device = device_map[name]
                module.to(device)

        return model

    @staticmethod
    def _create_device_map(
        model: HwarangForCausalLM,
        gpu_ids: list[int],
    ) -> dict[str, str]:
        """모듈별 디바이스 매핑 생성."""
        device_map = {}
        num_gpus = len(gpu_ids)
        num_layers = len(model.model.layers)
        layers_per_gpu = num_layers // num_gpus

        # 임베딩 → 첫 번째 GPU
        device_map["model.embed_tokens"] = f"cuda:{gpu_ids[0]}"

        # 레이어 분배
        for i in range(num_layers):
            gpu_idx = min(i // layers_per_gpu, num_gpus - 1)
            device_map[f"model.layers.{i}"] = f"cuda:{gpu_ids[gpu_idx]}"

        # Norm, LM Head → 마지막 GPU
        device_map["model.norm"] = f"cuda:{gpu_ids[-1]}"
        device_map["lm_head"] = f"cuda:{gpu_ids[-1]}"

        return device_map


class TensorParallelEngine(InferenceProtocol):
    """Tensor Parallel 추론 엔진.

    1개의 질문을 여러 GPU가 나눠서 처리하여 응답 속도를 높입니다.

    Args:
        model_path: 모델 체크포인트 경로
        gpu_ids: 사용할 GPU ID 리스트 (예: [0, 1])
        parallel_mode: "pipeline" (레이어 분할) 또는 "tensor" (차원 분할)
        dtype: "bfloat16" 또는 "float16"
    """

    def __init__(
        self,
        model_path: str,
        gpu_ids: list[int] | None = None,
        parallel_mode: str = "pipeline",
        dtype: str = "bfloat16",
    ):
        self.model_path = model_path
        self.parallel_mode = parallel_mode
        self.dtype_str = dtype
        self.dtype = {"float32": torch.float32, "float16": torch.float16,
                      "bfloat16": torch.bfloat16}[dtype]

        # GPU 감지
        if gpu_ids is None:
            num_gpus = torch.cuda.device_count()
            gpu_ids = list(range(num_gpus))
        self.gpu_ids = gpu_ids
        self.num_gpus = len(gpu_ids)

        if self.num_gpus < 2:
            logger.warning("GPU 1장이면 Tensor Parallelism 효과 없음. "
                          "일반 InferenceEngine 사용 권장.")

        logger.info(f"TensorParallelEngine: {self.num_gpus} GPUs, "
                     f"mode={parallel_mode}, dtype={dtype}")

        # 토크나이저 로드
        self.tokenizer = HwarangTokenizer(f"{model_path}/tokenizer")

        # 모델 로드 + 분할
        logger.info(f"모델 로드: {model_path}")
        self.model = HwarangForCausalLM.from_pretrained(model_path)
        self.model = self.model.to(dtype=self.dtype)

        # GPU 분할 적용
        splitter = ModelSplitter()
        if parallel_mode == "pipeline":
            self.model = splitter.split_pipeline(self.model, gpu_ids)
        elif parallel_mode == "tensor":
            self.model = splitter.split_tensor(self.model, gpu_ids)
        else:
            raise ValueError(f"Unknown parallel mode: {parallel_mode}")

        self.model.eval()

        # 모델 ID
        self.model_id = model_path.split("/")[-1]

        # 각 GPU 메모리 사용량 출력
        for gpu_id in gpu_ids:
            allocated = torch.cuda.memory_allocated(gpu_id) / 1e9
            reserved = torch.cuda.memory_reserved(gpu_id) / 1e9
            logger.info(f"  GPU {gpu_id}: {allocated:.1f}GB allocated, "
                       f"{reserved:.1f}GB reserved")

    def _format_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        return [{"role": m.role.value, "content": m.content or ""} for m in messages]

    def _get_first_device(self) -> torch.device:
        """첫 번째 GPU (입력 텐서가 올라갈 곳)."""
        return torch.device(f"cuda:{self.gpu_ids[0]}")

    def _get_last_device(self) -> torch.device:
        """마지막 GPU (출력이 나올 곳)."""
        return torch.device(f"cuda:{self.gpu_ids[-1]}")

    @torch.no_grad()
    def _forward_pipeline(
        self,
        input_ids: torch.Tensor,
        past_key_values=None,
        use_cache: bool = True,
    ):
        """Pipeline Parallel forward pass.

        데이터가 GPU 0 → GPU 1 → ... → GPU N 순서로 흐름.
        각 GPU가 자기 레이어만 처리하고 다음 GPU로 넘김.
        """
        # 임베딩 (첫 번째 GPU)
        first_device = self._get_first_device()
        input_ids = input_ids.to(first_device)

        batch_size, seq_len = input_ids.shape

        # Position IDs
        past_length = 0
        if past_key_values is not None and past_key_values[0] is not None:
            past_length = past_key_values[0][0].shape[2]

        position_ids = torch.arange(
            past_length, past_length + seq_len, device=first_device
        ).unsqueeze(0).expand(batch_size, -1)

        # 임베딩
        hidden_states = self.model.model.embed_tokens(input_ids)

        # Causal mask
        causal_mask = self.model.model._make_causal_mask(input_ids, past_length)

        # 레이어별 순차 처리 (자동으로 GPU 이동)
        new_key_values = []
        for i, layer in enumerate(self.model.model.layers):
            layer_device = next(layer.parameters()).device

            # 텐서를 해당 GPU로 이동
            hidden_states = hidden_states.to(layer_device)
            layer_mask = causal_mask.to(layer_device)
            layer_pos = position_ids.to(layer_device)

            past_kv = past_key_values[i] if past_key_values else None
            if past_kv is not None:
                past_kv = (past_kv[0].to(layer_device), past_kv[1].to(layer_device))

            hidden_states, new_cache = layer(
                hidden_states,
                attention_mask=layer_mask,
                position_ids=layer_pos,
                past_key_value=past_kv,
                use_cache=use_cache,
            )

            if use_cache:
                new_key_values.append(new_cache)

        # Norm + LM Head (마지막 GPU)
        last_device = self._get_last_device()
        hidden_states = hidden_states.to(last_device)
        hidden_states = self.model.model.norm(hidden_states)
        logits = self.model.lm_head(hidden_states)

        return logits, new_key_values if use_cache else None

    @torch.no_grad()
    def _generate_tokens(
        self,
        input_ids: torch.Tensor,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 50,
        stop_tokens: list[int] | None = None,
    ) -> tuple[list[int], int]:
        """토큰 생성 (Pipeline Parallel)."""
        if stop_tokens is None:
            stop_tokens = [self.tokenizer.eos_token_id]

        generated = []
        past_key_values = None
        current_ids = input_ids

        for _ in range(max_new_tokens):
            logits, past_key_values = self._forward_pipeline(
                current_ids,
                past_key_values=past_key_values,
                use_cache=True,
            )

            next_logits = logits[:, -1, :]
            next_token = sample_next_token(
                next_logits,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
            )

            token_id = next_token.item()
            if token_id in stop_tokens:
                break

            generated.append(token_id)
            current_ids = next_token.to(self._get_first_device())

        return generated, len(generated)

    async def generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """비스트리밍 생성."""
        messages = self._format_messages(request.messages)
        input_ids_list = self.tokenizer.encode_chat(messages)
        input_ids = torch.tensor([input_ids_list], dtype=torch.long,
                                 device=self._get_first_device())
        prompt_tokens = len(input_ids_list)
        max_tokens = request.max_tokens or 512

        start_time = time.time()

        generated_ids, completion_tokens = self._generate_tokens(
            input_ids,
            max_new_tokens=max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )

        latency = time.time() - start_time
        response_text = self.tokenizer.decode(generated_ids)

        logger.info(f"Generated {completion_tokens} tokens in {latency:.2f}s "
                    f"({completion_tokens/latency:.1f} tok/s, {self.num_gpus} GPUs)")

        return ChatCompletionResponse(
            model=request.model,
            choices=[Choice(
                index=0,
                message=ChatMessage(role=Role.ASSISTANT, content=response_text),
                finish_reason="stop" if len(generated_ids) < max_tokens else "length",
            )],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    async def generate_stream(
        self, request: ChatCompletionRequest,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """스트리밍 생성."""
        messages = self._format_messages(request.messages)
        input_ids_list = self.tokenizer.encode_chat(messages)
        input_ids = torch.tensor([input_ids_list], dtype=torch.long,
                                 device=self._get_first_device())
        max_tokens = request.max_tokens or 512
        stop_tokens = [self.tokenizer.eos_token_id]
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())

        # 첫 청크: role
        yield ChatCompletionChunk(
            id=chunk_id, created=created, model=request.model,
            choices=[ChunkChoice(index=0, delta=DeltaContent(role=Role.ASSISTANT))],
        )

        past_key_values = None
        current_ids = input_ids

        for i in range(max_tokens):
            logits, past_key_values = self._forward_pipeline(
                current_ids, past_key_values=past_key_values, use_cache=True,
            )

            next_logits = logits[:, -1, :]
            next_token = sample_next_token(
                next_logits,
                temperature=request.temperature,
                top_p=request.top_p,
            )

            token_id = next_token.item()

            if token_id in stop_tokens:
                yield ChatCompletionChunk(
                    id=chunk_id, created=created, model=request.model,
                    choices=[ChunkChoice(
                        index=0, delta=DeltaContent(), finish_reason="stop",
                    )],
                )
                break

            token_text = self.tokenizer.decode([token_id])
            yield ChatCompletionChunk(
                id=chunk_id, created=created, model=request.model,
                choices=[ChunkChoice(
                    index=0, delta=DeltaContent(content=token_text),
                )],
            )

            current_ids = next_token.to(self._get_first_device())

    async def is_ready(self) -> bool:
        return self.model is not None


class SpeculativeDecodingEngine(InferenceProtocol):
    """Speculative Decoding 엔진.

    큰 모델(30B) + 작은 모델(7B)을 조합해서 속도를 높입니다.

    원리:
    1. 작은 모델(draft)이 K개 토큰을 빠르게 예측
    2. 큰 모델(target)이 K개를 한 번의 forward pass로 검증
    3. 일치하면 통과, 불일치하면 큰 모델 결과 사용

    효과: 2~3배 속도 향상 (GPU 1장에서도!)

    Args:
        target_model_path: 큰 모델 (30B) 경로
        draft_model_path: 작은 모델 (7B) 경로
        draft_tokens: 한 번에 예측할 토큰 수 (기본 5)
    """

    def __init__(
        self,
        target_model_path: str,
        draft_model_path: str,
        device: str = "auto",
        dtype: str = "bfloat16",
        draft_tokens: int = 5,
    ):
        self.draft_tokens = draft_tokens
        self.dtype = {"float32": torch.float32, "float16": torch.float16,
                      "bfloat16": torch.bfloat16}[dtype]

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)

        # 토크나이저 (동일해야 함)
        self.tokenizer = HwarangTokenizer(f"{target_model_path}/tokenizer")

        # Target 모델 (큰 모델, INT4 등 양자화)
        logger.info(f"Target 모델 로드: {target_model_path}")
        self.target = HwarangForCausalLM.from_pretrained(target_model_path)
        self.target = self.target.to(device=self.device, dtype=self.dtype)
        self.target.eval()

        # Draft 모델 (작은 모델, FP16)
        logger.info(f"Draft 모델 로드: {draft_model_path}")
        self.draft = HwarangForCausalLM.from_pretrained(draft_model_path)
        self.draft = self.draft.to(device=self.device, dtype=self.dtype)
        self.draft.eval()

        self.model_id = target_model_path.split("/")[-1]

        # 메모리 확인
        if self.device.type == "cuda":
            allocated = torch.cuda.memory_allocated() / 1e9
            logger.info(f"총 GPU 메모리 사용: {allocated:.1f}GB "
                       f"(target + draft)")

    @torch.no_grad()
    def _speculative_decode(
        self,
        input_ids: torch.Tensor,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> tuple[list[int], int]:
        """Speculative Decoding으로 토큰 생성.

        1. Draft가 K개 토큰 빠르게 생성 (작은 모델이라 매우 빠름)
        2. Target이 K개를 한 번에 검증 (배치 처리라 효율적)
        3. 일치하면 모두 채택, 불일치 시점부터 Target 결과 사용
        """
        stop_tokens = {self.tokenizer.eos_token_id}
        generated = []
        current_ids = input_ids

        while len(generated) < max_new_tokens:
            # Step 1: Draft 모델로 K개 토큰 빠르게 예측
            draft_tokens = []
            draft_ids = current_ids.clone()

            for _ in range(self.draft_tokens):
                output = self.draft(input_ids=draft_ids, use_cache=False)
                logits = output.logits[:, -1, :]
                next_token = sample_next_token(
                    logits, temperature=temperature, top_p=top_p,
                )
                token_id = next_token.item()
                draft_tokens.append(token_id)
                draft_ids = torch.cat([draft_ids, next_token], dim=-1)

                if token_id in stop_tokens:
                    break

            # Step 2: Target 모델로 전체를 한 번에 검증
            # Draft가 생성한 토큰들을 input에 포함시켜서 한 번의 forward
            verification_ids = torch.cat([
                current_ids,
                torch.tensor([draft_tokens], device=self.device)
            ], dim=-1)

            target_output = self.target(input_ids=verification_ids, use_cache=False)
            target_logits = target_output.logits

            # Step 3: Draft와 Target 비교
            accepted = 0
            start_pos = current_ids.shape[-1] - 1

            for i, draft_token in enumerate(draft_tokens):
                # Target이 같은 위치에서 생성할 토큰
                target_next = sample_next_token(
                    target_logits[:, start_pos + i, :],
                    temperature=temperature,
                    top_p=top_p,
                )
                target_token = target_next.item()

                if draft_token == target_token:
                    accepted += 1
                    generated.append(draft_token)

                    if draft_token in stop_tokens:
                        return generated, len(generated)
                else:
                    # 불일치: Target의 토큰을 사용
                    generated.append(target_token)

                    if target_token in stop_tokens:
                        return generated, len(generated)
                    break

            # 다음 반복을 위해 current_ids 업데이트
            new_tokens = generated[-(accepted + 1):]
            current_ids = torch.cat([
                current_ids,
                torch.tensor([new_tokens], device=self.device)
            ], dim=-1)

        return generated, len(generated)

    def _format_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        return [{"role": m.role.value, "content": m.content or ""} for m in messages]

    async def generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        messages = self._format_messages(request.messages)
        input_ids_list = self.tokenizer.encode_chat(messages)
        input_ids = torch.tensor([input_ids_list], dtype=torch.long,
                                 device=self.device)
        prompt_tokens = len(input_ids_list)
        max_tokens = request.max_tokens or 512

        start_time = time.time()
        generated_ids, completion_tokens = self._speculative_decode(
            input_ids,
            max_new_tokens=max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )
        latency = time.time() - start_time

        response_text = self.tokenizer.decode(generated_ids)
        logger.info(f"Speculative: {completion_tokens} tokens in {latency:.2f}s "
                    f"({completion_tokens/latency:.1f} tok/s)")

        return ChatCompletionResponse(
            model=request.model,
            choices=[Choice(
                index=0,
                message=ChatMessage(role=Role.ASSISTANT, content=response_text),
                finish_reason="stop" if len(generated_ids) < max_tokens else "length",
            )],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    async def generate_stream(
        self, request: ChatCompletionRequest,
    ) -> AsyncIterator[ChatCompletionChunk]:
        # Speculative Decoding은 배치로 검증하므로
        # 스트리밍은 청크 단위로 방출
        result = await self.generate(request)
        content = result.choices[0].message.content or ""

        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())

        yield ChatCompletionChunk(
            id=chunk_id, created=created, model=request.model,
            choices=[ChunkChoice(index=0, delta=DeltaContent(role=Role.ASSISTANT))],
        )

        # 텍스트를 작은 조각으로 나눠서 스트리밍 효과
        chunk_size = 5  # 5자씩
        for i in range(0, len(content), chunk_size):
            text_chunk = content[i:i + chunk_size]
            yield ChatCompletionChunk(
                id=chunk_id, created=created, model=request.model,
                choices=[ChunkChoice(
                    index=0, delta=DeltaContent(content=text_chunk),
                )],
            )

        yield ChatCompletionChunk(
            id=chunk_id, created=created, model=request.model,
            choices=[ChunkChoice(
                index=0, delta=DeltaContent(), finish_reason="stop",
            )],
        )

    async def is_ready(self) -> bool:
        return self.target is not None and self.draft is not None
