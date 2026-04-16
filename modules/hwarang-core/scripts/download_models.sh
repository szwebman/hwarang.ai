#!/bin/bash
# ============================================================
# Hwarang AI - 모델 다운로드 스크립트
#
# 사용법:
#   bash scripts/download_models.sh [모델명]
#
# 예시:
#   bash scripts/download_models.sh all          # 전체 다운로드
#   bash scripts/download_models.sh exaone       # EXAONE만
#   bash scripts/download_models.sh qwen-coder   # Qwen Coder만
#
# 저장 경로: /mnt/nvme2/hwarang/models/
# ============================================================

set -e

MODEL_DIR="/mnt/nvme2/hwarang/models"
mkdir -p "$MODEL_DIR"

echo "============================================================"
echo " Hwarang AI 모델 다운로드"
echo " 저장 경로: $MODEL_DIR"
echo "============================================================"

TARGET="${1:-list}"

# ─── 모델 목록 ────────────────────────────────────────────────

download_exaone() {
    echo ""
    echo "[EXAONE 3.0 32B] 한국어 특화 - LG AI Research"
    echo "  용도: 법률, 세무, 한국어 일반 대화"
    echo "  크기: ~65GB (FP16), ~18GB (4bit)"
    echo ""
    hf download LGAI-EXAONE/EXAONE-3.0-7.8B-Instruct \
        --local-dir "$MODEL_DIR/exaone-3.0-7.8b" \
        --local-dir-use-symlinks False
    echo "  ✅ EXAONE 3.0 7.8B 다운로드 완료"
    echo ""
    echo "  [참고] 32B 버전은 별도 요청 필요 (LGAI-EXAONE/EXAONE-3.5-32B-Instruct)"
    echo "  huggingface-cli login 후 접근 가능"
}

download_exaone_32b() {
    echo ""
    echo "[EXAONE 3.5 32B] 한국어 특화 - LG AI Research (최신)"
    echo "  용도: 법률, 세무, 한국어 일반 대화"
    echo "  주의: HuggingFace 로그인 + 라이선스 동의 필요"
    echo ""
    hf download LGAI-EXAONE/EXAONE-3.5-32B-Instruct \
        --local-dir "$MODEL_DIR/exaone-3.5-32b" \
        --local-dir-use-symlinks False
    echo "  ✅ EXAONE 3.5 32B 다운로드 완료"
}

download_qwen_coder() {
    echo ""
    echo "[Qwen2.5-Coder-32B] 코딩 전용 - Alibaba"
    echo "  용도: 코딩 특화 (일반 Qwen보다 코딩 성능 높음)"
    echo "  크기: ~65GB (FP16), ~18GB (4bit)"
    echo ""
    hf download Qwen/Qwen2.5-Coder-32B-Instruct \
        --local-dir "$MODEL_DIR/qwen2.5-coder-32b" \
        --local-dir-use-symlinks False
    echo "  ✅ Qwen2.5-Coder-32B 다운로드 완료"
}

download_deepseek_coder() {
    echo ""
    echo "[DeepSeek-Coder-V2-Lite] 코딩 특화 MoE - DeepSeek"
    echo "  용도: 코딩 (MoE라 실행 효율 좋음)"
    echo "  크기: ~16B 활성 파라미터"
    echo ""
    hf download deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct \
        --local-dir "$MODEL_DIR/deepseek-coder-v2-lite" \
        --local-dir-use-symlinks False
    echo "  ✅ DeepSeek-Coder-V2-Lite 다운로드 완료"
}

download_starcoder2() {
    echo ""
    echo "[StarCoder2-15B] 코딩 - BigCode"
    echo "  용도: 600+ 프로그래밍 언어, 가벼움"
    echo "  크기: ~30GB (FP16), ~9GB (4bit)"
    echo ""
    hf download bigcode/starcoder2-15b-instruct-v0.1 \
        --local-dir "$MODEL_DIR/starcoder2-15b" \
        --local-dir-use-symlinks False
    echo "  ✅ StarCoder2-15B 다운로드 완료"
}

download_deepseek_v3() {
    echo ""
    echo "[DeepSeek-V3-0324] 현존 오픈소스 최강 - DeepSeek"
    echo "  용도: 고급 코딩, 복잡한 추론, 일반 대화 (GPT-4o급)"
    echo "  구조: MoE 671B 전체 / 37B 활성 파라미터"
    echo "  크기: ~350GB (FP16), ~22GB (4bit 서빙)"
    echo "  주의: 다운로드 용량이 크므로 디스크 여유 확인!"
    echo ""
    hf download deepseek-ai/DeepSeek-V3-0324 \
        --local-dir "$MODEL_DIR/deepseek-v3" \
        --local-dir-use-symlinks False
    echo "  ✅ DeepSeek-V3 다운로드 완료"
    echo ""
    echo "  서빙 명령어:"
    echo "  vllm serve $MODEL_DIR/deepseek-v3 \\"
    echo "    --trust-remote-code --gpu-memory-utilization 0.9 \\"
    echo "    --max-model-len 4096 --port 8000"
}

download_solar() {
    echo ""
    echo "[SOLAR-10.7B] 한국어 - Upstage"
    echo "  용도: 한국어 일반 (가벼움)"
    echo "  크기: ~21GB (FP16), ~6GB (4bit)"
    echo ""
    hf download upstage/SOLAR-10.7B-Instruct-v1.0 \
        --local-dir "$MODEL_DIR/solar-10.7b" \
        --local-dir-use-symlinks False
    echo "  ✅ SOLAR-10.7B 다운로드 완료"
}

# ─── 실행 ─────────────────────────────────────────────────────

case "$TARGET" in
    exaone)
        download_exaone
        ;;
    exaone-32b)
        download_exaone_32b
        ;;
    qwen-coder)
        download_qwen_coder
        ;;
    deepseek)
        download_deepseek_coder
        ;;
    deepseek-v3)
        download_deepseek_v3
        ;;
    starcoder)
        download_starcoder2
        ;;
    solar)
        download_solar
        ;;
    all)
        download_deepseek_v3
        download_exaone
        download_qwen_coder
        download_deepseek_coder
        download_starcoder2
        download_solar
        echo ""
        echo "============================================================"
        echo " 전체 다운로드 완료!"
        echo "============================================================"
        ;;
    coding)
        echo "코딩 모델 전체 다운로드..."
        download_qwen_coder
        download_deepseek_coder
        download_starcoder2
        ;;
    korean)
        echo "한국어 모델 전체 다운로드..."
        download_exaone
        download_solar
        ;;
    list|*)
        echo ""
        echo "사용 가능한 모델:"
        echo ""
        echo "  deepseek-v3  ⭐ DeepSeek-V3 671B MoE (현존 최강, ~350GB)"
        echo "  exaone       EXAONE 3.0 7.8B (한국어, LG)"
        echo "  exaone-32b   EXAONE 3.5 32B (한국어 최강, 로그인 필요)"
        echo "  qwen-coder   Qwen2.5-Coder-32B (코딩 최강)"
        echo "  deepseek     DeepSeek-Coder-V2-Lite (코딩 MoE)"
        echo "  starcoder    StarCoder2-15B (600+ 언어)"
        echo "  solar        SOLAR-10.7B (한국어, 가벼움)"
        echo ""
        echo "  coding       코딩 모델 전체 (qwen-coder + deepseek + starcoder)"
        echo "  korean       한국어 모델 전체 (exaone + solar)"
        echo "  all          전체 다운로드 (V3 포함)"
        echo ""
        echo "사용법: bash scripts/download_models.sh [모델명]"
        echo ""
        echo "현재 다운로드된 모델:"
        ls -d "$MODEL_DIR"/*/ 2>/dev/null || echo "  (없음)"
        echo ""
        ;;
esac
