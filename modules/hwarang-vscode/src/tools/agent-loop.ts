/**
 * Agent Loop - ReAct-style tool-using agent (Claude Code equivalent)
 *
 * Flow:
 * 1. User message + workspace context → LLM
 * 2. LLM returns tool calls → execute → feed back → loop
 * 3. LLM returns text → final answer
 *
 * Features:
 * - Multi-turn with full history
 * - Automatic context injection (file, selection, workspace)
 * - Abort support
 * - Token usage tracking
 */

import * as vscode from "vscode";
import { LLMClient, ChatMessage, ToolCall } from "../providers/llm-client";
import { ToolExecutor, TOOL_DEFINITIONS } from "./executor";
import { getMode, getSystemPromptAddition } from "./mode";
import { detectWorkspaceContext, invalidateWorkspaceContextCache } from "../utils/workspace-context";
import { PlanModeManager, PlanWebviewBridge } from "./plan-mode";
import { ContextCompactor } from "./context-compact";

const MAX_ITERATIONS = 12;
const MAX_FALLBACK_SYNTH = 5; // run() 한 번에 fallback 합성 최대 횟수
const MAX_SUBAGENT_ITERATIONS = 8; // sub-agent 의 자체 iteration 제한

/**
 * 응답 signature — 코드블록/특수문자/숫자 제거 후 단어 set 만 추출.
 * jaccard 유사도 비교용.
 */
function makeResponseSignature(text: string): Set<string> {
  if (!text) return new Set();
  const cleaned = text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[`*_~#>\[\]()]/g, " ")
    .replace(/[0-9]+/g, " ")
    .toLowerCase();
  const words = cleaned.split(/\s+/).filter((w) => w.length >= 2);
  return new Set(words);
}

function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let intersect = 0;
  for (const x of a) if (b.has(x)) intersect++;
  const union = a.size + b.size - intersect;
  return union === 0 ? 0 : intersect / union;
}

/**
 * "결론/마무리 시그널" 감지 — LLM 이 명시적으로 답변을 마무리한 경우 즉시 종료.
 *
 * 매치 시 가드/fallback 모두 발동 안 하고 final 처리.
 * 예: "최종 결론입니다", "이해하셨나요?", "더 궁금한 부분이 있으시면", "Hope this helps".
 */
function isConclusionSignal(text: string): boolean {
  if (!text) return false;
  const ko =
    /(최종\s*(분석|결론|결과|정리|요약)|분석\s*완료|이해\s*(하|되)?셨나요|이해\s*하셨|이해\s*되셨|더\s*궁금|추가\s*질문|말씀해\s*주세요|도움이\s*되|물어보세요|언제든지|이상입니다|마치겠습니다|정리하면|요약하면)/;
  const en =
    /\b(final\s*(analysis|conclusion|summary|result)|let me know if|hope this helps|in conclusion|to summarize|that('s| is) all|in summary|feel free to ask)/i;
  return ko.test(text) || en.test(text);
}

/**
 * "행위 약속만 한 응답" 감지 — 도돌이표 가드용.
 *
 * 예: "리팩토링하겠습니다", "수정하겠습니다", "I will refactor..."
 * 짧고 (300자 미만), 미래형 약속만 있고 코드/구조적 출력이 없는 경우 true.
 */
function isLikelyActionPromise(text: string): boolean {
  if (!text) return false;
  const t = text.trim();
  if (t.length === 0) return false;

  // 코드블록 제거 후 plain text 만 추출 (약속 패턴 검사용)
  const plain = t.replace(/```[\s\S]*?```/g, " ").trim();
  if (plain.length === 0 || plain.length > 600) return false;

  const ko =
    /(하겠습니다|할게요|진행하겠|만들겠|수정하겠|개선하겠|리팩토링하겠|시작하겠|작성하겠|업데이트하겠|만들어드리겠|생성하겠|확인하겠|살펴보겠)/;
  const en =
    /\b(I('ll| will)|let me|going to)\s+(refactor|create|modify|update|fix|implement|improve|write|edit|generate|set up|configure)/i;
  const apology = /(죄송|sorry)/i;

  const hasPromise =
    ko.test(plain) || en.test(plain) || (apology.test(plain) && plain.length < 150);
  if (!hasPromise) return false;

  // 코드블록 검사 — 진짜 결과물 코드면 약속 아님 (이미 작업 완료한 상태)
  const codeBlocks = t.match(/```[\s\S]*?```/g);
  if (codeBlocks && codeBlocks.length > 0) {
    const allCode = codeBlocks.join("\n");
    // 진짜 코드 패턴: 변수 할당, 함수 정의, import, HTML/JSX 태그 등
    const realCodeIndicators =
      /(\w+\s*=\s*['"`\d{[]|function\s+\w|class\s+\w+|import\s+\w|export\s+|def\s+\w|fn\s+\w|public\s+|private\s+|<\/?\w+[^>]*>|return\s+|<!DOCTYPE|@media|\$\w+\s*=)/;
    // step/안내 패턴: "1. xxx", "Step 1:", "## 1)"
    const stepIndicators = /^\s*(\d+[.)]\s|Step\s*\d|##\s*\d|---|====)/m;

    const isRealCode = realCodeIndicators.test(allCode);
    const isStepOnly = stepIndicators.test(allCode) && !isRealCode;

    if (isRealCode && !isStepOnly) {
      return false; // 진짜 결과물 코드 — 가드 안 발동
    }
    // step/설명만 있는 블록은 여전히 약속으로 간주 (가드 발동)
  }

  return true;
}

/**
 * LLM 응답에서 첫 큰 코드 블록 + 컨텍스트의 활성 파일을 매칭하여
 * write_file 인자를 합성한다. 매칭 실패 시 null.
 *
 * 코드 블록과 파일 확장자가 합리적으로 매칭될 때만 동작 (안전성):
 *   - ```html```  → .html / .htm
 *   - ```typescript / ts``` → .ts / .tsx
 *   - ```javascript / js``` → .js / .jsx
 *   - ```python / py``` → .py
 *   - ```css```   → .css
 *   - ```json```  → .json
 *   - ```bash / sh``` → .sh
 *   - 언어 미지정 단일 큰 블록 → 활성 파일 확장자 무관 적용 (200자 이상일 때)
 */
function trySynthesizeWriteFile(
  llmResponse: string,
  history: ChatMessage[]
): { path: string; content: string } | null {
  if (!llmResponse) return null;

  // 1. 코드 블록 추출 — 가장 큰 것 1개
  const blocks = extractFencedCodeBlocks(llmResponse);
  if (blocks.length === 0) return null;

  const biggest = blocks.reduce((a, b) =>
    b.code.length > a.code.length ? b : a
  );
  if (biggest.code.length < 50) return null; // 너무 작으면 합성 안 함

  // 2. 컨텍스트에서 활성 파일 추출 — 3단계 fallback
  //    a) buildContext() 의 "[Active file: src/index.html ...]" prepend
  //    b) LLM 응답에서 명시된 파일명 (예: "style.css 를 보고 있습니다")
  //    c) 사용자 메시지에서 명시된 파일명
  const userMsgs = history.filter((m) => m.role === "user");
  let activeFile: string | null = null;
  for (let i = userMsgs.length - 1; i >= 0; i--) {
    const m = userMsgs[i].content;
    const match = m.match(/\[Active file:\s*([^\s\(\]]+)/);
    if (match) {
      activeFile = match[1];
      break;
    }
  }

  // (b) LLM 응답 자체에서 파일명 추출
  if (!activeFile) {
    const filesInLlm = extractMentionedFiles(llmResponse);
    if (filesInLlm.length > 0) {
      // 코드블록 언어와 매칭되는 첫 파일 선택 (안전성)
      const lang = (biggest.lang || "").toLowerCase();
      activeFile =
        filesInLlm.find((f) => {
          const fl = f.toLowerCase();
          if (!lang) return true;
          return (
            (lang === "html" && (fl.endsWith(".html") || fl.endsWith(".htm"))) ||
            (lang === "css" && fl.endsWith(".css")) ||
            ((lang === "js" || lang === "javascript") && (fl.endsWith(".js") || fl.endsWith(".mjs"))) ||
            ((lang === "ts" || lang === "typescript") && (fl.endsWith(".ts") || fl.endsWith(".tsx"))) ||
            (lang === "py" || lang === "python") && fl.endsWith(".py") ||
            (lang === "json" && fl.endsWith(".json"))
          );
        }) || filesInLlm[0];
    }
  }

  // (c) 사용자 메시지에서 파일명 추출
  if (!activeFile) {
    for (let i = userMsgs.length - 1; i >= 0; i--) {
      const filesInUser = extractMentionedFiles(userMsgs[i].content);
      if (filesInUser.length > 0) {
        activeFile = filesInUser[0];
        break;
      }
    }
  }

  if (!activeFile) return null;

  // 3. 언어/확장자 매칭 검사 (안전 가드)
  const extLangMap: Record<string, string[]> = {
    html: [".html", ".htm"],
    htm: [".html", ".htm"],
    typescript: [".ts", ".tsx"],
    ts: [".ts", ".tsx"],
    tsx: [".tsx"],
    javascript: [".js", ".jsx", ".mjs"],
    js: [".js", ".jsx", ".mjs"],
    jsx: [".jsx"],
    python: [".py"],
    py: [".py"],
    css: [".css"],
    scss: [".scss"],
    json: [".json"],
    bash: [".sh"],
    sh: [".sh"],
    yaml: [".yml", ".yaml"],
    yml: [".yml", ".yaml"],
    md: [".md"],
    markdown: [".md"],
    rust: [".rs"],
    rs: [".rs"],
    go: [".go"],
    java: [".java"],
  };

  const lang = (biggest.lang || "").toLowerCase();
  if (lang && extLangMap[lang]) {
    const ok = extLangMap[lang].some((ext) =>
      activeFile!.toLowerCase().endsWith(ext)
    );
    if (!ok) return null; // 언어/확장자 불일치 → 합성 안 함
  } else if (lang) {
    // 알 수 없는 언어 → 합성 안 함 (안전)
    return null;
  } else if (biggest.code.length < 200) {
    // 언어 미지정 + 작은 블록 → 합성 안 함
    return null;
  }

  return { path: activeFile, content: biggest.code };
}

interface FencedBlock {
  lang: string;
  code: string;
}

function extractFencedCodeBlocks(text: string): FencedBlock[] {
  const out: FencedBlock[] = [];
  // ```lang\n ... \n```  (lang 옵션)
  const re = /```([a-zA-Z0-9_+-]*)\n([\s\S]*?)\n```/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    out.push({ lang: m[1] || "", code: m[2] });
  }
  return out;
}

/**
 * 사용자 메시지에서 "읽기/탐색" 의도 감지.
 * - "list" : 디렉토리 둘러보기 (프로젝트 파악, 구조 보기)
 * - "read" : 특정 파일 내용 읽기 (이 파일 분석, 이거 뭐임)
 * - null  : read 의도 아님
 */
function detectReadIntent(text: string): "list" | "read" | "list-deep" | null {
  if (!text) return null;
  const cleaned = text.replace(/^\[[^\]]+\]\s*/g, "").trim();

  // 더 깊이/자세히/recursive 탐색 (assistant 후속 약속 패턴 포함)
  const deepKo = /(더 깊이|더 자세히|조금 더|recursive|하위|내부|세부|subdirectory)/;
  const deepEn = /\b(deeper|more detail|recursive|drill down|inside|subdir)/i;
  if (deepKo.test(cleaned) || deepEn.test(cleaned)) return "list-deep";

  // 프로젝트/디렉토리 탐색 의도
  const listKo =
    /(파악|구조|살펴|훑어|개요|전체.*보|뭐가.*있|어떤.*있|디렉토리|폴더|프로젝트.*보)/;
  const listEn =
    /\b(explore|overview|structure|list|walk through|what('?s| is)\s+in|whats in)\b/i;
  if (listKo.test(cleaned) || listEn.test(cleaned)) return "list";

  // 단일 파일 읽기 의도 (활성 파일 컨텍스트 있을 때)
  // "확인/검토/체크/보겠/다음으로" 등 어시스턴트 후속 약속 패턴도 포함
  const readKo =
    /(이 파일|이 코드|분석|리뷰|이해|읽어|봐줘|뭐.*하는|확인하|검토|체크|살펴보|보겠|읽어서|먼저.*확인|다음.*확인)/;
  const readEn =
    /\b(analyze|review|read|understand|what does this|explain this file|check|inspect|look at|examine)\b/i;
  if (readKo.test(cleaned) || readEn.test(cleaned)) return "read";

  return null;
}

/**
 * 텍스트에서 파일 경로 패턴 추출 (확장자 있는 것).
 * 예: "style.css", "src/index.html", "package.json"
 *
 * 발견 순서대로 반환. 같은 파일이 여러 번이면 첫 등장만.
 */
function extractMentionedFiles(text: string): string[] {
  if (!text) return [];
  // 확장자 화이트리스트 (안전 가드 — 임의 문자열 .test 같은 거 잡지 않게)
  const exts =
    "(html|htm|css|scss|sass|less|js|jsx|mjs|cjs|ts|tsx|json|json5|md|mdx|py|go|rs|java|kt|swift|c|cpp|h|hpp|yml|yaml|sh|bash|zsh|toml|env|ini|cfg|conf|sql|graphql|prisma|vue|svelte|astro)";
  const re = new RegExp(`(?:^|[\\s"'\`(<\\[])([\\w./\\-]+\\.${exts})(?=[\\s"'\`):>\\],.!?]|$)`, "gi");

  const seen = new Set<string>();
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    let p = m[1];
    if (p.startsWith("/") || p.startsWith("../")) continue;
    if (!seen.has(p)) {
      seen.add(p);
      out.push(p);
    }
  }

  // 표준 dotfile (정확한 이름만 화이트리스트 — CSS 셀렉터 .user-list 같은 거 잘못 잡지 않게)
  const knownDotfiles =
    /(?:^|[\s"'`(<\[])(\.(?:env(?:\.[\w-]+)?|gitignore|gitattributes|gitmodules|dockerignore|npmignore|npmrc|nvmrc|node-version|python-version|ruby-version|prettierrc(?:\.\w+)?|eslintrc(?:\.\w+)?|babelrc(?:\.\w+)?|editorconfig|stylelintrc(?:\.\w+)?))(?=[\s"'`):>\],.!?]|$)/gi;

  // 확장자 없는 표준 파일
  const knownNoExt = [
    /(?:^|[\s"'`(<\[])(Dockerfile)(?=[\s"'`):>\],.!?]|$)/g,
    /(?:^|[\s"'`(<\[])(Makefile)(?=[\s"'`):>\],.!?]|$)/g,
    /(?:^|[\s"'`(<\[])(Procfile|Jenkinsfile|Vagrantfile|Rakefile|Gemfile)(?=[\s"'`):>\],.!?]|$)/g,
    /(?:^|[\s"'`(<\[])(README|LICENSE|CHANGELOG|CONTRIBUTING|AUTHORS|NOTICE)(?=[\s"'`):>\],.!?]|$)/g,
  ];

  for (const dpat of [knownDotfiles, ...knownNoExt]) {
    let dm: RegExpExecArray | null;
    while ((dm = dpat.exec(text)) !== null) {
      let p = dm[1];
      if (p.startsWith("/") || p.startsWith("../")) continue;
      if (!seen.has(p)) {
        seen.add(p);
        out.push(p);
      }
    }
  }

  return out;
}

/**
 * read 의도 → list_directory 또는 read_file tool_call 합성.
 * - list : 활성 파일 디렉토리 또는 "."
 * - read : 활성 파일 (없으면 null)
 */
function synthesizeReadCall(
  intent: "list" | "read" | "list-deep",
  history: ChatMessage[]
): ToolCall | null {
  // 활성 파일 추출
  let activeFile: string | null = null;
  const userMsgs = history.filter((m) => m.role === "user");
  for (let i = userMsgs.length - 1; i >= 0; i--) {
    const m = userMsgs[i].content;
    const match = m.match(/\[Active file:\s*([^\s\(\]]+)/);
    if (match) {
      activeFile = match[1];
      break;
    }
  }

  if (intent === "read") {
    if (!activeFile) return null;
    return {
      id: `auto-read-${Date.now()}`,
      type: "function",
      function: {
        name: "read_file",
        arguments: JSON.stringify({ path: activeFile }),
      },
    };
  }

  // list / list-deep — 활성 파일의 부모 디렉토리, 없으면 워크스페이스 루트
  let listPath = ".";
  if (activeFile) {
    const idx = activeFile.lastIndexOf("/");
    if (idx > 0) listPath = activeFile.slice(0, idx);
  }
  const recursive = intent === "list-deep";
  return {
    id: `auto-list-${Date.now()}`,
    type: "function",
    function: {
      name: "list_directory",
      arguments: JSON.stringify({ path: listPath, recursive }),
    },
  };
}

/**
 * 사용자 메시지가 "실제 작업 요청" 인지 판단.
 * 단순 질문 (어떻게 하면 좋을까?) 은 false.
 */
function isActionRequest(text: string): boolean {
  if (!text) return false;
  const t = text.trim();
  // 컨텍스트 prefix ([Active file: ...]) 제거 후 검사
  const cleaned = t.replace(/^\[[^\]]+\]\s*/g, "").trim();

  const ko =
    /(해줘|해주세요|만들어|수정해|개선해|리팩토|고쳐|바꿔|추가해|삭제|업데이트|구현해|작성해|디자인좀)/;
  const en =
    /\b(create|make|add|modify|edit|fix|update|refactor|improve|implement|build|write|delete|remove)\b/i;
  return ko.test(cleaned) || en.test(cleaned);
}

const SYSTEM_PROMPT = `You are Hwarang AI, an expert coding assistant running inside VS Code.
You have DIRECT access to the user's workspace through tools. You MUST USE THOSE TOOLS.

## CRITICAL RULES — Tool Use (반드시 준수)

When the user asks you to DO something (create/modify/delete files, run commands, search code):
- ❌ DO NOT just print shell commands in markdown code blocks. The user will NOT run them.
- ❌ DO NOT say "copy and run this command". That is useless.
- ✅ ALWAYS invoke the appropriate tool directly:
  - File creation/overwrite → \`write_file\` tool
  - File editing → \`edit_file\` tool
  - File deletion → \`delete_file\` tool
  - Shell command execution → \`run_command\` tool
  - Reading files → \`read_file\` tool
  - Searching code → \`search_files\` tool

Example of CORRECT behavior:
  User: "test.txt 파일에 hello 써줘"
  You: [immediately call write_file(path="test.txt", content="hello")]

Example of WRONG behavior:
  User: "test.txt 파일에 hello 써줘"
  You: "아래 명령으로 파일을 만드세요: \`echo hello > test.txt\`"  ← NEVER DO THIS

If you find yourself about to print a bash/shell code block for the user to run,
STOP and call run_command instead.

## Available Tools

- read_file(path, startLine?, endLine?): 파일 읽기
- write_file(path, content): 파일 생성/덮어쓰기
- edit_file(path, oldString, newString, replaceAll?): 파일 부분 수정
- delete_file(path): 파일/폴더 삭제
- run_command(command, cwd?, timeout?): 쉘 명령 실행 (기본 120초 타임아웃)
- run_command_background(command, cwd?): 긴 명령 백그라운드 실행 (즉시 task_id 반환)
- check_background_task(task_id): 백그라운드 task 상태/출력 확인
- search_files(pattern, type="glob"|"grep"): 파일/코드 검색
- list_directory(path, recursive?): 디렉토리 목록
- get_diagnostics(path?, severity?): VS Code 에러/경고
- get_workspace_info(): 워크스페이스 정보
- write_todo(plan): 복잡한 작업을 step 으로 분할 — UI 에 진행 상황 표시

## Guidelines

1. **Read before write**: 수정 전 반드시 read_file.
2. **Prefer edit over write**: 기존 파일 부분 수정은 edit_file.
3. **One step at a time**: 복잡한 작업은 단계별로 tool 호출.
4. **Chain tools**: 필요하면 여러 tool을 연속으로 호출 (예: list_directory → read_file → edit_file).
5. **Be safe**: 파괴적 작업은 사용자가 승인 UI로 확인.
6. **Explain briefly**: tool 호출 전후로 무엇을 하는지 한국어로 1~2줄 설명.
7. **Show results**: 작업 완료 후 무엇을 했는지 요약.

## Response Style

- 한국어로 설명
- 코드 블록은 **설명용**으로만 (실행이 필요하면 반드시 tool 호출)
- 간결하지만 충분히

## Slash Commands

- /explain — 선택한 코드 설명
- /fix — 버그 찾아 수정
- /refactor — 리팩토링
- /test — 유닛 테스트 생성
- /doc — 문서 추가
- /review — 코드 리뷰

## TodoWrite 도구 사용 (중요)

3개 이상 step 이 필요한 복잡한 작업을 받으면:
1. 먼저 \`write_todo\` 로 plan 작성 (모든 status="pending" 으로 시작)
2. 각 step 시작 시 \`write_todo\` 재호출 (해당 step status="in_progress")
3. step 완료 시 \`write_todo\` 재호출 (status="completed")
4. 실패 시 status="failed" 로 표시 후 다른 접근 시도

예시:
- 사용자: "결제 시스템 추가해줘"
- 응답: write_todo([
    {id:"1", title:"결제 모델 정의", status:"pending"},
    {id:"2", title:"API 엔드포인트", status:"pending"},
    {id:"3", title:"webhook 핸들러", status:"pending"},
    {id:"4", title:"테스트 작성", status:"pending"},
    {id:"5", title:"문서 갱신", status:"pending"},
  ])
- 이후 각 step 시작/종료 시 같은 plan 을 status 만 갱신해서 재호출

단순 1-2 단계 작업이면 write_todo 호출하지 마세요.

## 백그라운드 실행 (긴 작업)

다음 명령은 \`run_command_background\` 를 사용하세요:
- npm install / pnpm install / yarn install
- npm run build / pnpm build / cargo build
- 테스트 swept (npm test, pytest 등)

즉시 task_id 가 반환됩니다. 이후 \`check_background_task\` 로 폴링하거나
다른 작업을 진행하다가 사용자에게 결과를 알리세요.

## 일괄 변경 (자동 batch)

한 응답에서 여러 파일 변경 (write_file/edit_file 2개 이상) 이 필요하면
순서대로 호출하기만 하면 됩니다 — 시스템이 자동으로 묶어서 한 번에 사용자 승인을 받습니다.

## Plan 모드

3 step 이상 또는 multi-file/multi-domain 작업 (예: "결제 시스템 추가",
"전체 리팩토링", "DB 마이그레이션") 을 받으면 자동으로 plan 이 작성됩니다.
사용자 승인 후 진행됩니다. 단순 작업 (단일 파일 수정 등) 은 plan 없이 바로 도구 호출하세요.

승인된 plan 이 system 메시지로 주입되면, 각 step 마다 write_todo 로 진행 상황을 갱신하면서 실행하세요.

## Subagent 위임 (delegate_subtask)

큰 작업을 logical sub-task 로 나눠 위임 가능:
- 사용 시점: 도메인이 다른 큰 작업 동시 진행 (예: "API 추가 + 프론트 + 테스트")
- 단순 step 분할은 write_todo 사용 (delegate 아님)
- 재귀 위임 금지 — sub-agent 안에서 또 delegate 하지 마세요
- 한 메인 작업당 최대 5개까지

## 컨텍스트 자동 압축

대화가 길어지면 (30 메시지 이상 + 30K자 이상) 시스템이 자동으로 이전 대화를 요약합니다.
이 동작은 투명하게 일어나며 별도 도구 호출이 필요 없습니다.`;

export interface AgentMessage {
  role: "user" | "assistant" | "tool_call" | "tool_result";
  content: string;
  toolName?: string;
  toolCallId?: string;
}

/**
 * Sub-agent 모드 옵션 — 메인 agent 가 delegate_subtask 로 호출 시 사용.
 * - excludeTools: 도구 목록에서 제외할 이름들 (재귀 위임 차단용)
 * - maxIterations: sub-agent 자체 iteration 한도
 */
interface SubagentOptions {
  excludeTools?: string[];
  maxIterations?: number;
  isSubagent?: boolean;
}

export class AgentLoop {
  private llm: LLMClient;
  private tools: ToolExecutor;
  private conversationHistory: ChatMessage[] = [];
  private abortController: AbortController | null = null;
  private _isRunning = false;

  /** Plan 모드 / 압축에 쓰는 webview bridge — 외부에서 setWebview 로 주입 */
  private planBridge: PlanWebviewBridge | null = null;
  /** Plan 매니저 / 압축기 (싱글톤 인스턴스) */
  private planMgr = new PlanModeManager();
  private compactor = new ContextCompactor();

  /** Sub-agent 인스턴스인지 — true 면 plan 모드/sub-agent 위임 비활성 */
  private readonly isSubagent: boolean;
  /** Sub-agent 일 때 도구 목록에서 제외할 이름들 */
  private readonly excludedTools: Set<string>;
  /** iteration 한도 (sub-agent 는 더 짧게) */
  private readonly maxIterations: number;

  constructor(llm: LLMClient, tools: ToolExecutor, opts?: SubagentOptions) {
    this.llm = llm;
    this.tools = tools;
    this.isSubagent = !!opts?.isSubagent;
    this.excludedTools = new Set(opts?.excludeTools || []);
    this.maxIterations = opts?.maxIterations ?? MAX_ITERATIONS;

    // Sub-agent 가 아닐 때만 위임 runner 등록 (재귀 차단)
    if (!this.isSubagent) {
      this.tools.setSubagentRunner(async (params) => {
        return this.runSubagent(params);
      });
    }
  }

  /**
   * Plan 모드 / batch 승인용 webview bridge 주입.
   * chat-view-provider 에서 webview 생성 후 호출.
   */
  setWebview(bridge: PlanWebviewBridge | null) {
    this.planBridge = bridge;
  }

  get isRunning(): boolean {
    return this._isRunning;
  }

  /**
   * 저장된 대화를 복원 (user/assistant만, 도구 호출 제외)
   */
  restoreHistory(messages: { role: "user" | "assistant"; content: string }[]) {
    this.conversationHistory = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));
  }

  clearHistory() {
    this.conversationHistory = [];
    // 새 대화 시작 — 워크스페이스 컨텍스트도 새로 감지 (변경됐을 수 있음)
    invalidateWorkspaceContextCache();
  }

  abort() {
    this.abortController?.abort();
    this.abortController = null;
    this._isRunning = false;
    this.llm.abort();
  }

  /**
   * Process a user message with tool-use loop. Yields messages as they happen.
   */
  async *run(userMessage: string): AsyncGenerator<AgentMessage, void, unknown> {
    this._isRunning = true;
    this.abortController = new AbortController();

    // 새 user turn 시작 — sub-agent 호출 카운터 리셋
    if (!this.isSubagent) {
      this.tools.resetSubagentCounter();
    }

    // run() 한 번에 fallback 합성 한도 (무한 루프 방지)
    let fallbackSynthCount = 0;
    // 응답 중복 감지 (LLM 이 같은 답 반복 시 즉시 종료)
    let lastResponseSig: Set<string> = new Set();
    let repeatedResponseCount = 0;

    // sub-agent 모드용 도구 정의 (delegate_subtask 등 제외)
    const activeToolDefs = this.excludedTools.size
      ? TOOL_DEFINITIONS.filter(
          (t: any) => !this.excludedTools.has(t.function.name)
        )
      : TOOL_DEFINITIONS;

    try {
      // ── Plan 모드 자동 진입 검사 (메인 agent 만, sub-agent 는 스킵) ──
      if (
        !this.isSubagent &&
        this.planMgr.shouldEnterPlanMode(userMessage, this.conversationHistory)
      ) {
        yield { role: "assistant", content: "Plan 작성 중..." };
        const plan = await this.planMgr.generatePlan(userMessage, this.llm);
        if (plan.length > 0) {
          const planText =
            "다음과 같이 진행하겠습니다:\n" +
            plan
              .map(
                (p, i) =>
                  `${i + 1}. ${p.title}` +
                  (p.description ? ` — ${p.description}` : "") +
                  (p.riskLevel === "high" ? " (위험도: 높음)" : "")
              )
              .join("\n");
          yield { role: "assistant", content: planText };

          const approval = await this.planMgr.requestApproval(
            plan,
            this.planBridge
          );
          if (!approval.approved) {
            yield { role: "assistant", content: "취소되었습니다." };
            return;
          }

          // 승인된 plan 을 system 으로 주입 (history 맨 앞)
          const finalPlan = approval.modifiedPlan || plan;
          this.conversationHistory.unshift({
            role: "system",
            content:
              `[Approved Plan]\n` +
              finalPlan
                .map((p, i) => `${i + 1}. ${p.title}`)
                .join("\n") +
              `\n\n각 step 마다 write_todo 로 진행 상황 갱신하면서 실행하세요.`,
          });
        }
      }

      const context = await this.buildContext();
      const fullMessage = context ? `${context}\n\n${userMessage}` : userMessage;

      this.conversationHistory.push({ role: "user", content: fullMessage });

      for (let i = 0; i < this.maxIterations; i++) {
        if (this.abortController.signal.aborted) {
          yield { role: "assistant", content: "(Cancelled)" };
          return;
        }

        // ── 컨텍스트 자동 압축 검사 (메인 agent 만 — sub-agent 는 짧으니 스킵) ──
        if (!this.isSubagent && this.compactor.shouldCompact(this.conversationHistory)) {
          const beforeLen = this.conversationHistory.length;
          try {
            this.conversationHistory = await this.compactor.compact(
              this.conversationHistory,
              this.llm
            );
            console.log(
              `[AgentLoop] 컨텍스트 압축 (${beforeLen} → ${this.conversationHistory.length})`
            );
          } catch (e) {
            console.warn("[AgentLoop] 압축 실패 — 원본 유지:", e);
          }
        }

        const currentMode = getMode();
        const messages: ChatMessage[] = [
          { role: "system", content: SYSTEM_PROMPT + getSystemPromptAddition(currentMode) },
          ...this.conversationHistory,
        ];

        const response = await this.llm.chat(messages, activeToolDefs);

        if (this.abortController.signal.aborted) {
          yield { role: "assistant", content: "(Cancelled)" };
          return;
        }

        // 응답 중복 감지 — LLM 이 비슷한 답을 반복하면 (특히 plain text + tool_call 없음) 무한루프 방지.
        // signature: 코드블록/특수문자/숫자 제거 후 핵심 단어만 비교 (약간 변형된 답도 감지)
        if (!response.toolCalls?.length) {
          const sig = makeResponseSignature(response.content || "");
          if (sig && lastResponseSig && jaccard(sig, lastResponseSig) > 0.7) {
            repeatedResponseCount++;
            if (repeatedResponseCount >= 1) {
              // 한 번만 반복돼도 종료 (이전 2회 → 1회로 더 빠르게 끊기)
              console.warn(
                `[AgentLoop] LLM 비슷한 응답 반복 감지 (similarity>0.7) → 종료 (iter=${i})`
              );
              this.conversationHistory.push({ role: "assistant", content: response.content || "" });
              yield { role: "assistant", content: response.content || "" };
              return;
            }
          } else {
            repeatedResponseCount = 0;
          }
          if (sig) lastResponseSig = sig;
        }

        if (response.toolCalls?.length) {
          // Assistant wants to use tools
          this.conversationHistory.push({
            role: "assistant",
            content: response.content || "",
            tool_calls: response.toolCalls,
          });

          if (response.content) {
            yield { role: "assistant", content: response.content };
          }

          // 자동 batch 모드: 한 turn 에서 write_file / edit_file 이 2개 이상이면
          // 큐로 모아서 사용자에게 한 번에 승인 받음.
          const fileMutationCount = response.toolCalls.filter(
            (t) => t.function.name === "write_file" || t.function.name === "edit_file"
          ).length;
          const useBatch = fileMutationCount >= 2;
          if (useBatch) {
            this.tools.beginBatch();
          }

          // Execute each tool
          for (const tc of response.toolCalls) {
            if (this.abortController.signal.aborted) {
              if (useBatch) await this.tools.commitBatch().catch(() => undefined);
              return;
            }

            const args = this.formatToolArgs(tc);
            yield {
              role: "tool_call",
              content: `${tc.function.name}(${args})`,
              toolName: tc.function.name,
              toolCallId: tc.id,
            };

            const result = await this.tools.execute(tc.function.name, tc.function.arguments);

            // Truncate very long results
            const output = result.output.length > 8000
              ? result.output.slice(0, 8000) + "\n... (truncated)"
              : result.output;

            yield {
              role: "tool_result",
              content: output,
              toolName: tc.function.name,
              toolCallId: tc.id,
            };

            this.conversationHistory.push({
              role: "tool",
              content: output,
              tool_call_id: tc.id,
            });
          }

          // batch 커밋 — 모든 file mutation 호출이 큐에 들어왔으니 한 번에 적용
          if (useBatch && this.tools.hasPendingBatch()) {
            const pendingCount = this.tools.pendingBatchCount();
            yield {
              role: "tool_call",
              content: `(batch_commit: ${pendingCount} files awaiting approval)`,
              toolName: "batch_commit",
              toolCallId: `batch-${Date.now()}`,
            };
            const batchResult = await this.tools.commitBatch();
            const summary = batchResult.approved
              ? `Batch applied: ${batchResult.appliedCount} file(s)` +
                (batchResult.skipped.length
                  ? `\nSkipped: ${batchResult.skipped.join(", ")}`
                  : "")
              : `Batch rejected by user (${pendingCount} file(s) not applied)`;
            yield {
              role: "tool_result",
              content: summary,
              toolName: "batch_commit",
              toolCallId: `batch-result-${Date.now()}`,
            };
            // batch 결과를 마지막 tool 메시지로 추가 (LLM 이 인지하도록)
            this.conversationHistory.push({
              role: "tool",
              content: summary,
              tool_call_id: response.toolCalls[response.toolCalls.length - 1].id,
            });
          }

          continue; // Next iteration
        }

        // No tool calls → final response
        const finalContent = response.content || "";
        const userAskedForActionEarly = isActionRequest(
          this.conversationHistory.filter((m) => m.role === "user").slice(-1)[0]?.content || ""
        );

        // 우선순위 1: write 의도 + 진짜 코드블록 → write_file 합성 (결론 시그널보다 우선)
        // 이유: 사용자가 "X 만들어줘/수정해줘" 했고 LLM 이 코드 결과물을 코드블록으로 줬으면
        // 마무리 멘트 ("적용할 부분이 있으면 알려주세요") 가 있어도 write_file 자동 적용해야
        // 사용자가 직접 복붙 안 해도 됨.
        if (
          userAskedForActionEarly &&
          !response.toolCalls?.length &&
          fallbackSynthCount < MAX_FALLBACK_SYNTH
        ) {
          const synth = trySynthesizeWriteFile(finalContent, this.conversationHistory);
          if (synth) {
            fallbackSynthCount++;
            console.log(
              `[AgentLoop] write 의도 + 코드블록 → write_file('${synth.path}') 자동 합성 (#${fallbackSynthCount})`
            );
            const synthCall: ToolCall = {
              id: `auto-write-${Date.now()}`,
              type: "function",
              function: {
                name: "write_file",
                arguments: JSON.stringify({ path: synth.path, content: synth.content }),
              },
            };
            yield {
              role: "assistant",
              content: finalContent + `\n\n_(자동 적용 시도: ${synth.path})_`,
            };
            yield {
              role: "tool_call",
              content: `write_file(path: "${synth.path}", content: "...${synth.content.length} chars")`,
              toolName: "write_file",
              toolCallId: synthCall.id,
            };
            const result = await this.tools.execute(
              "write_file",
              synthCall.function.arguments
            );
            const output =
              result.output.length > 8000
                ? result.output.slice(0, 8000) + "\n... (truncated)"
                : result.output;
            yield {
              role: "tool_result",
              content: output,
              toolName: "write_file",
              toolCallId: synthCall.id,
            };
            this.conversationHistory.push({
              role: "assistant",
              content: finalContent,
              tool_calls: [synthCall],
            });
            this.conversationHistory.push({
              role: "tool",
              content: output,
              tool_call_id: synthCall.id,
            });
            continue;
          }
        }

        // 우선순위 2: 결론 시그널 감지 → 즉시 final 처리
        // LLM 이 "최종 결론", "이해하셨나요?", "더 궁금한 부분이..." 처럼 명시적으로
        // 답변을 마무리하면 가드/fallback 발동 안 하고 그대로 종료.
        if (isConclusionSignal(finalContent)) {
          console.log(`[AgentLoop] 결론 시그널 감지 → final 처리 (iter=${i})`);
          this.conversationHistory.push({ role: "assistant", content: finalContent });
          yield { role: "assistant", content: finalContent };
          return;
        }

        // 가드: 행위만 약속하고 tool call 안 한 경우 (도돌이표 방지)
        // "리팩토링하겠습니다", "수정하겠습니다", "만들겠습니다", "I'll create/modify..." 등
        // 사용자가 명시적 작업 (디자인 개선, 파일 수정 등) 을 요청한 후의 첫 응답에서만 동작
        const isActionPromise = isLikelyActionPromise(finalContent);
        const userAskedForAction = isActionRequest(
          this.conversationHistory.filter((m) => m.role === "user").slice(-1)[0]?.content || ""
        );

        if (isActionPromise && userAskedForAction && i < 4) {
          // 한 번 더 강제로 tool call 유도.
          //
          // 핵심: 행위 약속 응답은 conversationHistory 에 절대 푸시하지 않는다.
          // 이유: vLLM hermes parser + LoRA 조합에서 multi-turn 시 모델이
          // "직전 assistant 가 plain text 였다 → 나도 plain text" 라고 in-context 학습해서
          // 다음 응답도 tool_call 없이 plain text 만 생성하는 패턴이 관찰됨.
          // 약속 응답을 history 에서 빼면 LLM 은 깨끗한 컨텍스트로 다시 시도함.
          console.log(`[AgentLoop] 행위 약속만 감지 (iter=${i}) → history 미오염 후 강제 재시도`);

          // 마지막 user 메시지에 강한 enforcement 추가 (1회만)
          const lastIdx = this.conversationHistory.length - 1;
          const ENFORCEMENT_TAG = "[CRITICAL_TOOL_USE]";
          if (
            lastIdx >= 0 &&
            this.conversationHistory[lastIdx].role === "user" &&
            !this.conversationHistory[lastIdx].content.includes(ENFORCEMENT_TAG)
          ) {
            this.conversationHistory[lastIdx].content +=
              `\n\n${ENFORCEMENT_TAG} 위 요청은 반드시 tool 호출로 수행하세요. ` +
              "설명/약속만 하지 말고 첫 응답 토큰부터 즉시 tool_call (read_file/write_file/edit_file/list_directory/run_command 등) 을 만드세요. " +
              "도구 호출 없는 답변은 거부됩니다.";
          }

          // UX: 사용자에게는 약속 메시지를 한 번 보여줌 (작업 중이라는 시그널)
          // 단 history 에는 추가하지 않음 — 다음 호출에서 LLM 이 깨끗한 컨텍스트 받게.
          yield { role: "assistant", content: finalContent };
          continue;
        }

        // Fallback A: read 의도 감지 시 list_directory / read_file 자동 합성.
        // 사용자의 마지막 메시지 OR LLM 의 약속 메시지 ("더 깊이 보겠습니다" 등) 둘 다 검사.
        // 같은 합성 무한 반복 방지 — 같은 의도+경로 조합은 라운드당 1회만.
        const lastUserText =
          this.conversationHistory.filter((m) => m.role === "user").slice(-1)[0]?.content || "";
        const readIntent =
          detectReadIntent(lastUserText) || detectReadIntent(finalContent);

        if (readIntent && !response.toolCalls?.length && fallbackSynthCount < MAX_FALLBACK_SYNTH) {
          const readCall = synthesizeReadCall(readIntent, this.conversationHistory);
          // 직전에 같은 tool 을 같은 인자로 합성했다면 스킵 (반복 방지)
          const lastSynth = this.conversationHistory
            .filter((m: any) => m.role === "assistant" && m.tool_calls?.length)
            .slice(-1)[0] as any;
          const dup =
            lastSynth?.tool_calls?.[0]?.function?.name === readCall?.function.name &&
            lastSynth?.tool_calls?.[0]?.function?.arguments === readCall?.function.arguments;
          if (readCall && !dup) {
            fallbackSynthCount++;
            console.log(
              `[AgentLoop] read 의도 감지 + tool_call 누락 → ${readCall.function.name} 자동 합성`
            );

            yield { role: "assistant", content: finalContent };
            yield {
              role: "tool_call",
              content: `${readCall.function.name}(${this.formatToolArgs(readCall)})`,
              toolName: readCall.function.name,
              toolCallId: readCall.id,
            };

            const result = await this.tools.execute(
              readCall.function.name,
              readCall.function.arguments
            );

            const output =
              result.output.length > 8000
                ? result.output.slice(0, 8000) + "\n... (truncated)"
                : result.output;

            yield {
              role: "tool_result",
              content: output,
              toolName: readCall.function.name,
              toolCallId: readCall.id,
            };

            this.conversationHistory.push({
              role: "assistant",
              content: finalContent,
              tool_calls: [readCall],
            });
            this.conversationHistory.push({
              role: "tool",
              content: output,
              tool_call_id: readCall.id,
            });
            continue;
          }
        }

        // Fallback C: LLM 응답에 명시적 파일명이 있고 tool_call 은 없을 때
        // (예: "style.css 의 현재 규칙을 확인하겠습니다" → style.css read_file 자동)
        if (!response.toolCalls?.length && fallbackSynthCount < MAX_FALLBACK_SYNTH) {
          const mentioned = extractMentionedFiles(finalContent);
          // 같은 라운드에서 이미 합성한 파일 제외 (반복 방지)
          const recentSynthFiles = new Set<string>();
          for (const m of this.conversationHistory.slice(-6) as any[]) {
            if (m.role === "assistant" && m.tool_calls?.length) {
              for (const tc of m.tool_calls) {
                try {
                  const args = JSON.parse(tc.function.arguments);
                  if (args.path) recentSynthFiles.add(args.path);
                } catch { /* ignore */ }
              }
            }
          }
          const target = mentioned.find((f) => !recentSynthFiles.has(f));

          if (target) {
            fallbackSynthCount++;
            console.log(`[AgentLoop] 파일명 언급 + tool_call 누락 → read_file('${target}') 자동 합성 (#${fallbackSynthCount})`);
            const synthCall: ToolCall = {
              id: `auto-readfile-${Date.now()}`,
              type: "function",
              function: {
                name: "read_file",
                arguments: JSON.stringify({ path: target }),
              },
            };

            yield { role: "assistant", content: finalContent };
            yield {
              role: "tool_call",
              content: `read_file(path: "${target}")`,
              toolName: "read_file",
              toolCallId: synthCall.id,
            };

            const result = await this.tools.execute(
              "read_file",
              synthCall.function.arguments
            );
            const output =
              result.output.length > 8000
                ? result.output.slice(0, 8000) + "\n... (truncated)"
                : result.output;

            yield {
              role: "tool_result",
              content: output,
              toolName: "read_file",
              toolCallId: synthCall.id,
            };

            this.conversationHistory.push({
              role: "assistant",
              content: finalContent,
              tool_calls: [synthCall],
            });
            this.conversationHistory.push({
              role: "tool",
              content: output,
              tool_call_id: synthCall.id,
            });
            continue;
          }
        }

        // Fallback B: LLM 이 코드 블록을 뱉었지만 tool_call 은 안 했을 때
        // (LoRA 가 multi-turn tool calling 못하는 케이스 회피)
        // → 활성 파일 컨텍스트가 있으면 write_file 자동 합성.
        // ToolExecutor 의 승인 UI 가 한 번 더 사용자에게 확인 받음.
        if (userAskedForAction && fallbackSynthCount < MAX_FALLBACK_SYNTH) {
          const synthesized = trySynthesizeWriteFile(
            finalContent,
            this.conversationHistory
          );
          if (synthesized) {
            fallbackSynthCount++;
            console.log(
              "[AgentLoop] tool_call 누락 — 코드블록 → write_file 자동 합성:",
              synthesized.path
            );

            const synthesizedCall: ToolCall = {
              id: `auto-${Date.now()}`,
              type: "function",
              function: {
                name: "write_file",
                arguments: JSON.stringify({
                  path: synthesized.path,
                  content: synthesized.content,
                }),
              },
            };

            yield {
              role: "assistant",
              content:
                finalContent +
                `\n\n_(자동 감지: ${synthesized.path} 에 위 코드를 적용 시도)_`,
            };
            yield {
              role: "tool_call",
              content: `write_file(path: "${synthesized.path}", content: "...${synthesized.content.length} chars")`,
              toolName: "write_file",
              toolCallId: synthesizedCall.id,
            };

            const result = await this.tools.execute(
              "write_file",
              synthesizedCall.function.arguments
            );

            const output =
              result.output.length > 8000
                ? result.output.slice(0, 8000) + "\n... (truncated)"
                : result.output;

            yield {
              role: "tool_result",
              content: output,
              toolName: "write_file",
              toolCallId: synthesizedCall.id,
            };

            this.conversationHistory.push({
              role: "assistant",
              content: finalContent,
              tool_calls: [synthesizedCall],
            });
            this.conversationHistory.push({
              role: "tool",
              content: output,
              tool_call_id: synthesizedCall.id,
            });
            continue;
          }
        }

        this.conversationHistory.push({ role: "assistant", content: finalContent });
        yield { role: "assistant", content: finalContent };
        return;
      }

      yield {
        role: "assistant",
        content: `Reached maximum tool iterations (${this.maxIterations}). Please try breaking this into smaller steps.`,
      };
    } finally {
      this._isRunning = false;
      this.abortController = null;
    }
  }

  /**
   * Sub-agent 실행 — delegate_subtask 도구 호출 시 트리거.
   *
   * - 새 ToolExecutor 를 만들지 않고 기존 인스턴스 재활용 (UI/배치 일관성)
   *   대신 sub-agent 인스턴스의 도구 목록에서 delegate_subtask 를 제외해 재귀 차단
   * - sub-agent 의 history 는 격리 (메인 history 오염 방지)
   * - 결과: 마지막 assistant 메시지 + tool_call 요약 3줄
   */
  private async runSubagent(params: {
    title: string;
    instructions: string;
    expectedOutputs?: string[];
  }): Promise<{ success: boolean; summary: string }> {
    const sub = new AgentLoop(this.llm, this.tools, {
      isSubagent: true,
      excludeTools: ["delegate_subtask"],
      maxIterations: MAX_SUBAGENT_ITERATIONS,
    });

    const expectedNote = params.expectedOutputs?.length
      ? `\n\n예상 산출물:\n${params.expectedOutputs.map((o) => `- ${o}`).join("\n")}`
      : "";

    const subUserMsg = `[Sub-task: ${params.title}]\n${params.instructions}${expectedNote}`;

    const lines: string[] = [];
    let lastAssistant = "";
    try {
      for await (const msg of sub.run(subUserMsg)) {
        if (msg.role === "assistant") {
          lastAssistant = msg.content;
          // 진행 상황 한 줄씩 누적 (요약용)
          if (msg.content && msg.content.length < 400) {
            lines.push(msg.content);
          }
        } else if (msg.role === "tool_call") {
          lines.push(`[tool] ${msg.toolName || "?"}`);
        }
      }
    } catch (e: any) {
      return {
        success: false,
        summary: `Sub-agent 실행 중 오류: ${e?.message || e}`,
      };
    }

    // 마지막 assistant + 마지막 tool_call 3개 정도만 요약
    const tail = lines.slice(-5).join("\n");
    const summary = lastAssistant
      ? `${tail}\n\n최종: ${lastAssistant.slice(0, 600)}`
      : tail || "(no output)";

    return { success: true, summary };
  }

  /**
   * Stream a simple response without tools (for inline chat).
   */
  async *streamResponse(userMessage: string): AsyncGenerator<string, void, unknown> {
    this._isRunning = true;
    this.abortController = new AbortController();

    try {
      const context = await this.buildContext();
      const fullMessage = context ? `${context}\n\n${userMessage}` : userMessage;

      this.conversationHistory.push({ role: "user", content: fullMessage });

      const currentMode = getMode();
      const messages: ChatMessage[] = [
        { role: "system", content: SYSTEM_PROMPT + getSystemPromptAddition(currentMode) },
        ...this.conversationHistory,
      ];

      let fullResponse = "";
      for await (const chunk of this.llm.streamChat(messages, this.abortController.signal)) {
        if (this.abortController.signal.aborted) break;
        fullResponse += chunk;
        yield chunk;
      }

      this.conversationHistory.push({ role: "assistant", content: fullResponse });
    } finally {
      this._isRunning = false;
      this.abortController = null;
    }
  }

  private formatToolArgs(tc: ToolCall): string {
    try {
      const args = JSON.parse(tc.function.arguments);
      const parts: string[] = [];
      for (const [key, value] of Object.entries(args)) {
        if (typeof value === "string" && value.length > 50) {
          parts.push(`${key}: "${value.slice(0, 50)}..."`);
        } else {
          parts.push(`${key}: ${JSON.stringify(value)}`);
        }
      }
      return parts.join(", ");
    } catch {
      return tc.function.arguments.slice(0, 100);
    }
  }

  private async buildContext(): Promise<string> {
    const parts: string[] = [];

    // 워크스페이스 자동 컨텍스트 (캐시 5분 TTL)
    try {
      const wsCtx = await detectWorkspaceContext();
      if (wsCtx?.raw) {
        parts.push(wsCtx.raw);
      }
    } catch {
      /* 워크스페이스 컨텍스트 실패해도 진행 */
    }

    // Active file info
    const editor = vscode.window.activeTextEditor;
    if (editor) {
      const doc = editor.document;
      const relPath = vscode.workspace.asRelativePath(doc.uri);
      parts.push(`[Active file: ${relPath} (${doc.languageId}, ${doc.lineCount} lines)]`);

      // Include selection if present
      if (!editor.selection.isEmpty) {
        const selection = doc.getText(editor.selection);
        if (selection.length < 3000) {
          const startLine = editor.selection.start.line + 1;
          const endLine = editor.selection.end.line + 1;
          parts.push(`[Selection (lines ${startLine}-${endLine}):\n\`\`\`${doc.languageId}\n${selection}\n\`\`\`]`);
        } else {
          parts.push(`[Selection: ${selection.length} chars, lines ${editor.selection.start.line + 1}-${editor.selection.end.line + 1}]`);
        }
      }
    }

    // Workspace info
    const folders = vscode.workspace.workspaceFolders;
    if (folders?.length) {
      parts.push(`[Workspace: ${folders[0].name} (${folders[0].uri.fsPath})]`);
    }

    // Active diagnostics (errors only)
    try {
      const allDiags = vscode.languages.getDiagnostics() as [vscode.Uri, readonly vscode.Diagnostic[]][];
      const errors = allDiags
        .flatMap(([uri, diags]) =>
          diags
            .filter((d) => d.severity === vscode.DiagnosticSeverity.Error)
            .map((d) => `${vscode.workspace.asRelativePath(uri)}:${d.range.start.line + 1}: ${d.message}`)
        )
        .slice(0, 5);
      if (errors.length) {
        parts.push(`[Active errors:\n${errors.join("\n")}]`);
      }
    } catch {}

    return parts.join("\n");
  }
}
