"""화랑 AI 웹 디자인/UI/UX 학습 데이터

웹 디자인 원칙, UI 컴포넌트, UX 패턴, 랜딩페이지, 대시보드 등.

사용법:
    python scripts/data/build_design_data.py \
        --output data/sft/design.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 UI/UX 디자이너 겸 프론트엔드 개발자 수준의 디자인 어시스턴트입니다.
설명은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 디자인 시스템 ═══
    m("디자인 시스템 구축 방법 알려줘",
'''체계적인 디자인 시스템을 구축하는 방법입니다.

```tsx
// ═══ 1. 디자인 토큰 (Design Tokens) ═══
// tailwind.config.ts

import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  theme: {
    extend: {
      // 색상 체계
      colors: {
        // 브랜드 색상
        brand: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",  // 기본
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
        },
        // 시맨틱 색상
        success: { DEFAULT: "#10b981", light: "#d1fae5", dark: "#065f46" },
        warning: { DEFAULT: "#f59e0b", light: "#fef3c7", dark: "#92400e" },
        error: { DEFAULT: "#ef4444", light: "#fee2e2", dark: "#991b1b" },
        info: { DEFAULT: "#3b82f6", light: "#dbeafe", dark: "#1e40af" },
      },
      // 타이포그래피
      fontFamily: {
        sans: ["Pretendard", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      fontSize: {
        "display-lg": ["3.5rem", { lineHeight: "1.2", letterSpacing: "-0.02em" }],
        "display": ["3rem", { lineHeight: "1.2", letterSpacing: "-0.02em" }],
        "heading-1": ["2.25rem", { lineHeight: "1.3" }],
        "heading-2": ["1.875rem", { lineHeight: "1.35" }],
        "heading-3": ["1.5rem", { lineHeight: "1.4" }],
        "body-lg": ["1.125rem", { lineHeight: "1.6" }],
        "body": ["1rem", { lineHeight: "1.6" }],
        "body-sm": ["0.875rem", { lineHeight: "1.5" }],
        "caption": ["0.75rem", { lineHeight: "1.5" }],
      },
      // 간격
      spacing: {
        "4xs": "0.125rem",  // 2px
        "3xs": "0.25rem",   // 4px
        "2xs": "0.375rem",  // 6px
        "xs": "0.5rem",     // 8px
        "sm": "0.75rem",    // 12px
        "md": "1rem",       // 16px
        "lg": "1.5rem",     // 24px
        "xl": "2rem",       // 32px
        "2xl": "3rem",      // 48px
        "3xl": "4rem",      // 64px
      },
      // 그림자
      boxShadow: {
        "elevation-1": "0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.06)",
        "elevation-2": "0 4px 6px rgba(0,0,0,0.1), 0 2px 4px rgba(0,0,0,0.06)",
        "elevation-3": "0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05)",
        "elevation-4": "0 20px 25px rgba(0,0,0,0.1), 0 10px 10px rgba(0,0,0,0.04)",
      },
      // 둥글기
      borderRadius: {
        "sm": "0.375rem",   // 6px
        "md": "0.5rem",     // 8px
        "lg": "0.75rem",    // 12px
        "xl": "1rem",       // 16px
        "2xl": "1.5rem",    // 24px
      },
    },
  },
};

// ═══ 2. 기본 컴포넌트 ═══

// Badge 컴포넌트
const badgeVariants = cva(
  "inline-flex items-center rounded-full font-medium",
  {
    variants: {
      variant: {
        default: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200",
        success: "bg-success-light text-success-dark",
        warning: "bg-warning-light text-warning-dark",
        error: "bg-error-light text-error-dark",
        info: "bg-info-light text-info-dark",
      },
      size: {
        sm: "px-2 py-0.5 text-xs",
        md: "px-2.5 py-0.5 text-sm",
        lg: "px-3 py-1 text-sm",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  }
);

// Avatar 컴포넌트
function Avatar({ src, name, size = "md" }: AvatarProps) {
  const sizes = { sm: "h-8 w-8", md: "h-10 w-10", lg: "h-12 w-12", xl: "h-16 w-16" };
  const initials = name.split(" ").map(n => n[0]).join("").toUpperCase();

  return src ? (
    <img src={src} alt={name} className={cn("rounded-full object-cover", sizes[size])} />
  ) : (
    <div className={cn(
      "rounded-full bg-brand-100 text-brand-700 flex items-center justify-center font-medium",
      sizes[size]
    )}>
      {initials}
    </div>
  );
}

// Card 컴포넌트
function Card({ children, className, hover = false }: CardProps) {
  return (
    <div className={cn(
      "rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800",
      hover && "transition-all hover:shadow-elevation-2 hover:-translate-y-0.5",
      className
    )}>
      {children}
    </div>
  );
}
```

디자인 시스템 핵심 요소:
1. **디자인 토큰** - 색상, 타이포, 간격, 그림자
2. **기본 컴포넌트** - Button, Input, Badge, Avatar, Card
3. **복합 컴포넌트** - Modal, Dropdown, Toast, Table
4. **레이아웃** - Grid, Stack, Container
5. **문서화** - Storybook으로 컴포넌트 카탈로그'''),

    # ═══ 랜딩 페이지 ═══
    m("랜딩 페이지 디자인 코드 만들어줘 SaaS 서비스용",
'''SaaS 서비스 랜딩 페이지 전체 코드입니다.

```tsx
// app/page.tsx - 랜딩 페이지

// ═══ Hero 섹션 ═══
function HeroSection() {
  return (
    <section className="relative overflow-hidden bg-gradient-to-br from-gray-900 via-blue-900 to-gray-900 pt-20 pb-32">
      {/* 배경 장식 */}
      <div className="absolute inset-0 opacity-20">
        <div className="absolute top-20 left-10 h-72 w-72 rounded-full bg-blue-500 blur-3xl" />
        <div className="absolute bottom-10 right-10 h-96 w-96 rounded-full bg-purple-500 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-7xl px-6 text-center">
        {/* 뱃지 */}
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-4 py-1.5 text-sm text-blue-300">
          <span className="h-2 w-2 rounded-full bg-green-400 animate-pulse" />
          새로운 기능 출시
        </div>

        {/* 제목 */}
        <h1 className="text-display-lg font-bold text-white">
          AI로 업무를
          <br />
          <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
            10배 빠르게
          </span>
        </h1>

        {/* 설명 */}
        <p className="mx-auto mt-6 max-w-2xl text-body-lg text-gray-300">
          화랑 AI가 코딩, 디자인, 문서 작성을 도와드립니다.
          한국어에 최적화된 AI 어시스턴트를 경험하세요.
        </p>

        {/* CTA 버튼 */}
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          <button className="rounded-xl bg-blue-600 px-8 py-3.5 text-lg font-semibold text-white shadow-lg shadow-blue-500/30 transition hover:bg-blue-500 hover:shadow-blue-500/40">
            무료로 시작하기
          </button>
          <button className="flex items-center gap-2 rounded-xl border border-gray-600 px-8 py-3.5 text-lg font-semibold text-gray-300 transition hover:bg-white/5">
            <PlayIcon className="h-5 w-5" />
            데모 보기
          </button>
        </div>

        {/* 스크린샷 */}
        <div className="mt-16 rounded-2xl border border-gray-700/50 bg-gray-800/50 p-2 shadow-2xl backdrop-blur">
          <img
            src="/screenshots/dashboard.png"
            alt="화랑 AI 대시보드 미리보기"
            className="rounded-xl"
          />
        </div>
      </div>
    </section>
  );
}

// ═══ 기능 섹션 ═══
function FeaturesSection() {
  const features = [
    {
      icon: <CodeIcon />,
      title: "코드 생성",
      description: "자연어로 설명하면 완성도 높은 코드를 생성합니다. Python, TypeScript, SQL 등 50+ 언어 지원.",
    },
    {
      icon: <PaletteIcon />,
      title: "디자인 도움",
      description: "UI 컴포넌트, 레이아웃, 색상 팔레트를 제안합니다. Tailwind CSS 코드로 바로 적용 가능.",
    },
    {
      icon: <ShieldIcon />,
      title: "보안 검사",
      description: "코드의 보안 취약점을 자동으로 발견하고 수정 방법을 안내합니다.",
    },
    {
      icon: <GlobeIcon />,
      title: "한국어 최적화",
      description: "한국어 이해도가 가장 높은 AI. 전문 용어도 정확하게 이해합니다.",
    },
  ];

  return (
    <section className="py-24 bg-white dark:bg-gray-900">
      <div className="mx-auto max-w-7xl px-6">
        <div className="text-center">
          <p className="text-sm font-semibold text-blue-600">기능</p>
          <h2 className="mt-2 text-heading-1 font-bold">
            모든 작업을 하나의 AI로
          </h2>
          <p className="mt-4 text-body-lg text-gray-600 dark:text-gray-400">
            개발부터 디자인까지, 화랑 AI가 모두 도와드립니다.
          </p>
        </div>

        <div className="mt-16 grid grid-cols-1 gap-8 md:grid-cols-2 lg:grid-cols-4">
          {features.map((feature, i) => (
            <div
              key={i}
              className="group rounded-2xl border border-gray-200 p-6 transition-all hover:border-blue-500/50 hover:shadow-elevation-2 dark:border-gray-700"
            >
              <div className="mb-4 inline-flex rounded-xl bg-blue-100 p-3 text-blue-600 dark:bg-blue-900/50 dark:text-blue-400 transition-transform group-hover:scale-110">
                {feature.icon}
              </div>
              <h3 className="text-heading-3 font-semibold">{feature.title}</h3>
              <p className="mt-2 text-body text-gray-600 dark:text-gray-400">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ═══ 가격 섹션 ═══
function PricingSection() {
  const plans = [
    {
      name: "무료",
      price: "0",
      description: "개인 사용자를 위한 기본 플랜",
      features: ["하루 50회 질문", "기본 코드 생성", "한국어 지원"],
      cta: "무료로 시작",
      highlighted: false,
    },
    {
      name: "프로",
      price: "29,000",
      description: "전문 개발자를 위한 플랜",
      features: ["무제한 질문", "고급 코드 생성", "디자인 도우미", "API 접근", "우선 지원"],
      cta: "프로 시작하기",
      highlighted: true,
    },
    {
      name: "팀",
      price: "99,000",
      description: "팀 협업을 위한 플랜",
      features: ["프로 모든 기능", "팀원 10명", "관리자 대시보드", "SSO 인증", "전담 지원"],
      cta: "팀 시작하기",
      highlighted: false,
    },
  ];

  return (
    <section className="py-24 bg-gray-50 dark:bg-gray-800">
      <div className="mx-auto max-w-7xl px-6">
        <div className="text-center">
          <h2 className="text-heading-1 font-bold">합리적인 가격</h2>
          <p className="mt-4 text-body-lg text-gray-600 dark:text-gray-400">
            필요한 만큼만 사용하세요. 언제든 업그레이드 가능합니다.
          </p>
        </div>

        <div className="mt-16 grid grid-cols-1 gap-8 md:grid-cols-3">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={cn(
                "rounded-2xl p-8 transition-all",
                plan.highlighted
                  ? "bg-blue-600 text-white shadow-xl shadow-blue-500/30 scale-105"
                  : "bg-white border border-gray-200 dark:bg-gray-900 dark:border-gray-700"
              )}
            >
              <h3 className="text-xl font-semibold">{plan.name}</h3>
              <p className={cn(
                "mt-1 text-sm",
                plan.highlighted ? "text-blue-200" : "text-gray-500"
              )}>
                {plan.description}
              </p>
              <div className="mt-6">
                <span className="text-4xl font-bold">₩{plan.price}</span>
                <span className={plan.highlighted ? "text-blue-200" : "text-gray-500"}>
                  /월
                </span>
              </div>
              <ul className="mt-8 space-y-3">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2">
                    <CheckIcon className={cn(
                      "h-5 w-5",
                      plan.highlighted ? "text-blue-200" : "text-green-500"
                    )} />
                    {feature}
                  </li>
                ))}
              </ul>
              <button className={cn(
                "mt-8 w-full rounded-xl py-3 font-semibold transition",
                plan.highlighted
                  ? "bg-white text-blue-600 hover:bg-blue-50"
                  : "bg-blue-600 text-white hover:bg-blue-700"
              )}>
                {plan.cta}
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ═══ 전체 페이지 구성 ═══
export default function LandingPage() {
  return (
    <>
      <Header />
      <HeroSection />
      <FeaturesSection />
      <PricingSection />
      <TestimonialsSection />
      <CTASection />
      <Footer />
    </>
  );
}
```

랜딩 페이지 디자인 원칙:
1. **Hero**: 한 문장으로 가치 전달 + 명확한 CTA
2. **기능**: 아이콘 + 짧은 설명 (3~4개)
3. **가격**: 3단계 플랜 (중간 강조)
4. **사회적 증거**: 고객 후기, 로고
5. **CTA**: 페이지 하단에 최종 행동 유도'''),

    # ═══ 대시보드 ═══
    m("관리자 대시보드 UI 디자인 알려줘",
'''관리자 대시보드 레이아웃과 컴포넌트입니다.

```tsx
// ═══ 대시보드 레이아웃 ═══
function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
      {/* 사이드바 */}
      <aside className="hidden md:flex w-64 flex-col border-r border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
        {/* 로고 */}
        <div className="flex h-16 items-center gap-2 border-b px-6">
          <img src="/logo.svg" alt="" className="h-8 w-8" />
          <span className="text-lg font-bold">화랑 Admin</span>
        </div>

        {/* 네비게이션 */}
        <nav className="flex-1 overflow-y-auto p-4 space-y-1">
          <NavItem icon={<HomeIcon />} label="대시보드" href="/admin" active />
          <NavItem icon={<UsersIcon />} label="사용자" href="/admin/users" />
          <NavItem icon={<ChatIcon />} label="대화" href="/admin/conversations" badge={12} />
          <NavItem icon={<ChartIcon />} label="통계" href="/admin/analytics" />
          <NavItem icon={<SettingsIcon />} label="설정" href="/admin/settings" />
        </nav>

        {/* 사용자 정보 */}
        <div className="border-t p-4">
          <div className="flex items-center gap-3">
            <Avatar name="관리자" size="sm" />
            <div>
              <p className="text-sm font-medium">관리자</p>
              <p className="text-xs text-gray-500">admin@hwarang.ai</p>
            </div>
          </div>
        </div>
      </aside>

      {/* 메인 콘텐츠 */}
      <main className="flex-1 overflow-y-auto">
        {/* 헤더 */}
        <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b bg-white/80 backdrop-blur px-6 dark:bg-gray-800/80">
          <h1 className="text-xl font-semibold">대시보드</h1>
          <div className="flex items-center gap-4">
            <button className="relative">
              <BellIcon className="h-5 w-5 text-gray-500" />
              <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-red-500 text-xs text-white flex items-center justify-center">
                3
              </span>
            </button>
            <ThemeToggle />
          </div>
        </header>

        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}

// ═══ 통계 카드 ═══
function StatsCards() {
  const stats = [
    { label: "전체 사용자", value: "12,847", change: "+12.5%", trend: "up", icon: <UsersIcon /> },
    { label: "오늘 대화", value: "1,423", change: "+8.2%", trend: "up", icon: <ChatIcon /> },
    { label: "API 호출", value: "89,234", change: "-2.1%", trend: "down", icon: <ServerIcon /> },
    { label: "평균 응답시간", value: "1.2초", change: "-15%", trend: "up", icon: <ClockIcon /> },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat) => (
        <div key={stat.label} className="rounded-xl border bg-white p-6 dark:bg-gray-800 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div className="rounded-lg bg-blue-100 p-2 text-blue-600 dark:bg-blue-900/50">
              {stat.icon}
            </div>
            <span className={cn(
              "text-sm font-medium",
              stat.trend === "up" ? "text-green-600" : "text-red-600"
            )}>
              {stat.change}
            </span>
          </div>
          <div className="mt-4">
            <p className="text-2xl font-bold">{stat.value}</p>
            <p className="text-sm text-gray-500">{stat.label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ═══ 데이터 테이블 ═══
function DataTable() {
  return (
    <div className="rounded-xl border bg-white dark:bg-gray-800 dark:border-gray-700">
      <div className="flex items-center justify-between border-b p-4">
        <h3 className="font-semibold">최근 사용자</h3>
        <div className="flex gap-2">
          <input
            placeholder="검색..."
            className="rounded-lg border px-3 py-1.5 text-sm"
          />
          <button className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm text-white">
            내보내기
          </button>
        </div>
      </div>
      <table className="w-full">
        <thead>
          <tr className="border-b text-left text-sm text-gray-500">
            <th className="p-4">사용자</th>
            <th className="p-4">이메일</th>
            <th className="p-4">가입일</th>
            <th className="p-4">상태</th>
            <th className="p-4">작업</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id} className="border-b hover:bg-gray-50 dark:hover:bg-gray-700/50">
              <td className="p-4">
                <div className="flex items-center gap-3">
                  <Avatar name={user.name} size="sm" />
                  <span className="font-medium">{user.name}</span>
                </div>
              </td>
              <td className="p-4 text-gray-500">{user.email}</td>
              <td className="p-4 text-gray-500">{user.createdAt}</td>
              <td className="p-4">
                <Badge variant={user.active ? "success" : "default"}>
                  {user.active ? "활성" : "비활성"}
                </Badge>
              </td>
              <td className="p-4">
                <button className="text-sm text-blue-600 hover:underline">수정</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* 페이지네이션 */}
      <div className="flex items-center justify-between border-t p-4">
        <span className="text-sm text-gray-500">1-10 / 총 247건</span>
        <div className="flex gap-1">
          <button className="rounded px-3 py-1 text-sm hover:bg-gray-100">이전</button>
          <button className="rounded bg-blue-600 px-3 py-1 text-sm text-white">1</button>
          <button className="rounded px-3 py-1 text-sm hover:bg-gray-100">2</button>
          <button className="rounded px-3 py-1 text-sm hover:bg-gray-100">3</button>
          <button className="rounded px-3 py-1 text-sm hover:bg-gray-100">다음</button>
        </div>
      </div>
    </div>
  );
}
```

대시보드 디자인 원칙:
1. **정보 계층**: 중요한 지표를 상단에 (KPI 카드)
2. **일관성**: 동일한 카드/테이블 스타일
3. **여백**: 컴포넌트 간 충분한 간격
4. **색상**: 의미 있는 색상 사용 (성공=초록, 경고=노랑)
5. **다크모드**: 필수 지원 (눈 피로 감소)'''),

    # ═══ 색상 팔레트 ═══
    m("웹 디자인 색상 팔레트 추천해줘",
'''프로젝트 유형별 색상 팔레트 추천입니다.

```
═══ 1. 모던 테크 (AI/SaaS) ═══
기본: #3B82F6 (Blue 500)   - 신뢰, 기술
강조: #8B5CF6 (Purple 500)  - 혁신, 프리미엄
배경: #0F172A (Slate 900)   - 다크 배경
텍스트: #F8FAFC (Slate 50)  - 밝은 텍스트

#0F172A → #1E293B → #334155 → #F8FAFC
배경      카드      보조      텍스트

═══ 2. 클린 비즈니스 ═══
기본: #2563EB (Blue 600)
강조: #059669 (Green 600)
배경: #FFFFFF
텍스트: #1E293B

#FFFFFF → #F8FAFC → #2563EB → #1E293B
배경      카드      액센트    텍스트

═══ 3. 따뜻한 브랜드 ═══
기본: #EA580C (Orange 600)
강조: #DC2626 (Red 600)
배경: #FFFBEB (Amber 50)
텍스트: #451A03

═══ 4. 자연/건강 ═══
기본: #059669 (Emerald 600)
강조: #0D9488 (Teal 600)
배경: #F0FDF4 (Green 50)
텍스트: #14532D
```

```tsx
// CSS 변수로 테마 구현
// globals.css

:root {
  /* 라이트 모드 */
  --color-bg-primary: 255 255 255;
  --color-bg-secondary: 248 250 252;
  --color-bg-tertiary: 241 245 249;

  --color-text-primary: 15 23 42;
  --color-text-secondary: 100 116 139;
  --color-text-tertiary: 148 163 184;

  --color-border: 226 232 240;

  --color-brand: 59 130 246;
  --color-brand-hover: 37 99 235;
}

.dark {
  --color-bg-primary: 15 23 42;
  --color-bg-secondary: 30 41 59;
  --color-bg-tertiary: 51 65 85;

  --color-text-primary: 248 250 252;
  --color-text-secondary: 148 163 184;
  --color-text-tertiary: 100 116 139;

  --color-border: 51 65 85;
}
```

색상 선택 규칙:
1. **60-30-10 법칙**: 배경 60%, 보조 30%, 강조 10%
2. **대비 비율**: 텍스트/배경 최소 4.5:1 (WCAG AA)
3. **의미 있는 색상**: 성공=초록, 경고=노랑, 에러=빨강, 정보=파랑
4. **채도 일관성**: 같은 채도 레벨의 색상 조합
5. **다크모드**: 밝기만 반전, 채도는 약간 낮추기'''),

    # ═══ 타이포그래피 ═══
    m("웹 타이포그래피 가이드 알려줘",
'''읽기 좋은 웹 타이포그래피 설정입니다.

```css
/* ═══ 폰트 설정 ═══ */

/* 1. 한국어 최적 폰트 스택 */
body {
  font-family:
    "Pretendard Variable",
    "Pretendard",
    -apple-system,
    BlinkMacSystemFont,
    system-ui,
    "Noto Sans KR",
    "맑은 고딕",
    sans-serif;
}

/* 코드용 폰트 */
code, pre {
  font-family:
    "JetBrains Mono",
    "Fira Code",
    "D2Coding",
    monospace;
}

/* 2. 타입 스케일 (1.25 비율) */
/*
  Display:  2.488rem (40px)
  H1:       2.074rem (33px)
  H2:       1.728rem (28px)
  H3:       1.44rem  (23px)
  H4:       1.2rem   (19px)
  Body:     1rem     (16px)
  Small:    0.833rem (13px)
  Caption:  0.694rem (11px)
*/

/* 3. 가독성 최적 설정 */
body {
  font-size: 16px;           /* 기본 크기 */
  line-height: 1.6;          /* 본문 줄 간격 */
  letter-spacing: -0.01em;   /* 한국어 자간 미세 조정 */
  word-break: keep-all;      /* 한국어 단어 단위 줄바꿈 */
  overflow-wrap: break-word;
}

h1, h2, h3, h4 {
  line-height: 1.3;          /* 제목은 좁은 줄 간격 */
  letter-spacing: -0.02em;   /* 제목은 좁은 자간 */
  font-weight: 700;
}

p {
  max-width: 70ch;           /* 최적 읽기 폭 (한 줄 70자) */
}

/* 4. 반응형 타이포그래피 */
html {
  /* 뷰포트에 따라 자동 조정 */
  font-size: clamp(14px, 1vw + 10px, 18px);
}

/* 또는 미디어 쿼리 */
@media (max-width: 768px) {
  h1 { font-size: 1.75rem; }
  h2 { font-size: 1.5rem; }
  body { font-size: 15px; }
}
```

```tsx
// Tailwind CSS 타이포그래피 플러그인
// pnpm add @tailwindcss/typography

// 마크다운/HTML 콘텐츠에 자동 스타일 적용
<article className="prose prose-lg dark:prose-invert max-w-none">
  <h1>제목</h1>
  <p>본문 텍스트...</p>
  <pre><code>코드 블록</code></pre>
  <blockquote>인용문</blockquote>
</article>

// prose 커스터마이징
// tailwind.config.ts
typography: {
  DEFAULT: {
    css: {
      maxWidth: "70ch",
      color: "var(--tw-prose-body)",
      a: {
        color: "#3b82f6",
        textDecoration: "none",
        "&:hover": { textDecoration: "underline" },
      },
      "code::before": { content: '""' },
      "code::after": { content: '""' },
    },
  },
},
```

타이포그래피 핵심:
1. **폰트**: Pretendard (한국어 최적)
2. **크기**: 본문 16px, 제목은 1.25배 스케일
3. **줄 간격**: 본문 1.6, 제목 1.3
4. **읽기 폭**: 최대 70자 (max-width: 70ch)
5. **자간**: 한국어는 -0.01em ~ -0.02em
6. **줄바꿈**: `word-break: keep-all` (한국어 필수)'''),

    # ═══ 반응형 디자인 ═══
    m("반응형 웹 디자인 실무 패턴 알려줘",
'''모바일 퍼스트 반응형 디자인 패턴입니다.

```tsx
// ═══ 1. 반응형 네비게이션 ═══
"use client";
import { useState } from "react";

function ResponsiveNav() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <nav className="border-b bg-white dark:bg-gray-900">
      <div className="mx-auto max-w-7xl px-4">
        <div className="flex h-16 items-center justify-between">
          {/* 로고 */}
          <a href="/" className="text-xl font-bold">화랑 AI</a>

          {/* 데스크탑 메뉴 */}
          <div className="hidden md:flex items-center gap-8">
            <a href="/features" className="text-gray-600 hover:text-gray-900">기능</a>
            <a href="/pricing" className="text-gray-600 hover:text-gray-900">가격</a>
            <a href="/docs" className="text-gray-600 hover:text-gray-900">문서</a>
            <button className="rounded-lg bg-blue-600 px-4 py-2 text-white">
              시작하기
            </button>
          </div>

          {/* 모바일 햄버거 */}
          <button
            className="md:hidden p-2"
            onClick={() => setIsOpen(!isOpen)}
            aria-label="메뉴 열기"
          >
            {isOpen ? <XIcon /> : <MenuIcon />}
          </button>
        </div>

        {/* 모바일 메뉴 */}
        {isOpen && (
          <div className="md:hidden border-t py-4 space-y-2">
            <a href="/features" className="block px-4 py-2 rounded hover:bg-gray-100">
              기능
            </a>
            <a href="/pricing" className="block px-4 py-2 rounded hover:bg-gray-100">
              가격
            </a>
            <a href="/docs" className="block px-4 py-2 rounded hover:bg-gray-100">
              문서
            </a>
            <button className="w-full rounded-lg bg-blue-600 px-4 py-2 text-white mt-2">
              시작하기
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}

// ═══ 2. 반응형 그리드 패턴 ═══
function ResponsiveGrid() {
  return (
    <>
      {/* 카드 그리드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {items.map(item => <Card key={item.id} {...item} />)}
      </div>

      {/* 사이드바 + 콘텐츠 */}
      <div className="flex flex-col lg:flex-row gap-6">
        <aside className="lg:w-64 lg:shrink-0">
          <FilterPanel />
        </aside>
        <main className="flex-1 min-w-0">
          <ContentArea />
        </main>
      </div>

      {/* 2열 폼 레이아웃 */}
      <form className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div><label>이름</label><input /></div>
        <div><label>이메일</label><input /></div>
        <div className="md:col-span-2"><label>메시지</label><textarea /></div>
      </form>
    </>
  );
}

// ═══ 3. 반응형 이미지 ═══
function ResponsiveImage() {
  return (
    <>
      {/* 비율 유지 이미지 */}
      <div className="relative aspect-video w-full overflow-hidden rounded-xl">
        <img
          src="/hero.jpg"
          alt="설명"
          className="absolute inset-0 h-full w-full object-cover"
          loading="lazy"
          sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
        />
      </div>

      {/* Next.js Image (자동 최적화) */}
      <Image
        src="/photo.jpg"
        alt="사진"
        width={800}
        height={600}
        className="w-full h-auto rounded-xl"
        sizes="(max-width: 768px) 100vw, 50vw"
        priority={false}
      />
    </>
  );
}

// ═══ 4. 반응형 텍스트 ═══
function ResponsiveText() {
  return (
    <h1 className="
      text-2xl      /* 모바일 */
      sm:text-3xl   /* 640px+ */
      md:text-4xl   /* 768px+ */
      lg:text-5xl   /* 1024px+ */
      font-bold
    ">
      화랑 AI와 함께하세요
    </h1>
  );
}
```

반응형 브레이크포인트:
| 접두사 | 최소 너비 | 대상 |
|--------|-----------|------|
| (없음) | 0px | 모바일 |
| `sm:` | 640px | 큰 모바일 |
| `md:` | 768px | 태블릿 |
| `lg:` | 1024px | 데스크탑 |
| `xl:` | 1280px | 와이드 |
| `2xl:` | 1536px | 울트라와이드 |

원칙: 모바일 퍼스트 → 작은 화면부터 디자인 후 점진적 확장.'''),

    # ═══ 로딩/스켈레톤 ═══
    m("로딩 상태 UI 패턴 알려줘 스켈레톤 포함",
'''사용자 경험을 높이는 로딩 상태 UI 패턴입니다.

```tsx
// ═══ 1. 스켈레톤 로더 ═══
function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn(
      "animate-pulse rounded-md bg-gray-200 dark:bg-gray-700",
      className
    )} />
  );
}

// 카드 스켈레톤
function CardSkeleton() {
  return (
    <div className="rounded-xl border p-6 space-y-4">
      {/* 아바타 + 이름 */}
      <div className="flex items-center gap-3">
        <Skeleton className="h-10 w-10 rounded-full" />
        <div className="space-y-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-24" />
        </div>
      </div>
      {/* 본문 */}
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
      {/* 이미지 */}
      <Skeleton className="h-48 w-full rounded-lg" />
    </div>
  );
}

// 테이블 스켈레톤
function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="rounded-xl border">
      <div className="border-b p-4">
        <Skeleton className="h-6 w-32" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 border-b p-4">
          <Skeleton className="h-8 w-8 rounded-full" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
      ))}
    </div>
  );
}

// ═══ 2. Next.js loading.tsx (자동 적용) ═══
// app/users/loading.tsx
export default function Loading() {
  return (
    <div className="space-y-6">
      {/* 통계 카드 스켈레톤 */}
      <div className="grid grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl border p-6">
            <Skeleton className="h-4 w-20 mb-2" />
            <Skeleton className="h-8 w-24" />
          </div>
        ))}
      </div>
      {/* 테이블 스켈레톤 */}
      <TableSkeleton />
    </div>
  );
}

// ═══ 3. 스피너 ═══
function Spinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "h-4 w-4", md: "h-8 w-8", lg: "h-12 w-12" };
  return (
    <svg
      className={cn("animate-spin text-blue-600", sizes[size])}
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        className="opacity-25"
        cx="12" cy="12" r="10"
        stroke="currentColor" strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

// ═══ 4. 프로그레스 바 ═══
function ProgressBar({ value, max = 100 }: { value: number; max?: number }) {
  const percentage = Math.min((value / max) * 100, 100);
  return (
    <div className="h-2 w-full rounded-full bg-gray-200 dark:bg-gray-700">
      <div
        className="h-full rounded-full bg-blue-600 transition-all duration-300"
        style={{ width: `${percentage}%` }}
        role="progressbar"
        aria-valuenow={value}
        aria-valuemax={max}
      />
    </div>
  );
}

// ═══ 5. 빈 상태 ═══
function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="rounded-full bg-gray-100 p-4 dark:bg-gray-800">
        <InboxIcon className="h-10 w-10 text-gray-400" />
      </div>
      <h3 className="mt-4 text-lg font-semibold">{title}</h3>
      <p className="mt-2 max-w-md text-gray-500">{description}</p>
      {action && (
        <button className="mt-6 rounded-lg bg-blue-600 px-4 py-2 text-white">
          {action.label}
        </button>
      )}
    </div>
  );
}
```

로딩 UI 원칙:
1. **스켈레톤**: 레이아웃 구조를 미리 보여줌 (최고의 UX)
2. **스피너**: 짧은 작업 (1-3초)
3. **프로그레스**: 진행률을 알 수 있는 작업
4. **빈 상태**: 데이터가 없을 때 안내 + 행동 유도
5. **낙관적 업데이트**: 서버 응답 전에 UI 먼저 업데이트'''),

    # ═══ 토스트/알림 ═══
    m("토스트 알림 컴포넌트 만들어줘",
'''Sonner 라이브러리로 간단하게 구현합니다.

```tsx
// ═══ 1. Sonner 설정 (가장 간단) ═══
// pnpm add sonner

// app/layout.tsx
import { Toaster } from "sonner";

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        {children}
        <Toaster
          position="top-right"
          toastOptions={{
            className: "dark:bg-gray-800 dark:text-white",
            duration: 4000,
          }}
          richColors
        />
      </body>
    </html>
  );
}

// 사용법
import { toast } from "sonner";

// 기본
toast("저장되었습니다");

// 성공
toast.success("사용자가 생성되었습니다");

// 에러
toast.error("저장에 실패했습니다");

// 프로미스 (로딩 → 성공/실패 자동)
toast.promise(saveUser(data), {
  loading: "저장 중...",
  success: "저장 완료!",
  error: "저장 실패",
});

// 커스텀 액션
toast("파일을 삭제할까요?", {
  action: {
    label: "삭제",
    onClick: () => deleteFile(fileId),
  },
  cancel: {
    label: "취소",
  },
});

// 되돌리기 (Undo)
toast("메시지가 삭제되었습니다", {
  action: {
    label: "되돌리기",
    onClick: () => restoreMessage(messageId),
  },
  duration: 5000,
});

// ═══ 2. 커스텀 토스트 (직접 구현) ═══
import { AnimatePresence, motion } from "framer-motion";

function Toast({ id, type, message, onDismiss }) {
  const icons = {
    success: <CheckCircleIcon className="text-green-500" />,
    error: <XCircleIcon className="text-red-500" />,
    info: <InfoIcon className="text-blue-500" />,
    warning: <AlertIcon className="text-yellow-500" />,
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -20, scale: 0.95 }}
      className="flex items-center gap-3 rounded-lg border bg-white px-4 py-3 shadow-elevation-3 dark:bg-gray-800"
    >
      {icons[type]}
      <p className="text-sm font-medium">{message}</p>
      <button
        onClick={() => onDismiss(id)}
        className="ml-auto text-gray-400 hover:text-gray-600"
      >
        <XIcon className="h-4 w-4" />
      </button>
    </motion.div>
  );
}
```

토스트 사용 가이드:
- **성공**: 저장/생성/삭제 완료
- **에러**: 요청 실패 (구체적 메시지)
- **경고**: 주의가 필요한 상황
- **정보**: 일반적인 안내
- `duration`: 기본 4초, 중요하면 더 길게
- 되돌리기(Undo)가 가능하면 항상 제공'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/design.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 웹 디자인/UI/UX 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  디자인: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
