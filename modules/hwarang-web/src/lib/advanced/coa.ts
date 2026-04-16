/**
 * CoA - Chain-of-Agents (Google 2025)
 *
 * 긴 문서를 여러 에이전트가 릴레이로 처리.
 * Long Context보다 정확도 높고 비용 낮음.
 */

export interface CoAChunk {
  index: number;
  content: string;
  summary?: string;
}

/**
 * 긴 문서를 청크로 나누고, 각 청크를 순차 처리.
 * 이전 청크의 요약을 다음 청크에 전달.
 */
export async function applyCoA(
  document: string,
  userQuery: string,
  vllmEndpoint: string,
  model: string,
  options: { chunkSize?: number } = {}
): Promise<{
  finalAnswer: string;
  chunks: CoAChunk[];
  totalChunks: number;
}> {
  const chunkSize = options.chunkSize ?? 4000;

  // 청크 분할
  const chunks: CoAChunk[] = [];
  for (let i = 0; i < document.length; i += chunkSize) {
    chunks.push({
      index: chunks.length,
      content: document.slice(i, i + chunkSize),
    });
  }

  // 순차 처리 (이전 요약 전달)
  let carriedContext = "";
  for (const chunk of chunks) {
    const prompt = `당신은 Chain-of-Agents의 한 에이전트입니다.

[사용자 질문]
${userQuery}

[이전 에이전트의 요약]
${carriedContext || "(첫 청크, 이전 없음)"}

[현재 청크 ${chunk.index + 1}/${chunks.length}]
${chunk.content}

[임무]
1. 현재 청크에서 질문 관련 정보 추출
2. 이전 요약과 통합하여 지식 누적
3. 다음 에이전트에게 전달할 요약 작성 (500자 이내)

[출력 형식]
요약: <다음 에이전트에게 전달할 요약>`;

    try {
      const resp = await fetch(`${vllmEndpoint}/v1/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          messages: [{ role: "user", content: prompt }],
          max_tokens: 800,
          temperature: 0.3,
        }),
        signal: AbortSignal.timeout(30000),
      });
      if (resp.ok) {
        const data = await resp.json();
        const summary = data.choices?.[0]?.message?.content || "";
        chunk.summary = summary;
        carriedContext = summary;
      }
    } catch {}
  }

  // 최종 답변 생성
  const finalPrompt = `[사용자 질문]
${userQuery}

[전체 문서 분석 결과]
${carriedContext}

[임무] 위 분석을 바탕으로 사용자 질문에 완전한 답변을 작성하세요.`;

  let finalAnswer = "";
  try {
    const resp = await fetch(`${vllmEndpoint}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        messages: [{ role: "user", content: finalPrompt }],
        max_tokens: 2048,
        temperature: 0.5,
      }),
    });
    if (resp.ok) {
      const data = await resp.json();
      finalAnswer = data.choices?.[0]?.message?.content || "";
    }
  } catch {}

  return { finalAnswer, chunks, totalChunks: chunks.length };
}
