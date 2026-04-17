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
    echo "[EXAONE 4.5-33B] ⭐ 최신 한국어 + 멀티모달 - LG AI Research (2026)"
    echo "  용도: 법률, 세무, 한국어 일반 대화 + 이미지 이해"
    echo "  크기: ~69GB (FP16)"
    echo "  언어: 한국어, 영어, 스페인어, 독일어, 일본어, 베트남어"
    echo "  특징: 이미지 입력 지원 (image-text-to-text)"
    echo ""
    hf download LGAI-EXAONE/EXAONE-4.5-33B \
        --local-dir "$MODEL_DIR/exaone-4.5-33b"
    echo "  ✅ EXAONE 4.5-33B 다운로드 완료"
}

download_exaone_gguf() {
    echo ""
    echo "[EXAONE 4.5-33B GGUF] 양자화 버전 (llama.cpp용)"
    echo "  용도: 메모리 제한 환경에서 서빙"
    echo "  크기: ~35~45GB (4~6bit 양자화)"
    echo ""
    hf download LGAI-EXAONE/EXAONE-4.5-33B-GGUF \
        --local-dir "$MODEL_DIR/exaone-4.5-33b-gguf"
    echo "  ✅ EXAONE 4.5-33B GGUF 다운로드 완료"
}

download_exaone_35() {
    echo ""
    echo "[EXAONE 3.5-32B] 한국어 특화 - LG AI Research (구버전)"
    echo "  용도: 4.5 못 쓸 때 폴백"
    echo "  주의: gated 모델일 수 있음 - HuggingFace 로그인 필요"
    echo ""
    hf download LGAI-EXAONE/EXAONE-3.5-32B-Instruct \
        --local-dir "$MODEL_DIR/exaone-3.5-32b"
    echo "  ✅ EXAONE 3.5-32B 다운로드 완료"
}

download_qwen_coder() {
    echo ""
    echo "[Qwen3-Coder-Next] ⭐ 코딩 최신 - Alibaba (2026)"
    echo "  용도: 최고 성능 코딩 (qwen3_next 새 아키텍처)"
    echo "  크기: ~160GB (FP16, 40 shards × 4GB)"
    echo "  예상 VRAM: 4bit ~30-40GB (RTX 5090 1장으로 시도)"
    echo "  주의: VRAM 초과 시 --gpu-memory-utilization 조정 또는"
    echo "        CPU offload 필요할 수 있음. 안 되면 30B-A3B로 폴백."
    echo ""
    hf download Qwen/Qwen3-Coder-Next \
        --local-dir "$MODEL_DIR/qwen3-coder-next"
    echo "  ✅ Qwen3-Coder-Next 다운로드 완료"
    echo ""
    echo "  서빙 시도:"
    echo "  vllm serve $MODEL_DIR/qwen3-coder-next \\"
    echo "    --trust-remote-code --gpu-memory-utilization 0.95 \\"
    echo "    --max-model-len 32768 --quantization awq --port 8000"
    echo ""
    echo "  서빙 실패 시 폴백:"
    echo "  bash scripts/download_models.sh qwen-coder-30b"
}

download_qwen_coder_30b() {
    echo ""
    echo "[Qwen3-Coder-30B-A3B] 코딩 MoE - Alibaba (폴백용)"
    echo "  용도: Next 안 될 때 폴백 (MoE 3B 활성)"
    echo "  크기: ~60GB (FP16), ~15GB (4bit 서빙)"
    echo "  성능: RTX 5090에서 100~150 토큰/초"
    echo ""
    hf download Qwen/Qwen3-Coder-30B-A3B-Instruct \
        --local-dir "$MODEL_DIR/qwen3-coder-30b"
    echo "  ✅ Qwen3-Coder-30B-A3B 다운로드 완료"
}

download_qwen_coder_25() {
    echo ""
    echo "[Qwen2.5-Coder-32B] 코딩 구버전 - Alibaba (최종 폴백)"
    echo "  용도: Next와 30B 모두 문제있을 때만"
    echo "  크기: ~65GB (FP16), ~18GB (4bit)"
    echo ""
    hf download Qwen/Qwen2.5-Coder-32B-Instruct \
        --local-dir "$MODEL_DIR/qwen2.5-coder-32b"
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
    echo "  ✅ SOLAR-10.7B 다운로드 완료"
}

# ─── 실행 ─────────────────────────────────────────────────────

case "$TARGET" in
    exaone)
        download_exaone
        ;;
    exaone-gguf)
        download_exaone_gguf
        ;;
    exaone-35)
        download_exaone_35
        ;;
    exaone-32b)
        download_exaone_35  # 별칭
        ;;
    qwen-coder)
        download_qwen_coder
        ;;
    qwen-coder-30b)
        download_qwen_coder_30b
        ;;
    qwen-coder-25)
        download_qwen_coder_25
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
        echo "  deepseek-v3   ⭐ DeepSeek-V3 671B MoE (최강 코딩, ~350GB)"
        echo "  exaone        ⭐ EXAONE 4.5-33B (2026 최신, 멀티모달, ~69GB)"
        echo "  exaone-gguf   EXAONE 4.5-33B GGUF (양자화, ~35-45GB)"
        echo "  exaone-35     EXAONE 3.5-32B (구버전, gated)"
        echo "  qwen-coder    Qwen3-Coder-Next (160GB, 비추)"
        echo "  qwen-coder-30b Qwen3-Coder-30B-A3B (폴백, 빠름)"
        echo "  qwen-coder-25  Qwen2.5-Coder-32B (최종 폴백)"
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
