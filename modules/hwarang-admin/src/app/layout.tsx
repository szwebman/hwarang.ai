import type { Metadata } from "next";
import "./globals.css";
import { AdminSidebar } from "@/components/admin-sidebar";

export const metadata: Metadata = {
  title: "화랑 AI 관리자",
  description: "Hwarang AI Admin Dashboard",
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <AdminSidebar>{children}</AdminSidebar>
      </body>
    </html>
  );
}
