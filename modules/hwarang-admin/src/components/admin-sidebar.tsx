"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";

const NAV_ITEMS = [
  { href: "/", icon: "📊", label: "대시보드" },
  { href: "/servers", icon: "🖥️", label: "서버 모니터링" },
  { href: "/users", icon: "👥", label: "유저 관리" },
  { href: "/plans", icon: "💎", label: "플랜 관리" },
  { href: "/models", icon: "🧠", label: "모델 관리" },
  { href: "/admins", icon: "🔐", label: "관리자 계정" },
  { href: "/billing", icon: "💳", label: "매출 현황" },
  { href: "/logs", icon: "📋", label: "요청 로그" },
];

export function AdminSidebar({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (pathname === "/login") {
      setChecked(true);
      return;
    }

    const token = localStorage.getItem("admin_token");
    const savedUser = localStorage.getItem("admin_user");

    if (!token) {
      router.push("/login");
    } else {
      setUser(savedUser ? JSON.parse(savedUser) : null);
      setChecked(true);
    }
  }, [pathname, router]);

  // 로그인 페이지는 사이드바 없이
  if (pathname === "/login") {
    return <>{children}</>;
  }

  if (!checked) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-sm" style={{ color: "var(--muted-foreground)" }}>인증 확인 중...</div>
      </div>
    );
  }

  const handleLogout = () => {
    localStorage.removeItem("admin_token");
    localStorage.removeItem("admin_user");
    router.push("/login");
  };

  return (
    <div className="flex h-screen">
      <aside className="w-56 shrink-0 border-r flex flex-col" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
        {/* 로고 */}
        <div className="p-4 border-b" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{ background: "var(--primary)" }}>H</div>
            <div>
              <div className="font-bold text-sm">화랑 AI</div>
              <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>관리자 패널</div>
            </div>
          </div>
        </div>

        {/* 네비게이션 */}
        <nav className="flex-1 p-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
            return (
              <Link key={item.href} href={item.href}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${isActive ? "font-medium" : ""}`}
                style={{
                  background: isActive ? "var(--accent)" : "transparent",
                  color: isActive ? "var(--accent-foreground)" : "var(--foreground)",
                }}>
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* 하단: 관리자 정보 + 로그아웃 */}
        <div className="p-3 border-t" style={{ borderColor: "var(--border)" }}>
          {user && (
            <div className="mb-2 px-2">
              <div className="text-xs font-medium">{user.name || user.email}</div>
              <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>
                {user.role === "SUPER_ADMIN" ? "최고 관리자" : "관리자"}
              </div>
            </div>
          )}
          <div className="flex gap-2">
            <a href="https://hwarang.ai" target="_blank"
              className="flex-1 text-center text-[10px] px-2 py-1.5 rounded-lg border"
              style={{ borderColor: "var(--border)", color: "var(--muted-foreground)" }}>
              서비스로
            </a>
            <button onClick={handleLogout}
              className="flex-1 text-center text-[10px] px-2 py-1.5 rounded-lg"
              style={{ color: "var(--destructive)" }}>
              로그아웃
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
