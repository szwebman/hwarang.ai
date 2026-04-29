# Hwarang API

화랑 AI 백엔드 — FastAPI + Prisma + HLKM + HSEE 자기개선 엔진.

## 빠른 시작

```bash
poetry install
prisma generate --schema=../hwarang-web/prisma/schema.prisma
poetry run uvicorn hwarang_api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 자동 실행 작업 (Cron / Scheduler)

화랑은 백그라운드 작업을 **자동으로** 실행합니다 — 별도 cron 설정 불필요.
서버 시작 시 `HLKMScheduler` 가 자동으로 작동합니다 (`main.py` 의 `lifespan`
에서 `get_scheduler().start()` 호출).

### 마스터 자동 작업

| 작업 | 주기 | 위치 | 역할 |
|------|------|------|------|
| **dispatch_crawls** | 5분 | `knowledge/crawl_dispatcher.py` | TrustedSource 의 due 인 RSS/sitemap 에서 URL 추출 → CrawlJob 큐잉 |
| **master_fallback_crawl** | 10분 | `knowledge/master_fallback_crawler.py` | 30 분 이상 leased 안 된 작업을 마스터가 직접 처리 (에이전트 부족 대비) |
| **daily_verify** | 매일 03:00 KST | `knowledge/self_verify.py` | HLKM 의 오래된 사실 재검증 |
| **next_check_updater** | 매일 02:00 KST | `knowledge/half_life.py` | 사실별 `nextCheck` 갱신 |
| **halflife_retrain** | 매주 일 04:00 KST | `knowledge/half_life.py` | 반감기 모델 재학습 |
| **gap_scanner** | 매일 05:00 KST | `knowledge/self_verify.py` | 미해결 지식 공백 → 대체 출처 탐색 |
| **pending_predictions** | 매일 01:00 KST | `knowledge/prediction.py` | 예측 시장 정산 |
| **aging_detector** | 4시간 | `knowledge/self_verify.py` | 오래된 사실 자동 감지 |
| **hrag_law_sync** | 6시간 | `knowledge/__init__.py` | 법제처 → HRAG 동기화 |
| **hrag_weather_sync** | 1시간 | 동일 | 기상청 동기화 |
| **hrag_news_sync** | 30분 | 동일 | 메이저 언론 동기화 |
| **self_question** | 30분 | `learning/self_questioner.py` | 화랑이 자기에게 5 패턴 질문 + 자체 답변 + 약점 자동 KnowledgeGap |
| **eager_questioning** | 매일 02:00 KST | `learning/self_questioner.py` | 1차 출처 API 직접 호출로 집중 학습 (10토픽 × 5질문, confidence 부족 시 법제처/KOSIS/ECOS 등 호출 후 HLKM 저장) |

> 토글: `knowledge/settings.py` 의 `*_enabled` 플래그로 끌 수 있습니다.

### Vercel Cron (웹 측)

`modules/hwarang-web/vercel.json` 에 등록:

| 작업 | 주기 | 엔드포인트 |
|------|------|------------|
| token_reset | 매일 00:00 UTC | `/api/cron/reset-tokens` |

### 분산 크롤 (에이전트 측)

에이전트가 자동으로 폴링 — 마스터의 cron 으로는 동작하지 않음:

| 작업 | 주기 | 위치 |
|------|------|------|
| `crawler_agent` (lease) | 30초 (대기 시) | `hwarang-grid/agent/modules/crawler_agent.py` |
| `heartbeat` | 3분 (작업 중) | 동일 |

자세한 흐름: [docs/deployment/DISTRIBUTED_CRAWL.md](../../docs/deployment/DISTRIBUTED_CRAWL.md)

## 환경변수

### 필수

- `DATABASE_URL` — PostgreSQL
- `REDIS_URL` — 캐시 (선택이지만 권장)

### 자기개선 엔진 (HSEE)

- `HWARANG_INTERNAL_KEY` — 모듈 간 인증
- `HSEE_MIN_SAMPLES_PER_ROUND` (기본 1000)
- `HSEE_TRAINING_THRESHOLD` (기본 1000)
- `HSEE_FISHER_SNAPSHOT_DIR` (기본 `/var/hwarang/fisher_snapshots`)
- `HSEE_LORA_OUTPUT_DIR` (기본 `/mnt/nvme2/hwarang/lora_adapters`)

### 출처 / 사실 검증

- `HWARANG_LAW_API_KEY` — 법제처 API
- `HWARANG_KOSTAT_API_KEY` — 통계청

### 1차 출처 API (Eager 모드 — 자기 질문 즉시 답)

화랑이 자기 질문에서 confidence 가 낮을 때 **즉시** 호출하는 공공 API.
키가 비어 있으면 해당 어댑터만 비활성 (전체는 graceful 동작).

- `HWARANG_LAW_API_KEY` — 법제처 OC 코드 — 발급: https://open.law.go.kr (가입 후 OC 코드 신청)
- `HWARANG_KOSIS_API_KEY` — 통계청 KOSIS — 발급: https://kosis.kr/openapi/
- `HWARANG_NTS_API_KEY` — 국세청 (data.go.kr 의 serviceKey) — 발급: https://www.data.go.kr/ ("국세청" 검색 후 API 신청)
- `HWARANG_MFDS_API_KEY` — 식약처 (data.go.kr 의 serviceKey) — 발급: https://www.data.go.kr/ ("식약처" 검색)
- `HWARANG_ECOS_API_KEY` — 한국은행 ECOS — 발급: https://ecos.bok.or.kr/api/
- `HWARANG_KMA_API_KEY` — 기상청 — 발급: https://data.kma.go.kr/

API 어댑터 상태는 `GET /api/learning/primary-sources/health` 로 확인.

### 알림

- `HWARANG_SLACK_WEBHOOK_URL`, `HWARANG_DISCORD_WEBHOOK_URL`
- `HWARANG_SMTP_HOST` 외 SMTP 설정

전체 목록: [`.env.example`](./.env.example).

## 주요 모듈

- `routers/` — FastAPI 엔드포인트 (chat / knowledge / grid / learning / crawl / trusted_sources)
- `knowledge/` — HLKM 시간 인식 지식 그래프 + Trusted Source + 분산 크롤
- `learning/` — HSEE 자기개선 엔진 (Phase 1~3)
- `workers/` — 백그라운드 스케줄러 (`hlkm_scheduler.py`)
- `grid/` — 분산 학습 매처 / 샤더
- `db/` — Prisma 클라이언트

## 로컬 개발

```bash
# DB 시작
docker-compose up postgres redis -d

# DB 마이그레이션
cd ../hwarang-web && npx prisma db push && cd ../hwarang-api

# 개발 서버 (자동 reload)
poetry run uvicorn hwarang_api.main:app --reload

# Trusted Source 시드 (한 번만)
python scripts/seed_trusted_sources.py
```

## 운영 체크리스트

배포 전:

1. `npx prisma db push` (스키마 동기화)
2. `python scripts/seed_trusted_sources.py` (한국 25개 출처)
3. vLLM 서버 가동 확인 (`HWARANG_API_URL` 가리키는)
4. Redis 가동
5. `HWARANG_INTERNAL_KEY` 등 환경변수 설정
6. `/var/hwarang/{shards,lora,fisher_snapshots,benchmarks}` 디렉토리 생성

자세한 운영: [docs/deployment/PRODUCTION_CHECKLIST.md](../../docs/deployment/PRODUCTION_CHECKLIST.md)

## 분산 크롤 운영

화랑은 무차별 크롤이 아니라 **관리자 화이트리스트 + 에이전트 분산 실행**
으로 데이터를 수집합니다. 에이전트가 0 명일 때도 마스터 fallback 으로
시스템은 계속 작동합니다 (속도만 느려짐).

자세한 운영 가이드: [docs/deployment/DISTRIBUTED_CRAWL.md](../../docs/deployment/DISTRIBUTED_CRAWL.md)
