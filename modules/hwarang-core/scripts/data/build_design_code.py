"""화랑 AI 디자인 코드 학습 데이터

"디자인 해줘" → 실제 HTML/CSS/React 코드를 출력하도록 학습.
텍스트 설명이 아닌 실행 가능한 코드를 생성하게 만듦.

사용법:
    python scripts/data/build_design_code.py --output data/sft/design_code.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
디자인 요청 시 반드시 실제 실행 가능한 HTML/CSS 또는 React 코드를 생성합니다.
텍스트 설명이나 아스키 아트가 아닌, 브라우저에서 바로 볼 수 있는 코드를 작성합니다.
설명은 한국어로, 코드는 완전한 형태로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 랜딩 페이지 ═══
    m("랜딩페이지 디자인 해줘",
'''랜딩 페이지를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>화랑 AI</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Pretendard', -apple-system, sans-serif; color: #1f2937; }

.hero {
  min-height: 100vh;
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0f172a 100%);
  display: flex; align-items: center; justify-content: center;
  text-align: center; padding: 2rem;
  position: relative; overflow: hidden;
}

.hero::before {
  content: ''; position: absolute; inset: 0;
  background: radial-gradient(circle at 30% 50%, rgba(59,130,246,0.15) 0%, transparent 50%),
              radial-gradient(circle at 70% 30%, rgba(139,92,246,0.1) 0%, transparent 50%);
}

.hero-content { position: relative; z-index: 1; max-width: 800px; }

.badge {
  display: inline-flex; align-items: center; gap: 8px;
  background: rgba(59,130,246,0.15); border: 1px solid rgba(59,130,246,0.3);
  color: #93c5fd; padding: 6px 16px; border-radius: 50px;
  font-size: 14px; margin-bottom: 2rem;
}

.badge::before {
  content: ''; width: 8px; height: 8px; background: #4ade80;
  border-radius: 50%; animation: pulse 2s infinite;
}

@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }

h1 { font-size: clamp(2.5rem, 6vw, 4rem); font-weight: 800; color: #fff; line-height: 1.2; margin-bottom: 1.5rem; }
h1 span { background: linear-gradient(135deg, #60a5fa, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

.subtitle { font-size: 1.2rem; color: #94a3b8; max-width: 600px; margin: 0 auto 2.5rem; line-height: 1.7; }

.cta-group { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }

.btn-primary {
  padding: 14px 32px; background: #3b82f6; color: #fff; border: none;
  border-radius: 12px; font-size: 1.1rem; font-weight: 600; cursor: pointer;
  box-shadow: 0 4px 20px rgba(59,130,246,0.4);
  transition: all 0.2s;
}
.btn-primary:hover { background: #2563eb; transform: translateY(-2px); box-shadow: 0 6px 25px rgba(59,130,246,0.5); }

.btn-secondary {
  padding: 14px 32px; background: transparent; color: #cbd5e1;
  border: 1px solid #475569; border-radius: 12px; font-size: 1.1rem;
  font-weight: 600; cursor: pointer; transition: all 0.2s;
}
.btn-secondary:hover { background: rgba(255,255,255,0.05); }

/* 기능 섹션 */
.features { padding: 6rem 2rem; max-width: 1200px; margin: 0 auto; }
.features h2 { text-align: center; font-size: 2.2rem; margin-bottom: 1rem; }
.features .sub { text-align: center; color: #6b7280; margin-bottom: 3rem; font-size: 1.1rem; }

.feature-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; }

.feature-card {
  padding: 2rem; border: 1px solid #e5e7eb; border-radius: 16px;
  transition: all 0.3s;
}
.feature-card:hover { border-color: rgba(59,130,246,0.3); box-shadow: 0 8px 30px rgba(0,0,0,0.08); transform: translateY(-4px); }

.feature-icon {
  width: 48px; height: 48px; border-radius: 12px;
  background: #eff6ff; display: flex; align-items: center; justify-content: center;
  font-size: 24px; margin-bottom: 1rem;
}

.feature-card h3 { font-size: 1.2rem; margin-bottom: 0.5rem; }
.feature-card p { color: #6b7280; line-height: 1.6; }

/* 가격 */
.pricing { padding: 6rem 2rem; background: #f8fafc; }
.pricing-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; max-width: 1000px; margin: 0 auto; }

.price-card {
  padding: 2.5rem; background: #fff; border: 1px solid #e5e7eb;
  border-radius: 20px; text-align: center;
}
.price-card.popular { border: 2px solid #3b82f6; position: relative; }
.price-card.popular::before {
  content: '인기'; position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
  background: #3b82f6; color: #fff; padding: 4px 16px; border-radius: 50px; font-size: 13px; font-weight: 600;
}

.price { font-size: 3rem; font-weight: 800; margin: 1rem 0; }
.price span { font-size: 1rem; font-weight: 400; color: #6b7280; }

.price-features { list-style: none; text-align: left; margin: 1.5rem 0; }
.price-features li { padding: 8px 0; color: #4b5563; }
.price-features li::before { content: '✓ '; color: #16a34a; font-weight: 700; }

footer {
  padding: 3rem 2rem; background: #0f172a; color: #94a3b8; text-align: center;
  font-size: 0.9rem;
}
</style>
</head>
<body>

<section class="hero">
  <div class="hero-content">
    <div class="badge">새로운 기능 출시</div>
    <h1>AI로 업무를<br><span>10배 빠르게</span></h1>
    <p class="subtitle">화랑 AI가 코딩, 디자인, 문서 작성을 도와드립니다. 한국어에 최적화된 AI 어시스턴트를 경험하세요.</p>
    <div class="cta-group">
      <button class="btn-primary">무료로 시작하기</button>
      <button class="btn-secondary">▶ 데모 보기</button>
    </div>
  </div>
</section>

<section class="features">
  <h2>모든 작업을 하나의 AI로</h2>
  <p class="sub">개발부터 디자인까지, 화랑 AI가 모두 도와드립니다.</p>
  <div class="feature-grid">
    <div class="feature-card">
      <div class="feature-icon">💻</div>
      <h3>코드 생성</h3>
      <p>자연어로 설명하면 완성도 높은 코드를 생성합니다. 50+ 언어를 지원합니다.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🎨</div>
      <h3>디자인 도움</h3>
      <p>UI 컴포넌트, 레이아웃, 색상 팔레트를 실제 코드로 제안합니다.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🔒</div>
      <h3>보안 검사</h3>
      <p>코드의 보안 취약점을 자동으로 발견하고 수정 방법을 안내합니다.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🇰🇷</div>
      <h3>한국어 최적화</h3>
      <p>한국어 이해도가 가장 높은 AI. 전문 용어도 정확하게 이해합니다.</p>
    </div>
  </div>
</section>

<section class="pricing">
  <h2 style="text-align:center;font-size:2.2rem;margin-bottom:3rem;">합리적인 가격</h2>
  <div class="pricing-grid">
    <div class="price-card">
      <h3>무료</h3>
      <p style="color:#6b7280;">개인 사용자</p>
      <div class="price">₩0<span>/월</span></div>
      <ul class="price-features">
        <li>하루 50회 질문</li>
        <li>기본 코드 생성</li>
        <li>한국어 지원</li>
      </ul>
      <button class="btn-secondary" style="width:100%;border-color:#d1d5db;color:#374151;">무료로 시작</button>
    </div>
    <div class="price-card popular">
      <h3>프로</h3>
      <p style="color:#6b7280;">전문 개발자</p>
      <div class="price">₩29,000<span>/월</span></div>
      <ul class="price-features">
        <li>무제한 질문</li>
        <li>고급 코드 생성</li>
        <li>디자인 도우미</li>
        <li>API 접근</li>
        <li>우선 지원</li>
      </ul>
      <button class="btn-primary" style="width:100%;">프로 시작하기</button>
    </div>
    <div class="price-card">
      <h3>팀</h3>
      <p style="color:#6b7280;">팀 협업</p>
      <div class="price">₩99,000<span>/월</span></div>
      <ul class="price-features">
        <li>프로 모든 기능</li>
        <li>팀원 10명</li>
        <li>관리자 대시보드</li>
        <li>SSO 인증</li>
        <li>전담 지원</li>
      </ul>
      <button class="btn-secondary" style="width:100%;border-color:#d1d5db;color:#374151;">팀 시작하기</button>
    </div>
  </div>
</section>

<footer>
  <p>&copy; 2025 Persismore. All rights reserved. | hwarang.ai</p>
</footer>

</body>
</html>
```

Hero 섹션, 기능 소개, 가격 표를 포함한 완전한 랜딩 페이지입니다. 브라우저에서 바로 열어볼 수 있어요. 수정이 필요하면 말씀해 주세요!'''),

    # ═══ 로그인 페이지 ═══
    m("로그인 페이지 디자인 해줘",
'''로그인 페이지를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>로그인</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Pretendard', -apple-system, sans-serif;
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  background: #f8fafc;
}

.login-container {
  width: 100%; max-width: 420px; padding: 2rem;
}

.logo {
  text-align: center; margin-bottom: 2rem;
}
.logo-icon {
  width: 48px; height: 48px; background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  border-radius: 14px; display: inline-flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 800; font-size: 20px; margin-bottom: 1rem;
}
.logo h1 { font-size: 1.5rem; color: #1f2937; }
.logo p { color: #6b7280; margin-top: 0.5rem; }

.login-card {
  background: #fff; border-radius: 20px; padding: 2rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 8px 30px rgba(0,0,0,0.04);
  border: 1px solid #f1f5f9;
}

.social-buttons { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1.5rem; }

.btn-social {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  width: 100%; padding: 12px; border: 1px solid #e2e8f0; border-radius: 12px;
  background: #fff; font-size: 15px; font-weight: 500; cursor: pointer;
  transition: all 0.2s; color: #374151;
}
.btn-social:hover { background: #f8fafc; border-color: #cbd5e1; }
.btn-social img { width: 20px; height: 20px; }

.divider {
  display: flex; align-items: center; gap: 1rem; margin: 1.5rem 0;
  color: #9ca3af; font-size: 13px;
}
.divider::before, .divider::after { content: ''; flex: 1; height: 1px; background: #e5e7eb; }

.form-group { margin-bottom: 1rem; }
.form-group label { display: block; font-size: 14px; font-weight: 500; color: #374151; margin-bottom: 6px; }

.form-group input {
  width: 100%; padding: 12px 14px; border: 1.5px solid #e2e8f0; border-radius: 10px;
  font-size: 15px; outline: none; transition: all 0.2s;
}
.form-group input:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }

.forgot { text-align: right; margin: -0.5rem 0 1rem; }
.forgot a { font-size: 13px; color: #3b82f6; text-decoration: none; }

.btn-login {
  width: 100%; padding: 13px; background: #3b82f6; color: #fff; border: none;
  border-radius: 12px; font-size: 16px; font-weight: 600; cursor: pointer;
  transition: all 0.2s;
}
.btn-login:hover { background: #2563eb; }

.signup-link {
  text-align: center; margin-top: 1.5rem; font-size: 14px; color: #6b7280;
}
.signup-link a { color: #3b82f6; text-decoration: none; font-weight: 600; }
</style>
</head>
<body>

<div class="login-container">
  <div class="logo">
    <div class="logo-icon">H</div>
    <h1>화랑 AI</h1>
    <p>계정에 로그인하세요</p>
  </div>

  <div class="login-card">
    <div class="social-buttons">
      <button class="btn-social">
        <svg width="20" height="20" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
        Google로 로그인
      </button>
      <button class="btn-social">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="#FEE500"><rect width="24" height="24" rx="4" fill="#FEE500"/><path d="M12 5.5c-4.14 0-7.5 2.73-7.5 6.1 0 2.17 1.44 4.07 3.6 5.15l-.92 3.38c-.08.28.24.5.48.34l4.04-2.67c.1 0 .2.01.3.01 4.14 0 7.5-2.73 7.5-6.1S16.14 5.5 12 5.5z" fill="#3C1E1E"/></svg>
        카카오로 로그인
      </button>
    </div>

    <div class="divider">또는 이메일로 로그인</div>

    <form>
      <div class="form-group">
        <label>이메일</label>
        <input type="email" placeholder="name@example.com">
      </div>
      <div class="form-group">
        <label>비밀번호</label>
        <input type="password" placeholder="비밀번호를 입력하세요">
      </div>
      <div class="forgot"><a href="#">비밀번호를 잊으셨나요?</a></div>
      <button type="submit" class="btn-login">로그인</button>
    </form>

    <div class="signup-link">
      아직 계정이 없으신가요? <a href="#">회원가입</a>
    </div>
  </div>
</div>

</body>
</html>
```

Google/카카오 소셜 로그인 + 이메일 로그인이 포함된 완전한 로그인 페이지입니다. 반응형이고 바로 브라우저에서 열어볼 수 있어요!'''),

    # ═══ 대시보드 ═══
    m("관리자 대시보드 디자인 해줘",
'''관리자 대시보드를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>대시보드</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Pretendard', -apple-system, sans-serif; background: #f1f5f9; color: #1f2937; display: flex; min-height: 100vh; }

/* 사이드바 */
.sidebar {
  width: 260px; background: #0f172a; color: #94a3b8; padding: 1.5rem; display: flex; flex-direction: column;
}
.sidebar-logo { display: flex; align-items: center; gap: 10px; color: #fff; font-size: 1.2rem; font-weight: 700; margin-bottom: 2rem; padding: 0.5rem; }
.sidebar-logo .icon { width: 36px; height: 36px; background: linear-gradient(135deg,#3b82f6,#8b5cf6); border-radius: 10px; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 800; }

.nav-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px;
  color: #94a3b8; text-decoration: none; font-size: 14px; margin-bottom: 4px; transition: all 0.2s;
}
.nav-item:hover, .nav-item.active { background: rgba(255,255,255,0.08); color: #fff; }
.nav-item.active { background: rgba(59,130,246,0.15); color: #60a5fa; }

.nav-badge { margin-left: auto; background: #ef4444; color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 10px; }

/* 메인 */
.main { flex: 1; padding: 2rem; overflow-y: auto; }

.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
.header h1 { font-size: 1.5rem; }
.header-right { display: flex; align-items: center; gap: 1rem; }

.avatar { width: 36px; height: 36px; border-radius: 50%; background: #3b82f6; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 14px; }

/* 통계 카드 */
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }

.stat-card {
  background: #fff; padding: 1.5rem; border-radius: 16px; border: 1px solid #e2e8f0;
}
.stat-card .label { font-size: 13px; color: #6b7280; }
.stat-card .value { font-size: 1.8rem; font-weight: 700; margin: 0.5rem 0 0.25rem; }
.stat-card .change { font-size: 13px; }
.stat-card .change.up { color: #16a34a; }
.stat-card .change.down { color: #ef4444; }

/* 테이블 */
.table-card { background: #fff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; }
.table-header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid #f1f5f9; }
.table-header h3 { font-size: 1rem; }

table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 12px 1.5rem; font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #f1f5f9; }
td { padding: 14px 1.5rem; font-size: 14px; border-bottom: 1px solid #f8fafc; }
tr:hover { background: #f8fafc; }

.user-cell { display: flex; align-items: center; gap: 10px; }
.user-avatar { width: 32px; height: 32px; border-radius: 50%; background: #e0e7ff; color: #4338ca; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; }

.badge { padding: 4px 10px; border-radius: 8px; font-size: 12px; font-weight: 500; }
.badge-active { background: #dcfce7; color: #166534; }
.badge-inactive { background: #f1f5f9; color: #64748b; }
</style>
</head>
<body>

<aside class="sidebar">
  <div class="sidebar-logo">
    <div class="icon">H</div>
    화랑 Admin
  </div>
  <a class="nav-item active" href="#">📊 대시보드</a>
  <a class="nav-item" href="#">👥 사용자</a>
  <a class="nav-item" href="#">💬 대화 <span class="nav-badge">12</span></a>
  <a class="nav-item" href="#">🤖 모델</a>
  <a class="nav-item" href="#">📈 통계</a>
  <a class="nav-item" href="#">⚙️ 설정</a>
</aside>

<main class="main">
  <div class="header">
    <h1>대시보드</h1>
    <div class="header-right">
      <div class="avatar">관</div>
    </div>
  </div>

  <div class="stats">
    <div class="stat-card">
      <div class="label">전체 사용자</div>
      <div class="value">12,847</div>
      <div class="change up">+12.5% 이번 달</div>
    </div>
    <div class="stat-card">
      <div class="label">오늘 대화</div>
      <div class="value">1,423</div>
      <div class="change up">+8.2%</div>
    </div>
    <div class="stat-card">
      <div class="label">API 호출</div>
      <div class="value">89,234</div>
      <div class="change down">-2.1%</div>
    </div>
    <div class="stat-card">
      <div class="label">평균 응답시간</div>
      <div class="value">1.2초</div>
      <div class="change up">-15% 개선</div>
    </div>
  </div>

  <div class="table-card">
    <div class="table-header">
      <h3>최근 사용자</h3>
      <button style="padding:8px 16px;background:#3b82f6;color:#fff;border:none;border-radius:8px;font-size:13px;cursor:pointer;">내보내기</button>
    </div>
    <table>
      <thead>
        <tr><th>사용자</th><th>이메일</th><th>가입일</th><th>상태</th></tr>
      </thead>
      <tbody>
        <tr>
          <td><div class="user-cell"><div class="user-avatar">홍</div>홍길동</div></td>
          <td>hong@example.com</td><td>2025-04-20</td>
          <td><span class="badge badge-active">활성</span></td>
        </tr>
        <tr>
          <td><div class="user-cell"><div class="user-avatar">김</div>김철수</div></td>
          <td>kim@example.com</td><td>2025-04-19</td>
          <td><span class="badge badge-active">활성</span></td>
        </tr>
        <tr>
          <td><div class="user-cell"><div class="user-avatar">이</div>이영희</div></td>
          <td>lee@example.com</td><td>2025-04-18</td>
          <td><span class="badge badge-inactive">비활성</span></td>
        </tr>
        <tr>
          <td><div class="user-cell"><div class="user-avatar">박</div>박지민</div></td>
          <td>park@example.com</td><td>2025-04-17</td>
          <td><span class="badge badge-active">활성</span></td>
        </tr>
      </tbody>
    </table>
  </div>
</main>

</body>
</html>
```

사이드바 + 통계 카드 4개 + 사용자 테이블이 포함된 관리자 대시보드입니다. 바로 브라우저에서 열어보세요!'''),

    # ═══ 카드 컴포넌트 ═══
    m("상품 카드 컴포넌트 디자인 해줘",
'''상품 카드 컴포넌트를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>상품 카드</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Pretendard', -apple-system, sans-serif; background: #f8fafc; padding: 2rem; display: flex; justify-content: center; }

.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; max-width: 1200px; width: 100%; }

.product-card {
  background: #fff; border-radius: 16px; overflow: hidden;
  border: 1px solid #f1f5f9; transition: all 0.3s;
  cursor: pointer;
}
.product-card:hover { transform: translateY(-4px); box-shadow: 0 12px 40px rgba(0,0,0,0.1); }

.card-image {
  position: relative; aspect-ratio: 1/1; background: #f1f5f9;
  display: flex; align-items: center; justify-content: center;
  font-size: 3rem; overflow: hidden;
}
.card-image img { width: 100%; height: 100%; object-fit: cover; }

.card-badge {
  position: absolute; top: 12px; left: 12px;
  background: #3b82f6; color: #fff; padding: 4px 10px;
  border-radius: 6px; font-size: 12px; font-weight: 600;
}

.card-heart {
  position: absolute; top: 12px; right: 12px;
  width: 36px; height: 36px; background: rgba(255,255,255,0.9);
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 18px; transition: all 0.2s;
  backdrop-filter: blur(4px);
}
.card-heart:hover { background: #fff; transform: scale(1.1); }
.card-heart.liked { color: #ef4444; }

.card-body { padding: 1rem 1.25rem 1.25rem; }
.card-brand { font-size: 12px; color: #6b7280; margin-bottom: 4px; }
.card-title { font-size: 15px; font-weight: 500; line-height: 1.4; margin-bottom: 8px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.card-price { display: flex; align-items: baseline; gap: 6px; margin-bottom: 8px; }
.discount { font-size: 15px; font-weight: 700; color: #ef4444; }
.price { font-size: 18px; font-weight: 700; }
.original { font-size: 13px; color: #9ca3af; text-decoration: line-through; }

.card-rating { display: flex; align-items: center; gap: 4px; font-size: 13px; color: #6b7280; }
.star { color: #fbbf24; }

.card-tags { display: flex; gap: 6px; margin-top: 8px; }
.tag { padding: 4px 8px; background: #f1f5f9; border-radius: 6px; font-size: 11px; color: #64748b; }
</style>
</head>
<body>

<div class="card-grid">
  <div class="product-card">
    <div class="card-image" style="background:linear-gradient(135deg,#dbeafe,#e0e7ff);">
      <span>🎧</span>
      <span class="card-badge">NEW</span>
      <span class="card-heart">🤍</span>
    </div>
    <div class="card-body">
      <div class="card-brand">소니</div>
      <div class="card-title">WH-1000XM5 무선 노이즈캔슬링 헤드폰</div>
      <div class="card-price">
        <span class="discount">20%</span>
        <span class="price">319,000원</span>
        <span class="original">399,000원</span>
      </div>
      <div class="card-rating">
        <span class="star">★★★★★</span> 4.8 (2,341)
      </div>
      <div class="card-tags"><span class="tag">무료배송</span><span class="tag">당일출고</span></div>
    </div>
  </div>

  <div class="product-card">
    <div class="card-image" style="background:linear-gradient(135deg,#fef3c7,#fde68a);">
      <span>⌨️</span>
      <span class="card-badge" style="background:#8b5cf6;">BEST</span>
      <span class="card-heart liked">❤️</span>
    </div>
    <div class="card-body">
      <div class="card-brand">로지텍</div>
      <div class="card-title">MX Keys S 무선 키보드 한영 자판</div>
      <div class="card-price">
        <span class="discount">15%</span>
        <span class="price">135,000원</span>
        <span class="original">159,000원</span>
      </div>
      <div class="card-rating">
        <span class="star">★★★★☆</span> 4.6 (892)
      </div>
      <div class="card-tags"><span class="tag">무료배송</span></div>
    </div>
  </div>

  <div class="product-card">
    <div class="card-image" style="background:linear-gradient(135deg,#d1fae5,#a7f3d0);">
      <span>🖥️</span>
      <span class="card-heart">🤍</span>
    </div>
    <div class="card-body">
      <div class="card-brand">삼성</div>
      <div class="card-title">오디세이 G9 49인치 커브드 게이밍 모니터</div>
      <div class="card-price">
        <span class="price">1,290,000원</span>
      </div>
      <div class="card-rating">
        <span class="star">★★★★★</span> 4.9 (567)
      </div>
      <div class="card-tags"><span class="tag">무료배송</span><span class="tag">설치비포함</span></div>
    </div>
  </div>
</div>

</body>
</html>
```

이미지, 뱃지(NEW/BEST), 찜 버튼, 할인율, 별점, 태그가 포함된 쇼핑몰 상품 카드입니다. 반응형 그리드로 화면 크기에 맞게 배치됩니다!'''),

    # ═══ 버튼 디자인 ═══
    m("버튼 디자인 해줘 다양한 스타일로",
'''다양한 스타일의 버튼 컴포넌트를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>버튼 디자인 시스템</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Pretendard', -apple-system, sans-serif; padding: 3rem; background: #f8fafc; }
h2 { font-size: 1.2rem; color: #374151; margin: 2rem 0 1rem; }
h2:first-child { margin-top: 0; }
.row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 0.5rem; }

/* 기본 버튼 */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 10px 20px; border: none; border-radius: 10px;
  font-size: 14px; font-weight: 600; cursor: pointer;
  transition: all 0.2s; text-decoration: none;
}
.btn:active { transform: scale(0.97); }

/* 변형 */
.btn-primary { background: #3b82f6; color: #fff; }
.btn-primary:hover { background: #2563eb; box-shadow: 0 4px 12px rgba(59,130,246,0.4); }

.btn-secondary { background: #f1f5f9; color: #374151; }
.btn-secondary:hover { background: #e2e8f0; }

.btn-danger { background: #ef4444; color: #fff; }
.btn-danger:hover { background: #dc2626; box-shadow: 0 4px 12px rgba(239,68,68,0.4); }

.btn-success { background: #16a34a; color: #fff; }
.btn-success:hover { background: #15803d; box-shadow: 0 4px 12px rgba(22,163,74,0.4); }

.btn-warning { background: #f59e0b; color: #fff; }
.btn-warning:hover { background: #d97706; }

.btn-purple { background: #8b5cf6; color: #fff; }
.btn-purple:hover { background: #7c3aed; box-shadow: 0 4px 12px rgba(139,92,246,0.4); }

/* 아웃라인 */
.btn-outline { background: transparent; border: 1.5px solid #d1d5db; color: #374151; }
.btn-outline:hover { background: #f9fafb; border-color: #9ca3af; }

.btn-outline-primary { background: transparent; border: 1.5px solid #3b82f6; color: #3b82f6; }
.btn-outline-primary:hover { background: #eff6ff; }

.btn-outline-danger { background: transparent; border: 1.5px solid #ef4444; color: #ef4444; }
.btn-outline-danger:hover { background: #fef2f2; }

/* 고스트 */
.btn-ghost { background: transparent; color: #3b82f6; }
.btn-ghost:hover { background: #eff6ff; }

/* 링크 */
.btn-link { background: transparent; color: #3b82f6; text-decoration: underline; padding: 10px 8px; }
.btn-link:hover { color: #1d4ed8; }

/* 크기 */
.btn-xs { padding: 6px 12px; font-size: 12px; border-radius: 6px; }
.btn-sm { padding: 8px 16px; font-size: 13px; border-radius: 8px; }
.btn-lg { padding: 14px 28px; font-size: 16px; border-radius: 12px; }
.btn-xl { padding: 16px 36px; font-size: 18px; border-radius: 14px; }

/* 아이콘 */
.btn-icon { width: 40px; height: 40px; padding: 0; border-radius: 10px; }
.btn-icon-round { width: 40px; height: 40px; padding: 0; border-radius: 50%; }

/* 그라데이션 */
.btn-gradient { background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: #fff; }
.btn-gradient:hover { box-shadow: 0 4px 15px rgba(99,102,241,0.4); }

.btn-gradient-warm { background: linear-gradient(135deg, #f97316, #ef4444); color: #fff; }
.btn-gradient-warm:hover { box-shadow: 0 4px 15px rgba(249,115,22,0.4); }

/* 로딩 */
.btn-loading { position: relative; color: transparent !important; pointer-events: none; }
.btn-loading::after {
  content: ''; position: absolute; width: 18px; height: 18px;
  border: 2.5px solid rgba(255,255,255,0.3); border-top-color: #fff;
  border-radius: 50%; animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 비활성 */
.btn:disabled, .btn-disabled { opacity: 0.5; cursor: not-allowed; pointer-events: none; }

/* 그룹 */
.btn-group { display: inline-flex; }
.btn-group .btn { border-radius: 0; }
.btn-group .btn:first-child { border-radius: 10px 0 0 10px; }
.btn-group .btn:last-child { border-radius: 0 10px 10px 0; }
.btn-group .btn + .btn { border-left: 1px solid rgba(255,255,255,0.2); }
</style>
</head>
<body>

<h2>기본 (Solid)</h2>
<div class="row">
  <button class="btn btn-primary">Primary</button>
  <button class="btn btn-secondary">Secondary</button>
  <button class="btn btn-danger">Danger</button>
  <button class="btn btn-success">Success</button>
  <button class="btn btn-warning">Warning</button>
  <button class="btn btn-purple">Purple</button>
</div>

<h2>아웃라인 (Outline)</h2>
<div class="row">
  <button class="btn btn-outline">Default</button>
  <button class="btn btn-outline-primary">Primary</button>
  <button class="btn btn-outline-danger">Danger</button>
  <button class="btn btn-ghost">Ghost</button>
  <button class="btn btn-link">Link</button>
</div>

<h2>크기 (Size)</h2>
<div class="row">
  <button class="btn btn-primary btn-xs">XS</button>
  <button class="btn btn-primary btn-sm">Small</button>
  <button class="btn btn-primary">Default</button>
  <button class="btn btn-primary btn-lg">Large</button>
  <button class="btn btn-primary btn-xl">XLarge</button>
</div>

<h2>그라데이션 (Gradient)</h2>
<div class="row">
  <button class="btn btn-gradient">✨ 그라데이션</button>
  <button class="btn btn-gradient-warm">🔥 워밍</button>
</div>

<h2>아이콘 (Icon)</h2>
<div class="row">
  <button class="btn btn-primary btn-icon">+</button>
  <button class="btn btn-danger btn-icon-round">✕</button>
  <button class="btn btn-primary">📤 업로드</button>
  <button class="btn btn-success">✓ 저장 완료</button>
</div>

<h2>상태 (State)</h2>
<div class="row">
  <button class="btn btn-primary btn-loading">로딩중</button>
  <button class="btn btn-primary" disabled>비활성</button>
</div>

<h2>그룹 (Group)</h2>
<div class="row">
  <div class="btn-group">
    <button class="btn btn-primary">왼쪽</button>
    <button class="btn btn-primary">가운데</button>
    <button class="btn btn-primary">오른쪽</button>
  </div>
</div>

</body>
</html>
```

Solid, Outline, Ghost, Link, 크기별, 그라데이션, 아이콘, 로딩, 그룹까지 포함된 완전한 버튼 디자인 시스템입니다!'''),

    # ═══ 프로필 페이지 ═══
    m("프로필 페이지 디자인 해줘",
'''사용자 프로필 페이지를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>프로필</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Pretendard', -apple-system, sans-serif; background: #f8fafc; }

.profile-header {
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  padding: 3rem 2rem 5rem; text-align: center; color: #fff;
}

.avatar-wrapper { position: relative; display: inline-block; margin-bottom: 1rem; }
.avatar {
  width: 96px; height: 96px; border-radius: 50%; border: 4px solid #fff;
  background: #e0e7ff; color: #4338ca; display: flex; align-items: center; justify-content: center;
  font-size: 2rem; font-weight: 700;
}
.avatar-badge {
  position: absolute; bottom: 4px; right: 4px;
  width: 28px; height: 28px; background: #fff; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

.profile-name { font-size: 1.5rem; font-weight: 700; }
.profile-email { color: rgba(255,255,255,0.8); margin-top: 4px; }

.profile-stats {
  display: flex; gap: 3rem; justify-content: center; margin-top: 1.5rem;
}
.stat { text-align: center; }
.stat-value { font-size: 1.3rem; font-weight: 700; }
.stat-label { font-size: 13px; color: rgba(255,255,255,0.7); margin-top: 2px; }

/* 콘텐츠 */
.content {
  max-width: 800px; margin: -2rem auto 2rem; padding: 0 1rem;
}

.card {
  background: #fff; border-radius: 16px; border: 1px solid #e2e8f0;
  padding: 1.5rem; margin-bottom: 1rem;
}
.card h3 { font-size: 1rem; margin-bottom: 1rem; display: flex; align-items: center; justify-content: space-between; }

.info-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 0; border-bottom: 1px solid #f1f5f9;
}
.info-row:last-child { border-bottom: none; }
.info-label { font-size: 14px; color: #6b7280; }
.info-value { font-size: 14px; font-weight: 500; }

.edit-btn {
  padding: 6px 14px; background: #f1f5f9; border: none; border-radius: 8px;
  font-size: 13px; color: #3b82f6; cursor: pointer; font-weight: 500;
}
.edit-btn:hover { background: #e2e8f0; }

/* 활동 */
.activity-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 0;
  border-bottom: 1px solid #f8fafc;
}
.activity-icon {
  width: 36px; height: 36px; border-radius: 10px; display: flex;
  align-items: center; justify-content: center; font-size: 16px;
}
.activity-text { flex: 1; }
.activity-text .title { font-size: 14px; font-weight: 500; }
.activity-text .time { font-size: 12px; color: #9ca3af; }

/* 토글 */
.toggle-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #f1f5f9; }
.toggle-label .title { font-size: 14px; font-weight: 500; }
.toggle-label .desc { font-size: 12px; color: #9ca3af; }

.toggle {
  width: 44px; height: 24px; background: #d1d5db; border-radius: 12px;
  position: relative; cursor: pointer; transition: all 0.2s;
}
.toggle.on { background: #3b82f6; }
.toggle::after {
  content: ''; position: absolute; width: 20px; height: 20px; background: #fff;
  border-radius: 50%; top: 2px; left: 2px; transition: all 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
.toggle.on::after { left: 22px; }
</style>
</head>
<body>

<div class="profile-header">
  <div class="avatar-wrapper">
    <div class="avatar">홍</div>
    <div class="avatar-badge">📷</div>
  </div>
  <div class="profile-name">홍길동</div>
  <div class="profile-email">hong@example.com</div>
  <div class="profile-stats">
    <div class="stat"><div class="stat-value">127</div><div class="stat-label">대화</div></div>
    <div class="stat"><div class="stat-value">15,430</div><div class="stat-label">토큰</div></div>
    <div class="stat"><div class="stat-value">Pro</div><div class="stat-label">플랜</div></div>
  </div>
</div>

<div class="content">
  <div class="card">
    <h3>기본 정보 <button class="edit-btn">수정</button></h3>
    <div class="info-row"><span class="info-label">이름</span><span class="info-value">홍길동</span></div>
    <div class="info-row"><span class="info-label">이메일</span><span class="info-value">hong@example.com</span></div>
    <div class="info-row"><span class="info-label">가입일</span><span class="info-value">2025년 3월 15일</span></div>
    <div class="info-row"><span class="info-label">플랜</span><span class="info-value" style="color:#3b82f6;">Pro 플랜</span></div>
  </div>

  <div class="card">
    <h3>최근 활동</h3>
    <div class="activity-item">
      <div class="activity-icon" style="background:#eff6ff;">💬</div>
      <div class="activity-text"><div class="title">React 컴포넌트 설계 질문</div><div class="time">10분 전</div></div>
    </div>
    <div class="activity-item">
      <div class="activity-icon" style="background:#f0fdf4;">💻</div>
      <div class="activity-text"><div class="title">Python 비동기 프로그래밍 코드 생성</div><div class="time">1시간 전</div></div>
    </div>
    <div class="activity-item">
      <div class="activity-icon" style="background:#fef3c7;">📄</div>
      <div class="activity-text"><div class="title">사업계획서 초안 작성</div><div class="time">어제</div></div>
    </div>
  </div>

  <div class="card">
    <h3>알림 설정</h3>
    <div class="toggle-row">
      <div class="toggle-label"><div class="title">이메일 알림</div><div class="desc">새 기능 및 업데이트 알림</div></div>
      <div class="toggle on" onclick="this.classList.toggle('on')"></div>
    </div>
    <div class="toggle-row">
      <div class="toggle-label"><div class="title">마케팅 알림</div><div class="desc">프로모션 및 이벤트 알림</div></div>
      <div class="toggle" onclick="this.classList.toggle('on')"></div>
    </div>
  </div>
</div>

</body>
</html>
```

프로필 헤더(아바타+통계) + 기본정보 + 최근활동 + 알림설정 토글이 포함된 프로필 페이지입니다!'''),

    # ═══ 간단한 요청들 ═══
    m("네비게이션 바 디자인 해줘",
'''반응형 네비게이션 바를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Pretendard', -apple-system, sans-serif; }

nav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 2rem; height: 64px;
  background: #fff; border-bottom: 1px solid #f1f5f9;
  position: sticky; top: 0; z-index: 100;
  backdrop-filter: blur(12px); background: rgba(255,255,255,0.85);
}

.nav-logo { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 1.1rem; color: #1f2937; text-decoration: none; }
.nav-logo .icon { width: 32px; height: 32px; background: linear-gradient(135deg,#3b82f6,#8b5cf6); border-radius: 8px; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 14px; font-weight: 800; }

.nav-links { display: flex; gap: 2rem; list-style: none; }
.nav-links a { color: #6b7280; text-decoration: none; font-size: 14px; font-weight: 500; transition: color 0.2s; padding: 4px 0; }
.nav-links a:hover, .nav-links a.active { color: #1f2937; }
.nav-links a.active { border-bottom: 2px solid #3b82f6; color: #3b82f6; }

.nav-right { display: flex; align-items: center; gap: 12px; }
.nav-btn { padding: 8px 18px; background: #3b82f6; color: #fff; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; }
.nav-btn:hover { background: #2563eb; }
.nav-btn-outline { padding: 8px 18px; background: transparent; border: 1px solid #d1d5db; border-radius: 8px; font-size: 14px; color: #374151; cursor: pointer; }

.content { max-width: 800px; margin: 4rem auto; padding: 0 2rem; }
.content h1 { font-size: 2rem; margin-bottom: 1rem; }
.content p { color: #6b7280; line-height: 1.7; }
</style>
</head>
<body>

<nav>
  <a href="#" class="nav-logo">
    <div class="icon">H</div>
    화랑 AI
  </a>
  <ul class="nav-links">
    <li><a href="#" class="active">홈</a></li>
    <li><a href="#">기능</a></li>
    <li><a href="#">가격</a></li>
    <li><a href="#">문서</a></li>
    <li><a href="#">블로그</a></li>
  </ul>
  <div class="nav-right">
    <button class="nav-btn-outline">로그인</button>
    <button class="nav-btn">시작하기</button>
  </div>
</nav>

<div class="content">
  <h1>네비게이션 바 예시</h1>
  <p>상단에 고정된 반투명 네비게이션 바입니다. 스크롤해도 상단에 유지됩니다. 로고, 메뉴 링크, 로그인/시작 버튼이 포함되어 있습니다.</p>
</div>

</body>
</html>
```

상단 고정 + 반투명(blur) 효과 + 액티브 상태 표시가 포함된 네비게이션 바입니다!'''),

    m("푸터 디자인 해줘",
'''웹사이트 푸터를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Pretendard', -apple-system, sans-serif; }

footer { background: #0f172a; color: #94a3b8; padding: 4rem 2rem 2rem; }
.footer-grid { max-width: 1200px; margin: 0 auto; display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 3rem; margin-bottom: 3rem; }

.footer-brand .logo { display: flex; align-items: center; gap: 8px; color: #fff; font-size: 1.2rem; font-weight: 700; margin-bottom: 1rem; }
.footer-brand .logo .icon { width: 32px; height: 32px; background: linear-gradient(135deg,#3b82f6,#8b5cf6); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 14px; }
.footer-brand p { line-height: 1.7; font-size: 14px; margin-bottom: 1.5rem; }

.social-links { display: flex; gap: 12px; }
.social-link { width: 36px; height: 36px; border-radius: 8px; background: rgba(255,255,255,0.08); display: flex; align-items: center; justify-content: center; color: #94a3b8; text-decoration: none; transition: all 0.2s; font-size: 16px; }
.social-link:hover { background: rgba(255,255,255,0.15); color: #fff; }

.footer-col h4 { color: #fff; font-size: 14px; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.5px; }
.footer-col a { display: block; color: #94a3b8; text-decoration: none; font-size: 14px; padding: 6px 0; transition: color 0.2s; }
.footer-col a:hover { color: #fff; }

.footer-bottom { max-width: 1200px; margin: 0 auto; padding-top: 2rem; border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
.footer-bottom a { color: #94a3b8; text-decoration: none; }
.footer-bottom a:hover { color: #fff; }
.footer-links { display: flex; gap: 1.5rem; }

@media (max-width: 768px) {
  .footer-grid { grid-template-columns: 1fr 1fr; }
  .footer-bottom { flex-direction: column; gap: 1rem; text-align: center; }
}
</style>
</head>
<body>

<footer>
  <div class="footer-grid">
    <div class="footer-brand">
      <div class="logo"><div class="icon">H</div> 화랑 AI</div>
      <p>한국어에 최적화된 AI 어시스턴트. 코딩, 디자인, 문서 작성을 도와드립니다.</p>
      <div class="social-links">
        <a href="#" class="social-link">𝕏</a>
        <a href="#" class="social-link">G</a>
        <a href="#" class="social-link">Y</a>
      </div>
    </div>
    <div class="footer-col">
      <h4>서비스</h4>
      <a href="#">채팅</a><a href="#">API</a><a href="#">VS Code 확장</a><a href="#">데스크탑 앱</a>
    </div>
    <div class="footer-col">
      <h4>회사</h4>
      <a href="#">소개</a><a href="#">블로그</a><a href="#">채용</a><a href="#">문의</a>
    </div>
    <div class="footer-col">
      <h4>지원</h4>
      <a href="#">문서</a><a href="#">가격</a><a href="#">FAQ</a><a href="#">커뮤니티</a>
    </div>
  </div>
  <div class="footer-bottom">
    <span>&copy; 2025 Persismore. All rights reserved.</span>
    <div class="footer-links">
      <a href="#">이용약관</a>
      <a href="#">개인정보처리방침</a>
      <a href="#">쿠키 정책</a>
    </div>
  </div>
</footer>

</body>
</html>
```

브랜드 소개, 소셜 링크, 4컬럼 메뉴, 하단 저작권 표시가 포함된 완전한 푸터입니다!'''),

    m("모달 다이얼로그 디자인 해줘",
'''모달 다이얼로그를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Pretendard', -apple-system, sans-serif; padding: 4rem 2rem; background: #f8fafc; }

button { cursor: pointer; }

.btn { padding: 10px 20px; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; }
.btn-primary { background: #3b82f6; color: #fff; }
.btn-outline { background: transparent; border: 1px solid #d1d5db; color: #374151; }
.btn-danger { background: #ef4444; color: #fff; }

/* 모달 오버레이 */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000; backdrop-filter: blur(4px);
  opacity: 0; pointer-events: none; transition: opacity 0.2s;
}
.modal-overlay.active { opacity: 1; pointer-events: all; }

/* 모달 */
.modal {
  background: #fff; border-radius: 20px; width: 90%; max-width: 480px;
  padding: 1.5rem; box-shadow: 0 20px 60px rgba(0,0,0,0.15);
  transform: scale(0.95) translateY(10px); transition: transform 0.2s;
}
.modal-overlay.active .modal { transform: scale(1) translateY(0); }

.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.modal-header h3 { font-size: 1.1rem; }
.modal-close { width: 32px; height: 32px; border: none; background: #f1f5f9; border-radius: 8px; font-size: 18px; display: flex; align-items: center; justify-content: center; color: #6b7280; }
.modal-close:hover { background: #e2e8f0; }

.modal-body { margin-bottom: 1.5rem; color: #6b7280; font-size: 14px; line-height: 1.6; }

.modal-footer { display: flex; justify-content: flex-end; gap: 8px; }

/* 폼 모달 */
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; font-size: 14px; font-weight: 500; color: #374151; margin-bottom: 6px; }
.form-group input, .form-group textarea {
  width: 100%; padding: 10px 14px; border: 1.5px solid #e2e8f0; border-radius: 10px;
  font-size: 14px; outline: none; transition: border-color 0.2s; font-family: inherit;
}
.form-group input:focus, .form-group textarea:focus { border-color: #3b82f6; }

.trigger-row { display: flex; gap: 12px; flex-wrap: wrap; }
</style>
</head>
<body>

<h2 style="margin-bottom:1rem;">모달 예시</h2>
<div class="trigger-row">
  <button class="btn btn-primary" onclick="openModal('confirm')">확인 모달</button>
  <button class="btn btn-danger" onclick="openModal('delete')">삭제 확인</button>
  <button class="btn btn-outline" onclick="openModal('form')">폼 모달</button>
</div>

<!-- 확인 모달 -->
<div class="modal-overlay" id="modal-confirm">
  <div class="modal">
    <div class="modal-header"><h3>변경 사항 저장</h3><button class="modal-close" onclick="closeModal('confirm')">✕</button></div>
    <div class="modal-body">저장하지 않은 변경 사항이 있습니다. 저장하시겠습니까?</div>
    <div class="modal-footer">
      <button class="btn btn-outline" onclick="closeModal('confirm')">취소</button>
      <button class="btn btn-primary" onclick="closeModal('confirm')">저장</button>
    </div>
  </div>
</div>

<!-- 삭제 확인 -->
<div class="modal-overlay" id="modal-delete">
  <div class="modal">
    <div class="modal-header"><h3 style="color:#ef4444;">삭제 확인</h3><button class="modal-close" onclick="closeModal('delete')">✕</button></div>
    <div class="modal-body">이 항목을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.</div>
    <div class="modal-footer">
      <button class="btn btn-outline" onclick="closeModal('delete')">취소</button>
      <button class="btn btn-danger" onclick="closeModal('delete')">삭제</button>
    </div>
  </div>
</div>

<!-- 폼 모달 -->
<div class="modal-overlay" id="modal-form">
  <div class="modal">
    <div class="modal-header"><h3>새 프로젝트</h3><button class="modal-close" onclick="closeModal('form')">✕</button></div>
    <div class="modal-body">
      <div class="form-group"><label>프로젝트 이름</label><input placeholder="프로젝트 이름을 입력하세요"></div>
      <div class="form-group"><label>설명</label><textarea rows="3" placeholder="설명을 입력하세요"></textarea></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-outline" onclick="closeModal('form')">취소</button>
      <button class="btn btn-primary" onclick="closeModal('form')">생성</button>
    </div>
  </div>
</div>

<script>
function openModal(id) { document.getElementById('modal-' + id).classList.add('active'); }
function closeModal(id) { document.getElementById('modal-' + id).classList.remove('active'); }
document.querySelectorAll('.modal-overlay').forEach(el => {
  el.addEventListener('click', (e) => { if (e.target === el) el.classList.remove('active'); });
});
</script>

</body>
</html>
```

확인/삭제/폼 3가지 모달 + 배경 클릭 닫기 + 애니메이션이 포함된 모달 컴포넌트입니다!'''),

    m("404 에러 페이지 디자인 해줘",
'''404 에러 페이지를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>404 - 페이지를 찾을 수 없습니다</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Pretendard', -apple-system, sans-serif;
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: #0f172a; color: #fff; text-align: center; padding: 2rem;
  overflow: hidden;
}

.container { position: relative; z-index: 1; }

.error-code {
  font-size: clamp(6rem, 20vw, 12rem); font-weight: 900;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6, #ec4899);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  line-height: 1; margin-bottom: 1rem;
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

h2 { font-size: 1.5rem; color: #e2e8f0; margin-bottom: 1rem; }
p { color: #94a3b8; max-width: 400px; margin: 0 auto 2rem; line-height: 1.6; }

.btn-home {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 14px 28px; background: #3b82f6; color: #fff; border: none;
  border-radius: 12px; font-size: 16px; font-weight: 600; cursor: pointer;
  text-decoration: none; transition: all 0.2s;
}
.btn-home:hover { background: #2563eb; transform: translateY(-2px); box-shadow: 0 8px 25px rgba(59,130,246,0.4); }

/* 배경 장식 */
.bg-circle {
  position: fixed; border-radius: 50%; opacity: 0.1;
  animation: drift 20s ease-in-out infinite;
}
.bg-circle:nth-child(1) { width: 400px; height: 400px; background: #3b82f6; top: -100px; left: -100px; }
.bg-circle:nth-child(2) { width: 300px; height: 300px; background: #8b5cf6; bottom: -50px; right: -50px; animation-delay: -10s; }
.bg-circle:nth-child(3) { width: 200px; height: 200px; background: #ec4899; top: 50%; left: 50%; animation-delay: -5s; }

@keyframes drift {
  0%, 100% { transform: translate(0, 0); }
  25% { transform: translate(30px, -30px); }
  50% { transform: translate(-20px, 20px); }
  75% { transform: translate(10px, 30px); }
}
</style>
</head>
<body>

<div class="bg-circle"></div>
<div class="bg-circle"></div>
<div class="bg-circle"></div>

<div class="container">
  <div class="error-code">404</div>
  <h2>페이지를 찾을 수 없습니다</h2>
  <p>요청하신 페이지가 존재하지 않거나, 이동되었을 수 있습니다. 주소를 다시 확인해 주세요.</p>
  <a href="/" class="btn-home">← 홈으로 돌아가기</a>
</div>

</body>
</html>
```

그라데이션 404 텍스트 + 플로팅 애니메이션 + 배경 장식 원이 포함된 404 페이지입니다!'''),

    m("토스트 알림 디자인 해줘",
'''토스트 알림 컴포넌트를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Pretendard', -apple-system, sans-serif; padding: 3rem; background: #f8fafc; }

.trigger-row { display: flex; gap: 12px; flex-wrap: wrap; }
.btn { padding: 10px 20px; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; color: #fff; cursor: pointer; }

/* 토스트 컨테이너 */
.toast-container {
  position: fixed; top: 1.5rem; right: 1.5rem;
  display: flex; flex-direction: column; gap: 10px;
  z-index: 9999; pointer-events: none;
}

.toast {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 20px; border-radius: 12px;
  background: #fff; border: 1px solid #e2e8f0;
  box-shadow: 0 8px 30px rgba(0,0,0,0.12);
  min-width: 320px; max-width: 420px;
  pointer-events: all;
  animation: slideIn 0.3s ease-out;
  transition: all 0.3s;
}

.toast.removing { animation: slideOut 0.3s ease-in forwards; }

@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
@keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(100%); opacity: 0; } }

.toast-icon { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }

.toast-content { flex: 1; }
.toast-title { font-size: 14px; font-weight: 600; color: #1f2937; }
.toast-message { font-size: 13px; color: #6b7280; margin-top: 2px; }

.toast-close { background: none; border: none; color: #9ca3af; font-size: 18px; cursor: pointer; padding: 4px; flex-shrink: 0; }
.toast-close:hover { color: #374151; }

/* 프로그레스 바 */
.toast-progress { height: 3px; border-radius: 0 0 12px 12px; margin: 0 -20px -14px; overflow: hidden; }
.toast-progress-bar { height: 100%; animation: progress 4s linear forwards; }
@keyframes progress { from { width: 100%; } to { width: 0; } }

/* 타입별 */
.toast-success .toast-icon { background: #dcfce7; color: #16a34a; }
.toast-success .toast-progress-bar { background: #16a34a; }
.toast-error .toast-icon { background: #fee2e2; color: #ef4444; }
.toast-error .toast-progress-bar { background: #ef4444; }
.toast-warning .toast-icon { background: #fef3c7; color: #f59e0b; }
.toast-warning .toast-progress-bar { background: #f59e0b; }
.toast-info .toast-icon { background: #dbeafe; color: #3b82f6; }
.toast-info .toast-progress-bar { background: #3b82f6; }
</style>
</head>
<body>

<h2 style="margin-bottom:1rem;">토스트 알림</h2>
<div class="trigger-row">
  <button class="btn" style="background:#16a34a;" onclick="showToast('success','저장 완료','변경 사항이 저장되었습니다.')">✓ 성공</button>
  <button class="btn" style="background:#ef4444;" onclick="showToast('error','저장 실패','서버 오류가 발생했습니다.')">✕ 에러</button>
  <button class="btn" style="background:#f59e0b;" onclick="showToast('warning','주의','저장 공간이 부족합니다.')">⚠ 경고</button>
  <button class="btn" style="background:#3b82f6;" onclick="showToast('info','알림','새 업데이트가 있습니다.')">ℹ 정보</button>
</div>

<div class="toast-container" id="toastContainer"></div>

<script>
const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };

function showToast(type, title, message) {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div class="toast-icon">${icons[type]}</div>
    <div class="toast-content">
      <div class="toast-title">${title}</div>
      <div class="toast-message">${message}</div>
    </div>
    <button class="toast-close" onclick="removeToast(this.parentElement)">✕</button>
    <div class="toast-progress"><div class="toast-progress-bar"></div></div>
  `;
  container.appendChild(toast);
  setTimeout(() => removeToast(toast), 4000);
}

function removeToast(toast) {
  if (!toast || toast.classList.contains('removing')) return;
  toast.classList.add('removing');
  setTimeout(() => toast.remove(), 300);
}
</script>

</body>
</html>
```

성공/에러/경고/정보 4가지 타입 + 프로그레스 바 + 자동 닫힘 + 수동 닫기가 포함된 토스트 알림입니다!'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/design_code.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 디자인 코드 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  디자인 코드: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
