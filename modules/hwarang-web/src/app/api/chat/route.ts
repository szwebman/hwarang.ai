/**
 * Chat API proxy route.
 * Proxies requests from the browser to the Hwarang API server,
 * keeping the API URL and credentials server-side.
 */

import { NextRequest } from "next/server";

const HWARANG_API_URL =
  process.env.HWARANG_API_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.json();

  const apiResponse = await fetch(
    `${HWARANG_API_URL}/v1/chat/completions`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }
  );

  if (!apiResponse.ok) {
    return new Response(
      JSON.stringify({ error: `API error: ${apiResponse.status}` }),
      { status: apiResponse.status }
    );
  }

  // For streaming responses, pipe through
  if (body.stream) {
    return new Response(apiResponse.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }

  // Non-streaming: return JSON directly
  const data = await apiResponse.json();
  return Response.json(data);
}
