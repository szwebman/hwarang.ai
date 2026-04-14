"""Tests for inference components."""

import pytest
import torch

from hwarang_core.inference.sampler import (
    apply_repetition_penalty,
    sample_next_token,
    top_k_top_p_filter,
)


class TestTopKTopPFilter:
    def test_top_k_filter(self):
        logits = torch.tensor([[1.0, 2.0, 3.0, 4.0, 5.0]])
        filtered = top_k_top_p_filter(logits, top_k=2)
        # Only top 2 values should remain
        assert (filtered[0, :3] == float("-inf")).all()
        assert filtered[0, 3] == 4.0
        assert filtered[0, 4] == 5.0

    def test_top_k_zero_is_disabled(self):
        logits = torch.tensor([[1.0, 2.0, 3.0]])
        filtered = top_k_top_p_filter(logits, top_k=0)
        torch.testing.assert_close(filtered, logits)

    def test_top_p_filter(self):
        logits = torch.tensor([[10.0, 1.0, 0.0, -1.0]])  # Very peaked
        filtered = top_k_top_p_filter(logits, top_p=0.9)
        # The top token should remain, others may be filtered
        assert filtered[0, 0] == 10.0

    def test_top_p_one_is_disabled(self):
        logits = torch.tensor([[1.0, 2.0, 3.0]])
        filtered = top_k_top_p_filter(logits, top_p=1.0)
        torch.testing.assert_close(filtered, logits)


class TestRepetitionPenalty:
    def test_penalty_reduces_repeated_token_scores(self):
        logits = torch.tensor([[5.0, 3.0, 1.0]])
        input_ids = torch.tensor([[0]])  # Token 0 was generated before
        penalized = apply_repetition_penalty(logits.clone(), input_ids, penalty=2.0)
        # Token 0's positive score should be divided by penalty
        assert penalized[0, 0] < logits[0, 0]

    def test_no_penalty_when_1(self):
        logits = torch.tensor([[5.0, 3.0, 1.0]])
        input_ids = torch.tensor([[0, 1]])
        penalized = apply_repetition_penalty(logits.clone(), input_ids, penalty=1.0)
        torch.testing.assert_close(penalized, logits)


class TestSampleNextToken:
    def test_greedy_decoding(self):
        logits = torch.tensor([[1.0, 5.0, 2.0]])
        token = sample_next_token(logits, temperature=0)
        assert token.item() == 1  # Index of max value

    def test_returns_valid_token(self):
        logits = torch.randn(1, 100)
        token = sample_next_token(logits, temperature=1.0, top_k=10)
        assert 0 <= token.item() < 100

    def test_batch_sampling(self):
        logits = torch.randn(4, 50)
        tokens = sample_next_token(logits, temperature=1.0)
        assert tokens.shape == (4, 1)

    def test_temperature_zero_is_greedy(self):
        logits = torch.tensor([[0.1, 0.2, 10.0, 0.3]])
        token = sample_next_token(logits, temperature=0.0)
        assert token.item() == 2
