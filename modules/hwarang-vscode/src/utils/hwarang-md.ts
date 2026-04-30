// HWARANG.md 프로젝트 메모리 파서/관리자
// 워크스페이스 root 의 HWARANG.md 를 자동으로 로드해 시스템 프롬프트에 prepend 한다.

import * as fs from "fs/promises";
import * as path from "path";

export interface HwarangProjectMemory {
  exists: boolean;
  raw?: string;
  conventions: string[];      // ## Conventions 섹션
  prohibitions: string[];     // ## Prohibitions 섹션
  notes: string[];            // ## Notes 섹션
  techStack?: string;         // ## Tech Stack
  tone?: string;              // ## Tone
  customSections: Record<string, string>;
}

/**
 * 워크스페이스 root 에서 HWARANG.md (또는 변형) 을 찾아 파싱한다.
 * 파일이 없으면 exists=false 를 반환한다.
 */
export async function loadHwarangMd(workspaceRoot: string): Promise<HwarangProjectMemory> {
  const candidates = [
    "HWARANG.md",
    "hwarang.md",
    ".hwarang/PROJECT.md",
    ".hwarang/CONVENTIONS.md",
  ];

  for (const c of candidates) {
    const fullPath = path.join(workspaceRoot, c);
    try {
      const raw = await fs.readFile(fullPath, "utf-8");
      return parseHwarangMd(raw);
    } catch {
      continue;
    }
  }

  return {
    exists: false,
    conventions: [],
    prohibitions: [],
    notes: [],
    customSections: {},
  };
}

/**
 * markdown 본문을 ## 섹션 단위로 분리하고, 각 섹션 제목을 한국어/영어 키워드로 매칭해
 * 5종 표준 섹션 (Conventions/Prohibitions/Notes/TechStack/Tone) 또는 customSections 로 분류한다.
 */
function parseHwarangMd(raw: string): HwarangProjectMemory {
  // ## Section Title 으로 분리
  const sections = raw.split(/^##\s+/m);
  const result: HwarangProjectMemory = {
    exists: true,
    raw,
    conventions: [],
    prohibitions: [],
    notes: [],
    customSections: {},
  };

  for (const sec of sections.slice(1)) {
    const [titleLine, ...bodyLines] = sec.split("\n");
    const title = titleLine.trim().toLowerCase();
    const body = bodyLines.join("\n").trim();

    // bullet list 추출
    const bullets = body
      .split("\n")
      .filter((l) => l.match(/^[-*]\s+/))
      .map((l) => l.replace(/^[-*]\s+/, ""));

    if (/(convention|규칙|컨벤션)/.test(title)) {
      result.conventions.push(...bullets);
    } else if (/(prohibit|금지|absolute)/.test(title)) {
      result.prohibitions.push(...bullets);
    } else if (/(note|memo|기억|메모)/.test(title)) {
      result.notes.push(...bullets);
    } else if (/(tech\s*stack|stack|기술)/.test(title)) {
      result.techStack = body.slice(0, 500);
    } else if (/(tone|어조|말투)/.test(title)) {
      result.tone = body.slice(0, 200);
    } else {
      result.customSections[titleLine.trim()] = body.slice(0, 500);
    }
  }

  return result;
}

/**
 * 파싱된 메모리를 LLM 시스템 프롬프트에 prepend 할 수 있는 한국어 텍스트로 변환한다.
 * 메모리가 없으면 빈 문자열을 반환한다.
 */
export function formatForPrompt(memory: HwarangProjectMemory): string {
  if (!memory.exists) return "";

  const parts: string[] = ["[HWARANG.md — 프로젝트 메모리]"];

  if (memory.conventions.length > 0) {
    parts.push("\n[코딩 컨벤션]");
    parts.push(...memory.conventions.slice(0, 20).map((c) => `- ${c}`));
  }
  if (memory.prohibitions.length > 0) {
    parts.push("\n[절대 금지 — 위반 시 작업 거부]");
    parts.push(...memory.prohibitions.slice(0, 15).map((p) => `- ${p}`));
  }
  if (memory.notes.length > 0) {
    parts.push("\n[프로젝트 메모]");
    parts.push(...memory.notes.slice(0, 15).map((n) => `- ${n}`));
  }
  if (memory.techStack) {
    parts.push("\n[기술 스택]");
    parts.push(memory.techStack);
  }
  if (memory.tone) {
    parts.push("\n[화랑 응대 톤]");
    parts.push(memory.tone);
  }

  return parts.join("\n");
}

/**
 * HWARANG.md 가 없으면 템플릿을 생성한다 (vscode 명령에서 호출 예정).
 * 반환값은 생성된 파일의 절대 경로.
 */
export async function createHwarangMdTemplate(workspaceRoot: string): Promise<string> {
  const fullPath = path.join(workspaceRoot, "HWARANG.md");
  const template = `# 화랑 AI 프로젝트 메모리

이 파일은 화랑 AI 가 이 프로젝트에서 항상 참조하는 메모리입니다.
편집해서 화랑이 영구적으로 기억할 사항을 적으세요.

## Conventions
- 변수명은 camelCase
- 함수는 화살표 함수보다 function 키워드 선호
- 모든 export 함수에 JSDoc 주석

## Prohibitions
- console.log 프로덕션 코드에 남기지 말 것
- any 타입 사용 금지 (unknown 사용)
- node_modules 안 파일 직접 수정 금지

## Notes
- 결제 시스템은 Stripe 사용
- DB 는 Postgres + Prisma
- 한국어 메시지는 모두 ko-KR namespace

## Tech Stack
Next.js 14 App Router + TypeScript 5 + Tailwind CSS + Prisma 5 + PostgreSQL

## Tone
사용자에게 정중한 한국어 (~습니다 체). 짧고 명확하게.
`;

  await fs.writeFile(fullPath, template, "utf-8");
  return fullPath;
}

/**
 * 통합 가이드:
 *
 * workspace-context.ts 에서 다음을 추가하세요:
 *
 *   import { loadHwarangMd, formatForPrompt } from "./hwarang-md";
 *
 *   // detectWorkspaceContext() 안에서:
 *   const hwarangMemory = await loadHwarangMd(workspaceRoot);
 *   const hwarangPromptText = formatForPrompt(hwarangMemory);
 *
 *   // 결과 객체에 추가:
 *   return {
 *     // ... 기존 필드 ...
 *     hwarangMemory,
 *     hwarangPromptText,
 *   };
 *
 * 그리고 system prompt 조립 시 hwarangPromptText 가 비어있지 않으면
 * 시스템 프롬프트의 가장 앞에 prepend 하세요.
 */
