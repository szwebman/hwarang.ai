"""Data pipeline orchestrator for preparing training data."""

from __future__ import annotations

import logging
from pathlib import Path

from hwarang_core.data.preprocessing import clean_text, dedup_lines, filter_by_length, tokenize_and_save

logger = logging.getLogger(__name__)


class DataPipeline:
    """Orchestrates the full data preparation pipeline.

    1. Load raw text files
    2. Clean and normalize
    3. Deduplicate
    4. Filter by length
    5. Tokenize and save as binary
    """

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def process(
        self,
        input_dir: str | Path,
        output_path: str | Path,
        file_pattern: str = "*.txt",
        min_chars: int = 50,
        max_chars: int = 100_000,
    ) -> dict:
        """Run the full pipeline.

        Args:
            input_dir: Directory containing raw text files.
            output_path: Path for the output .bin file.
            file_pattern: Glob pattern for input files.
            min_chars: Minimum text length in characters.
            max_chars: Maximum text length in characters.

        Returns:
            Statistics dict.
        """
        input_dir = Path(input_dir)
        files = sorted(input_dir.rglob(file_pattern))
        logger.info(f"Found {len(files)} files matching '{file_pattern}'")

        # Load
        texts: list[str] = []
        for file_path in files:
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                texts.append(text)
            except Exception as e:
                logger.warning(f"Failed to read {file_path}: {e}")
        logger.info(f"Loaded {len(texts)} texts")

        # Clean
        texts = [clean_text(t) for t in texts]
        texts = [t for t in texts if t]  # Remove empty
        logger.info(f"After cleaning: {len(texts)}")

        # Dedup
        before = len(texts)
        texts = dedup_lines(texts)
        logger.info(f"After dedup: {len(texts)} (removed {before - len(texts)})")

        # Filter
        texts = filter_by_length(texts, min_chars, max_chars)
        logger.info(f"After length filter: {len(texts)}")

        # Tokenize and save
        total_tokens = tokenize_and_save(texts, self.tokenizer, output_path)
        logger.info(f"Total tokens: {total_tokens:,}")
        logger.info(f"Saved to {output_path}")

        return {
            "num_files": len(files),
            "num_texts": len(texts),
            "total_tokens": total_tokens,
            "output_path": str(output_path),
        }
