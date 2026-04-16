/**
 * MMRM - Multi-Memory Retention Model
 *
 * 화랑 AI 고유 정렬 기법 #9
 *
 * 계층적 메모리 시스템:
 *   Layer 1 (단기): 현재 대화 (32K 토큰)
 *   Layer 2 (중기): 최근 30일 대화 요약
 *   Layer 3 (장기): 유저 프로필
 *   Layer 4 (에피소딕): 중요 이벤트
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

// ─── 메모리 타입 정의 ──────────────────────────────────────────

export interface UserProfile {
  // 기본 정보
  occupation?: string;           // 직업 (개발자, 변호사, 학생 등)
  industry?: string;             // 업종
  techStack?: string[];          // 기술 스택 (Python, React 등)
  interests?: string[];          // 관심 도메인 (세무, 부동산 등)

  // 개인 상황
  residence?: string;            // 거주지 (강남, 판교 등)
  maritalStatus?: string;        // 결혼 상태
  hasChildren?: boolean;

  // 사업 정보
  businessType?: "개인사업자" | "법인" | "프리랜서" | "직장인";

  // 선호도
  communicationStyle?: "formal" | "casual" | "technical" | "simple";
  preferredLanguage?: "ko" | "en" | "ko_en";

  // 메타
  lastUpdated: Date;
}

export interface EpisodicMemory {
  id: string;
  userId: string;
  title: string;
  content: string;
  category: "personal" | "work" | "legal" | "tax" | "other";
  importance: number;             // 1~10
  createdAt: Date;
  referencedCount: number;        // 얼마나 자주 참조되는지
}

// ─── 대화 요약 생성 (Layer 2) ──────────────────────────────────

export async function summarizeConversation(
  userId: string,
  conversationId: string,
  vllmEndpoint: string,
  model: string
): Promise<string> {
  const conv = await prisma.conversation.findUnique({
    where: { id: conversationId },
    include: { messages: { orderBy: { createdAt: "asc" }, take: 50 } },
  });

  if (!conv || conv.messages.length === 0) return "";

  const transcript = conv.messages
    .map((m) => `${m.role}: ${m.content.slice(0, 300)}`)
    .join("\n");

  const prompt = `다음 대화를 3~5문장으로 요약하세요. 중요한 정보(날짜, 숫자, 결정사항)는 반드시 포함.

[대화]
${transcript}

[요약]`;

  try {
    const resp = await fetch(`${vllmEndpoint}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        messages: [{ role: "user", content: prompt }],
        max_tokens: 300,
        temperature: 0.3,
      }),
    });

    if (!resp.ok) return "";
    const data = await resp.json();
    return data.choices?.[0]?.message?.content || "";
  } catch {
    return "";
  }
}

// ─── 유저 프로필 추론/업데이트 ─────────────────────────────────

export async function inferUserProfile(
  userId: string,
  vllmEndpoint: string,
  model: string
): Promise<UserProfile> {
  // 최근 30일 대화에서 프로필 정보 추출
  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const conversations = await prisma.conversation.findMany({
    where: { userId, updatedAt: { gte: thirtyDaysAgo } },
    include: { messages: { take: 20, orderBy: { createdAt: "desc" } } },
    take: 20,
  });

  // 유저 발화만 추출
  const userMessages = conversations
    .flatMap((c) => c.messages)
    .filter((m) => m.role === "user")
    .map((m) => m.content.slice(0, 200))
    .slice(0, 100);

  if (userMessages.length === 0) {
    return { lastUpdated: new Date() };
  }

  const prompt = `다음 사용자의 질문/발화에서 프로필을 추론하세요. 확실하지 않으면 생략.

[사용자 발화]
${userMessages.join("\n---\n")}

[출력 JSON]
{
  "occupation": "직업 (명확할 때만)",
  "industry": "업종",
  "techStack": ["기술 스택 - 개발자인 경우"],
  "interests": ["관심 도메인"],
  "businessType": "개인사업자|법인|프리랜서|직장인",
  "communicationStyle": "formal|casual|technical|simple"
}

JSON만 출력:`;

  try {
    const resp = await fetch(`${vllmEndpoint}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        messages: [{ role: "user", content: prompt }],
        max_tokens: 500,
        temperature: 0.1,
      }),
    });

    if (!resp.ok) return { lastUpdated: new Date() };

    const data = await resp.json();
    const text = data.choices?.[0]?.message?.content || "";
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) return { lastUpdated: new Date() };

    const parsed = JSON.parse(jsonMatch[0]);
    return { ...parsed, lastUpdated: new Date() };
  } catch {
    return { lastUpdated: new Date() };
  }
}

// ─── 프로필 저장/조회 (SystemSetting에 유저별 JSON 저장) ────

export async function getUserProfile(userId: string): Promise<UserProfile | null> {
  const setting = await prisma.systemSetting.findUnique({
    where: { key: `mmrm_profile_${userId}` },
  });
  if (!setting) return null;
  try {
    return JSON.parse(setting.value);
  } catch {
    return null;
  }
}

export async function saveUserProfile(userId: string, profile: UserProfile): Promise<void> {
  await prisma.systemSetting.upsert({
    where: { key: `mmrm_profile_${userId}` },
    update: { value: JSON.stringify(profile) },
    create: { key: `mmrm_profile_${userId}`, value: JSON.stringify(profile) },
  });
}

// ─── 에피소딕 메모리 저장 ──────────────────────────────────────

export async function saveEpisodicMemory(
  memory: Omit<EpisodicMemory, "id" | "referencedCount">
): Promise<void> {
  const existing = await prisma.systemSetting.findUnique({
    where: { key: `mmrm_episodes_${memory.userId}` },
  });

  const episodes: EpisodicMemory[] = existing ? JSON.parse(existing.value) : [];
  episodes.push({
    ...memory,
    id: `ep_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    referencedCount: 0,
  });

  // 중요도 낮은 오래된 것부터 제거 (최대 50개 유지)
  episodes.sort((a, b) => b.importance - a.importance);
  const kept = episodes.slice(0, 50);

  await prisma.systemSetting.upsert({
    where: { key: `mmrm_episodes_${memory.userId}` },
    update: { value: JSON.stringify(kept) },
    create: { key: `mmrm_episodes_${memory.userId}`, value: JSON.stringify(kept) },
  });
}

export async function getEpisodicMemories(
  userId: string,
  query?: string,
  limit: number = 5
): Promise<EpisodicMemory[]> {
  const setting = await prisma.systemSetting.findUnique({
    where: { key: `mmrm_episodes_${userId}` },
  });
  if (!setting) return [];

  try {
    let episodes: EpisodicMemory[] = JSON.parse(setting.value);

    // 쿼리로 필터링 (간단한 키워드 매칭)
    if (query) {
      const queryLower = query.toLowerCase();
      episodes = episodes.filter(
        (e) =>
          e.title.toLowerCase().includes(queryLower) ||
          e.content.toLowerCase().includes(queryLower)
      );
    }

    // 중요도 순
    episodes.sort((a, b) => b.importance - a.importance);
    return episodes.slice(0, limit);
  } catch {
    return [];
  }
}

// ─── 대화 요약 히스토리 ────────────────────────────────────────

export async function getConversationSummaries(
  userId: string,
  limit: number = 5
): Promise<string[]> {
  const conversations = await prisma.conversation.findMany({
    where: { userId },
    orderBy: { updatedAt: "desc" },
    take: limit,
  });

  // 각 대화의 첫 유저 메시지로 요약 대체 (간단 버전)
  const summaries: string[] = [];
  for (const conv of conversations) {
    const firstMsg = await prisma.message.findFirst({
      where: { conversationId: conv.id, role: "user" },
      orderBy: { createdAt: "asc" },
    });
    if (firstMsg) {
      summaries.push(`[${conv.updatedAt.toISOString().split("T")[0]}] ${firstMsg.content.slice(0, 150)}`);
    }
  }

  return summaries;
}

// ─── 시스템 프롬프트 생성 (메모리 통합) ─────────────────────────

export async function buildMMRMPrompt(userId: string, currentQuery: string): Promise<string> {
  const [profile, episodes, summaries] = await Promise.all([
    getUserProfile(userId),
    getEpisodicMemories(userId, currentQuery, 3),
    getConversationSummaries(userId, 3),
  ]);

  let prompt = "\n\n[MMRM - 계층적 메모리]";

  // Layer 3: 유저 프로필
  if (profile) {
    prompt += "\n\n[사용자 프로필]";
    if (profile.occupation) prompt += `\n- 직업: ${profile.occupation}`;
    if (profile.industry) prompt += `\n- 업종: ${profile.industry}`;
    if (profile.techStack && profile.techStack.length > 0) {
      prompt += `\n- 기술 스택: ${profile.techStack.join(", ")}`;
    }
    if (profile.interests && profile.interests.length > 0) {
      prompt += `\n- 관심 도메인: ${profile.interests.join(", ")}`;
    }
    if (profile.businessType) prompt += `\n- 사업 형태: ${profile.businessType}`;
    if (profile.communicationStyle) prompt += `\n- 소통 스타일: ${profile.communicationStyle}`;
  }

  // Layer 4: 에피소딕
  if (episodes.length > 0) {
    prompt += "\n\n[과거 중요 정보]";
    episodes.forEach((ep) => {
      prompt += `\n- [${ep.createdAt.toISOString().split("T")[0]}] ${ep.title}: ${ep.content.slice(0, 150)}`;
    });
  }

  // Layer 2: 최근 대화 요약
  if (summaries.length > 0) {
    prompt += "\n\n[최근 대화 요약]";
    summaries.forEach((s) => {
      prompt += `\n- ${s}`;
    });
  }

  if (profile || episodes.length > 0 || summaries.length > 0) {
    prompt += "\n\n[지침] 위 정보를 참고하여 사용자 상황에 맞는 맞춤 답변을 제공하세요. 단, 위 정보를 직접 인용하지 말고 자연스럽게 반영하세요.";
  }

  return prompt;
}

export async function applyMMRM(userId: string, userMessage: string): Promise<{
  systemPrompt: string;
  profile: UserProfile | null;
  episodes: EpisodicMemory[];
}> {
  const [profile, episodes] = await Promise.all([
    getUserProfile(userId),
    getEpisodicMemories(userId, userMessage, 3),
  ]);

  const systemPrompt = await buildMMRMPrompt(userId, userMessage);
  return { systemPrompt, profile, episodes };
}
