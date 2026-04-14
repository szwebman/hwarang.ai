/**
 * 인증 + 토큰 관리 - Claude Code와 동일한 경험
 *
 * 기능:
 * - API 키 또는 이메일/비밀번호 로그인
 * - 토큰 잔액 실시간 표시 (상태바)
 * - 토큰 소진 시 경고
 * - 로그인 상태 영구 저장 (SecretStorage)
 */

import * as vscode from "vscode";

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

  // 이벤트: 로그인/로그아웃/토큰 변경 시
  private _onAuthChanged = new vscode.EventEmitter<UserInfo | null>();
  readonly onAuthChanged = this._onAuthChanged.event;

  constructor(context: vscode.ExtensionContext) {
    this.context = context;

    // 상태바: 토큰 잔액 표시
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right, 99
    );
    this.statusBarItem.command = "hwarang.showTokenStatus";
    context.subscriptions.push(this.statusBarItem);
  }

  /**
   * 초기화: 저장된 API 키로 자동 로그인
   */
  async initialize(): Promise<boolean> {
    // SecretStorage에서 API 키 복구
    const savedKey = await this.context.secrets.get("hwarang-api-key");
    if (savedKey) {
      this._apiKey = savedKey;
      const success = await this.fetchUserInfo();
      if (success) {
        this.startTokenRefresh();
        return true;
      }
      // 키가 만료됨
      await this.context.secrets.delete("hwarang-api-key");
      this._apiKey = null;
    }

    this.updateStatusBar();
    return false;
  }

  /**
   * API 키로 로그인
   */
  async loginWithApiKey(apiKey: string): Promise<boolean> {
    this._apiKey = apiKey;

    const success = await this.fetchUserInfo();
    if (success) {
      // 키 영구 저장
      await this.context.secrets.store("hwarang-api-key", apiKey);
      this.startTokenRefresh();
      vscode.window.showInformationMessage(
        `Hwarang AI: ${this._user!.name}님으로 로그인했습니다 (${this._user!.plan?.displayName || "Free"})`
      );
      return true;
    }

    this._apiKey = null;
    vscode.window.showErrorMessage("Hwarang AI: 유효하지 않은 API 키입니다");
    return false;
  }

  /**
   * 이메일/비밀번호로 로그인 → API 키 발급
   */
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
        vscode.window.showErrorMessage(`로그인 실패: ${error}`);
        return false;
      }

      const data = await resp.json() as { api_key: string };
      return await this.loginWithApiKey(data.api_key);
    } catch (e: any) {
      vscode.window.showErrorMessage(`연결 실패: ${e.message}`);
      return false;
    }
  }

  /**
   * 로그아웃
   */
  async logout(): Promise<void> {
    this._apiKey = null;
    this._user = null;
    await this.context.secrets.delete("hwarang-api-key");
    this.stopTokenRefresh();
    this.updateStatusBar();
    this._onAuthChanged.fire(null);
    vscode.window.showInformationMessage("Hwarang AI: 로그아웃되었습니다");
  }

  /**
   * 서버에서 사용자 정보 + 토큰 잔액 조회
   */
  async fetchUserInfo(): Promise<boolean> {
    if (!this._apiKey) return false;

    const apiUrl = this.getApiUrl();

    try {
      const resp = await fetch(`${apiUrl}/v1/users/me`, {
        headers: { "Authorization": `Bearer ${this._apiKey}` },
      });

      if (!resp.ok) return false;

      this._user = await resp.json() as UserInfo;
      this.updateStatusBar();
      this._onAuthChanged.fire(this._user);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * 토큰 사용 후 잔액 갱신 (매 요청 후)
   */
  async refreshTokenBalance(): Promise<void> {
    await this.fetchUserInfo();
  }

  /**
   * 요청 전 토큰 체크
   */
  canMakeRequest(estimatedTokens: number = 500): { allowed: boolean; reason?: string } {
    if (!this._user) {
      return { allowed: false, reason: "로그인이 필요합니다" };
    }

    const tokens = this._user.tokens;
    if (!tokens) {
      return { allowed: false, reason: "토큰 정보를 불러올 수 없습니다" };
    }

    // 잔액 체크
    if (tokens.balance < estimatedTokens) {
      return {
        allowed: false,
        reason: `토큰 부족: ${tokens.balance.toLocaleString()}개 남음 (예상 ${estimatedTokens}개 필요)`,
      };
    }

    // 일일 한도 체크
    if (tokens.dailyUsed + estimatedTokens > tokens.dailyLimit) {
      return {
        allowed: false,
        reason: `오늘 한도 초과: ${tokens.dailyUsed.toLocaleString()}/${tokens.dailyLimit.toLocaleString()} 사용 (자정에 리셋)`,
      };
    }

    return { allowed: true };
  }

  // ---- 상태바 ----

  private updateStatusBar(): void {
    if (!this._user || !this._user.tokens) {
      this.statusBarItem.text = "$(key) Hwarang: 로그인";
      this.statusBarItem.tooltip = "클릭하여 로그인";
      this.statusBarItem.backgroundColor = undefined;
      this.statusBarItem.show();
      return;
    }

    const tokens = this._user.tokens;
    const balance = tokens.balance;
    const dailyUsed = tokens.dailyUsed;
    const dailyLimit = tokens.dailyLimit;
    const dailyPercent = Math.round((dailyUsed / Math.max(dailyLimit, 1)) * 100);

    // 토큰 포맷
    const formatTokens = (n: number) => {
      if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
      if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
      return n.toString();
    };

    // 잔액에 따라 색상 변경
    if (balance < 1000) {
      this.statusBarItem.text = `$(warning) ${formatTokens(balance)} 토큰`;
      this.statusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
    } else {
      this.statusBarItem.text = `$(pulse) ${formatTokens(balance)} 토큰`;
      this.statusBarItem.backgroundColor = undefined;
    }

    this.statusBarItem.tooltip = [
      `Hwarang AI - ${this._user.name}`,
      `플랜: ${this._user.plan?.displayName || "Free"}`,
      ``,
      `잔여 토큰: ${balance.toLocaleString()}`,
      `오늘 사용: ${dailyUsed.toLocaleString()} / ${dailyLimit.toLocaleString()} (${dailyPercent}%)`,
      `누적 사용: ${tokens.totalUsed.toLocaleString()}`,
      ``,
      `클릭하여 상세 보기`,
    ].join("\n");

    this.statusBarItem.show();
  }

  // ---- 자동 갱신 ----

  private startTokenRefresh(): void {
    this.stopTokenRefresh();
    // 60초마다 토큰 잔액 갱신
    this._refreshInterval = setInterval(() => {
      this.fetchUserInfo();
    }, 60_000);
  }

  private stopTokenRefresh(): void {
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = null;
    }
  }

  // ---- Getter ----

  get isLoggedIn(): boolean { return this._user !== null; }
  get user(): UserInfo | null { return this._user; }
  get apiKey(): string | null { return this._apiKey; }

  getAuthHeaders(): Record<string, string> {
    if (!this._apiKey) return {};
    return { "Authorization": `Bearer ${this._apiKey}` };
  }

  private getApiUrl(): string {
    const config = vscode.workspace.getConfiguration("hwarang");
    return config.get("apiUrl", "http://localhost:8000");
  }
}
