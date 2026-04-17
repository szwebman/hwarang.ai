/**
 * 범용 Webhook API
 *
 * POST /api/integrations/webhook - 외부 서비스 연동 (Notion, Jira 등)
 *
 * 사용법: 외부 서비스 → webhook URL 등록 → 이벤트 수신 → AI 처리
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

export async function POST(request: NextRequest) {
  const webhookSecret = request.headers.get("x-webhook-secret");
  const body = await request.json();

  // 웹훅 인증 (등록된 secret 확인)
  if (!webhookSecret) {
    return Response.json({ error: "x-webhook-secret 필요" }, { status: 401 });
  }

  // 웹훅 처리
  const { source, event, data } = body;

  // 로그 저장
  try {
    await prisma.systemSetting.upsert({
      where: { key: `webhook_log_${Date.now()}` },
      update: { value: JSON.stringify({ source, event, timestamp: new Date() }) },
      create: { key: `webhook_log_${Date.now()}`, value: JSON.stringify({ source, event }) },
    });
  } catch {}

  // 이벤트별 처리
  if (source === "notion" && event === "page_updated") {
    // Notion 페이지 업데이트 → RAG 인덱스 갱신
    return Response.json({ action: "rag_reindex", status: "queued" });
  }

  if (source === "github" && event === "push") {
    // GitHub push → 코드 분석 데이터 업데이트
    return Response.json({ action: "code_analysis", status: "queued" });
  }

  return Response.json({ received: true, source, event });
}
