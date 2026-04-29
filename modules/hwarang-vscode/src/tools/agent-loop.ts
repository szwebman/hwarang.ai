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

const MAX_ITERATIONS = 25;

/**
 * "행위 약속만 한 응답" 감지 — 도돌이표 가드용.
 *
 * 예: "리팩토링하겠습니다", "수정하겠습니다", "I will refactor..."
 * 짧고 (300자 미만), 미래형 약속만 있고 코드/구조적 출력이 없는 경우 true.
 */
function isLikelyActionPromise(text: string): boolean {
  if (!text) return false;
  const t = text.trim();
  if (t.length === 0 || t.length > 400) return false;
  // 코드 블록이 있으면 약속이 아니라 실제 결과물일 가능성
  if (t.includes("```")) return false;

  const ko = /(하겠습니다|할게요|진행하겠|만들겠|수정하겠|개선하겠|리팩토링하겠|시작하겠|작성하겠|업데이트하겠)/;
  const en = /\b(I('ll| will)|let me|going to)\s+(refactor|create|modify|update|fix|implement|improve|write|edit)/i;
  const apology = /(죄송|sorry)/i;

  return ko.test(t) || en.test(t) || (apology.test(t) && t.length < 100);
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
- run_command(command, cwd?, timeout?): 쉘 명령 실행
- search_files(pattern, type="glob"|"grep"): 파일/코드 검색
- list_directory(path, recursive?): 디렉토리 목록
- get_diagnostics(path?, severity?): VS Code 에러/경고
- get_workspace_info(): 워크스페이스 정보

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
- /review — 코드 리뷰`;

export interface AgentMessage {
  role: "user" | "assistant" | "tool_call" | "tool_result";
  content: string;
  toolName?: string;
  toolCallId?: string;
}

export class AgentLoop {
  private llm: LLMClient;
  private tools: ToolExecutor;
  private conversationHistory: ChatMessage[] = [];
  private abortController: AbortController | null = null;
  private _isRunning = false;

  constructor(llm: LLMClient, tools: ToolExecutor) {
    this.llm = llm;
    this.tools = tools;
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

    try {
      const context = await this.buildContext();
      const fullMessage = context ? `${context}\n\n${userMessage}` : userMessage;

      this.conversationHistory.push({ role: "user", content: fullMessage });

      for (let i = 0; i < MAX_ITERATIONS; i++) {
        if (this.abortController.signal.aborted) {
          yield { role: "assistant", content: "(Cancelled)" };
          return;
        }

        const currentMode = getMode();
        const messages: ChatMessage[] = [
          { role: "system", content: SYSTEM_PROMPT + getSystemPromptAddition(currentMode) },
          ...this.conversationHistory,
        ];

        const response = await this.llm.chat(messages, TOOL_DEFINITIONS);

        if (this.abortController.signal.aborted) {
          yield { role: "assistant", content: "(Cancelled)" };
          return;
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

          // Execute each tool
          for (const tc of response.toolCalls) {
            if (this.abortController.signal.aborted) return;

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

          continue; // Next iteration
        }

        // No tool calls → final response
        const finalContent = response.content || "";

        // 가드: 행위만 약속하고 tool call 안 한 경우 (도돌이표 방지)
        // "리팩토링하겠습니다", "수정하겠습니다", "만들겠습니다", "I'll create/modify..." 등
        // 사용자가 명시적 작업 (디자인 개선, 파일 수정 등) 을 요청한 후의 첫 응답에서만 동작
        const isActionPromise = isLikelyActionPromise(finalContent);
        const userAskedForAction = isActionRequest(
          this.conversationHistory.filter((m) => m.role === "user").slice(-1)[0]?.content || ""
        );

        if (isActionPromise && userAskedForAction && i < 2) {
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

        this.conversationHistory.push({ role: "assistant", content: finalContent });
        yield { role: "assistant", content: finalContent };
        return;
      }

      yield {
        role: "assistant",
        content: "Reached maximum tool iterations (25). Please try breaking this into smaller steps.",
      };
    } finally {
      this._isRunning = false;
      this.abortController = null;
    }
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
