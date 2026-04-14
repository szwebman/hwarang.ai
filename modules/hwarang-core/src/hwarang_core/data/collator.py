"""Data collators for dynamic padding."""

from __future__ import annotations

import torch


class PaddingCollator:
    """Dynamically pads sequences to the longest in the batch."""

    def __init__(self, pad_token_id: int = 0, label_pad_id: int = -100):
        self.pad_token_id = pad_token_id
        self.label_pad_id = label_pad_id

    def __call__(self, batch: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
        max_len = max(item["input_ids"].size(0) for item in batch)

        input_ids = []
        labels = []
        attention_mask = []

        for item in batch:
            seq_len = item["input_ids"].size(0)
            pad_len = max_len - seq_len

            input_ids.append(
                torch.cat([item["input_ids"], torch.full((pad_len,), self.pad_token_id)])
            )
            attention_mask.append(
                torch.cat([torch.ones(seq_len), torch.zeros(pad_len)])
            )

            if "labels" in item:
                labels.append(
                    torch.cat([item["labels"], torch.full((pad_len,), self.label_pad_id)])
                )

        result = {
            "input_ids": torch.stack(input_ids).long(),
            "attention_mask": torch.stack(attention_mask).long(),
        }
        if labels:
            result["labels"] = torch.stack(labels).long()

        return result


class DPOCollator:
    """Collator for DPO training pairs."""

    def __init__(self, pad_token_id: int = 0):
        self.pad_token_id = pad_token_id

    def __call__(self, batch: list[dict]) -> dict[str, torch.Tensor]:
        chosen_ids = [item["chosen_input_ids"] for item in batch]
        rejected_ids = [item["rejected_input_ids"] for item in batch]
        prompt_lengths = [item["prompt_length"] for item in batch]

        max_chosen = max(x.size(0) for x in chosen_ids)
        max_rejected = max(x.size(0) for x in rejected_ids)
        max_len = max(max_chosen, max_rejected)

        def pad_list(tensors: list[torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
            padded = []
            masks = []
            for t in tensors:
                pad_len = max_len - t.size(0)
                padded.append(torch.cat([t, torch.full((pad_len,), self.pad_token_id)]))
                masks.append(torch.cat([torch.ones(t.size(0)), torch.zeros(pad_len)]))
            return torch.stack(padded).long(), torch.stack(masks).long()

        c_ids, c_mask = pad_list(chosen_ids)
        r_ids, r_mask = pad_list(rejected_ids)

        return {
            "chosen_input_ids": c_ids,
            "chosen_attention_mask": c_mask,
            "rejected_input_ids": r_ids,
            "rejected_attention_mask": r_mask,
            "prompt_lengths": torch.tensor(prompt_lengths, dtype=torch.long),
        }
