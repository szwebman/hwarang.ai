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

/**
 * 옵션 카드 1개 (웹과 동일 스키마, options.py 의 generate 응답).
 */
export interface OptionCard {
  id: string;
  title: string;
  description: string;
  keywords: string[];
  preview_emoji: string;
}

/**
 * 직접 chat 호출 응답 (옵션 모드 / 일반 답변 통합).
 */
export type DirectChatResponse =
  | {
      type: "options";
      intro: string;
      options: OptionCard[];
      deliverable?: string;
      conversationId?: string;
    }
  | {
      type: "answer";
      content: string;
      model?: string;
      chargedTokens?: number;
      latencyMs?: number;
      conversationId?: string;
    };

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
      stop: ["<|im_start|>", "<|im_end|>"],
    };
    if (tools?.length) {
      body.tools = tools;
      body.tool_choice = "auto";
    }

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
  // Direct chat (옵션 모드 / 이미지 / 사용량 메타) — 웹과 동등
  // ================================================================

  /**
   * /api/chat 단일턴 호출. AgentLoop 의 conversationHistory 와 별개로
   * webview 가 직접 user 메시지+이미지를 보내고 옵션/답변/메타를 받는 경로.
   *
   * - 옵션 응답이 오면 _meta.options 를 그대로 노출
   * - 일반 답변이면 choices[0].message.content + _meta 를 OpenAI 호환 처리
   * - non-stream 으로만 동작 (스트리밍은 후속 작업)
   */
  async chatDirect(params: {
    text: string;
    images?: string[]; // base64 data URLs (data:image/png;base64,...)
    model?: string;
    safety?: string;
    conversationId?: string;
    history?: { role: "user" | "assistant"; content: string }[];
  }): Promise<DirectChatResponse> {
    const url = `${this.config.apiUrl}/api/chat`;

    const userContent: any =
      params.images && params.images.length > 0
        ? {
            role: "user",
            content: params.text,
            images: params.images,
          }
        : { role: "user", content: params.text };

    const messages = [...(params.history || []), userContent];

    const body: Record<string, unknown> = {
      model: params.model || this.config.model,
      messages,
      temperature: this.config.temperature,
      max_tokens: this.config.maxTokens,
      stream: false,
    };
    if (params.safety) body.safety = params.safety;
    if (params.conversationId) body.conversationId = params.conversationId;

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
    const meta = data._meta || {};
    const conversationId = meta.conversationId;

    // 옵션 모드 응답 감지
    if (meta.options?.options?.length) {
      const intro =
        data.choices?.[0]?.message?.content ||
        `다음 ${meta.options.options.length}가지 중 선택해 주세요:`;
      return {
        type: "options",
        intro,
        options: meta.options.options,
        deliverable: meta.options.deliverable,
        conversationId,
      };
    }

    const content =
      data.choices?.[0]?.message?.content ||
      data.response ||
      data.content ||
      "";

    return {
      type: "answer",
      content,
      model: meta.model,
      chargedTokens: meta.chargedTokens,
      latencyMs: meta.latencyMs,
      conversationId,
    };
  }

  /**
   * 옵션 카드 클릭 후속 호출. continueOptionId/Title/Keywords 를 보내서
   * 같은 메시지에 답변을 이어붙임.
   */
  async continueMessage(params: {
    optionId: string;
    optionTitle: string;
    keywords: string[];
    messageId?: string;
    conversationId?: string;
    history?: { role: "user" | "assistant"; content: string }[];
  }): Promise<{ content: string; chargedTokens?: number; conversationId?: string }> {
    const url = `${this.config.apiUrl}/api/chat`;

    const body: Record<string, unknown> = {
      model: this.config.model,
      messages: params.history || [],
      continueOptionId: params.optionId,
      continueOptionTitle: params.optionTitle,
      continueOptionKeywords: params.keywords,
      stream: false,
      temperature: this.config.temperature,
      max_tokens: this.config.maxTokens,
    };
    if (params.messageId) body.continueMessageId = params.messageId;
    if (params.conversationId) body.conversationId = params.conversationId;

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
    const meta = data._meta || {};
    const content =
      data.choices?.[0]?.message?.content ||
      data.response ||
      data.content ||
      "";
    return {
      content,
      chargedTokens: meta.chargedTokens,
      conversationId: meta.conversationId,
    };
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
