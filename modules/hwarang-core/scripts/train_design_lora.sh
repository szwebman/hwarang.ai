#!/bin/bash
# ============================================================
# Hwarang AI - 웹디자인 LoRA 학습 스크립트
#
# Qwen3-Coder-30B-A3B 기반으로 디자인 특화 LoRA 학습.
# 학습 완료 후 vLLM에 --enable-lora로 등록하면
# HNTL이 domain=coding 중 "design" 요청에 자동 활성화.
#
# 전제 조건:
#   1. Qwen3-Coder-30B 다운로드 완료
#   2. QLoRA 학습 환경 (transformers, peft, trl, bitsandbytes)
#
# 사용법:
#   bash scripts/train_design_lora.sh
# ============================================================

set -e

MODEL_DIR="/mnt/nvme2/hwarang/models"
DATA_DIR="/mnt/nvme2/hwarang/data/sft"
ADAPTER_DIR="/mnt/nvme2/hwarang/lora_adapters"

BASE_MODEL="$MODEL_DIR/qwen3-coder-30b"
DATA_FILE="$DATA_DIR/web_design.jsonl"
OUTPUT="$ADAPTER_DIR/hwarang-design-v1"

# ─── 체크 ──────────────────────────────────────────────────
if [ ! -d "$BASE_MODEL" ]; then
    echo "❌ 베이스 모델 없음: $BASE_MODEL"
    echo "   먼저 다운로드: bash scripts/download_models.sh qwen-coder-30b"
    exit 1
fi

# ─── 데이터 수집 (없으면 자동) ─────────────────────────────
if [ ! -f "$DATA_FILE" ]; then
    echo "📦 웹디자인 데이터 수집..."
    mkdir -p "$DATA_DIR"
    python scripts/data/collect_web_design.py \
        --output "$DATA_FILE" \
        --max-samples 10000
fi

DATA_COUNT=$(wc -l < "$DATA_FILE")
echo "📊 학습 데이터: $DATA_COUNT 개"

# ─── QLoRA 학습 ────────────────────────────────────────────
echo ""
echo "============================================================"
echo " Hwarang AI 웹디자인 LoRA 학습 (Qwen3-Coder-30B)"
echo "============================================================"
echo "  베이스 모델: $BASE_MODEL"
echo "  데이터:      $DATA_FILE ($DATA_COUNT 개)"
echo "  출력:        $OUTPUT"
echo "  에포크:      3"
echo "  LoRA r=16, alpha=32"
echo "  예상 시간:   ~4~6시간 (RTX 5090 기준)"
echo "============================================================"
echo ""

python scripts/qlora_qwen.py \
    --model-path "$BASE_MODEL" \
    --data "$DATA_FILE" \
    --output "$OUTPUT" \
    --epochs 3 \
    --batch-size 2 \
    --grad-accum 8 \
    --lr 2e-4 \
    --lora-r 16 \
    --lora-alpha 32 \
    --max-length 4096

echo ""
echo "✅ 학습 완료!"
echo ""
echo "============================================================"
echo " 다음 단계:"
echo "============================================================"
echo ""
echo "1. vLLM에 LoRA 등록:"
echo "   vllm serve $BASE_MODEL \\"
echo "     --enable-lora \\"
echo "     --max-loras 4 \\"
echo "     --max-lora-rank 16 \\"
echo "     --lora-modules design=$OUTPUT \\"
echo "     --port 8000"
echo ""
echo "2. 관리자 페이지에서 AIModel 활성화:"
echo "   - name: hwarang-design"
echo "   - backendId: design (vLLM에 등록된 LoRA 이름)"
echo "   - category: coding"
echo "   - minPlan: null (Free부터 사용 가능)"
echo ""
echo "3. HNTL이 자동 라우팅:"
echo "   '디자인/UI/페이지/컴포넌트' 키워드 질문 →"
echo "   hwarang-design LoRA 활성화"
echo ""
