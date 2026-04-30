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
import { getMode, isWriteAllowed, isAutoApprove } from "./mode";
import {
  checkDangerous,
  requiresConfirmation,
  checkDelete,
  confirmDangerous,
} from "./safety";
import { GitPRCreator } from "../utils/git-pr";

export interface ToolResult {
  output: string;
  success: boolean;
}

/**
 * Webview 로 양방향 통신하기 위한 인터페이스.
 * postMessage 만 노출 — chat-view-provider 가 webview 를 주입한다.
 */
export interface WebviewBridge {
  postMessage(message: any): Thenable<boolean> | boolean;
}

/**
 * 배치 모드에서 큐에 쌓이는 파일 변경 항목.
 */
interface PendingFileChange {
  tool: "write_file" | "edit_file";
  path: string;
  absPath: string;
  oldContent: string; // 삭제됨/없음이면 ""
  newContent: string;
  // edit_file 전용
  oldString?: string;
  newString?: string;
  replaceAll?: boolean;
  occurrences?: number;
}

/**
 * 배치 결과.
 */
export interface BatchResult {
  approved: boolean;
  appliedCount: number;
  skipped: string[];
}

/**
 * 백그라운드 task 상태.
 */
interface BgTask {
  id: string;
  command: string;
  cwd: string;
  proc: cp.ChildProcess;
  output: string;
  status: "running" | "completed" | "failed";
  exitCode?: number;
  startedAt: number;
  finishedAt?: number;
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
  {
    type: "function",
    function: {
      name: "write_todo",
      description:
        "복잡한 작업을 step 으로 분할해 UI 에 진행 상황을 표시한다. 3개 이상 step 이 필요한 작업이면 먼저 호출. 같은 plan 을 status 만 갱신해서 재호출하면 진행률이 업데이트된다.",
      parameters: {
        type: "object",
        properties: {
          plan: {
            type: "array",
            items: {
              type: "object",
              properties: {
                id: { type: "string", description: "step 식별자 (간단한 영숫자)" },
                title: { type: "string", description: "step 제목 (한국어 권장, 짧게)" },
                status: {
                  type: "string",
                  enum: ["pending", "in_progress", "completed", "failed"],
                  description: "현재 상태",
                },
              },
              required: ["id", "title", "status"],
            },
          },
        },
        required: ["plan"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "run_command_background",
      description:
        "긴 명령 (npm install / build / test 등) 을 백그라운드로 실행. 즉시 task_id 반환. check_background_task 로 폴링하여 결과 확인. 완료 시 UI 토스트 알림.",
      parameters: {
        type: "object",
        properties: {
          command: { type: "string", description: "쉘 명령" },
          cwd: { type: "string", description: "작업 디렉토리 (선택)" },
        },
        required: ["command"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "check_background_task",
      description:
        "백그라운드 task 의 상태/출력 확인. 마지막 4000자만 반환.",
      parameters: {
        type: "object",
        properties: {
          task_id: { type: "string", description: "run_command_background 가 반환한 ID" },
        },
        required: ["task_id"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "delegate_subtask",
      description:
        "큰 sub-task 를 별도 에이전트에 위임. 메인 작업이 multi-domain (예: 'API 추가 + 프론트 + 테스트') 일 때만 사용. " +
        "단순 step 분할은 write_todo 사용. 재귀 위임 금지 (sub-agent 안에서 또 호출 금지). " +
        "결과 요약만 메인 agent 로 반환됨.",
      parameters: {
        type: "object",
        properties: {
          title: { type: "string", description: "sub-task 의 짧은 제목" },
          instructions: {
            type: "string",
            description: "sub-task 의 상세 지시문 (sub-agent 가 받을 user message)",
          },
          expected_outputs: {
            type: "array",
            items: { type: "string" },
            description: "이 sub-task 가 만들어야 할 결과물 목록 (파일/명령 결과 등)",
          },
        },
        required: ["title", "instructions"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "create_pull_request",
      description:
        "현재 변경사항을 새 브랜치로 push 후 GitHub PR 자동 생성. 큰 작업 마무리에 사용. " +
        "main/master 직접 push 금지. 기본 draft 모드로 안전하게 생성. gh CLI 필요.",
      parameters: {
        type: "object",
        properties: {
          title: { type: "string", description: "PR 제목 (한국어 또는 영어)" },
          body: { type: "string", description: "PR 본문 (작업 요약, 변경 내용)" },
          base_branch: {
            type: "string",
            description: "병합 대상 브랜치 (기본: main)",
          },
          draft: {
            type: "boolean",
            description: "draft 모드 (기본: true, 안전)",
          },
        },
        required: ["title", "body"],
      },
    },
  },
];

/**
 * Sub-agent 위임 핸들러 — agent-loop 가 실제 AgentLoop 인스턴스를 만들기 위해
 * 외부에서 주입한다. (executor.ts 가 agent-loop.ts 에 의존하면 순환 import 발생)
 *
 * agent-loop.ts 가 ToolExecutor 생성 후 setSubagentRunner 로 콜백 등록.
 * 콜백은 instructions 를 받아 sub-agent 를 돌리고 요약 문자열을 반환.
 */
export type SubagentRunner = (params: {
  title: string;
  instructions: string;
  expectedOutputs?: string[];
}) => Promise<{ success: boolean; summary: string }>;

export class ToolExecutor {
  /** webview 와 양방향 통신 (todo / batch / bg task 알림). agent-loop 가 주입. */
  private bridge: WebviewBridge | null = null;

  /** 배치 모드 상태 — agent-loop 가 한 turn 안의 여러 write/edit 를 한 번에 묶을 때 사용 */
  private batchMode = false;
  private pendingFileChanges: PendingFileChange[] = [];

  /** 백그라운드 task 추적 */
  private bgTasks: Map<string, BgTask> = new Map();

  /** Sub-agent 위임 콜백 — agent-loop 가 setSubagentRunner 로 주입. */
  private subagentRunner: SubagentRunner | null = null;

  /** 메인 작업당 sub-task 호출 카운터 (5회 제한) */
  private subagentCallCount = 0;
  private static readonly MAX_SUBAGENT_CALLS = 5;

  /** webview bridge 주입 — chat-view-provider 가 호출. */
  setBridge(bridge: WebviewBridge | null) {
    this.bridge = bridge;
  }

  /** Sub-agent 위임 러너 주입 — agent-loop 가 호출. null 이면 도구 비활성. */
  setSubagentRunner(runner: SubagentRunner | null) {
    this.subagentRunner = runner;
  }

  /** 새 user turn 시작 시 sub-agent 카운터 리셋 — agent-loop 가 호출 */
  resetSubagentCounter() {
    this.subagentCallCount = 0;
  }

  /** 배치 모드 시작 — 이후 write_file / edit_file 은 즉시 적용 안 하고 큐에 쌓임. */
  beginBatch() {
    this.batchMode = true;
    this.pendingFileChanges = [];
  }

  /** 배치 큐가 비어있는지 확인 (agent-loop 가 자동 batch 진입 결정 시 사용) */
  hasPendingBatch(): boolean {
    return this.batchMode && this.pendingFileChanges.length > 0;
  }

  /** 배치 큐 길이 */
  pendingBatchCount(): number {
    return this.pendingFileChanges.length;
  }

  /**
   * 배치 모드 종료 + 사용자 승인 받기 + 일괄 적용.
   * - bridge 가 있으면 webview 모달로 미리보기 노출
   * - 없으면 vscode.window.showInformationMessage 폴백
   */
  async commitBatch(): Promise<BatchResult> {
    const changes = this.pendingFileChanges;
    this.batchMode = false;
    this.pendingFileChanges = [];

    if (changes.length === 0) {
      return { approved: true, appliedCount: 0, skipped: [] };
    }

    // 자동 모드면 모달 없이 즉시 적용
    const mode = getMode();
    let approved = isAutoApprove(mode);

    if (!approved) {
      // 1) webview 모달 우선
      if (this.bridge) {
        approved = await this.requestBatchApprovalViaWebview(changes);
      } else {
        // 2) 폴백: VS Code 다이얼로그
        const list = changes
          .map((c) => `  ${c.tool === "write_file" ? "쓰기" : "수정"}: ${c.path}`)
          .join("\n");
        const r = await vscode.window.showInformationMessage(
          `${changes.length}개 파일 변경 제안 — 모두 적용할까요?`,
          { modal: true, detail: list },
          "모두 적용",
          "취소"
        );
        approved = r === "모두 적용";
      }
    }

    if (!approved) {
      return {
        approved: false,
        appliedCount: 0,
        skipped: changes.map((c) => c.path),
      };
    }

    // 적용 — 실패한 항목은 skipped 에 누적
    const skipped: string[] = [];
    let appliedCount = 0;
    for (const c of changes) {
      try {
        if (c.tool === "write_file") {
          await fs.mkdir(path.dirname(c.absPath), { recursive: true });
          await fs.writeFile(c.absPath, c.newContent, "utf-8");
        } else {
          // edit_file
          const current = await fs.readFile(c.absPath, "utf-8");
          if (!current.includes(c.oldString!)) {
            skipped.push(`${c.path} (oldString not found)`);
            continue;
          }
          const updated = c.replaceAll
            ? current.split(c.oldString!).join(c.newString!)
            : current.replace(c.oldString!, c.newString!);
          await fs.writeFile(c.absPath, updated, "utf-8");
        }
        appliedCount++;
      } catch (e: any) {
        skipped.push(`${c.path} (${e.message})`);
      }
    }

    // 적용된 파일을 에디터에서 갱신
    for (const c of changes) {
      try {
        const doc = await vscode.workspace.openTextDocument(c.absPath);
        await vscode.window.showTextDocument(doc, { preview: false, preserveFocus: true });
      } catch { /* skip */ }
    }

    return { approved: true, appliedCount, skipped };
  }

  /**
   * webview 모달로 일괄 승인 요청. 사용자가 응답하면 resolve.
   */
  private requestBatchApprovalViaWebview(
    changes: PendingFileChange[]
  ): Promise<boolean> {
    return new Promise((resolve) => {
      const requestId = `batch-${Date.now()}`;
      const summary = changes.map((c) => ({
        path: c.path,
        tool: c.tool,
        oldLen: c.oldContent.length,
        newLen: c.newContent.length,
        diff: makeSimpleDiff(c.oldContent, c.newContent).slice(0, 4000),
      }));

      // 일회성 응답 핸들러는 chat-view-provider 가 처리.
      // 여기서는 postMessage 후 onBatchResponse 콜백 등록.
      this.pendingBatchResolve = resolve;
      this.bridge?.postMessage({
        type: "batchApprovalRequest",
        requestId,
        files: summary,
      });

      // 60초 안에 응답 없으면 거부
      setTimeout(() => {
        if (this.pendingBatchResolve === resolve) {
          this.pendingBatchResolve = null;
          resolve(false);
        }
      }, 60000);
    });
  }

  private pendingBatchResolve: ((v: boolean) => void) | null = null;

  /** chat-view-provider 가 webview 의 batch 응답을 받으면 이 메서드 호출. */
  resolveBatchApproval(approved: boolean) {
    if (this.pendingBatchResolve) {
      this.pendingBatchResolve(approved);
      this.pendingBatchResolve = null;
    }
  }

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
        case "write_todo":
          return this.writeTodo(args.plan);
        case "run_command_background":
          return this.runCommandBackground(args.command, args.cwd);
        case "check_background_task":
          return this.checkBackgroundTask(args.task_id);
        case "delegate_subtask":
          return await this.delegateSubtask(
            args.title,
            args.instructions,
            args.expected_outputs
          );
        case "create_pull_request":
          return await this.createPullRequest(
            args.title,
            args.body,
            args.base_branch,
            args.draft
          );
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
    const mode = getMode();

    // 플랜 모드: 실제 쓰기 안 하고 계획만 반환
    if (!isWriteAllowed(mode)) {
      const exists = await fs.access(absPath).then(() => true).catch(() => false);
      const action = exists ? "덮어쓰기" : "생성";
      const lines = content.split("\n").length;
      return {
        output: `[플랜 모드] 예정 작업: ${action} ${filePath} (${lines}줄, ${content.length}바이트)\n실행하려면 자동/수동 모드로 전환하세요.`,
        success: true,
      };
    }

    // 배치 모드: 실제 적용 안 하고 큐에 쌓기
    if (this.batchMode) {
      const oldContent = await fs.readFile(absPath, "utf-8").catch(() => "");
      this.pendingFileChanges.push({
        tool: "write_file",
        path: filePath,
        absPath,
        oldContent,
        newContent: content,
      });
      return {
        success: true,
        output: `Queued for batch approval: write_file(${filePath}, ${content.length} bytes)`,
      };
    }

    // 수동 모드: 승인 요청
    if (!isAutoApprove(mode)) {
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

    const mode = getMode();

    // 플랜 모드: 계획만
    if (!isWriteAllowed(mode)) {
      return {
        output: `[플랜 모드] 예정 수정: ${filePath} (${occurrences}개 치환, ${oldString.length}자 → ${newString.length}자)\n실행하려면 자동/수동 모드로 전환하세요.`,
        success: true,
      };
    }

    // 배치 모드: 큐에 쌓기
    if (this.batchMode) {
      const newContent = replaceAll
        ? content.split(oldString).join(newString)
        : content.replace(oldString, newString);
      this.pendingFileChanges.push({
        tool: "edit_file",
        path: filePath,
        absPath,
        oldContent: content,
        newContent,
        oldString,
        newString,
        replaceAll,
        occurrences,
      });
      return {
        success: true,
        output: `Queued for batch approval: edit_file(${filePath}, ${occurrences} replacement${occurrences > 1 ? "s" : ""})`,
      };
    }

    if (!isAutoApprove(mode)) {
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
    const root = this.getWorkspaceRoot();
    const mode = getMode();

    // 안전망: path traversal / .git 보호 / 큰 디렉토리 경고
    const safety = checkDelete(absPath, root);
    if (safety.blocked) {
      return { output: `[안전 차단] ${safety.reason}`, success: false };
    }

    // 플랜 모드: 삭제 계획만
    if (!isWriteAllowed(mode)) {
      return {
        output: `[플랜 모드] 예정 삭제: ${filePath}\n실행하려면 자동/수동 모드로 전환하세요.`,
        success: true,
      };
    }

    // 큰 디렉토리는 자동 모드라도 한 번 더 확인
    if (safety.warnLargeDir) {
      const ok = await confirmDangerous(
        `대용량 디렉토리 삭제: ${filePath}`,
        "node_modules / dist 등의 큰 디렉토리는 시간이 오래 걸리고 복구가 어렵습니다. 진행할까요?"
      );
      if (!ok) return { output: "User cancelled delete (heavy dir)", success: false };
    } else if (!isAutoApprove(mode)) {
      // 일반 삭제 — 수동 모드면 확인
      const confirm = await vscode.window.showWarningMessage(
        `Hwarang wants to delete: ${filePath}`,
        { modal: true },
        "Delete",
        "Cancel"
      );
      if (confirm !== "Delete") {
        return { output: "User cancelled delete", success: false };
      }
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

  private async runCommand(command: string, cwd?: string, timeout = 120000): Promise<ToolResult> {
    // Safety: 즉시 차단 패턴
    const danger = checkDangerous(command);
    if (danger.blocked) {
      return {
        output: `[안전 차단] ${danger.reason}\n명령: ${command}`,
        success: false,
      };
    }

    const mode = getMode();

    // 플랜 모드: 명령 계획만
    if (!isWriteAllowed(mode)) {
      return {
        output: `[플랜 모드] 예정 명령: ${command}\n실행하려면 자동/수동 모드로 전환하세요.`,
        success: true,
      };
    }

    // 명시 승인 필요 패턴 → 모드 무관 모달
    const reqPat = requiresConfirmation(command);
    if (reqPat) {
      const ok = await confirmDangerous(
        `명시 승인 필요한 명령: ${command}`,
        `이 명령은 시스템/원격 상태를 변경합니다 (패턴: ${reqPat.source}).\n계속할까요?`
      );
      if (!ok) {
        return { output: "User declined confirmation-required command", success: false };
      }
    } else if (!isAutoApprove(mode)) {
      // 일반 명령 — 수동 모드면 확인
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

  // ============================================================
  // 신규 도구: write_todo / run_command_background / check_background_task
  // ============================================================

  private writeTodo(plan: any[]): ToolResult {
    if (!Array.isArray(plan)) {
      return { output: "Invalid plan: must be an array", success: false };
    }

    // webview 로 진행 상황 push
    this.bridge?.postMessage({ type: "todoUpdate", plan });

    const summary = plan
      .map((t) => {
        const mark =
          t.status === "completed" ? "[x]" :
          t.status === "in_progress" ? "[~]" :
          t.status === "failed" ? "[!]" : "[ ]";
        return `${mark} ${t.title}`;
      })
      .join("\n");

    return {
      success: true,
      output: `Todo updated (${plan.length} items)\n${summary}`,
    };
  }

  private runCommandBackground(command: string, cwd?: string): ToolResult {
    // 안전망 — 백그라운드라도 dangerous 패턴은 차단
    const danger = checkDangerous(command);
    if (danger.blocked) {
      return {
        output: `[안전 차단] ${danger.reason}\n명령: ${command}`,
        success: false,
      };
    }

    const mode = getMode();
    if (!isWriteAllowed(mode)) {
      return {
        output: `[플랜 모드] 예정 백그라운드 명령: ${command}`,
        success: true,
      };
    }

    const workDir = cwd ? this.resolvePath(cwd) : this.getWorkspaceRoot();
    const taskId = `bg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;

    const proc = cp.spawn(command, {
      shell: true,
      cwd: workDir,
      env: { ...process.env, FORCE_COLOR: "0" },
    });

    const task: BgTask = {
      id: taskId,
      command,
      cwd: workDir,
      proc,
      output: "",
      status: "running",
      startedAt: Date.now(),
    };
    this.bgTasks.set(taskId, task);

    const onData = (d: Buffer) => {
      task.output += d.toString();
      // 메모리 보호 — 마지막 200KB 만 유지
      if (task.output.length > 200_000) {
        task.output = task.output.slice(-200_000);
      }
    };

    proc.stdout?.on("data", onData);
    proc.stderr?.on("data", onData);

    proc.on("close", (code) => {
      const t = this.bgTasks.get(taskId);
      if (!t) return;
      t.status = code === 0 ? "completed" : "failed";
      t.exitCode = code ?? -1;
      t.finishedAt = Date.now();
      this.bridge?.postMessage({
        type: "bgTaskComplete",
        taskId,
        status: t.status,
        exitCode: t.exitCode,
        durationMs: t.finishedAt - t.startedAt,
        command,
      });
    });

    proc.on("error", (err) => {
      const t = this.bgTasks.get(taskId);
      if (!t) return;
      t.status = "failed";
      t.exitCode = -1;
      t.output += `\n[spawn error] ${err.message}`;
      t.finishedAt = Date.now();
      this.bridge?.postMessage({
        type: "bgTaskComplete",
        taskId,
        status: "failed",
        exitCode: -1,
        durationMs: (t.finishedAt || Date.now()) - t.startedAt,
        command,
      });
    });

    return {
      success: true,
      output:
        `Background task started: ${taskId}\nCommand: ${command}\ncwd: ${workDir}\n` +
        `Use check_background_task(task_id="${taskId}") to poll status.`,
    };
  }

  private checkBackgroundTask(taskId: string): ToolResult {
    const t = this.bgTasks.get(taskId);
    if (!t) {
      return { output: `Task not found: ${taskId}`, success: false };
    }
    const dur = t.finishedAt ? t.finishedAt - t.startedAt : Date.now() - t.startedAt;
    const tail = t.output.slice(-4000);
    return {
      success: true,
      output:
        `Task: ${taskId}\n` +
        `Command: ${t.command}\n` +
        `Status: ${t.status}\n` +
        `Exit code: ${t.exitCode ?? "(running)"}\n` +
        `Duration: ${(dur / 1000).toFixed(1)}s\n` +
        `--- output (last 4KB) ---\n${tail || "(no output yet)"}`,
    };
  }

  /**
   * Sub-agent 위임 — agent-loop 가 주입한 SubagentRunner 콜백 호출.
   * 안전 제한:
   *  - 메인 작업당 최대 MAX_SUBAGENT_CALLS 번
   *  - 재귀 위임은 sub-agent 의 도구 목록에서 delegate_subtask 를 빼는 방식으로 차단 (agent-loop 측)
   */
  private async delegateSubtask(
    title: string,
    instructions: string,
    expectedOutputs?: string[]
  ): Promise<ToolResult> {
    if (!this.subagentRunner) {
      return {
        output:
          "delegate_subtask 비활성 — sub-agent 모드입니다 (재귀 위임 금지) 또는 메인 agent 가 runner 를 주입하지 않았습니다.",
        success: false,
      };
    }

    if (this.subagentCallCount >= ToolExecutor.MAX_SUBAGENT_CALLS) {
      return {
        output: `Sub-task 호출 한도 (${ToolExecutor.MAX_SUBAGENT_CALLS}개) 초과 — 메인 agent 가 직접 처리하세요.`,
        success: false,
      };
    }

    if (!title || !instructions) {
      return {
        output: "delegate_subtask: title 과 instructions 는 필수입니다.",
        success: false,
      };
    }

    this.subagentCallCount++;

    try {
      const r = await this.subagentRunner({
        title,
        instructions,
        expectedOutputs,
      });
      return {
        success: r.success,
        output:
          `Subtask "${title}" ${r.success ? "완료" : "실패"}.\n${r.summary}`,
      };
    } catch (e: any) {
      return {
        output: `Sub-task 실행 중 오류: ${e?.message || e}`,
        success: false,
      };
    }
  }

  /**
   * GitHub PR 자동 생성 — 큰 작업 마무리 시 LLM 이 호출.
   *
   * 흐름: status 확인 → branch 생성 → add+commit → push → gh pr create --draft
   *
   * 안전:
   *  - main/master 직접 push 차단 (git-pr.ts 내부 검증)
   *  - 기본 draft 모드 (사용자 검토 후 ready-for-review)
   *  - gh CLI 미설치 시 graceful 에러
   */
  private async createPullRequest(
    title: string,
    body: string,
    baseBranch?: string,
    draft?: boolean,
  ): Promise<ToolResult> {
    if (!title || !body) {
      return {
        output: "create_pull_request: title 과 body 는 필수입니다.",
        success: false,
      };
    }

    const folders = vscode.workspace.workspaceFolders;
    if (!folders?.length) {
      return {
        output: "create_pull_request: 워크스페이스가 열려있지 않습니다.",
        success: false,
      };
    }
    const workspaceRoot = folders[0].uri.fsPath;

    try {
      const creator = new GitPRCreator();
      const result = await creator.createPR({
        workspaceRoot,
        title,
        body,
        baseBranch: baseBranch || "main",
        draft: draft !== false, // 기본 true (안전)
      });

      if (result.success) {
        const lines = [
          `✓ PR 생성 완료`,
          `URL: ${result.prUrl || "(URL 미반환)"}`,
          `branch: ${result.branch}`,
          result.commitHash ? `commit: ${result.commitHash.slice(0, 8)}` : "",
        ].filter(Boolean);
        return { success: true, output: lines.join("\n") };
      }

      return {
        success: false,
        output: `PR 생성 실패: ${result.error || "(알 수 없는 오류)"}`,
      };
    } catch (e: any) {
      return {
        output: `PR 생성 중 오류: ${e?.message || e}`,
        success: false,
      };
    }
  }
}

// ============================================================
// Helpers
// ============================================================

/**
 * 매우 간단한 diff — 줄 단위로 +/- 표시. 진짜 LCS 안 쓰고
 * "old 에는 있고 new 에 없는 줄" / "new 에 있고 old 에 없는 줄" 만 표시.
 * webview 미리보기용 — 라이브러리 없이 빠르게.
 */
function makeSimpleDiff(oldContent: string, newContent: string): string {
  if (!oldContent) {
    return newContent
      .split("\n")
      .slice(0, 200)
      .map((l) => `+ ${l}`)
      .join("\n");
  }
  const oldLines = oldContent.split("\n");
  const newLines = newContent.split("\n");
  const oldSet = new Set(oldLines);
  const newSet = new Set(newLines);

  const out: string[] = [];
  const maxLen = Math.max(oldLines.length, newLines.length);
  for (let i = 0; i < maxLen && out.length < 400; i++) {
    const o = oldLines[i];
    const n = newLines[i];
    if (o === n) continue;
    if (o !== undefined && !newSet.has(o)) out.push(`- ${o}`);
    if (n !== undefined && !oldSet.has(n)) out.push(`+ ${n}`);
  }
  return out.join("\n") || "(content reorganized)";
}
