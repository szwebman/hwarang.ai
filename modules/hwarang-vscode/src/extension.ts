/**
 * Hwarang AI VS Code Extension
 *
 * Features:
 * - 로그인 + 토큰 잔액 실시간 표시 (Claude Code 스타일)
 * - Sidebar chat panel with streaming responses
 * - File read/write/edit/delete from AI commands
 * - Terminal command execution
 * - Code explanation, fixing, refactoring
 * - Inline chat (Ctrl+I)
 * - Context-aware: sends current file, selection, workspace info
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

export async function activate(context: vscode.ExtensionContext) {
  console.log("Hwarang AI extension activated");

  // 1. 인증 초기화
  authManager = new AuthManager(context);
  const isLoggedIn = await authManager.initialize();

  // 2. LLM + Agent
  const llmClient = new LLMClient();
  const toolExecutor = new ToolExecutor();
  const agentLoop = new AgentLoop(llmClient, toolExecutor);

  authManager.onAuthChanged(() => {
    llmClient.refreshConfig();
  });

  // 3. 사이드바 채팅
  chatViewProvider = new ChatViewProvider(context.extensionUri, agentLoop);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("hwarang.chatView", chatViewProvider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  // 4. 명령어 등록
  context.subscriptions.push(
    // ===== 로그인 =====
    vscode.commands.registerCommand("hwarang.login", async () => {
      const choice = await vscode.window.showQuickPick([
        { label: "$(key) API 키로 로그인", description: "hwarang.ai에서 발급받은 키", value: "apikey" },
        { label: "$(link-external) hwarang.ai에서 API 키 발급", description: "브라우저에서 열기", value: "web" },
      ], { placeHolder: "로그인 방법 선택" });

      if (!choice) return;
      if (choice.value === "apikey") {
        const key = await vscode.window.showInputBox({
          prompt: "API 키 입력", placeHolder: "hk-xxxxxxxxxxxx", password: true,
          validateInput: (v) => v.startsWith("hk-") ? null : "hk-로 시작해야 합니다",
        });
        if (key) await authManager.loginWithApiKey(key);
      } else {
        vscode.env.openExternal(vscode.Uri.parse("https://hwarang.ai/api-keys"));
      }
    }),

    // ===== 로그아웃 =====
    vscode.commands.registerCommand("hwarang.logout", () => authManager.logout()),

    // ===== 토큰 현황 =====
    vscode.commands.registerCommand("hwarang.showTokenStatus", async () => {
      if (!authManager.isLoggedIn) {
        const r = await vscode.window.showInformationMessage("로그인이 필요합니다", "로그인");
        if (r) vscode.commands.executeCommand("hwarang.login");
        return;
      }

      await authManager.refreshTokenBalance();
      const user = authManager.user!;
      const t = user.tokens;
      if (!t) return;

      const fmt = (n: number) => n >= 1e6 ? `${(n/1e6).toFixed(1)}M` : n >= 1e3 ? `${(n/1e3).toFixed(0)}K` : `${n}`;
      const dailyPct = Math.round((t.dailyUsed / Math.max(t.dailyLimit, 1)) * 100);

      const choice = await vscode.window.showQuickPick([
        { label: `$(person) ${user.name}`, description: user.email, value: "" },
        { label: `$(star) ${user.plan?.displayName || "Free"} 플랜`, description: `월 ${fmt(user.plan?.tokensIncluded || 0)} 토큰`, value: "" },
        { label: "", kind: vscode.QuickPickItemKind.Separator, value: "" },
        { label: `$(pulse) 잔여: ${fmt(t.balance)} 토큰`, description: "", value: "" },
        { label: `$(clock) 오늘: ${fmt(t.dailyUsed)} / ${fmt(t.dailyLimit)} (${dailyPct}%)`, description: "", value: "" },
        { label: `$(graph) 누적: ${fmt(t.totalUsed)}`, description: "", value: "" },
        { label: "", kind: vscode.QuickPickItemKind.Separator, value: "" },
        { label: "$(link-external) 토큰 추가 구매", value: "buy" },
        { label: "$(arrow-up) 플랜 업그레이드", value: "upgrade" },
        { label: "$(sign-out) 로그아웃", value: "logout" },
      ].filter(i => i.label !== "" || i.kind === vscode.QuickPickItemKind.Separator), {
        placeHolder: "Hwarang AI 계정",
      });

      if (choice?.value === "buy") vscode.env.openExternal(vscode.Uri.parse("https://hwarang.ai/pricing#tokens"));
      else if (choice?.value === "upgrade") vscode.env.openExternal(vscode.Uri.parse("https://hwarang.ai/pricing"));
      else if (choice?.value === "logout") authManager.logout();
    }),

    // ===== 채팅 =====
    vscode.commands.registerCommand("hwarang.openChat", () => {
      vscode.commands.executeCommand("hwarang.chatView.focus");
    }),
    vscode.commands.registerCommand("hwarang.newChat", () => chatViewProvider.newChat()),

    // ===== 코드 명령어 (로그인+토큰 체크 포함) =====
    vscode.commands.registerCommand("hwarang.explainSelection", () => guardedCommand("Explain this code in detail:", agentLoop)),
    vscode.commands.registerCommand("hwarang.fixSelection", () => guardedCommand("Fix any bugs in this code:", agentLoop)),
    vscode.commands.registerCommand("hwarang.refactorSelection", () => guardedCommand("Refactor this code:", agentLoop)),
    vscode.commands.registerCommand("hwarang.generateTests", () => guardedCommand("Generate unit tests:", agentLoop)),
    vscode.commands.registerCommand("hwarang.inlineChat", async () => {
      if (!await requireAuth()) return;
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;
      const input = await vscode.window.showInputBox({
        prompt: "Ask Hwarang AI...", placeHolder: "e.g., Add error handling",
      });
      if (input) {
        const inlineChat = new InlineChatProvider(agentLoop);
        await inlineChat.handleInlineChat(editor, input);
        await authManager.refreshTokenBalance();
      }
    }),
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
      "Hwarang AI를 사용하려면 로그인하세요", "로그인", "나중에"
    );
    if (r === "로그인") vscode.commands.executeCommand("hwarang.login");
  }
}

export function deactivate() {
  console.log("Hwarang AI extension deactivated");
}

// ============================================================
// 헬퍼: 로그인 + 토큰 체크 후 명령어 실행
// ============================================================

async function requireAuth(): Promise<boolean> {
  if (!authManager.isLoggedIn) {
    const r = await vscode.window.showInformationMessage("로그인이 필요합니다", "로그인");
    if (r) vscode.commands.executeCommand("hwarang.login");
    return false;
  }
  const check = authManager.canMakeRequest();
  if (!check.allowed) {
    vscode.window.showWarningMessage(`Hwarang: ${check.reason}`);
    return false;
  }
  return true;
}

async function guardedCommand(prefix: string, agentLoop: AgentLoop) {
  if (!await requireAuth()) return;

  const editor = vscode.window.activeTextEditor;
  if (!editor) { vscode.window.showWarningMessage("No active editor"); return; }
  const selection = editor.document.getText(editor.selection);
  if (!selection) { vscode.window.showWarningMessage("No text selected"); return; }

  const lang = editor.document.languageId;
  const file = editor.document.fileName;
  chatViewProvider.sendMessage(`${prefix}\n\nFile: ${file}\nLanguage: ${lang}\n\n\`\`\`${lang}\n${selection}\n\`\`\``);
  await authManager.refreshTokenBalance();
}
