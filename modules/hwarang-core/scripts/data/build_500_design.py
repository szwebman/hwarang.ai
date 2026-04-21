"""화랑 AI 디자인 대량 추가 (80건)

500건 달성을 위한 디자인 학습 데이터.
다양한 UI 컴포넌트와 페이지를 실제 HTML/CSS 코드로.
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
디자인 요청 시 반드시 실제 실행 가능한 완전한 HTML/CSS 코드를 생성합니다.
브라우저에서 바로 볼 수 있는 코드를 작성하며, 설명은 한국어로 합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

# 간결한 디자인 항목 (각각 완전한 HTML)
ITEMS = [
    ("블로그 카드 리스트 디자인 해줘", "블로그 카드 리스트", "#f8fafc", """
.container{max-width:800px;margin:0 auto;padding:2rem}
h1{font-size:1.5rem;margin-bottom:1.5rem}
.blog-grid{display:flex;flex-direction:column;gap:1.5rem}
.blog-card{display:flex;gap:1.5rem;background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:1.25rem;transition:.3s;cursor:pointer}
.blog-card:hover{box-shadow:0 8px 25px rgba(0,0,0,.06);transform:translateY(-2px)}
.blog-thumb{width:200px;height:140px;border-radius:12px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:3rem}
.blog-content{flex:1;display:flex;flex-direction:column}
.blog-tag{font-size:12px;font-weight:600;color:#3b82f6;margin-bottom:.5rem}
.blog-title{font-size:1.1rem;font-weight:700;margin-bottom:.5rem;line-height:1.4}
.blog-excerpt{font-size:14px;color:#6b7280;line-height:1.6;flex:1}
.blog-meta{display:flex;align-items:center;gap:8px;font-size:12px;color:#9ca3af;margin-top:.75rem}
.blog-avatar{width:24px;height:24px;border-radius:50%;background:#e0e7ff;display:flex;align-items:center;justify-content:center;font-size:10px;color:#4338ca;font-weight:600}
""", """
<div class="container">
<h1>블로그</h1>
<div class="blog-grid">
<div class="blog-card"><div class="blog-thumb" style="background:linear-gradient(135deg,#dbeafe,#ede9fe)">📝</div><div class="blog-content"><div class="blog-tag">개발</div><div class="blog-title">Next.js 15에서 달라진 점 총정리</div><div class="blog-excerpt">App Router의 안정화, Server Actions 개선, 그리고 새로운 캐싱 전략까지 핵심만 정리했습니다.</div><div class="blog-meta"><div class="blog-avatar">홍</div><span>홍길동</span><span>·</span><span>4월 20일</span><span>·</span><span>5분 읽기</span></div></div></div>
<div class="blog-card"><div class="blog-thumb" style="background:linear-gradient(135deg,#fef3c7,#fde68a)">🎨</div><div class="blog-content"><div class="blog-tag">디자인</div><div class="blog-title">2025 UI 디자인 트렌드 7가지</div><div class="blog-excerpt">Bento Grid, 글래스모피즘, AI 통합 UI까지. 올해 웹 디자인에서 가장 주목할 트렌드를 소개합니다.</div><div class="blog-meta"><div class="blog-avatar">김</div><span>김디자인</span><span>·</span><span>4월 18일</span><span>·</span><span>7분 읽기</span></div></div></div>
<div class="blog-card"><div class="blog-thumb" style="background:linear-gradient(135deg,#dcfce7,#bbf7d0)">🤖</div><div class="blog-content"><div class="blog-tag">AI</div><div class="blog-title">RAG 시스템 구축 가이드 (실전편)</div><div class="blog-excerpt">벡터 DB 선택부터 환각 줄이기까지, 프로덕션 RAG 시스템 구축의 모든 것을 공유합니다.</div><div class="blog-meta"><div class="blog-avatar">이</div><span>이AI</span><span>·</span><span>4월 15일</span><span>·</span><span>10분 읽기</span></div></div></div>
</div></div>"""),

    ("통계 차트 카드 디자인 해줘 라인 차트로", "라인 차트 카드", "#f8fafc", """
.container{max-width:700px;margin:0 auto;padding:2rem}
.chart-card{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:1.5rem}
.chart-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem}
.chart-title{font-size:1rem;font-weight:600}
.chart-period{display:flex;gap:4px}
.period-btn{padding:6px 12px;border:1px solid #e2e8f0;border-radius:8px;font-size:12px;cursor:pointer;background:#fff;transition:.2s}
.period-btn.active{background:#3b82f6;color:#fff;border-color:#3b82f6}
.chart-stats{display:flex;gap:2rem;margin-bottom:1.5rem}
.stat{display:flex;flex-direction:column}
.stat-value{font-size:1.5rem;font-weight:700}
.stat-label{font-size:12px;color:#6b7280}
.stat-change{font-size:12px;color:#16a34a;font-weight:500}
.line-chart{height:200px;display:flex;align-items:flex-end;gap:2px;padding:1rem 0;position:relative;border-bottom:1px solid #f1f5f9}
.line-chart::before{content:'';position:absolute;top:25%;left:0;right:0;border-top:1px dashed #f1f5f9}
.line-chart::after{content:'';position:absolute;top:50%;left:0;right:0;border-top:1px dashed #f1f5f9}
.bar{flex:1;background:linear-gradient(180deg,#3b82f6,#6366f1);border-radius:4px 4px 0 0;min-height:8px;transition:.3s;opacity:.7}
.bar:hover{opacity:1}
.chart-labels{display:flex;justify-content:space-between;padding-top:8px;font-size:11px;color:#9ca3af}
""", """
<div class="container">
<div class="chart-card">
<div class="chart-header"><div class="chart-title">사용량 추이</div><div class="chart-period"><button class="period-btn">7일</button><button class="period-btn active">30일</button><button class="period-btn">90일</button></div></div>
<div class="chart-stats"><div class="stat"><div class="stat-value">89,234</div><div class="stat-label">이번 달 API 호출</div></div><div class="stat"><div class="stat-value">+23.1%</div><div class="stat-label">전월 대비</div><div class="stat-change">↑ 16,744건 증가</div></div></div>
<div class="line-chart">
<div class="bar" style="height:30%"></div><div class="bar" style="height:45%"></div><div class="bar" style="height:35%"></div><div class="bar" style="height:55%"></div><div class="bar" style="height:42%"></div><div class="bar" style="height:60%"></div><div class="bar" style="height:50%"></div>
<div class="bar" style="height:65%"></div><div class="bar" style="height:55%"></div><div class="bar" style="height:70%"></div><div class="bar" style="height:62%"></div><div class="bar" style="height:75%"></div><div class="bar" style="height:68%"></div><div class="bar" style="height:80%"></div>
<div class="bar" style="height:72%"></div><div class="bar" style="height:85%"></div><div class="bar" style="height:78%"></div><div class="bar" style="height:90%"></div><div class="bar" style="height:82%"></div><div class="bar" style="height:88%"></div><div class="bar" style="height:95%"></div>
<div class="bar" style="height:85%"></div><div class="bar" style="height:90%"></div><div class="bar" style="height:82%"></div><div class="bar" style="height:88%"></div><div class="bar" style="height:92%"></div><div class="bar" style="height:85%"></div><div class="bar" style="height:95%"></div>
<div class="bar" style="height:88%"></div><div class="bar" style="height:100%"></div>
</div>
<div class="chart-labels"><span>4/1</span><span>4/5</span><span>4/10</span><span>4/15</span><span>4/20</span><span>4/25</span><span>4/30</span></div>
</div></div>"""),

    ("쿠키 배너 디자인 해줘", "쿠키 동의 배너", "#f8fafc;min-height:80vh", """
.cookie-banner{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #e5e7eb;padding:1.5rem 2rem;box-shadow:0 -4px 20px rgba(0,0,0,.08);display:flex;align-items:center;gap:1.5rem;z-index:1000;animation:slideUp .4s ease}
@keyframes slideUp{from{transform:translateY(100%)}to{transform:translateY(0)}}
.cookie-icon{font-size:2rem;flex-shrink:0}
.cookie-text{flex:1}
.cookie-text h3{font-size:15px;font-weight:600;margin-bottom:4px}
.cookie-text p{font-size:13px;color:#6b7280;line-height:1.5}
.cookie-text a{color:#3b82f6;text-decoration:none}
.cookie-btns{display:flex;gap:8px;flex-shrink:0}
.cookie-btn{padding:10px 20px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;transition:.2s;border:none}
.btn-accept{background:#3b82f6;color:#fff}
.btn-accept:hover{background:#2563eb}
.btn-settings{background:#f1f5f9;color:#374151}
.btn-settings:hover{background:#e2e8f0}
.btn-reject{background:transparent;color:#6b7280;border:1px solid #e2e8f0}
.page{padding:2rem;text-align:center;font-size:1.5rem;color:#9ca3af}
""", """
<div class="page"><p>웹사이트 콘텐츠 영역</p><p style="font-size:14px;margin-top:1rem">하단에 쿠키 배너가 표시됩니다</p></div>
<div class="cookie-banner" id="cookieBanner">
<span class="cookie-icon">🍪</span>
<div class="cookie-text"><h3>쿠키 사용 안내</h3><p>더 나은 서비스를 위해 쿠키를 사용합니다. <a href="#">쿠키 정책</a>에서 자세히 알아보세요.</p></div>
<div class="cookie-btns">
<button class="cookie-btn btn-reject" onclick="document.getElementById('cookieBanner').style.display='none'">거부</button>
<button class="cookie-btn btn-settings">설정</button>
<button class="cookie-btn btn-accept" onclick="document.getElementById('cookieBanner').style.display='none'">모두 수락</button>
</div></div>"""),

    ("사이드 패널 디자인 해줘 오른쪽에서 나오는", "슬라이드 사이드 패널", "#f8fafc", """
.page{padding:2rem}
.open-btn{padding:12px 24px;background:#3b82f6;color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);opacity:0;pointer-events:none;transition:.3s;z-index:100}
.overlay.active{opacity:1;pointer-events:all}
.panel{position:fixed;top:0;right:0;bottom:0;width:400px;background:#fff;transform:translateX(100%);transition:.3s ease;z-index:101;display:flex;flex-direction:column;box-shadow:-10px 0 40px rgba(0,0,0,.1)}
.panel.active{transform:translateX(0)}
.panel-header{display:flex;justify-content:space-between;align-items:center;padding:1.25rem 1.5rem;border-bottom:1px solid #f1f5f9}
.panel-header h3{font-size:1.1rem;font-weight:600}
.close-btn{width:32px;height:32px;border-radius:8px;border:none;background:#f1f5f9;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center}
.close-btn:hover{background:#e2e8f0}
.panel-body{flex:1;padding:1.5rem;overflow-y:auto}
.panel-footer{padding:1rem 1.5rem;border-top:1px solid #f1f5f9;display:flex;gap:8px}
.panel-footer button{flex:1;padding:12px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;border:none;transition:.2s}
.btn-save{background:#3b82f6;color:#fff}
.btn-cancel{background:#f1f5f9;color:#374151}
.form-group{margin-bottom:1.25rem}
.form-group label{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px}
.form-group input,.form-group textarea,.form-group select{width:100%;padding:10px 14px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;outline:none;transition:.2s;font-family:inherit}
.form-group input:focus,.form-group textarea:focus{border-color:#3b82f6}
""", """
<div class="page">
<h1 style="font-size:1.5rem;margin-bottom:1rem">사이드 패널 예시</h1>
<button class="open-btn" onclick="openPanel()">패널 열기 →</button>
</div>
<div class="overlay" id="overlay" onclick="closePanel()"></div>
<div class="panel" id="panel">
<div class="panel-header"><h3>사용자 추가</h3><button class="close-btn" onclick="closePanel()">✕</button></div>
<div class="panel-body">
<div class="form-group"><label>이름</label><input placeholder="홍길동"></div>
<div class="form-group"><label>이메일</label><input type="email" placeholder="hong@example.com"></div>
<div class="form-group"><label>역할</label><select><option>사용자</option><option>관리자</option><option>편집자</option></select></div>
<div class="form-group"><label>메모</label><textarea rows="4" placeholder="추가 메모..."></textarea></div>
</div>
<div class="panel-footer"><button class="btn-cancel" onclick="closePanel()">취소</button><button class="btn-save">저장</button></div>
</div>
<script>
function openPanel(){document.getElementById('panel').classList.add('active');document.getElementById('overlay').classList.add('active')}
function closePanel(){document.getElementById('panel').classList.remove('active');document.getElementById('overlay').classList.remove('active')}
</script>"""),

    ("커맨드 팔레트 디자인 해줘 Cmd+K 스타일", "커맨드 팔레트", "#0f172a;min-height:100vh;display:flex;align-items:center;justify-content:center", """
.cmd-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);backdrop-filter:blur(4px);display:flex;align-items:flex-start;justify-content:center;padding-top:20vh;z-index:1000}
.cmd-palette{width:560px;background:#1e293b;border:1px solid #334155;border-radius:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.4)}
.cmd-input{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid #334155}
.cmd-input .icon{color:#64748b;font-size:18px}
.cmd-input input{flex:1;background:none;border:none;color:#e2e8f0;font-size:15px;outline:none}
.cmd-input input::placeholder{color:#475569}
.cmd-input .shortcut{font-size:11px;color:#475569;background:#334155;padding:3px 8px;border-radius:4px}
.cmd-results{max-height:400px;overflow-y:auto;padding:8px}
.cmd-group{padding:8px 12px}
.cmd-group-label{font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.cmd-item{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:10px;cursor:pointer;transition:.15s}
.cmd-item:hover,.cmd-item.active{background:#334155}
.cmd-item-icon{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0}
.cmd-item-text{flex:1}
.cmd-item-title{font-size:14px;color:#e2e8f0}
.cmd-item-desc{font-size:12px;color:#64748b}
.cmd-item-shortcut{font-size:11px;color:#475569;background:#0f172a;padding:2px 6px;border-radius:4px}
.cmd-footer{display:flex;align-items:center;gap:1rem;padding:10px 16px;border-top:1px solid #334155;font-size:11px;color:#475569}
.cmd-footer kbd{background:#334155;padding:2px 6px;border-radius:3px;font-family:inherit}
.hint{position:fixed;bottom:2rem;left:50%;transform:translateX(-50%);color:#475569;font-size:13px}
""", """
<div class="cmd-overlay">
<div class="cmd-palette">
<div class="cmd-input"><span class="icon">🔍</span><input placeholder="명령어 검색..." autofocus><span class="shortcut">ESC</span></div>
<div class="cmd-results">
<div class="cmd-group"><div class="cmd-group-label">최근</div>
<div class="cmd-item active"><div class="cmd-item-icon" style="background:#1e3a5f">💬</div><div class="cmd-item-text"><div class="cmd-item-title">새 대화</div><div class="cmd-item-desc">화랑 AI와 새 대화 시작</div></div><span class="cmd-item-shortcut">⌘N</span></div>
<div class="cmd-item"><div class="cmd-item-icon" style="background:#1e3a2f">💻</div><div class="cmd-item-text"><div class="cmd-item-title">코드 생성</div><div class="cmd-item-desc">AI로 코드 작성</div></div></div>
</div>
<div class="cmd-group"><div class="cmd-group-label">페이지</div>
<div class="cmd-item"><div class="cmd-item-icon" style="background:#2d1b4e">📊</div><div class="cmd-item-text"><div class="cmd-item-title">대시보드</div></div></div>
<div class="cmd-item"><div class="cmd-item-icon" style="background:#1b2e4e">⚙️</div><div class="cmd-item-text"><div class="cmd-item-title">설정</div></div><span class="cmd-item-shortcut">⌘,</span></div>
<div class="cmd-item"><div class="cmd-item-icon" style="background:#1b4e3a">👥</div><div class="cmd-item-text"><div class="cmd-item-title">사용자 관리</div></div></div>
</div>
<div class="cmd-group"><div class="cmd-group-label">액션</div>
<div class="cmd-item"><div class="cmd-item-icon" style="background:#4e1b1b">🌙</div><div class="cmd-item-text"><div class="cmd-item-title">다크 모드 전환</div></div><span class="cmd-item-shortcut">⌘D</span></div>
<div class="cmd-item"><div class="cmd-item-icon" style="background:#4e3a1b">📤</div><div class="cmd-item-text"><div class="cmd-item-title">내보내기</div></div></div>
</div>
</div>
<div class="cmd-footer"><span><kbd>↑↓</kbd> 이동</span><span><kbd>Enter</kbd> 실행</span><span><kbd>ESC</kbd> 닫기</span></div>
</div>
</div>
<div class="hint">⌘K 로 커맨드 팔레트를 열 수 있습니다</div>"""),

    ("쿠폰 카드 디자인 해줘", "쿠폰/할인 카드", "#f8fafc;padding:2rem;display:flex;justify-content:center", """
.coupons{display:flex;flex-direction:column;gap:1rem;max-width:420px;width:100%}
.coupon{display:flex;border-radius:16px;overflow:hidden;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.06);border:1px solid #e5e7eb;position:relative}
.coupon::before{content:'';position:absolute;top:50%;right:115px;width:20px;height:20px;background:#f8fafc;border-radius:50%;transform:translateY(-50%);border:1px solid #e5e7eb}
.coupon-left{flex:1;padding:1.25rem;display:flex;flex-direction:column;justify-content:center}
.coupon-brand{font-size:12px;color:#6b7280;margin-bottom:4px}
.coupon-title{font-size:15px;font-weight:700;margin-bottom:4px}
.coupon-desc{font-size:12px;color:#9ca3af}
.coupon-expire{font-size:11px;color:#ef4444;margin-top:8px;display:flex;align-items:center;gap:4px}
.coupon-right{width:120px;display:flex;flex-direction:column;align-items:center;justify-content:center;border-left:1px dashed #e5e7eb;padding:1rem}
.coupon-discount{font-size:1.8rem;font-weight:800;color:#3b82f6}
.coupon-type{font-size:12px;color:#6b7280}
.coupon-btn{margin-top:8px;padding:6px 14px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;font-size:12px;color:#2563eb;font-weight:600;cursor:pointer;transition:.2s}
.coupon-btn:hover{background:#dbeafe}
.coupon.premium{border-color:#c084fc;background:linear-gradient(135deg,#faf5ff,#fff)}
.coupon.premium .coupon-discount{color:#7c3aed}
.coupon.premium .coupon-btn{background:#f3e8ff;border-color:#d8b4fe;color:#7c3aed}
""", """
<div class="coupons">
<div class="coupon"><div class="coupon-left"><div class="coupon-brand">화랑 AI</div><div class="coupon-title">첫 결제 30% 할인</div><div class="coupon-desc">Pro 플랜 첫 달 적용</div><div class="coupon-expire">⏰ 3일 남음</div></div><div class="coupon-right"><div class="coupon-discount">30%</div><div class="coupon-type">할인</div><button class="coupon-btn">사용하기</button></div></div>
<div class="coupon premium"><div class="coupon-left"><div class="coupon-brand">VIP 전용</div><div class="coupon-title">50,000 토큰 보너스</div><div class="coupon-desc">Pro 이상 플랜 사용자</div><div class="coupon-expire">⏰ 7일 남음</div></div><div class="coupon-right"><div class="coupon-discount">50K</div><div class="coupon-type">토큰</div><button class="coupon-btn">받기</button></div></div>
<div class="coupon"><div class="coupon-left"><div class="coupon-brand">추천인 보상</div><div class="coupon-title">10,000원 크레딧</div><div class="coupon-desc">친구 초대 시 양쪽 지급</div><div class="coupon-expire" style="color:#16a34a">✓ 사용 가능</div></div><div class="coupon-right"><div class="coupon-discount">₩1만</div><div class="coupon-type">크레딧</div><button class="coupon-btn">사용하기</button></div></div>
</div>"""),

    ("에러 알림 배너 디자인 해줘 여러 종류로", "알림 배너 (Alert)", "#f8fafc;padding:2rem", """
.container{max-width:600px;margin:0 auto;display:flex;flex-direction:column;gap:1rem}
.alert{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;border-radius:12px;font-size:14px;line-height:1.5}
.alert-icon{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;margin-top:1px}
.alert-content{flex:1}
.alert-title{font-weight:600;margin-bottom:2px}
.alert-desc{font-size:13px;opacity:.8}
.alert-close{background:none;border:none;cursor:pointer;font-size:16px;opacity:.5;padding:2px}
.alert-close:hover{opacity:1}
.alert-info{background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe}
.alert-info .alert-icon{background:#dbeafe}
.alert-success{background:#f0fdf4;color:#166534;border:1px solid #bbf7d0}
.alert-success .alert-icon{background:#dcfce7}
.alert-warning{background:#fffbeb;color:#92400e;border:1px solid #fde68a}
.alert-warning .alert-icon{background:#fef3c7}
.alert-error{background:#fef2f2;color:#991b1b;border:1px solid #fecaca}
.alert-error .alert-icon{background:#fee2e2}
.alert-actions{display:flex;gap:8px;margin-top:8px}
.alert-action{padding:4px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid;transition:.2s}
""", """
<div class="container">
<div class="alert alert-info"><div class="alert-icon">ℹ️</div><div class="alert-content"><div class="alert-title">시스템 업데이트 예정</div><div class="alert-desc">4월 22일 새벽 2시~4시 정기 점검이 예정되어 있습니다.</div></div><button class="alert-close">&times;</button></div>
<div class="alert alert-success"><div class="alert-icon">✅</div><div class="alert-content"><div class="alert-title">결제 완료!</div><div class="alert-desc">Pro 플랜이 활성화되었습니다. 무제한 AI 대화를 즐겨보세요.</div></div><button class="alert-close">&times;</button></div>
<div class="alert alert-warning"><div class="alert-icon">⚠️</div><div class="alert-content"><div class="alert-title">토큰 사용량 경고</div><div class="alert-desc">이번 달 토큰의 80%를 사용했습니다. 초과 시 추가 요금이 발생합니다.</div><div class="alert-actions"><button class="alert-action" style="border-color:#92400e;color:#92400e">플랜 업그레이드</button><button class="alert-action" style="border-color:#d1d5db;color:#6b7280">나중에</button></div></div></div>
<div class="alert alert-error"><div class="alert-icon">❌</div><div class="alert-content"><div class="alert-title">연결 실패</div><div class="alert-desc">서버에 연결할 수 없습니다. 인터넷 연결을 확인해주세요.</div><div class="alert-actions"><button class="alert-action" style="border-color:#991b1b;color:#991b1b">다시 시도</button></div></div></div>
</div>"""),

    ("가격 비교 테이블 디자인 해줘", "기능 비교 테이블", "#f8fafc;padding:2rem", """
.container{max-width:900px;margin:0 auto}
h1{font-size:1.5rem;text-align:center;margin-bottom:2rem}
.compare-table{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden}
.compare-table th,.compare-table td{padding:14px 20px;text-align:center;border-bottom:1px solid #f1f5f9;font-size:14px}
.compare-table th{background:#f8fafc;font-weight:600;color:#374151}
.compare-table th:first-child{text-align:left}
.compare-table td:first-child{text-align:left;font-weight:500;color:#374151}
.compare-table tr:last-child td{border-bottom:none}
.compare-table .highlight{background:#eff6ff}
.compare-table th.highlight{background:#dbeafe;color:#1e40af}
.check{color:#16a34a;font-weight:700}
.cross{color:#d1d5db}
.plan-header{font-size:13px;color:#6b7280;font-weight:400;display:block;margin-top:2px}
.plan-price{font-size:1.1rem;font-weight:700;color:#1e40af;margin-top:4px;display:block}
""", """
<div class="container">
<h1>플랜 비교</h1>
<table class="compare-table">
<thead><tr><th>기능</th><th>Free</th><th class="highlight">Pro <span class="plan-header">인기</span><span class="plan-price">₩29,000/월</span></th><th>Team <span class="plan-header">팀용</span><span class="plan-price">₩99,000/월</span></th></tr></thead>
<tbody>
<tr><td>일일 질문 수</td><td>50회</td><td class="highlight">무제한</td><td>무제한</td></tr>
<tr><td>AI 모델</td><td>7B</td><td class="highlight">30B</td><td>30B</td></tr>
<tr><td>코드 생성</td><td class="check">✓</td><td class="highlight check">✓</td><td class="check">✓</td></tr>
<tr><td>디자인 코드 생성</td><td class="cross">—</td><td class="highlight check">✓</td><td class="check">✓</td></tr>
<tr><td>API 접근</td><td class="cross">—</td><td class="highlight check">✓ (100K 토큰)</td><td class="check">✓ (무제한)</td></tr>
<tr><td>팀 협업</td><td class="cross">—</td><td class="highlight cross">—</td><td class="check">✓ (50명)</td></tr>
<tr><td>SSO 인증</td><td class="cross">—</td><td class="highlight cross">—</td><td class="check">✓</td></tr>
<tr><td>우선 응답</td><td class="cross">—</td><td class="highlight check">✓</td><td class="check">✓</td></tr>
<tr><td>전담 지원</td><td>커뮤니티</td><td class="highlight">이메일</td><td>전담 매니저</td></tr>
</tbody></table>
</div>"""),

]

DATA = []
for q, title, body_bg, css_str, body_str in ITEMS:
    html_code = f'''```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Pretendard',-apple-system,sans-serif;background:{body_bg};color:#1f2937}}
{css_str}
</style>
</head>
<body>
{body_str}
</body>
</html>
```'''
    DATA.append(m(q, f'''{title}을 만들어 드릴게요.

{html_code}

브라우저에서 바로 열어볼 수 있는 완전한 코드입니다!'''))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/500_design.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"디자인 추가: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
