"""화랑 AI 인증/보안 패턴 학습 데이터

OAuth2, JWT, RBAC, 2FA, API 키, CORS, CSP 등.

사용법:
    python scripts/data/build_auth_security.py \
        --output data/sft/auth_security.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
보안 전문가 수준의 어시스턴트입니다.
설명은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("NextAuth.js 인증 구현 알려줘 최신으로",
'''NextAuth.js v5 (Auth.js) 최신 구현입니다.

```typescript
// ═══ 1. Auth.js 설정 (v5) ═══
// auth.ts
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import GitHub from "next-auth/providers/github";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "@/lib/db";
import bcrypt from "bcryptjs";
import { z } from "zod";

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: PrismaAdapter(prisma),
  session: { strategy: "jwt" },

  providers: [
    // 소셜 로그인
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
    GitHub({
      clientId: process.env.GITHUB_CLIENT_ID!,
      clientSecret: process.env.GITHUB_CLIENT_SECRET!,
    }),

    // 이메일/비밀번호
    Credentials({
      name: "credentials",
      credentials: {
        email: { label: "이메일", type: "email" },
        password: { label: "비밀번호", type: "password" },
      },
      async authorize(credentials) {
        const parsed = loginSchema.safeParse(credentials);
        if (!parsed.success) return null;

        const user = await prisma.user.findUnique({
          where: { email: parsed.data.email },
        });

        if (!user || !user.hashedPassword) return null;

        const isValid = await bcrypt.compare(
          parsed.data.password,
          user.hashedPassword,
        );

        if (!isValid) return null;

        return {
          id: user.id,
          name: user.name,
          email: user.email,
          role: user.role,
        };
      },
    }),
  ],

  callbacks: {
    // JWT에 역할 추가
    async jwt({ token, user }) {
      if (user) {
        token.role = (user as any).role;
        token.id = user.id;
      }
      return token;
    },

    // 세션에 역할 추가
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.id as string;
        session.user.role = token.role as string;
      }
      return session;
    },

    // 페이지 접근 제어
    authorized({ auth, request: { nextUrl } }) {
      const isLoggedIn = !!auth?.user;
      const isAdmin = auth?.user?.role === "admin";
      const isAdminPage = nextUrl.pathname.startsWith("/admin");

      if (isAdminPage && !isAdmin) return false;
      if (nextUrl.pathname.startsWith("/dashboard") && !isLoggedIn) {
        return Response.redirect(new URL("/login", nextUrl));
      }
      return true;
    },
  },

  pages: {
    signIn: "/login",
    error: "/login?error=true",
  },
});

// ═══ 2. 미들웨어 (라우트 보호) ═══
// middleware.ts
export { auth as middleware } from "@/auth";

export const config = {
  matcher: ["/dashboard/:path*", "/admin/:path*", "/api/protected/:path*"],
};

// ═══ 3. 서버 컴포넌트에서 사용 ═══
// app/dashboard/page.tsx
import { auth } from "@/auth";
import { redirect } from "next/navigation";

export default async function DashboardPage() {
  const session = await auth();
  if (!session) redirect("/login");

  return (
    <div>
      <h1>안녕하세요, {session.user.name}님</h1>
      <p>역할: {session.user.role}</p>
    </div>
  );
}

// ═══ 4. API 라우트 보호 ═══
// app/api/protected/route.ts
import { auth } from "@/auth";

export async function GET() {
  const session = await auth();
  if (!session) {
    return Response.json({ error: "로그인 필요" }, { status: 401 });
  }
  if (session.user.role !== "admin") {
    return Response.json({ error: "권한 없음" }, { status: 403 });
  }
  return Response.json({ data: "관리자 데이터" });
}

// ═══ 5. 클라이언트에서 사용 ═══
"use client";
import { useSession, signIn, signOut } from "next-auth/react";

function AuthButton() {
  const { data: session, status } = useSession();

  if (status === "loading") return <Skeleton />;

  if (!session) {
    return (
      <div className="flex gap-2">
        <button onClick={() => signIn("google")} className="btn">
          Google 로그인
        </button>
        <button onClick={() => signIn("credentials")} className="btn">
          이메일 로그인
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <span>{session.user.name}</span>
      <button onClick={() => signOut()} className="btn-outline">
        로그아웃
      </button>
    </div>
  );
}
```

인증 체크리스트:
- [ ] 비밀번호 bcrypt 해싱 (salt rounds: 12)
- [ ] JWT에 민감 정보 넣지 않기 (비밀번호 X)
- [ ] CSRF 보호 (NextAuth 자동)
- [ ] Rate Limiting (로그인 시도 제한)
- [ ] 세션 만료 설정 (30일)
- [ ] Secure, HttpOnly, SameSite 쿠키 플래그'''),

    m("JWT 토큰 인증 직접 구현 알려줘 FastAPI로",
'''FastAPI에서 JWT 인증을 직접 구현합니다.

```python
# ═══ JWT 인증 시스템 ═══
from datetime import datetime, timedelta
from typing import Annotated
import jwt
import bcrypt
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

app = FastAPI()

# 설정
SECRET_KEY = "super-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = timedelta(minutes=30)
REFRESH_TOKEN_EXPIRE = timedelta(days=7)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ═══ 모델 ═══
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

# ═══ 비밀번호 해싱 ═══
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

# ═══ 토큰 생성/검증 ═══
def create_token(data: dict, expires_delta: timedelta) -> str:
    payload = {
        **data,
        "exp": datetime.utcnow() + expires_delta,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_tokens(user_id: str, role: str) -> TokenResponse:
    access = create_token(
        {"sub": user_id, "role": role, "type": "access"},
        ACCESS_TOKEN_EXPIRE,
    )
    refresh = create_token(
        {"sub": user_id, "type": "refresh"},
        REFRESH_TOKEN_EXPIRE,
    )
    return TokenResponse(access_token=access, refresh_token=refresh)

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")

# ═══ 의존성 (현재 사용자) ═══
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> User:
    payload = verify_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="올바른 액세스 토큰이 아닙니다")

    user = await db.user.find_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")
    return user

# 역할 기반 접근 제어 (RBAC)
def require_role(*roles: str):
    async def role_checker(
        user: Annotated[User, Depends(get_current_user)]
    ) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"권한 부족 (필요: {', '.join(roles)})"
            )
        return user
    return role_checker

# ═══ 엔드포인트 ═══

# 회원가입
@app.post("/auth/register")
async def register(data: UserCreate):
    existing = await db.user.find_by_email(data.email)
    if existing:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다")

    hashed = hash_password(data.password)
    user = await db.user.create(name=data.name, email=data.email, password=hashed)
    return create_tokens(user.id, user.role)

# 로그인
@app.post("/auth/login")
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = await db.user.find_by_email(form.username)
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")
    return create_tokens(user.id, user.role)

# 토큰 갱신
@app.post("/auth/refresh")
async def refresh_token(refresh_token: str):
    payload = verify_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="리프레시 토큰이 아닙니다")
    user = await db.user.find_by_id(payload["sub"])
    return create_tokens(user.id, user.role)

# 보호된 엔드포인트
@app.get("/users/me")
async def get_me(user: Annotated[User, Depends(get_current_user)]):
    return user

# 관리자 전용
@app.get("/admin/users")
async def list_users(
    admin: Annotated[User, Depends(require_role("admin"))]
):
    return await db.user.find_all()
```

JWT 보안 규칙:
- Access Token: 짧게 (15-30분)
- Refresh Token: 길게 (7-30일)
- 비밀번호: bcrypt + salt (12 rounds)
- Secret Key: 환경변수, 32자 이상
- HTTPS 필수 (토큰 탈취 방지)
- Refresh Token Rotation (사용 시 새로 발급)'''),

    m("API 보안 베스트 프랙티스 알려줘 Rate Limiting CORS 포함",
'''API 보안 실무 베스트 프랙티스입니다.

```python
# ═══ FastAPI 보안 설정 ═══
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
import secrets

app = FastAPI()

# ═══ 1. CORS 설정 ═══
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hwarang.ai",
        "https://admin.hwarang.ai",
        "http://localhost:3000",  # 개발 환경
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=3600,  # preflight 캐시 1시간
)

# ═══ 2. Rate Limiting ═══
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

@app.post("/auth/login")
@limiter.limit("5/minute")  # 분당 5회
async def login(request: Request):
    ...

@app.post("/api/chat")
@limiter.limit("30/minute")  # 분당 30회
async def chat(request: Request):
    ...

# ═══ 3. API 키 인증 ═══
from fastapi import Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    key = await db.api_key.find_by_key(hash_key(api_key))
    if not key or key.revoked:
        raise HTTPException(status_code=401, detail="유효하지 않은 API 키")
    if key.expires_at and key.expires_at < datetime.now():
        raise HTTPException(status_code=401, detail="만료된 API 키")

    # 사용량 기록
    await db.api_key.increment_usage(key.id)
    return key

@app.get("/api/v1/data")
async def get_data(key: ApiKey = Depends(verify_api_key)):
    ...

# API 키 생성
def generate_api_key() -> str:
    return f"hwr_{secrets.token_urlsafe(32)}"

# ═══ 4. 입력 검증 (SQL Injection 방지) ═══
# Pydantic + ORM 사용 시 자동 방지

from pydantic import BaseModel, constr

class SearchQuery(BaseModel):
    q: constr(max_length=200, pattern=r"^[a-zA-Z0-9가-힣\\s]+$")  # 특수문자 차단
    page: int = 1
    limit: int = 20

# ═══ 5. 보안 헤더 ═══
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# ═══ 6. 요청 로깅 (감사 추적) ═══
@app.middleware("http")
async def audit_log(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    if request.url.path.startswith("/api/"):
        logger.info(
            f"{request.method} {request.url.path} "
            f"status={response.status_code} "
            f"duration={duration:.3f}s "
            f"ip={request.client.host} "
            f"user_agent={request.headers.get('user-agent', 'unknown')[:100]}"
        )
    return response
```

```typescript
// Next.js 보안 헤더
// next.config.ts
const securityHeaders = [
  { key: "X-DNS-Prefetch-Control", value: "on" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-XSS-Protection", value: "1; mode=block" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

module.exports = {
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};
```

API 보안 체크리스트:
- [ ] HTTPS 필수 (TLS 1.2+)
- [ ] CORS 화이트리스트 (와일드카드 * 금지)
- [ ] Rate Limiting (엔드포인트별)
- [ ] 입력 검증 (Pydantic/Zod)
- [ ] SQL Injection 방지 (ORM 사용)
- [ ] XSS 방지 (출력 이스케이프)
- [ ] 보안 헤더 설정
- [ ] API 키 해싱 저장
- [ ] 감사 로그 기록
- [ ] 에러 메시지에 내부 정보 노출 금지'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/auth_security.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 인증/보안 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  인증/보안: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
