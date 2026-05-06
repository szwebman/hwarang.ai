// HP (Hwarang Protocol) v1.0 — TypeScript types
// Mirrors docs/hp-protocol.md exactly.

// ─────────────────────────────────────────────────────────
// OpenAI 호환 타입
// ─────────────────────────────────────────────────────────

export interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
}

export interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export interface ToolDefinition {
  type: "function";
  function: {
    name: string;
    description?: string;
    parameters?: object;
  };
}

// ─────────────────────────────────────────────────────────
// HP 확장 타입
// ─────────────────────────────────────────────────────────

export type Intent =
  | "refactor"
  | "explain"
  | "fix"
  | "add"
  | "test"
  | "review"
  | "optimize"
  | "secure"
  | "document"
  | "translate"
  | "diagnose"
  | "commit"
  | "plan";

export type Scope = "line" | "selection" | "file" | "module" | "project";
export type Language = "ko" | "en" | "mixed";
export type Format = "plain" | "markup" | "json";
export type Identity = "strict" | "lenient";
export type Safety = "loose" | "standard" | "strict";
export type Expertise = "junior" | "mid" | "senior";
export type Style = "functional" | "oop" | "declarative" | "imperative" | string;

export interface WorkflowStep {
  id: string;
  tool?: string;
  command?: string;
  depends?: string[];
}

export interface Workflow {
  name?: string;
  steps?: WorkflowStep[];
  on_fail?: "abort" | "retry-once" | "continue" | "rollback";
  max_iterations?: number;
}

export interface WorkspaceHint {
  root?: string;
  stack?: string[];
  branch?: string;
}

export interface HwarangExtension {
  // Prompt DSL
  intent?: Intent;
  scope?: Scope;
  target?: string;
  language?: Language;
  constraints?: string[];
  style?: Style;
  expertise?: Expertise;

  // Output Markup
  format?: Format;
  include?: string[];

  // Workflow
  workflow?: Workflow;

  // Identity / Safety
  identity?: Identity;
  safety?: Safety;
  redact_secrets?: boolean;

  // Context Hints
  workspace?: WorkspaceHint;

  // Telemetry
  telemetry?: string[];
}

// ─────────────────────────────────────────────────────────
// Markup 파싱 결과
// ─────────────────────────────────────────────────────────

export interface MarkupPlanItem {
  id: string;
  title: string;
  status: string;
}

export interface MarkupDiff {
  path: string;
  added: number;
  removed: number;
  raw?: string;
}

export interface MarkupSuggestion {
  level: string;
  text: string;
}

export interface MarkupNote {
  text: string;
}

export interface MarkupSection {
  plan: MarkupPlanItem[];
  diffs: MarkupDiff[];
  suggestions: MarkupSuggestion[];
  warnings: MarkupNote[];
  errors: MarkupNote[];
  summary?: string;
}

// ─────────────────────────────────────────────────────────
// 응답 메타데이터
// ─────────────────────────────────────────────────────────

export interface ToolCallMeta {
  id: string;
  risk?: "low" | "medium" | "high";
  auto_approved?: boolean;
  needs_user?: boolean;
}

export interface WorkflowProgress {
  name?: string;
  current_step?: string;
  completed?: string[];
  remaining?: string[];
}

export interface HwarangResponseMeta {
  format_used?: Format;
  lora_used?: string;
  identity?: string;
  identity_confidence?: number;
  markup?: MarkupSection;
  tool_calls_meta?: ToolCallMeta[];
  workflow?: WorkflowProgress;
  telemetry?: Record<string, any>;
}

// ─────────────────────────────────────────────────────────
// Request / Response
// ─────────────────────────────────────────────────────────

export type ToolChoice =
  | "auto"
  | "none"
  | { type: "function"; function: { name: string } };

export interface ChatRequest {
  model?: string;
  messages: ChatMessage[];
  tools?: ToolDefinition[];
  tool_choice?: ToolChoice;
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
  /** SDK 측 — 내부에서 `@hwarang` 으로 wire 전송 */
  hwarang?: HwarangExtension;
}

export interface ChatChoice {
  index: number;
  message: ChatMessage;
  finish_reason: string;
}

export interface ChatUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ChatResponse {
  id: string;
  object: string;
  model: string;
  choices: ChatChoice[];
  usage: ChatUsage;

  /** 응답에서 추출된 화랑 전용 필드 */
  hwarang?: HwarangResponseMeta;

  // 첫 번째 choice 의 편의 접근자
  text: string;
  toolCalls: ToolCall[];
  markup?: MarkupSection;
}

// ─────────────────────────────────────────────────────────
// /v1/hwarang/do 단순 엔트리
// ─────────────────────────────────────────────────────────

export interface DoRequest {
  intent: Intent;
  scope?: Scope;
  target?: string;
  language?: Language;
  input: string;
  constraints?: string[];
  workflow?: string[] | Workflow;
}

export interface DoResponse {
  ok: boolean;
  summary: string;
  files_changed: string[];
  next_steps: string[];
  hwarang?: HwarangResponseMeta;
}

// ─────────────────────────────────────────────────────────
// Streaming
// ─────────────────────────────────────────────────────────

export interface ChatStreamChunk {
  id: string;
  object: string;
  model: string;
  choices: Array<{
    index: number;
    delta: Partial<ChatMessage>;
    finish_reason: string | null;
  }>;
}
