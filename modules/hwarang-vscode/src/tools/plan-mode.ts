/**
 * Plan 모드 — 대규모 작업 사전 합의 매니저
 *
 * 동작:
 * 1. 사용자 메시지가 multi-step / multi-file 인지 휴리스틱으로 판단
 * 2. LLM 으로 plan (단계 목록) 생성
 * 3. webview 에 승인 요청 → 사용자 ✓진행 / 수정 / 취소
 * 4. 승인된 plan 을 system 메시지로 conversationHistory 에 주입
 *
 * 다른 그룹 (chat-view-provider) 과의 인터페이스:
 * - 송신: postMessage({ type: "planApprovalRequest", plan, requestId })
 * - 수신: webview → extension 의 message {type:"planResponse", approved, modifiedPlan?}
 */

import { ChatMessage, LLMClient } from "../providers/llm-client";

export interface PlanItem {
  id: string;
  title: string;
  description?: string;
  /** 이 step 에서 사용 예상되는 도구 이름 목록 */
  estimatedTools: string[];
  /** 위험도 (UI 색상/경고 표시에 활용) */
  riskLevel: "low" | "medium" | "high";
}

export interface PlanApproval {
  approved: boolean;
  modifiedPlan?: PlanItem[];
}

/**
 * webview 와의 최소 인터페이스 — postMessage / onDidReceiveMessage 만 사용.
 */
export interface PlanWebviewBridge {
  postMessage(message: any): Thenable<boolean> | boolean;
  onDidReceiveMessage(listener: (msg: any) => any): { dispose(): void };
}

const PLAN_KEYWORDS_KO = [
  "결제",
  "인증",
  "회원가입",
  "로그인",
  "리팩토링",
  "마이그레이션",
  "전체",
  "시스템",
  "통합",
  "배포",
  "테스트 전체",
  "전체 테스트",
  "DB 스키마",
  "스키마",
  "모듈",
  "프로젝트",
];

const PLAN_KEYWORDS_EN = [
  "refactor",
  "migration",
  "migrate",
  "implement",
  "integrate",
  "system",
  "deploy",
  "redesign",
  "rewrite",
];

const RISK_KEYWORDS_KO = [
  "마이그레이션",
  "삭제",
  "DB",
  "데이터베이스",
  "schema",
  "스키마",
  "패키지 설치",
  "install",
  "deploy",
  "배포",
];

const PLAN_TRIGGER_RE_KO =
  /(plan\s*(보여|먼저|짜)|계획\s*(먼저|보여|짜))/i;
const PLAN_TRIGGER_RE_EN = /(\/plan|show\s+plan|plan\s+first)/i;

export class PlanModeManager {
  /**
   * Plan 모드 진입 휴리스틱.
   *
   * 진입 조건 (OR):
   * - 명시적 요청 (/plan, "계획 먼저", "plan 보여줘")
   * - 위험 키워드 (DB 마이그레이션, 패키지 설치 등) + 작업 요청 동사
   * - 다중 도메인 키워드 (UI/API/DB 등을 동시에 언급)
   * - 메시지가 길고 (200자 이상) 작업 요청 동사 + 4단계 이상 추정 키워드
   *
   * 짧은 단순 작업 ("test.txt 에 hello 써줘") 은 false 반환.
   */
  shouldEnterPlanMode(userMessage: string, _history: ChatMessage[]): boolean {
    if (!userMessage) return false;
    const t = userMessage.replace(/^\[[^\]]+\]\s*/g, "").trim();
    if (t.length === 0) return false;

    // 명시적 요청
    if (PLAN_TRIGGER_RE_KO.test(t) || PLAN_TRIGGER_RE_EN.test(t)) return true;

    // 단순 단일 파일 작업 — 빠르게 false (사용자 흐름 방해 방지)
    if (t.length < 30) return false;

    // 작업 요청 동사 검사
    const actionKo =
      /(해줘|해주세요|만들어|구현|추가|개선|리팩토|수정|업데이트|작성|디자인|배포)/;
    const actionEn =
      /\b(create|build|add|implement|refactor|update|integrate|deploy|design|migrate|setup|set up)\b/i;
    const isAction = actionKo.test(t) || actionEn.test(t);
    if (!isAction) return false;

    // 위험 키워드
    const hasRisk =
      RISK_KEYWORDS_KO.some((k) => t.includes(k)) ||
      /\b(migrate|migration|deploy|install|drop\s+table)\b/i.test(t);

    // 도메인 키워드 카운트 (multi-domain 추정)
    const domainHits = [
      /API|api|라우터|router|endpoint|엔드포인트/,
      /UI|ui|컴포넌트|component|프론트|front|페이지|page/,
      /DB|db|데이터베이스|database|prisma|schema|스키마|모델|model/,
      /webhook|훅|이벤트|event/,
      /테스트|test|spec/,
      /환경변수|env|환경 변수/,
      /설치|install|패키지|package|sdk|SDK/,
    ].filter((re) => re.test(t)).length;

    // 4단계 이상 추정 — 명시 키워드 OR 도메인 3개 이상
    const hasMultiStep =
      PLAN_KEYWORDS_KO.some((k) => t.includes(k)) ||
      PLAN_KEYWORDS_EN.some((k) => new RegExp(`\\b${k}\\b`, "i").test(t)) ||
      domainHits >= 3;

    if (hasRisk && isAction) return true;
    if (hasMultiStep && t.length >= 30) return true;
    if (domainHits >= 2 && t.length >= 60) return true;

    return false;
  }

  /**
   * LLM 호출하여 plan 생성. 실패 시 빈 배열.
   */
  async generatePlan(
    userMessage: string,
    llm: LLMClient
  ): Promise<PlanItem[]> {
    const sys: ChatMessage = {
      role: "system",
      content:
        "당신은 화랑 코딩 어시스턴트의 Plan 작성기입니다.\n" +
        "사용자 요청을 받아 실행 가능한 step 목록을 JSON 배열로만 반환하세요.\n" +
        "각 step 은 한 가지 책임만 갖고, 3~8 단계가 적절합니다.\n" +
        "스키마: [{\"id\":\"1\",\"title\":\"짧은 한국어 제목\",\"description\":\"세부 설명\",\"estimatedTools\":[\"write_file\",\"run_command\"],\"riskLevel\":\"low|medium|high\"}, ...]\n" +
        "도구 목록: read_file, write_file, edit_file, delete_file, run_command, run_command_background, search_files, list_directory, get_diagnostics, write_todo, delegate_subtask\n" +
        "응답은 JSON 배열만, 다른 텍스트 금지.",
    };
    const usr: ChatMessage = {
      role: "user",
      content: `다음 요청에 대한 plan 을 JSON 배열로 만들어주세요:\n\n${userMessage}`,
    };

    try {
      const resp = await llm.chat([sys, usr]);
      const text = resp.content || "";
      const parsed = extractJsonArray(text);
      if (!Array.isArray(parsed) || parsed.length === 0) return [];

      return parsed
        .map((p: any, idx: number) => ({
          id: String(p.id || idx + 1),
          title: String(p.title || `Step ${idx + 1}`),
          description: p.description ? String(p.description) : undefined,
          estimatedTools: Array.isArray(p.estimatedTools)
            ? p.estimatedTools.map(String)
            : [],
          riskLevel:
            p.riskLevel === "high" || p.riskLevel === "medium"
              ? p.riskLevel
              : "low",
        }))
        .slice(0, 12);
    } catch (e) {
      console.warn("[PlanMode] generatePlan 실패:", e);
      return [];
    }
  }

  /**
   * webview 에 승인 요청 후 응답 대기 (Promise).
   * 60초 타임아웃 시 거부 처리.
   */
  async requestApproval(
    plan: PlanItem[],
    bridge: PlanWebviewBridge | null
  ): Promise<PlanApproval> {
    if (!bridge) {
      // bridge 없으면 자동 승인 (CLI / 테스트 환경)
      return { approved: true };
    }

    return new Promise<PlanApproval>((resolve) => {
      const requestId = `plan-${Date.now()}`;
      let settled = false;

      const disposable = bridge.onDidReceiveMessage((msg: any) => {
        if (!msg || msg.type !== "planResponse") return;
        if (msg.requestId && msg.requestId !== requestId) return;
        if (settled) return;
        settled = true;
        disposable.dispose();
        resolve({
          approved: !!msg.approved,
          modifiedPlan: Array.isArray(msg.modifiedPlan)
            ? msg.modifiedPlan
            : undefined,
        });
      });

      bridge.postMessage({
        type: "planApprovalRequest",
        requestId,
        plan,
      });

      // 타임아웃 — 5분
      setTimeout(() => {
        if (settled) return;
        settled = true;
        disposable.dispose();
        resolve({ approved: false });
      }, 300_000);
    });
  }
}

/**
 * LLM 응답 텍스트에서 첫 JSON 배열 추출.
 * 코드블록 / 그냥 텍스트 둘 다 지원.
 */
function extractJsonArray(text: string): any {
  if (!text) return null;
  // 1. 코드블록 우선
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (fenced) {
    try {
      return JSON.parse(fenced[1]);
    } catch {
      /* ignore */
    }
  }
  // 2. 첫 [ ... ] 블록
  const start = text.indexOf("[");
  const end = text.lastIndexOf("]");
  if (start >= 0 && end > start) {
    try {
      return JSON.parse(text.slice(start, end + 1));
    } catch {
      /* ignore */
    }
  }
  return null;
}
