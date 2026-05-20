#!/usr/bin/env bash
# v11 학습 데이터 통합 빌드 + 합성
#
# 목적: v10 의 긴 prose 누출 (3/6) 해결 — markdown 분석/평가 형태 한국어 prose 대폭 확대
#       정체성 데이터는 v8_clean 사용 (이미 한자 잔여 정제됨)
#
# 사용:
#   cd /home/perseismore/hwarang.ai/modules/hwarang-core
#   bash scripts/build_v11_dataset.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/data/sft"
SCRIPTS="$ROOT/scripts/data"

mkdir -p "$DATA"

echo "=== [1/4] v11 신규 빌더 실행 (10,000건) ==="
python3 "$SCRIPTS/build_ko_prose_v11.py" --output "$DATA/ko_prose_v11.jsonl"

echo
echo "=== [2/4] 사후 검증 (validate 모드) ==="
python3 "$SCRIPTS/build_ko_prose_v11.py" --output "$DATA/ko_prose_v11.jsonl" --validate || true

echo
echo "=== [3/4] v8_clean 누적 데이터 확인 ==="
if [ ! -f "$DATA/lora_v8_clean.jsonl" ]; then
  echo "⚠ lora_v8_clean.jsonl 없음 — v9/v10 라운드에서 만들었던 정제 파일 필요"
  echo "  fallback: v8_combined 에서 한자 행 제거 후 재생성"
  python3 << 'PYEOF'
import json, re
CJK = re.compile(r"[一-龥]")
CYR = re.compile(r"[Ѐ-ӿ]")
KANA = re.compile(r"[぀-ヿ]")
NEG = re.compile(r"(아닙니다|아닙니|와는 다|이 아닌|별도|별개|아니에요)")
kept, kept_neg, dropped = 0, 0, 0
with open("data/sft/lora_v8_combined.jsonl") as fin, \
     open("data/sft/lora_v8_clean.jsonl", "w") as fout:
    for line in fin:
        try:
            obj = json.loads(line)
            text = "\n".join(m.get("content","") for m in obj.get("messages", []))
            has_foreign = bool(CJK.search(text) or CYR.search(text) or KANA.search(text))
            if not has_foreign:
                fout.write(line); kept += 1
            elif NEG.search(text):
                fout.write(line); kept_neg += 1
            else:
                dropped += 1
        except Exception:
            dropped += 1
print(f"v8_clean 재생성: kept_clean={kept}, kept_neg={kept_neg}, dropped={dropped}")
PYEOF
fi

LINES_V8_CLEAN=$(wc -l < "$DATA/lora_v8_clean.jsonl")
echo "  lora_v8_clean.jsonl: $LINES_V8_CLEAN 라인"

echo
echo "=== [4/4] v11 합성 (oversample 균형) ==="
COMBINED="$DATA/lora_v11_combined.jsonl"
> "$COMBINED"

# v8 정제 누적 (정체성 100% 효과 보존)
cat "$DATA/lora_v8_clean.jsonl" >> "$COMBINED"

# ko_long_v9 1배 (v10 회고: 3배는 과했고 0배는 부족, 1배가 균형)
[ -f "$DATA/ko_long_v9.jsonl" ] && cat "$DATA/ko_long_v9.jsonl" >> "$COMBINED"

# ko_prose_v11 2배 (이번 라운드 핵심 — 양 크지만 균형 위해 2배)
for _ in 1 2; do
  cat "$DATA/ko_prose_v11.jsonl" >> "$COMBINED"
done

# 셔플
shuf "$COMBINED" -o "$COMBINED"

LINES=$(wc -l < "$COMBINED")
HANJA=$(grep -c "[一-龥]" "$COMBINED" || true)
echo
echo "=== 완료 ==="
echo "  combined: $COMBINED"
echo "  lines:    $LINES"
echo "  한자 잔여: $HANJA (부정 맥락 보존분 — 50건 미만이면 정상)"
echo
echo "다음 단계: 학습 시작 (v8/v10 와 동일한 qlora_hwarang.py)"
echo "  python3.12 scripts/qlora_hwarang.py \\"
echo "    --model-path /mnt/nvme2/hwarang/models/hwarang-v5-fp16-merged \\"
echo "    --data $COMBINED \\"
echo "    --output /mnt/nvme2/hwarang/lora_adapters/hwarang-general-v11 \\"
echo "    --lora-r 16 --lora-alpha 32 \\"
echo "    --epochs 4 \\"
echo "    --batch-size 1 --grad-accum 16 \\"
echo "    --max-length 2048"
