"""Tests for the Hwarang transformer model."""

import pytest
import torch

from hwarang_core.model.config import HwarangConfig
from hwarang_core.model.transformer import HwarangForCausalLM, HwarangModel


class TestHwarangConfig:
    def test_default_config(self):
        config = HwarangConfig()
        assert config.hidden_size == 768
        assert config.num_hidden_layers == 12
        assert config.head_dim == 768 // 12

    def test_small_preset(self):
        config = HwarangConfig.small()
        assert config.hidden_size == 768

    def test_medium_preset(self):
        config = HwarangConfig.medium()
        assert config.hidden_size == 1024

    def test_large_preset(self):
        config = HwarangConfig.large()
        assert config.hidden_size == 2048

    def test_gqa_validation(self):
        # Valid: 12 heads / 4 kv heads = 3 groups
        config = HwarangConfig(num_attention_heads=12, num_key_value_heads=4)
        assert config.num_attention_heads % config.num_key_value_heads == 0

    def test_gqa_invalid_raises(self):
        with pytest.raises(AssertionError):
            HwarangConfig(num_attention_heads=12, num_key_value_heads=5)


class TestHwarangModel:
    def test_forward_shape(self, tiny_model, tiny_config, sample_input_ids):
        hidden_states, _ = tiny_model(sample_input_ids)
        batch, seq = sample_input_ids.shape
        assert hidden_states.shape == (batch, seq, tiny_config.hidden_size)

    def test_forward_with_cache(self, tiny_model, sample_input_ids):
        hidden_states, kv_cache = tiny_model(sample_input_ids, use_cache=True)
        assert kv_cache is not None
        assert len(kv_cache) == 2  # 2 layers
        # Each cache entry is (key, value) tuple
        k, v = kv_cache[0]
        assert k.shape[2] == sample_input_ids.shape[1]  # seq_len

    def test_causal_mask(self, tiny_model, sample_input_ids):
        """Model should not attend to future positions."""
        hidden_states, _ = tiny_model(sample_input_ids)
        assert hidden_states is not None

    def test_num_parameters(self, tiny_model):
        num_params = tiny_model.num_parameters()
        assert num_params > 0
        assert isinstance(num_params, int)


class TestHwarangForCausalLM:
    def test_forward_logits_shape(self, tiny_causal_lm, tiny_config, sample_input_ids):
        output = tiny_causal_lm(sample_input_ids)
        batch, seq = sample_input_ids.shape
        assert output.logits.shape == (batch, seq, tiny_config.vocab_size)
        assert output.loss is None  # No labels provided

    def test_forward_with_labels(self, tiny_causal_lm, sample_input_ids):
        labels = sample_input_ids.clone()
        output = tiny_causal_lm(sample_input_ids, labels=labels)
        assert output.loss is not None
        assert output.loss.item() > 0  # Loss should be positive

    def test_forward_with_cache(self, tiny_causal_lm, sample_input_ids):
        output = tiny_causal_lm(sample_input_ids, use_cache=True)
        assert output.past_key_values is not None

    def test_incremental_decoding(self, tiny_causal_lm):
        """Test that KV cache produces same logits as full forward pass."""
        input_ids = torch.randint(0, 256, (1, 8))

        # Full forward
        full_output = tiny_causal_lm(input_ids)
        full_last_logits = full_output.logits[:, -1, :]

        # Incremental: first pass all but last, then last token with cache
        prefix = input_ids[:, :-1]
        last_token = input_ids[:, -1:]

        prefix_output = tiny_causal_lm(prefix, use_cache=True)
        incr_output = tiny_causal_lm(
            last_token,
            past_key_values=prefix_output.past_key_values,
            use_cache=True,
        )
        incr_logits = incr_output.logits[:, -1, :]

        # Should produce same logits (within float tolerance)
        torch.testing.assert_close(full_last_logits, incr_logits, atol=1e-4, rtol=1e-4)

    def test_tied_embeddings(self, tiny_config):
        tiny_config.tie_word_embeddings = True
        model = HwarangForCausalLM(tiny_config)
        assert model.lm_head.weight is model.model.embed_tokens.token_embedding.weight

    def test_untied_embeddings(self, tiny_config):
        tiny_config.tie_word_embeddings = False
        model = HwarangForCausalLM(tiny_config)
        assert model.lm_head.weight is not model.model.embed_tokens.token_embedding.weight
