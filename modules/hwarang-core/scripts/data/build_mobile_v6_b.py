"""화랑 LoRA v6 모바일 학습 데이터 (M-3 SwiftUI + M-4 Jetpack Compose).

총 700 샘플 (350 + 350). generator only — 패턴 hardcoded 20 개 (10 + 10).
각 샘플 9~13 turn: read → write → build → error → fix → rebuild → success.

핵심 함정 포커스:
  - SwiftUI: iOS deployment target 호환 (StateObject/NavigationStack/dismiss/swipeActions)
  - Compose: Gradle plugin / Hilt 어노테이션 / Manifest permission / Room @Entity
"""
import random
import json
import os
import argparse

from build_tools_multiturn import (
    m,
    sys as _sys,
    user,
    assistant,
    tool,
    tc,
    TOOLS_DESC,  # noqa: F401
)


def syss():
    return _sys()


random.seed(2051)


# ============================================================
# M-3: SwiftUI + iOS native (350 = 10 패턴 × 35)
# ============================================================

SWIFTUI_PATTERNS = [
    {
        "task": "@StateObject 로 ViewModel 바인딩",
        "files": ["ContentView.swift", "ViewModel.swift", "Info.plist"],
        "build_cmd": "xcodebuild -scheme MyApp -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 15'",
        "common_error": "error: 'StateObject' is only available in iOS 14.0 or newer",
        "fix": "Deployment Target 을 iOS 14+ 로 (Xcode → Build Settings → IPHONEOS_DEPLOYMENT_TARGET = 14.0)",
        "code": (
            "import SwiftUI\n\n"
            "final class CounterVM: ObservableObject {\n"
            "  @Published var count = 0\n"
            "  func inc() { count += 1 }\n"
            "}\n\n"
            "struct ContentView: View {\n"
            "  @StateObject private var vm = CounterVM()\n"
            "  var body: some View {\n"
            "    VStack { Text(\"\\(vm.count)\"); Button(\"+\", action: vm.inc) }\n"
            "  }\n"
            "}\n"
        ),
        "old": "// stub",
        "new": "// IPHONEOS_DEPLOYMENT_TARGET=14.0",
    },
    {
        "task": "NavigationStack 다중 화면 전환",
        "files": ["RootView.swift", "DetailView.swift"],
        "build_cmd": "xcodebuild test -scheme MyApp -destination 'platform=iOS Simulator,name=iPhone 15'",
        "common_error": "error: 'NavigationStack' is only available in iOS 16.0 or newer",
        "fix": "if #available(iOS 16, *) { NavigationStack { ... } } else { NavigationView { ... } } 분기 처리",
        "code": (
            "import SwiftUI\n\n"
            "struct RootView: View {\n"
            "  var body: some View {\n"
            "    NavigationStack {\n"
            "      NavigationLink(\"Detail\", destination: DetailView())\n"
            "    }\n"
            "  }\n"
            "}\n"
        ),
        "old": "NavigationStack {",
        "new": "if #available(iOS 16, *) { NavigationStack {",
    },
    {
        "task": "Combine + AsyncSequence 데이터 스트림",
        "files": ["api/Client.swift"],
        "build_cmd": "swift test",
        "common_error": "error: 'await' in a function that does not support concurrency",
        "fix": "함수 시그니처에 async 추가 또는 Task { ... } 안에서 await 호출",
        "code": (
            "import Combine\n\n"
            "func fetchEvents() async throws {\n"
            "  let url = URL(string: \"https://api.example.com/sse\")!\n"
            "  for try await line in url.lines { print(line) }\n"
            "}\n"
        ),
        "old": "func fetchEvents()",
        "new": "func fetchEvents() async throws",
    },
    {
        "task": "Core Data 모델 + @FetchRequest",
        "files": ["Persistence.swift", "Item.xcdatamodeld"],
        "build_cmd": "xcodebuild build -scheme MyApp",
        "common_error": "error: NSManagedObject not found in scope",
        "fix": "Persistence.shared.container.viewContext 를 environment 로 주입 + @FetchRequest 사용",
        "code": (
            "import CoreData\n\n"
            "struct PersistenceController {\n"
            "  static let shared = PersistenceController()\n"
            "  let container: NSPersistentContainer\n"
            "  init() {\n"
            "    container = NSPersistentContainer(name: \"Item\")\n"
            "    container.loadPersistentStores { _, _ in }\n"
            "  }\n"
            "}\n"
        ),
        "old": "// inject ctx",
        "new": ".environment(\\.managedObjectContext, PersistenceController.shared.container.viewContext)",
    },
    {
        "task": "Camera permission + AVFoundation 캡처",
        "files": ["CameraView.swift", "Info.plist"],
        "build_cmd": "xcodebuild build -scheme MyApp",
        "common_error": "App crashed: This app has crashed because it attempted to access privacy-sensitive data without a usage description. NSCameraUsageDescription not set.",
        "fix": "Info.plist 에 <key>NSCameraUsageDescription</key><string>카메라 사용</string> 추가",
        "code": (
            "import AVFoundation\nimport SwiftUI\n\n"
            "struct CameraView: UIViewControllerRepresentable {\n"
            "  func makeUIViewController(context: Context) -> UIImagePickerController {\n"
            "    let p = UIImagePickerController(); p.sourceType = .camera; return p\n"
            "  }\n"
            "  func updateUIViewController(_ u: UIImagePickerController, context: Context) {}\n"
            "}\n"
        ),
        "old": "<!-- usage -->",
        "new": "<key>NSCameraUsageDescription</key><string>카메라 사용</string>",
    },
    {
        "task": "WidgetKit 위젯 + Live Activities",
        "files": ["MyWidget.swift"],
        "build_cmd": "xcodebuild -scheme MyWidgetExtension -sdk iphonesimulator",
        "common_error": "error: WidgetBundle not found / @main attribute on multiple types",
        "fix": "@main WidgetBundle struct 추가 + Xcode 에 Widget Extension Target 별도 추가",
        "code": (
            "import WidgetKit\nimport SwiftUI\n\n"
            "struct MyWidget: Widget {\n"
            "  var body: some WidgetConfiguration {\n"
            "    StaticConfiguration(kind: \"MyWidget\", provider: Provider()) { entry in\n"
            "      Text(entry.date, style: .time)\n"
            "    }\n"
            "  }\n"
            "}\n"
        ),
        "old": "struct MyWidget",
        "new": "@main\nstruct MyWidgetBundle: WidgetBundle { var body: some Widget { MyWidget() } }\n\nstruct MyWidget",
    },
    {
        "task": "async/await URLSession 네트워크 호출",
        "files": ["api/Network.swift"],
        "build_cmd": "swift test",
        "common_error": "error: 'async' call in a function that does not support concurrency",
        "fix": "함수에 async throws 추가 + URLSession.shared.data(for: req) 사용",
        "code": (
            "import Foundation\n\n"
            "func fetchUser() throws -> Data {\n"
            "  let url = URL(string: \"https://api.example.com/me\")!\n"
            "  let (data, _) = try await URLSession.shared.data(from: url)\n"
            "  return data\n"
            "}\n"
        ),
        "old": "func fetchUser() throws -> Data",
        "new": "func fetchUser() async throws -> Data",
    },
    {
        "task": "@AppStorage 영속 설정 저장",
        "files": ["SettingsView.swift"],
        "build_cmd": "xcodebuild build -scheme MyApp",
        "common_error": "warning: @AppStorage requires UserDefaults — sensitive data leak",
        "fix": "토큰/비밀번호 등 민감 정보는 Keychain 라이브러리(KeychainSwift) 별도 저장",
        "code": (
            "import SwiftUI\n\n"
            "struct SettingsView: View {\n"
            "  @AppStorage(\"username\") var username: String = \"\"\n"
            "  @AppStorage(\"apiToken\") var apiToken: String = \"\"\n"
            "  var body: some View { TextField(\"Token\", text: $apiToken) }\n"
            "}\n"
        ),
        "old": "@AppStorage(\"apiToken\")",
        "new": "// Keychain 저장 — KeychainSwift().set(value, forKey: \"apiToken\")",
    },
    {
        "task": "Sheet + @Environment(\\.dismiss) 닫기",
        "files": ["MainView.swift"],
        "build_cmd": "xcodebuild build -scheme MyApp",
        "common_error": "error: cannot find 'dismiss' in scope",
        "fix": "@Environment(\\.dismiss) var dismiss 선언 (iOS 15+) — 14 이하는 presentationMode 사용",
        "code": (
            "import SwiftUI\n\n"
            "struct ChildView: View {\n"
            "  var body: some View {\n"
            "    Button(\"닫기\") { dismiss() }\n"
            "  }\n"
            "}\n"
        ),
        "old": "struct ChildView: View {",
        "new": "struct ChildView: View {\n  @Environment(\\.dismiss) var dismiss\n",
    },
    {
        "task": "List + swipeActions 스와이프 액션",
        "files": ["TodoListView.swift"],
        "build_cmd": "xcodebuild build -scheme MyApp",
        "common_error": "error: 'swipeActions' is only available in iOS 15.0 or newer",
        "fix": "iOS 14 호환은 .onDelete(perform:) 사용 — swipeActions 는 IPHONEOS_DEPLOYMENT_TARGET 15+ 필요",
        "code": (
            "import SwiftUI\n\n"
            "struct TodoListView: View {\n"
            "  @State var items = [\"a\", \"b\"]\n"
            "  var body: some View {\n"
            "    List(items, id: \\.self) { it in\n"
            "      Text(it).swipeActions { Button(\"Del\") {} }\n"
            "    }\n"
            "  }\n"
            "}\n"
        ),
        "old": ".swipeActions { Button(\"Del\") {} }",
        "new": "// iOS 14: .onDelete { idx in items.remove(atOffsets: idx) }",
    },
]


def gen_swiftui(p):
    f0 = p["files"][0]
    return m([
        syss(),
        user(f"SwiftUI 로 {p['task']} 구현해줘"),
        assistant(
            f"먼저 기존 프로젝트 구조와 {f0} 를 확인합니다.\n\n"
            + tc("read_file", {"path": f0})
        ),
        tool(f"// 기존 SwiftUI 스텁 ({f0})\nimport SwiftUI\n// stub\n"),
        assistant(
            f"{p['task']} 코드를 작성합니다.\n\n"
            + tc("write_file", {"path": f0, "content": p["code"]})
        ),
        tool(f"File written: {f0}"),
        assistant(
            "Xcode 빌드를 실행해 검증합니다.\n\n"
            + tc("run_command", {"command": p["build_cmd"]})
        ),
        tool(p["common_error"]),
        assistant(
            f"에러 분석: `{p['common_error']}`\n\n"
            f"원인 — iOS/SwiftUI 호환성 또는 설정 누락.\n"
            f"해결 — {p['fix']}\n\n"
            f"적용합니다.\n\n"
            + tc(
                "edit_file",
                {"path": f0, "oldString": p["old"], "newString": p["new"]},
            )
        ),
        tool(f"File modified: {f0}"),
        assistant("재빌드.\n\n" + tc("run_command", {"command": p["build_cmd"]})),
        tool("** BUILD SUCCEEDED **"),
        assistant(
            f"✓ {p['task']} 완성. SwiftUI 작업의 핵심 함정은 **iOS deployment target 호환성** "
            f"이었습니다 — `IPHONEOS_DEPLOYMENT_TARGET` 와 SwiftUI API 의 `available` "
            f"버전을 항상 매칭하세요."
        ),
    ])


SCENARIO_M3 = [gen_swiftui(random.choice(SWIFTUI_PATTERNS)) for _ in range(350)]


# ============================================================
# M-4: Jetpack Compose + Android native (350 = 10 패턴 × 35)
# ============================================================

COMPOSE_PATTERNS = [
    {
        "task": "ViewModel + StateFlow Compose 바인딩",
        "files": ["MainActivity.kt", "MainViewModel.kt", "build.gradle.kts"],
        "build_cmd": "./gradlew assembleDebug",
        "common_error": "e: file:///.../MainActivity.kt: unresolved reference: viewModel",
        "fix": "build.gradle.kts 의 dependencies 에 androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0 추가",
        "code": (
            "package com.example\n\n"
            "import androidx.lifecycle.ViewModel\n"
            "import kotlinx.coroutines.flow.MutableStateFlow\n"
            "import kotlinx.coroutines.flow.asStateFlow\n\n"
            "class MainViewModel : ViewModel() {\n"
            "  private val _count = MutableStateFlow(0)\n"
            "  val count = _count.asStateFlow()\n"
            "  fun inc() { _count.value += 1 }\n"
            "}\n"
        ),
        "old": "// deps",
        "new": "implementation(\"androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0\")",
    },
    {
        "task": "Hilt DI Application 클래스 설정",
        "files": ["MyApplication.kt", "AndroidManifest.xml"],
        "build_cmd": "./gradlew build",
        "common_error": "error: [Hilt] Cannot generate Hilt components for Application — missing @HiltAndroidApp",
        "fix": "@HiltAndroidApp 어노테이션 추가 + AndroidManifest 의 <application android:name=\".MyApplication\"> 지정",
        "code": (
            "package com.example\n\n"
            "import android.app.Application\n"
            "import dagger.hilt.android.HiltAndroidApp\n\n"
            "class MyApplication : Application()\n"
        ),
        "old": "class MyApplication : Application()",
        "new": "@HiltAndroidApp\nclass MyApplication : Application()",
    },
    {
        "task": "Retrofit + suspend 함수 API 호출",
        "files": ["api/ApiService.kt", "data/Repository.kt"],
        "build_cmd": "./gradlew test",
        "common_error": "java.lang.IllegalArgumentException: Could not locate ResponseBody converter for class com.example.User",
        "fix": "build.gradle 에 converter-gson 추가 + Retrofit.Builder().addConverterFactory(GsonConverterFactory.create())",
        "code": (
            "package com.example.api\n\n"
            "import retrofit2.http.GET\n\n"
            "data class User(val id: Int, val name: String)\n\n"
            "interface ApiService {\n"
            "  @GET(\"users/me\")\n"
            "  suspend fun getMe(): User\n"
            "}\n"
        ),
        "old": "// builder",
        "new": ".addConverterFactory(GsonConverterFactory.create())",
    },
    {
        "task": "Room DB 엔티티 + DAO",
        "files": ["data/AppDatabase.kt", "data/UserDao.kt"],
        "build_cmd": "./gradlew build",
        "common_error": "error: Type of the parameter must be a class annotated with @Entity or a collection/array of it.",
        "fix": "data class User(...) 위에 @Entity(tableName = \"users\") + @PrimaryKey 어노테이션 추가",
        "code": (
            "package com.example.data\n\n"
            "import androidx.room.*\n\n"
            "data class User(val id: Int, val name: String)\n\n"
            "@Dao\n"
            "interface UserDao {\n"
            "  @Insert suspend fun insert(u: User)\n"
            "  @Query(\"SELECT * FROM users\") suspend fun all(): List<User>\n"
            "}\n"
        ),
        "old": "data class User(val id: Int, val name: String)",
        "new": "@Entity(tableName = \"users\")\ndata class User(@PrimaryKey val id: Int, val name: String)",
    },
    {
        "task": "Camera permission Manifest + Compose 런타임 요청",
        "files": ["MainActivity.kt", "AndroidManifest.xml"],
        "build_cmd": "./gradlew assembleDebug",
        "common_error": "java.lang.SecurityException: Permission Denial: opening provider — Camera permission not granted",
        "fix": "AndroidManifest 에 <uses-permission android:name=\"android.permission.CAMERA\"/> + Compose 에서 rememberPermissionState (Accompanist)",
        "code": (
            "package com.example\n\n"
            "import android.os.Bundle\n"
            "import androidx.activity.ComponentActivity\n"
            "import androidx.activity.compose.setContent\n\n"
            "class MainActivity : ComponentActivity() {\n"
            "  override fun onCreate(s: Bundle?) {\n"
            "    super.onCreate(s)\n"
            "    setContent { /* Camera UI */ }\n"
            "  }\n"
            "}\n"
        ),
        "old": "<!-- perm -->",
        "new": "<uses-permission android:name=\"android.permission.CAMERA\"/>",
    },
    {
        "task": "Navigation Compose 라우팅",
        "files": ["NavGraph.kt", "build.gradle.kts"],
        "build_cmd": "./gradlew assembleDebug",
        "common_error": "e: unresolved reference: rememberNavController",
        "fix": "androidx.navigation:navigation-compose:2.7.7 dependency 추가",
        "code": (
            "package com.example.nav\n\n"
            "import androidx.compose.runtime.Composable\n"
            "import androidx.navigation.compose.NavHost\n"
            "import androidx.navigation.compose.composable\n"
            "import androidx.navigation.compose.rememberNavController\n\n"
            "@Composable\n"
            "fun AppNav() {\n"
            "  val nav = rememberNavController()\n"
            "  NavHost(nav, startDestination = \"home\") {\n"
            "    composable(\"home\") { /* HomeScreen */ }\n"
            "    composable(\"detail\") { /* DetailScreen */ }\n"
            "  }\n"
            "}\n"
        ),
        "old": "// nav-deps",
        "new": "implementation(\"androidx.navigation:navigation-compose:2.7.7\")",
    },
    {
        "task": "Material3 테마 + 다크 모드 동적 색상",
        "files": ["ui/Theme.kt", "build.gradle.kts"],
        "build_cmd": "./gradlew assembleDebug",
        "common_error": "e: unresolved reference: dynamicDarkColorScheme",
        "fix": "compose-bom 2024.02.00 이상 + minSdk 31 (Android 12) — 그 미만은 darkColorScheme() 정적 사용",
        "code": (
            "package com.example.ui\n\n"
            "import androidx.compose.foundation.isSystemInDarkTheme\n"
            "import androidx.compose.material3.MaterialTheme\n"
            "import androidx.compose.material3.dynamicDarkColorScheme\n"
            "import androidx.compose.material3.dynamicLightColorScheme\n"
            "import androidx.compose.runtime.Composable\n"
            "import androidx.compose.ui.platform.LocalContext\n\n"
            "@Composable\n"
            "fun AppTheme(content: @Composable () -> Unit) {\n"
            "  val ctx = LocalContext.current\n"
            "  val cs = if (isSystemInDarkTheme()) dynamicDarkColorScheme(ctx)\n"
            "           else dynamicLightColorScheme(ctx)\n"
            "  MaterialTheme(colorScheme = cs, content = content)\n"
            "}\n"
        ),
        "old": "// minSdk",
        "new": "minSdk = 31  // dynamic color requires Android 12+",
    },
    {
        "task": "WorkManager 주기 작업 등록",
        "files": ["work/SyncWorker.kt", "AndroidManifest.xml"],
        "build_cmd": "./gradlew build",
        "common_error": "java.lang.IllegalStateException: WorkManager is not initialized properly",
        "fix": "Hilt 사용 시 androidx.hilt:hilt-work + @HiltWorker + Manifest 의 WorkManagerInitializer provider 비활성화",
        "code": (
            "package com.example.work\n\n"
            "import android.content.Context\n"
            "import androidx.work.CoroutineWorker\n"
            "import androidx.work.WorkerParameters\n\n"
            "class SyncWorker(c: Context, p: WorkerParameters) : CoroutineWorker(c, p) {\n"
            "  override suspend fun doWork(): Result { return Result.success() }\n"
            "}\n"
        ),
        "old": "<!-- work-init -->",
        "new": "<provider android:name=\"androidx.startup.InitializationProvider\" tools:node=\"remove\"/>",
    },
    {
        "task": "ProGuard / R8 release 최적화",
        "files": ["proguard-rules.pro", "build.gradle.kts"],
        "build_cmd": "./gradlew assembleRelease",
        "common_error": "java.lang.RuntimeException: Unable to instantiate Retrofit service — class stripped by R8",
        "fix": "proguard-rules.pro 에 -keep class com.example.api.** { *; } + -keepattributes Signature,RuntimeVisibleAnnotations 추가",
        "code": (
            "# proguard-rules.pro\n"
            "-keepattributes Signature\n"
            "-keepattributes *Annotation*\n"
            "-keepattributes RuntimeVisibleAnnotations\n"
        ),
        "old": "# api-keep",
        "new": "-keep class com.example.api.** { *; }\n-keep interface com.example.api.** { *; }",
    },
    {
        "task": "remember + mutableStateOf Composable 카운터",
        "files": ["ui/Counter.kt"],
        "build_cmd": "./gradlew assembleDebug",
        "common_error": "e: 'mutableStateOf' is recomposing infinitely — state read inside composition without remember",
        "fix": "val count by remember { mutableStateOf(0) } 으로 wrapping — remember 없이는 recomposition 마다 초기화됨",
        "code": (
            "package com.example.ui\n\n"
            "import androidx.compose.foundation.layout.Column\n"
            "import androidx.compose.material3.Button\n"
            "import androidx.compose.material3.Text\n"
            "import androidx.compose.runtime.*\n\n"
            "@Composable\n"
            "fun Counter() {\n"
            "  var count = mutableStateOf(0)\n"
            "  Column {\n"
            "    Text(\"${count.value}\")\n"
            "    Button(onClick = { count.value += 1 }) { Text(\"+\") }\n"
            "  }\n"
            "}\n"
        ),
        "old": "var count = mutableStateOf(0)",
        "new": "var count by remember { mutableStateOf(0) }",
    },
]


def gen_compose(p):
    f0 = p["files"][0]
    return m([
        syss(),
        user(f"Jetpack Compose 로 {p['task']} 구현해줘"),
        assistant(
            f"먼저 기존 {f0} 와 build.gradle 설정을 확인합니다.\n\n"
            + tc("read_file", {"path": f0})
        ),
        tool(f"// 기존 Kotlin 스텁 ({f0})\npackage com.example\n// stub\n"),
        assistant(
            f"{p['task']} 코드를 작성합니다.\n\n"
            + tc("write_file", {"path": f0, "content": p["code"]})
        ),
        tool(f"File written: {f0}"),
        assistant(
            "Gradle 빌드를 실행해 검증합니다.\n\n"
            + tc("run_command", {"command": p["build_cmd"]})
        ),
        tool(p["common_error"]),
        assistant(
            f"에러 분석: `{p['common_error']}`\n\n"
            f"원인 — Android 빌드 시스템 (Gradle / Manifest / ProGuard) 또는 Compose 규칙 누락.\n"
            f"해결 — {p['fix']}\n\n"
            f"적용합니다.\n\n"
            + tc(
                "edit_file",
                {"path": f0, "oldString": p["old"], "newString": p["new"]},
            )
        ),
        tool(f"File modified: {f0}"),
        assistant("재빌드.\n\n" + tc("run_command", {"command": p["build_cmd"]})),
        tool("BUILD SUCCESSFUL in 12s"),
        assistant(
            f"✓ {p['task']} 완성. Compose 작업의 핵심 함정은 **Gradle dependency / "
            f"Manifest / ProGuard keep rule** 누락이었습니다 — 빌드 단계마다 "
            f"`./gradlew assembleDebug` 와 `assembleRelease` 양쪽에서 검증하세요."
        ),
    ])


SCENARIO_M4 = [gen_compose(random.choice(COMPOSE_PATTERNS)) for _ in range(350)]


# ============================================================
# 출력
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="data/sft/mobile_v6_b.jsonl",
        help="출력 jsonl 경로 (cwd 기준)",
    )
    args = parser.parse_args()

    all_data = SCENARIO_M3 + SCENARIO_M4
    assert len(all_data) == 700, f"expected 700 samples, got {len(all_data)}"

    out_dir = os.path.dirname(args.out)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(args.out, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[OK] {args.out}: {len(all_data)} samples "
          f"(M-3 SwiftUI {len(SCENARIO_M3)} + M-4 Compose {len(SCENARIO_M4)})")


if __name__ == "__main__":
    main()
