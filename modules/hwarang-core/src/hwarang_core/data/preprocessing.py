"""Text preprocessing utilities for training data."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path


def clean_text(text: str) -> str:
    """Clean and normalize text for training.

    - Unicode normalize (NFC)
    - Replace multiple whitespace with single
    - Remove control characters (except newlines/tabs)
    - Strip leading/trailing whitespace
    """
    # Unicode normalization
    text = unicodedata.normalize("NFC", text)

    # Remove control characters except \n and \t
    text = "".join(
        ch for ch in text
        if unicodedata.category(ch) != "Cc" or ch in "\n\t"
    )

    # Normalize whitespace (but preserve newlines)
    lines = text.split("\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    text = "\n".join(lines)

    # Remove excessive newlines (more than 2 consecutive)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def dedup_lines(texts: list[str], threshold: float = 1.0) -> list[str]:
    """Remove exact duplicate texts.

    Args:
        texts: List of text strings.
        threshold: Not used for exact dedup (reserved for fuzzy).

    Returns:
        Deduplicated list.
    """
    seen: set[str] = set()
    result: list[str] = []
    for text in texts:
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if text_hash not in seen:
            seen.add(text_hash)
            result.append(text)
    return result


def filter_by_length(
    texts: list[str],
    min_chars: int = 50,
    max_chars: int = 100_000,
) -> list[str]:
    """Filter texts by character length."""
    return [t for t in texts if min_chars <= len(t) <= max_chars]


def tokenize_and_save(
    texts: list[str],
    tokenizer,
    output_path: str | Path,
    seq_length: int = 2048,
) -> int:
    """Tokenize texts and save as a binary file for PretrainDataset.

    Concatenates all tokenized texts into a single stream,
    saved as uint16 numpy array.

    Args:
        texts: List of text strings.
        tokenizer: HwarangTokenizer instance.
        output_path: Path to save the .bin file.
        seq_length: Not used here (dataset handles chunking).

    Returns:
        Total number of tokens.
    """
    import numpy as np

    all_ids: list[int] = []
    for text in texts:
        ids = tokenizer.encode(text, add_special_tokens=True)
        all_ids.extend(ids)

    # Save as uint16 (supports vocab up to 65535)
    arr = np.array(all_ids, dtype=np.uint16)
    arr.tofile(str(output_path))

    return len(all_ids)
