"use client";

import { useEffect, useState } from "react";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function LegalPage() {
  const [tab, setTab] = useState<"terms" | "privacy">("terms");
  const [terms, setTerms] = useState("");
  const [privacy, setPrivacy] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [currentRole, setCurrentRole] = useState("");

  useEffect(() => {
    try {
      const raw = localStorage.getItem("admin_user");
      if (raw) setCurrentRole(JSON.parse(raw).role || "");
    } catch {}
    fetchLegal();
  }, []);

  const fetchLegal = async () => {
    try {
      const resp = await fetch("/api/legal", { headers: authHeaders() });
      if (resp.ok) {
        const data = await resp.json();
        setTerms(data.terms || DEFAULT_TERMS);
        setPrivacy(data.privacy || DEFAULT_PRIVACY);
      }
    } catch {}
    setLoading(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const resp = await fetch("/api/legal", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ terms, privacy }),
      });
      if (resp.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      } else {
        const data = await resp.json();
        alert(data.error || "저장 실패");
      }
    } catch {}
    setSaving(false);
  };

  return (
    <div className="p-6 lg:p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">약관 관리</h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted-foreground)" }}>이용약관 및 개인정보처리방침 편집</p>
        </div>
        {currentRole === "SUPER_ADMIN" && (
          <button onClick={handleSave} disabled={saving}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50"
            style={{ background: saved ? "#16a34a" : "var(--primary)" }}>
            {saving ? "저장 중..." : saved ? "저장 완료!" : "저장"}
          </button>
        )}
      </div>

      {/* 탭 */}
      <div className="flex gap-1 mb-6 p-1 rounded-lg inline-flex" style={{ background: "var(--muted)" }}>
        <button onClick={() => setTab("terms")}
          className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
          style={{
            background: tab === "terms" ? "var(--background)" : "transparent",
            color: tab === "terms" ? "var(--foreground)" : "var(--muted-foreground)",
          }}>
          이용약관
        </button>
        <button onClick={() => setTab("privacy")}
          className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
          style={{
            background: tab === "privacy" ? "var(--background)" : "transparent",
            color: tab === "privacy" ? "var(--foreground)" : "var(--muted-foreground)",
          }}>
          개인정보처리방침
        </button>
      </div>

      {/* 안내 */}
      <div className="rounded-lg p-3 mb-4 text-xs" style={{ background: "var(--accent)", color: "var(--accent-foreground)" }}>
        HTML 태그를 사용할 수 있습니다. 예: &lt;h2&gt;제목&lt;/h2&gt;, &lt;p&gt;내용&lt;/p&gt;, &lt;strong&gt;강조&lt;/strong&gt;
      </div>

      {/* 에디터 */}
      {loading ? (
        <div className="text-center py-12 text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</div>
      ) : (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <textarea
            value={tab === "terms" ? terms : privacy}
            onChange={(e) => tab === "terms" ? setTerms(e.target.value) : setPrivacy(e.target.value)}
            className="w-full h-[600px] p-5 text-sm font-mono resize-none border-none outline-none"
            style={{ background: "var(--background)" }}
            placeholder={tab === "terms" ? "이용약관 내용을 입력하세요..." : "개인정보처리방침 내용을 입력하세요..."}
            readOnly={currentRole !== "SUPER_ADMIN"}
          />
        </div>
      )}

      {/* 미리보기 */}
      <div className="mt-6">
        <h3 className="font-semibold mb-3">미리보기</h3>
        <div className="rounded-xl border p-6 prose prose-sm max-w-none" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div dangerouslySetInnerHTML={{ __html: tab === "terms" ? terms : privacy }} />
        </div>
      </div>
    </div>
  );
}

const DEFAULT_TERMS = `<h2>제1조 (목적)</h2>
<p>이 약관은 (주)퍼시스모어(이하 "회사")가 제공하는 화랑 AI 서비스(이하 "서비스")의 이용 조건 및 절차, 회사와 이용자의 권리, 의무 및 책임사항을 규정함을 목적으로 합니다.</p>

<h2>제2조 (정의)</h2>
<p>1. "서비스"란 회사가 제공하는 AI 기반 코딩, 법률, 세무 어시스턴트 서비스를 말합니다.</p>
<p>2. "토큰"이란 서비스 이용의 단위로, AI 응답 생성 시 소비되는 크레딧을 말합니다.</p>
<p>3. "이용자"란 이 약관에 따라 서비스를 이용하는 자를 말합니다.</p>

<h2>제3조 (서비스 내용)</h2>
<p>1. AI 채팅 서비스 (웹, VS Code, CLI, API)</p>
<p>2. 코딩, 법률, 세무 도메인 특화 AI</p>
<p>3. GPU 공유 네트워크 (Hwarang Grid)</p>
<p>4. 토큰 기반 과금 시스템</p>

<h2>제4조 (면책 조항)</h2>
<p>1. 본 서비스는 AI 기술을 기반으로 하며, 생성된 응답의 정확성을 100% 보장하지 않습니다.</p>
<p>2. 법률/세무 관련 응답은 정보 제공 목적이며, 전문적인 법률 자문이나 세무 상담을 대체하지 않습니다.</p>
<p>3. 중요한 의사결정은 반드시 해당 분야 전문가와 상담하시기 바랍니다.</p>

<h2>제5조 (토큰 정책)</h2>
<p>1. 토큰은 플랜 구독, 직접 구매, GPU 기여를 통해 획득할 수 있습니다.</p>
<p>2. 플랜 토큰은 매월 리셋되며, 미사용 토큰은 이월되지 않습니다.</p>
<p>3. 구매한 토큰은 유효기간이 없습니다.</p>
<p>4. 하루 최대 소진량은 플랜별로 제한됩니다.</p>

<h2>제6조 (금지 행위)</h2>
<p>1. 서비스를 이용한 불법 행위</p>
<p>2. 타인의 개인정보 수집/유포</p>
<p>3. 서비스 시스템에 대한 무단 접근</p>
<p>4. API 키의 무단 공유/재판매</p>

<p><br/>시행일: 2026년 4월 15일<br/>(주)퍼시스모어</p>`;

const DEFAULT_PRIVACY = `<h2>1. 개인정보의 수집 항목</h2>
<p>회사는 서비스 제공을 위해 다음 개인정보를 수집합니다.</p>
<p><strong>필수 항목:</strong> 이메일, 이름 (소셜 로그인 시 자동 수집)</p>
<p><strong>자동 수집:</strong> 서비스 이용 기록, 접속 로그, IP 주소</p>
<p><strong>선택 항목:</strong> 프로필 이미지</p>

<h2>2. 수집 방법</h2>
<p>1. Google/카카오 소셜 로그인을 통한 수집</p>
<p>2. 서비스 이용 과정에서 자동 생성/수집</p>

<h2>3. 개인정보의 이용 목적</h2>
<p>1. 회원 관리: 회원 식별, 서비스 이용, 불량 회원 방지</p>
<p>2. 서비스 제공: AI 응답 생성, 토큰 관리, 결제 처리</p>
<p>3. 서비스 개선: 이용 통계, 서비스 품질 개선</p>

<h2>4. 대화 데이터 처리</h2>
<p>1. AI와의 대화 내용은 서비스 제공 및 품질 개선 목적으로 저장될 수 있습니다.</p>
<p>2. 대화 내용은 암호화되어 저장됩니다.</p>
<p>3. 이용자는 언제든지 대화 기록 삭제를 요청할 수 있습니다.</p>

<h2>5. GPU 공유 네트워크 (Hwarang Grid)</h2>
<p>1. Grid 참여 시 GPU 하드웨어 정보가 수집됩니다 (GPU 모델, VRAM 등).</p>
<p>2. 처리하는 AI 작업 데이터는 암호화되어 전달되며, 참여자의 PC에 저장되지 않습니다.</p>
<p>3. 토큰 보상 기록은 서비스 운영 목적으로 저장됩니다.</p>

<h2>6. 개인정보의 보유 및 이용 기간</h2>
<p>1. 회원 탈퇴 시 즉시 파기 (단, 법령에 따른 보관 의무가 있는 경우 제외)</p>
<p>2. 결제 기록: 5년 (전자상거래법)</p>
<p>3. 접속 로그: 3개월 (통신비밀보호법)</p>

<h2>7. 이용자의 권리</h2>
<p>1. 개인정보 열람, 정정, 삭제 요청</p>
<p>2. 대화 기록 삭제 요청</p>
<p>3. 회원 탈퇴</p>
<p>4. 처리 정지 요청</p>
<p>요청 방법: hello@persismore.com 또는 서비스 내 설정</p>

<h2>8. 개인정보 보호책임자</h2>
<p>성명: (주)퍼시스모어 대표</p>
<p>이메일: privacy@persismore.com</p>

<p><br/>시행일: 2026년 4월 15일<br/>(주)퍼시스모어</p>`;
