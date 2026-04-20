"""화랑 AI 웹디자인 샘플 + 어드민/사용자 최신 패턴 학습 데이터

실제 HTML/CSS 코드로 최신 디자인 패턴 학습.
2025 트렌드: Bento Grid, 글래스모피즘, 다크모드, 마이크로인터랙션.

사용법:
    python scripts/data/build_design_samples.py --output data/sft/design_samples.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
디자인 요청 시 반드시 실제 실행 가능한 HTML/CSS 코드를 생성합니다.
텍스트 설명이 아닌, 브라우저에서 바로 볼 수 있는 완전한 코드를 작성합니다.
최신 2025 디자인 트렌드를 반영하고, 설명은 한국어로 합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 가격표 페이지 ═══
    m("가격표 페이지 디자인 해줘 SaaS용으로",
'''SaaS 가격표 페이지를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>가격표</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#f8fafc;color:#1f2937}
.container{max-width:1100px;margin:0 auto;padding:4rem 1.5rem;text-align:center}
h1{font-size:2.5rem;font-weight:800;margin-bottom:.5rem}
.sub{color:#6b7280;font-size:1.1rem;margin-bottom:1rem}
.toggle{display:inline-flex;background:#e2e8f0;border-radius:10px;padding:4px;margin-bottom:3rem}
.toggle button{padding:8px 20px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;background:transparent;color:#64748b;transition:.2s}
.toggle button.active{background:#fff;color:#1f2937;box-shadow:0 1px 3px rgba(0,0,0,.1)}
.save-badge{display:inline-block;background:#dcfce7;color:#16a34a;font-size:12px;font-weight:600;padding:2px 8px;border-radius:6px;margin-left:6px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1.5rem;text-align:left}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:20px;padding:2rem;transition:.3s;position:relative}
.card:hover{box-shadow:0 12px 40px rgba(0,0,0,.08);transform:translateY(-4px)}
.card.popular{border:2px solid #3b82f6;box-shadow:0 8px 30px rgba(59,130,246,.15)}
.card.popular::before{content:'가장 인기';position:absolute;top:-13px;left:50%;transform:translateX(-50%);background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;padding:4px 16px;border-radius:20px;font-size:12px;font-weight:600}
.plan-name{font-size:1.2rem;font-weight:700;margin-bottom:.25rem}
.plan-desc{color:#6b7280;font-size:14px;margin-bottom:1.5rem}
.price{font-size:3rem;font-weight:800;line-height:1}
.price span{font-size:1rem;font-weight:400;color:#6b7280}
.price-period{color:#9ca3af;font-size:13px;margin-top:.25rem;margin-bottom:1.5rem}
.features{list-style:none;margin-bottom:2rem}
.features li{padding:8px 0;font-size:14px;color:#4b5563;display:flex;align-items:center;gap:8px}
.features li::before{content:'✓';color:#16a34a;font-weight:700;font-size:16px}
.features li.disabled{color:#d1d5db}
.features li.disabled::before{content:'—';color:#d1d5db}
.btn{display:block;width:100%;padding:13px;border:none;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;transition:.2s;text-align:center}
.btn-primary{background:#3b82f6;color:#fff}
.btn-primary:hover{background:#2563eb}
.btn-outline{background:#fff;border:1.5px solid #d1d5db;color:#374151}
.btn-outline:hover{border-color:#9ca3af;background:#f9fafb}
@media(max-width:768px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="container">
<h1>합리적인 가격</h1>
<p class="sub">14일 무료 체험. 언제든 취소 가능.</p>
<div class="toggle">
<button class="active">월간</button>
<button>연간 <span class="save-badge">20% 할인</span></button>
</div>
<div class="grid">
<div class="card">
<div class="plan-name">Starter</div>
<div class="plan-desc">개인 사용자를 위한 플랜</div>
<div class="price">₩0<span>/월</span></div>
<div class="price-period">영원히 무료</div>
<ul class="features">
<li>하루 50회 질문</li>
<li>기본 AI 모델</li>
<li>한국어 지원</li>
<li class="disabled">API 접근</li>
<li class="disabled">우선 지원</li>
</ul>
<button class="btn btn-outline">무료로 시작</button>
</div>
<div class="card popular">
<div class="plan-name">Pro</div>
<div class="plan-desc">전문 개발자를 위한 플랜</div>
<div class="price">₩29,000<span>/월</span></div>
<div class="price-period">연간 결제 시 ₩23,200/월</div>
<ul class="features">
<li>무제한 질문</li>
<li>고급 AI 모델 (30B)</li>
<li>코드 생성 + 디자인</li>
<li>API 접근 (월 100K 토큰)</li>
<li>이메일 지원</li>
</ul>
<button class="btn btn-primary">Pro 시작하기</button>
</div>
<div class="card">
<div class="plan-name">Team</div>
<div class="plan-desc">팀 협업을 위한 플랜</div>
<div class="price">₩99,000<span>/월</span></div>
<div class="price-period">팀원당, 연간 결제 시 ₩79,200</div>
<ul class="features">
<li>Pro 모든 기능</li>
<li>팀원 최대 50명</li>
<li>관리자 대시보드</li>
<li>SSO / SAML 인증</li>
<li>전담 매니저 지원</li>
</ul>
<button class="btn btn-outline">영업팀 문의</button>
</div>
</div>
</div>
</body>
</html>
```

월간/연간 토글, 인기 플랜 강조, 기능 비교 리스트가 포함된 SaaS 가격표입니다!'''),

    # ═══ 사용자 설정 페이지 ═══
    m("사용자 설정 페이지 디자인 해줘",
'''사용자 설정 페이지를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>설정</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#f8fafc;color:#1f2937}
.layout{display:flex;max-width:1000px;margin:2rem auto;gap:2rem;padding:0 1rem}
.sidebar{width:220px;flex-shrink:0}
.sidebar h2{font-size:1.3rem;margin-bottom:1.5rem}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:10px;font-size:14px;color:#64748b;cursor:pointer;margin-bottom:2px;transition:.2s;text-decoration:none}
.nav-item:hover{background:#f1f5f9;color:#1f2937}
.nav-item.active{background:#eff6ff;color:#3b82f6;font-weight:600}
.content{flex:1}
.section{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:1.5rem;margin-bottom:1.5rem}
.section-title{font-size:1rem;font-weight:600;margin-bottom:.25rem}
.section-desc{font-size:13px;color:#6b7280;margin-bottom:1.5rem}
.form-row{display:flex;gap:1rem;margin-bottom:1rem}
.form-group{flex:1}
.form-group label{display:block;font-size:13px;font-weight:500;margin-bottom:6px;color:#374151}
.form-group input,.form-group select{width:100%;padding:10px 14px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;outline:none;transition:.2s}
.form-group input:focus,.form-group select:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.1)}
.avatar-section{display:flex;align-items:center;gap:1rem;margin-bottom:1.5rem}
.avatar{width:64px;height:64px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:#fff;display:flex;align-items:center;justify-content:center;font-size:1.5rem;font-weight:700}
.avatar-actions{display:flex;gap:8px}
.btn-sm{padding:8px 16px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;border:none;transition:.2s}
.btn-blue{background:#3b82f6;color:#fff}.btn-blue:hover{background:#2563eb}
.btn-gray{background:#f1f5f9;color:#374151;border:1px solid #e2e8f0}.btn-gray:hover{background:#e2e8f0}
.btn-red{background:#fef2f2;color:#ef4444;border:1px solid #fecaca}.btn-red:hover{background:#fee2e2}
.toggle-row{display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid #f1f5f9}
.toggle-row:last-child{border-bottom:none}
.toggle-info .title{font-size:14px;font-weight:500}
.toggle-info .desc{font-size:12px;color:#9ca3af;margin-top:2px}
.toggle{width:44px;height:24px;background:#d1d5db;border-radius:12px;position:relative;cursor:pointer;transition:.2s;flex-shrink:0}
.toggle.on{background:#3b82f6}
.toggle::after{content:'';position:absolute;width:20px;height:20px;background:#fff;border-radius:50%;top:2px;left:2px;transition:.2s;box-shadow:0 1px 3px rgba(0,0,0,.2)}
.toggle.on::after{left:22px}
.divider{height:1px;background:#e5e7eb;margin:1.5rem 0}
.danger-zone{border-color:#fecaca}
.danger-zone .section-title{color:#ef4444}
</style>
</head>
<body>
<div class="layout">
<aside class="sidebar">
<h2>설정</h2>
<a class="nav-item active" href="#">👤 프로필</a>
<a class="nav-item" href="#">🔒 보안</a>
<a class="nav-item" href="#">🔔 알림</a>
<a class="nav-item" href="#">🎨 외관</a>
<a class="nav-item" href="#">💳 결제</a>
<a class="nav-item" href="#">🔗 연동</a>
<a class="nav-item" href="#">📊 사용량</a>
</aside>
<main class="content">
<div class="section">
<div class="section-title">프로필 정보</div>
<div class="section-desc">공개 프로필과 개인 정보를 관리합니다.</div>
<div class="avatar-section">
<div class="avatar">홍</div>
<div><div class="avatar-actions"><button class="btn-sm btn-blue">사진 변경</button><button class="btn-sm btn-gray">삭제</button></div></div>
</div>
<div class="form-row">
<div class="form-group"><label>이름</label><input value="홍길동"></div>
<div class="form-group"><label>사용자명</label><input value="@honggildong"></div>
</div>
<div class="form-row">
<div class="form-group"><label>이메일</label><input type="email" value="hong@example.com"></div>
<div class="form-group"><label>전화번호</label><input type="tel" value="010-1234-5678"></div>
</div>
<div style="text-align:right;margin-top:1rem"><button class="btn-sm btn-blue">변경사항 저장</button></div>
</div>
<div class="section">
<div class="section-title">알림 설정</div>
<div class="section-desc">알림 수신 방식을 설정합니다.</div>
<div class="toggle-row">
<div class="toggle-info"><div class="title">이메일 알림</div><div class="desc">새 기능 및 업데이트 소식</div></div>
<div class="toggle on" onclick="this.classList.toggle('on')"></div>
</div>
<div class="toggle-row">
<div class="toggle-info"><div class="title">보안 알림</div><div class="desc">로그인 시도 및 비밀번호 변경</div></div>
<div class="toggle on" onclick="this.classList.toggle('on')"></div>
</div>
<div class="toggle-row">
<div class="toggle-info"><div class="title">마케팅 알림</div><div class="desc">프로모션 및 이벤트 정보</div></div>
<div class="toggle" onclick="this.classList.toggle('on')"></div>
</div>
<div class="toggle-row">
<div class="toggle-info"><div class="title">주간 리포트</div><div class="desc">AI 사용량 요약 리포트</div></div>
<div class="toggle on" onclick="this.classList.toggle('on')"></div>
</div>
</div>
<div class="section danger-zone">
<div class="section-title">위험 구역</div>
<div class="section-desc">계정 삭제는 되돌릴 수 없습니다.</div>
<button class="btn-sm btn-red">계정 삭제</button>
</div>
</main>
</div>
</body>
</html>
```

사이드 네비게이션 + 프로필 수정 + 알림 토글 + 위험 구역이 포함된 설정 페이지입니다!'''),

    # ═══ 어드민 통계 ═══
    m("어드민 통계 대시보드 디자인 해줘 차트 포함",
'''어드민 통계 대시보드를 만들어 드릴게요. CSS로 차트를 구현합니다.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>통계 대시보드</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
.dashboard{max-width:1200px;margin:0 auto;padding:2rem}
h1{font-size:1.5rem;margin-bottom:.5rem;color:#fff}
.subtitle{color:#64748b;margin-bottom:2rem;font-size:14px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:2rem}
.stat{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:1.25rem}
.stat .label{font-size:12px;color:#64748b;margin-bottom:.5rem}
.stat .value{font-size:1.8rem;font-weight:700;color:#fff}
.stat .change{font-size:13px;margin-top:.25rem}
.stat .up{color:#4ade80}
.stat .down{color:#f87171}
.charts{display:grid;grid-template-columns:2fr 1fr;gap:1rem;margin-bottom:2rem}
.chart-card{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:1.5rem}
.chart-card h3{font-size:14px;color:#94a3b8;margin-bottom:1rem}
.bar-chart{display:flex;align-items:flex-end;gap:8px;height:200px;padding-top:1rem}
.bar-group{flex:1;display:flex;flex-direction:column;align-items:center;gap:6px}
.bar{width:100%;border-radius:6px 6px 0 0;background:linear-gradient(180deg,#3b82f6,#6366f1);min-height:4px;transition:.3s}
.bar:hover{opacity:.8}
.bar-label{font-size:11px;color:#64748b}
.donut{width:180px;height:180px;border-radius:50%;margin:0 auto;position:relative;background:conic-gradient(#3b82f6 0% 45%,#8b5cf6 45% 70%,#f59e0b 70% 85%,#334155 85% 100%)}
.donut::after{content:'';position:absolute;inset:30%;border-radius:50%;background:#1e293b}
.donut-center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:1}
.donut-value{font-size:1.5rem;font-weight:700;color:#fff}
.donut-label{font-size:12px;color:#64748b}
.legend{display:flex;flex-direction:column;gap:8px;margin-top:1.5rem}
.legend-item{display:flex;align-items:center;gap:8px;font-size:13px}
.legend-dot{width:10px;height:10px;border-radius:3px;flex-shrink:0}
.legend-item span{color:#94a3b8;margin-left:auto}
.activity{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:1.5rem}
.activity h3{font-size:14px;color:#94a3b8;margin-bottom:1rem}
.activity-item{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid #1e293b}
.activity-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.activity-text{flex:1;font-size:13px}
.activity-time{font-size:12px;color:#475569}
</style>
</head>
<body>
<div class="dashboard">
<h1>통계 대시보드</h1>
<p class="subtitle">최근 30일 기준</p>
<div class="stats">
<div class="stat"><div class="label">총 사용자</div><div class="value">12,847</div><div class="change up">↑ 12.5%</div></div>
<div class="stat"><div class="label">활성 사용자 (DAU)</div><div class="value">3,421</div><div class="change up">↑ 8.2%</div></div>
<div class="stat"><div class="label">총 대화 수</div><div class="value">89,234</div><div class="change up">↑ 23.1%</div></div>
<div class="stat"><div class="label">평균 응답시간</div><div class="value">1.2초</div><div class="change up">↓ 15%</div></div>
</div>
<div class="charts">
<div class="chart-card">
<h3>일별 API 호출 수</h3>
<div class="bar-chart">
<div class="bar-group"><div class="bar" style="height:60%"></div><div class="bar-label">월</div></div>
<div class="bar-group"><div class="bar" style="height:75%"></div><div class="bar-label">화</div></div>
<div class="bar-group"><div class="bar" style="height:90%"></div><div class="bar-label">수</div></div>
<div class="bar-group"><div class="bar" style="height:65%"></div><div class="bar-label">목</div></div>
<div class="bar-group"><div class="bar" style="height:85%"></div><div class="bar-label">금</div></div>
<div class="bar-group"><div class="bar" style="height:45%"></div><div class="bar-label">토</div></div>
<div class="bar-group"><div class="bar" style="height:35%"></div><div class="bar-label">일</div></div>
<div class="bar-group"><div class="bar" style="height:70%"></div><div class="bar-label">월</div></div>
<div class="bar-group"><div class="bar" style="height:80%"></div><div class="bar-label">화</div></div>
<div class="bar-group"><div class="bar" style="height:95%"></div><div class="bar-label">수</div></div>
<div class="bar-group"><div class="bar" style="height:72%"></div><div class="bar-label">목</div></div>
<div class="bar-group"><div class="bar" style="height:88%"></div><div class="bar-label">금</div></div>
</div>
</div>
<div class="chart-card">
<h3>카테고리별 사용량</h3>
<div style="position:relative">
<div class="donut"><div class="donut-center"><div class="donut-value">89K</div><div class="donut-label">총 호출</div></div></div>
</div>
<div class="legend">
<div class="legend-item"><div class="legend-dot" style="background:#3b82f6"></div>코딩 <span>45%</span></div>
<div class="legend-item"><div class="legend-dot" style="background:#8b5cf6"></div>일반 대화 <span>25%</span></div>
<div class="legend-item"><div class="legend-dot" style="background:#f59e0b"></div>문서 작성 <span>15%</span></div>
<div class="legend-item"><div class="legend-dot" style="background:#334155"></div>기타 <span>15%</span></div>
</div>
</div>
</div>
<div class="activity">
<h3>최근 활동</h3>
<div class="activity-item"><div class="activity-dot" style="background:#4ade80"></div><div class="activity-text">새 사용자 가입: hong@example.com</div><div class="activity-time">2분 전</div></div>
<div class="activity-item"><div class="activity-dot" style="background:#3b82f6"></div><div class="activity-text">API 키 생성: team-production</div><div class="activity-time">15분 전</div></div>
<div class="activity-item"><div class="activity-dot" style="background:#f59e0b"></div><div class="activity-text">플랜 업그레이드: Pro → Team</div><div class="activity-time">1시간 전</div></div>
<div class="activity-item"><div class="activity-dot" style="background:#f87171"></div><div class="activity-text">Rate Limit 초과: 203.0.113.42</div><div class="activity-time">3시간 전</div></div>
</div>
</div>
</body>
</html>
```

다크 테마 통계 대시보드 + CSS 바 차트 + 도넛 차트 + 활동 로그입니다!'''),

    # ═══ Bento Grid ═══
    m("벤토 그리드 디자인 해줘 Apple 스타일로",
'''Apple 스타일 벤토 그리드를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bento Grid</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#000;color:#fff;padding:2rem}
.bento{display:grid;grid-template-columns:repeat(4,1fr);grid-template-rows:repeat(3,200px);gap:16px;max-width:1200px;margin:0 auto}
.cell{border-radius:24px;padding:2rem;overflow:hidden;position:relative;transition:.3s}
.cell:hover{transform:scale(1.02)}
.cell h2{font-size:1.5rem;font-weight:700;margin-bottom:.5rem;position:relative;z-index:1}
.cell p{font-size:14px;color:rgba(255,255,255,.7);position:relative;z-index:1;line-height:1.5}
.cell .big-icon{position:absolute;right:1.5rem;bottom:1rem;font-size:4rem;opacity:.3}
.c1{grid-column:span 2;grid-row:span 2;background:linear-gradient(135deg,#1d4ed8,#7c3aed);display:flex;flex-direction:column;justify-content:flex-end}
.c1 h2{font-size:2.2rem}
.c2{background:linear-gradient(135deg,#0f766e,#059669)}
.c3{background:linear-gradient(135deg,#9333ea,#c026d3)}
.c4{grid-column:span 2;background:linear-gradient(135deg,#1e293b,#334155)}
.c5{background:linear-gradient(135deg,#ea580c,#dc2626)}
.c6{background:linear-gradient(135deg,#0369a1,#0284c7)}
.c7{grid-column:span 2;background:#1e293b;display:flex;align-items:center;gap:2rem}
.counter{text-align:center}
.counter .num{font-size:2.5rem;font-weight:800;background:linear-gradient(135deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.counter .label{font-size:12px;color:#64748b;margin-top:.25rem}
@media(max-width:768px){.bento{grid-template-columns:repeat(2,1fr);grid-template-rows:auto}.c1{grid-column:span 2}.c4,.c7{grid-column:span 2}}
</style>
</head>
<body>
<div class="bento">
<div class="cell c1">
<h2>AI로 업무를<br>10배 빠르게</h2>
<p>코딩, 디자인, 문서 작성을 도와드립니다</p>
<div class="big-icon">🚀</div>
</div>
<div class="cell c2">
<h2>코드 생성</h2>
<p>50+ 언어 지원</p>
<div class="big-icon">💻</div>
</div>
<div class="cell c3">
<h2>디자인</h2>
<p>UI/UX 실시간 생성</p>
<div class="big-icon">🎨</div>
</div>
<div class="cell c4">
<h2>엔터프라이즈 보안</h2>
<p>SOC 2 인증, 데이터 암호화, SSO 지원으로 기업 보안 요구사항을 충족합니다.</p>
<div class="big-icon">🔒</div>
</div>
<div class="cell c5">
<h2>실시간</h2>
<p>스트리밍 응답</p>
<div class="big-icon">⚡</div>
</div>
<div class="cell c6">
<h2>API</h2>
<p>OpenAI 호환</p>
<div class="big-icon">🔗</div>
</div>
<div class="cell c7">
<div class="counter"><div class="num">12,847</div><div class="label">사용자</div></div>
<div class="counter"><div class="num">89K</div><div class="label">일일 요청</div></div>
<div class="counter"><div class="num">99.9%</div><div class="label">가동률</div></div>
<div class="counter"><div class="num">1.2초</div><div class="label">평균 응답</div></div>
</div>
</div>
</body>
</html>
```

다양한 크기의 카드가 격자로 배치된 벤토 그리드입니다. 그라데이션 + 큰 아이콘 + 통계 카운터 포함!'''),

    # ═══ 채팅 UI ═══
    m("채팅 UI 디자인 해줘 메신저 스타일로",
'''메신저 스타일 채팅 UI를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>채팅</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#0f172a;display:flex;justify-content:center;align-items:center;min-height:100vh}
.chat{width:420px;height:700px;background:#1e293b;border-radius:24px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.chat-header{display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid #334155}
.chat-avatar{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;color:#fff}
.chat-info h3{font-size:15px;color:#fff}
.chat-info p{font-size:12px;color:#4ade80;display:flex;align-items:center;gap:4px}
.chat-info p::before{content:'';width:6px;height:6px;background:#4ade80;border-radius:50%}
.chat-actions{margin-left:auto;display:flex;gap:8px}
.chat-actions button{width:36px;height:36px;border-radius:10px;border:none;background:#334155;color:#94a3b8;cursor:pointer;font-size:16px;transition:.2s}
.chat-actions button:hover{background:#475569}
.messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:80%;display:flex;gap:8px;align-items:flex-end}
.msg-right{align-self:flex-end;flex-direction:row-reverse}
.msg-avatar{width:28px;height:28px;border-radius:50%;background:#334155;display:flex;align-items:center;justify-content:center;font-size:11px;color:#94a3b8;flex-shrink:0}
.msg-bubble{padding:10px 14px;border-radius:16px;font-size:14px;line-height:1.5}
.msg-left .msg-bubble{background:#334155;color:#e2e8f0;border-bottom-left-radius:6px}
.msg-right .msg-bubble{background:#3b82f6;color:#fff;border-bottom-right-radius:6px}
.msg-time{font-size:10px;color:#475569;margin-top:4px}
.typing{display:flex;gap:4px;padding:10px 14px;background:#334155;border-radius:16px;border-bottom-left-radius:6px;width:fit-content}
.typing span{width:7px;height:7px;background:#64748b;border-radius:50%;animation:bounce .6s infinite}
.typing span:nth-child(2){animation-delay:.15s}
.typing span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
.chat-input{display:flex;align-items:center;gap:10px;padding:12px 16px;border-top:1px solid #334155;background:#1e293b}
.chat-input input{flex:1;padding:10px 14px;background:#334155;border:none;border-radius:12px;color:#fff;font-size:14px;outline:none}
.chat-input input::placeholder{color:#64748b}
.send-btn{width:40px;height:40px;border-radius:50%;background:#3b82f6;border:none;color:#fff;cursor:pointer;font-size:18px;display:flex;align-items:center;justify-content:center;transition:.2s}
.send-btn:hover{background:#2563eb;transform:scale(1.05)}
</style>
</head>
<body>
<div class="chat">
<div class="chat-header">
<div class="chat-avatar">H</div>
<div class="chat-info"><h3>화랑 AI</h3><p>온라인</p></div>
<div class="chat-actions"><button>📞</button><button>⋯</button></div>
</div>
<div class="messages">
<div class="msg msg-left"><div class="msg-avatar">H</div><div><div class="msg-bubble">안녕하세요! 화랑 AI입니다. 무엇을 도와드릴까요?</div><div class="msg-time">오전 10:30</div></div></div>
<div class="msg msg-right"><div><div class="msg-bubble">로그인 페이지 디자인 해줘</div><div class="msg-time" style="text-align:right">오전 10:31</div></div></div>
<div class="msg msg-left"><div class="msg-avatar">H</div><div><div class="msg-bubble">네! 로그인 페이지를 만들어 드릴게요. 소셜 로그인도 포함할까요?</div><div class="msg-time">오전 10:31</div></div></div>
<div class="msg msg-right"><div><div class="msg-bubble">응 구글이랑 카카오 포함해줘</div><div class="msg-time" style="text-align:right">오전 10:32</div></div></div>
<div class="msg msg-left"><div class="msg-avatar">H</div><div><div class="msg-bubble">Google + 카카오 소셜 로그인이 포함된 로그인 페이지를 만들고 있습니다. 잠시만 기다려주세요! ✨</div><div class="msg-time">오전 10:32</div></div></div>
<div class="msg msg-left"><div class="msg-avatar">H</div><div class="typing"><span></span><span></span><span></span></div></div>
</div>
<div class="chat-input">
<button style="background:none;border:none;font-size:20px;cursor:pointer">📎</button>
<input placeholder="메시지를 입력하세요...">
<button class="send-btn">→</button>
</div>
</div>
</body>
</html>
```

다크 테마 메신저 + 말풍선 + 타이핑 인디케이터 + 온라인 상태가 포함된 채팅 UI입니다!'''),

    # ═══ 테이블 디자인 ═══
    m("데이터 테이블 디자인 해줘 어드민용",
'''어드민용 데이터 테이블을 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>데이터 테이블</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#f8fafc;padding:2rem}
.table-card{background:#fff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;max-width:1100px;margin:0 auto}
.table-toolbar{display:flex;justify-content:space-between;align-items:center;padding:1.25rem 1.5rem;border-bottom:1px solid #f1f5f9;flex-wrap:wrap;gap:1rem}
.table-toolbar h3{font-size:1.1rem;font-weight:600}
.toolbar-right{display:flex;gap:8px;align-items:center}
.search-box{display:flex;align-items:center;gap:8px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:8px 14px}
.search-box input{border:none;background:none;outline:none;font-size:13px;width:200px}
.filter-btn,.export-btn{padding:8px 16px;border-radius:10px;font-size:13px;font-weight:500;cursor:pointer;transition:.2s}
.filter-btn{background:#f8fafc;border:1px solid #e5e7eb;color:#374151}.filter-btn:hover{background:#f1f5f9}
.export-btn{background:#3b82f6;border:none;color:#fff}.export-btn:hover{background:#2563eb}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:12px 1.5rem;font-size:12px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid #f1f5f9;background:#fafafa}
td{padding:14px 1.5rem;font-size:14px;border-bottom:1px solid #f8fafc}
tr:hover td{background:#f8fafc}
.user-cell{display:flex;align-items:center;gap:10px}
.user-img{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;flex-shrink:0}
.user-name{font-weight:500}
.user-email{font-size:12px;color:#9ca3af}
.badge{padding:4px 10px;border-radius:8px;font-size:12px;font-weight:500;display:inline-block}
.badge-active{background:#dcfce7;color:#166534}
.badge-inactive{background:#f1f5f9;color:#64748b}
.badge-pending{background:#fef3c7;color:#92400e}
.badge-admin{background:#ede9fe;color:#5b21b6}
.actions{display:flex;gap:4px}
.actions button{width:32px;height:32px;border:none;border-radius:8px;background:#f1f5f9;cursor:pointer;font-size:14px;transition:.2s}
.actions button:hover{background:#e2e8f0}
.actions button.delete:hover{background:#fee2e2;color:#ef4444}
.checkbox{width:18px;height:18px;border-radius:5px;border:2px solid #d1d5db;cursor:pointer;accent-color:#3b82f6}
.table-footer{display:flex;justify-content:space-between;align-items:center;padding:1rem 1.5rem;font-size:13px;color:#6b7280}
.pagination{display:flex;gap:4px}
.pagination button{width:32px;height:32px;border:1px solid #e5e7eb;border-radius:8px;background:#fff;cursor:pointer;font-size:13px;transition:.2s}
.pagination button:hover{background:#f1f5f9}
.pagination button.active{background:#3b82f6;color:#fff;border-color:#3b82f6}
</style>
</head>
<body>
<div class="table-card">
<div class="table-toolbar">
<h3>사용자 관리 <span style="font-weight:400;color:#6b7280;font-size:14px">(247명)</span></h3>
<div class="toolbar-right">
<div class="search-box">🔍 <input placeholder="이름 또는 이메일 검색..."></div>
<button class="filter-btn">🔽 필터</button>
<button class="export-btn">📥 내보내기</button>
</div>
</div>
<table>
<thead><tr><th><input type="checkbox" class="checkbox"></th><th>사용자</th><th>역할</th><th>플랜</th><th>상태</th><th>가입일</th><th>작업</th></tr></thead>
<tbody>
<tr><td><input type="checkbox" class="checkbox"></td>
<td><div class="user-cell"><div class="user-img" style="background:#dbeafe;color:#1d4ed8">홍</div><div><div class="user-name">홍길동</div><div class="user-email">hong@example.com</div></div></div></td>
<td><span class="badge badge-admin">관리자</span></td><td>Pro</td><td><span class="badge badge-active">활성</span></td><td>2025.04.20</td>
<td><div class="actions"><button>✏️</button><button class="delete">🗑️</button></div></td></tr>
<tr><td><input type="checkbox" class="checkbox"></td>
<td><div class="user-cell"><div class="user-img" style="background:#fef3c7;color:#92400e">김</div><div><div class="user-name">김철수</div><div class="user-email">kim@example.com</div></div></div></td>
<td>사용자</td><td>Free</td><td><span class="badge badge-active">활성</span></td><td>2025.04.19</td>
<td><div class="actions"><button>✏️</button><button class="delete">🗑️</button></div></td></tr>
<tr><td><input type="checkbox" class="checkbox"></td>
<td><div class="user-cell"><div class="user-img" style="background:#fce7f3;color:#be185d">이</div><div><div class="user-name">이영희</div><div class="user-email">lee@example.com</div></div></div></td>
<td>사용자</td><td>Team</td><td><span class="badge badge-inactive">비활성</span></td><td>2025.04.18</td>
<td><div class="actions"><button>✏️</button><button class="delete">🗑️</button></div></td></tr>
<tr><td><input type="checkbox" class="checkbox"></td>
<td><div class="user-cell"><div class="user-img" style="background:#dcfce7;color:#166534">박</div><div><div class="user-name">박지민</div><div class="user-email">park@example.com</div></div></div></td>
<td>사용자</td><td>Pro</td><td><span class="badge badge-pending">대기</span></td><td>2025.04.17</td>
<td><div class="actions"><button>✏️</button><button class="delete">🗑️</button></div></td></tr>
</tbody>
</table>
<div class="table-footer">
<span>1-10 / 총 247건</span>
<div class="pagination">
<button>←</button><button class="active">1</button><button>2</button><button>3</button><button>...</button><button>25</button><button>→</button>
</div>
</div>
</div>
</body>
</html>
```

검색 + 필터 + 체크박스 + 페이지네이션 + 배지 + 액션 버튼이 포함된 어드민 데이터 테이블입니다!'''),

    # ═══ 로딩/스켈레톤 ═══
    m("로딩 스켈레톤 디자인 해줘",
'''로딩 스켈레톤 애니메이션을 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>스켈레톤 로딩</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#f8fafc;padding:2rem}
h2{font-size:1rem;color:#6b7280;margin-bottom:1rem;margin-top:2rem}
h2:first-child{margin-top:0}
.container{max-width:800px;margin:0 auto}

.skeleton{background:#e2e8f0;border-radius:8px;position:relative;overflow:hidden}
.skeleton::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.6),transparent);animation:shimmer 1.5s infinite}
@keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}

/* 카드 스켈레톤 */
.card-skeleton{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:1.5rem;margin-bottom:1rem}
.sk-row{display:flex;align-items:center;gap:12px;margin-bottom:1rem}
.sk-circle{width:40px;height:40px;border-radius:50%}
.sk-text{height:14px;flex:1}
.sk-text-sm{height:10px;width:60%}
.sk-block{height:120px;border-radius:12px;margin-bottom:1rem}
.sk-btn{height:40px;width:120px;border-radius:10px}

/* 리스트 */
.list-skeleton{background:#fff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden}
.list-item{display:flex;align-items:center;gap:12px;padding:14px 1.5rem;border-bottom:1px solid #f1f5f9}
.list-item:last-child{border-bottom:none}

/* 그리드 */
.grid-skeleton{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}
.grid-card{background:#fff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden}
.grid-card .sk-img{height:160px;border-radius:0}
.grid-card .body{padding:1rem}
</style>
</head>
<body>
<div class="container">

<h2>카드 스켈레톤</h2>
<div class="card-skeleton">
<div class="sk-row"><div class="skeleton sk-circle"></div><div style="flex:1"><div class="skeleton sk-text" style="margin-bottom:6px"></div><div class="skeleton sk-text-sm"></div></div></div>
<div class="skeleton sk-block"></div>
<div class="sk-row"><div class="skeleton sk-text" style="width:40%"></div><div class="skeleton sk-btn" style="margin-left:auto"></div></div>
</div>

<h2>리스트 스켈레톤</h2>
<div class="list-skeleton">
<div class="list-item"><div class="skeleton sk-circle"></div><div style="flex:1"><div class="skeleton sk-text" style="margin-bottom:6px"></div><div class="skeleton sk-text-sm"></div></div><div class="skeleton" style="width:60px;height:24px;border-radius:6px"></div></div>
<div class="list-item"><div class="skeleton sk-circle"></div><div style="flex:1"><div class="skeleton sk-text" style="margin-bottom:6px"></div><div class="skeleton sk-text-sm"></div></div><div class="skeleton" style="width:60px;height:24px;border-radius:6px"></div></div>
<div class="list-item"><div class="skeleton sk-circle"></div><div style="flex:1"><div class="skeleton sk-text" style="margin-bottom:6px"></div><div class="skeleton sk-text-sm"></div></div><div class="skeleton" style="width:60px;height:24px;border-radius:6px"></div></div>
</div>

<h2>그리드 스켈레톤</h2>
<div class="grid-skeleton">
<div class="grid-card"><div class="skeleton sk-img"></div><div class="body"><div class="skeleton sk-text" style="margin-bottom:8px"></div><div class="skeleton sk-text-sm" style="margin-bottom:8px"></div><div class="skeleton sk-text" style="width:50%"></div></div></div>
<div class="grid-card"><div class="skeleton sk-img"></div><div class="body"><div class="skeleton sk-text" style="margin-bottom:8px"></div><div class="skeleton sk-text-sm" style="margin-bottom:8px"></div><div class="skeleton sk-text" style="width:50%"></div></div></div>
<div class="grid-card"><div class="skeleton sk-img"></div><div class="body"><div class="skeleton sk-text" style="margin-bottom:8px"></div><div class="skeleton sk-text-sm" style="margin-bottom:8px"></div><div class="skeleton sk-text" style="width:50%"></div></div></div>
</div>

</div>
</body>
</html>
```

카드/리스트/그리드 3가지 스켈레톤 + shimmer 애니메이션이 포함된 로딩 UI입니다!'''),

    # ═══ 이커머스 상품 상세 ═══
    m("이커머스 상품 상세 페이지 디자인 해줘",
'''이커머스 상품 상세 페이지를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>상품 상세</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#fff;color:#1f2937}
.product{max-width:1100px;margin:2rem auto;padding:0 1rem;display:grid;grid-template-columns:1fr 1fr;gap:3rem}
.gallery{position:sticky;top:2rem}
.main-image{aspect-ratio:1/1;background:#f8fafc;border-radius:20px;display:flex;align-items:center;justify-content:center;font-size:6rem;margin-bottom:1rem}
.thumbs{display:flex;gap:8px}
.thumb{width:72px;height:72px;border-radius:12px;background:#f8fafc;display:flex;align-items:center;justify-content:center;font-size:2rem;border:2px solid transparent;cursor:pointer;transition:.2s}
.thumb.active,.thumb:hover{border-color:#3b82f6}
.info{padding:1rem 0}
.breadcrumb{font-size:13px;color:#9ca3af;margin-bottom:1rem}
.breadcrumb a{color:#9ca3af;text-decoration:none}
.brand{font-size:14px;color:#6b7280;margin-bottom:.5rem}
h1{font-size:1.6rem;font-weight:700;margin-bottom:.5rem}
.rating{display:flex;align-items:center;gap:6px;font-size:14px;margin-bottom:1.5rem}
.stars{color:#fbbf24}
.rating span{color:#6b7280}
.price-box{margin-bottom:1.5rem}
.original-price{font-size:14px;color:#9ca3af;text-decoration:line-through}
.price-row{display:flex;align-items:baseline;gap:8px}
.discount{font-size:1.5rem;font-weight:700;color:#ef4444}
.current-price{font-size:2rem;font-weight:800}
.delivery{background:#f0fdf4;border-radius:10px;padding:12px 16px;margin-bottom:1.5rem;font-size:14px;color:#166534;display:flex;align-items:center;gap:8px}
.options{margin-bottom:1.5rem}
.option-label{font-size:14px;font-weight:600;margin-bottom:8px}
.option-group{display:flex;gap:8px;flex-wrap:wrap}
.option-btn{padding:10px 18px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;cursor:pointer;transition:.2s;background:#fff}
.option-btn:hover{border-color:#3b82f6}
.option-btn.selected{border-color:#3b82f6;background:#eff6ff;color:#3b82f6;font-weight:600}
.qty{display:flex;align-items:center;gap:0;margin-bottom:1.5rem}
.qty button{width:40px;height:40px;border:1px solid #e2e8f0;background:#f8fafc;font-size:18px;cursor:pointer}
.qty button:first-child{border-radius:10px 0 0 10px}
.qty button:last-child{border-radius:0 10px 10px 0}
.qty input{width:60px;height:40px;border:1px solid #e2e8f0;border-left:none;border-right:none;text-align:center;font-size:16px;font-weight:600;outline:none}
.btn-group{display:flex;gap:10px}
.btn-cart{flex:1;padding:16px;background:#fff;border:1.5px solid #3b82f6;color:#3b82f6;border-radius:14px;font-size:16px;font-weight:600;cursor:pointer;transition:.2s}
.btn-cart:hover{background:#eff6ff}
.btn-buy{flex:1;padding:16px;background:#3b82f6;border:none;color:#fff;border-radius:14px;font-size:16px;font-weight:600;cursor:pointer;transition:.2s}
.btn-buy:hover{background:#2563eb}
@media(max-width:768px){.product{grid-template-columns:1fr}.gallery{position:static}}
</style>
</head>
<body>
<div class="product">
<div class="gallery">
<div class="main-image">🎧</div>
<div class="thumbs">
<div class="thumb active">🎧</div>
<div class="thumb">📦</div>
<div class="thumb">🔌</div>
<div class="thumb">📱</div>
</div>
</div>
<div class="info">
<div class="breadcrumb"><a href="#">홈</a> / <a href="#">전자기기</a> / <a href="#">헤드폰</a></div>
<div class="brand">소니 (SONY)</div>
<h1>WH-1000XM5 무선 노이즈캔슬링 헤드폰</h1>
<div class="rating"><span class="stars">★★★★★</span> 4.8 <span>(2,341개 리뷰)</span></div>
<div class="price-box">
<div class="original-price">정가 ₩399,000</div>
<div class="price-row"><span class="discount">20%</span><span class="current-price">₩319,000</span></div>
</div>
<div class="delivery">🚚 내일 도착 예정 (무료배송)</div>
<div class="options">
<div class="option-label">색상</div>
<div class="option-group">
<button class="option-btn selected">블랙</button>
<button class="option-btn">실버</button>
<button class="option-btn">미드나잇블루</button>
</div>
</div>
<div class="options">
<div class="option-label">수량</div>
<div class="qty">
<button>−</button>
<input type="number" value="1" min="1">
<button>+</button>
</div>
</div>
<div class="btn-group">
<button class="btn-cart">장바구니</button>
<button class="btn-buy">바로 구매</button>
</div>
</div>
</div>
</body>
</html>
```

상품 갤러리 + 옵션 선택 + 수량 조절 + 장바구니/구매 버튼이 포함된 상품 상세 페이지입니다!'''),

    # ═══ 온보딩 화면 ═══
    m("앱 온보딩 화면 디자인 해줘",
'''앱 온보딩 화면을 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>온보딩</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#0f172a;color:#fff;display:flex;justify-content:center;align-items:center;min-height:100vh}
.phone{width:380px;height:750px;background:#1e293b;border-radius:40px;overflow:hidden;position:relative;box-shadow:0 20px 60px rgba(0,0,0,.5);border:3px solid #334155}
.notch{width:120px;height:28px;background:#0f172a;border-radius:0 0 16px 16px;position:absolute;top:0;left:50%;transform:translateX(-50%);z-index:10}
.slides{display:flex;transition:transform .5s ease;height:100%}
.slide{min-width:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:4rem 2rem 6rem;text-align:center}
.slide-icon{font-size:6rem;margin-bottom:2rem;animation:float 3s ease-in-out infinite}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-15px)}}
.slide h2{font-size:1.5rem;font-weight:700;margin-bottom:1rem}
.slide p{color:#94a3b8;line-height:1.6;font-size:14px}
.s1 .slide-icon{background:linear-gradient(135deg,#dbeafe,#bfdbfe);border-radius:30%;width:120px;height:120px;display:flex;align-items:center;justify-content:center}
.s2 .slide-icon{background:linear-gradient(135deg,#fef3c7,#fde68a);border-radius:30%;width:120px;height:120px;display:flex;align-items:center;justify-content:center}
.s3 .slide-icon{background:linear-gradient(135deg,#d1fae5,#a7f3d0);border-radius:30%;width:120px;height:120px;display:flex;align-items:center;justify-content:center}
.controls{position:absolute;bottom:2rem;left:0;right:0;display:flex;flex-direction:column;align-items:center;gap:1.5rem;padding:0 2rem}
.dots{display:flex;gap:8px}
.dot{width:8px;height:8px;border-radius:4px;background:#475569;transition:.3s}
.dot.active{width:24px;background:#3b82f6}
.btn-start{width:100%;padding:16px;background:#3b82f6;border:none;color:#fff;border-radius:14px;font-size:16px;font-weight:600;cursor:pointer;transition:.2s}
.btn-start:hover{background:#2563eb}
.skip{color:#64748b;font-size:14px;cursor:pointer;position:absolute;top:3rem;right:1.5rem}
</style>
</head>
<body>
<div class="phone">
<div class="notch"></div>
<span class="skip" onclick="goTo(2)">건너뛰기</span>
<div class="slides" id="slides">
<div class="slide s1"><div class="slide-icon">🤖</div><h2>AI와 대화하세요</h2><p>한국어에 최적화된 AI가 코딩, 디자인, 문서 작성을 도와드립니다.</p></div>
<div class="slide s2"><div class="slide-icon">⚡</div><h2>빠른 응답</h2><p>실시간 스트리밍으로 즉시 답변을 받아보세요. 기다림 없이 바로 시작합니다.</p></div>
<div class="slide s3"><div class="slide-icon">🔒</div><h2>안전한 사용</h2><p>모든 대화는 암호화되며, 개인정보는 철저히 보호됩니다.</p></div>
</div>
<div class="controls">
<div class="dots"><div class="dot active" id="d0"></div><div class="dot" id="d1"></div><div class="dot" id="d2"></div></div>
<button class="btn-start" id="nextBtn" onclick="next()">다음</button>
</div>
</div>
<script>
let current=0;
function goTo(i){current=i;update()}
function next(){current=Math.min(current+1,2);update()}
function update(){
document.getElementById('slides').style.transform=`translateX(-${current*100}%)`;
for(let i=0;i<3;i++){document.getElementById('d'+i).className=i===current?'dot active':'dot'}
document.getElementById('nextBtn').textContent=current===2?'시작하기':'다음';
}
</script>
</body>
</html>
```

모바일 프레임 + 3단계 슬라이드 + 플로팅 아이콘 애니메이션 + 인디케이터가 포함된 온보딩 화면입니다!'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/design_samples.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 웹디자인 샘플 + 어드민 패턴 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  디자인 샘플: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
