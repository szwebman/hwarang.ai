"use client";

import { useRef, useState, type KeyboardEvent } from "react";

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [input, setInput] = useState("");
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput("");

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  };

  const hasContent = input.trim().length > 0;

  return (
    <div
      className="flex items-end gap-3 rounded-2xl border px-4 py-3 transition-all duration-200"
      style={{
        borderColor: focused ? "var(--primary)" : "var(--border)",
        background: "var(--background)",
        boxShadow: focused ? `0 0 0 3px color-mix(in srgb, var(--primary) 15%, transparent)` : "var(--shadow-sm)",
      }}
    >
      {/* Attachment button */}
      <button
        className="p-1.5 rounded-lg hover:bg-[var(--muted)] transition-colors shrink-0 mb-0.5"
        style={{ color: "var(--muted-foreground)" }}
        title="Attach file"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
        </svg>
      </button>

      {/* Textarea */}
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder="메시지를 입력하세요..."
        disabled={disabled}
        rows={1}
        className="flex-1 resize-none bg-transparent outline-none text-sm leading-relaxed placeholder:text-[var(--muted-foreground)]"
        style={{ maxHeight: "200px" }}
      />

      {/* Send button */}
      <button
        onClick={handleSend}
        disabled={disabled || !hasContent}
        className="p-2 rounded-xl transition-all duration-200 disabled:opacity-30 disabled:scale-100 hover:scale-105 active:scale-95 shrink-0 mb-0.5"
        style={{
          background: hasContent ? "var(--primary)" : "var(--muted)",
          color: hasContent ? "var(--primary-foreground)" : "var(--muted-foreground)",
        }}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M5 12h14" />
          <path d="m12 5 7 7-7 7" />
        </svg>
      </button>
    </div>
  );
}
