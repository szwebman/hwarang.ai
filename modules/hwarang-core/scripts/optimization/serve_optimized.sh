#!/bin/bash
# ============================================================
# Hwarang AI - 최적화 vLLM 서빙 스크립트
#
# 적용 최적화:
#   HSD  - Speculative Decoding (작은 모델이 draft, 큰 모델이 verify)
#   HLC  - Long Context (YaRN scaling으로 128K)
#   HPC  - Prefix Caching (반복 프롬프트 가속)
#   FA3  - Flash Attention 3 (VRAM 절감)
#
# 사용법:
#   bash scripts/optimization/serve_optimized.sh [모델]
# ============================================================

set -e

MODEL="${1:-qwen}"
MODEL_DIR="/mnt/nvme2/hwarang/models"
PORT="${PORT:-8000}"

case "$MODEL" in
    qwen|qwen32b)
        MAIN_MODEL="$MODEL_DIR/qwen2.5-32b-int4"
        DRAFT_MODEL=""  # 없으면 Speculative 비활성
        CONTEXT_LEN=131072   # 128K (Qwen2.5 네이티브)
        ;;
    qwen-coder)
        MAIN_MODEL="$MODEL_DIR/qwen2.5-coder-32b"
        DRAFT_MODEL=""
        CONTEXT_LEN=131072
        ;;
    exaone)
        MAIN_MODEL="$MODEL_DIR/exaone-3.5-32b"
        DRAFT_MODEL=""
        CONTEXT_LEN=32768
        ;;
    deepseek|deepseek-v3|v3)
        MAIN_MODEL="$MODEL_DIR/deepseek-v3"
        DRAFT_MODEL=""
        CONTEXT_LEN=163840   # 160K
        ;;
    qwen-speculative)
        # HSD: 큰 모델 + 작은 draft 모델 조합
        MAIN_MODEL="$MODEL_DIR/qwen2.5-32b-int4"
        DRAFT_MODEL="$MODEL_DIR/qwen2.5-1.5b"  # 작은 draft
        CONTEXT_LEN=32768
        ;;
    *)
        echo "사용법: bash scripts/optimization/serve_optimized.sh [qwen|qwen-coder|exaone|deepseek-v3|qwen-speculative]"
        exit 1
        ;;
esac

if [ ! -d "$MAIN_MODEL" ]; then
    echo "❌ 모델 경로 없음: $MAIN_MODEL"
    exit 1
fi

echo "============================================================"
echo " Hwarang AI - 최적화 vLLM 서빙"
echo "============================================================"
echo "  메인 모델:    $MAIN_MODEL"
echo "  Draft 모델:   ${DRAFT_MODEL:-(비활성)}"
echo "  컨텍스트:     $CONTEXT_LEN 토큰 (HLC)"
echo "  Prefix Cache: 활성 (HPC)"
echo "  Flash Attn:   자동 (vLLM 내장)"
echo "  포트:         $PORT"
echo "============================================================"

# vLLM 공통 옵션
VLLM_OPTS=(
    --port "$PORT"
    --trust-remote-code
    --gpu-memory-utilization 0.9
    --max-model-len "$CONTEXT_LEN"
    --enable-prefix-caching              # HPC: prefix KV 캐시 재사용
    --enforce-eager                       # 안정성 (컴파일 문제 회피)
    --dtype bfloat16
)

# Speculative Decoding (HSD)
if [ -n "$DRAFT_MODEL" ] && [ -d "$DRAFT_MODEL" ]; then
    VLLM_OPTS+=(
        --speculative-model "$DRAFT_MODEL"
        --num-speculative-tokens 5        # 한번에 5토큰 예측
        --use-v2-block-manager
    )
    echo "  🚀 Speculative Decoding 활성화"
fi

# YaRN Long Context (HLC)
if [ "$CONTEXT_LEN" -gt 32768 ]; then
    VLLM_OPTS+=(
        --rope-scaling '{"type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'
    )
    echo "  🔍 YaRN Long Context (32K → ${CONTEXT_LEN}) 활성화"
fi

# 실행
echo ""
echo "실행 명령어:"
echo "vllm serve $MAIN_MODEL ${VLLM_OPTS[@]}"
echo ""

exec vllm serve "$MAIN_MODEL" "${VLLM_OPTS[@]}"
