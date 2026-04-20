"""화랑 AI 앱 디자인 패턴 학습 데이터

React Native, 모바일 UI 패턴, 네이티브 인터랙션, PWA 등.

사용법:
    python scripts/data/build_app_design_patterns.py \
        --output data/sft/app_design_patterns.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 모바일/앱 디자이너 겸 개발자 수준의 어시스턴트입니다.
설명은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ React Native 최신 ═══
    m("React Native 최신 앱 디자인 패턴 알려줘 2025년 기준으로",
'''2025년 React Native 최신 패턴입니다.

```tsx
// ═══ 1. Expo Router (파일 기반 라우팅) ═══
// app/_layout.tsx
import { Stack } from "expo-router";
import { ThemeProvider } from "@react-navigation/native";

export default function RootLayout() {
  return (
    <ThemeProvider value={colorScheme === "dark" ? DarkTheme : DefaultTheme}>
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.bg.primary },
          headerTintColor: colors.text.primary,
          headerShadowVisible: false,
          animation: "slide_from_right",
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="modal"
          options={{ presentation: "modal", animation: "slide_from_bottom" }}
        />
      </Stack>
    </ThemeProvider>
  );
}

// app/(tabs)/_layout.tsx - 탭 네비게이션
import { Tabs } from "expo-router";

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: "#3b82f6",
        tabBarInactiveTintColor: "#9ca3af",
        tabBarStyle: {
          borderTopWidth: 0,
          elevation: 0,
          backgroundColor: colors.bg.primary,
          paddingBottom: 8,
          height: 60,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "홈",
          tabBarIcon: ({ color, size }) => <HomeIcon color={color} size={size} />,
        }}
      />
      <Tabs.Screen name="chat" options={{ title: "채팅", tabBarIcon: ChatIcon }} />
      <Tabs.Screen name="search" options={{ title: "검색", tabBarIcon: SearchIcon }} />
      <Tabs.Screen name="profile" options={{ title: "프로필", tabBarIcon: UserIcon }} />
    </Tabs>
  );
}

// ═══ 2. 모바일 최적화 리스트 (FlashList) ═══
import { FlashList } from "@shopify/flash-list";
import { RefreshControl } from "react-native";

function ChatList() {
  const [refreshing, setRefreshing] = useState(false);
  const { data, fetchNextPage, hasNextPage } = useInfiniteQuery({...});

  const chats = data?.pages.flatMap((page) => page.chats) ?? [];

  return (
    <FlashList
      data={chats}
      renderItem={({ item }) => <ChatItem chat={item} />}
      estimatedItemSize={80}
      keyExtractor={(item) => item.id}
      // 당겨서 새로고침
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
      // 무한 스크롤
      onEndReached={() => hasNextPage && fetchNextPage()}
      onEndReachedThreshold={0.5}
      // 구분선
      ItemSeparatorComponent={() => (
        <View className="ml-16 h-px bg-gray-200 dark:bg-gray-700" />
      )}
      // 빈 상태
      ListEmptyComponent={<EmptyState message="대화가 없습니다" />}
      // 스크롤 최적화
      removeClippedSubviews
    />
  );
}

// ═══ 3. 바텀 시트 (Bottom Sheet) ═══
import BottomSheet, { BottomSheetView, BottomSheetBackdrop } from "@gorhom/bottom-sheet";

function ActionSheet() {
  const bottomSheetRef = useRef<BottomSheet>(null);
  const snapPoints = useMemo(() => ["25%", "50%", "90%"], []);

  return (
    <BottomSheet
      ref={bottomSheetRef}
      snapPoints={snapPoints}
      enablePanDownToClose
      backdropComponent={(props) => (
        <BottomSheetBackdrop {...props} disappearsOnIndex={-1} appearsOnIndex={0} opacity={0.5} />
      )}
      handleIndicatorStyle={{ backgroundColor: "#9ca3af", width: 40 }}
      backgroundStyle={{
        backgroundColor: colors.bg.primary,
        borderRadius: 24,
      }}
    >
      <BottomSheetView className="p-6">
        <Text className="text-xl font-bold mb-4">옵션</Text>
        <TouchableOpacity className="flex-row items-center gap-3 py-3">
          <EditIcon className="text-blue-500" />
          <Text className="text-base">수정</Text>
        </TouchableOpacity>
        <TouchableOpacity className="flex-row items-center gap-3 py-3">
          <ShareIcon className="text-green-500" />
          <Text className="text-base">공유</Text>
        </TouchableOpacity>
        <TouchableOpacity className="flex-row items-center gap-3 py-3">
          <TrashIcon className="text-red-500" />
          <Text className="text-base text-red-500">삭제</Text>
        </TouchableOpacity>
      </BottomSheetView>
    </BottomSheet>
  );
}

// ═══ 4. 제스처 인터랙션 (Swipe to Delete) ═══
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, {
  useSharedValue, useAnimatedStyle, withSpring, runOnJS,
} from "react-native-reanimated";

function SwipeableItem({ item, onDelete }: Props) {
  const translateX = useSharedValue(0);

  const panGesture = Gesture.Pan()
    .onUpdate((e) => { translateX.value = Math.min(0, e.translationX); })
    .onEnd((e) => {
      if (e.translationX < -100) {
        translateX.value = withSpring(-200);
        runOnJS(onDelete)(item.id);
      } else {
        translateX.value = withSpring(0);
      }
    });

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: translateX.value }],
  }));

  return (
    <View>
      {/* 삭제 배경 */}
      <View className="absolute inset-y-0 right-0 w-24 bg-red-500 items-center justify-center">
        <TrashIcon className="text-white" />
      </View>

      {/* 스와이프 가능한 아이템 */}
      <GestureDetector gesture={panGesture}>
        <Animated.View style={animatedStyle} className="bg-white dark:bg-gray-800 p-4">
          <Text>{item.title}</Text>
        </Animated.View>
      </GestureDetector>
    </View>
  );
}
```

React Native 2025 핵심:
- **Expo Router**: 파일 기반 라우팅 (Next.js와 유사)
- **FlashList**: 고성능 리스트 (FlatList 대체)
- **Reanimated 3**: 네이티브 애니메이션
- **NativeWind**: Tailwind CSS for RN
- **Bottom Sheet**: iOS 스타일 모달'''),

    # ═══ 모바일 UI 패턴 ═══
    m("모바일 앱 UI 디자인 패턴 알려줘",
'''모바일 앱의 핵심 UI 패턴입니다.

```tsx
// ═══ 1. 풀 투 리프레시 + 스켈레톤 ═══
function FeedScreen() {
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["feed"],
    queryFn: fetchFeed,
  });

  if (isLoading) return <FeedSkeleton />;

  return (
    <ScrollView
      refreshControl={
        <RefreshControl
          refreshing={isRefetching}
          onRefresh={refetch}
          tintColor="#3b82f6"
        />
      }
    >
      {data?.map((item) => (
        <FeedCard key={item.id} item={item} />
      ))}
    </ScrollView>
  );
}

// 스켈레톤 (모바일)
function FeedSkeleton() {
  return (
    <View className="p-4 gap-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <View key={i} className="gap-3">
          <View className="flex-row items-center gap-3">
            <View className="h-10 w-10 rounded-full bg-gray-200 dark:bg-gray-700 animate-pulse" />
            <View className="gap-1">
              <View className="h-3 w-24 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
              <View className="h-2 w-16 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
            </View>
          </View>
          <View className="h-48 rounded-xl bg-gray-200 dark:bg-gray-700 animate-pulse" />
        </View>
      ))}
    </View>
  );
}

// ═══ 2. 검색 바 (헤더 통합) ═══
function SearchHeader() {
  const scrollY = useSharedValue(0);
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 300);

  const headerStyle = useAnimatedStyle(() => ({
    height: interpolate(scrollY.value, [0, 100], [120, 60], Extrapolation.CLAMP),
    opacity: interpolate(scrollY.value, [0, 80], [1, 0.8]),
  }));

  return (
    <Animated.View style={headerStyle} className="bg-white dark:bg-gray-900 px-4 pb-3 justify-end">
      <View className="flex-row items-center bg-gray-100 dark:bg-gray-800 rounded-xl px-4 h-10">
        <SearchIcon className="text-gray-400 mr-2" size={18} />
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="검색..."
          placeholderTextColor="#9ca3af"
          className="flex-1 text-base"
          returnKeyType="search"
        />
        {query.length > 0 && (
          <TouchableOpacity onPress={() => setQuery("")}>
            <XCircleIcon className="text-gray-400" size={18} />
          </TouchableOpacity>
        )}
      </View>
    </Animated.View>
  );
}

// ═══ 3. 카드 디자인 ═══
function ProductCard({ product }: { product: Product }) {
  return (
    <Pressable
      className="rounded-2xl bg-white dark:bg-gray-800 overflow-hidden active:scale-[0.98] transition-transform"
      style={{
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 8,
        elevation: 3,
      }}
    >
      {/* 이미지 */}
      <View className="relative aspect-square">
        <Image
          source={{ uri: product.image }}
          className="w-full h-full"
          contentFit="cover"
        />
        {/* 뱃지 */}
        {product.isNew && (
          <View className="absolute top-3 left-3 bg-blue-600 rounded-full px-2.5 py-0.5">
            <Text className="text-xs font-bold text-white">NEW</Text>
          </View>
        )}
        {/* 찜 버튼 */}
        <TouchableOpacity className="absolute top-3 right-3 h-8 w-8 rounded-full bg-white/80 items-center justify-center">
          <HeartIcon className={product.liked ? "text-red-500 fill-red-500" : "text-gray-400"} size={18} />
        </TouchableOpacity>
      </View>

      {/* 정보 */}
      <View className="p-3">
        <Text className="text-sm text-gray-500">{product.brand}</Text>
        <Text className="font-medium mt-0.5" numberOfLines={2}>{product.name}</Text>
        <View className="flex-row items-baseline gap-2 mt-2">
          {product.discount > 0 && (
            <Text className="text-sm font-bold text-red-500">{product.discount}%</Text>
          )}
          <Text className="text-lg font-bold">
            {product.price.toLocaleString()}원
          </Text>
          {product.originalPrice > product.price && (
            <Text className="text-sm text-gray-400 line-through">
              {product.originalPrice.toLocaleString()}
            </Text>
          )}
        </View>
        {/* 평점 */}
        <View className="flex-row items-center gap-1 mt-1.5">
          <StarIcon className="text-yellow-400" size={14} fill="#facc15" />
          <Text className="text-sm text-gray-500">{product.rating}</Text>
          <Text className="text-sm text-gray-400">({product.reviewCount})</Text>
        </View>
      </View>
    </Pressable>
  );
}

// ═══ 4. 프로필 헤더 (패럴랙스) ═══
function ProfileHeader({ user }: { user: User }) {
  return (
    <View className="items-center py-8 bg-gradient-to-b from-blue-600 to-blue-700">
      {/* 아바타 */}
      <View className="relative">
        <Image
          source={{ uri: user.avatar }}
          className="h-24 w-24 rounded-full border-4 border-white"
        />
        <TouchableOpacity className="absolute bottom-0 right-0 h-8 w-8 rounded-full bg-blue-500 border-2 border-white items-center justify-center">
          <CameraIcon className="text-white" size={14} />
        </TouchableOpacity>
      </View>

      <Text className="mt-3 text-xl font-bold text-white">{user.name}</Text>
      <Text className="text-sm text-blue-200">{user.email}</Text>

      {/* 통계 */}
      <View className="flex-row gap-8 mt-6">
        {[
          { label: "게시글", value: user.postCount },
          { label: "팔로워", value: user.followerCount },
          { label: "팔로잉", value: user.followingCount },
        ].map((stat) => (
          <View key={stat.label} className="items-center">
            <Text className="text-xl font-bold text-white">{stat.value}</Text>
            <Text className="text-xs text-blue-200">{stat.label}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

// ═══ 5. 설정 화면 ═══
function SettingsScreen() {
  return (
    <ScrollView className="flex-1 bg-gray-50 dark:bg-gray-900">
      <SettingsSection title="계정">
        <SettingsItem icon={<UserIcon />} title="프로필 수정" onPress={() => {}} showArrow />
        <SettingsItem icon={<LockIcon />} title="비밀번호 변경" onPress={() => {}} showArrow />
        <SettingsItem icon={<BellIcon />} title="알림 설정" onPress={() => {}} showArrow />
      </SettingsSection>

      <SettingsSection title="앱">
        <SettingsItem
          icon={<MoonIcon />}
          title="다크 모드"
          right={<AnimatedToggle checked={darkMode} onChange={setDarkMode} />}
        />
        <SettingsItem
          icon={<GlobeIcon />}
          title="언어"
          right={<Text className="text-gray-500">한국어</Text>}
          onPress={() => {}}
          showArrow
        />
      </SettingsSection>

      <SettingsSection title="기타">
        <SettingsItem icon={<InfoIcon />} title="버전" right={<Text className="text-gray-500">1.0.0</Text>} />
        <SettingsItem icon={<LogOutIcon />} title="로그아웃" titleColor="text-red-500" onPress={logout} />
      </SettingsSection>
    </ScrollView>
  );
}

function SettingsItem({ icon, title, right, onPress, showArrow, titleColor }: SettingsItemProps) {
  return (
    <TouchableOpacity
      onPress={onPress}
      className="flex-row items-center justify-between bg-white dark:bg-gray-800 px-4 py-3.5"
    >
      <View className="flex-row items-center gap-3">
        <View className="h-8 w-8 rounded-lg bg-gray-100 dark:bg-gray-700 items-center justify-center">
          {icon}
        </View>
        <Text className={cn("text-base", titleColor || "text-gray-900 dark:text-white")}>{title}</Text>
      </View>
      <View className="flex-row items-center gap-2">
        {right}
        {showArrow && <ChevronRightIcon className="text-gray-400" size={18} />}
      </View>
    </TouchableOpacity>
  );
}
```

모바일 UI 핵심 패턴:
1. **탭 바**: 하단 3-5개 메인 기능
2. **Pull to Refresh**: 당겨서 새로고침
3. **Bottom Sheet**: iOS 스타일 옵션 시트
4. **Swipe Actions**: 밀어서 삭제/보관
5. **Floating Action Button**: 주요 액션
6. **설정 그룹**: 섹션별 토글/링크'''),

    # ═══ PWA 패턴 ═══
    m("PWA 프로그레시브 웹 앱 만드는 방법 알려줘",
'''PWA로 앱 같은 웹 경험을 제공합니다.

```typescript
// ═══ 1. Service Worker 등록 ═══
// public/sw.js

const CACHE_NAME = "hwarang-v1";
const STATIC_ASSETS = [
  "/",
  "/offline",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

// 설치: 정적 자산 캐시
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// 활성화: 이전 캐시 정리
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// 페치: 네트워크 우선, 실패 시 캐시
self.addEventListener("fetch", (event) => {
  // API 요청은 네트워크만
  if (event.request.url.includes("/api/")) {
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(JSON.stringify({ error: "오프라인" }), {
          headers: { "Content-Type": "application/json" },
          status: 503,
        })
      )
    );
    return;
  }

  // 정적 자산: 캐시 우선
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        // 새 자산 캐시
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      });
    }).catch(() => caches.match("/offline"))
  );
});

// 푸시 알림
self.addEventListener("push", (event) => {
  const data = event.data?.json() ?? { title: "알림", body: "새 메시지" };
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/badge-72.png",
      vibrate: [100, 50, 100],
      data: { url: data.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url)
  );
});
```

```json
// public/manifest.json
{
  "name": "화랑 AI",
  "short_name": "화랑",
  "description": "한국형 AI 어시스턴트",
  "start_url": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#ffffff",
  "theme_color": "#3b82f6",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/icons/icon-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ],
  "screenshots": [
    { "src": "/screenshots/wide.png", "sizes": "1280x720", "form_factor": "wide" },
    { "src": "/screenshots/narrow.png", "sizes": "750x1334", "form_factor": "narrow" }
  ]
}
```

```tsx
// ═══ Next.js PWA 설정 ═══
// app/layout.tsx
export const metadata = {
  manifest: "/manifest.json",
  themeColor: "#3b82f6",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "화랑 AI",
  },
};

// 설치 프롬프트
"use client";
function InstallPrompt() {
  const [installPrompt, setInstallPrompt] = useState<any>(null);
  const [isInstalled, setIsInstalled] = useState(false);

  useEffect(() => {
    // 설치 가능 이벤트 캐치
    const handler = (e: Event) => {
      e.preventDefault();
      setInstallPrompt(e);
    };
    window.addEventListener("beforeinstallprompt", handler);

    // 이미 설치 확인
    if (window.matchMedia("(display-mode: standalone)").matches) {
      setIsInstalled(true);
    }

    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  if (isInstalled || !installPrompt) return null;

  return (
    <div className="fixed bottom-20 left-4 right-4 z-50 rounded-2xl bg-white p-4 shadow-2xl border dark:bg-gray-800 md:left-auto md:right-6 md:w-80">
      <div className="flex items-start gap-3">
        <img src="/icons/icon-192.png" className="h-12 w-12 rounded-xl" />
        <div className="flex-1">
          <h3 className="font-bold">화랑 AI 설치</h3>
          <p className="text-sm text-gray-500">홈 화면에 추가하면 더 빠르게 사용할 수 있어요</p>
        </div>
      </div>
      <div className="flex gap-2 mt-3">
        <button
          onClick={() => setInstallPrompt(null)}
          className="flex-1 rounded-lg border py-2 text-sm"
        >
          나중에
        </button>
        <button
          onClick={async () => {
            await installPrompt.prompt();
            setInstallPrompt(null);
          }}
          className="flex-1 rounded-lg bg-blue-600 py-2 text-sm text-white"
        >
          설치
        </button>
      </div>
    </div>
  );
}

// 오프라인 감지
function OfflineIndicator() {
  const [isOnline, setIsOnline] = useState(true);

  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => setIsOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    setIsOnline(navigator.onLine);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  if (isOnline) return null;

  return (
    <div className="fixed top-0 left-0 right-0 bg-yellow-500 py-1 text-center text-sm font-medium text-white z-50">
      오프라인 상태입니다
    </div>
  );
}
```

PWA 체크리스트:
- [ ] `manifest.json` (이름, 아이콘, 색상)
- [ ] Service Worker (캐싱, 오프라인)
- [ ] HTTPS 필수
- [ ] 반응형 디자인
- [ ] 아이콘 192px + 512px + maskable
- [ ] 설치 프롬프트
- [ ] 오프라인 폴백 페이지
- [ ] 푸시 알림 (선택)'''),

    # ═══ 앱 내비게이션 패턴 ═══
    m("앱 내비게이션 패턴 종류 알려줘",
'''모바일 앱의 주요 내비게이션 패턴입니다.

```
═══ 1. 탭 바 (Bottom Tab) ═══
가장 일반적. 3-5개 주요 기능.

┌──────────────────────┐
│                      │
│    메인 콘텐츠       │
│                      │
├──────────────────────┤
│ 🏠  💬  🔍  👤     │  ← 하단 탭 바
└──────────────────────┘

사용: 카카오톡, 인스타그램, 네이버

═══ 2. 사이드 드로어 (Drawer) ═══
많은 메뉴를 숨겨놓음. 햄버거 메뉴.

┌──┬───────────────────┐
│  │                   │
│메│    메인 콘텐츠     │
│뉴│                   │
│  │                   │
│  │                   │
└──┴───────────────────┘
← 왼쪽에서 슬라이드

사용: Gmail, 설정 앱

═══ 3. 스택 (Stack) ═══
화면 위에 화면을 쌓음. 뒤로 가기.

[A] → [B] → [C] → [D]
          ← 뒤로 가기

사용: 모든 상세 페이지, 설정 깊이

═══ 4. 탭 + 스택 (하이브리드) ═══
탭 바 + 각 탭 내 스택. 가장 일반적인 조합.

홈 탭: 홈 → 상품 상세 → 리뷰 → 작성
채팅 탭: 목록 → 채팅방 → 프로필
마이 탭: 프로필 → 설정 → 알림 설정
```

```tsx
// Expo Router로 구현
// app/
// ├── (tabs)/
// │   ├── _layout.tsx      → 탭 바
// │   ├── index.tsx         → 홈 탭
// │   ├── chat/
// │   │   ├── _layout.tsx   → 채팅 스택
// │   │   ├── index.tsx     → 채팅 목록
// │   │   └── [id].tsx      → 채팅방
// │   ├── search.tsx        → 검색 탭
// │   └── profile/
// │       ├── _layout.tsx   → 프로필 스택
// │       ├── index.tsx     → 프로필
// │       └── settings.tsx  → 설정
// ├── modal.tsx             → 모달
// └── _layout.tsx           → 루트 레이아웃

// 공유 전환 애니메이션 (Shared Element)
import { SharedTransition } from "react-native-reanimated";

function ProductList() {
  return (
    <FlatList
      data={products}
      renderItem={({ item }) => (
        <Link href={`/product/${item.id}`} asChild>
          <Pressable>
            <Animated.Image
              source={{ uri: item.image }}
              sharedTransitionTag={`product-${item.id}`}
              className="h-48 w-full rounded-xl"
            />
          </Pressable>
        </Link>
      )}
    />
  );
}

function ProductDetail({ id }: { id: string }) {
  return (
    <Animated.Image
      source={{ uri: product.image }}
      sharedTransitionTag={`product-${id}`}
      className="h-72 w-full"
    />
  );
}
```

내비게이션 설계 원칙:
1. **3탭 규칙**: 어떤 화면이든 3번 이내에 도달
2. **뒤로 가기**: 항상 이전 화면으로 돌아갈 수 있어야 함
3. **탭 유지**: 탭 전환 시 각 탭의 상태 유지
4. **모달 vs 스택**: 독립 작업=모달, 계층 깊이=스택
5. **딥링크**: URL로 특정 화면 직접 접근 가능'''),

    # ═══ 앱 UX 패턴 ═══
    m("모바일 앱 UX 디자인 패턴 알려줘 온보딩 포함",
'''모바일 앱의 핵심 UX 패턴입니다.

```tsx
// ═══ 1. 온보딩 (첫 실행 가이드) ═══
function OnboardingScreen() {
  const [currentPage, setCurrentPage] = useState(0);
  const flatListRef = useRef<FlatList>(null);

  const pages = [
    {
      title: "AI와 대화하세요",
      description: "한국어에 최적화된 AI가 코딩, 디자인, 문서 작성을 도와드립니다.",
      image: require("./assets/onboarding-1.png"),
      color: "#3b82f6",
    },
    {
      title: "어디서든 사용하세요",
      description: "웹, 앱, VS Code에서 동일한 경험을 제공합니다.",
      image: require("./assets/onboarding-2.png"),
      color: "#8b5cf6",
    },
    {
      title: "시작할 준비가 됐나요?",
      description: "지금 바로 무료로 시작해보세요.",
      image: require("./assets/onboarding-3.png"),
      color: "#06b6d4",
    },
  ];

  return (
    <View className="flex-1">
      <FlatList
        ref={flatListRef}
        data={pages}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={(e) => {
          setCurrentPage(Math.round(e.nativeEvent.contentOffset.x / screenWidth));
        }}
        renderItem={({ item }) => (
          <View className="w-screen items-center justify-center px-8" style={{ backgroundColor: item.color }}>
            <Image source={item.image} className="h-64 w-64" resizeMode="contain" />
            <Text className="mt-8 text-3xl font-bold text-white text-center">
              {item.title}
            </Text>
            <Text className="mt-4 text-base text-white/80 text-center">
              {item.description}
            </Text>
          </View>
        )}
      />

      {/* 인디케이터 + 버튼 */}
      <View className="absolute bottom-12 left-0 right-0 px-8">
        {/* 페이지 인디케이터 */}
        <View className="flex-row justify-center gap-2 mb-8">
          {pages.map((_, i) => (
            <View
              key={i}
              className={cn(
                "h-2 rounded-full transition-all",
                i === currentPage ? "w-8 bg-white" : "w-2 bg-white/40"
              )}
            />
          ))}
        </View>

        {currentPage === pages.length - 1 ? (
          <TouchableOpacity
            onPress={() => router.replace("/login")}
            className="bg-white rounded-2xl py-4"
          >
            <Text className="text-center text-lg font-bold" style={{ color: pages[currentPage].color }}>
              시작하기
            </Text>
          </TouchableOpacity>
        ) : (
          <View className="flex-row justify-between">
            <TouchableOpacity onPress={() => router.replace("/login")}>
              <Text className="text-white/70 text-base">건너뛰기</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => {
                flatListRef.current?.scrollToIndex({ index: currentPage + 1 });
              }}
            >
              <Text className="text-white text-base font-bold">다음</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>
    </View>
  );
}

// ═══ 2. 빈 상태 (Empty State) ═══
function EmptyState({ type }: { type: "chat" | "search" | "error" | "offline" }) {
  const config = {
    chat: {
      icon: <ChatIcon className="text-gray-300" size={64} />,
      title: "대화가 없습니다",
      description: "새 대화를 시작해보세요",
      action: { label: "새 대화", onPress: startNewChat },
    },
    search: {
      icon: <SearchIcon className="text-gray-300" size={64} />,
      title: "검색 결과가 없습니다",
      description: "다른 키워드로 검색해보세요",
      action: null,
    },
    error: {
      icon: <AlertIcon className="text-red-300" size={64} />,
      title: "오류가 발생했습니다",
      description: "잠시 후 다시 시도해주세요",
      action: { label: "다시 시도", onPress: retry },
    },
    offline: {
      icon: <WifiOffIcon className="text-gray-300" size={64} />,
      title: "인터넷에 연결되지 않았습니다",
      description: "Wi-Fi 또는 모바일 데이터를 확인해주세요",
      action: null,
    },
  };

  const { icon, title, description, action } = config[type];

  return (
    <View className="flex-1 items-center justify-center px-8">
      {icon}
      <Text className="mt-6 text-xl font-bold text-gray-900 dark:text-white">
        {title}
      </Text>
      <Text className="mt-2 text-center text-gray-500">
        {description}
      </Text>
      {action && (
        <TouchableOpacity
          onPress={action.onPress}
          className="mt-6 rounded-xl bg-blue-600 px-6 py-3"
        >
          <Text className="font-semibold text-white">{action.label}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

// ═══ 3. 햅틱 피드백 ═══
import * as Haptics from "expo-haptics";

// 가벼운 탭
const onButtonPress = () => {
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
};

// 성공
const onSuccess = () => {
  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
};

// 에러
const onError = () => {
  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
};

// 토글 전환
const onToggle = () => {
  Haptics.selectionAsync();
};
```

모바일 UX 핵심:
1. **온보딩**: 3페이지 이하, 건너뛰기 가능
2. **빈 상태**: 안내 + 행동 유도 (CTA)
3. **로딩**: 스켈레톤 > 스피너
4. **햅틱**: 터치 피드백 (성공, 에러, 선택)
5. **토스트**: 짧은 알림 (하단)
6. **당겨서 새로고침**: 직관적 데이터 갱신'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/app_design_patterns.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 앱 디자인 패턴 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  앱 디자인 패턴: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
