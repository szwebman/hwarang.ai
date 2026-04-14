/**
 * Inline Chat - Ctrl+I to chat directly in the editor.
 *
 * Shows a diff of proposed changes and lets the user accept/reject.
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

    // Build the full prompt with context
    let fullPrompt: string;
    if (selectedText) {
      fullPrompt =
        `The user selected the following code in ${fileName} (${language}) and asks: "${prompt}"\n\n` +
        `Selected code:\n\`\`\`${language}\n${selectedText}\n\`\`\`\n\n` +
        `Please provide the replacement code ONLY (no explanation, no markdown fences). ` +
        `The output will directly replace the selected code.`;
    } else {
      // No selection: generate code at cursor position
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
        `The user is at line ${line + 1} in ${fileName} (${language}) and asks: "${prompt}"\n\n` +
        `Surrounding code:\n\`\`\`${language}\n${context}\n\`\`\`\n\n` +
        `Please provide the code to insert at the cursor position ONLY (no explanation, no markdown fences).`;
    }

    // Show progress
    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Hwarang AI: Generating...",
        cancellable: true,
      },
      async (progress, token) => {
        let response = "";

        for await (const chunk of this.agentLoop.streamResponse(fullPrompt)) {
          if (token.isCancellationRequested) return;
          response += chunk;
        }

        if (!response.trim()) return;

        // Strip markdown code fences if present
        let code = response.trim();
        const fenceMatch = code.match(/^```\w*\n([\s\S]*?)```$/);
        if (fenceMatch) {
          code = fenceMatch[1];
        }

        if (selectedText) {
          // Replace selection: show diff
          const edit = new vscode.WorkspaceEdit();
          edit.replace(document.uri, selection, code);

          const confirm = await vscode.window.showInformationMessage(
            "Apply Hwarang's suggestion?",
            "Apply",
            "Show Diff",
            "Cancel"
          );

          if (confirm === "Apply") {
            await vscode.workspace.applyEdit(edit);
          } else if (confirm === "Show Diff") {
            // Create a temp document with the proposed change
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
              `${fileName}: Current ↔ Hwarang's Suggestion`
            );

            const apply = await vscode.window.showInformationMessage(
              "Apply this change?",
              "Apply",
              "Cancel"
            );
            if (apply === "Apply") {
              await vscode.workspace.applyEdit(edit);
            }
          }
        } else {
          // Insert at cursor
          const edit = new vscode.WorkspaceEdit();
          edit.insert(document.uri, selection.active, code);

          const confirm = await vscode.window.showInformationMessage(
            "Insert Hwarang's code at cursor?",
            "Insert",
            "Cancel"
          );

          if (confirm === "Insert") {
            await vscode.workspace.applyEdit(edit);
          }
        }
      }
    );
  }
}
