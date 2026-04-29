#!/bin/bash
# 화랑 LoRA 재학습 — multi-turn tool calling 강화
# 기존 hwarang-general-v1 LoRA 위에 추가 학습 또는 새로 학습.
# 핵심: tools_multiturn.jsonl 200 샘플을 기존 데이터와 합쳐 v2 LoRA 생성.

set -euo pipefail

# ============================================================
# 환경변수 (오버라이드 가능)
# ============================================================
DATA_DIR=${DATA_DIR:-./data/sft}
OUTPUT=${OUTPUT:-./lora_adapters/hwarang-general-v2}
BASE=${BASE:-/mnt/nvme2/hwarang/models/hwarang-v5-awq}
LORA_R=${LORA_R:-64}
LORA_ALPHA=${LORA_ALPHA:-128}
MAX_LEN=${MAX_LEN:-4096}
VLLM_URL=${VLLM_URL:-http://localhost:8001}

# ============================================================
# 1. 데이터 생성
# ============================================================
echo "[1/5] multi-turn 데이터 생성"
python scripts/data/build_tools_multiturn.py --output "$DATA_DIR/tools_multiturn.jsonl"

# ============================================================
# 2. 기존 데이터와 합치기
#    기존 (filesystem + complex + shell_git + coding_all) + 신규 multi-turn
# ============================================================
echo "[2/5] 데이터 합치기"
COMBINED="$DATA_DIR/lora_v2_combined.jsonl"
> "$COMBINED"

for f in \
    "$DATA_DIR/tools_filesystem.jsonl" \
    "$DATA_DIR/tools_complex.jsonl" \
    "$DATA_DIR/tools_shell_git.jsonl" \
    "$DATA_DIR/coding_all.jsonl" \
    "$DATA_DIR/tools_multiturn.jsonl"; do
    if [ -f "$f" ]; then
        cat "$f" >> "$COMBINED"
        echo "  추가: $f ($(wc -l < "$f") 줄)"
    else
        echo "  스킵: $f (없음)"
    fi
done

# ============================================================
# 3. 셔플
# ============================================================
echo "[3/5] 셔플"
shuf "$COMBINED" -o "$COMBINED"
echo "  최종: $(wc -l < "$COMBINED") 샘플 → $COMBINED"

# ============================================================
# 4. LoRA 학습
# ============================================================
echo "[4/5] LoRA 학습 시작"
python scripts/lora_train.py \
    --checkpoint "$BASE" \
    --data "$COMBINED" \
    --output "$OUTPUT" \
    --r "$LORA_R" --alpha "$LORA_ALPHA" \
    --target-modules q_proj k_proj v_proj o_proj gate_proj up_proj down_proj \
    --max-length "$MAX_LEN"

echo "  학습 완료: $OUTPUT"

# ============================================================
# 5. vLLM 핫 리로드 가이드 (수동)
# ============================================================
echo "[5/5] vLLM 핫 리로드 명령:"
echo ""
echo "  # 기존 LoRA 언로드 (필요 시):"
echo "  curl -X POST $VLLM_URL/v1/unload_lora_adapter \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"lora_name\":\"hwarang\"}'"
echo ""
echo "  # 신규 LoRA 로드:"
echo "  curl -X POST $VLLM_URL/v1/load_lora_adapter \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"lora_name\":\"hwarang-v2\",\"lora_path\":\"$OUTPUT\"}'"
echo ""
echo "  # 평가 스크립트 (10건 multi-turn 시나리오):"
echo "  python scripts/eval_tool_calling.py --model hwarang-v2 --url $VLLM_URL"
