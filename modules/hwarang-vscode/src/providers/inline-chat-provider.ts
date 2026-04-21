/**
 * 인라인 채팅 - Ctrl+I로 편집기에서 직접 AI ��화
 * 제안된 변경사항을 diff로 보여주고 수락/거부
 */

import * as vscode from "vscode";
import { AgentLoop } from "../tools/agent-loop";

export class InlineChatProvider {
  private agentLoop: AgentLoop;

  constructor(agentLoop: AgentLoop) {
    this.agentLoop = agentLoop;
  }

  async handleInlineChat(editor: vscode.TextEditor, prompt: string) {
    const document = editor.document;
    const selection = editor.selection;
    const selectedText = document.getText(selection);
    const language = document.languageId;
    const fileName = vscode.workspace.asRelativePath(document.uri);

    let fullPrompt: string;
    if (selectedText) {
      fullPrompt =
        `사용자가 ${fileName} (${language}) 파일에서 다음 코드를 선택하고 요청합니다: "${prompt}"\n\n` +
        `선택된 코드:\n\`\`\`${language}\n${selectedText}\n\`\`\`\n\n` +
        `교체할 코드만 출력하세요 (설명 없이, 마크다운 펜스 없이). 출력이 선택 영역을 직접 대체합니다.`;
    } else {
      const line = selection.active.line;
      const context = document.getText(
        new vscode.Range(
          Math.max(0, line - 10),
          0,
          Math.min(document.lineCount - 1, line + 10),
          1000
        )
      );
      fullPrompt =
        `사용자가 ${fileName} (${language}) 파일의 ${line + 1}번째 줄에서 요청합니다: "${prompt}"\n\n` +
        `주변 코드:\n\`\`\`${language}\n${context}\n\`\`\`\n\n` +
        `커서 위치에 삽입할 코드만 출력하세요 (설명 없이, 마크다운 펜스 없이).`;
    }

    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "화랑 AI: 코드 생성 중...",
        cancellable: true,
      },
      async (_progress, token) => {
        let response = "";

        for await (const chunk of this.agentLoop.streamResponse(fullPrompt)) {
          if (token.isCancellationRequested) return;
          response += chunk;
        }

        if (!response.trim()) return;

        // 마크다운 코드 펜스 제거
        let code = response.trim();
        const fenceMatch = code.match(/^```\w*\n([\s\S]*?)```$/);
        if (fenceMatch) {
          code = fenceMatch[1];
        }

        if (selectedText) {
          const edit = new vscode.WorkspaceEdit();
          edit.replace(document.uri, selection, code);

          const confirm = await vscode.window.showInformationMessage(
            "화랑의 제안을 적용할까요?",
            "적용",
            "비교 보기",
            "취소"
          );

          if (confirm === "적용") {
            await vscode.workspace.applyEdit(edit);
          } else if (confirm === "비교 보기") {
            const fullText = document.getText();
            const newText =
              fullText.substring(0, document.offsetAt(selection.start)) +
              code +
              fullText.substring(document.offsetAt(selection.end));

            const proposedDoc = await vscode.workspace.openTextDocument({
              content: newText,
              language,
            });

            await vscode.commands.executeCommand(
              "vscode.diff",
              document.uri,
              proposedDoc.uri,
              `${fileName}: 현재 ↔ 화랑 제안`
            );

            const apply = await vscode.window.showInformationMessage(
              "이 변경사항을 적용할까요?",
              "적용",
              "취소"
            );
            if (apply === "적용") {
              await vscode.workspace.applyEdit(edit);
            }
          }
        } else {
          const edit = new vscode.WorkspaceEdit();
          edit.insert(document.uri, selection.active, code);

          const confirm = await vscode.window.showInformationMessage(
            "화랑이 생성한 코드를 삽입할까요?",
            "삽입",
            "취소"
          );

          if (confirm === "삽입") {
            await vscode.workspace.applyEdit(edit);
          }
        }
      }
    );
  }
}
