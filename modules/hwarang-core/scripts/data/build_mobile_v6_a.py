"""화랑 LoRA v6 — Mobile (Flutter + React Native) 풀 워크플로우 800 샘플.

핵심 원칙:
- 알고리즘 generator 만 사용 (hardcoded 50 패턴 이하)
- 패턴 list × generator 함수 × random.choice → 800 곱
- 단순 코드 작성이 아닌 풀 사이클 (read deps → write → build → 에러 → fix → 재빌드)
- 각 샘플 9~13 turn (의미 있는 multi-turn tool calling)
"""
import random
import json
import os
import argparse
from build_tools_multiturn import m, sys as _sys, user, assistant, tool, tc, TOOLS_DESC


def syss():
    return _sys()


random.seed(2050)


# ============================================================
# 다양성 변수 (random.choice 로 표현 다양화)
# ============================================================

INTENT_PREFIXES = [
    "새로",
    "기존 코드에",
    "기존 setState 대신",
    "Riverpod 에서 Provider 로 마이그레이션해서",
    "이 프로젝트에",
    "초보자도 이해되게",
    "프로덕션 수준으로",
]

USER_TONES = [
    "{X} 만들어줘",
    "{X} 좀 만들 수 있어?",
    "{X} 추가해",
    "{X} 작성해줘",
    "{X} 구현해주세요",
    "{X} 짜줘",
]

DEVICE_TARGETS = [
    "iOS",
    "Android",
    "iOS + Android 둘 다",
    "iPad 전용",
    "Android tablet",
    "에뮬레이터",
    "실 기기",
]

WRAP_UP_PHRASES = [
    "✓ {task} 완성. {fix} 적용해서 일반적 함정도 회피했습니다.",
    "{task} 빌드 성공. 핵심 포인트: {fix}.",
    "완료했습니다. 추후 같은 에러 만나면 → {fix}.",
    "{task} 동작 확인. 학습 포인트: {fix}.",
    "✓ 완료. 이 패턴은 {device} 에서 검증된 구성입니다.",
]


def vary_user_msg(task: str) -> str:
    """user 메시지 다양화 — intent prefix + tone template + device 가끔."""
    intent = random.choice(INTENT_PREFIXES)
    tone = random.choice(USER_TONES)
    base = tone.format(X=f"{intent} {task}")
    if random.random() < 0.35:
        device = random.choice(DEVICE_TARGETS)
        base += f" ({device} 타겟)"
    return base


# ============================================================
# M-1: Flutter 풀 워크플로우 (10 패턴 × 40 = 400)
# ============================================================

FLUTTER_PATTERNS = [
    {
        "task": "Counter 앱 + Provider state 관리",
        "files": ["lib/main.dart", "lib/providers/counter.dart", "pubspec.yaml"],
        "deps_initial": "name: my_app\nversion: 1.0.0+1\n\ndependencies:\n  flutter: { sdk: flutter }",
        "code_main": (
            "import 'package:flutter/material.dart';\n"
            "import 'package:provider/provider.dart';\n"
            "import 'providers/counter.dart';\n\n"
            "void main() => runApp(\n"
            "  ChangeNotifierProvider(\n"
            "    create: (_) => Counter(),\n"
            "    child: const MyApp(),\n"
            "  ),\n"
            ");\n\n"
            "class MyApp extends StatelessWidget {\n"
            "  const MyApp({super.key});\n"
            "  @override\n"
            "  Widget build(BuildContext context) {\n"
            "    final counter = context.watch<Counter>();\n"
            "    return MaterialApp(\n"
            "      home: Scaffold(\n"
            "        body: Center(child: Text('${counter.value}')),\n"
            "        floatingActionButton: FloatingActionButton(\n"
            "          onPressed: counter.increment,\n"
            "          child: const Icon(Icons.add),\n"
            "        ),\n"
            "      ),\n"
            "    );\n"
            "  }\n"
            "}\n"
        ),
        "build_cmd": "flutter build apk --release",
        "common_error": "Error: Cannot run with sound null safety, because the following dependencies don't support null safety: provider",
        "fix_summary": "pubspec.yaml dependencies 의 provider 버전 6.0+ 로 업그레이드",
        "fix_target": "pubspec.yaml",
        "fix_old": "dependencies:\n  flutter: { sdk: flutter }",
        "fix_new": "dependencies:\n  flutter: { sdk: flutter }\n  provider: ^6.1.1",
    },
    {
        "task": "이미지 캐싱 + 그리드 갤러리",
        "files": ["lib/screens/gallery.dart", "lib/widgets/cached_image.dart"],
        "deps_initial": "name: gallery\ndependencies:\n  flutter: { sdk: flutter }\n  cached_network_image: ^3.3.0",
        "code_main": (
            "import 'package:flutter/material.dart';\n"
            "import 'package:cached_network_image/cached_network_image.dart';\n\n"
            "class Gallery extends StatelessWidget {\n"
            "  final List<String> urls;\n"
            "  const Gallery({super.key, required this.urls});\n"
            "  @override\n"
            "  Widget build(BuildContext c) => GridView.builder(\n"
            "    gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 3),\n"
            "    itemCount: urls.length,\n"
            "    itemBuilder: (_, i) => CachedNetworkImage(imageUrl: urls[i]),\n"
            "  );\n"
            "}\n"
        ),
        "build_cmd": "flutter run",
        "common_error": "Image not loading - ClientException: Failed to load network image (CORS or HTTPS issue)",
        "fix_summary": "AndroidManifest.xml 에 INTERNET permission + iOS Info.plist 의 NSAppTransportSecurity",
        "fix_target": "android/app/src/main/AndroidManifest.xml",
        "fix_old": "<application",
        "fix_new": "<uses-permission android:name=\"android.permission.INTERNET\"/>\n    <application",
    },
    {
        "task": "REST API 호출 + JSON 파싱",
        "files": ["lib/api/client.dart", "lib/models/user.dart"],
        "deps_initial": "name: api_app\ndependencies:\n  flutter: { sdk: flutter }\n  http: ^1.1.0",
        "code_main": (
            "import 'dart:convert';\n"
            "import 'package:http/http.dart' as http;\n"
            "import '../models/user.dart';\n\n"
            "class ApiClient {\n"
            "  Future<List<User>> fetchUsers() async {\n"
            "    final res = await http.get(Uri.parse('https://api.example.com/users'));\n"
            "    final List data = jsonDecode(utf8.decode(res.bodyBytes));\n"
            "    return data.map((e) => User.fromJson(e)).toList();\n"
            "  }\n"
            "}\n"
        ),
        "build_cmd": "flutter test",
        "common_error": "FormatException: SyntaxError: Unexpected token < in JSON at position 0",
        "fix_summary": "http response.body 가 JSON 인지 확인 + utf8 decode + status code 체크",
        "fix_target": "lib/api/client.dart",
        "fix_old": "final List data = jsonDecode(utf8.decode(res.bodyBytes));",
        "fix_new": "if (res.statusCode != 200) throw Exception('HTTP ${res.statusCode}');\n    final List data = jsonDecode(utf8.decode(res.bodyBytes));",
    },
    {
        "task": "BottomNavigationBar 다중 탭",
        "files": ["lib/main.dart", "lib/screens/home.dart"],
        "deps_initial": "name: tabs\ndependencies:\n  flutter: { sdk: flutter }",
        "code_main": (
            "import 'package:flutter/material.dart';\n\n"
            "class Home extends StatefulWidget {\n"
            "  const Home({super.key});\n"
            "  @override\n"
            "  State<Home> createState() => _HomeState();\n"
            "}\n\n"
            "class _HomeState extends State<Home> {\n"
            "  int _idx = 0;\n"
            "  final pages = const [Text('홈'), Text('검색'), Text('프로필')];\n"
            "  @override\n"
            "  Widget build(BuildContext c) => Scaffold(\n"
            "    body: pages[_idx],\n"
            "    bottomNavigationBar: BottomNavigationBar(\n"
            "      currentIndex: _idx,\n"
            "      onTap: (i) => setState(() => _idx = i),\n"
            "      items: const [\n"
            "        BottomNavigationBarItem(icon: Icon(Icons.home), label: '홈'),\n"
            "        BottomNavigationBarItem(icon: Icon(Icons.search), label: '검색'),\n"
            "        BottomNavigationBarItem(icon: Icon(Icons.person), label: '프로필'),\n"
            "      ],\n"
            "    ),\n"
            "  );\n"
            "}\n"
        ),
        "build_cmd": "flutter run",
        "common_error": "setState() called after dispose(): _HomeState#abc12(lifecycle state: defunct)",
        "fix_summary": "비동기 작업 후 mounted check 추가",
        "fix_target": "lib/screens/home.dart",
        "fix_old": "onTap: (i) => setState(() => _idx = i),",
        "fix_new": "onTap: (i) { if (!mounted) return; setState(() => _idx = i); },",
    },
    {
        "task": "SharedPreferences 로컬 저장",
        "files": ["lib/services/prefs.dart"],
        "deps_initial": "name: prefs_app\ndependencies:\n  flutter: { sdk: flutter }\n  shared_preferences: ^2.2.0",
        "code_main": (
            "import 'package:shared_preferences/shared_preferences.dart';\n\n"
            "class PrefsService {\n"
            "  static Future<void> setToken(String token) async {\n"
            "    final prefs = await SharedPreferences.getInstance();\n"
            "    await prefs.setString('token', token);\n"
            "  }\n"
            "  static Future<String?> getToken() async {\n"
            "    final prefs = await SharedPreferences.getInstance();\n"
            "    return prefs.getString('token');\n"
            "  }\n"
            "}\n"
        ),
        "build_cmd": "flutter test",
        "common_error": "MissingPluginException(No implementation found for method getAll on channel plugins.flutter.io/shared_preferences)",
        "fix_summary": "flutter clean + flutter pub get + iOS pod install 로 plugin 재등록",
        "fix_target": "ios/Podfile",
        "fix_old": "platform :ios, '11.0'",
        "fix_new": "platform :ios, '12.0'",
    },
    {
        "task": "Firebase Auth 통합",
        "files": ["lib/auth/firebase_auth.dart"],
        "deps_initial": "name: auth_app\ndependencies:\n  flutter: { sdk: flutter }\n  firebase_core: ^2.24.0\n  firebase_auth: ^4.15.0",
        "code_main": (
            "import 'package:firebase_auth/firebase_auth.dart';\n\n"
            "class AuthService {\n"
            "  final _auth = FirebaseAuth.instance;\n"
            "  Future<User?> signIn(String email, String pw) async {\n"
            "    final cred = await _auth.signInWithEmailAndPassword(email: email, password: pw);\n"
            "    return cred.user;\n"
            "  }\n"
            "  Stream<User?> get authState => _auth.authStateChanges();\n"
            "}\n"
        ),
        "build_cmd": "flutter build ios --no-codesign",
        "common_error": "GoogleService-Info.plist not found in iOS Runner target",
        "fix_summary": "iOS Runner 에 GoogleService-Info.plist 추가 + Xcode target Build Phases 에 등록",
        "fix_target": "ios/Runner/Info.plist",
        "fix_old": "<key>CFBundleName</key>",
        "fix_new": "<key>FirebaseAppDelegateProxyEnabled</key>\n    <false/>\n    <key>CFBundleName</key>",
    },
    {
        "task": "AnimationController 카드 페이드인",
        "files": ["lib/widgets/animated_card.dart"],
        "deps_initial": "name: anim_app\ndependencies:\n  flutter: { sdk: flutter }",
        "code_main": (
            "import 'package:flutter/material.dart';\n\n"
            "class AnimatedCard extends StatefulWidget {\n"
            "  const AnimatedCard({super.key});\n"
            "  @override\n"
            "  State<AnimatedCard> createState() => _AnimatedCardState();\n"
            "}\n\n"
            "class _AnimatedCardState extends State<AnimatedCard>\n"
            "    with SingleTickerProviderStateMixin {\n"
            "  late AnimationController _ctrl;\n"
            "  @override\n"
            "  void initState() {\n"
            "    super.initState();\n"
            "    _ctrl = AnimationController(\n"
            "      vsync: this,\n"
            "      duration: const Duration(milliseconds: 600),\n"
            "    )..forward();\n"
            "  }\n"
            "  @override\n"
            "  Widget build(BuildContext c) =>\n"
            "      FadeTransition(opacity: _ctrl, child: const Card(child: Text('Hello')));\n"
            "}\n"
        ),
        "build_cmd": "flutter run",
        "common_error": "AnimationController not disposed - memory leak detected by leak_tracker",
        "fix_summary": "dispose() 메서드에서 controller.dispose() 호출 필수",
        "fix_target": "lib/widgets/animated_card.dart",
        "fix_old": "  Widget build(BuildContext c) =>",
        "fix_new": "  @override\n  void dispose() {\n    _ctrl.dispose();\n    super.dispose();\n  }\n  @override\n  Widget build(BuildContext c) =>",
    },
    {
        "task": "Dio HTTP 클라이언트 + interceptor 토큰 갱신",
        "files": ["lib/api/dio_client.dart"],
        "deps_initial": "name: dio_app\ndependencies:\n  flutter: { sdk: flutter }\n  dio: ^5.4.0",
        "code_main": (
            "import 'package:dio/dio.dart';\n\n"
            "class DioClient {\n"
            "  late final Dio dio;\n"
            "  String? _token;\n"
            "  DioClient() {\n"
            "    dio = Dio(BaseOptions(baseUrl: 'https://api.example.com'));\n"
            "    dio.interceptors.add(InterceptorsWrapper(\n"
            "      onRequest: (opts, handler) {\n"
            "        if (_token != null) opts.headers['Authorization'] = 'Bearer $_token';\n"
            "        handler.next(opts);\n"
            "      },\n"
            "    ));\n"
            "  }\n"
            "}\n"
        ),
        "build_cmd": "flutter test",
        "common_error": "DioException [DioExceptionType.badResponse]: Http status error [401]",
        "fix_summary": "interceptor onError 에서 401 시 token refresh + retry 로직 추가",
        "fix_target": "lib/api/dio_client.dart",
        "fix_old": "      },\n    ));",
        "fix_new": "      },\n      onError: (err, handler) async {\n        if (err.response?.statusCode == 401) {\n          // refresh token logic here\n        }\n        handler.next(err);\n      },\n    ));",
    },
    {
        "task": "GoRouter 기반 라우팅",
        "files": ["lib/router/app_router.dart"],
        "deps_initial": "name: router_app\ndependencies:\n  flutter: { sdk: flutter }",
        "code_main": (
            "import 'package:flutter/material.dart';\n"
            "import 'package:go_router/go_router.dart';\n\n"
            "final appRouter = GoRouter(\n"
            "  routes: [\n"
            "    GoRoute(path: '/', builder: (_, __) => const HomePage()),\n"
            "    GoRoute(path: '/detail/:id', builder: (_, s) => DetailPage(id: s.pathParameters['id']!)),\n"
            "  ],\n"
            ");\n"
        ),
        "build_cmd": "flutter analyze",
        "common_error": "Error: Type 'GoRouter' not found. Did you forget to add 'go_router' to pubspec.yaml?",
        "fix_summary": "go_router pubspec 추가 + flutter pub get",
        "fix_target": "pubspec.yaml",
        "fix_old": "dependencies:\n  flutter: { sdk: flutter }",
        "fix_new": "dependencies:\n  flutter: { sdk: flutter }\n  go_router: ^13.0.0",
    },
    {
        "task": "flutter_gen 으로 assets 자동 코드 생성",
        "files": ["pubspec.yaml", "lib/gen/assets.gen.dart"],
        "deps_initial": "name: assets_app\ndependencies:\n  flutter: { sdk: flutter }\n\ndev_dependencies:\n  build_runner: ^2.4.0",
        "code_main": (
            "# pubspec.yaml — flutter_gen 설정\n"
            "flutter:\n"
            "  uses-material-design: true\n"
            "  assets:\n"
            "    - assets/images/\n"
            "\n"
            "flutter_gen:\n"
            "  output: lib/gen/\n"
            "  line_length: 80\n"
            "  integrations:\n"
            "    flutter_svg: true\n"
        ),
        "build_cmd": "flutter pub run build_runner build --delete-conflicting-outputs",
        "common_error": "[SEVERE] Could not find a generator for `flutter_gen_runner`",
        "fix_summary": "build_runner 와 flutter_gen_runner 둘 다 dev_dependencies 에 추가",
        "fix_target": "pubspec.yaml",
        "fix_old": "dev_dependencies:\n  build_runner: ^2.4.0",
        "fix_new": "dev_dependencies:\n  build_runner: ^2.4.0\n  flutter_gen_runner: ^5.4.0",
    },
]


def gen_flutter_workflow(p):
    """Flutter 풀 워크플로우 generator: read → write → build → 에러 → fix → 재빌드 → 마무리."""
    user_msg = vary_user_msg(p["task"])
    main_file = p["files"][0]
    fix_target = p["fix_target"]
    device = random.choice(DEVICE_TARGETS)
    wrap = random.choice(WRAP_UP_PHRASES).format(
        task=p["task"], fix=p["fix_summary"], device=device
    )

    msgs = [
        syss(),
        user(user_msg),
        assistant(
            f"{p['task']} 진행하겠습니다. 먼저 현재 pubspec.yaml 확인.\n\n"
            + tc("read_file", {"path": "pubspec.yaml"})
        ),
        tool(p["deps_initial"]),
        assistant(
            f"의존성 파악 완료. 이제 {main_file} 작성합니다.\n\n"
            + tc("write_file", {"path": main_file, "content": p["code_main"]})
        ),
        tool(f"File written: {main_file} ({len(p['code_main'])} bytes)"),
    ]

    # 가끔 추가 파일 (~50%)
    if len(p["files"]) > 1 and random.random() < 0.5:
        extra = p["files"][1]
        stub = f"// {p['task']} - {extra}\n// generated stub\n"
        msgs.append(
            assistant(
                f"부속 파일 {extra} 도 함께 생성합니다.\n\n"
                + tc("write_file", {"path": extra, "content": stub})
            )
        )
        msgs.append(tool(f"File written: {extra}"))

    # 빌드 시도 → 에러
    msgs.append(
        assistant(
            f"이제 빌드 검증.\n\n" + tc("run_command", {"command": p["build_cmd"]})
        )
    )
    msgs.append(tool(p["common_error"]))

    # fix
    msgs.append(
        assistant(
            f"에러 분석: 이는 {p['fix_summary']} 로 해결됩니다. {fix_target} 수정합니다.\n\n"
            + tc(
                "edit_file",
                {
                    "path": fix_target,
                    "oldString": p["fix_old"],
                    "newString": p["fix_new"],
                },
            )
        )
    )
    msgs.append(tool(f"Edit applied to {fix_target}: 1 replacement"))

    # 재빌드
    msgs.append(
        assistant("재빌드 시도.\n\n" + tc("run_command", {"command": p["build_cmd"]}))
    )
    msgs.append(tool("BUILD SUCCESS in 28.4s"))

    # 가끔 디바이스 배포 (~30%)
    if random.random() < 0.3:
        deploy_cmd = random.choice(
            [
                "flutter install",
                "flutter run -d " + random.choice(["iPhone", "Pixel_6", "macos"]),
                "flutter run --release",
            ]
        )
        msgs.append(
            assistant(
                f"디바이스에 배포해 동작 확인.\n\n"
                + tc("run_command", {"command": deploy_cmd})
            )
        )
        msgs.append(tool("✓ App launched on device — no runtime errors"))

    msgs.append(assistant(wrap))
    return m(msgs)


SCENARIO_M1 = [gen_flutter_workflow(random.choice(FLUTTER_PATTERNS)) for _ in range(400)]


# ============================================================
# M-2: React Native 풀 워크플로우 (10 패턴 × 40 = 400)
# ============================================================

RN_PATTERNS = [
    {
        "task": "Expo 새 앱 + tab navigation",
        "files": ["App.tsx", "app.json"],
        "deps_initial": (
            '{\n  "name": "expo-app",\n  "version": "1.0.0",\n'
            '  "dependencies": {\n    "expo": "~50.0.0",\n    "react": "18.2.0",\n'
            '    "react-native": "0.73.0"\n  }\n}'
        ),
        "code_main": (
            "import { NavigationContainer } from '@react-navigation/native';\n"
            "import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';\n"
            "import { Text, View } from 'react-native';\n\n"
            "const Tab = createBottomTabNavigator();\n"
            "const Home = () => <View><Text>홈</Text></View>;\n"
            "const Profile = () => <View><Text>프로필</Text></View>;\n\n"
            "export default function App() {\n"
            "  return (\n"
            "    <NavigationContainer>\n"
            "      <Tab.Navigator>\n"
            "        <Tab.Screen name='Home' component={Home} />\n"
            "        <Tab.Screen name='Profile' component={Profile} />\n"
            "      </Tab.Navigator>\n"
            "    </NavigationContainer>\n"
            "  );\n"
            "}\n"
        ),
        "build_cmd": "npx expo start",
        "common_error": "Error: Unable to resolve module @react-navigation/native from App.tsx",
        "fix_summary": "@react-navigation/native + bottom-tabs + screens + safe-area-context 모두 설치",
        "fix_target": "package.json",
        "fix_old": '"react-native": "0.73.0"',
        "fix_new": '"react-native": "0.73.0",\n    "@react-navigation/native": "^6.1.9",\n    "@react-navigation/bottom-tabs": "^6.5.11",\n    "react-native-screens": "~3.29.0",\n    "react-native-safe-area-context": "4.8.2"',
    },
    {
        "task": "AsyncStorage 영속화 토큰",
        "files": ["src/storage/index.ts"],
        "deps_initial": '{\n  "dependencies": {\n    "react-native": "0.73.0"\n  }\n}',
        "code_main": (
            "import AsyncStorage from '@react-native-async-storage/async-storage';\n\n"
            "export const Storage = {\n"
            "  async setToken(token: string) {\n"
            "    await AsyncStorage.setItem('@auth_token', token);\n"
            "  },\n"
            "  async getToken(): Promise<string | null> {\n"
            "    return AsyncStorage.getItem('@auth_token');\n"
            "  },\n"
            "  async clear() {\n"
            "    await AsyncStorage.removeItem('@auth_token');\n"
            "  },\n"
            "};\n"
        ),
        "build_cmd": "npx jest",
        "common_error": "Error: AsyncStorage has been removed from react-native core. Use @react-native-async-storage/async-storage",
        "fix_summary": "@react-native-async-storage/async-storage 별도 설치 + iOS pod install",
        "fix_target": "package.json",
        "fix_old": '"react-native": "0.73.0"',
        "fix_new": '"react-native": "0.73.0",\n    "@react-native-async-storage/async-storage": "^1.21.0"',
    },
    {
        "task": "EAS Build 클라우드 빌드 설정",
        "files": ["eas.json"],
        "deps_initial": '{\n  "dependencies": {\n    "expo": "~50.0.0"\n  }\n}',
        "code_main": (
            "{\n"
            '  "cli": { "version": ">= 7.0.0" },\n'
            '  "build": {\n'
            '    "preview": {\n'
            '      "distribution": "internal",\n'
            '      "ios": { "simulator": true }\n'
            "    },\n"
            '    "production": {\n'
            '      "autoIncrement": true\n'
            "    }\n"
            "  }\n"
            "}\n"
        ),
        "build_cmd": "eas build --profile preview --platform ios",
        "common_error": "Error: EAS project not configured. Run `eas init` first.",
        "fix_summary": "eas init 실행해 expo project ID 등록 + app.json 에 extra.eas.projectId 추가",
        "fix_target": "app.json",
        "fix_old": '"name": "expo-app"',
        "fix_new": '"name": "expo-app",\n    "extra": { "eas": { "projectId": "abc-123-def" } }',
    },
    {
        "task": "CodePush OTA 업데이트",
        "files": ["src/CodePushApp.tsx"],
        "deps_initial": '{\n  "dependencies": {\n    "react-native": "0.73.0",\n    "react-native-code-push": "^8.1.0"\n  }\n}',
        "code_main": (
            "import codePush from 'react-native-code-push';\n"
            "import App from './App';\n\n"
            "const codePushOptions = {\n"
            "  checkFrequency: codePush.CheckFrequency.ON_APP_RESUME,\n"
            "  installMode: codePush.InstallMode.ON_NEXT_RESUME,\n"
            "};\n\n"
            "export default codePush(codePushOptions)(App);\n"
        ),
        "build_cmd": "npx react-native run-android --variant=release",
        "common_error": "Error: CodePushUpdateManager: No deployment key configured",
        "fix_summary": "android/app/src/main/res/values/strings.xml 에 CodePushDeploymentKey 추가",
        "fix_target": "android/app/src/main/res/values/strings.xml",
        "fix_old": "<resources>",
        "fix_new": "<resources>\n    <string moduleConfig=\"true\" name=\"CodePushDeploymentKey\">YOUR_KEY_HERE</string>",
    },
    {
        "task": "React Navigation 6 stack + drawer",
        "files": ["src/navigation/RootStack.tsx"],
        "deps_initial": '{\n  "dependencies": {\n    "react-native": "0.73.0",\n    "@react-navigation/native": "^6.1.9"\n  }\n}',
        "code_main": (
            "import { createNativeStackNavigator } from '@react-navigation/native-stack';\n"
            "import { createDrawerNavigator } from '@react-navigation/drawer';\n\n"
            "const Stack = createNativeStackNavigator();\n"
            "const Drawer = createDrawerNavigator();\n\n"
            "export const RootStack = () => (\n"
            "  <Stack.Navigator>\n"
            "    <Stack.Screen name='Main' component={MainDrawer} />\n"
            "  </Stack.Navigator>\n"
            ");\n\n"
            "const MainDrawer = () => (\n"
            "  <Drawer.Navigator>\n"
            "    <Drawer.Screen name='Home' component={HomeScreen} />\n"
            "  </Drawer.Navigator>\n"
            ");\n"
        ),
        "build_cmd": "npx react-native run-ios",
        "common_error": "Error: react-native-gesture-handler not installed (required by drawer)",
        "fix_summary": "react-native-gesture-handler + reanimated 설치 + index.js 최상단 import",
        "fix_target": "index.js",
        "fix_old": "import { AppRegistry }",
        "fix_new": "import 'react-native-gesture-handler';\nimport { AppRegistry }",
    },
    {
        "task": "Firebase + Sentry 통합",
        "files": ["src/monitoring.ts"],
        "deps_initial": '{\n  "dependencies": {\n    "react-native": "0.73.0",\n    "@sentry/react-native": "^5.19.0"\n  }\n}',
        "code_main": (
            "import * as Sentry from '@sentry/react-native';\n"
            "import firebase from '@react-native-firebase/app';\n\n"
            "export const initMonitoring = () => {\n"
            "  Sentry.init({\n"
            "    dsn: process.env.SENTRY_DSN,\n"
            "    enableAutoSessionTracking: true,\n"
            "    tracesSampleRate: 0.2,\n"
            "  });\n"
            "  if (!firebase.apps.length) firebase.initializeApp();\n"
            "};\n"
        ),
        "build_cmd": "npx react-native run-ios",
        "common_error": "Error: GoogleService-Info.plist not found in app bundle",
        "fix_summary": "iOS 프로젝트 Runner target 의 Build Phases 에 GoogleService-Info.plist 추가",
        "fix_target": "ios/Podfile",
        "fix_old": "platform :ios, '12.0'",
        "fix_new": "platform :ios, '13.0'\nuse_frameworks! :linkage => :static",
    },
    {
        "task": "Native Module 작성 (Swift bridge)",
        "files": ["ios/CalendarBridge.swift"],
        "deps_initial": '{\n  "dependencies": {\n    "react-native": "0.73.0"\n  }\n}',
        "code_main": (
            "import Foundation\n"
            "import EventKit\n\n"
            "@objc(CalendarBridge)\n"
            "class CalendarBridge: NSObject {\n"
            "  @objc static func requiresMainQueueSetup() -> Bool { false }\n"
            "  @objc func addEvent(_ title: String,\n"
            "                      resolver resolve: @escaping RCTPromiseResolveBlock,\n"
            "                      rejecter reject: @escaping RCTPromiseRejectBlock) {\n"
            "    let store = EKEventStore()\n"
            "    store.requestAccess(to: .event) { granted, _ in\n"
            "      resolve(granted)\n"
            "    }\n"
            "  }\n"
            "}\n"
        ),
        "build_cmd": "npx react-native run-ios",
        "common_error": "Error: Module CalendarBridge is not registered (no .m bridging file)",
        "fix_summary": "ios/CalendarBridge.m 파일 생성 + RCT_EXTERN_MODULE 매크로로 bridge",
        "fix_target": "ios/CalendarBridge.m",
        "fix_old": "// stub",
        "fix_new": "#import <React/RCTBridgeModule.h>\n@interface RCT_EXTERN_MODULE(CalendarBridge, NSObject)\nRCT_EXTERN_METHOD(addEvent:(NSString *)title resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject)\n@end",
    },
    {
        "task": "iOS Pod install / cocoapods 의존성 해결",
        "files": ["ios/Podfile"],
        "deps_initial": '{\n  "dependencies": {\n    "react-native": "0.73.0",\n    "react-native-vector-icons": "^10.0.0"\n  }\n}',
        "code_main": (
            "platform :ios, '13.0'\n"
            "require_relative '../node_modules/react-native/scripts/react_native_pods'\n\n"
            "target 'MyApp' do\n"
            "  config = use_native_modules!\n"
            "  use_react_native!(:path => config[:reactNativePath])\n"
            "  pod 'RNVectorIcons', :path => '../node_modules/react-native-vector-icons'\n"
            "end\n"
        ),
        "build_cmd": "cd ios && pod install --repo-update",
        "common_error": "[!] CocoaPods could not find compatible versions for pod \"hermes-engine\"",
        "fix_summary": "pod repo update + Podfile.lock 삭제 후 pod install 재시도",
        "fix_target": "ios/Podfile",
        "fix_old": "platform :ios, '13.0'",
        "fix_new": "platform :ios, '13.4'\nensure_bundler!",
    },
    {
        "task": "ProGuard / R8 Android release minify",
        "files": ["android/app/proguard-rules.pro"],
        "deps_initial": '{\n  "dependencies": {\n    "react-native": "0.73.0"\n  }\n}',
        "code_main": (
            "# ProGuard rules for React Native\n"
            "-keep class com.facebook.react.** { *; }\n"
            "-keep class com.facebook.hermes.** { *; }\n"
            "-keep class com.facebook.jni.** { *; }\n"
            "-dontwarn com.facebook.react.**\n"
            "\n"
            "# 앱 자체 모델 클래스 보존 (JSON 파싱용)\n"
            "-keep class com.myapp.models.** { *; }\n"
        ),
        "build_cmd": "cd android && ./gradlew assembleRelease",
        "common_error": "Error: R8: Missing class com.facebook.react.bridge.NativeArrayInterface",
        "fix_summary": "proguard-rules.pro 에 React Native bridge 클래스 -keep 규칙 추가",
        "fix_target": "android/app/build.gradle",
        "fix_old": "minifyEnabled false",
        "fix_new": "minifyEnabled true\n            shrinkResources true\n            proguardFiles getDefaultProguardFile(\"proguard-android.txt\"), \"proguard-rules.pro\"",
    },
    {
        "task": "Metro bundler + Hermes 활성화",
        "files": ["metro.config.js"],
        "deps_initial": '{\n  "dependencies": {\n    "react-native": "0.73.0"\n  }\n}',
        "code_main": (
            "const { getDefaultConfig, mergeConfig } = require('@react-native/metro-config');\n\n"
            "const config = {\n"
            "  transformer: {\n"
            "    getTransformOptions: async () => ({\n"
            "      transform: {\n"
            "        experimentalImportSupport: false,\n"
            "        inlineRequires: true,\n"
            "      },\n"
            "    }),\n"
            "  },\n"
            "};\n"
            "module.exports = mergeConfig(getDefaultConfig(__dirname), config);\n"
        ),
        "build_cmd": "npx react-native start --reset-cache",
        "common_error": "Error: Hermes bytecode version mismatch (expected 96, got 90)",
        "fix_summary": "android/app/build.gradle 의 hermesEnabled 확인 + ./gradlew clean 후 재빌드",
        "fix_target": "android/gradle.properties",
        "fix_old": "hermesEnabled=false",
        "fix_new": "hermesEnabled=true\nnewArchEnabled=false",
    },
]


def gen_rn_workflow(p):
    """React Native 풀 워크플로우 generator: read pkg.json → write → build → 에러 → fix → 재빌드 → 마무리."""
    user_msg = vary_user_msg(p["task"])
    main_file = p["files"][0]
    fix_target = p["fix_target"]
    device = random.choice(DEVICE_TARGETS)
    wrap = random.choice(WRAP_UP_PHRASES).format(
        task=p["task"], fix=p["fix_summary"], device=device
    )

    msgs = [
        syss(),
        user(user_msg),
        assistant(
            f"{p['task']} 시작. 먼저 package.json 확인.\n\n"
            + tc("read_file", {"path": "package.json"})
        ),
        tool(p["deps_initial"]),
        assistant(
            f"의존성 파악 완료. {main_file} 작성합니다.\n\n"
            + tc("write_file", {"path": main_file, "content": p["code_main"]})
        ),
        tool(f"File written: {main_file} ({len(p['code_main'])} bytes)"),
    ]

    # 가끔 추가 native side 파일 (~40%)
    if len(p["files"]) > 1 and random.random() < 0.4:
        extra = p["files"][1]
        stub = f"// {p['task']} - {extra}\n// generated stub\n"
        msgs.append(
            assistant(
                f"부속 파일 {extra} 생성.\n\n"
                + tc("write_file", {"path": extra, "content": stub})
            )
        )
        msgs.append(tool(f"File written: {extra}"))

    # 빌드 시도
    msgs.append(
        assistant(
            f"이제 빌드 검증.\n\n" + tc("run_command", {"command": p["build_cmd"]})
        )
    )
    msgs.append(tool(p["common_error"]))

    # fix
    msgs.append(
        assistant(
            f"에러 분석 결과: {p['fix_summary']}. {fix_target} 수정합니다.\n\n"
            + tc(
                "edit_file",
                {
                    "path": fix_target,
                    "oldString": p["fix_old"],
                    "newString": p["fix_new"],
                },
            )
        )
    )
    msgs.append(tool(f"Edit applied to {fix_target}: 1 replacement"))

    # 재빌드
    msgs.append(
        assistant("재빌드 시도.\n\n" + tc("run_command", {"command": p["build_cmd"]}))
    )
    msgs.append(tool("BUILD SUCCESSFUL in 42s"))

    # 가끔 디바이스 배포 (~30%)
    if random.random() < 0.3:
        deploy_cmd = random.choice(
            [
                "npx react-native run-ios --device",
                "npx react-native run-android --variant=release",
                "eas build --profile preview --platform all",
                "fastlane ios beta",
            ]
        )
        msgs.append(
            assistant(
                f"디바이스 배포 진행.\n\n"
                + tc("run_command", {"command": deploy_cmd})
            )
        )
        msgs.append(tool("✓ Installed on device — ready"))

    msgs.append(assistant(wrap))
    return m(msgs)


SCENARIO_M2 = [gen_rn_workflow(random.choice(RN_PATTERNS)) for _ in range(400)]


# ============================================================
# Output
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mobile_v6_a.jsonl")
    args = parser.parse_args()

    all_data = SCENARIO_M1 + SCENARIO_M2
    assert len(all_data) == 800, f"Expected 800, got {len(all_data)}"

    out_dir = os.path.dirname(args.output) or "."
    os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[OK] {len(all_data)} 샘플 → {args.output}")
    print(f"  - M-1 Flutter: {len(SCENARIO_M1)} (패턴 {len(FLUTTER_PATTERNS)} × 변형)")
    print(f"  - M-2 RN: {len(SCENARIO_M2)} (패턴 {len(RN_PATTERNS)} × 변형)")
