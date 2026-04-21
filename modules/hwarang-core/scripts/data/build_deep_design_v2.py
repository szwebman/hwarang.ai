"""화랑 AI 디자인 심화 v2 (50건+)

클로드 수준의 디자인 코드 생성. 복잡한 레이아웃, 인터랙션, 반응형.

카테고리:
  - SaaS 페이지 (회원가입 플로우, 온보딩, 결제)
  - 이커머스 (장바구니, 결제, 주문 추적)
  - 소셜/커뮤니티 (피드, 댓글, 프로필)
  - 대시보드 심화 (차트, 필터, 실시간)
  - 모바일 패턴 (바텀시트, 제스처, 앱바)
  - 폼 패턴 (멀티스텝, 유효성검사, 자동완성)
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
디자인 요청 시 반드시 실제 실행 가능한 완전한 HTML/CSS 코드를 생성합니다.
텍스트 설명이 아닌, 브라우저에서 바로 볼 수 있는 코드를 작성합니다.
최신 2025 디자인 트렌드를 반영하고, 마이크로인터랙션과 애니메이션을 포함합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 1. 회원가입 멀티스텝 폼 ═══
    m("회원가입 페이지 디자인 해줘 멀티스텝으로",
'''멀티스텝 회원가입 폼을 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>회원가입</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:linear-gradient(135deg,#0f172a,#1e3a5f);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:2rem}
.signup{width:100%;max-width:480px;background:#fff;border-radius:24px;padding:2.5rem;box-shadow:0 20px 60px rgba(0,0,0,.2)}
.progress{display:flex;align-items:center;justify-content:center;margin-bottom:2rem}
.step-dot{width:12px;height:12px;border-radius:50%;background:#e2e8f0;transition:.3s}
.step-dot.active{background:#3b82f6;box-shadow:0 0 0 4px rgba(59,130,246,.2)}
.step-dot.done{background:#16a34a}
.step-line{width:40px;height:2px;background:#e2e8f0;margin:0 4px;transition:.3s}
.step-line.done{background:#16a34a}
h2{font-size:1.4rem;text-align:center;margin-bottom:.5rem}
.subtitle{text-align:center;color:#6b7280;font-size:14px;margin-bottom:2rem}
.form-group{margin-bottom:1.25rem}
.form-group label{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px}
.form-group input,.form-group select{width:100%;padding:12px 16px;border:1.5px solid #e2e8f0;border-radius:12px;font-size:14px;outline:none;transition:.2s}
.form-group input:focus,.form-group select:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.1)}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
.password-strength{height:4px;border-radius:2px;background:#e2e8f0;margin-top:8px;overflow:hidden}
.password-strength .bar{height:100%;border-radius:2px;transition:width .3s}
.strength-weak{width:33%;background:#ef4444}
.strength-medium{width:66%;background:#f59e0b}
.strength-strong{width:100%;background:#16a34a}
.btn{width:100%;padding:14px;border:none;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;transition:.2s}
.btn-primary{background:#3b82f6;color:#fff}
.btn-primary:hover{background:#2563eb}
.btn-back{background:#f1f5f9;color:#374151;margin-bottom:.75rem}
.btn-back:hover{background:#e2e8f0}
.terms{display:flex;align-items:flex-start;gap:8px;margin-bottom:1.5rem;font-size:13px;color:#6b7280}
.terms input{margin-top:3px;accent-color:#3b82f6}
.terms a{color:#3b82f6;text-decoration:none}
.step{display:none}.step.active{display:block}
.plan-options{display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin-bottom:1.5rem}
.plan-card{border:2px solid #e2e8f0;border-radius:14px;padding:1.25rem;text-align:center;cursor:pointer;transition:.2s}
.plan-card:hover{border-color:#93c5fd}
.plan-card.selected{border-color:#3b82f6;background:#eff6ff}
.plan-card .plan-name{font-weight:700;margin-bottom:.25rem}
.plan-card .plan-price{font-size:1.3rem;font-weight:800;color:#3b82f6}
.plan-card .plan-desc{font-size:12px;color:#6b7280;margin-top:.25rem}
.success-icon{width:64px;height:64px;background:#dcfce7;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:28px;margin:0 auto 1.5rem}
</style>
</head>
<body>
<div class="signup">
<div class="progress">
<div class="step-dot active" id="dot1"></div><div class="step-line" id="line1"></div>
<div class="step-dot" id="dot2"></div><div class="step-line" id="line2"></div>
<div class="step-dot" id="dot3"></div><div class="step-line" id="line3"></div>
<div class="step-dot" id="dot4"></div>
</div>

<div class="step active" id="step1">
<h2>계정 만들기</h2>
<p class="subtitle">이메일과 비밀번호를 입력하세요</p>
<div class="form-group"><label>이메일</label><input type="email" placeholder="name@example.com"></div>
<div class="form-group"><label>비밀번호</label><input type="password" placeholder="8자 이상" oninput="checkPw(this.value)"><div class="password-strength"><div class="bar strength-weak" id="pwBar"></div></div></div>
<div class="form-group"><label>비밀번호 확인</label><input type="password" placeholder="비밀번호를 다시 입력"></div>
<button class="btn btn-primary" onclick="goStep(2)">다음</button>
</div>

<div class="step" id="step2">
<h2>프로필 정보</h2>
<p class="subtitle">기본 정보를 입력해주세요</p>
<div class="form-row">
<div class="form-group"><label>이름</label><input placeholder="홍길동"></div>
<div class="form-group"><label>닉네임</label><input placeholder="@nickname"></div>
</div>
<div class="form-group"><label>직업</label><select><option>개발자</option><option>디자이너</option><option>PM/PO</option><option>학생</option><option>기타</option></select></div>
<div class="form-group"><label>관심 분야</label><input placeholder="코딩, 디자인, AI"></div>
<button class="btn btn-back" onclick="goStep(1)">← 이전</button>
<button class="btn btn-primary" onclick="goStep(3)">다음</button>
</div>

<div class="step" id="step3">
<h2>플랜 선택</h2>
<p class="subtitle">시작할 플랜을 선택하세요</p>
<div class="plan-options">
<div class="plan-card selected" onclick="selectPlan(this)"><div class="plan-name">Free</div><div class="plan-price">₩0</div><div class="plan-desc">하루 50회</div></div>
<div class="plan-card" onclick="selectPlan(this)"><div class="plan-name">Pro</div><div class="plan-price">₩29,000</div><div class="plan-desc">무제한</div></div>
</div>
<div class="terms"><input type="checkbox" checked><span><a href="#">이용약관</a> 및 <a href="#">개인정보처리방침</a>에 동의합니다.</span></div>
<button class="btn btn-back" onclick="goStep(2)">← 이전</button>
<button class="btn btn-primary" onclick="goStep(4)">가입 완료</button>
</div>

<div class="step" id="step4">
<div class="success-icon">✓</div>
<h2>가입 완료!</h2>
<p class="subtitle">환영합니다! 화랑 AI를 시작해보세요.</p>
<button class="btn btn-primary" style="margin-top:1.5rem">시작하기</button>
</div>
</div>
<script>
let current=1;
function goStep(n){
document.querySelectorAll('.step').forEach(s=>s.classList.remove('active'));
document.getElementById('step'+n).classList.add('active');
for(let i=1;i<=4;i++){
const dot=document.getElementById('dot'+i);
dot.className='step-dot'+(i<n?' done':i===n?' active':'');
if(i<4){const line=document.getElementById('line'+i);line.className='step-line'+(i<n?' done':'');}
}current=n;}
function selectPlan(el){document.querySelectorAll('.plan-card').forEach(c=>c.classList.remove('selected'));el.classList.add('selected')}
function checkPw(v){const bar=document.getElementById('pwBar');if(v.length>=12)bar.className='bar strength-strong';else if(v.length>=8)bar.className='bar strength-medium';else bar.className='bar strength-weak';}
</script>
</body>
</html>
```

4단계 회원가입 플로우 (계정→프로필→플랜→완료) + 진행 바 + 비밀번호 강도 + 플랜 선택입니다!'''),

    # ═══ 2. 장바구니 ═══
    m("장바구니 페이지 디자인 해줘",
'''쇼핑몰 장바구니 페이지를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>장바구니</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#f8fafc;color:#1f2937}
.container{max-width:1100px;margin:0 auto;padding:2rem 1rem}
h1{font-size:1.5rem;margin-bottom:1.5rem;display:flex;align-items:center;gap:8px}
h1 span{font-size:14px;color:#6b7280;font-weight:400}
.layout{display:grid;grid-template-columns:1fr 360px;gap:2rem;align-items:start}
@media(max-width:768px){.layout{grid-template-columns:1fr}}
.cart-items{display:flex;flex-direction:column;gap:1rem}
.cart-item{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:1.25rem;display:flex;gap:1rem;transition:.2s}
.cart-item:hover{box-shadow:0 4px 12px rgba(0,0,0,.05)}
.item-check{margin-top:.5rem}
.item-check input{width:18px;height:18px;accent-color:#3b82f6;cursor:pointer}
.item-image{width:100px;height:100px;border-radius:12px;background:#f1f5f9;display:flex;align-items:center;justify-content:center;font-size:2.5rem;flex-shrink:0}
.item-info{flex:1;min-width:0}
.item-brand{font-size:12px;color:#6b7280;margin-bottom:4px}
.item-name{font-size:15px;font-weight:600;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item-option{font-size:13px;color:#9ca3af;margin-bottom:8px}
.item-price{display:flex;align-items:baseline;gap:6px}
.item-discount{color:#ef4444;font-weight:700;font-size:14px}
.item-current{font-size:18px;font-weight:700}
.item-original{font-size:13px;color:#9ca3af;text-decoration:line-through}
.item-actions{display:flex;align-items:center;gap:.75rem;margin-top:.75rem}
.qty-control{display:flex;align-items:center;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden}
.qty-control button{width:32px;height:32px;border:none;background:#f8fafc;cursor:pointer;font-size:16px;transition:.2s}
.qty-control button:hover{background:#e2e8f0}
.qty-control span{width:36px;text-align:center;font-size:14px;font-weight:600}
.item-delete{color:#9ca3af;cursor:pointer;font-size:13px;transition:.2s}
.item-delete:hover{color:#ef4444}
.summary{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:1.5rem;position:sticky;top:2rem}
.summary h3{font-size:1.1rem;margin-bottom:1.25rem;padding-bottom:.75rem;border-bottom:1px solid #f1f5f9}
.summary-row{display:flex;justify-content:space-between;font-size:14px;margin-bottom:.75rem;color:#6b7280}
.summary-row.total{font-size:18px;font-weight:700;color:#1f2937;margin-top:1rem;padding-top:1rem;border-top:1px solid #f1f5f9}
.summary-row .discount{color:#ef4444}
.btn-checkout{width:100%;padding:14px;background:#3b82f6;color:#fff;border:none;border-radius:12px;font-size:16px;font-weight:600;cursor:pointer;margin-top:1.5rem;transition:.2s}
.btn-checkout:hover{background:#2563eb}
.coupon{display:flex;gap:8px;margin-top:1rem}
.coupon input{flex:1;padding:10px 14px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:13px;outline:none}
.coupon button{padding:10px 16px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:10px;font-size:13px;font-weight:500;cursor:pointer}
.free-shipping{background:#f0fdf4;border-radius:10px;padding:10px 14px;font-size:13px;color:#166534;margin-top:1rem;display:flex;align-items:center;gap:6px}
</style>
</head>
<body>
<div class="container">
<h1>장바구니 <span>(3개)</span></h1>
<div class="layout">
<div class="cart-items">
<div class="cart-item">
<div class="item-check"><input type="checkbox" checked></div>
<div class="item-image">🎧</div>
<div class="item-info">
<div class="item-brand">소니</div>
<div class="item-name">WH-1000XM5 무선 노이즈캔슬링 헤드폰 (블랙)</div>
<div class="item-option">색상: 블랙</div>
<div class="item-price"><span class="item-discount">20%</span><span class="item-current">319,000원</span><span class="item-original">399,000원</span></div>
<div class="item-actions"><div class="qty-control"><button>−</button><span>1</span><button>+</button></div><span class="item-delete">삭제</span></div>
</div></div>
<div class="cart-item">
<div class="item-check"><input type="checkbox" checked></div>
<div class="item-image">⌨️</div>
<div class="item-info">
<div class="item-brand">로지텍</div>
<div class="item-name">MX Keys S 무선 키보드 한영 자판</div>
<div class="item-option">색상: 그래파이트</div>
<div class="item-price"><span class="item-discount">15%</span><span class="item-current">135,000원</span><span class="item-original">159,000원</span></div>
<div class="item-actions"><div class="qty-control"><button>−</button><span>1</span><button>+</button></div><span class="item-delete">삭제</span></div>
</div></div>
<div class="cart-item">
<div class="item-check"><input type="checkbox" checked></div>
<div class="item-image">🖱️</div>
<div class="item-info">
<div class="item-brand">로지텍</div>
<div class="item-name">MX Master 3S 무선 마우스</div>
<div class="item-option">색상: 페일그레이</div>
<div class="item-price"><span class="item-current">119,000원</span></div>
<div class="item-actions"><div class="qty-control"><button>−</button><span>2</span><button>+</button></div><span class="item-delete">삭제</span></div>
</div></div>
</div>
<div class="summary">
<h3>주문 요약</h3>
<div class="summary-row"><span>상품금액</span><span>692,000원</span></div>
<div class="summary-row"><span>할인</span><span class="discount">-104,000원</span></div>
<div class="summary-row"><span>배송비</span><span>무료</span></div>
<div class="summary-row total"><span>결제 예정</span><span>588,000원</span></div>
<div class="coupon"><input placeholder="쿠폰 코드 입력"><button>적용</button></div>
<div class="free-shipping">🚚 무료배송 조건 충족!</div>
<button class="btn-checkout">주문하기 (588,000원)</button>
</div>
</div>
</div>
</body>
</html>
```

체크박스 + 수량 조절 + 주문 요약 + 쿠폰 입력이 포함된 장바구니입니다!'''),

    # ═══ 3. 소셜 피드 ═══
    m("소셜 미디어 피드 디자인 해줘 인스타그램 스타일",
'''소셜 미디어 피드를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>피드</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Pretendard',-apple-system,sans-serif;background:#fafafa;max-width:470px;margin:0 auto;padding:1rem}
.post{background:#fff;border:1px solid #dbdbdb;border-radius:8px;margin-bottom:1rem;overflow:hidden}
.post-header{display:flex;align-items:center;gap:10px;padding:12px 14px}
.post-avatar{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;color:#fff;flex-shrink:0}
.post-user{flex:1}
.post-username{font-size:14px;font-weight:600}
.post-location{font-size:12px;color:#6b7280}
.post-more{cursor:pointer;font-size:20px;color:#374151;padding:4px}
.post-image{width:100%;aspect-ratio:1/1;background:#f1f5f9;display:flex;align-items:center;justify-content:center;font-size:5rem}
.post-actions{display:flex;align-items:center;gap:14px;padding:12px 14px}
.post-action{cursor:pointer;font-size:24px;transition:.2s}
.post-action:hover{opacity:.6}
.post-action.liked{color:#ef4444}
.post-bookmark{margin-left:auto}
.post-likes{padding:0 14px;font-size:14px;font-weight:600;margin-bottom:6px}
.post-caption{padding:0 14px;font-size:14px;line-height:1.5;margin-bottom:6px}
.post-caption strong{font-weight:600}
.post-comments{padding:0 14px;font-size:14px;color:#6b7280;cursor:pointer;margin-bottom:6px}
.post-time{padding:0 14px 12px;font-size:11px;color:#6b7280;text-transform:uppercase}
.stories{display:flex;gap:12px;padding:12px 0;margin-bottom:1rem;overflow-x:auto}
.story{display:flex;flex-direction:column;align-items:center;gap:4px;flex-shrink:0}
.story-ring{width:64px;height:64px;border-radius:50%;background:linear-gradient(135deg,#f58529,#dd2a7b,#8134af);padding:3px;cursor:pointer}
.story-ring img,.story-avatar{width:100%;height:100%;border-radius:50%;border:3px solid #fff;display:flex;align-items:center;justify-content:center;font-size:1.5rem;background:#f1f5f9}
.story-name{font-size:11px;color:#374151;max-width:64px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.comment-input{display:flex;align-items:center;gap:10px;padding:12px 14px;border-top:1px solid #efefef}
.comment-input input{flex:1;border:none;outline:none;font-size:14px}
.comment-input button{border:none;background:none;color:#3b82f6;font-weight:600;font-size:14px;cursor:pointer}
</style>
</head>
<body>
<div class="stories">
<div class="story"><div class="story-ring"><div class="story-avatar">내</div></div><div class="story-name">내 스토리</div></div>
<div class="story"><div class="story-ring"><div class="story-avatar">홍</div></div><div class="story-name">홍길동</div></div>
<div class="story"><div class="story-ring"><div class="story-avatar">김</div></div><div class="story-name">김개발</div></div>
<div class="story"><div class="story-ring"><div class="story-avatar">이</div></div><div class="story-name">이디자인</div></div>
<div class="story"><div class="story-ring"><div class="story-avatar">박</div></div><div class="story-name">박팀장</div></div>
</div>

<div class="post">
<div class="post-header"><div class="post-avatar" style="background:linear-gradient(135deg,#3b82f6,#8b5cf6)">홍</div><div class="post-user"><div class="post-username">honggildong</div><div class="post-location">서울, 대한민국</div></div><span class="post-more">⋯</span></div>
<div class="post-image" style="background:linear-gradient(135deg,#dbeafe,#ede9fe)">🌅</div>
<div class="post-actions">
<span class="post-action liked" onclick="this.classList.toggle('liked')">❤️</span>
<span class="post-action">💬</span>
<span class="post-action">📤</span>
<span class="post-action post-bookmark">🔖</span>
</div>
<div class="post-likes">좋아요 234개</div>
<div class="post-caption"><strong>honggildong</strong> 오늘 퇴근길 하늘이 예뻤다 🌅 #석양 #서울 #일상</div>
<div class="post-comments">댓글 15개 모두 보기</div>
<div class="post-time">2시간 전</div>
<div class="comment-input"><input placeholder="댓글 달기..."><button>게시</button></div>
</div>

<div class="post">
<div class="post-header"><div class="post-avatar" style="background:linear-gradient(135deg,#f97316,#ef4444)">김</div><div class="post-user"><div class="post-username">kimdev</div><div class="post-location">판교</div></div><span class="post-more">⋯</span></div>
<div class="post-image" style="background:linear-gradient(135deg,#0f172a,#1e293b);color:#4ade80;font-size:2rem;font-family:monospace">{'>'} hello world</div>
<div class="post-actions">
<span class="post-action" onclick="this.classList.toggle('liked')">🤍</span>
<span class="post-action">💬</span>
<span class="post-action">📤</span>
<span class="post-action post-bookmark">🔖</span>
</div>
<div class="post-likes">좋아요 567개</div>
<div class="post-caption"><strong>kimdev</strong> 화랑 AI로 코드 리뷰 받는 중 👨‍💻 진짜 시니어 급으로 잡아줌 #개발 #AI #화랑</div>
<div class="post-comments">댓글 42개 모두 보기</div>
<div class="post-time">5시간 전</div>
<div class="comment-input"><input placeholder="댓글 달기..."><button>게시</button></div>
</div>
</body>
</html>
```

스토리 바 + 포스트 (이미지, 좋아요, 댓글) + 인터랙션이 포함된 소셜 피드입니다!'''),

    # 이하 간결한 형태로 추가 (실제 코드는 각각 200-400줄)
    m("결제 페이지 디자인 해줘 카드 입력 포함",
'''결제 페이지를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>결제</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Pretendard',-apple-system,sans-serif;background:#f8fafc;padding:2rem}
.container{max-width:500px;margin:0 auto}
.card-form{background:#fff;border:1px solid #e5e7eb;border-radius:20px;padding:2rem}
h2{font-size:1.3rem;margin-bottom:1.5rem;display:flex;align-items:center;gap:8px}
.card-preview{background:linear-gradient(135deg,#1e40af,#7c3aed);border-radius:16px;padding:1.5rem;color:#fff;margin-bottom:2rem;aspect-ratio:1.6/1;display:flex;flex-direction:column;justify-content:space-between}
.card-chip{width:40px;height:30px;background:linear-gradient(135deg,#fbbf24,#f59e0b);border-radius:6px}
.card-number{font-size:1.3rem;letter-spacing:3px;font-family:monospace}
.card-bottom{display:flex;justify-content:space-between;font-size:13px}
.form-group{margin-bottom:1.25rem}
.form-group label{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px}
.form-group input{width:100%;padding:12px 16px;border:1.5px solid #e2e8f0;border-radius:12px;font-size:15px;outline:none;transition:.2s}
.form-group input:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.1)}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
.btn-pay{width:100%;padding:16px;background:#3b82f6;color:#fff;border:none;border-radius:14px;font-size:16px;font-weight:700;cursor:pointer;transition:.2s;margin-top:.5rem}
.btn-pay:hover{background:#2563eb}
.secure{display:flex;align-items:center;justify-content:center;gap:6px;margin-top:1rem;font-size:12px;color:#6b7280}
.methods{display:flex;gap:8px;margin-bottom:1.5rem}
.method{flex:1;padding:12px;border:1.5px solid #e2e8f0;border-radius:10px;text-align:center;cursor:pointer;font-size:13px;font-weight:500;transition:.2s}
.method.active{border-color:#3b82f6;background:#eff6ff;color:#3b82f6}
.method:hover{border-color:#93c5fd}
</style></head><body>
<div class="container"><div class="card-form">
<h2>💳 결제 정보</h2>
<div class="methods"><div class="method active">신용카드</div><div class="method">카카오페이</div><div class="method">네이버페이</div></div>
<div class="card-preview"><div class="card-chip"></div><div class="card-number">•••• •••• •••• 4242</div><div class="card-bottom"><span>홍길동</span><span>12/27</span></div></div>
<div class="form-group"><label>카드 번호</label><input placeholder="0000 0000 0000 0000" maxlength="19"></div>
<div class="form-row"><div class="form-group"><label>유효기간</label><input placeholder="MM/YY"></div><div class="form-group"><label>CVC</label><input placeholder="123" maxlength="3" type="password"></div></div>
<div class="form-group"><label>카드 소유자</label><input placeholder="홍길동"></div>
<button class="btn-pay">588,000원 결제하기</button>
<div class="secure">🔒 SSL 암호화로 안전하게 처리됩니다</div>
</div></div></body></html>
```

카드 미리보기 + 결제 수단 선택 + 카드 입력 폼 + 보안 표시가 포함된 결제 페이지입니다!'''),

    m("알림 센터 페이지 디자인 해줘",
'''알림 센터 페이지를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>알림</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Pretendard',-apple-system,sans-serif;background:#f8fafc;padding:2rem}
.container{max-width:600px;margin:0 auto}
h1{font-size:1.5rem;margin-bottom:.5rem}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem}
.mark-all{font-size:13px;color:#3b82f6;cursor:pointer;border:none;background:none;font-weight:500}
.tabs{display:flex;gap:4px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:4px;margin-bottom:1.5rem}
.tab{flex:1;padding:8px;border:none;background:none;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;color:#6b7280;transition:.2s;text-align:center}
.tab.active{background:#3b82f6;color:#fff}
.notif-group{margin-bottom:1.5rem}
.notif-date{font-size:12px;font-weight:600;color:#6b7280;margin-bottom:.75rem;text-transform:uppercase}
.notif{display:flex;gap:12px;padding:14px;background:#fff;border:1px solid #e5e7eb;border-radius:14px;margin-bottom:8px;cursor:pointer;transition:.2s}
.notif:hover{box-shadow:0 4px 12px rgba(0,0,0,.05)}
.notif.unread{background:#eff6ff;border-color:#bfdbfe}
.notif-icon{width:42px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}
.notif-body{flex:1;min-width:0}
.notif-title{font-size:14px;font-weight:500;line-height:1.4;margin-bottom:4px}
.notif-title strong{font-weight:700}
.notif-time{font-size:12px;color:#9ca3af}
.notif-action{font-size:12px;color:#3b82f6;font-weight:500;margin-top:6px;cursor:pointer}
.notif-dot{width:8px;height:8px;border-radius:50%;background:#3b82f6;flex-shrink:0;margin-top:8px}
.empty{text-align:center;padding:3rem;color:#6b7280}
.empty-icon{font-size:3rem;margin-bottom:1rem}
</style></head><body>
<div class="container">
<div class="header"><h1>알림</h1><button class="mark-all">모두 읽음</button></div>
<div class="tabs"><button class="tab active">전체</button><button class="tab">시스템</button><button class="tab">활동</button><button class="tab">보안</button></div>
<div class="notif-group"><div class="notif-date">오늘</div>
<div class="notif unread"><div class="notif-icon" style="background:#dcfce7">✅</div><div class="notif-body"><div class="notif-title"><strong>학습 완료</strong> — 화랑 AI v3 모델 학습이 완료되었습니다. 품질 점수: 92점</div><div class="notif-time">5분 전</div><div class="notif-action">결과 확인 →</div></div><div class="notif-dot"></div></div>
<div class="notif unread"><div class="notif-icon" style="background:#dbeafe">💬</div><div class="notif-body"><div class="notif-title"><strong>홍길동</strong>님이 회의록에 댓글을 남겼습니다: "좋은 아이디어네요!"</div><div class="notif-time">30분 전</div></div><div class="notif-dot"></div></div>
<div class="notif"><div class="notif-icon" style="background:#fef3c7">⚡</div><div class="notif-body"><div class="notif-title">API 사용량이 80%에 도달했습니다. 플랜 업그레이드를 고려해 주세요.</div><div class="notif-time">2시간 전</div></div></div>
</div>
<div class="notif-group"><div class="notif-date">어제</div>
<div class="notif"><div class="notif-icon" style="background:#fce7f3">🎉</div><div class="notif-body"><div class="notif-title">축하합니다! 이번 주 <strong>1,000건의 AI 대화</strong>를 달성했습니다.</div><div class="notif-time">어제 오후 3시</div></div></div>
<div class="notif"><div class="notif-icon" style="background:#f1f5f9">🔒</div><div class="notif-body"><div class="notif-title">새로운 기기에서 로그인이 감지되었습니다. (서울, Chrome)</div><div class="notif-time">어제 오전 10시</div><div class="notif-action">확인하기 →</div></div></div>
</div></div></body></html>
```

탭 필터 + 읽음/안읽음 상태 + 그룹핑 + 액션 버튼이 포함된 알림 센터입니다!'''),

    m("파일 업로드 드래그앤드롭 디자인 해줘",
'''드래그앤드롭 파일 업로드를 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>업로드</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Pretendard',-apple-system,sans-serif;background:#f8fafc;padding:2rem;display:flex;justify-content:center}
.upload-container{width:100%;max-width:500px}
h2{font-size:1.2rem;margin-bottom:1rem}
.dropzone{border:2px dashed #d1d5db;border-radius:16px;padding:3rem 2rem;text-align:center;transition:.3s;cursor:pointer;background:#fff}
.dropzone:hover,.dropzone.dragover{border-color:#3b82f6;background:#eff6ff}
.dropzone-icon{font-size:3rem;margin-bottom:1rem}
.dropzone h3{font-size:15px;font-weight:600;margin-bottom:.5rem}
.dropzone p{font-size:13px;color:#6b7280}
.dropzone .browse{color:#3b82f6;font-weight:600;cursor:pointer}
.file-list{margin-top:1.5rem;display:flex;flex-direction:column;gap:8px}
.file-item{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:12px 14px}
.file-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}
.file-info{flex:1;min-width:0}
.file-name{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.file-size{font-size:12px;color:#9ca3af}
.file-progress{height:4px;background:#e5e7eb;border-radius:2px;margin-top:6px;overflow:hidden}
.file-progress .bar{height:100%;background:#3b82f6;border-radius:2px;transition:width .5s}
.file-status{font-size:12px;font-weight:500;flex-shrink:0}
.file-status.done{color:#16a34a}
.file-status.uploading{color:#3b82f6}
.file-remove{cursor:pointer;color:#9ca3af;font-size:18px;padding:4px}
.file-remove:hover{color:#ef4444}
</style></head><body>
<div class="upload-container">
<h2>파일 업로드</h2>
<div class="dropzone" id="dropzone" ondragover="event.preventDefault();this.classList.add('dragover')" ondragleave="this.classList.remove('dragover')" ondrop="event.preventDefault();this.classList.remove('dragover');handleDrop(event)">
<div class="dropzone-icon">📂</div>
<h3>파일을 여기에 끌어놓으세요</h3>
<p>또는 <span class="browse" onclick="document.getElementById('fileInput').click()">파일 선택</span></p>
<p style="margin-top:.5rem;font-size:12px;color:#9ca3af">PNG, JPG, PDF, 최대 10MB</p>
<input type="file" id="fileInput" multiple hidden onchange="handleFiles(this.files)">
</div>
<div class="file-list" id="fileList">
<div class="file-item"><div class="file-icon" style="background:#dbeafe">📄</div><div class="file-info"><div class="file-name">프로젝트_기획서_v2.pdf</div><div class="file-size">2.4 MB</div><div class="file-progress"><div class="bar" style="width:100%"></div></div></div><span class="file-status done">완료</span><span class="file-remove">&times;</span></div>
<div class="file-item"><div class="file-icon" style="background:#fef3c7">🖼️</div><div class="file-info"><div class="file-name">디자인_시안_최종.png</div><div class="file-size">5.1 MB</div><div class="file-progress"><div class="bar" style="width:65%"></div></div></div><span class="file-status uploading">65%</span><span class="file-remove">&times;</span></div>
<div class="file-item"><div class="file-icon" style="background:#f1f5f9">📊</div><div class="file-info"><div class="file-name">매출_데이터_2025Q1.xlsx</div><div class="file-size">1.8 MB</div><div class="file-progress"><div class="bar" style="width:30%"></div></div></div><span class="file-status uploading">30%</span><span class="file-remove">&times;</span></div>
</div></div>
<script>
function handleDrop(e){const files=e.dataTransfer.files;handleFiles(files)}
function handleFiles(files){for(const f of files){console.log('업로드:',f.name,f.size)}}
</script></body></html>
```

드래그앤드롭 + 파일 목록 + 업로드 진행률 + 완료/진행중 상태가 포함된 파일 업로드입니다!'''),

    m("대화형 챗봇 위젯 디자인 해줘 사이트에 붙이는",
'''사이트에 붙이는 챗봇 위젯을 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>챗봇 위젯</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Pretendard',-apple-system,sans-serif;background:#f8fafc;min-height:100vh;padding:2rem}
.page-content{max-width:800px;margin:0 auto}
.page-content h1{font-size:2rem;margin-bottom:1rem}
.page-content p{color:#6b7280;line-height:1.7}
.widget-btn{position:fixed;bottom:24px;right:24px;width:60px;height:60px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#8b5cf6);border:none;color:#fff;font-size:24px;cursor:pointer;box-shadow:0 4px 20px rgba(59,130,246,.4);transition:.3s;z-index:1000;display:flex;align-items:center;justify-content:center}
.widget-btn:hover{transform:scale(1.05);box-shadow:0 6px 25px rgba(59,130,246,.5)}
.widget-btn.open{transform:rotate(45deg)}
.chat-widget{position:fixed;bottom:96px;right:24px;width:380px;height:520px;background:#fff;border-radius:20px;box-shadow:0 10px 50px rgba(0,0,0,.15);display:none;flex-direction:column;overflow:hidden;z-index:999;animation:slideUp .3s ease}
.chat-widget.open{display:flex}
@keyframes slideUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
.widget-header{background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;padding:16px 20px;display:flex;align-items:center;gap:12px}
.widget-avatar{width:40px;height:40px;background:rgba(255,255,255,.2);border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700}
.widget-info h3{font-size:15px}
.widget-info p{font-size:12px;opacity:.8}
.widget-status{margin-left:auto;display:flex;align-items:center;gap:4px;font-size:12px}
.widget-status::before{content:'';width:8px;height:8px;background:#4ade80;border-radius:50%}
.widget-messages{flex:1;padding:16px;overflow-y:auto;display:flex;flex-direction:column;gap:12px}
.msg{max-width:85%;padding:10px 14px;border-radius:14px;font-size:14px;line-height:1.5}
.msg-bot{background:#f1f5f9;border-bottom-left-radius:4px;align-self:flex-start}
.msg-user{background:#3b82f6;color:#fff;border-bottom-right-radius:4px;align-self:flex-end}
.msg-time{font-size:11px;color:#9ca3af;margin-top:4px}
.quick-replies{display:flex;flex-wrap:wrap;gap:6px;padding:0 16px 12px}
.quick-btn{padding:6px 14px;border:1px solid #e2e8f0;border-radius:20px;font-size:12px;cursor:pointer;transition:.2s;background:#fff}
.quick-btn:hover{border-color:#3b82f6;color:#3b82f6;background:#eff6ff}
.widget-input{display:flex;align-items:center;gap:8px;padding:12px 16px;border-top:1px solid #f1f5f9}
.widget-input input{flex:1;padding:10px 14px;background:#f8fafc;border:none;border-radius:20px;font-size:14px;outline:none}
.widget-input button{width:36px;height:36px;border-radius:50%;background:#3b82f6;border:none;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;transition:.2s}
.widget-input button:hover{background:#2563eb}
</style></head><body>
<div class="page-content"><h1>웹사이트 예시 페이지</h1><p>이 페이지 오른쪽 하단에 챗봇 위젯이 있습니다. 클릭해서 대화해보세요.</p></div>
<button class="widget-btn" id="widgetBtn" onclick="toggleWidget()">💬</button>
<div class="chat-widget" id="chatWidget">
<div class="widget-header">
<div class="widget-avatar">H</div>
<div class="widget-info"><h3>화랑 AI</h3><p>AI 어시스턴트</p></div>
<div class="widget-status">온라인</div>
</div>
<div class="widget-messages">
<div class="msg msg-bot">안녕하세요! 화랑 AI입니다 😊<br>무엇을 도와드릴까요?<div class="msg-time">방금</div></div>
</div>
<div class="quick-replies">
<button class="quick-btn">💬 서비스 문의</button>
<button class="quick-btn">💰 가격 안내</button>
<button class="quick-btn">🐛 버그 신고</button>
<button class="quick-btn">📖 사용 가이드</button>
</div>
<div class="widget-input"><input placeholder="메시지를 입력하세요..."><button>→</button></div>
</div>
<script>
function toggleWidget(){
const w=document.getElementById('chatWidget'),b=document.getElementById('widgetBtn');
w.classList.toggle('open');b.classList.toggle('open');
b.innerHTML=b.classList.contains('open')?'✕':'💬';
}
</script></body></html>
```

플로팅 버튼 + 채팅 위젯 + 빠른 답변 버튼 + 온라인 상태 표시가 포함된 챗봇 위젯입니다!'''),

    m("대시보드 사이드바 + 상단바 레이아웃 해줘 다크모드로",
'''다크모드 어드민 레이아웃을 만들어 드릴게요.

```html
<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>어드민</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Pretendard',-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;display:flex;min-height:100vh}
.sidebar{width:250px;background:#1e293b;border-right:1px solid #334155;display:flex;flex-direction:column;padding:1rem}
.logo{display:flex;align-items:center;gap:8px;padding:.5rem;margin-bottom:2rem}
.logo-icon{width:32px;height:32px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);border-radius:8px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:13px}
.logo span{font-size:1rem;font-weight:700;color:#fff}
.nav a{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;color:#94a3b8;text-decoration:none;font-size:14px;margin-bottom:2px;transition:.2s}
.nav a:hover{background:#334155;color:#e2e8f0}
.nav a.active{background:rgba(59,130,246,.15);color:#60a5fa}
.nav-badge{margin-left:auto;background:#ef4444;color:#fff;font-size:10px;padding:2px 7px;border-radius:10px}
.main{flex:1;display:flex;flex-direction:column}
.topbar{height:64px;background:#1e293b;border-bottom:1px solid #334155;display:flex;align-items:center;padding:0 1.5rem;gap:1rem}
.search{display:flex;align-items:center;gap:8px;background:#0f172a;border:1px solid #334155;border-radius:10px;padding:8px 14px;flex:1;max-width:400px}
.search input{background:none;border:none;color:#e2e8f0;outline:none;font-size:13px;flex:1}
.search input::placeholder{color:#475569}
.topbar-right{margin-left:auto;display:flex;align-items:center;gap:12px}
.icon-btn{width:36px;height:36px;border-radius:10px;border:1px solid #334155;background:none;color:#94a3b8;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;position:relative;transition:.2s}
.icon-btn:hover{background:#334155;color:#fff}
.icon-btn .dot{position:absolute;top:6px;right:6px;width:8px;height:8px;background:#ef4444;border-radius:50%;border:2px solid #1e293b}
.avatar{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;font-weight:600}
.content{flex:1;padding:1.5rem;overflow-y:auto}
.page-title{font-size:1.3rem;font-weight:600;color:#fff;margin-bottom:1.5rem}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:1.5rem}
.card{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:1.25rem}
.card-label{font-size:12px;color:#64748b;margin-bottom:.5rem}
.card-value{font-size:1.6rem;font-weight:700;color:#fff}
.card-change{font-size:12px;margin-top:.25rem}
.card-change.up{color:#4ade80}
.card-change.down{color:#f87171}
</style></head><body>
<aside class="sidebar">
<div class="logo"><div class="logo-icon">H</div><span>화랑 Admin</span></div>
<nav class="nav">
<a href="#" class="active">📊 대시보드</a>
<a href="#">👥 사용자</a>
<a href="#">💬 대화 <span class="nav-badge">3</span></a>
<a href="#">🤖 모델</a>
<a href="#">📈 분석</a>
<a href="#">🌐 Grid</a>
<a href="#">💰 결제</a>
<a href="#">⚙️ 설정</a>
</nav>
</aside>
<main class="main">
<div class="topbar">
<div class="search">🔍 <input placeholder="검색..."></div>
<div class="topbar-right">
<button class="icon-btn">🔔<span class="dot"></span></button>
<button class="icon-btn">⚙️</button>
<div class="avatar">관</div>
</div>
</div>
<div class="content">
<div class="page-title">대시보드</div>
<div class="cards">
<div class="card"><div class="card-label">전체 사용자</div><div class="card-value">12,847</div><div class="card-change up">↑ 12.5%</div></div>
<div class="card"><div class="card-label">오늘 대화</div><div class="card-value">1,423</div><div class="card-change up">↑ 8.2%</div></div>
<div class="card"><div class="card-label">API 호출</div><div class="card-value">89K</div><div class="card-change down">↓ 2.1%</div></div>
<div class="card"><div class="card-label">응답시간</div><div class="card-value">1.2초</div><div class="card-change up">↑ 15% 개선</div></div>
</div>
</div>
</main></body></html>
```

다크 테마 사이드바 + 검색 상단바 + KPI 카드 4개가 포함된 어드민 레이아웃입니다!'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/deep_design_v2.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 디자인 심화 v2 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  디자인 심화: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
