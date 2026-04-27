#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — 코드 사이닝 + 공증 통합 빌드 스크립트
#
# 사용법:
#   ./build_signed.sh mac        # macOS 사이닝 + 공증 → .dmg
#   ./build_signed.sh windows    # Windows 사이닝 → .msi/.exe
#   ./build_signed.sh linux      # Linux 패키징 (.deb / .AppImage)
#   ./build_signed.sh all        # 현재 OS에서 가능한 전부
#
# 환경변수 (macOS):
#   APPLE_SIGNING_IDENTITY  "Developer ID Application: Your Name (TEAMID)"
#   APPLE_ID                Apple ID 이메일
#   APPLE_PASSWORD          앱 전용 암호 (https://appleid.apple.com 에서 생성)
#   APPLE_TEAM_ID           Apple 개발자 팀 ID (10자)
#
# 환경변수 (Windows):
#   WINDOWS_CERT_PATH       .pfx 파일 경로
#   WINDOWS_CERT_PASSWORD   .pfx 암호
#   WINDOWS_TIMESTAMP_URL   기본값: http://timestamp.digicert.com
#
# 환경변수 (공통):
#   SIGN_SKIP=1             서명 단계 건너뜀 (개발/CI 테스트용)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ─── 컬러 출력 ────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()     { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()   { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()    { echo -e "${RED}[FAIL]${NC}  $*" >&2; }

# ─── 변수 ─────────────────────────────────────────────────────────────────────
TARGET="${1:-}"
VERSION="$(grep -E '"version"' src-tauri/tauri.conf.json | head -1 | sed -E 's/.*"version"[^"]*"([^"]+)".*/\1/')"
DIST_DIR="$SCRIPT_DIR/dist"
BUNDLE_DIR="$SCRIPT_DIR/src-tauri/target/release/bundle"

mkdir -p "$DIST_DIR"

if [[ -z "$TARGET" ]]; then
    err "사용법: $0 <mac|windows|linux|all>"
    exit 1
fi

log "버전: $VERSION"
log "타겟: $TARGET"
log "출력: $DIST_DIR"

# ─── env 검증 함수 ────────────────────────────────────────────────────────────
require_env() {
    local var_name="$1"
    if [[ -z "${!var_name:-}" ]]; then
        err "환경변수 $var_name 가 설정되지 않았습니다."
        err "  CODESIGN.md 참고하세요."
        exit 2
    fi
}

# ─── macOS 서명 + 공증 ────────────────────────────────────────────────────────
sign_macos() {
    log "macOS 빌드 시작..."

    if [[ "${SIGN_SKIP:-0}" == "1" ]]; then
        warn "SIGN_SKIP=1 → 서명 없이 빌드합니다."
    else
        require_env APPLE_SIGNING_IDENTITY
        require_env APPLE_ID
        require_env APPLE_PASSWORD
        require_env APPLE_TEAM_ID
    fi

    # 1. Tauri 빌드 (앱 번들 생성)
    log "Tauri build (universal binary)..."
    if cargo tauri build --target universal-apple-darwin 2>/dev/null; then
        ARCH_TAG="universal"
    else
        warn "universal 타겟 실패, 기본 아키텍처로 빌드합니다."
        cargo tauri build
        ARCH_TAG="$(uname -m)"
    fi

    # 2. .app 위치 확인
    local app_path
    app_path="$(find "$BUNDLE_DIR" -name '*.app' -type d | head -1)"
    if [[ -z "$app_path" ]]; then
        err ".app 번들을 찾을 수 없습니다: $BUNDLE_DIR"
        exit 3
    fi
    ok ".app 번들: $app_path"

    if [[ "${SIGN_SKIP:-0}" == "1" ]]; then
        warn "서명 단계 건너뜀."
    else
        # 3. 코드 서명 (deep sign + hardened runtime + timestamp)
        log "코드 서명 중..."
        codesign --force --deep --options runtime \
            --timestamp \
            --entitlements src-tauri/entitlements.plist \
            --sign "$APPLE_SIGNING_IDENTITY" \
            "$app_path" 2>/dev/null || \
        codesign --force --deep --options runtime \
            --timestamp \
            --sign "$APPLE_SIGNING_IDENTITY" \
            "$app_path"
        ok "코드 서명 완료"

        # 4. 서명 검증
        log "서명 검증 중..."
        codesign --verify --verbose=2 "$app_path"
        spctl --assess --type execute --verbose "$app_path" || warn "spctl 검증 경고 (notarize 후 재확인)"
    fi

    # 5. .dmg 생성
    local dmg_name="Hwarang-Grid-Agent-${VERSION}-${ARCH_TAG}.dmg"
    local dmg_path="$DIST_DIR/$dmg_name"
    log "DMG 생성: $dmg_name"

    if [[ -x "installer/macos/build_dmg.sh" ]]; then
        bash installer/macos/build_dmg.sh "$app_path" "$dmg_path"
    else
        # fallback: hdiutil
        rm -f "$dmg_path"
        hdiutil create -volname "Hwarang Grid Agent" \
            -srcfolder "$app_path" \
            -ov -format UDZO \
            "$dmg_path"
    fi
    ok "DMG 생성 완료: $dmg_path"

    # 6. DMG 서명
    if [[ "${SIGN_SKIP:-0}" != "1" ]]; then
        log "DMG 서명 중..."
        codesign --force --sign "$APPLE_SIGNING_IDENTITY" --timestamp "$dmg_path"

        # 7. 공증 (notarize)
        log "공증 제출 중... (수 분 소요)"
        xcrun notarytool submit "$dmg_path" \
            --apple-id "$APPLE_ID" \
            --password "$APPLE_PASSWORD" \
            --team-id "$APPLE_TEAM_ID" \
            --wait

        # 8. 스테이플 (오프라인 검증 가능)
        log "스테이플..."
        xcrun stapler staple "$dmg_path"
        xcrun stapler validate "$dmg_path"
        ok "공증 + 스테이플 완료"
    fi

    # 9. 체크섬
    (cd "$DIST_DIR" && shasum -a 256 "$dmg_name" > "${dmg_name}.sha256")
    ok "체크섬: ${dmg_name}.sha256"
}

# ─── Windows 서명 ─────────────────────────────────────────────────────────────
sign_windows() {
    log "Windows 빌드 시작..."

    if [[ "${SIGN_SKIP:-0}" == "1" ]]; then
        warn "SIGN_SKIP=1 → 서명 없이 빌드합니다."
    else
        require_env WINDOWS_CERT_PATH
        require_env WINDOWS_CERT_PASSWORD
    fi

    local timestamp_url="${WINDOWS_TIMESTAMP_URL:-http://timestamp.digicert.com}"

    # 1. Tauri 빌드
    log "Tauri build (Windows)..."
    cargo tauri build

    # 2. .exe / .msi 찾기
    local exe_path msi_path
    exe_path="$(find "$BUNDLE_DIR" -name 'hwarang-grid*.exe' | head -1 || true)"
    msi_path="$(find "$BUNDLE_DIR" -name '*.msi' | head -1 || true)"

    # 3. signtool / osslsigncode 선택
    local signer=""
    if command -v signtool &>/dev/null; then
        signer="signtool"
    elif command -v osslsigncode &>/dev/null; then
        signer="osslsigncode"
    else
        warn "signtool / osslsigncode 둘 다 없음. 서명 건너뜀."
        SIGN_SKIP=1
    fi

    sign_one() {
        local file="$1"
        [[ -z "$file" || ! -f "$file" ]] && return 0
        log "서명: $file"
        if [[ "${SIGN_SKIP:-0}" == "1" ]]; then
            return 0
        fi
        if [[ "$signer" == "signtool" ]]; then
            signtool sign /fd SHA256 \
                /f "$WINDOWS_CERT_PATH" \
                /p "$WINDOWS_CERT_PASSWORD" \
                /tr "$timestamp_url" \
                /td SHA256 \
                "$file"
            signtool verify /pa "$file"
        else
            local out="${file}.signed"
            osslsigncode sign \
                -pkcs12 "$WINDOWS_CERT_PATH" \
                -pass "$WINDOWS_CERT_PASSWORD" \
                -t "$timestamp_url" \
                -h sha256 \
                -in "$file" \
                -out "$out"
            mv "$out" "$file"
        fi
        ok "서명 완료: $file"
    }

    sign_one "$exe_path"
    sign_one "$msi_path"

    # 4. dist/ 로 복사 + 체크섬
    local arch_tag="x64"
    if [[ -n "$msi_path" ]]; then
        local out="Hwarang-Grid-Agent-${VERSION}-${arch_tag}.msi"
        cp "$msi_path" "$DIST_DIR/$out"
        (cd "$DIST_DIR" && sha256sum "$out" > "${out}.sha256" 2>/dev/null || shasum -a 256 "$out" > "${out}.sha256")
        ok "$out"
    fi
    if [[ -n "$exe_path" ]]; then
        local out="Hwarang-Grid-Agent-${VERSION}-${arch_tag}-setup.exe"
        cp "$exe_path" "$DIST_DIR/$out"
        (cd "$DIST_DIR" && sha256sum "$out" > "${out}.sha256" 2>/dev/null || shasum -a 256 "$out" > "${out}.sha256")
        ok "$out"
    fi
}

# ─── Linux 패키징 ─────────────────────────────────────────────────────────────
package_linux() {
    log "Linux 빌드 시작..."

    cargo tauri build

    local arch_tag
    arch_tag="$(uname -m)"

    # .deb
    local deb_path
    deb_path="$(find "$BUNDLE_DIR" -name '*.deb' | head -1 || true)"
    if [[ -n "$deb_path" ]]; then
        local out="hwarang-grid-agent_${VERSION}_${arch_tag}.deb"
        cp "$deb_path" "$DIST_DIR/$out"
        (cd "$DIST_DIR" && sha256sum "$out" > "${out}.sha256")
        ok "$out"
    fi

    # AppImage
    local appimg_path
    appimg_path="$(find "$BUNDLE_DIR" -name '*.AppImage' | head -1 || true)"
    if [[ -n "$appimg_path" ]]; then
        local out="Hwarang-Grid-Agent-${VERSION}-${arch_tag}.AppImage"
        cp "$appimg_path" "$DIST_DIR/$out"
        chmod +x "$DIST_DIR/$out"
        (cd "$DIST_DIR" && sha256sum "$out" > "${out}.sha256")
        ok "$out"
    fi
}

# ─── 메인 라우터 ──────────────────────────────────────────────────────────────
case "$TARGET" in
    mac|macos|darwin)
        sign_macos
        ;;
    windows|win)
        sign_windows
        ;;
    linux)
        package_linux
        ;;
    all)
        case "$(uname -s)" in
            Darwin)  sign_macos ;;
            Linux)   package_linux ;;
            MINGW*|MSYS*|CYGWIN*)  sign_windows ;;
            *) err "알 수 없는 OS: $(uname -s)"; exit 4 ;;
        esac
        ;;
    *)
        err "알 수 없는 타겟: $TARGET (mac|windows|linux|all)"
        exit 1
        ;;
esac

echo
ok "═══════════════════════════════════════════"
ok " 빌드 완료: $DIST_DIR"
ok "═══════════════════════════════════════════"
ls -lh "$DIST_DIR"
