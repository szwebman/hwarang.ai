/**
 * Safety Layer — run_command / delete_file 검증.
 *
 * 분류:
 *   1. DANGEROUS_PATTERNS — 즉시 차단 (사용자에게도 노출 안 함)
 *   2. REQUIRES_CONFIRMATION — 명시 승인 필요 (수동/자동 모드 무관 모달)
 *
 * 추가:
 *   - delete_file 의 path traversal / .git 보호 검증
 *   - 큰 디렉토리 (node_modules) 경고
 */

import * as path from "path";
import * as vscode from "vscode";

/**
 * 즉시 거부할 명령 패턴.
 * 어떤 모드에서도 실행 안 됨.
 */
export const DANGEROUS_PATTERNS: RegExp[] = [
  /\brm\s+-rf\s+\/(?!\w)/,                              // rm -rf / (root 파괴)
  /\brm\s+-rf\s+~\b/,                                   // rm -rf ~ (홈 파괴)
  /\bsudo\s+rm\b/,                                       // sudo rm
  /\bdd\s+if=.*of=\/dev\//,                              // dd to /dev (디스크 파괴)
  /\bmkfs\b/,                                             // 파일시스템 포맷
  /\b:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:/,          // fork bomb
  /\b>\s*\/dev\/sd[a-z]/,                                // 디스크 직접 쓰기
  /\bchmod\s+-R\s+777\s+\//,                             // 권한 망가뜨림 (root 부터)
  /\bcurl[^|]*\|\s*(sudo\s+)?(bash|sh|zsh)\b/,           // curl | sh (검증 안 된 스크립트)
];

/**
 * 명시 승인 필요한 명령 패턴.
 * auto 모드라도 모달 띄워야 함.
 */
export const REQUIRES_CONFIRMATION: RegExp[] = [
  /\bgit\s+push\b/,
  /\bgit\s+reset\s+--hard\b/,
  /\bnpm\s+publish\b/,
  /\bcargo\s+publish\b/,
  /\bdocker\b.*--privileged\b/,
  /\bDROP\s+(TABLE|DATABASE)\b/i,
  /\bTRUNCATE\b/i,
  /\bdelete\s+from\s+\w+\s+where\s+1\s*=\s*1\b/i,
];

/**
 * 추가 차단: main / master / production 브랜치에 force push.
 */
export const FORCE_PUSH_MAIN = /\bgit\s+push\b.*--force\b.*\b(main|master|production)\b/;

export interface SafetyCheck {
  blocked: boolean;
  reason?: string;
}

/**
 * 명령이 즉시 차단 대상인지 검사.
 */
export function checkDangerous(command: string): SafetyCheck {
  if (FORCE_PUSH_MAIN.test(command)) {
    return {
      blocked: true,
      reason: "보호된 브랜치(main/master/production)에 force push 는 차단됩니다.",
    };
  }
  for (const pat of DANGEROUS_PATTERNS) {
    if (pat.test(command)) {
      return {
        blocked: true,
        reason: `위험 명령 패턴 감지: ${pat.source}`,
      };
    }
  }
  return { blocked: false };
}

/**
 * 명시 승인 필요 여부.
 * 매치 시 사용자에게 별도 모달로 한 번 더 확인 받아야 함.
 */
export function requiresConfirmation(command: string): RegExp | null {
  for (const pat of REQUIRES_CONFIRMATION) {
    if (pat.test(command)) return pat;
  }
  return null;
}

/**
 * delete_file 검증.
 * - 워크스페이스 밖 절대 경로 차단 (path traversal)
 * - .git/ 내부 파일 차단
 * - node_modules / dist 등 큰 디렉토리는 경고 메시지
 */
export interface DeleteCheck {
  blocked: boolean;
  reason?: string;
  warnLargeDir?: boolean;
}

export function checkDelete(absPath: string, workspaceRoot: string): DeleteCheck {
  const normalized = path.resolve(absPath);
  const rootNormalized = path.resolve(workspaceRoot);

  // path traversal: 워크스페이스 밖
  if (
    normalized !== rootNormalized &&
    !normalized.startsWith(rootNormalized + path.sep)
  ) {
    return {
      blocked: true,
      reason: "워크스페이스 외부 경로 삭제는 차단됩니다 (path traversal 보호).",
    };
  }

  // .git 보호
  const rel = path.relative(rootNormalized, normalized);
  if (rel === ".git" || rel.startsWith(".git" + path.sep) || rel.includes(path.sep + ".git" + path.sep)) {
    return {
      blocked: true,
      reason: ".git 디렉토리 내부 파일은 삭제할 수 없습니다 (저장소 보호).",
    };
  }

  // 큰 디렉토리 경고 (차단은 아님)
  const baseName = path.basename(normalized);
  const heavyDirs = ["node_modules", "dist", "build", "target", ".next", ".turbo", "__pycache__"];
  if (heavyDirs.includes(baseName)) {
    return { blocked: false, warnLargeDir: true };
  }

  return { blocked: false };
}

/**
 * 사용자에게 명시 승인 모달을 띄움. true 반환 시 진행.
 */
export async function confirmDangerous(message: string, detail?: string): Promise<boolean> {
  const r = await vscode.window.showWarningMessage(
    message,
    { modal: true, detail },
    "실행"
  );
  return r === "실행";
}
