/**
 * 실행 모드 관리
 *
 * - auto:   파일 변경/명령 실행 자동 (확인 없음)
 * - manual: 파일 변경/명령 실행 전 승인 (기본)
 * - plan:   실제 파일 변경 없이 계획만 출력
 */

import * as vscode from "vscode";

export type HwarangMode = "auto" | "manual" | "plan";

export function getMode(): HwarangMode {
  const config = vscode.workspace.getConfiguration("hwarang");
  const mode = config.get<string>("mode", "manual");

  // 레거시 호환: autoApplyEdits가 true면 auto 모드로
  const legacyAutoApply = config.get<boolean>("autoApplyEdits", false);
  if (legacyAutoApply && mode === "manual") return "auto";

  if (mode === "auto" || mode === "manual" || mode === "plan") return mode;
  return "manual";
}

export async function setMode(mode: HwarangMode): Promise<void> {
  const config = vscode.workspace.getConfiguration("hwarang");
  await config.update("mode", mode, vscode.ConfigurationTarget.Global);
}

export function getModeLabel(mode: HwarangMode): string {
  switch (mode) {
    case "auto": return "🚀 자동 모드";
    case "manual": return "✋ 수동 모드";
    case "plan": return "📋 플랜 모드";
  }
}

export function getModeDescription(mode: HwarangMode): string {
  switch (mode) {
    case "auto": return "파일 변경과 명령을 확인 없이 실행";
    case "manual": return "매 변경마다 승인 받음 (안전)";
    case "plan": return "실제 변경 없이 계획만 출력 (읽기 전용)";
  }
}

export function getSystemPromptAddition(mode: HwarangMode): string {
  switch (mode) {
    case "auto":
      return "\n\n[실행 모드: 자동] 사용자는 모든 변경을 자동 승인했습니다. 작업을 효율적으로 진행하세요.";
    case "manual":
      return "\n\n[실행 모드: 수동] 사용자가 각 변경을 직접 승인합니다. 명확한 설명과 함께 진행하세요.";
    case "plan":
      return "\n\n[실행 모드: 플랜] 실제 파일 변경이나 명령 실행 없이 **계획만 수립**합니다. write_file/edit_file/delete_file/run_command 도구는 호출하지 마세요. 대신 실행할 작업의 **목록과 순서, 각 파일의 예상 내용 요약**을 마크다운으로 출력하세요. 사용자가 플랜을 보고 승인하면 자동/수동 모드로 전환해서 실행할 것입니다.";
  }
}

/** 쓰기 작업(write/edit/delete/run) 허용 여부 */
export function isWriteAllowed(mode: HwarangMode): boolean {
  return mode !== "plan";
}

/** 자동 승인 여부 */
export function isAutoApprove(mode: HwarangMode): boolean {
  return mode === "auto";
}
