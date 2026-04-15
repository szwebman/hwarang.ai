"use client";

import { useState } from "react";

interface CodeBlockProps {
  language: string;
  code: string;
}

export function CodeBlock({ language, code }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const lineCount = code.split("\n").length;

  return (
    <div
      className="relative group my-4 rounded-xl overflow-hidden border"
      style={{ borderColor: "var(--border)", boxShadow: "var(--shadow-sm)" }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2"
        style={{ background: "var(--muted)", borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2">
          {/* Language icon dot */}
          <span
            className="w-2.5 h-2.5 rounded-full"
            style={{ background: "var(--primary)", opacity: 0.7 }}
          />
          <span className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
            {language}
          </span>
          <span className="text-[10px]" style={{ color: "var(--muted-foreground)", opacity: 0.5 }}>
            {lineCount}줄
          </span>
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg opacity-0 group-hover:opacity-100 transition-all duration-200 hover:bg-[var(--border)]"
          style={{ color: "var(--muted-foreground)" }}
        >
          {copied ? (
            <>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <span style={{ color: "var(--success)" }}>복사됨!</span>
            </>
          ) : (
            <>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              복사
            </>
          )}
        </button>
      </div>

      {/* Code */}
      <pre className="!m-0 !rounded-none !border-0 overflow-x-auto p-4 text-[13px] leading-6">
        <code>{code}</code>
      </pre>
    </div>
  );
}
