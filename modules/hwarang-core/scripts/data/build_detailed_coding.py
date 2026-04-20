"""화랑 AI 상세 코딩 학습 데이터

실무에서 자주 쓰는 패턴, 디버깅, 최적화, 보안, 테스트 등
깊이 있는 코딩 데이터.

사용법:
    python scripts/data/build_detailed_coding.py \
        --output data/sft/detailed_coding.jsonl
"""

import json, os, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 디버깅 ═══
    m("TypeError: Cannot read properties of undefined 에러 해결해줘",
'''이 에러는 `undefined`인 객체의 속성에 접근할 때 발생합니다.

```javascript
// ❌ 에러 발생
const user = undefined;
console.log(user.name); // TypeError!

// ✅ 해결 방법들

// 1. 옵셔널 체이닝 (?.)
console.log(user?.name); // undefined (에러 안 남)

// 2. 기본값 (Nullish coalescing)
console.log(user?.name ?? "이름 없음");

// 3. 조건 체크
if (user && user.name) {
    console.log(user.name);
}

// 4. API 응답에서 자주 발생
const response = await fetch("/api/user");
const data = await response.json();
// data.user가 null일 수 있음
const userName = data?.user?.name ?? "게스트";
```

**흔한 원인:**
- API 응답이 예상과 다른 구조
- 배열이 비어있는데 `arr[0].name` 접근
- 비동기 로딩 중 데이터가 아직 없을 때
- `useState`의 초기값이 `null`'''),

    m("CORS 에러 해결 방법",
'''CORS 에러는 브라우저가 다른 도메인의 API를 차단할 때 발생합니다.

```
에러: Access to fetch at 'http://api.example.com' from origin
'http://localhost:3000' has been blocked by CORS policy
```

**해결 방법:**

```javascript
// ── 1. 서버에서 CORS 허용 (백엔드) ──

// Express
const cors = require("cors");
app.use(cors({
    origin: ["http://localhost:3000", "https://내도메인.com"],
    methods: ["GET", "POST", "PUT", "DELETE"],
    credentials: true,  // 쿠키 포함 시
}));

// FastAPI
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

// Next.js API Route (자동으로 같은 도메인)
// → CORS 문제 없음! 프록시로 해결

// ── 2. Next.js 프록시 (프론트) ──

// next.config.ts
const nextConfig = {
    async rewrites() {
        return [
            {
                source: "/api/external/:path*",
                destination: "http://api.example.com/:path*",
            },
        ];
    },
};

// 프론트에서
fetch("/api/external/users"); // 같은 도메인 → CORS 없음
```

**핵심: 백엔드에서 `Access-Control-Allow-Origin` 헤더를 추가하거나, 같은 도메인 프록시를 사용하세요.**'''),

    # ═══ 성능 최적화 ═══
    m("React 성능 최적화 방법 알려줘",
'''React 성능 최적화 핵심 기법들입니다.

```tsx
// ── 1. React.memo (불필요한 리렌더링 방지) ──

// ❌ 부모가 렌더링되면 매번 같이 렌더링
function 자식({ 이름 }: { 이름: string }) {
    console.log("렌더링됨!");
    return <div>{이름}</div>;
}

// ✅ props가 변경될 때만 렌더링
const 자식 = React.memo(function 자식({ 이름 }: { 이름: string }) {
    console.log("렌더링됨!");
    return <div>{이름}</div>;
});

// ── 2. useMemo (비싼 계산 캐싱) ──

function 컴포넌트({ 데이터 }: { 데이터: number[] }) {
    // ❌ 매 렌더링마다 재계산
    const 합계 = 데이터.reduce((a, b) => a + b, 0);

    // ✅ 데이터가 변할 때만 재계산
    const 합계 = useMemo(
        () => 데이터.reduce((a, b) => a + b, 0),
        [데이터]
    );

    return <div>합계: {합계}</div>;
}

// ── 3. useCallback (함수 참조 고정) ──

function 부모() {
    const [카운트, 카운트설정] = useState(0);

    // ❌ 매 렌더링마다 새 함수 생성
    const 클릭 = () => console.log("클릭");

    // ✅ 의존성 변할 때만 새 함수
    const 클릭 = useCallback(() => {
        console.log("클릭", 카운트);
    }, [카운트]);

    return <자식 onClick={클릭} />;
}

// ── 4. 가상화 (대량 리스트) ──

import { useVirtualizer } from "@tanstack/react-virtual";

function 대량리스트({ 아이템들 }: { 아이템들: string[] }) {
    const parentRef = useRef<HTMLDivElement>(null);

    const virtualizer = useVirtualizer({
        count: 아이템들.length,  // 10만개라도 OK
        getScrollElement: () => parentRef.current,
        estimateSize: () => 50,  // 아이템 높이
    });

    return (
        <div ref={parentRef} style={{ height: "400px", overflow: "auto" }}>
            <div style={{ height: virtualizer.getTotalSize() }}>
                {virtualizer.getVirtualItems().map(item => (
                    <div key={item.key} style={{
                        position: "absolute",
                        top: item.start,
                        height: item.size,
                    }}>
                        {아이템들[item.index]}
                    </div>
                ))}
            </div>
        </div>
    );
}
// 10만개 아이템도 DOM에는 ~10개만 렌더링!

// ── 5. 코드 분할 (lazy loading) ──

const 무거운컴포넌트 = lazy(() => import("./HeavyComponent"));

function 앱() {
    return (
        <Suspense fallback={<div>로딩 중...</div>}>
            <무거운컴포넌트 />
        </Suspense>
    );
}

// ── 6. 이미지 최적화 (Next.js) ──

import Image from "next/image";

// ❌
<img src="/big-photo.jpg" />

// ✅ 자동 최적화 + lazy loading
<Image src="/big-photo.jpg" width={800} height={600} alt="사진" />
```'''),

    m("SQL 쿼리 최적화 방법",
'''SQL 쿼리 성능 최적화 핵심입니다.

```sql
-- ═══ 1. 인덱스 ═══

-- ❌ 느린 쿼리 (풀 테이블 스캔)
SELECT * FROM orders WHERE user_id = 123;

-- ✅ 인덱스 추가
CREATE INDEX idx_orders_user ON orders(user_id);
-- → 수백만 건도 즉시 검색

-- 복합 인덱스 (자주 같이 쓰는 컬럼)
CREATE INDEX idx_orders_user_date ON orders(user_id, created_at DESC);

-- ═══ 2. SELECT * 지양 ═══

-- ❌ 모든 컬럼 (불필요한 데이터 전송)
SELECT * FROM users;

-- ✅ 필요한 컬럼만
SELECT id, name, email FROM users;

-- ═══ 3. N+1 문제 해결 ═══

-- ❌ N+1 쿼리 (게시글 100개 → 쿼리 101번)
-- 1번: SELECT * FROM posts LIMIT 100;
-- 100번: SELECT * FROM users WHERE id = ?; (각 게시글마다)

-- ✅ JOIN으로 한 번에
SELECT p.*, u.name as author_name
FROM posts p
JOIN users u ON p.user_id = u.id
LIMIT 100;

-- ═══ 4. 페이지네이션 ═══

-- ❌ OFFSET 방식 (뒤로 갈수록 느림)
SELECT * FROM posts ORDER BY id DESC OFFSET 10000 LIMIT 20;

-- ✅ 커서 기반 (일정 속도)
SELECT * FROM posts
WHERE id < 마지막_본_id
ORDER BY id DESC
LIMIT 20;

-- ═══ 5. 서브쿼리 vs JOIN ═══

-- ❌ 느린 서브쿼리
SELECT * FROM users
WHERE id IN (SELECT DISTINCT user_id FROM orders WHERE amount > 10000);

-- ✅ EXISTS (대량 데이터에서 빠름)
SELECT * FROM users u
WHERE EXISTS (
    SELECT 1 FROM orders o
    WHERE o.user_id = u.id AND o.amount > 10000
);

-- ═══ 6. EXPLAIN으로 분석 ═══

EXPLAIN ANALYZE
SELECT * FROM orders WHERE user_id = 123 AND status = 'paid';
-- → Seq Scan (느림) vs Index Scan (빠름) 확인
```

**가장 중요한 것: 인덱스 + SELECT 최소화 + N+1 방지**'''),

    # ═══ 보안 ═══
    m("웹 보안 취약점과 방어 방법 알려줘",
'''웹 보안 핵심 취약점과 방어입니다.

```javascript
// ═══ 1. XSS (Cross-Site Scripting) ═══

// ❌ 위험: 사용자 입력을 그대로 출력
document.innerHTML = userInput;
// 공격: <script>document.cookie를 해커에게 전송</script>

// ✅ 방어: 이스케이프 처리
// React는 기본 방어됨 (자동 이스케이프)
return <div>{userInput}</div>; // 안전

// dangerouslySetInnerHTML 사용 시 주의!
// ❌
return <div dangerouslySetInnerHTML={{ __html: userInput }} />;
// ✅ DOMPurify로 정화
import DOMPurify from "dompurify";
return <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(userInput) }} />;

// ═══ 2. SQL Injection ═══

// ❌ 위험: 문자열 직접 삽입
query = f"SELECT * FROM users WHERE email = '{email}'"
// 공격: email = "' OR '1'='1" → 모든 유저 조회

// ✅ 방어: 파라미터 바인딩
// Prisma (자동 방어)
await prisma.user.findUnique({ where: { email } });

// Raw SQL 시
await prisma.$queryRaw`SELECT * FROM users WHERE email = ${email}`;

// ═══ 3. CSRF (Cross-Site Request Forgery) ═══

// ❌ 위험: 다른 사이트에서 폼 전송
// 해커 사이트: <form action="https://bank.com/transfer" method="POST">

// ✅ 방어
// - CSRF 토큰 사용
// - SameSite 쿠키
// - Origin 헤더 확인

// ═══ 4. 인증 보안 ═══

// ❌ 비밀번호 평문 저장
await db.user.create({ data: { password: "1234" } });

// ✅ bcrypt 해싱
import bcrypt from "bcrypt";
const 해시 = await bcrypt.hash("1234", 12); // 솔트 라운드 12
const 일치 = await bcrypt.compare("1234", 해시);

// ❌ JWT 시크릿 하드코딩
const token = jwt.sign(data, "my-secret");

// ✅ 환경변수 사용
const token = jwt.sign(data, process.env.JWT_SECRET);

// ═══ 5. 입력 검증 ═══

// ✅ zod로 서버 입력 검증
import { z } from "zod";

const 회원가입스키마 = z.object({
    email: z.string().email("올바른 이메일을 입력하세요"),
    password: z.string().min(8, "8자 이상"),
    name: z.string().min(2).max(50),
});

// API에서
const 결과 = 회원가입스키마.safeParse(body);
if (!결과.success) {
    return Response.json({ errors: 결과.error.issues }, { status: 400 });
}

// ═══ 6. 환경변수 보안 ═══

// .env (절대 git에 커밋하지 말 것!)
DATABASE_URL=postgresql://...
JWT_SECRET=랜덤문자열
TOSS_SECRET_KEY=...

// .gitignore에 추가
.env
.env.local
.env.production
```

**체크리스트: XSS(React 기본 방어) + SQL Injection(ORM 사용) + bcrypt(비번 해싱) + 환경변수(시크릿 보호)**'''),

    # ═══ 테스트 ═══
    m("테스트 코드 작성법 알려줘. 유닛테스트, 통합테스트, E2E",
'''테스트 종류별 작성법입니다.

```typescript
// ═══ 1. 유닛 테스트 (Vitest/Jest) ═══

// utils/calculate.ts
export function 세금계산(소득: number): number {
    if (소득 <= 14000000) return 소득 * 0.06;
    if (소득 <= 50000000) return 소득 * 0.15 - 1260000;
    if (소득 <= 88000000) return 소득 * 0.24 - 5760000;
    return 소득 * 0.35 - 15440000;
}

// utils/calculate.test.ts
import { describe, it, expect } from "vitest";
import { 세금계산 } from "./calculate";

describe("세금계산", () => {
    it("1400만원 이하: 6%", () => {
        expect(세금계산(10000000)).toBe(600000);
    });

    it("5000만원 이하: 15%", () => {
        expect(세금계산(30000000)).toBe(3240000);
    });

    it("0원 입력", () => {
        expect(세금계산(0)).toBe(0);
    });

    it("음수 입력 (엣지 케이스)", () => {
        expect(세금계산(-1000)).toBe(-60);
    });
});

// ═══ 2. API 통합 테스트 ═══

// api/users.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";

describe("유저 API", () => {
    let 토큰: string;

    beforeAll(async () => {
        // 테스트 유저 생성 + 로그인
        const 응답 = await fetch("http://localhost:3000/api/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: "test@test.com",
                password: "test1234",
                name: "테스터",
            }),
        });
        const 데이터 = await 응답.json();
        토큰 = 데이터.token;
    });

    it("내 정보 조회", async () => {
        const 응답 = await fetch("http://localhost:3000/api/users/me", {
            headers: { Authorization: `Bearer ${토큰}` },
        });
        expect(응답.status).toBe(200);
        const 유저 = await 응답.json();
        expect(유저.email).toBe("test@test.com");
    });

    it("비인증 요청 → 401", async () => {
        const 응답 = await fetch("http://localhost:3000/api/users/me");
        expect(응답.status).toBe(401);
    });
});

// ═══ 3. E2E 테스트 (Playwright) ═══

// e2e/login.spec.ts
import { test, expect } from "@playwright/test";

test("로그인 흐름", async ({ page }) => {
    // 로그인 페이지 이동
    await page.goto("http://localhost:3000/login");

    // 이메일/비밀번호 입력
    await page.fill('[type="email"]', "test@test.com");
    await page.fill('[type="password"]', "test1234");

    // 로그인 버튼 클릭
    await page.click('button:text("로그인")');

    // 대시보드로 이동 확인
    await expect(page).toHaveURL(/dashboard/);
    await expect(page.locator("h1")).toContainText("대시보드");
});

test("잘못된 비밀번호 → 에러", async ({ page }) => {
    await page.goto("http://localhost:3000/login");
    await page.fill('[type="email"]', "test@test.com");
    await page.fill('[type="password"]', "틀린비번");
    await page.click('button:text("로그인")');

    await expect(page.locator(".text-red-500")).toBeVisible();
});
```

```bash
# 실행
pnpm vitest          # 유닛 + 통합
pnpm playwright test # E2E
```'''),

    # ═══ 디자인 패턴 ═══
    m("자주 쓰는 디자인 패턴 알려줘",
'''실무에서 자주 쓰는 디자인 패턴입니다.

```typescript
// ═══ 1. 싱글톤 (인스턴스 1개 보장) ═══

class DB {
    private static instance: DB;
    private constructor() { /* DB 연결 */ }

    static getInstance(): DB {
        if (!DB.instance) {
            DB.instance = new DB();
        }
        return DB.instance;
    }
}

// 어디서든 같은 인스턴스
const db1 = DB.getInstance();
const db2 = DB.getInstance();
console.log(db1 === db2); // true

// ═══ 2. 옵저버 (이벤트 시스템) ═══

class 이벤트버스 {
    private 리스너들: Map<string, Function[]> = new Map();

    on(이벤트: string, 콜백: Function) {
        const 목록 = this.리스너들.get(이벤트) || [];
        목록.push(콜백);
        this.리스너들.set(이벤트, 목록);
    }

    emit(이벤트: string, 데이터?: any) {
        const 목록 = this.리스너들.get(이벤트) || [];
        목록.forEach(콜백 => 콜백(데이터));
    }
}

const bus = new 이벤트버스();
bus.on("주문완료", (주문) => console.log("이메일 발송:", 주문.id));
bus.on("주문완료", (주문) => console.log("재고 감소:", 주문.상품));
bus.emit("주문완료", { id: "123", 상품: "노트북" });

// ═══ 3. 팩토리 (객체 생성 위임) ═══

interface 알림 {
    보내기(메시지: string): void;
}

class 이메일알림 implements 알림 {
    보내기(메시지: string) { console.log(`이메일: ${메시지}`); }
}

class SMS알림 implements 알림 {
    보내기(메시지: string) { console.log(`SMS: ${메시지}`); }
}

class 푸시알림 implements 알림 {
    보내기(메시지: string) { console.log(`푸시: ${메시지}`); }
}

function 알림생성(유형: string): 알림 {
    switch (유형) {
        case "email": return new 이메일알림();
        case "sms": return new SMS알림();
        case "push": return new 푸시알림();
        default: throw new Error("알 수 없는 유형");
    }
}

const 알림 = 알림생성("email");
알림.보내기("주문이 완료되었습니다");

// ═══ 4. 전략 (알고리즘 교체) ═══

interface 할인전략 {
    계산(가격: number): number;
}

const 정가: 할인전략 = { 계산: (가격) => 가격 };
const 회원할인: 할인전략 = { 계산: (가격) => 가격 * 0.9 };
const VIP할인: 할인전략 = { 계산: (가격) => 가격 * 0.8 };
const 쿠폰할인 = (금액: number): 할인전략 => ({
    계산: (가격) => Math.max(0, 가격 - 금액),
});

function 최종가격(가격: number, 전략: 할인전략): number {
    return 전략.계산(가격);
}

console.log(최종가격(10000, 회원할인));        // 9000
console.log(최종가격(10000, 쿠폰할인(3000)));  // 7000

// ═══ 5. 미들웨어 (체인 처리) ═══

type 미들웨어 = (req: any, res: any, next: () => void) => void;

function 로깅(): 미들웨어 {
    return (req, res, next) => {
        console.log(`${req.method} ${req.url}`);
        next();
    };
}

function 인증체크(): 미들웨어 {
    return (req, res, next) => {
        if (!req.headers.authorization) {
            res.status = 401;
            return;
        }
        next();
    };
}

// Express 스타일로 연결
// app.use(로깅());
// app.use(인증체크());
```

**실무 팁: 싱글톤(DB), 옵저버(이벤트), 전략(할인/정렬) 3개만 알아도 대부분 해결됩니다.**'''),

    # ═══ Git 고급 ═══
    m("Git 고급 사용법 알려줘. 충돌 해결, rebase, cherry-pick",
'''Git 고급 기법들입니다.

```bash
# ═══ 1. 충돌 해결 ═══

# 충돌 발생 시
git merge feature-branch
# CONFLICT (content): Merge conflict in src/app.tsx

# 파일 열면:
<<<<<<< HEAD
const 제목 = "현재 브랜치 코드";
=======
const 제목 = "병합할 브랜치 코드";
>>>>>>> feature-branch

# 원하는 코드만 남기고 마커 삭제 후:
const 제목 = "최종 코드";

git add src/app.tsx
git commit -m "충돌 해결: 제목 통합"

# ═══ 2. Rebase (히스토리 정리) ═══

# ❌ merge (커밋 히스토리 복잡)
# A─B─C─────M (merge commit)
#    └─D─E─┘

# ✅ rebase (깔끔한 히스토리)
# A─B─C─D'─E'
git checkout feature-branch
git rebase main
# 충돌 있으면 해결 후:
git rebase --continue

# Interactive rebase (커밋 합치기)
git rebase -i HEAD~3
# 에디터에서:
# pick abc123 기능 A 구현
# squash def456 기능 A 수정
# squash ghi789 기능 A 버그 수정
# → 3개 커밋이 1개로 합쳐짐

# ═══ 3. Cherry-pick (특정 커밋만 가져오기) ═══

# main에 hotfix 커밋만 가져오기
git checkout main
git cherry-pick abc123  # 커밋 해시

# 여러 개
git cherry-pick abc123 def456

# ═══ 4. Stash (임시 저장) ═══

# 작업 중인데 급히 다른 브랜치로 가야 할 때
git stash              # 현재 변경사항 임시 저장
git checkout hotfix    # 다른 브랜치로
# ... 작업 ...
git checkout feature   # 원래 브랜치로
git stash pop          # 임시 저장 복원

# ═══ 5. Reset vs Revert ═══

# reset: 커밋 자체를 삭제 (주의!)
git reset --soft HEAD~1  # 커밋 취소, 변경 유지
git reset --hard HEAD~1  # 커밋 + 변경 모두 삭제

# revert: 취소하는 새 커밋 생성 (안전)
git revert abc123       # abc123을 되돌리는 커밋 생성

# ═══ 6. 실수 복구 ═══

# 삭제한 브랜치 복구
git reflog             # 모든 작업 기록 확인
git checkout -b 복구 abc123  # 해당 시점으로 복구

# 강제 push 후 복구
git reflog
git reset --hard HEAD@{2}  # 2번 전 상태로
```

**핵심: rebase(정리), cherry-pick(선택 가져오기), stash(임시 저장), reflog(실수 복구)**'''),

    # ═══ 환경 설정 ═══
    m("개발 환경 세팅 처음부터 알려줘. Mac 기준",
'''Mac 개발 환경 전체 세팅입니다.

```bash
# ═══ 1. 기본 도구 ═══

# Homebrew (패키지 관리자)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Git
brew install git
git config --global user.name "이름"
git config --global user.email "email@example.com"

# ═══ 2. Node.js (nvm으로 관리) ═══

brew install nvm
echo 'export NVM_DIR="$HOME/.nvm"' >> ~/.zshrc
source ~/.zshrc

nvm install 22       # Node.js 22 LTS
nvm use 22
nvm alias default 22

# pnpm (npm 대체, 빠름)
npm install -g pnpm

# ═══ 3. Python ═══

brew install python@3.12
brew install poetry    # 파이썬 패키지 관리

# ═══ 4. 데이터베이스 ═══

# PostgreSQL
brew install postgresql@16
brew services start postgresql@16

# Redis
brew install redis
brew services start redis

# ═══ 5. Docker ═══

brew install --cask docker
# Docker Desktop 앱 실행

# ═══ 6. 에디터 ═══

brew install --cask visual-studio-code

# VS Code 확장 추천
code --install-extension dbaeumer.vscode-eslint
code --install-extension esbenp.prettier-vscode
code --install-extension bradlc.vscode-tailwindcss
code --install-extension prisma.prisma

# ═══ 7. 터미널 ═══

# Oh My Zsh
sh -c "$(curl -fsSL https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# .zshrc 설정
echo '
alias gs="git status"
alias gc="git commit"
alias gp="git push"
alias gl="git log --oneline"
alias dev="pnpm dev"
alias build="pnpm build"
' >> ~/.zshrc

# ═══ 8. 새 프로젝트 시작 ═══

# Next.js
pnpm create next-app 프로젝트명 --typescript --tailwind --app

# FastAPI
mkdir 프로젝트명 && cd 프로젝트명
poetry init
poetry add fastapi uvicorn

# 바로 개발 시작!
cd 프로젝트명 && pnpm dev
```'''),

    # ═══ API 설계 ═══
    m("REST API 설계 원칙 알려줘",
'''REST API 설계 핵심 원칙입니다.

```
═══ 1. URL 규칙 ═══

✅ 좋은 예                     ❌ 나쁜 예
GET    /users                  GET    /getUsers
GET    /users/123              GET    /user?id=123
POST   /users                  POST   /createUser
PUT    /users/123              POST   /updateUser
DELETE /users/123              GET    /deleteUser/123
GET    /users/123/posts        GET    /getUserPosts?userId=123

규칙:
- 명사 사용 (동사 X)
- 복수형 (/users, /posts)
- 소문자 + 하이픈 (/api-keys, 아닌 /apiKeys)
- 중첩은 2단계까지 (/users/123/posts)

═══ 2. HTTP 상태 코드 ═══

200  성공
201  생성됨 (POST 성공)
204  성공 (응답 본문 없음, DELETE)
400  잘못된 요청 (유효성 실패)
401  인증 필요 (로그인 안 됨)
403  권한 없음 (로그인은 했지만 접근 불가)
404  없음
409  충돌 (이미 존재)
422  처리 불가 (데이터 형식 오류)
429  요청 과다 (Rate Limit)
500  서버 오류

═══ 3. 응답 형식 ═══
```

```json
// 성공
{
    "data": { "id": "123", "name": "홍길동" },
    "meta": { "timestamp": "2026-04-20T10:00:00Z" }
}

// 목록 (페이지네이션)
{
    "data": [{ "id": "1" }, { "id": "2" }],
    "pagination": {
        "page": 1,
        "limit": 20,
        "total": 150,
        "totalPages": 8
    }
}

// 에러
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "이메일 형식이 올바르지 않습니다",
        "details": [
            { "field": "email", "message": "올바른 이메일을 입력하세요" }
        ]
    }
}
```

```
═══ 4. 버전 관리 ═══

/api/v1/users    ← URL에 버전
/api/v2/users    ← 새 버전

═══ 5. 인증 ═══

// 헤더에 Bearer 토큰
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...

// API 키
X-API-Key: hk-a1b2c3d4e5f6

═══ 6. Rate Limiting ═══

// 응답 헤더
X-RateLimit-Limit: 100       // 제한
X-RateLimit-Remaining: 95    // 남은 횟수
X-RateLimit-Reset: 1620000   // 리셋 시간
```

**핵심: 일관된 URL + 올바른 상태 코드 + 명확한 에러 응답**'''),

    # ═══ Prisma 고급 ═══
    m("Prisma 고급 사용법 알려줘",
'''Prisma ORM 고급 기법들입니다.

```typescript
// ═══ 1. 트랜잭션 ═══

// 여러 작업을 하나의 단위로 (하나라도 실패하면 전체 롤백)
const 결과 = await prisma.$transaction(async (tx) => {
    // 1. 주문 생성
    const 주문 = await tx.order.create({
        data: { userId, totalAmount: 50000 },
    });

    // 2. 재고 감소 (실패하면 주문도 취소됨)
    await tx.product.update({
        where: { id: productId },
        data: { stock: { decrement: 1 } },
    });

    // 3. 결제 기록
    await tx.payment.create({
        data: { orderId: 주문.id, amount: 50000 },
    });

    return 주문;
});

// ═══ 2. 복잡한 쿼리 ═══

// 검색 + 필터 + 정렬 + 페이지네이션
const { search, category, sort, page = 1 } = params;

const where = {
    AND: [
        search ? {
            OR: [
                { name: { contains: search, mode: "insensitive" } },
                { description: { contains: search, mode: "insensitive" } },
            ],
        } : {},
        category ? { categoryId: category } : {},
        { isActive: true },
    ],
};

const [상품들, 총수] = await Promise.all([
    prisma.product.findMany({
        where,
        include: {
            category: true,
            _count: { select: { reviews: true } },
        },
        orderBy: sort === "price" ? { price: "asc" }
               : sort === "newest" ? { createdAt: "desc" }
               : { createdAt: "desc" },
        skip: (page - 1) * 20,
        take: 20,
    }),
    prisma.product.count({ where }),
]);

// ═══ 3. 집계 (Aggregate) ═══

// 매출 통계
const 통계 = await prisma.order.aggregate({
    where: { status: "PAID", paidAt: { gte: 이번달시작 } },
    _sum: { totalAmount: true },
    _avg: { totalAmount: true },
    _count: true,
});
// { _sum: { totalAmount: 15000000 }, _avg: { totalAmount: 75000 }, _count: 200 }

// 그룹별 통계
const 카테고리별 = await prisma.product.groupBy({
    by: ["categoryId"],
    _count: true,
    _avg: { price: true },
    orderBy: { _count: { categoryId: "desc" } },
});

// ═══ 4. Raw SQL (복잡한 쿼리) ═══

const 매출순위 = await prisma.$queryRaw`
    SELECT u.name, SUM(o.total_amount) as total_sales
    FROM "User" u
    JOIN "Order" o ON u.id = o.user_id
    WHERE o.status = 'PAID'
    GROUP BY u.id, u.name
    ORDER BY total_sales DESC
    LIMIT 10
`;

// ═══ 5. 미들웨어 (로깅, 소프트 삭제) ═══

// 모든 쿼리 로깅
prisma.$use(async (params, next) => {
    const 시작 = Date.now();
    const 결과 = await next(params);
    const 소요 = Date.now() - 시작;
    console.log(`${params.model}.${params.action}: ${소요}ms`);
    return 결과;
});

// 소프트 삭제 (실제 삭제 대신 deletedAt 설정)
prisma.$use(async (params, next) => {
    if (params.action === "delete") {
        params.action = "update";
        params.args.data = { deletedAt: new Date() };
    }
    return next(params);
});
```'''),

    # ═══ WebSocket ═══
    m("WebSocket 실시간 통신 구현해줘",
'''WebSocket 실시간 통신입니다.

```typescript
// ═══ 서버 (Next.js + Socket.io) ═══

// server.ts
import { Server } from "socket.io";
import { createServer } from "http";

const httpServer = createServer();
const io = new Server(httpServer, {
    cors: { origin: "http://localhost:3000" },
});

// 온라인 유저 관리
const 온라인유저 = new Map<string, string>(); // socketId → userId

io.on("connection", (socket) => {
    console.log("연결:", socket.id);

    // 로그인
    socket.on("login", (userId: string) => {
        온라인유저.set(socket.id, userId);
        socket.join(`user:${userId}`); // 개인 채널
        io.emit("online_count", 온라인유저.size);
    });

    // 채팅방 참가
    socket.on("join_room", (roomId: string) => {
        socket.join(roomId);
        socket.to(roomId).emit("user_joined", {
            userId: 온라인유저.get(socket.id),
        });
    });

    // 메시지 전송
    socket.on("message", (data: { roomId: string; content: string }) => {
        const userId = 온라인유저.get(socket.id);
        io.to(data.roomId).emit("new_message", {
            userId,
            content: data.content,
            timestamp: new Date(),
        });
    });

    // 타이핑 표시
    socket.on("typing", (roomId: string) => {
        socket.to(roomId).emit("user_typing", {
            userId: 온라인유저.get(socket.id),
        });
    });

    // 연결 해제
    socket.on("disconnect", () => {
        온라인유저.delete(socket.id);
        io.emit("online_count", 온라인유저.size);
    });
});

httpServer.listen(3001);

// ═══ 클라이언트 (React) ═══

// hooks/useSocket.ts
import { io, Socket } from "socket.io-client";
import { useEffect, useRef, useState } from "react";

export function useSocket(roomId: string) {
    const socketRef = useRef<Socket>();
    const [메시지들, 메시지설정] = useState<any[]>([]);
    const [타이핑유저, 타이핑설정] = useState<string | null>(null);
    const [온라인수, 온라인설정] = useState(0);

    useEffect(() => {
        const socket = io("http://localhost:3001");
        socketRef.current = socket;

        socket.emit("join_room", roomId);

        socket.on("new_message", (msg) => {
            메시지설정(이전 => [...이전, msg]);
        });

        socket.on("user_typing", ({ userId }) => {
            타이핑설정(userId);
            setTimeout(() => 타이핑설정(null), 2000);
        });

        socket.on("online_count", (count) => {
            온라인설정(count);
        });

        return () => { socket.disconnect(); };
    }, [roomId]);

    const 전송 = (content: string) => {
        socketRef.current?.emit("message", { roomId, content });
    };

    const 타이핑알림 = () => {
        socketRef.current?.emit("typing", roomId);
    };

    return { 메시지들, 전송, 타이핑알림, 타이핑유저, 온라인수 };
}
```'''),

    # ═══ 정규표현식 ═══
    m("정규표현식 자주 쓰는 패턴",
'''실무에서 자주 쓰는 정규표현식입니다.

```javascript
// ═══ 검증 ═══

// 이메일
/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/

// 한국 전화번호
/^01[016789]-?\d{3,4}-?\d{4}$/

// 비밀번호 (8자+, 영문+숫자+특수문자)
/^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$/

// 한국 주민번호
/^\d{6}-?[1-4]\d{6}$/

// URL
/^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$/

// ═══ 추출 ═══

const text = "연락처: 010-1234-5678, 이메일: test@mail.com";

// 전화번호 추출
const 전화 = text.match(/01[016789]-?\d{3,4}-?\d{4}/g);
// ["010-1234-5678"]

// 이메일 추출
const 이메일 = text.match(/[\w.-]+@[\w.-]+\.\w+/g);
// ["test@mail.com"]

// ═══ 치환 ═══

// 개인정보 마스킹
"홍길동".replace(/(.)(.+)(.)/, "$1*$3");           // "홍*동"
"010-1234-5678".replace(/(\d{3})-(\d{4})-(\d{4})/, "$1-****-$3"); // "010-****-5678"

// HTML 태그 제거
"<p>안녕<b>하세요</b></p>".replace(/<[^>]*>/g, ""); // "안녕하세요"

// 연속 공백 정리
"안녕   하세요    반갑습니다".replace(/\s+/g, " ");  // "안녕 하세요 반갑습니다"

// ═══ 실전 예시 ═══

// 금액 포맷 (3자리 콤마)
function 금액포맷(n: number): string {
    return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}
금액포맷(1234567); // "1,234,567"

// 카멜케이스 → 스네이크케이스
"camelCase".replace(/([A-Z])/g, "_$1").toLowerCase(); // "camel_case"
```'''),
]


def build_detailed_coding(output_path):
    logger.info(f"  상세 코딩: {len(DATA)}건")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"\n총 {len(DATA)}건 → {output_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/detailed_coding.jsonl")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" 화랑 AI 상세 코딩 학습 데이터")
    logger.info("=" * 60)
    build_detailed_coding(args.output)
