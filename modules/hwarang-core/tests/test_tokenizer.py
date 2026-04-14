"""Tests for the BPE tokenizer."""

import json
import tempfile
from pathlib import Path

import pytest

from hwarang_core.tokenizer.trainer import BPETrainer
from hwarang_core.tokenizer.tokenizer import HwarangTokenizer


@pytest.fixture
def sample_texts():
    return [
        "Hello world! This is a test.",
        "The quick brown fox jumps over the lazy dog.",
        "Machine learning is fascinating.",
        "Hello world! Hello again.",
        "The fox is quick. The dog is lazy.",
    ] * 10  # Repeat for sufficient frequency


@pytest.fixture
def trained_tokenizer(sample_texts, tmp_path):
    """Train a small tokenizer and return it."""
    trainer = BPETrainer(vocab_size=200, min_frequency=2)
    trainer.train(sample_texts, tmp_path / "tokenizer")
    return HwarangTokenizer(tmp_path / "tokenizer")


class TestBPETrainer:
    def test_train_creates_files(self, sample_texts, tmp_path):
        trainer = BPETrainer(vocab_size=100, min_frequency=2)
        result = trainer.train(sample_texts, tmp_path / "out")

        assert (tmp_path / "out" / "vocab.json").exists()
        assert (tmp_path / "out" / "merges.txt").exists()
        assert (tmp_path / "out" / "tokenizer_config.json").exists()
        assert result["vocab_size"] > 0
        assert result["num_merges"] >= 0

    def test_special_tokens_in_vocab(self, sample_texts, tmp_path):
        trainer = BPETrainer(vocab_size=100, min_frequency=2)
        trainer.train(sample_texts, tmp_path / "out")

        with open(tmp_path / "out" / "vocab.json") as f:
            vocab = json.load(f)

        assert "<|pad|>" in vocab
        assert "<|bos|>" in vocab
        assert "<|eos|>" in vocab
        assert vocab["<|pad|>"] == 0
        assert vocab["<|bos|>"] == 1
        assert vocab["<|eos|>"] == 2

    def test_train_from_file(self, tmp_path):
        # Write sample text to a file
        text_file = tmp_path / "corpus.txt"
        text_file.write_text("Hello world\nHello again\nWorld hello\n" * 20)

        trainer = BPETrainer(vocab_size=50, min_frequency=2)
        result = trainer.train(str(text_file), tmp_path / "out")
        assert result["vocab_size"] > 0


class TestHwarangTokenizer:
    def test_encode_decode_roundtrip(self, trained_tokenizer):
        text = "Hello world"
        ids = trained_tokenizer.encode(text, add_special_tokens=False)
        decoded = trained_tokenizer.decode(ids)
        assert decoded == text

    def test_special_tokens_added(self, trained_tokenizer):
        ids = trained_tokenizer.encode("test", add_special_tokens=True)
        assert ids[0] == trained_tokenizer.bos_token_id
        assert ids[-1] == trained_tokenizer.eos_token_id

    def test_special_tokens_skipped_in_decode(self, trained_tokenizer):
        ids = trained_tokenizer.encode("Hello", add_special_tokens=True)
        decoded = trained_tokenizer.decode(ids, skip_special_tokens=True)
        assert "<|bos|>" not in decoded
        assert "<|eos|>" not in decoded

    def test_vocab_size(self, trained_tokenizer):
        assert trained_tokenizer.vocab_size > 0
        assert len(trained_tokenizer) == trained_tokenizer.vocab_size

    def test_encode_empty_string(self, trained_tokenizer):
        ids = trained_tokenizer.encode("", add_special_tokens=False)
        assert ids == []

    def test_encode_chat(self, trained_tokenizer):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        ids = trained_tokenizer.encode_chat(messages)
        assert len(ids) > 0
        assert ids[0] == trained_tokenizer.bos_token_id

    def test_save_and_reload(self, trained_tokenizer, tmp_path):
        save_dir = tmp_path / "saved_tokenizer"
        trained_tokenizer.save(save_dir)

        reloaded = HwarangTokenizer(save_dir)
        assert reloaded.vocab_size == trained_tokenizer.vocab_size

        text = "Hello world"
        orig_ids = trained_tokenizer.encode(text, add_special_tokens=False)
        reload_ids = reloaded.encode(text, add_special_tokens=False)
        assert orig_ids == reload_ids

    def test_repr(self, trained_tokenizer):
        repr_str = repr(trained_tokenizer)
        assert "HwarangTokenizer" in repr_str
        assert str(trained_tokenizer.vocab_size) in repr_str
