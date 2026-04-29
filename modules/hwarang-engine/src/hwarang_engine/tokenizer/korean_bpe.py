"""Korean BPE Tokenizer — Layer 1.

mecab + sentencepiece 결합. 한국어 평균 토큰 30% 절약 목표.
영어/한자/이모지 mixed corpus 호환. fallback 으로 byte-level BPE.

실 구현은 Phase 4.1 에서:
  1. mecab 으로 형태소 분석 → subword 단위 추출
  2. sentencepiece 로 BPE 학습
  3. vocab merge (mecab tokens + sentencepiece pieces)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TokenizerConfig:
    vocab_size: int = 64_000
    use_mecab: bool = True
    fallback_byte_level: bool = True
    max_length: int = 8192


class KoreanBPETokenizer:
    """현재는 stub. 실 구현은 Phase 4.1 vLLM fork 단계에서."""

    def __init__(self, config: Optional[TokenizerConfig] = None):
        self.config = config or TokenizerConfig()
        # TODO Phase 4.1: mecab + sentencepiece 모델 로드
        self._vocab: dict[str, int] = {}

    def encode(self, text: str) -> list[int]:
        # TODO Phase 4.1: 형태소 분석 → BPE → token id
        raise NotImplementedError("Korean BPE encode — 실 구현은 Phase 4.1")

    def decode(self, ids: list[int]) -> str:
        raise NotImplementedError("Korean BPE decode — 실 구현은 Phase 4.1")

    @property
    def vocab_size(self) -> int:
        return self.config.vocab_size
