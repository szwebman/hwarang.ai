"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface TokenData {
  balance: number;
  dailyUsed: number;
  dailyLimit: number;
}

function formatK(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return `${n}`;
}

/**
 * 헤더에 표시되는 토큰 잔량 위젯
 * - 1분마다 /api/users/me 폴링
 * - 잔량 부족 (10% 미만) → 빨간색
 * - 클릭 → 대시보드, 호버 → 상세 정보
 * - 모바일(< sm)에서는 숨김
 */
export function TokenBalanceDisplay() {
  const [data, setData] = useState<TokenData | null>(null);

  useEffect(() => {
    let mounted = true;
    const fetchBalance = async () => {
      try {
        const res = await fetch("/api/users/me");
        if (!res.ok) return;
        const u = await res.json();
        // /api/users/me 는 `tokens` 필드로 반환
        const t = u.tokens;
        if (mounted && t) {
          setData({
            balance: t.balance ?? 0,
            dailyUsed: t.dailyUsed ?? 0,
            dailyLimit: t.dailyLimit ?? 0,
          });
        }
      } catch {
        // 네트워크 오류 시 표시 유지 (이전 값 사용)
      }
    };
    fetchBalance();
    const interval = setInterval(fetchBalance, 60_000); // 1분
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  if (!data) return null;

  const remaining = Math.max(0, data.dailyLimit - data.dailyUsed);
  const percentLeft = data.dailyLimit > 0 ? (remaining / data.dailyLimit) * 100 : 100;
  const low = percentLeft < 10;
  const warn = percentLeft < 30;

  const colorVar = low
    ? "var(--destructive)"
    : warn
      ? "#f59e0b"
      : "var(--primary)";

  const tooltip =
    `잔여: ${data.balance.toLocaleString()} 토큰\n` +
    `오늘: ${data.dailyUsed.toLocaleString()} / ${data.dailyLimit.toLocaleString()} ` +
    `(${Math.round(100 - percentLeft)}% 사용)\n` +
    `클릭하면 대시보드 열림`;

  return (
    <Link
      href={low ? "/pricing" : "/dashboard"}
      title={tooltip}
      className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[var(--muted)] transition-all duration-200 active:scale-95 border"
      style={{ borderColor: "var(--border)" }}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke={colorVar}
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="10" />
        <path d="M8 12h8M12 8v8" opacity="0.6" />
      </svg>
      <span className="text-xs font-mono leading-none">
        <span style={{ color: colorVar, fontWeight: 600 }}>
          {formatK(remaining)}
        </span>
        <span style={{ color: "var(--muted-foreground)" }} className="ml-1">
          / {formatK(data.dailyLimit)}
        </span>
      </span>
      {low && (
        <span
          className="text-[10px] font-semibold px-1.5 py-0.5 rounded ml-1"
          style={{
            background: "color-mix(in srgb, var(--destructive) 15%, transparent)",
            color: "var(--destructive)",
          }}
        >
          충전
        </span>
      )}
    </Link>
  );
}
