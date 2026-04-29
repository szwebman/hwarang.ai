#!/usr/bin/env bash
# 화랑그리드 CLI 에이전트 원라이너 설치
# 사용:
#   curl -fsSL https://hwarang.ai/install-grid.sh | bash
#   curl -fsSL https://hwarang.ai/install-grid.sh | bash -s -- --login
#   curl -fsSL https://hwarang.ai/install-grid.sh | bash -s -- --version v1.0.0 --prefix ~/.local/bin

set -euo pipefail

# ───── 설정 (배포 시 수정) ─────
REPO="${HWARANG_REPO:-gallera/hwarang.ai}"
DEFAULT_VERSION="${HWARANG_VERSION:-latest}"
DEFAULT_PREFIX="/usr/local/bin"
USER_PREFIX="$HOME/.local/bin"

# ───── 색상 ─────
if [ -t 1 ]; then
  RED=$'\033[0;31m'
  GREEN=$'\033[0;32m'
  YELLOW=$'\033[0;33m'
  BOLD=$'\033[1m'
  RESET=$'\033[0m'
else
  RED=""
  GREEN=""
  YELLOW=""
  BOLD=""
  RESET=""
fi

log()  { printf "%s[화랑]%s %s\n" "$GREEN" "$RESET" "$*"; }
warn() { printf "%s[화랑 ⚠]%s %s\n" "$YELLOW" "$RESET" "$*" >&2; }
err()  { printf "%s[화랑 ✗]%s %s\n" "$RED" "$RESET" "$*" >&2; }

# ───── 인자 파싱 ─────
DO_LOGIN=0
VERSION="$DEFAULT_VERSION"
PREFIX=""
SKIP_CHECKSUM=0
USE_SUDO=0

while [ $# -gt 0 ]; do
  case "$1" in
    --login) DO_LOGIN=1; shift ;;
    --version) VERSION="$2"; shift 2 ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    --skip-checksum) SKIP_CHECKSUM=1; shift ;;
    --user) PREFIX="$USER_PREFIX"; shift ;;
    -h|--help)
      cat <<EOF
화랑그리드 CLI 설치 스크립트

사용:
  curl -fsSL https://hwarang.ai/install-grid.sh | bash
  curl -fsSL https://hwarang.ai/install-grid.sh | bash -s -- [옵션]

옵션:
  --login              설치 후 즉시 hwarang-agent login 실행
  --version VERSION    설치할 버전 (기본: latest)
  --prefix DIR         설치 경로 (기본: /usr/local/bin)
  --user               유저 디렉터리 설치 (~/.local/bin)
  --skip-checksum      SHA256 검증 생략 (권장 안 함)
  -h, --help           이 메시지

환경변수:
  HWARANG_REPO         GitHub repo (기본: gallera/hwarang.ai)
  HWARANG_VERSION      설치 버전
EOF
      exit 0
      ;;
    *) err "알 수 없는 옵션: $1"; exit 2 ;;
  esac
done

# ───── OS / Arch 감지 ─────
detect_platform() {
  local os arch
  os=$(uname -s | tr '[:upper:]' '[:lower:]')
  arch=$(uname -m)
  case "$os" in
    linux) os="linux" ;;
    darwin) os="macos" ;;
    *) err "지원하지 않는 OS: $os"; exit 3 ;;
  esac
  case "$arch" in
    x86_64|amd64) arch="x86_64" ;;
    aarch64|arm64) arch="arm64" ;;
    *) err "지원하지 않는 아키텍처: $arch"; exit 3 ;;
  esac
  echo "${os}-${arch}"
}

PLATFORM=$(detect_platform)
ARTIFACT="hwarang-agent-${PLATFORM}"
log "감지된 플랫폼: ${BOLD}${PLATFORM}${RESET}"

# ───── 의존성 체크 ─────
need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "$1 이 필요합니다 (설치: $2)"
    exit 4
  fi
}
need curl "https://curl.se/"
need uname "coreutils"

SHA_CMD=""
if [ "$SKIP_CHECKSUM" -eq 0 ]; then
  if command -v sha256sum >/dev/null 2>&1; then
    SHA_CMD="sha256sum"
  elif command -v shasum >/dev/null 2>&1; then
    SHA_CMD="shasum -a 256"
  else
    warn "sha256sum / shasum 없음 — 체크섬 검증 생략"
    SKIP_CHECKSUM=1
  fi
fi

# ───── 버전 결정 ─────
if [ "$VERSION" = "latest" ]; then
  log "최신 버전 조회 중..."
  VERSION=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
    | grep -oE '"tag_name":[[:space:]]*"[^"]+"' \
    | head -1 \
    | cut -d'"' -f4)
  if [ -z "$VERSION" ]; then
    err "최신 버전을 가져오지 못했습니다 (네트워크 / repo 권한 확인)"
    exit 5
  fi
fi
log "설치 버전: ${BOLD}${VERSION}${RESET}"

# ───── prefix 결정 ─────
if [ -z "$PREFIX" ]; then
  if [ -w "$DEFAULT_PREFIX" ] || [ "$(id -u)" -eq 0 ]; then
    PREFIX="$DEFAULT_PREFIX"
  elif command -v sudo >/dev/null 2>&1; then
    PREFIX="$DEFAULT_PREFIX"
    USE_SUDO=1
  else
    log "sudo 없음 → 유저 디렉터리에 설치"
    PREFIX="$USER_PREFIX"
  fi
fi

# ───── 다운로드 ─────
TMP_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t hwarang)
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${VERSION}/${ARTIFACT}"
SHA_URL="${DOWNLOAD_URL}.sha256"

log "다운로드: ${DOWNLOAD_URL}"
if ! curl -fL --progress-bar -o "$TMP_DIR/$ARTIFACT" "$DOWNLOAD_URL"; then
  err "다운로드 실패. 다른 OS/Arch 자산이 없거나 버전이 잘못됐을 수 있습니다."
  err "수동 다운로드: https://github.com/${REPO}/releases/${VERSION}"
  exit 6
fi

# ───── 체크섬 검증 ─────
if [ "$SKIP_CHECKSUM" -eq 0 ]; then
  log "SHA256 체크섬 검증 중..."
  if curl -fsSL "$SHA_URL" -o "$TMP_DIR/${ARTIFACT}.sha256" 2>/dev/null; then
    (
      cd "$TMP_DIR"
      # shellcheck disable=SC2086
      if ! $SHA_CMD -c "${ARTIFACT}.sha256" >/dev/null 2>&1; then
        err "체크섬 불일치 — 다운로드 손상 가능성"
        exit 7
      fi
    )
    log "체크섬 OK"
  else
    warn "체크섬 파일이 릴리즈에 없음 — 검증 생략"
  fi
fi

# ───── macOS Gatekeeper ─────
if [ "$(uname -s)" = "Darwin" ]; then
  xattr -d com.apple.quarantine "$TMP_DIR/$ARTIFACT" 2>/dev/null || true
fi

chmod +x "$TMP_DIR/$ARTIFACT"

# ───── 설치 ─────
TARGET="$PREFIX/hwarang-agent"
log "설치 위치: ${BOLD}${TARGET}${RESET}"

if [ "$USE_SUDO" -eq 1 ]; then
  log "sudo 권한 필요 (한 번만)"
  sudo mkdir -p "$PREFIX"
  sudo mv -f "$TMP_DIR/$ARTIFACT" "$TARGET"
else
  mkdir -p "$PREFIX"
  mv -f "$TMP_DIR/$ARTIFACT" "$TARGET"
fi

# ───── PATH 안내 ─────
case ":$PATH:" in
  *":${PREFIX}:"*) ;;
  *)
    warn "${PREFIX} 가 PATH 에 없습니다."
    warn "다음을 ~/.bashrc 또는 ~/.zshrc 에 추가하세요:"
    warn "  export PATH=\"${PREFIX}:\$PATH\""
    ;;
esac

# ───── 검증 ─────
if "$TARGET" version >/dev/null 2>&1; then
  log "${GREEN}✓ 설치 완료${RESET}"
  "$TARGET" version || true
elif "$TARGET" --help >/dev/null 2>&1; then
  log "${GREEN}✓ 설치 완료${RESET}"
else
  warn "검증 실패 — 직접 실행해 보세요: $TARGET --help"
fi

# ───── 다음 단계 안내 ─────
cat <<EOF

${BOLD}다음 단계:${RESET}
  hwarang-agent login        # 다중 기기 로그인
  hwarang-agent daemon       # 백그라운드 실행
  hwarang-agent status       # 현황 확인
  hwarang-agent --help       # 전체 명령

${BOLD}문서:${RESET}
  https://hwarang.ai/grid/docs

EOF

# ───── --login ─────
if [ "$DO_LOGIN" -eq 1 ]; then
  log "로그인 시작 (--login)..."
  exec "$TARGET" login
fi
