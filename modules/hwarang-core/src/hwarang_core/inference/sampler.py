"""Sampling strategies for text generation."""

from __future__ import annotations

import torch
import torch.nn.functional as F


def top_k_top_p_filter(
    logits: torch.Tensor,
    top_k: int = 0,
    top_p: float = 1.0,
) -> torch.Tensor:
    """Apply top-k and top-p (nucleus) filtering to logits.

    Args:
        logits: Shape (batch, vocab_size)
        top_k: Keep only top-k tokens. 0 = disabled.
        top_p: Keep smallest set of tokens with cumulative prob >= top_p. 1.0 = disabled.

    Returns:
        Filtered logits with -inf for removed tokens.
    """
    if top_k > 0:
        top_k = min(top_k, logits.size(-1))
        indices_to_remove = logits < torch.topk(logits, top_k)[0][..., -1, None]
        logits = logits.masked_fill(indices_to_remove, float("-inf"))

    if top_p < 1.0:
        sorted_logits, sorted_indices = torch.sort(logits, descending=True)
        cumulative_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)

        # Remove tokens with cumulative probability above threshold
        sorted_indices_to_remove = cumulative_probs > top_p
        # Shift right to keep the first token above threshold
        sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
        sorted_indices_to_remove[..., 0] = False

        indices_to_remove = sorted_indices_to_remove.scatter(
            -1, sorted_indices, sorted_indices_to_remove
        )
        logits = logits.masked_fill(indices_to_remove, float("-inf"))

    return logits


def apply_repetition_penalty(
    logits: torch.Tensor,
    input_ids: torch.Tensor,
    penalty: float = 1.0,
) -> torch.Tensor:
    """Apply repetition penalty to previously generated tokens.

    Args:
        logits: Shape (batch, vocab_size)
        input_ids: Previously generated token IDs (batch, seq_len)
        penalty: Penalty factor. > 1.0 discourages repetition.
    """
    if penalty == 1.0:
        return logits

    score = torch.gather(logits, -1, input_ids)

    # If score < 0, multiply by penalty (making it more negative)
    # If score > 0, divide by penalty (making it less positive)
    score = torch.where(score < 0, score * penalty, score / penalty)

    logits.scatter_(-1, input_ids, score)
    return logits


def sample_next_token(
    logits: torch.Tensor,
    temperature: float = 1.0,
    top_k: int = 50,
    top_p: float = 0.9,
    input_ids: torch.Tensor | None = None,
    repetition_penalty: float = 1.0,
) -> torch.Tensor:
    """Sample the next token from logits.

    Args:
        logits: Shape (batch, vocab_size)
        temperature: Sampling temperature. 0 = greedy.
        top_k: Top-k filtering. 0 = disabled.
        top_p: Nucleus sampling threshold. 1.0 = disabled.
        input_ids: Previous tokens for repetition penalty.
        repetition_penalty: Penalty for repeating tokens.

    Returns:
        Token IDs of shape (batch, 1)
    """
    # Apply repetition penalty
    if input_ids is not None and repetition_penalty != 1.0:
        logits = apply_repetition_penalty(logits, input_ids, repetition_penalty)

    # Greedy decoding
    if temperature == 0 or temperature < 1e-8:
        return logits.argmax(dim=-1, keepdim=True)

    # Temperature scaling
    logits = logits / temperature

    # Top-k / Top-p filtering
    logits = top_k_top_p_filter(logits, top_k=top_k, top_p=top_p)

    # Sample
    probs = F.softmax(logits, dim=-1)
    return torch.multinomial(probs, num_samples=1)
