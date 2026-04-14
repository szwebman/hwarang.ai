#!/bin/bash
#
# Hwarang 데이터 수집 마스터 스크립트
#
# 동시에 실행:
# 1. 공개 데이터셋 다운로드 (한국어 + 코드 + SFT + DPO)
# 2. GitHub 한국 저장소 크롤링
# 3. 한국 기술블로그 스크래이핑
#
# 사용법:
#   ./scripts/data/run_all.sh
#
# 종료:
#   tmux kill-session -t hwarang_data

set -e

# ============================================================
# 환경 확인
# ============================================================

echo "🚀 Hwarang 데이터 수집 시작"
echo "=========================================="

# tmux 확인
if ! command -v tmux &> /dev/null; then
    echo "❌ tmux가 필요합니다: sudo apt install tmux"
    exit 1
fi

# Python 패키지 확인
if ! python -c "import datasets" 2>/dev/null; then
    echo "❌ datasets 패키지 필요: pip install datasets tqdm huggingface_hub"
    exit 1
fi

# GitHub Token 확인
if [ -z "$GITHUB_TOKEN" ]; then
    echo "⚠️  GITHUB_TOKEN이 설정되지 않음 (GitHub 크롤러 건너뜀)"
    SKIP_GITHUB=1
else
    SKIP_GITHUB=0
fi

# Hugging Face 로그인 확인 (OSCAR 등 인증 필요)
if [ -z "$HF_TOKEN" ]; then
    echo "⚠️  HF_TOKEN이 설정되지 않음 (일부 데이터셋 접근 제한)"
fi

# 데이터 디렉토리 생성
DATA_DIR="${DATA_DIR:-data}"
mkdir -p "$DATA_DIR"/{raw/{github,blogs,public},processed,final}

echo "  📁 데이터 디렉토리: $DATA_DIR"
echo "  🔑 GitHub Token: $([ -n "$GITHUB_TOKEN" ] && echo "✅" || echo "❌")"
echo "  🔑 HF Token:     $([ -n "$HF_TOKEN" ] && echo "✅" || echo "❌")"
echo ""

# ============================================================
# tmux 세션 생성
# ============================================================

SESSION="hwarang_data"

# 기존 세션 종료
tmux kill-session -t $SESSION 2>/dev/null || true

# 새 세션 (분할 화면)
tmux new-session -d -s $SESSION -n monitor

# 윈도우 1: 모니터링 대시보드
tmux send-keys -t $SESSION:monitor "python scripts/data/monitor.py --data-dir $DATA_DIR" C-m

# 윈도우 2: 공개 데이터셋 - 한국어 (가장 큼, 가장 먼저)
tmux new-window -t $SESSION -n datasets-ko
tmux send-keys -t $SESSION:datasets-ko \
    "python scripts/data/download_all.py --stage pretrain-ko --output $DATA_DIR" C-m

# 윈도우 3: 공개 데이터셋 - 코드
tmux new-window -t $SESSION -n datasets-code
tmux send-keys -t $SESSION:datasets-code \
    "python scripts/data/download_all.py --stage pretrain-code --output $DATA_DIR" C-m

# 윈도우 4: 공개 데이터셋 - SFT
tmux new-window -t $SESSION -n datasets-sft
tmux send-keys -t $SESSION:datasets-sft \
    "python scripts/data/download_all.py --stage sft --output $DATA_DIR" C-m

# 윈도우 5: 공개 데이터셋 - DPO
tmux new-window -t $SESSION -n datasets-dpo
tmux send-keys -t $SESSION:datasets-dpo \
    "python scripts/data/download_all.py --stage dpo --output $DATA_DIR" C-m

# 윈도우 6: GitHub 크롤러 (Token 있을 때만)
if [ "$SKIP_GITHUB" -eq 0 ]; then
    tmux new-window -t $SESSION -n crawler-github
    tmux send-keys -t $SESSION:crawler-github \
        "python scripts/data/github_crawler.py --output $DATA_DIR/raw/github" C-m
fi

# 윈도우 7: 블로그 스크래퍼
tmux new-window -t $SESSION -n crawler-blogs
tmux send-keys -t $SESSION:crawler-blogs \
    "python scripts/data/blog_scraper.py --output $DATA_DIR/raw/blogs" C-m

# ============================================================
# 안내
# ============================================================

echo "✅ 모든 파이프라인이 백그라운드에서 시작되었습니다"
echo ""
echo "윈도우 목록:"
echo "  1. monitor         - 실시간 진행 상황"
echo "  2. datasets-ko     - 한국어 Pretrain 데이터셋"
echo "  3. datasets-code   - 코드 Pretrain 데이터셋"
echo "  4. datasets-sft    - SFT 데이터셋"
echo "  5. datasets-dpo    - DPO 데이터셋"
if [ "$SKIP_GITHUB" -eq 0 ]; then
    echo "  6. crawler-github  - GitHub 한국 저장소 크롤러"
fi
echo "  7. crawler-blogs   - 한국 기술블로그 스크래퍼"
echo ""
echo "tmux 사용법:"
echo "  세션 접속:    tmux attach -t $SESSION"
echo "  윈도우 전환:  Ctrl+B, [숫자]"
echo "  세션 분리:    Ctrl+B, D"
echo "  세션 종료:    tmux kill-session -t $SESSION"
echo ""
echo "지금 모니터에 접속하시려면:"
echo "  tmux attach -t $SESSION:monitor"
