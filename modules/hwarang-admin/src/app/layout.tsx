import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "화랑 AI 관리자",
  description: "Hwarang AI Admin Dashboard",
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <div className="flex h-screen">
          {/* 사이드 네비 */}
          <aside className="w-56 shrink-0 border-r flex flex-col" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
            <div className="p-4 border-b" style={{ borderColor: "var(--border)" }}>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{ background: "var(--primary)" }}>H</div>
                <div>
                  <div className="font-bold text-sm">화랑 AI</div>
                  <div className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>관리자</div>
                </div>
              </div>
            </div>
            <nav className="flex-1 p-3 space-y-1">
              {[
                { href: "/", icon: "📊", label: "대시보드" },
                { href: "/servers", icon: "🖥️", label: "서버 모니터링" },
                { href: "/users", icon: "👥", label: "유저 관리" },
                { href: "/plans", icon: "💎", label: "플랜 관리" },
                { href: "/models", icon: "🧠", label: "모델 관리" },
                { href: "/billing", icon: "💳", label: "매출 현황" },
                { href: "/logs", icon: "📋", label: "요청 로그" },
              ].map((item) => (
                <Link key={item.href} href={item.href}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-[var(--muted)] transition-colors">
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              ))}
            </nav>
            <div className="p-3 border-t text-xs" style={{ borderColor: "var(--border)", color: "var(--muted-foreground)" }}>
              <a href="https://hwarang.ai" target="_blank" className="hover:underline">← hwarang.ai로 돌아가기</a>
            </div>
          </aside>

          {/* 메인 콘텐츠 */}
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
