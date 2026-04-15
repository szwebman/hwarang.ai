"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export default function PrivacyPage() {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/legal?type=privacy")
      .then((r) => r.json())
      .then((data) => { if (data.content) setContent(data.content); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      <div className="max-w-3xl mx-auto px-4 py-16">
        <Link href="/" className="text-sm mb-8 inline-block" style={{ color: "var(--primary)" }}>← 홈으로</Link>

        <h1 className="text-3xl font-bold mb-8">개인정보처리방침</h1>

        {loading ? (
          <div className="text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</div>
        ) : content ? (
          <div className="prose prose-sm space-y-4 text-sm" style={{ color: "var(--muted-foreground)" }}
            dangerouslySetInnerHTML={{ __html: content }} />
        ) : (
          <DefaultPrivacy />
        )}
      </div>
    </div>
  );
}

function DefaultPrivacy() {
  return (
    <div className="prose prose-sm space-y-6 text-sm" style={{ color: "var(--muted-foreground)" }}>
      <section>
        <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>1. 개인정보의 수집 항목</h2>
        <p>회사는 서비스 제공을 위해 다음 개인정보를 수집합니다.</p>
        <p><strong>필수 항목:</strong> 이메일, 이름 (소셜 로그인 시 자동 수집)</p>
        <p><strong>자동 수집:</strong> 서비스 이용 기록, 접속 로그, IP 주소</p>
        <p><strong>선택 항목:</strong> 프로필 이미지</p>
      </section>
      <section>
        <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>2. 수집 방법</h2>
        <p>1. Google/카카오 소셜 로그인을 통한 수집</p>
        <p>2. 서비스 이용 과정에서 자동 생성/수집</p>
      </section>
      <section>
        <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>3. 개인정보의 이용 목적</h2>
        <p>1. 회원 관리: 회원 식별, 서비스 이용, 불량 회원 방지</p>
        <p>2. 서비스 제공: AI 응답 생성, 토큰 관리, 결제 처리</p>
        <p>3. 서비스 개선: 이용 통계, 서비스 품질 개선</p>
      </section>
      <section>
        <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>4. 대화 데이터 처리</h2>
        <p>1. AI와의 대화 내용은 서비스 제공 및 품질 개선 목적으로 저장될 수 있습니다.</p>
        <p>2. 대화 내용은 암호화되어 저장됩니다.</p>
        <p>3. 이용자는 언제든지 대화 기록 삭제를 요청할 수 있습니다.</p>
      </section>
      <section>
        <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>5. 개인정보의 보유 및 이용 기간</h2>
        <p>1. 회원 탈퇴 시 즉시 파기 (단, 법령에 따른 보관 의무가 있는 경우 제외)</p>
        <p>2. 결제 기록: 5년 (전자상거래법)</p>
        <p>3. 접속 로그: 3개월 (통신비밀보호법)</p>
      </section>
      <section>
        <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>6. 이용자의 권리</h2>
        <p>요청 방법: hello@persismore.com 또는 서비스 내 설정</p>
      </section>
      <section>
        <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>7. 개인정보 보호책임자</h2>
        <p>성명: (주)퍼시스모어 대표</p>
        <p>이메일: privacy@persismore.com</p>
      </section>
      <p className="pt-8 border-t" style={{ borderColor: "var(--border)" }}>
        시행일: 2026년 4월 15일<br />(주)퍼시스모어
      </p>
    </div>
  );
}
