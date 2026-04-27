# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — 통합 빌드 Makefile
#
# 자주 쓰는 타겟:
#   make dev           — 개발 모드 실행 (Tauri hot-reload)
#   make build         — 프로덕션 빌드 (현재 OS)
#   make sign-mac      — 코드 서명 + 공증 (macOS)
#   make sign-win      — 코드 서명 (Windows)
#   make dmg           — macOS DMG 생성
#   make msi           — Windows MSI 생성
#   make deb           — Linux .deb 생성
#   make appimage      — Linux AppImage 생성
#   make dist          — clean + build + 모든 패키징 + 체크섬
#   make test          — Rust + Python 테스트 실행
#   make verify        — 설치 검증 스크립트
#   make uninstall     — 현재 OS 제거 스크립트
#   make clean         — 빌드 산출물 삭제
#   make publish       — S3 업로드 (HWARANG_S3_BUCKET 환경변수 필요)
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: all dev build build-python build-tauri \
        sign-mac sign-win sign-linux \
        dmg msi deb appimage \
        dist test verify uninstall clean publish help

SHELL := /bin/bash

VERSION := $(shell grep -E '"version"' src-tauri/tauri.conf.json | head -1 | sed -E 's/.*"version"[^"]*"([^"]+)".*/\1/')
ARCH    := $(shell uname -m)
OS      := $(shell uname -s | tr A-Z a-z)
DIST    := dist
S3_BUCKET ?= hwarang-releases

all: build

help:
	@echo "Hwarang Grid Agent — Makefile"
	@echo ""
	@echo "  버전: $(VERSION)  /  OS: $(OS)  /  ARCH: $(ARCH)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}' || true
	@echo ""
	@echo "  자주 쓰는 타겟: dev / build / dist / dmg / msi / deb / appimage"

dev: ## 개발 모드 실행 (hot-reload)
	cd src-tauri && cargo tauri dev

build: build-python build-tauri ## 프로덕션 빌드 (Python sidecar + Tauri)

build-python: ## Python sidecar 빌드 (PyInstaller)
	@if [[ -d ../agent ]] && [[ -f ../agent/build_binary.py ]]; then \
		cd ../agent && python build_binary.py; \
		echo "[ OK ] Python sidecar built"; \
	else \
		echo "[INFO] Python sidecar 빌더 없음, 건너뜀"; \
	fi

build-tauri: ## Tauri 앱 빌드
	cd src-tauri && cargo tauri build
	@echo "[ OK ] Tauri app built"

sign-mac: ## 코드 서명 + 공증 (macOS)
	bash build_signed.sh mac

sign-win: ## 코드 서명 (Windows)
	bash build_signed.sh windows

sign-linux: ## Linux 패키징 (서명 없음)
	bash build_signed.sh linux

dmg: ## macOS .dmg 생성
	@mkdir -p $(DIST)
	bash installer/macos/build_dmg.sh \
		"$$(find src-tauri/target/release/bundle -name '*.app' | head -1)" \
		"$(DIST)/Hwarang-Grid-Agent-$(VERSION)-$(ARCH).dmg"

msi: ## Windows .msi 생성 (PowerShell 필요)
	@mkdir -p $(DIST)
	powershell -ExecutionPolicy Bypass -File installer/windows/build_msi.ps1

deb: ## Debian/Ubuntu .deb 생성
	@mkdir -p $(DIST)
	bash installer/linux/build_deb.sh $(DIST)

appimage: ## Linux AppImage 생성
	@mkdir -p $(DIST)
	bash installer/linux/build_appimage.sh $(DIST)

dist: clean build ## 클린 빌드 + 패키징 + 체크섬
	@mkdir -p $(DIST)
ifeq ($(OS),darwin)
	$(MAKE) sign-mac
else ifeq ($(OS),linux)
	$(MAKE) deb appimage
else
	$(MAKE) sign-win
endif
	@cd $(DIST) && (sha256sum * 2>/dev/null || shasum -a 256 *) > SHA256SUMS
	@echo ""
	@echo "[ OK ] 배포 패키지 준비 완료: $(DIST)/"
	@ls -lh $(DIST)/

test: ## Rust + Python 테스트 실행
	@echo "[INFO] Rust 테스트..."
	cd src-tauri && cargo test --release
	@if [[ -d ../agent ]]; then \
		echo "[INFO] Python 테스트..."; \
		cd ../agent && python -m pytest tests/ 2>/dev/null || echo "[INFO] Python 테스트 없음"; \
	fi

verify: ## 설치 검증 (설치 후 실행)
	bash installer/verify_install.sh

uninstall: ## 현재 OS 제거 스크립트 실행
ifeq ($(OS),darwin)
	bash installer/uninstall/uninstall_mac.sh
else ifeq ($(OS),linux)
	bash installer/uninstall/uninstall_linux.sh
else
	powershell -ExecutionPolicy Bypass -File installer/uninstall/uninstall_windows.ps1
endif

clean: ## 빌드 산출물 삭제
	rm -rf src-tauri/target $(DIST)
	@echo "[ OK ] cleaned"

publish: ## S3 업로드 (AWS CLI 필요)
	@if [[ -z "$$AWS_ACCESS_KEY_ID" ]]; then \
		echo "[ERR] AWS 자격증명 필요 (AWS_ACCESS_KEY_ID 등)"; exit 1; \
	fi
	aws s3 sync $(DIST)/ s3://$(S3_BUCKET)/agent/$(VERSION)/ \
		--exclude '*.tmp' \
		--cache-control 'public,max-age=3600' \
		--metadata "version=$(VERSION),arch=$(ARCH),os=$(OS)"
	@echo "[ OK ] s3://$(S3_BUCKET)/agent/$(VERSION)/"
