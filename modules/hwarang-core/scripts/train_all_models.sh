#!/bin/bash
# ============================================================
# Hwarang AI - 멀티 모델 QLoRA 학습 스크립트
#
# 사용법:
#   bash scripts/train_all_models.sh [모델명]
#
# 예시:
#   bash scripts/train_all_models.sh qwen-coder   # 코딩 모델만
#   bash scripts/train_all_models.sh exaone        # EXAONE만
#   bash scripts/train_all_models.sh all           # 전체 순차 학습
# ============================================================

set -e

MODEL_DIR="/mnt/nvme2/hwarang/models"
ADAPTER_DIR="/mnt/nvme2/hwarang/lora_adapters"
DATA_DIR="/mnt/nvme2/hwarang/data/sft"

# 데이터 경로
CODE_DATA="$DATA_DIR/all_sft_cleaned.jsonl"        # 코딩 SFT
LEGAL_DATA="$DATA_DIR/legal_tax.jsonl"              # 법률/세무 SFT
ALL_DATA="$DATA_DIR/all_sft_cleaned.jsonl"          # 전체 SFT

EPOCHS=3
BATCH=2
GRAD_ACCUM=8
LR="2e-4"
LORA_R=16
LORA_ALPHA=32

echo "============================================================"
echo " Hwarang AI 멀티 모델 QLoRA 학습"
echo "============================================================"

TARGET="${1:-list}"

train_model() {
    local MODEL_PATH="$1"
    local DATA_PATH="$2"
    local OUTPUT_NAME="$3"
    local MODEL_LABEL="$4"

    echo ""
    echo "────────────────────────────────────────────────────────"
    echo " 학습 시작: $MODEL_LABEL"
    echo " 모델: $MODEL_PATH"
    echo " 데이터: $DATA_PATH"
    echo " 출력: $ADAPTER_DIR/$OUTPUT_NAME"
    echo "────────────────────────────────────────────────────────"

    if [ ! -d "$MODEL_PATH" ]; then
        echo "  ❌ 모델 경로 없음: $MODEL_PATH"
        echo "  먼저 다운로드하세요: bash scripts/download_models.sh"
        return 1
    fi

    if [ ! -f "$DATA_PATH" ]; then
        echo "  ❌ 데이터 경로 없음: $DATA_PATH"
        echo "  먼저 데이터 파이프라인을 실행하세요: bash scripts/data/run_pipeline.sh"
        return 1
    fi

    python scripts/qlora_qwen.py \
        --model-path "$MODEL_PATH" \
        --data "$DATA_PATH" \
        --output "$ADAPTER_DIR/$OUTPUT_NAME" \
        --epochs $EPOCHS \
        --batch-size $BATCH \
        --grad-accum $GRAD_ACCUM \
        --lr $LR \
        --lora-r $LORA_R \
        --lora-alpha $LORA_ALPHA

    echo "  ✅ 학습 완료: $ADAPTER_DIR/$OUTPUT_NAME"
}

case "$TARGET" in
    qwen)
        train_model "$MODEL_DIR/qwen2.5-32b-int4" "$ALL_DATA" \
            "hwarang-general-v2" "Qwen2.5-32B (일반)"
        ;;
    qwen-coder)
        train_model "$MODEL_DIR/qwen3-coder-next" "$CODE_DATA" \
            "hwarang-code-v1" "Qwen2.5-Coder-32B (코딩)"
        ;;
    exaone)
        train_model "$MODEL_DIR/exaone-3.5-32b" "$LEGAL_DATA" \
            "hwarang-legal-v1" "EXAONE 3.5-32B (법률/세무)"
        ;;
    exaone-7b)
        train_model "$MODEL_DIR/exaone-3.0-7.8b" "$LEGAL_DATA" \
            "hwarang-legal-7b-v1" "EXAONE 3.0-7.8B (법률/세무 경량)"
        ;;
    deepseek)
        train_model "$MODEL_DIR/deepseek-coder-v2-lite" "$CODE_DATA" \
            "hwarang-code-ds-v1" "DeepSeek-Coder-V2-Lite (코딩)"
        ;;
    solar)
        train_model "$MODEL_DIR/solar-10.7b" "$ALL_DATA" \
            "hwarang-general-solar-v1" "SOLAR-10.7B (한국어 일반)"
        ;;
    coding)
        echo "코딩 모델 순차 학습..."
        train_model "$MODEL_DIR/qwen3-coder-next" "$CODE_DATA" \
            "hwarang-code-v1" "Qwen2.5-Coder-32B (코딩)"
        train_model "$MODEL_DIR/deepseek-coder-v2-lite" "$CODE_DATA" \
            "hwarang-code-ds-v1" "DeepSeek-Coder-V2-Lite (코딩)"
        ;;
    korean)
        echo "한국어 모델 순차 학습..."
        train_model "$MODEL_DIR/exaone-3.5-32b" "$LEGAL_DATA" \
            "hwarang-legal-v1" "EXAONE 3.5-32B (법률/세무)"
        train_model "$MODEL_DIR/solar-10.7b" "$ALL_DATA" \
            "hwarang-general-solar-v1" "SOLAR-10.7B (한국어 일반)"
        ;;
    all)
        echo "전체 모델 순차 학습 (약 200시간+ 소요)..."
        train_model "$MODEL_DIR/qwen3-coder-next" "$CODE_DATA" \
            "hwarang-code-v1" "Qwen2.5-Coder-32B (코딩)"
        train_model "$MODEL_DIR/exaone-3.5-32b" "$LEGAL_DATA" \
            "hwarang-legal-v1" "EXAONE 3.5-32B (법률/세무)"
        train_model "$MODEL_DIR/deepseek-coder-v2-lite" "$CODE_DATA" \
            "hwarang-code-ds-v1" "DeepSeek-Coder-V2-Lite (코딩)"
        train_model "$MODEL_DIR/solar-10.7b" "$ALL_DATA" \
            "hwarang-general-solar-v1" "SOLAR-10.7B (한국어 일반)"
        echo ""
        echo "============================================================"
        echo " 전체 학습 완료!"
        echo " LoRA 어댑터: $ADAPTER_DIR/"
        echo "============================================================"
        ;;
    list|*)
        echo ""
        echo "학습 가능한 모델:"
        echo ""
        echo "  qwen          Qwen2.5-32B 일반 (현재 학습 중인 것 재학습)"
        echo "  qwen-coder    Qwen2.5-Coder-32B 코딩 전용"
        echo "  exaone        EXAONE 3.5-32B 법률/세무"
        echo "  exaone-7b     EXAONE 3.0-7.8B 법률/세무 (경량)"
        echo "  deepseek      DeepSeek-Coder-V2-Lite 코딩"
        echo "  solar         SOLAR-10.7B 한국어 일반"
        echo ""
        echo "  coding        코딩 모델 전체 (qwen-coder + deepseek)"
        echo "  korean        한국어 모델 전체 (exaone + solar)"
        echo "  all           전부 순차 학습"
        echo ""
        echo "사용법: bash scripts/train_all_models.sh [모델명]"
        echo ""
        echo "현재 다운로드된 모델:"
        ls -d "$MODEL_DIR"/*/ 2>/dev/null || echo "  (없음 - 먼저 download_models.sh 실행)"
        echo ""
        echo "현재 학습된 어댑터:"
        ls -d "$ADAPTER_DIR"/*/ 2>/dev/null || echo "  (없음)"
        echo ""
        ;;
esac
