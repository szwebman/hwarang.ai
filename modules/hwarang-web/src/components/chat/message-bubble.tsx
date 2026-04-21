"use client";

import type { Message } from "@/types/chat";
import { MarkdownRenderer } from "./markdown-renderer";
import { CodePreview, extractHtmlBlocks } from "./code-preview";
import { useMemo } from "react";

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  // HTML 코드 블록 감지 (어시스턴트 메시지만)
  const { text, htmlBlocks } = useMemo(() => {
    if (isUser) return { text: message.content, htmlBlocks: [] };
    return extractHtmlBlocks(message.content);
  }, [message.content, isUser]);

  return (
    <div className={`flex gap-3 py-4 ${isUser ? "justify-end" : ""}`}>
      {/* Assistant avatar */}
      {!isUser && (
        <div className="w-8 h-8 rounded-xl gradient-bg flex items-center justify-center text-xs font-bold text-white shrink-0 shadow-sm">
          H
        </div>
      )}

      {/* Message content */}
      <div
        className={`rounded-2xl px-4 py-3 shadow-sm ${
          isUser ? "max-w-[80%] rounded-br-lg" : "max-w-[85%] rounded-bl-lg"
        }`}
        style={{
          background: isUser ? "var(--message-user-bg)" : "var(--message-assistant-bg)",
          color: isUser ? "var(--message-user-fg)" : "var(--message-assistant-fg)",
        }}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
        ) : (
          <>
            <div className="text-sm prose prose-sm dark:prose-invert max-w-none">
              <MarkdownRenderer content={text} />
            </div>

            {/* HTML 코드 미리보기 (Artifacts 스타일) */}
            {htmlBlocks.map((html, i) => (
              <CodePreview key={i} code={html} language="HTML" />
            ))}
          </>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div
          className="w-8 h-8 rounded-xl flex items-center justify-center text-xs font-bold shrink-0 shadow-sm"
          style={{ background: "var(--accent)", color: "var(--accent-foreground)" }}
        >
          U
        </div>
      )}
    </div>
  );
}
