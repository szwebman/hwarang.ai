/**
 * 인증 관리 - Claude Code 방식 브라우저 OAuth 로그인
 *
 * 로그인 흐름:
 * 1. 사용자가 "로그인" 클릭
 * 2. 브라우저에서 hwarang.ai/auth/vscode 열림
 * 3. 사이트에서 로그인 완료 → 콜백으로 API 키 전달
 * 4. VS Code가 API 키 수신 → SecretStorage 저장
 *
 * 대안: API 키 직접 입력
 */

import * as vscode from "vscode";
import * as http from "http";

export interface UserInfo {
  id: string;
  name: string;
  email: string;
  plan: {
    name: string;
    displayName: string;
    tokensIncluded: number;
    dailyTokenLimit: number;
  } | null;
  tokens: {
    balance: number;
    dailyUsed: number;
    dailyLimit: number;
    totalUsed: number;
  } | null;
}

export class AuthManager {
  private context: vscode.ExtensionContext;
  private statusBarItem: vscode.StatusBarItem;
  private _apiKey: string | null = null;
  private _user: UserInfo | null = null;
  private _refreshInterval: NodeJS.Timer | null = null;
  private _callbackServer: http.Server | null = null;

  private _onAuthChanged = new vscode.EventEmitter<UserInfo | null>();
  readonly onAuthChanged = this._onAuthChanged.event;

  constructor(context: vscode.ExtensionContext) {
    this.context = context;

    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      99
    );
    this.statusBarItem.command = "hwarang.showTokenStatus";
    context.subscriptions.push(this.statusBarItem);
  }

  // ============================================================
  // 초기화
  // ============================================================

  async initialize(): Promise<boolean> {
    const savedKey = await this.context.secrets.get("hwarang-api-key");
    if (savedKey) {
      this._apiKey = savedKey;
      const success = await this.fetchUserInfo();
      if (success) {
        this.startTokenRefresh();
        return true;
      }
      await this.context.secrets.delete("hwarang-api-key");
      this._apiKey = null;
    }

    this.updateStatusBar();
    return false;
  }

  // ============================================================
  // 로그인 방법 1: 브라우저 OAuth (Claude Code 방식)
  // ============================================================

  async loginWithBrowser(): Promise<boolean> {
    return new Promise(async (resolve) => {
      let settled = false;
      const finish = (ok: boolean) => {
        if (settled) return;
        settled = true;
        this.stopCallbackServer();
        resolve(ok);
      };

      try {
        // 로컬 콜백 서버 시작 (API 키 수신)
        const port = await this.startCallbackServer(async (apiKey) => {
          const ok = await this.loginWithApiKey(apiKey);
          finish(ok);
        });

        // 브라우저에서 인증 페이지 열기
        const apiUrl = this.getApiUrl();
        const authUrl = `${apiUrl}/auth/vscode?callback_port=${port}&editor=vscode`;
        vscode.env.openExternal(vscode.Uri.parse(authUrl));

        // 진행 알림 (5분 타임아웃, 사용자 취소 가능)
        vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: "화랑 AI: 브라우저에서 로그인을 완료해주세요",
            cancellable: true,
          },
          async (progress, token) => {
            progress.report({
              message: "브라우저에서 로그인 후 자동으로 연결됩니다",
            });

            token.onCancellationRequested(() => finish(false));

            // 5분 대기 (300초) — NextAuth OAuth는 시간이 걸릴 수 있음
            const TIMEOUT_MS = 5 * 60 * 1000;
            const start = Date.now();
            while (!settled && Date.now() - start < TIMEOUT_MS) {
              await new Promise((r) => setTimeout(r, 500));
              if (token.isCancellationRequested) break;
            }

            if (!settled) {
              vscode.window.showWarningMessage(
                "화랑 AI: 로그인 시간이 초과되었습니다. 다시 시도하세요."
              );
              finish(false);
            }
          }
        );
      } catch (e: any) {
        vscode.window.showErrorMessage(
          `화랑 AI: 콜백 서버 시작 실패 - ${e.message}`
        );
        finish(false);
      }
    });
  }

  private startCallbackServer(
    onApiKey: (key: string) => void
  ): Promise<number> {
    return new Promise((resolve, reject) => {
      // 기존 서버가 있으면 먼저 정리
      this.stopCallbackServer();

      let handled = false;
      const handleOnce = (key: string) => {
        if (handled) return;
        handled = true;
        onApiKey(key);
      };

      const server = http.createServer((req, res) => {
        // CORS 허용 (hwarang.ai에서 리다이렉트 시)
        res.setHeader("Access-Control-Allow-Origin", "*");
        res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
        res.setHeader("Access-Control-Allow-Headers", "Content-Type");

        if (req.method === "OPTIONS") {
          res.writeHead(204);
          res.end();
          return;
        }

        const url = new URL(req.url || "", "http://127.0.0.1");

        // 헬스체크
        if (url.pathname === "/health") {
          res.writeHead(200, { "Content-Type": "text/plain" });
          res.end("ok");
          return;
        }

        const apiKey =
          url.searchParams.get("api_key") || url.searchParams.get("token");

        if (apiKey) {
          // 먼저 콜백 실행 (즉시 처리, 중복 호출 방지)
          handleOnce(apiKey);

          res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
          res.end(`<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>로그인 완료</title></head><body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 50%,#312e81 100%);color:#fff;margin:0;">
  <div style="text-align:center;padding:40px;">
    <div style="width:64px;height:64px;margin:0 auto 20px;border-radius:16px;background:linear-gradient(135deg,#c084fc,#7c3aed);display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:bold;color:#fff;box-shadow:0 10px 30px rgba(124,58,237,0.4);">H</div>
    <h2 style="margin:0 0 8px;font-size:24px;">로그인 완료!</h2>
    <p style="opacity:0.7;font-size:14px;margin:0;">VS Code로 돌아가주세요. 이 창은 닫으셔도 됩니다.</p>
  </div>
  <script>setTimeout(function(){window.close()}, 2000)</script>
</body></html>`);
        } else {
          res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
          res.end("api_key 파라미터가 없습니다");
        }
      });

      server.on("error", (err) => {
        reject(err);
      });

      server.listen(0, "127.0.0.1", () => {
        const addr = server.address() as { port: number };
        this._callbackServer = server;
        resolve(addr.port);
      });
    });
  }

  private stopCallbackServer() {
    if (this._callbackServer) {
      this._callbackServer.close();
      this._callbackServer = null;
    }
  }

  // ============================================================
  // 로그인 방법 2: API 키 직접 입력
  // ============================================================

  async loginWithApiKey(apiKey: string): Promise<boolean> {
    this._apiKey = apiKey;

    const success = await this.fetchUserInfo();
    if (success) {
      await this.context.secrets.store("hwarang-api-key", apiKey);
      this.startTokenRefresh();
      vscode.window.showInformationMessage(
        `화랑 AI: ${this._user!.name}님, 환영합니다! (${this._user!.plan?.displayName || "무료"} 플랜)`
      );
      return true;
    }

    this._apiKey = null;
    vscode.window.showErrorMessage("화랑 AI: 유효하지 않은 API 키입니다");
    return false;
  }

  // ============================================================
  // 로그��� 방법 3: 이메일/비밀번호
  // ============================================================

  async loginWithEmail(email: string, password: string): Promise<boolean> {
    const apiUrl = this.getApiUrl();
    try {
      const resp = await fetch(`${apiUrl}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!resp.ok) {
        const error = await resp.text();
        vscode.window.showErrorMessage(`로��인 실패: ${error}`);
        return false;
      }

      const data = (await resp.json()) as { api_key: string };
      return await this.loginWithApiKey(data.api_key);
    } catch (e: any) {
      vscode.window.showErrorMessage(`서버 연결 실패: ${e.message}`);
      return false;
    }
  }

  // ============================================================
  // 로그아웃
  // ============================================================

  async logout(): Promise<void> {
    this._apiKey = null;
    this._user = null;
    await this.context.secrets.delete("hwarang-api-key");
    this.stopTokenRefresh();
    this.updateStatusBar();
    this._onAuthChanged.fire(null);
    vscode.window.showInformationMessage("화랑 AI: 로그아웃 완료");
  }

  // ============================================================
  // 사용자 정보 조회
  // ============================================================

  async fetchUserInfo(): Promise<boolean> {
    if (!this._apiKey) return false;
    const apiUrl = this.getApiUrl();

    // Next.js Route Handler 경로 (/api/users/me) 시도, 실패 시 /api/v1/users/me
    const endpoints = [`${apiUrl}/api/users/me`, `${apiUrl}/api/v1/users/me`];

    for (const url of endpoints) {
      try {
        const resp = await fetch(url, {
          headers: { Authorization: `Bearer ${this._apiKey}` },
        });
        if (!resp.ok) {
          if (resp.status === 401 || resp.status === 403) {
            // 인증 실패 - 키가 잘못됨
            return false;
          }
          // 404 등은 다음 엔드포인트 시도
          continue;
        }

        this._user = (await resp.json()) as UserInfo;
        this.updateStatusBar();
        this._onAuthChanged.fire(this._user);
        return true;
      } catch (e) {
        // 네트워크 오류 - 다음 엔드포인트 시도
        continue;
      }
    }
    return false;
  }

  async refreshTokenBalance(): Promise<void> {
    await this.fetchUserInfo();
  }

  canMakeRequest(estimatedTokens: number = 500): { allowed: boolean; reason?: string } {
    if (!this._user) {
      return { allowed: false, reason: "로그인이 필요합니��" };
    }
    const tokens = this._user.tokens;
    if (!tokens) {
      return { allowed: false, reason: "토��� 정보를 불러올 수 없습니다" };
    }
    if (tokens.balance < estimatedTokens) {
      return {
        allowed: false,
        reason: `토큰 부족: ${tokens.balance.toLocaleString()}�� 남음`,
      };
    }
    if (tokens.dailyUsed + estimatedTokens > tokens.dailyLimit) {
      return {
        allowed: false,
        reason: `일일 한도 초과 (자정에 리셋)`,
      };
    }
    return { allowed: true };
  }

  // ============================================================
  // 상태바
  // ============================================================

  private updateStatusBar(): void {
    if (!this._user || !this._user.tokens) {
      this.statusBarItem.text = "$(key) 화랑 AI: 로그인";
      this.statusBarItem.tooltip = "클릭하여 로그인";
      this.statusBarItem.backgroundColor = undefined;
      this.statusBarItem.show();
      return;
    }

    const tokens = this._user.tokens;
    const balance = tokens.balance;
    const fmt = (n: number) => {
      if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
      if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
      return n.toString();
    };

    if (balance < 1000) {
      this.statusBarItem.text = `$(warning) ${fmt(balance)} ��큰`;
      this.statusBarItem.backgroundColor = new vscode.ThemeColor(
        "statusBarItem.warningBackground"
      );
    } else {
      this.statusBarItem.text = `$(pulse) ${fmt(balance)} 토큰`;
      this.statusBarItem.backgroundColor = undefined;
    }

    const dailyPct = Math.round(
      (tokens.dailyUsed / Math.max(tokens.dailyLimit, 1)) * 100
    );
    this.statusBarItem.tooltip = [
      `화랑 AI - ${this._user.name}`,
      `플랜: ${this._user.plan?.displayName || "무료"}`,
      ``,
      `잔여: ${balance.toLocaleString()} 토큰`,
      `오늘: ${tokens.dailyUsed.toLocaleString()} / ${tokens.dailyLimit.toLocaleString()} (${dailyPct}%)`,
      `누적: ${tokens.totalUsed.toLocaleString()}`,
    ].join("\n");

    this.statusBarItem.show();
  }

  // ============================================================
  // 자동 갱신
  // ============================================================

  private startTokenRefresh(): void {
    this.stopTokenRefresh();
    this._refreshInterval = setInterval(() => this.fetchUserInfo(), 60_000);
  }

  private stopTokenRefresh(): void {
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = null;
    }
  }

  // ============================================================
  // Getters
  // ============================================================

  get isLoggedIn(): boolean {
    return this._user !== null;
  }
  get user(): UserInfo | null {
    return this._user;
  }
  get apiKey(): string | null {
    return this._apiKey;
  }

  getAuthHeaders(): Record<string, string> {
    if (!this._apiKey) return {};
    return { Authorization: `Bearer ${this._apiKey}` };
  }

  private getApiUrl(): string {
    const config = vscode.workspace.getConfiguration("hwarang");
    return config.get("apiUrl", "https://hwarang.ai");
  }
}
