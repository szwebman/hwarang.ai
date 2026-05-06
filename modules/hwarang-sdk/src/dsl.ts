import type { HwarangClient } from "./client";
import type {
  ChatRequest,
  ChatResponse,
  DoRequest,
  DoResponse,
  Format,
  Identity,
  Intent,
  Language,
  Scope,
} from "./types";

/**
 * DSL 헬퍼 — `Hwarang` 메인 클래스에서 사용.
 * 짧은 호출로 자주 쓰는 패턴을 캡슐화.
 */
export class HwarangDSL {
  constructor(private readonly client: HwarangClient) {}

  /**
   * 한 줄 질문. format 이 "markup" 이면 응답의 markup 자동 파싱됨.
   */
  ask(
    text: string,
    opts?: {
      language?: Language;
      format?: Format;
      identity?: Identity;
      model?: string;
    },
  ): Promise<ChatResponse> {
    return this.client.chatCompletion({
      model: opts?.model,
      messages: [{ role: "user", content: text }],
      hwarang: {
        language: opts?.language ?? "ko",
        format: opts?.format ?? "plain",
        identity: opts?.identity ?? "strict",
      },
    });
  }

  /**
   * /v1/hwarang/do — intent 기반 단순 엔트리.
   */
  do(req: DoRequest): Promise<DoResponse> {
    return this.client.do(req);
  }

  /**
   * intent 별 편의 메서드. `do()` 의 단축형.
   */
  refactor(input: string, opts: Partial<DoRequest> = {}): Promise<DoResponse> {
    return this.do({ intent: "refactor", input, ...opts });
  }

  explain(input: string, opts: Partial<DoRequest> = {}): Promise<DoResponse> {
    return this.do({ intent: "explain", input, ...opts });
  }

  fix(input: string, opts: Partial<DoRequest> = {}): Promise<DoResponse> {
    return this.do({ intent: "fix", input, ...opts });
  }

  add(input: string, opts: Partial<DoRequest> = {}): Promise<DoResponse> {
    return this.do({ intent: "add", input, ...opts });
  }

  test(input: string, opts: Partial<DoRequest> = {}): Promise<DoResponse> {
    return this.do({ intent: "test", input, ...opts });
  }

  review(input: string, opts: Partial<DoRequest> = {}): Promise<DoResponse> {
    return this.do({ intent: "review", input, ...opts });
  }

  /**
   * 멀티턴 대화 — 메시지 배열 그대로 전송, markup 자동 파싱 포함.
   */
  chat(req: ChatRequest): Promise<ChatResponse> {
    return this.client.chatCompletion(req);
  }

  /**
   * 스트리밍 응답. AsyncIterable<chunk> 반환.
   */
  stream(req: ChatRequest) {
    return this.client.chatCompletionStream(req);
  }
}

// 편의 type re-export
export type { Intent, Scope, Language, Format, Identity };
