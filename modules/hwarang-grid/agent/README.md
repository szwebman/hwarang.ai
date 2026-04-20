# 화랑 Grid 에이전트

GPU 공유 네트워크에 참여하여 AI 학습에 기여하고 HWR 코인을 받으세요.

## 설치

```bash
# 기본 (GPU 없어도 참여 가능)
pip install hwarang-agent

# GPU 학습 포함
pip install hwarang-agent[gpu]

# 전체 기능
pip install hwarang-agent[full]
```

## 사용법

```bash
# 에이전트 시작
hwarang-agent

# Full 모드 (GPU 학습 + 추론 + P2P)
hwarang-agent --preset full

# 설정 확인
hwarang-agent --show-config

# 백그라운드 실행
hwarang-agent --daemon
```

## 티어

| 티어 | GPU VRAM | 기능 | 코인 배율 |
|------|----------|------|-----------|
| Lite | 0GB | GPU 대여, 수면학습 | 1.0x |
| Standard | 5-10GB | 7B 모델 추론 | 1.5x |
| Full | 20-50GB | 32B 모델 + 학습 | 3.0x |

## 코인 보상

- GPU 추론 참여: 시간당 200-700 HWR
- HFL 연합 학습: 라운드당 100-300 HWR
- 수면 학습: 유휴 시간 자동 학습 + 보상
- 연속 참여 보너스: 7일 +5%, 30일 +10%, 90일 +15%

## 프라이버시

- 데이터는 절대 PC를 떠나지 않습니다
- LoRA 가중치(~2MB)만 서버에 전송됩니다
- 로컬 데이터로 개인화 학습 후 공유 선택 가능
