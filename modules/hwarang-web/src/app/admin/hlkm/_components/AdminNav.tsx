"use client";

/**
 * AdminNav — HLKM 관리자 사이드바 네비게이션
 * 현재 경로를 하이라이트하고, 아이콘과 설명을 함께 표시
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  icon: string;
  hint?: string;
}

const NAV: NavItem[] = [
  { href: "/admin/hlkm", label: "대시보드", icon: "📊", hint: "전체 현황" },
  { href: "/admin/hlkm/curation", label: "큐레이션", icon: "📝", hint: "사실 승인/반려" },
  { href: "/admin/hlkm/conflicts", label: "모순 관리", icon: "⚡", hint: "충돌 해결" },
  { href: "/admin/hlkm/gaps", label: "지식 공백", icon: "🕳️", hint: "답변 실패 추적" },
  { href: "/admin/hlkm/contributions", label: "기여자 랭킹", icon: "💰", hint: "보상 지급" },
  { href: "/admin/hlkm/settings", label: "설정", icon: "⚙️", hint: "임계값·스케줄" },
];

export default function AdminNav() {
  const pathname = usePathname() || "";

  const isActive = (href: string) => {
    if (href === "/admin/hlkm") {
      return pathname === "/admin/hlkm";
    }
    return pathname.startsWith(href);
  };

  return (
    <nav className="flex flex-col gap-1 p-3">
      <div className="mb-3 px-3 pt-2">
        <div className="text-xs font-medium uppercase tracking-wider text-gray-400">
          HLKM
        </div>
        <div className="mt-1 text-sm font-semibold text-gray-900">
          Living Knowledge Mesh
        </div>
      </div>

      {NAV.map((item) => {
        const active = isActive(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
              active
                ? "bg-blue-50 text-blue-700"
                : "text-gray-700 hover:bg-gray-50"
            }`}
          >
            <span className="text-base">{item.icon}</span>
            <div className="flex-1">
              <div className={`font-medium ${active ? "text-blue-700" : "text-gray-900"}`}>
                {item.label}
              </div>
              {item.hint && (
                <div className="text-[11px] text-gray-500">{item.hint}</div>
              )}
            </div>
            {active && <span className="text-xs text-blue-600">●</span>}
          </Link>
        );
      })}

      <div className="mt-6 border-t pt-3" style={{ borderColor: "#e5e7eb" }}>
        <Link
          href="/dashboard"
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-500 hover:bg-gray-50"
        >
          ← 일반 대시보드로
        </Link>
      </div>
    </nav>
  );
}
