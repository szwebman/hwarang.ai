/**
 * Agent Loop - ReAct-style agent that can use tools.
 *
 * Flow:
 * 1. User sends message
 * 2. Send to LLM with tool definitions + workspace context
 * 3. If LLM calls tools → execute → feed results back → loop
 * 4. If LLM returns text → return as final response
 */

import * as vscode from "vscode";
import { LLMClient, ChatMessage, ToolCall } from "../providers/llm-client";
import { ToolExecutor, TOOL_DEFINITIONS } from "./executor";

const MAX_ITERATIONS = 15;

const SYSTEM_PROMPT = `You are Hwarang AI, a coding assistant running inside VS Code.

You have access to tools for reading, writing, editing, and deleting files in the user's workspace.
You can also run terminal commands and search the codebase.

Guidelines:
- When the user asks you to create or modify files, use the write_file or edit_file tools.
- Use read_file to understand existing code before modifying it.
- Use search_files to find relevant files in the project.
- Use edit_file for targeted changes (preferred over write_file for existing files).
- Always explain what you're doing and why.
- When editing files, show the user what changed.
- For destructive operations (delete, overwrite), the user will be asked for confirmation.
- Be concise but thorough in your responses.`;

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

  constructor(llm: LLMClient, tools: ToolExecutor) {
    this.llm = llm;
    this.tools = tools;
  }

  clearHistory() {
    this.conversationHistory = [];
  }

  /**
   * Process a user message. Yields agent messages as they happen.
   */
  async *run(userMessage: string): AsyncGenerator<AgentMessage, void, unknown> {
    // Add context about current workspace
    const context = await this.buildContext();

    this.conversationHistory.push({
      role: "user",
      content: `${context}\n\n${userMessage}`,
    });

    for (let i = 0; i < MAX_ITERATIONS; i++) {
      const messages: ChatMessage[] = [
        { role: "system", content: SYSTEM_PROMPT },
        ...this.conversationHistory,
      ];

      const response = await this.llm.chat(messages, TOOL_DEFINITIONS);

      if (response.toolCalls?.length) {
        // Add assistant's tool call message
        this.conversationHistory.push({
          role: "assistant",
          content: response.content || "",
          tool_calls: response.toolCalls,
        });

        // Show what the AI is thinking
        if (response.content) {
          yield { role: "assistant", content: response.content };
        }

        // Execute each tool call
        for (const tc of response.toolCalls) {
          yield {
            role: "tool_call",
            content: `Calling \`${tc.function.name}\`...`,
            toolName: tc.function.name,
            toolCallId: tc.id,
          };

          const result = await this.tools.execute(tc.function.name, tc.function.arguments);

          yield {
            role: "tool_result",
            content: result.output,
            toolName: tc.function.name,
            toolCallId: tc.id,
          };

          this.conversationHistory.push({
            role: "tool",
            content: result.output,
            tool_call_id: tc.id,
          });
        }

        continue; // Loop back for next LLM call
      }

      // No tool calls → final response
      const finalContent = response.content || "";
      this.conversationHistory.push({
        role: "assistant",
        content: finalContent,
      });

      yield { role: "assistant", content: finalContent };
      return;
    }

    yield {
      role: "assistant",
      content: "Reached maximum iterations. Please try a simpler request.",
    };
  }

  /**
   * Stream a simple response (no tools).
   */
  async *streamResponse(userMessage: string): AsyncGenerator<string, void, unknown> {
    const context = await this.buildContext();

    this.conversationHistory.push({
      role: "user",
      content: `${context}\n\n${userMessage}`,
    });

    const messages: ChatMessage[] = [
      { role: "system", content: SYSTEM_PROMPT },
      ...this.conversationHistory,
    ];

    let fullResponse = "";
    for await (const chunk of this.llm.streamChat(messages)) {
      fullResponse += chunk;
      yield chunk;
    }

    this.conversationHistory.push({
      role: "assistant",
      content: fullResponse,
    });
  }

  private async buildContext(): Promise<string> {
    const parts: string[] = [];

    // Active file info
    const editor = vscode.window.activeTextEditor;
    if (editor) {
      const doc = editor.document;
      const relPath = vscode.workspace.asRelativePath(doc.uri);
      parts.push(`[Current file: ${relPath} (${doc.languageId})]`);

      // If there's a selection, include it
      if (!editor.selection.isEmpty) {
        const selection = doc.getText(editor.selection);
        if (selection.length < 2000) {
          parts.push(`[Selected code:\n\`\`\`${doc.languageId}\n${selection}\n\`\`\`]`);
        }
      }
    }

    // Workspace info
    const folders = vscode.workspace.workspaceFolders;
    if (folders?.length) {
      parts.push(`[Workspace: ${folders[0].name}]`);
    }

    return parts.join("\n");
  }
}
