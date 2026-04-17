/**
 * API 문서 (OpenAPI/Swagger 스타일)
 *
 * GET /api/docs - API 스펙 JSON
 */

export async function GET() {
  const spec = {
    openapi: "3.0.0",
    info: {
      title: "Hwarang AI API",
      version: "1.0.0",
      description: "화랑 AI 서비스 API. OpenAI 호환 엔드포인트 + 화랑 전용 기능.",
      contact: { email: "api@persismore.com", url: "https://hwarang.ai" },
    },
    servers: [
      { url: "https://hwarang.ai/api", description: "프로덕션" },
      { url: "http://localhost:3000/api", description: "로컬 개발" },
    ],
    paths: {
      "/chat": {
        post: {
          summary: "AI 채팅 (OpenAI 호환)",
          description: "메시지 전송 → AI 응답. 스트리밍 지원. 26개 정렬 기법 자동 적용.",
          tags: ["Chat"],
          requestBody: {
            content: { "application/json": { schema: { $ref: "#/components/schemas/ChatRequest" } } },
          },
          responses: {
            200: { description: "성공", content: { "application/json": { schema: { $ref: "#/components/schemas/ChatResponse" } } } },
            401: { description: "인증 필요" },
            402: { description: "토큰 부족" },
            429: { description: "일일 한도 초과" },
          },
        },
      },
      "/users/me": {
        get: { summary: "내 정보 + 토큰 잔액", tags: ["User"] },
      },
      "/payment": {
        post: { summary: "결제 요청 (토스페이먼츠)", tags: ["Payment"] },
        get: { summary: "결제 내역", tags: ["Payment"] },
      },
      "/payment/confirm": {
        post: { summary: "결제 승인 (토스 콜백)", tags: ["Payment"] },
      },
      "/feedback": {
        post: { summary: "AI 응답 피드백 (👍/👎) → GRPO 토큰 보상", tags: ["Feedback"] },
      },
      "/referral": {
        get: { summary: "내 추천 코드 + 통계", tags: ["Referral"] },
        post: { summary: "추천 코드 적용 (3000 토큰 보상)", tags: ["Referral"] },
      },
      "/notifications": {
        get: { summary: "알림 목록", tags: ["Notification"] },
        put: { summary: "읽음 처리", tags: ["Notification"] },
      },
      "/multimodal": {
        post: { summary: "이미지 + 텍스트 → AI 분석 (EXAONE 멀티모달)", tags: ["Multimodal"] },
      },
      "/voice": {
        post: { summary: "음성 입출력 (STT/TTS)", tags: ["Voice"] },
      },
      "/plugins": {
        get: { summary: "플러그인 카탈로그", tags: ["Plugin"] },
        post: { summary: "플러그인 설치/제거", tags: ["Plugin"] },
      },
      "/team": {
        get: { summary: "팀 목록", tags: ["Team"] },
        post: { summary: "팀 생성", tags: ["Team"] },
      },
      "/integrations/slack": {
        post: { summary: "Slack 봇 이벤트 수신", tags: ["Integration"] },
      },
      "/integrations/discord": {
        post: { summary: "Discord 봇 인터랙션", tags: ["Integration"] },
      },
      "/integrations/webhook": {
        post: { summary: "범용 Webhook (Notion, GitHub 등)", tags: ["Integration"] },
      },
      "/legal": {
        get: { summary: "이용약관/개인정보처리방침", tags: ["Legal"] },
      },
    },
    components: {
      schemas: {
        ChatRequest: {
          type: "object",
          properties: {
            model: { type: "string", description: "모델 이름 (자동 선택 가능)", example: "hwarang-pro" },
            messages: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  role: { type: "string", enum: ["system", "user", "assistant"] },
                  content: { type: "string" },
                },
              },
            },
            stream: { type: "boolean", default: false },
            max_tokens: { type: "integer", default: 2048 },
            temperature: { type: "number", default: 0.7 },
          },
          required: ["messages"],
        },
        ChatResponse: {
          type: "object",
          properties: {
            choices: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  message: {
                    type: "object",
                    properties: {
                      role: { type: "string" },
                      content: { type: "string" },
                    },
                  },
                },
              },
            },
            usage: {
              type: "object",
              properties: {
                prompt_tokens: { type: "integer" },
                completion_tokens: { type: "integer" },
                total_tokens: { type: "integer" },
              },
            },
            _meta: {
              type: "object",
              description: "화랑 전용 메타데이터 (모델, 토큰, 정렬 정보)",
            },
          },
        },
      },
      securitySchemes: {
        BearerAuth: {
          type: "http",
          scheme: "bearer",
          description: "API 키 (hk-xxx) 또는 세션 토큰",
        },
      },
    },
    security: [{ BearerAuth: [] }],
  };

  return Response.json(spec);
}
