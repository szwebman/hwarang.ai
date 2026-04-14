# Mac Mini M시리즈 클러스터 구성 가이드

## 추천 구성

### 소규모 (개인/스타트업)

```
Mac Mini #1 (M4 Pro 48GB)  → API Server + Redis + PostgreSQL
Mac Mini #2 (M4 Pro 48GB)  → Worker (hwarang-small, hwarang-medium)
Mac Mini #3 (M4 Pro 48GB)  → Worker (hwarang-small, hwarang-medium)

예상 비용: ~750만원
예상 처리량: ~30-50 req/s (hwarang-small)
전력: ~150W 총 (월 전기세 ~2만원)
```

### 중규모 (서비스 운영)

```
Mac Mini #1 (M4 Pro 24GB)  → API Server + Web UI (GPU 불필요)
Mac Mini #2 (M4 Max 128GB) → Worker (hwarang-large 1.3B)
Mac Mini #3 (M4 Max 128GB) → Worker (hwarang-large 1.3B)
Mac Mini #4 (M4 Pro 48GB)  → Worker (hwarang-small, 빠른 응답용)
Mac Mini #5 (M4 Pro 48GB)  → Worker (hwarang-small, 빠른 응답용)
Mac Studio (M4 Ultra 192GB) → Worker (7B+ 대형 모델)

예상 비용: ~2500만원
예상 처리량: ~100+ req/s (혼합)
```

### 모델 크기별 필요 메모리

| 모델 | 파라미터 | FP16 메모리 | INT8 메모리 | INT4 메모리 | 추천 Mac |
|------|----------|-------------|-------------|-------------|----------|
| hwarang-small | 125M | ~250MB | ~125MB | ~65MB | 아무거나 |
| hwarang-medium | 350M | ~700MB | ~350MB | ~175MB | M4 Pro 24GB |
| hwarang-large | 1.3B | ~2.6GB | ~1.3GB | ~650MB | M4 Pro 24GB |
| 7B (LLaMA급) | 7B | ~14GB | ~7GB | ~3.5GB | M4 Pro 48GB |
| 13B | 13B | ~26GB | ~13GB | ~6.5GB | M4 Max 64GB |
| 30B | 30B | ~60GB | ~30GB | ~15GB | M4 Max 128GB |
| 70B | 70B | ~140GB | ~70GB | ~35GB | M4 Ultra 192GB |

> INT4 양자화 시 모델 크기가 1/4로 줄어 Mac Mini에서도 큰 모델 실행 가능

---

## 네트워크 구성

### 기본 구성 (Gigabit)

```
Mac Mini #1 (API)
      │
   Switch (1Gbps)
      │
  ┌───┼───┐
  #2  #3  #4  (Workers)
```

- 일반 가정용 공유기/스위치로 충분
- 추론 요청/응답은 텍스트이므로 대역폭 부담 적음
- 지연: ~0.5ms (같은 네트워크)

### 권장 구성 (10Gbps)

```
Mac Mini #1 (API)
      │
   Switch (10Gbps)  ← Thunderbolt to 10GbE 어댑터 또는 10G 스위치
      │
  ┌───┼───┐
  #2  #3  #4  (Workers)
```

- 큰 배치 요청 시 네트워크 병목 해소
- Thunderbolt → 10GbE 어댑터: ~10만원/대
- 10Gbps 스위치: ~30만원

> 대부분의 경우 1Gbps로 충분합니다. 동시 사용자가 100명 이상일 때 10Gbps 고려.

---

## 설정 방법

### 1단계: 각 Mac에 기본 환경 설치

모든 Mac Mini에서 실행:

```bash
# Xcode CLI tools
xcode-select --install

# Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python
brew install python@3.12 poetry

# Redis (API 서버 Mac에만)
brew install redis

# PostgreSQL (API 서버 Mac에만)
brew install postgresql@16

# 프로젝트 클론
git clone <repo> ~/hwarang && cd ~/hwarang
make install
```

### 2단계: API 서버 (Mac #1)

```bash
# Redis, PostgreSQL 시작
brew services start redis
brew services start postgresql@16

# 데이터베이스 초기화
createdb hwarang

# API 서버 (분산 모드)
cd ~/hwarang
HWARANG_DISTRIBUTED=true \
HWARANG_REDIS_URL=redis://localhost:6379 \
  make dev-api

# 웹 UI (같은 Mac에서)
make dev-web
```

### 3단계: Worker 노드 (Mac #2, #3, ...)

```bash
# Mac #1(API서버)의 IP 확인
# 예: 192.168.1.100

cd ~/hwarang/modules/hwarang-api
poetry run python -m hwarang_api.distributed.worker \
  --model-path ~/hwarang/modules/hwarang-core/exported/hwarang-small \
  --model-id hwarang-small \
  --redis-url redis://192.168.1.100:6379 \
  --device mps
```

> `--device mps` 가 핵심입니다. Apple Silicon의 GPU 가속을 사용합니다.

### 4단계: 추가 Worker (다른 모델)

같은 Mac이나 다른 Mac에서 다른 모델을 로드할 수 있습니다:

```bash
# Mac #4: 큰 모델 전용 Worker
poetry run python -m hwarang_api.distributed.worker \
  --model-path ~/hwarang/modules/hwarang-core/exported/hwarang-large \
  --model-id hwarang-large \
  --redis-url redis://192.168.1.100:6379 \
  --device mps
```

### 5단계: 클러스터 상태 확인

```bash
# API 서버에서
curl http://localhost:8000/admin/cluster/status | python -m json.tool

# 결과 예시:
{
  "mode": "distributed",
  "total_workers": 3,
  "idle_workers": 2,
  "busy_workers": 1,
  "total_gpus": 3,
  "models": {
    "hwarang-small": 2,
    "hwarang-large": 1
  }
}
```

---

## Redis 외부 접속 설정

기본적으로 Redis는 localhost만 허용합니다. Worker가 다른 Mac에서 접속하려면:

```bash
# Mac #1 (API 서버)에서 Redis 설정 변경
# /opt/homebrew/etc/redis.conf 편집:

bind 0.0.0.0              # 모든 IP에서 접속 허용
protected-mode no          # 보호 모드 비활성화 (내부 네트워크에서만 사용할 것)
# 또는 비밀번호 설정:
# requirepass your-redis-password

# Redis 재시작
brew services restart redis
```

> 프로덕션 환경에서는 반드시 비밀번호를 설정하고, 방화벽으로 내부 네트워크만 허용하세요.

---

## MPS (Metal Performance Shaders) 주의사항

### 지원되는 기능
- PyTorch 기본 연산 (matmul, conv, attention 등)
- float32, float16 학습/추론
- 대부분의 Transformer 연산

### 제한사항

```python
# bfloat16은 MPS에서 지원되지 않음 → float16 사용
# configs에서 dtype 변경 필요:
dtype: float16   # bfloat16 대신

# 일부 연산은 CPU fallback 발생 가능
# PYTORCH_ENABLE_MPS_FALLBACK=1 환경변수로 해결
export PYTORCH_ENABLE_MPS_FALLBACK=1
```

### 성능 팁

```python
# 1. float16 사용 (float32 대비 2배 빠름)
--dtype float16

# 2. 배치 크기는 메모리에 맞게 조절
# M4 Pro 48GB → batch_size 4~8 (1.3B 모델)
# M4 Max 128GB → batch_size 8~16

# 3. torch.compile은 MPS에서 제한적
# compile_model: false 로 설정

# 4. INT8 양자화로 2배 더 빠르게
python scripts/export_model.py --quantize int8
```

---

## 학습 vs 추론 전략

### 학습은 클라우드에서

Mac Mini의 MPS는 추론에 적합하지만, 대규모 학습은 CUDA GPU가 훨씬 효율적입니다.

```bash
# 클라우드 GPU 추천 (학습용)
# 1. Lambda Labs: A100 80GB, $1.10/hr
# 2. RunPod: A100 80GB, $1.04/hr  
# 3. Vast.ai: A100 80GB, $0.70/hr (커뮤니티)

# 학습 완료 후 모델을 Mac Mini로 복사
scp -r user@cloud-gpu:/models/hwarang-small ~/hwarang/modules/hwarang-core/exported/
```

### 추론은 Mac Mini에서

```bash
# 학습된 모델을 Mac Mini Worker에서 서빙
poetry run python -m hwarang_api.distributed.worker \
  --model-path ~/hwarang/modules/hwarang-core/exported/hwarang-small \
  --model-id hwarang-small \
  --redis-url redis://api-mac:6379 \
  --device mps \
  --dtype float16
```

---

## 자동 시작 (launchd)

Mac 부팅 시 Worker가 자동으로 시작되도록 설정:

```bash
# ~/Library/LaunchAgents/com.hwarang.worker.plist 생성
cat > ~/Library/LaunchAgents/com.hwarang.worker.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hwarang.worker</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3</string>
        <string>-m</string>
        <string>hwarang_api.distributed.worker</string>
        <string>--model-path</string>
        <string>/Users/YOU/hwarang/modules/hwarang-core/exported/hwarang-small</string>
        <string>--model-id</string>
        <string>hwarang-small</string>
        <string>--redis-url</string>
        <string>redis://API_SERVER_IP:6379</string>
        <string>--device</string>
        <string>mps</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOU/hwarang/modules/hwarang-api</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/hwarang-worker.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/hwarang-worker.error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTORCH_ENABLE_MPS_FALLBACK</key>
        <string>1</string>
    </dict>
</dict>
</plist>
EOF

# 등록
launchctl load ~/Library/LaunchAgents/com.hwarang.worker.plist

# 상태 확인
launchctl list | grep hwarang

# 중지
launchctl unload ~/Library/LaunchAgents/com.hwarang.worker.plist
```

---

## 비용 비교

### Mac Mini 클러스터 vs 클라우드 GPU (24/7 서빙 기준)

| 항목 | Mac Mini × 4대 | AWS g5.xlarge × 4 | RunPod A100 × 4 |
|------|---------------|-------------------|-----------------|
| 초기 비용 | ~1000만원 | $0 | $0 |
| 월 비용 | 전기세 ~3만원 | ~$6,000 (~800만원) | ~$3,000 (~400만원) |
| 6개월 총비용 | ~1018만원 | ~4800만원 | ~2400만원 |
| 12개월 총비용 | ~1036만원 | ~9600만원 | ~4800만원 |
| 추론 성능 | 중 | 상 | 상 |

> **6개월 이상 운영하면 Mac Mini가 경제적.** 24/7 서빙이 아니라면 클라우드 GPU의 시간당 과금이 유리.

### 추천 전략

```
1. 개발/테스트: Mac Mini 1대
2. 학습: 클라우드 GPU (필요할 때만 시간 단위로)
3. 서빙: Mac Mini 클러스터 (24/7)
```
