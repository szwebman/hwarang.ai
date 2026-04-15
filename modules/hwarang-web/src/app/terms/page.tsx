"use client";

import Link from "next/link";

export default function TermsPage() {
  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      <div className="max-w-3xl mx-auto px-4 py-16">
        <Link href="/" className="text-sm mb-8 inline-block" style={{ color: "var(--primary)" }}>← 홈으로</Link>

        <h1 className="text-3xl font-bold mb-8">이용약관</h1>

        <div className="prose prose-sm space-y-6 text-sm" style={{ color: "var(--muted-foreground)" }}>
          <section>
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>제1조 (목적)</h2>
            <p>이 약관은 (주)퍼시스모어(이하 "회사")가 제공하는 화랑 AI 서비스(이하 "서비스")의 이용 조건 및 절차, 회사와 이용자의 권리, 의무 및 책임사항을 규정함을 목적으로 합니다.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>제2조 (정의)</h2>
            <p>1. "서비스"란 회사가 제공하는 AI 기반 코딩, 법률, 세무 어시스턴트 서비스를 말합니다.</p>
            <p>2. "토큰"이란 서비스 이용의 단위로, AI 응답 생성 시 소비되는 크레딧을 말합니다.</p>
            <p>3. "이용자"란 이 약관에 따라 서비스를 이용하는 자를 말합니다.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>제3조 (서비스 내용)</h2>
            <p>1. AI 채팅 서비스 (웹, VS Code, CLI, API)</p>
            <p>2. 코딩, 법률, 세무 도메인 특화 AI</p>
            <p>3. GPU 공유 네트워크 (Hwarang Grid)</p>
            <p>4. 토큰 기반 과금 시스템</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>제4조 (면책 조항)</h2>
            <p>1. 본 서비스는 AI 기술을 기반으로 하며, 생성된 응답의 정확성을 100% 보장하지 않습니다.</p>
            <p>2. 법률/세무 관련 응답은 정보 제공 목적이며, 전문적인 법률 자문이나 세무 상담을 대체하지 않습니다.</p>
            <p>3. 중요한 의사결정은 반드시 해당 분야 전문가와 상담하시기 바랍니다.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>제5조 (토큰 정책)</h2>
            <p>1. 토큰은 플랜 구독, 직접 구매, GPU 기여를 통해 획득할 수 있습니다.</p>
            <p>2. 플랜 토큰은 매월 리셋되며, 미사용 토큰은 이월되지 않습니다.</p>
            <p>3. 구매한 토큰은 유효기간이 없습니다.</p>
            <p>4. 하루 최대 소진량은 플랜별로 제한됩니다.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>제6조 (금지 행위)</h2>
            <p>1. 서비스를 이용한 불법 행위</p>
            <p>2. 타인의 개인정보 수집/유포</p>
            <p>3. 서비스 시스템에 대한 무단 접근</p>
            <p>4. API 키의 무단 공유/재판매</p>
          </section>

          <p className="pt-8 border-t" style={{ borderColor: "var(--border)" }}>
            시행일: 2026년 4월 15일
            <br />
            (주)퍼시스모어
          </p>
        </div>
      </div>
    </div>
  );
}
