"""Vision - 이미지 이해 (멀티모달).

텍스트뿐 아니라 이미지도 입력으로 받아서 처리합니다.

방식:
1. Vision Encoder (CLIP/SigLIP)로 이미지 → 벡터
2. Projection Layer로 LLM 차원에 맞춤
3. 텍스트 토큰과 이미지 토큰을 결합하여 LLM에 입력

예시:
  사용자: [코드 스크린샷] + "이 코드의 버그를 찾아줘"
  → 이미지 인코딩 → LLM → "3번째 줄에서 인덱스 에러가 있습니다"
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class VisionEncoder(nn.Module):
    """이미지를 벡터로 인코딩.

    사전학습된 CLIP/SigLIP 모델을 사용합니다.
    """

    def __init__(
        self,
        model_name: str = "openai/clip-vit-large-patch14-336",
        output_dim: int = 4096,  # LLM hidden_size에 맞춤
    ):
        super().__init__()
        self.model_name = model_name
        self.output_dim = output_dim
        self._encoder = None
        self._processor = None

        # 이미지 토큰을 LLM 차원으로 변환하는 프로젝션
        # CLIP ViT-L/14: 1024 → 4096
        self.projection = nn.Sequential(
            nn.Linear(1024, output_dim),
            nn.GELU(),
            nn.Linear(output_dim, output_dim),
        )

    def load_encoder(self):
        """CLIP 인코더 로드."""
        try:
            from transformers import CLIPVisionModel, CLIPProcessor
            self._encoder = CLIPVisionModel.from_pretrained(self.model_name)
            self._processor = CLIPProcessor.from_pretrained(self.model_name)
            self._encoder.eval()
            for p in self._encoder.parameters():
                p.requires_grad = False
            logger.info(f"Vision Encoder 로드: {self.model_name}")
        except ImportError:
            logger.error("transformers 필요: pip install transformers")
        except Exception as e:
            logger.error(f"Vision Encoder 로드 실패: {e}")

    def encode_image(self, image) -> torch.Tensor:
        """이미지 → 벡터.

        Args:
            image: PIL.Image 또는 파일 경로

        Returns:
            image_features: (1, num_patches, output_dim)
        """
        if self._encoder is None:
            self.load_encoder()

        if isinstance(image, (str, Path)):
            from PIL import Image
            image = Image.open(image).convert("RGB")

        inputs = self._processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.projection[0].weight.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._encoder(**inputs)
            # (batch, num_patches, 1024)
            image_features = outputs.last_hidden_state

        # 프로젝션: 1024 → LLM hidden_size
        projected = self.projection(image_features)
        return projected

    def forward(self, images) -> torch.Tensor:
        return self.encode_image(images)


class VisionLanguageModel:
    """Vision + Language 통합 모델.

    텍스트 토큰과 이미지 토큰을 결합하여 LLM에 입력합니다.
    """

    def __init__(self, llm, vision_encoder: VisionEncoder):
        self.llm = llm
        self.vision = vision_encoder

        # 특수 토큰
        self.image_token = "<|image|>"
        self.image_start = "<|image_start|>"
        self.image_end = "<|image_end|>"

    def prepare_inputs(
        self,
        text: str,
        images: list = None,
        tokenizer=None,
    ) -> dict:
        """텍스트 + 이미지를 모델 입력으로 변환.

        텍스트에서 <|image|> 위치에 이미지 토큰을 삽입합니다.
        """
        if images is None or tokenizer is None:
            # 텍스트만
            input_ids = tokenizer.encode(text, add_special_tokens=True)
            return {"input_ids": torch.tensor([input_ids])}

        # 이미지 인코딩
        image_features = []
        for img in images:
            feat = self.vision.encode_image(img)  # (1, num_patches, hidden)
            image_features.append(feat)

        # 텍스트 토큰화 (<|image|>를 특수 토큰으로)
        parts = text.split(self.image_token)
        all_embeddings = []

        embed_layer = self.llm.model.embed_tokens

        for i, part in enumerate(parts):
            if part:
                ids = tokenizer.encode(part, add_special_tokens=(i == 0))
                text_emb = embed_layer(torch.tensor([ids]))
                all_embeddings.append(text_emb)

            if i < len(image_features):
                all_embeddings.append(image_features[i])

        if all_embeddings:
            combined = torch.cat(all_embeddings, dim=1)
            return {"inputs_embeds": combined}

        return {}
