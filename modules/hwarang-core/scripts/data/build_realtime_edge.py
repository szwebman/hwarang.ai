"""화랑 AI 실시간/Edge/최신 기술 학습 데이터

WebSocket, SSE, WebRTC, Edge Functions, tRPC, GraphQL 등.

사용법:
    python scripts/data/build_realtime_edge.py \
        --output data/sft/realtime_edge.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("WebSocket 실시간 채팅 구현 알려줘",
'''WebSocket으로 실시간 양방향 통신을 구현합니다.

```python
# ═══ FastAPI WebSocket 서버 ═══
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dataclasses import dataclass, field
import json, asyncio

app = FastAPI()

@dataclass
class Room:
    id: str
    connections: dict[str, WebSocket] = field(default_factory=dict)

    async def broadcast(self, message: dict, exclude: str | None = None):
        for user_id, ws in self.connections.items():
            if user_id != exclude:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass

    async def send_to(self, user_id: str, message: dict):
        ws = self.connections.get(user_id)
        if ws:
            await ws.send_json(message)

class ChatManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}

    def get_room(self, room_id: str) -> Room:
        if room_id not in self.rooms:
            self.rooms[room_id] = Room(id=room_id)
        return self.rooms[room_id]

    async def connect(self, room_id: str, user_id: str, ws: WebSocket):
        await ws.accept()
        room = self.get_room(room_id)
        room.connections[user_id] = ws
        await room.broadcast({
            "type": "user_joined",
            "user_id": user_id,
            "online_count": len(room.connections),
        })

    async def disconnect(self, room_id: str, user_id: str):
        room = self.get_room(room_id)
        room.connections.pop(user_id, None)
        await room.broadcast({
            "type": "user_left",
            "user_id": user_id,
            "online_count": len(room.connections),
        })
        if not room.connections:
            del self.rooms[room_id]

manager = ChatManager()

@app.websocket("/ws/chat/{room_id}")
async def websocket_chat(ws: WebSocket, room_id: str, user_id: str):
    await manager.connect(room_id, user_id, ws)
    try:
        while True:
            data = await ws.receive_json()
            if data["type"] == "message":
                # DB 저장
                msg = await save_message(room_id, user_id, data["content"])
                # 전체 브로드캐스트
                await manager.get_room(room_id).broadcast({
                    "type": "message",
                    "id": msg.id,
                    "user_id": user_id,
                    "content": data["content"],
                    "created_at": msg.created_at.isoformat(),
                })
            elif data["type"] == "typing":
                await manager.get_room(room_id).broadcast(
                    {"type": "typing", "user_id": user_id},
                    exclude=user_id,
                )
    except WebSocketDisconnect:
        await manager.disconnect(room_id, user_id)
```

```typescript
// ═══ React 클라이언트 ═══
"use client";
import { useEffect, useRef, useState, useCallback } from "react";

function useWebSocket(url: string) {
  const ws = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const reconnectTimer = useRef<NodeJS.Timeout>();

  const connect = useCallback(() => {
    ws.current = new WebSocket(url);

    ws.current.onopen = () => {
      setConnected(true);
      console.log("WebSocket 연결됨");
    };

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case "message":
          setMessages((prev) => [...prev, data]);
          break;
        case "typing":
          // 타이핑 표시
          break;
      }
    };

    ws.current.onclose = () => {
      setConnected(false);
      // 자동 재연결 (지수 백오프)
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.current.onerror = () => ws.current?.close();
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      ws.current?.close();
    };
  }, [connect]);

  const send = useCallback((data: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(data));
    }
  }, []);

  return { connected, messages, send };
}

// 채팅 컴포넌트
function ChatRoom({ roomId }: { roomId: string }) {
  const { connected, messages, send } = useWebSocket(
    `wss://api.hwarang.ai/ws/chat/${roomId}?user_id=${userId}`
  );
  const [input, setInput] = useState("");

  const handleSend = () => {
    if (!input.trim()) return;
    send({ type: "message", content: input });
    setInput("");
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </div>
      <div className="border-t p-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="메시지 입력..."
          className="flex-1 rounded-lg border px-3 py-2"
        />
        <button onClick={handleSend} disabled={!connected}>전송</button>
      </div>
    </div>
  );
}
```

WebSocket vs SSE vs 폴링:
| 방식 | 방향 | 사용 |
|------|------|------|
| WebSocket | 양방향 | 채팅, 게임, 협업 |
| SSE | 서버→클라이언트 | AI 스트리밍, 알림 |
| 폴링 | 클라이언트→서버 | 대시보드 (간단) |'''),

    m("SSE 서버 센트 이벤트 구현 알려줘 AI 스트리밍용",
'''SSE(Server-Sent Events)로 AI 응답을 실시간 스트리밍합니다.

```python
# ═══ FastAPI SSE ═══
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio, json

@app.post("/api/chat")
async def chat(request: ChatRequest):
    async def event_stream():
        # AI 모델에서 토큰 단위 스트리밍
        async for token in generate_response(request.messages):
            data = json.dumps({"token": token}, ensure_ascii=False)
            yield f"data: {data}\\n\\n"

        # 완료 신호
        yield f"data: {json.dumps({'done': True})}\\n\\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 버퍼링 비활성화
        },
    )
```

```typescript
// ═══ Next.js SSE API Route ═══
// app/api/chat/route.ts
export async function POST(request: Request) {
  const { messages } = await request.json();

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      try {
        // OpenAI 스트리밍
        const response = await openai.chat.completions.create({
          model: "gpt-4o",
          messages,
          stream: true,
        });

        for await (const chunk of response) {
          const token = chunk.choices[0]?.delta?.content || "";
          if (token) {
            controller.enqueue(
              encoder.encode(`data: ${JSON.stringify({ token })}\\n\\n`)
            );
          }
        }

        controller.enqueue(encoder.encode(`data: [DONE]\\n\\n`));
      } catch (error) {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ error: "서버 오류" })}\\n\\n`)
        );
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}

// ═══ 클라이언트 SSE 소비 ═══
function useStreamChat() {
  const [streaming, setStreaming] = useState(false);
  const [response, setResponse] = useState("");

  const sendMessage = async (messages: Message[]) => {
    setStreaming(true);
    setResponse("");

    const res = await fetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({ messages }),
    });

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split("\\n").filter((l) => l.startsWith("data: "));

      for (const line of lines) {
        const data = line.slice(6);  // "data: " 제거
        if (data === "[DONE]") break;

        try {
          const { token } = JSON.parse(data);
          setResponse((prev) => prev + token);
        } catch {}
      }
    }

    setStreaming(false);
  };

  return { sendMessage, response, streaming };
}
```

SSE 핵심:
- `text/event-stream` Content-Type
- `data: {...}\n\n` 형식 (줄바꿈 2개 필수)
- Nginx: `X-Accel-Buffering: no` 필수
- 자동 재연결 (브라우저 기본 지원)'''),

    m("tRPC 사용법 알려줘 Next.js에서",
'''tRPC는 타입 안전한 API를 코드 생성 없이 만듭니다.

```typescript
// ═══ 1. 서버 설정 ═══
// server/trpc.ts
import { initTRPC, TRPCError } from "@trpc/server";
import { z } from "zod";
import superjson from "superjson";

const t = initTRPC.context<{ user: User | null }>().create({
  transformer: superjson,
});

export const router = t.router;
export const publicProcedure = t.procedure;

// 인증 미들웨어
const isAuthed = t.middleware(({ ctx, next }) => {
  if (!ctx.user) {
    throw new TRPCError({ code: "UNAUTHORIZED", message: "로그인 필요" });
  }
  return next({ ctx: { user: ctx.user } });
});

export const protectedProcedure = t.procedure.use(isAuthed);

// ═══ 2. 라우터 정의 ═══
// server/routers/user.ts
export const userRouter = router({
  // 목록 조회
  list: publicProcedure
    .input(z.object({
      page: z.number().default(1),
      limit: z.number().max(100).default(20),
      search: z.string().optional(),
    }))
    .query(async ({ input }) => {
      const { page, limit, search } = input;
      const [users, total] = await Promise.all([
        db.user.findMany({
          where: search ? { name: { contains: search } } : undefined,
          skip: (page - 1) * limit,
          take: limit,
        }),
        db.user.count(),
      ]);
      return { users, total };
    }),

  // 단일 조회
  getById: publicProcedure
    .input(z.string())
    .query(async ({ input: id }) => {
      const user = await db.user.findUnique({ where: { id } });
      if (!user) throw new TRPCError({ code: "NOT_FOUND" });
      return user;
    }),

  // 생성 (인증 필요)
  create: protectedProcedure
    .input(z.object({
      name: z.string().min(2),
      email: z.string().email(),
    }))
    .mutation(async ({ input, ctx }) => {
      return db.user.create({ data: { ...input, createdBy: ctx.user.id } });
    }),

  // 수정
  update: protectedProcedure
    .input(z.object({
      id: z.string(),
      name: z.string().min(2).optional(),
      email: z.string().email().optional(),
    }))
    .mutation(async ({ input: { id, ...data } }) => {
      return db.user.update({ where: { id }, data });
    }),

  // 삭제
  delete: protectedProcedure
    .input(z.string())
    .mutation(async ({ input: id }) => {
      await db.user.delete({ where: { id } });
    }),
});

// 메인 라우터
// server/routers/_app.ts
export const appRouter = router({
  user: userRouter,
  post: postRouter,
  chat: chatRouter,
});

export type AppRouter = typeof appRouter;

// ═══ 3. 클라이언트 설정 ═══
// lib/trpc.ts
import { createTRPCReact } from "@trpc/react-query";
import type { AppRouter } from "@/server/routers/_app";

export const trpc = createTRPCReact<AppRouter>();

// ═══ 4. 컴포넌트에서 사용 ═══
function UserList() {
  // 완전한 타입 추론! (서버 코드와 타입 공유)
  const { data, isLoading } = trpc.user.list.useQuery({
    page: 1,
    limit: 20,
    search: "홍",
  });

  const createMutation = trpc.user.create.useMutation({
    onSuccess: () => {
      utils.user.list.invalidate();  // 캐시 무효화
    },
  });

  const utils = trpc.useUtils();

  if (isLoading) return <Skeleton />;

  return (
    <div>
      {data?.users.map((user) => (
        <div key={user.id}>{user.name}</div>  // 타입 자동 완성!
      ))}
      <button onClick={() => createMutation.mutate({ name: "새 사용자", email: "new@test.com" })}>
        {createMutation.isPending ? "생성 중..." : "사용자 추가"}
      </button>
    </div>
  );
}
```

tRPC 장점:
- **타입 공유**: 서버 코드 변경 → 클라이언트 즉시 타입 에러
- **코드 생성 없음**: GraphQL 스키마, OpenAPI 불필요
- **Zod 통합**: 입력 검증 + 타입 추론 동시
- **React Query 내장**: 캐싱, 로딩, 에러 처리 자동'''),

    m("GraphQL 실무 사용법 알려줘",
'''GraphQL로 유연한 API를 구현합니다.

```typescript
// ═══ 1. 스키마 정의 ═══
// schema.graphql
type Query {
  user(id: ID!): User
  users(page: Int = 1, limit: Int = 20, search: String): UserConnection!
  post(id: ID!): Post
}

type Mutation {
  createUser(input: CreateUserInput!): User!
  updateUser(id: ID!, input: UpdateUserInput!): User!
  deleteUser(id: ID!): Boolean!
}

type Subscription {
  messageAdded(roomId: ID!): Message!
  userOnline: User!
}

type User {
  id: ID!
  name: String!
  email: String!
  role: Role!
  posts(limit: Int = 10): [Post!]!
  postCount: Int!
  createdAt: DateTime!
}

type Post {
  id: ID!
  title: String!
  content: String!
  author: User!
  comments: [Comment!]!
  tags: [String!]!
  viewCount: Int!
}

type UserConnection {
  edges: [User!]!
  totalCount: Int!
  pageInfo: PageInfo!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
}

input CreateUserInput {
  name: String!
  email: String!
  role: Role = USER
}

enum Role {
  USER
  ADMIN
  EDITOR
}

// ═══ 2. 리졸버 ═══
const resolvers = {
  Query: {
    user: async (_, { id }, ctx) => {
      return ctx.db.user.findUnique({ where: { id } });
    },
    users: async (_, { page, limit, search }, ctx) => {
      const where = search
        ? { OR: [{ name: { contains: search } }, { email: { contains: search } }] }
        : {};
      const [edges, totalCount] = await Promise.all([
        ctx.db.user.findMany({ where, skip: (page - 1) * limit, take: limit }),
        ctx.db.user.count({ where }),
      ]);
      return {
        edges,
        totalCount,
        pageInfo: {
          hasNextPage: page * limit < totalCount,
          hasPreviousPage: page > 1,
        },
      };
    },
  },

  // 필드 리졸버 (N+1 방지)
  User: {
    posts: async (parent, { limit }, ctx) => {
      return ctx.loaders.postsByUser.load(parent.id);  // DataLoader
    },
    postCount: async (parent, _, ctx) => {
      return ctx.db.post.count({ where: { authorId: parent.id } });
    },
  },

  Mutation: {
    createUser: async (_, { input }, ctx) => {
      if (!ctx.user || ctx.user.role !== "ADMIN") {
        throw new AuthenticationError("관리자 권한 필요");
      }
      return ctx.db.user.create({ data: input });
    },
  },
};

// ═══ 3. DataLoader (N+1 해결) ═══
import DataLoader from "dataloader";

function createLoaders(db: PrismaClient) {
  return {
    postsByUser: new DataLoader(async (userIds: string[]) => {
      const posts = await db.post.findMany({
        where: { authorId: { in: userIds } },
      });
      // userIds 순서에 맞게 그룹핑
      return userIds.map((id) => posts.filter((p) => p.authorId === id));
    }),
  };
}
```

```typescript
// ═══ 클라이언트 (urql) ═══
import { useQuery, useMutation } from "urql";

const UsersQuery = graphql(`
  query Users($page: Int!, $search: String) {
    users(page: $page, search: $search) {
      edges {
        id
        name
        email
        postCount
      }
      totalCount
    }
  }
`);

function UserList() {
  const [result] = useQuery({
    query: UsersQuery,
    variables: { page: 1 },
  });

  const { data, fetching, error } = result;
  if (fetching) return <Spinner />;
  return data.users.edges.map((u) => <div key={u.id}>{u.name}</div>);
}
```

GraphQL vs REST vs tRPC:
| 항목 | REST | GraphQL | tRPC |
|------|------|---------|------|
| 타입 안전 | ❌ | ⚠️ (codegen) | ✅ (네이티브) |
| 오버페칭 | 있음 | 없음 | 없음 |
| 학습 곡선 | 낮음 | 높음 | 중간 |
| 에코시스템 | 큼 | 큼 | 작음 |
| 적합 | 공개 API | 복잡한 관계 | 풀스택 TS |'''),

    m("Edge Functions 서버리스 엣지 컴퓨팅 알려줘",
'''Edge Functions는 사용자에게 가장 가까운 서버에서 실행됩니다.

```typescript
// ═══ 1. Vercel Edge Functions ═══
// app/api/hello/route.ts
export const runtime = "edge";  // Edge Runtime 사용

export async function GET(request: Request) {
  // 사용자 위치 정보 (자동 제공)
  const country = request.headers.get("x-vercel-ip-country") || "KR";
  const city = request.headers.get("x-vercel-ip-city") || "Seoul";

  return Response.json({
    message: `안녕하세요! (${city}, ${country})`,
    timestamp: Date.now(),
  });
}

// ═══ 2. 미들웨어 (Edge에서 실행) ═══
// middleware.ts
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const url = request.nextUrl;
  const country = request.geo?.country || "KR";

  // 1. 지역별 리다이렉트
  if (country === "JP" && !url.pathname.startsWith("/ja")) {
    return NextResponse.redirect(new URL(`/ja${url.pathname}`, url));
  }

  // 2. A/B 테스트
  const bucket = request.cookies.get("ab-bucket")?.value || (Math.random() < 0.5 ? "A" : "B");
  const response = NextResponse.next();
  response.cookies.set("ab-bucket", bucket, { maxAge: 60 * 60 * 24 * 30 });
  response.headers.set("x-ab-bucket", bucket);

  // 3. Bot 감지
  const ua = request.headers.get("user-agent") || "";
  if (/bot|crawler|spider/i.test(ua)) {
    // SEO 최적화된 응답 또는 차단
  }

  // 4. Rate Limiting (Edge KV 사용)
  const ip = request.ip || "unknown";
  // Redis/KV에서 카운트 확인...

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

// ═══ 3. Cloudflare Workers ═══
// worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // KV Store (글로벌 키-값 저장소)
    const cached = await env.CACHE.get(url.pathname);
    if (cached) {
      return new Response(cached, {
        headers: { "Content-Type": "application/json", "X-Cache": "HIT" },
      });
    }

    // 원본 서버에서 가져오기
    const response = await fetch(`https://api.hwarang.ai${url.pathname}`);
    const data = await response.text();

    // 캐시 저장 (5분)
    await env.CACHE.put(url.pathname, data, { expirationTtl: 300 });

    return new Response(data, {
      headers: { "Content-Type": "application/json", "X-Cache": "MISS" },
    });
  },
};

// ═══ 4. Edge에서 AI 스트리밍 ═══
export const runtime = "edge";

export async function POST(request: Request) {
  const { messages } = await request.json();

  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify({ model: "gpt-4o", messages, stream: true }),
  });

  // 스트림 변환 (OpenAI → SSE)
  const transformStream = new TransformStream({
    transform(chunk, controller) {
      controller.enqueue(chunk);
    },
  });

  return new Response(
    response.body!.pipeThrough(transformStream),
    {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    },
  );
}
```

Edge vs Serverless vs Server:
| 항목 | Edge | Serverless | Server |
|------|------|------------|--------|
| 지연 시간 | 최소 (~10ms) | 보통 (~100ms) | 고정 |
| 콜드 스타트 | 거의 없음 | 있음 (~500ms) | 없음 |
| 런타임 | V8 (제한적) | Node.js (풀) | Node.js (풀) |
| DB 접근 | 제한 (HTTP만) | 가능 | 가능 |
| 적합 | 미들웨어, 캐시, A/B | API, 백그라운드 | 무거운 로직 |'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/realtime_edge.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 실시간/Edge 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  실시간/Edge: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
