/**
 * HSEE Phase 1 — Implicit feedback collector (서버측 프록시)
 *
 * POST /api/feedback/implicit
 *
 * GRPO 보상 없음. RLHFFeedback 풀에만 fire-and-forget 으로 기록.
 * 명시 피드백은 /api/feedback (route.ts) 에서 처리 — 이 라우트와 충돌 X.
 *
 * Body:
 *   { kind: "copy" | "negative_followup" | "edit_distance", messageId, ... }
 *
 * 매핑:
 *   - copy              → rating= 1, comment="[implicit:copy]"
 *   - negative_followup → rating=-1, comment="[implicit:followup] <user msg>"
 *   - edit_distance     → rating= 0, comment="[implicit:edit_distance=<n>]"
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";
const INTERNAL_KEY = process.env.HWARANG_INTERNAL_KEY || "";

interface ImplicitBody {
  kind?: string;
  messageId?: string;
  userMessage?: string;
  distance?: number;
}

export async function POST(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    // 로그인 안 된 사용자도 implicit 신호는 무의미 → 401
    return Response.json({ ok: false, reason: "no_session" }, { status: 401 });
  }

  let body: ImplicitBody = {};
  try {
    body = (await request.json()) as ImplicitBody;
  } catch {
    return Response.json({ ok: false, reason: "bad_json" }, { status: 400 });
  }

  if (!body.messageId || !body.kind) {
    return Response.json({ ok: false, reason: "missing_fields" }, { status: 400 });
  }

  let rating = 0;
  let comment: string | null = null;

  if (body.kind === "copy") {
    rating = 1;
    comment = "[implicit:copy]";
  } else if (body.kind === "negative_followup") {
    rating = -1;
    const head = (body.userMessage || "").slice(0, 240);
    comment = `[implicit:followup] ${head}`;
  } else if (body.kind === "edit_distance") {
    rating = 0;
    const d = typeof body.distance === "number" ? body.distance : 0;
    comment = `[implicit:edit_distance=${d.toFixed(3)}]`;
  } else {
    return Response.json({ ok: false, reason: "unknown_kind" }, { status: 400 });
  }

  // 백엔드로 fire-and-forget 전달
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (INTERNAL_KEY) headers.Authorization = `Bearer ${INTERNAL_KEY}`;
  const payload = {
    message_id: body.messageId,
    user_id: session.user.id,
    rating,
    comment,
  };

  // 비동기 fire-and-forget — 응답은 즉시 반환
  fetch(`${HWARANG_API_URL}/api/learning/feedback`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  }).catch(() => {});

  return Response.json({ ok: true, kind: body.kind });
}
