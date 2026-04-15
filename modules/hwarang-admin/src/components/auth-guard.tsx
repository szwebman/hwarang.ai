"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (pathname === "/login") {
      setChecked(true);
      return;
    }

    const token = localStorage.getItem("admin_token");
    if (!token) {
      router.push("/login");
    } else {
      setChecked(true);
    }
  }, [pathname, router]);

  if (!checked && pathname !== "/login") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-sm" style={{ color: "var(--muted-foreground)" }}>인증 확인 중...</div>
      </div>
    );
  }

  return <>{children}</>;
}
