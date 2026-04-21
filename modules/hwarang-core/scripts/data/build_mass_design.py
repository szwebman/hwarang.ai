"""화랑 AI 대량 디자인 학습 데이터 (100건+)

모든 디자인 요청에 실제 HTML/CSS 코드를 출력하도록 학습.
클로드 수준의 디자인 코드 생성 능력 확보.

카테고리:
  - 웹 컴포넌트 (30건): 카드, 폼, 리스트, 배지, 아바타, 탭, 아코디언 등
  - 페이지 레이아웃 (20건): 사이드바, 그리드, 히어로, 섹션 등
  - 어드민/대시보드 (15건): 테이블, 차트, KPI, 필터 등
  - 이커머스 (15건): 상품, 장바구니, 결제, 리뷰 등
  - 모바일/앱 (10건): 바텀시트, 탭바, 카드스와이프 등
  - 마이크로인터랙션 (10건): 애니메이션, 전환, 피드백 등

사용법:
    python scripts/data/build_mass_design.py --output data/sft/mass_design.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
디자인 요청 시 반드시 실제 실행 가능한 완전한 HTML/CSS 코드를 생성합니다.
텍스트 설명이나 아스키 아트가 아닌, 브라우저에서 바로 볼 수 있는 코드를 작성합니다.
최신 2025 디자인 트렌드를 반영하고, 설명은 한국어로 합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

def html_wrap(title, css, body):
    """완전한 HTML 문서 래퍼."""
    return f'''```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Pretendard',-apple-system,sans-serif;{css.get('body','')}}}
{css.get('styles','')}
</style>
</head>
<body>
{body}
</body>
</html>
```'''

DATA = []

# ════════════════════════════════════════════════════════════════
# 웹 컴포넌트 (30건)
# ════════════════════════════════════════════════════════════════

# 1. 아코디언
DATA.append(m("아코디언 FAQ 디자인 해줘", f'''FAQ 아코디언을 만들어 드릴게요.

{html_wrap("FAQ 아코디언", {"body":"background:#f8fafc;padding:2rem","styles":"""
.faq{{max-width:700px;margin:0 auto}}
h1{{font-size:1.8rem;text-align:center;margin-bottom:2rem}}
.item{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;margin-bottom:8px;overflow:hidden}}
.question{{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;cursor:pointer;font-weight:600;font-size:15px;transition:.2s}}
.question:hover{{background:#f8fafc}}
.question .arrow{{transition:transform .3s;font-size:12px;color:#6b7280}}
.item.open .arrow{{transform:rotate(180deg)}}
.answer{{max-height:0;overflow:hidden;transition:max-height .3s ease;padding:0 20px}}
.item.open .answer{{max-height:200px;padding:0 20px 16px}}
.answer p{{color:#6b7280;font-size:14px;line-height:1.7}}
"""}, """
<div class="faq">
<h1>자주 묻는 질문</h1>
<div class="item open" onclick="this.classList.toggle('open')">
<div class="question">화랑 AI는 무료인가요? <span class="arrow">▼</span></div>
<div class="answer"><p>네, 기본 플랜은 무료입니다. 하루 50회 질문이 가능하며, 더 많은 기능이 필요하시면 Pro 플랜을 이용해 주세요.</p></div>
</div>
<div class="item" onclick="this.classList.toggle('open')">
<div class="question">어떤 프로그래밍 언어를 지원하나요? <span class="arrow">▼</span></div>
<div class="answer"><p>Python, JavaScript, TypeScript, Go, Rust, Java, C#, Swift 등 50개 이상의 언어를 지원합니다.</p></div>
</div>
<div class="item" onclick="this.classList.toggle('open')">
<div class="question">데이터 보안은 어떻게 되나요? <span class="arrow">▼</span></div>
<div class="answer"><p>모든 대화는 암호화되며, 사용자 데이터는 한국 내 서버에 안전하게 보관됩니다. ISMS 인증을 받았습니다.</p></div>
</div>
<div class="item" onclick="this.classList.toggle('open')">
<div class="question">API를 사용할 수 있나요? <span class="arrow">▼</span></div>
<div class="answer"><p>Pro 플랜 이상에서 REST API를 제공합니다. OpenAI 호환 형식이라 기존 코드를 거의 수정 없이 사용 가능합니다.</p></div>
</div>
<div class="item" onclick="this.classList.toggle('open')">
<div class="question">환불 정책은 어떻게 되나요? <span class="arrow">▼</span></div>
<div class="answer"><p>결제 후 7일 이내 무조건 전액 환불이 가능합니다. 고객센터로 연락해 주세요.</p></div>
</div>
</div>
""")}

클릭하면 열리고 닫히는 FAQ 아코디언입니다!'''))

# 2. 탭 컴포넌트
DATA.append(m("탭 컴포넌트 디자인 해줘", f'''탭 컴포넌트를 만들어 드릴게요.

{html_wrap("탭", {"body":"background:#f8fafc;padding:2rem;display:flex;justify-content:center","styles":"""
.tabs{{max-width:600px;width:100%}}
.tab-header{{display:flex;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:4px;margin-bottom:1.5rem}}
.tab-btn{{flex:1;padding:10px;border:none;background:none;border-radius:8px;font-size:14px;font-weight:500;cursor:pointer;color:#6b7280;transition:.2s}}
.tab-btn.active{{background:#3b82f6;color:#fff;box-shadow:0 2px 8px rgba(59,130,246,.3)}}
.tab-content{{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:1.5rem}}
.tab-panel{{display:none}}
.tab-panel.active{{display:block}}
.tab-panel h3{{font-size:1.1rem;margin-bottom:.75rem}}
.tab-panel p{{color:#6b7280;line-height:1.7;font-size:14px}}
"""}, """
<div class="tabs">
<div class="tab-header">
<button class="tab-btn active" onclick="switchTab(0)">개요</button>
<button class="tab-btn" onclick="switchTab(1)">기능</button>
<button class="tab-btn" onclick="switchTab(2)">가격</button>
<button class="tab-btn" onclick="switchTab(3)">리뷰</button>
</div>
<div class="tab-content">
<div class="tab-panel active"><h3>화랑 AI 개요</h3><p>한국어에 최적화된 AI 어시스턴트입니다. 코딩, 디자인, 문서 작성 등 다양한 작업을 도와드립니다.</p></div>
<div class="tab-panel"><h3>주요 기능</h3><p>코드 생성, 디버깅, 디자인 코드 생성, 문서 번역, 데이터 분석 등 다양한 기능을 제공합니다.</p></div>
<div class="tab-panel"><h3>가격 정보</h3><p>무료 플랜부터 팀 플랜까지 다양한 옵션을 제공합니다. 14일 무료 체험도 가능합니다.</p></div>
<div class="tab-panel"><h3>사용자 리뷰</h3><p>⭐⭐⭐⭐⭐ "한국어 이해가 정말 뛰어나요. 업무 생산성이 확실히 올랐습니다." - 김개발</p></div>
</div>
</div>
<script>
function switchTab(i){
document.querySelectorAll('.tab-btn').forEach((b,j)=>{b.className='tab-btn'+(j===i?' active':'')});
document.querySelectorAll('.tab-panel').forEach((p,j)=>{p.className='tab-panel'+(j===i?' active':'')});
}
</script>
""")}

4개 탭 + 활성 애니메이션이 포함된 탭 컴포넌트입니다!'''))

# 3. 검색 바
DATA.append(m("검색 바 디자인 해줘 자동완성 포함", f'''자동완성 검색 바를 만들어 드릴게요.

{html_wrap("검색", {"body":"background:#0f172a;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:2rem","styles":"""
.search-container{{width:100%;max-width:600px}}
h2{{color:#fff;text-align:center;font-size:1.5rem;margin-bottom:1.5rem}}
.search-box{{position:relative}}
.search-input{{width:100%;padding:16px 20px 16px 48px;background:#1e293b;border:1.5px solid #334155;border-radius:16px;color:#fff;font-size:16px;outline:none;transition:.2s}}
.search-input:focus{{border-color:#3b82f6;box-shadow:0 0 0 4px rgba(59,130,246,.15)}}
.search-input::placeholder{{color:#64748b}}
.search-icon{{position:absolute;left:16px;top:50%;transform:translateY(-50%);color:#64748b;font-size:18px}}
.results{{position:absolute;top:calc(100% + 8px);left:0;right:0;background:#1e293b;border:1px solid #334155;border-radius:14px;overflow:hidden;display:none;box-shadow:0 10px 40px rgba(0,0,0,.3)}}
.search-input:focus ~ .results{{display:block}}
.result-item{{display:flex;align-items:center;gap:12px;padding:12px 16px;cursor:pointer;transition:.2s}}
.result-item:hover{{background:#334155}}
.result-icon{{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}}
.result-text{{flex:1}}
.result-title{{font-size:14px;color:#e2e8f0}}
.result-sub{{font-size:12px;color:#64748b}}
.result-tag{{font-size:11px;padding:3px 8px;border-radius:6px;background:#334155;color:#94a3b8}}
.divider{{height:1px;background:#334155;margin:0 16px}}
.search-footer{{padding:10px 16px;font-size:12px;color:#475569;display:flex;justify-content:space-between}}
.kbd{{background:#334155;padding:2px 6px;border-radius:4px;font-size:11px;color:#94a3b8}}
"""}, """
<div class="search-container">
<h2>무엇을 도와드릴까요?</h2>
<div class="search-box">
<span class="search-icon">🔍</span>
<input class="search-input" placeholder="검색어를 입력하세요..." autofocus>
<div class="results">
<div class="result-item"><div class="result-icon" style="background:#eff6ff">💻</div><div class="result-text"><div class="result-title">React 컴포넌트 만들기</div><div class="result-sub">최근 검색</div></div></div>
<div class="result-item"><div class="result-icon" style="background:#fef3c7">🎨</div><div class="result-text"><div class="result-title">로그인 페이지 디자인</div><div class="result-sub">최근 검색</div></div></div>
<div class="divider"></div>
<div class="result-item"><div class="result-icon" style="background:#f0fdf4">📄</div><div class="result-text"><div class="result-title">파이썬 정렬 알고리즘</div><div class="result-sub">추천</div></div><span class="result-tag">인기</span></div>
<div class="result-item"><div class="result-icon" style="background:#fce7f3">🔒</div><div class="result-text"><div class="result-title">JWT 인증 구현</div><div class="result-sub">추천</div></div><span class="result-tag">신규</span></div>
<div class="search-footer"><span>↑↓ 이동</span><span><span class="kbd">Enter</span> 선택</span><span><span class="kbd">Esc</span> 닫기</span></div>
</div>
</div>
</div>
""")}

다크 테마 검색 바 + 자동완성 드롭다운 + 키보드 단축키 힌트 포함!'''))

# 4. 알림 드롭다운
DATA.append(m("알림 벨 드롭다운 디자인 해줘", f'''알림 벨 드롭다운을 만들어 드릴게요.

{html_wrap("알림", {"body":"background:#f8fafc;padding:2rem;display:flex;justify-content:flex-end","styles":"""
.notification-wrapper{{position:relative}}
.bell-btn{{width:44px;height:44px;border-radius:12px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:20px;position:relative;display:flex;align-items:center;justify-content:center;transition:.2s}}
.bell-btn:hover{{background:#f1f5f9}}
.bell-badge{{position:absolute;top:-4px;right:-4px;width:20px;height:20px;background:#ef4444;color:#fff;border-radius:50%;font-size:11px;font-weight:600;display:flex;align-items:center;justify-content:center;border:2px solid #fff}}
.dropdown{{position:absolute;top:calc(100% + 8px);right:0;width:380px;background:#fff;border:1px solid #e5e7eb;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,.1);display:none;z-index:100}}
.dropdown.open{{display:block;animation:fadeIn .2s}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(-8px)}}to{{opacity:1;transform:translateY(0)}}}}
.dropdown-header{{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid #f1f5f9}}
.dropdown-header h3{{font-size:15px;font-weight:600}}
.mark-read{{font-size:13px;color:#3b82f6;cursor:pointer;border:none;background:none}}
.notif-list{{max-height:360px;overflow-y:auto}}
.notif-item{{display:flex;gap:12px;padding:14px 16px;cursor:pointer;transition:.2s;border-bottom:1px solid #f8fafc}}
.notif-item:hover{{background:#f8fafc}}
.notif-item.unread{{background:#eff6ff}}
.notif-icon{{width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}}
.notif-content{{flex:1;min-width:0}}
.notif-title{{font-size:13px;font-weight:500;line-height:1.4}}
.notif-time{{font-size:12px;color:#9ca3af;margin-top:4px}}
.notif-dot{{width:8px;height:8px;border-radius:50%;background:#3b82f6;flex-shrink:0;margin-top:6px}}
.dropdown-footer{{padding:12px;text-align:center;border-top:1px solid #f1f5f9}}
.dropdown-footer a{{font-size:13px;color:#3b82f6;text-decoration:none;font-weight:500}}
"""}, """
<div class="notification-wrapper">
<button class="bell-btn" onclick="document.querySelector('.dropdown').classList.toggle('open')">
🔔<span class="bell-badge">3</span>
</button>
<div class="dropdown">
<div class="dropdown-header"><h3>알림</h3><button class="mark-read">모두 읽음</button></div>
<div class="notif-list">
<div class="notif-item unread"><div class="notif-icon" style="background:#dcfce7">✅</div><div class="notif-content"><div class="notif-title"><strong>학습 완료!</strong> 화랑 AI v2 모델 학습이 완료되었습니다.</div><div class="notif-time">5분 전</div></div><div class="notif-dot"></div></div>
<div class="notif-item unread"><div class="notif-icon" style="background:#dbeafe">💬</div><div class="notif-content"><div class="notif-title"><strong>새 댓글</strong> 홍길동님이 회의록에 댓글을 남겼습니다.</div><div class="notif-time">30분 전</div></div><div class="notif-dot"></div></div>
<div class="notif-item unread"><div class="notif-icon" style="background:#fef3c7">⚡</div><div class="notif-content"><div class="notif-title"><strong>시스템 알림</strong> 서버 점검이 내일 새벽 2시에 예정되어 있습니다.</div><div class="notif-time">1시간 전</div></div><div class="notif-dot"></div></div>
<div class="notif-item"><div class="notif-icon" style="background:#f1f5f9">👤</div><div class="notif-content"><div class="notif-title">Pro 플랜 갱신이 3일 후 예정입니다.</div><div class="notif-time">어제</div></div></div>
<div class="notif-item"><div class="notif-icon" style="background:#f1f5f9">🎉</div><div class="notif-content"><div class="notif-title">이번 주 AI 사용량: 1,234건 (지난주 대비 +23%)</div><div class="notif-time">3일 전</div></div></div>
</div>
<div class="dropdown-footer"><a href="#">모든 알림 보기 →</a></div>
</div>
</div>
""")}

알림 벨 + 뱃지 카운트 + 읽지 않은 알림 표시 + 드롭다운 포함!'''))

# 5. 사이드바 네비게이션
DATA.append(m("사이드바 네비게이션 디자인 해줘 접었다 펼 수 있게", f'''접이식 사이드바를 만들어 드릴게요.

{html_wrap("사이드바", {"body":"display:flex;min-height:100vh","styles":"""
.sidebar{{width:260px;background:#0f172a;color:#94a3b8;padding:1rem;transition:width .3s;overflow:hidden;display:flex;flex-direction:column}}
.sidebar.collapsed{{width:72px}}
.sidebar-header{{display:flex;align-items:center;gap:10px;padding:.5rem;margin-bottom:1.5rem}}
.sidebar-logo{{width:36px;height:36px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);border-radius:10px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:14px;flex-shrink:0}}
.sidebar-title{{font-size:1.1rem;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;transition:opacity .2s}}
.sidebar.collapsed .sidebar-title{{opacity:0;width:0}}
.toggle-btn{{margin-left:auto;width:28px;height:28px;border-radius:8px;border:none;background:#1e293b;color:#94a3b8;cursor:pointer;font-size:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.toggle-btn:hover{{background:#334155}}
.nav-section{{margin-bottom:1.5rem}}
.nav-label{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#475569;padding:0 .5rem;margin-bottom:.5rem;white-space:nowrap;overflow:hidden}}
.sidebar.collapsed .nav-label{{opacity:0;height:0;margin:0}}
.nav-item{{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;color:#94a3b8;cursor:pointer;margin-bottom:2px;transition:.2s;white-space:nowrap}}
.nav-item:hover{{background:rgba(255,255,255,.06);color:#e2e8f0}}
.nav-item.active{{background:rgba(59,130,246,.15);color:#60a5fa}}
.nav-icon{{font-size:18px;width:24px;text-align:center;flex-shrink:0}}
.nav-text{{font-size:14px;overflow:hidden;transition:opacity .2s}}
.sidebar.collapsed .nav-text{{opacity:0;width:0}}
.nav-badge{{margin-left:auto;background:#ef4444;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px}}
.sidebar.collapsed .nav-badge{{display:none}}
.sidebar-footer{{margin-top:auto;padding:.5rem;border-top:1px solid #1e293b}}
.user-info{{display:flex;align-items:center;gap:10px;padding:.5rem}}
.user-avatar{{width:32px;height:32px;border-radius:8px;background:#334155;display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0}}
.user-name{{font-size:13px;color:#e2e8f0;overflow:hidden}}
.user-role{{font-size:11px;color:#64748b}}
.sidebar.collapsed .user-name,.sidebar.collapsed .user-role{{opacity:0;width:0}}
.main{{flex:1;background:#f8fafc;padding:2rem}}
.main h1{{font-size:1.5rem;color:#1f2937}}
"""}, """
<aside class="sidebar" id="sidebar">
<div class="sidebar-header">
<div class="sidebar-logo">H</div>
<span class="sidebar-title">화랑 AI</span>
<button class="toggle-btn" onclick="document.getElementById('sidebar').classList.toggle('collapsed')">☰</button>
</div>
<div class="nav-section">
<div class="nav-label">메인</div>
<div class="nav-item active"><span class="nav-icon">📊</span><span class="nav-text">대시보드</span></div>
<div class="nav-item"><span class="nav-icon">💬</span><span class="nav-text">대화</span><span class="nav-badge">12</span></div>
<div class="nav-item"><span class="nav-icon">🤖</span><span class="nav-text">모델</span></div>
</div>
<div class="nav-section">
<div class="nav-label">관리</div>
<div class="nav-item"><span class="nav-icon">👥</span><span class="nav-text">사용자</span></div>
<div class="nav-item"><span class="nav-icon">📈</span><span class="nav-text">통계</span></div>
<div class="nav-item"><span class="nav-icon">💳</span><span class="nav-text">결제</span></div>
<div class="nav-item"><span class="nav-icon">⚙️</span><span class="nav-text">설정</span></div>
</div>
<div class="sidebar-footer">
<div class="user-info">
<div class="user-avatar">관</div>
<div><div class="user-name">관리자</div><div class="user-role">admin@hwarang.ai</div></div>
</div>
</div>
</aside>
<main class="main"><h1>대시보드</h1><p style="color:#6b7280;margin-top:.5rem">화랑 AI 관리자 패널입니다.</p></main>
""")}

접기/펼치기 + 섹션 구분 + 뱃지 + 사용자 정보가 포함된 사이드바입니다!'''))

# 6-10. 추가 컴포넌트들
DATA.append(m("진행 바 디자인 해줘 여러 스타일로", f'''다양한 진행 바를 만들어 드릴게요.

{html_wrap("진행 바", {"body":"background:#f8fafc;padding:3rem","styles":"""
.container{{max-width:600px;margin:0 auto}}
h2{{font-size:14px;color:#6b7280;margin:2rem 0 1rem}}h2:first-child{{margin-top:0}}
.progress{{height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden;margin-bottom:.75rem}}
.progress-bar{{height:100%;border-radius:4px;transition:width 1s ease}}
.blue{{background:linear-gradient(90deg,#3b82f6,#6366f1)}}
.green{{background:#16a34a}}
.red{{background:#ef4444}}
.amber{{background:#f59e0b}}
.progress-label{{display:flex;justify-content:space-between;font-size:13px;margin-bottom:.5rem}}
.progress-label span:last-child{{font-weight:600}}
.progress-lg{{height:12px;border-radius:6px}}
.progress-sm{{height:4px;border-radius:2px}}
.striped .progress-bar{{background-image:linear-gradient(45deg,rgba(255,255,255,.15) 25%,transparent 25%,transparent 50%,rgba(255,255,255,.15) 50%,rgba(255,255,255,.15) 75%,transparent 75%);background-size:1rem 1rem;animation:stripe .5s linear infinite}}
@keyframes stripe{{0%{{background-position:0 0}}100%{{background-position:1rem 0}}}}
.circular{{width:80px;height:80px;border-radius:50%;background:conic-gradient(#3b82f6 0% 75%,#e5e7eb 75% 100%);display:flex;align-items:center;justify-content:center;position:relative}}
.circular::after{{content:'';position:absolute;inset:8px;border-radius:50%;background:#f8fafc}}
.circular span{{position:relative;z-index:1;font-size:16px;font-weight:700}}
.steps{{display:flex;align-items:center;gap:0;margin-bottom:1rem}}
.step{{display:flex;align-items:center}}
.step-circle{{width:32px;height:32px;border-radius:50%;border:2px solid #d1d5db;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;color:#6b7280;background:#fff;transition:.2s}}
.step.done .step-circle{{background:#3b82f6;border-color:#3b82f6;color:#fff}}
.step.current .step-circle{{border-color:#3b82f6;color:#3b82f6}}
.step-line{{width:60px;height:2px;background:#d1d5db}}
.step.done + .step .step-line,.step.done .step-line{{background:#3b82f6}}
.step-label{{font-size:11px;text-align:center;margin-top:6px;color:#6b7280}}
"""}, """
<div class="container">
<h2>기본 진행 바</h2>
<div class="progress-label"><span>업로드 중...</span><span>75%</span></div>
<div class="progress"><div class="progress-bar blue" style="width:75%"></div></div>

<h2>컬러 변형</h2>
<div class="progress"><div class="progress-bar green" style="width:90%"></div></div>
<div class="progress"><div class="progress-bar amber" style="width:60%"></div></div>
<div class="progress"><div class="progress-bar red" style="width:30%"></div></div>

<h2>크기 변형</h2>
<div class="progress progress-lg"><div class="progress-bar blue" style="width:65%"></div></div>
<div class="progress progress-sm"><div class="progress-bar blue" style="width:85%"></div></div>

<h2>스트라이프 애니메이션</h2>
<div class="progress striped"><div class="progress-bar blue" style="width:70%"></div></div>

<h2>원형 진행</h2>
<div style="display:flex;gap:2rem">
<div class="circular" style="background:conic-gradient(#3b82f6 0% 75%,#e5e7eb 75%)"><span>75%</span></div>
<div class="circular" style="background:conic-gradient(#16a34a 0% 90%,#e5e7eb 90%)"><span>90%</span></div>
<div class="circular" style="background:conic-gradient(#ef4444 0% 30%,#e5e7eb 30%)"><span>30%</span></div>
</div>

<h2>스텝 진행</h2>
<div class="steps">
<div class="step done"><div class="step-circle">✓</div></div>
<div class="step done"><div class="step-line"></div><div class="step-circle">✓</div></div>
<div class="step current"><div class="step-line"></div><div class="step-circle">3</div></div>
<div class="step"><div class="step-line"></div><div class="step-circle">4</div></div>
</div>
</div>
""")}

바 형태, 원형, 스텝, 스트라이프 등 다양한 진행 바입니다!'''))

# 7. 타임라인
DATA.append(m("타임라인 디자인 해줘", f'''타임라인을 만들어 드릴게요.

{html_wrap("타임라인", {"body":"background:#f8fafc;padding:2rem","styles":"""
.timeline{{max-width:600px;margin:0 auto;position:relative;padding-left:2rem}}
.timeline::before{{content:'';position:absolute;left:7px;top:0;bottom:0;width:2px;background:#e5e7eb}}
.tl-item{{position:relative;padding-bottom:2rem}}
.tl-item:last-child{{padding-bottom:0}}
.tl-dot{{position:absolute;left:-2rem;top:4px;width:16px;height:16px;border-radius:50%;border:3px solid #3b82f6;background:#fff;z-index:1}}
.tl-item.done .tl-dot{{background:#3b82f6}}
.tl-item.done .tl-dot::after{{content:'✓';color:#fff;font-size:9px;display:flex;align-items:center;justify-content:center;height:100%}}
.tl-card{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:1rem 1.25rem}}
.tl-card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.06)}}
.tl-time{{font-size:12px;color:#9ca3af;margin-bottom:.5rem}}
.tl-title{{font-size:15px;font-weight:600;margin-bottom:.25rem}}
.tl-desc{{font-size:13px;color:#6b7280;line-height:1.5}}
.tl-tags{{display:flex;gap:6px;margin-top:.75rem}}
.tl-tag{{padding:3px 8px;background:#f1f5f9;border-radius:6px;font-size:11px;color:#64748b}}
"""}, """
<div class="timeline">
<div class="tl-item done">
<div class="tl-dot"></div>
<div class="tl-card"><div class="tl-time">2025.04.20 10:30</div><div class="tl-title">모델 학습 완료</div><div class="tl-desc">화랑 AI v2 모델 학습이 완료되었습니다. 229건 데이터, 10 에포크.</div><div class="tl-tags"><span class="tl-tag">AI</span><span class="tl-tag">학습</span></div></div>
</div>
<div class="tl-item done">
<div class="tl-dot"></div>
<div class="tl-card"><div class="tl-time">2025.04.20 09:00</div><div class="tl-title">서버 배포</div><div class="tl-desc">hwarang.ai 웹 서비스 + 관리자 패널 배포 완료.</div><div class="tl-tags"><span class="tl-tag">배포</span><span class="tl-tag">서버</span></div></div>
</div>
<div class="tl-item">
<div class="tl-dot"></div>
<div class="tl-card"><div class="tl-time">2025.04.20 14:00</div><div class="tl-title">에이전트 앱 빌드</div><div class="tl-desc">Mac .dmg 빌드 성공. Windows .exe는 GitHub Actions로 진행 예정.</div><div class="tl-tags"><span class="tl-tag">데스크탑</span><span class="tl-tag">빌드</span></div></div>
</div>
<div class="tl-item">
<div class="tl-dot"></div>
<div class="tl-card"><div class="tl-time">2025.04.21 예정</div><div class="tl-title">디자인 학습 데이터 추가</div><div class="tl-desc">100건+ 디자인 패턴 학습 데이터 추가 후 재학습 예정.</div><div class="tl-tags"><span class="tl-tag">학습</span><span class="tl-tag">디자인</span></div></div>
</div>
</div>
""")}

세로 타임라인 + 완료/진행중 상태 + 태그가 포함된 타임라인입니다!'''))

# 8. 이미지 갤러리
DATA.append(m("이미지 갤러리 디자인 해줘 Masonry 레이아웃으로", f'''Masonry 갤러리를 만들어 드릴게요.

{html_wrap("갤러리", {"body":"background:#0f172a;padding:2rem","styles":"""
.gallery{{max-width:1100px;margin:0 auto;columns:3;gap:1rem}}
@media(max-width:768px){{.gallery{{columns:2}}}}
.gallery-item{{break-inside:avoid;margin-bottom:1rem;border-radius:16px;overflow:hidden;position:relative;cursor:pointer;transition:.3s}}
.gallery-item:hover{{transform:scale(1.02)}}
.gallery-item:hover .overlay{{opacity:1}}
.gallery-img{{width:100%;display:block;background:#1e293b}}
.overlay{{position:absolute;inset:0;background:linear-gradient(transparent 50%,rgba(0,0,0,.7));opacity:0;transition:.3s;display:flex;align-items:flex-end;padding:1.5rem}}
.overlay-info{{color:#fff}}
.overlay-title{{font-size:15px;font-weight:600;margin-bottom:4px}}
.overlay-sub{{font-size:12px;color:rgba(255,255,255,.7)}}
h1{{color:#fff;text-align:center;font-size:1.8rem;margin-bottom:2rem}}
"""}, """
<h1>갤러리</h1>
<div class="gallery">
<div class="gallery-item"><div class="gallery-img" style="height:280px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-size:4rem">🏔️</div><div class="overlay"><div class="overlay-info"><div class="overlay-title">산 풍경</div><div class="overlay-sub">2025.04.20 · 좋아요 234</div></div></div></div>
<div class="gallery-item"><div class="gallery-img" style="height:200px;background:linear-gradient(135deg,#059669,#10b981);display:flex;align-items:center;justify-content:center;font-size:4rem">🌊</div><div class="overlay"><div class="overlay-info"><div class="overlay-title">바다</div><div class="overlay-sub">2025.04.19 · 좋아요 189</div></div></div></div>
<div class="gallery-item"><div class="gallery-img" style="height:320px;background:linear-gradient(135deg,#dc2626,#f97316);display:flex;align-items:center;justify-content:center;font-size:4rem">🌅</div><div class="overlay"><div class="overlay-info"><div class="overlay-title">일몰</div><div class="overlay-sub">2025.04.18 · 좋아요 456</div></div></div></div>
<div class="gallery-item"><div class="gallery-img" style="height:240px;background:linear-gradient(135deg,#7c3aed,#ec4899);display:flex;align-items:center;justify-content:center;font-size:4rem">🌸</div><div class="overlay"><div class="overlay-info"><div class="overlay-title">벚꽃</div><div class="overlay-sub">2025.04.17 · 좋아요 567</div></div></div></div>
<div class="gallery-item"><div class="gallery-img" style="height:180px;background:linear-gradient(135deg,#0891b2,#06b6d4);display:flex;align-items:center;justify-content:center;font-size:4rem">🏙️</div><div class="overlay"><div class="overlay-info"><div class="overlay-title">도시 야경</div><div class="overlay-sub">2025.04.16 · 좋아요 321</div></div></div></div>
<div class="gallery-item"><div class="gallery-img" style="height:300px;background:linear-gradient(135deg,#ca8a04,#eab308);display:flex;align-items:center;justify-content:center;font-size:4rem">🍂</div><div class="overlay"><div class="overlay-info"><div class="overlay-title">단풍</div><div class="overlay-sub">2025.04.15 · 좋아요 432</div></div></div></div>
</div>
""")}

Masonry 레이아웃 + 호버 오버레이 + 반응형이 포함된 이미지 갤러리입니다!'''))

# 9. 빈 상태
DATA.append(m("빈 상태 페이지 디자인 해줘", f'''빈 상태(Empty State) 페이지를 만들어 드릴게요.

{html_wrap("빈 상태", {"body":"background:#f8fafc;padding:2rem","styles":"""
.container{{max-width:900px;margin:0 auto}}
h2{{font-size:14px;color:#6b7280;margin:2rem 0 1rem}}
.empty{{background:#fff;border:1px solid #e5e7eb;border-radius:20px;padding:3rem 2rem;text-align:center}}
.empty-icon{{width:80px;height:80px;margin:0 auto 1.5rem;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:2.5rem}}
.empty h3{{font-size:1.1rem;font-weight:600;margin-bottom:.5rem;color:#1f2937}}
.empty p{{color:#6b7280;font-size:14px;max-width:360px;margin:0 auto;line-height:1.6}}
.empty .btn{{display:inline-flex;align-items:center;gap:6px;margin-top:1.5rem;padding:10px 20px;background:#3b82f6;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer}}
.empty .btn:hover{{background:#2563eb}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:1.5rem}}
"""}, """
<div class="container">
<div class="grid">
<div>
<h2>검색 결과 없음</h2>
<div class="empty"><div class="empty-icon" style="background:#f1f5f9">🔍</div><h3>검색 결과가 없습니다</h3><p>다른 키워드로 검색해 보세요. 검색어가 정확한지 확인해 주세요.</p></div>
</div>
<div>
<h2>데이터 없음</h2>
<div class="empty"><div class="empty-icon" style="background:#eff6ff">📊</div><h3>아직 데이터가 없습니다</h3><p>첫 번째 프로젝트를 만들어 시작해 보세요.</p><button class="btn">+ 새 프로젝트</button></div>
</div>
<div>
<h2>오류 발생</h2>
<div class="empty"><div class="empty-icon" style="background:#fef2f2">⚠️</div><h3>문제가 발생했습니다</h3><p>일시적인 오류입니다. 잠시 후 다시 시도해 주세요.</p><button class="btn" style="background:#ef4444">다시 시도</button></div>
</div>
<div>
<h2>접근 권한 없음</h2>
<div class="empty"><div class="empty-icon" style="background:#fef3c7">🔒</div><h3>접근 권한이 없습니다</h3><p>이 페이지에 접근하려면 관리자에게 문의하세요.</p><button class="btn" style="background:#6b7280">돌아가기</button></div>
</div>
</div>
</div>
""")}

검색없음, 데이터없음, 오류, 권한없음 4가지 빈 상태 디자인입니다!'''))

# 10. 통계 위젯
DATA.append(m("KPI 통계 위젯 디자인 해줘", f'''KPI 통계 위젯을 만들어 드릴게요.

{html_wrap("KPI 위젯", {"body":"background:#f8fafc;padding:2rem","styles":"""
.container{{max-width:1100px;margin:0 auto}}
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:2rem}}
.kpi{{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:1.5rem;transition:.3s}}
.kpi:hover{{box-shadow:0 8px 25px rgba(0,0,0,.06);transform:translateY(-2px)}}
.kpi-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem}}
.kpi-icon{{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:20px}}
.kpi-change{{font-size:12px;font-weight:600;padding:4px 8px;border-radius:6px}}
.kpi-change.up{{background:#dcfce7;color:#166534}}
.kpi-change.down{{background:#fee2e2;color:#991b1b}}
.kpi-value{{font-size:2rem;font-weight:800;color:#1f2937;margin-bottom:.25rem}}
.kpi-label{{font-size:13px;color:#6b7280}}
.kpi-sparkline{{display:flex;align-items:flex-end;gap:3px;height:40px;margin-top:1rem}}
.kpi-sparkline .bar{{flex:1;background:#e2e8f0;border-radius:2px;min-height:4px;transition:.3s}}
.kpi:hover .kpi-sparkline .bar{{background:#bfdbfe}}
.kpi-sparkline .bar.active{{background:#3b82f6}}
"""}, """
<div class="container">
<div class="kpi-grid">
<div class="kpi">
<div class="kpi-header"><div class="kpi-icon" style="background:#eff6ff">👥</div><span class="kpi-change up">↑ 12.5%</span></div>
<div class="kpi-value">12,847</div>
<div class="kpi-label">전체 사용자</div>
<div class="kpi-sparkline"><div class="bar" style="height:30%"></div><div class="bar" style="height:45%"></div><div class="bar" style="height:60%"></div><div class="bar" style="height:40%"></div><div class="bar" style="height:70%"></div><div class="bar" style="height:55%"></div><div class="bar active" style="height:85%"></div></div>
</div>
<div class="kpi">
<div class="kpi-header"><div class="kpi-icon" style="background:#f0fdf4">💰</div><span class="kpi-change up">↑ 23.1%</span></div>
<div class="kpi-value">₩4.2M</div>
<div class="kpi-label">이번 달 매출</div>
<div class="kpi-sparkline"><div class="bar" style="height:40%"></div><div class="bar" style="height:35%"></div><div class="bar" style="height:50%"></div><div class="bar" style="height:65%"></div><div class="bar" style="height:55%"></div><div class="bar" style="height:75%"></div><div class="bar active" style="height:90%"></div></div>
</div>
<div class="kpi">
<div class="kpi-header"><div class="kpi-icon" style="background:#fef3c7">📊</div><span class="kpi-change up">↑ 8.2%</span></div>
<div class="kpi-value">89,234</div>
<div class="kpi-label">API 호출</div>
<div class="kpi-sparkline"><div class="bar" style="height:60%"></div><div class="bar" style="height:55%"></div><div class="bar" style="height:70%"></div><div class="bar" style="height:50%"></div><div class="bar" style="height:80%"></div><div class="bar" style="height:65%"></div><div class="bar active" style="height:75%"></div></div>
</div>
<div class="kpi">
<div class="kpi-header"><div class="kpi-icon" style="background:#fce7f3">⚡</div><span class="kpi-change down">↓ 15%</span></div>
<div class="kpi-value">1.2초</div>
<div class="kpi-label">평균 응답시간</div>
<div class="kpi-sparkline"><div class="bar" style="height:80%"></div><div class="bar" style="height:70%"></div><div class="bar" style="height:60%"></div><div class="bar" style="height:55%"></div><div class="bar" style="height:45%"></div><div class="bar" style="height:35%"></div><div class="bar active" style="height:25%"></div></div>
</div>
</div>
</div>
""")}

KPI 4개 + 스파크라인 차트 + 증감 표시 + 호버 애니메이션이 포함된 통계 위젯입니다!'''))

# 추가 30건 (간결한 형태)
simple_designs = [
    ("체크박스 라디오 버튼 디자인 해줘", "커스텀 체크박스/라디오", """
.container{max-width:500px;margin:2rem auto;padding:0 1rem}
h3{font-size:15px;margin:1.5rem 0 .75rem;color:#374151}
.option{display:flex;align-items:center;gap:10px;padding:10px;border-radius:10px;cursor:pointer;transition:.2s;margin-bottom:4px}
.option:hover{background:#f8fafc}
.custom-check{width:20px;height:20px;border:2px solid #d1d5db;border-radius:6px;display:flex;align-items:center;justify-content:center;transition:.2s;flex-shrink:0;font-size:12px;color:transparent}
.option.checked .custom-check{background:#3b82f6;border-color:#3b82f6;color:#fff}
.custom-radio{width:20px;height:20px;border:2px solid #d1d5db;border-radius:50%;position:relative;transition:.2s;flex-shrink:0}
.option.checked .custom-radio{border-color:#3b82f6}
.option.checked .custom-radio::after{content:'';width:10px;height:10px;background:#3b82f6;border-radius:50%;position:absolute;top:50%;left:50%;transform:translate(-50%,-50%)}
.option-text{font-size:14px;color:#374151}
.option-desc{font-size:12px;color:#9ca3af}
""", """
<div class="container">
<h3>체크박스</h3>
<div class="option checked" onclick="this.classList.toggle('checked')"><div class="custom-check">✓</div><div><div class="option-text">이메일 알림</div><div class="option-desc">새 소식을 이메일로 받습니다</div></div></div>
<div class="option" onclick="this.classList.toggle('checked')"><div class="custom-check">✓</div><div><div class="option-text">마케팅 알림</div><div class="option-desc">프로모션 정보를 받습니다</div></div></div>
<div class="option checked" onclick="this.classList.toggle('checked')"><div class="custom-check">✓</div><div><div class="option-text">보안 알림</div><div class="option-desc">로그인 시도를 알립니다</div></div></div>
<h3>라디오 버튼</h3>
<div class="option checked" onclick="this.parentElement.querySelectorAll('.option').forEach(o=>o.classList.remove('checked'));this.classList.add('checked')"><div class="custom-radio"></div><div><div class="option-text">라이트 모드</div></div></div>
<div class="option" onclick="this.parentElement.querySelectorAll('.option').forEach(o=>o.classList.remove('checked'));this.classList.add('checked')"><div class="custom-radio"></div><div><div class="option-text">다크 모드</div></div></div>
<div class="option" onclick="this.parentElement.querySelectorAll('.option').forEach(o=>o.classList.remove('checked'));this.classList.add('checked')"><div class="custom-radio"></div><div><div class="option-text">시스템 설정</div></div></div>
</div>"""),

    ("칩/태그 입력 디자인 해줘", "태그 입력 컴포넌트", """
.container{max-width:500px;margin:2rem auto;padding:0 1rem}
.tag-input{border:1.5px solid #e2e8f0;border-radius:12px;padding:8px 12px;display:flex;flex-wrap:wrap;gap:6px;background:#fff;transition:.2s}
.tag-input:focus-within{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.1)}
.tag{display:inline-flex;align-items:center;gap:4px;background:#eff6ff;color:#2563eb;padding:4px 10px;border-radius:8px;font-size:13px;font-weight:500}
.tag button{background:none;border:none;color:#2563eb;cursor:pointer;font-size:14px;padding:0 2px}
.tag button:hover{color:#dc2626}
.tag-input input{border:none;outline:none;flex:1;min-width:100px;font-size:14px;padding:4px}
.preset-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:1rem}
.preset{padding:6px 12px;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;color:#6b7280;cursor:pointer;transition:.2s;background:#fff}
.preset:hover{border-color:#3b82f6;color:#3b82f6;background:#eff6ff}
""", """
<div class="container">
<label style="font-size:14px;font-weight:500;display:block;margin-bottom:8px">태그</label>
<div class="tag-input">
<span class="tag">Python <button onclick="this.parentElement.remove()">&times;</button></span>
<span class="tag">React <button onclick="this.parentElement.remove()">&times;</button></span>
<span class="tag">TypeScript <button onclick="this.parentElement.remove()">&times;</button></span>
<input placeholder="태그 입력 후 Enter..." onkeydown="if(event.key==='Enter'&&this.value){const t=document.createElement('span');t.className='tag';t.innerHTML=this.value+' <button onclick=\\'this.parentElement.remove()\\'>&times;</button>';this.before(t);this.value=''}">
</div>
<div class="preset-tags">
<span class="preset" onclick="const t=document.createElement('span');t.className='tag';t.innerHTML=this.textContent+' <button onclick=\\'this.parentElement.remove()\\'>&times;</button>';document.querySelector('.tag-input input').before(t)">JavaScript</span>
<span class="preset" onclick="const t=document.createElement('span');t.className='tag';t.innerHTML=this.textContent+' <button onclick=\\'this.parentElement.remove()\\'>&times;</button>';document.querySelector('.tag-input input').before(t)">Docker</span>
<span class="preset" onclick="const t=document.createElement('span');t.className='tag';t.innerHTML=this.textContent+' <button onclick=\\'this.parentElement.remove()\\'>&times;</button>';document.querySelector('.tag-input input').before(t)">AWS</span>
<span class="preset" onclick="const t=document.createElement('span');t.className='tag';t.innerHTML=this.textContent+' <button onclick=\\'this.parentElement.remove()\\'>&times;</button>';document.querySelector('.tag-input input').before(t)">AI</span>
</div>
</div>"""),

    ("별점 리뷰 컴포넌트 디자인 해줘", "별점 리뷰 위젯", """
.container{max-width:500px;margin:2rem auto;padding:0 1rem}
.review-card{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:1.5rem}
.review-header{display:flex;align-items:center;gap:12px;margin-bottom:1rem}
.review-avatar{width:44px;height:44px;border-radius:50%;background:#eff6ff;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:600;color:#2563eb}
.review-name{font-size:15px;font-weight:600}
.review-date{font-size:12px;color:#9ca3af}
.stars{display:flex;gap:2px;margin-bottom:.75rem}
.star{font-size:20px;cursor:pointer;color:#d1d5db;transition:.2s}
.star.filled{color:#fbbf24}
.star:hover,.star:hover~.star{color:#fbbf24}
.review-text{font-size:14px;color:#4b5563;line-height:1.6;margin-bottom:1rem}
.review-actions{display:flex;gap:1rem;font-size:13px;color:#6b7280}
.review-action{cursor:pointer;display:flex;align-items:center;gap:4px}
.review-action:hover{color:#3b82f6}
.write-review{margin-top:1.5rem}
.write-review textarea{width:100%;padding:12px;border:1.5px solid #e2e8f0;border-radius:12px;resize:none;font-size:14px;font-family:inherit;outline:none;transition:.2s}
.write-review textarea:focus{border-color:#3b82f6}
""", """
<div class="container">
<div class="review-card">
<div class="review-header"><div class="review-avatar">홍</div><div><div class="review-name">홍길동</div><div class="review-date">2025.04.20</div></div></div>
<div class="stars"><span class="star filled">★</span><span class="star filled">★</span><span class="star filled">★</span><span class="star filled">★</span><span class="star filled">★</span></div>
<div class="review-text">화랑 AI 정말 좋습니다! 한국어 이해가 뛰어나고, 코드 생성 품질도 높아요. 특히 한국 법률/세무 관련 답변이 정확해서 업무에 큰 도움이 됩니다.</div>
<div class="review-actions"><span class="review-action">👍 도움됨 (23)</span><span class="review-action">💬 댓글 (5)</span></div>
</div>
<div class="review-card" style="margin-top:1rem">
<div class="review-header"><div class="review-avatar" style="background:#fef3c7;color:#92400e">김</div><div><div class="review-name">김개발</div><div class="review-date">2025.04.19</div></div></div>
<div class="stars"><span class="star filled">★</span><span class="star filled">★</span><span class="star filled">★</span><span class="star filled">★</span><span class="star">★</span></div>
<div class="review-text">코딩 어시스턴트로 아주 만족합니다. React와 TypeScript 코드 생성이 특히 좋아요.</div>
<div class="review-actions"><span class="review-action">👍 도움됨 (15)</span><span class="review-action">💬 댓글 (2)</span></div>
</div>
</div>"""),

    ("달력 캘린더 디자인 해줘", "캘린더 컴포넌트", """
.container{max-width:360px;margin:2rem auto}
.calendar{background:#fff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden}
.cal-header{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;background:#3b82f6;color:#fff}
.cal-header h3{font-size:16px;font-weight:600}
.cal-nav{display:flex;gap:8px}
.cal-nav button{width:32px;height:32px;border-radius:8px;border:none;background:rgba(255,255,255,.2);color:#fff;cursor:pointer;font-size:16px}
.cal-nav button:hover{background:rgba(255,255,255,.3)}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:0;padding:8px}
.cal-day{text-align:center;padding:10px 0;font-size:13px;border-radius:10px;cursor:pointer;transition:.2s}
.cal-day.header{font-size:11px;font-weight:600;color:#6b7280;cursor:default}
.cal-day:not(.header):hover{background:#eff6ff}
.cal-day.today{background:#3b82f6;color:#fff;font-weight:600}
.cal-day.other{color:#d1d5db}
.cal-day.has-event::after{content:'';display:block;width:4px;height:4px;background:#ef4444;border-radius:50%;margin:2px auto 0}
.cal-day.today.has-event::after{background:#fff}
""", """
<div class="container">
<div class="calendar">
<div class="cal-header"><div class="cal-nav"><button>←</button></div><h3>2025년 4월</h3><div class="cal-nav"><button>→</button></div></div>
<div class="cal-grid">
<div class="cal-day header">일</div><div class="cal-day header">월</div><div class="cal-day header">화</div><div class="cal-day header">수</div><div class="cal-day header">목</div><div class="cal-day header">금</div><div class="cal-day header">토</div>
<div class="cal-day other">30</div><div class="cal-day other">31</div><div class="cal-day">1</div><div class="cal-day">2</div><div class="cal-day">3</div><div class="cal-day">4</div><div class="cal-day">5</div>
<div class="cal-day">6</div><div class="cal-day">7</div><div class="cal-day has-event">8</div><div class="cal-day">9</div><div class="cal-day">10</div><div class="cal-day">11</div><div class="cal-day">12</div>
<div class="cal-day">13</div><div class="cal-day">14</div><div class="cal-day has-event">15</div><div class="cal-day">16</div><div class="cal-day">17</div><div class="cal-day">18</div><div class="cal-day">19</div>
<div class="cal-day today has-event">20</div><div class="cal-day">21</div><div class="cal-day">22</div><div class="cal-day">23</div><div class="cal-day">24</div><div class="cal-day">25</div><div class="cal-day">26</div>
<div class="cal-day">27</div><div class="cal-day">28</div><div class="cal-day">29</div><div class="cal-day">30</div><div class="cal-day other">1</div><div class="cal-day other">2</div><div class="cal-day other">3</div>
</div></div>
</div>"""),

    ("브레드크럼 디자인 해줘", "브레드크럼 네비게이션", """
.container{max-width:600px;margin:2rem auto;padding:0 1rem;display:flex;flex-direction:column;gap:1.5rem}
h3{font-size:13px;color:#6b7280;margin-bottom:.5rem}
.breadcrumb{display:flex;align-items:center;gap:8px;font-size:14px;flex-wrap:wrap}
.breadcrumb a{color:#6b7280;text-decoration:none;transition:.2s}
.breadcrumb a:hover{color:#3b82f6}
.breadcrumb .current{color:#1f2937;font-weight:600}
.breadcrumb .sep{color:#d1d5db}
.breadcrumb-pill{display:flex;align-items:center;gap:0;background:#f1f5f9;border-radius:10px;padding:4px}
.breadcrumb-pill a,.breadcrumb-pill .current{padding:6px 12px;border-radius:8px;font-size:13px;color:#6b7280;text-decoration:none;transition:.2s}
.breadcrumb-pill a:hover{background:#e2e8f0;color:#1f2937}
.breadcrumb-pill .current{background:#fff;color:#1f2937;font-weight:500;box-shadow:0 1px 3px rgba(0,0,0,.1)}
.breadcrumb-pill .sep{color:#d1d5db;font-size:12px}
""", """
<div class="container">
<div><h3>기본 스타일</h3>
<div class="breadcrumb"><a href="#">홈</a><span class="sep">/</span><a href="#">상품</a><span class="sep">/</span><a href="#">전자기기</a><span class="sep">/</span><span class="current">헤드폰</span></div></div>
<div><h3>화살표 스타일</h3>
<div class="breadcrumb"><a href="#">홈</a><span class="sep">›</span><a href="#">설정</a><span class="sep">›</span><a href="#">프로필</a><span class="sep">›</span><span class="current">보안</span></div></div>
<div><h3>필 스타일</h3>
<div class="breadcrumb-pill"><a href="#">홈</a><span class="sep">›</span><a href="#">관리자</a><span class="sep">›</span><a href="#">사용자</a><span class="sep">›</span><span class="current">상세</span></div></div>
</div>"""),

    ("뱃지 디자인 해줘 여러 종류로", "다양한 뱃지 컴포넌트", """
.container{max-width:600px;margin:2rem auto;padding:0 1rem}
h3{font-size:13px;color:#6b7280;margin:1.5rem 0 .75rem}h3:first-child{margin-top:0}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:8px;font-size:12px;font-weight:600}
.b-blue{background:#dbeafe;color:#1e40af}
.b-green{background:#dcfce7;color:#166534}
.b-red{background:#fee2e2;color:#991b1b}
.b-yellow{background:#fef3c7;color:#92400e}
.b-purple{background:#ede9fe;color:#5b21b6}
.b-gray{background:#f1f5f9;color:#475569}
.badge-dot::before{content:'';width:6px;height:6px;border-radius:50%}
.b-blue .dot{background:#2563eb}.b-green .dot{background:#16a34a}.b-red .dot{background:#ef4444}
.badge-outline{background:transparent;border:1px solid}
.bo-blue{border-color:#93c5fd;color:#2563eb}
.bo-red{border-color:#fca5a5;color:#dc2626}
.badge-pill{border-radius:50px;padding:4px 12px}
.badge-lg{padding:6px 14px;font-size:13px;border-radius:10px}
.badge-icon{padding:4px 10px 4px 6px}
.badge-closable{padding-right:6px}
.badge-closable button{background:none;border:none;margin-left:2px;cursor:pointer;color:inherit;font-size:14px;opacity:.6}
.badge-closable button:hover{opacity:1}
""", """
<div class="container">
<h3>기본</h3>
<div class="row"><span class="badge b-blue">정보</span><span class="badge b-green">성공</span><span class="badge b-red">에러</span><span class="badge b-yellow">경고</span><span class="badge b-purple">프리미엄</span><span class="badge b-gray">기본</span></div>
<h3>도트</h3>
<div class="row"><span class="badge b-blue badge-dot"><span class="dot" style="width:6px;height:6px;border-radius:50%;background:#2563eb"></span>온라인</span><span class="badge b-green badge-dot"><span class="dot" style="width:6px;height:6px;border-radius:50%;background:#16a34a"></span>활성</span><span class="badge b-red badge-dot"><span class="dot" style="width:6px;height:6px;border-radius:50%;background:#ef4444"></span>오프라인</span></div>
<h3>아웃라인</h3>
<div class="row"><span class="badge badge-outline bo-blue">v2.0</span><span class="badge badge-outline bo-red">긴급</span></div>
<h3>필 (둥근)</h3>
<div class="row"><span class="badge b-blue badge-pill">NEW</span><span class="badge b-green badge-pill">✓ 완료</span><span class="badge b-purple badge-pill">PRO</span></div>
<h3>닫기 가능</h3>
<div class="row"><span class="badge b-blue badge-closable">Python <button onclick="this.parentElement.remove()">&times;</button></span><span class="badge b-green badge-closable">React <button onclick="this.parentElement.remove()">&times;</button></span></div>
</div>"""),

    ("아바타 그룹 디자인 해줘", "아바타 + 그룹 컴포넌트", """
.container{max-width:500px;margin:2rem auto;padding:0 1rem}
h3{font-size:13px;color:#6b7280;margin:1.5rem 0 .75rem}h3:first-child{margin-top:0}
.row{display:flex;align-items:center;gap:1rem;flex-wrap:wrap}
.avatar{display:flex;align-items:center;justify-content:center;border-radius:50%;font-weight:600;color:#fff;flex-shrink:0}
.a-xs{width:28px;height:28px;font-size:11px}
.a-sm{width:36px;height:36px;font-size:13px}
.a-md{width:44px;height:44px;font-size:15px}
.a-lg{width:56px;height:56px;font-size:20px}
.a-xl{width:72px;height:72px;font-size:26px}
.avatar-status{position:relative}
.avatar-status::after{content:'';position:absolute;bottom:0;right:0;width:25%;height:25%;border-radius:50%;border:2px solid #fff}
.avatar-status.online::after{background:#16a34a}
.avatar-status.busy::after{background:#ef4444}
.avatar-status.away::after{background:#f59e0b}
.avatar-group{display:flex}
.avatar-group .avatar{border:3px solid #fff;margin-left:-12px}
.avatar-group .avatar:first-child{margin-left:0}
.avatar-group .avatar-more{background:#f1f5f9;color:#6b7280;font-size:12px;font-weight:600}
""", """
<div class="container">
<h3>크기</h3>
<div class="row">
<div class="avatar a-xs" style="background:#3b82f6">H</div>
<div class="avatar a-sm" style="background:#8b5cf6">H</div>
<div class="avatar a-md" style="background:#ec4899">H</div>
<div class="avatar a-lg" style="background:#f97316">H</div>
<div class="avatar a-xl" style="background:#14b8a6">H</div>
</div>
<h3>상태 표시</h3>
<div class="row">
<div class="avatar a-md avatar-status online" style="background:#3b82f6">홍</div>
<div class="avatar a-md avatar-status busy" style="background:#8b5cf6">김</div>
<div class="avatar a-md avatar-status away" style="background:#f97316">이</div>
</div>
<h3>아바타 그룹</h3>
<div class="row">
<div class="avatar-group">
<div class="avatar a-md" style="background:#3b82f6">홍</div>
<div class="avatar a-md" style="background:#8b5cf6">김</div>
<div class="avatar a-md" style="background:#ec4899">이</div>
<div class="avatar a-md" style="background:#f97316">박</div>
<div class="avatar a-md avatar-more">+5</div>
</div>
</div>
</div>"""),

    ("드롭다운 메뉴 디자인 해줘", "드롭다운 메뉴 컴포넌트", """
.container{max-width:500px;margin:2rem auto;padding:0 1rem;display:flex;gap:1rem}
.dropdown-wrapper{position:relative;display:inline-block}
.trigger{padding:10px 18px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;font-size:14px;font-weight:500;cursor:pointer;display:flex;align-items:center;gap:6px;transition:.2s}
.trigger:hover{border-color:#93c5fd}
.menu{position:absolute;top:calc(100% + 6px);left:0;min-width:200px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.1);display:none;z-index:100;padding:6px;animation:fadeIn .2s}
.dropdown-wrapper.open .menu{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
.menu-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;font-size:14px;color:#374151;cursor:pointer;transition:.2s}
.menu-item:hover{background:#f8fafc}
.menu-item .icon{font-size:16px;width:20px;text-align:center}
.menu-item.danger{color:#ef4444}
.menu-item.danger:hover{background:#fef2f2}
.menu-divider{height:1px;background:#f1f5f9;margin:4px 0}
.menu-label{padding:8px 12px;font-size:11px;text-transform:uppercase;color:#9ca3af;letter-spacing:.5px}
""", """
<div class="container">
<div class="dropdown-wrapper" onclick="this.classList.toggle('open')">
<button class="trigger">옵션 ▾</button>
<div class="menu">
<div class="menu-item"><span class="icon">✏️</span> 수정</div>
<div class="menu-item"><span class="icon">📋</span> 복사</div>
<div class="menu-item"><span class="icon">📤</span> 공유</div>
<div class="menu-divider"></div>
<div class="menu-item danger"><span class="icon">🗑️</span> 삭제</div>
</div>
</div>
<div class="dropdown-wrapper" onclick="this.classList.toggle('open')">
<button class="trigger">계정 ▾</button>
<div class="menu">
<div class="menu-label">내 계정</div>
<div class="menu-item"><span class="icon">👤</span> 프로필</div>
<div class="menu-item"><span class="icon">⚙️</span> 설정</div>
<div class="menu-item"><span class="icon">💳</span> 결제</div>
<div class="menu-divider"></div>
<div class="menu-item danger"><span class="icon">🚪</span> 로그아웃</div>
</div>
</div>
</div>"""),

    ("툴팁 디자인 해줘", "다양한 툴팁 컴포넌트", """
.container{max-width:600px;margin:4rem auto;padding:0 1rem;display:flex;flex-wrap:wrap;gap:2rem;justify-content:center}
.tooltip-wrapper{position:relative;display:inline-block}
.btn{padding:10px 20px;border:1px solid #e2e8f0;border-radius:10px;background:#fff;font-size:14px;cursor:pointer;font-weight:500;transition:.2s}
.btn:hover{border-color:#93c5fd;background:#f8fafc}
.tooltip{position:absolute;padding:8px 14px;background:#1e293b;color:#fff;border-radius:8px;font-size:13px;white-space:nowrap;opacity:0;pointer-events:none;transition:.2s;z-index:10}
.tooltip::after{content:'';position:absolute;border:6px solid transparent}
.tooltip-top{bottom:calc(100% + 10px);left:50%;transform:translateX(-50%)}
.tooltip-top::after{top:100%;left:50%;transform:translateX(-50%);border-top-color:#1e293b}
.tooltip-bottom{top:calc(100% + 10px);left:50%;transform:translateX(-50%)}
.tooltip-bottom::after{bottom:100%;left:50%;transform:translateX(-50%);border-bottom-color:#1e293b}
.tooltip-left{right:calc(100% + 10px);top:50%;transform:translateY(-50%)}
.tooltip-left::after{left:100%;top:50%;transform:translateY(-50%);border-left-color:#1e293b}
.tooltip-right{left:calc(100% + 10px);top:50%;transform:translateY(-50%)}
.tooltip-right::after{right:100%;top:50%;transform:translateY(-50%);border-right-color:#1e293b}
.tooltip-wrapper:hover .tooltip{opacity:1}
""", """
<div class="container">
<div class="tooltip-wrapper"><button class="btn">위쪽</button><div class="tooltip tooltip-top">위쪽 툴팁입니다</div></div>
<div class="tooltip-wrapper"><button class="btn">아래쪽</button><div class="tooltip tooltip-bottom">아래쪽 툴팁입니다</div></div>
<div class="tooltip-wrapper"><button class="btn">왼쪽</button><div class="tooltip tooltip-left">왼쪽 툴팁</div></div>
<div class="tooltip-wrapper"><button class="btn">오른쪽</button><div class="tooltip tooltip-right">오른쪽 툴팁</div></div>
</div>"""),

    ("색상 피커 디자인 해줘", "색상 피커 UI", """
.container{max-width:320px;margin:2rem auto}
.picker{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:1.5rem}
.picker h3{font-size:15px;margin-bottom:1rem}
.colors{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:1rem}
.color-btn{width:100%;aspect-ratio:1;border-radius:10px;border:2px solid transparent;cursor:pointer;transition:.2s}
.color-btn:hover{transform:scale(1.1)}
.color-btn.selected{border-color:#1f2937;box-shadow:0 0 0 2px #fff,0 0 0 4px #1f2937}
.color-input{display:flex;align-items:center;gap:8px;margin-top:1rem}
.color-preview{width:40px;height:40px;border-radius:10px;border:1px solid #e5e7eb}
.color-input input{flex:1;padding:10px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;font-family:monospace;outline:none}
.color-input input:focus{border-color:#3b82f6}
.recent{margin-top:1rem}
.recent-label{font-size:12px;color:#6b7280;margin-bottom:.5rem}
.recent-colors{display:flex;gap:6px}
.recent-color{width:28px;height:28px;border-radius:8px;cursor:pointer;border:1px solid #e5e7eb}
""", """
<div class="container">
<div class="picker">
<h3>색상 선택</h3>
<div class="colors">
<div class="color-btn selected" style="background:#ef4444" onclick="select(this,'#ef4444')"></div>
<div class="color-btn" style="background:#f97316" onclick="select(this,'#f97316')"></div>
<div class="color-btn" style="background:#eab308" onclick="select(this,'#eab308')"></div>
<div class="color-btn" style="background:#22c55e" onclick="select(this,'#22c55e')"></div>
<div class="color-btn" style="background:#3b82f6" onclick="select(this,'#3b82f6')"></div>
<div class="color-btn" style="background:#8b5cf6" onclick="select(this,'#8b5cf6')"></div>
<div class="color-btn" style="background:#ec4899" onclick="select(this,'#ec4899')"></div>
<div class="color-btn" style="background:#14b8a6" onclick="select(this,'#14b8a6')"></div>
<div class="color-btn" style="background:#f43f5e" onclick="select(this,'#f43f5e')"></div>
<div class="color-btn" style="background:#0ea5e9" onclick="select(this,'#0ea5e9')"></div>
<div class="color-btn" style="background:#1f2937" onclick="select(this,'#1f2937')"></div>
<div class="color-btn" style="background:#6b7280" onclick="select(this,'#6b7280')"></div>
</div>
<div class="color-input">
<div class="color-preview" id="preview" style="background:#ef4444"></div>
<input id="hexInput" value="#ef4444" oninput="document.getElementById('preview').style.background=this.value">
</div>
<div class="recent"><div class="recent-label">최근 사용</div><div class="recent-colors">
<div class="recent-color" style="background:#3b82f6"></div>
<div class="recent-color" style="background:#1f2937"></div>
<div class="recent-color" style="background:#ec4899"></div>
</div></div>
</div>
</div>
<script>
function select(el,color){document.querySelectorAll('.color-btn').forEach(b=>b.classList.remove('selected'));el.classList.add('selected');document.getElementById('preview').style.background=color;document.getElementById('hexInput').value=color}
</script>"""),

    ("슬라이더 캐러셀 디자인 해줘", "이미지 캐러셀", """
.container{max-width:700px;margin:2rem auto;padding:0 1rem}
.carousel{position:relative;border-radius:20px;overflow:hidden;background:#0f172a}
.slides{display:flex;transition:transform .5s ease}
.slide{min-width:100%;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;font-size:4rem;color:#fff}
.nav-btn{position:absolute;top:50%;transform:translateY(-50%);width:44px;height:44px;border-radius:50%;background:rgba(255,255,255,.9);border:none;font-size:20px;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.2);transition:.2s;z-index:5}
.nav-btn:hover{background:#fff;transform:translateY(-50%) scale(1.05)}
.prev{left:16px}
.next{right:16px}
.dots{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);display:flex;gap:8px;z-index:5}
.dot{width:8px;height:8px;border-radius:4px;background:rgba(255,255,255,.4);cursor:pointer;transition:.3s}
.dot.active{width:24px;background:#fff}
.slide-info{position:absolute;bottom:0;left:0;right:0;padding:2rem;background:linear-gradient(transparent,rgba(0,0,0,.7));color:#fff;z-index:2}
.slide-title{font-size:1.2rem;font-weight:600}
.slide-sub{font-size:13px;color:rgba(255,255,255,.7);margin-top:4px}
""", """
<div class="container">
<div class="carousel">
<div class="slides" id="slides">
<div class="slide" style="background:linear-gradient(135deg,#1e40af,#7c3aed)">🏔️</div>
<div class="slide" style="background:linear-gradient(135deg,#059669,#10b981)">🌊</div>
<div class="slide" style="background:linear-gradient(135deg,#dc2626,#f97316)">🌅</div>
</div>
<button class="nav-btn prev" onclick="go(-1)">‹</button>
<button class="nav-btn next" onclick="go(1)">›</button>
<div class="dots"><div class="dot active" onclick="goTo(0)"></div><div class="dot" onclick="goTo(1)"></div><div class="dot" onclick="goTo(2)"></div></div>
</div>
</div>
<script>
let cur=0,total=3;
function go(d){cur=(cur+d+total)%total;update()}
function goTo(i){cur=i;update()}
function update(){document.getElementById('slides').style.transform=`translateX(-${cur*100}%)`;document.querySelectorAll('.dot').forEach((d,i)=>{d.className=i===cur?'dot active':'dot'})}
setInterval(()=>go(1),4000);
</script>"""),
]

for q, title, css_str, body_str in simple_designs:
    DATA.append(m(q, f'''{title}을 만들어 드릴게요.

{html_wrap(title, {"body": "background:#f8fafc", "styles": css_str}, body_str)}

브라우저에서 바로 열어볼 수 있는 완전한 코드입니다!'''))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mass_design.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 대량 디자인 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  디자인: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
