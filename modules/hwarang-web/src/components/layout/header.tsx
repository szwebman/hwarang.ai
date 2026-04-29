"use client";

import { useSession, signOut } from "next-auth/react";
import { useTheme } from "@/components/providers/theme-provider";
import Link from "next/link";
import { TokenBalanceDisplay } from "./token-balance-display";

interface HeaderProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
}

export function Header({ sidebarOpen, onToggleSidebar }: HeaderProps) {
  const { theme, toggleTheme } = useTheme();
  const { data: session } = useSession();

  return (
    <header
      className="flex items-center justify-between px-4 h-14 border-b glass"
      style={{ borderColor: "var(--border)", background: `color-mix(in srgb, var(--background) 80%, transparent)` }}
    >
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="p-2 rounded-lg hover:bg-[var(--muted)] transition-all duration-200 active:scale-95"
          title={sidebarOpen ? "사이드바 닫기" : "사이드바 열기"}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            {sidebarOpen ? (
              <><rect x="3" y="3" width="7" height="18" rx="1" opacity="0.5" /><rect x="14" y="3" width="7" height="18" rx="1" /></>
            ) : (
              <><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" /></>
            )}
          </svg>
        </button>

        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg gradient-bg flex items-center justify-center">
            <span className="text-white text-xs font-bold">H</span>
          </div>
          <h1 className="text-base font-semibold">
            <span className="gradient-text">화랑 AI</span>
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {/* 테마 */}
        <button onClick={toggleTheme}
          className="p-2 rounded-lg hover:bg-[var(--muted)] transition-all duration-200 active:scale-95"
          title="테마 변경">
          {theme === "light" ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          )}
        </button>

        {/* 토큰 잔량 (로그인 시) */}
        {session && <TokenBalanceDisplay />}

        {/* 로그인/유저 */}
        {session ? (
          <div className="flex items-center gap-2">
            <Link href="/account/devices"
              className="hidden md:inline-block text-xs px-2 py-1 rounded-lg hover:bg-[var(--muted)] transition-all"
              style={{ color: "var(--muted-foreground)" }}
              title="화랑 그리드 등록 기기 관리">
              내 기기
            </Link>
            <Link href="/dashboard"
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-[var(--muted)] transition-all text-sm">
              {session.user?.image ? (
                <img src={session.user.image} alt="" className="w-6 h-6 rounded-full" />
              ) : (
                <div className="w-6 h-6 rounded-full gradient-bg flex items-center justify-center">
                  <span className="text-white text-[10px] font-bold">
                    {(session.user?.name || "U")[0]}
                  </span>
                </div>
              )}
              <span className="hidden sm:inline">{session.user?.name || "사용자"}</span>
            </Link>
            <button onClick={() => signOut()}
              className="text-xs px-2 py-1 rounded-lg hover:bg-[var(--muted)]"
              style={{ color: "var(--muted-foreground)" }}>
              로그아웃
            </button>
          </div>
        ) : (
          <Link href="/login"
            className="px-4 py-1.5 rounded-lg text-sm font-medium text-white gradient-bg hover:shadow-md transition-all">
            로그인
          </Link>
        )}
      </div>
    </header>
  );
}
