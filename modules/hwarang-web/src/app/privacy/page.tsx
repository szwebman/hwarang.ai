"use client";

import Link from "next/link";

export default function PrivacyPage() {
  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      <div className="max-w-3xl mx-auto px-4 py-16">
        <Link href="/" className="text-sm mb-8 inline-block" style={{ color: "var(--primary)" }}>← 홈으로</Link>

        <h1 className="text-3xl font-bold mb-8">개인정보처리방침</h1>

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
            <p>4. 온프레미스 설치 시 대화 데이터는 고객 서버에만 저장됩니다.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>5. GPU 공유 네트워크 (Hwarang Grid)</h2>
            <p>1. Grid 참여 시 GPU 하드웨어 정보가 수집됩니다 (GPU 모델, VRAM 등).</p>
            <p>2. 처리하는 AI 작업 데이터는 암호화되어 전달되며, 참여자의 PC에 저장되지 않습니다.</p>
            <p>3. 토큰 보상 기록은 서비스 운영 목적으로 저장됩니다.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>6. 개인정보의 보유 및 이용 기간</h2>
            <p>1. 회원 탈퇴 시 즉시 파기 (단, 법령에 따른 보관 의무가 있는 경우 제외)</p>
            <p>2. 결제 기록: 5년 (전자상거래법)</p>
            <p>3. 접속 로그: 3개월 (통신비밀보호법)</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>7. 이용자의 권리</h2>
            <p>1. 개인정보 열람, 정정, 삭제 요청</p>
            <p>2. 대화 기록 삭제 요청</p>
            <p>3. 회원 탈퇴</p>
            <p>4. 처리 정지 요청</p>
            <p>요청 방법: hello@persismore.com 또는 서비스 내 설정</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>8. 개인정보 보호책임자</h2>
            <p>성명: (주)퍼시스모어 대표</p>
            <p>이메일: privacy@persismore.com</p>
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
