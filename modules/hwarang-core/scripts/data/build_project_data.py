"""화랑 AI 프로젝트 단위 코딩 학습 데이터

단일 함수가 아닌 전체 프로젝트 수준의 코딩 학습.
아키텍처 설계 → 파일 구조 → 핵심 코드 → 연결까지.

카테고리:
  1. 풀스택 웹앱 (Next.js + DB)
  2. REST API 서버 (FastAPI)
  3. CLI 도구
  4. 인증 시스템
  5. 결제 연동
  6. 실시간 채팅
  7. 대시보드
  8. 크롤러/봇

사용법:
    python scripts/data/build_project_data.py \
        --output data/sft/project_coding.jsonl
"""

import json
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SYSTEM = """당신은 화랑 AI입니다. 시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
프로젝트 단위의 코드를 설계하고 구현합니다.
항상 한국어로 설명하고, 코드 주석도 한국어로 작성합니다.
프로젝트 구조 → 핵심 코드 → 사용 방법 순서로 답변합니다."""


def make(q, a):
    return {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": q},
        {"role": "assistant", "content": a},
    ]}


# ═══════════════════════════════════════════════════════════════
# 1. 풀스택 웹앱
# ═══════════════════════════════════════════════════════════════

FULLSTACK = [
    make("Next.js + Prisma로 게시판 만들어줘",
'''게시판 프로젝트 전체 구조와 핵심 코드입니다.

## 프로젝트 구조

```
board-app/
├── prisma/
│   └── schema.prisma          # DB 스키마
├── src/
│   ├── app/
│   │   ├── page.tsx            # 게시글 목록
│   │   ├── write/page.tsx      # 글쓰기
│   │   ├── posts/[id]/page.tsx # 게시글 상세
│   │   └── api/
│   │       └── posts/
│   │           ├── route.ts    # GET(목록), POST(작성)
│   │           └── [id]/route.ts # GET(상세), PUT, DELETE
│   └── lib/
│       └── db.ts               # Prisma 클라이언트
├── package.json
└── .env
```

## 1. DB 스키마

```prisma
// prisma/schema.prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model Post {
  id        String   @id @default(cuid())
  title     String
  content   String   @db.Text
  author    String
  views     Int      @default(0)
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
  comments  Comment[]
}

model Comment {
  id        String   @id @default(cuid())
  content   String
  author    String
  post      Post     @relation(fields: [postId], references: [id], onDelete: Cascade)
  postId    String
  createdAt DateTime @default(now())
}
```

## 2. API 라우트

```typescript
// src/app/api/posts/route.ts
import { prisma } from "@/lib/db";

// 게시글 목록
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const page = parseInt(searchParams.get("page") || "1");
  const limit = 10;

  const [posts, total] = await Promise.all([
    prisma.post.findMany({
      orderBy: { createdAt: "desc" },
      skip: (page - 1) * limit,
      take: limit,
      include: { _count: { select: { comments: true } } },
    }),
    prisma.post.count(),
  ]);

  return Response.json({
    posts,
    pagination: { page, limit, total, totalPages: Math.ceil(total / limit) },
  });
}

// 게시글 작성
export async function POST(request: Request) {
  const { title, content, author } = await request.json();

  if (!title || !content) {
    return Response.json({ error: "제목과 내용은 필수입니다" }, { status: 400 });
  }

  const post = await prisma.post.create({
    data: { title, content, author: author || "익명" },
  });

  return Response.json(post, { status: 201 });
}
```

## 3. 게시글 목록 페이지

```tsx
// src/app/page.tsx
import Link from "next/link";

async function getPosts(page = 1) {
  const res = await fetch(`http://localhost:3000/api/posts?page=${page}`, {
    cache: "no-store",
  });
  return res.json();
}

export default async function 게시판() {
  const { posts, pagination } = await getPosts();

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">게시판</h1>
        <Link href="/write"
          className="px-4 py-2 bg-blue-500 text-white rounded-lg">
          글쓰기
        </Link>
      </div>

      <div className="space-y-2">
        {posts.map((post: any) => (
          <Link key={post.id} href={`/posts/${post.id}`}
            className="block p-4 border rounded-lg hover:bg-gray-50">
            <h2 className="font-medium">{post.title}</h2>
            <div className="text-sm text-gray-500 mt-1">
              {post.author} · {new Date(post.createdAt).toLocaleDateString("ko-KR")}
              · 조회 {post.views} · 댓글 {post._count.comments}
            </div>
          </Link>
        ))}
      </div>

      {/* 페이지네이션 */}
      <div className="flex justify-center gap-2 mt-6">
        {Array.from({ length: pagination.totalPages }, (_, i) => (
          <Link key={i} href={`/?page=${i + 1}`}
            className={`px-3 py-1 rounded ${
              pagination.page === i + 1 ? "bg-blue-500 text-white" : "border"
            }`}>
            {i + 1}
          </Link>
        ))}
      </div>
    </div>
  );
}
```

## 4. 실행 방법

```bash
# 설치
pnpm install
pnpm add prisma @prisma/client
pnpm add -D @types/node typescript

# DB 설정
echo 'DATABASE_URL="postgresql://user:pass@localhost:5432/board"' > .env
npx prisma db push

# 실행
pnpm dev
# → http://localhost:3000
```

이 구조를 기반으로 기능을 확장할 수 있습니다 (회원가입, 좋아요, 검색 등).'''),

    make("FastAPI로 REST API 서버 만들어줘. 유저 CRUD + 인증 포함",
'''FastAPI REST API 서버 전체 구조입니다.

## 프로젝트 구조

```
api-server/
├── app/
│   ├── __init__.py
│   ├── main.py              # 앱 진입점
│   ├── config.py             # 설정
│   ├── database.py           # DB 연결
│   ├── models/
│   │   └── user.py           # SQLAlchemy 모델
│   ├── schemas/
│   │   └── user.py           # Pydantic 스키마
│   ├── routers/
│   │   ├── auth.py           # 인증 (로그인/회원가입)
│   │   └── users.py          # 유저 CRUD
│   └── utils/
│       ├── security.py       # JWT + 비밀번호 해싱
│       └── dependencies.py   # 인증 의존성
├── requirements.txt
└── .env
```

## 1. 메인 앱

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, users

app = FastAPI(
    title="화랑 API",
    description="유저 관리 REST API",
    version="1.0.0",
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router, prefix="/auth", tags=["인증"])
app.include_router(users.router, prefix="/users", tags=["유저"])

@app.get("/")
def 메인():
    return {"서비스": "화랑 API", "버전": "1.0.0"}
```

## 2. 인증 (JWT)

```python
# app/utils/security.py
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
import os

SECRET_KEY = os.getenv("SECRET_KEY", "비밀키")
ALGORITHM = "HS256"

비밀번호_컨텍스트 = CryptContext(schemes=["bcrypt"])

def 비밀번호_해싱(비밀번호: str) -> str:
    return 비밀번호_컨텍스트.hash(비밀번호)

def 비밀번호_확인(평문: str, 해시: str) -> bool:
    return 비밀번호_컨텍스트.verify(평문, 해시)

def 토큰_생성(유저_id: str) -> str:
    만료 = datetime.utcnow() + timedelta(hours=24)
    payload = {"sub": 유저_id, "exp": 만료}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def 토큰_검증(토큰: str) -> str | None:
    try:
        payload = jwt.decode(토큰, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
```

```python
# app/routers/auth.py
from fastapi import APIRouter, HTTPException
from app.schemas.user import 회원가입요청, 로그인요청, 토큰응답
from app.utils.security import 비밀번호_해싱, 비밀번호_확인, 토큰_생성

router = APIRouter()

@router.post("/회원가입", response_model=토큰응답)
async def 회원가입(요청: 회원가입요청):
    # 이메일 중복 체크
    기존유저 = await db.유저_조회(이메일=요청.이메일)
    if 기존유저:
        raise HTTPException(409, "이미 가입된 이메일입니다")

    # 생성
    해시 = 비밀번호_해싱(요청.비밀번호)
    유저 = await db.유저_생성(이름=요청.이름, 이메일=요청.이메일, 비밀번호=해시)
    토큰 = 토큰_생성(유저.id)

    return {"access_token": 토큰, "token_type": "bearer"}

@router.post("/로그인", response_model=토큰응답)
async def 로그인(요청: 로그인요청):
    유저 = await db.유저_조회(이메일=요청.이메일)
    if not 유저 or not 비밀번호_확인(요청.비밀번호, 유저.비밀번호):
        raise HTTPException(401, "이메일 또는 비밀번호가 틀렸습니다")

    토큰 = 토큰_생성(유저.id)
    return {"access_token": 토큰, "token_type": "bearer"}
```

## 3. 유저 CRUD

```python
# app/routers/users.py
from fastapi import APIRouter, Depends, HTTPException
from app.utils.dependencies import 현재유저_가져오기

router = APIRouter()

@router.get("/me")
async def 내정보(유저 = Depends(현재유저_가져오기)):
    return {"id": 유저.id, "이름": 유저.이름, "이메일": 유저.이메일}

@router.get("/")
async def 유저목록(skip: int = 0, limit: int = 20):
    유저들 = await db.유저_목록(skip=skip, limit=limit)
    return 유저들

@router.put("/me")
async def 내정보수정(이름: str, 유저 = Depends(현재유저_가져오기)):
    수정된 = await db.유저_수정(유저.id, 이름=이름)
    return 수정된

@router.delete("/me")
async def 탈퇴(유저 = Depends(현재유저_가져오기)):
    await db.유저_삭제(유저.id)
    return {"메시지": "탈퇴 완료"}
```

## 4. 실행

```bash
pip install fastapi uvicorn python-jose passlib[bcrypt] sqlalchemy
uvicorn app.main:app --reload
# → http://localhost:8000/docs (Swagger 문서)
```

`/docs`에서 모든 API를 테스트할 수 있습니다.'''),

    make("파이썬으로 웹 크롤러 만들어줘",
'''웹 크롤러 프로젝트입니다.

## 프로젝트 구조

```
crawler/
├── crawler.py           # 메인 크롤러
├── parser.py            # HTML 파싱
├── storage.py           # 데이터 저장
├── config.py            # 설정
└── requirements.txt
```

## 핵심 코드

```python
# crawler.py
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import time
from dataclasses import dataclass

@dataclass
class 크롤링결과:
    url: str
    제목: str
    내용: str
    날짜: str
    수집시간: float

class 웹크롤러:
    """비동기 웹 크롤러"""

    def __init__(self, 동시요청수: int = 5, 딜레이: float = 1.0):
        self.동시요청수 = 동시요청수
        self.딜레이 = 딜레이  # 요청 간 대기 (예의)
        self.결과들: list[크롤링결과] = []

    async def 페이지_가져오기(self, session, url: str) -> str | None:
        """URL에서 HTML 가져오기"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as 응답:
                if 응답.status == 200:
                    return await 응답.text()
                print(f"오류 {응답.status}: {url}")
        except Exception as e:
            print(f"실패: {url} - {e}")
        return None

    def HTML_파싱(self, html: str, url: str) -> 크롤링결과 | None:
        """HTML에서 데이터 추출"""
        soup = BeautifulSoup(html, "html.parser")

        제목 = soup.find("title")
        본문 = soup.find("article") or soup.find("main") or soup.find("body")

        if not 제목:
            return None

        return 크롤링결과(
            url=url,
            제목=제목.get_text(strip=True),
            내용=본문.get_text(strip=True)[:1000] if 본문 else "",
            날짜=time.strftime("%Y-%m-%d"),
            수집시간=time.time(),
        )

    async def 크롤링(self, urls: list[str]):
        """여러 URL 비동기 크롤링"""
        semaphore = asyncio.Semaphore(self.동시요청수)

        async def 작업(session, url):
            async with semaphore:
                html = await self.페이지_가져오기(session, url)
                if html:
                    결과 = self.HTML_파싱(html, url)
                    if 결과:
                        self.결과들.append(결과)
                await asyncio.sleep(self.딜레이)

        async with aiohttp.ClientSession() as session:
            tasks = [작업(session, url) for url in urls]
            await asyncio.gather(*tasks)

        print(f"크롤링 완료: {len(self.결과들)}/{len(urls)}건 성공")

    def 저장(self, 파일경로: str = "결과.json"):
        """결과를 JSON으로 저장"""
        데이터 = [
            {"url": r.url, "제목": r.제목, "내용": r.내용[:500], "날짜": r.날짜}
            for r in self.결과들
        ]
        with open(파일경로, "w", encoding="utf-8") as f:
            json.dump(데이터, f, ensure_ascii=False, indent=2)
        print(f"저장 완료: {파일경로} ({len(데이터)}건)")


# 사용 예시
async def main():
    크롤러 = 웹크롤러(동시요청수=3, 딜레이=0.5)

    urls = [
        "https://news.ycombinator.com",
        "https://github.com/trending",
        "https://python.org",
    ]

    await 크롤러.크롤링(urls)
    크롤러.저장("크롤링_결과.json")

if __name__ == "__main__":
    asyncio.run(main())
```

## 실행

```bash
pip install aiohttp beautifulsoup4
python crawler.py
```

⚠️ 크롤링 시 해당 사이트의 robots.txt를 확인하고, 과도한 요청은 자제해주세요.'''),

    make("실시간 채팅 앱 만들어줘",
'''WebSocket 기반 실시간 채팅 앱입니다.

## 구조

```
chat-app/
├── server.py            # FastAPI WebSocket 서버
├── static/
│   └── index.html       # 채팅 UI
└── requirements.txt
```

## 서버 (FastAPI + WebSocket)

```python
# server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from datetime import datetime

app = FastAPI()

# 연결된 클라이언트 관리
class 채팅매니저:
    def __init__(self):
        self.연결들: list[WebSocket] = []

    async def 연결추가(self, ws: WebSocket):
        await ws.accept()
        self.연결들.append(ws)

    def 연결제거(self, ws: WebSocket):
        self.연결들.remove(ws)

    async def 전체전송(self, 메시지: dict):
        for 연결 in self.연결들:
            try:
                await 연결.send_json(메시지)
            except:
                pass

매니저 = 채팅매니저()

@app.websocket("/ws/{닉네임}")
async def 채팅(ws: WebSocket, 닉네임: str):
    await 매니저.연결추가(ws)

    # 입장 알림
    await 매니저.전체전송({
        "유형": "시스템",
        "내용": f"{닉네임}님이 입장했습니다.",
        "시간": datetime.now().strftime("%H:%M"),
    })

    try:
        while True:
            데이터 = await ws.receive_text()
            await 매니저.전체전송({
                "유형": "메시지",
                "닉네임": 닉네임,
                "내용": 데이터,
                "시간": datetime.now().strftime("%H:%M"),
            })
    except WebSocketDisconnect:
        매니저.연결제거(ws)
        await 매니저.전체전송({
            "유형": "시스템",
            "내용": f"{닉네임}님이 퇴장했습니다.",
            "시간": datetime.now().strftime("%H:%M"),
        })

app.mount("/", StaticFiles(directory="static", html=True))
```

## 프론트 (HTML + JS)

```html
<!-- static/index.html -->
<!DOCTYPE html>
<html lang="ko">
<head>
    <title>실시간 채팅</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: sans-serif; height: 100vh; display: flex; flex-direction: column; }
        #messages { flex: 1; overflow-y: auto; padding: 16px; }
        .msg { margin-bottom: 8px; padding: 8px 12px; border-radius: 8px; max-width: 70%; }
        .msg.mine { background: #3b82f6; color: white; margin-left: auto; }
        .msg.other { background: #f1f5f9; }
        .msg.system { text-align: center; color: #94a3b8; font-size: 12px; max-width: 100%; }
        #input-area { display: flex; padding: 12px; border-top: 1px solid #e2e8f0; }
        #input-area input { flex: 1; padding: 8px 16px; border: 1px solid #e2e8f0; border-radius: 8px; }
        #input-area button { margin-left: 8px; padding: 8px 20px; background: #3b82f6; color: white; border: none; border-radius: 8px; cursor: pointer; }
    </style>
</head>
<body>
    <div id="messages"></div>
    <div id="input-area">
        <input id="msg" placeholder="메시지 입력..." onkeypress="if(event.key==='Enter')전송()">
        <button onclick="전송()">보내기</button>
    </div>
    <script>
        const 닉네임 = prompt("닉네임을 입력하세요") || "익명";
        const ws = new WebSocket(`ws://localhost:8000/ws/${닉네임}`);
        const 메시지영역 = document.getElementById("messages");

        ws.onmessage = (e) => {
            const 데이터 = JSON.parse(e.data);
            const div = document.createElement("div");
            div.className = `msg ${데이터.유형 === "시스템" ? "system" : 데이터.닉네임 === 닉네임 ? "mine" : "other"}`;
            div.textContent = 데이터.유형 === "시스템"
                ? 데이터.내용
                : `${데이터.닉네임} (${데이터.시간}): ${데이터.내용}`;
            메시지영역.appendChild(div);
            메시지영역.scrollTop = 메시지영역.scrollHeight;
        };

        function 전송() {
            const input = document.getElementById("msg");
            if (input.value.trim()) {
                ws.send(input.value);
                input.value = "";
            }
        }
    </script>
</body>
</html>
```

## 실행

```bash
pip install fastapi uvicorn websockets
uvicorn server:app --reload
# → http://localhost:8000 (여러 탭에서 열어 테스트)
```'''),
]


# ═══════════════════════════════════════════════════════════════
# 합치기 + 저장
# ═══════════════════════════════════════════════════════════════

def build_project_data(output_path):
    all_data = FULLSTACK

    logger.info(f"  프로젝트 코딩: {len(all_data)}건")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"\n총 {len(all_data)}건 → {output_path}")
    return len(all_data)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/project_coding.jsonl")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" 화랑 AI 프로젝트 코딩 학습 데이터")
    logger.info("=" * 60)
    build_project_data(args.output)
