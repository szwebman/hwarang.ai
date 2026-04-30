/**
 * Workspace Auto Context
 *
 * 첫 진입 / 새 대화 시 워크스페이스를 자동 분석하여
 * SYSTEM_PROMPT 에 prefix 할 컨텍스트 블록을 생성한다.
 *
 * 분석 대상:
 *   - 매니페스트 파일 (package.json / pyproject.toml / Cargo.toml / go.mod / pom.xml)
 *   - README (첫 30줄 요약)
 *   - 주요 디렉토리 (src/, app/, lib/, packages/, modules/) depth 2 트리
 *   - 빌드/린트/테스트 설정 (tsconfig, jest, eslint, prettier 등)
 *   - git branch + 최근 commit 5개
 *
 * 캐싱:
 *   - 5 분 TTL — 같은 워크스페이스에서 재호출 시 캐시 반환
 *   - 워크스페이스 폴더 변경 시 자동 무효화
 *
 * 토큰 예산:
 *   - 전체 출력 < 2000 토큰 (대략 8000자 기준)
 *   - README 는 첫 30줄만, 트리는 항목 수 제한
 */

import * as vscode from "vscode";
import * as fs from "fs/promises";
import * as path from "path";
import * as cp from "child_process";
import { loadHwarangMd, formatForPrompt, HwarangProjectMemory } from "./hwarang-md";

export interface WorkspaceContext {
  projectName: string;
  stack: string[]; // 예: ["Next.js 14", "Prisma 5", "TypeScript 5"]
  branch?: string;
  recentCommits: string[]; // oneline 5개
  structure: string[]; // 주요 디렉토리 트리 라인
  configs: string[]; // tsconfig.json, jest.config.js 등
  readmeSummary?: string; // 첫 30줄
  hwarangMemory?: HwarangProjectMemory; // HWARANG.md 파싱 결과
  hwarangPromptText?: string; // SYSTEM_PROMPT 에 prepend 할 메모리 블록
  raw: string; // SYSTEM_PROMPT 에 prefix 할 최종 문자열
}

interface CacheEntry {
  ctx: WorkspaceContext;
  ts: number;
  rootPath: string;
}

let cache: CacheEntry | null = null;
const CACHE_TTL_MS = 5 * 60 * 1000;
const MAX_RAW_LEN = 8000; // ~2000 tokens

const CONFIG_FILES = [
  "tsconfig.json",
  "jsconfig.json",
  "jest.config.js",
  "jest.config.ts",
  "vitest.config.ts",
  "vitest.config.js",
  ".eslintrc",
  ".eslintrc.js",
  ".eslintrc.json",
  ".eslintrc.cjs",
  "eslint.config.js",
  "eslint.config.mjs",
  ".prettierrc",
  ".prettierrc.json",
  ".prettierrc.js",
  "prettier.config.js",
  "babel.config.js",
  "babel.config.json",
  ".babelrc",
  "next.config.js",
  "next.config.mjs",
  "next.config.ts",
  "vite.config.js",
  "vite.config.ts",
  "webpack.config.js",
  "rollup.config.js",
  "tailwind.config.js",
  "tailwind.config.ts",
  "postcss.config.js",
  "Dockerfile",
  "docker-compose.yml",
  "docker-compose.yaml",
  "Makefile",
  ".env.example",
  "pytest.ini",
  "tox.ini",
  "ruff.toml",
  ".ruff.toml",
  "uv.toml",
  "poetry.lock",
];

const KEY_DIRS = ["src", "app", "lib", "packages", "modules", "components", "pages", "api", "server", "client", "core", "tests", "test", "spec"];

/**
 * 워크스페이스 컨텍스트 자동 감지. 캐시 사용.
 */
export async function detectWorkspaceContext(force = false): Promise<WorkspaceContext | null> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders?.length) return null;
  const root = folders[0].uri.fsPath;

  // 캐시 hit
  if (
    !force &&
    cache &&
    cache.rootPath === root &&
    Date.now() - cache.ts < CACHE_TTL_MS
  ) {
    return cache.ctx;
  }

  const ctx: WorkspaceContext = {
    projectName: folders[0].name,
    stack: [],
    recentCommits: [],
    structure: [],
    configs: [],
    raw: "",
  };

  // 1. 매니페스트 + 스택 감지
  await detectStack(root, ctx);

  // 2. README 첫 30줄
  ctx.readmeSummary = await readReadme(root);

  // 3. 설정 파일 감지
  ctx.configs = await detectConfigs(root);

  // 4. 주요 디렉토리 트리 (depth 2)
  ctx.structure = await buildStructure(root);

  // 5. git 정보
  await detectGit(root, ctx);

  // 6. HWARANG.md 프로젝트 메모리 (있으면 로드)
  try {
    ctx.hwarangMemory = await loadHwarangMd(root);
    ctx.hwarangPromptText = formatForPrompt(ctx.hwarangMemory);
  } catch {
    /* HWARANG.md 없거나 파싱 실패 — 무시 */
  }

  // 7. 최종 raw 문자열 합성
  ctx.raw = formatContext(ctx);

  cache = { ctx, ts: Date.now(), rootPath: root };
  return ctx;
}

/**
 * 캐시 무효화 — 새 대화 시작 시 호출.
 */
export function invalidateWorkspaceContextCache() {
  cache = null;
}

// ======== 내부 구현 ========

async function detectStack(root: string, ctx: WorkspaceContext) {
  // package.json (Node.js / TypeScript)
  try {
    const pkgRaw = await fs.readFile(path.join(root, "package.json"), "utf-8");
    const pkg = JSON.parse(pkgRaw);
    if (pkg.name) ctx.projectName = pkg.name;

    const deps: Record<string, string> = {
      ...(pkg.dependencies || {}),
      ...(pkg.devDependencies || {}),
    };

    // 주요 프레임워크 감지 (버전 포함)
    const frameworkMap: Record<string, string> = {
      next: "Next.js",
      react: "React",
      vue: "Vue",
      svelte: "Svelte",
      "@angular/core": "Angular",
      express: "Express",
      fastify: "Fastify",
      "@nestjs/core": "NestJS",
      prisma: "Prisma",
      "@prisma/client": "Prisma",
      typescript: "TypeScript",
      vite: "Vite",
      vitest: "Vitest",
      jest: "Jest",
      mocha: "Mocha",
      "@playwright/test": "Playwright",
      tailwindcss: "Tailwind",
      "drizzle-orm": "Drizzle",
      mongoose: "Mongoose",
      typeorm: "TypeORM",
      electron: "Electron",
      "react-native": "React Native",
    };

    for (const [name, label] of Object.entries(frameworkMap)) {
      if (deps[name]) {
        const v = String(deps[name]).replace(/^[\^~]/, "").split(".")[0];
        ctx.stack.push(v ? `${label} ${v}` : label);
      }
    }

    // 스크립트 힌트 (build/test 명령)
    if (pkg.scripts) {
      const scriptKeys = Object.keys(pkg.scripts).slice(0, 8);
      if (scriptKeys.length) {
        ctx.configs.push(`npm scripts: ${scriptKeys.join(", ")}`);
      }
    }
  } catch {
    /* package.json 없음 — 다음 매니페스트 시도 */
  }

  // pyproject.toml (Python)
  try {
    const py = await fs.readFile(path.join(root, "pyproject.toml"), "utf-8");
    ctx.stack.push("Python");
    // 간단 파싱 — 핵심 의존성만 추출
    if (/fastapi/i.test(py)) ctx.stack.push("FastAPI");
    if (/django/i.test(py)) ctx.stack.push("Django");
    if (/flask/i.test(py)) ctx.stack.push("Flask");
    if (/torch/i.test(py)) ctx.stack.push("PyTorch");
    if (/transformers/i.test(py)) ctx.stack.push("Transformers");
    if (/pydantic/i.test(py)) ctx.stack.push("Pydantic");
    const nameMatch = py.match(/^\s*name\s*=\s*["']([^"']+)["']/m);
    if (nameMatch && !ctx.projectName) ctx.projectName = nameMatch[1];
  } catch { /* skip */ }

  try {
    await fs.access(path.join(root, "requirements.txt"));
    if (!ctx.stack.includes("Python")) ctx.stack.push("Python");
  } catch { /* skip */ }

  // Cargo.toml (Rust)
  try {
    const cargo = await fs.readFile(path.join(root, "Cargo.toml"), "utf-8");
    ctx.stack.push("Rust");
    const nameMatch = cargo.match(/^\s*name\s*=\s*"([^"]+)"/m);
    if (nameMatch && !ctx.projectName) ctx.projectName = nameMatch[1];
  } catch { /* skip */ }

  // go.mod (Go)
  try {
    const gomod = await fs.readFile(path.join(root, "go.mod"), "utf-8");
    ctx.stack.push("Go");
    const moduleMatch = gomod.match(/^module\s+(\S+)/m);
    if (moduleMatch && !ctx.projectName) {
      ctx.projectName = moduleMatch[1].split("/").pop() || moduleMatch[1];
    }
  } catch { /* skip */ }

  // pom.xml / build.gradle (Java)
  try {
    await fs.access(path.join(root, "pom.xml"));
    ctx.stack.push("Java (Maven)");
  } catch {
    try {
      await fs.access(path.join(root, "build.gradle"));
      ctx.stack.push("Java (Gradle)");
    } catch { /* skip */ }
  }
}

async function readReadme(root: string): Promise<string | undefined> {
  const candidates = ["README.md", "README.MD", "Readme.md", "readme.md", "README.rst", "README.txt", "README"];
  for (const name of candidates) {
    try {
      const content = await fs.readFile(path.join(root, name), "utf-8");
      const lines = content.split("\n").slice(0, 30);
      // 빈 줄과 마크다운 노이즈 줄임
      const trimmed = lines
        .map((l) => l.trim())
        .filter((l) => l.length > 0)
        .slice(0, 20)
        .join("\n");
      return trimmed.slice(0, 1500);
    } catch { /* try next */ }
  }
  return undefined;
}

async function detectConfigs(root: string): Promise<string[]> {
  const out: string[] = [];
  for (const cf of CONFIG_FILES) {
    try {
      await fs.access(path.join(root, cf));
      out.push(cf);
    } catch { /* skip */ }
  }
  return out;
}

async function buildStructure(root: string): Promise<string[]> {
  const lines: string[] = [];
  let entries: string[] = [];
  try {
    entries = await fs.readdir(root);
  } catch {
    return lines;
  }

  // 최상위 — 주요 디렉토리만 표시
  const dirs: string[] = [];
  for (const name of entries) {
    if (name.startsWith(".") || name === "node_modules" || name === "dist" || name === "build" || name === "__pycache__" || name === "target" || name === "venv" || name === ".venv") continue;
    try {
      const stat = await fs.stat(path.join(root, name));
      if (stat.isDirectory()) dirs.push(name);
    } catch { /* skip */ }
  }

  // 우선순위 정렬: KEY_DIRS 먼저
  dirs.sort((a, b) => {
    const ai = KEY_DIRS.indexOf(a);
    const bi = KEY_DIRS.indexOf(b);
    if (ai >= 0 && bi >= 0) return ai - bi;
    if (ai >= 0) return -1;
    if (bi >= 0) return 1;
    return a.localeCompare(b);
  });

  // 최대 12개 디렉토리만
  const topDirs = dirs.slice(0, 12);
  for (const d of topDirs) {
    lines.push(`  ${d}/`);
    // depth 2 — 각 주요 디렉토리의 직계 자식 (최대 8개)
    if (KEY_DIRS.includes(d) || lines.length < 30) {
      try {
        const sub = await fs.readdir(path.join(root, d));
        const filtered = sub
          .filter((n) => !n.startsWith(".") && n !== "node_modules" && n !== "__pycache__")
          .slice(0, 8);
        for (const s of filtered) {
          try {
            const ss = await fs.stat(path.join(root, d, s));
            lines.push(`    ${s}${ss.isDirectory() ? "/" : ""}`);
          } catch { /* skip */ }
        }
      } catch { /* skip */ }
    }
    if (lines.length >= 60) break;
  }

  return lines;
}

async function detectGit(root: string, ctx: WorkspaceContext) {
  const exec = (cmd: string, timeout = 3000) =>
    new Promise<string>((resolve) => {
      cp.exec(cmd, { cwd: root, timeout, windowsHide: true }, (err, stdout) => {
        resolve(err ? "" : (stdout || "").trim());
      });
    });

  // .git 존재 확인
  try {
    await fs.access(path.join(root, ".git"));
  } catch {
    return;
  }

  const branch = await exec("git branch --show-current");
  if (branch) ctx.branch = branch;

  const log = await exec("git log --oneline -5 --no-color");
  if (log) {
    ctx.recentCommits = log.split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 5);
  }
}

function formatContext(ctx: WorkspaceContext): string {
  const lines: string[] = [];
  lines.push("[Workspace Context]");
  lines.push(`- Project: ${ctx.projectName}`);

  if (ctx.stack.length) {
    lines.push(`- Stack: ${ctx.stack.slice(0, 8).join(" + ")}`);
  }

  if (ctx.branch) {
    const lastCommit = ctx.recentCommits[0] || "";
    lines.push(`- Branch: ${ctx.branch}${lastCommit ? ` (last: ${lastCommit})` : ""}`);
  }

  if (ctx.recentCommits.length > 1) {
    lines.push(`- Recent commits:`);
    for (const c of ctx.recentCommits.slice(0, 5)) {
      lines.push(`    ${c}`);
    }
  }

  if (ctx.structure.length) {
    lines.push(`- Structure:`);
    lines.push(...ctx.structure);
  }

  if (ctx.configs.length) {
    // 토큰 절약 — 한 줄로
    lines.push(`- Configs: ${ctx.configs.slice(0, 12).join(", ")}`);
  }

  if (ctx.readmeSummary) {
    lines.push(`- README excerpt:`);
    for (const l of ctx.readmeSummary.split("\n").slice(0, 15)) {
      lines.push(`    ${l}`);
    }
  }

  // HWARANG.md 메모리 (가장 중요한 사용자 지정 컨텍스트 — 마지막에 강조)
  if (ctx.hwarangPromptText) {
    lines.push("");
    lines.push(ctx.hwarangPromptText);
  }

  let raw = lines.join("\n");
  if (raw.length > MAX_RAW_LEN) {
    raw = raw.slice(0, MAX_RAW_LEN) + "\n... (truncated)";
  }
  return raw;
}
