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
import { ToolExecutor } from "../tools/executor";
import { LLMClient } from "./llm-client";
import { AuthManager } from "./auth";
import {
  expandSlashCommand,
  getSlashCommandList,
  SlashCommandContext,
} from "../commands/slash-commands";
import { VisionClient } from "../utils/vision-client";
import { FeedbackTracker } from "../utils/feedback-tracker";

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
  private toolExecutor: ToolExecutor | null = null;
  private context: vscode.ExtensionContext;
  private llmClient: LLMClient;
  private authManager: AuthManager;
  private currentConversationId: string | null = null;
  private currentMessages: StoredMessage[] = [];
  /** 옵션 답변용 단순 history (web 의 messages 배열과 동등) */
  private directHistory: { role: "user" | "assistant"; content: string }[] = [];
  /** 옵션 카드를 보낸 마지막 메시지 ID — continueMessage 시 사용 */
  private lastOptionsMessageId: string | null = null;
  private usageRefreshTimer: NodeJS.Timer | null = null;
  /** HSEE Phase 1 — implicit feedback (Apply / Copy / Reject + edit distance) */
  private feedbackTracker: FeedbackTracker;

  constructor(
    private readonly extensionUri: vscode.Uri,
    agentLoop: AgentLoop,
    context: vscode.ExtensionContext,
    llmClient: LLMClient,
    authManager: AuthManager,
    toolExecutor?: ToolExecutor
  ) {
    this.agentLoop = agentLoop;
    this.context = context;
    this.llmClient = llmClient;
    this.authManager = authManager;
    this.toolExecutor = toolExecutor || null;

    this.feedbackTracker = new FeedbackTracker({
      apiUrl:
        vscode.workspace.getConfiguration("hwarang").get<string>("apiUrl") ||
        "https://hwarang.ai",
      getApiKey: () => this.authManager.apiKey,
      getUserId: () => this.authManager.user?.id ?? null,
    });
    context.subscriptions.push({
      dispose: () => this.feedbackTracker.dispose(),
    });
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
    this.directHistory = [];
    this.lastOptionsMessageId = null;
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

    // 에이전트 + directChat 히스토리에도 반영
    this.agentLoop.clearHistory();
    const userAssistantMsgs = conv.messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.content,
      }));
    this.agentLoop.restoreHistory(userAssistantMsgs);
    this.directHistory = userAssistantMsgs;

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

    // Tool executor 와 webview 를 연결 — todo / batch / bg task 알림 채널
    if (this.toolExecutor) {
      this.toolExecutor.setBridge({
        postMessage: (msg) => webviewView.webview.postMessage(msg),
      });
    }

    // Agent loop (Plan 모드) 와 webview 연결 — planApprovalRequest / planResponse
    if (typeof (this.agentLoop as any).setWebview === "function") {
      (this.agentLoop as any).setWebview({
        postMessage: (msg: any) => webviewView.webview.postMessage(msg),
        onDidReceiveMessage: (listener: (msg: any) => any) =>
          webviewView.webview.onDidReceiveMessage(listener),
      });
    }

    webviewView.webview.onDidReceiveMessage(async (message) => {
      switch (message.type) {
        case "batchApprovalResponse":
          // webview 일괄 승인 응답
          this.toolExecutor?.resolveBatchApproval(!!message.approved);
          break;
        case "sendMessage":
          // 일반 텍스트(또는 첨부 이미지) — 옵션/이미지 파라미터 포함이면 directChat,
          // 없으면 기존 AgentLoop 흐름.
          if (message.images?.length || message.model || message.safety) {
            await this.handleDirectMessage(message);
          } else {
            await this.handleUserMessage(message.text);
          }
          break;
        case "selectOption":
          await this.handleSelectOption(message);
          break;
        case "fetchUsage":
          await this.sendUsageToWebview();
          break;
        case "newChat":
          await this.newChat();
          break;
        case "showHistory":
          await this.showHistory();
          break;
        case "stopGeneration":
          this.agentLoop.abort();
          this.llmClient.abort();
          break;
        case "insertCode":
          this.insertCodeToEditor(message.code);
          this.feedbackTracker.recordCopy(message.messageId);
          break;
        case "applyDiff":
          this.applyCodeToFile(message.code, message.language);
          // HSEE — Apply 클릭은 강한 positive 신호 + 30초 edit-distance 추적 시작
          this.feedbackTracker.recordApply(message.messageId, message.code);
          break;
        case "copyCode":
          vscode.env.clipboard.writeText(message.code);
          vscode.window.showInformationMessage("클립보드에 복사됨");
          this.feedbackTracker.recordCopy(message.messageId);
          break;
        case "openFile":
          this.openFileInEditor(message.path);
          break;
        case "slashCommand":
          await this.handleSlashCommand(message.command, message.args);
          break;
        case "planResponse":
          // PlanModeManager (agent-loop.ts) 가 listen 중. webview 이벤트는
          // agent-loop 가 setWebview 로 주입한 onDidReceiveMessage 로 직접 수신함.
          // 여기서는 별도 처리 불필요 — case 만 두어 unknown type 경고 방지.
          break;
        case "transcribeAudio":
          await this.handleTranscribeAudio(message);
          break;
      }
    });

    // 워크스페이스 이름 전송
    webviewView.webview.postMessage({
      type: "setWorkspace",
      name: this.getWorkspaceName(),
    });

    // 사용량 초기 전송 + 30 초 주기 갱신
    this.sendUsageToWebview();
    this.startUsageRefresh();

    // 이전 세션 복원
    this.restorePreviousSession();
  }

  // ============================================================
  // 사용량 표시 (webview 갱신)
  // ============================================================

  private async sendUsageToWebview() {
    if (!this.webviewView) return;
    try {
      const usage = await this.authManager.fetchUsage();
      this.webviewView.webview.postMessage({ type: "usageUpdate", usage });
    } catch {
      this.webviewView.webview.postMessage({ type: "usageUpdate", usage: null });
    }
  }

  private startUsageRefresh() {
    if (this.usageRefreshTimer) return;
    this.usageRefreshTimer = setInterval(() => {
      this.sendUsageToWebview();
    }, 30_000);
  }

  // ============================================================
  // 음성 STT — webview 에서 받은 base64 음성 → /api/audio/transcribe
  // ============================================================

  private async handleTranscribeAudio(msg: {
    fileName?: string;
    fileType?: string;
    base64?: string;
    mode?: string;
  }) {
    const webview = this.webviewView?.webview;
    if (!webview) return;
    try {
      if (!msg.base64) {
        throw new Error("음성 데이터가 비어있습니다");
      }
      const apiUrl =
        vscode.workspace.getConfiguration("hwarang").get<string>("apiUrl") ||
        "https://hwarang.ai";
      const apiKey = this.authManager.apiKey || "";

      // base64 → Uint8Array → Blob (Node 18+ 글로벌 FormData/Blob 사용)
      const buf = Buffer.from(msg.base64, "base64");
      const formData = new FormData();
      formData.append(
        "file",
        new Blob([buf], { type: msg.fileType || "audio/mpeg" }),
        msg.fileName || "audio.mp3"
      );
      formData.append("language", "ko");

      const headers: Record<string, string> = {};
      if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

      const resp = await fetch(`${apiUrl.replace(/\/$/, "")}/api/audio/transcribe`, {
        method: "POST",
        headers,
        body: formData,
      });

      if (!resp.ok) {
        const errText = await resp.text().catch(() => "");
        let parsed = errText;
        try {
          const obj = JSON.parse(errText);
          parsed = obj?.error || obj?.message || obj?.detail || errText;
        } catch {
          /* not JSON */
        }
        throw new Error(parsed || `HTTP ${resp.status}`);
      }

      const data = (await resp.json()) as {
        text?: string;
        language?: string;
      };
      webview.postMessage({
        type: "transcribeResult",
        text: data.text || "",
        language: data.language,
        mode: msg.mode || "prefill",
      });
    } catch (e: any) {
      webview.postMessage({
        type: "transcribeResult",
        error: e?.message || String(e),
        mode: msg.mode || "prefill",
      });
    }
  }

  // ============================================================
  // Direct chat (옵션 / 이미지 / 사용량) — webview 가 직접 호출
  // ============================================================

  private async handleDirectMessage(msg: {
    text: string;
    images?: { base64: string; name: string; type: string }[];
    model?: string;
    safety?: string;
    /** true 면 메인 chat 직전에 Vision API 로 description 추출 → user 메시지에 prepend */
    visionPreprocess?: boolean;
  }) {
    const webview = this.webviewView?.webview;
    if (!webview) return;
    let text = (msg.text || "").trim();
    const images = msg.images || [];
    if (!text && images.length === 0) return;

    // Vision 사전 처리 — 별도 endpoint (/api/vision/analyze) 로 description 받아
    // 사용자 메시지에 prepend. 이 경로를 쓰면 일반 텍스트 모델이 받아도 이미지 내용을
    // 코드/UI 컴포넌트로 변환할 수 있음.
    if (msg.visionPreprocess && images.length > 0) {
      try {
        const apiUrl =
          vscode.workspace.getConfiguration("hwarang").get<string>("apiUrl") ||
          "https://hwarang.ai";
        const apiKey = this.authManager.apiKey || "";
        const visionClient = new VisionClient(apiUrl, apiKey);
        const description = await visionClient.analyzeMany(
          images.map((i) => ({ base64: i.base64, name: i.name })),
          text || undefined
        );
        if (description) {
          text = `${description}\n\n${text || "이 이미지를 코드/UI 로 변환해주세요."}`;
        }
      } catch (e: any) {
        webview.postMessage({
          type: "error",
          text: `Vision 사전 분석 실패: ${e?.message || e}`,
        });
      }
    }

    if (!this.currentConversationId) {
      this.currentConversationId = `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      await this.context.globalState.update(
        CURRENT_ID_KEY,
        this.currentConversationId
      );
    }

    // user 메시지 기록 + UI
    this.currentMessages.push({
      role: "user",
      content: text || "(이미지)",
      timestamp: Date.now(),
    });
    this.directHistory.push({ role: "user", content: text });

    webview.postMessage({ type: "startResponse" });

    try {
      const resp = await this.llmClient.chatDirect({
        text,
        images: images.map((i) => i.base64),
        model: msg.model || undefined,
        safety: msg.safety,
        conversationId: this.currentConversationId || undefined,
        history: this.directHistory.slice(0, -1), // 마지막 user 는 chatDirect 내부에서 추가
      });

      if (resp.type === "options") {
        const messageId = `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        this.lastOptionsMessageId = messageId;
        // 옵션 인트로는 directHistory 에 assistant 로 남김
        this.directHistory.push({ role: "assistant", content: resp.intro });
        this.currentMessages.push({
          role: "assistant",
          content: resp.intro,
          timestamp: Date.now(),
        });
        webview.postMessage({
          type: "options",
          messageId,
          intro: resp.intro,
          options: resp.options,
        });
      } else {
        this.directHistory.push({ role: "assistant", content: resp.content });
        this.currentMessages.push({
          role: "assistant",
          content: resp.content,
          timestamp: Date.now(),
        });
        webview.postMessage({
          type: "assistantChunk",
          text: resp.content,
        });
        webview.postMessage({
          type: "answerMeta",
          model: resp.model,
          chargedTokens: resp.chargedTokens,
          latencyMs: resp.latencyMs,
        });
      }

      webview.postMessage({ type: "endResponse" });
      await this.persistCurrent();
      // 응답 직후 사용량 즉시 갱신
      this.sendUsageToWebview();
    } catch (e: any) {
      webview.postMessage({ type: "error", text: e.message });
      webview.postMessage({ type: "endResponse" });
    }
  }

  private async handleSelectOption(msg: {
    messageId: string;
    optionId: string;
    optionTitle: string;
    keywords: string[];
  }) {
    const webview = this.webviewView?.webview;
    if (!webview) return;

    webview.postMessage({ type: "startResponse" });
    try {
      const resp = await this.llmClient.continueMessage({
        optionId: msg.optionId,
        optionTitle: msg.optionTitle,
        keywords: msg.keywords || [],
        messageId: msg.messageId,
        conversationId: this.currentConversationId || undefined,
        history: this.directHistory,
      });

      this.directHistory.push({ role: "assistant", content: resp.content });
      this.currentMessages.push({
        role: "assistant",
        content: resp.content,
        timestamp: Date.now(),
      });
      webview.postMessage({
        type: "appendToOptions",
        messageId: msg.messageId,
        content: resp.content,
      });
      webview.postMessage({ type: "endResponse" });
      await this.persistCurrent();
      this.sendUsageToWebview();
    } catch (e: any) {
      webview.postMessage({ type: "error", text: e.message });
      webview.postMessage({ type: "endResponse" });
    }
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
    const userAssistantMsgs = conv.messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.content,
      }));
    this.agentLoop.restoreHistory(userAssistantMsgs);
    // directChat history 도 동일하게 복원
    this.directHistory = userAssistantMsgs;

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

  /** extension.ts 의 팔레트 명령 → 슬래시 커맨드 실행 (webview 우회) */
  async runSlashCommand(command: string, args: string) {
    if (this.webviewView) {
      this.webviewView.show?.(true);
      this.webviewView.webview.postMessage({
        type: "addUserMessage",
        text: `/${command}${args ? " " + args : ""}`,
      });
    }
    await this.handleSlashCommand(command, args);
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

    const ctx: SlashCommandContext = {
      activeFile: file || undefined,
      selection: selection || undefined,
      languageId: lang || undefined,
    };

    // commands/slash-commands.ts 의 중앙 레지스트리 사용
    const expanded = expandSlashCommand(`/${command} ${args || ""}`.trim(), ctx);

    if (expanded === null) {
      // 등록되지 않은 명령 — 인자만 그대로 전송 (fallback)
      const fallback = args
        ? args
        : `/${command} 명령은 정의되지 않았습니다.`;
      await this.sendMessage(fallback);
      return;
    }

    // 특수: /clear → 대화 초기화
    if (expanded === "__CLEAR__") {
      await this.newChat();
      this.webviewView?.webview.postMessage({
        type: "assistantChunk",
        text: "(대화 history 가 초기화되었습니다)",
      });
      this.webviewView?.webview.postMessage({ type: "endResponse" });
      return;
    }

    await this.sendMessage(expanded);
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
  box-sizing: border-box;
  min-height: 28px;
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

/* === 옵션 바 (이미지/모델/안전/사용량) === */
.option-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 0 8px;
  font-size: 11px;
}
.option-bar button,
.option-bar select {
  height: 24px;
  padding: 0 8px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.03);
  color: var(--vscode-foreground);
  border-radius: 6px;
  cursor: pointer;
  font-size: 11px;
  outline: none;
}
.option-bar button:hover,
.option-bar select:hover {
  background: rgba(255,255,255,0.07);
  border-color: rgba(192,132,252,0.3);
}
.option-bar .spacer { flex: 1; }
.usage-chip {
  font-family: "SF Mono", Menlo, monospace;
  font-size: 10px;
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(255,255,255,0.04);
}
.usage-chip.empty { display: none; }

/* === 이미지 미리보기 === */
#image-preview {
  display: none;
  flex-wrap: wrap;
  gap: 6px;
  padding: 6px 0;
}
#image-preview.show { display: flex; }
.image-thumb {
  position: relative;
  display: inline-block;
}
.image-thumb img {
  height: 60px;
  width: 60px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.08);
}
.image-thumb button.remove {
  position: absolute;
  top: -6px; right: -6px;
  width: 18px; height: 18px;
  background: #dc2626; color: #fff;
  border: none; border-radius: 50%;
  font-size: 11px; line-height: 1;
  cursor: pointer;
  padding: 0;
}

/* === 옵션 카드 (continue 모드) === */
.options-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 8px;
  margin-top: 10px;
}
.option-card {
  text-align: left;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.02);
  color: var(--vscode-foreground);
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.option-card:hover:not(:disabled) {
  border-color: rgba(192,132,252,0.5);
  background: rgba(192,132,252,0.05);
  transform: translateY(-1px);
}
.option-card:disabled { cursor: default; }
.option-card.dimmed { opacity: 0.35; }
.option-card.selected {
  border-color: #c084fc;
  background: rgba(192,132,252,0.08);
  box-shadow: 0 0 0 1px rgba(192,132,252,0.3);
}
.option-card .emoji { font-size: 18px; margin-bottom: 4px; }
.option-card .title {
  font-weight: 600;
  font-size: 12px;
  margin-bottom: 4px;
}
.option-card .desc {
  font-size: 11px;
  opacity: 0.65;
  line-height: 1.4;
  margin-bottom: 6px;
}
.option-card .keywords {
  display: flex; flex-wrap: wrap; gap: 3px;
}
.option-card .keywords span {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.55);
}

.options-separator {
  text-align: center;
  font-size: 10px;
  opacity: 0.4;
  margin: 12px 0 6px;
  letter-spacing: 1px;
}

.answer-meta {
  font-size: 10px;
  opacity: 0.4;
  margin-top: 6px;
  font-family: "SF Mono", Menlo, monospace;
}

/* === Todo 패널 (작업 진행) === */
.todo-panel {
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--vscode-sideBar-background, rgba(20,20,28,0.95));
  border-bottom: 1px solid rgba(255,255,255,0.06);
  padding: 8px 14px;
  backdrop-filter: blur(6px);
}
.todo-header {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.75;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.todo-progress {
  font-size: 10px;
  opacity: 0.5;
  margin-left: auto;
  font-family: "SF Mono", Menlo, monospace;
}
.todo-list { list-style: none; padding: 0; margin: 0; }
.todo-item {
  font-size: 12px;
  padding: 2px 0 2px 18px;
  position: relative;
  line-height: 1.5;
}
.todo-item::before {
  content: "";
  position: absolute;
  left: 0;
  top: 6px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 1.5px solid rgba(255,255,255,0.25);
}
.todo-item.in_progress::before {
  border-color: #60a5fa;
  background: radial-gradient(circle, #60a5fa 30%, transparent 35%);
  animation: todoPulse 1.2s ease-in-out infinite;
}
.todo-item.completed::before {
  border-color: #22c55e;
  background: #22c55e;
}
.todo-item.completed::after {
  content: "";
  position: absolute;
  left: 3px;
  top: 9px;
  width: 6px;
  height: 3px;
  border-left: 1.5px solid #fff;
  border-bottom: 1.5px solid #fff;
  transform: rotate(-45deg);
}
.todo-item.failed::before {
  border-color: var(--vscode-errorForeground, #f87171);
  background: var(--vscode-errorForeground, #f87171);
}
.todo-item.in_progress { color: var(--vscode-textLink-foreground, #60a5fa); font-weight: 500; }
.todo-item.completed { color: rgba(255,255,255,0.45); text-decoration: line-through; }
.todo-item.failed { color: var(--vscode-errorForeground, #f87171); }
@keyframes todoPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* === Batch 승인 모달 === */
.batch-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
}
.batch-modal-backdrop[hidden] {
  display: none !important;
}
.batch-modal {
  background: var(--vscode-editor-background);
  border: 1px solid var(--vscode-panel-border, rgba(255,255,255,0.1));
  border-radius: 10px;
  max-width: 720px;
  width: 100%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.batch-modal h3 {
  padding: 14px 18px;
  font-size: 14px;
  font-weight: 600;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.batch-actions {
  display: flex;
  gap: 8px;
  padding: 12px 18px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.batch-actions button {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.08);
  color: var(--vscode-foreground);
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.batch-actions button:hover { background: rgba(255,255,255,0.12); }
.batch-actions button.primary {
  background: linear-gradient(135deg, #7c3aed, #6d28d9);
  border-color: #7c3aed;
  color: #fff;
}
.batch-actions button.primary:hover { filter: brightness(1.1); }
.batch-actions button.danger {
  background: rgba(248, 113, 113, 0.15);
  border-color: rgba(248, 113, 113, 0.4);
  color: #f87171;
}
.batch-files {
  overflow-y: auto;
  padding: 12px 18px;
  font-family: "SF Mono", Menlo, monospace;
  font-size: 11px;
}
.batch-file {
  margin-bottom: 14px;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 6px;
  overflow: hidden;
}
.batch-file-head {
  padding: 6px 10px;
  background: rgba(255,255,255,0.04);
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}
.batch-file-tool {
  font-size: 10px;
  background: rgba(124, 58, 237, 0.2);
  border: 1px solid rgba(124, 58, 237, 0.4);
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
}
.batch-file-meta { font-size: 10px; opacity: 0.5; margin-left: auto; }
.batch-file-diff {
  padding: 8px 10px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  background: rgba(0,0,0,0.2);
  line-height: 1.5;
}
.batch-file-diff .add { color: #4ade80; }
.batch-file-diff .del { color: #f87171; }

/* === 백그라운드 task 토스트 === */
.toast-stack {
  position: fixed;
  bottom: 12px;
  right: 12px;
  z-index: 999;
  display: flex;
  flex-direction: column;
  gap: 6px;
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  background: var(--vscode-notifications-background, rgba(40,40,55,0.95));
  border: 1px solid var(--vscode-notifications-border, rgba(255,255,255,0.1));
  color: var(--vscode-notifications-foreground, #fff);
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 12px;
  max-width: 320px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.35);
  animation: toastIn 0.2s ease-out;
}
.toast.success { border-left: 3px solid #22c55e; }
.toast.failed { border-left: 3px solid var(--vscode-errorForeground, #f87171); }
@keyframes toastIn {
  from { transform: translateX(20px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
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

  <!-- 작업 진행 (todo 패널) -->
  <div id="todoPanel" class="todo-panel" hidden>
    <div class="todo-header">
      <span>작업 진행</span>
      <span id="todoProgress" class="todo-progress"></span>
    </div>
    <ul id="todoList" class="todo-list"></ul>
  </div>

  <!-- 백그라운드 task 토스트 -->
  <div id="toastStack" class="toast-stack"></div>

  <!-- Batch 승인 모달 -->
  <div id="batchBackdrop" class="batch-modal-backdrop" hidden>
    <div class="batch-modal">
      <h3 id="batchTitle">파일 변경 제안</h3>
      <div class="batch-actions">
        <button class="primary" id="batchApprove">모두 적용</button>
        <button class="danger" id="batchReject">거절</button>
      </div>
      <div id="batchFiles" class="batch-files"></div>
    </div>
  </div>

  <!-- Plan 승인 모달 (group 1 PlanModeManager 가 listen) -->
  <div id="planBackdrop" class="batch-modal-backdrop" hidden>
    <div class="batch-modal" style="max-width:560px;">
      <h3 id="planTitle">작업 계획</h3>
      <ol id="planItems" style="padding:14px 18px 4px 36px; font-size:12.5px; line-height:1.7;"></ol>
      <div class="batch-actions" style="border-top:1px solid rgba(255,255,255,0.06); border-bottom:none;">
        <button class="primary" id="planApprove">진행</button>
        <button id="planModify">수정</button>
        <button class="danger" id="planCancel">취소</button>
      </div>
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
        <span class="slash-desc">선택한 코드 설명</span>
      </div>
      <div class="slash-item" onclick="pickSlash('fix')">
        <span class="slash-cmd">/fix</span>
        <span class="slash-desc">현재 파일 버그 찾아 수정</span>
      </div>
      <div class="slash-item" onclick="pickSlash('refactor')">
        <span class="slash-cmd">/refactor</span>
        <span class="slash-desc">선택한 코드 리팩토링</span>
      </div>
      <div class="slash-item" onclick="pickSlash('test')">
        <span class="slash-cmd">/test</span>
        <span class="slash-desc">유닛 테스트 생성</span>
      </div>
      <div class="slash-item" onclick="pickSlash('doc')">
        <span class="slash-cmd">/doc</span>
        <span class="slash-desc">문서/주석 추가</span>
      </div>
      <div class="slash-item" onclick="pickSlash('review')">
        <span class="slash-cmd">/review</span>
        <span class="slash-desc">코드 리뷰</span>
      </div>
      <div class="slash-item" onclick="pickSlash('optimize')">
        <span class="slash-cmd">/optimize</span>
        <span class="slash-desc">성능 최적화 제안</span>
      </div>
      <div class="slash-item" onclick="pickSlash('translate')">
        <span class="slash-cmd">/translate</span>
        <span class="slash-desc">다른 언어로 변환 (예: /translate python)</span>
      </div>
      <div class="slash-item" onclick="pickSlash('diagnose')">
        <span class="slash-cmd">/diagnose</span>
        <span class="slash-desc">빌드/lint 에러 자동 분석</span>
      </div>
      <div class="slash-item" onclick="pickSlash('commit')">
        <span class="slash-cmd">/commit</span>
        <span class="slash-desc">git status 확인 후 자동 커밋</span>
      </div>
      <div class="slash-item" onclick="pickSlash('plan')">
        <span class="slash-cmd">/plan</span>
        <span class="slash-desc">Plan 모드 강제 진입</span>
      </div>
      <div class="slash-item" onclick="pickSlash('clear')">
        <span class="slash-cmd">/clear</span>
        <span class="slash-desc">대화 history 초기화</span>
      </div>
    </div>
    <!-- 이미지 미리보기 -->
    <div id="image-preview"></div>

    <div class="input-box">
      <textarea
        id="input"
        rows="1"
        placeholder="화랑에게 물어보세요... (/ 로 명령어, 이미지 붙여넣기 가능)"
        onkeydown="onKey(event)"
        oninput="onInput(this)"
        oncompositionstart="onCompositionStart()"
        oncompositionend="onCompositionEnd()"
      ></textarea>
      <button class="btn-send" id="btnSend" onclick="send()">전송</button>
      <button class="btn-stop" id="btnStop" onclick="stop()">중지</button>
    </div>

    <!-- 옵션 바: 이미지 / 모델 / 안전 / 사용량 -->
    <div class="option-bar">
      <button id="image-btn" title="이미지 첨부" onclick="document.getElementById('image-input').click()">📎 이미지</button>
      <select id="model-select" title="모델 선택">
        <option value="">⚡ Auto</option>
        <option value="hwarang-default">화랑 기본</option>
        <option value="hwarang-coder">코더</option>
        <option value="hwarang-vision">비전</option>
      </select>
      <select id="safety-select" title="안전 모드">
        <option value="loose">🆓 관대</option>
        <option value="standard" selected>🛡️ 표준</option>
        <option value="strict">🔒 엄격</option>
      </select>
      <select id="voice-mode" title="음성 입력 모드">
        <option value="prefill" selected>🎤 채우기 (확인 후 전송)</option>
        <option value="auto">🎤 자동 전송</option>
      </select>
      <button id="voice-btn" title="음성 파일 업로드 (mp3/wav/m4a/webm/ogg/flac)" type="button" onclick="document.getElementById('voice-input').click()">🎤</button>
      <span class="spacer"></span>
      <span id="usage-display" class="usage-chip empty" title="잔여 / 일일 한도"></span>
    </div>

    <input type="file" id="image-input" accept="image/*" multiple style="display:none;">
    <input type="file" id="voice-input" accept="audio/*,.mp3,.wav,.m4a,.webm,.ogg,.flac" style="display:none;">

    <div class="input-hint">Enter 전송 · Shift+Enter 줄바꿈 · 이미지 붙여넣기/드래그 지원</div>
  </div>

<script>
const vscode = acquireVsCodeApi();
const $msgs = document.getElementById('messages');
const $input = document.getElementById('input');
const $send = document.getElementById('btnSend');
const $stop = document.getElementById('btnStop');
const $welcome = document.getElementById('welcome');
const $slash = document.getElementById('slashPopup');
const $imageInput = document.getElementById('image-input');
const $imagePreview = document.getElementById('image-preview');
const $modelSelect = document.getElementById('model-select');
const $safetySelect = document.getElementById('safety-select');
const $usageDisplay = document.getElementById('usage-display');
const $voiceBtn = document.getElementById('voice-btn');
const $voiceInput = document.getElementById('voice-input');
const $voiceMode = document.getElementById('voice-mode');
const ORIGINAL_INPUT_PLACEHOLDER = $input.placeholder;

// ======== 음성 입력 (STT) ========

if ($voiceInput) {
  $voiceInput.addEventListener('change', async (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;

    // 50MB 제한 (서버와 동일)
    if (f.size > 50 * 1024 * 1024) {
      showToast('음성 파일이 너무 큽니다 (최대 50MB)', 'failed');
      $voiceInput.value = '';
      return;
    }

    try {
      // ArrayBuffer → base64 (Uint8Array 청크로 변환, 큰 파일에서 stack overflow 방지)
      const buf = await f.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let bin = '';
      const CHUNK = 0x8000;
      for (let i = 0; i < bytes.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
      }
      const base64 = btoa(bin);

      vscode.postMessage({
        type: 'transcribeAudio',
        fileName: f.name,
        fileType: f.type || 'audio/mpeg',
        base64,
        mode: $voiceMode ? $voiceMode.value : 'prefill',
      });

      // 같은 파일 재선택 가능하도록 reset
      $voiceInput.value = '';

      // UI: 변환 중 표시
      $input.placeholder = '음성 변환 중...';
      $input.disabled = true;
      if ($voiceBtn) $voiceBtn.disabled = true;
    } catch (err) {
      showToast('음성 파일 읽기 실패: ' + (err && err.message ? err.message : err), 'failed');
      $input.disabled = false;
      $input.placeholder = ORIGINAL_INPUT_PLACEHOLDER;
      if ($voiceBtn) $voiceBtn.disabled = false;
    }
  });
}

let busy = false;
let curAI = null;       // 현재 AI 메시지의 .msg-text
let curTool = null;     // 현재 tool-block
let attachedImages = []; // [{base64, name, type}]
const MAX_IMAGES = 4;

// ======== 전송 ========

function send() {
  // IME 조합 중이면 전송 안 함
  if (isComposing) return;

  const t = $input.value.trim();
  const hasImages = attachedImages.length > 0;
  if ((!t && !hasImages) || busy) return;
  $input.value = '';
  $input.style.height = 'auto';
  $slash.classList.remove('show');

  // 옵션바 값
  const model = $modelSelect.value;
  const safety = $safetySelect.value;
  // 이미지 첨부 시 자동으로 Vision 사전분석 (사용자가 별도 체크할 필요 없음)
  const visionPreprocess = hasImages;
  // 이미지 동봉 또는 모델/안전 명시 시 → directChat (옵션 모드/비전)
  const useDirect =
    hasImages || (model && model.length > 0) || (safety && safety !== 'standard');

  const slashRe = /^\\/([a-z]+)(?:\\s+([\\s\\S]*))?$/;
  const slashMatch = t.match(slashRe);
  if (slashMatch && !useDirect) {
    addUser(t);
    vscode.postMessage({ type: 'slashCommand', command: slashMatch[1], args: slashMatch[2] || '' });
    return;
  }

  addUser(t || '(이미지)', attachedImages);
  vscode.postMessage({
    type: 'sendMessage',
    text: t,
    images: attachedImages,
    model: useDirect ? model : '',
    safety: useDirect ? safety : '',
    visionPreprocess,
  });
  attachedImages = [];
  renderImagePreview();
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
  // 비어있으면 CSS 기본 (min-height 28px = 1줄) 으로 reset
  if (!el.value) {
    el.style.height = '';
  } else {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  }

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

function addUser(text, imgs) {
  hideWelcome();
  const d = document.createElement('div');
  d.className = 'msg user-msg';
  let imgHtml = '';
  if (imgs && imgs.length) {
    imgHtml = '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px;">' +
      imgs.map(function(i){
        return '<img src="' + i.base64 + '" alt="' + esc(i.name || '') +
          '" style="height:80px;border-radius:6px;border:1px solid rgba(255,255,255,0.08);">';
      }).join('') + '</div>';
  }
  d.innerHTML =
    '<div class="msg-label"><span class="dot"></span>나</div>' +
    imgHtml +
    '<div class="msg-text">' + esc(text) + '</div>';
  $msgs.appendChild(d);
  scroll();
}

// ======== 이미지 첨부 ========

function fileToDataUrl(file) {
  return new Promise(function(resolve, reject) {
    const r = new FileReader();
    r.onload = function() { resolve(r.result); };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

async function addFiles(files) {
  for (let i = 0; i < files.length; i++) {
    if (attachedImages.length >= MAX_IMAGES) break;
    const f = files[i];
    if (!f.type || !f.type.startsWith('image/')) continue;
    try {
      const base64 = await fileToDataUrl(f);
      attachedImages.push({ base64: base64, name: f.name || 'image', type: f.type });
    } catch (e) { /* skip */ }
  }
  renderImagePreview();
}

function renderImagePreview() {
  if (!$imagePreview) return;
  if (attachedImages.length === 0) {
    $imagePreview.classList.remove('show');
    $imagePreview.innerHTML = '';
    return;
  }
  $imagePreview.classList.add('show');
  $imagePreview.innerHTML = attachedImages.map(function(img, idx) {
    return '<div class="image-thumb">' +
      '<img src="' + img.base64 + '" alt="' + esc(img.name || '') + '">' +
      '<button class="remove" data-idx="' + idx + '" title="삭제">&times;</button>' +
    '</div>';
  }).join('');
  $imagePreview.querySelectorAll('button.remove').forEach(function(btn) {
    btn.addEventListener('click', function() {
      const idx = parseInt(btn.dataset.idx, 10);
      attachedImages.splice(idx, 1);
      renderImagePreview();
    });
  });
}

// 1) 파일 선택
$imageInput.addEventListener('change', function(e) {
  addFiles(Array.from(e.target.files || []));
  $imageInput.value = '';
});

// 2) 클립보드 붙여넣기
$input.addEventListener('paste', function(e) {
  const items = e.clipboardData ? e.clipboardData.items : null;
  if (!items) return;
  const files = [];
  for (let i = 0; i < items.length; i++) {
    if (items[i].type && items[i].type.startsWith('image/')) {
      const f = items[i].getAsFile();
      if (f) files.push(f);
    }
  }
  if (files.length) {
    e.preventDefault();
    addFiles(files);
  }
});

// 3) 드래그 앤 드롭
document.body.addEventListener('dragover', function(e) {
  if (e.dataTransfer && Array.from(e.dataTransfer.types || []).indexOf('Files') !== -1) {
    e.preventDefault();
  }
});
document.body.addEventListener('drop', function(e) {
  if (!e.dataTransfer) return;
  const files = Array.from(e.dataTransfer.files || []).filter(function(f) {
    return f.type && f.type.startsWith('image/');
  });
  if (files.length) {
    e.preventDefault();
    addFiles(files);
  }
});

// ======== 사용량 표시 ========

function updateUsageDisplay(usage) {
  if (!usage || !$usageDisplay) {
    if ($usageDisplay) $usageDisplay.classList.add('empty');
    return;
  }
  $usageDisplay.classList.remove('empty');
  const dailyLimit = usage.dailyLimit || 0;
  const dailyUsed = usage.dailyUsed || 0;
  const remaining = Math.max(0, dailyLimit - dailyUsed);
  const fmt = function(n) {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
    return String(n);
  };
  if (dailyLimit > 0) {
    const pct = (remaining / dailyLimit) * 100;
    const color = pct < 10 ? '#ef4444' : pct < 30 ? '#f59e0b' : '#10b981';
    $usageDisplay.innerHTML =
      '<span style="color:' + color + ';">' + fmt(remaining) + '</span>' +
      '<span style="opacity:0.5;margin-left:3px;"> / ' + fmt(dailyLimit) + '</span>';
  } else {
    $usageDisplay.innerHTML = '<span style="opacity:0.7;">' + fmt(usage.balance || 0) + '</span>';
  }
}

// 첫 진입 시 사용량 요청
vscode.postMessage({ type: 'fetchUsage' });

function startAI() {
  hideWelcome();
  const d = document.createElement('div');
  d.className = 'msg ai-msg';
  // HSEE Phase 1 — implicit feedback 추적용 messageId (Apply/Copy 클릭 시 사용)
  d.dataset.id = 'ai_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
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
function getMsgId(btn) {
  // HSEE Phase 1 — 코드블록이 속한 가장 가까운 ai-msg 의 id (없으면 빈 문자열)
  const m = btn.closest('.msg.ai-msg');
  return (m && m.dataset && m.dataset.id) ? m.dataset.id : '';
}
function doCopy(btn) {
  vscode.postMessage({ type: 'copyCode', code: getCode(btn), messageId: getMsgId(btn) });
}
function doInsert(btn) {
  vscode.postMessage({ type: 'insertCode', code: getCode(btn), messageId: getMsgId(btn) });
}
function doApply(btn, lang) {
  vscode.postMessage({ type: 'applyDiff', code: getCode(btn), language: lang, messageId: getMsgId(btn) });
}

// ======== 메시지 수신 ========

// ======== 옵션 카드 렌더링 ========

function renderOptions(messageId, intro, options) {
  hideWelcome();
  removeThinking();
  curAI = null;

  const d = document.createElement('div');
  d.className = 'msg ai-msg';
  d.dataset.id = messageId;

  const introHtml = '<div class="msg-text">' + md(intro) + '</div>';
  const cardsHtml = '<div class="options-grid">' + options.map(function(opt, i) {
    const kw = (opt.keywords || []).slice(0, 3).map(function(k) {
      return '<span>' + esc(String(k)) + '</span>';
    }).join('');
    return '<button class="option-card" data-msg-id="' + messageId + '" data-idx="' + i + '">' +
      '<div class="emoji">' + esc(opt.preview_emoji || '✨') + '</div>' +
      '<div class="title">' + esc(opt.title || '') + '</div>' +
      '<div class="desc">' + esc(opt.description || '') + '</div>' +
      '<div class="keywords">' + kw + '</div>' +
    '</button>';
  }).join('') + '</div>';

  d.innerHTML =
    '<div class="msg-label"><span class="dot"></span>화랑</div>' +
    introHtml + cardsHtml;
  $msgs.appendChild(d);

  // 카드 클릭
  d.querySelectorAll('.option-card').forEach(function(card) {
    card.addEventListener('click', function() {
      const idx = parseInt(card.dataset.idx, 10);
      const opt = options[idx];
      if (!opt) return;
      d.querySelectorAll('.option-card').forEach(function(c) {
        c.disabled = true;
        if (c === card) c.classList.add('selected');
        else c.classList.add('dimmed');
      });
      vscode.postMessage({
        type: 'selectOption',
        messageId: messageId,
        optionId: opt.id,
        optionTitle: opt.title,
        keywords: opt.keywords || [],
      });
    });
  });

  scroll();
}

function appendAnswerToOptions(messageId, content) {
  const d = $msgs.querySelector('[data-id="' + messageId + '"]');
  if (!d) {
    // 옵션 메시지 못 찾으면 일반 답변으로 표시
    startAI();
    if (curAI) curAI.innerHTML = md(content);
    return;
  }
  let answer = d.querySelector('.answer-content');
  if (!answer) {
    answer = document.createElement('div');
    answer.className = 'answer-content';
    answer.innerHTML =
      '<div class="options-separator">─── ✨ 답변 ───</div>' +
      '<div class="msg-text answer-text"></div>';
    d.appendChild(answer);
  }
  const t = answer.querySelector('.answer-text');
  t.innerHTML = md(content);
  scroll();
}

// ======== Todo 패널 ========
function renderTodos(plan) {
  const panel = document.getElementById('todoPanel');
  const list = document.getElementById('todoList');
  const prog = document.getElementById('todoProgress');
  if (!panel || !list) return;
  if (!plan || !plan.length) {
    panel.hidden = true;
    list.innerHTML = '';
    return;
  }
  panel.hidden = false;
  const completed = plan.filter(t => t.status === 'completed').length;
  if (prog) prog.textContent = completed + '/' + plan.length;

  list.innerHTML = plan.map(t => {
    const safeTitle = esc(t.title || '');
    const safeStatus = (t.status || 'pending').replace(/[^a-z_]/gi, '');
    return '<li class="todo-item ' + safeStatus + '">' + safeTitle + '</li>';
  }).join('');
}

// ======== Batch 모달 ========
let pendingBatchRequestId = null;

function showBatchModal(payload) {
  const backdrop = document.getElementById('batchBackdrop');
  const title = document.getElementById('batchTitle');
  const filesDiv = document.getElementById('batchFiles');
  if (!backdrop || !title || !filesDiv) return;

  pendingBatchRequestId = payload.requestId;
  title.textContent = (payload.files?.length || 0) + '개 파일 변경 제안';

  const html = (payload.files || []).map(f => {
    const tool = f.tool === 'write_file' ? 'write' : 'edit';
    const meta = f.oldLen + ' → ' + f.newLen + ' bytes';
    const diffHtml = (f.diff || '').split('\\n').map(line => {
      const safe = esc(line);
      if (line.startsWith('+ ')) return '<div class="add">' + safe + '</div>';
      if (line.startsWith('- ')) return '<div class="del">' + safe + '</div>';
      return '<div>' + safe + '</div>';
    }).join('');
    return '<div class="batch-file">' +
      '<div class="batch-file-head">' +
        '<span class="batch-file-tool">' + tool + '</span>' +
        '<span>' + esc(f.path) + '</span>' +
        '<span class="batch-file-meta">' + meta + '</span>' +
      '</div>' +
      '<div class="batch-file-diff">' + (diffHtml || '(no preview)') + '</div>' +
    '</div>';
  }).join('');
  filesDiv.innerHTML = html || '(no changes)';

  backdrop.hidden = false;
}

function hideBatchModal() {
  const backdrop = document.getElementById('batchBackdrop');
  if (backdrop) backdrop.hidden = true;
  pendingBatchRequestId = null;
}

document.getElementById('batchApprove')?.addEventListener('click', () => {
  vscode.postMessage({ type: 'batchApprovalResponse', approved: true, requestId: pendingBatchRequestId });
  hideBatchModal();
});
document.getElementById('batchReject')?.addEventListener('click', () => {
  vscode.postMessage({ type: 'batchApprovalResponse', approved: false, requestId: pendingBatchRequestId });
  hideBatchModal();
});

// ======== Plan 모달 (그룹 1 PlanModeManager) ========
let pendingPlanRequestId = null;
let pendingPlanItems = [];

function showPlanModal(payload) {
  const back = document.getElementById('planBackdrop');
  const items = document.getElementById('planItems');
  const title = document.getElementById('planTitle');
  if (!back || !items) return;
  pendingPlanRequestId = payload.requestId || null;
  pendingPlanItems = Array.isArray(payload.plan) ? payload.plan : [];
  if (title) title.textContent = '작업 계획 (' + pendingPlanItems.length + '단계)';
  items.innerHTML = pendingPlanItems.map(function(p, i) {
    const safeTitle = esc(p && p.title ? String(p.title) : ('Step ' + (i + 1)));
    const desc = p && p.description ? '<div style="font-size:11px;opacity:0.55;margin-top:2px;">' + esc(String(p.description)) + '</div>' : '';
    const risk = p && p.riskLevel === 'high' ? ' <span style="color:#f87171;font-size:10px;">[HIGH]</span>'
      : p && p.riskLevel === 'medium' ? ' <span style="color:#fbbf24;font-size:10px;">[MED]</span>' : '';
    return '<li style="margin-bottom:6px;">' + safeTitle + risk + desc + '</li>';
  }).join('');
  back.hidden = false;
}

function hidePlanModal() {
  const back = document.getElementById('planBackdrop');
  if (back) back.hidden = true;
  pendingPlanRequestId = null;
  pendingPlanItems = [];
}

document.getElementById('planApprove')?.addEventListener('click', function() {
  vscode.postMessage({ type: 'planResponse', approved: true, requestId: pendingPlanRequestId });
  hidePlanModal();
});
document.getElementById('planCancel')?.addEventListener('click', function() {
  vscode.postMessage({ type: 'planResponse', approved: false, requestId: pendingPlanRequestId });
  hidePlanModal();
});
document.getElementById('planModify')?.addEventListener('click', function() {
  // 단순 prompt 기반 수정 — 줄 단위로 편집.
  const initial = pendingPlanItems.map(function(p, i) { return (i + 1) + '. ' + (p.title || ''); }).join('\\n');
  const edited = window.prompt('각 줄 = 한 단계입니다. 수정하세요:', initial);
  if (edited === null) return; // 취소 시 modal 유지
  const lines = edited.split('\\n').map(function(l) { return l.replace(/^\\s*\\d+[.)]\\s*/, '').trim(); }).filter(Boolean);
  const modified = lines.map(function(line, i) {
    const orig = pendingPlanItems[i] || {};
    return {
      id: String(orig.id || (i + 1)),
      title: line,
      description: orig.description,
      estimatedTools: orig.estimatedTools || [],
      riskLevel: orig.riskLevel || 'low',
    };
  });
  vscode.postMessage({
    type: 'planResponse',
    approved: true,
    requestId: pendingPlanRequestId,
    modifiedPlan: modified,
  });
  hidePlanModal();
});

// ======== 토스트 ========
function showToast(text, kind) {
  const stack = document.getElementById('toastStack');
  if (!stack) return;
  const t = document.createElement('div');
  t.className = 'toast ' + (kind || '');
  t.textContent = text;
  stack.appendChild(t);
  setTimeout(() => t.remove(), 5500);
}

window.addEventListener('message', e => {
  const m = e.data;
  switch (m.type) {
    case 'addUserMessage':
      addUser(m.text);
      break;
    case 'todoUpdate':
      renderTodos(m.plan || []);
      break;
    case 'batchApprovalRequest':
      showBatchModal(m);
      break;
    case 'planApprovalRequest':
      showPlanModal(m);
      break;
    case 'bgTaskComplete':
      const sym = m.status === 'completed' ? '✓' : '✗';
      const dur = m.durationMs ? ' (' + (m.durationMs / 1000).toFixed(1) + 's)' : '';
      showToast(sym + ' ' + (m.command || m.taskId) + ' ' + m.status + dur,
        m.status === 'completed' ? 'success' : 'failed');
      break;
    case 'options':
      removeThinking();
      renderOptions(m.messageId, m.intro, m.options || []);
      break;
    case 'appendToOptions':
      appendAnswerToOptions(m.messageId, m.content);
      break;
    case 'usageUpdate':
      updateUsageDisplay(m.usage);
      break;
    case 'answerMeta':
      if (curAI) {
        const meta = [];
        if (m.model) meta.push(m.model);
        if (m.chargedTokens != null) meta.push(m.chargedTokens + ' 토큰');
        if (m.latencyMs != null) meta.push(m.latencyMs + 'ms');
        if (meta.length) {
          const mdiv = document.createElement('div');
          mdiv.className = 'answer-meta';
          mdiv.textContent = meta.join(' · ');
          curAI.parentElement.appendChild(mdiv);
        }
      }
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

    case 'transcribeResult':
      // STT 결과 — UI 복원 후 모드에 따라 prefill / auto 전송
      $input.disabled = false;
      $input.placeholder = ORIGINAL_INPUT_PLACEHOLDER;
      if ($voiceBtn) $voiceBtn.disabled = false;
      if (m.error) {
        showToast('음성 변환 실패: ' + m.error, 'failed');
        break;
      }
      const sttText = (m.text || '').trim();
      if (!sttText) {
        showToast('음성에서 텍스트를 추출하지 못했습니다', 'failed');
        break;
      }
      if (m.mode === 'auto') {
        $input.value = sttText;
        send();
      } else {
        // 채우기 모드: 입력창에 표시 후 사용자 확인 대기
        $input.value = sttText;
        $input.focus();
        onInput($input);  // textarea height auto-resize
      }
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
