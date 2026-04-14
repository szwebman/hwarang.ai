"""BPE Tokenizer Trainer.

Trains a Byte-Pair Encoding tokenizer from scratch on a text corpus.
Supports Korean-optimized mode for better Hangul handling.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from hwarang_core.tokenizer.korean import (
    build_korean_initial_vocab,
)

# Default pre-tokenization pattern (GPT-4 style + Korean)
DEFAULT_PATTERN = re.compile(
    r"""'(?:[sdmt]|ll|ve|re)|"""
    r""" ?[\uAC00-\uD7A3]+|"""       # Korean syllable blocks (가-힣)
    r""" ?[a-zA-Z\u00C0-\u024F]+|"""  # Latin letters
    r""" ?[0-9]+|"""                   # Numbers
    r""" ?[^\s\w\uAC00-\uD7A3]+|"""   # Punctuation
    r"""\s+"""
)


class BPETrainer:
    """Train a BPE tokenizer from text data.

    Args:
        vocab_size: Target vocabulary size.
        min_frequency: Minimum pair frequency for a merge.
        special_tokens: Special tokens to include.
        korean_optimized: If True, pre-seeds vocab with Korean jamo, syllables,
                         and common particles for dramatically better Korean performance.
    """

    def __init__(
        self,
        vocab_size: int = 32000,
        min_frequency: int = 2,
        special_tokens: list[str] | None = None,
        korean_optimized: bool = True,
    ):
        self.vocab_size = vocab_size
        self.min_frequency = min_frequency
        self.special_tokens = special_tokens or [
            "<|pad|>",
            "<|bos|>",
            "<|eos|>",
            "<|unk|>",
            "<|im_start|>",
            "<|im_end|>",
        ]
        self.korean_optimized = korean_optimized
        self.pattern = DEFAULT_PATTERN

    def _pre_tokenize(self, text: str) -> list[str]:
        """Split text into pre-tokens using regex pattern."""
        return self.pattern.findall(text)

    def _get_pairs(self, word: tuple[str, ...]) -> set[tuple[str, str]]:
        """Get all adjacent pairs in a word."""
        return {(word[i], word[i + 1]) for i in range(len(word) - 1)}

    def train(self, texts: list[str] | str, output_dir: str | Path) -> dict:
        """Train BPE tokenizer on texts.

        Args:
            texts: List of text strings or path to a text file.
            output_dir: Directory to save tokenizer files.

        Returns:
            Dictionary with vocab and merges info.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load texts if path provided
        if isinstance(texts, (str, Path)):
            with open(texts, encoding="utf-8") as f:
                texts = [line.strip() for line in f if line.strip()]

        # Step 1: Pre-tokenize and count word frequencies
        print(f"Pre-tokenizing {len(texts):,} texts...")
        word_freqs: Counter[tuple[str, ...]] = Counter()
        for text in texts:
            pre_tokens = self._pre_tokenize(text)
            for token in pre_tokens:
                chars = tuple(token)
                word_freqs[chars] += 1

        print(f"  Unique pre-tokens: {len(word_freqs):,}")

        # Step 2: Initialize vocab
        vocab: dict[str, int] = {}
        idx = 0

        # Special tokens first
        for token in self.special_tokens:
            vocab[token] = idx
            idx += 1

        # Korean-optimized: add jamo, common syllables, particles
        if self.korean_optimized:
            print("  Korean optimization: adding initial Korean vocab...")
            korean_tokens = build_korean_initial_vocab()
            for token in korean_tokens:
                if token not in vocab:
                    vocab[token] = idx
                    idx += 1
            print(f"  Korean initial tokens: {len(korean_tokens)}")

        # Add all individual characters from the corpus
        all_chars: set[str] = set()
        for word in word_freqs:
            all_chars.update(word)
        for ch in sorted(all_chars):
            if ch not in vocab:
                vocab[ch] = idx
                idx += 1

        print(f"  Initial vocab size: {len(vocab)} (before merges)")

        # Step 3: Iteratively merge most frequent pairs
        merges: list[tuple[str, str]] = []

        while len(vocab) < self.vocab_size:
            # Count all pairs
            pair_freqs: Counter[tuple[str, str]] = Counter()
            for word, freq in word_freqs.items():
                pairs = self._get_pairs(word)
                for pair in pairs:
                    pair_freqs[pair] += freq

            if not pair_freqs:
                break

            # Find most frequent pair
            best_pair = pair_freqs.most_common(1)[0]
            if best_pair[1] < self.min_frequency:
                break

            pair = best_pair[0]
            merges.append(pair)

            # Merge the pair in all words
            new_token = pair[0] + pair[1]
            vocab[new_token] = idx
            idx += 1

            # Update word_freqs with merged pair
            new_word_freqs: Counter[tuple[str, ...]] = Counter()
            for word, freq in word_freqs.items():
                new_word = self._merge_pair(word, pair)
                new_word_freqs[new_word] += freq
            word_freqs = new_word_freqs

            if len(merges) % 500 == 0:
                print(f"  Merge {len(merges)}: {pair[0]!r} + {pair[1]!r} -> {new_token!r} "
                      f"(freq={best_pair[1]}, vocab_size={len(vocab)})")

        # Step 4: Analyze Korean coverage
        korean_tokens_in_vocab = sum(
            1 for t in vocab if any("\uAC00" <= c <= "\uD7A3" for c in t)
        )
        print(f"\nVocab analysis:")
        print(f"  Total vocab size: {len(vocab)}")
        print(f"  Total merges: {len(merges)}")
        print(f"  Korean tokens: {korean_tokens_in_vocab}")
        print(f"  Korean ratio: {korean_tokens_in_vocab / len(vocab) * 100:.1f}%")

        # Step 5: Save
        vocab_path = output_dir / "vocab.json"
        with open(vocab_path, "w", encoding="utf-8") as f:
            json.dump(vocab, f, ensure_ascii=False, indent=2)

        merges_path = output_dir / "merges.txt"
        with open(merges_path, "w", encoding="utf-8") as f:
            for p in merges:
                f.write(f"{p[0]} {p[1]}\n")

        config = {
            "vocab_size": len(vocab),
            "special_tokens": self.special_tokens,
            "min_frequency": self.min_frequency,
            "korean_optimized": self.korean_optimized,
        }
        config_path = output_dir / "tokenizer_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        print(f"Saved to {output_dir}")

        return {
            "vocab_size": len(vocab),
            "num_merges": len(merges),
            "korean_tokens": korean_tokens_in_vocab,
        }

    @staticmethod
    def _merge_pair(word: tuple[str, ...], pair: tuple[str, str]) -> tuple[str, ...]:
        """Merge all occurrences of a pair in a word."""
        new_word: list[str] = []
        i = 0
        while i < len(word):
            if i < len(word) - 1 and word[i] == pair[0] and word[i + 1] == pair[1]:
                new_word.append(pair[0] + pair[1])
                i += 2
            else:
                new_word.append(word[i])
                i += 1
        return tuple(new_word)
