#!/bin/bash
# ============================================================
# Hwarang AI - 데이터 수집/정제/검증 전체 파이프라인
#
# 사용법:
#   cd modules/hwarang-core
#   bash scripts/data/run_pipeline.sh
#
# 단계:
#   1. 한국어 코딩 데이터 수집
#   2. 법률/세무 데이터 수집
#   3. 기존 데이터와 병합
#   4. 데이터 정제 (중국어 제거, 중복 제거 등)
#   5. 품질 검증
#   6. DPO 쌍 생성
#   7. 최종 검증
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)/data"
SFT_DIR="$DATA_DIR/sft"
DPO_DIR="$DATA_DIR/dpo"

echo "============================================================"
echo " Hwarang AI 데이터 파이프라인"
echo " 데이터 경로: $DATA_DIR"
echo "============================================================"

mkdir -p "$SFT_DIR" "$DPO_DIR"

# ─── 1. 한국어 코딩 데이터 수집 ─────────────────────────────────
echo ""
echo "[1/7] 한국어 코딩 데이터 수집..."
python "$SCRIPT_DIR/collect_korean_code.py" \
    --output "$SFT_DIR/korean_code.jsonl" \
    --max-samples 50000

# ─── 2. 법률/세무 데이터 수집 ────────────────────────────────────
echo ""
echo "[2/7] 법률/세무 데이터 수집..."
python "$SCRIPT_DIR/collect_legal_tax.py" \
    --output "$SFT_DIR/legal_tax.jsonl" \
    --max-samples 30000

# ─── 3. 전체 데이터 병합 ─────────────────────────────────────────
echo ""
echo "[3/7] 전체 데이터 병합..."
MERGED="$SFT_DIR/all_merged.jsonl"
cat /dev/null > "$MERGED"

# 기존 SFT 데이터가 있으면 포함
if [ -f "$SFT_DIR/all_sft.jsonl" ]; then
    echo "  기존 데이터 포함: all_sft.jsonl"
    cat "$SFT_DIR/all_sft.jsonl" >> "$MERGED"
fi

# 새로 수집한 데이터 추가
for f in "$SFT_DIR/korean_code.jsonl" "$SFT_DIR/legal_tax.jsonl"; do
    if [ -f "$f" ]; then
        echo "  추가: $(basename $f)"
        cat "$f" >> "$MERGED"
    fi
done

TOTAL=$(wc -l < "$MERGED")
echo "  → 총 ${TOTAL}줄 병합 완료"

# ─── 4. 데이터 정제 ──────────────────────────────────────────────
echo ""
echo "[4/7] 데이터 정제 (중국어 제거, 중복 제거, 길이 필터)..."
python "$SCRIPT_DIR/clean_data.py" \
    --input "$MERGED" \
    --output "$SFT_DIR/all_sft_cleaned.jsonl" \
    --rejected "$SFT_DIR/rejected.jsonl" \
    --chinese-threshold 0.10

# ─── 5. SFT 데이터 검증 ──────────────────────────────────────────
echo ""
echo "[5/7] SFT 데이터 품질 검증..."
python "$SCRIPT_DIR/validate_data.py" \
    --input "$SFT_DIR/all_sft_cleaned.jsonl" \
    --format sft

# ─── 6. DPO 쌍 생성 ──────────────────────────────────────────────
echo ""
echo "[6/7] DPO 쌍 데이터 생성..."
python "$SCRIPT_DIR/generate_dpo.py" \
    --input "$SFT_DIR/all_sft_cleaned.jsonl" \
    --output "$DPO_DIR/dpo_pairs.jsonl" \
    --max-pairs 10000

# ─── 7. DPO 데이터 검증 ──────────────────────────────────────────
echo ""
echo "[7/7] DPO 데이터 검증..."
python "$SCRIPT_DIR/validate_data.py" \
    --input "$DPO_DIR/dpo_pairs.jsonl" \
    --format dpo

# ─── 요약 ────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " 파이프라인 완료!"
echo "============================================================"
echo ""
echo " SFT 데이터:"
echo "   원본: $MERGED"
echo "   정제: $SFT_DIR/all_sft_cleaned.jsonl"
echo "   제거: $SFT_DIR/rejected.jsonl"
echo ""
echo " DPO 데이터:"
echo "   쌍 데이터: $DPO_DIR/dpo_pairs.jsonl"
echo ""
echo " 다음 단계:"
echo "   1. SFT 학습: python scripts/qlora_qwen.py --data $SFT_DIR/all_sft_cleaned.jsonl ..."
echo "   2. DPO 학습: python scripts/align.py --data $DPO_DIR/dpo_pairs.jsonl ..."
echo "============================================================"
