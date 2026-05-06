/**
 * HwarangError — 모든 SDK 에러의 기본 클래스.
 *
 * - status: HTTP 상태 코드 (네트워크 호출 실패 시)
 * - code: 화랑 API 가 반환한 에러 코드 (예: "rate_limited", "invalid_api_key")
 */
export class HwarangError extends Error {
  public readonly status?: number;
  public readonly code?: string;

  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = "HwarangError";
    this.status = status;
    this.code = code;

    // V8 stack trace 정리
    if (typeof (Error as any).captureStackTrace === "function") {
      (Error as any).captureStackTrace(this, HwarangError);
    }
  }
}
