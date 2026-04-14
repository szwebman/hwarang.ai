"use client";

import { useEffect, useState } from "react";

interface Plan {
  id: string;
  name: string;
  displayName: string;
  priceMonthly: number;
  priceYearly: number;
  tokensIncluded: number;
  dailyTokenLimit: number;
  maxTokensPerReq: number;
  models: string[];
  features: string[];
  apiKeysAllowed: number;
  overagePrice7b: number;
  overagePrice30b: number;
  _count?: { users: number };
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}

export default function PricingPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [yearly, setYearly] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/plans")
      .then((r) => r.json())
      .then((data) => { setPlans(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const popularPlan = "pro";

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-sm" style={{ color: "var(--muted-foreground)" }}>
          플랜 로딩 중...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      <div className="max-w-6xl mx-auto px-4 py-16">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold mb-4">
            <span className="gradient-text">토큰만 보면 됩니다</span>
          </h1>
          <p className="text-lg" style={{ color: "var(--muted-foreground)" }}>
            복잡한 요금제 없이, 토큰 충전 → 사용 → 소진 시 충전. 단순합니다.
          </p>

          <div className="flex items-center justify-center gap-3 mt-8">
            <span className={`text-sm ${!yearly ? "font-semibold" : ""}`}
              style={{ color: yearly ? "var(--muted-foreground)" : "var(--foreground)" }}>월간</span>
            <button onClick={() => setYearly(!yearly)}
              className="relative w-12 h-6 rounded-full transition-colors"
              style={{ background: yearly ? "var(--primary)" : "var(--border)" }}>
              <span className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform"
                style={{ transform: yearly ? "translateX(26px)" : "translateX(2px)" }} />
            </button>
            <span className={`text-sm ${yearly ? "font-semibold" : ""}`}
              style={{ color: !yearly ? "var(--muted-foreground)" : "var(--foreground)" }}>
              연간 <span className="text-xs px-1.5 py-0.5 rounded-full"
                style={{ background: "var(--accent)", color: "var(--primary)" }}>2개월 무료</span>
            </span>
          </div>
        </div>

        {/* Plans from API */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {plans.map((plan) => {
            const price = yearly ? plan.priceYearly : plan.priceMonthly;
            const period = yearly ? "/년" : "/월";
            const isPopular = plan.name === popularPlan;

            return (
              <div key={plan.id}
                className={`relative rounded-2xl p-6 border transition-all hover:shadow-lg ${isPopular ? "border-2 shadow-md" : ""}`}
                style={{ borderColor: isPopular ? "var(--primary)" : "var(--border)", background: "var(--background)" }}>

                {isPopular && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 text-xs font-bold px-3 py-1 rounded-full text-white"
                    style={{ background: "var(--primary)" }}>가장 인기</span>
                )}

                <h3 className="text-lg font-semibold">{plan.displayName}</h3>

                <div className="mt-4 mb-2">
                  {price > 0 ? (
                    <><span className="text-3xl font-bold">{price.toLocaleString()}원</span>
                    <span className="text-sm" style={{ color: "var(--muted-foreground)" }}>{period}</span></>
                  ) : (
                    <span className="text-3xl font-bold">무료</span>
                  )}
                </div>

                {/* 토큰 핵심 */}
                <div className="rounded-xl p-3 my-4" style={{ background: "var(--muted)" }}>
                  <div className="text-center">
                    <div className="text-2xl font-bold" style={{ color: "var(--primary)" }}>
                      {formatTokens(plan.tokensIncluded)}
                    </div>
                    <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>토큰 / 월</div>
                  </div>
                  <div className="flex justify-between mt-2 text-xs" style={{ color: "var(--muted-foreground)" }}>
                    <span>하루 최대: <strong style={{ color: "var(--foreground)" }}>{formatTokens(plan.dailyTokenLimit)}</strong></span>
                    <span>요청당: <strong style={{ color: "var(--foreground)" }}>{formatTokens(plan.maxTokensPerReq)}</strong></span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 mb-4 text-xs" style={{ color: "var(--muted-foreground)" }}>
                  <div>모델: <strong style={{ color: "var(--foreground)" }}>{plan.models.join("+")}</strong></div>
                  <div>API키: <strong style={{ color: "var(--foreground)" }}>{plan.apiKeysAllowed}개</strong></div>
                </div>

                {/* 초과 단가 */}
                {(plan.overagePrice7b > 0 || plan.overagePrice30b > 0) ? (
                  <div className="text-xs mb-4 px-2 py-1.5 rounded-lg" style={{ background: "var(--accent)" }}>
                    <span style={{ color: "var(--primary)" }}>초과 시: </span>
                    {plan.overagePrice7b > 0 && <span>7B {plan.overagePrice7b}원/1K </span>}
                    {plan.overagePrice30b > 0 && <span>· 30B {plan.overagePrice30b}원/1K</span>}
                  </div>
                ) : (
                  <div className="text-xs mb-4 px-2 py-1.5 rounded-lg" style={{ background: "#fef3c7", color: "#92400e" }}>
                    토큰 소진 → 다음 달 리셋 대기
                  </div>
                )}

                <ul className="space-y-2 mb-6">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm">
                      <svg className="w-4 h-4 mt-0.5 shrink-0" style={{ color: "var(--primary)" }}
                        fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>{f}
                    </li>
                  ))}
                </ul>

                <button className={`w-full py-2.5 rounded-xl text-sm font-medium transition-all ${isPopular ? "text-white" : "border"}`}
                  style={{ background: isPopular ? "var(--primary)" : "transparent", borderColor: isPopular ? "transparent" : "var(--border)" }}>
                  {price > 0 ? "시작하기" : "무료로 시작"}
                </button>
              </div>
            );
          })}
        </div>

        {/* 토큰 환산 가이드 */}
        <div className="mt-16">
          <h2 className="text-2xl font-bold text-center mb-8">토큰이 뭔가요?</h2>
          <div className="max-w-3xl mx-auto rounded-2xl border p-8" style={{ borderColor: "var(--border)" }}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-xl p-4" style={{ background: "var(--muted)" }}>
                <div className="font-semibold text-sm mb-2">한국어 기준</div>
                <div className="text-xs space-y-1" style={{ color: "var(--muted-foreground)" }}>
                  <div>100자 ≈ <strong style={{ color: "var(--foreground)" }}>~70 토큰</strong></div>
                  <div>짧은 질문+답변 ≈ <strong style={{ color: "var(--foreground)" }}>~300 토큰</strong></div>
                  <div>코드 50줄+설명 ≈ <strong style={{ color: "var(--foreground)" }}>~800 토큰</strong></div>
                </div>
              </div>
              <div className="rounded-xl p-4" style={{ background: "var(--muted)" }}>
                <div className="font-semibold text-sm mb-2">플랜별 약 대화 횟수</div>
                <div className="text-xs space-y-1" style={{ color: "var(--muted-foreground)" }}>
                  {plans.map((p) => (
                    <div key={p.id}>
                      {p.displayName} {formatTokens(p.tokensIncluded)} →{" "}
                      <strong style={{ color: "var(--foreground)" }}>
                        ~{Math.round(p.tokensIncluded / 300).toLocaleString()}회
                      </strong>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 토큰 추가 구매 */}
        <div className="mt-12 text-center">
          <h2 className="text-2xl font-bold mb-4">토큰 부족하면?</h2>
          <p className="mb-6" style={{ color: "var(--muted-foreground)" }}>필요한 만큼만 추가 구매. 유효기간 없음.</p>
          <div className="inline-grid grid-cols-3 gap-4">
            {[
              { tokens: 50_000, price: 4900, label: "가벼운 사용" },
              { tokens: 200_000, price: 15900, label: "일반 사용" },
              { tokens: 1_000_000, price: 69000, label: "대량 사용" },
            ].map((pack) => (
              <div key={pack.tokens}
                className="rounded-2xl border p-6 hover:shadow-md transition-all cursor-pointer"
                style={{ borderColor: "var(--border)" }}>
                <div className="text-2xl font-bold" style={{ color: "var(--primary)" }}>{formatTokens(pack.tokens)}</div>
                <div className="text-xs mb-1" style={{ color: "var(--muted-foreground)" }}>토큰</div>
                <div className="text-lg font-bold">{pack.price.toLocaleString()}원</div>
                <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                  {(pack.price / (pack.tokens / 1000)).toFixed(1)}원/1K · {pack.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
