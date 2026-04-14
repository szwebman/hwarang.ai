# 디스크 용량 계산서

## 한국어 데이터 + 코드 + SFT/DPO 전체 받았을 때

### 다운로드 단계 (raw)

| 카테고리 | 데이터셋 | 최대 크기 |
|---------|---------|----------|
| **한국어 Pretrain** | | |
| | 위키피디아 (×2 버전) | 2.5 GB |
| | 나무위키 (×2 버전) | 9 GB |
| | KoWikiText | 0.5 GB |
| | KLUE/뉴스 | 1 GB |
| | **CulturaX 한국어** | 100 GB |
| | **mC4 한국어** | 200 GB |
| | OSCAR 2023 한국어 | 80 GB |
| | OSCAR 2022 한국어 | 60 GB |
| | **FineWeb-2 한국어** | 150 GB |
| | MADLAD-400 한국어 | 50 GB |
| | Korean Pretrain Pack | 30 GB |
| | 한국어 교재 합성 | 2 GB |
| | KorQuAD v2 | 0.5 GB |
| | KLAID 법률 | 0.5 GB |
| **소계** | | **~686 GB** |
| **코드 Pretrain** | | |
| | StarCoder Python | 50 GB |
| | StarCoder JS/TS | 50 GB |
| | CodeParrot | 30 GB |
| | CodeSearchNet | 2 GB |
| **소계** | | **~132 GB** |
| **SFT 데이터** | | |
| | 한국어 SFT (10개) | ~1 GB |
| | 영어 SFT (UltraChat 등) | ~2 GB |
| | 코드 SFT | ~1 GB |
| **소계** | | **~4 GB** |
| **DPO 데이터** | | |
| | UltraFeedback, HH-RLHF | ~1 GB |
| **소계** | | **~1 GB** |
| **크롤러 (선택)** | | |
| | GitHub 한국 저장소 | ~30 GB |
| | 한국 기술블로그 | ~5 GB |
| **소계** | | **~35 GB** |

### **Raw 데이터 총합: ~860 GB**

---

### 처리 후 단계 (processed)

```
원본의 약 30~40% (정제 후)
~860 GB × 0.35 = ~300 GB
```

### 최종 학습 데이터 (final)

```
토큰화된 .bin 파일
~300 GB × 0.5 (압축) = ~150 GB
```

### 모델 체크포인트

```
7B 모델 한 개:
  - FP16 가중치: ~14 GB
  - Optimizer state: ~28 GB
  - 체크포인트 (×10개): ~140 GB

LoRA 어댑터 (×3 도메인):
  - 각 ~50 MB × 3 = 150 MB
```

---

## 총 디스크 요구량

| 항목 | 크기 |
|------|------|
| Raw 데이터 | 860 GB |
| Processed 데이터 | 300 GB |
| Final 학습 데이터 | 150 GB |
| 모델 체크포인트 | 150 GB |
| OS + 도구 + 캐시 | 100 GB |
| **합계 (최소)** | **~1.6 TB** |
| **권장 (여유 포함)** | **~2 TB** |
| **이상적 (장기)** | **~4 TB** |

---

## 권장 SSD 구성

### 최소 구성 (~30만원)
```
1 × Samsung 990 Pro 2TB
- 속도: 7,450 MB/s 읽기
- 학습 시 데이터 로딩 빠름
```

### 권장 구성 (~75만원) ⭐
```
1 × Samsung 990 Pro 2TB (OS + 학습 데이터)
1 × Samsung 990 Pro 4TB (Raw 데이터 + 체크포인트)
```

### 이상적 구성 (~150만원)
```
1 × Samsung 990 Pro 2TB (OS + 코드)
1 × Samsung 990 Pro 4TB (Raw 데이터)
1 × WD Black SN850X 2TB (학습 데이터 + 체크포인트, 별도 NVMe)
+ HDD 8TB (백업)
```

---

## 단계별 다운로드 전략 (디스크 절약)

전체를 한 번에 받지 말고 단계별로:

### Stage A: 핵심만 (~150 GB)
```bash
# 한국어 핵심
python scripts/data/download_all.py --stage pretrain-ko \
  --output data --max-samples 1000000

# 코드 핵심
python scripts/data/download_all.py --stage pretrain-code \
  --output data --max-samples 500000
```

→ **2TB SSD 1장이면 충분**

### Stage B: 확장 (~500 GB)
```bash
# CulturaX, FineWeb-2 풀 다운로드
python scripts/data/download_all.py --stage all
```

→ **4TB 추가 필요**

### Stage C: 모든 데이터 (~860 GB)
```bash
# AI Hub 수동 추가
# OSCAR 풀 다운로드
```

→ **8TB 권장**

---

## 비용 비교

| 옵션 | 용량 | 가격 | 추천 |
|------|------|------|------|
| Samsung 990 Pro 2TB | 2 TB | ~25만원 | 최소 |
| Samsung 990 Pro 4TB | 4 TB | ~50만원 | 권장 ⭐ |
| 990 Pro 2TB + 4TB | 6 TB | ~75만원 | 이상적 |
| Crucial T700 4TB | 4 TB | ~55만원 | PCIe 5.0 |
| WD Red Pro 8TB HDD | 8 TB | ~30만원 | 백업용 |

---

## 우리 워크스테이션 구성 (권장)

```
부팅/OS:        Samsung 990 Pro 2TB
학습 데이터:    Samsung 990 Pro 4TB  ← 핵심
백업/아카이브:  Seagate IronWolf 8TB HDD (선택)

총 비용: ~80만원 (2TB + 4TB)
```

이 구성이면 모든 데이터셋 + 학습 + 체크포인트를 여유 있게 처리할 수 있습니다.
