/**
 * 플러그인 시스템 API
 *
 * GET    /api/plugins          - 사용 가능한 플러그인 목록
 * POST   /api/plugins/install  - 플러그인 설치
 * DELETE /api/plugins          - 플러그인 제거
 *
 * 플러그인 유형:
 *   - 도구 (Tool): AI가 호출할 수 있는 외부 도구
 *   - 테마 (Theme): UI 커스터마이징
 *   - 데이터 소스 (DataSource): RAG용 데이터 연결
 *   - 모델 (Model): 커스텀 모델/LoRA 추가
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";

// 기본 플러그인 카탈로그
const PLUGIN_CATALOG = [
  {
    id: "calculator",
    name: "계산기",
    description: "복잡한 수학 계산, 환율 변환, 단위 변환",
    type: "tool",
    version: "1.0.0",
    author: "Hwarang",
    installed: true,  // 기본 설치
  },
  {
    id: "law_search",
    name: "법령 검색",
    description: "한국 법제처 법령/판례 실시간 검색 (HRAG)",
    type: "tool",
    version: "1.0.0",
    author: "Hwarang",
    installed: true,
  },
  {
    id: "web_search",
    name: "웹 검색",
    description: "실시간 웹 검색 (네이버/구글)",
    type: "tool",
    version: "1.0.0",
    author: "Hwarang",
    installed: false,
    requiresKey: "NAVER_CLIENT_ID",
  },
  {
    id: "code_exec",
    name: "코드 실행",
    description: "Python 코드 샌드박스 실행",
    type: "tool",
    version: "1.0.0",
    author: "Hwarang",
    installed: false,
    requiresKey: "PYTHON_SANDBOX_URL",
  },
  {
    id: "notion_sync",
    name: "Notion 연동",
    description: "Notion 페이지를 RAG 데이터로 자동 동기화",
    type: "datasource",
    version: "1.0.0",
    author: "Hwarang",
    installed: false,
    requiresKey: "NOTION_API_KEY",
  },
  {
    id: "slack_bot",
    name: "Slack 봇",
    description: "Slack 채널에서 화랑 AI 사용",
    type: "tool",
    version: "1.0.0",
    author: "Hwarang",
    installed: false,
    requiresKey: "SLACK_BOT_TOKEN",
  },
  {
    id: "discord_bot",
    name: "Discord 봇",
    description: "Discord 서버에서 /hwarang 명령어",
    type: "tool",
    version: "1.0.0",
    author: "Hwarang",
    installed: false,
    requiresKey: "DISCORD_BOT_TOKEN",
  },
  {
    id: "image_analysis",
    name: "이미지 분석",
    description: "이미지 업로드 → AI 분석 (EXAONE 4.5 멀티모달)",
    type: "tool",
    version: "1.0.0",
    author: "Hwarang",
    installed: true,
  },
  {
    id: "voice_io",
    name: "음성 입출력",
    description: "음성으로 질문, 음성으로 답변 (STT/TTS)",
    type: "tool",
    version: "1.0.0",
    author: "Hwarang",
    installed: false,
  },
];

export async function GET() {
  return Response.json({ plugins: PLUGIN_CATALOG });
}

export async function POST(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return Response.json({ error: "로그인 필요" }, { status: 401 });

  const { pluginId, action } = await request.json();

  if (action === "install") {
    const plugin = PLUGIN_CATALOG.find((p) => p.id === pluginId);
    if (!plugin) return Response.json({ error: "플러그인 없음" }, { status: 404 });

    // 유저별 설치 기록
    const key = `plugins_${session.user.id}`;
    const setting = await prisma.systemSetting.findUnique({ where: { key } });
    const installed = setting ? JSON.parse(setting.value) : [];

    if (!installed.includes(pluginId)) {
      installed.push(pluginId);
      await prisma.systemSetting.upsert({
        where: { key },
        update: { value: JSON.stringify(installed) },
        create: { key, value: JSON.stringify(installed) },
      });
    }

    return Response.json({ success: true, installed: pluginId });
  }

  return Response.json({ error: "알 수 없는 action" }, { status: 400 });
}
