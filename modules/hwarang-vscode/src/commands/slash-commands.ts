/**
 * Slash Commands - 자주 쓰는 워크플로우를 1초 단축.
 *
 * 입력창에 `/` 로 시작하면 expandSlashCommand 가 풀어 본문 prompt 로 변환.
 * webview 의 자동완성 드롭다운이 SLASH_COMMANDS 의 이름/설명을 그대로 표시.
 *
 * 특수값:
 *   - "__CLEAR__" : history 초기화 신호 (chat-view-provider 에서 처리)
 *   - "[/plan] ..." : Plan 모드 강제 진입 (agent-loop 가 prefix 감지)
 */

export interface SlashCommandContext {
  /** 현재 활성 파일의 워크스페이스 상대 경로. */
  activeFile?: string;
  /** 사용자가 선택한 코드 (있으면 prompt 에 fenced 로 삽입). */
  selection?: string;
  /** 현재 파일의 언어 ID (typescript/python/...) — 코드 펜스에 활용. */
  languageId?: string;
}

export interface SlashCommand {
  name: string;
  description: string;
  /**
   * args = `/cmd <args>` 의 args 부분. context 는 active editor 정보.
   * "__CLEAR__" 같은 특수 토큰을 반환할 수도 있음.
   */
  expand: (args: string, context: SlashCommandContext) => string;
}

/** 선택 영역이 있으면 fenced code block 으로 감싸서 반환. 없으면 빈 문자열. */
function selectionBlock(ctx: SlashCommandContext): string {
  if (!ctx.selection) return "";
  const lang = ctx.languageId || "";
  return `\n\n\`\`\`${lang}\n${ctx.selection}\n\`\`\``;
}

/** active file 표기 ("현재 파일") — 없으면 "현재 파일". */
function fileLabel(ctx: SlashCommandContext): string {
  return ctx.activeFile ? `${ctx.activeFile}` : "현재 파일";
}

export const SLASH_COMMANDS: Record<string, SlashCommand> = {
  explain: {
    name: "explain",
    description: "선택한 코드 설명",
    expand: (args, ctx) => {
      const tail = args ? `\n추가 요청: ${args}` : "";
      if (ctx.selection) {
        return `다음 코드를 한국어로 자세히 설명해주세요.${selectionBlock(ctx)}${tail}`;
      }
      return `${fileLabel(ctx)} 의 코드를 한국어로 설명해주세요. read_file 로 파일을 읽고 분석하세요.${tail}`;
    },
  },

  fix: {
    name: "fix",
    description: "현재 파일 버그 찾아 수정",
    expand: (args, ctx) =>
      `${fileLabel(ctx)} 의 버그를 찾아 수정해주세요.${args ? "\n요청: " + args : ""}\n` +
      `read_file 로 파일을 읽고, 문제를 발견하면 edit_file 로 수정하세요.`,
  },

  refactor: {
    name: "refactor",
    description: "선택한 코드 리팩토링",
    expand: (args, ctx) => {
      const target = ctx.selection ? "선택된 코드" : `${fileLabel(ctx)} 전체`;
      const tail = args ? `\n요청: ${args}` : "";
      return (
        `${target} 를 리팩토링해주세요.${selectionBlock(ctx)}${tail}\n` +
        `read_file 로 현재 코드 확인 후 edit_file 로 개선을 적용하세요. ` +
        `기능 변경 없이 가독성과 구조만 개선합니다.`
      );
    },
  },

  test: {
    name: "test",
    description: "유닛 테스트 생성",
    expand: (args, ctx) => {
      const file = ctx.activeFile || "현재 파일";
      const testFile = ctx.activeFile
        ? ctx.activeFile.replace(/\.(ts|tsx|js|jsx|py)$/, (m) => `.test${m}`)
        : "(파일명).test.(확장자)";
      return (
        `${file} 에 대한 유닛 테스트를 작성해주세요.${args ? "\n요청: " + args : ""}\n` +
        `테스트 파일 (${testFile}) 을 write_file 로 생성하세요. ` +
        `엣지 케이스, 정상 흐름, 에러 흐름을 모두 포함합니다.`
      );
    },
  },

  doc: {
    name: "doc",
    description: "문서/주석 추가",
    expand: (args, ctx) =>
      `${fileLabel(ctx)} 의 함수/클래스에 한국어 docstring/주석을 추가해주세요.${args ? "\n요청: " + args : ""}\n` +
      `read_file 로 읽고 edit_file 로 주석을 삽입하세요. 코드 동작은 변경하지 마세요.`,
  },

  review: {
    name: "review",
    description: "코드 리뷰",
    expand: (args, ctx) =>
      `${fileLabel(ctx)} 코드 리뷰를 진행해주세요.\n` +
      `다음 관점에서 분석:\n` +
      `- 가독성 / 네이밍\n` +
      `- 성능 / 메모리\n` +
      `- 보안 (XSS, SQLi, 비밀키 노출 등)\n` +
      `- 에러 처리\n` +
      `${args ? "추가 요청: " + args + "\n" : ""}` +
      `read_file 로 읽고 한국어로 분석 결과를 제시하세요.`,
  },

  optimize: {
    name: "optimize",
    description: "성능 최적화 제안",
    expand: (args, ctx) =>
      `${fileLabel(ctx)} 의 성능을 최적화해주세요.${args ? "\n요청: " + args : ""}\n` +
      `read_file 로 분석 → 병목 식별 → edit_file 로 개선 적용. ` +
      `기능은 동일하게 유지하세요.`,
  },

  translate: {
    name: "translate",
    description: "다른 언어로 변환 (예: /translate python)",
    expand: (args, ctx) => {
      const targetLang = (args.trim().split(/\s+/)[0] || "python").toLowerCase();
      return (
        `${fileLabel(ctx)} 를 ${targetLang} 로 변환해주세요. ` +
        `read_file 로 원본을 읽고, 변환된 코드를 새 파일로 write_file 하세요. ` +
        `의미는 보존하고, 대상 언어의 관용에 맞게 작성합니다.`
      );
    },
  },

  diagnose: {
    name: "diagnose",
    description: "빌드/lint 에러 자동 분석",
    expand: (args, ctx) =>
      `현재 워크스페이스의 빌드/lint 에러를 진단해주세요.${args ? "\n요청: " + args : ""}\n` +
      `get_diagnostics 호출 → 에러 분석 → 자동 수정 시도 (edit_file).`,
  },

  commit: {
    name: "commit",
    description: "git status 확인 후 자동 커밋",
    expand: (args, _ctx) =>
      `git status 와 git diff 를 확인해 변경사항을 분석하고, ` +
      `한국어로 적절한 커밋 메시지를 만들어 git commit 까지 실행해주세요.${args ? "\n추가 지시: " + args : ""}\n` +
      `필요 시 run_command 로 git 명령을 실행합니다.`,
  },

  plan: {
    name: "plan",
    description: "Plan 모드 강제 진입",
    expand: (args, _ctx) => `[/plan] ${args || "작업을 plan 모드로 진행"}`,
  },

  clear: {
    name: "clear",
    description: "대화 history 초기화",
    expand: () => "__CLEAR__",
  },
};

/**
 * 입력 문자열이 슬래시 커맨드면 풀어서 prompt 로 반환.
 * 슬래시가 아니거나 매칭 실패면 null.
 *
 * 결과가 "__CLEAR__" 면 호출자가 history 를 비워야 함.
 */
export function expandSlashCommand(
  input: string,
  context: SlashCommandContext
): string | null {
  if (!input || !input.startsWith("/")) return null;
  const match = input.match(/^\/(\w+)\s*(.*)$/s);
  if (!match) return null;
  const cmd = SLASH_COMMANDS[match[1].toLowerCase()];
  if (!cmd) return null;
  return cmd.expand(match[2] || "", context);
}

/** webview UI 자동완성용 메타. */
export function getSlashCommandList(): {
  name: string;
  description: string;
}[] {
  return Object.values(SLASH_COMMANDS).map((c) => ({
    name: c.name,
    description: c.description,
  }));
}
