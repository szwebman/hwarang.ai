/**
 * CoRD - Collaborative Reasoning & Debate
 *
 * 화랑 AI 고유 정렬 기법 #6
 *
 * 여러 모델이 토론하며 합의 도출.
 * 단일 모델의 환각 감소, 신뢰도 향상.
 *
 * 동작:
 *   Round 1: N개 모델이 각자 답변 (병렬)
 *   Round 2: 서로 답변 보고 재검토 (비판 + 수정)
 *   Round 3: 심판 모델이 최종 합의 도출
 */

export interface ModelEndpoint {
  name: string;
  endpoint: string;
  modelId: string;
  role?: "generator" | "critic" | "judge";
}

export interface CoRDRound {
  round: number;
  responses: Array<{
    model: string;
    content: string;
    reasoning?: string;
  }>;
}

export interface CoRDResult {
  finalAnswer: string;
  confidence: number;
  rounds: CoRDRound[];
  disagreements: string[];
  consensusMethod: "unanimous" | "majority" | "judge_decision";
}

// ─── Round 1: 병렬 답변 생성 ────────────────────────────────────

async function generateResponse(
  model: ModelEndpoint,
  messages: any[],
  maxTokens: number = 1024
): Promise<string> {
  try {
    const resp = await fetch(`${model.endpoint}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: model.modelId,
        messages,
        max_tokens: maxTokens,
        temperature: 0.7,
      }),
      signal: AbortSignal.timeout(30000),
    });

    if (!resp.ok) return "";
    const data = await resp.json();
    return data.choices?.[0]?.message?.content || "";
  } catch {
    return "";
  }
}

// ─── Round 2: 상호 비판 및 재검토 ──────────────────────────────

function buildCriticPrompt(
  originalQuestion: string,
  myAnswer: string,
  otherAnswers: Array<{ model: string; content: string }>
): string {
  return `다음은 같은 질문에 대한 여러 AI의 답변입니다.

[질문]
${originalQuestion}

[나의 이전 답변]
${myAnswer}

[다른 AI의 답변]
${otherAnswers.map((a, i) => `--- ${a.model} ---\n${a.content}`).join("\n\n")}

[요청]
위 답변들을 비교한 후, 다음을 수행하세요:
1. 다른 AI의 답변 중 나보다 정확한 부분이 있다면 인정하고 반영
2. 나의 답변에서 오류나 부족한 부분을 찾아 수정
3. 최종 개선된 답변 작성

**중요**: 단순히 다른 의견을 따라가지 말고, 근거가 충분한 것만 반영하세요.`;
}

// ─── Round 3: 심판 모델이 최종 합의 ─────────────────────────────

function buildJudgePrompt(
  originalQuestion: string,
  finalResponses: Array<{ model: string; content: string }>
): string {
  return `다음은 여러 AI가 같은 질문에 대해 2라운드 토론한 최종 답변들입니다.
당신은 심판으로서 가장 신뢰할 수 있는 답변을 만들어야 합니다.

[질문]
${originalQuestion}

[최종 답변들]
${finalResponses.map((a) => `--- ${a.model} ---\n${a.content}`).join("\n\n")}

[요청]
1. 여러 답변에서 공통되는(일관된) 내용 → 신뢰도 높음
2. 일부 답변에만 있는 내용 → 근거 확인 후 선택
3. 서로 모순되는 내용 → 명확히 지적하고 더 타당한 쪽 선택
4. 환각(hallucination) 의심 부분 → 제거

[출력 형식]
먼저 합의된 내용으로 최종 답변을 작성하세요.
답변 끝에 다음을 JSON으로 첨부:
\`\`\`json
{
  "confidence": 0.0~1.0,
  "consensus_method": "unanimous" | "majority" | "judge_decision",
  "disagreements": ["모순되었던 부분들"]
}
\`\`\``;
}

// ─── 동의 수준 계산 ────────────────────────────────────────────

function calculateAgreement(responses: string[]): number {
  if (responses.length < 2) return 1.0;

  // 단순 유사도: 공통 단어 비율
  const wordSets = responses.map((r) =>
    new Set(r.split(/\s+/).filter((w) => w.length > 2))
  );

  const intersection = [...wordSets[0]].filter((w) =>
    wordSets.every((s) => s.has(w))
  );

  const avgSize = wordSets.reduce((s, w) => s + w.size, 0) / wordSets.length;
  return avgSize > 0 ? intersection.length / avgSize : 0;
}

// ─── 메인 파이프라인 ──────────────────────────────────────────

export async function applyCoRD(
  question: string,
  models: ModelEndpoint[],
  options: {
    rounds?: number;           // 토론 라운드 수 (기본 2)
    maxTokens?: number;
    systemPrompt?: string;
  } = {}
): Promise<CoRDResult> {
  const { rounds = 2, maxTokens = 1024, systemPrompt = "" } = options;
  const roundHistory: CoRDRound[] = [];

  const baseMessages = systemPrompt
    ? [{ role: "system", content: systemPrompt }, { role: "user", content: question }]
    : [{ role: "user", content: question }];

  // ─── Round 1: 병렬 생성 ──────────────
  const round1Results = await Promise.all(
    models.map((m) => generateResponse(m, baseMessages, maxTokens).then((content) => ({
      model: m.name,
      content,
    })))
  );

  roundHistory.push({ round: 1, responses: round1Results });

  let currentResponses = round1Results;

  // ─── Round 2~N: 상호 비판 ──────────────
  for (let r = 2; r <= rounds; r++) {
    const newResponses = await Promise.all(
      models.map(async (m, idx) => {
        const myAnswer = currentResponses[idx].content;
        const others = currentResponses.filter((_, i) => i !== idx);
        const criticPrompt = buildCriticPrompt(question, myAnswer, others);

        const refined = await generateResponse(
          m,
          [{ role: "user", content: criticPrompt }],
          maxTokens
        );

        return { model: m.name, content: refined || myAnswer };
      })
    );

    roundHistory.push({ round: r, responses: newResponses });
    currentResponses = newResponses;
  }

  // ─── 심판 라운드 (첫 번째 모델을 심판으로) ──────────────
  const judge = models[0];
  const judgePrompt = buildJudgePrompt(question, currentResponses);
  const finalRaw = await generateResponse(
    judge,
    [{ role: "user", content: judgePrompt }],
    maxTokens * 2
  );

  // JSON 메타데이터 파싱
  let confidence = 0.7;
  let consensusMethod: CoRDResult["consensusMethod"] = "judge_decision";
  let disagreements: string[] = [];
  let finalAnswer = finalRaw;

  const jsonMatch = finalRaw.match(/```json\s*([\s\S]*?)\s*```/);
  if (jsonMatch) {
    try {
      const meta = JSON.parse(jsonMatch[1]);
      confidence = meta.confidence ?? 0.7;
      consensusMethod = meta.consensus_method ?? "judge_decision";
      disagreements = meta.disagreements ?? [];
      // JSON 블록 제거
      finalAnswer = finalRaw.replace(/```json\s*[\s\S]*?\s*```/, "").trim();
    } catch {}
  }

  // 전체 동의 수준으로 confidence 보정
  const agreement = calculateAgreement(currentResponses.map((r) => r.content));
  confidence = (confidence + agreement) / 2;

  return {
    finalAnswer,
    confidence,
    rounds: roundHistory,
    disagreements,
    consensusMethod,
  };
}

// ─── CoRD 활성화 조건 ──────────────────────────────────────────

export function shouldUseCoRD(domain: string, userPlan?: string): boolean {
  // 고위험 도메인 + Pro 이상 플랜에서 활성화
  const highRiskDomains = ["legal", "tax", "medical", "finance"];
  const eligiblePlans = ["pro", "business", "enterprise"];

  return highRiskDomains.includes(domain) &&
         (userPlan ? eligiblePlans.includes(userPlan) : false);
}
