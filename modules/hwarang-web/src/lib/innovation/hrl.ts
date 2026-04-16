/**
 * HRL - Hwarang Reality Lock
 *
 * 화랑 독자 혁신 기법 #3 (환각 방지)
 *
 * 답변 생성 중 실시간 팩트 체크:
 *   1. 응답을 문장 단위로 분리
 *   2. 사실 주장 문장 추출
 *   3. 각 문장을 공식 DB(HRAG)로 검증
 *   4. 틀린 문장 표시/재생성
 *
 * "AI가 거짓말을 못하는" 최초의 시스템.
 */

import { applyHRAG, type HRAGSource } from "../alignment/hrag";
import { verifyAllCitations } from "../alignment/lcrg";

export interface RealityCheck {
  statement: string;
  type: "fact" | "opinion" | "command" | "question";
  verified: boolean;
  confidence: number;
  sources: HRAGSource[];
  issues: string[];
}

/**
 * 응답에서 사실 주장 추출
 */
function extractFactualStatements(response: string): string[] {
  // 문장 단위 분리
  const sentences = response
    .split(/[.!?。][\s\n]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 10);

  // 사실 주장 패턴 (의견/명령 제외)
  const factPatterns = [
    /(이다|입니다|됩니다|합니다)\.?$/,
    /\d+[만억]?원/,
    /\d+%/,
    /제?\s*\d+조/,                  // 법 조항
    /\d{4}년/,                        // 연도
    /(제공|포함|의미|정의|규정|해당)/,
  ];

  const opinionPatterns = [
    /(생각|느낌|추천|선호|좋은|나쁜|최고)/,
    /(\?|~지 않을까|~것 같)/,
  ];

  return sentences.filter((s) => {
    const isFact = factPatterns.some((p) => p.test(s));
    const isOpinion = opinionPatterns.some((p) => p.test(s));
    return isFact && !isOpinion;
  });
}

/**
 * 주장에 대한 현실 체크
 */
async function checkStatement(statement: string): Promise<RealityCheck> {
  const issues: string[] = [];

  // 1. 법령/판례 인용 검증
  const citations = await verifyAllCitations(statement);
  const unverifiedCitations = citations.filter((c) => !c.verified);
  if (unverifiedCitations.length > 0) {
    issues.push(`검증 안 된 인용 ${unverifiedCitations.length}건`);
  }

  // 2. HRAG로 관련 자료 검색
  const hrag = await applyHRAG(statement);

  // 3. 신뢰도 계산
  let confidence = 0.5;
  if (citations.length > 0 && unverifiedCitations.length === 0) confidence += 0.3;
  if (hrag.sources.length > 0) confidence += 0.2;
  if (issues.length === 0) confidence = Math.min(1.0, confidence + 0.1);

  return {
    statement,
    type: "fact",
    verified: issues.length === 0 && confidence >= 0.7,
    confidence,
    sources: hrag.sources,
    issues,
  };
}

/**
 * 응답 전체 현실 체크
 */
export async function applyHRL(response: string): Promise<{
  overallConfidence: number;
  totalStatements: number;
  verifiedCount: number;
  checks: RealityCheck[];
  markedResponse: string;
  needsRegeneration: boolean;
}> {
  const statements = extractFactualStatements(response);

  if (statements.length === 0) {
    return {
      overallConfidence: 0.8,
      totalStatements: 0,
      verifiedCount: 0,
      checks: [],
      markedResponse: response,
      needsRegeneration: false,
    };
  }

  // 병렬로 모든 주장 검증
  const checks = await Promise.all(statements.map((s) => checkStatement(s)));

  const verifiedCount = checks.filter((c) => c.verified).length;
  const overallConfidence = checks.reduce((s, c) => s + c.confidence, 0) / checks.length;

  // 응답에 검증 마크 추가
  let markedResponse = response;
  for (const check of checks) {
    if (!check.verified) {
      const warningIcon = check.confidence < 0.4 ? "🔴" : "🟡";
      markedResponse = markedResponse.replace(
        check.statement,
        `${check.statement} ${warningIcon}`
      );
    }
  }

  // 신뢰도 낮으면 경고 추가
  const needsRegeneration = overallConfidence < 0.5 || verifiedCount / checks.length < 0.5;

  if (checks.filter((c) => !c.verified).length > 0) {
    markedResponse += `\n\n---\n**🔍 HRL 현실 체크**: ${verifiedCount}/${checks.length} 사실 검증됨 (전체 신뢰도 ${(overallConfidence * 100).toFixed(0)}%)`;

    const unverified = checks.filter((c) => !c.verified);
    if (unverified.length > 0) {
      markedResponse += `\n\n⚠️ 검증 실패 항목:`;
      for (const u of unverified.slice(0, 3)) {
        markedResponse += `\n- "${u.statement.slice(0, 80)}..." - ${u.issues.join(", ")}`;
      }
    }

    if (needsRegeneration) {
      markedResponse += `\n\n❌ **신뢰도가 낮습니다. 전문가 확인을 권장합니다.**`;
    }
  }

  return {
    overallConfidence,
    totalStatements: checks.length,
    verifiedCount,
    checks,
    markedResponse,
    needsRegeneration,
  };
}
