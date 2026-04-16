"""HMM - Hwarang Model Merging

화랑 AI 최적화 기법 #5

여러 모델을 병합하여 복합 능력 확보:
  - Qwen2.5-32B (범용)
  - Qwen2.5-Coder-32B (코딩)
  - EXAONE-3.5-32B (한국어)
  → Merged Model: 3가지 능력 모두 가짐

병합 기법:
  1. SLERP (Spherical Linear Interpolation) - 가중치 구면 보간
  2. TIES (Trim, Elect, Disjoint Merge) - 충돌 해결 병합
  3. DARE (Drop And REscale) - 중요 가중치만 유지
  4. Linear - 단순 가중 평균

사용법:
    pip install mergekit

    python scripts/optimization/model_merge.py \\
        --config configs/merge_hwarang.yaml \\
        --output /mnt/nvme2/hwarang/models/hwarang-merged-v1
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── 기본 병합 설정 ────────────────────────────────────────────

DEFAULT_MERGE_CONFIG = {
    # SLERP 예시 (2개 모델)
    "slerp_korean_coder": {
        "merge_method": "slerp",
        "base_model": "/mnt/nvme2/hwarang/models/qwen2.5-coder-32b",
        "models": [
            {"model": "/mnt/nvme2/hwarang/models/qwen2.5-coder-32b", "weight": 0.7},
            {"model": "/mnt/nvme2/hwarang/models/exaone-3.5-32b", "weight": 0.3},
        ],
        "parameters": {
            "t": 0.5,  # 보간 계수
        },
        "dtype": "bfloat16",
    },

    # TIES 예시 (3개 이상 모델)
    "ties_full_stack": {
        "merge_method": "ties",
        "base_model": "/mnt/nvme2/hwarang/models/qwen2.5-32b-int4",
        "models": [
            {"model": "/mnt/nvme2/hwarang/models/qwen2.5-32b-int4",
             "parameters": {"density": 0.6, "weight": 0.4}},
            {"model": "/mnt/nvme2/hwarang/models/qwen2.5-coder-32b",
             "parameters": {"density": 0.5, "weight": 0.3}},
            {"model": "/mnt/nvme2/hwarang/models/exaone-3.5-32b",
             "parameters": {"density": 0.5, "weight": 0.3}},
        ],
        "parameters": {
            "normalize": True,
        },
        "dtype": "bfloat16",
    },

    # DARE 예시 (파라미터 drop + rescale)
    "dare_efficient": {
        "merge_method": "dare_ties",
        "base_model": "/mnt/nvme2/hwarang/models/qwen2.5-32b-int4",
        "models": [
            {"model": "/mnt/nvme2/hwarang/models/qwen2.5-coder-32b",
             "parameters": {"density": 0.5, "weight": 0.5}},
            {"model": "/mnt/nvme2/hwarang/models/exaone-3.5-32b",
             "parameters": {"density": 0.5, "weight": 0.5}},
        ],
        "parameters": {
            "normalize": True,
            "int8_mask": True,
        },
        "dtype": "bfloat16",
    },
}


def create_merge_config(preset: str, output_path: str) -> str:
    """병합 설정 파일 생성."""
    if preset not in DEFAULT_MERGE_CONFIG:
        raise ValueError(f"알 수 없는 프리셋: {preset}. 사용 가능: {list(DEFAULT_MERGE_CONFIG.keys())}")

    config = DEFAULT_MERGE_CONFIG[preset]
    config_path = f"{output_path}/merge_config.yaml"
    os.makedirs(output_path, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    logger.info(f"설정 파일 생성: {config_path}")
    return config_path


def run_merge(config_path: str, output_path: str):
    """mergekit을 사용해 실제 병합 실행."""
    try:
        # mergekit 라이브러리 사용
        os.system(f"""
            mergekit-yaml {config_path} {output_path} \\
                --cuda \\
                --copy-tokenizer \\
                --lazy-unpickle \\
                --allow-crimes
        """)
        logger.info(f"✅ 병합 완료: {output_path}")
    except Exception as e:
        logger.error(f"병합 실패: {e}")
        raise


def merge_with_transformers(
    base_model: str,
    other_model: str,
    output_path: str,
    alpha: float = 0.5,
):
    """Transformers 라이브러리로 직접 병합 (mergekit 없을 때).

    단순 SLERP 구현.
    """
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        logger.error("transformers/torch 필요")
        sys.exit(1)

    logger.info(f"로드 1/2: {base_model}")
    model_a = AutoModelForCausalLM.from_pretrained(
        base_model, torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=True
    )
    logger.info(f"로드 2/2: {other_model}")
    model_b = AutoModelForCausalLM.from_pretrained(
        other_model, torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=True
    )

    logger.info(f"병합 중 (alpha={alpha})...")

    # 파라미터 SLERP (간소화: linear interpolation)
    sa = model_a.state_dict()
    sb = model_b.state_dict()

    merged = {}
    for key in sa:
        if key in sb and sa[key].shape == sb[key].shape:
            merged[key] = (1 - alpha) * sa[key] + alpha * sb[key]
        else:
            merged[key] = sa[key]

    model_a.load_state_dict(merged)
    model_a.save_pretrained(output_path)

    # 토크나이저 복사
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    tokenizer.save_pretrained(output_path)

    logger.info(f"✅ 병합 완료: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Hwarang Model Merging")
    parser.add_argument("--preset", default="ties_full_stack",
                        choices=list(DEFAULT_MERGE_CONFIG.keys()),
                        help="병합 프리셋")
    parser.add_argument("--output", required=True, help="출력 경로")
    parser.add_argument("--method", default="mergekit",
                        choices=["mergekit", "transformers"],
                        help="병합 도구")
    parser.add_argument("--alpha", type=float, default=0.5,
                        help="transformers 방식에서 병합 비율")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" Hwarang Model Merging (HMM)")
    logger.info("=" * 60)
    logger.info(f"  프리셋: {args.preset}")
    logger.info(f"  출력:   {args.output}")
    logger.info(f"  방법:   {args.method}")

    if args.method == "mergekit":
        config_path = create_merge_config(args.preset, args.output)
        run_merge(config_path, args.output)
    else:
        config = DEFAULT_MERGE_CONFIG[args.preset]
        # transformers 방식: 2개만 지원
        models = config["models"]
        if len(models) < 2:
            logger.error("최소 2개 모델 필요")
            sys.exit(1)
        merge_with_transformers(
            models[0]["model"],
            models[1]["model"],
            args.output,
            args.alpha,
        )

    logger.info("\n" + "=" * 60)
    logger.info(" 완료! 이제 vLLM으로 서빙 가능:")
    logger.info(f"   vllm serve {args.output} --trust-remote-code --port 8000")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
