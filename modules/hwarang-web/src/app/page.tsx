"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useTheme } from "@/components/providers/theme-provider";

export default function LandingPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();

  // 로그인된 유저는 바로 채팅으로
  if (session) {
    router.push("/chat");
    return null;
  }

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>

      {/* 네비게이션 */}
      <nav className="fixed top-0 w-full z-50 glass border-b" style={{ borderColor: "var(--border)", background: "color-mix(in srgb, var(--background) 80%, transparent)" }}>
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg gradient-bg flex items-center justify-center">
              <span className="text-white text-sm font-bold">H</span>
            </div>
            <span className="text-lg font-bold gradient-text">화랑 AI</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/chat" className="text-sm hover:opacity-70 transition-opacity hidden sm:inline" style={{ color: "var(--muted-foreground)" }}>AI 채팅</Link>
            <Link href="/pricing" className="text-sm hover:opacity-70 transition-opacity" style={{ color: "var(--muted-foreground)" }}>요금제</Link>
            <Link href="/community" className="text-sm hover:opacity-70 transition-opacity hidden sm:inline" style={{ color: "var(--muted-foreground)" }}>커뮤니티</Link>
            <button onClick={toggleTheme} className="p-2 rounded-lg hover:bg-[var(--muted)]">
              {theme === "light" ? "🌙" : "☀️"}
            </button>
            <Link href="/login" className="px-4 py-2 rounded-xl text-sm font-medium text-white gradient-bg hover:shadow-lg transition-all">
              시작하기
            </Link>
          </div>
        </div>
      </nav>

      {/* 히어로 섹션 */}
      <section className="relative pt-32 pb-20 overflow-hidden">
        {/* 배경 장식 */}
        <div className="absolute inset-0 overflow-hidden">
          <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full blur-3xl opacity-20" style={{ background: "var(--primary)" }} />
          <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full blur-3xl opacity-10" style={{ background: "var(--primary)" }} />
        </div>

        <div className="relative max-w-4xl mx-auto px-4 text-center">
          {/* 뱃지 */}
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border mb-8 text-sm"
            style={{ borderColor: "var(--border)", background: "var(--muted)" }}>
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            32B 모델로 서비스 중
          </div>

          {/* 메인 카피 */}
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold leading-tight mb-6">
            한국어를 가장 잘 이해하는
            <br />
            <span className="gradient-text">AI 코딩 어시스턴트</span>
          </h1>

          <p className="text-lg sm:text-xl mb-10 max-w-2xl mx-auto leading-relaxed" style={{ color: "var(--muted-foreground)" }}>
            코딩, 법률, 세무 전문 AI.
            <br />
            한국어 주석, 한국 법령, 한국 세법을 정확히 이해합니다.
          </p>

          {/* CTA */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
            <Link href="/login"
              className="px-8 py-4 rounded-2xl text-base font-semibold text-white gradient-bg hover:shadow-xl transition-all hover:-translate-y-0.5">
              무료로 시작하기 →
            </Link>
            <Link href="/pricing"
              className="px-8 py-4 rounded-2xl text-base font-medium border hover:shadow-md transition-all"
              style={{ borderColor: "var(--border)" }}>
              요금제 보기
            </Link>
          </div>

          {/* 데모 스크린샷 */}
          <div className="relative max-w-3xl mx-auto rounded-2xl overflow-hidden border shadow-2xl"
            style={{ borderColor: "var(--border)" }}>
            <div className="p-4" style={{ background: "var(--muted)" }}>
              <div className="flex gap-2 mb-3">
                <div className="w-3 h-3 rounded-full bg-red-400" />
                <div className="w-3 h-3 rounded-full bg-yellow-400" />
                <div className="w-3 h-3 rounded-full bg-green-400" />
              </div>
              <div className="rounded-xl p-6" style={{ background: "var(--background)" }}>
                <div className="flex gap-3 mb-4">
                  <div className="w-8 h-8 rounded-xl gradient-bg flex items-center justify-center text-white text-xs font-bold">H</div>
                  <div className="flex-1 rounded-2xl p-4" style={{ background: "var(--muted)" }}>
                    <p className="text-sm">파이썬으로 REST API 서버를 만들어줘. FastAPI 사용하고 한국어 주석도 달아줘.</p>
                  </div>
                </div>
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-xl flex items-center justify-center text-xs font-bold" style={{ background: "var(--accent)", color: "var(--primary)" }}>AI</div>
                  <div className="flex-1 rounded-2xl p-4" style={{ background: "var(--muted)" }}>
                    <p className="text-sm mb-2">네, FastAPI로 REST API 서버를 만들어 드리겠습니다.</p>
                    <div className="rounded-lg p-3 text-xs font-mono" style={{ background: "var(--background)" }}>
                      <span style={{ color: "#8b5cf6" }}>from</span> fastapi <span style={{ color: "#8b5cf6" }}>import</span> FastAPI<br/>
                      <br/>
                      <span style={{ color: "#6b7280" }}># 앱 초기화</span><br/>
                      app = FastAPI(title=<span style={{ color: "#22c55e" }}>"화랑 API"</span>)<br/>
                      <br/>
                      <span style={{ color: "#8b5cf6" }}>@</span>app.get(<span style={{ color: "#22c55e" }}>"/"</span>)<br/>
                      <span style={{ color: "#8b5cf6" }}>async def</span> <span style={{ color: "#3b82f6" }}>루트</span>():<br/>
                      &nbsp;&nbsp;&nbsp;&nbsp;<span style={{ color: "#6b7280" }}># 메인 엔드포인트</span><br/>
                      &nbsp;&nbsp;&nbsp;&nbsp;<span style={{ color: "#8b5cf6" }}>return</span> {`{"message": "안녕하세요!"}`}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 기능 섹션 */}
      <section className="py-20" style={{ background: "var(--muted)" }}>
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-3xl font-bold text-center mb-4">왜 화랑 AI인가?</h2>
          <p className="text-center mb-12" style={{ color: "var(--muted-foreground)" }}>
            대기업 AI가 못하는 것을 합니다
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                icon: "💻",
                title: "한국어 코딩",
                desc: "한국어 주석, 변수명 제안, 카카오/네이버 API 코드를 자연스럽게 작성합니다",
                highlight: "GPT-3.5보다 한국어 코딩이 자연스러움",
              },
              {
                icon: "⚖️",
                title: "법률 전문",
                desc: "한국 법령과 판례를 검색하고, 출처를 인용하며 답변합니다. 환각이 없습니다.",
                highlight: "법령 인용 정확도 95%+",
              },
              {
                icon: "💰",
                title: "세무 전문",
                desc: "양도세, 소득세, 부가세를 단계별로 계산하고 관련 세법 조항을 안내합니다.",
                highlight: "세무사처럼 단계별 계산",
              },
            ].map((f) => (
              <div key={f.title} className="rounded-2xl p-6 border hover:shadow-lg transition-all"
                style={{ background: "var(--background)", borderColor: "var(--border)" }}>
                <span className="text-3xl mb-4 block">{f.icon}</span>
                <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
                <p className="text-sm mb-3" style={{ color: "var(--muted-foreground)" }}>{f.desc}</p>
                <span className="text-xs px-2 py-1 rounded-full" style={{ background: "var(--accent)", color: "var(--primary)" }}>
                  {f.highlight}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 플랫폼 섹션 */}
      <section className="py-20">
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-3xl font-bold text-center mb-4">어디서든 사용하세요</h2>
          <p className="text-center mb-12" style={{ color: "var(--muted-foreground)" }}>
            웹, VS Code, CLI, 모바일 — 하나의 계정으로
          </p>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { icon: "🌐", name: "웹 채팅", desc: "hwarang.ai" },
              { icon: "💻", name: "VS Code", desc: "확장 프로그램" },
              { icon: "⌨️", name: "CLI", desc: "터미널 에이전트" },
              { icon: "🔌", name: "API", desc: "개발자 통합" },
            ].map((p) => (
              <div key={p.name} className="rounded-2xl p-6 border text-center hover:shadow-md transition-all"
                style={{ borderColor: "var(--border)" }}>
                <span className="text-3xl mb-3 block">{p.icon}</span>
                <div className="font-semibold text-sm">{p.name}</div>
                <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>{p.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 토큰 경제 섹션 */}
      <section className="py-20" style={{ background: "var(--muted)" }}>
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold mb-4">GPU를 나누면 토큰이 됩니다</h2>
          <p className="mb-8" style={{ color: "var(--muted-foreground)" }}>
            놀고 있는 GPU로 AI를 함께 만들고, 토큰으로 무료로 사용하세요
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="rounded-2xl p-6 border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
              <span className="text-2xl mb-2 block">💳</span>
              <div className="font-semibold mb-1">결제로 구매</div>
              <div className="text-sm" style={{ color: "var(--muted-foreground)" }}>필요한 만큼 토큰 충전</div>
            </div>
            <div className="rounded-2xl p-6 border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
              <span className="text-2xl mb-2 block">📋</span>
              <div className="font-semibold mb-1">플랜 구독</div>
              <div className="text-sm" style={{ color: "var(--muted-foreground)" }}>매월 토큰 자동 충전</div>
            </div>
            <div className="rounded-2xl p-6 border" style={{ background: "var(--background)", borderColor: "var(--border)" }}>
              <span className="text-2xl mb-2 block">🖥️</span>
              <div className="font-semibold mb-1">GPU 기여</div>
              <div className="text-sm" style={{ color: "var(--muted-foreground)" }}>놀고 있는 GPU로 토큰 적립</div>
            </div>
          </div>

          <Link href="/community" className="text-sm" style={{ color: "var(--primary)" }}>
            GPU 공유 네트워크 자세히 보기 →
          </Link>
        </div>
      </section>

      {/* 요금제 미리보기 */}
      <section className="py-20">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold mb-4">토큰만 보면 됩니다</h2>
          <p className="mb-12" style={{ color: "var(--muted-foreground)" }}>
            복잡한 요금제 없이, 단순하게
          </p>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            {[
              { name: "Free", tokens: "10K", price: "무료", highlight: false },
              { name: "Starter", tokens: "100K", price: "9,900원/월", highlight: false },
              { name: "Pro", tokens: "500K", price: "29,000원/월", highlight: true },
              { name: "Business", tokens: "2M", price: "99,000원/월", highlight: false },
            ].map((p) => (
              <div key={p.name} className={`rounded-2xl p-5 border ${p.highlight ? "border-2 shadow-md" : ""}`}
                style={{ borderColor: p.highlight ? "var(--primary)" : "var(--border)" }}>
                {p.highlight && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full text-white mb-2 inline-block" style={{ background: "var(--primary)" }}>인기</span>
                )}
                <div className="font-semibold">{p.name}</div>
                <div className="text-2xl font-bold my-2" style={{ color: "var(--primary)" }}>{p.tokens}</div>
                <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>토큰/월</div>
                <div className="text-sm font-medium mt-2">{p.price}</div>
              </div>
            ))}
          </div>

          <Link href="/pricing" className="text-sm" style={{ color: "var(--primary)" }}>
            요금제 자세히 보기 →
          </Link>
        </div>
      </section>

      {/* 커뮤니티 메시지 */}
      <section className="py-20" style={{ background: "var(--muted)" }}>
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold mb-6">혼자서는 무리입니다</h2>
          <p className="text-lg leading-relaxed mb-8" style={{ color: "var(--muted-foreground)" }}>
            한국에서 진짜 쓸만한 AI를 만들고 싶습니다.
            <br />
            같이 만들고, 같이 쓰고, 같이 성장합시다.
            <br />
            <strong style={{ color: "var(--foreground)" }}>그것이 화랑(花郞)입니다.</strong>
          </p>
          <Link href="/login"
            className="px-8 py-4 rounded-2xl text-base font-semibold text-white gradient-bg hover:shadow-xl transition-all hover:-translate-y-0.5 inline-block">
            함께 시작하기 →
          </Link>
        </div>
      </section>

      {/* 푸터 */}
      <footer className="py-12 border-t" style={{ borderColor: "var(--border)" }}>
        <div className="max-w-6xl mx-auto px-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-6 h-6 rounded-md gradient-bg flex items-center justify-center">
                  <span className="text-white text-[10px] font-bold">H</span>
                </div>
                <span className="font-bold">화랑 AI</span>
              </div>
              <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                한국어 특화 AI 플랫폼
                <br />
                (주)퍼시스모어
              </p>
            </div>
            <div>
              <div className="font-semibold text-sm mb-3">서비스</div>
              <div className="space-y-2 text-xs" style={{ color: "var(--muted-foreground)" }}>
                <div><Link href="/chat" className="hover:underline">AI 채팅</Link></div>
                <div><Link href="/pricing" className="hover:underline">요금제</Link></div>
                <div><Link href="/api-keys" className="hover:underline">API</Link></div>
                <div><Link href="/community" className="hover:underline">커뮤니티</Link></div>
              </div>
            </div>
            <div>
              <div className="font-semibold text-sm mb-3">도메인</div>
              <div className="space-y-2 text-xs" style={{ color: "var(--muted-foreground)" }}>
                <div><Link href="/chat" className="hover:underline">코딩 AI</Link></div>
                <div><Link href="/chat" className="hover:underline">법률 AI</Link></div>
                <div><Link href="/chat" className="hover:underline">세무 AI</Link></div>
              </div>
            </div>
            <div>
              <div className="font-semibold text-sm mb-3">회사</div>
              <div className="space-y-2 text-xs" style={{ color: "var(--muted-foreground)" }}>
                <div><Link href="/terms" className="hover:underline">이용약관</Link></div>
                <div><Link href="/privacy" className="hover:underline">개인정보처리방침</Link></div>
                <div><a href="mailto:hello@persismore.com" className="hover:underline">hello@persismore.com</a></div>
              </div>
            </div>
          </div>
          <div className="pt-8 border-t text-center text-xs" style={{ borderColor: "var(--border)", color: "var(--muted-foreground)" }}>
            © 2026 Persismore Inc. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  );
}
