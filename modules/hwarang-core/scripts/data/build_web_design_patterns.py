"""화랑 AI 웹 디자인 패턴 학습 데이터

최신 웹 디자인 트렌드, 레이아웃, 인터랙션, 마이크로인터랙션 등.

사용법:
    python scripts/data/build_web_design_patterns.py \
        --output data/sft/web_design_patterns.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 UI/UX 디자이너 겸 프론트엔드 개발자 수준의 디자인 어시스턴트입니다.
설명은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 최신 웹 디자인 트렌드 2025 ═══
    m("2025년 최신 웹 디자인 트렌드 알려줘",
'''2025년 웹 디자인 핵심 트렌드입니다.

**1. AI 통합 인터페이스**
```tsx
// AI 채팅 통합 UI - 모든 서비스에 AI 어시스턴트 삽입
function AIAssistantWidget() {
  return (
    <div className="fixed bottom-6 right-6 z-50">
      {/* 플로팅 버튼 */}
      <button
        onClick={() => setOpen(!open)}
        className="h-14 w-14 rounded-full bg-gradient-to-br from-blue-600 to-purple-600 shadow-lg shadow-blue-500/30 flex items-center justify-center text-white transition-transform hover:scale-110 active:scale-95"
      >
        <SparklesIcon className="h-6 w-6" />
      </button>

      {/* AI 채팅 패널 */}
      {open && (
        <div className="absolute bottom-16 right-0 w-96 rounded-2xl border bg-white shadow-2xl dark:bg-gray-900">
          <div className="border-b p-4">
            <h3 className="font-semibold">화랑 AI 어시스턴트</h3>
            <p className="text-sm text-gray-500">무엇을 도와드릴까요?</p>
          </div>
          <div className="h-96 overflow-y-auto p-4">
            {/* 메시지 목록 */}
          </div>
          <div className="border-t p-3">
            <input
              placeholder="메시지를 입력하세요..."
              className="w-full rounded-lg border px-3 py-2"
            />
          </div>
        </div>
      )}
    </div>
  );
}
```

**2. Bento Grid 레이아웃**
```tsx
// Apple 스타일 벤토 그리드
function BentoGrid() {
  return (
    <div className="grid grid-cols-4 grid-rows-3 gap-4 p-6">
      {/* 대형 카드 (2x2) */}
      <div className="col-span-2 row-span-2 rounded-3xl bg-gradient-to-br from-blue-500 to-purple-600 p-8 text-white">
        <h2 className="text-3xl font-bold">주요 기능</h2>
        <p className="mt-4 text-lg text-white/80">AI 기반 코드 생성</p>
        <img src="/feature-hero.png" className="mt-8 rounded-2xl" />
      </div>

      {/* 중형 카드 (2x1) */}
      <div className="col-span-2 rounded-3xl bg-gray-100 p-6 dark:bg-gray-800">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-green-100 p-2"><ChartIcon /></div>
          <div>
            <p className="text-3xl font-bold">10배</p>
            <p className="text-gray-500">생산성 향상</p>
          </div>
        </div>
      </div>

      {/* 소형 카드 (1x1) */}
      <div className="rounded-3xl bg-orange-50 p-6 dark:bg-orange-900/20">
        <LightningIcon className="h-8 w-8 text-orange-500" />
        <p className="mt-3 font-semibold">실시간 협업</p>
      </div>

      {/* 소형 카드 */}
      <div className="rounded-3xl bg-purple-50 p-6 dark:bg-purple-900/20">
        <ShieldIcon className="h-8 w-8 text-purple-500" />
        <p className="mt-3 font-semibold">보안 내장</p>
      </div>

      {/* 와이드 카드 (2x1) */}
      <div className="col-span-2 rounded-3xl bg-gray-900 p-6 text-white">
        <pre className="font-mono text-sm text-green-400">
          <code>{'> 화랑 AI가 코드를 생성하고 있습니다...'}</code>
        </pre>
      </div>
    </div>
  );
}
```

**3. 글래스모피즘 (Glassmorphism)**
```tsx
function GlassCard() {
  return (
    <div className="relative">
      {/* 배경 블러 효과 */}
      <div className="absolute inset-0 rounded-2xl bg-white/10 backdrop-blur-xl border border-white/20 shadow-xl" />
      <div className="relative p-6">
        <h3 className="text-xl font-bold text-white">투명 카드</h3>
        <p className="mt-2 text-white/70">글래스모피즘 효과</p>
      </div>
    </div>
  );
}

/* CSS 글래스모피즘 */
.glass {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 16px;
}
```

**4. 스크롤 기반 애니메이션**
```tsx
// CSS scroll-driven animation (네이티브!)
function ScrollAnimation() {
  return (
    <>
      <style>{`
        @keyframes fadeSlideUp {
          from { opacity: 0; transform: translateY(40px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .scroll-animate {
          animation: fadeSlideUp linear both;
          animation-timeline: view();
          animation-range: entry 0% entry 40%;
        }

        /* 프로그레스 바 */
        .scroll-progress {
          position: fixed;
          top: 0;
          left: 0;
          height: 3px;
          background: linear-gradient(to right, #3b82f6, #8b5cf6);
          transform-origin: left;
          animation: scaleX linear;
          animation-timeline: scroll();
        }

        @keyframes scaleX {
          from { transform: scaleX(0); }
          to { transform: scaleX(1); }
        }
      `}</style>

      <div className="scroll-progress" />
      {sections.map((section) => (
        <div key={section.id} className="scroll-animate">
          {section.content}
        </div>
      ))}
    </>
  );
}
```

**5. 뉴모피즘 (Neumorphism) - 소프트 UI**
```css
.neumorphic {
  background: #e0e5ec;
  border-radius: 20px;
  box-shadow:
    8px 8px 16px #b8bec7,
    -8px -8px 16px #ffffff;
}

.neumorphic-inset {
  box-shadow:
    inset 4px 4px 8px #b8bec7,
    inset -4px -4px 8px #ffffff;
}

/* 다크모드 뉴모피즘 */
.dark .neumorphic {
  background: #1a1a2e;
  box-shadow:
    8px 8px 16px #0f0f1a,
    -8px -8px 16px #252542;
}
```

2025 핵심 트렌드:
1. **AI 통합 UI** - 모든 앱에 AI 어시스턴트
2. **Bento Grid** - 다양한 크기의 카드 격자
3. **CSS scroll-driven** - JS 없이 스크롤 애니메이션
4. **3D & 모션** - 인터랙티브 3D 요소
5. **다크모드 기본** - 시스템 설정 자동 감지
6. **마이크로인터랙션** - 세밀한 피드백 애니메이션'''),

    # ═══ 마이크로인터랙션 ═══
    m("마이크로인터랙션 디자인 패턴 코드로 알려줘",
'''사용자 경험을 높이는 마이크로인터랙션 패턴입니다.

```tsx
// ═══ 1. 버튼 피드백 ═══
"use client";
import { motion, AnimatePresence } from "framer-motion";

function InteractiveButton({ children, onClick }: ButtonProps) {
  const [state, setState] = useState<"idle" | "loading" | "success" | "error">("idle");

  const handleClick = async () => {
    setState("loading");
    try {
      await onClick();
      setState("success");
      setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2000);
    }
  };

  return (
    <motion.button
      onClick={handleClick}
      disabled={state === "loading"}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      className={cn(
        "relative rounded-xl px-6 py-3 font-semibold text-white transition-colors",
        state === "idle" && "bg-blue-600 hover:bg-blue-700",
        state === "loading" && "bg-blue-400 cursor-wait",
        state === "success" && "bg-green-500",
        state === "error" && "bg-red-500",
      )}
    >
      <AnimatePresence mode="wait">
        {state === "idle" && (
          <motion.span key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            {children}
          </motion.span>
        )}
        {state === "loading" && (
          <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <Spinner className="h-5 w-5 animate-spin" />
          </motion.div>
        )}
        {state === "success" && (
          <motion.div key="success" initial={{ scale: 0 }} animate={{ scale: 1 }}>
            <CheckIcon className="h-5 w-5" />
          </motion.div>
        )}
        {state === "error" && (
          <motion.span key="error" initial={{ x: -10 }} animate={{ x: [0, -5, 5, -5, 5, 0] }}>
            다시 시도
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  );
}

// ═══ 2. 좋아요 애니메이션 ═══
function LikeButton() {
  const [liked, setLiked] = useState(false);
  const [count, setCount] = useState(42);

  return (
    <button
      onClick={() => {
        setLiked(!liked);
        setCount((c) => (liked ? c - 1 : c + 1));
      }}
      className="flex items-center gap-2"
    >
      <motion.div
        animate={liked ? {
          scale: [1, 1.3, 0.9, 1.1, 1],
          rotate: [0, -15, 15, -5, 0],
        } : { scale: 1 }}
        transition={{ duration: 0.4 }}
      >
        <HeartIcon
          className={cn(
            "h-6 w-6 transition-colors",
            liked ? "fill-red-500 text-red-500" : "text-gray-400"
          )}
        />
      </motion.div>

      {/* 숫자 롤링 애니메이션 */}
      <AnimatePresence mode="wait">
        <motion.span
          key={count}
          initial={{ y: liked ? 10 : -10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: liked ? -10 : 10, opacity: 0 }}
          className="text-sm font-medium"
        >
          {count}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}

// ═══ 3. 토글 스위치 ═══
function AnimatedToggle({ checked, onChange }: ToggleProps) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-7 w-12 rounded-full transition-colors duration-200",
        checked ? "bg-blue-600" : "bg-gray-300"
      )}
    >
      <motion.div
        className="absolute top-0.5 h-6 w-6 rounded-full bg-white shadow-md"
        animate={{ x: checked ? 22 : 2 }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
      />
    </button>
  );
}

// ═══ 4. 숫자 카운트업 ═══
function AnimatedCounter({ value }: { value: number }) {
  const [displayed, setDisplayed] = useState(0);

  useEffect(() => {
    const duration = 1000;
    const start = displayed;
    const diff = value - start;
    const startTime = Date.now();

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // 이징 함수 (easeOutExpo)
      const eased = 1 - Math.pow(2, -10 * progress);
      setDisplayed(Math.floor(start + diff * eased));

      if (progress < 1) requestAnimationFrame(animate);
    };

    requestAnimationFrame(animate);
  }, [value]);

  return (
    <span className="tabular-nums text-3xl font-bold">
      {displayed.toLocaleString()}
    </span>
  );
}

// ═══ 5. 입력 필드 피드백 ═══
function FloatingLabelInput({ label, error, ...props }: InputProps) {
  const [focused, setFocused] = useState(false);
  const hasValue = !!props.value;

  return (
    <div className="relative">
      <input
        {...props}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className={cn(
          "peer w-full rounded-lg border-2 bg-transparent px-4 pb-2 pt-5 outline-none transition-colors",
          focused && !error && "border-blue-500",
          error && "border-red-500",
          !focused && !error && "border-gray-300",
        )}
      />
      {/* 플로팅 라벨 */}
      <label
        className={cn(
          "absolute left-4 transition-all pointer-events-none",
          focused || hasValue
            ? "top-1 text-xs font-medium"
            : "top-3.5 text-base text-gray-500",
          focused && !error && "text-blue-500",
          error && "text-red-500",
        )}
      >
        {label}
      </label>
      {/* 에러 메시지 */}
      <AnimatePresence>
        {error && (
          <motion.p
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            className="mt-1 text-sm text-red-500"
          >
            {error}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}

// ═══ 6. 페이지 전환 ═══
// app/template.tsx (Next.js)
function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3, ease: "easeInOut" }}
    >
      {children}
    </motion.div>
  );
}
```

마이크로인터랙션 원칙:
1. **즉각적 피드백**: 클릭, 호버 시 바로 반응
2. **상태 전환**: 로딩→성공→완료 명확한 표시
3. **자연스러운 모션**: spring 물리 기반 애니메이션
4. **과하지 않게**: 0.2-0.4초 내 완료
5. **의미 있는 움직임**: 방향성 있는 전환 (위→아래, 좌→우)'''),

    # ═══ 다크모드 디자인 ═══
    m("다크모드 디자인 시스템 만드는 방법 알려줘",
'''체계적인 다크모드 디자인 시스템입니다.

```tsx
// ═══ 1. CSS 변수 기반 테마 시스템 ═══
// globals.css

/* 시맨틱 색상 토큰 */
:root {
  /* 배경 */
  --bg-primary: 255 255 255;      /* #ffffff */
  --bg-secondary: 249 250 251;    /* #f9fafb */
  --bg-tertiary: 243 244 246;     /* #f3f4f6 */
  --bg-inverse: 17 24 39;         /* #111827 */

  /* 텍스트 */
  --text-primary: 17 24 39;       /* #111827 */
  --text-secondary: 107 114 128;  /* #6b7280 */
  --text-tertiary: 156 163 175;   /* #9ca3af */
  --text-inverse: 255 255 255;

  /* 테두리 */
  --border-default: 229 231 235;  /* #e5e7eb */
  --border-strong: 209 213 219;   /* #d1d5db */

  /* 브랜드 */
  --brand-primary: 59 130 246;
  --brand-hover: 37 99 235;

  /* 시맨틱 */
  --success: 16 185 129;
  --warning: 245 158 11;
  --error: 239 68 68;

  /* 그림자 */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.07);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1);

  /* 오버레이 */
  --overlay: rgba(0, 0, 0, 0.5);
}

.dark {
  --bg-primary: 17 24 39;         /* #111827 */
  --bg-secondary: 31 41 55;       /* #1f2937 */
  --bg-tertiary: 55 65 81;        /* #374151 */
  --bg-inverse: 255 255 255;

  --text-primary: 249 250 251;
  --text-secondary: 156 163 175;
  --text-tertiary: 107 114 128;
  --text-inverse: 17 24 39;

  --border-default: 55 65 81;
  --border-strong: 75 85 99;

  --brand-primary: 96 165 250;    /* 다크에서 더 밝게 */
  --brand-hover: 147 197 253;

  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.5);

  --overlay: rgba(0, 0, 0, 0.7);
}

// ═══ 2. Tailwind 설정 ═══
// tailwind.config.ts
const config = {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "rgb(var(--bg-primary) / <alpha-value>)",
          secondary: "rgb(var(--bg-secondary) / <alpha-value>)",
          tertiary: "rgb(var(--bg-tertiary) / <alpha-value>)",
        },
        text: {
          primary: "rgb(var(--text-primary) / <alpha-value>)",
          secondary: "rgb(var(--text-secondary) / <alpha-value>)",
        },
      },
    },
  },
};

// ═══ 3. 테마 전환 컴포넌트 ═══
"use client";
import { useTheme } from "next-themes";

function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="h-9 w-9" />;  // SSR 스켈레톤

  return (
    <button
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      className="rounded-lg p-2 hover:bg-bg-tertiary transition-colors"
      aria-label={`${resolvedTheme === "dark" ? "라이트" : "다크"} 모드로 전환`}
    >
      <motion.div
        animate={{ rotate: resolvedTheme === "dark" ? 180 : 0 }}
        transition={{ duration: 0.3 }}
      >
        {resolvedTheme === "dark" ? (
          <SunIcon className="h-5 w-5 text-yellow-400" />
        ) : (
          <MoonIcon className="h-5 w-5 text-gray-600" />
        )}
      </motion.div>
    </button>
  );
}

// ═══ 4. 3단계 테마 (시스템/라이트/다크) ═══
function ThemeSelector() {
  const { theme, setTheme } = useTheme();

  const options = [
    { value: "system", icon: <MonitorIcon />, label: "시스템" },
    { value: "light", icon: <SunIcon />, label: "라이트" },
    { value: "dark", icon: <MoonIcon />, label: "다크" },
  ];

  return (
    <div className="flex rounded-lg border p-1 gap-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => setTheme(opt.value)}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
            theme === opt.value
              ? "bg-bg-tertiary text-text-primary font-medium"
              : "text-text-secondary hover:text-text-primary"
          )}
        >
          {opt.icon}
          {opt.label}
        </button>
      ))}
    </div>
  );
}
```

다크모드 디자인 규칙:
1. **밝기만 반전** - 채도를 약간 낮추기 (눈 피로 감소)
2. **순수 검정 피하기** - `#111827` 사용 (`#000000` X)
3. **대비 유지** - 텍스트/배경 4.5:1 이상
4. **그림자 조정** - 다크에서는 더 진한 그림자
5. **이미지 밝기 조정** - `dark:brightness-90` 적용
6. **시스템 설정 존중** - `prefers-color-scheme` 기본'''),

    # ═══ 인터랙티브 폼 디자인 ═══
    m("인터랙티브 폼 UI 디자인 패턴 알려줘",
'''사용자 경험을 극대화하는 폼 디자인 패턴입니다.

```tsx
// ═══ 1. 스텝 폼 (Multi-Step Form) ═══
function StepForm() {
  const [step, setStep] = useState(1);
  const totalSteps = 4;

  return (
    <div className="mx-auto max-w-lg">
      {/* 프로그레스 */}
      <div className="mb-8 flex items-center justify-between">
        {Array.from({ length: totalSteps }).map((_, i) => (
          <Fragment key={i}>
            <div className={cn(
              "flex h-10 w-10 items-center justify-center rounded-full font-semibold transition-all",
              i + 1 <= step
                ? "bg-blue-600 text-white shadow-lg shadow-blue-500/30"
                : "bg-gray-200 text-gray-500 dark:bg-gray-700"
            )}>
              {i + 1 < step ? <CheckIcon className="h-5 w-5" /> : i + 1}
            </div>
            {i < totalSteps - 1 && (
              <div className={cn(
                "h-1 flex-1 mx-2 rounded transition-colors",
                i + 1 < step ? "bg-blue-600" : "bg-gray-200 dark:bg-gray-700"
              )} />
            )}
          </Fragment>
        ))}
      </div>

      {/* 스텝별 폼 */}
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
        >
          {step === 1 && <PersonalInfoStep />}
          {step === 2 && <AccountStep />}
          {step === 3 && <PreferencesStep />}
          {step === 4 && <ReviewStep />}
        </motion.div>
      </AnimatePresence>

      {/* 네비게이션 */}
      <div className="mt-8 flex justify-between">
        <button
          onClick={() => setStep(step - 1)}
          disabled={step === 1}
          className="rounded-lg border px-6 py-2 disabled:opacity-50"
        >
          이전
        </button>
        <button
          onClick={() => step < totalSteps ? setStep(step + 1) : submit()}
          className="rounded-lg bg-blue-600 px-6 py-2 text-white"
        >
          {step === totalSteps ? "완료" : "다음"}
        </button>
      </div>
    </div>
  );
}

// ═══ 2. 인라인 유효성 검사 ═══
function InlineValidation() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "checking" | "valid" | "invalid">("idle");

  const debouncedCheck = useDebounce(email, 500);

  useEffect(() => {
    if (!debouncedCheck) { setStatus("idle"); return; }
    setStatus("checking");

    checkEmailAvailable(debouncedCheck).then((available) => {
      setStatus(available ? "valid" : "invalid");
    });
  }, [debouncedCheck]);

  return (
    <div className="relative">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className={cn(
          "w-full rounded-lg border-2 px-4 py-3 pr-10 transition-colors",
          status === "valid" && "border-green-500",
          status === "invalid" && "border-red-500",
        )}
        placeholder="이메일"
      />
      {/* 상태 아이콘 */}
      <div className="absolute right-3 top-3.5">
        {status === "checking" && <Spinner className="h-5 w-5 animate-spin text-blue-500" />}
        {status === "valid" && <CheckCircle className="h-5 w-5 text-green-500" />}
        {status === "invalid" && <XCircle className="h-5 w-5 text-red-500" />}
      </div>
      {status === "invalid" && (
        <p className="mt-1 text-sm text-red-500">이미 사용 중인 이메일입니다</p>
      )}
    </div>
  );
}

// ═══ 3. 비밀번호 강도 표시기 ═══
function PasswordStrength({ password }: { password: string }) {
  const strength = useMemo(() => {
    let score = 0;
    if (password.length >= 8) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;
    if (password.length >= 12) score++;
    return score;
  }, [password]);

  const levels = ["매우 약함", "약함", "보통", "강함", "매우 강함"];
  const colors = ["bg-red-500", "bg-orange-500", "bg-yellow-500", "bg-green-500", "bg-emerald-500"];

  if (!password) return null;

  return (
    <div className="mt-2 space-y-1">
      <div className="flex gap-1">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-colors",
              i < strength ? colors[strength - 1] : "bg-gray-200 dark:bg-gray-700"
            )}
          />
        ))}
      </div>
      <p className={cn(
        "text-xs",
        strength <= 1 && "text-red-500",
        strength === 2 && "text-yellow-500",
        strength >= 3 && "text-green-500",
      )}>
        {levels[strength - 1] || ""}
      </p>
    </div>
  );
}

// ═══ 4. 태그 입력 ═══
function TagInput({ value, onChange, suggestions }: TagInputProps) {
  const [input, setInput] = useState("");

  const addTag = (tag: string) => {
    if (tag && !value.includes(tag)) {
      onChange([...value, tag]);
    }
    setInput("");
  };

  const removeTag = (tag: string) => {
    onChange(value.filter((t) => t !== tag));
  };

  return (
    <div className="rounded-lg border-2 p-2 focus-within:border-blue-500 transition-colors">
      <div className="flex flex-wrap gap-1.5">
        {value.map((tag) => (
          <span
            key={tag}
            className="flex items-center gap-1 rounded-md bg-blue-100 px-2 py-0.5 text-sm text-blue-700 dark:bg-blue-900/50 dark:text-blue-300"
          >
            {tag}
            <button onClick={() => removeTag(tag)} className="hover:text-red-500">
              <XIcon className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); addTag(input); }
            if (e.key === "Backspace" && !input) removeTag(value[value.length - 1]);
          }}
          placeholder={value.length === 0 ? "태그 입력 후 Enter" : ""}
          className="flex-1 min-w-[100px] bg-transparent outline-none text-sm"
        />
      </div>
    </div>
  );
}
```

폼 디자인 핵심:
1. **실시간 유효성 검사** - 제출 전에 피드백
2. **명확한 에러 메시지** - 어떻게 수정할지 안내
3. **진행률 표시** - 멀티스텝 폼에 프로그레스
4. **키보드 지원** - Enter로 태그 추가, Tab으로 이동
5. **자동 포커스** - 다음 입력 필드로 자동 이동'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/web_design_patterns.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 웹 디자인 패턴 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  웹 디자인 패턴: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
