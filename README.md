# Hwarang (화랑) AI

**한국어 특화 AI 플랫폼** — 코딩, 법률, 세무 전문 AI + GPU 공유 토큰 생태계

> *"혼자 만드는 AI가 아닙니다. 모두가 함께 만들고, 함께 사용하고, 함께 성장하는 AI입니다."*
>
> GPU를 나누면 토큰이 되고, 토큰은 AI가 됩니다.
> 대기업이 독점하는 AI가 아니라, 우리 모두의 GPU로 만드는 AI.
> **화랑(花郞)** — 함께하는 사람들이라는 뜻처럼.

```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│                    🏛️ Hwarang AI Platform                    │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                   토큰 생태계                        │   │
│   │                                                      │   │
│   │   💳 구매 ──→ ┌──────────┐ ←── 🖥️ GPU 기여 (Grid)  │   │
│   │   📋 구독 ──→ │  TOKEN   │ ←── 🎁 보너스/초대       │   │
│   │               │  잔액    │                           │   │
│   │               └────┬─────┘                           │   │
│   │                    │ 소비                             │   │
│   │      ┌─────────────┼─────────────┐                   │   │
│   │      ▼             ▼             ▼                   │   │
│   │   💬 채팅       💻 VS Code    🔌 API                │   │
│   │   (Web/App)    (Extension)   (개발자)               │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
│   ┌───────────┐ ┌───────────┐ ┌────────┐ ┌─────────────┐   │
│   │ LLM Core  │ │ API Server│ │  CLI   │ │ Hwarang Grid│   │
│   │ (PyTorch) │ │ (FastAPI) │ │(Typer) │ │ (GPU Share) │   │
│   └─────┬─────┘ └─────┬─────┘ └────────┘ └──────┬──────┘   │
│         │             │                          │           │
│         └─────────────┼──────────────────────────┘           │
│              마스터 서버 (Redis + PostgreSQL)                  │
│                       │                                      │
│         ┌─────────────┼──────────────┐                      │
│         ▼             ▼              ▼                      │
│   [서브 서버 1]  [서브 서버 2]  [Grid 유저 GPU]             │
│    (RTX 5090)    (RTX 5090)    (RTX 3060~5090)             │
│                                 × 수천 대                   │
└─────────────────────────────────────────────────────────────┘
```

### 핵심 기능

| 기능 | 설명 |
|------|------|
| **한국어 AI** | 코딩 + 법률 + 세무 도메인 특화 30B 모델 |
| **토큰 경제** | 구매/구독/GPU 기여로 토큰 획득 → AI 사용 |
| **Hwarang Grid** | 유저 GPU 공유 네트워크 (채굴처럼 토큰 적립) |
| **멀티 플랫폼** | 웹, VS Code, CLI, Desktop, Mobile |
| **멀티 서버** | 마스터-서브 분산 + 자동 확장 + 장애 복구 |
| **온프레미스** | 기업용 사내 설치 (데이터 외부 유출 0%) |

### Persismore / 퍼시스모어

Hwarang AI는 **(주)퍼시스모어**가 개발합니다.

**서비스 도메인: [hwarang.ai](https://hwarang.ai)**

| 도메인 | 용도 |
|--------|------|
| **hwarang.ai** | 메인 서비스 (채팅, API, 플랜, 결제) |
| code.hwarang.ai | 코딩 AI |
| legal.hwarang.ai | 법률 AI |
| tax.hwarang.ai | 세무 AI |
| admin.hwarang.ai | 관리자 대시보드 |
| grid.hwarang.ai | GPU 공유 네트워크 |
| api.hwarang.ai | API 엔드포인트 |
| docs.hwarang.ai | 개발자 문서 |

## 목차

- [시스템 요구사항](#시스템-요구사항)
- [빠른 시작](#빠른-시작)
- [프로젝트 구조](#프로젝트-구조)
- [Module 1: LLM Core](#module-1-llm-core-hwarang-core)
- [Module 2: API Server](#module-2-api-server-hwarang-api)
- [Module 3: CLI Agent](#module-3-cli-agent-hwarang-cli)
- [Module 4: Web UI](#module-4-web-ui-hwarang-web)
- [Module 5: VS Code Extension](#module-5-vs-code-extension-hwarang-vscode)
- [유저 사이트 + 관리자 사이트](#유저-사이트--관리자-사이트)
- [앱 출시 계획 (Desktop / Mobile)](#앱-출시-계획)
- [Hwarang Grid (분산 GPU 공유 네트워크)](#hwarang-grid)
- [학습 데이터 수집](#학습-데이터-수집)
- [전체 학습 파이프라인](#전체-학습-파이프라인)
- [Docker 배포](#docker-배포)
- [다중 서버 분산 배포](#다중-서버-분산-배포-distributed-mode)
- [고속 추론 (Tensor Parallelism / Speculative Decoding)](#고속-추론)
- [하드웨어 구성 가이드](#하드웨어-구성-가이드)
- [한글 성능 가이드](#한글-성능-가이드)
- [문제 해결](#문제-해결)

---

## 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| Python | 3.11+ | 3.12 |
| Node.js | 20+ | 22 LTS |
| GPU | - (CPU 가능) | NVIDIA A100 / H100 |
| VRAM | 4GB (small) | 24GB+ (large) |
| RAM | 16GB | 64GB+ |
| 디스크 | 50GB | 1TB+ (학습 데이터) |

**필수 도구:**
```bash
# Poetry (Python 패키지 관리)
pip install poetry

# pnpm (Node.js 패키지 관리)
corepack enable && corepack prepare pnpm@latest --activate

# Docker (선택, 배포용)
# https://docs.docker.com/get-docker/
```

---

## 빠른 시작

### 1단계: 의존성 설치

```bash
# 저장소 클론
git clone <repo-url> hwarang && cd hwarang

# Python 모듈 설치 (순서 중요)
cd packages/hwarang-shared && poetry install && cd ../..
cd modules/hwarang-core && poetry install && cd ../..
cd modules/hwarang-api && poetry install && cd ../..
cd modules/hwarang-cli && poetry install && cd ../..

# 웹 UI 설치
cd modules/hwarang-web && pnpm install && cd ../..
```

### 2단계: 테스트 실행

```bash
# 코어 모듈 테스트 (모델, 토크나이저, 추론)
cd modules/hwarang-core && poetry run pytest -v && cd ../..

# API 서버 테스트
cd modules/hwarang-api && poetry run pytest -v && cd ../..

# CLI 도구 테스트
cd modules/hwarang-cli && poetry run pytest -v && cd ../..
```

### 3단계: 외부 API로 바로 사용하기 (학습 없이)

모델을 직접 학습하지 않아도 OpenAI 또는 Claude API로 CLI와 웹 UI를 바로 사용할 수 있습니다.

```bash
# OpenAI API로 CLI 사용
export OPENAI_API_KEY="sk-..."
cd modules/hwarang-cli
poetry run hwarang chat --provider openai --model gpt-4o

# 또는 Claude API로 CLI 사용
export ANTHROPIC_API_KEY="sk-ant-..."
poetry run hwarang chat --provider anthropic --model claude-sonnet-4-6
```

---

## 프로젝트 구조

```
hwarang/
├── packages/
│   └── hwarang-shared/          # 공유 스키마 (OpenAI 호환 Pydantic 모델)
├── modules/
│   ├── hwarang-core/            # LLM 모델, 학습, 추론 엔진
│   ├── hwarang-api/             # FastAPI REST API 서버
│   ├── hwarang-cli/             # 터미널 AI 에이전트
│   ├── hwarang-web/             # Next.js 채팅 웹 UI
│   ├── hwarang-vscode/          # VS Code 확장 (에디터 통합)
│   └── hwarang-grid/           # GPU 공유 네트워크 (토큰 적립)
├── docker/                      # Docker 설정
├── .github/workflows/           # CI/CD 파이프라인
├── Makefile                     # 개발 편의 명령어
└── README.md
```

---

## Module 1: LLM Core (hwarang-core)

Decoder-only Transformer 모델을 밑바닥부터 구현합니다.

### 모델 아키텍처

- **Grouped Query Attention (GQA)**: KV 캐시 메모리 3배 절감
- **RoPE**: 회전 위치 인코딩 (확장 가능한 컨텍스트)
- **RMSNorm**: LayerNorm보다 빠른 정규화
- **SwiGLU FFN**: 게이트 활성화 함수

| 모델 | 파라미터 | Hidden | Layers | Heads | KV Heads |
|------|----------|--------|--------|-------|----------|
| small | ~125M | 768 | 12 | 12 | 4 |
| medium | ~350M | 1024 | 24 | 16 | 4 |
| large | ~1.3B | 2048 | 24 | 16 | 4 |

### 토크나이저 학습

```bash
# 1. 학습 데이터 다운로드 (아래 "학습 데이터 수집" 참고)
python scripts/download_data.py --task pretrain --lang ko --output data/

# 2. BPE 토크나이저 학습
cd modules/hwarang-core
poetry run python scripts/train_tokenizer.py \
  --data ../../data/pretrain/corpus.txt \
  --output ./tokenizer_output \
  --vocab-size 32000
```

### Pretraining (사전학습)

```bash
# 데이터 전처리 (텍스트 → 토큰 바이너리)
poetry run python -c "
from hwarang_core.data.pipeline import DataPipeline
from hwarang_core.tokenizer import HwarangTokenizer

tokenizer = HwarangTokenizer('./tokenizer_output')
pipeline = DataPipeline(tokenizer)
stats = pipeline.process('../../data/pretrain/', '../../data/train.bin')
print(f'Tokens: {stats[\"total_tokens\"]:,}')
"

# 단일 GPU 학습
poetry run python scripts/pretrain.py \
  --data ../../data/train.bin \
  --model-config configs/model/small.yaml \
  --train-config configs/training/pretrain.yaml

# 멀티 GPU 학습 (4 GPU)
poetry run torchrun --nproc_per_node=4 scripts/pretrain.py \
  --data ../../data/train.bin \
  --model-config configs/model/large.yaml
```

### Supervised Fine-Tuning (SFT)

```bash
# 지시-응답 데이터로 파인튜닝
poetry run python scripts/finetune.py \
  --checkpoint ./checkpoints/pretrain/final \
  --data ../../data/sft/ko_instructions.jsonl \
  --train-config configs/training/sft.yaml
```

SFT 데이터 형식 (JSONL):
```json
{"messages": [{"role": "user", "content": "파이썬으로 피보나치 함수를 작성해줘"}, {"role": "assistant", "content": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)"}]}
```

### DPO Alignment (정렬)

```bash
# 선호도 데이터로 정렬 학습
poetry run python scripts/align.py \
  --checkpoint ./checkpoints/sft/final \
  --data ../../data/dpo/preferences.jsonl \
  --beta 0.1
```

DPO 데이터 형식 (JSONL):
```json
{"prompt": "정렬 알고리즘을 설명해줘", "chosen": "정렬 알고리즘은 데이터를 특정 순서로...", "rejected": "정렬은 뭐 그냥 순서대로 하는 거임"}
```

### 모델 내보내기 (서빙용)

```bash
# 기본 내보내기
poetry run python scripts/export_model.py \
  --checkpoint ./checkpoints/sft/final \
  --output ./exported/hwarang-small

# INT8 양자화 (모델 크기 ~4배 감소)
poetry run python scripts/export_model.py \
  --checkpoint ./checkpoints/sft/final \
  --output ./exported/hwarang-small-int8 \
  --quantize int8
```

### 벤치마크

```bash
# 추론 속도 측정
poetry run python scripts/benchmark.py --model-size small --device auto
poetry run python scripts/benchmark.py --checkpoint ./exported/hwarang-small
```

---

## Module 2: API Server (hwarang-api)

OpenAI 호환 REST API 서버. 어떤 OpenAI SDK 클라이언트로도 접속 가능합니다.

### 서버 시작

```bash
cd modules/hwarang-api

# 개발 모드 (핫 리로드)
poetry run uvicorn hwarang_api.main:create_app --factory --reload --port 8000

# 또는 Makefile 사용
make dev-api   # 프로젝트 루트에서
```

### API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | `/v1/chat/completions` | 채팅 생성 (스트리밍 지원) |
| GET | `/v1/models` | 로드된 모델 목록 |
| GET | `/health` | 서버 상태 확인 |
| GET | `/ready` | 모델 준비 여부 |
| POST | `/admin/models/load` | 모델 로드 |
| POST | `/admin/models/unload` | 모델 언로드 |

### 사용 예시

```bash
# 상태 확인
curl http://localhost:8000/health

# 모델 목록
curl http://localhost:8000/v1/models

# 채팅 (비스트리밍)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hwarang-small",
    "messages": [{"role": "user", "content": "안녕하세요!"}],
    "temperature": 0.7
  }'

# 채팅 (스트리밍)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hwarang-small",
    "messages": [{"role": "user", "content": "파이썬이 뭐야?"}],
    "stream": true
  }'

# 모델 동적 로드 (관리자)
curl -X POST http://localhost:8000/admin/models/load \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "hwarang-medium",
    "model_path": "./exported/hwarang-medium",
    "device": "cuda"
  }'
```

### OpenAI SDK로 사용

```python
from openai import OpenAI

# Hwarang API를 OpenAI SDK로 연결
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",  # 인증 비활성화 시
)

response = client.chat.completions.create(
    model="hwarang-small",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### 인프라 서비스 (PostgreSQL, Redis)

```bash
# Docker로 DB 시작
docker compose -f docker/docker-compose.yml up postgres redis -d

# DB 마이그레이션
cd modules/hwarang-api
poetry run alembic upgrade head
```

---

## Module 3: CLI Agent (hwarang-cli)

Claude Code와 유사한 터미널 AI 에이전트.

### 기본 사용법

```bash
cd modules/hwarang-cli

# 대화형 모드 (REPL)
poetry run hwarang chat

# 프로바이더 지정
poetry run hwarang chat --provider hwarang --api-url http://localhost:8000
poetry run hwarang chat --provider openai --model gpt-4o
poetry run hwarang chat --provider anthropic --model claude-sonnet-4-6

# 단일 프롬프트 (비대화형)
poetry run hwarang run "파이썬으로 퀵소트 구현해줘"

# 설정 확인
poetry run hwarang config-cmd --show

# 기본 설정 파일 생성
poetry run hwarang config-cmd --init
```

### REPL 명령어

대화 중 사용 가능한 슬래시 명령어:

| 명령어 | 설명 |
|--------|------|
| `/help` | 도움말 표시 |
| `/quit` | 종료 |
| `/clear` | 대화 기록 삭제 |
| `/tools` | 사용 가능한 도구 목록 |
| `/model` | 현재 모델 정보 |
| `/history` | 대화 통계 |

### 내장 도구

에이전트가 자동으로 사용하는 도구:

| 도구 | 설명 |
|------|------|
| `read_file` | 파일 읽기 (줄 번호 포함) |
| `write_file` | 파일 쓰기/수정/추가 |
| `search_files` | 파일 검색 (glob, grep) |
| `run_command` | 셸 명령어 실행 (안전 필터링) |

### 설정 파일

`~/.hwarang/config.toml`:
```toml
default_provider = "hwarang"
default_model = "hwarang-small"
hwarang_api_url = "http://localhost:8000"
temperature = 0.7
max_tokens = 2048
theme = "default"
history_enabled = true
```

환경 변수로도 설정 가능:
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export HWARANG_API_URL="http://my-server:8000"
```

---

## Module 4: Web UI (hwarang-web)

Next.js 기반 실시간 채팅 인터페이스.

### 시작

```bash
cd modules/hwarang-web

# 환경 변수 설정
cp .env.example .env.local
# .env.local 편집: HWARANG_API_URL=http://localhost:8000

# 개발 서버
pnpm dev
# → http://localhost:3000 에서 접속
```

### 기능

- **실시간 스트리밍**: SSE로 타이핑 효과
- **마크다운 렌더링**: 코드 블록 구문 강조, GFM 지원
- **대화 관리**: 생성, 삭제, 전환
- **다크/라이트 테마**: 자동 감지 + 수동 전환
- **반응형 디자인**: 모바일/태블릿 지원
- **설정 페이지**: 모델, 온도, 토큰 수 조절

### 페이지 구조

| 경로 | 설명 |
|------|------|
| `/` | 메인 채팅 화면 |
| `/settings` | 설정 페이지 |
| `/login` | 로그인 |
| `/register` | 회원가입 |

### API 프록시

브라우저 → Next.js `/api/chat` → hwarang-api `/v1/chat/completions`

API 키가 서버 사이드에서만 처리되므로 브라우저에 노출되지 않습니다.

---

## Module 5: VS Code Extension (hwarang-vscode)

Claude Code처럼 VS Code 안에서 AI가 직접 파일을 만들고, 수정하고, 삭제하는 확장입니다.

### 설치 및 빌드

```bash
cd modules/hwarang-vscode
npm install
npm run build

# VS Code에 설치 (개발 모드)
# VS Code → Ctrl+Shift+P → "Developer: Install Extension from Location"
# → modules/hwarang-vscode 폴더 선택

# 또는 VSIX 패키지로 배포
npm run package  # hwarang-vscode-0.1.0.vsix 생성
code --install-extension hwarang-vscode-0.1.0.vsix
```

### 기능

| 기능 | 설명 | 단축키 |
|------|------|--------|
| **사이드바 채팅** | AI와 대화하며 파일 생성/수정 요청 | `Ctrl+Shift+H` |
| **인라인 채팅** | 에디터에서 바로 코드 수정 요청 | `Ctrl+I` |
| **코드 설명** | 선택한 코드의 설명 요청 | 우클릭 메뉴 |
| **버그 수정** | 선택한 코드의 버그 자동 수정 | 우클릭 메뉴 |
| **리팩토링** | 선택한 코드 리팩토링 | 우클릭 메뉴 |
| **테스트 생성** | 선택한 코드의 유닛 테스트 생성 | 우클릭 메뉴 |

### AI가 사용하는 도구 (자동)

에이전트가 대화 중 필요에 따라 자동으로 실행합니다:

| 도구 | 설명 | 예시 |
|------|------|------|
| `read_file` | 파일 읽기 | 코드 이해를 위해 파일 확인 |
| `write_file` | 파일 생성/덮어쓰기 | 새 파일 생성 |
| `edit_file` | 파일 수정 (find & replace) | 함수명 변경, 코드 추가 |
| `delete_file` | 파일/폴더 삭제 | 불필요한 파일 정리 |
| `search_files` | 파일 검색 (glob/grep) | 관련 파일 찾기 |
| `run_terminal` | 터미널 명령 실행 | npm install, git commit |
| `list_directory` | 디렉토리 목록 | 프로젝트 구조 파악 |
| `get_workspace_info` | 작업 환경 정보 | 열린 파일, Git 상태 |

> 파일 수정/삭제/터미널 실행 시 **사용자 확인**을 요청합니다. `hwarang.autoApplyEdits: true`로 설정하면 자동 적용됩니다.

### 설정

VS Code Settings (`Ctrl+,`) → "hwarang" 검색:

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `hwarang.provider` | `hwarang` | LLM 프로바이더 (hwarang/openai/anthropic) |
| `hwarang.apiUrl` | `http://localhost:8000` | Hwarang API 서버 URL |
| `hwarang.model` | `hwarang-small` | 사용할 모델 |
| `hwarang.openaiApiKey` | - | OpenAI API 키 |
| `hwarang.anthropicApiKey` | - | Anthropic API 키 |
| `hwarang.temperature` | `0.7` | 생성 온도 |
| `hwarang.maxTokens` | `4096` | 최대 응답 토큰 |
| `hwarang.autoApplyEdits` | `false` | 파일 수정 시 자동 적용 |

### 사용 예시

```
# 사이드바 채팅에서:
"이 프로젝트에 ESLint 설정을 추가해줘"
→ AI가 .eslintrc.json 생성, package.json에 의존성 추가, npm install 실행

"src/utils.ts에서 formatDate 함수를 찾아서 한국 시간대를 지원하도록 수정해줘"
→ AI가 파일 읽기 → 수정 사항 제안 → 사용자 확인 후 적용

"새로운 React 컴포넌트 UserProfile을 만들어줘"
→ AI가 src/components/UserProfile.tsx 생성, 타입 정의, 스타일 추가
```

---

## 유저 사이트 + 관리자 사이트

### 유저 사이트 (hwarang.ai)

사용자가 플랜을 선택하고, 결제하고, API 키를 발급받는 사이트입니다.

| 페이지 | 경로 | 기능 |
|--------|------|------|
| **랜딩** | `/` | 마케팅 페이지, 제품 소개 |
| **플랜/가격** | `/pricing` | Free/Pro/Business/Enterprise 선택 |
| **로그인** | `/login` | 이메일/소셜 로그인 |
| **회원가입** | `/register` | 계정 생성 |
| **대시보드** | `/dashboard` | 사용량 현황, 빠른 링크 |
| **AI 채팅** | `/chat` | AI 대화 (기존) |
| **API 키 관리** | `/api-keys` | 키 생성/삭제, 사용법 안내 |
| **결제/청구서** | `/billing` | 결제 내역, 플랜 변경 |
| **설정** | `/settings` | 계정 설정, 테마 |
| **커뮤니티** | `/community` | Grid 실시간 현황, 기여자 피드, 리더보드 |
| **API 문서** | `/docs` | 개발자 가이드 |

**사용자 흐름:**
```
회원가입 → 무료 플랜 자동 적용 → AI 채팅 사용
         → Pro 업그레이드 → 결제 (토스페이먼츠)
         → API 키 발급 → 자기 앱에서 API 호출
```

**플랜 구성 (토큰 기반):**

| 플랜 | 가격 | 월 토큰 | 하루 최대 소진 | 모델 | API 키 | 초과 단가 |
|------|------|---------|-------------|------|--------|----------|
| Free | 무료 | **10K** | 3K | 7B | 1개 | 불가 (리셋 대기) |
| Starter | 9,900원/월 | **100K** | 20K | 7B | 2개 | 7B: 10원/1K |
| Pro | 29,000원/월 | **500K** | 50K | 7B+30B | 5개 | 7B: 8원 / 30B: 25원 |
| Business | 99,000원/월 | **2M** | 200K | 전체 | 20개 | 7B: 5원 / 30B: 15원 |
| Enterprise | 맞춤 | 맞춤 | 맞춤 | 맞춤 | 무제한 | 맞춤 |

**토큰 추가 구매 (유효기간 없음):**

| 패키지 | 가격 | 단가 |
|--------|------|------|
| 50K 토큰 | 4,900원 | 98원/1K |
| 200K 토큰 | 15,900원 | 79.5원/1K |
| 1M 토큰 | 69,000원 | 69원/1K |

**토큰 = 대략 이만큼:**
- 짧은 질문+답변 1회 ≈ 300 토큰
- Free 10K → 약 30회 대화
- Pro 500K → 약 1,500회 대화

**하루 소진 한도:** 토큰이 남아있어도 하루에 사용할 수 있는 최대량이 정해져 있음 (폭주 방지)

### 토큰 경제 (Token Economy)

Hwarang의 모든 것은 **토큰**으로 돌아갑니다.

**토큰을 얻는 3가지 방법:**

```
┌────────────────────────────────────────────────────────┐
│               토큰을 얻는 방법                          │
│                                                         │
│  💳 결제로 구매         50K = 4,900원                   │
│  📋 플랜 구독           Pro = 월 500K 토큰 충전         │
│  🖥️ GPU 기여 (Grid)    RTX 4070 = 월 ~163K 토큰 적립  │
│                                                         │
│            ┌──────────────┐                             │
│            │   내 토큰    │                             │
│            │   잔액: 342K │                             │
│            └──────┬───────┘                             │
│                   │ 소비                                │
│     ┌─────────────┼──────────────┐                     │
│     ▼             ▼              ▼                     │
│  💬 웹 채팅    💻 VS Code    🔌 API 호출              │
│  📱 모바일     ⌨️ CLI        ⚖️ 법률/세무             │
│                                                         │
│  어디서 벌든 어디서 쓰든 같은 토큰!                     │
└────────────────────────────────────────────────────────┘
```

**GPU 기여 시나리오:**

| 유저 | GPU | Grid 적립 | 필요 추가 결제 | 실질 절약 |
|------|-----|----------|-------------|----------|
| 김개발 | RTX 4070 | 월 163K | Pro 500K - 163K = 337K (19,500원) | **33% 절약** |
| 박겜러 | RTX 4090 | 월 336K | Pro 500K - 336K = 164K (9,500원) | **67% 절약** |
| 이학생 | RTX 3060 | 월 96K | Free 10K + 96K = 106K | **돈 0원으로 Starter급** |

> GPU를 많이 기여할수록 AI를 더 저렴하게 (또는 무료로) 사용합니다.

### 관리자 사이트 (admin.hwarang.ai)

서비스 운영자를 위한 관리 도구입니다.

| 페이지 | 경로 | 기능 |
|--------|------|------|
| **대시보드** | `/admin/dashboard` | 전체 현황 (사용자, 매출, 서버, 요청) |
| **서버 모니터링** | `/admin/servers` | 마스터/서브 실시간 상태, GPU 사용률 |
| **유저 관리** | `/admin/users` | 사용자 검색, 플랜 변경, 차단 |
| **플랜 관리** | `/admin/plans` | 플랜 생성/수정/가격 변경 |
| **매출 현황** | `/admin/billing` | 월별 매출, 결제 내역, 환불 |
| **모델 관리** | `/admin/models` | 로드된 모델 목록, LoRA 어댑터 |
| **요청 로그** | `/admin/logs` | API 요청 로그, 에러 분석 |

**관리자 대시보드 핵심 지표:**
- 전체 사용자 수 / 신규 가입 / 활성 사용자
- 오늘 요청 수 / 전일 대비 변화
- 이번 달 매출 / 전월 대비 변화
- 서버 클러스터 상태 (서브 대수, GPU 사용률)
- 플랜별 사용자 분포

**관리자 접근 권한:**
- `SUPER_ADMIN`: 모든 기능
- `ADMIN`: 유저/플랜 관리 (서버 설정 제외)
- `USER`: 일반 사용자 (관리자 접근 불가)

---

## 앱 출시 계획

> 앱은 **베타 이후** (Month 7~) 에 개발합니다. 모델과 사용자가 먼저입니다.

### 플랫폼별 기술 선택

| 플랫폼 | 기술 | 비고 |
|--------|------|------|
| **iPhone / iPad** | React Native (Expo) | iOS + Android 코드 95% 공유 |
| **Android** | React Native (Expo) | 동일 코드 |
| **Windows Desktop** | Tauri | hwarang-web을 앱으로 감싸기 |
| **Mac Desktop** | Tauri | 동일 (macOS 네이티브) |

### 왜 이 기술인가?

```
모바일: React Native (Expo)
  → hwarang-web이 React(Next.js)라서 컴포넌트 재사용 가능
  → 1개 코드로 iOS + Android 동시 출시
  → Expo로 빌드/배포 자동화

데스크톱: Tauri (Rust + WebView)
  → Electron 대비 10배 작은 앱 크기 (20MB vs 200MB)
  → hwarang-web을 그대로 WebView에 로드
  → Rust로 네이티브 기능 (파일 접근, 터미널 등)
  → 메모리 사용량 1/5
```

### 앱 기능 (Claude 앱 수준)

```
모든 플랫폼 공통:
  ✅ AI 채팅 (스트리밍)
  ✅ 대화 목록/관리
  ✅ 다크/라이트 테마
  ✅ 토큰 잔액 확인
  ✅ 푸시 알림 (토큰 소진 경고)
  ✅ 오프라인 대화 기록 보기

데스크톱 전용:
  ✅ 파일 드래그 & 드롭 (코드 파일 분석)
  ✅ 시스템 트레이 상주
  ✅ 글로벌 단축키 (Cmd+Shift+H → 채팅)
  ✅ VS Code 연동

모바일 전용:
  ✅ 음성 입력
  ✅ 카메라로 코드 사진 → 분석
  ✅ 위젯 (빠른 질문)
```

### 출시 로드맵

```
Month 7:  Mac Desktop 앱 (Tauri) → 가장 빠름 (웹 그대로 감싸기)
Month 8:  Windows Desktop 앱 (Tauri)
Month 9:  iOS 앱 (React Native)
Month 10: Android 앱 (React Native)
```

### 비용

```
Apple Developer: $99/년 (iOS/Mac 배포)
Google Play: $25 (1회)
Windows: 무료 (서명 인증서 ~$200/년)
─────────────────────
총: ~$325/년
```

---

## Hwarang Grid — 분산 GPU 공유 네트워크

> **"당신의 놀고 있는 GPU가 돈이 됩니다"**

전 세계 수억 대의 GPU가 대부분의 시간 동안 놀고 있습니다.
Hwarang Grid는 이 유휴 GPU를 모아서 AI 추론과 학습에 활용하고,
기여한 만큼 **토큰으로 보상**합니다.

```
비트코인 채굴:   GPU → 무의미한 해시 계산 → 코인 보상
                 → 에너지 낭비, 사회적 비판

Hwarang Grid:   GPU → 실제 AI 서비스에 기여 → 토큰 보상
                 → 유용한 작업, 사회적 가치
```

### 작동 방식

```
┌──────────────────────────────────────────────────────────┐
│                                                           │
│   1. Grid Agent 설치 (무료)                              │
│      ↓                                                    │
│   2. API 키 입력 → 자동 등록                             │
│      ↓                                                    │
│   3. 평소에는 조용히 대기 (시스템 트레이)                │
│      ↓                                                    │
│   4. GPU가 놀고 있으면 → AI 작업 자동 수신               │
│      ↓                                                    │
│   5. 작업 처리 → 결과 전송 → 토큰 적립!                 │
│      ↓                                                    │
│   6. 게임/작업 시작하면 → 즉시 중단 (방해 0%)           │
│      ↓                                                    │
│   7. 적립된 토큰 → Hwarang AI 무료 사용                  │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### GPU별 예상 월 수익

| GPU | 성능 배수 | 시간당 | 월 적립 (16h/일) | 상당 플랜 | 전기세 | **순이익** |
|-----|----------|--------|-----------------|----------|--------|-----------|
| RTX 3060 | 1.0x | 200 | **96K** | Starter (9,900원) | 4,900원 | **+5,000원** |
| RTX 4060 Ti | 1.5x | 300 | **144K** | Pro 근접 | 5,800원 | **+13,000원** |
| RTX 4070 | 1.7x | 340 | **163K** | Pro (29,000원) | 8,100원 | **+20,900원** |
| RTX 4080 | 2.5x | 500 | **240K** | Pro+ | 13,000원 | **+35,000원** |
| RTX 4090 | 3.5x | 700 | **336K** | Pro++ | 18,000원 | **+49,000원** |
| RTX 5090 | 4.5x | 900 | **432K** | Business 근접 | 23,000원 | **+63,000원** |

> RTX 3060 기준 = 1.0x. 하루 16시간 기여 가정. 토큰 가치는 Pro 플랜 29,000원 / 500K 기준.

### 보너스 시스템

| 보너스 | 조건 | 보상 |
|--------|------|------|
| **연속 참여** | 7일 연속 | +10% 보너스 |
| | 30일 연속 | +20% 보너스 |
| | 90일 연속 | +30% 보너스 |
| **친구 초대** | 1명당 | 10,000 토큰 |
| **첫 참여** | 최초 등록 | 5,000 토큰 웰컴 |

### 유저 사용법

```bash
# 1. hwarang.ai에서 가입 + API 키 발급

# 2. Grid Agent 설치 + 실행 (원클릭)
hwarang-grid start --api-key hk-xxxxx

# 3. 시스템 트레이에 상주 (백그라운드)
#    GPU 놀 때: 자동 작업 → 토큰 적립
#    게임/작업 시: 자동 중단 → 방해 0%

# 4. 실시간 현황 확인
#    [시스템 트레이] 오늘: +2,340 토큰 | 총: 45,230 토큰

# 5. 적립 토큰으로 Hwarang AI 사용!
```

### 선순환 구조

```
┌──────────────────────────────────────────────┐
│                                               │
│    유저가 Grid Agent 설치                     │
│         ↓                                     │
│    GPU 기여 → 토큰 적립                      │
│         ↓                                     │
│    토큰으로 AI 무료 사용                      │
│         ↓                                     │
│    "좋다!" → 친구에게 추천                    │
│         ↓                                     │
│    더 많은 유저 = 더 많은 GPU                 │
│         ↓                                     │
│    서비스 품질 향상 + 비용 감소               │
│         ↓                                     │
│    더 많은 사용자 유입                         │
│         ↓                                     │
│    🔄 반복 (네트워크 효과)                    │
│                                               │
└──────────────────────────────────────────────┘
```

### Hwarang에 미치는 효과

```
Grid 참여자 규모별:

100명:    GPU 100장 → 소규모 추론 서버 대체
1,000명:  GPU 1,000장 → 클라우드 비용 월 5,000만원 절약
10,000명: GPU 10,000장 → 대형 AI 회사급 인프라
100,000명: GPU 100,000장 → GPT-4 서빙 수준

비용 비교:
  클라우드 GPU 1,000장: 월 5,000만원+ (현금)
  Grid GPU 1,000장:     월 0원 (토큰 보상만)
```

### 보안

| 위협 | 대응 |
|------|------|
| 모델 가중치 유출 | 모델을 조각내서 분배 (1유저 = 전체의 1/N, 복원 불가) |
| 잘못된 결과 제출 | 같은 작업을 2~3명에게 보내서 다수결 검증 |
| 사용자 데이터 노출 | 추론 입력/출력 E2E 암호화 |
| 가짜 작업 보고 | 랜덤 검증 작업 (정답을 아는 문제) 삽입 |
| GPU 과부하 | 사용률/온도 실시간 모니터링, 임계값 초과 시 자동 중단 |

### 출시 로드맵

```
Phase 1 (Month 1~6):  자체 서버로 서비스 출시
Phase 2 (Month 7~9):  Grid Agent 베타 (초대제 100명)
Phase 3 (Month 10+):  Grid 정식 오픈
Phase 4 (Month 12+):  Grid가 메인 인프라로 전환
```

### 비슷한 성공 사례

| 서비스 | 모델 | 규모 |
|--------|------|------|
| Folding@home | 유휴 GPU → 단백질 분석 | 1 exaFLOP 달성 |
| BOINC | 유휴 CPU → 과학 연산 | 20년+ 운영, 수백만 참여 |
| Render Network | 유휴 GPU → 3D 렌더링 | $1B+ 시가총액 |
| io.net | 유휴 GPU → AI 학습 | 2024년 급성장 |

> Hwarang Grid는 이 검증된 모델을 **한국어 AI + 토큰 생태계**로 현지화한 것입니다.

### 함께 만드는 AI

```
기존 AI 회사:
  거대 자본 → 거대 데이터센터 → AI 독점 → 비싼 가격

Hwarang:
  여러분의 GPU → 모두의 인프라 → AI 공유 → 토큰으로 무료

  1명의 GPU는 작지만
  1,000명이 모이면 데이터센터
  10,000명이 모이면 빅테크
  100,000명이 모이면 새로운 패러다임
```

> ### 왜 "함께"인가?
>
> 솔직히 말합니다. **혼자서는 무리입니다.**
>
> GPT-4를 만드는 데 수천억 원의 GPU가 필요합니다.
> 한 사람, 한 회사가 감당할 수 있는 규모가 아닙니다.
> 하지만 우리 모두의 GPU를 합치면? 이야기가 달라집니다.
>
> **한국에서 진짜 쓸만한 AI를 만들고 싶습니다.**
> 한국어를 잘 이해하고, 한국 법률을 알고, 한국 세법을 알고,
> 한국 개발자의 코딩 스타일을 아는 AI.
>
> 이건 혼자 만드는 게 아닙니다.
> **같이 만들어야 합니다.**
>
> 당신의 GPU 한 장이 학습 데이터 1GB를 처리하고,
> 옆집 개발자의 GPU가 또 1GB를 처리하고,
> 1,000명이 모이면 1TB,
> 10,000명이 모이면 10TB.
>
> 그렇게 만든 AI는 어느 한 기업의 자산이 아닙니다.
> **같이 만들었으니, 같이 씁니다.**
> 기여한 만큼 토큰으로 돌려받고, 그 토큰으로 AI를 사용합니다.
>
> 대기업이 만든 AI는 우리에게 사용료를 받습니다.
> 우리가 함께 만든 AI는 우리에게 토큰을 줍니다.
>
> **같이 만들고, 같이 쓰고, 같이 성장합시다.**
> **그것이 화랑(花郞)입니다.**

---

## 학습 데이터 수집

### 자동 다운로드

```bash
# 전체 다운로드 (텍스트 + 코드 + SFT + DPO)
python scripts/download_data.py --task all --output data/

# Pretrain 데이터만 (한국어 위키 + 영어)
python scripts/download_data.py --task pretrain --lang ko --output data/

# 코드 데이터만 (20개 프로그래밍 언어)
python scripts/download_data.py --task code --output data/

# 디자인 데이터만 (UI/UX, CSS, 컴포넌트)
python scripts/download_data.py --task design --output data/

# SFT 데이터만 (지시-응답)
python scripts/download_data.py --task sft --lang ko --output data/

# DPO 데이터만 (선호도)
python scripts/download_data.py --task dpo --output data/

# 빠른 테스트 (소량)
python scripts/download_data.py --task all --max-samples 1000 --output data/
```

### 데이터 소스

**텍스트 Pretrain:**

| 데이터셋 | 언어 | 크기 | 설명 |
|----------|------|------|------|
| Korean Wikipedia | 한국어 | ~1GB | 위키피디아 전문 |
| KLUE MRC | 한국어 | ~100MB | 뉴스 본문 |
| FineWeb (sample) | 영어 | ~10GB | 고품질 웹 텍스트 |

**코드 Pretrain (20개 언어):**

| 데이터셋 | 언어 | 크기 | 설명 |
|----------|------|------|------|
| StarCoderData | 20개 언어 | ~50GB | Python, JS, TS, Java, C, C++, Go, Rust 등 |
| GitHub Code (Python) | Python | ~10GB | MIT/Apache 라이선스 코드 |

**SFT (지시-응답):**

| 데이터셋 | 언어 | 크기 | 설명 |
|----------|------|------|------|
| KoAlpaca v1.1a | 한국어 | 52K | 한국어 지시 데이터 |
| KoVicuna 대화 | 한국어 | ~10K | 한국어 ChatGPT 대화 |
| SlimOrca | 영어 | 518K | GPT-4 생성 지시-응답 |
| Code-Alpaca | 영어 | 20K | 코드 지시 기본 |
| EvolInstruct-Code | 영어 | 80K | WizardCoder 학습 데이터 |
| Magicoder OSS | 영어 | 75K | OSS 기반 코딩 문제 |
| Glaive Code Assistant | 영어 | ~100K | 대화형 코딩 어시스턴트 |
| CommitPackFT | Python | ~100K | 커밋 메시지 + 코드 변경 |

**Design (UI/UX 디자인):**

| 데이터셋 | 용도 | 크기 | 설명 |
|----------|------|------|------|
| StarCoderData (CSS/HTML) | Pretrain | ~10GB | CSS, HTML, TSX, JSX 디자인 관련 코드 |
| Design Principles | Pretrain | ~50KB | 색상 이론, 타이포그래피, 레이아웃, 다크모드, 애니메이션 |
| WebSight | SFT | 50K | 웹 디자인 설명 → HTML/CSS 코드 생성 |
| UI Components (합성) | SFT | 6+ | Navbar, Pricing, Login, Dashboard, Modal, Hero 템플릿 |

> 프로덕션 팁: UI 컴포넌트 합성 데이터는 GPT-4/Claude로 수천 개를 추가 생성하면 디자인 능력이 크게 향상됩니다.

**DPO (선호도 정렬):**

| 데이터셋 | 크기 | 설명 |
|----------|------|------|
| UltraFeedback | 64K | 다중 모델 비교 선호도 |
| HH-RLHF (Anthropic) | ~170K | 안전성 중심 선호도 |

**지원 프로그래밍 언어 (20개):**

```
Python, JavaScript, TypeScript, Java, C, C++, C#,
Go, Rust, Ruby, PHP, Swift, Kotlin, Scala,
Shell/Bash, SQL, HTML, CSS, R, Lua
```

---

## 전체 학습 파이프라인

처음부터 끝까지의 전체 과정:

```bash
# ===== 1. 데이터 준비 =====
python scripts/download_data.py --task all --output data/

# ===== 2. 토크나이저 학습 =====
cd modules/hwarang-core
poetry run python scripts/train_tokenizer.py \
  --data ../../data/pretrain/ko_wiki.txt \
  --output ./tokenizer_output \
  --vocab-size 32000

# ===== 3. 데이터 토큰화 =====
poetry run python -c "
from hwarang_core.data.pipeline import DataPipeline
from hwarang_core.tokenizer import HwarangTokenizer

tokenizer = HwarangTokenizer('./tokenizer_output')
pipeline = DataPipeline(tokenizer)

# Pretrain 데이터
stats = pipeline.process('../../data/pretrain/', '../../data/train.bin')
print(f'Pretrain tokens: {stats[\"total_tokens\"]:,}')
"

# ===== 4. Pretraining =====
poetry run python scripts/pretrain.py \
  --data ../../data/train.bin \
  --model-config configs/model/small.yaml \
  --train-config configs/training/pretrain.yaml

# ===== 5. SFT =====
poetry run python scripts/finetune.py \
  --checkpoint ./checkpoints/pretrain/final \
  --data ../../data/sft/ko_instructions.jsonl

# ===== 6. DPO Alignment =====
poetry run python scripts/align.py \
  --checkpoint ./checkpoints/sft/final \
  --data ../../data/dpo/preferences.jsonl

# ===== 7. 모델 내보내기 =====
poetry run python scripts/export_model.py \
  --checkpoint ./checkpoints/dpo/final \
  --output ./exported/hwarang-small

# 토크나이저도 복사
cp -r ./tokenizer_output ./exported/hwarang-small/tokenizer

# ===== 8. API 서버 시작 =====
cd ../hwarang-api
HWARANG_MODEL_PATH=../hwarang-core/exported/hwarang-small \
  poetry run uvicorn hwarang_api.main:create_app --factory --port 8000

# ===== 9. 웹 UI 시작 (다른 터미널) =====
cd ../hwarang-web
pnpm dev

# ===== 10. CLI로 대화 (다른 터미널) =====
cd ../hwarang-cli
poetry run hwarang chat --provider hwarang --api-url http://localhost:8000
```

---

## Docker 배포

### 단일 서버 (Local Mode)

```bash
# .env 파일 생성
cp .env.example .env
# .env 편집: DB_PASSWORD, NEXTAUTH_SECRET 등 설정

# 모델 파일을 Docker 볼륨에 복사
docker volume create hwarang-models
docker run --rm -v hwarang-models:/models -v $(pwd)/modules/hwarang-core/exported:/src alpine \
  cp -r /src/hwarang-small /models/

# 전체 시작 (PostgreSQL + Redis + API + Web)
docker compose -f docker/docker-compose.yml up --build

# 접속
# API: http://localhost:8000
# Web: http://localhost:3000
```

### 개별 서비스만 시작

```bash
# DB만 (개발 시)
docker compose -f docker/docker-compose.yml up postgres redis -d

# API만
docker build -f docker/api.Dockerfile -t hwarang-api .
docker run -p 8000:8000 hwarang-api

# Web만
docker build -f docker/web.Dockerfile -t hwarang-web .
docker run -p 3000:3000 -e HWARANG_API_URL=http://host.docker.internal:8000 hwarang-web
```

---

## 다중 서버 분산 배포 (Distributed Mode)

### 서버 역할 구분: 마스터 vs 서브

Hwarang 클러스터에서 각 서버는 명확한 역할을 가집니다.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                        Hwarang 클러스터 구조                               │
│                                                                           │
│  ┌──────────────────────────────────────────────┐                        │
│  │           마스터 서버 (Master)                 │   GPU 불필요          │
│  │                                               │                       │
│  │  ┌──────────┐ ┌──────┐ ┌──────┐ ┌──────────┐│                       │
│  │  │ API 서버 │ │Redis │ │  DB  │ │ Web UI   ││                       │
│  │  │(FastAPI) │ │(큐)  │ │(PG)  │ │(Next.js) ││                       │
│  │  └────┬─────┘ └──┬───┘ └──────┘ └──────────┘│                       │
│  │       │          │                            │                       │
│  └───────┼──────────┼────────────────────────────┘                       │
│          │          │                                                     │
│          │     Redis Queue (요청 분배)                                    │
│          │          │                                                     │
│  ┌───────┼──────────┼──────────────────────────────────────────────────┐ │
│  │       ▼          ▼          서브 서버들 (Sub / Worker)               │ │
│  │                                                                     │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │ │
│  │  │  서브 1    │  │  서브 2    │  │  서브 3    │  │  서브 N    │   │ │
│  │  │            │  │            │  │            │  │            │   │ │
│  │  │ GPU: 5090  │  │ GPU: 5090  │  │ GPU: 4090  │  │ GPU: 5090  │   │ │
│  │  │ 모델: 30B  │  │ 모델: 30B  │  │ 모델: 7B   │  │ 모델: 30B  │   │ │
│  │  │ 역할: 추론 │  │ 역할: 추론 │  │ 역할: 빠른 │  │ 역할: 추론 │   │ │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

### 마스터 서버 (Master) - 두뇌

마스터는 **직접 추론하지 않습니다.** 모든 요청을 관리하고 서브에게 분배합니다.

| 역할 | 설명 |
|------|------|
| **API Gateway** | 모든 클라이언트 요청의 진입점 |
| **로드밸런서** | 요청을 서브 서버에 분배 |
| **하이브리드 라우터** | 요청 종류에 따라 적절한 서브 선택 |
| **인증/과금** | API 키 검증, 사용량 추적, 결제 |
| **Redis** | 요청 큐, 서브 등록, 하트비트 관리 |
| **PostgreSQL** | 사용자, 대화, 결제 데이터 |
| **Web UI** | Next.js 프론트엔드 서빙 |
| **서브 감시** | 하트비트 확인, 죽은 서브 자동 제거 |

**마스터에서 실행하는 것:**
```bash
# API 서버 (분산 모드)
HWARANG_DISTRIBUTED=true \
HWARANG_REDIS_URL=redis://localhost:6379 \
  make dev-api

# 웹 UI
make dev-web

# Redis (같은 서버 또는 별도)
redis-server

# PostgreSQL
pg_ctl start
```

**마스터 하드웨어 (GPU 불필요):**
```
CPU:  아무거나 (4코어 이상)
RAM:  16~32GB
SSD:  256GB
GPU:  ❌ 필요 없음
네트워크: 1Gbps 이상

예시: Mac Mini M4 24GB (~150만원)
     또는 일반 PC (~50만원)
     또는 클라우드 VM (~월 5만원)
```

### 서브 서버 (Sub / Worker) - 근육

서브는 **추론만 합니다.** 다른 건 신경 쓰지 않습니다.

| 역할 | 설명 |
|------|------|
| **모델 로드** | GPU에 AI 모델을 올려둠 |
| **추론 처리** | Redis 큐에서 요청 가져와서 GPU로 처리 |
| **결과 반환** | 처리 결과를 Redis를 통해 마스터에 전달 |
| **하트비트** | 5초마다 마스터에 "살아있다" 보고 |
| **자동 등록** | 시작하면 자동으로 클러스터에 합류 |

**서브에서 실행하는 것:**
```bash
# Worker 노드 (이것만 실행하면 됨)
poetry run python -m hwarang_api.distributed.worker \
  --model-path /data/models/hwarang-code-30b \
  --model-id hwarang-code-30b \
  --redis-url redis://마스터IP:6379 \
  --device cuda
```

**서브 하드웨어 (GPU 필수):**
```
CPU:  16코어 이상 (데이터 전처리)
RAM:  64~128GB
SSD:  1TB (모델 저장)
GPU:  ⭐ RTX 5090 32GB (핵심)
네트워크: 1Gbps 이상

예시: 9950X3D + RTX 5090 (~745만원)
```

### 마스터 vs 서브: 한눈에 비교

| 항목 | 마스터 (Master) | 서브 (Sub/Worker) |
|------|----------------|-------------------|
| **역할** | 관리, 분배, DB | 추론 (GPU 연산) |
| **GPU** | ❌ 불필요 | ⭐ 필수 |
| **CPU** | 가벼움 (4코어+) | 보통 (16코어+) |
| **RAM** | 16~32GB | 64~128GB |
| **개수** | 1~2대 (이중화) | N대 (무한 확장) |
| **비용** | 저렴 (~150만원) | 비쌈 (~745만원/대) |
| **죽으면?** | 서비스 중단 | 다른 서브가 처리 |
| **추가하면?** | 의미 없음 | 처리량 비례 증가 |
| **실행 명령** | `make dev-api` | `worker --redis-url ...` |
| **인터넷** | 외부 공개 | 내부망만 (보안) |

### 서브 서버 유형: 4가지 역할

서브 서버도 용도에 따라 역할을 나눌 수 있습니다:

```
┌────────────────────────────────────────────────────────────┐
│                 서브 서버 역할 분류                          │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  유형 A: 빠른 응답 서브 (Fast Worker)                      │
│  ─────────────────────────────                             │
│  모델: 7B FP16                                             │
│  용도: 코드 완성, 짧은 질문, VS Code 인라인               │
│  속도: ~125 tok/s (0.4초)                                  │
│  GPU:  RTX 5090 또는 RTX 4090                              │
│                                                            │
│  유형 B: 고품질 서브 (Quality Worker)                      │
│  ─────────────────────────────────                         │
│  모델: 30B INT4                                            │
│  용도: 법률 분석, 세무 계산, 복잡한 코딩                   │
│  속도: ~45 tok/s (1.5초)                                   │
│  GPU:  RTX 5090 (32GB 필수)                                │
│                                                            │
│  유형 C: 고속 분할 서브 (Tensor Parallel Worker)           │
│  ─────────────────────────────────────────                 │
│  모델: 30B INT4 (GPU 2장에 분할)                           │
│  용도: 최고 속도가 필요한 유료 사용자                      │
│  속도: ~80 tok/s (0.9초)                                   │
│  GPU:  RTX 5090 × 2 (같은 서버에 2장)                     │
│                                                            │
│  유형 D: 추측 디코딩 서브 (Speculative Worker)             │
│  ───────────────────────────────────────────               │
│  모델: 7B(draft) + 30B(target) 동시 로드                   │
│  용도: GPU 1장으로 최대 성능                               │
│  속도: ~100 tok/s (0.7초)                                  │
│  GPU:  RTX 5090 1장 (32GB에 둘 다 로드)                   │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 실전 클러스터 구성 예시

#### 소규모 (베타, 사용자 ~50명)

```
[마스터] Mac Mini M4 24GB (150만원)
  ├─ API 서버, Redis, DB, Web UI
  │
[서브 1] 9950X3D + RTX 5090 (745만원)
  ├─ 유형 D: Speculative (7B + 30B)
  ├─ 속도: ~100 tok/s
  └─ 동시 2~3명 처리

총 비용: ~895만원
응답 시간: 0.7초
```

#### 중규모 (정식 출시, 사용자 ~500명)

```
[마스터] 클라우드 VM 또는 전용 서버
  ├─ API 서버 × 2 (이중화)
  ├─ Redis Cluster
  ├─ PostgreSQL
  │
[서브 1] RTX 5090 → 유형 A: Fast (7B)
  ├─ VS Code 인라인, 짧은 질문
  ├─ 속도: 0.4초
  │
[서브 2] RTX 5090 → 유형 D: Speculative (7B+30B)
  ├─ 법률/세무/복잡한 코딩
  ├─ 속도: 0.7초
  │
[서브 3] RTX 5090 → 유형 D: Speculative (7B+30B)
  ├─ 동시 처리량 확보
  ├─ 속도: 0.7초

총 비용: ~2,400만원
응답 시간: 0.4~0.7초
동시 사용자: ~50명
```

#### 대규모 (성장 후, 사용자 ~5,000명)

```
[마스터 1+2] 이중화 (Active-Active)
  ├─ API 서버 × 4 (nginx로 로드밸런싱)
  ├─ Redis Cluster (3노드)
  ├─ PostgreSQL (Primary + Replica)
  │
[서브 1~3]  유형 A: Fast (7B) × 3대
  ├─ 일반 질문, 코드 완성
  │
[서브 4~6]  유형 D: Speculative (7B+30B) × 3대
  ├─ 복잡한 질문, 도메인 특화
  │
[서브 7~8]  유형 C: Tensor Parallel (30B, GPU 2장) × 2대
  ├─ Pro 사용자 전용 (최고 속도)
  │
[서브 9]    유형 B: Quality (30B INT8) × 1대
  ├─ 최고 품질 (기업 고객 전용)

총 비용: ~8,000만원
응답 시간: 0.4~0.9초
동시 사용자: ~500명
```

### 마스터가 서브를 선택하는 로직

마스터의 하이브리드 라우터가 요청을 분석해서 **적절한 서브 유형**을 자동 선택합니다:

```
요청이 들어오면:

1. 사용자 등급 확인
   ├─ Free  → 유형 A (Fast, 7B) → 빠르지만 기본 품질
   ├─ Pro   → 유형 D (Speculative, 30B) → 빠르고 고품질
   └─ Biz   → 유형 C (Tensor Parallel) → 최고 속도

2. 요청 복잡도 분석
   ├─ 짧은 질문 (< 50자)     → 유형 A (7B, 0.4초)
   ├─ 코드 생성               → 유형 D (30B, 0.7초)
   ├─ 법률/세무 분석          → 유형 D (30B, 0.7초)
   └─ 긴 문서 분석 (> 1000자) → 유형 B (30B INT8, 3초)

3. 부하 분산
   ├─ 같은 유형의 서브가 여러 대면
   ├─ 가장 한가한 서브에 배정
   └─ 모든 서브가 바쁘면 큐에서 대기
```

### Docker Compose로 클러스터 시작

```bash
# 전체 클러스터 시작 (마스터 + 서브 2대)
docker compose -f docker/docker-compose.distributed.yml up --build

# 서브 서버 5대로 확장 (무중단)
docker compose -f docker/docker-compose.distributed.yml up --scale worker=5 --no-recreate -d

# 클러스터 상태 확인
curl http://localhost:8000/admin/cluster/status | python -m json.tool

# 클러스터 종료
docker compose -f docker/docker-compose.distributed.yml down
```

### 수동 설정 (서버별 명령어)

```bash
# ================================================================
# 마스터 서버 (서버 A - GPU 불필요)
# ================================================================

# Redis 시작
redis-server --bind 0.0.0.0 --protected-mode no

# PostgreSQL 시작
pg_ctl start

# API 서버 (분산 모드)
HWARANG_DISTRIBUTED=true \
HWARANG_REDIS_URL=redis://localhost:6379 \
  make dev-api

# 웹 UI
make dev-web

# ================================================================
# 서브 서버 1 (서버 B - GPU: RTX 5090, 유형 D: Speculative)
# ================================================================

# 7B(draft) + 30B(target) 동시 로드
poetry run python -m hwarang_api.distributed.worker \
  --model-path /data/models/hwarang-code-30b \
  --model-id hwarang-code-30b \
  --redis-url redis://서버A_IP:6379 \
  --device cuda \
  --engine speculative \
  --draft-model /data/models/hwarang-code-7b

# ================================================================
# 서브 서버 2 (서버 C - GPU: RTX 4090, 유형 A: Fast)
# ================================================================

# 7B만 로드 (빠른 응답)
poetry run python -m hwarang_api.distributed.worker \
  --model-path /data/models/hwarang-code-7b \
  --model-id hwarang-code-7b \
  --redis-url redis://서버A_IP:6379 \
  --device cuda

# ================================================================
# 서브 서버 3 (서버 D - GPU: RTX 5090 × 2, 유형 C: Tensor Parallel)
# ================================================================

# 30B를 GPU 2장에 분할
poetry run python -m hwarang_api.distributed.worker \
  --model-path /data/models/hwarang-code-30b \
  --model-id hwarang-code-30b \
  --redis-url redis://서버A_IP:6379 \
  --device cuda \
  --engine tensor_parallel \
  --gpu-ids 0,1

# ================================================================
# 서브 서버 N (새 서버 추가 - 자동으로 클러스터에 합류)
# ================================================================

# 같은 명령어만 실행하면 자동 등록됨
# 모델이 로컬에 없으면 마스터에서 자동 다운로드!
poetry run python -m hwarang_api.distributed.worker \
  --model-path /data/models/hwarang-code-30b \
  --model-id hwarang-code-30b \
  --redis-url redis://서버A_IP:6379
```

### 서브 서버 자동 모델 다운로드

서브 서버에 모델이 없어도 **자동으로 가져옵니다.** 마스터에서 모델 소스만 등록하면 됩니다.

```bash
# Step 1: 마스터에서 모델 소스 등록 (1회만)
curl -X POST http://마스터:8000/admin/models/register-source \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "hwarang-code-30b",
    "source_type": "rsync",
    "host": "마스터IP",
    "path": "/mnt/nvme2/hwarang/models/hwarang-code-30b"
  }'

# Step 2: 서브 서버에서 Worker 실행 (모델이 없어도 OK!)
poetry run python -m hwarang_api.distributed.worker \
  --model-path /models/hwarang-code-30b \
  --model-id hwarang-code-30b \
  --redis-url redis://마스터IP:6379

# → 자동으로:
#   1. /models/hwarang-code-30b 확인 → 없음
#   2. Redis에서 소스 정보 확인 → rsync
#   3. rsync로 마스터에서 복사 (~30GB, 1Gbps → 약 4분)
#   4. 복사 완료 → 모델 로드 → 추론 시작
```

**지원하는 다운로드 방식:**

| 방식 | 설정 | 용도 |
|------|------|------|
| **rsync** | host + path | 마스터에서 직접 복사 (가장 빠름, 추천) |
| **scp** | host + path | SSH 복사 |
| **http** | url | MinIO/S3에서 다운로드 (대규모) |
| **hf** | hf_repo | Hugging Face Hub에서 다운로드 |

### 클러스터 관리 API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/admin/cluster/status` | 전체 상태 (마스터/서브 현황) |
| GET | `/admin/cluster/workers` | 서브 서버 목록 + 유형 + 상태 |
| GET | `/admin/cluster/models` | 로드된 모델 + 어떤 서브에 있는지 |
| POST | `/admin/models/deploy` | **학습 완료 → 서브 자동 배포** |
| GET | `/admin/models/deploy/status` | 배포 진행 상태 확인 |
| POST | `/admin/models/rollback` | 이전 버전으로 롤백 |
| POST | `/admin/models/register-source` | 모델 다운로드 소스 등록 |

### 무중단 모델 업데이트

학습이 완료되면 서브 서버를 중단하지 않고 새 모델을 배포합니다.

```bash
# 1. 학습 완료 → 새 버전 내보내기
make export  # → /mnt/nvme2/hwarang/models/hwarang-code-30b-v2.1

# 2. 마스터에서 배포 명령 (1줄)
curl -X POST http://마스터:8000/admin/models/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "hwarang-code-30b",
    "version": "v2.1",
    "source_path": "/mnt/nvme2/hwarang/models/hwarang-code-30b-v2.1",
    "source_host": "192.168.1.100"
  }'

# 3. 배포 상태 확인
curl http://마스터:8000/admin/models/deploy/status?model_id=hwarang-code-30b

# 4. 문제 시 롤백
curl -X POST http://마스터:8000/admin/models/rollback \
  -d '{"model_id": "hwarang-code-30b"}'
```

**동작 순서:**
```
배포 명령
  ↓
각 서브가 이벤트 수신
  ↓
백그라운드로 새 모델 다운로드 (기존 모델로 계속 서비스!)
  ↓
다운로드 완료 → 심볼릭 링크 교체 (핫 스왑, <1초)
  ↓
새 모델로 서비스 시작
  ↓
이전 버전 2세대까지 보관 (롤백 가능)
```

### 자동 문제 감지 + 자동 롤백

배포 후 자동으로 모니터링하여 문제를 실시간 감지합니다.

**감지하는 문제:**

| 문제 | 감지 방법 | 자동 대응 |
|------|----------|----------|
| **배포 실패** | 다운로드/로드 오류 | 기존 모델 유지 + 알림 |
| **에러율 급증** | 배포 전 대비 2배 이상 | 자동 롤백 + 알림 |
| **응답 속도 저하** | 배포 전 대비 2배 이상 느림 | 경고 알림 |
| **모델 품질 저하** | 테스트 프롬프트 자동 실행 | 자동 롤백 + 알림 |
| **GPU 과열** | 90도 이상 | 경고 알림 |
| **GPU 메모리 초과** | 95% 이상 | 경고 알림 |
| **서브 서버 죽음** | 하트비트 15초 없음 | 다른 서브로 트래픽 이동 |

**배포 후 자동 검증 흐름:**

```
모델 배포 완료
  ↓
자동 테스트 프롬프트 실행 (3개):
  "안녕하세요" → 한국어 응답 확인
  "1+1은?" → 기본 추론 확인
  "파이썬으로 hello world" → 코드 생성 확인
  ↓
통과 → 정상 서비스 ✅
  ↓
실패 → 자동 롤백 + Slack/이메일 알림 🚨
```

**알림 설정:**

```bash
# Slack 웹훅으로 알림 받기
# configs/monitor.yaml 또는 환경변수:
HWARANG_ALERT_WEBHOOK=https://hooks.slack.com/services/T.../B.../xxx
HWARANG_ALERT_EMAIL=admin@persismore.com
```

```bash
curl http://마스터:8000/admin/cluster/status

# 응답 예시:
{
  "mode": "distributed",
  "master": {
    "host": "192.168.1.10",
    "api_servers": 1,
    "redis": "connected",
    "db": "connected"
  },
  "workers": {
    "total": 3,
    "idle": 2,
    "busy": 1,
    "types": {
      "fast (7B)": 1,
      "speculative (7B+30B)": 1,
      "tensor_parallel (30B×2GPU)": 1
    }
  },
  "total_gpus": 4,
  "models": {
    "hwarang-code-7b": ["sub-1", "sub-2"],
    "hwarang-code-30b": ["sub-2", "sub-3"]
  }
}
```

### 서브 서버 자동 관리

| 기능 | 설명 |
|------|------|
| **자동 등록** | 서브 시작 → Redis에 등록 → 마스터가 인식 |
| **하트비트** | 5초마다 "살아있다" 보고 |
| **자동 제거** | 15초 무응답 → 마스터가 제거 |
| **Graceful Shutdown** | SIGTERM → 처리 중인 요청 완료 후 종료 |
| **모델별 큐** | 7B 요청 → 7B 서브만 / 30B 요청 → 30B 서브만 |
| **무중단 추가** | 새 서브 시작만 하면 자동 합류 (설정 변경 불필요) |
| **무중단 제거** | 서브 종료 → 다른 서브가 이어받음 |

### 장애 복구 (Fault Tolerance)

서버가 죽거나 연결이 끊어져도 서비스가 계속 동작합니다.

```
사용자 질문 → 서브1 처리 중... → 서브1 사망 💀
                                    │
                                    ▼
                        자동 감지 (타임아웃 15초)
                                    │
                                    ▼
                        다른 서브2에 자동 재전송 ✅
                                    │
                                    ▼
                        사용자에게 응답 도착 (약간 느려질 뿐)
```

| 장애 상황 | 자동 처리 |
|----------|----------|
| **서브가 추론 중 사망** | 다른 서브에 자동 재전송 (최대 3회 재시도) |
| **네트워크 일시 끊김** | Exponential backoff로 재시도 (0.1초 → 0.2초 → 0.4초) |
| **서브 연속 5회 실패** | Circuit Breaker: 60초간 차단 → 다른 서브로 우회 |
| **모든 서브 죽음** | Dead Letter Queue에 저장 → 서브 복구 후 재처리 |
| **스트리밍 중 끊김** | "[연결 재시도 중...]" 표시 후 다른 서브로 처음부터 재시도 |

```bash
# 장애 복구 상태 확인
curl http://마스터:8000/admin/cluster/status

# 응답에 포함:
{
  "fault_tolerance": {
    "total_requests": 1000,
    "completed": 995,
    "retried_at_least_once": 12,
    "failed": 0,
    "success_rate": "99.5%",
    "circuit_breakers": {
      "sub-1": {"state": "closed", "failures": 0},
      "sub-2": {"state": "open", "failures": 5}
    }
  }
}
```

### 비용 vs 성능 가이드

| 구성 | 마스터 | 서브 | 총 비용 | 응답 시간 | 동시 사용자 |
|------|--------|------|---------|----------|-----------|
| **1대** (개발) | 겸용 | 겸용 | 745만원 | 1.5초 | 1~2명 |
| **2대** (베타) | Mac Mini | 5090 × 1 | 895만원 | 0.7초 | 5~10명 |
| **4대** (출시) | 전용 | 5090 × 3 | 2,400만원 | 0.4~0.7초 | 50명 |
| **10대** (성장) | 이중화 | 5090 × 8 | 6,500만원 | 0.4초 | 500명 |

> 서브 서버만 추가하면 처리량이 비례해서 증가합니다.
> 마스터는 1~2대면 사용자 수만 명까지 버팁니다 (추론 안 하니까 가벼움).

---

## AI 패턴 (Advanced Patterns)

Hwarang에 구현된 최신 AI 기법 10가지입니다.

### 구현 현황

| # | 패턴 | 상태 | 설명 | 효과 |
|---|------|------|------|------|
| 1 | **RAG** | ✅ 구현 | 검색 증강 생성 (Vector DB + 하이브리드 검색) | 환각 제거, 출처 표시 |
| 2 | **Function Calling** | ✅ 구현 | LLM이 함수 호출 (세무 계산, 코드 실행) | 실제 작업 수행 |
| 3 | **Safety / Guardrails** | ✅ 구현 | 유해 콘텐츠 차단, 인젝션 방지, PII 마스킹 | 서비스 안전성 |
| 4 | **Structured Output** | ✅ 구현 | JSON 모드 (스키마 강제) | API 통합 용이 |
| 5 | **Multi-turn Memory** | ✅ 구현 | 이전 세션 대화 기억 (Vector DB) | 맥락 유지 |
| 6 | **Chain-of-Thought** | ✅ 구현 | 단계별 추론 (도메인별 CoT 프롬프트) | 추론 정확도 향상 |
| 7 | **Long Context** | ✅ 구현 | 128K+ (NTK RoPE 스케일링 + 슬라이딩 윈도우) | 긴 문서 처리 |
| 8 | **MoE** | ✅ 구현 | Mixture of Experts (N개 중 K개만 활성화) | 30B 품질 + 8B 속도 |
| 9 | **Vision** | ✅ 구현 | 이미지 이해 (CLIP + Projection) | 스크린샷/문서 분석 |
| 10 | **Agentic** | ✅ 구현 | 자율 에이전트 (ReAct, Plan-Execute, Reflection) | 복잡한 작업 자동화 |
| 11 | **Embedding API** | ✅ 구현 | 텍스트→벡터 변환 (RAG/검색 필수) | 유사도 검색 |
| 12 | **Streaming** | ✅ 구현 | SSE + WebSocket 통합 (중단 버튼 지원) | 실시간 응답 |
| 13 | **Prompt Template** | ✅ 구현 | 도메인별 프롬프트 관리 (버전/A/B) | 프롬프트 품질 |
| 14 | **Output Parser** | ✅ 구현 | 코드/JSON/마크다운/출처 자동 추출 | 구조화된 결과 |
| 15 | **Hallucination Detection** | ✅ 구현 | RAG 답변 vs 출처 비교 검증 | 환각 방지 |
| 16 | **Token Counter** | ✅ 구현 | 정확한 토큰 수 계산 (과금 정확성) | 과금 신뢰 |
| 17 | **Conversation Summarizer** | ✅ 구현 | 긴 대화 자동 요약 (토큰 절약) | 컨텍스트 효율 |
| 18 | **Multi-Model Router** | ✅ 구현 | 질문 난이도→7B/30B 자동 선택 | 비용 최적화 |

### 패턴별 활용 예시

```
[코딩 작업]
  Chain-of-Thought → 문제 분석 → 알고리즘 설계 → 코드 작성 → 검증
  Function Calling → 코드 실행 → 결과 확인
  Reflection → 자기 코드 리뷰 → 개선

[법률 질문]
  RAG → 법령/판례 검색 → 관련 조문 인용
  Safety → 면책 조항 자동 추가
  Structured Output → 판례 분석 결과를 JSON으로

[세무 계산]
  Chain-of-Thought → 과세 요건 → 세율 → 공제 → 세액 순서
  Function Calling → calculate_tax() 실제 계산
  RAG → 관련 세법 조항 검색 + 인용

[복잡한 프로젝트]
  Agentic (Plan-Execute) → 계획 수립 → 단계별 실행
  Multi-turn Memory → 이전 작업 내용 기억
  Long Context → 프로젝트 전체 파일 분석
```

### 파일 구조

```
hwarang-core/src/hwarang_core/
├── rag/
│   └── retriever.py          # Vector DB (Chroma/Qdrant/FAISS) + 하이브리드 검색
├── patterns/
│   ├── function_calling.py   # 함수 호출 레지스트리 + 실행
│   ├── safety.py             # 안전 필터 (입력/출력 검사)
│   ├── structured_output.py  # JSON 추출 + 스키마 검증
│   ├── memory.py             # 장기 기억 (Vector DB 기반)
│   ├── chain_of_thought.py   # CoT 프롬프트 (도메인별)
│   ├── long_context.py       # NTK RoPE + 슬라이딩 윈도우 + 압축
│   ├── moe.py                # MoE 라우터 + Expert 레이어
│   ├── vision.py             # CLIP 인코더 + LLM 프로젝션
│   └── agentic.py            # ReAct + Plan-Execute + Reflection
```

### 앞으로의 방향

```
Phase 1 (현재):
  ✅ 10개 패턴 기본 구현 완료
  → 모든 패턴의 코어 로직이 동작하는 상태

Phase 2 (출시 전):
  - RAG: 법률/세무 Vector DB 구축 + 실제 데이터 인덱싱
  - Safety: 한국어 유해 콘텐츠 사전 확장
  - Function Calling: 세무 계산기, 법령 검색 등 실제 도구 연결
  - Agentic: VS Code 확장에서 ReAct 에이전트 활용

Phase 3 (출시 후):
  - MoE: 자체 MoE 모델 학습 (8x4B = 32B, 활성 8B)
  - Vision: 코드 스크린샷 → 분석, 문서 OCR
  - Long Context: 1M+ 토큰 (Infini-Attention 등)
  - 새로운 패턴: Self-Play, Constitutional AI, RLHF-Online
```

### 소프트웨어 설계 패턴 (Software Design Patterns)

AI 패턴 외에 서비스 운영에 필수적인 설계 패턴도 구현되어 있습니다.

| # | 패턴 | 상태 | 설명 |
|---|------|------|------|
| 1 | **Response Cache** | ✅ | 동일 질문 즉시 응답 (GPU 절약, <10ms) |
| 2 | **Priority Queue** | ✅ | Business > Pro > Free 순서 처리 |
| 3 | **Event Sourcing** | ✅ | 모든 이벤트 기록 (감사/디버깅) |
| 4 | **Webhook** | ✅ | 외부 서비스 알림 (HMAC 서명) |
| 5 | **API Versioning** | ✅ | /v1 → /v2 무중단 전환 |
| 6 | **Middleware Chain** | ✅ | 요청 파이프라인 (인증→한도→안전→캐시→추론→로깅) |
| 7 | **Plugin System** | ✅ | 외부 도구 연결 (슬랙, 웹검색 등) |
| 8 | **A/B Testing** | ✅ | 모델 v1 vs v2 품질 비교 실험 |
| 9 | **Feature Flags** | ✅ | 특정 유저/플랜만 기능 활성화 |
| 10 | **Retry + Circuit Breaker** | ✅ | 장애 복구 (자동 재시도, 서브 차단) |
| 11 | **Rate Limiting** | ✅ | 토큰 기반 한도 (일일/월간) |
| 12 | **CQRS** | ✅ | 읽기(대시보드)/쓰기(추론) 분리 |
| 13 | **Health Check** | ✅ | /health, /ready, /live 엔드포인트 |
| 14 | **Graceful Shutdown** | ✅ | 진행 중 요청 완료 후 종료 |
| 15 | **Request Tracing** | ✅ | 요청 추적 ID (마스터→서브→로그) |
| 16 | **Idempotency** | ✅ | 중복 요청 방지 (네트워크 재시도 안전) |
| 17 | **Backpressure** | ✅ | 서버 과부하 시 503 거부 |
| 18 | **Bulkhead** | ✅ | 도메인별 자원 격리 (법률 장애 → 코딩 영향 X) |
| 19 | **Saga Pattern** | ✅ | 결제→충전→플랜변경 트랜잭션 (실패 시 보상) |
| 20 | **Observability** | ✅ | Prometheus 메트릭 + 히스토그램 |
| 21 | **Blue-Green Deploy** | ✅ | 무중단 배포 (v1↔v2 전환) |
| 22 | **Canary Release** | ✅ | 점진적 배포 (5%→20%→50%→100%) |
| 23 | **Config Hot Reload** | ✅ | 재시작 없이 설정 변경 |
| 24 | **Secret Management** | ✅ | API 키/비밀번호 안전 관리 (마스킹) |

**요청 처리 흐름:**

```
요청 들어옴
  ↓
[1] 인증 미들웨어 → API 키 검증
  ↓
[2] 플랜 확인 → 토큰 잔액 + 일일 한도 체크
  ↓
[3] 우선순위 할당 → Business > Pro > Free
  ↓
[4] 안전 필터 → 유해 콘텐츠/인젝션 차단
  ↓
[5] 캐시 확인 → 히트면 즉시 반환 (<10ms)
  ↓
[6] 추론 (GPU) → 서브 서버에서 처리
  ↓
[7] 안전 필터 (출력) → PII 마스킹, 면책 조항
  ↓
[8] 토큰 차감 → 잔액 업데이트
  ↓
[9] 이벤트 기록 → Event Store
  ↓
[10] 웹훅 발송 → 설정된 URL에 알림
  ↓
응답 반환
```

---

## 고속 추론

1개의 질문을 여러 GPU가 나눠서 처리하여 응답 속도를 높입니다.

### 3가지 고속 추론 모드

| 모드 | 방식 | 속도 향상 | GPU 필요 |
|------|------|---------|---------|
| **Pipeline Parallelism** | 레이어를 GPU별 분배 | ~1.8배 | 2장+ |
| **Tensor Parallelism** | 연산을 GPU별 분할 | ~1.8배 | 2장+ |
| **Speculative Decoding** | 작은 모델이 예측, 큰 모델이 검증 | ~2.5배 | **1장으로 충분** |

### 사용법

```python
# Pipeline Parallelism (GPU 2장 → 1.8배 빠름)
from hwarang_core.inference.tensor_parallel import TensorParallelEngine

engine = TensorParallelEngine(
    model_path="./exported/hwarang-code-30b",
    gpu_ids=[0, 1],            # GPU 2장에 분할
    parallel_mode="pipeline",
)

# Speculative Decoding (GPU 1장으로 2.5배 빠름!)
from hwarang_core.inference.tensor_parallel import SpeculativeDecodingEngine

engine = SpeculativeDecodingEngine(
    target_model_path="./exported/hwarang-code-30b",  # 큰 모델
    draft_model_path="./exported/hwarang-code-7b",    # 작은 모델
    device="cuda",
)
```

### 30B 모델 속도 비교 (RTX 5090 기준)

| 방식 | 속도 | 100자 답변 |
|------|------|-----------|
| 일반 (GPU 1장) | ~45 tok/s | 1.5초 |
| **Speculative Decoding** (GPU 1장) | **~100 tok/s** | **0.7초** |
| **Pipeline Parallel** (GPU 2장) | **~80 tok/s** | **0.9초** |
| Pipeline + Speculative (GPU 2장) | **~160 tok/s** | **0.4초** |

> Speculative Decoding은 추가 GPU 없이 소프트웨어만으로 2~3배 속도 향상을 달성합니다.
> 7B(draft) + 30B(target)를 RTX 5090 32GB에 동시 로드 가능합니다.

### 서버 간 통신: Redis vs gRPC

Hwarang은 서버 간 통신에 **2가지 방식**을 지원합니다:

| 방식 | 지연 | 용도 | 설정 난이도 |
|------|------|------|-----------|
| **Redis** (기본) | ~200μs | Worker 등록, 작업 큐, 상태 관리 | 매우 쉬움 |
| **gRPC** (고속) | ~100μs | 실제 추론 데이터 직접 전송 | 쉬움 |

**하이브리드 추천 (Redis + gRPC)**:
- Redis: 서브 서버 등록/발견, 하트비트, 큐 관리
- gRPC: 실제 추론 요청-응답 (Redis를 거치지 않고 직접 전송)

```bash
# Redis Worker (기본 - 간단)
python -m hwarang_api.distributed.worker \
  --model-path ./models/30b --redis-url redis://마스터:6379

# gRPC Worker (고속 - 직접 통신)
python -m hwarang_api.distributed.grpc_worker \
  --model-path ./models/30b --port 50051 --redis-url redis://마스터:6379
```

---

## 하드웨어 구성 가이드

### 추천 전략

```
학습(Training)  → 클라우드 GPU (Lambda Labs, RunPod) - 필요할 때만 시간 단위로
추론(Serving)   → Mac Mini 클러스터 - 24/7 저비용 운영
개발/테스트      → Mac Mini 1대면 충분
```

### Mac Mini M시리즈 클러스터 (추론 서빙용)

| 구성 | Mac | 역할 | 비용 |
|------|-----|------|------|
| **소규모** | M4 Pro 48GB × 3 | 1 API + 2 Worker | ~750만원 |
| **중규모** | M4 Pro + M4 Max 128GB × 2 + M4 Pro × 2 | 1 API + 2 대형 + 2 소형 | ~2500만원 |

### 모델 크기별 필요 메모리

| 모델 | 파라미터 | FP16 | INT8 | INT4 | 추천 Mac |
|------|----------|------|------|------|----------|
| small | 125M | 250MB | 125MB | 65MB | 아무거나 |
| medium | 350M | 700MB | 350MB | 175MB | M4 Pro 24GB |
| large | 1.3B | 2.6GB | 1.3GB | 650MB | M4 Pro 24GB |
| 7B급 | 7B | 14GB | 7GB | 3.5GB | M4 Pro 48GB |
| 13B급 | 13B | 26GB | 13GB | 6.5GB | M4 Max 64GB |
| 70B급 | 70B | 140GB | 70GB | 35GB | M4 Ultra 192GB |

### Mac Mini vs 클라우드 비용 (24/7 서빙)

| 기간 | Mac Mini × 4대 | 클라우드 GPU × 4 |
|------|----------------|-----------------|
| 초기 | ~1000만원 | $0 |
| 월 운영 | ~3만원 (전기) | ~400만원 |
| **12개월** | **~1036만원** | **~4800만원** |

> 6개월 이상 운영하면 Mac Mini가 경제적입니다.

### Mac Mini Worker 시작

```bash
# MPS (Metal) 가속으로 Worker 실행
PYTORCH_ENABLE_MPS_FALLBACK=1 \
poetry run python -m hwarang_api.distributed.worker \
  --model-path ./exported/hwarang-small \
  --model-id hwarang-small \
  --redis-url redis://api-server-ip:6379 \
  --device mps \
  --dtype float16   # MPS는 bfloat16 미지원, float16 사용
```

> 자세한 설정은 [docs/mac-mini-cluster.md](docs/mac-mini-cluster.md) 참고 (네트워크, 자동 시작, Redis 설정 등)

---

## 한글 성능 가이드

### 한글 인식률을 높이는 3가지 핵심

#### 1. 토크나이저 (가장 중요)

일반 BPE는 한글을 글자 단위로 쪼개서 비효율적입니다. Hwarang은 **한글 최적화 토크나이저**를 사용합니다:

```
일반 BPE:    "안녕하세요" → ["안", "녕", "하", "세", "요"]        (5토큰)
Hwarang BPE: "안녕하세요" → ["안녕", "하세요"]                    (2토큰) ← 2.5배 효율
```

한글 최적화가 하는 것:
- 한글 자모(ㄱ~ㅎ, ㅏ~ㅣ) 67개를 초기 vocab에 포함
- 자주 쓰이는 음절 150개 사전 등록 (가, 나, 다, ...)
- 조사/어미 60개 사전 등록 (은, 는, 이, 가, 을, 를, 습니다, ...)
- Pre-tokenization에서 한글 음절 블록을 하나로 유지

```bash
# 토크나이저 학습 시 자동으로 적용됨 (기본값: korean_optimized=True)
make train-tokenizer
```

#### 2. 학습 데이터 비율

한글 성능의 핵심은 **데이터 양과 비율**입니다:

| 한글 비율 | 예상 성능 | 설명 |
|-----------|----------|------|
| 2% | 낮음 | 기본적인 한글 이해만 가능 |
| 15~20% | 중간 | 자연스러운 한글 대화 가능 |
| **30~40%** | **높음** | **한글 특화 모델 (추천)** |
| 50%+ | 최고 | 영어 성능 저하 가능성 |

현재 다운로드 가능한 한글 데이터:

| 데이터셋 | 크기 | 용도 |
|----------|------|------|
| **mC4 한국어** | ~20GB | Pretrain (웹 텍스트, 가장 큼) |
| **나무위키** | ~5GB | Pretrain (백과사전) |
| **한국어 위키** | ~1GB | Pretrain (백과사전) |
| KoWikiText | ~500MB | Pretrain (정제된 텍스트) |
| KLUE 뉴스 | ~100MB | Pretrain (뉴스) |
| **KoAlpaca** | 52K | SFT (지시-응답) |
| **KO-OpenOrca** | ~100K | SFT (지시-응답) |
| KoVicuna 대화 | ~10K | SFT (대화) |

```bash
# 한국어 데이터만 집중 다운로드
make download-ko
```

#### 3. 학습 전략

**한글 특화 모델을 만드는 순서:**

```bash
# Step 1: 한국어 중심 데이터 준비 (한글 ~40%, 영어 ~40%, 코드 ~20%)
python scripts/download_data.py --task all --lang ko --output data/

# Step 2: 토크나이저는 반드시 한국어 데이터를 포함해서 학습
#   (한국어 텍스트 비율이 높을수록 한글 토큰이 많이 생성됨)
make train-tokenizer

# Step 3: Pretrain - 한국어 데이터를 충분히 포함
make pretrain

# Step 4: SFT - 한국어 지시 데이터로 파인튜닝
#   KoAlpaca + KO-OpenOrca + KoVicuna = ~162K 한국어 예제
make finetune

# Step 5: DPO - (선택) 한국어 선호도 데이터가 있으면 추가
make align
```

### 현실적 기대치

| 모델 크기 | 한글 성능 | 참고 |
|-----------|----------|------|
| 125M (small) | 간단한 질문응답, 번역 수준 | 복잡한 추론 어려움 |
| 350M (medium) | 기본 대화, 코드 설명 가능 | GPT-2 급 |
| 1.3B (large) | 자연스러운 한글 대화 | GPT-3 초기 급 |
| 7B+ | 실용적 수준 | LLaMA-2 7B 급 |

> 솔직하게 말하면, **1.3B 이하 모델**로 Claude/GPT-4 수준의 한글은 불가능합니다.
> 하지만 특정 도메인(코딩 도우미, FAQ 봇, 문서 요약 등)에 특화하면 충분히 실용적입니다.
> 범용 한글 능력을 원하면 **7B 이상 + mC4 한국어 20GB+ + SFT 162K+** 가 필요합니다.

---

## Makefile 명령어 모음

```bash
make help             # 사용 가능한 명령어 목록

# 설치
make install          # 전체 의존성 설치

# 개발 (단일 서버)
make dev-api          # API 서버 시작 (핫 리로드)
make dev-web          # 웹 UI 시작
make dev-cli          # CLI 에이전트 시작

# 개발 (다중 서버)
make dev-api-distributed  # API 서버 (분산 모드)
make dev-worker           # Worker 노드 시작

# 테스트
make test-core        # LLM 코어 테스트
make test-api         # API 서버 테스트
make test-cli         # CLI 도구 테스트
make test-web         # 웹 UI 테스트
make test-all         # 전체 테스트

# 데이터
make download-data    # 전체 학습 데이터 다운로드
make download-code    # 코드 데이터만 (20개 언어)
make download-design  # 디자인 데이터만 (UI/UX)
make download-ko      # 한국어 데이터만
make download-test    # 소량 테스트 셋

# 학습
make train-tokenizer  # BPE 토크나이저 학습
make pretrain         # 사전학습
make finetune         # SFT 파인튜닝
make align            # DPO 정렬
make export           # 모델 내보내기
make benchmark        # 추론 벤치마크

# Docker (단일 서버)
make docker-up        # 전체 스택 시작
make docker-down      # 전체 스택 종료

# Docker (다중 서버)
make cluster-up       # 분산 클러스터 시작
make cluster-scale N=5  # Worker를 5대로 확장
make cluster-status   # 클러스터 상태 확인
make cluster-down     # 클러스터 종료
```

---

## 멀티 디스크 스토리지 설정

디스크가 여러 개일 때 용도별로 데이터를 분산 저장합니다.

### 디스크 역할 분배

```
디스크 1 (4TB NVMe) - 학습용 (빠른 읽기/쓰기)
├── 토큰화된 학습 데이터 (.bin)
├── 학습 체크포인트
└── 토크나이저

디스크 2 (4TB NVMe) - Raw 데이터 (대용량)
├── 공개 데이터셋 다운로드 (~500GB)
├── GitHub/블로그 크롤링
├── AI Hub 데이터
└── 정제 데이터

디스크 3 (4TB NVMe) - 서빙 + 백업 (안정성)
├── 내보낸 모델 (추론 서버용)
├── LoRA 어댑터
├── Vector DB (RAG)
└── 백업
```

### 설정 방법

**방법 1: storage.yaml (추천)**

```bash
# configs/storage.yaml 수정
vi configs/storage.yaml

# 디렉토리 자동 생성
make setup-storage

# 경로 확인만 (생성 안 함)
make check-storage
```

**방법 2: 환경변수**

```bash
# .env 파일에 추가
HWARANG_TRAIN_DATA_DIR=/mnt/nvme0/hwarang/train_data
HWARANG_CHECKPOINT_DIR=/mnt/nvme0/hwarang/checkpoints
HWARANG_DOWNLOAD_DIR=/mnt/nvme1/hwarang/downloads
HWARANG_MODEL_DIR=/mnt/nvme2/hwarang/models
```

**방법 3: 단일 디스크 (간편)**

```bash
# 디스크 1개에 모든 데이터 저장
python scripts/setup_storage.py --single ./data
```

### 코드에서 사용

```python
from hwarang_core.config.storage import get_storage

storage = get_storage()
print(storage.train_data)   # /mnt/nvme0/hwarang/train_data
print(storage.downloads)    # /mnt/nvme1/hwarang/downloads
print(storage.models)       # /mnt/nvme2/hwarang/models
```

모든 스크립트(학습, 데이터 수집, 서빙)가 이 설정을 참조합니다.

---

## 문제 해결

### PyTorch GPU가 인식되지 않을 때

```bash
python -c "import torch; print(torch.cuda.is_available())"

# CUDA 버전에 맞는 PyTorch 설치
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

### Apple Silicon (M1/M2/M3) 에서 학습

```bash
# MPS 백엔드 자동 감지됨. 설정에서 device를 auto로 두면 됨
# bfloat16이 지원되지 않을 수 있음 → float32 사용
poetry run python scripts/pretrain.py \
  --data data/train.bin \
  --model-config configs/model/small.yaml
# config에서 dtype: float32 로 변경
```

### 메모리 부족 (OOM)

```bash
# 배치 크기 줄이기 (configs/training/pretrain.yaml)
batch_size: 2                    # 기본 8 → 2
gradient_accumulation_steps: 16  # 기본 4 → 16 (실효 배치 크기 유지)

# 또는 small 모델 사용
--model-config configs/model/small.yaml
```

### 웹 UI에서 API 연결 실패

```bash
# 1. API 서버가 실행 중인지 확인
curl http://localhost:8000/health

# 2. .env.local 에서 URL 확인
cat modules/hwarang-web/.env.local
# HWARANG_API_URL=http://localhost:8000

# 3. CORS 설정 확인 (다른 포트에서 접속 시)
# modules/hwarang-api/src/hwarang_api/config.py 에서 cors_origins 수정
```

---

## 함께 만들어요

Hwarang은 **모두가 참여할 수 있는 프로젝트**입니다.

### 참여 방법

| 방법 | 기여 | 보상 |
|------|------|------|
| **GPU 기여** | Grid Agent 설치 → 놀고 있는 GPU 공유 | 토큰 적립 |
| **데이터 기여** | 한국어 학습 데이터 제보/제공 | 토큰 보상 |
| **코드 기여** | GitHub PR (버그 수정, 기능 추가) | 토큰 보상 + 컨트리뷰터 뱃지 |
| **번역 기여** | 다국어 지원 (영어, 일본어 등) | 토큰 보상 |
| **피드백** | 버그 리포트, 기능 제안 | 토큰 보상 |
| **홍보** | 블로그 글, SNS 공유, 커뮤니티 활동 | 초대 보너스 |

### 연락처

- **웹사이트**: [hwarang.ai](https://hwarang.ai)
- **GitHub**: [github.com/persismore/hwarang](https://github.com/persismore/hwarang)
- **이메일**: hello@persismore.com
- **디스코드**: (출시 후 오픈)

### 만든 사람들

**(주)퍼시스모어 (Persismore)**

> *"더 끈질기게, 더 멀리"* — Persist + More

---

## 라이선스

MIT License
