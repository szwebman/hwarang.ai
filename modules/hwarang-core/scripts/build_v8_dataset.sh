#!/usr/bin/env bash
# v8 학습 데이터 통합 빌드 + 합성
#
# 사용:
#   cd /home/perseismore/hwarang.ai/modules/hwarang-core
#   bash scripts/build_v8_dataset.sh
#
# 결과:
#   data/sft/identity_v8.jsonl              3000
#   data/sft/base_consistency_v8.jsonl      1200
#   data/sft/ko_only_v8.jsonl               3500
#   data/sft/code_switch_block_v8.jsonl     1000
#   data/sft/pressure_v8.jsonl              2000
#   ───────────────────────────────────────────
#   data/sft/lora_v8_combined.jsonl   ≈19,000+ 라인 (oversample 적용)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/data/sft"
SCRIPTS="$ROOT/scripts/data"

mkdir -p "$DATA"

echo "=== [1/3] v8 빌더 5종 실행 ==="
python3 "$SCRIPTS/build_identity_v8.py"          --output "$DATA/identity_v8.jsonl"
python3 "$SCRIPTS/build_base_consistency_v8.py"  --output "$DATA/base_consistency_v8.jsonl"
python3 "$SCRIPTS/build_ko_only_v8.py"           --output "$DATA/ko_only_v8.jsonl"
python3 "$SCRIPTS/build_code_switch_block_v8.py" --output "$DATA/code_switch_block_v8.jsonl"
python3 "$SCRIPTS/build_pressure_v8.py"          --output "$DATA/pressure_v8.jsonl"

echo
echo "=== [2/3] 사후 검증 (validate 모드) ==="
python3 "$SCRIPTS/build_identity_v8.py"          --output "$DATA/identity_v8.jsonl"          --validate || true
python3 "$SCRIPTS/build_base_consistency_v8.py"  --output "$DATA/base_consistency_v8.jsonl"  --validate || true
python3 "$SCRIPTS/build_ko_only_v8.py"           --output "$DATA/ko_only_v8.jsonl"           --validate || true
python3 "$SCRIPTS/build_code_switch_block_v8.py" --output "$DATA/code_switch_block_v8.jsonl" --validate || true

echo
echo "=== [3/3] 통합 + oversample (정체성 누적 원칙) ==="
COMBINED="$DATA/lora_v8_combined.jsonl"
> "$COMBINED"

# v7 누적 데이터 (이전 라운드)
[ -f "$DATA/lora_v7_combined.jsonl" ] && cat "$DATA/lora_v7_combined.jsonl" >> "$COMBINED"

# identity 누적 (v3 → v7 → v8) — 신규일수록 oversample 강하게
for f in \
  "$DATA/identity_v3.jsonl" \
  "$DATA/identity_v7.jsonl" \
  "$DATA/identity_v7.jsonl" \
  "$DATA/identity_v8.jsonl" \
  "$DATA/identity_v8.jsonl" \
  "$DATA/identity_v8.jsonl" \
  "$DATA/base_consistency_v8.jsonl" \
  "$DATA/base_consistency_v8.jsonl" \
  "$DATA/ko_only_v8.jsonl" \
  "$DATA/ko_only_v8.jsonl" \
  "$DATA/code_switch_block_v8.jsonl" \
  "$DATA/pressure_v8.jsonl" \
  "$DATA/pressure_v8.jsonl" \
  "$DATA/hp_markup_v8.jsonl" ; do
  if [ -f "$f" ]; then
    cat "$f" >> "$COMBINED"
  else
    echo "⚠ skip (missing): $f"
  fi
done

# 셔플
shuf "$COMBINED" -o "$COMBINED"

LINES=$(wc -l < "$COMBINED")
echo
echo "=== 완료 ==="
echo "  combined: $COMBINED"
echo "  lines:    $LINES"
echo
echo "다음 단계: 학습 시작 (v7 학습과 동일한 qlora_hwarang.py 사용)"
echo "  python3 scripts/qlora_hwarang.py \\"
echo "    --model-path /mnt/nvme2/hwarang/models/Qwen2.5-32B-Instruct \\"
echo "    --data $COMBINED \\"
echo "    --output /mnt/nvme2/hwarang/lora_adapters/hwarang-general-v8 \\"
echo "    --lora-r 16 --lora-alpha 32 \\"
echo "    --epochs 4 \\"
echo "    --batch-size 1 --grad-accum 16 \\"
echo "    --max-length 2048"
echo
echo "(weight_decay=0.01, bf16, warmup, cosine LR 은 qlora_hwarang.py 에 이미 적용됨)"
