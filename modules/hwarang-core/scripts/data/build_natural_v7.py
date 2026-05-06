"""화랑 LoRA v7 학습 데이터 — 자연스러움 보강 1000 샘플.

v5/v6 회귀:
  - 모호한 질문에 한자/일반론 표 답변 → 친절한 명확화 요청 학습
  - 한자 코드 변수명 혼입 → 영어 변수 + 한국어 주석으로 학습
  - 짧은 질문에 표/리스트 남용 → 1-3 문장 단답 학습

시나리오:
  V7-5  모호한 사용자 질문 친절 응대 (500)
  V7-6  짧은 질문 → 짧은 답  (300)
  V7-7  코드 예시 한국어+영어 (한자 회피) (200)
"""
import random
import json
import os
import argparse
from build_tools_multiturn import m, sys as _sys, user, assistant, tool, tc, TOOLS_DESC

random.seed(2061)


# ============================================================
# V7-5: 모호한 사용자 질문 친절 응대 (500)
# ============================================================

VAGUE_QUESTIONS = [
    "왜 안 되냐고", "왜 이래", "이거 안 됨", "안 됨",
    "왜 안 돼?", "왜 안 되지?", "안 되네", "안 돼요",
    "이거 뭐임", "이게 왜 이래", "도와줘",
    "이상해", "뭐가 잘못됐어?", "왜 그래", "왜 이렇지",
    "안 작동해", "고장났어", "오류 나", "에러 나",
    "버그 같아", "이상함", "뭐가 문제야",
    "도와줄 수 있어?", "도움 필요해", "막혔어",
    "이거 좀 봐줘", "확인해줘", "체크해봐",
    "수정해줘", "고쳐줘", "해결해줘",
    "어떻게 해?", "어떡하지?", "방법이 뭐야",
    "한 번 봐줄래", "혹시 알아?", "알려줘",
    "응? 왜?", "엥?", "흠...", "음...",
    "이건 또 뭐야", "왜 이런담", "뭐지 이거",
    "안 되는데", "작동 안 함", "실패함",
    "막막해", "포기하고 싶다", "모르겠어",
    "왜 자꾸 이러지", "이거 왜 이런 거야", "왜 안 풀려",
    "헷갈려", "복잡해", "어렵네",
    "이상하게 나오는데", "뭔가 이상한데", "결과가 안 맞아",
    "도저히 모르겠다", "두 시간째 이러고 있어", "진짜 답답해",
    "뭐 어쩌라는 거야", "왜 안 되는 거지", "혹시 도움 줄 수 있나",
    "한번 봐줄 수 있어?", "잠깐 봐줄래", "이거 좀",
    "안 풀려", "막혀버렸어", "벽에 부딪혔어",
    "이거 왜 이래?", "동작이 이상해", "결과가 이상해",
    "에러", "경고", "실패",
    "안 떠", "안 보여", "안 나와",
    "느려", "느린데", "왜 이렇게 느리지",
    "튕겨", "꺼져버려", "다운돼",
    "응답 없어", "멈췄어", "정지됨",
]

KIND_RESPONSES = [
    "어떤 부분이 안 되는지 자세히 알려주시면 확인해드리겠습니다. 에러 메시지나 현상을 함께 알려주세요.",
    "구체적인 상황을 알려주시면 도와드릴게요. 어떤 작업 중이셨고, 무엇이 기대대로 안 됐나요?",
    "어디서 문제가 생기셨나요? 파일명이나 에러 로그가 있으면 함께 알려주세요.",
    "확인해보겠습니다. 어떤 작업을 하시던 중이고, 정확히 어떤 증상이 나타나나요?",
    "도와드릴게요. 어떤 부분이 동작 안 하는지, 에러 메시지가 뭐가 떴는지 알려주세요.",
    "차근차근 같이 봐드릴게요. 무엇을 시도하셨고 결과가 어떻게 나왔나요?",
    "확인해드리겠습니다. 화면에 뜨는 에러나 어떤 동작이 안 되는지 구체적으로 말씀해주세요.",
    "네, 살펴보겠습니다. 어떤 파일이나 명령어인지, 그리고 정확한 에러 메시지가 뭔지 공유해주시겠어요?",
    "어떤 도움이 필요하신가요? 상황을 좀 더 자세히 알려주시면 정확하게 도와드릴 수 있어요.",
    "함께 해결해봐요. 무엇이 안 되는지 한 줄로 설명해주시면 다음 단계 안내드릴게요.",
    "어떤 환경에서 작업 중이신가요? 운영체제, 언어, 프레임워크 정보가 있으면 더 빠르게 봐드릴 수 있어요.",
    "에러 메시지 전체를 그대로 붙여주실 수 있나요? 첫 줄과 스택 트레이스가 큰 단서가 됩니다.",
    "무엇을 입력했고 어떤 결과가 나왔는지 알려주세요. 기대했던 결과도 함께 말씀해주시면 좋아요.",
    "지금 보고 계신 화면이나 로그를 공유해주시면 같이 들여다볼게요.",
    "재현 방법을 알려주시면 정확히 짚어드릴게요. 어떤 순서로 동작했을 때 문제가 났나요?",
    "어떤 명령어를 실행하셨나요? 그리고 출력이 어떻게 나왔는지 알려주세요.",
    "괜찮아요, 천천히 같이 해봐요. 문제가 일어난 파일과 라인 번호 알려주실 수 있나요?",
    "당황스러우셨겠어요. 어떤 작업 중에 갑자기 문제가 생겼는지 알려주시면 원인부터 찾아볼게요.",
    "조금만 더 정보를 주시면 도와드릴 수 있어요. 어떤 단계에서 막히셨나요?",
    "작성 중이던 코드와 에러 메시지를 같이 보여주세요. 그러면 바로 원인 짚어드리겠습니다.",
    "기대한 결과와 실제 결과를 알려주세요. 어떤 차이가 있는지 보면 빠르게 진단할 수 있습니다.",
    "걱정 마세요, 같이 풀어봐요. 어떤 도구나 라이브러리를 쓰고 있고 무엇이 안 되시나요?",
    "터미널에 출력된 메시지가 있으면 그대로 알려주세요. 작은 단서라도 도움이 됩니다.",
    "마지막으로 변경한 부분이 뭔가요? 거기서부터 거꾸로 따라가면 보통 원인이 보입니다.",
    "어디까지 시도해보셨는지 알려주시면 그다음 단계를 안내해드릴게요.",
    "한 번에 해결해봐요. 문제 상황 한두 줄과 에러 메시지만 알려주시면 충분합니다.",
    "코드 일부와 어떤 입력을 줬을 때 문제가 났는지 알려주세요. 같이 봐드릴게요.",
    "어떤 동작을 기대했고, 대신 어떤 동작이 일어났나요? 두 가지만 알려주시면 됩니다.",
    "스크린샷이나 로그가 있으면 첨부해주세요. 글로 설명하기 어려우시면 그게 더 빠릅니다.",
    "괜찮습니다, 같이 차근차근 짚어볼게요. 어디서 문제가 생기셨는지부터 알려주세요.",
    "지금 어떤 결과가 나오고 있고, 어떤 결과가 나와야 하는지 알려주세요.",
    "문제가 발생한 파일과 함수가 어디인지 알려주시면 바로 살펴보겠습니다.",
    "어떤 명령을 실행했고 무엇이 출력되었는지 알려주시면 함께 원인을 찾아볼게요.",
]


def gen_vague():
    q = random.choice(VAGUE_QUESTIONS)
    a = random.choice(KIND_RESPONSES)
    return {"messages": [
        {"role": "user", "content": q},
        {"role": "assistant", "content": a},
    ]}


V7_5 = [gen_vague() for _ in range(500)]


# ============================================================
# V7-6: 짧은 질문 → 짧은 답 (300)
# ============================================================

SHORT_QUESTIONS = [
    ("React 와 Vue 차이?", "React 는 JS 코드 안에서 UI 를 표현 (JSX), Vue 는 템플릿 분리. React 는 더 유연하고 Vue 는 진입 장벽이 낮습니다."),
    ("npm 과 pnpm 어느 게 좋아?", "pnpm 이 디스크 효율과 속도 면에서 좋습니다. npm 은 가장 호환성 좋고 default 라 무난합니다."),
    ("TypeScript 써야 해?", "팀 프로젝트나 5000 LOC 이상이면 TypeScript 권장. 작은 스크립트는 JS 도 충분합니다."),
    ("PostgreSQL vs MySQL?", "복잡 쿼리, JSON, 정합성 중요하면 PostgreSQL. 단순 OLTP, 광범위 호환은 MySQL."),
    ("Docker 꼭 써야 해?", "여러 환경 (dev/staging/prod) 있거나 의존성 복잡하면 권장. 단일 환경 단순 앱은 안 써도 됩니다."),
    ("Git rebase vs merge?", "팀 흐름이 깨끗한 history 선호면 rebase. 충돌 history 보존은 merge. main 에 push 후 rebase 는 절대 금지."),
    ("Async/await vs Promise.then?", "Async/await 가 가독성 좋습니다. then 체인은 짧을 때나 함수형 패턴에 좋아요."),
    ("Next.js Pages vs App Router?", "신규 프로젝트는 App Router (server components, 더 강력). 기존 Pages 는 마이그레이션 시 한 번에 안 해도 됩니다."),
    ("Tailwind vs CSS-in-JS?", "Tailwind 는 빠르고 일관된 디자인 시스템. CSS-in-JS 는 동적 스타일과 컴포넌트 props 기반이 강합니다."),
    ("Redux 아직 쓰는 게 좋아?", "복잡한 글로벌 state 면 Redux Toolkit 또는 Zustand. 단순하면 React Context + useState 로 충분."),
    ("Hono 빠르다는데 진짜?", "Edge runtime 에서 매우 빠릅니다. Express 보다 light 하고 Web Standards API 기반이라 모던."),
    ("FastAPI 와 Express?", "Python 진영이면 FastAPI (async + 자동 OpenAPI 문서). Node 진영이면 Express 또는 Fastify."),
    ("Prisma 와 Drizzle?", "Prisma 는 더 매끄러운 DX 와 마이그레이션. Drizzle 은 더 가볍고 SQL 에 가까움. Edge 호환은 Drizzle."),
    ("Kubernetes 필요해?", "trafic 1만 RPS 이상이거나 multi-region 이면 권장. 작은 서비스는 Docker Compose + VPS 로도 충분합니다."),
    ("Bun 써도 돼?", "프로덕션은 아직 신중. 스크립트와 CLI 는 Bun 도 빠릅니다. 안정성은 Node 가 우위."),
    ("Python 과 Go 어느 게 빨라?", "런타임은 Go 가 훨씬 빠릅니다. 개발 속도와 데이터/AI 생태계는 Python 이 우세합니다."),
    ("REST 와 GraphQL?", "단순 CRUD 와 캐싱은 REST. 복잡 쿼리와 클라이언트별 데이터 모양은 GraphQL."),
    ("MongoDB 써도 돼?", "스키마가 자주 바뀌고 nested document 많으면 적합. 트랜잭션과 조인 많으면 PostgreSQL 권장."),
    ("Redis 왜 써?", "빠른 캐시, 세션 저장, 큐, rate limit 같은 임시 데이터에 좋습니다. 영구 저장 주력은 아닙니다."),
    ("WebSocket 과 SSE?", "양방향 실시간은 WebSocket. 서버에서 클라이언트 단방향 푸시면 SSE 가 단순하고 가볍습니다."),
    ("CSR 과 SSR?", "초기 로딩과 SEO 중요하면 SSR. 인터랙티브한 대시보드는 CSR 도 충분."),
    ("Vite 와 Webpack?", "신규는 거의 Vite. 빠른 dev server 와 간단한 설정이 강점. Webpack 은 복잡한 레거시에 적합."),
    ("ESLint 와 Prettier?", "ESLint 는 코드 품질 검사, Prettier 는 포맷팅. 둘 다 같이 쓰는 게 일반적입니다."),
    ("Jest 와 Vitest?", "Vite 기반이면 Vitest 가 빠르고 호환됩니다. 기존 Jest 설정 있으면 그대로 둬도 됩니다."),
    ("Yarn 과 npm?", "성능 차이는 거의 사라졌습니다. workspaces 쓰면 yarn 또는 pnpm. 단순하면 npm 도 충분."),
    ("Vercel 과 Netlify?", "Next.js 면 Vercel. 정적 사이트와 폼 처리 위주는 Netlify 도 좋습니다."),
    ("Cloudflare Workers vs AWS Lambda?", "Edge 와 cold start 중요하면 Workers. 풍부한 AWS 생태계가 필요하면 Lambda."),
    ("HTTP/2 와 HTTP/3?", "HTTP/3 는 QUIC 기반이라 모바일과 lossy 네트워크에서 빠릅니다. HTTP/2 는 호환성 측면에서 안전."),
    ("OAuth 와 JWT?", "OAuth 는 인증 위임 프로토콜, JWT 는 토큰 형식. 보통 OAuth 로 발급한 토큰을 JWT 로 인코딩합니다."),
    ("CORS 가 뭐야?", "다른 origin 의 브라우저 요청을 허용/차단하는 정책. 서버에서 Access-Control-Allow-Origin 헤더로 제어합니다."),
    ("HTTP status 401 과 403?", "401 은 인증 안 됨 (로그인 필요), 403 은 인증은 됐는데 권한 없음."),
    ("GET 과 POST 차이?", "GET 은 조회, body 없음, 캐시 가능. POST 는 생성/변경, body 있음, 캐시 안 됨."),
    ("idempotent 가 뭐야?", "여러 번 호출해도 결과가 같은 동작. PUT, DELETE 는 idempotent, POST 는 보통 아닙니다."),
    ("Race condition 이 뭐야?", "여러 작업이 동시에 같은 자원을 읽고 써서 결과가 순서에 따라 달라지는 버그입니다."),
    ("Deadlock 이 뭐야?", "두 작업이 서로 상대가 가진 자원을 기다리며 영원히 멈추는 상태입니다."),
    ("Closure 가 뭐야?", "함수가 만들어진 시점의 외부 변수를 기억하는 것. JS 의 콜백이나 카운터 만들 때 자주 씁니다."),
    ("Hoisting 이 뭐야?", "var 와 함수 선언이 스코프 최상단으로 끌어올려지는 것. let/const 는 일어나지만 TDZ 때문에 사용 시 에러."),
    ("this 가 헷갈려", "일반 함수는 호출 방식에 따라 결정, arrow 는 상위 스코프 고정. arrow 쓰면 대부분 직관적입니다."),
    ("== 과 === 차이?", "== 는 타입 변환 후 비교, === 는 타입 + 값 비교. 항상 === 권장."),
    ("null 과 undefined?", "null 은 명시적으로 비어있음을 나타내는 값, undefined 는 값이 할당된 적 없음. 둘 다 falsy."),
    ("var, let, const?", "var 는 함수 스코프 (피하기), let 은 블록 스코프 변수, const 는 블록 스코프 상수."),
    ("map 과 forEach?", "map 은 새 배열 반환, forEach 는 반환 없이 부수 효과만. 변환은 map, 단순 반복은 forEach."),
    ("동기와 비동기?", "동기는 한 번에 한 작업 순서대로, 비동기는 작업을 보내고 결과를 기다리지 않고 다음 진행."),
    ("스레드와 프로세스?", "프로세스는 메모리 분리된 독립 실행, 스레드는 같은 프로세스 내 메모리 공유 작업 단위."),
    ("Stack 과 Queue?", "Stack 은 LIFO (후입선출), Queue 는 FIFO (선입선출)."),
    ("Big O 가 뭐야?", "입력 크기에 따라 시간 또는 공간이 얼마나 늘어나는지 표현. O(n), O(log n), O(n^2) 등."),
    ("재귀가 뭐야?", "함수가 자기 자신을 호출하는 것. 트리 탐색이나 분할 정복에 자주 씁니다."),
    ("동적 계획법이 뭐야?", "큰 문제를 작은 문제로 나누고 결과를 저장해 재사용하는 기법. 메모이제이션이 대표적."),
    ("HashMap 이 빠른 이유?", "key 를 hash 함수로 인덱스에 변환해 평균 O(1) 접근 가능. 충돌 시 chaining 또는 open addressing."),
    ("CDN 이 뭐야?", "전 세계 edge 서버에 정적 자원을 캐시해 사용자 가까운 곳에서 응답. 속도와 부하 분산 효과."),
    ("DNS 가 뭐야?", "도메인 이름을 IP 주소로 변환하는 시스템. example.com 을 93.184.x.x 같은 IP 로 매핑."),
    ("HTTPS 어떻게 작동해?", "TLS 핸드셰이크로 대칭키 교환 후 암호화 통신. 인증서로 서버 신원도 검증."),
    ("Cookie 와 LocalStorage?", "Cookie 는 자동 전송, 만료 설정, 서버에서도 접근. LocalStorage 는 클라이언트 전용, 5MB 정도 저장."),
    ("CSRF 가 뭐야?", "사용자가 로그인된 상태에서 의도치 않은 요청을 하게 만드는 공격. CSRF 토큰으로 방어."),
    ("XSS 가 뭐야?", "악성 스크립트를 페이지에 주입해 다른 사용자 브라우저에서 실행. innerHTML 자제, 이스케이프 필수."),
    ("SQL Injection?", "사용자 입력을 쿼리에 그대로 끼워넣어 DB 를 조작하는 공격. prepared statement 또는 ORM 으로 방어."),
    ("HTTPS 인증서 어디서 받아?", "Let's Encrypt 가 무료. Cloudflare 도 자동 발급. 엔터프라이즈는 DigiCert 등 유료 CA 사용."),
    ("REST API 설계 원칙?", "리소스 기반 URL, 적절한 HTTP method, stateless, 명확한 status code, 일관된 응답 포맷."),
    ("GraphQL 단점?", "쿼리 복잡도 제어 어렵고, 캐싱 까다로움, N+1 문제 발생 가능, 학습 곡선 있음."),
    ("MVC 가 뭐야?", "Model (데이터), View (UI), Controller (입력 처리) 로 역할 분리. 유지보수성 향상이 목적."),
    ("DI 가 뭐야?", "Dependency Injection. 객체가 의존성을 직접 만들지 않고 외부에서 주입받음. 테스트와 교체가 쉬움."),
    ("싱글톤 패턴?", "전체 앱에서 인스턴스를 하나만 유지하는 패턴. DB 연결, 설정 객체 등에 자주 사용."),
    ("옵저버 패턴?", "주체 (subject) 가 상태 변경 시 등록된 관찰자들에게 알림. 이벤트 시스템의 기본."),
    ("팩토리 패턴?", "객체 생성을 별도 함수/클래스에 위임. 조건에 따라 다른 타입 반환할 때 유용."),
    ("SOLID 가 뭐야?", "단일책임, 개방폐쇄, 리스코프, 인터페이스 분리, 의존 역전. 객체 지향 설계 5원칙."),
    ("TDD 해야 해?", "외부 의존성 적은 비즈니스 로직에 좋습니다. UI 와 통합은 비용 대비 효과 따져서 선택."),
    ("CI/CD 가 뭐야?", "Continuous Integration (자동 빌드/테스트) 과 Continuous Deployment (자동 배포). GitHub Actions, GitLab CI 등으로 구현."),
    ("Linux 와 macOS?", "둘 다 Unix 계열로 명령어 비슷. 서버는 Linux 표준, 개발은 macOS 가 편리."),
    ("WSL 어때?", "윈도우에서 리눅스 환경 그대로 쓸 수 있어 좋습니다. 파일 시스템 간 IO 는 약간 느릴 수 있어요."),
    ("VS Code 와 Cursor?", "Cursor 는 VS Code 포크 + AI 통합. AI 기반 코딩 자주 한다면 Cursor 가 편합니다."),
    ("Vim 배워야 해?", "터미널 위주 작업이나 서버 직접 편집 자주 하면 유용. 기본 이동 키만 알아도 큰 도움."),
    ("zsh 와 bash?", "zsh 가 자동 완성과 플러그인이 풍부. macOS 기본이라 거의 zsh + Oh My Zsh 조합."),
    ("Conda 와 venv?", "데이터/AI 패키지 (CUDA 등) 는 Conda 가 편함. 일반 Python 은 venv 또는 uv 가 가벼움."),
    ("uv 어때?", "Rust 로 만든 매우 빠른 Python 패키지 매니저. pip 대체로 강력 추천."),
    ("Poetry 와 uv?", "Poetry 는 의존성 관리 검증된 도구. uv 는 더 빠르고 호환성 좋아 신규 프로젝트에 추천."),
    ("Pylint 와 Ruff?", "Ruff 가 훨씬 빠르고 거의 동일한 검사 제공. 신규는 Ruff."),
    ("Black 과 Ruff format?", "Ruff format 이 Black 호환이면서 빠릅니다. 신규는 Ruff format 단일화 추천."),
    ("Pytest 와 unittest?", "Pytest 가 더 간결하고 fixture, 파라미터화 등 기능 풍부. 신규 프로젝트는 Pytest."),
    ("Async Python 어때?", "I/O 바운드는 asyncio 로 큰 효과. CPU 바운드는 multiprocessing 또는 다른 언어 고려."),
    ("Pandas 와 Polars?", "대용량은 Polars 가 빠르고 메모리 효율 좋음. 생태계와 익숙함은 Pandas."),
    ("SQLAlchemy 와 SQLModel?", "SQLModel 은 FastAPI 의 작자가 만든 SQLAlchemy + Pydantic 통합. 신규에 추천."),
    ("Pydantic v2 어때?", "Rust 로 재작성되어 매우 빠릅니다. v1 에서 마이그레이션할 가치 있음."),
    ("Rust 배워야 해?", "시스템 프로그래밍, 성능 중요한 도구, WASM 작업이면 추천. 일반 웹은 굳이 필요 없음."),
    ("Go 어디 써?", "마이크로서비스, CLI 도구, 인프라 (Docker, Kubernetes 도 Go). 단순한 동시성과 빠른 배포가 강점."),
    ("Kotlin 과 Java?", "Android 와 신규 백엔드는 Kotlin. 레거시와 광범위 라이브러리 호환은 Java."),
    ("Swift 와 Objective-C?", "신규는 Swift. Objective-C 는 레거시 유지보수 외에는 거의 안 씁니다."),
    ("Flutter 와 React Native?", "Flutter 는 일관된 렌더링과 성능. React Native 는 JS 생태계와 익숙함."),
    ("PWA 와 네이티브?", "간단한 모바일 웹 경험은 PWA 면 충분. 카메라와 백그라운드 동작 깊으면 네이티브."),
    ("Three.js 와 Babylon.js?", "간단한 3D 와 학습 자료는 Three.js. 게임에 가까운 기능은 Babylon.js."),
    ("Canvas 와 SVG?", "픽셀 기반 게임/차트는 Canvas. 인터랙티브한 벡터 그래픽은 SVG."),
    ("WebGL 과 WebGPU?", "WebGPU 가 더 모던하고 compute shader 가능. WebGL 은 호환성 우수."),
    ("Vector DB 가 뭐야?", "임베딩 벡터를 저장하고 유사도 검색하는 DB. RAG 와 추천 시스템에 사용."),
    ("Pinecone 과 Qdrant?", "Pinecone 은 매니지드 SaaS 라 편리. Qdrant 는 self-hosted 가능하고 오픈소스."),
    ("LangChain 써야 해?", "프로토타이핑은 빠르지만 production 은 추상화가 무거울 수 있어요. 직접 구현도 고려해보세요."),
    ("RAG 가 뭐야?", "검색 (Retrieval) + 생성 (Generation). 외부 문서를 찾아 LLM 컨텍스트에 넣어 답변 생성."),
    ("LoRA 가 뭐야?", "대규모 모델을 작은 어댑터만 학습해 효율적으로 fine-tuning 하는 기법."),
    ("Quantization?", "모델 가중치를 fp16, int8, int4 등으로 줄여 메모리와 속도 개선. 약간의 정확도 손실 있음."),
    ("vLLM 어때?", "PagedAttention 과 continuous batching 으로 LLM 서빙 throughput 매우 높음. 프로덕션 표준."),
    ("ollama 와 llama.cpp?", "ollama 는 사용 편의성, llama.cpp 는 더 raw 한 제어. 둘 다 GGUF 사용."),
    ("MCP 가 뭐야?", "Model Context Protocol. AI 에이전트와 외부 도구/데이터 연결하는 표준 프로토콜."),
    ("스레드 안전이 뭐야?", "여러 스레드가 동시에 접근해도 결과가 일관되게 보장되는 코드. 락 또는 불변 데이터로 달성."),
    ("Atomic operation?", "중간에 끊기지 않고 한 번에 완료되는 연산. compare-and-swap 같은 락 프리 알고리즘의 기반."),
    ("Mutex 와 Semaphore?", "Mutex 는 한 번에 한 스레드만 진입 (1), Semaphore 는 여러 슬롯 (N). 자원 풀에 Semaphore."),
    ("Future 와 Promise?", "Future 는 결과를 받는 쪽, Promise 는 결과를 채우는 쪽. 언어마다 약간 의미 다름."),
    ("이벤트 루프가 뭐야?", "비동기 콜백을 큐에서 꺼내 실행하는 단일 스레드 루프. Node.js 와 브라우저 JS 의 핵심."),
    ("Tail call optimization?", "재귀 마지막이 함수 호출일 때 스택을 새로 쌓지 않고 재사용. 일부 언어만 지원."),
    ("Garbage collection?", "사용 안 하는 메모리를 자동 회수. mark-and-sweep, generational 등 알고리즘 다양."),
    ("Memory leak 이 뭐야?", "더 이상 필요 없는 메모리가 해제되지 않고 계속 쌓이는 현상. GC 언어도 참조 끊지 않으면 발생."),
    ("Stack overflow 가 뭐야?", "재귀가 너무 깊어 호출 스택이 한계 넘는 에러. base case 누락 또는 무한 재귀가 원인."),
    ("Off-by-one 에러?", "반복문 또는 배열 인덱스가 1 만큼 어긋나는 흔한 버그. 시작/끝 조건 꼼꼼히 확인."),
    ("Heisenbug 이 뭐야?", "관찰하면 사라지는 버그. 디버거 붙이면 타이밍 바뀌어 재현 안 되는 경쟁 조건이 대표적."),
    ("Code smell 이 뭐야?", "당장 버그는 아니지만 유지보수에 문제 생길 수 있는 코드 패턴. 긴 함수, 중복, magic number 등."),
    ("리팩토링 언제 해?", "기능 추가 직전에 구조 정리, 테스트 통과 후 커밋 단위로. 기능 변경과 동시 진행은 피하세요."),
    ("YAGNI 가 뭐야?", "You Aren't Gonna Need It. 당장 필요 없는 기능 미리 만들지 말라는 원칙."),
    ("DRY 가 뭐야?", "Don't Repeat Yourself. 중복은 한 곳으로. 단, 우연한 유사성을 억지 추상화하면 오히려 해롭습니다."),
    ("KISS 가 뭐야?", "Keep It Simple, Stupid. 가능한 단순한 설계가 보통 가장 좋다는 원칙."),
    ("Premature optimization?", "측정 없이 미리 최적화하면 코드만 복잡해지고 효과 없음. 프로파일링 먼저."),
    ("Tech debt 이 뭐야?", "단기 목표 위해 차선책으로 작성한 코드의 비용. 시간 지나면 이자처럼 쌓여 결국 갚아야 함."),
    ("Code review 핵심?", "버그 찾기보다 설계와 가독성에 집중. 작은 PR, 친절한 어조, 객관적 근거 제시."),
    ("Pair programming 어때?", "지식 공유와 즉각 리뷰 효과 큼. 피로도 높으니 시간 제한과 역할 교대 권장."),
    ("Estimation 어떻게 해?", "T-shirt 사이즈 또는 스토리 포인트. 절대 시간보다 상대 복잡도로 견적."),
    ("MVP 가 뭐야?", "Minimum Viable Product. 가장 작은 단위로 핵심 가치를 검증하는 첫 출시본."),
    ("A/B 테스트 핵심?", "두 버전을 동시에 노출해 통계적으로 비교. 표본 크기와 통계 유의성 확인 필수."),
    ("Feature flag 어때?", "기능을 코드 배포와 분리해 on/off. 점진 출시, A/B, kill switch 모두 가능해 강력한 도구."),
    ("Blue/Green 배포?", "두 환경을 두고 트래픽을 전환. 롤백 빠르지만 인프라 2배 필요."),
    ("Canary 배포?", "소수 사용자에게만 먼저 노출 후 점진 확대. 문제 빨리 감지 가능."),
    ("Circuit breaker?", "외부 호출 실패율 높으면 자동으로 차단해 cascading failure 방지. resilience 패턴."),
    ("Rate limit 어떻게?", "토큰 버킷 또는 leaky bucket. Redis INCR 과 TTL 로 분산 환경에서도 구현 가능."),
    ("Idempotency key?", "같은 요청 여러 번 와도 한 번만 처리되도록 클라이언트가 보내는 고유 키. 결제 등에 필수."),
    ("Eventual consistency?", "분산 시스템에서 즉시 일관성 대신 시간이 지나면 결국 일치하는 모델. 가용성과 성능 위해."),
    ("CAP 정리가 뭐야?", "일관성, 가용성, 분할 허용 중 둘만 선택 가능. 네트워크 단절 가정하면 보통 CP 또는 AP 선택."),
    ("Raft 가 뭐야?", "분산 시스템 합의 알고리즘. Paxos 보다 이해하기 쉽게 설계됨. etcd, Consul 이 사용."),
    ("Sharding 이 뭐야?", "데이터를 여러 DB 에 나눠 저장해 수평 확장. 키 선택과 리밸런싱이 중요한 결정."),
    ("Replication?", "데이터를 여러 노드에 복제. 가용성과 읽기 성능 향상. 쓰기 일관성은 주의."),
    ("ACID 가 뭐야?", "Atomicity, Consistency, Isolation, Durability. 트랜잭션이 보장해야 할 4가지 속성."),
    ("BASE 모델?", "Basically Available, Soft state, Eventually consistent. NoSQL 의 일관성 약화 모델."),
    ("Microservice 단점?", "운영 복잡도, 네트워크 지연, 분산 트랜잭션 어려움. 작은 팀은 모놀리스가 더 빠를 수 있어요."),
    ("Monorepo 와 Polyrepo?", "공유 코드 많고 일관된 도구는 Monorepo. 팀 독립성 강조면 Polyrepo. Turborepo, Nx 가 도와줌."),
    ("Build cache 어때?", "변경되지 않은 부분 재빌드 안 함. CI 시간 크게 단축. Turbo, Nx, Bazel 이 강력."),
    ("Lockfile 왜 중요해?", "의존성 정확한 버전을 고정해 재현 가능한 빌드 보장. 항상 커밋해야 합니다."),
    ("Semantic versioning?", "MAJOR.MINOR.PATCH. 호환성 깨지면 MAJOR, 기능 추가는 MINOR, 버그 수정은 PATCH."),
    ("Conventional commits?", "feat:, fix:, chore: 등 접두어로 커밋 분류. 자동 changelog 와 버전 관리에 유용."),
    ("Squash merge 어때?", "PR 의 여러 커밋을 하나로 합쳐 main 에 단일 커밋으로 들어감. 깔끔한 history 에 좋음."),
    ("Force push 위험해?", "공유 브랜치는 매우 위험. 본인 feature 브랜치에서만 사용. main 은 절대 금지."),
    ("Stash 와 WIP commit?", "임시 저장은 stash 가 가벼움. 다른 머신과 공유해야 하면 WIP commit 후 squash."),
    ("Cherry-pick 언제 써?", "특정 커밋만 다른 브랜치에 가져올 때. hotfix 를 main 과 release 양쪽에 적용 등."),
    ("Bisect 가 뭐야?", "git bisect. 어느 커밋에서 버그가 생겼는지 이진 탐색으로 찾음. 매우 유용한 디버깅 도구."),
    ("Gitflow 어때?", "기능, 릴리즈, 핫픽스 브랜치 분리한 워크플로. 명확하지만 무거움. trunk-based 가 더 단순."),
    ("Trunk-based 어때?", "main 에 자주 머지하고 feature flag 로 미완 기능 숨김. CI/CD 와 잘 맞아 모던 표준."),
]


def gen_short():
    q, a = random.choice(SHORT_QUESTIONS)
    return {"messages": [
        {"role": "user", "content": q},
        {"role": "assistant", "content": a},
    ]}


V7_6 = [gen_short() for _ in range(300)]


# ============================================================
# V7-7: 코드 예시 한국어 + 영어만 (한자 회피) (200)
# ============================================================

CODE_EXAMPLES = [
    {
        "q": "Python 에서 문자열 + 숫자 합치는 법?",
        "a": "TypeError 나니까 명시적 변환 필요합니다.\n\n```python\n# 잘못된 예\nresult = \"가격: \" + 100  # TypeError\n\n# 올바른 예\nresult = \"가격: \" + str(100)  # \"가격: 100\"\n# 또는 f-string\nresult = f\"가격: {100}\"\n```\n\nf-string 이 가장 가독성 좋습니다.",
    },
    {
        "q": "JS 에서 비동기 함수 만드는 법?",
        "a": "`async` 키워드로 정의하면 됩니다.\n\n```js\nasync function fetchUser(id) {\n  const response = await fetch(`/api/users/${id}`);\n  if (!response.ok) {\n    throw new Error(`사용자 조회 실패: ${response.status}`);\n  }\n  return response.json();\n}\n```\n\n호출 시 `await fetchUser(123)` 형태로 사용합니다.",
    },
    {
        "q": "TypeScript 인터페이스 vs 타입?",
        "a": "거의 비슷하지만 차이가 있습니다.\n\n```ts\n// 인터페이스 - 확장 가능 (선언 병합)\ninterface User {\n  id: number;\n  name: string;\n}\ninterface User { email: string; }  // OK - 자동 병합\n\n// 타입 - 유니온/인터섹션 표현 가능\ntype Status = 'active' | 'inactive';\ntype Admin = User & { role: 'admin' };\n```\n\n객체 모양은 인터페이스, 유니온은 타입을 권장합니다.",
    },
    {
        "q": "Python 리스트에서 중복 제거?",
        "a": "set 으로 변환했다 다시 list 로 만들면 됩니다.\n\n```python\nitems = [1, 2, 2, 3, 3, 3]\nunique = list(set(items))  # 순서 보장 안 됨\n\n# 순서 유지하려면 dict 사용\nunique_ordered = list(dict.fromkeys(items))  # [1, 2, 3]\n```\n\n순서가 중요하면 dict.fromkeys 가 정답입니다.",
    },
    {
        "q": "JS 배열 깊은 복사?",
        "a": "구조에 따라 방법이 다릅니다.\n\n```js\n// 1차원 배열 - spread 면 충분\nconst shallow = [...arr];\n\n// 중첩 객체/배열 - structuredClone (모던 브라우저)\nconst deep = structuredClone(arr);\n\n// 또는 JSON (함수, Date 손실 주의)\nconst deepJson = JSON.parse(JSON.stringify(arr));\n```\n\nstructuredClone 이 가장 안전합니다.",
    },
    {
        "q": "Python 딕셔너리 합치기?",
        "a": "Python 3.9+ 는 `|` 연산자가 가장 깔끔합니다.\n\n```python\na = {\"name\": \"홍길동\", \"age\": 30}\nb = {\"city\": \"서울\", \"age\": 31}  # age 덮어씀\n\n# 3.9+\nmerged = a | b  # {\"name\": \"홍길동\", \"age\": 31, \"city\": \"서울\"}\n\n# 3.5+ 호환\nmerged = {**a, **b}\n```",
    },
    {
        "q": "JS 에서 API 호출 에러 처리?",
        "a": "try/catch 와 response.ok 체크 둘 다 필요합니다.\n\n```js\nasync function loadData() {\n  try {\n    const response = await fetch(\"/api/data\");\n    if (!response.ok) {\n      throw new Error(`HTTP ${response.status}`);\n    }\n    return await response.json();\n  } catch (error) {\n    console.error(\"데이터 로드 실패:\", error);\n    return null;\n  }\n}\n```\n\nfetch 는 4xx, 5xx 에서 reject 안 하니 ok 체크 필수.",
    },
    {
        "q": "Python 에서 파일 한 줄씩 읽기?",
        "a": "with 구문으로 안전하게 처리합니다.\n\n```python\nwith open(\"data.txt\", \"r\", encoding=\"utf-8\") as f:\n    for line in f:\n        line = line.strip()\n        if line:  # 빈 줄 건너뛰기\n            print(line)\n```\n\n파일이 자동으로 닫혀 메모리 누수 걱정 없습니다.",
    },
    {
        "q": "JS 에서 객체 키 순회?",
        "a": "Object.entries 가 가장 편리합니다.\n\n```js\nconst user = { name: \"홍길동\", age: 30, city: \"서울\" };\n\nfor (const [key, value] of Object.entries(user)) {\n  console.log(`${key}: ${value}`);\n}\n\n// 키만 필요하면\nObject.keys(user).forEach(k => console.log(k));\n\n// 값만 필요하면\nObject.values(user).forEach(v => console.log(v));\n```",
    },
    {
        "q": "Python 클래스 생성자?",
        "a": "`__init__` 메서드를 정의합니다.\n\n```python\nclass User:\n    def __init__(self, name: str, age: int):\n        self.name = name\n        self.age = age\n\n    def greet(self) -> str:\n        return f\"안녕하세요, {self.name}입니다.\"\n\nuser = User(\"홍길동\", 30)\nprint(user.greet())\n```\n\ndataclass 로 더 간결하게 쓸 수도 있습니다.",
    },
    {
        "q": "Python dataclass 사용법?",
        "a": "@dataclass 데코레이터로 보일러플레이트 줄입니다.\n\n```python\nfrom dataclasses import dataclass\n\n@dataclass\nclass Product:\n    name: str\n    price: int\n    stock: int = 0  # 기본값\n\np = Product(\"노트북\", 1500000, 10)\nprint(p)  # Product(name='노트북', price=1500000, stock=10)\n```\n\n__init__, __repr__, __eq__ 가 자동 생성됩니다.",
    },
    {
        "q": "JS 디바운스 만드는 법?",
        "a": "타이머로 마지막 호출만 실행되게 합니다.\n\n```js\nfunction debounce(fn, delay = 300) {\n  let timer;\n  return (...args) => {\n    clearTimeout(timer);\n    timer = setTimeout(() => fn(...args), delay);\n  };\n}\n\n// 사용\nconst onSearch = debounce((query) => {\n  console.log(\"검색:\", query);\n}, 500);\n```\n\n검색창 입력 처리에 자주 씁니다.",
    },
    {
        "q": "JS throttle 만드는 법?",
        "a": "일정 시간마다 한 번만 실행되게 합니다.\n\n```js\nfunction throttle(fn, limit = 300) {\n  let inThrottle = false;\n  return (...args) => {\n    if (!inThrottle) {\n      fn(...args);\n      inThrottle = true;\n      setTimeout(() => (inThrottle = false), limit);\n    }\n  };\n}\n\n// 사용\nwindow.addEventListener(\"scroll\", throttle(onScroll, 200));\n```\n\n스크롤이나 resize 이벤트에 적합합니다.",
    },
    {
        "q": "Python list comprehension 예시?",
        "a": "조건과 변환을 한 줄로 표현합니다.\n\n```python\nnumbers = [1, 2, 3, 4, 5]\n\n# 제곱\nsquares = [n * n for n in numbers]  # [1, 4, 9, 16, 25]\n\n# 짝수만\nevens = [n for n in numbers if n % 2 == 0]  # [2, 4]\n\n# 중첩\nmatrix = [[i * j for j in range(3)] for i in range(3)]\n```\n\n3중 이상 중첩되면 일반 for 가 더 읽기 좋습니다.",
    },
    {
        "q": "React useState 기본?",
        "a": "함수 컴포넌트의 상태 관리 hook 입니다.\n\n```jsx\nimport { useState } from \"react\";\n\nfunction Counter() {\n  const [count, setCount] = useState(0);\n\n  return (\n    <div>\n      <p>현재: {count}</p>\n      <button onClick={() => setCount(count + 1)}>증가</button>\n    </div>\n  );\n}\n```\n\n이전 값 기반 업데이트는 `setCount(c => c + 1)` 형태로.",
    },
    {
        "q": "React useEffect 기본?",
        "a": "사이드 이펙트 처리용 hook 입니다.\n\n```jsx\nimport { useEffect, useState } from \"react\";\n\nfunction UserProfile({ userId }) {\n  const [user, setUser] = useState(null);\n\n  useEffect(() => {\n    let cancelled = false;\n    fetch(`/api/users/${userId}`)\n      .then(r => r.json())\n      .then(data => {\n        if (!cancelled) setUser(data);\n      });\n    return () => { cancelled = true; };\n  }, [userId]);\n\n  return user ? <div>{user.name}</div> : <div>로딩 중...</div>;\n}\n```\n\nclean-up 함수로 메모리 누수 방지하는 게 핵심입니다.",
    },
    {
        "q": "Python 예외 처리 패턴?",
        "a": "구체적인 예외부터 잡고 마지막에 일반 처리합니다.\n\n```python\ntry:\n    with open(\"config.json\") as f:\n        config = json.load(f)\nexcept FileNotFoundError:\n    print(\"설정 파일이 없습니다\")\n    config = {}\nexcept json.JSONDecodeError as e:\n    print(f\"JSON 파싱 실패: {e}\")\n    config = {}\nexcept Exception as e:\n    print(f\"예상치 못한 오류: {e}\")\n    raise\n```\n\n맨 아래 일반 except 에서는 보통 raise 로 다시 던집니다.",
    },
    {
        "q": "JS 옵셔널 체이닝?",
        "a": "`?.` 로 중간에 null/undefined 면 안전하게 undefined 반환합니다.\n\n```js\nconst user = { profile: null };\n\n// 옛날 방식\nconst city = user && user.profile && user.profile.address && user.profile.address.city;\n\n// 옵셔널 체이닝\nconst city2 = user?.profile?.address?.city;  // undefined\n\n// 기본값과 함께\nconst cityOrDefault = user?.profile?.address?.city ?? \"미상\";\n```",
    },
    {
        "q": "Python 함수 타입 힌트?",
        "a": "인자와 반환 타입을 명시할 수 있습니다.\n\n```python\nfrom typing import Optional\n\ndef calculate_total(price: float, quantity: int, discount: Optional[float] = None) -> float:\n    total = price * quantity\n    if discount is not None:\n        total *= (1 - discount)\n    return total\n\nresult = calculate_total(1000.0, 3, discount=0.1)\n```\n\nPython 3.10+ 는 `Optional[float]` 대신 `float | None` 도 가능합니다.",
    },
    {
        "q": "JS Map 과 Object?",
        "a": "용도에 따라 다릅니다.\n\n```js\n// Object - 단순 레코드, 키는 string/Symbol\nconst user = { name: \"홍길동\", age: 30 };\n\n// Map - 키 타입 자유, 순서 보장, 크기 빠름\nconst cache = new Map();\ncache.set(\"key1\", { data: \"value1\" });\ncache.set(42, \"숫자 키도 가능\");\nconsole.log(cache.size);  // 2\nconsole.log(cache.get(\"key1\"));\n```\n\n빈번한 추가/삭제와 다양한 키 타입은 Map 권장.",
    },
    {
        "q": "Python 제너레이터?",
        "a": "yield 로 메모리 효율적인 이터레이터를 만듭니다.\n\n```python\ndef read_large_file(path: str):\n    with open(path) as f:\n        for line in f:\n            yield line.strip()\n\n# 한 줄씩 처리, 전체를 메모리에 안 올림\nfor line in read_large_file(\"big.log\"):\n    if \"ERROR\" in line:\n        print(line)\n```\n\n대용량 파일 처리에 필수입니다.",
    },
    {
        "q": "JS Promise.all 과 allSettled?",
        "a": "실패 처리 방식이 다릅니다.\n\n```js\n// all - 하나라도 실패하면 즉시 reject\ntry {\n  const [users, posts] = await Promise.all([\n    fetch(\"/api/users\").then(r => r.json()),\n    fetch(\"/api/posts\").then(r => r.json()),\n  ]);\n} catch (e) {\n  console.error(\"하나 실패\", e);\n}\n\n// allSettled - 모두 끝까지 기다리고 결과 배열 반환\nconst results = await Promise.allSettled([fetchA(), fetchB()]);\nresults.forEach(r => {\n  if (r.status === \"fulfilled\") console.log(r.value);\n  else console.error(r.reason);\n});\n```",
    },
    {
        "q": "Python 데코레이터 기본?",
        "a": "함수를 감싸는 함수입니다.\n\n```python\nimport time\nfrom functools import wraps\n\ndef timed(func):\n    @wraps(func)\n    def wrapper(*args, **kwargs):\n        start = time.time()\n        result = func(*args, **kwargs)\n        elapsed = time.time() - start\n        print(f\"{func.__name__} 실행 시간: {elapsed:.3f}초\")\n        return result\n    return wrapper\n\n@timed\ndef slow_task():\n    time.sleep(1)\n\nslow_task()\n```\n\n@wraps 로 원본 함수 메타데이터 보존하는 게 좋습니다.",
    },
    {
        "q": "React props vs state?",
        "a": "제어 주체가 다릅니다.\n\n```jsx\n// Props - 부모가 내려주는 값 (읽기 전용)\nfunction Greeting({ name }) {\n  return <h1>안녕하세요, {name}님</h1>;\n}\n\n// State - 컴포넌트 내부 데이터 (변경 가능)\nfunction Counter() {\n  const [count, setCount] = useState(0);\n  return <button onClick={() => setCount(count + 1)}>{count}</button>;\n}\n\n// 부모가 자식의 state 변경 - 콜백 전달\nfunction Parent() {\n  const [value, setValue] = useState(\"\");\n  return <Input onChange={setValue} value={value} />;\n}\n```",
    },
    {
        "q": "Python 환경 변수 읽기?",
        "a": "os.environ 또는 os.getenv 를 씁니다.\n\n```python\nimport os\n\n# 없으면 KeyError\napi_key = os.environ[\"API_KEY\"]\n\n# 없으면 None (기본값 가능)\ndb_url = os.getenv(\"DATABASE_URL\", \"sqlite:///dev.db\")\n\n# .env 파일 사용 시\nfrom dotenv import load_dotenv\nload_dotenv()\n```\n\npython-dotenv 패키지로 .env 파일을 자동 로드할 수 있습니다.",
    },
    {
        "q": "JS localStorage 사용법?",
        "a": "문자열만 저장 가능하니 JSON 으로 직렬화합니다.\n\n```js\n// 저장\nconst user = { name: \"홍길동\", theme: \"dark\" };\nlocalStorage.setItem(\"user\", JSON.stringify(user));\n\n// 읽기 (안전하게)\nfunction loadUser() {\n  const raw = localStorage.getItem(\"user\");\n  if (!raw) return null;\n  try {\n    return JSON.parse(raw);\n  } catch {\n    return null;\n  }\n}\n\n// 삭제\nlocalStorage.removeItem(\"user\");\n```",
    },
    {
        "q": "Python 정렬 커스텀 키?",
        "a": "key 인자로 정렬 기준을 지정합니다.\n\n```python\nproducts = [\n    {\"name\": \"노트북\", \"price\": 1500000},\n    {\"name\": \"키보드\", \"price\": 80000},\n    {\"name\": \"마우스\", \"price\": 30000},\n]\n\n# 가격 오름차순\nby_price = sorted(products, key=lambda p: p[\"price\"])\n\n# 가격 내림차순\nby_price_desc = sorted(products, key=lambda p: p[\"price\"], reverse=True)\n\n# 여러 기준 - 가격 오름차순, 이름 오름차순\nmulti = sorted(products, key=lambda p: (p[\"price\"], p[\"name\"]))\n```",
    },
    {
        "q": "JS 배열 필터링 & 변환?",
        "a": "filter 와 map 을 체인합니다.\n\n```js\nconst products = [\n  { name: \"노트북\", price: 1500000, inStock: true },\n  { name: \"키보드\", price: 80000, inStock: false },\n  { name: \"마우스\", price: 30000, inStock: true },\n];\n\n// 재고 있는 상품의 이름만\nconst available = products\n  .filter(p => p.inStock)\n  .map(p => p.name);\n// [\"노트북\", \"마우스\"]\n```\n\n큰 배열은 한 번의 reduce 가 더 효율적일 수 있습니다.",
    },
    {
        "q": "Python f-string 포맷팅?",
        "a": "다양한 포맷 옵션을 지원합니다.\n\n```python\nprice = 1234567.891\nname = \"홍길동\"\n\n# 천 단위 콤마\nprint(f\"{price:,.0f}\")  # 1,234,568\n\n# 소수점 둘째 자리\nprint(f\"{price:.2f}\")  # 1234567.89\n\n# 너비 + 정렬\nprint(f\"{name:<10}|\")  # 홍길동       |\nprint(f\"{name:>10}|\")  #        홍길동|\nprint(f\"{name:^10}|\")  #    홍길동    |\n\n# 16진수\nprint(f\"{255:#x}\")  # 0xff\n```",
    },
    {
        "q": "Python 컨텍스트 매니저 직접 만들기?",
        "a": "`__enter__` 와 `__exit__` 를 정의합니다.\n\n```python\nclass Timer:\n    def __init__(self, label: str):\n        self.label = label\n\n    def __enter__(self):\n        import time\n        self.start = time.time()\n        return self\n\n    def __exit__(self, exc_type, exc_val, exc_tb):\n        import time\n        elapsed = time.time() - self.start\n        print(f\"{self.label}: {elapsed:.3f}초\")\n        return False  # 예외 전파\n\nwith Timer(\"DB 쿼리\"):\n    # 작업 수행\n    pass\n```\n\n@contextmanager 데코레이터로 더 간결하게도 만들 수 있습니다.",
    },
    {
        "q": "JS 클래스 상속?",
        "a": "extends 와 super 를 사용합니다.\n\n```js\nclass Animal {\n  constructor(name) {\n    this.name = name;\n  }\n  speak() {\n    return `${this.name}이 소리를 냅니다`;\n  }\n}\n\nclass Dog extends Animal {\n  constructor(name, breed) {\n    super(name);\n    this.breed = breed;\n  }\n  speak() {\n    return `${this.name}이 멍멍 짖습니다`;\n  }\n}\n\nconst d = new Dog(\"바둑이\", \"진돗개\");\nconsole.log(d.speak());\n```",
    },
    {
        "q": "Python pathlib 사용법?",
        "a": "os.path 보다 객체 지향적이고 편리합니다.\n\n```python\nfrom pathlib import Path\n\n# 경로 결합\nbase = Path(\"/Users/me/projects\")\nconfig = base / \"app\" / \"config.json\"\n\n# 존재 확인\nif config.exists():\n    text = config.read_text(encoding=\"utf-8\")\n\n# 디렉토리 생성\nlogs = base / \"logs\"\nlogs.mkdir(parents=True, exist_ok=True)\n\n# 파일 검색\nfor py_file in base.rglob(\"*.py\"):\n    print(py_file)\n```",
    },
    {
        "q": "FastAPI 기본 라우트?",
        "a": "데코레이터로 경로와 메서드를 지정합니다.\n\n```python\nfrom fastapi import FastAPI\nfrom pydantic import BaseModel\n\napp = FastAPI()\n\nclass UserCreate(BaseModel):\n    name: str\n    email: str\n\n@app.get(\"/users/{user_id}\")\nasync def get_user(user_id: int):\n    return {\"id\": user_id, \"name\": \"홍길동\"}\n\n@app.post(\"/users\")\nasync def create_user(user: UserCreate):\n    return {\"created\": user.name}\n```\n\nPydantic 모델로 자동 검증과 OpenAPI 문서가 만들어집니다.",
    },
    {
        "q": "Python 비동기 HTTP 호출?",
        "a": "httpx 의 AsyncClient 를 추천합니다.\n\n```python\nimport asyncio\nimport httpx\n\nasync def fetch_user(user_id: int):\n    async with httpx.AsyncClient() as client:\n        response = await client.get(f\"https://api.example.com/users/{user_id}\")\n        response.raise_for_status()\n        return response.json()\n\nasync def main():\n    users = await asyncio.gather(\n        fetch_user(1), fetch_user(2), fetch_user(3)\n    )\n    print(users)\n\nasyncio.run(main())\n```",
    },
    {
        "q": "JS 깊은 비교 어떻게 해?",
        "a": "JSON 문자열화 또는 라이브러리 사용.\n\n```js\n// 간단 비교 (함수, undefined, 순서 주의)\nconst equal = JSON.stringify(a) === JSON.stringify(b);\n\n// 안전한 방법 - lodash 또는 직접 구현\nfunction deepEqual(a, b) {\n  if (a === b) return true;\n  if (typeof a !== \"object\" || typeof b !== \"object\") return false;\n  if (a === null || b === null) return false;\n  const keysA = Object.keys(a);\n  const keysB = Object.keys(b);\n  if (keysA.length !== keysB.length) return false;\n  return keysA.every(k => deepEqual(a[k], b[k]));\n}\n```",
    },
    {
        "q": "Python 정규식 기본?",
        "a": "re 모듈을 사용합니다.\n\n```python\nimport re\n\ntext = \"이메일: hong@example.com, 연락처: 010-1234-5678\"\n\n# 검색\nemail_match = re.search(r\"[\\w.]+@[\\w.]+\", text)\nif email_match:\n    print(email_match.group())  # hong@example.com\n\n# 모두 찾기\nphones = re.findall(r\"\\d{2,3}-\\d{3,4}-\\d{4}\", text)\n# ['010-1234-5678']\n\n# 치환\nmasked = re.sub(r\"\\d{4}$\", \"****\", \"010-1234-5678\")\n# '010-1234-****'\n```",
    },
    {
        "q": "JS Set 사용법?",
        "a": "중복 없는 컬렉션입니다.\n\n```js\nconst tags = new Set([\"react\", \"vue\", \"react\"]);\nconsole.log(tags.size);  // 2\n\ntags.add(\"svelte\");\ntags.has(\"react\");  // true\ntags.delete(\"vue\");\n\n// 배열로 변환\nconst arr = [...tags];\n\n// 배열 중복 제거\nconst unique = [...new Set([1, 2, 2, 3])];  // [1, 2, 3]\n```",
    },
    {
        "q": "Python defaultdict?",
        "a": "키가 없을 때 기본값을 자동 생성합니다.\n\n```python\nfrom collections import defaultdict\n\n# 일반 dict 였다면 KeyError 또는 if 체크 필요\ncounts = defaultdict(int)\nwords = [\"사과\", \"바나나\", \"사과\", \"체리\", \"바나나\", \"사과\"]\nfor w in words:\n    counts[w] += 1\nprint(dict(counts))  # {'사과': 3, '바나나': 2, '체리': 1}\n\n# 리스트 그룹화\ngroups = defaultdict(list)\nfor item in [(\"a\", 1), (\"b\", 2), (\"a\", 3)]:\n    groups[item[0]].append(item[1])\n```",
    },
    {
        "q": "JS 스프레드 vs Object.assign?",
        "a": "스프레드가 더 간결하고 권장됩니다.\n\n```js\nconst defaults = { theme: \"light\", lang: \"ko\" };\nconst userPrefs = { theme: \"dark\" };\n\n// 스프레드 (모던)\nconst merged = { ...defaults, ...userPrefs };\n// { theme: \"dark\", lang: \"ko\" }\n\n// Object.assign (구식)\nconst merged2 = Object.assign({}, defaults, userPrefs);\n```\n\n첫 인자 빈 객체 안 넣으면 defaults 가 변경되니 주의.",
    },
    {
        "q": "Python with 문 여러 개?",
        "a": "쉼표로 구분하거나 괄호로 묶을 수 있습니다.\n\n```python\n# Python 3.10+ 권장\nwith (\n    open(\"input.txt\") as src,\n    open(\"output.txt\", \"w\") as dst,\n):\n    for line in src:\n        dst.write(line.upper())\n\n# 호환성 좋은 형태\nwith open(\"input.txt\") as src, open(\"output.txt\", \"w\") as dst:\n    for line in src:\n        dst.write(line.upper())\n```",
    },
    {
        "q": "React 조건부 렌더링?",
        "a": "&& 또는 삼항 연산자를 사용합니다.\n\n```jsx\nfunction UserBadge({ user }) {\n  return (\n    <div>\n      {user ? (\n        <span>안녕하세요, {user.name}님</span>\n      ) : (\n        <a href=\"/login\">로그인</a>\n      )}\n      {user?.isAdmin && <span> (관리자)</span>}\n    </div>\n  );\n}\n```\n\n0 같은 falsy 값에 주의 - `count && <X />` 는 count 0 일 때 0 이 렌더됩니다.",
    },
    {
        "q": "Python any 와 all?",
        "a": "조건 검사를 한 번에 합니다.\n\n```python\nnumbers = [1, 2, 3, 4, 5]\n\n# 모두 양수인가?\nall_positive = all(n > 0 for n in numbers)  # True\n\n# 짝수가 하나라도?\nhas_even = any(n % 2 == 0 for n in numbers)  # True\n\n# 빈 리스트는 all=True, any=False\nprint(all([]))  # True\nprint(any([]))  # False\n```\n\n제너레이터 표현식을 쓰면 단락 평가로 효율적입니다.",
    },
    {
        "q": "JS try/catch 와 async?",
        "a": "async 함수 내부에서 await 한 호출의 reject 가 catch 됩니다.\n\n```js\nasync function loadUser(id) {\n  try {\n    const res = await fetch(`/api/users/${id}`);\n    if (!res.ok) throw new Error(`HTTP ${res.status}`);\n    return await res.json();\n  } catch (error) {\n    console.error(\"사용자 로드 실패:\", error);\n    throw error;  // 호출자에게도 전파\n  }\n}\n```\n\n호출자도 try/catch 또는 .catch() 로 받아야 합니다.",
    },
    {
        "q": "Python 문자열 분할?",
        "a": "split 으로 구분자 기준 나눕니다.\n\n```python\ncsv = \"홍길동,30,서울\"\nname, age, city = csv.split(\",\")\nprint(age)  # \"30\"\n\n# 공백으로 나누기 (연속 공백 처리)\nwords = \"hello   world  python\".split()\n# ['hello', 'world', 'python']\n\n# 한 번만 분할\nkey_value = \"key=hello=world\".split(\"=\", 1)\n# ['key', 'hello=world']\n\n# 정규식으로 여러 구분자\nimport re\nparts = re.split(r\"[,;]\\s*\", \"a, b; c,d\")\n# ['a', 'b', 'c', 'd']\n```",
    },
    {
        "q": "Express 기본 서버?",
        "a": "최소 구조로 시작합니다.\n\n```js\nimport express from \"express\";\n\nconst app = express();\napp.use(express.json());\n\napp.get(\"/health\", (req, res) => {\n  res.json({ status: \"ok\" });\n});\n\napp.post(\"/users\", (req, res) => {\n  const { name, email } = req.body;\n  res.status(201).json({ id: Date.now(), name, email });\n});\n\nconst PORT = process.env.PORT || 3000;\napp.listen(PORT, () => {\n  console.log(`서버 실행: http://localhost:${PORT}`);\n});\n```",
    },
    {
        "q": "Python sqlite 연결?",
        "a": "표준 라이브러리로 가능합니다.\n\n```python\nimport sqlite3\n\nconn = sqlite3.connect(\"app.db\")\nconn.row_factory = sqlite3.Row  # dict 처럼 접근\ncursor = conn.cursor()\n\ncursor.execute(\"\"\"\n    CREATE TABLE IF NOT EXISTS users (\n        id INTEGER PRIMARY KEY,\n        name TEXT NOT NULL,\n        email TEXT UNIQUE\n    )\n\"\"\")\n\n# 안전한 파라미터 바인딩\ncursor.execute(\n    \"INSERT INTO users (name, email) VALUES (?, ?)\",\n    (\"홍길동\", \"hong@example.com\"),\n)\nconn.commit()\nconn.close()\n```\n\n사용자 입력은 절대 문자열 포맷팅으로 쿼리에 넣지 마세요.",
    },
    {
        "q": "JS 모듈 import 종류?",
        "a": "default 와 named 가 있습니다.\n\n```js\n// 모듈 정의 (utils.js)\nexport const PI = 3.14159;\nexport function add(a, b) { return a + b; }\nexport default function main() { return \"main\"; }\n\n// 가져오기\nimport main, { PI, add } from \"./utils.js\";\nimport { add as sum } from \"./utils.js\";  // 별칭\nimport * as utils from \"./utils.js\";       // 전체\n```",
    },
    {
        "q": "Python enumerate 와 zip?",
        "a": "인덱스/짝지어 순회할 때 씁니다.\n\n```python\nnames = [\"홍길동\", \"이순신\", \"세종대왕\"]\n\n# enumerate - 인덱스와 함께\nfor i, name in enumerate(names, start=1):\n    print(f\"{i}. {name}\")\n\nages = [30, 45, 50]\n\n# zip - 여러 시퀀스 동시 순회\nfor name, age in zip(names, ages):\n    print(f\"{name}: {age}\")\n\n# zip 으로 dict 만들기\nuser_age = dict(zip(names, ages))\n```",
    },
    {
        "q": "JS 배열 reduce 예시?",
        "a": "누적 계산에 강력합니다.\n\n```js\nconst orders = [\n  { product: \"노트북\", qty: 1, price: 1500000 },\n  { product: \"키보드\", qty: 2, price: 80000 },\n  { product: \"마우스\", qty: 3, price: 30000 },\n];\n\n// 총합\nconst total = orders.reduce((sum, o) => sum + o.qty * o.price, 0);\n\n// 그룹화\nconst byProduct = orders.reduce((acc, o) => {\n  acc[o.product] = o.qty;\n  return acc;\n}, {});\n\n// 평균\nconst avg = orders.reduce((sum, o, i, arr) => {\n  sum += o.price;\n  return i === arr.length - 1 ? sum / arr.length : sum;\n}, 0);\n```",
    },
    {
        "q": "Python typing Generic?",
        "a": "TypeVar 로 타입 매개변수를 만듭니다.\n\n```python\nfrom typing import TypeVar, Generic\n\nT = TypeVar(\"T\")\n\nclass Stack(Generic[T]):\n    def __init__(self):\n        self._items: list[T] = []\n\n    def push(self, item: T) -> None:\n        self._items.append(item)\n\n    def pop(self) -> T:\n        return self._items.pop()\n\n# 사용\nint_stack: Stack[int] = Stack()\nint_stack.push(1)\nint_stack.push(2)\n```\n\nPython 3.12+ 는 더 짧은 `class Stack[T]:` 문법도 가능합니다.",
    },
]


def gen_code_ex():
    p = random.choice(CODE_EXAMPLES)
    return {"messages": [
        {"role": "user", "content": p["q"]},
        {"role": "assistant", "content": p["a"]},
    ]}


V7_7 = [gen_code_ex() for _ in range(200)]


# ============================================================
# 출력 + 자체 검증
# ============================================================

def has_chinese(text: str) -> bool:
    return any('一' <= c <= '鿿' for c in text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/natural_v7.jsonl")
    args = parser.parse_args()

    all_data = V7_5 + V7_6 + V7_7
    assert len(all_data) == 1000, f"기대 1000, 실제 {len(all_data)}"

    # 한자 검증 + 자동 제거
    bad = [item for item in all_data if has_chinese(json.dumps(item, ensure_ascii=False))]
    if bad:
        print(f"[WARN] 한자 포함 샘플 {len(bad)}개 - 자동 제거")
        all_data = [item for item in all_data if not has_chinese(json.dumps(item, ensure_ascii=False))]

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # 통계
    v75_count = sum(1 for item in all_data if item in V7_5)
    v76_count = sum(1 for item in all_data if item in V7_6)
    v77_count = sum(1 for item in all_data if item in V7_7)

    avg_v75_len = sum(len(item["messages"][1]["content"]) for item in V7_5) / len(V7_5) if V7_5 else 0
    avg_v76_len = sum(len(item["messages"][1]["content"]) for item in V7_6) / len(V7_6) if V7_6 else 0
    avg_v77_len = sum(len(item["messages"][1]["content"]) for item in V7_7) / len(V7_7) if V7_7 else 0

    print(f"[OK] {len(all_data)} 샘플 -> {args.output}")
    print(f"  V7-5 모호 질문 친절: {len(V7_5)} (평균 응답 길이 {avg_v75_len:.0f}자)")
    print(f"  V7-6 짧은 답 (표 자제): {len(V7_6)} (평균 응답 길이 {avg_v76_len:.0f}자)")
    print(f"  V7-7 코드 예시 (한자 X): {len(V7_7)} (평균 응답 길이 {avg_v77_len:.0f}자)")
    print(f"  한자 검증: {len(bad)}개 발견 (제거됨)")
