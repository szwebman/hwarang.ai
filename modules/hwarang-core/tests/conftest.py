"""Test fixtures for hwarang-core."""

import pytest
import torch

from hwarang_core.model.config import HwarangConfig
from hwarang_core.model.transformer import HwarangForCausalLM, HwarangModel


@pytest.fixture
def tiny_config():
    """Minimal config for fast tests."""
    return HwarangConfig(
        vocab_size=256,
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=128,
    )


@pytest.fixture
def tiny_model(tiny_config):
    """Tiny model for testing."""
    return HwarangModel(tiny_config)


@pytest.fixture
def tiny_causal_lm(tiny_config):
    """Tiny causal LM for testing."""
    return HwarangForCausalLM(tiny_config)


@pytest.fixture
def sample_input_ids():
    """Sample input tensor."""
    return torch.randint(0, 256, (2, 16))  # batch=2, seq=16
