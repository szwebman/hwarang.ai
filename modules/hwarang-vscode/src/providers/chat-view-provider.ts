/**
 * Chat View Provider - Sidebar webview panel for chat.
 *
 * Manages the webview that displays the chat UI and handles
 * communication between the webview and the extension.
 */

import * as vscode from "vscode";
import { AgentLoop, AgentMessage } from "../tools/agent-loop";

export class ChatViewProvider implements vscode.WebviewViewProvider {
  private webviewView?: vscode.WebviewView;
  private agentLoop: AgentLoop;

  constructor(
    private readonly extensionUri: vscode.Uri,
    agentLoop: AgentLoop
  ) {
    this.agentLoop = agentLoop;
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

    // Handle messages from webview
    webviewView.webview.onDidReceiveMessage(async (message) => {
      switch (message.type) {
        case "sendMessage":
          await this.handleUserMessage(message.text);
          break;
        case "newChat":
          this.newChat();
          break;
      }
    });
  }

  /**
   * Send a message to the chat (from commands).
   */
  async sendMessage(text: string) {
    if (this.webviewView) {
      // Show the sidebar
      this.webviewView.show?.(true);

      // Post user message to webview
      this.webviewView.webview.postMessage({ type: "addUserMessage", text });

      // Process with agent
      await this.handleUserMessage(text);
    }
  }

  newChat() {
    this.agentLoop.clearHistory();
    this.webviewView?.webview.postMessage({ type: "clearChat" });
  }

  private async handleUserMessage(text: string) {
    const webview = this.webviewView?.webview;
    if (!webview) return;

    try {
      // Signal start of response
      webview.postMessage({ type: "startResponse" });

      for await (const msg of this.agentLoop.run(text)) {
        switch (msg.role) {
          case "assistant":
            webview.postMessage({ type: "assistantMessage", text: msg.content });
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
    } catch (e: any) {
      webview.postMessage({
        type: "error",
        text: `Error: ${e.message}`,
      });
    }
  }

  private getWebviewContent(): string {
    return /*html*/ `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    color: var(--vscode-foreground);
    background: var(--vscode-sideBar-background);
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  /* Header */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid var(--vscode-panel-border);
  }
  .header h3 {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    opacity: 0.7;
  }
  .header button {
    background: none;
    border: none;
    color: var(--vscode-foreground);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    font-size: 14px;
  }
  .header button:hover {
    background: var(--vscode-toolbar-hoverBackground);
  }

  /* Messages */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
  }

  .message {
    margin-bottom: 16px;
    animation: fadeIn 0.2s ease-out;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .message-role {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .role-user { color: var(--vscode-terminal-ansiCyan); }
  .role-assistant { color: var(--vscode-terminal-ansiGreen); }
  .role-tool { color: var(--vscode-terminal-ansiYellow); }

  .message-content {
    padding: 8px 12px;
    border-radius: 8px;
    line-height: 1.5;
    font-size: 13px;
    white-space: pre-wrap;
    word-wrap: break-word;
  }

  .msg-user .message-content {
    background: var(--vscode-input-background);
    border: 1px solid var(--vscode-input-border);
  }
  .msg-assistant .message-content {
    background: var(--vscode-editor-background);
    border: 1px solid var(--vscode-panel-border);
  }
  .msg-tool .message-content {
    background: var(--vscode-textBlockQuote-background);
    border-left: 3px solid var(--vscode-terminal-ansiYellow);
    font-family: var(--vscode-editor-font-family);
    font-size: 12px;
    max-height: 200px;
    overflow-y: auto;
  }

  /* Code blocks */
  .message-content pre {
    background: var(--vscode-textCodeBlock-background);
    padding: 8px 10px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 8px 0;
    font-family: var(--vscode-editor-font-family);
    font-size: 12px;
  }
  .message-content code {
    font-family: var(--vscode-editor-font-family);
    font-size: 12px;
  }
  .message-content :not(pre) > code {
    background: var(--vscode-textCodeBlock-background);
    padding: 1px 4px;
    border-radius: 3px;
  }

  /* Typing indicator */
  .typing {
    display: flex;
    gap: 4px;
    padding: 8px 12px;
  }
  .typing span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--vscode-terminal-ansiGreen);
    animation: pulse 1.2s infinite;
  }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }

  @keyframes pulse {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 1; }
  }

  /* Empty state */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    opacity: 0.6;
    text-align: center;
    padding: 20px;
  }
  .empty-state .logo {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: bold;
    font-size: 20px;
    margin-bottom: 12px;
  }
  .empty-state p {
    font-size: 12px;
    margin-top: 4px;
  }

  /* Quick actions */
  .quick-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 12px;
  }
  .quick-action {
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 11px;
    border: 1px solid var(--vscode-input-border);
    background: var(--vscode-input-background);
    color: var(--vscode-foreground);
    cursor: pointer;
  }
  .quick-action:hover {
    background: var(--vscode-list-hoverBackground);
  }

  /* Input */
  .input-area {
    padding: 8px 12px;
    border-top: 1px solid var(--vscode-panel-border);
  }
  .input-wrapper {
    display: flex;
    align-items: flex-end;
    gap: 6px;
    border: 1px solid var(--vscode-input-border);
    border-radius: 8px;
    background: var(--vscode-input-background);
    padding: 6px 10px;
  }
  .input-wrapper:focus-within {
    border-color: var(--vscode-focusBorder);
  }
  textarea {
    flex: 1;
    background: transparent;
    border: none;
    color: var(--vscode-input-foreground);
    font-family: var(--vscode-font-family);
    font-size: 13px;
    resize: none;
    outline: none;
    max-height: 150px;
    line-height: 1.4;
  }
  .send-btn {
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    cursor: pointer;
    font-size: 12px;
    white-space: nowrap;
  }
  .send-btn:hover {
    background: var(--vscode-button-hoverBackground);
  }
  .send-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
</style>
</head>
<body>
  <div class="header">
    <h3>Hwarang AI</h3>
    <button onclick="newChat()" title="New Chat">✨ New</button>
  </div>

  <div class="messages" id="messages">
    <div class="empty-state" id="emptyState">
      <div class="logo">H</div>
      <strong>Hwarang AI</strong>
      <p>Ask me to edit files, write code, or explain your project.</p>
      <div class="quick-actions">
        <button class="quick-action" onclick="quickSend('Explain this project structure')">📁 Explain project</button>
        <button class="quick-action" onclick="quickSend('Find and fix bugs in the current file')">🐛 Find bugs</button>
        <button class="quick-action" onclick="quickSend('Write unit tests for the current file')">🧪 Write tests</button>
      </div>
    </div>
  </div>

  <div class="input-area">
    <div class="input-wrapper">
      <textarea
        id="input"
        rows="1"
        placeholder="Ask Hwarang..."
        onkeydown="handleKey(event)"
        oninput="autoResize(this)"
      ></textarea>
      <button class="send-btn" id="sendBtn" onclick="send()">Send</button>
    </div>
  </div>

<script>
  const vscode = acquireVsCodeApi();
  const messagesEl = document.getElementById('messages');
  const inputEl = document.getElementById('input');
  const sendBtn = document.getElementById('sendBtn');
  const emptyState = document.getElementById('emptyState');
  let isProcessing = false;

  function send() {
    const text = inputEl.value.trim();
    if (!text || isProcessing) return;
    inputEl.value = '';
    inputEl.style.height = 'auto';
    addMessage('user', text);
    vscode.postMessage({ type: 'sendMessage', text });
  }

  function quickSend(text) {
    addMessage('user', text);
    vscode.postMessage({ type: 'sendMessage', text });
  }

  function newChat() {
    vscode.postMessage({ type: 'newChat' });
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 150) + 'px';
  }

  function addMessage(role, content, toolName) {
    if (emptyState) emptyState.style.display = 'none';

    const div = document.createElement('div');
    div.className = 'message msg-' + role;

    const roleLabel = {
      user: '👤 You',
      assistant: '🤖 Hwarang',
      tool_call: '🔧 Tool: ' + (toolName || ''),
      tool_result: '📋 Result: ' + (toolName || ''),
    }[role] || role;

    const roleClass = role.startsWith('tool') ? 'role-tool' : 'role-' + role;

    div.innerHTML =
      '<div class="message-role ' + roleClass + '">' + roleLabel + '</div>' +
      '<div class="message-content">' + escapeHtml(content) + '</div>';

    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addTypingIndicator() {
    const div = document.createElement('div');
    div.id = 'typing';
    div.className = 'typing';
    div.innerHTML = '<span></span><span></span><span></span>';
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function removeTypingIndicator() {
    document.getElementById('typing')?.remove();
  }

  function escapeHtml(text) {
    // Basic markdown: code blocks and inline code
    text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    text = text.replace(/\`\`\`([\\s\\S]*?)\`\`\`/g, '<pre><code>$1</code></pre>');
    text = text.replace(/\`([^\`]+)\`/g, '<code>$1</code>');
    text = text.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
    return text;
  }

  // Handle messages from extension
  window.addEventListener('message', (event) => {
    const msg = event.data;
    switch (msg.type) {
      case 'addUserMessage':
        addMessage('user', msg.text);
        break;
      case 'startResponse':
        isProcessing = true;
        sendBtn.disabled = true;
        addTypingIndicator();
        break;
      case 'assistantMessage':
        removeTypingIndicator();
        addMessage('assistant', msg.text);
        break;
      case 'toolCall':
        removeTypingIndicator();
        addMessage('tool_call', msg.text, msg.toolName);
        addTypingIndicator();
        break;
      case 'toolResult':
        removeTypingIndicator();
        addMessage('tool_result', msg.text, msg.toolName);
        addTypingIndicator();
        break;
      case 'endResponse':
        removeTypingIndicator();
        isProcessing = false;
        sendBtn.disabled = false;
        break;
      case 'error':
        removeTypingIndicator();
        addMessage('assistant', '❌ ' + msg.text);
        isProcessing = false;
        sendBtn.disabled = false;
        break;
      case 'clearChat':
        messagesEl.innerHTML = '';
        if (emptyState) {
          messagesEl.appendChild(emptyState);
          emptyState.style.display = '';
        }
        break;
    }
  });
</script>
</body>
</html>`;
  }
}
