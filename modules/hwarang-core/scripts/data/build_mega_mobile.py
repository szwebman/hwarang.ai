"""화랑 AI 모바일 앱 추가 학습 데이터

React Native + Expo 기반 실전 모바일 앱 6건.
각 앱: 폴더 구조 + 6~10개 파일 전체 코드.

카테고리:
  - 가계부 앱 (Zustand + AsyncStorage)
  - 날씨 앱 (expo-location)
  - 메모/노트 앱 (폴더 정리 + 리치 텍스트)
  - 운동 기록 앱 (세트/횟수/중량 + 캘린더)
  - 습관 트래커 앱 (스트릭 + 통계)
  - 레시피 앱 (재료 체크 + 타이머)
"""

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
    # ═══ 1. 가계부 앱 ═══
    m("React Native로 가계부 앱 만들어줘 전체 코드로",
'''React Native 가계부 앱을 만들어 드릴게요. 수입/지출 입력, 카테고리별 예산, 월간 요약 차트를 포함합니다.

## 폴더 구조

```
budget-app/
├── App.tsx
├── src/
│   ├── store/
│   │   └── useBudgetStore.ts
│   ├── screens/
│   │   ├── HomeScreen.tsx
│   │   ├── AddTransactionScreen.tsx
│   │   └── StatsScreen.tsx
│   ├── components/
│   │   ├── TransactionItem.tsx
│   │   ├── BarChart.tsx
│   │   └── CategoryBreakdown.tsx
│   └── utils/
│       └── categories.ts
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "budget-app",
  "version": "1.0.0",
  "scripts": { "start": "expo start", "android": "expo start --android", "ios": "expo start --ios" },
  "dependencies": {
    "expo": "~50.0.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/bottom-tabs": "^6.5.12",
    "react-native-screens": "~3.29.0",
    "react-native-safe-area-context": "4.8.2",
    "zustand": "^4.5.0",
    "@react-native-async-storage/async-storage": "1.21.0",
    "react-native-svg": "14.1.0"
  }
}
```

## src/utils/categories.ts

```typescript
// 카테고리 정의 — 색상은 차트 표시용
export interface Category {
  id: string;
  label: string;
  icon: string;
  color: string;
  type: "income" | "expense";
}

export const CATEGORIES: Category[] = [
  { id: "salary", label: "급여", icon: "💰", color: "#4CAF50", type: "income" },
  { id: "freelance", label: "프리랜서", icon: "💻", color: "#8BC34A", type: "income" },
  { id: "food", label: "식비", icon: "🍚", color: "#FF5722", type: "expense" },
  { id: "transport", label: "교통", icon: "🚌", color: "#2196F3", type: "expense" },
  { id: "shopping", label: "쇼핑", icon: "🛍️", color: "#E91E63", type: "expense" },
  { id: "entertainment", label: "여가", icon: "🎬", color: "#9C27B0", type: "expense" },
  { id: "health", label: "의료", icon: "🏥", color: "#00BCD4", type: "expense" },
  { id: "housing", label: "주거", icon: "🏠", color: "#FF9800", type: "expense" },
];

export const getCategoryById = (id: string) => CATEGORIES.find((c) => c.id === id);
```

## src/store/useBudgetStore.ts

```typescript
import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";

export interface Transaction {
  id: string;
  amount: number;
  categoryId: string;
  note: string;
  date: string; // ISO string
  type: "income" | "expense";
}

export interface BudgetLimit {
  categoryId: string;
  limit: number;
}

interface BudgetState {
  transactions: Transaction[];
  budgets: BudgetLimit[];
  addTransaction: (t: Omit<Transaction, "id">) => void;
  deleteTransaction: (id: string) => void;
  setBudget: (categoryId: string, limit: number) => void;
  loadData: () => Promise<void>;
}

const persist = async (key: string, data: unknown) => {
  await AsyncStorage.setItem(key, JSON.stringify(data));
};

export const useBudgetStore = create<BudgetState>((set, get) => ({
  transactions: [],
  budgets: [],
  addTransaction: (t) => {
    const tx: Transaction = { ...t, id: Date.now().toString() };
    const next = [...get().transactions, tx];
    set({ transactions: next });
    persist("@transactions", next);
  },
  deleteTransaction: (id) => {
    const next = get().transactions.filter((t) => t.id !== id);
    set({ transactions: next });
    persist("@transactions", next);
  },
  setBudget: (categoryId, limit) => {
    const budgets = get().budgets.filter((b) => b.categoryId !== categoryId);
    const next = [...budgets, { categoryId, limit }];
    set({ budgets: next });
    persist("@budgets", next);
  },
  loadData: async () => {
    const [txRaw, budRaw] = await Promise.all([
      AsyncStorage.getItem("@transactions"),
      AsyncStorage.getItem("@budgets"),
    ]);
    set({
      transactions: txRaw ? JSON.parse(txRaw) : [],
      budgets: budRaw ? JSON.parse(budRaw) : [],
    });
  },
}));
```

## src/components/TransactionItem.tsx

```tsx
import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Transaction } from "../store/useBudgetStore";
import { getCategoryById } from "../utils/categories";

interface Props {
  item: Transaction;
  onDelete: (id: string) => void;
}

export default function TransactionItem({ item, onDelete }: Props) {
  const cat = getCategoryById(item.categoryId);
  const isIncome = item.type === "income";
  return (
    <TouchableOpacity onLongPress={() => onDelete(item.id)} style={styles.row}>
      <Text style={styles.icon}>{cat?.icon ?? "📌"}</Text>
      <View style={styles.info}>
        <Text style={styles.label}>{cat?.label}</Text>
        <Text style={styles.note}>{item.note || "메모 없음"}</Text>
      </View>
      <Text style={[styles.amount, { color: isIncome ? "#4CAF50" : "#F44336" }]}>
        {isIncome ? "+" : "-"}{item.amount.toLocaleString()}원
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", padding: 14, borderBottomWidth: 1, borderColor: "#eee" },
  icon: { fontSize: 24, marginRight: 12 },
  info: { flex: 1 },
  label: { fontSize: 15, fontWeight: "600" },
  note: { fontSize: 12, color: "#999", marginTop: 2 },
  amount: { fontSize: 16, fontWeight: "700" },
});
```

## src/components/BarChart.tsx

```tsx
import React from "react";
import { View, Text, StyleSheet } from "react-native";

// 순수 RN 막대 차트 — 외부 라이브러리 없이 구현
interface BarData { label: string; value: number; color: string }
interface Props { data: BarData[]; height?: number }

export default function BarChart({ data, height = 160 }: Props) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <View style={styles.container}>
      {data.map((d, i) => (
        <View key={i} style={styles.col}>
          <Text style={styles.value}>{(d.value / 10000).toFixed(0)}만</Text>
          <View style={[styles.bar, { height: (d.value / max) * height, backgroundColor: d.color }]} />
          <Text style={styles.label}>{d.label}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flexDirection: "row", justifyContent: "space-around", alignItems: "flex-end", paddingVertical: 12 },
  col: { alignItems: "center", flex: 1 },
  bar: { width: 28, borderRadius: 4, minHeight: 4 },
  value: { fontSize: 10, color: "#666", marginBottom: 4 },
  label: { fontSize: 11, color: "#888", marginTop: 4 },
});
```

## src/components/CategoryBreakdown.tsx

```tsx
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { useBudgetStore } from "../store/useBudgetStore";
import { CATEGORIES } from "../utils/categories";

// 카테고리별 지출 비중을 가로 프로그레스 바로 표시 (파이 차트 대안)
export default function CategoryBreakdown({ month }: { month: string }) {
  const transactions = useBudgetStore((s) => s.transactions);
  const budgets = useBudgetStore((s) => s.budgets);
  const expenses = transactions.filter((t) => t.type === "expense" && t.date.startsWith(month));
  const total = expenses.reduce((s, t) => s + t.amount, 0) || 1;

  const grouped = CATEGORIES.filter((c) => c.type === "expense").map((cat) => {
    const sum = expenses.filter((t) => t.categoryId === cat.id).reduce((s, t) => s + t.amount, 0);
    const budget = budgets.find((b) => b.categoryId === cat.id)?.limit ?? 0;
    return { ...cat, sum, ratio: sum / total, budget };
  }).filter((g) => g.sum > 0);

  return (
    <View style={styles.wrap}>
      {grouped.map((g) => (
        <View key={g.id} style={styles.row}>
          <Text style={styles.label}>{g.icon} {g.label}</Text>
          <View style={styles.barBg}>
            <View style={[styles.barFill, { width: `${Math.min(g.ratio * 100, 100)}%`, backgroundColor: g.color }]} />
          </View>
          <Text style={styles.amount}>{g.sum.toLocaleString()}원</Text>
          {g.budget > 0 && <Text style={[styles.badge, g.sum > g.budget && { color: "#F44336" }]}> / {g.budget.toLocaleString()}</Text>}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 12 },
  row: { flexDirection: "row", alignItems: "center", marginBottom: 10 },
  label: { width: 70, fontSize: 13 },
  barBg: { flex: 1, height: 10, backgroundColor: "#eee", borderRadius: 5, overflow: "hidden", marginHorizontal: 8 },
  barFill: { height: "100%", borderRadius: 5 },
  amount: { fontSize: 12, fontWeight: "600", width: 80, textAlign: "right" },
  badge: { fontSize: 10, color: "#999" },
});
```

## src/screens/HomeScreen.tsx

```tsx
import React, { useEffect, useState } from "react";
import { View, Text, FlatList, StyleSheet, TouchableOpacity } from "react-native";
import { useBudgetStore } from "../store/useBudgetStore";
import TransactionItem from "../components/TransactionItem";

export default function HomeScreen({ navigation }: any) {
  const { transactions, deleteTransaction, loadData } = useBudgetStore();
  const [month] = useState(() => new Date().toISOString().slice(0, 7));

  useEffect(() => { loadData(); }, []);

  const monthly = transactions.filter((t) => t.date.startsWith(month));
  const income = monthly.filter((t) => t.type === "income").reduce((s, t) => s + t.amount, 0);
  const expense = monthly.filter((t) => t.type === "expense").reduce((s, t) => s + t.amount, 0);

  return (
    <View style={styles.container}>
      <View style={styles.summary}>
        <Text style={styles.title}>{month} 요약</Text>
        <Text style={{ color: "#4CAF50", fontSize: 16 }}>수입 +{income.toLocaleString()}원</Text>
        <Text style={{ color: "#F44336", fontSize: 16 }}>지출 -{expense.toLocaleString()}원</Text>
        <Text style={styles.balance}>잔액 {(income - expense).toLocaleString()}원</Text>
      </View>
      <TouchableOpacity style={styles.addBtn} onPress={() => navigation.navigate("Add")}>
        <Text style={styles.addText}>+ 기록 추가</Text>
      </TouchableOpacity>
      <FlatList
        data={monthly.sort((a, b) => b.date.localeCompare(a.date))}
        keyExtractor={(i) => i.id}
        renderItem={({ item }) => <TransactionItem item={item} onDelete={deleteTransaction} />}
        ListEmptyComponent={<Text style={styles.empty}>아직 기록이 없습니다</Text>}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  summary: { padding: 20, backgroundColor: "#F5F5F5", alignItems: "center" },
  title: { fontSize: 18, fontWeight: "700", marginBottom: 8 },
  balance: { fontSize: 20, fontWeight: "800", marginTop: 6 },
  addBtn: { backgroundColor: "#2196F3", margin: 12, padding: 14, borderRadius: 8, alignItems: "center" },
  addText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  empty: { textAlign: "center", color: "#aaa", marginTop: 40 },
});
```

## src/screens/AddTransactionScreen.tsx

```tsx
import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet, Alert } from "react-native";
import { useBudgetStore } from "../store/useBudgetStore";
import { CATEGORIES } from "../utils/categories";

export default function AddTransactionScreen({ navigation }: any) {
  const [type, setType] = useState<"income" | "expense">("expense");
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const addTransaction = useBudgetStore((s) => s.addTransaction);

  const filtered = CATEGORIES.filter((c) => c.type === type);

  const handleSave = () => {
    if (!categoryId || !amount) return Alert.alert("입력 오류", "카테고리와 금액을 입력하세요");
    addTransaction({ amount: Number(amount), categoryId, note, date: new Date().toISOString(), type });
    navigation.goBack();
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.toggle}>
        {(["income", "expense"] as const).map((t) => (
          <TouchableOpacity key={t} onPress={() => { setType(t); setCategoryId(""); }}
            style={[styles.tab, type === t && styles.activeTab]}>
            <Text style={[styles.tabText, type === t && styles.activeTabText]}>
              {t === "income" ? "수입" : "지출"}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.label}>카테고리</Text>
      <View style={styles.catGrid}>
        {filtered.map((c) => (
          <TouchableOpacity key={c.id} onPress={() => setCategoryId(c.id)}
            style={[styles.catBtn, categoryId === c.id && { backgroundColor: c.color + "22", borderColor: c.color }]}>
            <Text style={styles.catIcon}>{c.icon}</Text>
            <Text style={styles.catLabel}>{c.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.label}>금액 (원)</Text>
      <TextInput style={styles.input} keyboardType="numeric" value={amount} onChangeText={setAmount} placeholder="0" />
      <Text style={styles.label}>메모</Text>
      <TextInput style={styles.input} value={note} onChangeText={setNote} placeholder="선택 사항" />
      <TouchableOpacity style={styles.saveBtn} onPress={handleSave}>
        <Text style={styles.saveText}>저장</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff", padding: 16 },
  toggle: { flexDirection: "row", marginBottom: 16 },
  tab: { flex: 1, padding: 12, alignItems: "center", borderWidth: 1, borderColor: "#ddd", borderRadius: 8, marginHorizontal: 4 },
  activeTab: { backgroundColor: "#2196F3", borderColor: "#2196F3" },
  tabText: { fontSize: 15, color: "#333" },
  activeTabText: { color: "#fff", fontWeight: "600" },
  label: { fontSize: 14, fontWeight: "600", marginTop: 12, marginBottom: 6 },
  catGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  catBtn: { padding: 10, borderWidth: 1, borderColor: "#ddd", borderRadius: 8, alignItems: "center", width: 76 },
  catIcon: { fontSize: 22 },
  catLabel: { fontSize: 11, marginTop: 2 },
  input: { borderWidth: 1, borderColor: "#ddd", borderRadius: 8, padding: 12, fontSize: 16 },
  saveBtn: { backgroundColor: "#4CAF50", padding: 16, borderRadius: 8, alignItems: "center", marginTop: 20 },
  saveText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
```

## App.tsx

```tsx
import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import HomeScreen from "./src/screens/HomeScreen";
import AddTransactionScreen from "./src/screens/AddTransactionScreen";
import StatsScreen from "./src/screens/StatsScreen";

const Tab = createBottomTabNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <Tab.Navigator screenOptions={{ headerShown: true }}>
        <Tab.Screen name="Home" component={HomeScreen} options={{ title: "가계부", tabBarIcon: () => null }} />
        <Tab.Screen name="Add" component={AddTransactionScreen} options={{ title: "추가", tabBarIcon: () => null }} />
        <Tab.Screen name="Stats" component={StatsScreen} options={{ title: "통계", tabBarIcon: () => null }} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
```

`expo start`로 실행하면 수입/지출 기록, 카테고리별 예산 관리, 월간 요약 통계를 사용할 수 있습니다.'''),

    # ═══ 2. 날씨 앱 ═══
    m("React Native로 날씨 앱 만들어줘 전체 코드로",
'''React Native 날씨 앱을 만들어 드릴게요. 현재 날씨, 7일 예보, 위치 기반 자동 갱신을 포함합니다.

## 폴더 구조

```
weather-app/
├── App.tsx
├── src/
│   ├── api/
│   │   └── weather.ts
│   ├── screens/
│   │   └── WeatherScreen.tsx
│   ├── components/
│   │   ├── CurrentWeather.tsx
│   │   ├── ForecastList.tsx
│   │   ├── WeatherIcon.tsx
│   │   └── LoadingView.tsx
│   └── types/
│       └── weather.ts
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "weather-app",
  "version": "1.0.0",
  "scripts": { "start": "expo start" },
  "dependencies": {
    "expo": "~50.0.0",
    "expo-location": "~16.3.0",
    "react-native-safe-area-context": "4.8.2"
  }
}
```

## src/types/weather.ts

```typescript
export interface CurrentWeather {
  temp: number;
  humidity: number;
  windSpeed: number;
  description: string;
  conditionCode: number;
  city: string;
}

export interface DayForecast {
  date: string;
  tempMin: number;
  tempMax: number;
  conditionCode: number;
  description: string;
}
```

## src/api/weather.ts

```typescript
import { CurrentWeather, DayForecast } from "../types/weather";

// Open-Meteo 무료 API — 키 불필요
const BASE = "https://api.open-meteo.com/v1";
const GEO = "https://geocoding-api.open-meteo.com/v1";

export async function fetchWeather(lat: number, lon: number): Promise<{ current: CurrentWeather; forecast: DayForecast[] }> {
  const url = `${BASE}/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code&daily=temperature_2m_max,temperature_2m_min,weather_code&timezone=auto`;
  const res = await fetch(url);
  const data = await res.json();

  // 역 지오코딩으로 도시명 조회
  const geoRes = await fetch(`${GEO}/search?name=&latitude=${lat}&longitude=${lon}&count=1`);
  const geoData = await geoRes.json().catch(() => ({}));
  const city = geoData?.results?.[0]?.name ?? `${lat.toFixed(2)}, ${lon.toFixed(2)}`;

  const current: CurrentWeather = {
    temp: Math.round(data.current.temperature_2m),
    humidity: data.current.relative_humidity_2m,
    windSpeed: data.current.wind_speed_10m,
    description: wmoDescription(data.current.weather_code),
    conditionCode: data.current.weather_code,
    city,
  };

  const forecast: DayForecast[] = data.daily.time.map((date: string, i: number) => ({
    date,
    tempMin: Math.round(data.daily.temperature_2m_min[i]),
    tempMax: Math.round(data.daily.temperature_2m_max[i]),
    conditionCode: data.daily.weather_code[i],
    description: wmoDescription(data.daily.weather_code[i]),
  }));

  return { current, forecast };
}

function wmoDescription(code: number): string {
  const map: Record<number, string> = {
    0: "맑음", 1: "대체로 맑음", 2: "구름 조금", 3: "흐림",
    45: "안개", 48: "짙은 안개",
    51: "이슬비", 53: "이슬비", 55: "강한 이슬비",
    61: "약한 비", 63: "비", 65: "강한 비",
    71: "약한 눈", 73: "눈", 75: "강한 눈",
    80: "소나기", 81: "소나기", 82: "강한 소나기",
    95: "뇌우", 96: "뇌우(우박)", 99: "뇌우(강한 우박)",
  };
  return map[code] ?? "알 수 없음";
}
```

## src/components/WeatherIcon.tsx

```tsx
import React from "react";
import { Text, StyleSheet } from "react-native";

// WMO 날씨 코드 → 이모지 매핑
export default function WeatherIcon({ code, size = 48 }: { code: number; size?: number }) {
  const emoji = getEmoji(code);
  return <Text style={[styles.icon, { fontSize: size }]}>{emoji}</Text>;
}

function getEmoji(code: number): string {
  if (code === 0) return "☀️";
  if (code <= 2) return "🌤️";
  if (code === 3) return "☁️";
  if (code <= 48) return "🌫️";
  if (code <= 55) return "🌦️";
  if (code <= 65) return "🌧️";
  if (code <= 75) return "❄️";
  if (code <= 82) return "🌧️";
  return "⛈️";
}

const styles = StyleSheet.create({
  icon: { textAlign: "center" },
});
```

## src/components/CurrentWeather.tsx

```tsx
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { CurrentWeather as CW } from "../types/weather";
import WeatherIcon from "./WeatherIcon";

export default function CurrentWeatherView({ data }: { data: CW }) {
  return (
    <View style={styles.card}>
      <Text style={styles.city}>{data.city}</Text>
      <WeatherIcon code={data.conditionCode} size={72} />
      <Text style={styles.temp}>{data.temp}°C</Text>
      <Text style={styles.desc}>{data.description}</Text>
      <View style={styles.details}>
        <DetailItem label="습도" value={`${data.humidity}%`} />
        <DetailItem label="풍속" value={`${data.windSpeed} km/h`} />
      </View>
    </View>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.detailItem}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { alignItems: "center", padding: 24, backgroundColor: "#E3F2FD", borderRadius: 16, margin: 16 },
  city: { fontSize: 22, fontWeight: "700", marginBottom: 8 },
  temp: { fontSize: 52, fontWeight: "800", marginVertical: 4 },
  desc: { fontSize: 16, color: "#555" },
  details: { flexDirection: "row", marginTop: 16, gap: 32 },
  detailItem: { alignItems: "center" },
  detailLabel: { fontSize: 12, color: "#888" },
  detailValue: { fontSize: 16, fontWeight: "600", marginTop: 2 },
});
```

## src/components/ForecastList.tsx

```tsx
import React from "react";
import { View, Text, FlatList, StyleSheet } from "react-native";
import { DayForecast } from "../types/weather";
import WeatherIcon from "./WeatherIcon";

export default function ForecastList({ data }: { data: DayForecast[] }) {
  const formatDay = (iso: string) => {
    const d = new Date(iso);
    const days = ["일", "월", "화", "수", "목", "금", "토"];
    return `${d.getMonth() + 1}/${d.getDate()} (${days[d.getDay()]})`;
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>7일 예보</Text>
      <FlatList
        data={data}
        keyExtractor={(i) => i.date}
        renderItem={({ item }) => (
          <View style={styles.row}>
            <Text style={styles.day}>{formatDay(item.date)}</Text>
            <WeatherIcon code={item.conditionCode} size={28} />
            <Text style={styles.tempRange}>{item.tempMin}° / {item.tempMax}°</Text>
            <Text style={styles.desc}>{item.description}</Text>
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  title: { fontSize: 18, fontWeight: "700", marginBottom: 12 },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 12, borderBottomWidth: 1, borderColor: "#eee" },
  day: { width: 90, fontSize: 14, fontWeight: "500" },
  tempRange: { fontSize: 14, fontWeight: "600", marginLeft: 12, width: 80 },
  desc: { fontSize: 12, color: "#888", marginLeft: 8, flex: 1 },
});
```

## src/components/LoadingView.tsx

```tsx
import React from "react";
import { View, Text, ActivityIndicator, StyleSheet } from "react-native";

export default function LoadingView({ message = "날씨 정보 불러오는 중..." }: { message?: string }) {
  return (
    <View style={styles.center}>
      <ActivityIndicator size="large" color="#2196F3" />
      <Text style={styles.text}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  text: { marginTop: 12, fontSize: 14, color: "#666" },
});
```

## src/screens/WeatherScreen.tsx

```tsx
import React, { useEffect, useState, useCallback } from "react";
import { ScrollView, RefreshControl, Alert, StyleSheet } from "react-native";
import * as Location from "expo-location";
import { fetchWeather } from "../api/weather";
import { CurrentWeather, DayForecast } from "../types/weather";
import CurrentWeatherView from "../components/CurrentWeather";
import ForecastList from "../components/ForecastList";
import LoadingView from "../components/LoadingView";

export default function WeatherScreen() {
  const [current, setCurrent] = useState<CurrentWeather | null>(null);
  const [forecast, setForecast] = useState<DayForecast[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") { Alert.alert("권한 필요", "위치 권한을 허용해 주세요"); return; }
      const loc = await Location.getCurrentPositionAsync({});
      const data = await fetchWeather(loc.coords.latitude, loc.coords.longitude);
      setCurrent(data.current);
      setForecast(data.forecast);
    } catch (e) {
      Alert.alert("오류", "날씨 정보를 불러올 수 없습니다");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = () => { setRefreshing(true); load(); };

  if (loading) return <LoadingView />;

  return (
    <ScrollView style={styles.container} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
      {current && <CurrentWeatherView data={current} />}
      <ForecastList data={forecast} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
});
```

## App.tsx

```tsx
import React from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";
import WeatherScreen from "./src/screens/WeatherScreen";

export default function App() {
  return (
    <SafeAreaProvider>
      <WeatherScreen />
    </SafeAreaProvider>
  );
}
```

`expo start`로 실행하면 현재 위치의 날씨와 7일 예보를 Pull-to-Refresh로 갱신할 수 있습니다.'''),

    # ═══ 3. 메모/노트 앱 ═══
    m("React Native로 메모/노트 앱 만들어줘 전체 코드로",
'''React Native 메모/노트 앱을 만들어 드릴게요. 폴더 정리, 검색, 즐겨찾기/핀, 리치 텍스트를 지원합니다.

## 폴더 구조

```
notes-app/
├── App.tsx
├── src/
│   ├── store/
│   │   └── useNoteStore.ts
│   ├── screens/
│   │   ├── NoteListScreen.tsx
│   │   └── NoteEditorScreen.tsx
│   ├── components/
│   │   ├── NoteCard.tsx
│   │   ├── FolderPicker.tsx
│   │   ├── SearchBar.tsx
│   │   └── RichToolbar.tsx
│   └── types/
│       └── note.ts
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "notes-app",
  "version": "1.0.0",
  "scripts": { "start": "expo start" },
  "dependencies": {
    "expo": "~50.0.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/native-stack": "^6.9.17",
    "react-native-screens": "~3.29.0",
    "react-native-safe-area-context": "4.8.2",
    "zustand": "^4.5.0",
    "@react-native-async-storage/async-storage": "1.21.0"
  }
}
```

## src/types/note.ts

```typescript
export interface Note {
  id: string;
  title: string;
  content: string;      // 마크다운 형식 저장 (**bold**, *italic*)
  folder: string;
  pinned: boolean;
  favorite: boolean;
  createdAt: string;
  updatedAt: string;
}
```

## src/store/useNoteStore.ts

```typescript
import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Note } from "../types/note";

interface NoteState {
  notes: Note[];
  folders: string[];
  searchQuery: string;
  selectedFolder: string | null;
  setSearchQuery: (q: string) => void;
  setSelectedFolder: (f: string | null) => void;
  addNote: (note: Omit<Note, "id" | "createdAt" | "updatedAt">) => void;
  updateNote: (id: string, updates: Partial<Note>) => void;
  deleteNote: (id: string) => void;
  addFolder: (name: string) => void;
  togglePin: (id: string) => void;
  toggleFavorite: (id: string) => void;
  loadData: () => Promise<void>;
}

const save = async (notes: Note[], folders: string[]) => {
  await AsyncStorage.multiSet([
    ["@notes", JSON.stringify(notes)],
    ["@folders", JSON.stringify(folders)],
  ]);
};

export const useNoteStore = create<NoteState>((set, get) => ({
  notes: [],
  folders: ["기본", "업무", "개인"],
  searchQuery: "",
  selectedFolder: null,
  setSearchQuery: (q) => set({ searchQuery: q }),
  setSelectedFolder: (f) => set({ selectedFolder: f }),
  addNote: (note) => {
    const now = new Date().toISOString();
    const n: Note = { ...note, id: Date.now().toString(), createdAt: now, updatedAt: now };
    const next = [n, ...get().notes];
    set({ notes: next });
    save(next, get().folders);
  },
  updateNote: (id, updates) => {
    const next = get().notes.map((n) => (n.id === id ? { ...n, ...updates, updatedAt: new Date().toISOString() } : n));
    set({ notes: next });
    save(next, get().folders);
  },
  deleteNote: (id) => {
    const next = get().notes.filter((n) => n.id !== id);
    set({ notes: next });
    save(next, get().folders);
  },
  addFolder: (name) => {
    if (get().folders.includes(name)) return;
    const next = [...get().folders, name];
    set({ folders: next });
    save(get().notes, next);
  },
  togglePin: (id) => {
    const note = get().notes.find((n) => n.id === id);
    if (note) get().updateNote(id, { pinned: !note.pinned });
  },
  toggleFavorite: (id) => {
    const note = get().notes.find((n) => n.id === id);
    if (note) get().updateNote(id, { favorite: !note.favorite });
  },
  loadData: async () => {
    const [notesRaw, foldersRaw] = await AsyncStorage.multiGet(["@notes", "@folders"]);
    set({
      notes: notesRaw[1] ? JSON.parse(notesRaw[1]) : [],
      folders: foldersRaw[1] ? JSON.parse(foldersRaw[1]) : ["기본", "업무", "개인"],
    });
  },
}));
```

## src/components/SearchBar.tsx

```tsx
import React from "react";
import { View, TextInput, StyleSheet } from "react-native";

export default function SearchBar({ value, onChange }: { value: string; onChange: (t: string) => void }) {
  return (
    <View style={styles.bar}>
      <TextInput style={styles.input} placeholder="🔍 노트 검색..." value={value}
        onChangeText={onChange} clearButtonMode="while-editing" />
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { paddingHorizontal: 12, paddingVertical: 8 },
  input: { backgroundColor: "#F0F0F0", borderRadius: 10, padding: 12, fontSize: 15 },
});
```

## src/components/FolderPicker.tsx

```tsx
import React from "react";
import { ScrollView, TouchableOpacity, Text, StyleSheet } from "react-native";

interface Props { folders: string[]; selected: string | null; onSelect: (f: string | null) => void }

export default function FolderPicker({ folders, selected, onSelect }: Props) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.row} contentContainerStyle={{ paddingHorizontal: 12 }}>
      <TouchableOpacity onPress={() => onSelect(null)} style={[styles.chip, !selected && styles.active]}>
        <Text style={[styles.label, !selected && styles.activeLabel]}>전체</Text>
      </TouchableOpacity>
      {folders.map((f) => (
        <TouchableOpacity key={f} onPress={() => onSelect(f)} style={[styles.chip, selected === f && styles.active]}>
          <Text style={[styles.label, selected === f && styles.activeLabel]}>{f}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: { maxHeight: 48, marginBottom: 4 },
  chip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20, backgroundColor: "#F0F0F0", marginRight: 8 },
  active: { backgroundColor: "#2196F3" },
  label: { fontSize: 13, color: "#555" },
  activeLabel: { color: "#fff", fontWeight: "600" },
});
```

## src/components/NoteCard.tsx

```tsx
import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Note } from "../types/note";

interface Props { note: Note; onPress: () => void; onLongPress: () => void }

export default function NoteCard({ note, onPress, onLongPress }: Props) {
  const preview = note.content.replace(/\*+/g, "").slice(0, 60);
  return (
    <TouchableOpacity style={styles.card} onPress={onPress} onLongPress={onLongPress}>
      <View style={styles.header}>
        {note.pinned && <Text style={styles.pin}>📌</Text>}
        <Text style={styles.title} numberOfLines={1}>{note.title || "제목 없음"}</Text>
        {note.favorite && <Text style={styles.fav}>⭐</Text>}
      </View>
      <Text style={styles.preview} numberOfLines={2}>{preview}</Text>
      <View style={styles.footer}>
        <Text style={styles.folder}>{note.folder}</Text>
        <Text style={styles.date}>{new Date(note.updatedAt).toLocaleDateString("ko-KR")}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: "#fff", padding: 14, marginHorizontal: 12, marginBottom: 8, borderRadius: 12, elevation: 1, shadowColor: "#000", shadowOpacity: 0.05, shadowRadius: 4 },
  header: { flexDirection: "row", alignItems: "center", marginBottom: 6 },
  pin: { fontSize: 14, marginRight: 4 },
  title: { flex: 1, fontSize: 16, fontWeight: "700" },
  fav: { fontSize: 14 },
  preview: { fontSize: 13, color: "#777", marginBottom: 8 },
  footer: { flexDirection: "row", justifyContent: "space-between" },
  folder: { fontSize: 11, color: "#2196F3", fontWeight: "500" },
  date: { fontSize: 11, color: "#aaa" },
});
```

## src/components/RichToolbar.tsx

```tsx
import React from "react";
import { View, TouchableOpacity, Text, StyleSheet } from "react-native";

// 간단한 마크다운 서식 삽입 툴바
interface Props { onInsert: (prefix: string, suffix: string) => void }

export default function RichToolbar({ onInsert }: Props) {
  const buttons = [
    { label: "B", prefix: "**", suffix: "**" },
    { label: "I", prefix: "*", suffix: "*" },
    { label: "H1", prefix: "# ", suffix: "" },
    { label: "H2", prefix: "## ", suffix: "" },
    { label: "•", prefix: "- ", suffix: "" },
    { label: "□", prefix: "- [ ] ", suffix: "" },
  ];
  return (
    <View style={styles.bar}>
      {buttons.map((b) => (
        <TouchableOpacity key={b.label} style={styles.btn} onPress={() => onInsert(b.prefix, b.suffix)}>
          <Text style={styles.label}>{b.label}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: "row", backgroundColor: "#F8F8F8", paddingVertical: 6, paddingHorizontal: 8, borderTopWidth: 1, borderColor: "#ddd" },
  btn: { paddingHorizontal: 14, paddingVertical: 6, marginRight: 4, borderRadius: 6, backgroundColor: "#E8E8E8" },
  label: { fontSize: 14, fontWeight: "700", color: "#333" },
});
```

## src/screens/NoteListScreen.tsx

```tsx
import React, { useEffect } from "react";
import { View, FlatList, Alert, StyleSheet } from "react-native";
import { useNoteStore } from "../store/useNoteStore";
import NoteCard from "../components/NoteCard";
import SearchBar from "../components/SearchBar";
import FolderPicker from "../components/FolderPicker";

export default function NoteListScreen({ navigation }: any) {
  const { notes, folders, searchQuery, selectedFolder, setSearchQuery, setSelectedFolder, deleteNote, togglePin, toggleFavorite, loadData } = useNoteStore();
  useEffect(() => { loadData(); }, []);

  const filtered = notes
    .filter((n) => !selectedFolder || n.folder === selectedFolder)
    .filter((n) => !searchQuery || n.title.includes(searchQuery) || n.content.includes(searchQuery))
    .sort((a, b) => (a.pinned === b.pinned ? 0 : a.pinned ? -1 : 1));

  const handleLong = (id: string) => {
    Alert.alert("노트 관리", "", [
      { text: "핀 고정/해제", onPress: () => togglePin(id) },
      { text: "즐겨찾기 토글", onPress: () => toggleFavorite(id) },
      { text: "삭제", style: "destructive", onPress: () => deleteNote(id) },
      { text: "취소", style: "cancel" },
    ]);
  };

  return (
    <View style={styles.container}>
      <SearchBar value={searchQuery} onChange={setSearchQuery} />
      <FolderPicker folders={folders} selected={selectedFolder} onSelect={setSelectedFolder} />
      <FlatList data={filtered} keyExtractor={(n) => n.id}
        renderItem={({ item }) => (
          <NoteCard note={item} onPress={() => navigation.navigate("Editor", { noteId: item.id })} onLongPress={() => handleLong(item.id)} />
        )} />
    </View>
  );
}

const styles = StyleSheet.create({ container: { flex: 1, backgroundColor: "#FAFAFA" } });
```

## App.tsx

```tsx
import React from "react";
import { TouchableOpacity, Text } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import NoteListScreen from "./src/screens/NoteListScreen";
import NoteEditorScreen from "./src/screens/NoteEditorScreen";

const Stack = createNativeStackNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="List" component={NoteListScreen}
          options={({ navigation }) => ({
            title: "메모",
            headerRight: () => (
              <TouchableOpacity onPress={() => navigation.navigate("Editor", {})}>
                <Text style={{ fontSize: 28, color: "#2196F3" }}>+</Text>
              </TouchableOpacity>
            ),
          })} />
        <Stack.Screen name="Editor" component={NoteEditorScreen} options={{ title: "편집" }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
```

`expo start`로 실행하면 폴더 분류, 검색, 핀/즐겨찾기, 리치 텍스트 서식을 지원하는 노트 앱을 사용할 수 있습니다.'''),

    # ═══ 4. 운동 기록 앱 ═══
    m("React Native로 운동 기록 앱 만들어줘 전체 코드로",
'''React Native 운동 기록 앱을 만들어 드릴게요. 종목별 세트/횟수/중량 기록, 캘린더 뷰, 개인 기록, 휴식 타이머를 포함합니다.

## 폴더 구조

```
workout-app/
├── App.tsx
├── src/
│   ├── store/
│   │   └── useWorkoutStore.ts
│   ├── screens/
│   │   ├── WorkoutScreen.tsx
│   │   ├── HistoryScreen.tsx
│   │   └── RecordsScreen.tsx
│   ├── components/
│   │   ├── ExercisePicker.tsx
│   │   ├── SetLogger.tsx
│   │   ├── RestTimer.tsx
│   │   └── CalendarView.tsx
│   └── data/
│       └── exercises.ts
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "workout-app",
  "version": "1.0.0",
  "scripts": { "start": "expo start" },
  "dependencies": {
    "expo": "~50.0.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/bottom-tabs": "^6.5.12",
    "react-native-screens": "~3.29.0",
    "react-native-safe-area-context": "4.8.2",
    "zustand": "^4.5.0",
    "@react-native-async-storage/async-storage": "1.21.0"
  }
}
```

## src/data/exercises.ts

```typescript
export interface ExerciseType {
  id: string;
  name: string;
  category: "chest" | "back" | "legs" | "shoulders" | "arms" | "core";
  emoji: string;
}

export const EXERCISES: ExerciseType[] = [
  { id: "squat", name: "스쿼트", category: "legs", emoji: "🦵" },
  { id: "bench", name: "벤치프레스", category: "chest", emoji: "🏋️" },
  { id: "deadlift", name: "데드리프트", category: "back", emoji: "💪" },
  { id: "ohp", name: "오버헤드프레스", category: "shoulders", emoji: "🙆" },
  { id: "row", name: "바벨로우", category: "back", emoji: "🚣" },
  { id: "pullup", name: "풀업", category: "back", emoji: "🧗" },
  { id: "curl", name: "바이셉컬", category: "arms", emoji: "💪" },
  { id: "lunge", name: "런지", category: "legs", emoji: "🦵" },
  { id: "plank", name: "플랭크", category: "core", emoji: "🧘" },
  { id: "dip", name: "딥스", category: "chest", emoji: "⬇️" },
];
```

## src/store/useWorkoutStore.ts

```typescript
import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";

export interface WorkoutSet {
  reps: number;
  weight: number;
}

export interface WorkoutEntry {
  exerciseId: string;
  sets: WorkoutSet[];
}

export interface WorkoutSession {
  id: string;
  date: string; // YYYY-MM-DD
  entries: WorkoutEntry[];
}

interface WorkoutState {
  sessions: WorkoutSession[];
  currentEntries: WorkoutEntry[];
  addSet: (exerciseId: string, set: WorkoutSet) => void;
  removeLastSet: (exerciseId: string) => void;
  saveSession: () => void;
  clearCurrent: () => void;
  loadData: () => Promise<void>;
  getPersonalRecord: (exerciseId: string) => number;
}

export const useWorkoutStore = create<WorkoutState>((set, get) => ({
  sessions: [],
  currentEntries: [],
  addSet: (exerciseId, s) => {
    const entries = [...get().currentEntries];
    const idx = entries.findIndex((e) => e.exerciseId === exerciseId);
    if (idx >= 0) {
      entries[idx] = { ...entries[idx], sets: [...entries[idx].sets, s] };
    } else {
      entries.push({ exerciseId, sets: [s] });
    }
    set({ currentEntries: entries });
  },
  removeLastSet: (exerciseId) => {
    const entries = get().currentEntries.map((e) => {
      if (e.exerciseId !== exerciseId) return e;
      return { ...e, sets: e.sets.slice(0, -1) };
    }).filter((e) => e.sets.length > 0);
    set({ currentEntries: entries });
  },
  saveSession: () => {
    const session: WorkoutSession = {
      id: Date.now().toString(),
      date: new Date().toISOString().slice(0, 10),
      entries: get().currentEntries,
    };
    const next = [session, ...get().sessions];
    set({ sessions: next, currentEntries: [] });
    AsyncStorage.setItem("@sessions", JSON.stringify(next));
  },
  clearCurrent: () => set({ currentEntries: [] }),
  loadData: async () => {
    const raw = await AsyncStorage.getItem("@sessions");
    if (raw) set({ sessions: JSON.parse(raw) });
  },
  getPersonalRecord: (exerciseId) => {
    let max = 0;
    for (const s of get().sessions) {
      for (const e of s.entries) {
        if (e.exerciseId === exerciseId) {
          for (const st of e.sets) {
            if (st.weight > max) max = st.weight;
          }
        }
      }
    }
    return max;
  },
}));
```

## src/components/ExercisePicker.tsx

```tsx
import React from "react";
import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from "react-native";
import { EXERCISES, ExerciseType } from "../data/exercises";

interface Props { selected: string | null; onSelect: (id: string) => void }

export default function ExercisePicker({ selected, onSelect }: Props) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
      {EXERCISES.map((ex) => (
        <TouchableOpacity key={ex.id} onPress={() => onSelect(ex.id)}
          style={[styles.chip, selected === ex.id && styles.active]}>
          <Text style={styles.emoji}>{ex.emoji}</Text>
          <Text style={[styles.name, selected === ex.id && { color: "#fff" }]}>{ex.name}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: { paddingHorizontal: 12, paddingVertical: 8 },
  chip: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: "#F0F0F0", marginRight: 8, alignItems: "center" },
  active: { backgroundColor: "#FF5722" },
  emoji: { fontSize: 22 },
  name: { fontSize: 11, marginTop: 2, color: "#333" },
});
```

## src/components/SetLogger.tsx

```tsx
import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet } from "react-native";
import { useWorkoutStore, WorkoutSet } from "../store/useWorkoutStore";
import { EXERCISES } from "../data/exercises";

interface Props { exerciseId: string }

export default function SetLogger({ exerciseId }: Props) {
  const [reps, setReps] = useState("10");
  const [weight, setWeight] = useState("0");
  const { addSet, removeLastSet, currentEntries, getPersonalRecord } = useWorkoutStore();
  const entry = currentEntries.find((e) => e.exerciseId === exerciseId);
  const ex = EXERCISES.find((e) => e.id === exerciseId);
  const pr = getPersonalRecord(exerciseId);

  const handleAdd = () => {
    addSet(exerciseId, { reps: Number(reps), weight: Number(weight) });
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{ex?.emoji} {ex?.name}</Text>
      {pr > 0 && <Text style={styles.pr}>🏆 개인 기록: {pr}kg</Text>}
      <View style={styles.inputRow}>
        <View style={styles.inputGroup}>
          <Text style={styles.label}>횟수</Text>
          <TextInput style={styles.input} keyboardType="numeric" value={reps} onChangeText={setReps} />
        </View>
        <View style={styles.inputGroup}>
          <Text style={styles.label}>중량(kg)</Text>
          <TextInput style={styles.input} keyboardType="numeric" value={weight} onChangeText={setWeight} />
        </View>
        <TouchableOpacity style={styles.addBtn} onPress={handleAdd}>
          <Text style={styles.addText}>+ 세트</Text>
        </TouchableOpacity>
      </View>
      {entry?.sets.map((s, i) => (
        <View key={i} style={styles.setRow}>
          <Text style={styles.setNum}>세트 {i + 1}</Text>
          <Text style={styles.setText}>{s.weight}kg × {s.reps}회</Text>
        </View>
      ))}
      {(entry?.sets.length ?? 0) > 0 && (
        <TouchableOpacity onPress={() => removeLastSet(exerciseId)}>
          <Text style={styles.undo}>마지막 세트 삭제</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, backgroundColor: "#fff", borderRadius: 12, margin: 12, elevation: 1 },
  title: { fontSize: 18, fontWeight: "700", marginBottom: 4 },
  pr: { fontSize: 13, color: "#FF9800", marginBottom: 8 },
  inputRow: { flexDirection: "row", alignItems: "flex-end", gap: 8, marginBottom: 12 },
  inputGroup: { flex: 1 },
  label: { fontSize: 12, color: "#888", marginBottom: 4 },
  input: { borderWidth: 1, borderColor: "#ddd", borderRadius: 8, padding: 10, fontSize: 16, textAlign: "center" },
  addBtn: { backgroundColor: "#FF5722", paddingHorizontal: 16, paddingVertical: 12, borderRadius: 8 },
  addText: { color: "#fff", fontWeight: "600" },
  setRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 8, borderBottomWidth: 1, borderColor: "#f0f0f0" },
  setNum: { fontSize: 14, color: "#888" },
  setText: { fontSize: 14, fontWeight: "600" },
  undo: { color: "#F44336", textAlign: "center", marginTop: 8, fontSize: 13 },
});
```

## src/components/RestTimer.tsx

```tsx
import React, { useState, useEffect, useRef } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";

// 세트 간 휴식 타이머 (기본 90초)
export default function RestTimer() {
  const [seconds, setSeconds] = useState(90);
  const [running, setRunning] = useState(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (running && seconds > 0) {
      intervalRef.current = setInterval(() => setSeconds((s) => s - 1), 1000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [running, seconds]);

  useEffect(() => {
    if (seconds === 0) setRunning(false);
  }, [seconds]);

  const format = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;
  const reset = (dur: number) => { setSeconds(dur); setRunning(false); };

  return (
    <View style={styles.container}>
      <Text style={styles.label}>⏱️ 휴식 타이머</Text>
      <Text style={[styles.time, seconds === 0 && { color: "#4CAF50" }]}>
        {seconds === 0 ? "GO!" : format(seconds)}
      </Text>
      <View style={styles.row}>
        <TouchableOpacity style={styles.btn} onPress={() => setRunning(!running)}>
          <Text style={styles.btnText}>{running ? "일시정지" : "시작"}</Text>
        </TouchableOpacity>
        {[60, 90, 120].map((d) => (
          <TouchableOpacity key={d} style={styles.presetBtn} onPress={() => reset(d)}>
            <Text style={styles.presetText}>{d}초</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: "center", padding: 16, backgroundColor: "#FFF3E0", borderRadius: 12, margin: 12 },
  label: { fontSize: 14, fontWeight: "600", marginBottom: 4 },
  time: { fontSize: 48, fontWeight: "800", color: "#FF5722", marginVertical: 8 },
  row: { flexDirection: "row", gap: 8 },
  btn: { backgroundColor: "#FF5722", paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8 },
  btnText: { color: "#fff", fontWeight: "600" },
  presetBtn: { backgroundColor: "#FFE0B2", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 8 },
  presetText: { fontSize: 13, fontWeight: "500" },
});
```

## src/components/CalendarView.tsx

```tsx
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { WorkoutSession } from "../store/useWorkoutStore";

// 간단한 월간 캘린더 — 운동한 날 표시
export default function CalendarView({ sessions, month }: { sessions: WorkoutSession[]; month: string }) {
  const year = parseInt(month.slice(0, 4));
  const mon = parseInt(month.slice(5, 7)) - 1;
  const firstDay = new Date(year, mon, 1).getDay();
  const daysInMonth = new Date(year, mon + 1, 0).getDate();
  const workedDays = new Set(sessions.filter((s) => s.date.startsWith(month)).map((s) => parseInt(s.date.slice(8, 10))));

  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{year}년 {mon + 1}월</Text>
      <View style={styles.header}>
        {["일", "월", "화", "수", "목", "금", "토"].map((d) => (
          <Text key={d} style={styles.dayLabel}>{d}</Text>
        ))}
      </View>
      <View style={styles.grid}>
        {cells.map((day, i) => (
          <View key={i} style={[styles.cell, day && workedDays.has(day) && styles.worked]}>
            <Text style={[styles.dayText, day && workedDays.has(day) && { color: "#fff" }]}>
              {day ?? ""}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 12 },
  title: { fontSize: 18, fontWeight: "700", textAlign: "center", marginBottom: 12 },
  header: { flexDirection: "row" },
  dayLabel: { flex: 1, textAlign: "center", fontSize: 12, color: "#888", marginBottom: 4 },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  cell: { width: "14.28%", aspectRatio: 1, justifyContent: "center", alignItems: "center", borderRadius: 20 },
  worked: { backgroundColor: "#FF5722" },
  dayText: { fontSize: 13 },
});
```

## App.tsx

```tsx
import React, { useEffect } from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import WorkoutScreen from "./src/screens/WorkoutScreen";
import HistoryScreen from "./src/screens/HistoryScreen";
import RecordsScreen from "./src/screens/RecordsScreen";
import { useWorkoutStore } from "./src/store/useWorkoutStore";

const Tab = createBottomTabNavigator();

export default function App() {
  const loadData = useWorkoutStore((s) => s.loadData);
  useEffect(() => { loadData(); }, []);

  return (
    <NavigationContainer>
      <Tab.Navigator>
        <Tab.Screen name="Workout" component={WorkoutScreen} options={{ title: "운동", tabBarIcon: () => null }} />
        <Tab.Screen name="History" component={HistoryScreen} options={{ title: "기록", tabBarIcon: () => null }} />
        <Tab.Screen name="Records" component={RecordsScreen} options={{ title: "개인기록", tabBarIcon: () => null }} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
```

`expo start`로 실행하면 운동 종목 선택, 세트/횟수/중량 기록, 휴식 타이머, 월간 캘린더 기록을 사용할 수 있습니다.'''),

    # ═══ 5. 습관 트래커 앱 ═══
    m("React Native로 습관 트래커 앱 만들어줘 전체 코드로",
'''React Native 습관 트래커 앱을 만들어 드릴게요. 습관 등록, 매일 체크, 스트릭, 통계, 알림 시간 설정을 포함합니다.

## 폴더 구조

```
habit-app/
├── App.tsx
├── src/
│   ├── store/
│   │   └── useHabitStore.ts
│   ├── screens/
│   │   ├── TodayScreen.tsx
│   │   ├── StatsScreen.tsx
│   │   └── AddHabitScreen.tsx
│   ├── components/
│   │   ├── HabitCard.tsx
│   │   ├── StreakBadge.tsx
│   │   └── WeeklyChart.tsx
│   └── utils/
│       └── date.ts
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "habit-app",
  "version": "1.0.0",
  "scripts": { "start": "expo start" },
  "dependencies": {
    "expo": "~50.0.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/bottom-tabs": "^6.5.12",
    "react-native-screens": "~3.29.0",
    "react-native-safe-area-context": "4.8.2",
    "zustand": "^4.5.0",
    "@react-native-async-storage/async-storage": "1.21.0"
  }
}
```

## src/utils/date.ts

```typescript
// 날짜 유틸리티
export const today = () => new Date().toISOString().slice(0, 10);

export const getWeekDates = (baseDate = new Date()): string[] => {
  const d = new Date(baseDate);
  const day = d.getDay();
  const monday = new Date(d);
  monday.setDate(d.getDate() - ((day + 6) % 7));
  return Array.from({ length: 7 }, (_, i) => {
    const dt = new Date(monday);
    dt.setDate(monday.getDate() + i);
    return dt.toISOString().slice(0, 10);
  });
};

export const getMonthDates = (year: number, month: number): string[] => {
  const days = new Date(year, month, 0).getDate();
  return Array.from({ length: days }, (_, i) => {
    const d = new Date(year, month - 1, i + 1);
    return d.toISOString().slice(0, 10);
  });
};

export const dayLabel = (iso: string) => {
  const days = ["일", "월", "화", "수", "목", "금", "토"];
  return days[new Date(iso).getDay()];
};
```

## src/store/useHabitStore.ts

```typescript
import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { today } from "../utils/date";

export interface Habit {
  id: string;
  name: string;
  icon: string;
  color: string;
  reminderTime: string | null; // "HH:MM" 형식
  createdAt: string;
}

// completions: { [habitId]: Set<"YYYY-MM-DD"> }
interface HabitState {
  habits: Habit[];
  completions: Record<string, string[]>; // habitId → date[]
  addHabit: (h: Omit<Habit, "id" | "createdAt">) => void;
  deleteHabit: (id: string) => void;
  toggleCompletion: (habitId: string, date?: string) => void;
  isCompleted: (habitId: string, date?: string) => boolean;
  getStreak: (habitId: string) => number;
  loadData: () => Promise<void>;
}

const persist = async (habits: Habit[], completions: Record<string, string[]>) => {
  await AsyncStorage.multiSet([
    ["@habits", JSON.stringify(habits)],
    ["@completions", JSON.stringify(completions)],
  ]);
};

export const useHabitStore = create<HabitState>((set, get) => ({
  habits: [],
  completions: {},
  addHabit: (h) => {
    const habit: Habit = { ...h, id: Date.now().toString(), createdAt: today() };
    const next = [...get().habits, habit];
    set({ habits: next });
    persist(next, get().completions);
  },
  deleteHabit: (id) => {
    const next = get().habits.filter((h) => h.id !== id);
    const comp = { ...get().completions };
    delete comp[id];
    set({ habits: next, completions: comp });
    persist(next, comp);
  },
  toggleCompletion: (habitId, date = today()) => {
    const comp = { ...get().completions };
    const dates = comp[habitId] ?? [];
    if (dates.includes(date)) {
      comp[habitId] = dates.filter((d) => d !== date);
    } else {
      comp[habitId] = [...dates, date];
    }
    set({ completions: comp });
    persist(get().habits, comp);
  },
  isCompleted: (habitId, date = today()) => {
    return (get().completions[habitId] ?? []).includes(date);
  },
  getStreak: (habitId) => {
    const dates = new Set(get().completions[habitId] ?? []);
    let streak = 0;
    const d = new Date();
    while (true) {
      const iso = d.toISOString().slice(0, 10);
      if (!dates.has(iso)) break;
      streak++;
      d.setDate(d.getDate() - 1);
    }
    return streak;
  },
  loadData: async () => {
    const [hRaw, cRaw] = await AsyncStorage.multiGet(["@habits", "@completions"]);
    set({
      habits: hRaw[1] ? JSON.parse(hRaw[1]) : [],
      completions: cRaw[1] ? JSON.parse(cRaw[1]) : {},
    });
  },
}));
```

## src/components/StreakBadge.tsx

```tsx
import React from "react";
import { View, Text, StyleSheet } from "react-native";

// 스트릭 뱃지 — 연속 일수에 따라 불꽃 크기 변화
export default function StreakBadge({ streak }: { streak: number }) {
  if (streak === 0) return null;
  const fire = streak >= 30 ? "🔥🔥🔥" : streak >= 7 ? "🔥🔥" : "🔥";
  return (
    <View style={styles.badge}>
      <Text style={styles.fire}>{fire}</Text>
      <Text style={styles.count}>{streak}일 연속</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { flexDirection: "row", alignItems: "center", backgroundColor: "#FFF3E0", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  fire: { fontSize: 16 },
  count: { fontSize: 12, fontWeight: "700", color: "#FF5722", marginLeft: 4 },
});
```

## src/components/HabitCard.tsx

```tsx
import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Habit, useHabitStore } from "../store/useHabitStore";
import StreakBadge from "./StreakBadge";

interface Props { habit: Habit; onLongPress: () => void }

export default function HabitCard({ habit, onLongPress }: Props) {
  const { isCompleted, toggleCompletion, getStreak } = useHabitStore();
  const done = isCompleted(habit.id);
  const streak = getStreak(habit.id);

  return (
    <TouchableOpacity onPress={() => toggleCompletion(habit.id)} onLongPress={onLongPress}
      style={[styles.card, { borderLeftColor: habit.color, borderLeftWidth: 4 }, done && styles.done]}>
      <View style={styles.row}>
        <Text style={styles.icon}>{habit.icon}</Text>
        <View style={styles.info}>
          <Text style={[styles.name, done && styles.nameStrike]}>{habit.name}</Text>
          {habit.reminderTime && <Text style={styles.time}>⏰ {habit.reminderTime}</Text>}
        </View>
        <View style={styles.right}>
          <StreakBadge streak={streak} />
          <Text style={styles.check}>{done ? "✅" : "⬜"}</Text>
        </View>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: "#fff", padding: 14, marginHorizontal: 12, marginBottom: 8, borderRadius: 12, elevation: 1, shadowColor: "#000", shadowOpacity: 0.05, shadowRadius: 4 },
  done: { backgroundColor: "#F1F8E9" },
  row: { flexDirection: "row", alignItems: "center" },
  icon: { fontSize: 28, marginRight: 12 },
  info: { flex: 1 },
  name: { fontSize: 16, fontWeight: "600" },
  nameStrike: { textDecorationLine: "line-through", color: "#aaa" },
  time: { fontSize: 11, color: "#888", marginTop: 2 },
  right: { alignItems: "flex-end", gap: 4 },
  check: { fontSize: 22 },
});
```

## src/components/WeeklyChart.tsx

```tsx
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { useHabitStore } from "../store/useHabitStore";
import { getWeekDates, dayLabel } from "../utils/date";

// 주간 완료율 차트
export default function WeeklyChart() {
  const { habits, completions } = useHabitStore();
  const week = getWeekDates();
  const total = habits.length || 1;

  const data = week.map((date) => {
    const count = habits.filter((h) => (completions[h.id] ?? []).includes(date)).length;
    return { date, ratio: count / total };
  });

  return (
    <View style={styles.container}>
      <Text style={styles.title}>이번 주 달성률</Text>
      <View style={styles.chart}>
        {data.map((d) => (
          <View key={d.date} style={styles.col}>
            <Text style={styles.pct}>{Math.round(d.ratio * 100)}%</Text>
            <View style={styles.barBg}>
              <View style={[styles.barFill, { height: `${d.ratio * 100}%` }]} />
            </View>
            <Text style={styles.day}>{dayLabel(d.date)}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, margin: 12, backgroundColor: "#fff", borderRadius: 12, elevation: 1 },
  title: { fontSize: 16, fontWeight: "700", marginBottom: 12 },
  chart: { flexDirection: "row", justifyContent: "space-around", height: 120 },
  col: { alignItems: "center", flex: 1 },
  pct: { fontSize: 10, color: "#888", marginBottom: 4 },
  barBg: { flex: 1, width: 18, backgroundColor: "#E8E8E8", borderRadius: 9, overflow: "hidden", justifyContent: "flex-end" },
  barFill: { backgroundColor: "#4CAF50", borderRadius: 9, width: "100%" },
  day: { fontSize: 12, color: "#666", marginTop: 4 },
});
```

## src/screens/TodayScreen.tsx

```tsx
import React, { useEffect } from "react";
import { View, Text, FlatList, Alert, StyleSheet } from "react-native";
import { useHabitStore } from "../store/useHabitStore";
import HabitCard from "../components/HabitCard";
import { today } from "../utils/date";

export default function TodayScreen() {
  const { habits, completions, deleteHabit, loadData } = useHabitStore();
  useEffect(() => { loadData(); }, []);

  const doneCount = habits.filter((h) => (completions[h.id] ?? []).includes(today())).length;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>오늘의 습관</Text>
        <Text style={styles.progress}>{doneCount} / {habits.length} 완료</Text>
      </View>
      <FlatList data={habits} keyExtractor={(h) => h.id}
        renderItem={({ item }) => (
          <HabitCard habit={item} onLongPress={() => {
            Alert.alert("삭제", `"${item.name}"을 삭제할까요?`, [
              { text: "취소", style: "cancel" },
              { text: "삭제", style: "destructive", onPress: () => deleteHabit(item.id) },
            ]);
          }} />
        )}
        ListEmptyComponent={<Text style={styles.empty}>습관을 추가해 보세요!</Text>}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FAFAFA" },
  header: { padding: 16, flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { fontSize: 20, fontWeight: "800" },
  progress: { fontSize: 14, color: "#4CAF50", fontWeight: "600" },
  empty: { textAlign: "center", color: "#aaa", marginTop: 40, fontSize: 15 },
});
```

## src/screens/AddHabitScreen.tsx

```tsx
import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet, Alert } from "react-native";
import { useHabitStore } from "../store/useHabitStore";

const ICONS = ["📚", "🏃", "💧", "🧘", "✍️", "🎵", "💊", "🥗", "😴", "🌅"];
const COLORS = ["#F44336", "#E91E63", "#9C27B0", "#2196F3", "#4CAF50", "#FF9800", "#795548", "#607D8B"];

export default function AddHabitScreen({ navigation }: any) {
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("📚");
  const [color, setColor] = useState("#2196F3");
  const [reminder, setReminder] = useState("");
  const addHabit = useHabitStore((s) => s.addHabit);

  const handleSave = () => {
    if (!name.trim()) return Alert.alert("입력 오류", "습관 이름을 입력하세요");
    addHabit({ name: name.trim(), icon, color, reminderTime: reminder || null });
    navigation.goBack();
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.label}>습관 이름</Text>
      <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="예: 물 8잔 마시기" />
      <Text style={styles.label}>아이콘 선택</Text>
      <View style={styles.grid}>
        {ICONS.map((ic) => (
          <TouchableOpacity key={ic} onPress={() => setIcon(ic)}
            style={[styles.iconBtn, icon === ic && { backgroundColor: color + "33" }]}>
            <Text style={{ fontSize: 28 }}>{ic}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.label}>색상 선택</Text>
      <View style={styles.grid}>
        {COLORS.map((c) => (
          <TouchableOpacity key={c} onPress={() => setColor(c)}
            style={[styles.colorBtn, { backgroundColor: c }, color === c && styles.colorActive]} />
        ))}
      </View>
      <Text style={styles.label}>알림 시간 (선택)</Text>
      <TextInput style={styles.input} value={reminder} onChangeText={setReminder} placeholder="예: 07:00" keyboardType="numbers-and-punctuation" />
      <TouchableOpacity style={[styles.saveBtn, { backgroundColor: color }]} onPress={handleSave}>
        <Text style={styles.saveText}>습관 추가</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff", padding: 16 },
  label: { fontSize: 14, fontWeight: "600", marginTop: 16, marginBottom: 8 },
  input: { borderWidth: 1, borderColor: "#ddd", borderRadius: 8, padding: 12, fontSize: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  iconBtn: { padding: 8, borderRadius: 10, borderWidth: 1, borderColor: "#eee" },
  colorBtn: { width: 36, height: 36, borderRadius: 18 },
  colorActive: { borderWidth: 3, borderColor: "#333" },
  saveBtn: { padding: 16, borderRadius: 8, alignItems: "center", marginTop: 24 },
  saveText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
```

## App.tsx

```tsx
import React from "react";
import { TouchableOpacity, Text } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import TodayScreen from "./src/screens/TodayScreen";
import StatsScreen from "./src/screens/StatsScreen";
import AddHabitScreen from "./src/screens/AddHabitScreen";

const Tab = createBottomTabNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <Tab.Navigator>
        <Tab.Screen name="Today" component={TodayScreen} options={{ title: "오늘", tabBarIcon: () => null }} />
        <Tab.Screen name="Add" component={AddHabitScreen} options={{ title: "추가", tabBarIcon: () => null }} />
        <Tab.Screen name="Stats" component={StatsScreen} options={{ title: "통계", tabBarIcon: () => null }} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
```

`expo start`로 실행하면 습관 등록, 매일 체크, 스트릭 카운터, 주간 달성률 통계를 사용할 수 있습니다.'''),

    # ═══ 6. 레시피 앱 ═══
    m("React Native로 레시피 앱 만들어줘 전체 코드로",
'''React Native 레시피 앱을 만들어 드릴게요. 레시피 목록, 재료 체크리스트, 단계별 조리, 타이머, 즐겨찾기, 재료 검색을 포함합니다.

## 폴더 구조

```
recipe-app/
├── App.tsx
├── src/
│   ├── store/
│   │   └── useRecipeStore.ts
│   ├── screens/
│   │   ├── RecipeListScreen.tsx
│   │   └── RecipeDetailScreen.tsx
│   ├── components/
│   │   ├── RecipeCard.tsx
│   │   ├── IngredientChecklist.tsx
│   │   ├── StepView.tsx
│   │   └── StepTimer.tsx
│   └── data/
│       └── sampleRecipes.ts
├── package.json
└── app.json
```

## package.json

```json
{
  "name": "recipe-app",
  "version": "1.0.0",
  "scripts": { "start": "expo start" },
  "dependencies": {
    "expo": "~50.0.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/native-stack": "^6.9.17",
    "react-native-screens": "~3.29.0",
    "react-native-safe-area-context": "4.8.2",
    "zustand": "^4.5.0",
    "@react-native-async-storage/async-storage": "1.21.0"
  }
}
```

## src/data/sampleRecipes.ts

```typescript
export interface Ingredient {
  name: string;
  amount: string;
}

export interface Step {
  instruction: string;
  timerSeconds: number | null; // null이면 타이머 없음
}

export interface Recipe {
  id: string;
  title: string;
  image: string; // emoji로 대체
  servings: number;
  prepTime: number;  // 분
  cookTime: number;  // 분
  ingredients: Ingredient[];
  steps: Step[];
  tags: string[];
}

export const SAMPLE_RECIPES: Recipe[] = [
  {
    id: "1", title: "김치찌개", image: "🍲", servings: 2, prepTime: 10, cookTime: 20,
    ingredients: [
      { name: "묵은지", amount: "300g" }, { name: "돼지고기 앞다리살", amount: "150g" },
      { name: "두부", amount: "1/2모" }, { name: "대파", amount: "1대" },
      { name: "고춧가루", amount: "1큰술" }, { name: "다진마늘", amount: "1큰술" },
      { name: "참기름", amount: "1큰술" }, { name: "물", amount: "400ml" },
    ],
    steps: [
      { instruction: "돼지고기를 한입 크기로 썰고 참기름에 볶습니다", timerSeconds: 180 },
      { instruction: "묵은지를 넣고 함께 볶아 줍니다", timerSeconds: 120 },
      { instruction: "물을 붓고 고춧가루, 다진마늘을 넣어 끓입니다", timerSeconds: 600 },
      { instruction: "두부를 넣고 5분 더 끓입니다", timerSeconds: 300 },
      { instruction: "대파를 넣고 한소끔 끓여 완성합니다", timerSeconds: 60 },
    ],
    tags: ["한식", "찌개", "매운맛"],
  },
  {
    id: "2", title: "카르보나라", image: "🍝", servings: 2, prepTime: 5, cookTime: 15,
    ingredients: [
      { name: "스파게티면", amount: "200g" }, { name: "베이컨", amount: "100g" },
      { name: "달걀", amount: "2개" }, { name: "파르메산 치즈", amount: "50g" },
      { name: "마늘", amount: "2쪽" }, { name: "올리브오일", amount: "2큰술" },
      { name: "후추", amount: "약간" }, { name: "소금", amount: "약간" },
    ],
    steps: [
      { instruction: "끓는 물에 소금을 넣고 스파게티를 삶습니다", timerSeconds: 480 },
      { instruction: "달걀, 치즈, 후추를 섞어 소스를 만듭니다", timerSeconds: null },
      { instruction: "올리브오일에 마늘과 베이컨을 볶습니다", timerSeconds: 180 },
      { instruction: "삶은 면을 넣고 불을 끈 뒤 소스를 부어 빠르게 섞습니다", timerSeconds: null },
      { instruction: "접시에 담고 치즈와 후추를 뿌려 완성합니다", timerSeconds: null },
    ],
    tags: ["양식", "파스타"],
  },
  {
    id: "3", title: "일본식 카레라이스", image: "🍛", servings: 4, prepTime: 15, cookTime: 30,
    ingredients: [
      { name: "카레 루", amount: "1갑" }, { name: "감자", amount: "2개" },
      { name: "당근", amount: "1개" }, { name: "양파", amount: "2개" },
      { name: "소고기/돼지고기", amount: "200g" }, { name: "물", amount: "800ml" },
      { name: "식용유", amount: "2큰술" }, { name: "밥", amount: "4공기" },
    ],
    steps: [
      { instruction: "야채와 고기를 한입 크기로 썹니다", timerSeconds: null },
      { instruction: "기름을 두르고 고기를 먼저 볶습니다", timerSeconds: 180 },
      { instruction: "양파, 당근, 감자 순으로 넣고 볶습니다", timerSeconds: 180 },
      { instruction: "물을 붓고 강불에서 끓인 뒤 약불로 줄입니다", timerSeconds: 900 },
      { instruction: "불을 끄고 카레 루를 넣어 녹입니다", timerSeconds: null },
      { instruction: "약불에서 5분 더 끓여 완성합니다", timerSeconds: 300 },
    ],
    tags: ["일식", "카레"],
  },
];
```

## src/store/useRecipeStore.ts

```typescript
import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Recipe, SAMPLE_RECIPES } from "../data/sampleRecipes";

interface RecipeState {
  recipes: Recipe[];
  favorites: string[];        // recipe id[]
  searchQuery: string;
  checkedIngredients: Record<string, string[]>; // recipeId → ingredient name[]
  setSearchQuery: (q: string) => void;
  toggleFavorite: (id: string) => void;
  toggleIngredient: (recipeId: string, name: string) => void;
  clearChecked: (recipeId: string) => void;
  loadData: () => Promise<void>;
}

export const useRecipeStore = create<RecipeState>((set, get) => ({
  recipes: SAMPLE_RECIPES,
  favorites: [],
  searchQuery: "",
  checkedIngredients: {},
  setSearchQuery: (q) => set({ searchQuery: q }),
  toggleFavorite: (id) => {
    const favs = get().favorites.includes(id)
      ? get().favorites.filter((f) => f !== id)
      : [...get().favorites, id];
    set({ favorites: favs });
    AsyncStorage.setItem("@recipe_favs", JSON.stringify(favs));
  },
  toggleIngredient: (recipeId, name) => {
    const checked = { ...get().checkedIngredients };
    const list = checked[recipeId] ?? [];
    checked[recipeId] = list.includes(name) ? list.filter((n) => n !== name) : [...list, name];
    set({ checkedIngredients: checked });
  },
  clearChecked: (recipeId) => {
    const checked = { ...get().checkedIngredients };
    delete checked[recipeId];
    set({ checkedIngredients: checked });
  },
  loadData: async () => {
    const raw = await AsyncStorage.getItem("@recipe_favs");
    if (raw) set({ favorites: JSON.parse(raw) });
  },
}));
```

## src/components/RecipeCard.tsx

```tsx
import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Recipe } from "../data/sampleRecipes";
import { useRecipeStore } from "../store/useRecipeStore";

interface Props { recipe: Recipe; onPress: () => void }

export default function RecipeCard({ recipe, onPress }: Props) {
  const { favorites, toggleFavorite } = useRecipeStore();
  const isFav = favorites.includes(recipe.id);

  return (
    <TouchableOpacity style={styles.card} onPress={onPress}>
      <Text style={styles.image}>{recipe.image}</Text>
      <View style={styles.info}>
        <Text style={styles.title}>{recipe.title}</Text>
        <Text style={styles.meta}>
          🕐 {recipe.prepTime + recipe.cookTime}분 · 👤 {recipe.servings}인분
        </Text>
        <View style={styles.tags}>
          {recipe.tags.map((t) => (
            <Text key={t} style={styles.tag}>{t}</Text>
          ))}
        </View>
      </View>
      <TouchableOpacity onPress={() => toggleFavorite(recipe.id)} style={styles.favBtn}>
        <Text style={styles.favIcon}>{isFav ? "❤️" : "🤍"}</Text>
      </TouchableOpacity>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: "row", backgroundColor: "#fff", padding: 14, marginHorizontal: 12, marginBottom: 8, borderRadius: 12, elevation: 1, shadowColor: "#000", shadowOpacity: 0.05, shadowRadius: 4, alignItems: "center" },
  image: { fontSize: 42, marginRight: 14 },
  info: { flex: 1 },
  title: { fontSize: 17, fontWeight: "700" },
  meta: { fontSize: 12, color: "#888", marginTop: 4 },
  tags: { flexDirection: "row", marginTop: 6, gap: 6 },
  tag: { fontSize: 11, backgroundColor: "#FFF3E0", color: "#E65100", paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  favBtn: { padding: 8 },
  favIcon: { fontSize: 22 },
});
```

## src/components/IngredientChecklist.tsx

```tsx
import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Ingredient } from "../data/sampleRecipes";
import { useRecipeStore } from "../store/useRecipeStore";

interface Props { recipeId: string; ingredients: Ingredient[] }

export default function IngredientChecklist({ recipeId, ingredients }: Props) {
  const { checkedIngredients, toggleIngredient } = useRecipeStore();
  const checked = checkedIngredients[recipeId] ?? [];

  return (
    <View style={styles.container}>
      <Text style={styles.title}>재료 체크리스트</Text>
      {ingredients.map((ing) => {
        const isDone = checked.includes(ing.name);
        return (
          <TouchableOpacity key={ing.name} style={styles.row} onPress={() => toggleIngredient(recipeId, ing.name)}>
            <Text style={styles.check}>{isDone ? "☑️" : "⬜"}</Text>
            <Text style={[styles.name, isDone && styles.strike]}>{ing.name}</Text>
            <Text style={styles.amount}>{ing.amount}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  title: { fontSize: 16, fontWeight: "700", marginBottom: 10 },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderBottomWidth: 1, borderColor: "#f0f0f0" },
  check: { fontSize: 20, marginRight: 10 },
  name: { flex: 1, fontSize: 15 },
  strike: { textDecorationLine: "line-through", color: "#aaa" },
  amount: { fontSize: 14, color: "#888", fontWeight: "500" },
});
```

## src/components/StepTimer.tsx

```tsx
import React, { useState, useEffect, useRef } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";

interface Props { seconds: number }

export default function StepTimer({ seconds: initial }: Props) {
  const [seconds, setSeconds] = useState(initial);
  const [running, setRunning] = useState(false);
  const ref = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (running && seconds > 0) {
      ref.current = setInterval(() => setSeconds((s) => s - 1), 1000);
    }
    return () => { if (ref.current) clearInterval(ref.current); };
  }, [running, seconds]);

  useEffect(() => {
    if (seconds === 0 && running) setRunning(false);
  }, [seconds, running]);

  const fmt = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;

  return (
    <View style={styles.timer}>
      <Text style={[styles.time, seconds === 0 && { color: "#4CAF50" }]}>
        {seconds === 0 ? "완료!" : fmt(seconds)}
      </Text>
      <TouchableOpacity style={styles.btn} onPress={() => running ? setRunning(false) : (setSeconds(seconds === 0 ? initial : seconds), setRunning(true))}>
        <Text style={styles.btnText}>{running ? "⏸" : seconds === 0 ? "🔄" : "▶️"}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  timer: { flexDirection: "row", alignItems: "center", backgroundColor: "#E8F5E9", padding: 8, borderRadius: 8, marginTop: 8 },
  time: { fontSize: 20, fontWeight: "700", color: "#FF5722", flex: 1 },
  btn: { padding: 8 },
  btnText: { fontSize: 20 },
});
```

## src/components/StepView.tsx

```tsx
import React, { useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Step } from "../data/sampleRecipes";
import StepTimer from "./StepTimer";

interface Props { steps: Step[] }

export default function StepView({ steps }: Props) {
  const [currentStep, setCurrentStep] = useState(0);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>조리 순서</Text>
      {steps.map((step, i) => (
        <TouchableOpacity key={i} onPress={() => setCurrentStep(i)}
          style={[styles.step, currentStep === i && styles.activeBg]}>
          <View style={[styles.badge, currentStep === i && styles.activeBadge]}>
            <Text style={[styles.badgeText, currentStep === i && { color: "#fff" }]}>{i + 1}</Text>
          </View>
          <View style={styles.content}>
            <Text style={[styles.instruction, currentStep === i && { fontWeight: "600" }]}>
              {step.instruction}
            </Text>
            {step.timerSeconds && currentStep === i && (
              <StepTimer seconds={step.timerSeconds} />
            )}
          </View>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  title: { fontSize: 16, fontWeight: "700", marginBottom: 10 },
  step: { flexDirection: "row", paddingVertical: 12, borderBottomWidth: 1, borderColor: "#f0f0f0" },
  activeBg: { backgroundColor: "#FFF8E1", borderRadius: 8, padding: 12 },
  badge: { width: 28, height: 28, borderRadius: 14, backgroundColor: "#E0E0E0", justifyContent: "center", alignItems: "center", marginRight: 12 },
  activeBadge: { backgroundColor: "#FF5722" },
  badgeText: { fontSize: 13, fontWeight: "700", color: "#666" },
  content: { flex: 1 },
  instruction: { fontSize: 14, lineHeight: 20 },
});
```

## src/screens/RecipeListScreen.tsx

```tsx
import React, { useEffect } from "react";
import { View, FlatList, TextInput, StyleSheet } from "react-native";
import { useRecipeStore } from "../store/useRecipeStore";
import RecipeCard from "../components/RecipeCard";

export default function RecipeListScreen({ navigation }: any) {
  const { recipes, searchQuery, setSearchQuery, loadData } = useRecipeStore();
  useEffect(() => { loadData(); }, []);

  // 재료 이름으로도 검색 가능
  const filtered = recipes.filter((r) => {
    const q = searchQuery.toLowerCase();
    if (!q) return true;
    if (r.title.toLowerCase().includes(q)) return true;
    if (r.tags.some((t) => t.includes(q))) return true;
    if (r.ingredients.some((ing) => ing.name.toLowerCase().includes(q))) return true;
    return false;
  });

  return (
    <View style={styles.container}>
      <TextInput style={styles.search} placeholder="🔍 레시피 또는 재료 검색..." value={searchQuery}
        onChangeText={setSearchQuery} clearButtonMode="while-editing" />
      <FlatList data={filtered} keyExtractor={(r) => r.id}
        renderItem={({ item }) => (
          <RecipeCard recipe={item} onPress={() => navigation.navigate("Detail", { recipeId: item.id })} />
        )} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FAFAFA" },
  search: { backgroundColor: "#fff", margin: 12, padding: 12, borderRadius: 10, fontSize: 15, borderWidth: 1, borderColor: "#eee" },
});
```

## src/screens/RecipeDetailScreen.tsx

```tsx
import React from "react";
import { ScrollView, View, Text, StyleSheet } from "react-native";
import { useRecipeStore } from "../store/useRecipeStore";
import IngredientChecklist from "../components/IngredientChecklist";
import StepView from "../components/StepView";

export default function RecipeDetailScreen({ route }: any) {
  const { recipeId } = route.params;
  const recipe = useRecipeStore((s) => s.recipes.find((r) => r.id === recipeId));
  if (!recipe) return <Text>레시피를 찾을 수 없습니다</Text>;

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.image}>{recipe.image}</Text>
        <Text style={styles.title}>{recipe.title}</Text>
        <Text style={styles.meta}>
          🕐 준비 {recipe.prepTime}분 + 조리 {recipe.cookTime}분 · 👤 {recipe.servings}인분
        </Text>
      </View>
      <IngredientChecklist recipeId={recipe.id} ingredients={recipe.ingredients} />
      <StepView steps={recipe.steps} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  header: { alignItems: "center", padding: 24, backgroundColor: "#FFF8E1" },
  image: { fontSize: 64 },
  title: { fontSize: 24, fontWeight: "800", marginTop: 8 },
  meta: { fontSize: 13, color: "#888", marginTop: 6 },
});
```

## App.tsx

```tsx
import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import RecipeListScreen from "./src/screens/RecipeListScreen";
import RecipeDetailScreen from "./src/screens/RecipeDetailScreen";

const Stack = createNativeStackNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="List" component={RecipeListScreen} options={{ title: "레시피" }} />
        <Stack.Screen name="Detail" component={RecipeDetailScreen} options={{ title: "상세" }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
```

`expo start`로 실행하면 레시피 검색, 재료 체크, 단계별 조리 타이머, 즐겨찾기를 사용할 수 있습니다.'''),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mega_mobile.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"모바일 추가: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
