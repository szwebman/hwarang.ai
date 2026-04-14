"use client";

import type { Message } from "@/types/chat";
import { MarkdownRenderer } from "./markdown-renderer";

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

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
        className={`max-w-[80%] rounded-2xl px-4 py-3 shadow-sm ${
          isUser ? "rounded-br-lg" : "rounded-bl-lg"
        }`}
        style={{
          background: isUser ? "var(--message-user-bg)" : "var(--message-assistant-bg)",
          color: isUser ? "var(--message-user-fg)" : "var(--message-assistant-fg)",
        }}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
        ) : (
          <div className="text-sm prose prose-sm dark:prose-invert max-w-none">
            <MarkdownRenderer content={message.content} />
          </div>
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
