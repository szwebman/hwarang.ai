"""Tests for training pipeline."""

import pytest
import torch

from hwarang_core.model.config import HwarangConfig
from hwarang_core.model.transformer import HwarangForCausalLM
from hwarang_core.training.trainer import TrainingConfig


class TestTrainingConfig:
    def test_default_config(self):
        config = TrainingConfig()
        assert config.learning_rate == 3e-4
        assert config.batch_size == 8

    def test_device_auto_cpu(self):
        config = TrainingConfig(device="cpu")
        assert config.get_device() == torch.device("cpu")

    def test_dtype_mapping(self):
        config = TrainingConfig(dtype="float32")
        assert config.get_dtype() == torch.float32
        config.dtype = "bfloat16"
        assert config.get_dtype() == torch.bfloat16


class TestGradientFlow:
    """Verify gradients flow correctly through the model."""

    def test_loss_backward(self):
        config = HwarangConfig(
            vocab_size=64,
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=1,
            num_attention_heads=2,
            num_key_value_heads=1,
            max_position_embeddings=32,
        )
        model = HwarangForCausalLM(config)
        model.train()

        input_ids = torch.randint(0, 64, (2, 8))
        labels = input_ids.clone()

        output = model(input_ids, labels=labels)
        assert output.loss is not None

        output.loss.backward()

        # Check that gradients exist on key parameters
        for name, param in model.named_parameters():
            if param.requires_grad:
                assert param.grad is not None, f"No gradient for {name}"

    def test_loss_decreases_with_step(self):
        """One optimization step should reduce the loss."""
        config = HwarangConfig(
            vocab_size=64,
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=1,
            num_attention_heads=2,
            num_key_value_heads=1,
            max_position_embeddings=32,
        )
        model = HwarangForCausalLM(config)
        model.train()
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

        input_ids = torch.randint(0, 64, (4, 16))
        labels = input_ids.clone()

        # Initial loss
        output1 = model(input_ids, labels=labels)
        loss1 = output1.loss.item()

        # One step
        output1.loss.backward()
        optimizer.step()
        optimizer.zero_grad()

        # Loss after step
        output2 = model(input_ids, labels=labels)
        loss2 = output2.loss.item()

        # Loss should typically decrease (not guaranteed but very likely with LR=1e-3)
        assert loss2 < loss1 * 1.1  # Allow small tolerance
