/**
 * NWNC - Noonchi-aware Natural Conversation
 *
 * 화랑 AI 고유 정렬 기법 #5 (한국 특화 최강)
 *
 * "눈치" 기반 한국인 대화 이해:
 *   - 간접 표현 해석
 *   - 감정 상태 추정
 *   - 체면 배려
 *   - 응답 톤 자동 조절
 */

// ─── 한국어 정서 패턴 ─────────────────────────────────────────

export interface EmotionState {
  primary: "neutral" | "frustrated" | "happy" | "sad" | "anxious" | "confused" | "excited" | "polite";
  intensity: number;           // 0~1
  isIndirect: boolean;         // 간접 표현 사용 여부
  hiddenMeaning?: string;      // 추정된 실제 의도
  formalityLevel: "formal" | "semi-formal" | "casual";
  tonalHint: "respectful" | "caring" | "neutral" | "friendly";
}

// 한국어 간접 표현 패턴
const INDIRECT_PATTERNS: Array<{ pattern: RegExp; meaning: string; emotion: EmotionState["primary"] }> = [
  // "괜찮긴 한데..." = 별로다
  { pattern: /괜찮(긴|은데|기는)\s*(한데|하지만|근데|반대로)/, meaning: "불만족. 개선이 필요하다는 뜻", emotion: "frustrated" },
  { pattern: /(나쁘지는|싫지는)\s*않(은데|아요)/, meaning: "적극적 동의는 아님. 미적지근", emotion: "neutral" },

  // "아쉬운데..." = 고쳐줘
  { pattern: /(아쉬운|좀 그런|애매한)데/, meaning: "개선 요청. 부족한 부분이 있다는 뜻", emotion: "frustrated" },

  // "뭐 어쩌라는 거야" = 짜증
  { pattern: /(뭐\s*어쩌라는|어떻게\s*하라고|대체|도대체)/, meaning: "짜증, 혼란. 명확한 도움이 필요", emotion: "frustrated" },

  // "아 진짜?" = 의심/놀람
  { pattern: /아\s*진짜\?+/, meaning: "놀람 또는 의심. 확인 필요", emotion: "confused" },

  // "그냥..." = 소극적
  { pattern: /^그냥\s/, meaning: "소극적 표현. 자세한 답변보다 간결함 선호", emotion: "neutral" },

  // 과한 존칭 = 긴장/정중함
  { pattern: /(여쭤|여쭙|죄송하지만|실례지만)/, meaning: "정중함. 예의있게 응답 필요", emotion: "polite" },

  // "ㅠㅠ" = 슬픔/부탁
  { pattern: /[ㅠㅜ]{2,}|흑흑|엉엉/, meaning: "슬픔 또는 간절한 부탁. 공감 필요", emotion: "sad" },

  // "!" 많음 = 흥분/기쁨
  { pattern: /!{3,}/, meaning: "강한 감정. 흥분 또는 기쁨", emotion: "excited" },

  // "?" 많음 = 혼란
  { pattern: /\?{3,}|어\?+|뭐지\?+/, meaning: "혼란. 명확한 설명 필요", emotion: "confused" },

  // 반복 = 강조/답답함
  { pattern: /(.{2,4})\1{2,}/, meaning: "답답함 또는 강조", emotion: "frustrated" },
];

// 한국어 존대 레벨 감지
function detectFormality(text: string): EmotionState["formalityLevel"] {
  // 해요체/합쇼체
  const formalEndings = /(습니다|입니다|니까|세요|해요|예요|이에요|십시오)[.?!\s]/g;
  // 반말
  const casualEndings = /(이야|야|어|지|데|냐|ㄹ까)\s*[.?!]?$/;
  // 비속어
  const slang = /(ㅋㅋ|ㅎㅎ|개|완전|쩔|짜증|ㄴㄴ|ㅇㅇ)/;

  const formalCount = (text.match(formalEndings) || []).length;
  const casualCount = (text.match(casualEndings) || []).length;

  if (formalCount > casualCount) return "formal";
  if (slang.test(text) || casualCount > 0) return "casual";
  return "semi-formal";
}

// 감정 분석
export function analyzeEmotion(text: string): EmotionState {
  let primary: EmotionState["primary"] = "neutral";
  let intensity = 0.3;
  let isIndirect = false;
  let hiddenMeaning: string | undefined;

  // 간접 표현 패턴 매칭
  for (const { pattern, meaning, emotion } of INDIRECT_PATTERNS) {
    if (pattern.test(text)) {
      primary = emotion;
      isIndirect = true;
      hiddenMeaning = meaning;
      intensity = 0.7;
      break;
    }
  }

  const formalityLevel = detectFormality(text);

  // 응답 톤 결정
  let tonalHint: EmotionState["tonalHint"] = "neutral";
  if (primary === "frustrated" || primary === "confused") {
    tonalHint = "caring";
  } else if (primary === "sad") {
    tonalHint = "caring";
  } else if (primary === "polite" || formalityLevel === "formal") {
    tonalHint = "respectful";
  } else if (formalityLevel === "casual") {
    tonalHint = "friendly";
  }

  return {
    primary,
    intensity,
    isIndirect,
    hiddenMeaning,
    formalityLevel,
    tonalHint,
  };
}

// ─── 시스템 프롬프트 생성 ─────────────────────────────────────

export function buildNWNCPrompt(emotion: EmotionState): string {
  let prompt = `\n\n[NWNC - 눈치 기반 대화 분석]
- 감정: ${emotion.primary} (강도 ${(emotion.intensity * 100).toFixed(0)}%)
- 존대 수준: ${emotion.formalityLevel}
- 응답 톤: ${emotion.tonalHint}`;

  if (emotion.isIndirect && emotion.hiddenMeaning) {
    prompt += `
- ⚠️ 간접 표현 감지: ${emotion.hiddenMeaning}`;
  }

  // 톤별 지침
  prompt += `\n\n[응답 지침]`;

  if (emotion.tonalHint === "caring") {
    prompt += `
- 공감과 이해를 먼저 표현하세요
- "답답하시겠어요", "이해합니다" 같은 공감 표현 사용
- 실질적 해결책을 친절하게 제시`;
  } else if (emotion.tonalHint === "respectful") {
    prompt += `
- 정중한 존댓말 사용 (습니다체)
- 간결하고 명확한 설명
- 과도한 친밀감 표현 자제`;
  } else if (emotion.tonalHint === "friendly") {
    prompt += `
- 친근한 톤 (해요체 또는 반말)
- 이모지/가벼운 표현 적절히 사용
- 너무 격식있지 않게`;
  } else {
    prompt += `
- 기본 존댓말 (해요체)
- 중립적이고 전문적인 톤`;
  }

  if (emotion.formalityLevel === "formal") {
    prompt += `\n- 반드시 합쇼체 또는 해요체 사용`;
  } else if (emotion.formalityLevel === "casual") {
    prompt += `\n- 반말 또는 해요체 혼용 허용`;
  }

  if (emotion.isIndirect) {
    prompt += `\n- 간접 표현의 실제 의도(${emotion.hiddenMeaning})를 파악하여 응답`;
    prompt += `\n- "혹시 이런 뜻이신가요?" 같은 확인 질문 적절히 활용`;
  }

  return prompt;
}

// ─── 메인 ───────────────────────────────────────────────────────

export function applyNWNC(userMessage: string): {
  emotion: EmotionState;
  systemPrompt: string;
} {
  const emotion = analyzeEmotion(userMessage);
  const systemPrompt = buildNWNCPrompt(emotion);
  return { emotion, systemPrompt };
}
