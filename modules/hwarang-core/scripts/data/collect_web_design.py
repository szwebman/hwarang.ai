"""웹디자인 SFT 데이터 수집 스크립트.

소스:
  1. HuggingFace 공개 데이터셋 (WebSight, Pix2Code 등)
  2. GitHub 인기 UI 라이브러리 (shadcn, Tailwind)
  3. 디자인 시스템 템플릿 (커스텀 큐레이션)

사용법:
    python scripts/data/collect_web_design.py \\
        --output data/sft/web_design.jsonl \\
        --max-samples 10000

필요 패키지:
    pip install datasets requests beautifulsoup4
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


SYSTEM_PROMPT_DESIGN = """당신은 화랑 AI 웹디자인 어시스턴트입니다.
모던하고 한국 사용자에게 친숙한 UI/UX를 생성합니다.

[화랑 디자인 원칙]
- 깔끔하고 미니멀 (네이버, 카카오 스타일)
- Tailwind CSS + shadcn/ui 기반
- 반응형 디자인 (모바일 우선)
- 다크 모드 지원
- 한국어 가독성 고려 (Pretendard 폰트)
- 컬러 팔레트: 인디고(#6366f1) + 퍼플(#8b5cf6)

[코드 스타일]
- React + TypeScript + Tailwind CSS
- 의미있는 변수명 (한국어 주석)
- 접근성 (ARIA 속성)
- 성능 최적화 (memo, lazy loading)"""


# ─── HuggingFace 데이터셋 ────────────────────────────────────

HF_WEBDESIGN_DATASETS = [
    {"name": "HuggingFaceM4/WebSight", "type": "image2code", "limit": 3000},
    {"name": "xcodemind/webcode2m", "type": "image2code", "limit": 2000},
    {"name": "HuggingFaceM4/Design2Code", "type": "image2code", "limit": 1000},
    {"name": "shtoshni/html_qa", "type": "qa", "limit": 2000},
]


def collect_hf_webdesign(max_per_dataset: int = 3000) -> list[dict]:
    """HuggingFace에서 웹디자인 데이터 수집."""
    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("datasets 패키지 없음")
        return []

    all_data = []

    for ds_info in HF_WEBDESIGN_DATASETS:
        name = ds_info["name"]
        dtype = ds_info["type"]
        limit = min(ds_info["limit"], max_per_dataset)

        logger.info(f"수집 중: {name} (type={dtype}, limit={limit})")

        try:
            ds = load_dataset(name, split="train", streaming=True, trust_remote_code=True)
            count = 0
            for item in ds:
                if count >= limit:
                    break

                if dtype == "image2code":
                    # 이미지는 비전 모델 학습용, 여기선 설명→코드로 변환
                    text_desc = item.get("text", item.get("description", ""))
                    code = item.get("html", item.get("code", ""))
                    if text_desc and code:
                        all_data.append({
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT_DESIGN},
                                {"role": "user", "content": f"다음과 같은 웹페이지를 만들어주세요:\n{text_desc[:500]}"},
                                {"role": "assistant", "content": f"```html\n{code[:3000]}\n```"},
                            ]
                        })
                        count += 1

                elif dtype == "qa":
                    q = item.get("question", item.get("instruction", ""))
                    a = item.get("answer", item.get("output", ""))
                    if q and a:
                        all_data.append({
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT_DESIGN},
                                {"role": "user", "content": q},
                                {"role": "assistant", "content": a},
                            ]
                        })
                        count += 1

            logger.info(f"  → {count}개")
        except Exception as e:
            logger.warning(f"  실패: {e}")

    return all_data


# ─── 화랑 디자인 시스템 템플릿 (커스텀 큐레이션) ─────────────

DESIGN_TEMPLATES = [
    # 랜딩 페이지 Hero 섹션
    {
        "q": "AI 서비스 랜딩 페이지의 Hero 섹션을 만들어줘. 모던하고 한국어로.",
        "a": """Hero 섹션 구현입니다. 그라디언트와 글래스모피즘을 활용했습니다.

```tsx
import Link from 'next/link';

export function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden"
      style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%)' }}>

      {/* 배경 장식 */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-[600px] h-[600px] rounded-full opacity-20"
          style={{ background: 'radial-gradient(circle, #6366f1 0%, transparent 70%)' }} />
        <div className="absolute -bottom-40 -left-40 w-[600px] h-[600px] rounded-full opacity-15"
          style={{ background: 'radial-gradient(circle, #8b5cf6 0%, transparent 70%)' }} />
      </div>

      {/* 메인 콘텐츠 */}
      <div className="relative z-10 max-w-5xl mx-auto px-6 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full mb-8
          bg-white/10 backdrop-blur-md border border-white/20">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-sm text-white/80">한국형 AI, 지금 체험</span>
        </div>

        <h1 className="text-6xl md:text-7xl font-bold text-white mb-6 tracking-tight">
          한국어를 가장 잘 이해하는<br />
          <span className="bg-clip-text text-transparent"
            style={{ backgroundImage: 'linear-gradient(to right, #a78bfa, #60a5fa)' }}>
            AI 어시스턴트
          </span>
        </h1>

        <p className="text-lg md:text-xl text-white/70 mb-10 max-w-2xl mx-auto">
          코딩, 법률, 세무. 한국인의 일상과 업무를 돕는 AI.<br />
          지금 Free 플랜으로 시작하세요.
        </p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link href="/register"
            className="px-8 py-3 rounded-xl text-base font-semibold text-white transition-all hover:scale-105"
            style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                     boxShadow: '0 10px 30px rgba(99,102,241,0.4)' }}>
            무료로 시작하기 →
          </Link>
          <Link href="/pricing"
            className="px-8 py-3 rounded-xl text-base font-medium text-white/90 border border-white/20 hover:bg-white/10 transition-all">
            요금제 보기
          </Link>
        </div>
      </div>
    </section>
  );
}
```

**디자인 포인트:**
- 글래스모피즘 (`backdrop-blur-md`)
- 그라디언트 버튼 + 섀도우
- 한국어 줄바꿈 고려 (`<br>`)
- 호버 스케일 애니메이션
""",
    },

    # 카드 컴포넌트
    {
        "q": "가격 플랜 카드 컴포넌트를 Tailwind로 만들어줘. 추천 표시 포함.",
        "a": """요금제 카드 컴포넌트입니다.

```tsx
interface PlanCardProps {
  name: string;
  price: number;
  tokens: number;
  features: string[];
  isRecommended?: boolean;
}

export function PlanCard({ name, price, tokens, features, isRecommended }: PlanCardProps) {
  return (
    <div className={`relative rounded-2xl p-6 transition-all ${
      isRecommended
        ? 'border-2 border-indigo-500 shadow-xl shadow-indigo-100'
        : 'border border-gray-200 hover:border-gray-300'
    }`}>

      {/* 추천 뱃지 */}
      {isRecommended && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold text-white"
            style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}>
            ⭐ 추천
          </span>
        </div>
      )}

      <h3 className="text-lg font-bold text-gray-900 mb-2">{name}</h3>

      <div className="flex items-baseline gap-1 mb-6">
        <span className="text-4xl font-bold">
          {price > 0 ? `₩${price.toLocaleString()}` : '무료'}
        </span>
        {price > 0 && <span className="text-sm text-gray-500">/월</span>}
      </div>

      {/* 토큰 */}
      <div className="p-3 rounded-lg bg-gray-50 mb-6">
        <div className="text-xs text-gray-500">월 토큰</div>
        <div className="text-lg font-bold text-indigo-600">
          {tokens.toLocaleString()}
        </div>
      </div>

      {/* 기능 목록 */}
      <ul className="space-y-2 mb-6">
        {features.map((feat, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <svg className="w-5 h-5 text-emerald-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/>
            </svg>
            <span className="text-gray-700">{feat}</span>
          </li>
        ))}
      </ul>

      {/* CTA */}
      <button className={`w-full py-2.5 rounded-xl font-medium transition-all ${
        isRecommended
          ? 'text-white hover:shadow-lg'
          : 'border border-gray-200 hover:border-gray-300'
      }`} style={isRecommended ? {
        background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
      } : {}}>
        시작하기
      </button>
    </div>
  );
}
```

**반응형 그리드로 배치:**
```tsx
<div className="grid grid-cols-1 md:grid-cols-3 gap-6">
  <PlanCard name="Free" price={0} tokens={10000} features={[...]} />
  <PlanCard name="Pro" price={29900} tokens={500000} features={[...]} isRecommended />
  <PlanCard name="Business" price={99000} tokens={2000000} features={[...]} />
</div>
```
""",
    },

    # 대시보드 레이아웃
    {
        "q": "관리자 대시보드 레이아웃 만들어줘. 좌측 사이드바, 우측 콘텐츠 구조로.",
        "a": """관리자 대시보드 레이아웃입니다.

```tsx
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV_ITEMS = [
  { href: '/', icon: '📊', label: '대시보드' },
  { href: '/users', icon: '👥', label: '유저 관리' },
  { href: '/billing', icon: '💳', label: '매출' },
  { href: '/settings', icon: '⚙️', label: '설정' },
];

export function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen bg-gray-50">
      {/* 사이드바 */}
      <aside className="w-60 bg-slate-900 flex flex-col">
        {/* 로고 */}
        <div className="flex items-center gap-3 px-5 h-16 border-b border-white/10">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold"
            style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}>
            H
          </div>
          <div>
            <div className="text-sm font-semibold text-white">Hwarang</div>
            <div className="text-[10px] text-slate-400">Admin</div>
          </div>
        </div>

        {/* 네비게이션 */}
        <nav className="flex-1 p-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link key={item.href} href={item.href}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-indigo-500/20 text-indigo-200'
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}>
                <span>{item.icon}</span>
                <span className={isActive ? 'font-medium' : ''}>{item.label}</span>
                {isActive && (
                  <span className="ml-auto w-1 h-4 rounded-full bg-indigo-400" />
                )}
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* 메인 콘텐츠 */}
      <main className="flex-1 overflow-y-auto">
        {/* 상단 바 */}
        <header className="sticky top-0 z-10 h-16 bg-white border-b flex items-center justify-between px-6">
          <h1 className="text-lg font-semibold">관리자 패널</h1>
          <div className="flex items-center gap-3">
            <button className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center">🔔</button>
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500" />
          </div>
        </header>

        {/* 콘텐츠 */}
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
```

**특징:**
- 고정 사이드바 + 스크롤 가능한 메인
- 활성 메뉴 강조 (좌측 인디케이터)
- Sticky 헤더
""",
    },

    # 폼 컴포넌트
    {
        "q": "모던한 로그인 폼을 만들어줘. 애니메이션과 유효성 검사 포함.",
        "a": """애니메이션이 있는 로그인 폼입니다.

```tsx
import { useState } from 'react';

export function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [loading, setLoading] = useState(false);

  const validate = () => {
    const newErrors: typeof errors = {};
    if (!email) newErrors.email = '이메일을 입력하세요';
    else if (!/\\S+@\\S+\\.\\S+/.test(email)) newErrors.email = '올바른 이메일 형식이 아닙니다';
    if (!password) newErrors.password = '비밀번호를 입력하세요';
    else if (password.length < 8) newErrors.password = '8자 이상 입력하세요';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    // 로그인 로직
    await new Promise(r => setTimeout(r, 1000));
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4"
      style={{ background: 'linear-gradient(135deg, #f0f4ff 0%, #faf5ff 100%)' }}>
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <div className="text-center mb-8">
            <div className="w-14 h-14 rounded-2xl mx-auto mb-4 flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}>
              <span className="text-white text-2xl font-bold">H</span>
            </div>
            <h1 className="text-2xl font-bold">다시 만나 반가워요</h1>
            <p className="text-sm text-gray-500 mt-1">계정에 로그인하세요</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* 이메일 */}
            <div className="group">
              <label className="block text-sm font-medium mb-1.5">이메일</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={`w-full px-4 py-3 rounded-xl border text-sm transition-all outline-none
                  ${errors.email
                    ? 'border-red-500 focus:ring-2 focus:ring-red-200'
                    : 'border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'}`}
                placeholder="you@example.com"
              />
              {errors.email && (
                <p className="text-xs text-red-500 mt-1 animate-in slide-in-from-top-1">
                  {errors.email}
                </p>
              )}
            </div>

            {/* 비밀번호 */}
            <div className="group">
              <label className="block text-sm font-medium mb-1.5">비밀번호</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={`w-full px-4 py-3 rounded-xl border text-sm transition-all outline-none
                  ${errors.password
                    ? 'border-red-500 focus:ring-2 focus:ring-red-200'
                    : 'border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'}`}
                placeholder="••••••••"
              />
              {errors.password && (
                <p className="text-xs text-red-500 mt-1 animate-in slide-in-from-top-1">
                  {errors.password}
                </p>
              )}
            </div>

            {/* 제출 버튼 */}
            <button type="submit" disabled={loading}
              className="w-full py-3 rounded-xl text-white font-medium transition-all disabled:opacity-60"
              style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}>
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  로그인 중...
                </span>
              ) : '로그인'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
```

**핵심 디자인:**
- 그라디언트 배경
- 포커스 링 애니메이션
- 에러 메시지 slide-in 애니메이션
- 로딩 스피너
""",
    },
]


def generate_design_templates() -> list[dict]:
    """디자인 템플릿에서 SFT 데이터 생성."""
    data = []
    for t in DESIGN_TEMPLATES:
        data.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_DESIGN},
                {"role": "user", "content": t["q"]},
                {"role": "assistant", "content": t["a"]},
            ]
        })
    return data


# ─── GitHub 인기 UI 라이브러리 ────────────────────────────

POPULAR_UI_REPOS = [
    "shadcn-ui/ui",
    "tailwindlabs/tailwindui",
    "radix-ui/primitives",
    "mui/material-ui",
    "chakra-ui/chakra-ui",
    "ant-design/ant-design",
    "mantinedev/mantine",
    "nextui-org/nextui",
    "geist-org/geist",
    "tremorlabs/tremor",
]


def generate_github_qa() -> list[dict]:
    """GitHub 인기 라이브러리 사용법 Q&A."""
    qa = [
        {
            "q": "shadcn/ui의 Button 컴포넌트 커스터마이징 방법",
            "a": """shadcn/ui Button은 Tailwind 기반이라 쉽게 커스터마이징 가능합니다.

```tsx
// components/ui/button.tsx (shadcn 기본)
import { cva } from 'class-variance-authority';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'bg-primary text-white hover:bg-primary/90',
        destructive: 'bg-red-500 text-white hover:bg-red-600',
        outline: 'border border-input hover:bg-accent',
        ghost: 'hover:bg-accent',
        // 🎨 화랑 커스텀 variant 추가
        hwarang: 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white hover:shadow-lg',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 px-3',
        lg: 'h-11 px-8',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  }
);

export function Button({ className, variant, size, ...props }) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
```

**사용:**
```tsx
<Button variant="hwarang" size="lg">화랑 시작하기</Button>
```""",
        },
        {
            "q": "Tailwind에서 커스텀 컬러 팔레트 설정하는 방법",
            "a": """`tailwind.config.js`에서 확장하면 됩니다.

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        hwarang: {
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#6366f1', // primary
          600: '#4f46e5',
          900: '#312e81',
        },
        brand: {
          primary: '#6366f1',
          secondary: '#8b5cf6',
          accent: '#06b6d4',
        },
      },
    },
  },
};
```

**사용:**
```tsx
<div className="bg-hwarang-500 hover:bg-hwarang-600">
  <h1 className="text-brand-primary">화랑 AI</h1>
</div>
```

**CSS 변수 방식 (테마 전환 쉬움):**
```css
/* globals.css */
:root {
  --primary: #6366f1;
}
.dark {
  --primary: #818cf8;
}
```
```js
// tailwind.config.js
colors: {
  primary: 'rgb(var(--primary) / <alpha-value>)',
}
```""",
        },
    ]

    return [{
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_DESIGN},
            {"role": "user", "content": item["q"]},
            {"role": "assistant", "content": item["a"]},
        ]
    } for item in qa]


# ─── 메인 ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="웹디자인 SFT 데이터 수집")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-samples", type=int, default=10000)
    parser.add_argument("--skip-hf", action="store_true")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" 웹디자인 SFT 데이터 수집")
    logger.info("=" * 60)

    all_data = []

    # 1. 화랑 디자인 템플릿
    logger.info("\n[1/3] 화랑 디자인 템플릿...")
    templates = generate_design_templates()
    all_data.extend(templates)
    logger.info(f"  → {len(templates)}개")

    # 2. GitHub UI 라이브러리 Q&A
    logger.info("\n[2/3] UI 라이브러리 Q&A...")
    gh_qa = generate_github_qa()
    all_data.extend(gh_qa)
    logger.info(f"  → {len(gh_qa)}개")

    # 3. HuggingFace 웹디자인 데이터셋
    if not args.skip_hf:
        logger.info("\n[3/3] HuggingFace 데이터셋...")
        hf_data = collect_hf_webdesign(max_per_dataset=args.max_samples // 4)
        all_data.extend(hf_data)

    # 저장
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"\n총 {len(all_data)}개 → {args.output}")
    logger.info("=" * 60)
    logger.info("\n다음 단계:")
    logger.info(f"  python scripts/qlora_qwen.py \\")
    logger.info(f"    --model-path /mnt/nvme2/hwarang/models/qwen3-coder-30b \\")
    logger.info(f"    --data {args.output} \\")
    logger.info(f"    --output /mnt/nvme2/hwarang/lora_adapters/hwarang-design-v1")


if __name__ == "__main__":
    main()
