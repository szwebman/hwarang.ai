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
