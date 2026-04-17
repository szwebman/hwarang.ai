/**
 * Slack 연동 API
 *
 * POST /api/integrations/slack - Slack 메시지에서 화랑 AI 호출
 *
 * 설정: Slack App → Event Subscriptions → Request URL: https://hwarang.ai/api/integrations/slack
 */

import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  const body = await request.json();

  // Slack URL 검증 (앱 등록 시)
  if (body.type === "url_verification") {
    return Response.json({ challenge: body.challenge });
  }

  // 메시지 이벤트
  if (body.event?.type === "app_mention" || body.event?.type === "message") {
    const text = body.event.text?.replace(/<@[^>]+>/g, "").trim();
    const channel = body.event.channel;
    const threadTs = body.event.thread_ts || body.event.ts;

    if (!text) return Response.json({ ok: true });

    // 비동기로 AI 응답 생성 + Slack에 전송
    processSlackMessage(text, channel, threadTs).catch(console.error);

    return Response.json({ ok: true });
  }

  return Response.json({ ok: true });
}

async function processSlackMessage(text: string, channel: string, threadTs: string) {
  const SLACK_BOT_TOKEN = process.env.SLACK_BOT_TOKEN;
  if (!SLACK_BOT_TOKEN) return;

  // 화랑 AI 호출
  try {
    const aiResp = await fetch(`${process.env.NEXTAUTH_URL || "http://localhost:3000"}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", content: text }],
        max_tokens: 1024,
      }),
    });

    const data = await aiResp.json();
    const reply = data.choices?.[0]?.message?.content || "응답을 생성할 수 없습니다.";

    // Slack에 응답 전송
    await fetch("https://slack.com/api/chat.postMessage", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${SLACK_BOT_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        channel,
        text: reply,
        thread_ts: threadTs,
      }),
    });
  } catch (e) {
    console.error("Slack 응답 실패:", e);
  }
}
