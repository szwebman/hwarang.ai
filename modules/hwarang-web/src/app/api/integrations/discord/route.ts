/**
 * Discord 봇 연동 API
 *
 * POST /api/integrations/discord - Discord 인터랙션 처리
 *
 * 설정: Discord Developer Portal → Interactions Endpoint URL
 */

import { NextRequest } from "next/server";
import crypto from "crypto";

const DISCORD_PUBLIC_KEY = process.env.DISCORD_PUBLIC_KEY || "";
const DISCORD_BOT_TOKEN = process.env.DISCORD_BOT_TOKEN || "";

function verifyDiscordSignature(body: string, signature: string, timestamp: string): boolean {
  const message = timestamp + body;
  const expected = crypto
    .verify("ed25519", Buffer.from(message), Buffer.from(DISCORD_PUBLIC_KEY, "hex"), Buffer.from(signature, "hex"));
  return expected;
}

export async function POST(request: NextRequest) {
  const body = await request.text();
  const signature = request.headers.get("x-signature-ed25519") || "";
  const timestamp = request.headers.get("x-signature-timestamp") || "";

  const data = JSON.parse(body);

  // Ping (검증)
  if (data.type === 1) {
    return Response.json({ type: 1 });
  }

  // 슬래시 커맨드: /hwarang
  if (data.type === 2) {
    const userInput = data.data?.options?.[0]?.value || "";
    const userId = data.member?.user?.id || data.user?.id;

    // 즉시 "생각 중..." 응답 (Discord 3초 제한)
    // 실제 응답은 Followup으로 전송
    processDiscordCommand(userInput, data.token).catch(console.error);

    return Response.json({
      type: 5,  // DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
    });
  }

  return Response.json({ type: 1 });
}

async function processDiscordCommand(question: string, interactionToken: string) {
  try {
    const aiResp = await fetch(`${process.env.NEXTAUTH_URL || "http://localhost:3000"}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", content: question }],
        max_tokens: 1024,
      }),
    });

    const data = await aiResp.json();
    const reply = data.choices?.[0]?.message?.content || "응답 생성 실패";

    // Discord Followup 메시지
    const appId = process.env.DISCORD_APP_ID || "";
    await fetch(`https://discord.com/api/v10/webhooks/${appId}/${interactionToken}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content: reply.slice(0, 2000),  // Discord 2000자 제한
      }),
    });
  } catch (e) {
    console.error("Discord 응답 실패:", e);
  }
}
