/**
 * Tool Executor - Executes AI tool calls in VS Code.
 *
 * These are the actions the AI can take:
 * - Read files
 * - Write/create files
 * - Edit files (find & replace)
 * - Delete files
 * - Search files (glob, grep)
 * - Run terminal commands
 * - Get workspace info
 */

import * as vscode from "vscode";
import * as fs from "fs/promises";
import * as path from "path";
import { glob } from "./glob-helper";

export interface ToolResult {
  output: string;
  success: boolean;
}

/** Tool definitions in OpenAI function-calling format */
export const TOOL_DEFINITIONS = [
  {
    type: "function",
    function: {
      name: "read_file",
      description: "Read the contents of a file in the workspace",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "File path relative to workspace root" },
          startLine: { type: "number", description: "Start line (1-based, optional)" },
          endLine: { type: "number", description: "End line (1-based, optional)" },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "write_file",
      description: "Create a new file or completely overwrite an existing file",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "File path relative to workspace root" },
          content: { type: "string", description: "Complete file content to write" },
        },
        required: ["path", "content"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "edit_file",
      description: "Edit a file by replacing a specific string with new content. Use this for targeted modifications.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "File path relative to workspace root" },
          oldString: { type: "string", description: "Exact string to find and replace" },
          newString: { type: "string", description: "Replacement string" },
        },
        required: ["path", "oldString", "newString"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "delete_file",
      description: "Delete a file or directory from the workspace",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "File path relative to workspace root" },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "search_files",
      description: "Search for files by name pattern (glob) or content (regex grep)",
      parameters: {
        type: "object",
        properties: {
          pattern: { type: "string", description: "Glob pattern (e.g. '**/*.ts') or regex for content search" },
          type: { type: "string", enum: ["glob", "grep"], description: "Search type" },
          maxResults: { type: "number", description: "Max results (default 20)" },
        },
        required: ["pattern", "type"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "run_terminal",
      description: "Execute a command in the VS Code integrated terminal",
      parameters: {
        type: "object",
        properties: {
          command: { type: "string", description: "Shell command to execute" },
        },
        required: ["command"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "list_directory",
      description: "List files and directories in a given path",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Directory path relative to workspace root (default: '.')" },
        },
        required: [],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_workspace_info",
      description: "Get information about the current workspace: open files, git status, project structure",
      parameters: { type: "object", properties: {}, required: [] },
    },
  },
];

export class ToolExecutor {
  private getWorkspaceRoot(): string {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders?.length) throw new Error("No workspace folder open");
    return folders[0].uri.fsPath;
  }

  private resolvePath(filePath: string): string {
    const root = this.getWorkspaceRoot();
    if (path.isAbsolute(filePath)) return filePath;
    return path.join(root, filePath);
  }

  async execute(toolName: string, argsJson: string): Promise<ToolResult> {
    try {
      const args = JSON.parse(argsJson);

      switch (toolName) {
        case "read_file":
          return await this.readFile(args.path, args.startLine, args.endLine);
        case "write_file":
          return await this.writeFile(args.path, args.content);
        case "edit_file":
          return await this.editFile(args.path, args.oldString, args.newString);
        case "delete_file":
          return await this.deleteFile(args.path);
        case "search_files":
          return await this.searchFiles(args.pattern, args.type, args.maxResults);
        case "run_terminal":
          return await this.runTerminal(args.command);
        case "list_directory":
          return await this.listDirectory(args.path);
        case "get_workspace_info":
          return await this.getWorkspaceInfo();
        default:
          return { output: `Unknown tool: ${toolName}`, success: false };
      }
    } catch (e: any) {
      return { output: `Error: ${e.message}`, success: false };
    }
  }

  // ---- Tool implementations ----

  private async readFile(
    filePath: string,
    startLine?: number,
    endLine?: number
  ): Promise<ToolResult> {
    const absPath = this.resolvePath(filePath);
    const content = await fs.readFile(absPath, "utf-8");
    const lines = content.split("\n");

    const start = (startLine || 1) - 1;
    const end = endLine || lines.length;
    const selected = lines.slice(start, end);
    const numbered = selected.map((line, i) => `${start + i + 1}\t${line}`).join("\n");

    return { output: `File: ${filePath} (${lines.length} lines)\n${numbered}`, success: true };
  }

  private async writeFile(filePath: string, content: string): Promise<ToolResult> {
    const absPath = this.resolvePath(filePath);
    const config = vscode.workspace.getConfiguration("hwarang");
    const autoApply = config.get("autoApplyEdits", false);

    if (!autoApply) {
      // Show diff and ask for confirmation
      const confirm = await vscode.window.showInformationMessage(
        `Hwarang wants to write to: ${filePath}`,
        "Allow",
        "Cancel"
      );
      if (confirm !== "Allow") {
        return { output: "User cancelled write operation", success: false };
      }
    }

    // Create directories if needed
    await fs.mkdir(path.dirname(absPath), { recursive: true });
    await fs.writeFile(absPath, content, "utf-8");

    // Open the file in editor
    const doc = await vscode.workspace.openTextDocument(absPath);
    await vscode.window.showTextDocument(doc, { preview: false });

    return { output: `Wrote ${content.length} bytes to ${filePath}`, success: true };
  }

  private async editFile(
    filePath: string,
    oldString: string,
    newString: string
  ): Promise<ToolResult> {
    const absPath = this.resolvePath(filePath);
    const content = await fs.readFile(absPath, "utf-8");

    if (!content.includes(oldString)) {
      return { output: `String not found in ${filePath}`, success: false };
    }

    const config = vscode.workspace.getConfiguration("hwarang");
    const autoApply = config.get("autoApplyEdits", false);

    if (!autoApply) {
      const confirm = await vscode.window.showInformationMessage(
        `Hwarang wants to edit: ${filePath}`,
        "Allow",
        "Show Diff",
        "Cancel"
      );

      if (confirm === "Show Diff") {
        // Show the diff in VS Code
        const newContent = content.replace(oldString, newString);
        const tempUri = vscode.Uri.parse(`untitled:${filePath}.proposed`);
        const doc = await vscode.workspace.openTextDocument({ content: newContent });
        await vscode.commands.executeCommand(
          "vscode.diff",
          vscode.Uri.file(absPath),
          doc.uri,
          `${filePath}: Current ↔ Proposed`
        );

        const applyConfirm = await vscode.window.showInformationMessage(
          "Apply this change?",
          "Apply",
          "Cancel"
        );
        if (applyConfirm !== "Apply") {
          return { output: "User cancelled edit", success: false };
        }
      } else if (confirm !== "Allow") {
        return { output: "User cancelled edit", success: false };
      }
    }

    const newContent = content.replace(oldString, newString);
    await fs.writeFile(absPath, newContent, "utf-8");

    // Refresh the editor
    const doc = await vscode.workspace.openTextDocument(absPath);
    await vscode.window.showTextDocument(doc);

    return { output: `Edited ${filePath}: replaced ${oldString.length} chars`, success: true };
  }

  private async deleteFile(filePath: string): Promise<ToolResult> {
    const absPath = this.resolvePath(filePath);

    const confirm = await vscode.window.showWarningMessage(
      `Hwarang wants to delete: ${filePath}`,
      { modal: true },
      "Delete",
      "Cancel"
    );

    if (confirm !== "Delete") {
      return { output: "User cancelled delete", success: false };
    }

    const stat = await fs.stat(absPath);
    if (stat.isDirectory()) {
      await fs.rm(absPath, { recursive: true });
    } else {
      await fs.unlink(absPath);
    }

    return { output: `Deleted ${filePath}`, success: true };
  }

  private async searchFiles(
    pattern: string,
    type: string,
    maxResults = 20
  ): Promise<ToolResult> {
    if (type === "glob") {
      const uris = await vscode.workspace.findFiles(pattern, "**/node_modules/**", maxResults);
      const paths = uris.map((u) => vscode.workspace.asRelativePath(u));
      return { output: paths.join("\n") || "No matches", success: true };
    }

    // grep
    const results: string[] = [];
    const uris = await vscode.workspace.findFiles("**/*", "**/node_modules/**", 500);

    for (const uri of uris) {
      if (results.length >= maxResults) break;
      try {
        const content = await fs.readFile(uri.fsPath, "utf-8");
        const regex = new RegExp(pattern, "gm");
        const lines = content.split("\n");
        for (let i = 0; i < lines.length; i++) {
          if (regex.test(lines[i])) {
            const relPath = vscode.workspace.asRelativePath(uri);
            results.push(`${relPath}:${i + 1}: ${lines[i].trim()}`);
            if (results.length >= maxResults) break;
          }
          regex.lastIndex = 0;
        }
      } catch {
        // skip binary/unreadable files
      }
    }

    return { output: results.join("\n") || "No matches", success: true };
  }

  private async runTerminal(command: string): Promise<ToolResult> {
    // Safety check
    const dangerous = ["rm -rf /", "format", "mkfs", ":(){:|:&};:"];
    if (dangerous.some((d) => command.includes(d))) {
      return { output: `Blocked dangerous command: ${command}`, success: false };
    }

    const confirm = await vscode.window.showInformationMessage(
      `Hwarang wants to run: ${command}`,
      "Allow",
      "Cancel"
    );

    if (confirm !== "Allow") {
      return { output: "User cancelled command", success: false };
    }

    // Execute via terminal
    const terminal =
      vscode.window.activeTerminal ||
      vscode.window.createTerminal("Hwarang");
    terminal.show();
    terminal.sendText(command);

    return { output: `Executed in terminal: ${command}`, success: true };
  }

  private async listDirectory(dirPath = "."): Promise<ToolResult> {
    const absPath = this.resolvePath(dirPath);
    const entries = await fs.readdir(absPath, { withFileTypes: true });

    const lines = entries.map((e) => {
      const type = e.isDirectory() ? "📁" : "📄";
      return `${type} ${e.name}`;
    });

    return { output: lines.join("\n"), success: true };
  }

  private async getWorkspaceInfo(): Promise<ToolResult> {
    const root = this.getWorkspaceRoot();
    const rootName = path.basename(root);

    // Open editors
    const openEditors = vscode.window.tabGroups.all
      .flatMap((g) => g.tabs)
      .map((t) => (t.input as any)?.uri?.fsPath)
      .filter(Boolean)
      .map((p: string) => path.relative(root, p));

    // Active file
    const activeFile = vscode.window.activeTextEditor?.document.fileName;
    const activeRelative = activeFile ? path.relative(root, activeFile) : "none";

    const info = [
      `Workspace: ${rootName}`,
      `Root: ${root}`,
      `Active file: ${activeRelative}`,
      `Open files: ${openEditors.join(", ") || "none"}`,
    ];

    // Try to get git info
    try {
      const gitExt = vscode.extensions.getExtension("vscode.git");
      if (gitExt?.isActive) {
        const git = gitExt.exports.getAPI(1);
        const repo = git.repositories[0];
        if (repo) {
          info.push(`Git branch: ${repo.state.HEAD?.name || "detached"}`);
          info.push(`Changed files: ${repo.state.workingTreeChanges.length}`);
        }
      }
    } catch {
      // git not available
    }

    return { output: info.join("\n"), success: true };
  }
}
