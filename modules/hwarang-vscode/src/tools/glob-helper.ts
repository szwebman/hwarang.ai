/**
 * Simple glob helper using VS Code's built-in file finder.
 */

import * as vscode from "vscode";

export async function glob(pattern: string, maxResults = 50): Promise<string[]> {
  const uris = await vscode.workspace.findFiles(pattern, "**/node_modules/**", maxResults);
  return uris.map((u) => vscode.workspace.asRelativePath(u));
}
