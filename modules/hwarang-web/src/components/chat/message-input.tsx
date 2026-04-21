"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";

interface MessageInputProps {
  onSend: (message: string, files?: File[]) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function MessageInput({ onSend, disabled, placeholder }: MessageInputProps) {
  const [input, setInput] = useState("");
  const [focused, setFocused] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [isComposing, setIsComposing] = useState(false);
  const lastSendAtRef = useRef(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = () => {
    // IME 조합 중이면 전송 안 함 (한글 중복 전송 방지)
    if (isComposing) return;

    const trimmed = input.trim();
    if (!trimmed && attachedFiles.length === 0) return;
    if (disabled) return;

    // 짧은 시간 내 중복 전송 방지
    const now = Date.now();
    if (now - lastSendAtRef.current < 200) return;
    lastSendAtRef.current = now;

    onSend(trimmed, attachedFiles.length > 0 ? attachedFiles : undefined);
    setInput("");
    setAttachedFiles([]);

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      setAttachedFiles((prev) => [...prev, ...files]);
    }
  };

  const removeFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  // 응답 완료 시 (disabled가 false로 바뀌면) 자동 포커스
  useEffect(() => {
    if (!disabled) {
      setTimeout(() => textareaRef.current?.focus(), 100);
    }
  }, [disabled]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // IME 조합 중인 Enter 무시 (한글 입력 중복 방지)
    if (
      e.key === "Enter" &&
      !e.shiftKey &&
      !e.nativeEvent.isComposing &&
      !isComposing &&
      e.keyCode !== 229
    ) {
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

  const hasContent = input.trim().length > 0 || attachedFiles.length > 0;

  return (
    <div className="flex flex-col gap-2">
      {/* 첨부 파일 미리보기 */}
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 px-2">
          {attachedFiles.map((file, i) => (
            <div
              key={i}
              className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs"
              style={{ background: "var(--muted)", borderColor: "var(--border)" }}
            >
              <span className="max-w-[150px] truncate">{file.name}</span>
              <span style={{ color: "var(--muted-foreground)" }}>
                ({(file.size / 1024).toFixed(0)}KB)
              </span>
              <button
                onClick={() => removeFile(i)}
                className="ml-1 hover:text-red-500 transition-colors"
                style={{ color: "var(--muted-foreground)" }}
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        className="flex items-center gap-3 rounded-2xl border px-4 py-2 transition-all duration-200"
        style={{
          borderColor: focused ? "var(--primary)" : "var(--border)",
          background: "var(--background)",
          boxShadow: focused ? `0 0 0 3px color-mix(in srgb, var(--primary) 15%, transparent)` : "var(--shadow-sm)",
        }}
      >
        {/* 숨겨진 파일 input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,.pdf,.txt,.md,.py,.js,.ts,.json,.csv,.xlsx,.doc,.docx"
          onChange={handleFileChange}
          className="hidden"
        />

        {/* Attachment button */}
        <button
          onClick={handleFileSelect}
          disabled={disabled}
          className="p-1.5 rounded-lg hover:bg-[var(--muted)] transition-colors shrink-0 self-end disabled:opacity-30"
          style={{ color: "var(--muted-foreground)", marginBottom: "2px" }}
          title="파일 첨부"
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
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          placeholder={placeholder || "메시지를 입력하세요..."}
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none bg-transparent outline-none text-sm placeholder:text-[var(--muted-foreground)]"
          style={{
            maxHeight: "200px",
            lineHeight: "24px",
            padding: "6px 0",
            margin: 0,
            minHeight: "24px",
            display: "block",
            verticalAlign: "middle",
          }}
        />

      {/* Send button */}
      <button
        onClick={handleSend}
        disabled={disabled || !hasContent}
        className="p-2 rounded-xl transition-all duration-200 disabled:opacity-30 disabled:scale-100 hover:scale-105 active:scale-95 shrink-0 self-end"
        style={{
          background: hasContent ? "var(--primary)" : "var(--muted)",
          color: hasContent ? "var(--primary-foreground)" : "var(--muted-foreground)",
          marginBottom: "2px",
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
    </div>
  );
}
