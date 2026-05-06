import { HwarangClient, type ClientOptions } from "./client";
import { HwarangDSL } from "./dsl";
import { parseMarkup } from "./markup";
import { parseSSEStream, streamTextDeltas } from "./streaming";
import { HwarangError } from "./errors";

import type {
  ChatRequest,
  ChatResponse,
  ChatStreamChunk,
  DoRequest,
  DoResponse,
  Format,
  Identity,
  Language,
} from "./types";

export * from "./types";
export {
  HwarangClient,
  HwarangDSL,
  HwarangError,
  parseMarkup,
  parseSSEStream,
  streamTextDeltas,
};
export type { ClientOptions };

/**
 * 화랑 AI 메인 SDK 진입점 — OpenAI SDK 와 비슷한 인터페이스 + HP 확장.
 *
 * @example OpenAI 스타일
 * ```ts
 * const hwarang = new Hwarang({ apiKey: "hk-..." });
 * const r = await hwarang.chat.completions.create({
 *   messages: [{ role: "user", content: "안녕" }],
 * });
 * console.log(r.text);
 * ```
 *
 * @example HP DSL 스타일
 * ```ts
 * const r = await hwarang.do({
 *   intent: "add",
 *   scope: "module",
 *   target: "src/api/",
 *   input: "POST /api/orders 라우터",
 *   workflow: ["plan", "code", "test"],
 * });
 * console.log(r.summary, r.files_changed);
 * ```
 *
 * @example Markup 자동 파싱
 * ```ts
 * const r = await hwarang.chat.completions.create({
 *   messages: [{ role: "user", content: "package.json 을 react 18 로" }],
 *   hwarang: { format: "markup", include: ["plan", "diff"] },
 * });
 * console.log(r.markup?.plan);   // [{ id, title, status }, ...]
 * console.log(r.markup?.diffs);  // [{ path, added, removed }, ...]
 * ```
 *
 * @example 스트리밍
 * ```ts
 * for await (const chunk of await hwarang.stream({
 *   messages: [{ role: "user", content: "hello" }],
 * })) {
 *   process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
 * }
 * ```
 */
export class Hwarang {
  private readonly client: HwarangClient;
  private readonly dsl: HwarangDSL;

  /** OpenAI SDK 스타일: hwarang.chat.completions.create({...}) */
  readonly chat: {
    completions: {
      create: (req: ChatRequest) => Promise<ChatResponse>;
    };
  };

  /** intent 단축형 — refactor / fix / add / test / review / explain */
  readonly refactor: HwarangDSL["refactor"];
  readonly fix: HwarangDSL["fix"];
  readonly add: HwarangDSL["add"];
  readonly test: HwarangDSL["test"];
  readonly review: HwarangDSL["review"];
  readonly explain: HwarangDSL["explain"];

  constructor(opts: ClientOptions = {}) {
    this.client = new HwarangClient(opts);
    this.dsl = new HwarangDSL(this.client);

    this.chat = {
      completions: {
        create: (req: ChatRequest): Promise<ChatResponse> =>
          this.client.chatCompletion(req),
      },
    };

    this.refactor = this.dsl.refactor.bind(this.dsl);
    this.fix = this.dsl.fix.bind(this.dsl);
    this.add = this.dsl.add.bind(this.dsl);
    this.test = this.dsl.test.bind(this.dsl);
    this.review = this.dsl.review.bind(this.dsl);
    this.explain = this.dsl.explain.bind(this.dsl);
  }

  /** /v1/hwarang/do — DSL 단순 엔트리 */
  do(req: DoRequest): Promise<DoResponse> {
    return this.client.do(req);
  }

  /** 스트리밍 chat — AsyncIterable<chunk> */
  stream(req: ChatRequest): Promise<AsyncIterable<ChatStreamChunk>> {
    return this.client.chatCompletionStream(req);
  }

  /** 한 줄 질문 (markup 자동 파싱). */
  ask(
    text: string,
    opts?: {
      language?: Language;
      format?: Format;
      identity?: Identity;
      model?: string;
    },
  ): Promise<ChatResponse> {
    return this.dsl.ask(text, opts);
  }

  /** 저수준 client 노출 (고급 사용) */
  get raw(): HwarangClient {
    return this.client;
  }
}

export default Hwarang;
