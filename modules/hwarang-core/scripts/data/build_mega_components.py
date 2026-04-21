"""화랑 AI React 컴포넌트 라이브러리 추가 학습 데이터"""
import json, os, logging, argparse
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
프로젝트 요청 시 폴더 구조와 각 파일의 전체 코드를 작성합니다.
실무에서 바로 사용할 수 있는 프로덕션 수준의 코드를 생성합니다.
설명은 한국어로, 코드는 완전한 형태로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 1. Tabs + Accordion + Collapse ═══
    m("React로 Tabs + Accordion + Collapse 컴포넌트 만들어줘 전체 코드로",
'''Tabs, Accordion, Collapse 컴포넌트를 만들어 드릴게요. 제어/비제어 모드, 키보드 내비게이션, 부드러운 높이 애니메이션을 모두 지원합니다.

## 폴더 구조

```
src/
├── components/
│   ├── Tabs/
│   │   ├── Tabs.tsx
│   │   ├── Tabs.css
│   │   └── index.ts
│   ├── Accordion/
│   │   ├── Accordion.tsx
│   │   ├── Accordion.css
│   │   └── index.ts
│   ├── Collapse/
│   │   ├── Collapse.tsx
│   │   ├── Collapse.css
│   │   └── index.ts
│   └── index.ts
├── hooks/
│   └── useControllable.ts
├── App.tsx
└── index.tsx
```

### hooks/useControllable.ts
제어/비제어 모드를 통합하는 커스텀 훅입니다.

```tsx
import { useState, useCallback, useRef } from "react";

export function useControllable<T>(
  controlledValue: T | undefined,
  defaultValue: T,
  onChange?: (value: T) => void
) {
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const isControlled = controlledValue !== undefined;
  const value = isControlled ? controlledValue : uncontrolled;
  const prevRef = useRef(value);

  const setValue = useCallback(
    (next: T | ((prev: T) => T)) => {
      const resolved = typeof next === "function"
        ? (next as (prev: T) => T)(prevRef.current)
        : next;
      prevRef.current = resolved;
      if (!isControlled) setUncontrolled(resolved);
      onChange?.(resolved);
    },
    [isControlled, onChange]
  );

  return [value, setValue] as const;
}
```

### components/Tabs/Tabs.tsx
키보드 좌우 화살표로 탭 전환이 가능합니다.

```tsx
import React, { useRef, KeyboardEvent } from "react";
import { useControllable } from "../../hooks/useControllable";
import "./Tabs.css";

interface TabItem {
  key: string;
  label: React.ReactNode;
  content: React.ReactNode;
  disabled?: boolean;
}

interface TabsProps {
  items: TabItem[];
  activeKey?: string;
  defaultActiveKey?: string;
  onChange?: (key: string) => void;
  variant?: "line" | "card";
}

export function Tabs({ items, activeKey, defaultActiveKey, onChange, variant = "line" }: TabsProps) {
  const first = items.find((t) => !t.disabled)?.key ?? items[0]?.key ?? "";
  const [current, setCurrent] = useControllable(activeKey, defaultActiveKey ?? first, onChange);
  const tabRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  const enabledItems = items.filter((t) => !t.disabled);

  const handleKeyDown = (e: KeyboardEvent) => {
    const idx = enabledItems.findIndex((t) => t.key === current);
    let nextIdx = idx;
    if (e.key === "ArrowRight") nextIdx = (idx + 1) % enabledItems.length;
    else if (e.key === "ArrowLeft") nextIdx = (idx - 1 + enabledItems.length) % enabledItems.length;
    else if (e.key === "Home") nextIdx = 0;
    else if (e.key === "End") nextIdx = enabledItems.length - 1;
    else return;
    e.preventDefault();
    const nextKey = enabledItems[nextIdx].key;
    setCurrent(nextKey);
    tabRefs.current.get(nextKey)?.focus();
  };

  const active = items.find((t) => t.key === current);

  return (
    <div className={`tabs tabs--${variant}`}>
      <div className="tabs__list" role="tablist" onKeyDown={handleKeyDown}>
        {items.map((tab) => (
          <button
            key={tab.key}
            ref={(el) => { if (el) tabRefs.current.set(tab.key, el); }}
            role="tab"
            aria-selected={tab.key === current}
            aria-disabled={tab.disabled}
            tabIndex={tab.key === current ? 0 : -1}
            className={`tabs__tab ${tab.key === current ? "tabs__tab--active" : ""}`}
            disabled={tab.disabled}
            onClick={() => setCurrent(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="tabs__panel" role="tabpanel">
        {active?.content}
      </div>
    </div>
  );
}
```

### components/Tabs/Tabs.css

```css
.tabs { width: 100%; }
.tabs__list { display: flex; gap: 0; border-bottom: 2px solid #e2e8f0; }
.tabs__tab {
  padding: 10px 20px; border: none; background: none; cursor: pointer;
  font-size: 14px; color: #64748b; position: relative; transition: color 0.2s;
}
.tabs__tab:hover:not(:disabled) { color: #1e293b; }
.tabs__tab--active { color: #3b82f6; font-weight: 600; }
.tabs__tab--active::after {
  content: ""; position: absolute; bottom: -2px; left: 0; right: 0;
  height: 2px; background: #3b82f6;
}
.tabs__tab:disabled { opacity: 0.4; cursor: not-allowed; }
.tabs__panel { padding: 16px 0; }
.tabs--card .tabs__list { border-bottom: none; gap: 4px; }
.tabs--card .tabs__tab {
  border: 1px solid #e2e8f0; border-radius: 8px 8px 0 0; background: #f8fafc;
}
.tabs--card .tabs__tab--active { background: #fff; border-bottom-color: #fff; }
```

### components/Tabs/index.ts

```ts
export { Tabs } from "./Tabs";
```

### components/Accordion/Accordion.tsx
단일/다중 확장 모드를 지원합니다. Collapse 컴포넌트를 내부적으로 사용합니다.

```tsx
import React, { useCallback } from "react";
import { useControllable } from "../../hooks/useControllable";
import { Collapse } from "../Collapse";
import "./Accordion.css";

interface AccordionItem {
  key: string;
  title: React.ReactNode;
  content: React.ReactNode;
}

interface AccordionProps {
  items: AccordionItem[];
  activeKeys?: string[];
  defaultActiveKeys?: string[];
  onChange?: (keys: string[]) => void;
  multiple?: boolean;
}

export function Accordion({
  items, activeKeys, defaultActiveKeys, onChange, multiple = false,
}: AccordionProps) {
  const [opened, setOpened] = useControllable(activeKeys, defaultActiveKeys ?? [], onChange);

  const toggle = useCallback(
    (key: string) => {
      setOpened((prev) => {
        if (prev.includes(key)) return prev.filter((k) => k !== key);
        return multiple ? [...prev, key] : [key];
      });
    },
    [multiple, setOpened]
  );

  return (
    <div className="accordion">
      {items.map((item) => {
        const isOpen = opened.includes(item.key);
        return (
          <div key={item.key} className="accordion__item">
            <button
              className={`accordion__header ${isOpen ? "accordion__header--open" : ""}`}
              onClick={() => toggle(item.key)}
              aria-expanded={isOpen}
            >
              <span>{item.title}</span>
              <span className={`accordion__icon ${isOpen ? "accordion__icon--open" : ""}`}>
                &#9662;
              </span>
            </button>
            <Collapse open={isOpen}>
              <div className="accordion__body">{item.content}</div>
            </Collapse>
          </div>
        );
      })}
    </div>
  );
}
```

### components/Accordion/Accordion.css

```css
.accordion { border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
.accordion__item + .accordion__item { border-top: 1px solid #e2e8f0; }
.accordion__header {
  width: 100%; display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border: none; background: #fff; cursor: pointer;
  font-size: 15px; font-weight: 500; text-align: left; transition: background 0.2s;
}
.accordion__header:hover { background: #f8fafc; }
.accordion__header--open { background: #f1f5f9; }
.accordion__icon { transition: transform 0.25s ease; font-size: 12px; }
.accordion__icon--open { transform: rotate(180deg); }
.accordion__body { padding: 14px 18px; color: #475569; line-height: 1.6; }
```

### components/Accordion/index.ts

```ts
export { Accordion } from "./Accordion";
```

### components/Collapse/Collapse.tsx
useRef로 자식 높이를 측정해 부드러운 애니메이션을 구현합니다.

```tsx
import React, { useRef, useEffect, useState } from "react";
import "./Collapse.css";

interface CollapseProps {
  open: boolean;
  duration?: number;
  children: React.ReactNode;
}

export function Collapse({ open, duration = 250, children }: CollapseProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | "auto">(open ? "auto" : 0);
  const [overflow, setOverflow] = useState(open ? "visible" : "hidden");
  const firstRender = useRef(true);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    const el = contentRef.current;
    if (!el) return;

    if (open) {
      const h = el.scrollHeight;
      setHeight(h);
      setOverflow("hidden");
      const timer = setTimeout(() => {
        setHeight("auto");
        setOverflow("visible");
      }, duration);
      return () => clearTimeout(timer);
    } else {
      const h = el.scrollHeight;
      setHeight(h);
      setOverflow("hidden");
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setHeight(0));
      });
    }
  }, [open, duration]);

  return (
    <div
      ref={contentRef}
      className="collapse"
      style={{
        height: typeof height === "number" ? `${height}px` : height,
        overflow,
        transitionDuration: `${duration}ms`,
      }}
    >
      {children}
    </div>
  );
}
```

### components/Collapse/Collapse.css

```css
.collapse {
  transition-property: height;
  transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
}
```

### components/Collapse/index.ts

```ts
export { Collapse } from "./Collapse";
```

모든 컴포넌트가 WAI-ARIA 패턴을 따르며, 키보드 내비게이션과 부드러운 애니메이션을 지원합니다.'''),

    # ═══ 2. DatePicker + TimePicker ═══
    m("React로 DatePicker + TimePicker 컴포넌트 만들어줘 전체 코드로",
'''DatePicker와 TimePicker 컴포넌트를 만들어 드릴게요. 캘린더 그리드, 월/연도 내비게이션, 날짜 범위 선택, 시간 드롭다운을 모두 지원합니다.

## 폴더 구조

```
src/
├── components/
│   ├── DatePicker/
│   │   ├── DatePicker.tsx
│   │   ├── Calendar.tsx
│   │   ├── DatePicker.css
│   │   └── index.ts
│   ├── TimePicker/
│   │   ├── TimePicker.tsx
│   │   ├── TimePicker.css
│   │   └── index.ts
│   └── index.ts
├── utils/
│   └── dateUtils.ts
├── App.tsx
└── index.tsx
```

### utils/dateUtils.ts
날짜 계산 유틸리티입니다.

```ts
export function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

export function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 1).getDay();
}

export function formatDate(date: Date, fmt: string = "yyyy-MM-dd"): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return fmt.replace("yyyy", String(y)).replace("MM", m).replace("dd", d);
}

export function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

export function isInRange(date: Date, start: Date | null, end: Date | null): boolean {
  if (!start || !end) return false;
  const t = date.getTime();
  return t >= start.getTime() && t <= end.getTime();
}

export function getCalendarGrid(year: number, month: number): (number | null)[][] {
  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const weeks: (number | null)[][] = [];
  let week: (number | null)[] = new Array(firstDay).fill(null);
  for (let d = 1; d <= daysInMonth; d++) {
    week.push(d);
    if (week.length === 7) {
      weeks.push(week);
      week = [];
    }
  }
  if (week.length > 0) {
    while (week.length < 7) week.push(null);
    weeks.push(week);
  }
  return weeks;
}

export const MONTH_NAMES = [
  "1월","2월","3월","4월","5월","6월",
  "7월","8월","9월","10월","11월","12월",
];

export const DAY_HEADERS = ["일","월","화","수","목","금","토"];
```

### components/DatePicker/Calendar.tsx
캘린더 그리드 UI입니다. 날짜 범위 선택 시 하이라이트를 표시합니다.

```tsx
import React from "react";
import { getCalendarGrid, isSameDay, isInRange, MONTH_NAMES, DAY_HEADERS } from "../../utils/dateUtils";

interface CalendarProps {
  year: number;
  month: number;
  selected: Date | null;
  rangeStart: Date | null;
  rangeEnd: Date | null;
  rangeMode: boolean;
  onSelect: (day: number) => void;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onPrevYear: () => void;
  onNextYear: () => void;
}

export function Calendar({
  year, month, selected, rangeStart, rangeEnd, rangeMode,
  onSelect, onPrevMonth, onNextMonth, onPrevYear, onNextYear,
}: CalendarProps) {
  const grid = getCalendarGrid(year, month);
  const today = new Date();

  const isSelected = (day: number) => {
    if (!selected) return false;
    return isSameDay(new Date(year, month, day), selected);
  };

  const isRangeHighlight = (day: number) => {
    if (!rangeMode) return false;
    return isInRange(new Date(year, month, day), rangeStart, rangeEnd);
  };

  const isToday = (day: number) =>
    isSameDay(new Date(year, month, day), today);

  return (
    <div className="calendar">
      <div className="calendar__nav">
        <button onClick={onPrevYear} title="이전 년도">&laquo;</button>
        <button onClick={onPrevMonth} title="이전 달">&lsaquo;</button>
        <span className="calendar__title">{year}년 {MONTH_NAMES[month]}</span>
        <button onClick={onNextMonth} title="다음 달">&rsaquo;</button>
        <button onClick={onNextYear} title="다음 년도">&raquo;</button>
      </div>
      <table className="calendar__grid">
        <thead>
          <tr>{DAY_HEADERS.map((d) => <th key={d}>{d}</th>)}</tr>
        </thead>
        <tbody>
          {grid.map((week, wi) => (
            <tr key={wi}>
              {week.map((day, di) => (
                <td key={di}>
                  {day && (
                    <button
                      className={[
                        "calendar__day",
                        isToday(day) ? "calendar__day--today" : "",
                        isSelected(day) ? "calendar__day--selected" : "",
                        isRangeHighlight(day) ? "calendar__day--range" : "",
                      ].join(" ")}
                      onClick={() => onSelect(day)}
                    >
                      {day}
                    </button>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### components/DatePicker/DatePicker.tsx
팝업 캘린더와 입력 필드를 연결합니다.

```tsx
import React, { useState, useRef, useEffect } from "react";
import { Calendar } from "./Calendar";
import { formatDate } from "../../utils/dateUtils";
import "./DatePicker.css";

interface DatePickerProps {
  value?: Date | null;
  onChange?: (date: Date | null) => void;
  format?: string;
  placeholder?: string;
  rangeMode?: boolean;
  onRangeChange?: (start: Date | null, end: Date | null) => void;
}

export function DatePicker({
  value, onChange, format = "yyyy-MM-dd", placeholder = "날짜 선택",
  rangeMode = false, onRangeChange,
}: DatePickerProps) {
  const [open, setOpen] = useState(false);
  const today = new Date();
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [selected, setSelected] = useState<Date | null>(value ?? null);
  const [rangeStart, setRangeStart] = useState<Date | null>(null);
  const [rangeEnd, setRangeEnd] = useState<Date | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSelect = (day: number) => {
    const date = new Date(viewYear, viewMonth, day);
    if (rangeMode) {
      if (!rangeStart || rangeEnd) {
        setRangeStart(date);
        setRangeEnd(null);
      } else {
        const [s, e] = date >= rangeStart ? [rangeStart, date] : [date, rangeStart];
        setRangeStart(s);
        setRangeEnd(e);
        onRangeChange?.(s, e);
      }
    } else {
      setSelected(date);
      onChange?.(date);
      setOpen(false);
    }
  };

  const displayValue = rangeMode
    ? (rangeStart && rangeEnd ? `${formatDate(rangeStart, format)} ~ ${formatDate(rangeEnd, format)}` : "")
    : (selected ? formatDate(selected, format) : "");

  return (
    <div className="datepicker" ref={wrapperRef}>
      <input
        className="datepicker__input"
        readOnly
        value={displayValue}
        placeholder={placeholder}
        onFocus={() => setOpen(true)}
      />
      {open && (
        <div className="datepicker__popup">
          <Calendar
            year={viewYear} month={viewMonth}
            selected={selected} rangeStart={rangeStart} rangeEnd={rangeEnd}
            rangeMode={rangeMode}
            onSelect={handleSelect}
            onPrevMonth={() => setViewMonth((m) => m === 0 ? (setViewYear((y) => y - 1), 11) : m - 1)}
            onNextMonth={() => setViewMonth((m) => m === 11 ? (setViewYear((y) => y + 1), 0) : m + 1)}
            onPrevYear={() => setViewYear((y) => y - 1)}
            onNextYear={() => setViewYear((y) => y + 1)}
          />
        </div>
      )}
    </div>
  );
}
```

### components/DatePicker/DatePicker.css

```css
.datepicker { position: relative; display: inline-block; }
.datepicker__input {
  padding: 10px 14px; border: 1px solid #d1d5db; border-radius: 8px;
  font-size: 14px; width: 260px; cursor: pointer; outline: none;
}
.datepicker__input:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,.15); }
.datepicker__popup {
  position: absolute; top: calc(100% + 6px); left: 0; z-index: 50;
  background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
  box-shadow: 0 10px 25px rgba(0,0,0,.1); padding: 12px;
}
.calendar__nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.calendar__nav button {
  border: none; background: none; cursor: pointer; font-size: 16px;
  padding: 4px 8px; border-radius: 4px; color: #64748b;
}
.calendar__nav button:hover { background: #f1f5f9; }
.calendar__title { font-weight: 600; font-size: 14px; }
.calendar__grid { width: 100%; border-collapse: collapse; }
.calendar__grid th { font-size: 12px; color: #94a3b8; padding: 6px; text-align: center; }
.calendar__grid td { padding: 2px; text-align: center; }
.calendar__day {
  width: 34px; height: 34px; border: none; background: none; border-radius: 50%;
  cursor: pointer; font-size: 13px; transition: all 0.15s;
}
.calendar__day:hover { background: #f1f5f9; }
.calendar__day--today { font-weight: 700; color: #3b82f6; }
.calendar__day--selected { background: #3b82f6; color: #fff; }
.calendar__day--range { background: #dbeafe; color: #1e40af; border-radius: 4px; }
```

### components/DatePicker/index.ts

```ts
export { DatePicker } from "./DatePicker";
```

### components/TimePicker/TimePicker.tsx
시간/분 드롭다운 선택기입니다.

```tsx
import React, { useState, useRef, useEffect } from "react";
import "./TimePicker.css";

interface TimePickerProps {
  value?: string;
  onChange?: (time: string) => void;
  use24Hour?: boolean;
}

export function TimePicker({ value, onChange, use24Hour = true }: TimePickerProps) {
  const [open, setOpen] = useState(false);
  const [hour, setHour] = useState(value ? parseInt(value.split(":")[0]) : 0);
  const [minute, setMinute] = useState(value ? parseInt(value.split(":")[1]) : 0);
  const wrapRef = useRef<HTMLDivElement>(null);

  const hours = Array.from({ length: use24Hour ? 24 : 12 }, (_, i) => (use24Hour ? i : i + 1));
  const minutes = Array.from({ length: 60 }, (_, i) => i);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSelect = (h: number, m: number) => {
    setHour(h);
    setMinute(m);
    const formatted = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
    onChange?.(formatted);
  };

  const display = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

  return (
    <div className="timepicker" ref={wrapRef}>
      <input className="timepicker__input" readOnly value={display} onFocus={() => setOpen(true)} />
      {open && (
        <div className="timepicker__popup">
          <div className="timepicker__columns">
            <div className="timepicker__col">
              <div className="timepicker__col-title">시</div>
              <div className="timepicker__scroll">
                {hours.map((h) => (
                  <button key={h}
                    className={`timepicker__cell ${h === hour ? "timepicker__cell--active" : ""}`}
                    onClick={() => handleSelect(h, minute)}
                  >{String(h).padStart(2, "0")}</button>
                ))}
              </div>
            </div>
            <div className="timepicker__col">
              <div className="timepicker__col-title">분</div>
              <div className="timepicker__scroll">
                {minutes.filter((m) => m % 5 === 0).map((m) => (
                  <button key={m}
                    className={`timepicker__cell ${m === minute ? "timepicker__cell--active" : ""}`}
                    onClick={() => handleSelect(hour, m)}
                  >{String(m).padStart(2, "0")}</button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

### components/TimePicker/TimePicker.css

```css
.timepicker { position: relative; display: inline-block; }
.timepicker__input {
  padding: 10px 14px; border: 1px solid #d1d5db; border-radius: 8px;
  font-size: 14px; width: 120px; cursor: pointer; text-align: center;
}
.timepicker__popup {
  position: absolute; top: calc(100% + 6px); left: 0; z-index: 50;
  background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
  box-shadow: 0 10px 25px rgba(0,0,0,.1); padding: 8px;
}
.timepicker__columns { display: flex; gap: 8px; }
.timepicker__col-title { font-size: 12px; color: #94a3b8; text-align: center; margin-bottom: 4px; }
.timepicker__scroll { max-height: 200px; overflow-y: auto; }
.timepicker__cell {
  display: block; width: 48px; padding: 6px 0; border: none; background: none;
  text-align: center; cursor: pointer; border-radius: 6px; font-size: 13px;
}
.timepicker__cell:hover { background: #f1f5f9; }
.timepicker__cell--active { background: #3b82f6; color: #fff; }
```

### components/TimePicker/index.ts

```ts
export { TimePicker } from "./TimePicker";
```

캘린더 그리드는 순수 계산으로 렌더링하며, 외부 라이브러리 없이 날짜 범위 선택까지 지원합니다.'''),

    # ═══ 3. Drag and Drop 칸반 보드 ═══
    m("React로 Drag and Drop 칸반 보드 컴포넌트 만들어줘 전체 코드로",
'''Drag and Drop 칸반 보드를 만들어 드릴게요. 네이티브 Drag API를 사용하고 카드 추가/편집/삭제, 컬럼 간 이동을 지원합니다.

## 폴더 구조

```
src/
├── components/
│   ├── KanbanBoard/
│   │   ├── KanbanBoard.tsx
│   │   ├── KanbanColumn.tsx
│   │   ├── KanbanCard.tsx
│   │   ├── AddCardForm.tsx
│   │   ├── KanbanBoard.css
│   │   └── index.ts
│   └── index.ts
├── types/
│   └── kanban.ts
├── App.tsx
└── index.tsx
```

### types/kanban.ts

```ts
export interface Card {
  id: string;
  title: string;
  description: string;
  color: string;
  createdAt: number;
}

export interface Column {
  id: string;
  title: string;
  cards: Card[];
}

export type ColumnId = "todo" | "inprogress" | "done";
```

### components/KanbanBoard/KanbanBoard.tsx
전체 보드 상태 관리 및 드래그 앤 드롭 핸들링입니다.

```tsx
import React, { useState, useCallback } from "react";
import { KanbanColumn } from "./KanbanColumn";
import { Column, Card } from "../../types/kanban";
import "./KanbanBoard.css";

const INITIAL_COLUMNS: Column[] = [
  { id: "todo", title: "📋 할 일", cards: [
    { id: "c1", title: "프로젝트 기획", description: "요구사항 정리", color: "#fef3c7", createdAt: Date.now() },
    { id: "c2", title: "디자인 시안", description: "Figma 작업", color: "#dbeafe", createdAt: Date.now() },
  ]},
  { id: "inprogress", title: "🔧 진행 중", cards: [
    { id: "c3", title: "API 개발", description: "REST 엔드포인트 구현", color: "#dcfce7", createdAt: Date.now() },
  ]},
  { id: "done", title: "✅ 완료", cards: [] },
];

let cardIdCounter = 4;

export function KanbanBoard() {
  const [columns, setColumns] = useState<Column[]>(INITIAL_COLUMNS);
  const [dragItem, setDragItem] = useState<{ cardId: string; fromCol: string } | null>(null);

  const handleDragStart = useCallback((cardId: string, fromCol: string) => {
    setDragItem({ cardId, fromCol });
  }, []);

  const handleDrop = useCallback((toColId: string) => {
    if (!dragItem) return;
    const { cardId, fromCol } = dragItem;
    if (fromCol === toColId) return;

    setColumns((prev) => {
      const next = prev.map((col) => ({ ...col, cards: [...col.cards] }));
      const srcCol = next.find((c) => c.id === fromCol)!;
      const dstCol = next.find((c) => c.id === toColId)!;
      const cardIdx = srcCol.cards.findIndex((c) => c.id === cardId);
      if (cardIdx === -1) return prev;
      const [card] = srcCol.cards.splice(cardIdx, 1);
      dstCol.cards.push(card);
      return next;
    });
    setDragItem(null);
  }, [dragItem]);

  const addCard = useCallback((colId: string, title: string, description: string) => {
    const newCard: Card = {
      id: `c${cardIdCounter++}`,
      title, description,
      color: ["#fef3c7", "#dbeafe", "#dcfce7", "#fce7f3", "#e0e7ff"][Math.floor(Math.random() * 5)],
      createdAt: Date.now(),
    };
    setColumns((prev) =>
      prev.map((col) => col.id === colId ? { ...col, cards: [...col.cards, newCard] } : col)
    );
  }, []);

  const deleteCard = useCallback((colId: string, cardId: string) => {
    setColumns((prev) =>
      prev.map((col) => col.id === colId ? { ...col, cards: col.cards.filter((c) => c.id !== cardId) } : col)
    );
  }, []);

  const editCard = useCallback((colId: string, cardId: string, title: string, description: string) => {
    setColumns((prev) =>
      prev.map((col) => col.id === colId ? {
        ...col,
        cards: col.cards.map((c) => c.id === cardId ? { ...c, title, description } : c),
      } : col)
    );
  }, []);

  return (
    <div className="kanban">
      <h2 className="kanban__title">칸반 보드</h2>
      <div className="kanban__board">
        {columns.map((col) => (
          <KanbanColumn
            key={col.id} column={col}
            onDragStart={handleDragStart}
            onDrop={() => handleDrop(col.id)}
            onAddCard={(t, d) => addCard(col.id, t, d)}
            onDeleteCard={(cid) => deleteCard(col.id, cid)}
            onEditCard={(cid, t, d) => editCard(col.id, cid, t, d)}
          />
        ))}
      </div>
    </div>
  );
}
```

### components/KanbanBoard/KanbanColumn.tsx
드롭 존과 카드 목록 렌더링을 담당합니다.

```tsx
import React, { useState, DragEvent } from "react";
import { KanbanCard } from "./KanbanCard";
import { AddCardForm } from "./AddCardForm";
import { Column } from "../../types/kanban";

interface Props {
  column: Column;
  onDragStart: (cardId: string, colId: string) => void;
  onDrop: () => void;
  onAddCard: (title: string, desc: string) => void;
  onDeleteCard: (cardId: string) => void;
  onEditCard: (cardId: string, title: string, desc: string) => void;
}

export function KanbanColumn({ column, onDragStart, onDrop, onAddCard, onDeleteCard, onEditCard }: Props) {
  const [isOver, setIsOver] = useState(false);

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsOver(true);
  };

  return (
    <div
      className={`kanban__column ${isOver ? "kanban__column--over" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={() => setIsOver(false)}
      onDrop={(e) => { e.preventDefault(); setIsOver(false); onDrop(); }}
    >
      <div className="kanban__column-header">
        <span>{column.title}</span>
        <span className="kanban__count">{column.cards.length}</span>
      </div>
      <div className="kanban__cards">
        {column.cards.map((card) => (
          <KanbanCard key={card.id} card={card} columnId={column.id}
            onDragStart={onDragStart} onDelete={onDeleteCard} onEdit={onEditCard} />
        ))}
      </div>
      <AddCardForm onAdd={onAddCard} />
    </div>
  );
}
```

### components/KanbanBoard/KanbanCard.tsx
개별 카드 렌더링, 드래그 시작, 편집/삭제 기능입니다.

```tsx
import React, { useState, DragEvent } from "react";
import { Card } from "../../types/kanban";

interface Props {
  card: Card;
  columnId: string;
  onDragStart: (cardId: string, colId: string) => void;
  onDelete: (cardId: string) => void;
  onEdit: (cardId: string, title: string, desc: string) => void;
}

export function KanbanCard({ card, columnId, onDragStart, onDelete, onEdit }: Props) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(card.title);
  const [desc, setDesc] = useState(card.description);

  const handleDragStart = (e: DragEvent) => {
    e.dataTransfer.effectAllowed = "move";
    onDragStart(card.id, columnId);
  };

  const handleSave = () => {
    if (title.trim()) onEdit(card.id, title, desc);
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="kanban__card" style={{ background: card.color }}>
        <input className="kanban__edit-input" value={title}
          onChange={(e) => setTitle(e.target.value)} autoFocus />
        <textarea className="kanban__edit-textarea" value={desc}
          onChange={(e) => setDesc(e.target.value)} rows={2} />
        <div className="kanban__edit-actions">
          <button className="kanban__btn kanban__btn--save" onClick={handleSave}>저장</button>
          <button className="kanban__btn kanban__btn--cancel" onClick={() => setEditing(false)}>취소</button>
        </div>
      </div>
    );
  }

  return (
    <div className="kanban__card" draggable onDragStart={handleDragStart}
      style={{ background: card.color }}>
      <div className="kanban__card-header">
        <strong>{card.title}</strong>
        <div className="kanban__card-actions">
          <button onClick={() => setEditing(true)} title="편집">✏️</button>
          <button onClick={() => onDelete(card.id)} title="삭제">🗑️</button>
        </div>
      </div>
      {card.description && <p className="kanban__card-desc">{card.description}</p>}
    </div>
  );
}
```

### components/KanbanBoard/AddCardForm.tsx

```tsx
import React, { useState } from "react";

interface Props { onAdd: (title: string, desc: string) => void; }

export function AddCardForm({ onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");

  const handleSubmit = () => {
    if (!title.trim()) return;
    onAdd(title.trim(), desc.trim());
    setTitle(""); setDesc(""); setOpen(false);
  };

  if (!open) return (
    <button className="kanban__add-btn" onClick={() => setOpen(true)}>+ 카드 추가</button>
  );

  return (
    <div className="kanban__add-form">
      <input placeholder="제목" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
      <textarea placeholder="설명 (선택)" value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} />
      <div className="kanban__edit-actions">
        <button className="kanban__btn kanban__btn--save" onClick={handleSubmit}>추가</button>
        <button className="kanban__btn kanban__btn--cancel" onClick={() => setOpen(false)}>취소</button>
      </div>
    </div>
  );
}
```

### components/KanbanBoard/KanbanBoard.css

```css
.kanban { padding: 24px; }
.kanban__title { font-size: 22px; margin-bottom: 20px; }
.kanban__board { display: flex; gap: 20px; overflow-x: auto; padding-bottom: 12px; }
.kanban__column {
  min-width: 300px; background: #f8fafc; border-radius: 12px;
  padding: 16px; border: 2px solid transparent; transition: border-color 0.2s;
}
.kanban__column--over { border-color: #3b82f6; background: #eff6ff; }
.kanban__column-header { display: flex; justify-content: space-between; margin-bottom: 12px; font-weight: 600; }
.kanban__count { background: #e2e8f0; border-radius: 10px; padding: 2px 10px; font-size: 12px; }
.kanban__cards { display: flex; flex-direction: column; gap: 10px; min-height: 40px; }
.kanban__card {
  padding: 12px; border-radius: 8px; cursor: grab; box-shadow: 0 1px 3px rgba(0,0,0,.08);
  transition: transform 0.15s, box-shadow 0.15s;
}
.kanban__card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.12); }
.kanban__card-header { display: flex; justify-content: space-between; align-items: start; }
.kanban__card-actions { display: flex; gap: 4px; }
.kanban__card-actions button { border: none; background: none; cursor: pointer; font-size: 14px; padding: 2px; }
.kanban__card-desc { margin: 6px 0 0; font-size: 13px; color: #475569; }
.kanban__add-btn {
  width: 100%; padding: 10px; margin-top: 10px; border: 2px dashed #cbd5e1;
  border-radius: 8px; background: none; cursor: pointer; color: #64748b; font-size: 14px;
}
.kanban__add-btn:hover { border-color: #3b82f6; color: #3b82f6; }
.kanban__add-form { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.kanban__add-form input, .kanban__add-form textarea {
  padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px;
}
.kanban__edit-input, .kanban__edit-textarea {
  width: 100%; padding: 6px; border: 1px solid #d1d5db; border-radius: 4px;
  font-size: 13px; margin-bottom: 4px;
}
.kanban__edit-actions { display: flex; gap: 6px; }
.kanban__btn { padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.kanban__btn--save { background: #3b82f6; color: #fff; }
.kanban__btn--cancel { background: #e2e8f0; color: #475569; }
```

### components/KanbanBoard/index.ts

```ts
export { KanbanBoard } from "./KanbanBoard";
```

네이티브 HTML Drag and Drop API를 사용하므로 외부 의존성이 없습니다. 카드 추가/편집/삭제가 모두 인라인으로 동작합니다.'''),

    # ═══ 4. 파일 업로더 ═══
    m("React로 파일 업로더 컴포넌트 만들어줘 전체 코드로",
'''파일 업로더 컴포넌트를 만들어 드릴게요. 드래그 앤 드롭, 다중 파일 선택, 업로드 진행률, 이미지 미리보기, 파일 유형/크기 검증을 지원합니다.

## 폴더 구조

```
src/
├── components/
│   ├── FileUploader/
│   │   ├── FileUploader.tsx
│   │   ├── DropZone.tsx
│   │   ├── FileList.tsx
│   │   ├── FileItem.tsx
│   │   ├── ProgressBar.tsx
│   │   ├── FileUploader.css
│   │   └── index.ts
│   └── index.ts
├── utils/
│   └── fileUtils.ts
├── App.tsx
└── index.tsx
```

### utils/fileUtils.ts
파일 크기/타입 검증 유틸입니다.

```ts
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

export function validateFile(
  file: File,
  acceptTypes?: string[],
  maxSize?: number
): { valid: boolean; error?: string } {
  if (acceptTypes && acceptTypes.length > 0) {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    const typeMatch = acceptTypes.some(
      (t) => file.type.startsWith(t.replace("*", "")) || t === ext
    );
    if (!typeMatch) return { valid: false, error: `허용되지 않는 파일 형식입니다: ${file.name}` };
  }
  if (maxSize && file.size > maxSize) {
    return { valid: false, error: `파일 크기 초과 (최대 ${formatFileSize(maxSize)}): ${file.name}` };
  }
  return { valid: true };
}

export function isImageFile(file: File): boolean {
  return file.type.startsWith("image/");
}

export function createThumbnail(file: File): Promise<string> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.readAsDataURL(file);
  });
}
```

### components/FileUploader/DropZone.tsx
드래그 앤 드롭 영역입니다.

```tsx
import React, { useState, useRef, DragEvent, ChangeEvent } from "react";

interface Props {
  onFiles: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
}

export function DropZone({ onFiles, accept, multiple = true }: Props) {
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragIn = (e: DragEvent) => { handleDrag(e); setIsDragOver(true); };
  const handleDragOut = (e: DragEvent) => { handleDrag(e); setIsDragOver(false); };

  const handleDrop = (e: DragEvent) => {
    handleDrag(e);
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length) onFiles(multiple ? files : [files[0]]);
  };

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length) onFiles(files);
    e.target.value = "";
  };

  return (
    <div
      className={`dropzone ${isDragOver ? "dropzone--active" : ""}`}
      onDragEnter={handleDragIn} onDragOver={handleDrag}
      onDragLeave={handleDragOut} onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <input ref={inputRef} type="file" accept={accept} multiple={multiple}
        onChange={handleInputChange} style={{ display: "none" }} />
      <div className="dropzone__icon">📁</div>
      <p className="dropzone__text">
        파일을 여기로 드래그하거나 <span className="dropzone__link">클릭하여 선택</span>하세요
      </p>
      <p className="dropzone__hint">최대 10MB, 여러 파일 동시 업로드 가능</p>
    </div>
  );
}
```

### components/FileUploader/ProgressBar.tsx

```tsx
import React from "react";

interface Props { percent: number; }

export function ProgressBar({ percent }: Props) {
  return (
    <div className="progress-bar">
      <div className="progress-bar__fill" style={{ width: `${percent}%` }} />
    </div>
  );
}
```

### components/FileUploader/FileItem.tsx
개별 파일 항목 (미리보기 + 진행률)입니다.

```tsx
import React, { useEffect, useState } from "react";
import { ProgressBar } from "./ProgressBar";
import { formatFileSize, isImageFile, createThumbnail } from "../../utils/fileUtils";

export interface UploadFile {
  id: string;
  file: File;
  progress: number;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
}

interface Props {
  item: UploadFile;
  onRemove: (id: string) => void;
}

export function FileItem({ item, onRemove }: Props) {
  const [thumbnail, setThumbnail] = useState<string | null>(null);

  useEffect(() => {
    if (isImageFile(item.file)) {
      createThumbnail(item.file).then(setThumbnail);
    }
  }, [item.file]);

  const statusIcon = {
    pending: "⏳", uploading: "⬆️", done: "✅", error: "❌",
  }[item.status];

  return (
    <div className="file-item">
      <div className="file-item__preview">
        {thumbnail ? (
          <img src={thumbnail} alt={item.file.name} className="file-item__thumb" />
        ) : (
          <div className="file-item__icon">📄</div>
        )}
      </div>
      <div className="file-item__info">
        <div className="file-item__name">
          <span>{item.file.name}</span>
          <span className="file-item__status">{statusIcon}</span>
        </div>
        <div className="file-item__size">{formatFileSize(item.file.size)}</div>
        {item.status === "uploading" && <ProgressBar percent={item.progress} />}
        {item.error && <div className="file-item__error">{item.error}</div>}
      </div>
      <button className="file-item__remove" onClick={() => onRemove(item.id)} title="삭제">✕</button>
    </div>
  );
}
```

### components/FileUploader/FileList.tsx

```tsx
import React from "react";
import { FileItem, UploadFile } from "./FileItem";

interface Props {
  files: UploadFile[];
  onRemove: (id: string) => void;
}

export function FileList({ files, onRemove }: Props) {
  if (files.length === 0) return null;
  return (
    <div className="file-list">
      {files.map((f) => <FileItem key={f.id} item={f} onRemove={onRemove} />)}
    </div>
  );
}
```

### components/FileUploader/FileUploader.tsx
전체를 조합하고 시뮬레이션 업로드를 실행합니다.

```tsx
import React, { useState, useCallback, useRef } from "react";
import { DropZone } from "./DropZone";
import { FileList } from "./FileList";
import { UploadFile } from "./FileItem";
import { validateFile } from "../../utils/fileUtils";
import "./FileUploader.css";

interface Props {
  accept?: string[];
  maxSize?: number;
  multiple?: boolean;
  onUploadComplete?: (files: File[]) => void;
}

let fileIdCounter = 0;

export function FileUploader({
  accept = ["image/*", ".pdf", ".doc", ".docx"],
  maxSize = 10 * 1024 * 1024,
  multiple = true,
  onUploadComplete,
}: Props) {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const intervalsRef = useRef<Map<string, number>>(new Map());

  const simulateUpload = useCallback((uf: UploadFile) => {
    const interval = window.setInterval(() => {
      setFiles((prev) => prev.map((f) => {
        if (f.id !== uf.id) return f;
        const next = Math.min(f.progress + Math.random() * 20, 100);
        if (next >= 100) {
          clearInterval(intervalsRef.current.get(f.id)!);
          intervalsRef.current.delete(f.id);
          return { ...f, progress: 100, status: "done" };
        }
        return { ...f, progress: next, status: "uploading" };
      }));
    }, 300);
    intervalsRef.current.set(uf.id, interval);
  }, []);

  const handleFiles = useCallback((incoming: File[]) => {
    const newFiles: UploadFile[] = [];
    for (const file of incoming) {
      const result = validateFile(file, accept, maxSize);
      const uf: UploadFile = {
        id: `file-${fileIdCounter++}`,
        file, progress: 0,
        status: result.valid ? "pending" : "error",
        error: result.error,
      };
      newFiles.push(uf);
    }
    setFiles((prev) => [...prev, ...newFiles]);
    newFiles.filter((f) => f.status === "pending").forEach(simulateUpload);
  }, [accept, maxSize, simulateUpload]);

  const handleRemove = useCallback((id: string) => {
    if (intervalsRef.current.has(id)) {
      clearInterval(intervalsRef.current.get(id)!);
      intervalsRef.current.delete(id);
    }
    setFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);

  return (
    <div className="file-uploader">
      <DropZone onFiles={handleFiles} accept={accept.join(",")} multiple={multiple} />
      <FileList files={files} onRemove={handleRemove} />
    </div>
  );
}
```

### components/FileUploader/FileUploader.css

```css
.file-uploader { width: 100%; max-width: 520px; }
.dropzone {
  border: 2px dashed #cbd5e1; border-radius: 12px; padding: 40px 20px;
  text-align: center; cursor: pointer; transition: all 0.2s; background: #fafbfc;
}
.dropzone:hover, .dropzone--active { border-color: #3b82f6; background: #eff6ff; }
.dropzone__icon { font-size: 40px; margin-bottom: 8px; }
.dropzone__text { font-size: 14px; color: #475569; margin: 0; }
.dropzone__link { color: #3b82f6; font-weight: 500; text-decoration: underline; }
.dropzone__hint { font-size: 12px; color: #94a3b8; margin: 6px 0 0; }
.file-list { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
.file-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 14px;
  background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
}
.file-item__preview { flex-shrink: 0; width: 44px; height: 44px; }
.file-item__thumb { width: 44px; height: 44px; object-fit: cover; border-radius: 6px; }
.file-item__icon { width: 44px; height: 44px; display: flex; align-items: center;
  justify-content: center; background: #f1f5f9; border-radius: 6px; font-size: 20px; }
.file-item__info { flex: 1; min-width: 0; }
.file-item__name { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; }
.file-item__name span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-item__size { font-size: 12px; color: #94a3b8; }
.file-item__error { font-size: 12px; color: #ef4444; margin-top: 2px; }
.file-item__remove {
  border: none; background: none; cursor: pointer; color: #94a3b8;
  font-size: 16px; padding: 4px; border-radius: 4px;
}
.file-item__remove:hover { background: #fee2e2; color: #ef4444; }
.progress-bar { width: 100%; height: 4px; background: #e2e8f0; border-radius: 2px; margin-top: 6px; }
.progress-bar__fill { height: 100%; background: #3b82f6; border-radius: 2px; transition: width 0.3s; }
```

### components/FileUploader/index.ts

```ts
export { FileUploader } from "./FileUploader";
```

시뮬레이션 업로드로 동작하며, 실제 서버 연동 시 `simulateUpload` 함수만 `fetch`/`XMLHttpRequest`로 교체하면 됩니다.'''),

    # ═══ 5. 커맨드 팔레트 (Cmd+K) ═══
    m("React로 커맨드 팔레트(Cmd+K) 컴포넌트 만들어줘 전체 코드로",
'''커맨드 팔레트(Cmd+K) 컴포넌트를 만들어 드릴게요. 모달 오버레이, 퍼지 검색, 키보드 내비게이션, 액션 그룹, 최근 항목, 단축키 표시를 지원합니다.

## 폴더 구조

```
src/
├── components/
│   ├── CommandPalette/
│   │   ├── CommandPalette.tsx
│   │   ├── CommandInput.tsx
│   │   ├── CommandList.tsx
│   │   ├── CommandItem.tsx
│   │   ├── CommandPalette.css
│   │   └── index.ts
│   └── index.ts
├── hooks/
│   └── useCommandPalette.ts
├── utils/
│   └── fuzzySearch.ts
├── App.tsx
└── index.tsx
```

### utils/fuzzySearch.ts
퍼지 검색 알고리즘입니다. 각 문자가 순서대로 매칭되는지 확인합니다.

```ts
export interface FuzzyResult<T> {
  item: T;
  score: number;
  matches: number[];
}

export function fuzzyMatch(query: string, text: string): { match: boolean; score: number; indices: number[] } {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  let qi = 0;
  let score = 0;
  const indices: number[] = [];
  let lastMatchIdx = -1;

  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) {
      indices.push(ti);
      score += (ti === lastMatchIdx + 1) ? 10 : 1;
      if (ti === 0 || t[ti - 1] === " " || t[ti - 1] === "/") score += 5;
      lastMatchIdx = ti;
      qi++;
    }
  }

  return { match: qi === q.length, score, indices };
}

export function fuzzySearch<T>(
  query: string,
  items: T[],
  getText: (item: T) => string
): FuzzyResult<T>[] {
  if (!query.trim()) return items.map((item) => ({ item, score: 0, matches: [] }));
  return items
    .map((item) => {
      const { match, score, indices } = fuzzyMatch(query, getText(item));
      return match ? { item, score, matches: indices } : null;
    })
    .filter(Boolean) as FuzzyResult<T>[]
    .sort((a, b) => b.score - a.score);
}
```

### hooks/useCommandPalette.ts
Cmd+K 단축키 감지와 열기/닫기 상태를 관리합니다.

```ts
import { useState, useEffect, useCallback } from "react";

export function useCommandPalette() {
  const [isOpen, setIsOpen] = useState(false);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  const toggle = useCallback(() => setIsOpen((p) => !p), []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        toggle();
      }
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [toggle, close]);

  return { isOpen, open, close, toggle };
}
```

### components/CommandPalette/CommandInput.tsx

```tsx
import React, { useRef, useEffect } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
}

export function CommandInput({ value, onChange }: Props) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);

  return (
    <div className="cmd__input-wrapper">
      <span className="cmd__search-icon">🔍</span>
      <input
        ref={ref}
        className="cmd__input"
        type="text"
        placeholder="명령어 검색..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <kbd className="cmd__kbd">ESC</kbd>
    </div>
  );
}
```

### components/CommandPalette/CommandItem.tsx

```tsx
import React from "react";

export interface Action {
  id: string;
  label: string;
  group: string;
  icon?: string;
  shortcut?: string[];
  onAction: () => void;
}

interface Props {
  action: Action;
  active: boolean;
  onSelect: () => void;
  onHover: () => void;
}

export function CommandItem({ action, active, onSelect, onHover }: Props) {
  return (
    <div
      className={`cmd__item ${active ? "cmd__item--active" : ""}`}
      onClick={onSelect}
      onMouseEnter={onHover}
    >
      {action.icon && <span className="cmd__item-icon">{action.icon}</span>}
      <span className="cmd__item-label">{action.label}</span>
      {action.shortcut && (
        <span className="cmd__item-shortcut">
          {action.shortcut.map((k, i) => <kbd key={i}>{k}</kbd>)}
        </span>
      )}
    </div>
  );
}
```

### components/CommandPalette/CommandList.tsx
키보드 내비게이션과 그룹 렌더링을 담당합니다.

```tsx
import React, { useEffect, useRef } from "react";
import { CommandItem, Action } from "./CommandItem";

interface Props {
  groups: Map<string, Action[]>;
  activeIdx: number;
  flatActions: Action[];
  onSelect: (action: Action) => void;
  onSetActive: (idx: number) => void;
}

export function CommandList({ groups, activeIdx, flatActions, onSelect, onSetActive }: Props) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = listRef.current?.querySelector(".cmd__item--active");
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIdx]);

  if (flatActions.length === 0) {
    return <div className="cmd__empty">검색 결과가 없습니다</div>;
  }

  let globalIdx = 0;
  return (
    <div className="cmd__list" ref={listRef}>
      {Array.from(groups.entries()).map(([group, actions]) => (
        <div key={group} className="cmd__group">
          <div className="cmd__group-label">{group}</div>
          {actions.map((action) => {
            const idx = globalIdx++;
            return (
              <CommandItem
                key={action.id}
                action={action}
                active={idx === activeIdx}
                onSelect={() => onSelect(action)}
                onHover={() => onSetActive(idx)}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}
```

### components/CommandPalette/CommandPalette.tsx

```tsx
import React, { useState, useCallback, useEffect, useMemo } from "react";
import { CommandInput } from "./CommandInput";
import { CommandList } from "./CommandList";
import { Action } from "./CommandItem";
import { fuzzySearch } from "../../utils/fuzzySearch";
import "./CommandPalette.css";

const SAMPLE_ACTIONS: Action[] = [
  { id: "new-file", label: "새 파일", group: "파일", icon: "📄", shortcut: ["⌘", "N"], onAction: () => alert("새 파일") },
  { id: "open-file", label: "파일 열기", group: "파일", icon: "📂", shortcut: ["⌘", "O"], onAction: () => alert("파일 열기") },
  { id: "save", label: "저장", group: "파일", icon: "💾", shortcut: ["⌘", "S"], onAction: () => alert("저장") },
  { id: "find", label: "찾기", group: "편집", icon: "🔍", shortcut: ["⌘", "F"], onAction: () => alert("찾기") },
  { id: "replace", label: "찾아 바꾸기", group: "편집", icon: "🔄", shortcut: ["⌘", "H"], onAction: () => alert("바꾸기") },
  { id: "terminal", label: "터미널 열기", group: "보기", icon: "🖥️", shortcut: ["⌃", "`"], onAction: () => alert("터미널") },
  { id: "sidebar", label: "사이드바 토글", group: "보기", icon: "📊", shortcut: ["⌘", "B"], onAction: () => alert("사이드바") },
  { id: "settings", label: "설정", group: "기타", icon: "⚙️", shortcut: ["⌘", ","], onAction: () => alert("설정") },
  { id: "theme", label: "테마 변경", group: "기타", icon: "🎨", onAction: () => alert("테마") },
  { id: "git-commit", label: "Git 커밋", group: "Git", icon: "📝", onAction: () => alert("커밋") },
  { id: "git-push", label: "Git 푸시", group: "Git", icon: "⬆️", onAction: () => alert("푸시") },
];

interface Props {
  isOpen: boolean;
  onClose: () => void;
  actions?: Action[];
}

export function CommandPalette({ isOpen, onClose, actions = SAMPLE_ACTIONS }: Props) {
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);

  const filtered = useMemo(() => {
    const results = fuzzySearch(query, actions, (a) => a.label);
    return results.map((r) => r.item);
  }, [query, actions]);

  const groups = useMemo(() => {
    const map = new Map<string, Action[]>();
    for (const action of filtered) {
      if (!map.has(action.group)) map.set(action.group, []);
      map.get(action.group)!.push(action);
    }
    return map;
  }, [filtered]);

  useEffect(() => { setActiveIdx(0); }, [query]);
  useEffect(() => { if (isOpen) setQuery(""); }, [isOpen]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActiveIdx((i) => Math.min(i + 1, filtered.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActiveIdx((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter" && filtered[activeIdx]) {
      filtered[activeIdx].onAction();
      onClose();
    }
  }, [filtered, activeIdx, onClose]);

  if (!isOpen) return null;

  return (
    <div className="cmd__overlay" onClick={onClose}>
      <div className="cmd__modal" onClick={(e) => e.stopPropagation()} onKeyDown={handleKeyDown}>
        <CommandInput value={query} onChange={setQuery} />
        <CommandList
          groups={groups} activeIdx={activeIdx} flatActions={filtered}
          onSelect={(action) => { action.onAction(); onClose(); }}
          onSetActive={setActiveIdx}
        />
        <div className="cmd__footer">
          <span><kbd>↑↓</kbd> 이동</span>
          <span><kbd>Enter</kbd> 실행</span>
          <span><kbd>Esc</kbd> 닫기</span>
        </div>
      </div>
    </div>
  );
}
```

### components/CommandPalette/CommandPalette.css

```css
.cmd__overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 100;
  display: flex; align-items: flex-start; justify-content: center; padding-top: 20vh;
  backdrop-filter: blur(4px);
}
.cmd__modal {
  width: 560px; max-height: 440px; background: #fff; border-radius: 14px;
  box-shadow: 0 20px 60px rgba(0,0,0,.25); overflow: hidden;
  display: flex; flex-direction: column;
}
.cmd__input-wrapper {
  display: flex; align-items: center; gap: 10px; padding: 14px 18px;
  border-bottom: 1px solid #e2e8f0;
}
.cmd__search-icon { font-size: 18px; }
.cmd__input {
  flex: 1; border: none; outline: none; font-size: 16px; background: none;
}
.cmd__kbd {
  padding: 2px 8px; background: #f1f5f9; border: 1px solid #e2e8f0;
  border-radius: 4px; font-size: 11px; color: #64748b;
}
.cmd__list { overflow-y: auto; padding: 6px 0; flex: 1; }
.cmd__group-label {
  padding: 8px 18px 4px; font-size: 11px; font-weight: 600; color: #94a3b8;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.cmd__item {
  display: flex; align-items: center; gap: 10px; padding: 10px 18px;
  cursor: pointer; transition: background 0.1s;
}
.cmd__item:hover, .cmd__item--active { background: #f1f5f9; }
.cmd__item--active { background: #3b82f6; color: #fff; }
.cmd__item--active .cmd__item-shortcut kbd { background: rgba(255,255,255,.2); border-color: rgba(255,255,255,.3); color: #fff; }
.cmd__item-icon { font-size: 16px; width: 24px; text-align: center; }
.cmd__item-label { flex: 1; font-size: 14px; }
.cmd__item-shortcut { display: flex; gap: 3px; }
.cmd__item-shortcut kbd {
  padding: 2px 6px; background: #f1f5f9; border: 1px solid #e2e8f0;
  border-radius: 4px; font-size: 11px; color: #64748b;
}
.cmd__empty { padding: 30px; text-align: center; color: #94a3b8; font-size: 14px; }
.cmd__footer {
  display: flex; gap: 16px; padding: 10px 18px; border-top: 1px solid #e2e8f0;
  font-size: 12px; color: #94a3b8;
}
.cmd__footer kbd {
  padding: 1px 5px; background: #f1f5f9; border: 1px solid #e2e8f0;
  border-radius: 3px; font-size: 11px; margin-right: 3px;
}
```

### components/CommandPalette/index.ts

```ts
export { CommandPalette } from "./CommandPalette";
export type { Action } from "./CommandItem";
```

Cmd+K (Mac) 또는 Ctrl+K (Windows)로 열고, 화살표 키로 탐색, Enter로 실행합니다. 퍼지 검색으로 빠른 명령 접근이 가능합니다.'''),

    # ═══ 6. 마크다운 에디터 ═══
    m("React로 마크다운 에디터 컴포넌트 만들어줘 전체 코드로",
'''마크다운 에디터 컴포넌트를 만들어 드릴게요. 분할 화면(에디터 + 미리보기), 툴바 버튼, 마크다운→HTML 렌더링, 자동 크기 조절, 키보드 단축키를 지원합니다.

## 폴더 구조

```
src/
├── components/
│   ├── MarkdownEditor/
│   │   ├── MarkdownEditor.tsx
│   │   ├── Toolbar.tsx
│   │   ├── EditorPane.tsx
│   │   ├── PreviewPane.tsx
│   │   ├── MarkdownEditor.css
│   │   └── index.ts
│   └── index.ts
├── utils/
│   └── markdownParser.ts
├── App.tsx
└── index.tsx
```

### utils/markdownParser.ts
정규식 기반 마크다운→HTML 파서입니다. 외부 의존성 없이 주요 문법을 지원합니다.

```ts
export function parseMarkdown(md: string): string {
  let html = md;

  // 코드 블록 (```...```)
  html = html.replace(/```(\\w*)\\n([\\s\\S]*?)```/g,
    (_, lang, code) => `<pre><code class="lang-${lang}">${escapeHtml(code.trim())}</code></pre>`);

  // 인라인 코드
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // 헤딩
  html = html.replace(/^#{6}\\s+(.+)$/gm, "<h6>$1</h6>");
  html = html.replace(/^#{5}\\s+(.+)$/gm, "<h5>$1</h5>");
  html = html.replace(/^#{4}\\s+(.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^###\\s+(.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^##\\s+(.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^#\\s+(.+)$/gm, "<h1>$1</h1>");

  // 볼드/이탤릭
  html = html.replace(/\\*\\*\\*(.+?)\\*\\*\\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\\*\\*(.+?)\\*\\*/g, "<strong>$1</strong>");
  html = html.replace(/\\*(.+?)\\*/g, "<em>$1</em>");

  // 취소선
  html = html.replace(/~~(.+?)~~/g, "<del>$1</del>");

  // 링크, 이미지
  html = html.replace(/!\\[([^\\]]*)\\]\\(([^)]+)\\)/g, '<img src="$2" alt="$1" />');
  html = html.replace(/\\[([^\\]]*)\\]\\(([^)]+)\\)/g, '<a href="$2">$1</a>');

  // 수평선
  html = html.replace(/^---$/gm, "<hr />");

  // 인용문
  html = html.replace(/^>\\s+(.+)$/gm, "<blockquote>$1</blockquote>");

  // 비순서 리스트
  html = html.replace(/^[\\-\\*]\\s+(.+)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\\/li>)/s, "<ul>$1</ul>");

  // 순서 리스트
  html = html.replace(/^\\d+\\.\\s+(.+)$/gm, "<li>$1</li>");

  // 줄바꿈 → 문단
  html = html.replace(/\\n\\n/g, "</p><p>");
  html = `<p>${html}</p>`;
  html = html.replace(/<p><(h[1-6]|pre|ul|ol|blockquote|hr)/g, "<$1");
  html = html.replace(/<\\/(h[1-6]|pre|ul|ol|blockquote)><\\/p>/g, "</$1>");

  return html;
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
```

### components/MarkdownEditor/Toolbar.tsx
굵게, 기울임, 헤딩, 링크, 코드, 리스트 버튼입니다.

```tsx
import React from "react";

interface Props {
  onAction: (type: string) => void;
}

const BUTTONS = [
  { type: "bold", label: "B", title: "굵게 (Ctrl+B)", style: { fontWeight: 700 } },
  { type: "italic", label: "I", title: "기울임 (Ctrl+I)", style: { fontStyle: "italic" } },
  { type: "heading", label: "H", title: "헤딩", style: { fontWeight: 700 } },
  { type: "link", label: "🔗", title: "링크 (Ctrl+K)", style: {} },
  { type: "code", label: "</>", title: "코드", style: { fontFamily: "monospace" } },
  { type: "ul", label: "• List", title: "비순서 리스트", style: {} },
  { type: "ol", label: "1. List", title: "순서 리스트", style: {} },
  { type: "quote", label: ">", title: "인용", style: {} },
  { type: "hr", label: "─", title: "수평선", style: {} },
];

export function Toolbar({ onAction }: Props) {
  return (
    <div className="md-toolbar">
      {BUTTONS.map((btn) => (
        <button
          key={btn.type}
          className="md-toolbar__btn"
          title={btn.title}
          style={btn.style as React.CSSProperties}
          onClick={() => onAction(btn.type)}
        >
          {btn.label}
        </button>
      ))}
    </div>
  );
}
```

### components/MarkdownEditor/EditorPane.tsx
자동 크기 조절 텍스트영역입니다.

```tsx
import React, { useRef, useEffect, useCallback, KeyboardEvent } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onAction: (type: string) => void;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
}

export function EditorPane({ value, onChange, onAction, textareaRef }: Props) {
  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(el.scrollHeight, 300)}px`;
  }, [textareaRef]);

  useEffect(() => { autoResize(); }, [value, autoResize]);

  const handleKeyDown = (e: KeyboardEvent) => {
    if (!e.ctrlKey && !e.metaKey) return;
    const map: Record<string, string> = { b: "bold", i: "italic", k: "link" };
    if (map[e.key]) {
      e.preventDefault();
      onAction(map[e.key]);
    }
  };

  return (
    <div className="md-editor-pane">
      <textarea
        ref={textareaRef as React.RefObject<HTMLTextAreaElement>}
        className="md-textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="마크다운을 입력하세요..."
        spellCheck={false}
      />
    </div>
  );
}
```

### components/MarkdownEditor/PreviewPane.tsx
HTML 미리보기 영역입니다.

```tsx
import React, { useMemo } from "react";
import { parseMarkdown } from "../../utils/markdownParser";

interface Props { markdown: string; }

export function PreviewPane({ markdown }: Props) {
  const html = useMemo(() => parseMarkdown(markdown), [markdown]);

  return (
    <div className="md-preview-pane">
      <div className="md-preview__content" dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
}
```

### components/MarkdownEditor/MarkdownEditor.tsx
툴바 액션은 선택 영역을 감싸는 방식으로 동작합니다.

```tsx
import React, { useState, useRef, useCallback } from "react";
import { Toolbar } from "./Toolbar";
import { EditorPane } from "./EditorPane";
import { PreviewPane } from "./PreviewPane";
import "./MarkdownEditor.css";

const INITIAL = `# 마크다운 에디터

**굵은 글씨**와 *기울임 글씨*를 지원합니다.

## 기능 목록

- 실시간 미리보기
- 툴바 버튼
- 키보드 단축키 (Ctrl+B, Ctrl+I, Ctrl+K)

\`\`\`javascript
const hello = "Hello, Hwarang!";
console.log(hello);
\`\`\`

> 인용문도 지원합니다.
`;

interface Props {
  defaultValue?: string;
  onChange?: (value: string) => void;
}

export function MarkdownEditor({ defaultValue = INITIAL, onChange }: Props) {
  const [value, setValue] = useState(defaultValue);
  const [mode, setMode] = useState<"split" | "edit" | "preview">("split");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleChange = useCallback((v: string) => {
    setValue(v);
    onChange?.(v);
  }, [onChange]);

  const insertAround = useCallback((before: string, after: string) => {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const selected = value.slice(start, end) || "텍스트";
    const newText = value.slice(0, start) + before + selected + after + value.slice(end);
    handleChange(newText);
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + before.length, start + before.length + selected.length);
    }, 0);
  }, [value, handleChange]);

  const insertLine = useCallback((prefix: string) => {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const lineStart = value.lastIndexOf("\\n", start - 1) + 1;
    const newText = value.slice(0, lineStart) + prefix + value.slice(lineStart);
    handleChange(newText);
  }, [value, handleChange]);

  const handleAction = useCallback((type: string) => {
    switch (type) {
      case "bold": insertAround("**", "**"); break;
      case "italic": insertAround("*", "*"); break;
      case "code": insertAround("`", "`"); break;
      case "link": insertAround("[", "](url)"); break;
      case "heading": insertLine("## "); break;
      case "ul": insertLine("- "); break;
      case "ol": insertLine("1. "); break;
      case "quote": insertLine("> "); break;
      case "hr": {
        const el = textareaRef.current;
        if (!el) break;
        const pos = el.selectionStart;
        handleChange(value.slice(0, pos) + "\\n---\\n" + value.slice(pos));
        break;
      }
    }
  }, [insertAround, insertLine, value, handleChange]);

  return (
    <div className="md-editor">
      <div className="md-editor__header">
        <Toolbar onAction={handleAction} />
        <div className="md-editor__modes">
          <button className={mode === "edit" ? "active" : ""} onClick={() => setMode("edit")}>편집</button>
          <button className={mode === "split" ? "active" : ""} onClick={() => setMode("split")}>분할</button>
          <button className={mode === "preview" ? "active" : ""} onClick={() => setMode("preview")}>미리보기</button>
        </div>
      </div>
      <div className={`md-editor__body md-editor__body--${mode}`}>
        {mode !== "preview" && (
          <EditorPane value={value} onChange={handleChange} onAction={handleAction} textareaRef={textareaRef} />
        )}
        {mode !== "edit" && <PreviewPane markdown={value} />}
      </div>
    </div>
  );
}
```

### components/MarkdownEditor/MarkdownEditor.css

```css
.md-editor { border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; }
.md-editor__header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;
}
.md-toolbar { display: flex; gap: 2px; }
.md-toolbar__btn {
  padding: 6px 10px; border: 1px solid transparent; border-radius: 6px;
  background: none; cursor: pointer; font-size: 13px; color: #475569;
}
.md-toolbar__btn:hover { background: #e2e8f0; }
.md-editor__modes { display: flex; gap: 2px; }
.md-editor__modes button {
  padding: 5px 12px; border: 1px solid #d1d5db; border-radius: 6px;
  background: #fff; cursor: pointer; font-size: 12px;
}
.md-editor__modes button.active { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.md-editor__body { display: flex; min-height: 400px; }
.md-editor__body--split > * { flex: 1; }
.md-editor__body--edit .md-editor-pane { flex: 1; }
.md-editor__body--preview .md-preview-pane { flex: 1; }
.md-editor-pane { border-right: 1px solid #e2e8f0; }
.md-textarea {
  width: 100%; min-height: 400px; padding: 16px; border: none; outline: none;
  font-family: "JetBrains Mono", "Fira Code", monospace; font-size: 14px;
  line-height: 1.7; resize: none; background: #fff;
}
.md-preview-pane { overflow-y: auto; }
.md-preview__content { padding: 16px; line-height: 1.8; font-size: 15px; color: #1e293b; }
.md-preview__content h1 { font-size: 28px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }
.md-preview__content h2 { font-size: 22px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }
.md-preview__content h3 { font-size: 18px; }
.md-preview__content code {
  background: #f1f5f9; padding: 2px 6px; border-radius: 4px;
  font-family: "JetBrains Mono", monospace; font-size: 13px;
}
.md-preview__content pre {
  background: #1e293b; color: #e2e8f0; padding: 16px; border-radius: 8px;
  overflow-x: auto;
}
.md-preview__content pre code { background: none; color: inherit; padding: 0; }
.md-preview__content blockquote {
  border-left: 4px solid #3b82f6; padding: 8px 16px; margin: 12px 0;
  background: #eff6ff; border-radius: 0 8px 8px 0; color: #1e40af;
}
.md-preview__content a { color: #3b82f6; text-decoration: underline; }
.md-preview__content img { max-width: 100%; border-radius: 8px; }
.md-preview__content hr { border: none; border-top: 2px solid #e2e8f0; margin: 20px 0; }
.md-preview__content ul, .md-preview__content ol { padding-left: 24px; }
.md-preview__content li { margin: 4px 0; }
```

### components/MarkdownEditor/index.ts

```ts
export { MarkdownEditor } from "./MarkdownEditor";
```

마크다운 파서를 직접 구현했으므로 외부 의존성 없이 동작합니다. 실무에서는 `marked`나 `remark` 라이브러리로 교체하면 더 완전한 파싱이 가능합니다.'''),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mega_components.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"컴포넌트 추가: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
