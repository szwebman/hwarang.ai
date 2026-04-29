export interface VerificationPrimarySource {
  name: string;
  url: string;
  trust: number;
  type?: string;
}

export interface VerificationClaim {
  text: string;
  confidence: number;
  verdict?: "verified" | "disputed" | "unverified";
  sourceCount: number;
  contradictionCount: number;
  primarySources: VerificationPrimarySource[];
}

export interface VerificationMeta {
  claims: VerificationClaim[];
  overallConfidence: number;
}

export interface RealtimeSource {
  title: string;
  url: string;
  source: string; // "naver" | "wikipedia" | "primary"
  trust: number;
}

export interface RealtimeMeta {
  used: boolean;
  sources: RealtimeSource[];
}

export interface VisionMeta {
  used: boolean;
  description: string;
  image_count: number;
  mode?: "general" | "code";
}

export interface ChatOption {
  id: string;
  title: string;
  description: string;
  keywords: string[];
  preview_emoji: string;
}

export interface OptionsMeta {
  deliverable: string;
  options: ChatOption[];
  /**
   * 사용자가 카드 클릭 후 선택한 옵션 ID. 같은 메시지 안에서 인라인으로 답변이
   * 이어지는 Claude-style 흐름에서 카드를 잠그고 시각적으로 표시하기 위해 사용.
   */
  selectedOptionId?: string;
}

export interface MessageMeta {
  verification?: VerificationMeta;
  realtime?: RealtimeMeta;
  vision?: VisionMeta;
  options?: OptionsMeta;
  [key: string]: any;
}

export interface AttachedImage {
  /** 전체 data URL (e.g. "data:image/png;base64,iVBO..."). 서버 전송 + 미리보기 폴백용. */
  base64: string;
  /** 클라이언트 표시용 ObjectURL (대용량 이미지 렌더 최적화) */
  preview?: string;
  /** MIME type ("image/png" 등) */
  type: string;
  /** 원본 파일명 (선택) */
  name?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  /** 사용자 첨부 이미지 (VLM 분석 대상) */
  images?: AttachedImage[];
  createdAt: Date;
  meta?: MessageMeta;
}

export interface Conversation {
  id: string;
  title: string;
  model: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

export interface ChatCompletionChunk {
  id: string;
  object: "chat.completion.chunk";
  created: number;
  model: string;
  choices: {
    index: number;
    delta: {
      role?: string;
      content?: string;
    };
    finish_reason: string | null;
  }[];
}
