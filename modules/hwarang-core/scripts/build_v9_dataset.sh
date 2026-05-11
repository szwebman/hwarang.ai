#!/usr/bin/env bash
# v9 학습 데이터 통합 빌드 + 합성
#
# 목적: v8 (정체성 100%) 의 약점 — 긴 응답에서 한국어→중국어 누출 — 보강
#       정체성 데이터는 v8 누적 유지, 긴 응답 한국어 강제 (ko_long_v9) 추가
#
# 사용:
#   cd /home/perseismore/hwarang.ai/modules/hwarang-core
#   bash scripts/build_v9_dataset.sh
#
# 결과:
#   data/sft/ko_long_v9.jsonl              4000 (긴 응답 한국어 강제)
#   data/sft/lora_v9_combined.jsonl   ≈70,000+ 라인 (v8 누적 + v9 oversample)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/data/sft"
SCRIPTS="$ROOT/scripts/data"

mkdir -p "$DATA"

echo "=== [1/3] v9 신규 빌더 실행 ==="
python3 "$SCRIPTS/build_ko_long_v9.py" --output "$DATA/ko_long_v9.jsonl"

echo
echo "=== [2/3] 사후 검증 (validate 모드) ==="
python3 "$SCRIPTS/build_ko_long_v9.py" --output "$DATA/ko_long_v9.jsonl" --validate || true

echo
echo "=== [3/3] 통합 + oversample (v8 누적 + v9 신규 강조) ==="
COMBINED="$DATA/lora_v9_combined.jsonl"
> "$COMBINED"

# v8 누적 데이터 (정체성 100% 효과 보존)
if [ -f "$DATA/lora_v8_combined.jsonl" ]; then
  cat "$DATA/lora_v8_combined.jsonl" >> "$COMBINED"
else
  echo "⚠ lora_v8_combined.jsonl 없음 — v8 효과 누적 안 됨!"
  # fallback: v8 의 구성요소들을 다시 합침
  for f in \
    "$DATA/identity_v3.jsonl" \
    "$DATA/identity_v7.jsonl" "$DATA/identity_v7.jsonl" \
    "$DATA/identity_v8.jsonl" "$DATA/identity_v8.jsonl" "$DATA/identity_v8.jsonl" \
    "$DATA/base_consistency_v8.jsonl" "$DATA/base_consistency_v8.jsonl" \
    "$DATA/ko_only_v8.jsonl" "$DATA/ko_only_v8.jsonl" \
    "$DATA/code_switch_block_v8.jsonl" \
    "$DATA/pressure_v8.jsonl" "$DATA/pressure_v8.jsonl" \
    "$DATA/hp_markup_v8.jsonl"; do
    [ -f "$f" ] && cat "$f" >> "$COMBINED"
  done
fi

# v9 신규 (긴 응답 한국어) — 3배 oversample (이번 라운드 핵심)
for _ in 1 2 3; do
  [ -f "$DATA/ko_long_v9.jsonl" ] && cat "$DATA/ko_long_v9.jsonl" >> "$COMBINED"
done

# 셔플
shuf "$COMBINED" -o "$COMBINED"

LINES=$(wc -l < "$COMBINED")
echo
echo "=== 완료 ==="
echo "  combined: $COMBINED"
echo "  lines:    $LINES"
echo
echo "다음 단계: 학습 시작 (v8 와 동일한 qlora_hwarang.py)"
echo "  python3 scripts/qlora_hwarang.py \\"
echo "    --model-path /mnt/nvme2/hwarang/models/hwarang-v5-fp16-merged \\"
echo "    --data $COMBINED \\"
echo "    --output /mnt/nvme2/hwarang/lora_adapters/hwarang-general-v9 \\"
echo "    --lora-r 16 --lora-alpha 32 \\"
echo "    --epochs 4 \\"
echo "    --batch-size 1 --grad-accum 16 \\"
echo "    --max-length 2048"
echo
echo "(weight_decay=0.01, bf16, warmup, cosine LR 은 qlora_hwarang.py 에 이미 적용됨)"
