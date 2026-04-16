/**
 * TADM - Temporal-Adaptive Decision Maker
 *
 * 화랑 AI 고유 정렬 기법 #8
 *
 * 시점 인식 + 한국 일정/규정 자동 반영.
 * "올해", "이번 달" 같은 상대 시간 표현 정확히 처리.
 */

// ─── 한국 주요 세무/법정 일정 ───────────────────────────────────

export interface TemporalEvent {
  name: string;
  description: string;
  date: Date | { month: number; day: number };  // 고정일 또는 매년 반복
  type: "tax" | "legal" | "holiday" | "deadline";
  reminder?: string;
}

export const KOREAN_TEMPORAL_EVENTS: TemporalEvent[] = [
  // 세무 일정
  {
    name: "종합소득세 신고",
    description: "전년도 소득 종합소득세 신고 및 납부",
    date: { month: 5, day: 31 },
    type: "tax",
    reminder: "홈택스(hometax.go.kr) 또는 세무사 통해 신고",
  },
  {
    name: "부가가치세 1기 확정신고",
    description: "1~6월 매출 부가세 신고",
    date: { month: 7, day: 25 },
    type: "tax",
  },
  {
    name: "부가가치세 2기 확정신고",
    description: "7~12월 매출 부가세 신고",
    date: { month: 1, day: 25 },
    type: "tax",
  },
  {
    name: "부가가치세 1기 예정신고",
    description: "1분기 매출 부가세 예정신고 (법인)",
    date: { month: 4, day: 25 },
    type: "tax",
  },
  {
    name: "부가가치세 2기 예정신고",
    description: "3분기 매출 부가세 예정신고 (법인)",
    date: { month: 10, day: 25 },
    type: "tax",
  },
  {
    name: "법인세 신고",
    description: "12월 결산 법인 법인세 신고",
    date: { month: 3, day: 31 },
    type: "tax",
  },
  {
    name: "연말정산 간소화",
    description: "연말정산 간소화 서비스 오픈",
    date: { month: 1, day: 15 },
    type: "tax",
  },
  // 한국 공휴일 (주요)
  { name: "신정", description: "새해", date: { month: 1, day: 1 }, type: "holiday" },
  { name: "삼일절", description: "3.1절", date: { month: 3, day: 1 }, type: "holiday" },
  { name: "어린이날", description: "어린이날", date: { month: 5, day: 5 }, type: "holiday" },
  { name: "현충일", description: "현충일", date: { month: 6, day: 6 }, type: "holiday" },
  { name: "광복절", description: "광복절", date: { month: 8, day: 15 }, type: "holiday" },
  { name: "개천절", description: "개천절", date: { month: 10, day: 3 }, type: "holiday" },
  { name: "한글날", description: "한글날", date: { month: 10, day: 9 }, type: "holiday" },
  { name: "성탄절", description: "성탄절", date: { month: 12, day: 25 }, type: "holiday" },
];

// ─── 시간 컨텍스트 ─────────────────────────────────────────────

export interface TemporalContext {
  now: Date;
  currentYear: number;
  currentMonth: number;
  currentDay: number;
  weekdayKorean: string;
  quarter: number;
  currentTaxYear: number;    // 세무 기준 년도
  upcomingEvents: Array<{
    event: TemporalEvent;
    date: Date;
    daysUntil: number;
  }>;
}

const WEEKDAYS_KR = ["일", "월", "화", "수", "목", "금", "토"];

export function getTemporalContext(now: Date = new Date()): TemporalContext {
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  const day = now.getDate();
  const weekday = WEEKDAYS_KR[now.getDay()];
  const quarter = Math.ceil(month / 3);

  // 다가오는 이벤트 (30일 이내)
  const upcomingEvents: TemporalContext["upcomingEvents"] = [];
  for (const event of KOREAN_TEMPORAL_EVENTS) {
    if (!("month" in event.date)) continue;

    // 올해 해당 날짜
    const thisYear = new Date(year, event.date.month - 1, event.date.day);
    const nextYear = new Date(year + 1, event.date.month - 1, event.date.day);

    // 올해 아직 안 지났으면 올해, 지났으면 내년
    const target = thisYear >= now ? thisYear : nextYear;
    const daysUntil = Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));

    if (daysUntil <= 60) {
      upcomingEvents.push({ event, date: target, daysUntil });
    }
  }

  upcomingEvents.sort((a, b) => a.daysUntil - b.daysUntil);

  return {
    now,
    currentYear: year,
    currentMonth: month,
    currentDay: day,
    weekdayKorean: weekday + "요일",
    quarter,
    currentTaxYear: month >= 5 ? year : year - 1,  // 5월 전이면 전년도 기준
    upcomingEvents,
  };
}

// ─── 상대 시간 표현 감지 ───────────────────────────────────────

export interface TemporalReference {
  expression: string;
  absolute: {
    start: Date;
    end: Date;
  };
}

const RELATIVE_PATTERNS: Array<{
  pattern: RegExp;
  resolve: (now: Date) => { start: Date; end: Date };
}> = [
  {
    pattern: /올해|이번\s*년|금년/,
    resolve: (now) => ({
      start: new Date(now.getFullYear(), 0, 1),
      end: new Date(now.getFullYear(), 11, 31),
    }),
  },
  {
    pattern: /작년|지난\s*해|전년도/,
    resolve: (now) => ({
      start: new Date(now.getFullYear() - 1, 0, 1),
      end: new Date(now.getFullYear() - 1, 11, 31),
    }),
  },
  {
    pattern: /내년|다음\s*해/,
    resolve: (now) => ({
      start: new Date(now.getFullYear() + 1, 0, 1),
      end: new Date(now.getFullYear() + 1, 11, 31),
    }),
  },
  {
    pattern: /이번\s*달|금월/,
    resolve: (now) => ({
      start: new Date(now.getFullYear(), now.getMonth(), 1),
      end: new Date(now.getFullYear(), now.getMonth() + 1, 0),
    }),
  },
  {
    pattern: /지난\s*달|전월/,
    resolve: (now) => ({
      start: new Date(now.getFullYear(), now.getMonth() - 1, 1),
      end: new Date(now.getFullYear(), now.getMonth(), 0),
    }),
  },
  {
    pattern: /다음\s*달/,
    resolve: (now) => ({
      start: new Date(now.getFullYear(), now.getMonth() + 1, 1),
      end: new Date(now.getFullYear(), now.getMonth() + 2, 0),
    }),
  },
  {
    pattern: /오늘/,
    resolve: (now) => ({
      start: new Date(now.getFullYear(), now.getMonth(), now.getDate()),
      end: new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59),
    }),
  },
  {
    pattern: /이번\s*주/,
    resolve: (now) => {
      const start = new Date(now);
      start.setDate(now.getDate() - now.getDay());
      start.setHours(0, 0, 0, 0);
      const end = new Date(start);
      end.setDate(start.getDate() + 6);
      end.setHours(23, 59, 59);
      return { start, end };
    },
  },
  {
    pattern: /이번\s*분기/,
    resolve: (now) => {
      const quarter = Math.floor(now.getMonth() / 3);
      return {
        start: new Date(now.getFullYear(), quarter * 3, 1),
        end: new Date(now.getFullYear(), quarter * 3 + 3, 0),
      };
    },
  },
];

export function detectTemporalReferences(text: string): TemporalReference[] {
  const now = new Date();
  const refs: TemporalReference[] = [];

  for (const { pattern, resolve } of RELATIVE_PATTERNS) {
    const match = text.match(pattern);
    if (match) {
      refs.push({
        expression: match[0],
        absolute: resolve(now),
      });
    }
  }

  return refs;
}

// ─── 시스템 프롬프트 생성 ─────────────────────────────────────

export function buildTADMPrompt(
  text: string,
  context: TemporalContext = getTemporalContext()
): string {
  const refs = detectTemporalReferences(text);

  let prompt = `\n\n[TADM - 시점 인식]
- 오늘 날짜: ${context.currentYear}년 ${context.currentMonth}월 ${context.currentDay}일 (${context.weekdayKorean})
- ${context.quarter}분기, 세무 기준년도 ${context.currentTaxYear}`;

  if (refs.length > 0) {
    prompt += `\n\n[질문의 시간 표현 해석]`;
    refs.forEach((r) => {
      const start = `${r.absolute.start.getFullYear()}.${r.absolute.start.getMonth() + 1}.${r.absolute.start.getDate()}`;
      const end = `${r.absolute.end.getFullYear()}.${r.absolute.end.getMonth() + 1}.${r.absolute.end.getDate()}`;
      prompt += `\n- "${r.expression}" = ${start} ~ ${end}`;
    });
  }

  if (context.upcomingEvents.length > 0) {
    prompt += `\n\n[다가오는 한국 주요 일정]`;
    context.upcomingEvents.slice(0, 3).forEach(({ event, date, daysUntil }) => {
      const dateStr = `${date.getFullYear()}.${date.getMonth() + 1}.${date.getDate()}`;
      prompt += `\n- ${event.name} (${dateStr}, D-${daysUntil}): ${event.description}`;
    });
  }

  prompt += `\n\n[지침]
- 상대 시간 표현은 위 해석에 따라 답변
- 세무/법정 일정 질문에는 D-day 포함
- 오래된 정보(2023~2024)에 의존하지 말고 최신 기준으로 답변`;

  return prompt;
}

export function applyTADM(userMessage: string): {
  context: TemporalContext;
  references: TemporalReference[];
  systemPrompt: string;
} {
  const context = getTemporalContext();
  const references = detectTemporalReferences(userMessage);
  const systemPrompt = buildTADMPrompt(userMessage, context);
  return { context, references, systemPrompt };
}
