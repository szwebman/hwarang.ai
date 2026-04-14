"""Hwarang Transformer Model.

Decoder-only transformer with GQA, RoPE, RMSNorm, and SwiGLU.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

from hwarang_core.model.attention import GroupedQueryAttention
from hwarang_core.model.config import HwarangConfig
from hwarang_core.model.embeddings import HwarangEmbeddings
from hwarang_core.model.layers import RMSNorm, SwiGLUFFN


@dataclass
class CausalLMOutput:
    """Output of the causal language model."""

    logits: torch.Tensor
    loss: torch.Tensor | None = None
    past_key_values: list[tuple[torch.Tensor, torch.Tensor]] | None = None
    hidden_states: torch.Tensor | None = None


class HwarangDecoderLayer(nn.Module):
    """Single transformer decoder layer."""

    def __init__(self, config: HwarangConfig):
        super().__init__()
        self.self_attn = GroupedQueryAttention(
            hidden_size=config.hidden_size,
            num_attention_heads=config.num_attention_heads,
            num_key_value_heads=config.num_key_value_heads,
            head_dim=config.head_dim,
            max_position_embeddings=config.max_position_embeddings,
            rope_theta=config.rope_theta,
            attention_dropout=config.attention_dropout,
        )
        self.mlp = SwiGLUFFN(
            hidden_size=config.hidden_size,
            intermediate_size=config.intermediate_size,
            dropout=config.hidden_dropout,
        )
        self.input_layernorm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.post_attention_layernorm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
        position_ids: torch.Tensor | None = None,
        past_key_value: tuple[torch.Tensor, torch.Tensor] | None = None,
        use_cache: bool = False,
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor] | None]:
        # Self-attention with pre-norm
        residual = hidden_states
        hidden_states = self.input_layernorm(hidden_states)
        hidden_states, new_cache = self.self_attn(
            hidden_states,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_value=past_key_value,
            use_cache=use_cache,
        )
        hidden_states = residual + hidden_states

        # FFN with pre-norm
        residual = hidden_states
        hidden_states = self.post_attention_layernorm(hidden_states)
        hidden_states = self.mlp(hidden_states)
        hidden_states = residual + hidden_states

        return hidden_states, new_cache


class HwarangModel(nn.Module):
    """Hwarang base transformer model (without LM head)."""

    def __init__(self, config: HwarangConfig):
        super().__init__()
        self.config = config
        self.embed_tokens = HwarangEmbeddings(
            config.vocab_size, config.hidden_size, config.pad_token_id
        )
        self.layers = nn.ModuleList(
            [HwarangDecoderLayer(config) for _ in range(config.num_hidden_layers)]
        )
        self.norm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)

        # Initialize weights
        self.apply(self._init_weights)

    def _init_weights(self, module: nn.Module) -> None:
        std = self.config.initializer_range
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=std)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=std)
            if module.padding_idx is not None:
                module.weight.data[module.padding_idx].zero_()

    def _make_causal_mask(
        self,
        input_ids: torch.Tensor,
        past_key_values_length: int = 0,
    ) -> torch.Tensor:
        """Create causal attention mask."""
        batch_size, seq_len = input_ids.shape
        total_len = seq_len + past_key_values_length

        # Create causal mask: 0 for allowed, -inf for masked
        mask = torch.full(
            (seq_len, total_len), float("-inf"), device=input_ids.device, dtype=torch.float32
        )
        mask = torch.triu(mask, diagonal=past_key_values_length + 1)

        # Expand for batch and heads: (1, 1, seq_len, total_len)
        return mask.unsqueeze(0).unsqueeze(0)

    def forward(
        self,
        input_ids: torch.LongTensor,
        attention_mask: torch.Tensor | None = None,
        position_ids: torch.LongTensor | None = None,
        past_key_values: list[tuple[torch.Tensor, torch.Tensor]] | None = None,
        use_cache: bool = False,
    ) -> tuple[torch.Tensor, list[tuple[torch.Tensor, torch.Tensor]] | None]:
        batch_size, seq_len = input_ids.shape

        # Compute past length for KV cache
        past_length = 0
        if past_key_values is not None and past_key_values[0] is not None:
            past_length = past_key_values[0][0].shape[2]

        # Position IDs
        if position_ids is None:
            position_ids = torch.arange(
                past_length, past_length + seq_len, device=input_ids.device
            ).unsqueeze(0).expand(batch_size, -1)

        # Causal mask
        causal_mask = self._make_causal_mask(input_ids, past_length)

        # If external attention mask provided (padding mask), combine
        if attention_mask is not None:
            # attention_mask: (batch, total_seq_len) with 1 for valid, 0 for padding
            padding_mask = (1 - attention_mask[:, None, None, :].float()) * float("-inf")
            causal_mask = causal_mask + padding_mask

        # Token embeddings
        hidden_states = self.embed_tokens(input_ids)

        # Decoder layers
        new_key_values: list[tuple[torch.Tensor, torch.Tensor]] = []
        for i, layer in enumerate(self.layers):
            past_kv = past_key_values[i] if past_key_values is not None else None
            hidden_states, new_cache = layer(
                hidden_states,
                attention_mask=causal_mask,
                position_ids=position_ids,
                past_key_value=past_kv,
                use_cache=use_cache,
            )
            if use_cache:
                new_key_values.append(new_cache)

        hidden_states = self.norm(hidden_states)

        return hidden_states, new_key_values if use_cache else None

    def num_parameters(self, trainable_only: bool = True) -> int:
        """Count model parameters."""
        if trainable_only:
            return sum(p.numel() for p in self.parameters() if p.requires_grad)
        return sum(p.numel() for p in self.parameters())


class HwarangForCausalLM(nn.Module):
    """Hwarang model with causal language modeling head."""

    def __init__(self, config: HwarangConfig):
        super().__init__()
        self.config = config
        self.model = HwarangModel(config)
        self.lm_head = nn.Linear(config.hidden_size, config.vocab_size, bias=False)

        # Tie embeddings
        if config.tie_word_embeddings:
            self.lm_head.weight = self.model.embed_tokens.token_embedding.weight

    def forward(
        self,
        input_ids: torch.LongTensor,
        attention_mask: torch.Tensor | None = None,
        position_ids: torch.LongTensor | None = None,
        past_key_values: list[tuple[torch.Tensor, torch.Tensor]] | None = None,
        labels: torch.LongTensor | None = None,
        use_cache: bool = False,
    ) -> CausalLMOutput:
        hidden_states, new_key_values = self.model(
            input_ids,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_values=past_key_values,
            use_cache=use_cache,
        )

        logits = self.lm_head(hidden_states)

        loss = None
        if labels is not None:
            # Shift for next-token prediction
            shift_logits = logits[..., :-1, :].contiguous()
            shift_labels = labels[..., 1:].contiguous()
            loss = F.cross_entropy(
                shift_logits.view(-1, self.config.vocab_size),
                shift_labels.view(-1),
                ignore_index=-100,
            )

        return CausalLMOutput(
            logits=logits,
            loss=loss,
            past_key_values=new_key_values,
            hidden_states=hidden_states,
        )

    def num_parameters(self, trainable_only: bool = True) -> int:
        """Count model parameters."""
        if trainable_only:
            return sum(p.numel() for p in self.parameters() if p.requires_grad)
        return sum(p.numel() for p in self.parameters())

    @classmethod
    def from_pretrained(cls, path: str) -> HwarangForCausalLM:
        """Load a pretrained model from checkpoint."""
        import yaml

        config_path = f"{path}/config.yaml"
        with open(config_path) as f:
            config_dict = yaml.safe_load(f)
        config = HwarangConfig(**config_dict)

        model = cls(config)
        checkpoint = torch.load(f"{path}/model.pt", map_location="cpu", weights_only=True)
        model.load_state_dict(checkpoint["model_state_dict"])

        return model

    def save_pretrained(self, path: str) -> None:
        """Save model checkpoint."""
        from pathlib import Path as P

        P(path).mkdir(parents=True, exist_ok=True)
        self.config.to_yaml(f"{path}/config.yaml")
        torch.save(
            {"model_state_dict": self.state_dict()},
            f"{path}/model.pt",
        )
