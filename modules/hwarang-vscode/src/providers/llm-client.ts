/**
 * LLM Client - Hwarang AI API (SSE streaming) + OpenAI/Anthropic fallback
 *
 * Primary: https://hwarang.ai/api/chat (SSE)
 * Auth: Bearer token from AuthManager
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
  private abortController: AbortController | null = null;

  constructor() {
    this.config = this.loadConfig();
  }

  refreshConfig() {
    this.config = this.loadConfig();
  }

  abort() {
    this.abortController?.abort();
    this.abortController = null;
  }

  private loadConfig(): Config {
    const cfg = vscode.workspace.getConfiguration("hwarang");
    return {
      provider: cfg.get("provider", "hwarang"),
      apiUrl: cfg.get("apiUrl", "https://hwarang.ai"),
      model: cfg.get("model", "hwarang-default"),
      openaiApiKey: cfg.get("openaiApiKey", ""),
      anthropicApiKey: cfg.get("anthropicApiKey", ""),
      temperature: cfg.get("temperature", 0.7),
      maxTokens: cfg.get("maxTokens", 4096),
    };
  }

  private getApiKey(): string | null {
    // Try to get from SecretStorage via auth headers
    const cfg = vscode.workspace.getConfiguration("hwarang");
    return cfg.get("_apiKey", null);
  }

  /**
   * Non-streaming chat completion with tool support.
   */
  async chat(messages: ChatMessage[], tools?: object[]): Promise<LLMResponse> {
    const { provider } = this.config;
    if (provider === "anthropic") return this.chatAnthropic(messages, tools);
    if (provider === "openai") return this.chatOpenAI(messages, tools);
    return this.chatHwarang(messages, tools);
  }

  /**
   * SSE streaming chat completion.
   */
  async *streamChat(
    messages: ChatMessage[],
    signal?: AbortSignal
  ): AsyncGenerator<string, void, unknown> {
    const { provider } = this.config;
    if (provider === "anthropic") {
      yield* this.streamAnthropic(messages, signal);
      return;
    }
    if (provider === "openai") {
      yield* this.streamOpenAI(messages, signal);
      return;
    }
    yield* this.streamHwarang(messages, signal);
  }

  // ================================================================
  // Hwarang AI (Primary) - SSE endpoint
  // ================================================================

  private getHwarangHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    };
    // API key injected by AuthManager
    const apiKey = (this as any)._injectedApiKey;
    if (apiKey) {
      headers["Authorization"] = `Bearer ${apiKey}`;
    }
    return headers;
  }

  /** Inject API key from AuthManager (avoids circular dependency) */
  setApiKey(key: string | null) {
    (this as any)._injectedApiKey = key;
  }

  private async chatHwarang(
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
    if (tools?.length) body.tools = tools;

    const url = `${this.config.apiUrl}/api/chat`;
    const resp = await fetch(url, {
      method: "POST",
      headers: this.getHwarangHeaders(),
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`Hwarang API ${resp.status}: ${errText}`);
    }

    const data = (await resp.json()) as any;

    // Support both OpenAI-compatible and custom format
    if (data.choices) {
      const choice = data.choices[0];
      return {
        content: choice.message?.content ?? null,
        toolCalls: choice.message?.tool_calls || null,
        finishReason: choice.finish_reason || "stop",
      };
    }

    // Custom Hwarang format
    return {
      content: data.response || data.content || data.message || null,
      toolCalls: data.tool_calls || null,
      finishReason: data.finish_reason || "stop",
    };
  }

  private async *streamHwarang(
    messages: ChatMessage[],
    signal?: AbortSignal
  ): AsyncGenerator<string, void, unknown> {
    const body = {
      model: this.config.model,
      messages,
      temperature: this.config.temperature,
      max_tokens: this.config.maxTokens,
      stream: true,
    };

    const url = `${this.config.apiUrl}/api/chat`;
    const resp = await fetch(url, {
      method: "POST",
      headers: this.getHwarangHeaders(),
      body: JSON.stringify(body),
      signal,
    });

    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`Hwarang API ${resp.status}: ${errText}`);
    }

    yield* this.parseSSEStream(resp, signal);
  }

  // ================================================================
  // OpenAI compatible
  // ================================================================

  private async chatOpenAI(
    messages: ChatMessage[],
    tools?: object[]
  ): Promise<LLMResponse> {
    const body: Record<string, unknown> = {
      model: this.config.model || "gpt-4o",
      messages,
      temperature: this.config.temperature,
      max_tokens: this.config.maxTokens,
      stream: false,
    };
    if (tools?.length) body.tools = tools;

    const resp = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.config.openaiApiKey}`,
      },
      body: JSON.stringify(body),
    });

    if (!resp.ok) throw new Error(`OpenAI ${resp.status}: ${await resp.text()}`);

    const data = (await resp.json()) as any;
    const choice = data.choices[0];
    return {
      content: choice.message.content,
      toolCalls: choice.message.tool_calls || null,
      finishReason: choice.finish_reason || "stop",
    };
  }

  private async *streamOpenAI(
    messages: ChatMessage[],
    signal?: AbortSignal
  ): AsyncGenerator<string, void, unknown> {
    const body = {
      model: this.config.model || "gpt-4o",
      messages,
      temperature: this.config.temperature,
      max_tokens: this.config.maxTokens,
      stream: true,
    };

    const resp = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.config.openaiApiKey}`,
      },
      body: JSON.stringify(body),
      signal,
    });

    if (!resp.ok) throw new Error(`OpenAI ${resp.status}: ${await resp.text()}`);
    yield* this.parseSSEStream(resp, signal);
  }

  // ================================================================
  // Anthropic
  // ================================================================

  private async chatAnthropic(
    messages: ChatMessage[],
    tools?: object[]
  ): Promise<LLMResponse> {
    let systemMsg = "";
    const chatMsgs = messages.filter((m) => {
      if (m.role === "system") {
        systemMsg = m.content;
        return false;
      }
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

    if (!resp.ok) throw new Error(`Anthropic ${resp.status}: ${await resp.text()}`);

    const data = (await resp.json()) as any;
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
    messages: ChatMessage[],
    signal?: AbortSignal
  ): AsyncGenerator<string, void, unknown> {
    let systemMsg = "";
    const chatMsgs = messages.filter((m) => {
      if (m.role === "system") {
        systemMsg = m.content;
        return false;
      }
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
      signal,
    });

    if (!resp.ok) throw new Error(`Anthropic ${resp.status}: ${await resp.text()}`);

    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (signal?.aborted) break;

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

  // ================================================================
  // Shared SSE parser (OpenAI-compatible format)
  // ================================================================

  private async *parseSSEStream(
    resp: Response,
    signal?: AbortSignal
  ): AsyncGenerator<string, void, unknown> {
    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (signal?.aborted) break;

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
            // OpenAI format
            const content = parsed.choices?.[0]?.delta?.content;
            if (content) {
              yield content;
              continue;
            }
            // Hwarang custom format
            if (parsed.text) {
              yield parsed.text;
              continue;
            }
            if (parsed.content) {
              yield parsed.content;
              continue;
            }
            if (parsed.delta) {
              yield typeof parsed.delta === "string" ? parsed.delta : parsed.delta.content || "";
            }
          } catch {
            // Skip malformed chunks
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }
}
