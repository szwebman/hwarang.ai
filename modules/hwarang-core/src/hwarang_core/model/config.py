"""Model configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class HwarangConfig:
    """Configuration for the Hwarang transformer model."""

    # Model architecture
    vocab_size: int = 32000
    hidden_size: int = 768
    intermediate_size: int = 2048
    num_hidden_layers: int = 12
    num_attention_heads: int = 12
    num_key_value_heads: int = 4  # GQA: fewer KV heads
    max_position_embeddings: int = 4096
    head_dim: int = 0  # Computed from hidden_size / num_attention_heads

    # Normalization
    rms_norm_eps: float = 1e-6

    # Positional encoding
    rope_theta: float = 10000.0

    # Dropout (0.0 for pretraining, can increase for fine-tuning)
    attention_dropout: float = 0.0
    hidden_dropout: float = 0.0

    # Embedding
    tie_word_embeddings: bool = True

    # Initialization
    initializer_range: float = 0.02

    # Special tokens
    pad_token_id: int = 0
    bos_token_id: int = 1
    eos_token_id: int = 2

    def __post_init__(self):
        if self.head_dim == 0:
            self.head_dim = self.hidden_size // self.num_attention_heads
        # Validate GQA configuration
        assert self.num_attention_heads % self.num_key_value_heads == 0, (
            f"num_attention_heads ({self.num_attention_heads}) must be divisible by "
            f"num_key_value_heads ({self.num_key_value_heads})"
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> HwarangConfig:
        """Load config from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def to_yaml(self, path: str | Path) -> None:
        """Save config to YAML file."""
        from dataclasses import asdict
        with open(path, "w") as f:
            yaml.dump(asdict(self), f, default_flow_style=False)

    @classmethod
    def small(cls) -> HwarangConfig:
        """~125M parameter model."""
        return cls(
            hidden_size=768,
            intermediate_size=2048,
            num_hidden_layers=12,
            num_attention_heads=12,
            num_key_value_heads=4,
        )

    @classmethod
    def medium(cls) -> HwarangConfig:
        """~350M parameter model."""
        return cls(
            hidden_size=1024,
            intermediate_size=2816,
            num_hidden_layers=24,
            num_attention_heads=16,
            num_key_value_heads=4,
        )

    @classmethod
    def large(cls) -> HwarangConfig:
        """~1.3B parameter model."""
        return cls(
            hidden_size=2048,
            intermediate_size=5504,
            num_hidden_layers=24,
            num_attention_heads=16,
            num_key_value_heads=4,
        )
