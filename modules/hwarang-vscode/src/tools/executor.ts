/**
 * Tool Executor - Claude Code 수준의 도구 실행기
 *
 * 도구:
 * - read_file: 파일 읽기 (줄 범위 지정 가능)
 * - write_file: 파일 생성/덮어쓰기
 * - edit_file: 문자열 치환 편집
 * - delete_file: 파일/폴더 삭제
 * - search_files: glob/grep 검색
 * - run_command: 셸 명령 실행 (출력 캡처)
 * - list_directory: 디렉토리 목록
 * - get_workspace_info: 워크스페이스 정보
 * - get_diagnostics: 현재 에러/경고 목록
 */

import * as vscode from "vscode";
import * as fs from "fs/promises";
import * as path from "path";
import * as cp from "child_process";
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
      description: "Read the contents of a file. Returns numbered lines.",
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
      description: "Create or overwrite a file with the given content.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "File path relative to workspace root" },
          content: { type: "string", description: "Complete file content" },
        },
        required: ["path", "content"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "edit_file",
      description: "Edit a file by finding and replacing an exact string. Preferred for targeted edits.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "File path relative to workspace root" },
          oldString: { type: "string", description: "Exact string to find (must be unique in file)" },
          newString: { type: "string", description: "Replacement string" },
          replaceAll: { type: "boolean", description: "Replace all occurrences (default: false)" },
        },
        required: ["path", "oldString", "newString"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "delete_file",
      description: "Delete a file or directory.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Path to delete" },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "search_files",
      description: "Search for files by glob pattern or search content by regex.",
      parameters: {
        type: "object",
        properties: {
          pattern: { type: "string", description: "Glob pattern (e.g. '**/*.ts') or regex for grep" },
          type: { type: "string", enum: ["glob", "grep"], description: "Search type" },
          include: { type: "string", description: "For grep: file glob filter (e.g. '*.py')" },
          maxResults: { type: "number", description: "Max results (default 30)" },
        },
        required: ["pattern", "type"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "run_command",
      description: "Execute a shell command and return its stdout/stderr. Use for build, test, git, etc.",
      parameters: {
        type: "object",
        properties: {
          command: { type: "string", description: "Shell command to execute" },
          cwd: { type: "string", description: "Working directory (optional, defaults to workspace root)" },
          timeout: { type: "number", description: "Timeout in ms (default: 30000)" },
        },
        required: ["command"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "list_directory",
      description: "List files and subdirectories with type indicators.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Directory path (default: '.')" },
          recursive: { type: "boolean", description: "List recursively (default: false, max depth 3)" },
        },
        required: [],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_workspace_info",
      description: "Get workspace metadata: open files, git branch, changed files, project type.",
      parameters: { type: "object", properties: {}, required: [] },
    },
  },
  {
    type: "function",
    function: {
      name: "get_diagnostics",
      description: "Get current errors, warnings from VS Code's diagnostics (linting, type checking).",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "File path to get diagnostics for (optional, all files if omitted)" },
          severity: { type: "string", enum: ["error", "warning", "all"], description: "Filter by severity (default: all)" },
        },
        required: [],
      },
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
          return await this.editFile(args.path, args.oldString, args.newString, args.replaceAll);
        case "delete_file":
          return await this.deleteFile(args.path);
        case "search_files":
          return await this.searchFiles(args.pattern, args.type, args.include, args.maxResults);
        case "run_command":
          return await this.runCommand(args.command, args.cwd, args.timeout);
        case "list_directory":
          return await this.listDirectory(args.path, args.recursive);
        case "get_workspace_info":
          return await this.getWorkspaceInfo();
        case "get_diagnostics":
          return await this.getDiagnostics(args.path, args.severity);
        default:
          return { output: `Unknown tool: ${toolName}`, success: false };
      }
    } catch (e: any) {
      return { output: `Error: ${e.message}`, success: false };
    }
  }

  // ======== Tool implementations ========

  private async readFile(filePath: string, startLine?: number, endLine?: number): Promise<ToolResult> {
    const absPath = this.resolvePath(filePath);
    const content = await fs.readFile(absPath, "utf-8");
    const lines = content.split("\n");

    const start = (startLine || 1) - 1;
    const end = endLine || lines.length;
    const selected = lines.slice(start, end);
    const numbered = selected.map((line, i) => `${start + i + 1}\t${line}`).join("\n");

    return {
      output: `File: ${filePath} (${lines.length} lines total, showing ${start + 1}-${Math.min(end, lines.length)})\n${numbered}`,
      success: true,
    };
  }

  private async writeFile(filePath: string, content: string): Promise<ToolResult> {
    const absPath = this.resolvePath(filePath);
    const config = vscode.workspace.getConfiguration("hwarang");
    const autoApply = config.get("autoApplyEdits", false);

    if (!autoApply) {
      const exists = await fs.access(absPath).then(() => true).catch(() => false);
      const action = exists ? "overwrite" : "create";
      const confirm = await vscode.window.showInformationMessage(
        `Hwarang wants to ${action}: ${filePath}`,
        "Allow",
        "Cancel"
      );
      if (confirm !== "Allow") {
        return { output: "User cancelled write operation", success: false };
      }
    }

    await fs.mkdir(path.dirname(absPath), { recursive: true });
    await fs.writeFile(absPath, content, "utf-8");

    // Open in editor
    const doc = await vscode.workspace.openTextDocument(absPath);
    await vscode.window.showTextDocument(doc, { preview: false, preserveFocus: true });

    const lines = content.split("\n").length;
    return { output: `Wrote ${filePath} (${lines} lines, ${content.length} bytes)`, success: true };
  }

  private async editFile(
    filePath: string,
    oldString: string,
    newString: string,
    replaceAll = false
  ): Promise<ToolResult> {
    const absPath = this.resolvePath(filePath);
    const content = await fs.readFile(absPath, "utf-8");

    if (!content.includes(oldString)) {
      return { output: `String not found in ${filePath}. Make sure the old_string matches exactly (including whitespace).`, success: false };
    }

    const occurrences = content.split(oldString).length - 1;
    if (occurrences > 1 && !replaceAll) {
      return {
        output: `Found ${occurrences} occurrences of the string in ${filePath}. Set replaceAll=true to replace all, or provide more context to make the match unique.`,
        success: false,
      };
    }

    const config = vscode.workspace.getConfiguration("hwarang");
    const autoApply = config.get("autoApplyEdits", false);

    if (!autoApply) {
      const confirm = await vscode.window.showInformationMessage(
        `Hwarang wants to edit: ${filePath} (${occurrences} replacement${occurrences > 1 ? "s" : ""})`,
        "Allow",
        "Show Diff",
        "Cancel"
      );

      if (confirm === "Show Diff") {
        const newContent = replaceAll
          ? content.split(oldString).join(newString)
          : content.replace(oldString, newString);
        const doc = await vscode.workspace.openTextDocument({ content: newContent, language: path.extname(filePath).slice(1) });
        await vscode.commands.executeCommand("vscode.diff", vscode.Uri.file(absPath), doc.uri, `${filePath}: Current ↔ Proposed`);

        const applyConfirm = await vscode.window.showInformationMessage("Apply this change?", "Apply", "Cancel");
        if (applyConfirm !== "Apply") {
          return { output: "User cancelled edit", success: false };
        }
      } else if (confirm !== "Allow") {
        return { output: "User cancelled edit", success: false };
      }
    }

    const newContent = replaceAll
      ? content.split(oldString).join(newString)
      : content.replace(oldString, newString);
    await fs.writeFile(absPath, newContent, "utf-8");

    // Refresh in editor
    const doc = await vscode.workspace.openTextDocument(absPath);
    await vscode.window.showTextDocument(doc, { preserveFocus: true });

    return {
      output: `Edited ${filePath}: replaced ${occurrences} occurrence${occurrences > 1 ? "s" : ""} (${oldString.length} → ${newString.length} chars)`,
      success: true,
    };
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
    include?: string,
    maxResults = 30
  ): Promise<ToolResult> {
    if (type === "glob") {
      const uris = await vscode.workspace.findFiles(pattern, "**/node_modules/**", maxResults);
      const paths = uris.map((u) => vscode.workspace.asRelativePath(u)).sort();
      return { output: paths.length ? paths.join("\n") : "No files matched", success: true };
    }

    // grep using ripgrep if available, else manual
    const root = this.getWorkspaceRoot();
    try {
      const rgArgs = [
        "--no-heading",
        "--line-number",
        "--color=never",
        "--max-count=5",
        `-m ${maxResults}`,
      ];
      if (include) rgArgs.push(`--glob=${include}`);
      rgArgs.push("--", pattern, ".");

      const result = await this.execCommand(`rg ${rgArgs.join(" ")}`, root, 10000);
      if (result.stdout.trim()) {
        const lines = result.stdout.trim().split("\n").slice(0, maxResults);
        return { output: lines.join("\n"), success: true };
      }
    } catch {
      // ripgrep not available, fall back to manual search
    }

    // Manual grep fallback
    const results: string[] = [];
    const fileGlob = include || "**/*";
    const uris = await vscode.workspace.findFiles(fileGlob, "**/node_modules/**", 500);

    for (const uri of uris) {
      if (results.length >= maxResults) break;
      try {
        const content = await fs.readFile(uri.fsPath, "utf-8");
        if (content.length > 500_000) continue; // skip large files
        const regex = new RegExp(pattern, "gm");
        const lines = content.split("\n");
        for (let i = 0; i < lines.length; i++) {
          if (regex.test(lines[i])) {
            const relPath = vscode.workspace.asRelativePath(uri);
            results.push(`${relPath}:${i + 1}: ${lines[i].trim().slice(0, 200)}`);
            if (results.length >= maxResults) break;
          }
          regex.lastIndex = 0;
        }
      } catch {
        // skip binary files
      }
    }

    return { output: results.length ? results.join("\n") : "No matches found", success: true };
  }

  private async runCommand(command: string, cwd?: string, timeout = 30000): Promise<ToolResult> {
    // Safety: block extremely dangerous commands
    const blocked = ["rm -rf /", "rm -rf /*", "mkfs", ":(){:|:&};:", "dd if=/dev"];
    if (blocked.some((b) => command.includes(b))) {
      return { output: `Blocked dangerous command: ${command}`, success: false };
    }

    const config = vscode.workspace.getConfiguration("hwarang");
    const autoApply = config.get("autoApplyEdits", false);

    if (!autoApply) {
      const confirm = await vscode.window.showInformationMessage(
        `Run command: ${command}`,
        "Allow",
        "Cancel"
      );
      if (confirm !== "Allow") {
        return { output: "User cancelled command execution", success: false };
      }
    }

    const workDir = cwd ? this.resolvePath(cwd) : this.getWorkspaceRoot();
    const result = await this.execCommand(command, workDir, timeout);

    const output = [
      result.stdout ? `stdout:\n${result.stdout}` : "",
      result.stderr ? `stderr:\n${result.stderr}` : "",
      `exit code: ${result.exitCode}`,
    ]
      .filter(Boolean)
      .join("\n\n");

    // Also show in terminal for visibility
    const terminal = vscode.window.activeTerminal || vscode.window.createTerminal("Hwarang");
    terminal.show(true);

    return { output: output.slice(0, 10000), success: result.exitCode === 0 };
  }

  private execCommand(
    command: string,
    cwd: string,
    timeout: number
  ): Promise<{ stdout: string; stderr: string; exitCode: number }> {
    return new Promise((resolve) => {
      cp.exec(
        command,
        {
          cwd,
          timeout,
          maxBuffer: 1024 * 1024 * 5, // 5MB
          env: { ...process.env, FORCE_COLOR: "0" },
        },
        (error, stdout, stderr) => {
          resolve({
            stdout: stdout || "",
            stderr: stderr || "",
            exitCode: error?.code ?? (error ? 1 : 0),
          });
        }
      );
    });
  }

  private async listDirectory(dirPath = ".", recursive = false): Promise<ToolResult> {
    const absPath = this.resolvePath(dirPath);
    const lines: string[] = [];

    const listDir = async (dir: string, prefix: string, depth: number) => {
      if (depth > 3) return;
      const entries = await fs.readdir(dir, { withFileTypes: true });
      entries.sort((a, b) => {
        if (a.isDirectory() && !b.isDirectory()) return -1;
        if (!a.isDirectory() && b.isDirectory()) return 1;
        return a.name.localeCompare(b.name);
      });

      for (const entry of entries) {
        if (entry.name.startsWith(".") && entry.name !== ".env.example") continue;
        if (entry.name === "node_modules" || entry.name === "__pycache__") continue;

        const icon = entry.isDirectory() ? "📁" : "📄";
        lines.push(`${prefix}${icon} ${entry.name}`);

        if (recursive && entry.isDirectory() && lines.length < 200) {
          await listDir(path.join(dir, entry.name), prefix + "  ", depth + 1);
        }
      }
    };

    await listDir(absPath, "", 0);
    return { output: lines.join("\n") || "Empty directory", success: true };
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

    const activeFile = vscode.window.activeTextEditor?.document.fileName;
    const activeRelative = activeFile ? path.relative(root, activeFile) : "none";

    const info: string[] = [
      `Workspace: ${rootName}`,
      `Root: ${root}`,
      `Active file: ${activeRelative}`,
      `Open files: ${openEditors.slice(0, 10).join(", ") || "none"}`,
    ];

    // Git info
    try {
      const branch = await this.execCommand("git branch --show-current", root, 3000);
      if (branch.stdout.trim()) {
        info.push(`Git branch: ${branch.stdout.trim()}`);
      }
      const status = await this.execCommand("git status --short", root, 3000);
      if (status.stdout.trim()) {
        const changes = status.stdout.trim().split("\n");
        info.push(`Changed files (${changes.length}):`);
        changes.slice(0, 15).forEach((c) => info.push(`  ${c}`));
        if (changes.length > 15) info.push(`  ... and ${changes.length - 15} more`);
      }
    } catch {
      // git not available
    }

    // Detect project type
    try {
      const files = await fs.readdir(root);
      const projectType: string[] = [];
      if (files.includes("package.json")) projectType.push("Node.js");
      if (files.includes("requirements.txt") || files.includes("pyproject.toml")) projectType.push("Python");
      if (files.includes("go.mod")) projectType.push("Go");
      if (files.includes("Cargo.toml")) projectType.push("Rust");
      if (files.includes("pom.xml") || files.includes("build.gradle")) projectType.push("Java");
      if (projectType.length) info.push(`Project type: ${projectType.join(", ")}`);
    } catch {}

    return { output: info.join("\n"), success: true };
  }

  private async getDiagnostics(filePath?: string, severity?: string): Promise<ToolResult> {
    let diagnostics: [vscode.Uri, readonly vscode.Diagnostic[]][];

    if (filePath) {
      const absPath = this.resolvePath(filePath);
      const uri = vscode.Uri.file(absPath);
      const diags = vscode.languages.getDiagnostics(uri);
      diagnostics = [[uri, diags]];
    } else {
      diagnostics = vscode.languages.getDiagnostics() as [vscode.Uri, readonly vscode.Diagnostic[]][];
    }

    const lines: string[] = [];
    const root = this.getWorkspaceRoot();

    for (const [uri, diags] of diagnostics) {
      const filtered = diags.filter((d) => {
        if (severity === "error") return d.severity === vscode.DiagnosticSeverity.Error;
        if (severity === "warning") return d.severity <= vscode.DiagnosticSeverity.Warning;
        return true;
      });

      if (filtered.length === 0) continue;

      const relPath = path.relative(root, uri.fsPath);
      for (const d of filtered) {
        const sev = d.severity === vscode.DiagnosticSeverity.Error ? "ERROR" :
                    d.severity === vscode.DiagnosticSeverity.Warning ? "WARN" : "INFO";
        lines.push(`${relPath}:${d.range.start.line + 1}: [${sev}] ${d.message}`);
      }
    }

    if (lines.length === 0) {
      return { output: "No diagnostics found", success: true };
    }

    return { output: `${lines.length} diagnostic(s):\n${lines.slice(0, 50).join("\n")}`, success: true };
  }
}
