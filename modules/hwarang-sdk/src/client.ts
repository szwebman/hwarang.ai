import type {
  ChatRequest,
  ChatResponse,
  ChatStreamChunk,
  DoRequest,
  DoResponse,
  HwarangExtension,
  HwarangResponseMeta,
} from "./types";
import { parseMarkup } from "./markup";
import { parseSSEStream } from "./streaming";
import { HwarangError } from "./errors";

export interface ClientOptions {
  /** 화랑 API 키. 없으면 process.env.HWARANG_API_KEY 사용 */
  apiKey?: string;
  /** API base URL. 기본: https://hwarang.ai */
  apiUrl?: string;
  /** 기본 모델명. 기본: "hwarang" */
  defaultModel?: string;
  /** 요청 타임아웃 (ms). 기본: 120000 */
  timeout?: number;
  /** 추가 fetch 옵션 (proxy 등) — 고급 사용 */
  fetchOptions?: RequestInit;
}

/**
 * HwarangClient — fetch 기반 저수준 HTTP 클라이언트.
 * 일반 사용자는 `new Hwarang(...)` 사용 권장.
 */
export class HwarangClient {
  private apiKey: string;
  private apiUrl: string;
  private defaultModel: string;
  private timeout: number;
  private fetchOptions: RequestInit;

  constructor(opts: ClientOptions = {}) {
    const envKey =
      typeof process !== "undefined" && process.env
        ? process.env.HWARANG_API_KEY
        : undefined;
    const envUrl =
      typeof process !== "undefined" && process.env
        ? process.env.HWARANG_API_URL
        : undefined;

    this.apiKey = opts.apiKey || envKey || "";
    this.apiUrl = (opts.apiUrl || envUrl || "https://hwarang.ai").replace(
      /\/$/,
      "",
    );
    this.defaultModel = opts.defaultModel || "hwarang";
    this.timeout = opts.timeout ?? 120_000;
    this.fetchOptions = opts.fetchOptions || {};
  }

  // ─────────────────────────────────────────────────────────
  // public API
  // ─────────────────────────────────────────────────────────

  /**
   * OpenAI 호환 chat completion. `req.hwarang` 가 있으면 wire 상에서
   * `@hwarang` 필드로 전송.
   */
  async chatCompletion(req: ChatRequest): Promise<ChatResponse> {
    const body = this.buildChatBody(req, false);
    const raw = await this.postJson<any>("/v1/chat/completions", body);
    return this.enhanceResponse(raw, req.hwarang);
  }

  /**
   * 스트리밍 chat completion. AsyncIterable 로 chunk 를 yield.
   */
  async chatCompletionStream(
    req: ChatRequest,
  ): Promise<AsyncIterable<ChatStreamChunk>> {
    const body = this.buildChatBody(req, true);
    const resp = await this.postRaw("/v1/chat/completions", body, {
      Accept: "text/event-stream",
    });
    return parseSSEStream(resp.body);
  }

  /**
   * /v1/hwarang/do — DSL 기반 단순 엔트리.
   */
  async do(req: DoRequest): Promise<DoResponse> {
    const raw = await this.postJson<any>("/v1/hwarang/do", req);
    return {
      ok: !!raw.ok,
      summary: raw.summary || "",
      files_changed: raw.files_changed || [],
      next_steps: raw.next_steps || [],
      hwarang: raw["@hwarang"] || raw.hwarang,
    };
  }

  // ─────────────────────────────────────────────────────────
  // internal
  // ─────────────────────────────────────────────────────────

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Hwarang-SDK": "ts/1.0",
      ...extra,
    };
    if (this.apiKey) h["Authorization"] = `Bearer ${this.apiKey}`;
    return h;
  }

  private buildChatBody(req: ChatRequest, stream: boolean): Record<string, any> {
    const body: Record<string, any> = {
      model: req.model || this.defaultModel,
      messages: req.messages,
      max_tokens: req.max_tokens ?? 16_384,
      stream,
    };
    if (req.tools) {
      body.tools = req.tools;
      body.tool_choice = req.tool_choice ?? "auto";
    }
    if (req.temperature != null) body.temperature = req.temperature;
    if (req.hwarang) body["@hwarang"] = req.hwarang;
    return body;
  }

  private async postJson<T>(path: string, body: unknown): Promise<T> {
    const resp = await this.postRaw(path, body);
    return (await resp.json()) as T;
  }

  private async postRaw(
    path: string,
    body: unknown,
    extraHeaders: Record<string, string> = {},
  ): Promise<Response> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeout);
    try {
      const resp = await fetch(`${this.apiUrl}${path}`, {
        ...this.fetchOptions,
        method: "POST",
        headers: this.headers(extraHeaders),
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        const { message, code } = parseError(text, `HTTP ${resp.status}`);
        throw new HwarangError(message, resp.status, code);
      }
      return resp;
    } catch (e) {
      if (e instanceof HwarangError) throw e;
      if (e instanceof Error && e.name === "AbortError") {
        throw new HwarangError(
          `요청 타임아웃 (${this.timeout}ms)`,
          undefined,
          "timeout",
        );
      }
      throw new HwarangError(
        e instanceof Error ? e.message : String(e),
        undefined,
        "network_error",
      );
    } finally {
      clearTimeout(timer);
    }
  }

  /**
   * 원본 응답에서 SDK 편의 필드 (text, toolCalls, markup, hwarang) 를 추출.
   */
  private enhanceResponse(
    raw: any,
    ext?: HwarangExtension,
  ): ChatResponse {
    const choice = raw?.choices?.[0];
    const content: string = choice?.message?.content ?? "";
    const meta: HwarangResponseMeta | undefined =
      raw?.["@hwarang"] || raw?.hwarang;

    // markup 자동 파싱:
    //   1) 서버가 @hwarang.markup 으로 미리 파싱해서 보냈으면 그대로 사용
    //   2) 아니면 클라이언트가 format: "markup" 요청한 경우 직접 파싱
    let markup = meta?.markup;
    if (!markup && ext?.format === "markup" && content) {
      markup = parseMarkup(content);
    }

    return {
      id: raw?.id ?? "",
      object: raw?.object ?? "chat.completion",
      model: raw?.model ?? "",
      choices: raw?.choices ?? [],
      usage: raw?.usage ?? {
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0,
      },
      hwarang: meta,
      text: content,
      toolCalls: choice?.message?.tool_calls ?? [],
      markup,
    };
  }
}

// ─────────────────────────────────────────────────────────
// helpers
// ─────────────────────────────────────────────────────────

function parseError(
  text: string,
  fallback: string,
): { message: string; code?: string } {
  if (!text) return { message: fallback };
  try {
    const j = JSON.parse(text);
    const message =
      j.error?.message || j.error || j.message || j.detail || fallback;
    const code = j.error?.code || j.code;
    return { message: typeof message === "string" ? message : fallback, code };
  } catch {
    return { message: text.slice(0, 200) || fallback };
  }
}
