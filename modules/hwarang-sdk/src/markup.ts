import type {
  MarkupSection,
  MarkupPlanItem,
  MarkupDiff,
  MarkupSuggestion,
} from "./types";

/**
 * HP markup parser — 서버측 markup.py 와 동일 로직.
 *
 * 인식하는 섹션:
 *   @@plan          → 번호 매긴 항목 + [status]
 *   @@diff <path>   → unified diff (+/- 라인 카운트)
 *   @@suggestion: <level>  → 제안
 *   @@warning       → 경고
 *   @@error         → 에러
 *   @@summary       → 한 줄 요약
 *
 * 형식:
 *   @@<name>[: <arg>]\n
 *   <body>\n
 *   @@end
 */

const SECTION_RE = /@@(\w[\w-]*)(?::\s*([^\n]*))?\n([\s\S]*?)\n@@end/g;
const PLAN_LINE_RE = /^\s*(\d+)\.\s*(.+?)(?:\s*\[(\w+)\])?\s*$/;

export function parseMarkup(content: string): MarkupSection {
  const result: MarkupSection = {
    plan: [],
    diffs: [],
    suggestions: [],
    warnings: [],
    errors: [],
  };

  if (!content) return result;

  // matchAll 은 stateful 한 글로벌 regex 가 필요하므로 새 RegExp 인스턴스 사용
  const re = new RegExp(SECTION_RE.source, "g");

  for (const m of content.matchAll(re)) {
    const name = (m[1] || "").toLowerCase();
    const arg = (m[2] || "").trim();
    const body = (m[3] || "").trim();

    switch (name) {
      case "plan":
        result.plan.push(...parsePlan(body));
        break;
      case "diff":
        result.diffs.push(parseDiff(arg, body));
        break;
      case "suggestion":
        result.suggestions.push(parseSuggestion(arg, body));
        break;
      case "warning":
        result.warnings.push({ text: body });
        break;
      case "error":
        result.errors.push({ text: body });
        break;
      case "summary":
        result.summary = body;
        break;
      default:
        // 알 수 없는 섹션은 무시 (forward-compat)
        break;
    }
  }

  return result;
}

function parsePlan(body: string): MarkupPlanItem[] {
  const items: MarkupPlanItem[] = [];
  for (const line of body.split("\n")) {
    const lm = line.match(PLAN_LINE_RE);
    if (lm) {
      items.push({
        id: lm[1],
        title: lm[2].trim(),
        status: (lm[3] || "pending").toLowerCase(),
      });
    }
  }
  return items;
}

function parseDiff(arg: string, body: string): MarkupDiff {
  const lines = body.split("\n");
  let added = 0;
  let removed = 0;
  for (const line of lines) {
    if (line.startsWith("+") && !line.startsWith("+++")) added++;
    else if (line.startsWith("-") && !line.startsWith("---")) removed++;
  }
  return {
    path: arg || "(unknown)",
    added,
    removed,
    raw: body,
  };
}

function parseSuggestion(arg: string, body: string): MarkupSuggestion {
  // arg 예: "medium-risk" → level = "medium"
  const level = arg ? arg.split("-")[0] : "info";
  return { level: level || "info", text: body };
}
