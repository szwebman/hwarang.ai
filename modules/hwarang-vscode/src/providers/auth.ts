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
      // 로컬 콜백 서버 시작
      const port = await this.startCallbackServer((apiKey) => {
        this.loginWithApiKey(apiKey).then(resolve);
      });

      // 브라우저에서 인증 페이지 열기
      const apiUrl = this.getApiUrl();
      const authUrl = `${apiUrl}/auth/vscode?callback_port=${port}&editor=vscode`;

      vscode.env.openExternal(vscode.Uri.parse(authUrl));

      vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "화랑 AI: 브라우저에서 로그인하는 중...",
          cancellable: true,
        },
        async (_progress, token) => {
          token.onCancellationRequested(() => {
            this.stopCallbackServer();
            resolve(false);
          });

          // 60초 타임아웃
          await new Promise((r) => setTimeout(r, 60000));
          this.stopCallbackServer();
          resolve(false);
        }
      );
    });
  }

  private startCallbackServer(
    onApiKey: (key: string) => void
  ): Promise<number> {
    return new Promise((resolve, reject) => {
      this._callbackServer = http.createServer((req, res) => {
        const url = new URL(req.url || "", "http://localhost");
        const apiKey = url.searchParams.get("api_key") || url.searchParams.get("token");

        if (apiKey) {
          // 성공 페이지
          res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
          res.end(`<!DOCTYPE html><html><body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;background:#1a1a2e;color:#fff;">
            <div style="text-align:center;">
              <div style="width:64px;height:64px;margin:0 auto 16px;border-radius:16px;background:linear-gradient(135deg,#6366f1,#8b5cf6);display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:bold;color:#fff;">H</div>
              <h2>로그인 완료!</h2>
              <p style="opacity:0.7;">VS Code로 돌아가세요. 이 창은 닫아도 됩니다.</p>
            </div>
          </body></html>`);

          this.stopCallbackServer();
          onApiKey(apiKey);
        } else {
          res.writeHead(400, { "Content-Type": "text/plain" });
          res.end("Missing api_key parameter");
        }
      });

      this._callbackServer.listen(0, "127.0.0.1", () => {
        const addr = this._callbackServer!.address() as { port: number };
        resolve(addr.port);
      });

      this._callbackServer.on("error", reject);
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
      const resp = await fetch(`${apiUrl}/v1/auth/login`, {
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

    try {
      const resp = await fetch(`${apiUrl}/v1/users/me`, {
        headers: { Authorization: `Bearer ${this._apiKey}` },
      });
      if (!resp.ok) return false;

      this._user = (await resp.json()) as UserInfo;
      this.updateStatusBar();
      this._onAuthChanged.fire(this._user);
      return true;
    } catch {
      return false;
    }
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
