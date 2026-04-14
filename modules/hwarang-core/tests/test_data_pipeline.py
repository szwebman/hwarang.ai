"""Tests for data pipeline."""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
import torch

from hwarang_core.data.collator import DPOCollator, PaddingCollator
from hwarang_core.data.dataset import PretrainDataset


class TestPretrainDataset:
    def test_load_and_index(self, tmp_path):
        # Create a small tokenized file
        data = np.random.randint(0, 1000, size=4096, dtype=np.uint16)
        data_path = tmp_path / "train.bin"
        data.tofile(str(data_path))

        dataset = PretrainDataset(data_path, seq_length=64)
        assert len(dataset) == 4096 // 64

        sample = dataset[0]
        assert "input_ids" in sample
        assert "labels" in sample
        assert sample["input_ids"].shape == (64,)
        assert sample["labels"].shape == (64,)

    def test_labels_are_shifted(self, tmp_path):
        data = np.arange(128, dtype=np.uint16)
        data_path = tmp_path / "train.bin"
        data.tofile(str(data_path))

        dataset = PretrainDataset(data_path, seq_length=32)
        sample = dataset[0]
        # labels should be input_ids shifted by 1
        assert sample["input_ids"][0].item() == 0
        assert sample["labels"][0].item() == 1


class TestPaddingCollator:
    def test_pads_to_max_length(self):
        collator = PaddingCollator(pad_token_id=0)
        batch = [
            {"input_ids": torch.tensor([1, 2, 3]), "labels": torch.tensor([2, 3, 4])},
            {"input_ids": torch.tensor([5, 6]), "labels": torch.tensor([6, 7])},
        ]
        result = collator(batch)

        assert result["input_ids"].shape == (2, 3)
        assert result["labels"].shape == (2, 3)
        assert result["attention_mask"].shape == (2, 3)

        # Second item should be padded
        assert result["input_ids"][1, 2].item() == 0
        assert result["attention_mask"][1, 2].item() == 0
        assert result["labels"][1, 2].item() == -100


class TestDPOCollator:
    def test_pads_chosen_and_rejected(self):
        collator = DPOCollator(pad_token_id=0)
        batch = [
            {
                "chosen_input_ids": torch.tensor([1, 2, 3, 4]),
                "rejected_input_ids": torch.tensor([1, 2, 5]),
                "prompt_length": 2,
            },
        ]
        result = collator(batch)

        assert "chosen_input_ids" in result
        assert "rejected_input_ids" in result
        assert "chosen_attention_mask" in result
        assert "rejected_attention_mask" in result
        assert result["chosen_input_ids"].shape == result["rejected_input_ids"].shape
