/**
 * 화랑 AI VS Code 확장팩
 * Claude Code 수준 AI 코딩 어시스턴트
 */

import * as vscode from "vscode";
import { AuthManager } from "./providers/auth";
import { ChatViewProvider } from "./providers/chat-view-provider";
import { InlineChatProvider } from "./providers/inline-chat-provider";
import { LLMClient } from "./providers/llm-client";
import { ToolExecutor } from "./tools/executor";
import { AgentLoop } from "./tools/agent-loop";

let chatViewProvider: ChatViewProvider;
let authManager: AuthManager;
let agentLoop: AgentLoop;

export async function activate(context: vscode.ExtensionContext) {
  // 1. 인증
  authManager = new AuthManager(context);
  const isLoggedIn = await authManager.initialize();

  // 2. LLM + 도구 + 에이전트
  const llmClient = new LLMClient();
  const toolExecutor = new ToolExecutor();
  agentLoop = new AgentLoop(llmClient, toolExecutor);

  if (authManager.apiKey) {
    llmClient.setApiKey(authManager.apiKey);
  }
  authManager.onAuthChanged(() => {
    llmClient.setApiKey(authManager.apiKey);
    llmClient.refreshConfig();
  });

  // 3. 사이드바 채팅
  chatViewProvider = new ChatViewProvider(context.extensionUri, agentLoop);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("hwarang.chatView", chatViewProvider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  // 4. 명령어
  context.subscriptions.push(
    // === 로그인 (Claude Code 방식: 브라우저) ===
    vscode.commands.registerCommand("hwarang.login", async () => {
      const choice = await vscode.window.showQuickPick(
        [
          {
            label: "$(link-external) 브라우저로 로그인",
            description: "hwarang.ai에서 로그인 (권장)",
            value: "browser",
          },
          {
            label: "$(key) API 키 직접 입력",
            description: "발급받은 키를 직접 입력",
            value: "apikey",
          },
        ],
        { placeHolder: "로그인 방법을 선택하세요" }
      );
      if (!choice) return;

      if (choice.value === "browser") {
        await authManager.loginWithBrowser();
        if (authManager.apiKey) llmClient.setApiKey(authManager.apiKey);
      } else {
        const key = await vscode.window.showInputBox({
          prompt: "화랑 AI API 키를 입력하세요",
          placeHolder: "hk-xxxxxxxxxxxxxxxxxxxx",
          password: true,
          validateInput: (v) =>
            v.startsWith("hk-") ? null : "API 키는 hk-로 시작합니다",
        });
        if (key) {
          await authManager.loginWithApiKey(key);
          if (authManager.apiKey) llmClient.setApiKey(authManager.apiKey);
        }
      }
    }),

    vscode.commands.registerCommand("hwarang.logout", () => authManager.logout()),

    // === 토큰 현황 ===
    vscode.commands.registerCommand("hwarang.showTokenStatus", async () => {
      if (!authManager.isLoggedIn) {
        const r = await vscode.window.showInformationMessage(
          "로그인이 필요합니다",
          "로그인"
        );
        if (r) vscode.commands.executeCommand("hwarang.login");
        return;
      }
      await authManager.refreshTokenBalance();
      const user = authManager.user!;
      const t = user.tokens;
      if (!t) return;

      const fmt = (n: number) =>
        n >= 1e6
          ? `${(n / 1e6).toFixed(1)}M`
          : n >= 1e3
            ? `${(n / 1e3).toFixed(0)}K`
            : `${n}`;
      const pct = Math.round((t.dailyUsed / Math.max(t.dailyLimit, 1)) * 100);

      const items = [
        { label: `$(person) ${user.name}`, description: user.email, value: "" },
        {
          label: `$(star) ${user.plan?.displayName || "무료"} 플랜`,
          description: `월 ${fmt(user.plan?.tokensIncluded || 0)} 토큰`,
          value: "",
        },
        { label: "", kind: vscode.QuickPickItemKind.Separator, value: "" },
        { label: `$(pulse) 잔여: ${fmt(t.balance)} 토큰`, description: "", value: "" },
        {
          label: `$(clock) 오늘: ${fmt(t.dailyUsed)} / ${fmt(t.dailyLimit)} (${pct}%)`,
          description: "",
          value: "",
        },
        { label: `$(graph) 누적: ${fmt(t.totalUsed)}`, description: "", value: "" },
        { label: "", kind: vscode.QuickPickItemKind.Separator, value: "" },
        { label: "$(link-external) 토큰 충전", value: "buy" },
        { label: "$(arrow-up) 플랜 업그레이드", value: "upgrade" },
        { label: "$(sign-out) 로그아웃", value: "logout" },
      ].filter(
        (i) => i.label !== "" || i.kind === vscode.QuickPickItemKind.Separator
      );

      const pick = await vscode.window.showQuickPick(items, {
        placeHolder: "화랑 AI 계정 ���보",
      });
      if (pick?.value === "buy")
        vscode.env.openExternal(vscode.Uri.parse("https://hwarang.ai/pricing#tokens"));
      else if (pick?.value === "upgrade")
        vscode.env.openExternal(vscode.Uri.parse("https://hwarang.ai/pricing"));
      else if (pick?.value === "logout") authManager.logout();
    }),

    // === 채팅 ===
    vscode.commands.registerCommand("hwarang.openChat", () => {
      vscode.commands.executeCommand("hwarang.chatView.focus");
    }),
    vscode.commands.registerCommand("hwarang.newChat", () =>
      chatViewProvider.newChat()
    ),

    // === 코드 명령어 ===
    vscode.commands.registerCommand("hwarang.explainSelection", () =>
      codeCmd("이 코드를 자세히 설명해줘:")
    ),
    vscode.commands.registerCommand("hwarang.fixSelection", () =>
      codeCmd("이 코드에서 버그를 찾아 고쳐줘:")
    ),
    vscode.commands.registerCommand("hwarang.refactorSelection", () =>
      codeCmd("이 코드를 리팩토링해줘:")
    ),
    vscode.commands.registerCommand("hwarang.generateTests", () =>
      codeCmd("이 코드의 유닛 테스트를 작성해줘:")
    ),

    // === 인라인 채팅 ===
    vscode.commands.registerCommand("hwarang.inlineChat", async () => {
      if (!(await requireAuth())) return;
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;
      const input = await vscode.window.showInputBox({
        prompt: "화랑 AI에게 물어보세요",
        placeHolder: "예: 에러 처리 추가, 이 함수 최적화",
      });
      if (input) {
        const inlineChat = new InlineChatProvider(agentLoop);
        await inlineChat.handleInlineChat(editor, input);
        await authManager.refreshTokenBalance();
      }
    })
  );

  // 5. 설정 변경 감시
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("hwarang")) llmClient.refreshConfig();
    })
  );

  // 6. 첫 실행 안내
  if (!isLoggedIn) {
    const r = await vscode.window.showInformationMessage(
      "화랑 AI를 사용하려면 로그인하세요",
      "로그인",
      "나중에"
    );
    if (r === "로그인") vscode.commands.executeCommand("hwarang.login");
  }
}

export function deactivate() {
  agentLoop?.abort();
}

// ============================================================

async function requireAuth(): Promise<boolean> {
  if (!authManager.isLoggedIn) {
    const r = await vscode.window.showInformationMessage(
      "로그인이 필요합니다",
      "로그인"
    );
    if (r) vscode.commands.executeCommand("hwarang.login");
    return false;
  }
  const check = authManager.canMakeRequest();
  if (!check.allowed) {
    vscode.window.showWarningMessage(`화랑 AI: ${check.reason}`);
    return false;
  }
  return true;
}

async function codeCmd(prefix: string) {
  if (!(await requireAuth())) return;

  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("편집기를 열어주세요");
    return;
  }
  const selection = editor.document.getText(editor.selection);
  if (!selection) {
    vscode.window.showWarningMessage("코드를 선택해주세요");
    return;
  }

  const lang = editor.document.languageId;
  const file = vscode.workspace.asRelativePath(editor.document.uri);
  chatViewProvider.sendMessage(
    `${prefix}\n\n파일: ${file}\n언어: ${lang}\n\n\`\`\`${lang}\n${selection}\n\`\`\``
  );
  await authManager.refreshTokenBalance();
}
