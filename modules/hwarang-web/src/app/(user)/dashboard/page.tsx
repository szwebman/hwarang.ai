"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface UserData {
  name: string;
  email: string;
  plan: { name: string; displayName: string; tokensIncluded: number; dailyTokenLimit: number } | null;
  tokens: { balance: number; dailyUsed: number; dailyLimit: number; totalUsed: number } | null;
  apiKeys: { id: string; name: string; keyPrefix: string; lastUsedAt: string | null }[];
  stats: { conversations: number; totalRequests: number };
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}

export default function UserDashboardPage() {
  const [user, setUser] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/users/me")
      .then((r) => r.json())
      .then((data) => { setUser(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</div>
      </div>
    );
  }

  const tokens = user.tokens;
  const plan = user.plan;
  const pct = (used: number, total: number) => Math.min(100, (used / Math.max(total, 1)) * 100);

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">안녕하세요, {user.name}님</h1>
            <p className="text-sm mt-1" style={{ color: "var(--muted-foreground)" }}>
              {plan?.displayName || "Free"} 플랜 사용 중
            </p>
          </div>
          <Link href="/chat" className="px-4 py-2 rounded-xl text-sm font-medium text-white"
            style={{ background: "var(--primary)" }}>AI 채팅 시작</Link>
        </div>

        {/* 토큰 잔액 (핵심 카드) */}
        <div className="rounded-2xl border p-6 mb-6" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">내 토큰</h2>
            <Link href="/pricing" className="text-xs" style={{ color: "var(--primary)" }}>플랜 업그레이드 →</Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* 잔여 토큰 */}
            <div className="text-center">
              <div className="text-4xl font-bold" style={{ color: "var(--primary)" }}>
                {tokens ? formatTokens(tokens.balance) : "0"}
              </div>
              <div className="text-sm mt-1" style={{ color: "var(--muted-foreground)" }}>잔여 토큰</div>
              {plan && (
                <div className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>
                  월 {formatTokens(plan.tokensIncluded)} 중
                </div>
              )}
            </div>

            {/* 오늘 사용량 */}
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span style={{ color: "var(--muted-foreground)" }}>오늘 사용</span>
                <span className="font-medium">
                  {tokens ? formatTokens(tokens.dailyUsed) : "0"} / {tokens ? formatTokens(tokens.dailyLimit) : "0"}
                </span>
              </div>
              <div className="h-3 rounded-full" style={{ background: "var(--muted)" }}>
                <div className="h-3 rounded-full transition-all" style={{
                  width: `${tokens ? pct(tokens.dailyUsed, tokens.dailyLimit) : 0}%`,
                  background: tokens && pct(tokens.dailyUsed, tokens.dailyLimit) > 80 ? "var(--destructive)" : "var(--primary)",
                }} />
              </div>
              <div className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>하루 한도 (자정에 리셋)</div>
            </div>

            {/* 누적 사용 */}
            <div>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl p-3" style={{ background: "var(--muted)" }}>
                  <div className="text-lg font-bold">{tokens ? formatTokens(tokens.totalUsed) : "0"}</div>
                  <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>누적 사용</div>
                </div>
                <div className="rounded-xl p-3" style={{ background: "var(--muted)" }}>
                  <div className="text-lg font-bold">{user.stats.totalRequests.toLocaleString()}</div>
                  <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>총 요청</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {[
            { href: "/chat", icon: "💬", label: "AI 채팅" },
            { href: "/api-keys", icon: "🔑", label: "API 키" },
            { href: "/billing", icon: "💳", label: "결제" },
            { href: "/settings", icon: "⚙️", label: "설정" },
          ].map((a) => (
            <Link key={a.href} href={a.href}
              className="rounded-xl border p-4 text-center hover:shadow-md transition-all"
              style={{ borderColor: "var(--border)" }}>
              <span className="text-2xl">{a.icon}</span>
              <div className="text-xs font-medium mt-1">{a.label}</div>
            </Link>
          ))}
        </div>

        {/* API 키 미리보기 */}
        <div className="rounded-2xl border p-5" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-sm">내 API 키</h3>
            <Link href="/api-keys" className="text-xs" style={{ color: "var(--primary)" }}>전체 보기 →</Link>
          </div>
          {user.apiKeys.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
              아직 API 키가 없습니다. <Link href="/api-keys" style={{ color: "var(--primary)" }}>만들기 →</Link>
            </p>
          ) : (
            <div className="space-y-2">
              {user.apiKeys.slice(0, 3).map((key) => (
                <div key={key.id} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{key.name}</span>
                    <code className="text-xs px-1.5 py-0.5 rounded" style={{ background: "var(--muted)" }}>{key.keyPrefix}</code>
                  </div>
                  <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                    {key.lastUsedAt || "미사용"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
