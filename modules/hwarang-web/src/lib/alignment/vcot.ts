/**
 * VCoT - Verified Chain-of-Thought
 *
 * 화랑 AI 고유 정렬 기법 #7
 *
 * 각 추론 단계마다 검증 + 신뢰도 표시.
 * 계산/법률/세무처럼 정확성 중요한 도메인 필수.
 */

export interface ReasoningStep {
  step: number;
  description: string;
  computation?: string;
  verification: "verified" | "warning" | "failed" | "not_verified";
  confidence: number;          // 0~1
  source?: string;              // 법령/공식 출처
  note?: string;
}

export interface VCoTResult {
  steps: ReasoningStep[];
  overallConfidence: number;
  needsExpertReview: boolean;
  summary: string;
}

// ─── 수식 검증 ──────────────────────────────────────────────────

function verifyComputation(expression: string): { valid: boolean; result?: number; error?: string } {
  try {
    // 안전한 수식만 허용 (숫자, +, -, *, /, %, (, ), 쉼표)
    if (!/^[\d+\-*/%().,\s]+$/.test(expression)) {
      return { valid: false, error: "unsafe expression" };
    }

    // 쉼표 제거 후 평가
    const cleaned = expression.replace(/,/g, "");
    // eslint-disable-next-line no-new-func
    const result = new Function(`return ${cleaned}`)();

    if (typeof result !== "number" || !isFinite(result)) {
      return { valid: false, error: "not a finite number" };
    }

    return { valid: true, result };
  } catch (e: any) {
    return { valid: false, error: e.message };
  }
}

// ─── 법령 인용 검증 ─────────────────────────────────────────────

async function verifyLegalCitation(citation: string): Promise<{ valid: boolean; url?: string }> {
  // 예: "민법 제543조"
  const match = citation.match(/(민법|형법|상법|노동법|세법)\s*제?\s*(\d+)조/);
  if (!match) return { valid: false };

  const [, law, article] = match;
  const apiKey = process.env.LAW_GO_KR_API_KEY;

  if (!apiKey) return { valid: false };

  try {
    const url = `http://www.law.go.kr/DRF/lawSearch.do?OC=${apiKey}&target=law&type=JSON&query=${encodeURIComponent(law)}&display=1`;
    const resp = await fetch(url, { signal: AbortSignal.timeout(3000) });
    if (!resp.ok) return { valid: false };

    const data = await resp.json();
    const laws = data.LawSearch?.law || [];

    if (laws.length > 0) {
      return {
        valid: true,
        url: `https://www.law.go.kr/lsInfoP.do?lsiSeq=${laws[0].법령ID}`,
      };
    }
  } catch {}

  return { valid: false };
}

// ─── 추론 단계 파싱 ────────────────────────────────────────────

function parseSteps(text: string): ReasoningStep[] {
  const steps: ReasoningStep[] = [];

  // "[단계 1]" 또는 "Step 1:" 패턴
  const stepPattern = /(?:\[단계\s*(\d+)\]|Step\s*(\d+)[:.])\s*([\s\S]+?)(?=\[단계|Step\s*\d+[:.]|$)/g;

  let match;
  while ((match = stepPattern.exec(text)) !== null) {
    const num = parseInt(match[1] || match[2], 10);
    const description = match[3].trim();

    // 계산식 추출 (예: "3,600만원 × 15% = 540만원")
    const compMatch = description.match(/([\d,]+(?:\.\d+)?(?:만|억)?원?\s*[×*]\s*[\d.,]+%?\s*[=\-+÷/]\s*[\d,]+(?:\.\d+)?)/);

    steps.push({
      step: num,
      description,
      computation: compMatch ? compMatch[1] : undefined,
      verification: "not_verified",
      confidence: 0.7,
    });
  }

  return steps;
}

// ─── 메인 파이프라인 ────────────────────────────────────────────

export async function applyVCoT(
  reasoningText: string,
  options: {
    verifyLegal?: boolean;
    verifyMath?: boolean;
  } = { verifyLegal: true, verifyMath: true }
): Promise<VCoTResult> {
  const steps = parseSteps(reasoningText);

  if (steps.length === 0) {
    return {
      steps: [],
      overallConfidence: 0.5,
      needsExpertReview: false,
      summary: "추론 단계를 찾을 수 없습니다",
    };
  }

  // 각 단계 검증
  for (const step of steps) {
    // 수식 검증
    if (options.verifyMath && step.computation) {
      const compResult = verifyComputation(step.computation);
      if (compResult.valid) {
        step.verification = "verified";
        step.confidence = 0.95;
        step.note = `계산 결과: ${compResult.result}`;
      } else {
        step.verification = "warning";
        step.confidence = 0.4;
        step.note = `수식 검증 실패: ${compResult.error}`;
      }
    }

    // 법령 인용 검증
    if (options.verifyLegal) {
      const legalMatch = step.description.match(/(민법|형법|상법|노동법|세법)\s*제?\s*\d+조/);
      if (legalMatch) {
        const legalResult = await verifyLegalCitation(legalMatch[0]);
        if (legalResult.valid) {
          step.verification = "verified";
          step.confidence = Math.max(step.confidence, 0.9);
          step.source = legalResult.url;
        } else {
          step.verification = "warning";
          step.confidence = 0.3;
          step.note = "인용된 법령을 확인할 수 없습니다";
        }
      }
    }
  }

  // 전체 신뢰도 = 각 단계 신뢰도 평균
  const overallConfidence = steps.reduce((s, st) => s + st.confidence, 0) / steps.length;

  // 경고가 있으면 전문가 검토 필요
  const hasWarning = steps.some((s) => s.verification === "warning" || s.verification === "failed");
  const needsExpertReview = hasWarning || overallConfidence < 0.7;

  // 요약 생성
  const verifiedCount = steps.filter((s) => s.verification === "verified").length;
  const summary = `총 ${steps.length}단계 중 ${verifiedCount}단계 검증 완료. 전체 신뢰도: ${(overallConfidence * 100).toFixed(0)}%`;

  return {
    steps,
    overallConfidence,
    needsExpertReview,
    summary,
  };
}

// ─── 프롬프트 생성 (VCoT 스타일로 답변 유도) ────────────────────

export function buildVCoTPrompt(): string {
  return `\n\n[VCoT - 검증된 추론 체인]
복잡한 계산이나 법률/세무 답변 시 다음 형식으로 작성하세요:

[단계 1] 문제 파악: <무엇을 계산/판단하는지>
[단계 2] 근거 수집: <관련 법령, 공식, 데이터>
[단계 3] 계산/추론: <수식을 명시적으로 작성>
[단계 4] 검증: <다른 방식으로 확인 가능?>
[단계 5] 최종 답: <명확한 결론 + 신뢰도>

예시:
[단계 1] 종합소득세 계산 (연봉 5천만원 기준)
[단계 2] 소득세법 제55조 (세율 구간)
[단계 3] 과세표준 × 세율: 42,000,000 × 0.15 = 6,300,000
[단계 4] 누진공제 적용: 6,300,000 - 1,080,000 = 5,220,000
[단계 5] 최종 세액: 약 522만원 (지방세 제외, 공제 미반영)`;
}

// ─── 결과를 답변에 시각화 ──────────────────────────────────────

export function renderVCoTResult(result: VCoTResult): string {
  if (result.steps.length === 0) return "";

  let output = "\n\n**🔍 추론 검증 (VCoT)**\n\n";

  for (const step of result.steps) {
    const icon = {
      verified: "✅",
      warning: "⚠️",
      failed: "❌",
      not_verified: "○",
    }[step.verification];

    output += `${icon} **단계 ${step.step}** (신뢰도 ${(step.confidence * 100).toFixed(0)}%)\n`;
    output += `   ${step.description.slice(0, 100)}${step.description.length > 100 ? "..." : ""}\n`;
    if (step.note) output += `   💡 ${step.note}\n`;
    if (step.source) output += `   🔗 출처: ${step.source}\n`;
    output += "\n";
  }

  output += `\n**전체 신뢰도: ${(result.overallConfidence * 100).toFixed(0)}%**`;

  if (result.needsExpertReview) {
    output += `\n\n⚠️ **전문가 검토 권장**: 일부 단계에서 검증이 완벽하지 않습니다.`;
  }

  return output;
}
