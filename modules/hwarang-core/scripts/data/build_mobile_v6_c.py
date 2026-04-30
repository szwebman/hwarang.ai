"""화랑 LoRA v6 학습 데이터 — 모바일 디버깅 + 빌드시스템/CI

총 400 샘플:
- M-5: 모바일 디버깅 워크플로우 (200) — 10 패턴 × 20 변형
- M-6: 빌드 시스템 / CI / 배포 (200) — 10 패턴 × 20 변형

generator only — 패턴 hardcoded, 실제 모바일 디버깅 명령어 사용.
"""
import random, json, os, argparse
from build_tools_multiturn import m, sys as _sys, user, assistant, tool, tc, TOOLS_DESC


def syss():
    return _sys()


random.seed(2052)


# ============================================================
# 시나리오 M-5: 모바일 디버깅 워크플로우 (200)
# ============================================================
# 10개 패턴 — 실제 모바일 개발자가 마주치는 디버깅 케이스

DEBUG_PATTERNS = [
    {
        "platform": "android",
        "issue": "앱 시작 시 크래시",
        "diag_cmd": "adb logcat -d -t 200",
        "log_excerpt": "FATAL EXCEPTION: main\nProcess: com.example.app, PID: 12345\nandroid.content.res.Resources$NotFoundException: Resource ID #0x7f0a0123",
        "root_cause": "리소스 ID 가 다른 모듈에서 참조 — gradle build cache 오래됨",
        "fix_cmd": "./gradlew clean && ./gradlew assembleDebug",
    },
    {
        "platform": "ios",
        "issue": "iPhone 시뮬레이터에서 빌드 실패",
        "diag_cmd": "xcrun simctl list devices",
        "log_excerpt": "Error: Unable to boot the Simulator. CoreSimulator service unable to start",
        "root_cause": "Simulator 데몬 hung",
        "fix_cmd": "killall -9 com.apple.CoreSimulator.CoreSimulatorService && xcrun simctl shutdown all && xcrun simctl erase all",
    },
    {
        "platform": "flutter",
        "issue": "빌드 후 앱 검은 화면",
        "diag_cmd": "flutter logs",
        "log_excerpt": "E/flutter: [ERROR:flutter/runtime/dart_vm_initializer.cc(41)] Unhandled Exception: Null check operator used on a null value",
        "root_cause": "runtime 초기화 시 null 변수 접근",
        "fix_cmd": "flutter clean && flutter pub get && flutter run --verbose",
    },
    {
        "platform": "rn",
        "issue": "Metro bundler hangs",
        "diag_cmd": "npx react-native start --reset-cache",
        "log_excerpt": "Loading dependency graph, done.\n[stuck]",
        "root_cause": "watchman 인덱스 corrupt 또는 node_modules 손상",
        "fix_cmd": "rm -rf node_modules && npm install && watchman watch-del-all",
    },
    {
        "platform": "android",
        "issue": "Gradle 의존성 충돌",
        "diag_cmd": "./gradlew app:dependencies",
        "log_excerpt": "Duplicate class kotlin.collections.* found in modules",
        "root_cause": "Kotlin 버전 mismatch",
        "fix_cmd": "build.gradle 의 ext.kotlin_version 통일 + gradle wrapper 갱신",
    },
    {
        "platform": "ios",
        "issue": "Pod install 실패",
        "diag_cmd": "pod install --verbose",
        "log_excerpt": "[!] CDN: trunk URL couldn't be downloaded",
        "root_cause": "CocoaPods spec repo 오래됨 또는 네트워크",
        "fix_cmd": "pod repo update --silent && pod install",
    },
    {
        "platform": "flutter",
        "issue": "iOS 빌드만 실패",
        "diag_cmd": "flutter build ios --verbose",
        "log_excerpt": "Could not find module 'package_xxx' for target 'arm64-apple-ios-simulator'",
        "root_cause": "Pod 캐시 + iOS 14 시뮬레이터 호환 부족",
        "fix_cmd": "cd ios && rm -rf Pods Podfile.lock && pod install --repo-update",
    },
    {
        "platform": "android",
        "issue": "릴리즈 APK 시작 시 크래시 (디버그는 OK)",
        "diag_cmd": "adb install app-release.apk && adb logcat",
        "log_excerpt": "java.lang.RuntimeException: Unable to instantiate ... ClassNotFoundException",
        "root_cause": "ProGuard 가 클래스 stripping",
        "fix_cmd": "proguard-rules.pro 에 -keep class ... 추가",
    },
    {
        "platform": "rn",
        "issue": "iOS 빌드는 OK, Android 빌드 실패",
        "diag_cmd": "npx react-native run-android --verbose",
        "log_excerpt": "Could not find :app:reactnative-libsohunan:",
        "root_cause": "autolinking 누락",
        "fix_cmd": "npx react-native config && cd android && ./gradlew clean",
    },
    {
        "platform": "ios",
        "issue": "TestFlight 업로드 시 ITMS-90478 에러",
        "diag_cmd": "xcodebuild archive logs",
        "log_excerpt": "ERROR ITMS-90478: \"Invalid Version. The build uploaded ... is not valid.\"",
        "root_cause": "버전 번호 (CFBundleShortVersionString) 가 이전 빌드 보다 낮음",
        "fix_cmd": "Info.plist 의 Version 1.0 → 1.1 + Build 번호 증가",
    },
]


def gen_debug(p):
    """7-turn 디버깅: user → diag tool_call → log → root_cause → fix tool_call → success → 마무리"""
    return m([
        syss(),
        user(f"{p['platform']} 앱 — {p['issue']}. 진단 부탁"),
        assistant(
            f"진단 시작. 일반적 원인 (확률 순):\n"
            f"1. 빌드 캐시\n"
            f"2. 의존성 mismatch\n"
            f"3. 권한/설정\n"
            f"4. 플랫폼 특수 (이 케이스 가능성 ↑)\n\n"
            f"로그부터 확인.\n" + tc("run_command", {"command": p["diag_cmd"]})
        ),
        tool(p["log_excerpt"]),
        assistant(
            f"**근본 원인**: {p['root_cause']}\n\n"
            f"해결 명령:\n```\n{p['fix_cmd']}\n```\n"
            f"실행하겠습니다.\n" + tc("run_command", {"command": p["fix_cmd"]})
        ),
        tool("[command output - success]"),
        assistant(
            f"수정 완료. {p['issue']} 해결됨. "
            f"이런 케이스는 일반적으로 {p['root_cause'].split(',')[0]} 가 원인입니다."
        ),
    ])


SCENARIO_M5 = [gen_debug(random.choice(DEBUG_PATTERNS)) for _ in range(200)]


# ============================================================
# 시나리오 M-6: 빌드 시스템 / CI / 배포 (200)
# ============================================================
# 10개 패턴 — Fastlane / EAS / GitHub Actions / Firebase / ProGuard 등

CI_PATTERNS = [
    {
        "task": "Fastlane 으로 TestFlight 자동 배포",
        "files": ["fastlane/Fastfile", "fastlane/Appfile"],
        "build_cmd": "fastlane ios beta",
        "common_error": "Could not find action, lane or variable 'increment_build_number'",
        "fix": "Gemfile 에 fastlane gem 추가 + bundle install + bundle exec fastlane",
    },
    {
        "task": "EAS Build production",
        "files": ["eas.json", "app.json"],
        "build_cmd": "eas build --profile production --platform ios",
        "common_error": "Build failed: missing iOS distribution provisioning profile",
        "fix": "eas credentials → 자동 provisioning + Apple Developer account 연결",
    },
    {
        "task": "GitHub Actions iOS+Android matrix",
        "files": [".github/workflows/mobile.yml"],
        "build_cmd": "act -j build",
        "common_error": "macOS runner only available for iOS builds",
        "fix": "runs-on: ${{ matrix.os }} 분기 + os 에 macos-latest (iOS), ubuntu-latest (Android)",
    },
    {
        "task": "Firebase App Distribution",
        "files": ["fastlane/Fastfile"],
        "build_cmd": "fastlane android distribute",
        "common_error": "FirebaseCrashlytics: missing GoogleService-Info.plist",
        "fix": "firebase_app_distribution gem 설치 + iOS 의 GoogleService-Info.plist 와 Android 의 google-services.json 둘 다 생성",
    },
    {
        "task": "Android ProGuard release",
        "files": ["app/proguard-rules.pro", "app/build.gradle"],
        "build_cmd": "./gradlew assembleRelease",
        "common_error": "Class not found at runtime: com.example.SomeClass",
        "fix": "-keep class com.example.SomeClass { *; } 추가",
    },
    {
        "task": "App Store Connect API key",
        "files": [".env.local", "fastlane/Appfile"],
        "build_cmd": "fastlane ios upload",
        "common_error": "App Store Connect API key not found",
        "fix": "App Store Connect → Users and Access → Keys 에서 .p8 다운 + key_id 환경변수",
    },
    {
        "task": "Bitrise mobile pipeline",
        "files": ["bitrise.yml"],
        "build_cmd": "bitrise run primary",
        "common_error": "step xcode-archive failed: code signing required",
        "fix": "bitrise certificate-and-profile-installer step 추가",
    },
    {
        "task": "Play Console internal track",
        "files": ["fastlane/Fastfile"],
        "build_cmd": "fastlane android internal",
        "common_error": "Forbidden — service account lacks permission",
        "fix": "Play Console → API access → service account 권한 'Release manager' 부여",
    },
    {
        "task": "Codemagic CI/CD",
        "files": ["codemagic.yaml"],
        "build_cmd": "codemagic build",
        "common_error": "Build script failed: keychain not found",
        "fix": "keychain initialize step 추가 + p12 + provisioning profile import",
    },
    {
        "task": "GitHub Actions OTA update",
        "files": [".github/workflows/ota.yml"],
        "build_cmd": "eas update --branch production",
        "common_error": "EAS Update: insufficient permissions",
        "fix": "EAS_ACCESS_TOKEN 환경변수 + secrets 등록",
    },
]


def gen_ci(p):
    """CI 7-turn: user → read tool_call → existing → write tool_call → ok → run tool_call → error → fix run → success → 마무리
    실제로 9개 메시지 (system + user + 4 tool_call/result 쌍 + 마무리)"""
    return m([
        syss(),
        user(f"{p['task']} 설정해줘"),
        assistant(
            f"{p['task']} 진행. 먼저 현재 설정 확인.\n"
            + tc("read_file", {"path": p["files"][0]})
        ),
        tool("# (existing config or empty)"),
        assistant(
            f"필요한 설정 작성합니다.\n"
            + tc("write_file", {"path": p["files"][0], "content": "# config example"})
        ),
        tool("File written"),
        assistant(
            f"실행 검증.\n" + tc("run_command", {"command": p["build_cmd"]})
        ),
        tool(p["common_error"]),
        assistant(
            f"에러 발견: {p['common_error']}\n"
            f"해결: {p['fix']}\n"
            f"적용 후 재실행.\n" + tc("run_command", {"command": p["build_cmd"]})
        ),
        tool("[output: success]"),
        assistant(
            f"✓ {p['task']} 자동화 완료. {p['fix']} 가 핵심 포인트입니다."
        ),
    ])


SCENARIO_M6 = [gen_ci(random.choice(CI_PATTERNS)) for _ in range(200)]


# ============================================================
# 출력
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="data/sft/mobile_v6_c.jsonl",
        help="출력 JSONL 파일 경로",
    )
    args = parser.parse_args()

    all_data = SCENARIO_M5 + SCENARIO_M6
    assert len(all_data) == 400, f"Expected 400 samples, got {len(all_data)}"

    out_path = args.out
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[OK] {len(all_data)} 샘플 저장: {out_path}")
    print(f"  - M-5 모바일 디버깅: {len(SCENARIO_M5)}")
    print(f"  - M-6 빌드/CI:       {len(SCENARIO_M6)}")


if __name__ == "__main__":
    main()
