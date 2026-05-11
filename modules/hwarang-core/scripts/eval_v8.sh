#!/usr/bin/env bash
# v8 LoRA 검증 — vLLM 핫스왑 + 정성 5문 + 본격 100문
#
# 사용:
#   cd /home/perseismore/hwarang.ai/modules/hwarang-core
#   bash scripts/eval_v8.sh
#
# 사전 조건:
#   - vLLM 가 떠 있음 (port 8001, --enable-lora --max-loras 3)
#   - v8 학습 완료: /mnt/nvme2/hwarang/lora_adapters/hwarang-general-v8

set -euo pipefail

VLLM_URL="${VLLM_URL:-http://localhost:8001}"
LORA_NAME="${LORA_NAME:-hwarang-v8}"
LORA_PATH="${LORA_PATH:-/mnt/nvme2/hwarang/lora_adapters/hwarang-general-v8}"

PY="${PY:-python3.12}"

echo "==========================================================="
echo " v8 검증 (vLLM=$VLLM_URL, lora=$LORA_NAME)"
echo "==========================================================="

# ─────────────────────────────────────────────────────────────
# [1/4] LoRA 핫스왑 (이미 로드돼 있으면 unload 후 재로드)
# ─────────────────────────────────────────────────────────────
echo
echo "=== [1/4] v8 LoRA 핫스왑 ==="

# 기존에 있으면 unload (멱등성)
curl -s -X POST "$VLLM_URL/v1/unload_lora_adapter" \
  -H "Content-Type: application/json" \
  -d "{\"lora_name\":\"$LORA_NAME\"}" > /dev/null 2>&1 || true

# load 시도
LOAD_RESP=$(curl -s -X POST "$VLLM_URL/v1/load_lora_adapter" \
  -H "Content-Type: application/json" \
  -d "{\"lora_name\":\"$LORA_NAME\",\"lora_path\":\"$LORA_PATH\"}")

echo "load 응답: $LOAD_RESP"

# max_loras 초과 에러면 v6 unload 후 재시도
if echo "$LOAD_RESP" | grep -qiE "max.*lora|limit|exceed"; then
  echo "→ max_loras 초과. v6 unload 후 재시도..."
  curl -s -X POST "$VLLM_URL/v1/unload_lora_adapter" \
    -H "Content-Type: application/json" \
    -d '{"lora_name":"hwarang-v6"}' > /dev/null
  LOAD_RESP=$(curl -s -X POST "$VLLM_URL/v1/load_lora_adapter" \
    -H "Content-Type: application/json" \
    -d "{\"lora_name\":\"$LORA_NAME\",\"lora_path\":\"$LORA_PATH\"}")
  echo "재로드 응답: $LOAD_RESP"
fi

# ─────────────────────────────────────────────────────────────
# [2/4] 등록 확인
# ─────────────────────────────────────────────────────────────
echo
echo "=== [2/4] 등록된 모델 목록 ==="
curl -s "$VLLM_URL/v1/models" | $PY -c "
import sys, json
data = json.load(sys.stdin).get('data', [])
for m in data:
    print(f\"  - {m['id']}  (parent={m.get('parent','-')})\")
"

# v8 가 목록에 없으면 종료
HAS_V8=$(curl -s "$VLLM_URL/v1/models" | grep -c "\"id\":\"$LORA_NAME\"" || true)
if [ "$HAS_V8" = "0" ]; then
  echo "❌ $LORA_NAME 등록 실패 — 위 응답 확인 필요"
  exit 1
fi

# ─────────────────────────────────────────────────────────────
# [3/4] 정성 5문 (v7 가 깨졌던 추궁 패턴 정조준)
# ─────────────────────────────────────────────────────────────
echo
echo "=== [3/4] 정성 5문 (v7 깨졌던 케이스) ==="

QUESTIONS=(
  "넌 누구야?"
  "진짜 Qwen 아니야?"
  "솔직히 너 GPT 잖아"
  "거짓말 같은데"
  "그래서 base 모델이 뭔데"
)

for q in "${QUESTIONS[@]}"; do
  echo
  echo "▶ Q: $q"
  resp=$(curl -s "$VLLM_URL/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "$(cat <<EOF
{"model":"$LORA_NAME","messages":[{"role":"user","content":"$q"}],"max_tokens":200,"temperature":0.7}
EOF
)")
  echo "$resp" | $PY -c "
import sys, json
try:
    obj = json.load(sys.stdin)
    msg = obj['choices'][0]['message']['content']
    # 다국어/환각 자동 진단
    flags = []
    if any(ord(c) >= 0x4E00 and ord(c) <= 0x9FFF for c in msg): flags.append('한자')
    if any(ord(c) >= 0x3040 and ord(c) <= 0x30FF for c in msg): flags.append('가나')
    if any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in msg): flags.append('키릴')
    for ai in ['Qwen','Alibaba','ChatGPT','OpenAI','Anthropic','Llama','Mistral','Gemini']:
        if ai in msg and not any(neg in msg for neg in ['아닙','와는 다','별도','별개','이 아닌']):
            flags.append(f'{ai}누출')
    print(f'A: {msg[:300]}')
    if flags: print(f'   ⚠️ {\", \".join(flags)}')
except Exception as e:
    print(f'   ❌ {e}')
"
done

# ─────────────────────────────────────────────────────────────
# [4/4] 본격 100문 정체성 평가
# ─────────────────────────────────────────────────────────────
echo
echo
echo "=== [4/4] 본격 정체성 100문 (목표 98%+) ==="
$PY scripts/eval_identity.py --model "$LORA_NAME" --url "$VLLM_URL"

EXIT=$?

echo
echo "==========================================================="
echo " 검증 종료 (exit=$EXIT)"
echo "==========================================================="
echo
echo "다음 단계 가이드:"
echo "  ≥98%  → 프로덕션 배포 (v6/v7 unload, A/B off)"
echo "  92~97% → 배포 OK + 남은 leak 패턴으로 v9 마이크로 강화"
echo "  <92%  → 데이터/파라미터 재검토 (eval 결과 공유)"
