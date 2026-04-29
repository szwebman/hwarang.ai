/**
 * Parse Server-Sent Events (SSE) stream from the Hwarang API.
 *
 * 두 종류의 이벤트를 산출:
 *   - { type: "content", content: string } — 본문 델타
 *   - { type: "meta", meta: any }          — 응답 직후 첨부된 _meta (verification 등)
 *
 * 하위 호환: 기본 산출 타입이 객체로 변경되었으므로 호출 측은 e.type 으로 분기.
 */

export type SSEEvent =
  | { type: "content"; content: string }
  | { type: "meta"; meta: Record<string, any> };

export async function* parseSSEStream(
  response: Response
): AsyncGenerator<SSEEvent, void, unknown> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith("data: ")) continue;

      const data = trimmed.slice(6);
      if (data === "[DONE]") return;

      try {
        const parsed = JSON.parse(data);

        // 메타 이벤트 (서버가 추가로 보내는 _meta — verification 등)
        if (parsed._meta) {
          yield { type: "meta", meta: parsed._meta };
          continue;
        }

        const content = parsed.choices?.[0]?.delta?.content;
        if (content) {
          yield { type: "content", content };
        }
      } catch {
        // Skip malformed chunks
      }
    }
  }
}
