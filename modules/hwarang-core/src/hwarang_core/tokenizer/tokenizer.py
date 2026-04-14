"""Hwarang BPE Tokenizer.

Encodes and decodes text using a trained BPE vocabulary.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class HwarangTokenizer:
    """BPE tokenizer for encoding/decoding text."""

    def __init__(self, vocab_dir: str | Path):
        vocab_dir = Path(vocab_dir)

        # Load vocab
        with open(vocab_dir / "vocab.json", encoding="utf-8") as f:
            self.token_to_id: dict[str, int] = json.load(f)
        self.id_to_token: dict[int, str] = {v: k for k, v in self.token_to_id.items()}

        # Load merges
        self.merges: list[tuple[str, str]] = []
        self.merge_ranks: dict[tuple[str, str], int] = {}
        with open(vocab_dir / "merges.txt", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line:
                    parts = line.split(" ", 1)
                    if len(parts) == 2:
                        pair = (parts[0], parts[1])
                        self.merges.append(pair)
                        self.merge_ranks[pair] = i

        # Load config
        with open(vocab_dir / "tokenizer_config.json", encoding="utf-8") as f:
            config = json.load(f)
        self.special_tokens: list[str] = config.get("special_tokens", [])

        # Build special token map
        self.special_token_ids = {
            tok: self.token_to_id[tok]
            for tok in self.special_tokens
            if tok in self.token_to_id
        }

        # Pre-tokenization pattern
        self.pattern = re.compile(
            r"""'(?:[sdmt]|ll|ve|re)|"""
            r""" ?[a-zA-Z\u00C0-\u024F\u1E00-\u1EFF]+|"""
            r""" ?[0-9]+|"""
            r""" ?[^\s\w]+|"""
            r"""\s+"""
        )

    @property
    def vocab_size(self) -> int:
        return len(self.token_to_id)

    @property
    def pad_token_id(self) -> int:
        return self.special_token_ids.get("<|pad|>", 0)

    @property
    def bos_token_id(self) -> int:
        return self.special_token_ids.get("<|bos|>", 1)

    @property
    def eos_token_id(self) -> int:
        return self.special_token_ids.get("<|eos|>", 2)

    @property
    def unk_token_id(self) -> int:
        return self.special_token_ids.get("<|unk|>", 3)

    def _bpe(self, token: str) -> list[str]:
        """Apply BPE merges to a single pre-token."""
        word = list(token)
        if len(word) <= 1:
            return word

        while True:
            # Find the highest-priority merge pair
            best_pair = None
            best_rank = float("inf")
            for i in range(len(word) - 1):
                pair = (word[i], word[i + 1])
                rank = self.merge_ranks.get(pair)
                if rank is not None and rank < best_rank:
                    best_pair = pair
                    best_rank = rank

            if best_pair is None:
                break

            # Apply the merge
            new_word: list[str] = []
            i = 0
            while i < len(word):
                if (
                    i < len(word) - 1
                    and word[i] == best_pair[0]
                    and word[i + 1] == best_pair[1]
                ):
                    new_word.append(best_pair[0] + best_pair[1])
                    i += 2
                else:
                    new_word.append(word[i])
                    i += 1
            word = new_word

            if len(word) == 1:
                break

        return word

    def encode(self, text: str, add_special_tokens: bool = True) -> list[int]:
        """Encode text to token IDs.

        Args:
            text: Input text string.
            add_special_tokens: Whether to add BOS/EOS tokens.

        Returns:
            List of token IDs.
        """
        ids: list[int] = []

        if add_special_tokens:
            ids.append(self.bos_token_id)

        # Pre-tokenize
        pre_tokens = self.pattern.findall(text)

        for pre_token in pre_tokens:
            bpe_tokens = self._bpe(pre_token)
            for token in bpe_tokens:
                token_id = self.token_to_id.get(token, self.unk_token_id)
                ids.append(token_id)

        if add_special_tokens:
            ids.append(self.eos_token_id)

        return ids

    def decode(self, ids: list[int], skip_special_tokens: bool = True) -> str:
        """Decode token IDs back to text.

        Args:
            ids: List of token IDs.
            skip_special_tokens: Whether to skip special tokens in output.

        Returns:
            Decoded text string.
        """
        tokens: list[str] = []
        special_ids = set(self.special_token_ids.values()) if skip_special_tokens else set()

        for token_id in ids:
            if token_id in special_ids:
                continue
            token = self.id_to_token.get(token_id, "")
            tokens.append(token)

        return "".join(tokens)

    def encode_chat(self, messages: list[dict[str, str]]) -> list[int]:
        """Encode chat messages in ChatML format.

        Args:
            messages: List of dicts with 'role' and 'content' keys.

        Returns:
            List of token IDs.
        """
        ids: list[int] = [self.bos_token_id]

        im_start = self.token_to_id.get("<|im_start|>")
        im_end = self.token_to_id.get("<|im_end|>")

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if im_start is not None:
                ids.append(im_start)

            # Encode role
            role_ids = self.encode(role + "\n", add_special_tokens=False)
            ids.extend(role_ids)

            # Encode content
            content_ids = self.encode(content, add_special_tokens=False)
            ids.extend(content_ids)

            if im_end is not None:
                ids.append(im_end)

        return ids

    def save(self, output_dir: str | Path) -> None:
        """Save tokenizer to directory."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_dir / "vocab.json", "w", encoding="utf-8") as f:
            json.dump(self.token_to_id, f, ensure_ascii=False, indent=2)

        with open(output_dir / "merges.txt", "w", encoding="utf-8") as f:
            for pair in self.merges:
                f.write(f"{pair[0]} {pair[1]}\n")

        config = {
            "vocab_size": self.vocab_size,
            "special_tokens": self.special_tokens,
        }
        with open(output_dir / "tokenizer_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def __len__(self) -> int:
        return self.vocab_size

    def __repr__(self) -> str:
        return f"HwarangTokenizer(vocab_size={self.vocab_size})"
