"""화랑 AI 풀 프로젝트 학습 데이터

"프로젝트 만들어줘" → 폴더 구조 + 각 파일 전체 코드 출력.
클로드처럼 여러 파일을 한 번에 작성하는 능력 학습.

카테고리:
  - Next.js 풀스택 앱 (10건)
  - FastAPI 백엔드 (10건)
  - React 컴포넌트 라이브러리 (5건)
  - CLI 도구 (5건)
  - 모바일 앱 (5건)
  - 유틸리티/라이브러리 (5건)
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
프로젝트 요청 시 폴더 구조와 각 파일의 전체 코드를 작성합니다.
실무에서 바로 사용할 수 있는 프로덕션 수준의 코드를 생성합니다.
설명은 한국어로, 코드는 완전한 형태로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 1. Next.js TODO 앱 ═══
    m("Next.js로 TODO 앱 만들어줘 전체 코드로",
'''Next.js TODO 앱을 만들어 드릴게요.

## 폴더 구조

```
todo-app/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── api/
│       └── todos/
│           ├── route.ts          # GET, POST
│           └── [id]/route.ts     # PATCH, DELETE
├── components/
│   ├── todo-list.tsx
│   ├── todo-item.tsx
│   └── add-todo.tsx
├── lib/
│   └── db.ts
├── prisma/
│   └── schema.prisma
├── package.json
└── .env.local
```

## prisma/schema.prisma

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = "file:./dev.db"
}

model Todo {
  id        String   @id @default(cuid())
  title     String
  completed Boolean  @default(false)
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

## lib/db.ts

```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
```

## app/api/todos/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

export async function GET() {
  const todos = await prisma.todo.findMany({
    orderBy: { createdAt: "desc" },
  });
  return NextResponse.json(todos);
}

export async function POST(request: Request) {
  const { title } = await request.json();

  if (!title || title.trim().length === 0) {
    return NextResponse.json({ error: "제목을 입력하세요" }, { status: 400 });
  }

  const todo = await prisma.todo.create({
    data: { title: title.trim() },
  });

  return NextResponse.json(todo, { status: 201 });
}
```

## app/api/todos/[id]/route.ts

```typescript
import { prisma } from "@/lib/db";
import { NextResponse } from "next/server";

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await request.json();

  const todo = await prisma.todo.update({
    where: { id },
    data: body,
  });

  return NextResponse.json(todo);
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  await prisma.todo.delete({ where: { id } });
  return new Response(null, { status: 204 });
}
```

## components/add-todo.tsx

```tsx
"use client";

import { useState } from "react";

interface AddTodoProps {
  onAdd: (title: string) => void;
}

export function AddTodo({ onAdd }: AddTodoProps) {
  const [title, setTitle] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    onAdd(title.trim());
    setTitle("");
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="할 일을 입력하세요..."
        className="flex-1 px-4 py-3 border border-gray-200 rounded-xl outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition"
      />
      <button
        type="submit"
        disabled={!title.trim()}
        className="px-6 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
      >
        추가
      </button>
    </form>
  );
}
```

## components/todo-item.tsx

```tsx
"use client";

interface Todo {
  id: string;
  title: string;
  completed: boolean;
}

interface TodoItemProps {
  todo: Todo;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
}

export function TodoItem({ todo, onToggle, onDelete }: TodoItemProps) {
  return (
    <div className="flex items-center gap-3 p-4 bg-white border border-gray-100 rounded-xl group hover:shadow-sm transition">
      <button
        onClick={() => onToggle(todo.id)}
        className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition ${
          todo.completed
            ? "bg-green-500 border-green-500 text-white"
            : "border-gray-300 hover:border-blue-400"
        }`}
      >
        {todo.completed && "✓"}
      </button>

      <span
        className={`flex-1 text-sm ${
          todo.completed ? "line-through text-gray-400" : "text-gray-700"
        }`}
      >
        {todo.title}
      </span>

      <button
        onClick={() => onDelete(todo.id)}
        className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 transition"
      >
        ✕
      </button>
    </div>
  );
}
```

## components/todo-list.tsx

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { AddTodo } from "./add-todo";
import { TodoItem } from "./todo-item";

interface Todo {
  id: string;
  title: string;
  completed: boolean;
}

export function TodoList() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [filter, setFilter] = useState<"all" | "active" | "completed">("all");

  useEffect(() => {
    fetch("/api/todos")
      .then((r) => r.json())
      .then(setTodos);
  }, []);

  const addTodo = useCallback(async (title: string) => {
    const res = await fetch("/api/todos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    const todo = await res.json();
    setTodos((prev) => [todo, ...prev]);
  }, []);

  const toggleTodo = useCallback(async (id: string) => {
    const todo = todos.find((t) => t.id === id);
    if (!todo) return;

    const res = await fetch(`/api/todos/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed: !todo.completed }),
    });
    const updated = await res.json();
    setTodos((prev) => prev.map((t) => (t.id === id ? updated : t)));
  }, [todos]);

  const deleteTodo = useCallback(async (id: string) => {
    await fetch(`/api/todos/${id}`, { method: "DELETE" });
    setTodos((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const filtered = todos.filter((t) => {
    if (filter === "active") return !t.completed;
    if (filter === "completed") return t.completed;
    return true;
  });

  const activeCount = todos.filter((t) => !t.completed).length;

  return (
    <div className="space-y-6">
      <AddTodo onAdd={addTodo} />

      {/* 필터 */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-500">{activeCount}개 남음</span>
        <div className="flex gap-1">
          {(["all", "active", "completed"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-lg transition ${
                filter === f
                  ? "bg-blue-100 text-blue-700 font-medium"
                  : "text-gray-500 hover:bg-gray-100"
              }`}
            >
              {f === "all" ? "전체" : f === "active" ? "진행중" : "완료"}
            </button>
          ))}
        </div>
      </div>

      {/* 목록 */}
      <div className="space-y-2">
        {filtered.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            {filter === "all" ? "할 일을 추가해보세요!" : "항목이 없습니다"}
          </div>
        ) : (
          filtered.map((todo) => (
            <TodoItem
              key={todo.id}
              todo={todo}
              onToggle={toggleTodo}
              onDelete={deleteTodo}
            />
          ))
        )}
      </div>
    </div>
  );
}
```

## app/page.tsx

```tsx
import { TodoList } from "@/components/todo-list";

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-50 py-12">
      <div className="max-w-lg mx-auto px-4">
        <h1 className="text-2xl font-bold text-center mb-8">
          📝 할 일 목록
        </h1>
        <TodoList />
      </div>
    </main>
  );
}
```

## app/layout.tsx

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TODO 앱",
  description: "Next.js TODO 앱",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
```

## package.json

```json
{
  "name": "todo-app",
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "db:push": "prisma db push",
    "db:studio": "prisma studio"
  },
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@prisma/client": "^6.0.0"
  },
  "devDependencies": {
    "prisma": "^6.0.0",
    "typescript": "^5.0.0",
    "@types/react": "^19.0.0",
    "tailwindcss": "^4.0.0"
  }
}
```

## 실행 방법

```bash
pnpm install
pnpm prisma db push   # DB 생성
pnpm dev              # http://localhost:3000
```

완전한 CRUD TODO 앱입니다. SQLite + Prisma + Next.js App Router + Tailwind!'''),

    # ═══ 2. FastAPI REST API ═══
    m("FastAPI로 사용자 관리 REST API 만들어줘 전체 코드로",
'''FastAPI 사용자 관리 API를 만들어 드릴게요.

## 폴더 구조

```
user-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 앱
│   ├── config.py            # 설정
│   ├── database.py          # DB 연결
│   ├── models.py            # SQLAlchemy 모델
│   ├── schemas.py           # Pydantic 스키마
│   ├── routers/
│   │   ├── __init__.py
│   │   └── users.py         # 사용자 라우터
│   └── services/
│       ├── __init__.py
│       └── user_service.py  # 비즈니스 로직
├── requirements.txt
├── .env
└── README.md
```

## app/config.py

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "사용자 관리 API"
    database_url: str = "sqlite:///./users.db"
    secret_key: str = "change-me-in-production"
    debug: bool = True

    model_config = {"env_file": ".env"}


settings = Settings()
```

## app/database.py

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite용
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

## app/models.py

```python
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

## app/schemas.py

```python
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50, examples=["홍길동"])
    email: EmailStr = Field(examples=["hong@example.com"])
    password: str = Field(min_length=8, examples=["securepass123"])


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=50)
    email: EmailStr | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    data: list[UserResponse]
    total: int
    page: int
    limit: int
```

## app/services/user_service.py

```python
import hashlib
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import User
from app.schemas import UserCreate, UserUpdate


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_users(db: Session, page: int = 1, limit: int = 20, search: str | None = None):
    query = db.query(User)

    if search:
        query = query.filter(
            (User.name.ilike(f"%{search}%")) | (User.email.ilike(f"%{search}%"))
        )

    total = query.count()
    users = query.offset((page - 1) * limit).limit(limit).all()

    return users, total


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, data: UserCreate) -> User:
    user = User(
        name=data.name,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, data: UserUpdate) -> User:
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User):
    db.delete(user)
    db.commit()
```

## app/routers/users.py

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import UserCreate, UserUpdate, UserResponse, UserListResponse
from app.services import user_service

router = APIRouter(prefix="/api/users", tags=["사용자"])


@router.get("", response_model=UserListResponse)
def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """사용자 목록 조회"""
    users, total = user_service.get_users(db, page, limit, search)
    return UserListResponse(
        data=users, total=total, page=page, limit=limit
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    """사용자 상세 조회"""
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return user


@router.post("", response_model=UserResponse, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    """사용자 생성"""
    existing = user_service.get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다")
    return user_service.create_user(db, data)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db)):
    """사용자 수정"""
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return user_service.update_user(db, user, data)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """사용자 삭제"""
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    user_service.delete_user(db, user)
```

## app/main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.routers import users

# 테이블 생성
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/docs",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터
app.include_router(users.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
```

## requirements.txt

```
fastapi==0.115.0
uvicorn==0.30.0
sqlalchemy==2.0.35
pydantic[email]==2.10.0
pydantic-settings==2.5.0
```

## 실행 방법

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# API 문서: http://localhost:8000/docs
# 헬스체크: http://localhost:8000/health
```

완전한 FastAPI REST API입니다. SQLAlchemy + Pydantic + 서비스 레이어 구조!'''),

    # ═══ 3. Python CLI 도구 ═══
    m("파이썬으로 파일 정리 CLI 도구 만들어줘",
'''파일 자동 정리 CLI 도구를 만들어 드릴게요.

## 폴더 구조

```
file-organizer/
├── organizer/
│   ├── __init__.py
│   ├── cli.py          # CLI 인터페이스
│   ├── organizer.py    # 핵심 로직
│   └── config.py       # 파일 분류 규칙
├── setup.py
└── README.md
```

## organizer/config.py

```python
"""파일 분류 규칙."""

# 확장자 → 폴더 매핑
CATEGORIES = {
    "이미지": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"],
    "동영상": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"],
    "음악": [".mp3", ".wav", ".flac", ".aac", ".ogg"],
    "문서": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"],
    "스프레드시트": [".xls", ".xlsx", ".csv"],
    "프레젠테이션": [".ppt", ".pptx"],
    "압축": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "코드": [".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rs", ".html", ".css"],
    "데이터": [".json", ".xml", ".yaml", ".yml", ".sql", ".db"],
    "설치파일": [".exe", ".msi", ".dmg", ".deb", ".rpm"],
    "폰트": [".ttf", ".otf", ".woff", ".woff2"],
}


def get_category(extension: str) -> str:
    """확장자로 카테고리 찾기."""
    ext = extension.lower()
    for category, extensions in CATEGORIES.items():
        if ext in extensions:
            return category
    return "기타"
```

## organizer/organizer.py

```python
"""파일 정리 핵심 로직."""

import os
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from .config import get_category


def scan_directory(path: str) -> dict[str, list[Path]]:
    """디렉토리 스캔 → 카테고리별 분류."""
    categories = defaultdict(list)
    target = Path(path)

    for file in target.iterdir():
        if file.is_file() and not file.name.startswith("."):
            category = get_category(file.suffix)
            categories[category].append(file)

    return dict(categories)


def organize(
    source: str,
    dry_run: bool = False,
    by_date: bool = False,
) -> dict[str, int]:
    """파일 정리 실행."""
    source_path = Path(source)

    if not source_path.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {source}")

    categories = scan_directory(source)
    results = {}

    for category, files in categories.items():
        # 대상 폴더
        if by_date:
            # 날짜별 하위 폴더
            for file in files:
                mtime = datetime.fromtimestamp(file.stat().st_mtime)
                dest_dir = source_path / category / mtime.strftime("%Y-%m")
                _move_file(file, dest_dir, dry_run)
        else:
            dest_dir = source_path / category
            for file in files:
                _move_file(file, dest_dir, dry_run)

        results[category] = len(files)

    return results


def _move_file(file: Path, dest_dir: Path, dry_run: bool):
    """파일을 대상 폴더로 이동."""
    if dry_run:
        print(f"  [시뮬레이션] {file.name} → {dest_dir}/")
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.name

    # 같은 이름 파일이 있으면 번호 추가
    if dest.exists():
        stem = file.stem
        suffix = file.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(str(file), str(dest))


def get_stats(path: str) -> dict:
    """디렉토리 통계."""
    categories = scan_directory(path)
    total_size = 0
    total_files = 0

    stats = {}
    for category, files in categories.items():
        size = sum(f.stat().st_size for f in files)
        stats[category] = {
            "count": len(files),
            "size_mb": round(size / 1024 / 1024, 1),
        }
        total_size += size
        total_files += len(files)

    return {
        "categories": stats,
        "total_files": total_files,
        "total_size_mb": round(total_size / 1024 / 1024, 1),
    }
```

## organizer/cli.py

```python
"""CLI 인터페이스."""

import argparse
import sys

from .organizer import organize, get_stats, scan_directory


def main():
    parser = argparse.ArgumentParser(
        description="파일 자동 정리 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  file-organizer ~/Downloads              # Downloads 폴더 정리
  file-organizer ~/Downloads --dry-run    # 시뮬레이션 (실제 이동 안 함)
  file-organizer ~/Downloads --by-date    # 날짜별 하위 폴더
  file-organizer ~/Downloads --stats      # 통계만 보기
        """,
    )

    parser.add_argument("path", help="정리할 폴더 경로")
    parser.add_argument("--dry-run", action="store_true", help="시뮬레이션 모드 (실제 이동 안 함)")
    parser.add_argument("--by-date", action="store_true", help="날짜별 하위 폴더 생성")
    parser.add_argument("--stats", action="store_true", help="통계만 표시")

    args = parser.parse_args()

    try:
        if args.stats:
            stats = get_stats(args.path)
            print(f"\\n📊 {args.path} 통계\\n")
            print(f"  전체: {stats['total_files']}개 파일, {stats['total_size_mb']}MB\\n")
            for cat, info in sorted(stats["categories"].items(), key=lambda x: -x[1]["count"]):
                print(f"  {cat:12s}: {info['count']:4d}개  ({info['size_mb']}MB)")
            return

        if args.dry_run:
            print("\\n🔍 시뮬레이션 모드 (실제 이동 없음)\\n")

        results = organize(args.path, dry_run=args.dry_run, by_date=args.by_date)

        print(f"\\n✅ 정리 완료!\\n")
        for category, count in sorted(results.items(), key=lambda x: -x[1]):
            print(f"  📁 {category}: {count}개")
        print(f"\\n  총 {sum(results.values())}개 파일 정리됨")

    except FileNotFoundError as e:
        print(f"❌ 에러: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 예상치 못한 에러: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

## setup.py

```python
from setuptools import setup, find_packages

setup(
    name="file-organizer",
    version="1.0.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "file-organizer=organizer.cli:main",
        ],
    },
    python_requires=">=3.10",
)
```

## 설치 & 사용

```bash
pip install -e .

# 사용
file-organizer ~/Downloads              # 정리 실행
file-organizer ~/Downloads --dry-run    # 미리보기
file-organizer ~/Downloads --stats      # 통계
file-organizer ~/Downloads --by-date    # 월별 정리
```

완전한 CLI 도구입니다. 설치하면 `file-organizer` 명령어로 바로 사용 가능!'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/full_projects.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"풀 프로젝트: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
