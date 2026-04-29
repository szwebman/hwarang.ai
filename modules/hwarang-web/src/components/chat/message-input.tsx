"use client";

import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent } from "react";
import type { AttachedImage } from "@/types/chat";
import { OptionBar } from "./option-bar";

interface MessageInputProps {
  onSend: (message: string, files?: File[], images?: AttachedImage[]) => void;
  disabled?: boolean;
  placeholder?: string;
  selectedModel?: string;
  setSelectedModel?: (m: string) => void;
  safetyMode?: string;
  setSafetyMode?: (m: string) => void;
}

const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024; // 10MB per image

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function MessageInput({
  onSend,
  disabled,
  placeholder,
  selectedModel,
  setSelectedModel,
  safetyMode,
  setSafetyMode,
}: MessageInputProps) {
  const [input, setInput] = useState("");
  const [focused, setFocused] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([]);
  const [isComposing, setIsComposing] = useState(false);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const lastSendAtRef = useRef(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  // 컴포넌트 unmount 시 ObjectURL 해제 (메모리 누수 방지)
  useEffect(() => {
    return () => {
      attachedImages.forEach((img) => {
        if (img.preview) URL.revokeObjectURL(img.preview);
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addImagesFromFiles = async (files: File[]) => {
    const imageFiles = files.filter(
      (f) => f.type.startsWith("image/") && f.size <= MAX_IMAGE_BYTES
    );
    if (imageFiles.length === 0) return;

    // 한도 초과 시 잘라냄
    const remainingSlots = Math.max(0, MAX_IMAGES - attachedImages.length);
    const accepted = imageFiles.slice(0, remainingSlots);

    const newImages = await Promise.all(
      accepted.map(async (f) => ({
        base64: await fileToBase64(f),
        preview: URL.createObjectURL(f),
        type: f.type,
        name: f.name,
      } as AttachedImage))
    );
    setAttachedImages((prev) => [...prev, ...newImages]);
  };

  const handleSend = () => {
    if (isComposing) return;

    const trimmed = input.trim();
    if (!trimmed && attachedFiles.length === 0 && attachedImages.length === 0) return;
    if (disabled) return;

    const now = Date.now();
    if (now - lastSendAtRef.current < 200) return;
    lastSendAtRef.current = now;

    onSend(
      trimmed,
      attachedFiles.length > 0 ? attachedFiles : undefined,
      attachedImages.length > 0 ? attachedImages : undefined,
    );
    setInput("");
    setAttachedFiles([]);
    // 미리보기 ObjectURL 정리 후 비우기
    attachedImages.forEach((img) => {
      if (img.preview) URL.revokeObjectURL(img.preview);
    });
    setAttachedImages([]);

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (imageInputRef.current) imageInputRef.current.value = "";

    setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleImageSelect = () => {
    imageInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      setAttachedFiles((prev) => [...prev, ...files]);
    }
  };

  const handleImageChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      await addImagesFromFiles(files);
    }
    // 같은 파일 재선택을 위해 value 초기화
    if (imageInputRef.current) imageInputRef.current.value = "";
  };

  const removeFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const removeImage = (index: number) => {
    setAttachedImages((prev) => {
      const target = prev[index];
      if (target?.preview) URL.revokeObjectURL(target.preview);
      return prev.filter((_, i) => i !== index);
    });
  };

  // 클립보드 붙여넣기 — 이미지 자동 첨부
  const handlePaste = async (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const imageFiles: File[] = [];
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      if (it.kind === "file" && it.type.startsWith("image/")) {
        const f = it.getAsFile();
        if (f) imageFiles.push(f);
      }
    }
    if (imageFiles.length > 0) {
      e.preventDefault();
      await addImagesFromFiles(imageFiles);
    }
  };

  // 드래그 앤 드롭 — 이미지 첨부
  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDraggingOver) setIsDraggingOver(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    // 자식으로 이동한 경우 무시
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setIsDraggingOver(false);
  };

  const handleDrop = async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);
    const files = Array.from(e.dataTransfer?.files || []);
    if (files.length > 0) {
      await addImagesFromFiles(files);
    }
  };

  useEffect(() => {
    if (!disabled) {
      setTimeout(() => textareaRef.current?.focus(), 100);
    }
  }, [disabled]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
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

  const hasContent =
    input.trim().length > 0 ||
    attachedFiles.length > 0 ||
    attachedImages.length > 0;

  return (
    <div
      className="flex flex-col gap-2"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* 드래그 오버레이 */}
      {isDraggingOver && (
        <div
          className="rounded-2xl border-2 border-dashed px-4 py-3 text-center text-sm"
          style={{
            borderColor: "var(--primary)",
            background: "color-mix(in srgb, var(--primary) 10%, transparent)",
            color: "var(--primary)",
          }}
        >
          이미지를 여기에 놓으세요 (최대 {MAX_IMAGES}장)
        </div>
      )}

      {/* 첨부 이미지 미리보기 */}
      {attachedImages.length > 0 && (
        <div className="flex flex-wrap gap-2 px-2">
          {attachedImages.map((img, i) => (
            <div key={i} className="relative">
              <img
                src={img.preview || img.base64}
                alt={img.name || "attached"}
                className="h-20 w-20 rounded-lg object-cover border"
                style={{ borderColor: "var(--border)" }}
              />
              <button
                onClick={() => removeImage(i)}
                className="absolute -top-1.5 -right-1.5 bg-red-500 hover:bg-red-600 text-white rounded-full w-5 h-5 text-xs flex items-center justify-center shadow"
                title="이미지 제거"
                type="button"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      )}

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
        {/* 숨겨진 일반 파일 input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.md,.py,.js,.ts,.json,.csv,.xlsx,.doc,.docx"
          onChange={handleFileChange}
          className="hidden"
        />
        {/* 숨겨진 이미지 input */}
        <input
          ref={imageInputRef}
          type="file"
          multiple
          accept="image/*"
          onChange={handleImageChange}
          className="hidden"
        />

        {/* 파일 첨부 버튼 */}
        <button
          onClick={handleFileSelect}
          disabled={disabled}
          className="p-1.5 rounded-lg hover:bg-[var(--muted)] transition-colors shrink-0 self-end disabled:opacity-30"
          style={{ color: "var(--muted-foreground)", marginBottom: "2px" }}
          title="파일 첨부"
          type="button"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
          </svg>
        </button>

        {/* 이미지 첨부 버튼 (Vision-to-Code) */}
        <button
          onClick={handleImageSelect}
          disabled={disabled || attachedImages.length >= MAX_IMAGES}
          className="p-1.5 rounded-lg hover:bg-[var(--muted)] transition-colors shrink-0 self-end disabled:opacity-30"
          style={{ color: "var(--muted-foreground)", marginBottom: "2px" }}
          title="이미지 첨부 (드래그/Cmd+V 지원, 최대 4장)"
          type="button"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </button>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          onPaste={handlePaste}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          placeholder={placeholder || "메시지 입력 또는 이미지 드래그/붙여넣기..."}
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
          type="button"
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

      {/* 옵션 바 — 입력창 바로 아래 (이미지 첨부 / 모델 / 안전 / 사용량) */}
      <OptionBar
        onImageClick={handleImageSelect}
        imageCount={attachedImages.length}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        selectedSafety={safetyMode}
        onSafetyChange={setSafetyMode}
        disabled={disabled}
      />
    </div>
  );
}
