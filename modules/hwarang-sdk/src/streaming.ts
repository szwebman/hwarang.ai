import type { ChatStreamChunk } from "./types";

/**
 * SSE (Server-Sent Events) 파서 — fetch 응답의 ReadableStream 을
 * AsyncIterable<ChatStreamChunk> 로 변환.
 *
 * OpenAI 호환 형식:
 *   data: {"id":"...","choices":[{"delta":{"content":"..."}}]}\n\n
 *   data: [DONE]\n\n
 */
export async function* parseSSEStream(
  body: ReadableStream<Uint8Array> | null,
): AsyncGenerator<ChatStreamChunk, void, unknown> {
  if (!body) return;

  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // 이벤트는 \n\n 으로 구분
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const event = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        for (const line of event.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const payload = line.slice(5).trim();
          if (!payload || payload === "[DONE]") continue;
          try {
            yield JSON.parse(payload) as ChatStreamChunk;
          } catch {
            // 잘못된 JSON 은 건너뜀
          }
        }
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* ignore */
    }
  }
}

/**
 * 스트림에서 누적된 텍스트만 추출하는 편의 함수.
 */
export async function* streamTextDeltas(
  stream: AsyncIterable<ChatStreamChunk>,
): AsyncGenerator<string, void, unknown> {
  for await (const chunk of stream) {
    const delta = chunk.choices?.[0]?.delta;
    if (delta?.content) yield delta.content;
  }
}
