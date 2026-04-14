"""Data format parsers for instruction-tuning datasets."""

from __future__ import annotations

import json
from pathlib import Path


def load_jsonl(path: str | Path) -> list[dict]:
    """Load a JSONL file."""
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def convert_alpaca_to_chatml(example: dict) -> dict:
    """Convert Alpaca format to ChatML messages.

    Alpaca format: {"instruction": ..., "input": ..., "output": ...}
    ChatML format: {"messages": [{"role": ..., "content": ...}, ...]}
    """
    instruction = example["instruction"]
    input_text = example.get("input", "")
    output = example["output"]

    user_content = instruction
    if input_text:
        user_content += f"\n\n{input_text}"

    return {
        "messages": [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": output},
        ]
    }


def convert_sharegpt_to_chatml(example: dict) -> dict:
    """Convert ShareGPT format to ChatML.

    ShareGPT: {"conversations": [{"from": "human"/"gpt", "value": ...}]}
    """
    messages = []
    role_map = {"human": "user", "gpt": "assistant", "system": "system"}

    for turn in example.get("conversations", []):
        role = role_map.get(turn["from"], turn["from"])
        messages.append({"role": role, "content": turn["value"]})

    return {"messages": messages}


def convert_dataset(
    input_path: str | Path,
    output_path: str | Path,
    source_format: str = "alpaca",
) -> int:
    """Convert a dataset from one format to ChatML JSONL.

    Args:
        input_path: Input JSONL file.
        output_path: Output JSONL file in ChatML format.
        source_format: "alpaca" or "sharegpt".

    Returns:
        Number of examples converted.
    """
    converter = {
        "alpaca": convert_alpaca_to_chatml,
        "sharegpt": convert_sharegpt_to_chatml,
    }[source_format]

    data = load_jsonl(input_path)
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for example in data:
            try:
                converted = converter(example)
                f.write(json.dumps(converted, ensure_ascii=False) + "\n")
                count += 1
            except (KeyError, TypeError):
                continue

    return count
