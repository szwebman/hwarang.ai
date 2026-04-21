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

const MAX_ITERATIONS = 25;

const SYSTEM_PROMPT = `You are Hwarang AI, an expert coding assistant running inside VS Code.
You have full access to the user's workspace through tools.

## Capabilities
- Read, write, edit, and delete files in the workspace
- Execute shell commands (build, test, git, etc.) with output capture
- Search code by filename patterns (glob) or content (regex grep)
- View VS Code diagnostics (errors, warnings)
- Analyze project structure

## Guidelines
1. **Read before write**: Always read a file before modifying it.
2. **Prefer edit over write**: Use edit_file for targeted changes on existing files.
3. **Explain your actions**: Briefly state what you're doing and why.
4. **Be safe**: For destructive operations the user will be asked to confirm.
5. **Show results**: After making changes, summarize what was done.
6. **Respect conventions**: Follow the existing code style in the project.
7. **One step at a time**: Break complex tasks into clear steps.

## Response Style
- Be concise but thorough
- Use markdown for formatting
- Include relevant code snippets in your explanations
- When showing file edits, describe what changed

## Slash Commands (user shortcuts)
- /explain — Explain the selected code
- /fix — Find and fix bugs
- /refactor — Refactor for clarity and performance
- /test — Generate unit tests
- /doc — Add documentation
- /review — Code review with suggestions`;

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

        const messages: ChatMessage[] = [
          { role: "system", content: SYSTEM_PROMPT },
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

      const messages: ChatMessage[] = [
        { role: "system", content: SYSTEM_PROMPT },
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
