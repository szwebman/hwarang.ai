"use client";

import { useState } from "react";
import type { ChatOption } from "@/types/chat";

interface OptionCardsProps {
  options: ChatOption[];
  deliverable: string;
  /** 어느 메시지에 속한 옵션인지 — 같은 메시지에 인라인 답변을 이어붙이기 위해 사용. */
  messageId: string;
  /**
   * 옵션 선택 콜백 — 선택된 옵션과 메시지 ID 를 부모(useChat.continueMessage)로 전달.
   * 부모가 await 동안 카드는 진행중 오버레이 표시.
   */
  onSelect: (option: ChatOption, messageId: string) => Promise<void> | void;
  /** 이미 선택된 옵션 ID — 있으면 카드 잠금 + ✓ 표시 + 비선택 카드는 흐림. */
  selectedOptionId?: string | null;
}

export function OptionCards({
  options,
  deliverable,
  messageId,
  onSelect,
  selectedOptionId,
}: OptionCardsProps) {
  const [pendingId, setPendingId] = useState<string | null>(null);

  const isLocked = !!selectedOptionId;

  const handleClick = async (opt: ChatOption) => {
    if (isLocked || pendingId) return;
    setPendingId(opt.id);
    try {
      await onSelect(opt, messageId);
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="mt-3 space-y-2">
      <div className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
        💡 {deliverable} — {options.length}가지 접근법
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {options.map((opt) => {
          const isSelected = selectedOptionId === opt.id;
          const isPending = pendingId === opt.id;
          const isDimmed = isLocked && !isSelected;

          return (
            <button
              key={opt.id}
              onClick={() => handleClick(opt)}
              disabled={isLocked || pendingId !== null}
              className={`text-left rounded-xl border p-3 transition-all relative ${
                isSelected
                  ? "ring-2"
                  : isDimmed
                  ? "opacity-40"
                  : "hover:shadow-md hover:border-[var(--primary)]"
              } ${isLocked ? "cursor-default" : "cursor-pointer"}`}
              style={{
                borderColor: isSelected ? "var(--primary)" : "var(--border)",
                background: isSelected
                  ? "color-mix(in srgb, var(--primary) 8%, transparent)"
                  : "var(--background)",
              }}
            >
              <div className="flex items-start gap-2 mb-1">
                <span className="text-xl">{opt.preview_emoji}</span>
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-sm flex items-center gap-1">
                    {opt.title}
                    {isSelected && <span className="text-xs">✓</span>}
                  </h4>
                </div>
              </div>
              <p className="text-xs mb-2" style={{ color: "var(--muted-foreground)" }}>
                {opt.description}
              </p>
              <div className="flex flex-wrap gap-1">
                {opt.keywords.slice(0, 3).map((k) => (
                  <span
                    key={k}
                    className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                    style={{ background: "var(--muted)", color: "var(--muted-foreground)" }}
                  >
                    {k}
                  </span>
                ))}
              </div>

              {/* 진행 중 오버레이 (해당 카드 클릭 직후 ~ 응답 시작 사이) */}
              {isPending && (
                <div
                  className="absolute inset-0 flex items-center justify-center rounded-xl"
                  style={{ background: "color-mix(in srgb, var(--primary) 15%, transparent)" }}
                >
                  <span className="text-xs font-medium">진행 중...</span>
                </div>
              )}
            </button>
          );
        })}
      </div>
      {!isLocked ? (
        <div className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
          하나 선택하면 같은 메시지에 이어서 답변이 추가됩니다.
        </div>
      ) : (
        <div className="text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
          ↓ 아래 답변이 이어집니다
        </div>
      )}
    </div>
  );
}
