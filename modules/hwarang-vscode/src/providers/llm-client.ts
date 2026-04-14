/**
 * LLM Client - Communicates with Hwarang API / OpenAI / Anthropic.
 *
 * Reads configuration from VS Code settings and provides a unified
 * interface for chat completions with streaming.
 */

import * as vscode from "vscode";

export interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}

export interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export interface LLMResponse {
  content: string | null;
  toolCalls: ToolCall[] | null;
  finishReason: string;
}

interface Config {
  provider: string;
  apiUrl: string;
  model: string;
  openaiApiKey: string;
  anthropicApiKey: string;
  temperature: number;
  maxTokens: number;
}

export class LLMClient {
  private config: Config;

  constructor() {
    this.config = this.loadConfig();
  }

  refreshConfig() {
    this.config = this.loadConfig();
  }

  private loadConfig(): Config {
    const cfg = vscode.workspace.getConfiguration("hwarang");
    return {
      provider: cfg.get("provider", "hwarang"),
      apiUrl: cfg.get("apiUrl", "http://localhost:8000"),
      model: cfg.get("model", "hwarang-small"),
      openaiApiKey: cfg.get("openaiApiKey", ""),
      anthropicApiKey: cfg.get("anthropicApiKey", ""),
      temperature: cfg.get("temperature", 0.7),
      maxTokens: cfg.get("maxTokens", 4096),
    };
  }

  /**
   * Send a chat completion request (non-streaming).
   */
  async chat(
    messages: ChatMessage[],
    tools?: object[]
  ): Promise<LLMResponse> {
    const { provider } = this.config;

    if (provider === "anthropic") {
      return this.chatAnthropic(messages, tools);
    }

    // Hwarang and OpenAI use the same OpenAI-compatible format
    return this.chatOpenAICompat(messages, tools);
  }

  /**
   * Stream a chat completion, yielding text chunks.
   */
  async *streamChat(
    messages: ChatMessage[]
  ): AsyncGenerator<string, void, unknown> {
    const { provider } = this.config;

    if (provider === "anthropic") {
      yield* this.streamAnthropic(messages);
      return;
    }

    yield* this.streamOpenAICompat(messages);
  }

  // ---- OpenAI-compatible (Hwarang API & OpenAI) ----

  private getOpenAIBaseUrl(): string {
    if (this.config.provider === "openai") {
      return "https://api.openai.com/v1";
    }
    return `${this.config.apiUrl}/v1`;
  }

  private getOpenAIHeaders(): Record<string, string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.config.provider === "openai" && this.config.openaiApiKey) {
      headers["Authorization"] = `Bearer ${this.config.openaiApiKey}`;
    }
    return headers;
  }

  private async chatOpenAICompat(
    messages: ChatMessage[],
    tools?: object[]
  ): Promise<LLMResponse> {
    const body: Record<string, unknown> = {
      model: this.config.model,
      messages,
      temperature: this.config.temperature,
      max_tokens: this.config.maxTokens,
      stream: false,
    };
    if (tools?.length) {
      body.tools = tools;
    }

    const resp = await fetch(`${this.getOpenAIBaseUrl()}/chat/completions`, {
      method: "POST",
      headers: this.getOpenAIHeaders(),
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      throw new Error(`API error ${resp.status}: ${await resp.text()}`);
    }

    const data = await resp.json() as any;
    const choice = data.choices[0];

    return {
      content: choice.message.content,
      toolCalls: choice.message.tool_calls || null,
      finishReason: choice.finish_reason || "stop",
    };
  }

  private async *streamOpenAICompat(
    messages: ChatMessage[]
  ): AsyncGenerator<string, void, unknown> {
    const body = {
      model: this.config.model,
      messages,
      temperature: this.config.temperature,
      max_tokens: this.config.maxTokens,
      stream: true,
    };

    const resp = await fetch(`${this.getOpenAIBaseUrl()}/chat/completions`, {
      method: "POST",
      headers: this.getOpenAIHeaders(),
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      throw new Error(`API error ${resp.status}: ${await resp.text()}`);
    }

    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;
        const data = trimmed.slice(6);
        if (data === "[DONE]") return;

        try {
          const parsed = JSON.parse(data);
          const content = parsed.choices?.[0]?.delta?.content;
          if (content) yield content;
        } catch {
          // skip malformed chunks
        }
      }
    }
  }

  // ---- Anthropic ----

  private async chatAnthropic(
    messages: ChatMessage[],
    tools?: object[]
  ): Promise<LLMResponse> {
    let systemMsg = "";
    const chatMsgs = messages.filter((m) => {
      if (m.role === "system") { systemMsg = m.content; return false; }
      return true;
    });

    const body: Record<string, unknown> = {
      model: this.config.model || "claude-sonnet-4-6",
      messages: chatMsgs,
      max_tokens: this.config.maxTokens,
      temperature: this.config.temperature,
    };
    if (systemMsg) body.system = systemMsg;
    if (tools?.length) {
      body.tools = (tools as any[]).map((t: any) => ({
        name: t.function.name,
        description: t.function.description,
        input_schema: t.function.parameters,
      }));
    }

    const resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": this.config.anthropicApiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      throw new Error(`Anthropic error ${resp.status}: ${await resp.text()}`);
    }

    const data = await resp.json() as any;
    let content = "";
    const toolCalls: ToolCall[] = [];

    for (const block of data.content) {
      if (block.type === "text") content += block.text;
      if (block.type === "tool_use") {
        toolCalls.push({
          id: block.id,
          type: "function",
          function: { name: block.name, arguments: JSON.stringify(block.input) },
        });
      }
    }

    return {
      content: content || null,
      toolCalls: toolCalls.length ? toolCalls : null,
      finishReason: toolCalls.length ? "tool_calls" : "stop",
    };
  }

  private async *streamAnthropic(
    messages: ChatMessage[]
  ): AsyncGenerator<string, void, unknown> {
    let systemMsg = "";
    const chatMsgs = messages.filter((m) => {
      if (m.role === "system") { systemMsg = m.content; return false; }
      return true;
    });

    const body: Record<string, unknown> = {
      model: this.config.model || "claude-sonnet-4-6",
      messages: chatMsgs,
      max_tokens: this.config.maxTokens,
      temperature: this.config.temperature,
      stream: true,
    };
    if (systemMsg) body.system = systemMsg;

    const resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": this.config.anthropicApiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      throw new Error(`Anthropic error ${resp.status}: ${await resp.text()}`);
    }

    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === "content_block_delta" && data.delta?.text) {
            yield data.delta.text;
          }
        } catch {
          // skip
        }
      }
    }
  }
}
