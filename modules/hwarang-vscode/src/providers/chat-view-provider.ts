/**
 * Chat View Provider - Claude Code 스타일 사이드바 채팅
 *
 * UI 특징:
 * - 미니멀 다크 디자인 (Claude Code 스타일)
 * - 터미널 느낌의 깔끔한 레이아웃
 * - 도구 호출은 접히는 블록으로 표시
 * - Markdown + 코드 블록 (복사/삽입/적용 버튼)
 * - 슬래시 명령어 지원
 * - 전체 한글 UI
 */

import * as vscode from "vscode";
import { AgentLoop, AgentMessage } from "../tools/agent-loop";

interface StoredMessage {
  role: "user" | "assistant" | "tool_call" | "tool_result";
  content: string;
  toolName?: string;
  timestamp: number;
}

interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: StoredMessage[];
  workspacePath?: string;  // 이 대화가 시작된 워크스페이스
  workspaceName?: string;
}

// Claude Code 방식: 워크스페이스별 대화 저장
// 구조: { [workspacePath]: Conversation[] }
const HISTORY_KEY = "hwarang.conversations.byWorkspace";
const CURRENT_ID_KEY = "hwarang.currentConversationId";
const MAX_CONVERSATIONS_PER_WORKSPACE = 50;
const NO_WORKSPACE_KEY = "__global__";

export class ChatViewProvider implements vscode.WebviewViewProvider {
  private webviewView?: vscode.WebviewView;
  private agentLoop: AgentLoop;
  private context: vscode.ExtensionContext;
  private currentConversationId: string | null = null;
  private currentMessages: StoredMessage[] = [];

  constructor(
    private readonly extensionUri: vscode.Uri,
    agentLoop: AgentLoop,
    context: vscode.ExtensionContext
  ) {
    this.agentLoop = agentLoop;
    this.context = context;
  }

  // ============================================================
  // 대화 기록 저장/불러오기 (Claude Code 방식: 워크스페이스별)
  // ============================================================

  /** 현재 워크스페이스 식별자 (폴더 경로 또는 "__global__") */
  private getWorkspaceKey(): string {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders?.length) return NO_WORKSPACE_KEY;
    return folders[0].uri.fsPath;
  }

  private getWorkspaceName(): string {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders?.length) return "(워크스페이스 없음)";
    return folders[0].name;
  }

  /** 전체 워크스페이스별 맵 */
  private getAllConversations(): Record<string, Conversation[]> {
    return this.context.globalState.get<Record<string, Conversation[]>>(HISTORY_KEY, {});
  }

  /** 현재 워크스페이스의 대화만 */
  private getConversations(): Conversation[] {
    const all = this.getAllConversations();
    return all[this.getWorkspaceKey()] || [];
  }

  private async saveConversations(list: Conversation[]) {
    const all = this.getAllConversations();
    const trimmed = list
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, MAX_CONVERSATIONS_PER_WORKSPACE);
    all[this.getWorkspaceKey()] = trimmed;
    await this.context.globalState.update(HISTORY_KEY, all);
  }

  /** 워크스페이스별 "마지막 활성 대화 ID" */
  private getCurrentIdForWorkspace(): string | undefined {
    const map = this.context.globalState.get<Record<string, string>>(
      CURRENT_ID_KEY,
      {}
    );
    return map[this.getWorkspaceKey()];
  }

  private async setCurrentIdForWorkspace(id: string) {
    const map = this.context.globalState.get<Record<string, string>>(
      CURRENT_ID_KEY,
      {}
    );
    map[this.getWorkspaceKey()] = id;
    await this.context.globalState.update(CURRENT_ID_KEY, map);
  }

  private async persistCurrent() {
    if (!this.currentConversationId || this.currentMessages.length === 0) return;

    const workspacePath = this.getWorkspaceKey();
    const workspaceName = this.getWorkspaceName();
    const all = this.getConversations();
    const existing = all.find((c) => c.id === this.currentConversationId);
    const firstUserMsg = this.currentMessages.find((m) => m.role === "user");
    const title = firstUserMsg
      ? firstUserMsg.content.slice(0, 50).replace(/\s+/g, " ").trim()
      : "새 대화";

    if (existing) {
      existing.messages = this.currentMessages;
      existing.updatedAt = Date.now();
      existing.title = title;
      existing.workspacePath = workspacePath;
      existing.workspaceName = workspaceName;
    } else {
      all.unshift({
        id: this.currentConversationId,
        title,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: this.currentMessages,
        workspacePath,
        workspaceName,
      });
    }
    await this.saveConversations(all);
  }

  private async startNewConversation() {
    await this.persistCurrent();
    this.currentConversationId = `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    this.currentMessages = [];
    await this.context.globalState.update(
      CURRENT_ID_KEY,
      this.currentConversationId
    );
    this.agentLoop.clearHistory();
  }

  private async loadConversation(id: string) {
    await this.persistCurrent();

    // 현재 워크스페이스뿐 아니라 모든 워크스페이스에서 검색
    let conv: Conversation | undefined;
    const all = this.getAllConversations();
    for (const convs of Object.values(all)) {
      conv = convs.find((c) => c.id === id);
      if (conv) break;
    }
    if (!conv) return;

    this.currentConversationId = id;
    this.currentMessages = [...conv.messages];
    await this.setCurrentIdForWorkspace(id);

    // 에이전트 히스토리에도 반영
    this.agentLoop.clearHistory();
    this.agentLoop.restoreHistory(
      conv.messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        }))
    );

    // 웹뷰에 복원 메시지 전송
    if (this.webviewView) {
      this.webviewView.webview.postMessage({ type: "clearChat" });
      for (const msg of conv.messages) {
        this.webviewView.webview.postMessage({
          type: "restoreMessage",
          role: msg.role,
          content: msg.content,
          toolName: msg.toolName,
        });
      }
    }
  }

  private async deleteConversation(id: string) {
    const all = this.getConversations().filter((c) => c.id !== id);
    await this.saveConversations(all);
    if (this.currentConversationId === id) {
      this.currentConversationId = null;
      this.currentMessages = [];
      this.agentLoop.clearHistory();
      this.webviewView?.webview.postMessage({ type: "clearChat" });
    }
  }

  private async showHistory(showAllWorkspaces = false) {
    await this.persistCurrent();

    const all = this.getAllConversations();
    const currentKey = this.getWorkspaceKey();
    const currentName = this.getWorkspaceName();

    // 현재 워크스페이스의 대화 우선, 옵션에 따라 전체도 표시
    const currentConvs = (all[currentKey] || []).sort(
      (a, b) => b.updatedAt - a.updatedAt
    );
    const otherConvs: Array<Conversation & { _wsName: string }> = [];
    for (const [key, convs] of Object.entries(all)) {
      if (key === currentKey) continue;
      for (const c of convs) {
        otherConvs.push({
          ...c,
          _wsName: c.workspaceName || (key === NO_WORKSPACE_KEY ? "(워크스페이스 없음)" : key.split("/").pop() || key),
        });
      }
    }
    otherConvs.sort((a, b) => b.updatedAt - a.updatedAt);

    const totalCount = currentConvs.length + (showAllWorkspaces ? otherConvs.length : 0);
    if (totalCount === 0) {
      const pick = await vscode.window.showInformationMessage(
        `저장된 대화가 없습니다 (현재: ${currentName})`,
        "다른 워크스페이스 보기"
      );
      if (pick === "다른 워크스페이스 보기" && otherConvs.length > 0) {
        return this.showHistory(true);
      }
      return;
    }

    type HistoryItem = vscode.QuickPickItem & { id?: string; action?: string };

    const formatDate = (ts: number) => {
      const date = new Date(ts);
      return `${date.getMonth() + 1}/${date.getDate()} ${date
        .getHours()
        .toString()
        .padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;
    };

    const items: HistoryItem[] = [];

    // 현재 워크스페이스 섹션
    items.push({
      label: `$(folder-opened) ${currentName}`,
      kind: vscode.QuickPickItemKind.Separator,
    });

    if (currentConvs.length === 0) {
      items.push({
        label: "$(info) 이 워크스페이스에 저장된 대화 없음",
      });
    } else {
      for (const c of currentConvs) {
        items.push({
          id: c.id,
          label: `$(comment-discussion) ${c.title}`,
          description: formatDate(c.updatedAt),
          detail: `${c.messages.length}개 메시지`,
        });
      }
    }

    // 다른 워크스페이스 섹션 (옵션)
    if (showAllWorkspaces && otherConvs.length > 0) {
      items.push({
        label: "$(archive) 다른 워크스페이스",
        kind: vscode.QuickPickItemKind.Separator,
      });
      for (const c of otherConvs) {
        items.push({
          id: c.id,
          label: `$(comment-discussion) ${c.title}`,
          description: `${formatDate(c.updatedAt)} · ${c._wsName}`,
          detail: `${c.messages.length}개 메시지`,
        });
      }
    }

    // 액션
    items.push({ label: "", kind: vscode.QuickPickItemKind.Separator });
    if (!showAllWorkspaces && otherConvs.length > 0) {
      items.push({
        label: `$(archive) 다른 워크스페이스 대화도 보기 (${otherConvs.length}개)`,
        action: "show-all",
      });
    }
    items.push({
      label: "$(trash) 이 워크스페이스 대화 모두 삭제",
      action: "clear-workspace",
    });
    if (otherConvs.length > 0 || currentConvs.length > 0) {
      items.push({
        label: "$(trash) 전체 대화 삭제 (모든 워크스페이스)",
        action: "clear-all",
      });
    }

    const pick = await vscode.window.showQuickPick(items, {
      placeHolder: showAllWorkspaces
        ? "대화 선택 (모든 워크스페이스)"
        : `이전 대화 선택 — ${currentName}`,
      matchOnDescription: true,
      matchOnDetail: true,
    });

    if (!pick) return;

    if (pick.action === "show-all") {
      return this.showHistory(true);
    }

    if (pick.action === "clear-workspace") {
      const confirm = await vscode.window.showWarningMessage(
        `'${currentName}' 워크스페이스의 모든 대화를 삭제할까요?`,
        { modal: true },
        "삭제"
      );
      if (confirm === "삭제") {
        await this.saveConversations([]);
        this.currentConversationId = null;
        this.currentMessages = [];
        this.agentLoop.clearHistory();
        this.webviewView?.webview.postMessage({ type: "clearChat" });
      }
      return;
    }

    if (pick.action === "clear-all") {
      const confirm = await vscode.window.showWarningMessage(
        "모든 워크스페이스의 대화를 삭제할까요? 되돌릴 수 없습니다.",
        { modal: true },
        "전체 삭제"
      );
      if (confirm === "전체 삭제") {
        await this.context.globalState.update(HISTORY_KEY, {});
        this.currentConversationId = null;
        this.currentMessages = [];
        this.agentLoop.clearHistory();
        this.webviewView?.webview.postMessage({ type: "clearChat" });
      }
      return;
    }

    if (pick.id) {
      await this.loadConversation(pick.id);
    }
  }

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ) {
    this.webviewView = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };

    webviewView.webview.html = this.getWebviewContent();

    webviewView.webview.onDidReceiveMessage(async (message) => {
      switch (message.type) {
        case "sendMessage":
          await this.handleUserMessage(message.text);
          break;
        case "newChat":
          await this.newChat();
          break;
        case "showHistory":
          await this.showHistory();
          break;
        case "stopGeneration":
          this.agentLoop.abort();
          break;
        case "insertCode":
          this.insertCodeToEditor(message.code);
          break;
        case "applyDiff":
          this.applyCodeToFile(message.code, message.language);
          break;
        case "copyCode":
          vscode.env.clipboard.writeText(message.code);
          vscode.window.showInformationMessage("클립보드에 복사됨");
          break;
        case "openFile":
          this.openFileInEditor(message.path);
          break;
        case "slashCommand":
          await this.handleSlashCommand(message.command, message.args);
          break;
      }
    });

    // 워크스페이스 이름 전송
    webviewView.webview.postMessage({
      type: "setWorkspace",
      name: this.getWorkspaceName(),
    });

    // 이전 세션 복원
    this.restorePreviousSession();
  }

  private async restorePreviousSession() {
    const prevId = this.getCurrentIdForWorkspace();
    if (!prevId) return;

    const all = this.getConversations();
    const conv = all.find((c) => c.id === prevId);
    if (!conv || conv.messages.length === 0) return;

    this.currentConversationId = prevId;
    this.currentMessages = [...conv.messages];

    this.agentLoop.clearHistory();
    this.agentLoop.restoreHistory(
      conv.messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        }))
    );

    // 웹뷰에 복원 메시지 전송 (약간의 지연 후)
    setTimeout(() => {
      if (!this.webviewView) return;
      for (const msg of conv.messages) {
        this.webviewView.webview.postMessage({
          type: "restoreMessage",
          role: msg.role,
          content: msg.content,
          toolName: msg.toolName,
        });
      }
    }, 200);
  }

  async sendMessage(text: string) {
    if (this.webviewView) {
      this.webviewView.show?.(true);
      this.webviewView.webview.postMessage({ type: "addUserMessage", text });
      await this.handleUserMessage(text);
    }
  }

  async newChat() {
    await this.startNewConversation();
    this.webviewView?.webview.postMessage({ type: "clearChat" });
  }

  /** 모드 변경을 채팅 뷰에 알림 (상태 표시용) */
  notifyModeChange(mode: string) {
    this.webviewView?.webview.postMessage({ type: "modeChanged", mode });
  }

  private async handleUserMessage(text: string) {
    const webview = this.webviewView?.webview;
    if (!webview) return;

    // 새 대화 ID가 없으면 생성
    if (!this.currentConversationId) {
      this.currentConversationId = `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      await this.context.globalState.update(
        CURRENT_ID_KEY,
        this.currentConversationId
      );
    }

    // 사용자 메시지 기록
    this.currentMessages.push({
      role: "user",
      content: text,
      timestamp: Date.now(),
    });

    try {
      webview.postMessage({ type: "startResponse" });

      for await (const msg of this.agentLoop.run(text)) {
        // 메시지 기록
        this.currentMessages.push({
          role: msg.role,
          content: msg.content,
          toolName: msg.toolName,
          timestamp: Date.now(),
        });

        switch (msg.role) {
          case "assistant":
            webview.postMessage({ type: "assistantChunk", text: msg.content });
            break;
          case "tool_call":
            webview.postMessage({
              type: "toolCall",
              toolName: msg.toolName,
              text: msg.content,
            });
            break;
          case "tool_result":
            webview.postMessage({
              type: "toolResult",
              toolName: msg.toolName,
              text: msg.content,
            });
            break;
        }
      }

      webview.postMessage({ type: "endResponse" });
      // 대화 영구 저장
      await this.persistCurrent();
    } catch (e: any) {
      webview.postMessage({ type: "error", text: e.message });
      await this.persistCurrent();
    }
  }

  private async handleSlashCommand(command: string, args: string) {
    const editor = vscode.window.activeTextEditor;
    const selection = editor?.document.getText(editor.selection) || "";
    const lang = editor?.document.languageId || "";
    const file = editor
      ? vscode.workspace.asRelativePath(editor.document.uri)
      : "";

    const prompts: Record<string, string> = {
      explain: "이 코드를 자세히 설명해줘:",
      fix: "이 코드에서 버그를 찾아서 고쳐줘:",
      refactor: "이 코드를 더 깔끔하게 리팩토링해줘:",
      test: "이 코드의 유닛 테스트를 작성해줘:",
      doc: "이 코드에 문서화 주석을 추가해줘:",
      review: "이 코드를 리뷰하고 개선점을 제안해줘:",
    };

    const prompt = prompts[command] || args;
    let fullPrompt = prompt;
    if (selection) {
      fullPrompt += `\n\n파일: ${file}\n언어: ${lang}\n\n\`\`\`${lang}\n${selection}\n\`\`\``;
    }
    if (args && prompts[command]) {
      fullPrompt = `${prompt} ${args}`;
    }

    await this.sendMessage(fullPrompt);
  }

  private async insertCodeToEditor(code: string) {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage("열린 편집기가 없습니다");
      return;
    }
    await editor.edit((edit) => {
      if (editor.selection.isEmpty) {
        edit.insert(editor.selection.active, code);
      } else {
        edit.replace(editor.selection, code);
      }
    });
  }

  private async applyCodeToFile(code: string, language: string) {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      const doc = await vscode.workspace.openTextDocument({
        content: code,
        language,
      });
      await vscode.window.showTextDocument(doc);
      return;
    }
    const confirm = await vscode.window.showInformationMessage(
      "이 코드를 어떻게 적용할까요?",
      "선택 영역 교체",
      "커서에 삽입",
      "새 파일",
      "취소"
    );
    if (confirm === "선택 영역 교체" && !editor.selection.isEmpty) {
      await editor.edit((edit) => edit.replace(editor.selection, code));
    } else if (confirm === "커서에 삽입") {
      await editor.edit((edit) => edit.insert(editor.selection.active, code));
    } else if (confirm === "새 파일") {
      const doc = await vscode.workspace.openTextDocument({
        content: code,
        language,
      });
      await vscode.window.showTextDocument(doc);
    }
  }

  private async openFileInEditor(filePath: string) {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders?.length) return;
    const uri = vscode.Uri.joinPath(folders[0].uri, filePath);
    try {
      const doc = await vscode.workspace.openTextDocument(uri);
      await vscode.window.showTextDocument(doc, { preview: true });
    } catch {
      vscode.window.showWarningMessage(`파일을 찾을 수 없습니다: ${filePath}`);
    }
  }

  // ============================================================
  // Claude Code 스타일 Webview HTML
  // ============================================================

  private getWebviewContent(): string {
    return /*html*/ `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
/* ==============================================
   화랑 AI - Claude Code 스타일 UI
   ============================================== */
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  font-size: 13px;
  color: var(--vscode-foreground);
  background: var(--vscode-editor-background);
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  line-height: 1.55;
}

/* === 상단 바 === */
.topbar {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--vscode-panel-border);
  gap: 10px;
  flex-shrink: 0;
}
.topbar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}
.brand-icon {
  width: 20px; height: 20px;
  border-radius: 5px;
  background: linear-gradient(135deg, #c084fc, #7c3aed);
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: #fff;
}
.brand-name {
  font-size: 13px;
  font-weight: 600;
  opacity: 0.9;
}
.topbar-btn {
  background: none;
  border: 1px solid var(--vscode-input-border, rgba(255,255,255,0.1));
  color: var(--vscode-foreground);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
  opacity: 0.8;
  transition: all 0.15s;
}
.topbar-btn:hover {
  opacity: 1;
  background: var(--vscode-toolbar-hoverBackground);
}

/* === 메시지 영역 === */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}
.messages::-webkit-scrollbar { width: 5px; }
.messages::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.08);
  border-radius: 3px;
}
.messages::-webkit-scrollbar-thumb:hover {
  background: rgba(255,255,255,0.15);
}

/* === 개별 메시지 === */
.msg {
  padding: 14px 16px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  animation: msgIn 0.15s ease-out;
}
@keyframes msgIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.msg-label {
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.msg-label .dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  display: inline-block;
}
.msg.user-msg { background: rgba(255,255,255,0.02); }
.msg.user-msg .dot { background: #60a5fa; }
.msg.user-msg .msg-label { color: #60a5fa; }

.msg.ai-msg { background: transparent; }
.msg.ai-msg .dot { background: #c084fc; }
.msg.ai-msg .msg-label { color: #c084fc; }

.msg-text {
  font-size: 13px;
  line-height: 1.65;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

/* === Markdown === */
.msg-text h1 { font-size: 17px; font-weight: 700; margin: 14px 0 8px; }
.msg-text h2 { font-size: 15px; font-weight: 600; margin: 12px 0 6px; }
.msg-text h3 { font-size: 13px; font-weight: 600; margin: 10px 0 4px; }
.msg-text p { margin: 6px 0; }
.msg-text ul, .msg-text ol { padding-left: 20px; margin: 6px 0; }
.msg-text li { margin: 3px 0; }
.msg-text strong { font-weight: 600; }
.msg-text em { font-style: italic; }
.msg-text blockquote {
  border-left: 2px solid rgba(255,255,255,0.15);
  padding: 2px 12px;
  margin: 8px 0;
  opacity: 0.85;
}
.msg-text hr {
  border: none;
  border-top: 1px solid rgba(255,255,255,0.08);
  margin: 12px 0;
}
.msg-text a {
  color: #93c5fd;
  text-decoration: none;
}
.msg-text a:hover { text-decoration: underline; }

/* === 코드 블록 (Claude 스타일) === */
.codeblock {
  margin: 10px 0;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.08);
  overflow: hidden;
}
.codeblock-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: rgba(255,255,255,0.04);
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.codeblock-lang {
  font-size: 11px;
  color: rgba(255,255,255,0.45);
  font-weight: 500;
}
.codeblock-actions {
  display: flex;
  gap: 2px;
}
.codeblock-actions button {
  background: none;
  border: none;
  color: rgba(255,255,255,0.4);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.12s;
}
.codeblock-actions button:hover {
  background: rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.8);
}
.codeblock pre {
  margin: 0;
  padding: 12px 14px;
  overflow-x: auto;
  background: rgba(0,0,0,0.2);
}
.codeblock code {
  font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, monospace;
  font-size: 12px;
  line-height: 1.55;
  tab-size: 4;
}

/* 인라인 코드 */
.msg-text code:not(.codeblock code) {
  background: rgba(255,255,255,0.07);
  padding: 1px 6px;
  border-radius: 4px;
  font-family: "SF Mono", "Fira Code", Menlo, monospace;
  font-size: 12px;
}

/* === 도구 호출 블록 === */
.tool-block {
  margin: 8px 0;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.06);
  overflow: hidden;
}
.tool-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
  font-size: 12px;
}
.tool-head:hover { background: rgba(255,255,255,0.03); }
.tool-arrow {
  font-size: 9px;
  opacity: 0.4;
  transition: transform 0.15s;
}
.tool-block.open .tool-arrow { transform: rotate(90deg); }
.tool-fn {
  font-weight: 600;
  color: #fbbf24;
  font-family: "SF Mono", Menlo, monospace;
  font-size: 12px;
}
.tool-summary {
  color: rgba(255,255,255,0.35);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.tool-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 500;
}
.tool-badge.running {
  background: rgba(251,191,36,0.15);
  color: #fbbf24;
}
.tool-badge.done {
  background: rgba(74,222,128,0.12);
  color: #4ade80;
}
.tool-body {
  display: none;
  padding: 10px 14px;
  background: rgba(0,0,0,0.15);
  font-family: "SF Mono", Menlo, monospace;
  font-size: 11px;
  line-height: 1.5;
  max-height: 180px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  color: rgba(255,255,255,0.55);
}
.tool-block.open .tool-body { display: block; }

/* === 로딩 === */
.thinking {
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: rgba(255,255,255,0.4);
}
.thinking-dots {
  display: flex; gap: 3px;
}
.thinking-dots span {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: #c084fc;
  animation: dotPulse 1.4s infinite;
}
.thinking-dots span:nth-child(2) { animation-delay: 0.15s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.3s; }
@keyframes dotPulse {
  0%,100% { opacity: 0.2; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1); }
}

/* === 빈 상태 (웰컴) === */
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 32px 20px;
  text-align: center;
}
.welcome-icon {
  width: 52px; height: 52px;
  border-radius: 14px;
  background: linear-gradient(135deg, #c084fc 0%, #7c3aed 50%, #6366f1 100%);
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 800; color: #fff;
  margin-bottom: 16px;
  box-shadow: 0 8px 24px rgba(124,58,237,0.25);
}
.welcome h2 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 6px;
}
.welcome p {
  font-size: 12px;
  opacity: 0.5;
  max-width: 260px;
  line-height: 1.5;
}
.welcome-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 20px;
  justify-content: center;
}
.welcome-btn {
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 12px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.03);
  color: var(--vscode-foreground);
  cursor: pointer;
  transition: all 0.15s;
}
.welcome-btn:hover {
  background: rgba(255,255,255,0.07);
  border-color: rgba(192,132,252,0.3);
}

/* === 입력 영역 === */
.input-area {
  padding: 12px 16px 14px;
  border-top: 1px solid var(--vscode-panel-border);
  flex-shrink: 0;
}

/* 슬래시 명령어 자동완성 */
.slash-popup {
  display: none;
  margin-bottom: 6px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  overflow: hidden;
  background: var(--vscode-editor-background);
}
.slash-popup.show { display: block; }
.slash-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.1s;
}
.slash-item:hover { background: rgba(255,255,255,0.05); }
.slash-cmd {
  font-family: "SF Mono", Menlo, monospace;
  font-weight: 600;
  color: #c084fc;
  min-width: 72px;
}
.slash-desc {
  color: rgba(255,255,255,0.4);
}

/* 입력 박스 */
.input-box {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 6px 10px 6px 12px;
  transition: border-color 0.15s;
}
.input-box:focus-within {
  border-color: rgba(192,132,252,0.4);
}

textarea {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--vscode-foreground);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  font-size: 13px;
  resize: none;
  outline: none;
  max-height: 140px;
  line-height: 20px;
  padding: 4px 0;
  margin: 0;
  vertical-align: middle;
  display: block;
}
textarea::placeholder {
  color: rgba(255,255,255,0.25);
  line-height: 20px;
}

.btn-send {
  background: #7c3aed;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.btn-send:hover { background: #6d28d9; }
.btn-send:disabled { opacity: 0.3; cursor: default; }

.btn-stop {
  background: #dc2626;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: none;
  white-space: nowrap;
  transition: background 0.15s;
}
.btn-stop.show { display: inline-block; }
.btn-stop:hover { background: #b91c1c; }

.input-hint {
  font-size: 10px;
  color: rgba(255,255,255,0.2);
  text-align: center;
  margin-top: 6px;
}
</style>
</head>
<body>
  <!-- 상단 바 -->
  <div class="topbar">
    <div class="topbar-brand">
      <div class="brand-icon">H</div>
      <div style="display:flex; flex-direction:column; line-height:1.2;">
        <span class="brand-name">화랑 AI</span>
        <span id="workspaceName" style="font-size:10px; opacity:0.5;"></span>
      </div>
    </div>
    <div style="display:flex; gap:6px;">
      <button class="topbar-btn" onclick="showHistory()" title="이전 대화 보기">이전 대화</button>
      <button class="topbar-btn" onclick="newChat()" title="새 대화 시작">새 대화</button>
    </div>
  </div>

  <!-- 메시지 -->
  <div class="messages" id="messages">
    <div class="welcome" id="welcome">
      <div class="welcome-icon">H</div>
      <h2>화랑 AI</h2>
      <p>파일 수정, 코드 작성, 명령어 실행, 프로젝트 분석 등 무엇이든 물어보세요.</p>
      <div class="welcome-actions">
        <button class="welcome-btn" onclick="quickSend('이 프로젝트 구조를 설명해줘')">프로젝트 분석</button>
        <button class="welcome-btn" onclick="quickSend('/fix')">버그 수정</button>
        <button class="welcome-btn" onclick="quickSend('/test')">테스트 작성</button>
        <button class="welcome-btn" onclick="quickSend('/refactor')">리팩토링</button>
        <button class="welcome-btn" onclick="quickSend('/explain')">코드 설명</button>
        <button class="welcome-btn" onclick="quickSend('/review')">코드 리뷰</button>
      </div>
    </div>
  </div>

  <!-- 입력 -->
  <div class="input-area">
    <div class="slash-popup" id="slashPopup">
      <div class="slash-item" onclick="pickSlash('explain')">
        <span class="slash-cmd">/explain</span>
        <span class="slash-desc">코드 설명</span>
      </div>
      <div class="slash-item" onclick="pickSlash('fix')">
        <span class="slash-cmd">/fix</span>
        <span class="slash-desc">버그 찾아 수정</span>
      </div>
      <div class="slash-item" onclick="pickSlash('refactor')">
        <span class="slash-cmd">/refactor</span>
        <span class="slash-desc">리팩토링</span>
      </div>
      <div class="slash-item" onclick="pickSlash('test')">
        <span class="slash-cmd">/test</span>
        <span class="slash-desc">테스트 코드 생성</span>
      </div>
      <div class="slash-item" onclick="pickSlash('doc')">
        <span class="slash-cmd">/doc</span>
        <span class="slash-desc">문서화 주석 추가</span>
      </div>
      <div class="slash-item" onclick="pickSlash('review')">
        <span class="slash-cmd">/review</span>
        <span class="slash-desc">코드 리뷰</span>
      </div>
    </div>
    <div class="input-box">
      <textarea
        id="input"
        rows="1"
        placeholder="화랑에게 물어보세요... (/ 로 명령어)"
        onkeydown="onKey(event)"
        oninput="onInput(this)"
        oncompositionstart="onCompositionStart()"
        oncompositionend="onCompositionEnd()"
      ></textarea>
      <button class="btn-send" id="btnSend" onclick="send()">전송</button>
      <button class="btn-stop" id="btnStop" onclick="stop()">중지</button>
    </div>
    <div class="input-hint">Enter 전송 · Shift+Enter 줄바꿈</div>
  </div>

<script>
const vscode = acquireVsCodeApi();
const $msgs = document.getElementById('messages');
const $input = document.getElementById('input');
const $send = document.getElementById('btnSend');
const $stop = document.getElementById('btnStop');
const $welcome = document.getElementById('welcome');
const $slash = document.getElementById('slashPopup');

let busy = false;
let curAI = null;       // 현재 AI 메시지의 .msg-text
let curTool = null;     // 현재 tool-block

// ======== 전송 ========

function send() {
  // IME 조합 중이면 전송 안 함
  if (isComposing) return;

  const t = $input.value.trim();
  if (!t || busy) return;
  $input.value = '';
  $input.style.height = 'auto';
  $slash.classList.remove('show');

  const slashRe = /^\\/([a-z]+)(?:\\s+(.*))?$/;
  const m = t.match(slashRe);
  if (m) {
    addUser(t);
    vscode.postMessage({ type: 'slashCommand', command: m[1], args: m[2] || '' });
    return;
  }
  addUser(t);
  vscode.postMessage({ type: 'sendMessage', text: t });
}

function quickSend(t) { $input.value = t; send(); }
function newChat() { vscode.postMessage({ type: 'newChat' }); }
function showHistory() { vscode.postMessage({ type: 'showHistory' }); }
function stop() { vscode.postMessage({ type: 'stopGeneration' }); }

function pickSlash(cmd) {
  $input.value = '/' + cmd + ' ';
  $input.focus();
  $slash.classList.remove('show');
}

// ======== 입력 핸들링 ========

// IME(한글 등) 조합 중인지 추적
let isComposing = false;
let lastSendAt = 0;

function onCompositionStart() { isComposing = true; }
function onCompositionEnd() { isComposing = false; }

function onKey(e) {
  // IME 조합 중 Enter는 무시 (한글 입력 시 중복 전송 방지)
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && !isComposing && e.keyCode !== 229) {
    // 짧은 시간 내 중복 Enter 방지 (200ms)
    const now = Date.now();
    if (now - lastSendAt < 200) { e.preventDefault(); return; }
    lastSendAt = now;
    e.preventDefault();
    send();
  }
  if (e.key === 'Escape') $slash.classList.remove('show');
}

function onInput(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';

  const v = el.value;
  if (v.startsWith('/') && !v.includes(' ')) {
    $slash.classList.add('show');
    const f = v.slice(1).toLowerCase();
    document.querySelectorAll('.slash-item').forEach(h => {
      const c = h.querySelector('.slash-cmd').textContent.slice(1);
      h.style.display = c.startsWith(f) ? 'flex' : 'none';
    });
  } else {
    $slash.classList.remove('show');
  }
}

// ======== 메시지 렌더링 ========

function hideWelcome() {
  if ($welcome) $welcome.style.display = 'none';
}

function scroll() {
  $msgs.scrollTop = $msgs.scrollHeight;
}

function addUser(text) {
  hideWelcome();
  const d = document.createElement('div');
  d.className = 'msg user-msg';
  d.innerHTML =
    '<div class="msg-label"><span class="dot"></span>나</div>' +
    '<div class="msg-text">' + esc(text) + '</div>';
  $msgs.appendChild(d);
  scroll();
}

function startAI() {
  hideWelcome();
  const d = document.createElement('div');
  d.className = 'msg ai-msg';
  d.innerHTML =
    '<div class="msg-label"><span class="dot"></span>화랑</div>' +
    '<div class="msg-text"></div>';
  $msgs.appendChild(d);
  curAI = d.querySelector('.msg-text');
  scroll();
}

function addToolCall(fn, summary) {
  hideWelcome();
  curAI = null;

  const d = document.createElement('div');
  d.className = 'tool-block';
  const short = summary.length > 80 ? summary.slice(0, 80) + '...' : summary;
  d.innerHTML =
    '<div class="tool-head" onclick="this.parentElement.classList.toggle(\\\'open\\\')">' +
      '<span class="tool-arrow">&#9654;</span>' +
      '<span class="tool-fn">' + esc(fn) + '</span>' +
      '<span class="tool-summary">' + esc(short) + '</span>' +
      '<span class="tool-badge running">실행중</span>' +
    '</div>' +
    '<div class="tool-body"></div>';
  $msgs.appendChild(d);
  curTool = d;
  scroll();
}

function addToolResult(fn, output) {
  if (curTool) {
    curTool.querySelector('.tool-body').textContent = output;
    const badge = curTool.querySelector('.tool-badge');
    badge.textContent = '완료';
    badge.className = 'tool-badge done';
    curTool = null;
  }
  scroll();
}

function showThinking() {
  removeThinking();
  const d = document.createElement('div');
  d.id = 'thinking';
  d.className = 'thinking';
  d.innerHTML = '<div class="thinking-dots"><span></span><span></span><span></span></div> 생각하는 중...';
  $msgs.appendChild(d);
  scroll();
}

function removeThinking() {
  document.getElementById('thinking')?.remove();
}

// ======== Markdown ========

function md(text) {
  if (!text) return '';
  let h = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  // 코드 블록
  const codeBlockRe = new RegExp('&#96;&#96;&#96;(\\\\w*)\\\\n([\\\\s\\\\S]*?)&#96;&#96;&#96;', 'g');
  // Use backtick-based matching after HTML escape
  const cbRe = /\x60\x60\x60(\\w*)\\n([\\s\\S]*?)\x60\x60\x60/g;
  h = h.replace(cbRe, function(_, lang, code) {
    const lb = lang || 'code';
    return '<div class="codeblock">' +
      '<div class="codeblock-head">' +
        '<span class="codeblock-lang">' + lb + '</span>' +
        '<div class="codeblock-actions">' +
          '<button onclick="doCopy(this)">복사</button>' +
          '<button onclick="doInsert(this)">삽입</button>' +
          '<button onclick="doApply(this,\\x27' + lb + '\\x27)">적용</button>' +
        '</div>' +
      '</div>' +
      '<pre><code>' + code + '</code></pre>' +
    '</div>';
  });

  // 인라인 코드
  const icRe = /\x60([^\x60]+)\x60/g;
  h = h.replace(icRe, '<code>$1</code>');

  // 헤더
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // 볼드/이탤릭
  h = h.replace(/[*][*](.+?)[*][*]/g, '<strong>$1</strong>');
  h = h.replace(/[*](.+?)[*]/g, '<em>$1</em>');

  // 인용
  h = h.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

  // 리스트
  h = h.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  h = h.replace(/((<li>.*<\\/li>)\\n?)+/g, '<ul>$&</ul>');
  h = h.replace(/^\\d+[.] (.+)$/gm, '<li>$1</li>');

  // 수평선
  h = h.replace(/^---$/gm, '<hr>');

  // 링크
  h = h.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '<a href="#">$1</a>');

  // 줄바꿈
  h = h.replace(/\\n\\n/g, '</p><p>');
  h = h.replace(/\\n/g, '<br>');

  return '<p>' + h + '</p>';
}

function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ======== 코드 액션 ========

function getCode(btn) {
  return btn.closest('.codeblock').querySelector('code').textContent;
}
function doCopy(btn) { vscode.postMessage({ type: 'copyCode', code: getCode(btn) }); }
function doInsert(btn) { vscode.postMessage({ type: 'insertCode', code: getCode(btn) }); }
function doApply(btn, lang) { vscode.postMessage({ type: 'applyDiff', code: getCode(btn), language: lang }); }

// ======== 메시지 수신 ========

window.addEventListener('message', e => {
  const m = e.data;
  switch (m.type) {
    case 'addUserMessage':
      addUser(m.text);
      break;

    case 'startResponse':
      busy = true;
      $send.disabled = true;
      $stop.classList.add('show');
      curAI = null;
      showThinking();
      break;

    case 'assistantChunk':
      removeThinking();
      if (!curAI) startAI();
      curAI.innerHTML = md(m.text);
      scroll();
      break;

    case 'toolCall':
      removeThinking();
      addToolCall(m.toolName, m.text);
      showThinking();
      break;

    case 'toolResult':
      removeThinking();
      addToolResult(m.toolName, m.text);
      showThinking();
      break;

    case 'endResponse':
      removeThinking();
      busy = false;
      $send.disabled = false;
      $stop.classList.remove('show');
      curAI = null;
      curTool = null;
      break;

    case 'error':
      removeThinking();
      const ed = document.createElement('div');
      ed.className = 'msg ai-msg';
      ed.innerHTML =
        '<div class="msg-label" style="color:#f87171;"><span class="dot" style="background:#f87171;"></span>오류</div>' +
        '<div class="msg-text" style="color:#f87171;">' + esc(m.text) + '</div>';
      $msgs.appendChild(ed);
      busy = false;
      $send.disabled = false;
      $stop.classList.remove('show');
      scroll();
      break;

    case 'clearChat':
      $msgs.innerHTML = '';
      if ($welcome) {
        $msgs.appendChild($welcome);
        $welcome.style.display = '';
      }
      curAI = null;
      curTool = null;
      break;

    case 'setWorkspace':
      const $ws = document.getElementById('workspaceName');
      if ($ws) $ws.textContent = m.name || '';
      break;

    case 'restoreMessage':
      // 저장된 대화 복원
      hideWelcome();
      if (m.role === 'user') {
        addUser(m.content);
      } else if (m.role === 'assistant') {
        const d = document.createElement('div');
        d.className = 'msg ai-msg';
        d.innerHTML =
          '<div class="msg-label"><span class="dot"></span>화랑</div>' +
          '<div class="msg-text">' + md(m.content) + '</div>';
        $msgs.appendChild(d);
        scroll();
      } else if (m.role === 'tool_call') {
        addToolCall(m.toolName || 'tool', m.content);
      } else if (m.role === 'tool_result') {
        addToolResult(m.toolName || 'tool', m.content);
      }
      break;
  }
});
</script>
</body>
</html>`;
  }
}
