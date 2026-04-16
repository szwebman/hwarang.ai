/**
 * HCE - Hwarang Community Evolution
 *
 * 화랑 독자 혁신 기법 #2
 *
 * Grid 커뮤니티 피드백을 유전 알고리즘처럼 모델 진화에 반영.
 * 매주 "가장 인기 있는 답변 스타일"을 자동 학습.
 *
 * 프로세스:
 *   1. 피드백 수집 (GRPO와 연동)
 *   2. 주간/월간 선호도 트렌드 분석
 *   3. 선호도 기반 DPO 쌍 자동 생성
 *   4. 증분 LoRA 학습 → 새 어댑터 배포
 *   5. A/B 테스트로 효과 검증
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

export interface EvolutionTrend {
  period: "daily" | "weekly" | "monthly";
  style: {
    preferredLength: "short" | "medium" | "long";
    preferredTone: "formal" | "friendly" | "technical";
    preferredStructure: "plain" | "markdown" | "numbered";
    includeCode: boolean;
    includeExamples: boolean;
  };
  topCategories: string[];     // 인기 도메인
  avoidedPatterns: string[];   // 싫어요 많이 받은 패턴
  sampleSize: number;
}

/**
 * 커뮤니티 피드백 분석 → 선호도 트렌드 추출
 */
export async function analyzeEvolutionTrend(
  period: "daily" | "weekly" | "monthly" = "weekly"
): Promise<EvolutionTrend> {
  const days = period === "daily" ? 1 : period === "weekly" ? 7 : 30;
  const since = new Date();
  since.setDate(since.getDate() - days);

  // GRPO 피드백 조회
  const feedbacks = await prisma.tokenTransaction.findMany({
    where: {
      type: "GRID_REWARD",
      createdAt: { gte: since },
    },
  });

  const positives: any[] = [];
  const negatives: any[] = [];

  for (const fb of feedbacks) {
    const meta = fb.metadata as any;
    if (!meta?.messageId) continue;

    // 해당 메시지 조회
    const msg = await prisma.message.findUnique({
      where: { id: meta.messageId },
    });
    if (!msg) continue;

    if (meta.rating === "thumbs_up") {
      positives.push({ content: msg.content, meta });
    } else if (meta.rating === "thumbs_down") {
      negatives.push({ content: msg.content, meta });
    }
  }

  // 선호도 분석
  const preferredLength = analyzeLength(positives);
  const preferredTone = analyzeTone(positives);
  const preferredStructure = analyzeStructure(positives);
  const includeCode = positives.filter((p) => p.content.includes("```")).length / Math.max(positives.length, 1) > 0.5;
  const includeExamples = positives.filter((p) => /예시|example/i.test(p.content)).length / Math.max(positives.length, 1) > 0.3;

  // 회피 패턴 추출 (싫어요 받은 공통점)
  const avoidedPatterns = extractCommonPatterns(negatives);

  // 인기 카테고리
  const categoryCount: Record<string, number> = {};
  for (const p of positives) {
    const cat = p.meta?.categories?.[0] || "general";
    categoryCount[cat] = (categoryCount[cat] || 0) + 1;
  }
  const topCategories = Object.entries(categoryCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([cat]) => cat);

  return {
    period,
    style: {
      preferredLength,
      preferredTone,
      preferredStructure,
      includeCode,
      includeExamples,
    },
    topCategories,
    avoidedPatterns,
    sampleSize: positives.length + negatives.length,
  };
}

function analyzeLength(responses: any[]): "short" | "medium" | "long" {
  if (responses.length === 0) return "medium";
  const avg = responses.reduce((s, r) => s + r.content.length, 0) / responses.length;
  if (avg < 300) return "short";
  if (avg > 1500) return "long";
  return "medium";
}

function analyzeTone(responses: any[]): "formal" | "friendly" | "technical" {
  if (responses.length === 0) return "friendly";
  let formalScore = 0, techScore = 0;
  for (const r of responses) {
    if (/(습니다|입니다|합니다)/.test(r.content)) formalScore++;
    if (r.content.includes("```") || /function|class|const|def/.test(r.content)) techScore++;
  }
  if (techScore / responses.length > 0.5) return "technical";
  if (formalScore / responses.length > 0.5) return "formal";
  return "friendly";
}

function analyzeStructure(responses: any[]): "plain" | "markdown" | "numbered" {
  if (responses.length === 0) return "markdown";
  let markdownScore = 0, numberedScore = 0;
  for (const r of responses) {
    if (/^#{1,3}\s|\*\*[^*]+\*\*/m.test(r.content)) markdownScore++;
    if (/^\d+\./m.test(r.content)) numberedScore++;
  }
  if (numberedScore / responses.length > 0.5) return "numbered";
  if (markdownScore / responses.length > 0.5) return "markdown";
  return "plain";
}

function extractCommonPatterns(negatives: any[]): string[] {
  const patterns: string[] = [];
  let chineseCount = 0;
  let englishMixCount = 0;
  let tooShortCount = 0;
  let noStructureCount = 0;

  for (const n of negatives) {
    const text = n.content;
    if (/[\u4e00-\u9fff]{3,}/.test(text)) chineseCount++;
    if (/[a-zA-Z]{20,}/.test(text) && text.length < 500) englishMixCount++;
    if (text.length < 100) tooShortCount++;
    if (!/\n|[*#\-]/.test(text)) noStructureCount++;
  }

  const threshold = Math.max(negatives.length * 0.3, 3);
  if (chineseCount > threshold) patterns.push("chinese_characters");
  if (englishMixCount > threshold) patterns.push("excessive_english");
  if (tooShortCount > threshold) patterns.push("too_short");
  if (noStructureCount > threshold) patterns.push("no_structure");

  return patterns;
}

/**
 * 진화된 시스템 프롬프트 생성.
 */
export function buildEvolutionPrompt(trend: EvolutionTrend): string {
  let prompt = `\n\n[HCE - 커뮤니티 진화 ${trend.period} 트렌드]`;
  prompt += `\n(샘플: ${trend.sampleSize}건)`;

  prompt += `\n\n[선호 스타일]`;
  prompt += `\n- 길이: ${trend.style.preferredLength}`;
  prompt += `\n- 톤: ${trend.style.preferredTone}`;
  prompt += `\n- 구조: ${trend.style.preferredStructure}`;
  if (trend.style.includeCode) prompt += `\n- 코드 예시 선호`;
  if (trend.style.includeExamples) prompt += `\n- 예시 포함 선호`;

  if (trend.avoidedPatterns.length > 0) {
    prompt += `\n\n[커뮤니티가 싫어함]`;
    for (const p of trend.avoidedPatterns) {
      prompt += `\n- ${p}`;
    }
  }

  return prompt;
}

export async function applyHCE(): Promise<string> {
  try {
    const trend = await analyzeEvolutionTrend("weekly");
    return buildEvolutionPrompt(trend);
  } catch {
    return "";
  }
}
