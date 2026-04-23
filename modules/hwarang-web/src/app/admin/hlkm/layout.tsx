/**
 * HLKM 관리자 레이아웃
 * - 좌측 사이드바 (AdminNav)
 * - 우측 메인 컨텐츠 영역
 * - 모바일: 상단에 드로어 토글 대신 단순 collapse (최소 지원)
 */

import type { ReactNode } from "react";
import AdminNav from "./_components/AdminNav";

export const metadata = {
  title: "HLKM 관리 — Hwarang AI",
  description: "Hwarang Living Knowledge Mesh 운영 콘솔",
};

export default function HLKMLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto flex max-w-[1400px] flex-col md:flex-row">
        {/* 사이드바 */}
        <aside
          className="w-full shrink-0 border-b bg-white md:sticky md:top-0 md:h-screen md:w-64 md:border-b-0 md:border-r"
          style={{ borderColor: "#e5e7eb" }}
        >
          <AdminNav />
        </aside>

        {/* 메인 */}
        <main className="flex-1 px-4 py-6 md:px-8 md:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
