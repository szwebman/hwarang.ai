"use client";

import { useState, useRef, useEffect } from "react";

interface CodePreviewProps {
  code: string;
  language?: string;
}

/**
 * 코드 미리보기 (클로드 Artifacts 스타일)
 *
 * HTML 코드를 iframe으로 실시간 렌더링.
 * 코드 보기 / 미리보기 탭 전환 가능.
 */
export function CodePreview({ code, language }: CodePreviewProps) {
  const [tab, setTab] = useState<"preview" | "code">("preview");
  const [copied, setCopied] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // iframe에 코드 주입
  useEffect(() => {
    if (tab === "preview" && iframeRef.current) {
      const doc = iframeRef.current.contentDocument;
      if (doc) {
        doc.open();
        doc.write(code);
        doc.close();
      }
    }
  }, [tab, code]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className="rounded-xl overflow-hidden border mt-3 mb-1"
      style={{ borderColor: "var(--border)", background: "var(--background)" }}
    >
      {/* 탭 헤더 */}
      <div
        className="flex items-center justify-between px-3 py-2 border-b"
        style={{ borderColor: "var(--border)", background: "var(--muted)" }}
      >
        <div className="flex gap-1">
          <button
            onClick={() => setTab("preview")}
            className="px-3 py-1 rounded-md text-xs font-medium transition-colors"
            style={{
              background: tab === "preview" ? "var(--background)" : "transparent",
              color: tab === "preview" ? "var(--foreground)" : "var(--muted-foreground)",
              boxShadow: tab === "preview" ? "var(--shadow-sm)" : "none",
            }}
          >
            미리보기
          </button>
          <button
            onClick={() => setTab("code")}
            className="px-3 py-1 rounded-md text-xs font-medium transition-colors"
            style={{
              background: tab === "code" ? "var(--background)" : "transparent",
              color: tab === "code" ? "var(--foreground)" : "var(--muted-foreground)",
              boxShadow: tab === "code" ? "var(--shadow-sm)" : "none",
            }}
          >
            코드
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            {language || "HTML"}
          </span>
          <button
            onClick={handleCopy}
            className="px-2 py-1 rounded text-xs transition-colors hover:bg-[var(--background)]"
            style={{ color: "var(--muted-foreground)" }}
          >
            {copied ? "복사됨!" : "복사"}
          </button>
          <a
            href={`data:text/html;charset=utf-8,${encodeURIComponent(code)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="px-2 py-1 rounded text-xs transition-colors hover:bg-[var(--background)]"
            style={{ color: "var(--muted-foreground)", textDecoration: "none" }}
            title="새 탭에서 열기"
          >
            ↗
          </a>
        </div>
      </div>

      {/* 콘텐츠 */}
      {tab === "preview" ? (
        <div className="relative" style={{ height: "400px", background: "#fff" }}>
          <iframe
            ref={iframeRef}
            sandbox="allow-scripts allow-same-origin"
            className="w-full h-full border-0"
            title="코드 미리보기"
          />
        </div>
      ) : (
        <div className="overflow-auto" style={{ maxHeight: "400px" }}>
          <pre
            className="p-4 text-xs leading-relaxed overflow-x-auto"
            style={{ background: "var(--muted)", color: "var(--foreground)", margin: 0 }}
          >
            <code>{code}</code>
          </pre>
        </div>
      )}
    </div>
  );
}

/**
 * 메시지 텍스트에서 HTML 코드 블록을 감지.
 * ```html ... ``` 패턴을 찾아 CodePreview로 교체.
 */
export function extractHtmlBlocks(content: string): { text: string; htmlBlocks: string[] } {
  const htmlBlocks: string[] = [];
  const pattern = /```html\s*\n([\s\S]*?)```/g;

  let match;
  while ((match = pattern.exec(content)) !== null) {
    htmlBlocks.push(match[1].trim());
  }

  // HTML 블록을 제거한 텍스트
  const text = content.replace(pattern, "\n[코드 미리보기는 아래에 표시됩니다]\n");

  return { text, htmlBlocks };
}
