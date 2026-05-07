/**
 * HSEE Phase 1 — Implicit Feedback Tracker (VS Code 전용)
 *
 * 명시 피드백 (👍/👎) 절대 수집하지 않음. 다음 신호만 추적한다:
 *   - Apply 클릭     → positive 약신호 (사용자가 코드를 수용)
 *   - Apply 후 N초 내 파일 수정 → edit distance 계산 (낮을수록 positive)
 *   - Copy 클릭      → positive 약신호 (코드 활용 의도)
 *   - Reject (취소)  → 약 negative
 *
 * 호출 흐름:
 *   chat-view-provider 가 webview 에서 받은 message 를 처리하면서
 *   해당 사용자 액션 종류에 맞는 record* 메서드를 fire-and-forget 으로 호출.
 *
 * 모든 POST 는 실패해도 침묵 (사용자 경험에 영향 X).
 */

import * as vscode from "vscode";

interface FeedbackPostBody {
  message_id: string;
  user_id: string;
  rating: number; // -1, 0, 1
  comment?: string | null;
}

/**
 * 트래킹 시작 시점의 코드 스냅샷 — Apply 후 사용자가 추가로 수정했는지 비교용.
 */
interface AppliedSnapshot {
  messageId: string;
  appliedCode: string;
  documentUri: string;
  startVersion: number;
  appliedAt: number;
}

/**
 * 짧은 정규화 거리 (Levenshtein 0~1).
 * 매우 큰 문자열은 1500자에서 잘라 가벼운 비교만 수행.
 */
function normalizedEditDistance(a: string, b: string): number {
  const A = (a || "").slice(0, 1500);
  const B = (b || "").slice(0, 1500);
  if (!A.length && !B.length) return 0;
  if (!A.length || !B.length) return 1;

  const m = A.length;
  const n = B.length;
  const prev = new Array(n + 1).fill(0);
  const curr = new Array(n + 1).fill(0);
  for (let j = 0; j <= n; j++) prev[j] = j;
  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = A[i - 1] === B[j - 1] ? 0 : 1;
      curr[j] = Math.min(
        prev[j] + 1,
        curr[j - 1] + 1,
        prev[j - 1] + cost,
      );
    }
    for (let j = 0; j <= n; j++) prev[j] = curr[j];
  }
  return prev[n] / Math.max(m, n);
}

export class FeedbackTracker {
  private apiUrl: string;
  private getApiKey: () => string | null;
  private getUserId: () => string | null;

  // Apply 직후 30 초간 모니터링하는 스냅샷
  private pendingSnapshots = new Map<string, AppliedSnapshot>();
  private disposables: vscode.Disposable[] = [];

  // followup window — 짧은 시간(60초) 안에 동일 메시지 재참조시 부정 신호 보강
  private MONITOR_WINDOW_MS = 30_000;

  constructor(opts: {
    apiUrl: string;
    getApiKey: () => string | null;
    getUserId: () => string | null;
  }) {
    this.apiUrl = opts.apiUrl;
    this.getApiKey = opts.getApiKey;
    this.getUserId = opts.getUserId;

    // 파일 변경 감지 — pendingSnapshots 의 documentUri 와 매칭되면 distance 계산.
    // 디바운스: 동일 messageId 는 마지막 변경 후 1.5초 뒤 1번만 전송.
    let debounceTimer: NodeJS.Timeout | null = null;
    this.disposables.push(
      vscode.workspace.onDidChangeTextDocument((evt) => {
        const uri = evt.document.uri.toString();
        const matches = Array.from(this.pendingSnapshots.values()).filter(
          (s) => s.documentUri === uri,
        );
        if (matches.length === 0) return;

        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          for (const snap of matches) {
            this.flushSnapshot(snap, evt.document.getText());
          }
        }, 1500);
      }),
    );
  }

  dispose() {
    for (const d of this.disposables) d.dispose();
    this.pendingSnapshots.clear();
  }

  /**
   * Apply 버튼 클릭 — 약 positive 즉시 + 스냅샷 시작.
   */
  recordApply(messageId: string | null | undefined, appliedCode: string) {
    if (!messageId) return;
    void this.post({
      message_id: messageId,
      user_id: this.getUserId() || "vscode-anon",
      rating: 1,
      comment: "[implicit:apply]",
    });

    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    const snap: AppliedSnapshot = {
      messageId,
      appliedCode,
      documentUri: editor.document.uri.toString(),
      startVersion: editor.document.version,
      appliedAt: Date.now(),
    };
    this.pendingSnapshots.set(messageId, snap);

    // 30 초 후 자동 정리 (변경 없으면 그대로 positive 유지)
    setTimeout(() => {
      this.pendingSnapshots.delete(messageId);
    }, this.MONITOR_WINDOW_MS);
  }

  /**
   * Copy 버튼 클릭 — 약 positive 1회만.
   */
  recordCopy(messageId: string | null | undefined) {
    if (!messageId) return;
    void this.post({
      message_id: messageId,
      user_id: this.getUserId() || "vscode-anon",
      rating: 1,
      comment: "[implicit:copy]",
    });
  }

  /**
   * Reject 버튼 클릭 — 약 negative.
   */
  recordReject(messageId: string | null | undefined) {
    if (!messageId) return;
    void this.post({
      message_id: messageId,
      user_id: this.getUserId() || "vscode-anon",
      rating: -1,
      comment: "[implicit:reject]",
    });
  }

  /**
   * Apply 후 사용자 수정 발생 — distance 계산 + comment 에 메타 첨부.
   * distance 가 매우 작으면 (<0.05) skip — 노이즈.
   */
  private async flushSnapshot(snap: AppliedSnapshot, currentText: string) {
    if (!this.pendingSnapshots.has(snap.messageId)) return;
    this.pendingSnapshots.delete(snap.messageId);

    // 적용한 코드 자체가 currentText 안에 포함돼 있으면 — 사용자가 그대로 둔 것.
    const stillIntact = currentText.includes(snap.appliedCode.trim());
    let distance = stillIntact
      ? 0
      : normalizedEditDistance(snap.appliedCode, currentText);
    if (distance < 0.05) distance = 0;

    // distance 가 작을수록 positive (rating=0 으로 두고 editDistance 메타로만 전달)
    void this.post({
      message_id: snap.messageId,
      user_id: this.getUserId() || "vscode-anon",
      rating: 0,
      comment: `[implicit:edit_distance=${distance.toFixed(3)}]`,
    });
  }

  private async post(body: FeedbackPostBody): Promise<void> {
    const url = `${this.apiUrl.replace(/\/$/, "")}/api/learning/feedback`;
    const apiKey = this.getApiKey();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
    try {
      // VS Code 18+ Node 의 fetch 가 글로벌. 실패해도 침묵.
      await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
    } catch {
      // ignore — 사용자 경험에 영향 주지 말 것
    }
  }
}

export type { FeedbackPostBody };
