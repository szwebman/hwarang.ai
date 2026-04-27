# Hwarang Grid Agent — 데스크탑 트레이 앱

Hwarang Grid 네트워크에 GPU 자원을 기여하는 사용자가 백그라운드에서 항상 실행해 두는
가벼운 트레이/메뉴바 앱. Tauri(Rust) 기반.

## 요구 사양

- Rust 1.74+
- Node 없음 (트레이 전용, WebView 사용 안 함)
- macOS 11+, Windows 10+, Linux (X11 + libayatana-appindicator 권장)

## 빌드

```bash
cd modules/hwarang-grid/desktop
./build.sh                      # 단순 래퍼 — cargo tauri build 호출
# 또는 직접:
cd src-tauri
cargo tauri build
```

생성물:
- macOS: `src-tauri/target/release/bundle/macos/Hwarang Grid Agent.app`
- Windows: `src-tauri/target/release/bundle/msi/*.msi`
- Linux: `.deb` 또는 `.AppImage`

## 트레이 아이콘 의미

| 색상 | 상태 | 설명 |
|------|------|------|
| 🟢 초록 | running | GPU가 작업을 처리 중 |
| 🟡 노랑 | idle | 에이전트는 켜져 있으나 작업 대기 중 |
| ⚪ 회색 | stopped | 에이전트 중지됨 |
| 🔴 빨강 | error | 연결 또는 GPU 오류 발생 |

아이콘 PNG는 `src-tauri/icons/icon-{green,yellow,gray,red}.png` 에 위치하며,
컴파일 시 `include_bytes!` 매크로로 바이너리에 임베드됩니다.

### 아이콘 재생성

```bash
cd src-tauri/icons
pip install Pillow              # 선택 — 없으면 단색 도트 fallback
python3 generate_state_icons.py
```

## 자동 시작 (Auto-launch)

트레이 메뉴 → "✓ 시스템 시작 시 자동 실행" 항목으로 토글.

내부적으로 `tauri-plugin-autostart` 사용.
- macOS: `~/Library/LaunchAgents/ai.hwarang.grid.plist` 등록
- Windows: 레지스트리 `HKCU\...\Run` 항목 추가
- Linux: `~/.config/autostart/Hwarang Grid Agent.desktop`

자동 시작 시 `--minimized` 인자로 실행되어 UI 창은 뜨지 않고 트레이만 활성화됩니다.

## 야간 모드

트레이 메뉴 → "🌙 야간 모드 (밤 10시-7시만)" 토글.

켜져 있으면 22:00-07:00 시간대에만 작업을 처리하고, 낮 동안에는 idle 상태로 유지됩니다.
GPU를 평소 사용하는 시간대에 작업으로 점유당하는 것을 막고 싶을 때 유용.

## 알림 (Notifications)

OS 네이티브 알림 5종이 자동 트리거됩니다:

| 알림 | 트리거 | 쿨다운 |
|------|--------|--------|
| HWARANG 보상 도착 💰 | `tokens_today` 증가 감지 | 30초 |
| 라운드 완료 ✅ | `current_round_id` → null + 토큰 증가 | 즉시 |
| KYC 인증 필요 🔐 | `kyc_verified == false` | 1회 |
| GPU 과열 경고 🔥 | `gpu_temp >= 85°C` | 5분 |
| 작업 실패 ⚠️ | `last_error` 채워짐 | 같은 에러 5분 |

전체 끄기: 트레이 메뉴 → "🔕 알림 꺼짐"

## 도메인 프리셋

GPU 작업을 받을 때 어떤 도메인 데이터에 우선 배정될지 선택:

- ⚖️ 법률 전문 (`law_specialist`)
- 🏥 의료 전문 (`medical_specialist`)
- 💼 세무 전문 (`tax_specialist`)
- 🌐 일반 (`general`)

선택하면 `~/.hwarang/agent_profile.yaml` 의 `preset:` 필드가 갱신되고,
실행 중인 Python 데몬에 `SIGUSR1` 시그널을 보내 즉시 재로드됩니다 (Unix 계열).
Windows에서는 다음 라운드부터 적용됩니다.

## 환경설정 파일

```
~/.hwarang/desktop_prefs.json     # 트레이 토글 상태 저장
~/.hwarang/agent_profile.yaml     # 도메인 프리셋
~/.hwarang/agent_status.json      # Python 에이전트가 쓰는 상태 (트레이가 읽음)
/tmp/hwarang-agent.pid            # Python 데몬 PID
```

`desktop_prefs.json` 예:

```json
{
  "autostart": true,
  "night_mode_only": false,
  "notifications_enabled": true,
  "selected_preset": "law_specialist"
}
```

## 트레이 메뉴 전체 구조

```
🟢 실행중 - GPU 작업 처리 중 | 오늘 +1.2K 토큰
   NVIDIA RTX 4090 | 67% | 72°C
   오늘 8건 처리 | 총 45K 토큰
─────────────────
⏹️ 중지
📊 내 현황 보기
🌐 커뮤니티 (Grid 현황)
⚙️ 설정
─────────────────
✓ 시스템 시작 시 자동 실행
  🌙 야간 모드 (밤 10시-7시만)
  🔔 알림 켜짐 (클릭 시 끄기)
─────────────────
🎯 도메인 프리셋:
  ✓ ⚖️  법률 전문
    🏥  의료 전문
    💼  세무 전문
    🌐  일반
─────────────────
🔗 hwarang.ai
─────────────────
종료
```

## 설정 윈도우 (Settings)

트레이 메뉴 → "⚙️ 설정" 클릭 시 600x720 의 네이티브 설정 창이 뜹니다
(`src/settings.html`, Tauri WebView 안에서 렌더링).

### 섹션
- **계정** : 이메일/KYC 상태/등급/전문 자격 표시. 로그인·로그아웃·KYC 시작 버튼.
- **전문 도메인** : `agent/config/presets/*.yaml` 과 1:1 매핑되는 6개 프리셋
  (`general`, `law_specialist`, `medical_specialist`, `tax_specialist`,
  `legal_and_tax`, `night_only`).
- **실행 설정** : 자동 시작, 자동 참여, 야간 모드, 동시 실행 라운드 수.
- **안전 설정** : 최대 VRAM/온도/라운드 시간, 화이트리스트 강제.
- **알림** : 5개 알림 종류 개별 on/off.
- **고급** : 로그 폴더 열기, 프로필 YAML 직접 열기, 업데이트 수동 확인,
  전체 초기화 (logs는 보존).

저장 시 `save_settings` 커맨드가 호출되어
- `profile` → `~/.hwarang/agent_profile.yaml` (YAML)
- `prefs`   → `~/.hwarang/desktop_prefs.json`
에 분리 저장된다. 닫기 버튼은 윈도우를 destroy 하지 않고 hide 처리하므로
다음 트레이 메뉴 클릭 시 동일 인스턴스가 재사용된다.

## KYC + 로그인 플로우

웹 인증을 그대로 재사용한다.

1. 사용자가 트레이 메뉴 / 설정창에서 **로그인** 클릭
2. 데스크탑이 외부 브라우저로
   `https://hwarang.ai/agent-login?nonce=<rand>&os=<macos|windows|linux>` 열기
3. 사용자가 웹에서 로그인 + (필요시) KYC 완료
4. 웹은 **deep link** 로
   `hwarang-grid://auth?token=<API_KEY>&nonce=<rand>&email=...&kyc=true&tier=GOLD`
   호출
5. 데스크탑은
   - nonce 일치 + 만료(10분) 검증
   - `GET https://hwarang.ai/api/auth/whoami` (Bearer token) 으로 서버 측 검증
   - `~/.hwarang/account.json` 저장 + 알림 발송

이미 로그인 된 상태에서 KYC만 시작하려면
`https://hwarang.ai/kyc?source=desktop_agent&token=<API_KEY>` 가 호출된다.

### Deep link 등록 (OS별)

`tauri-plugin-deep-link` 가 처리:
- **macOS** : 번들 `Info.plist` 에 `CFBundleURLTypes` 자동 등록
- **Windows** : 첫 실행 시 레지스트리 `HKCU\Software\Classes\hwarang-grid` 작성
- **Linux** : `~/.local/share/applications/ai.hwarang.grid.desktop` 의
  `MimeType=x-scheme-handler/hwarang-grid` 항목

### account.json 스키마

```json
{
  "email": "user@example.com",
  "user_id": "u_abc123",
  "api_key": "sk-xxxxx",
  "kyc_verified": true,
  "tier": "GOLD",
  "expert_credentials": ["lawyer", "tax_accountant"],
  "last_synced_at": "2026-04-22T10:30:00+09:00"
}
```

## 자동 업데이트 (Tauri Updater)

`tauri.conf.json` 의 `tauri.updater`:

```json
"updater": {
  "active": true,
  "endpoints": ["https://hwarang.ai/api/agent/update/latest.json"],
  "dialog": true,
  "pubkey": ""
}
```

> **운영 시 `pubkey`** 는 `cargo tauri signer generate -w ~/.tauri/hwarang.key`
> 로 생성한 공개키로 채워야 합니다. 빈 문자열이면 빌드 단계에서 경고가 발생합니다.

### 체크 주기
- 앱 시작 후 5분 뒤 1차 확인 (네트워크 안정화 대기)
- 이후 6시간마다 재확인
- 트레이 / 설정 → "🔄 업데이트 확인" 으로 즉시 수동 확인 가능

`dialog: true` 로 두면 새 버전 발견 시 Tauri 가 자동으로 사용자에게 prompt
다이얼로그를 띄운다. "지금 설치"를 누르면 `download_and_install()` 후 재기동.

### 서버 측 응답 형식

`GET https://hwarang.ai/api/agent/update/latest.json`:

```json
{
  "version": "0.2.0",
  "notes": "버그 수정 + 의료 도메인 보강",
  "pub_date": "2026-04-30T12:00:00Z",
  "platforms": {
    "darwin-aarch64": {
      "signature": "<base64 minisign>",
      "url": "https://hwarang.ai/downloads/hwarang-grid-0.2.0-arm64.app.tar.gz"
    },
    "darwin-x86_64": {
      "signature": "...",
      "url": "https://hwarang.ai/downloads/hwarang-grid-0.2.0-x64.app.tar.gz"
    },
    "windows-x86_64": {
      "signature": "...",
      "url": "https://hwarang.ai/downloads/hwarang-grid-0.2.0-x64-setup.nsis.zip"
    },
    "linux-x86_64": {
      "signature": "...",
      "url": "https://hwarang.ai/downloads/hwarang-grid-0.2.0-x64.AppImage.tar.gz"
    }
  }
}
```

서버는 단순 정적 JSON 으로 충분 (`hwarang-api` 의 `/api/agent/update/` 라우트
구현). 서명은 빌드 산출물 옆 `*.sig` 파일에서 읽어 base64 로 인코딩.

## 로그 시스템

| 항목 | 위치 |
|------|------|
| 로그 파일 | `~/.hwarang/logs/desktop-YYYY-MM-DD.log` |
| 보존 기간 | 30 일 (앱 시작 시 자동 로테이션) |
| 출력 레벨 | release: INFO 이상 / debug: DEBUG 포함 |

설정창 → "📁 로그 폴더 열기" 로 OS 파일 탐색기로 곧장 이동.

### 로그 형식

```
[2026-04-22 14:23:01] [INFO ] [hwarang_grid::auth] 로그인 플로우 시작: nonce=a1b2c3d4
[2026-04-22 14:23:18] [INFO ] [hwarang_grid::auth] 로그인 처리 완료: email=Some("user@x.com"), kyc=true
[2026-04-22 14:24:00] [WARN ] [hwarang_grid] 업데이트 체크 실패: connection timeout
```

## 트러블슈팅

- **Linux: 트레이가 안 보임** — `libayatana-appindicator3-1` 패키지 설치
- **Windows: 자동 시작이 안 됨** — 일부 백신이 Run 레지스트리 변경을 차단합니다.
  관리자 권한으로 한 번 실행해 주세요.
- **Mac: 메뉴바에 아이콘 대신 빈 공간** — `tauri.conf.json` 의
  `iconAsTemplate` 을 `false` 로 두면 컬러 PNG가 그대로 표시됩니다.
- **알림이 뜨지 않음** — OS 알림 권한 (`시스템 설정 → 알림 → Hwarang Grid Agent`)
  허용 여부 확인.
- **deep link 가 안 잡힘 (macOS)** — `.app` 번들이 `Applications/` 에 설치된
  상태에서 한 번 실행해야 `Launch Services` 가 스킴을 등록합니다. dev 모드
  실행 시에는 등록되지 않을 수 있음.
- **업데이터 검증 실패** — `pubkey` 와 빌드 시 사용한 비밀키가 일치하는지 확인.
  `tauri.conf.json` pubkey 와 `TAURI_PRIVATE_KEY` 환경변수 페어 매칭 필수.
