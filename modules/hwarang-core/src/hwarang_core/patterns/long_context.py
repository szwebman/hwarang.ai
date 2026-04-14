"""Long Context - 128K+ 컨텍스트 지원.

기본 4K 컨텍스트를 128K 이상으로 확장합니다.

기법:
1. RoPE 스케일링 (NTK-aware) - 추론 시 위치 인코딩 확장
2. Sliding Window Attention - 긴 문서를 청크로 나눠 처리
3. Context Compression - 긴 컨텍스트를 요약해서 압축
"""

from __future__ import annotations

import math
import logging
import torch

logger = logging.getLogger(__name__)


def apply_ntk_rope_scaling(
    rope_theta: float = 10000.0,
    original_max_pos: int = 4096,
    target_max_pos: int = 131072,
    scaling_factor: float | None = None,
) -> float:
    """NTK-aware RoPE 스케일링.

    학습 때 4K였던 모델을 128K로 확장합니다.
    추가 학습 없이 추론만으로 가능 (약간의 품질 저하).

    Returns:
        새로운 rope_theta 값
    """
    if scaling_factor is None:
        scaling_factor = target_max_pos / original_max_pos

    new_theta = rope_theta * (scaling_factor ** (2.0 / (64 - 2)))
    logger.info(f"RoPE 스케일링: {original_max_pos} → {target_max_pos} "
               f"(theta: {rope_theta} → {new_theta:.0f})")
    return new_theta


def sliding_window_process(
    text: str,
    window_size: int = 4096,
    overlap: int = 512,
    summarize_fn=None,
) -> list[dict]:
    """긴 텍스트를 슬라이딩 윈도우로 처리.

    Args:
        text: 긴 입력 텍스트
        window_size: 한 번에 처리할 토큰 수
        overlap: 윈도우 간 겹침
        summarize_fn: 각 윈도우 결과를 요약하는 함수

    Returns:
        윈도우별 처리 결과 리스트
    """
    words = text.split()
    windows = []

    for i in range(0, len(words), window_size - overlap):
        chunk = " ".join(words[i:i + window_size])
        windows.append({
            "text": chunk,
            "start": i,
            "end": min(i + window_size, len(words)),
        })

    return windows


def compress_context(
    messages: list[dict],
    max_tokens: int = 4096,
    keep_recent: int = 3,
) -> list[dict]:
    """긴 대화를 압축 (오래된 것 요약).

    최근 N턴은 유지, 나머지는 요약으로 대체.

    Args:
        messages: 대화 메시지 리스트
        max_tokens: 최대 토큰 수
        keep_recent: 최근 유지할 턴 수

    Returns:
        압축된 메시지 리스트
    """
    if len(messages) <= keep_recent + 1:  # system + recent
        return messages

    system = [m for m in messages if m["role"] == "system"]
    others = [m for m in messages if m["role"] != "system"]

    recent = others[-keep_recent:]
    old = others[:-keep_recent]

    # 오래된 대화 요약
    summary_text = "[이전 대화 요약]\n"
    for m in old:
        content_preview = m["content"][:100] + "..." if len(m["content"]) > 100 else m["content"]
        summary_text += f"- {m['role']}: {content_preview}\n"

    compressed = system + [{"role": "system", "content": summary_text}] + recent
    return compressed
