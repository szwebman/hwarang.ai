"""Training datasets for pretraining, SFT, and DPO."""

from __future__ import annotations

import json
from pathlib import Path

import torch
from torch.utils.data import Dataset


class PretrainDataset(Dataset):
    """Dataset for language model pretraining.

    Reads tokenized data stored as .bin files (uint16 numpy arrays).
    """

    def __init__(self, data_path: str | Path, seq_length: int = 2048):
        import numpy as np

        self.seq_length = seq_length
        self.data = np.memmap(str(data_path), dtype=np.uint16, mode="r")
        self.num_samples = len(self.data) // seq_length

    def __len__(self) -> int:
        return self.num_samples

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        start = idx * self.seq_length
        end = start + self.seq_length + 1  # +1 for labels shift

        chunk = self.data[start:end].astype("int64")
        x = torch.from_numpy(chunk[:-1])
        y = torch.from_numpy(chunk[1:])

        return {"input_ids": x, "labels": y}


class SFTDataset(Dataset):
    """Dataset for supervised fine-tuning.

    Reads JSONL files with 'messages' field (ChatML format).
    Labels are masked for instruction tokens (only compute loss on responses).
    """

    IGNORE_INDEX = -100

    def __init__(
        self,
        data_path: str | Path,
        tokenizer,
        max_length: int = 2048,
    ):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.examples: list[dict] = []

        with open(data_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.examples.append(json.loads(line))

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        example = self.examples[idx]
        messages = example["messages"]

        input_ids: list[int] = [self.tokenizer.bos_token_id]
        labels: list[int] = [self.IGNORE_INDEX]

        im_start = self.tokenizer.token_to_id.get("<|im_start|>")
        im_end = self.tokenizer.token_to_id.get("<|im_end|>")

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            # Encode role header
            if im_start is not None:
                input_ids.append(im_start)
                labels.append(self.IGNORE_INDEX)

            role_tokens = self.tokenizer.encode(role + "\n", add_special_tokens=False)
            input_ids.extend(role_tokens)
            labels.extend([self.IGNORE_INDEX] * len(role_tokens))

            # Encode content
            content_tokens = self.tokenizer.encode(content, add_special_tokens=False)
            input_ids.extend(content_tokens)

            # Only compute loss on assistant responses
            if role == "assistant":
                labels.extend(content_tokens)
            else:
                labels.extend([self.IGNORE_INDEX] * len(content_tokens))

            if im_end is not None:
                input_ids.append(im_end)
                labels.append(im_end if role == "assistant" else self.IGNORE_INDEX)

        # Add EOS
        input_ids.append(self.tokenizer.eos_token_id)
        labels.append(self.tokenizer.eos_token_id)

        # Truncate
        input_ids = input_ids[: self.max_length]
        labels = labels[: self.max_length]

        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


class DPODataset(Dataset):
    """Dataset for Direct Preference Optimization.

    Reads JSONL with 'prompt', 'chosen', 'rejected' fields.
    """

    def __init__(
        self,
        data_path: str | Path,
        tokenizer,
        max_length: int = 2048,
    ):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.examples: list[dict] = []

        with open(data_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.examples.append(json.loads(line))

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        example = self.examples[idx]
        prompt = example["prompt"]
        chosen = example["chosen"]
        rejected = example["rejected"]

        # Encode prompt + chosen
        prompt_ids = self.tokenizer.encode(prompt, add_special_tokens=True)
        chosen_ids = self.tokenizer.encode(chosen, add_special_tokens=False)
        rejected_ids = self.tokenizer.encode(rejected, add_special_tokens=False)

        chosen_input = prompt_ids + chosen_ids + [self.tokenizer.eos_token_id]
        rejected_input = prompt_ids + rejected_ids + [self.tokenizer.eos_token_id]

        # Truncate
        chosen_input = chosen_input[: self.max_length]
        rejected_input = rejected_input[: self.max_length]

        prompt_len = len(prompt_ids)

        return {
            "chosen_input_ids": torch.tensor(chosen_input, dtype=torch.long),
            "rejected_input_ids": torch.tensor(rejected_input, dtype=torch.long),
            "prompt_length": prompt_len,
        }
