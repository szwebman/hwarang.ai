"use client";

/**
 * OptionBar — 채팅 입력창 아래에 표시되는 옵션 바
 *
 * 영역:
 *   1) 이미지 첨부 트리거 (실제 첨부는 부모 MessageInput 의 hidden input 에 위임)
 *   2) 모델 선택 — Auto + DB 활성·공개 모델
 *   3) 안전 모드 — loose / standard / strict (3단계)
 *   4) 사용량 표시 — 잔여 일일 토큰 / 색상 (10% 빨강, 30% 주황, 그 외 초록)
 *
 * 자동 갱신:
 *   - 30초 인터벌 + window 의 "hwarang:usage-changed" 이벤트 (응답 직후 즉시 갱신)
 *
 * 모바일(< 640px) 대응:
 *   - 모델/안전 메뉴는 화면 폭에 따라 자연스럽게 wrap.
 *   - 작은 화면에서는 라벨 일부 축약(아이콘만 표시).
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

interface OptionBarProps {
  onImageClick: () => void;
  imageCount?: number;
  onModelChange?: (model: string) => void;
  selectedModel?: string;
  onSafetyChange?: (mode: string) => void;
  selectedSafety?: string;
  showModel?: boolean;
  disabled?: boolean;
}

interface UsageData {
  balance: number;
  dailyUsed: number;
  dailyLimit: number;
}

interface ModelOption {
  name: string;
  displayName: string;
  description?: string | null;
  category: string;
  tier?: string;
  isDefault?: boolean;
}

const SAFETY_MODES = [
  { value: "loose", label: "관대", icon: "🆓", desc: "최소 필터링, 빠른 응답" },
  { value: "standard", label: "표준", icon: "🛡️", desc: "균형잡힌 안전" },
  { value: "strict", label: "엄격", icon: "🔒", desc: "법률/의료 안전 ↑" },
] as const;

export function OptionBar({
  onImageClick,
  imageCount = 0,
  onModelChange,
  selectedModel,
  onSafetyChange,
  selectedSafety = "standard",
  showModel = true,
  disabled = false,
}: OptionBarProps) {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [showSafetyMenu, setShowSafetyMenu] = useState(false);
  const modelMenuRef = useRef<HTMLDivElement>(null);
  const safetyMenuRef = useRef<HTMLDivElement>(null);

  const fetchUsage = async () => {
    try {
      const r = await fetch("/api/users/me");
      if (!r.ok) return;
      const u = await r.json();
      const t = u.tokens || u.tokenBalance;
      if (t) {
        setUsage({
          balance: t.balance ?? 0,
          dailyUsed: t.dailyUsed ?? 0,
          dailyLimit: t.dailyLimit ?? 0,
        });
      }
    } catch {
      /* noop */
    }
  };

  const fetchModels = async () => {
    try {
      const r = await fetch("/api/models/public");
      if (!r.ok) return;
      const data = await r.json();
      setModels(data.models || []);
    } catch {
      /* noop */
    }
  };

  // 초기 로드 + 30초 폴링 + 응답 직후 즉시 갱신 이벤트 리스너
  useEffect(() => {
    fetchUsage();
    if (showModel) fetchModels();

    const interval = setInterval(fetchUsage, 30000);

    const handler = () => fetchUsage();
    if (typeof window !== "undefined") {
      window.addEventListener("hwarang:usage-changed", handler);
    }

    return () => {
      clearInterval(interval);
      if (typeof window !== "undefined") {
        window.removeEventListener("hwarang:usage-changed", handler);
      }
    };
  }, [showModel]);

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (
        showModelMenu &&
        modelMenuRef.current &&
        !modelMenuRef.current.contains(e.target as Node)
      ) {
        setShowModelMenu(false);
      }
      if (
        showSafetyMenu &&
        safetyMenuRef.current &&
        !safetyMenuRef.current.contains(e.target as Node)
      ) {
        setShowSafetyMenu(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [showModelMenu, showSafetyMenu]);

  const remaining = usage ? Math.max(0, usage.dailyLimit - usage.dailyUsed) : 0;
  const percentLeft =
    usage && usage.dailyLimit > 0 ? (remaining / usage.dailyLimit) * 100 : 100;
  const usageColor =
    percentLeft < 10 ? "#ef4444" : percentLeft < 30 ? "#f59e0b" : "#10b981";

  const currentSafety =
    SAFETY_MODES.find((s) => s.value === selectedSafety) || SAFETY_MODES[1];
  const currentModel: ModelOption =
    models.find((m) => m.name === selectedModel) ||
    {
      name: "",
      displayName: "Auto",
      category: "auto",
    };

  const buttonBase =
    "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition disabled:opacity-50";
  const buttonBaseStyle = { borderColor: "var(--border)", height: 28 };

  return (
    <div className="flex flex-wrap items-center gap-1.5 mt-2 text-xs">
      {/* 이미지 첨부 */}
      <button
        onClick={onImageClick}
        disabled={disabled}
        className={`${buttonBase} hover:bg-[var(--muted)]`}
        style={buttonBaseStyle}
        title="이미지 첨부"
        type="button"
      >
        <span aria-hidden>📎</span>
        <span className="hidden sm:inline">이미지</span>
        {imageCount > 0 && (
          <span
            className="text-[10px] px-1 rounded text-white"
            style={{ background: "var(--primary)" }}
          >
            {imageCount}
          </span>
        )}
      </button>

      {/* 모델 선택 */}
      {showModel && (
        <div className="relative" ref={modelMenuRef}>
          <button
            onClick={() => {
              setShowModelMenu((v) => !v);
              setShowSafetyMenu(false);
            }}
            disabled={disabled}
            className={`${buttonBase} hover:bg-[var(--muted)] ${
              showModelMenu ? "ring-1" : ""
            }`}
            style={{
              ...buttonBaseStyle,
              ...(showModelMenu ? { boxShadow: `0 0 0 1px var(--primary)` } : null),
            }}
            title="모델 선택"
            type="button"
          >
            <span aria-hidden>🎯</span>
            <span className="max-w-[120px] truncate">
              {currentModel.displayName.slice(0, 14)}
            </span>
            <span className="text-[10px]">▾</span>
          </button>

          {showModelMenu && (
            <div
              className="absolute bottom-full mb-1 left-0 z-50 rounded-lg border shadow-lg w-60 max-h-72 overflow-y-auto"
              style={{
                background: "var(--background)",
                borderColor: "var(--border)",
              }}
            >
              <button
                onClick={() => {
                  onModelChange?.("");
                  setShowModelMenu(false);
                }}
                className="w-full text-left px-3 py-2 hover:bg-[var(--muted)] text-xs"
                type="button"
              >
                <div className="font-medium flex items-center gap-1.5">
                  <span>⚡ Auto</span>
                  {!selectedModel && <span className="ml-auto">✓</span>}
                </div>
                <div
                  className="text-[10px]"
                  style={{ color: "var(--muted-foreground)" }}
                >
                  도메인 자동 감지
                </div>
              </button>
              {models.map((m) => (
                <button
                  key={m.name}
                  onClick={() => {
                    onModelChange?.(m.name);
                    setShowModelMenu(false);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-[var(--muted)] text-xs border-t"
                  style={{ borderColor: "var(--border)" }}
                  type="button"
                >
                  <div className="font-medium flex items-center gap-1.5">
                    <span className="truncate">{m.displayName}</span>
                    {selectedModel === m.name && <span className="ml-auto">✓</span>}
                  </div>
                  <div
                    className="text-[10px]"
                    style={{ color: "var(--muted-foreground)" }}
                  >
                    {m.category}
                    {m.tier ? ` · ${m.tier}` : ""}
                  </div>
                </button>
              ))}
              {models.length === 0 && (
                <div
                  className="px-3 py-2 text-[11px]"
                  style={{ color: "var(--muted-foreground)" }}
                >
                  등록된 모델이 없습니다.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 안전 모드 */}
      <div className="relative" ref={safetyMenuRef}>
        <button
          onClick={() => {
            setShowSafetyMenu((v) => !v);
            setShowModelMenu(false);
          }}
          disabled={disabled}
          className={`${buttonBase} hover:bg-[var(--muted)] ${
            showSafetyMenu ? "ring-1" : ""
          }`}
          style={{
            ...buttonBaseStyle,
            ...(showSafetyMenu ? { boxShadow: `0 0 0 1px var(--primary)` } : null),
          }}
          title="안전 모드"
          type="button"
        >
          <span aria-hidden>{currentSafety.icon}</span>
          <span className="hidden sm:inline">{currentSafety.label}</span>
          <span className="text-[10px]">▾</span>
        </button>

        {showSafetyMenu && (
          <div
            className="absolute bottom-full mb-1 left-0 z-50 rounded-lg border shadow-lg w-56"
            style={{
              background: "var(--background)",
              borderColor: "var(--border)",
            }}
          >
            {SAFETY_MODES.map((m) => (
              <button
                key={m.value}
                onClick={() => {
                  onSafetyChange?.(m.value);
                  setShowSafetyMenu(false);
                }}
                className="w-full text-left px-3 py-2 hover:bg-[var(--muted)] text-xs flex items-start gap-2"
                type="button"
              >
                <span aria-hidden>{m.icon}</span>
                <div className="flex-1">
                  <div className="font-medium">{m.label}</div>
                  <div
                    className="text-[10px]"
                    style={{ color: "var(--muted-foreground)" }}
                  >
                    {m.desc}
                  </div>
                </div>
                {selectedSafety === m.value && <span className="ml-1">✓</span>}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 가운데 빈 공간 (사용량을 우측으로) */}
      <div className="flex-1" />

      {/* 사용량 표시 */}
      {usage && usage.dailyLimit > 0 && (
        <Link
          href="/dashboard"
          className={`${buttonBase} hover:bg-[var(--muted)]`}
          style={buttonBaseStyle}
          title={`잔액: ${usage.balance.toLocaleString()} · 오늘 사용: ${usage.dailyUsed.toLocaleString()} / ${usage.dailyLimit.toLocaleString()}`}
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="2" y1="12" x2="22" y2="12" />
          </svg>
          <span className="font-mono">
            <span style={{ color: usageColor }}>
              {(remaining / 1000).toFixed(1)}K
            </span>
            <span style={{ color: "var(--muted-foreground)" }}>
              {" "}
              / {(usage.dailyLimit / 1000).toFixed(0)}K
            </span>
          </span>
        </Link>
      )}

      {/* 잔액 부족 경고 */}
      {usage && usage.dailyLimit > 0 && percentLeft < 10 && (
        <Link
          href="/pricing"
          className="text-[10px] px-2 py-1 rounded text-white"
          style={{ background: "#ef4444" }}
        >
          충전
        </Link>
      )}
    </div>
  );
}
