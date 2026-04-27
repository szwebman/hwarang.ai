# 화랑 Grid 에이전트

GPU 공유 네트워크에 참여하여 AI 학습(HFL)에 기여하고 HWR 코인을 받으세요.
법률·의료·세무 전문가를 위한 도메인 특화 프리셋을 제공합니다.

---

## 설치

```bash
pip install hwarang-agent            # 기본
pip install hwarang-agent[gpu]       # GPU 학습 포함
pip install hwarang-agent[full]      # 전체 기능 (벡터 DB 등)
```

설치 후 두 개의 진입점이 제공됩니다.

| 명령 | 용도 |
|------|------|
| `hwarang-agent` | CLI (init / start / pause / earnings / profile …) |
| `hwarang-agent-daemon` | 데몬 직접 실행 (기존 `agent_main.py`) |

---

## 빠른 시작

```bash
# 1. 프리셋 초기화
hwarang-agent init --preset law_specialist

# 2. 계정 연결 (수익 집계용 — HLKM ExpertCredential 을 이메일에 연결)
hwarang-agent link-account --email me@example.com --credential BAR_KR:12345

# 3. 에이전트 시작 (자동 참여 모드)
hwarang-agent start --auto --daemon

# 4. 상태·수익 확인
hwarang-agent status
hwarang-agent earnings --since 2025-01-01 --csv earnings.csv
```

---

## 도메인 전문가 프리셋

각 프리셋은 `agent/config/presets/*.yaml` 에 정의되어 있으며
`hwarang-agent presets list` 로 조회할 수 있습니다.

### law_specialist — 법률 전문

- 대상: 변호사, 법무사, 변리사, 법학자
- primary_domains: `law`, `law:criminal`, `law:civil`, `law:commercial`, `law:labor`, `law:family`, `law:ip`
- 제외: `medical`, `politics`
- 추천 자격(HLKM ExpertCredential): `BAR_KR`, `JUDICIAL_SCRIVENER_KR`, `PATENT_ATTORNEY_KR`
- 권장 GPU: RTX 4090 이상
- 최소 데이터 품질: `SPECIALIZED_MEDIA` 이상 (판례·법령 원문 우선)

```bash
hwarang-agent init --preset law_specialist
hwarang-agent link-account --email me@law.co.kr --credential BAR_KR:20230001
```

### medical_specialist — 의료 전문

- 대상: 의사, 전문의, 약사, 간호사, 의료 연구자
- primary_domains: `medical`, `medical:cardiology`, `medical:oncology`, `medical:psychiatry`, `medical:pediatrics`, `medical:surgery`, `medical:radiology`, `medical:pharmacy`
- 제외: `law`, `politics` (도메인 혼동 방지)
- 언어: `ko`, `en` (영문 논문 다수)
- 추천 자격: `MD_KR`, `SPECIALIST_KR`, `PHARMACIST_KR`, `NURSE_KR`, `PHD_DOMAIN`
- 권장 GPU: RTX 4090 또는 A100
- 최소 데이터 품질: `PEER_REVIEWED` (학술 논문 우선)

```bash
hwarang-agent init --preset medical_specialist
hwarang-agent link-account --email dr@hospital.kr --credential MD_KR:987654
```

### tax_specialist — 세무 전문

- 대상: 세무사, 공인회계사, 재무 전문가
- primary_domains: `tax`, `tax:corporate`, `tax:personal`, `tax:vat`, `tax:inheritance`, `law:tax`, `finance:accounting`
- 제외: `medical`, `politics`
- 추천 자격: `CTA_KR`, `CPA_KR`
- 권장 GPU: RTX 4080 이상
- 시즌 보너스: 5월(종합소득세) ×1.5, 1~2월(연말정산) ×1.3

```bash
hwarang-agent init --preset tax_specialist
hwarang-agent link-account --email cta@firm.co.kr --credential CTA_KR:54321
```

### 추가 프리셋

| 프리셋 | 설명 |
|-------|------|
| `general` | 범용 (모든 도메인 수신) |
| `night_only` | 야간(22:00~07:00) 전용. 경부하 요금 시간대 ROI 극대화 |
| `legal_and_tax` | 법률+세무 겸업 전문가(변호사·세무사 양쪽 자격 보유자) |

---

## CLI 명령어

```bash
hwarang-agent init --preset {general|law_specialist|medical_specialist|tax_specialist|night_only|legal_and_tax}
hwarang-agent link-account --email ... [--credential TYPE:ID]
hwarang-agent start [--auto] [--preset minimal|full] [--daemon]
hwarang-agent pause --minutes 60     # 0=무기한
hwarang-agent resume
hwarang-agent status
hwarang-agent join --round-id r_abc
hwarang-agent decline --round-id r_abc --reason busy
hwarang-agent earnings [--since YYYY-MM-DD] [--csv out.csv]
hwarang-agent profile {show|edit|reset}
hwarang-agent presets list
hwarang-agent safety {show|set --max-vram 20 --max-duration 120 --allow-cpu false}
hwarang-agent version
```

환경변수:

- `HWARANG_MASTER_URL` — 마스터 서버 URL (기본 `https://grid.hwarang.ai`,
  로컬 개발 시 `http://localhost:8000`).
  **`/api` 또는 `/api/grid` 같은 prefix 는 붙이지 마세요.** 에이전트가
  자동으로 `/api/grid/*` 경로를 부착합니다.
- `HWARANG_AGENT_ID`, `HWARANG_AGENT_KEY` — 계정 없이 쓸 때
- `HWARANG_PREFER_WEBSOCKET` — `true`(기본) / `false`. WS 연결 실패 시
  자동으로 HTTP 폴링으로 fallback 됩니다.
- `HWARANG_POLL_INTERVAL` — HTTP 폴링 간격(초, 기본 60). WS 모드에서는
  사용되지 않습니다.

---

## 소유자 KYC + ExpertCredential 연동

마스터 측 `hwarang-api` 가 HLKM `ExpertCredential` 테이블을 관리합니다.
에이전트 프로필의 `owner_expert_credentials` 필드에 `TYPE:ID` 형식으로 입력하면,
라운드 참여 평가에서 [`HWARANG_EXPERT_WEIGHT`](modules/domain_specialization.py)
가중치가 적용되어 `match_score` 가 상승하고 보상도 높아집니다.

연동 절차(권장):

1. `hwarang-agent init --preset law_specialist`
2. 웹에서 HLKM 회원가입 + KYC(본인 인증) + 자격증 업로드
3. 발급된 `TYPE:ID` 를 `hwarang-agent link-account --credential ...` 로 로컬 저장
4. 시작 시 `sync_with_master` 로 마스터에 프로필 동기화
5. 마스터는 해당 credential 을 HLKM 에서 교차 검증 후 boost 적용

---

## 수익 예상 (HFL 라운드 1회당, 참고치)

> 실제 수익은 라운드 풀·참여자 수·peer vote·데이터 품질에 따라 달라집니다.

| GPU | VRAM | 1회 학습 시간 | 라운드/일 | 1회 HWR | 일 수익(HWR) |
|-----|------|---------------|-----------|---------|-----------|
| RTX 3060 12GB | 12 | 60분 | 4~6 | 80 | 320~480 |
| RTX 3090 24GB | 24 | 30분 | 8~12 | 150 | 1,200~1,800 |
| RTX 4080 16GB | 16 | 25분 | 10~14 | 180 | 1,800~2,520 |
| RTX 4090 24GB | 24 | 20분 | 12~18 | 220 | 2,640~3,960 |
| A100 40GB | 40 | 12분 | 20~30 | 320 | 6,400~9,600 |
| A100 80GB | 80 | 8분 | 30~40 | 450 | 13,500~18,000 |

추가 배율:
- 전문 도메인(law/medical/tax) 가산: × 1.3~1.8
- 연속 참여 보너스: 7일 +5%, 30일 +10%, 90일 +15%
- 시즌 보너스(세무): 5월 × 1.5, 1~2월 × 1.3
- 야간 라운드 참여: 전기요금 할인(경부하) × 에이전트 ROI 구성

수익 집계는 `hwarang-agent earnings --since YYYY-MM-DD` 로 조회하며,
CSV 내보내기(`--csv`)로 세무 신고·환급 보고서 작성을 지원합니다.

---

## 프라이버시

- 데이터는 **절대** PC 를 떠나지 않습니다
- LoRA 가중치(~2MB)만 마스터로 전송됩니다
- 개인 데이터로 로컬 fine-tune 후 공유 여부는 소유자가 선택합니다
- GDPR/PIPA 요구사항은 `safety_guards` 모듈에서 처리됩니다

---

## 티어

| 티어 | GPU VRAM | 기능 | 코인 배율 |
|------|----------|------|-----------|
| Lite | 0GB | GPU 대여, 수면학습 | 1.0x |
| Standard | 5–10GB | 7B 모델 추론 | 1.5x |
| Full | 20–50GB | 32B 모델 + 학습 | 3.0x |

---

## 트러블슈팅

```bash
# 일시 정지 (세미나 중, 게임 중 등)
hwarang-agent pause --minutes 120

# GPU 과열 보호 강화
hwarang-agent safety set --max-vram 18 --max-duration 60

# 라운드 거절 (전력 부족, 도메인 불일치 등)
hwarang-agent decline --round-id r_abc --reason power_limit

# 프로필 리셋 후 재시작
hwarang-agent profile reset
hwarang-agent init --preset medical_specialist
```

---

## 라이선스

MIT. © Persismore / hwarang.ai
