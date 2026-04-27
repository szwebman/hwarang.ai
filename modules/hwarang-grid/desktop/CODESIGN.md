# 코드 사이닝 가이드

화랑 Grid Agent 데스크탑 앱을 일반 사용자에게 배포하기 전에 코드 사이닝을 해야 합니다. 사이닝 없이 배포하면 macOS / Windows 모두 보안 경고를 띄워 사용자 다수가 설치를 포기합니다.

---

## 왜 필요한가?

| OS | 사이닝 없을 때 | 사이닝 했을 때 |
|---|---|---|
| macOS | 첫 실행 시 "확인되지 않은 개발자" 경고. 우클릭 → 열기 필요 | 더블클릭 즉시 실행 |
| Windows | SmartScreen "알 수 없는 게시자" 큰 경고창 | 신뢰된 게시자로 즉시 설치 |
| Linux | 경고 없음 (실용 목적상 불필요) | — |

---

## macOS 사이닝

### 1. Apple Developer Program 가입

- https://developer.apple.com/programs/ → $99/년
- 개인 / 단체 계정 모두 가능 (단체가 회사 명의로 표시됨)

### 2. 인증서 생성

1. Xcode → Preferences → Accounts → Apple ID 추가
2. **Manage Certificates** → `+` → **Developer ID Application**
3. (DMG 직접 서명하려면) **Developer ID Installer** 도 추가
4. 키체인에 자동 등록됨

확인:
```bash
security find-identity -v -p codesigning
# 출력 예:
#  1) ABC123... "Developer ID Application: Hong Gildong (TEAMID12)"
```

### 3. 앱 전용 암호 (App-Specific Password)

공증(notarytool)에 사용합니다.

1. https://appleid.apple.com → 로그인 → 보안 → **앱 암호**
2. 라벨: `hwarang-notarize`
3. 생성된 16자 암호를 안전한 곳에 보관

### 4. 환경변수 설정

```bash
# ~/.zshrc 또는 ~/.bashrc
export APPLE_SIGNING_IDENTITY="Developer ID Application: Hong Gildong (TEAMID12)"
export APPLE_ID="you@example.com"
export APPLE_PASSWORD="abcd-efgh-ijkl-mnop"   # 4. 에서 받은 앱 전용 암호
export APPLE_TEAM_ID="TEAMID12"               # 인증서 괄호 안 10자
```

**보안 주의**: `.zshrc` 대신 `~/.config/hwarang/secrets.env` 같은 파일에 저장 후 `source` 하는 것이 안전합니다. CI에서는 GitHub Secrets / AWS Secrets Manager 사용.

### 5. entitlements.plist 확인

`src-tauri/entitlements.plist` 가 존재해야 합니다 (Hardened Runtime용):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.cs.allow-jit</key>
  <true/>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
  <true/>
  <key>com.apple.security.network.client</key>
  <true/>
  <key>com.apple.security.network.server</key>
  <true/>
  <key>com.apple.security.device.audio-input</key>
  <false/>
</dict>
</plist>
```

### 6. 빌드 & 공증

```bash
./build_signed.sh mac
```

스크립트 내부 단계:
1. `cargo tauri build` (Universal binary)
2. `codesign` (Hardened Runtime + Timestamp)
3. `hdiutil` 또는 `create-dmg` 로 .dmg 생성
4. .dmg 도 codesign
5. `xcrun notarytool submit` (Apple 서버에 제출, 보통 2~10분)
6. `xcrun stapler staple` (오프라인 검증 가능하게)

성공 시 `dist/Hwarang-Grid-Agent-<version>-universal.dmg` 가 생성됩니다.

### 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| `errSecInternalComponent` | 키체인 잠금 → `security unlock-keychain login.keychain` |
| `notarytool: Invalid credentials` | 앱 전용 암호 만료. 재발급 |
| `not stapled` | 인터넷 끊긴 상태. notarytool 다시 실행 |
| `The executable does not have the hardened runtime enabled` | `--options runtime` 누락 |

---

## Windows 사이닝

### 1. 인증서 종류 선택

| 종류 | 가격 | SmartScreen 평판 | 발급 |
|---|---|---|---|
| **OV (Organization Validation)** | $200~$300/년 | 시간 지나며 누적 | 1~3일 |
| **EV (Extended Validation)** | $300~$500/년 | 즉시 신뢰 | 1~2주 (HW 토큰 발송) |
| Self-signed | 무료 | 사용자 PC에 수동 설치해야 인식 | 즉시 |

권장: **첫 출시는 OV**로 시작 → 다운로드 누적되면 EV 업그레이드.

발급사 예: DigiCert, Sectigo, GlobalSign, SSL.com

### 2. .pfx 변환

발급받은 인증서를 `.pfx` (PKCS#12) 형식으로 export:

- Windows 인증서 관리자 (`certmgr.msc`) → 인증서 우클릭 → 내보내기 → 개인 키 포함 → .pfx
- 강력한 암호 설정

### 3. 환경변수

```powershell
# PowerShell (영구 저장: System Properties → Environment Variables)
$env:WINDOWS_CERT_PATH = "C:\secure\hwarang-codesign.pfx"
$env:WINDOWS_CERT_PASSWORD = "<강력한 암호>"
$env:WINDOWS_TIMESTAMP_URL = "http://timestamp.digicert.com"
```

### 4. signtool 또는 osslsigncode

- **Windows에서 직접 빌드**: Windows SDK에 포함된 `signtool.exe` 사용 (스크립트가 자동 감지)
- **macOS / Linux 크로스 컴파일**: `osslsigncode` 설치
  ```bash
  brew install osslsigncode      # macOS
  apt install osslsigncode       # Debian/Ubuntu
  ```

### 5. 빌드

```bash
./build_signed.sh windows
```

생성:
- `dist/Hwarang-Grid-Agent-<version>-x64.msi`
- `dist/Hwarang-Grid-Agent-<version>-x64-setup.exe`

### EV 인증서 (HW 토큰)

EV 는 USB 토큰에 키가 저장되어 있어 자동화가 까다롭습니다.

- DigiCert KeyLocker / SafeNet eToken Pass 자동 입력 도구 활용
- CI/CD: GitHub-hosted runner 에서는 사용 불가 → self-hosted runner 필수
- 또는 클라우드 HSM (Azure Key Vault, AWS CloudHSM)

---

## 사이닝 안 하면 어떻게 보이나

### macOS
사용자가 .app 더블클릭 시:
> **"확인할 수 없는 개발자이기 때문에 'Hwarang Grid Agent.app'을(를) 열 수 없습니다."**

회피법 (사용자에게 안내):
1. Finder 에서 .app **우클릭 → 열기**
2. "여시겠습니까?" → 열기

### Windows
사용자가 .exe 더블클릭 시:
> **"Windows에서 PC를 보호했습니다 / 알 수 없는 게시자"**

회피법 (사용자에게 안내):
1. "추가 정보" 클릭
2. "실행" 버튼

---

## CI/CD 자동화

`.github/workflows/release.yml` 에서 GitHub Secrets 로 주입:

```yaml
env:
  APPLE_SIGNING_IDENTITY: ${{ secrets.APPLE_SIGNING_IDENTITY }}
  APPLE_ID:               ${{ secrets.APPLE_ID }}
  APPLE_PASSWORD:         ${{ secrets.APPLE_PASSWORD }}
  APPLE_TEAM_ID:          ${{ secrets.APPLE_TEAM_ID }}
  WINDOWS_CERT_BASE64:    ${{ secrets.WINDOWS_CERT_BASE64 }}  # base64 인코딩된 .pfx
  WINDOWS_CERT_PASSWORD:  ${{ secrets.WINDOWS_CERT_PASSWORD }}
```

**중요**:
- 키체인/.pfx 를 GitHub 저장소에 절대 커밋하지 마세요.
- macOS 키체인은 CI에서 임시 키체인 생성 후 `security import` 사용.
- 토큰 만료 모니터링 (Apple 인증서 1년, OV/EV 1~3년).

---

## 비용 요약

| 항목 | 비용 (1년) |
|---|---|
| Apple Developer Program | $99 |
| Windows OV 인증서 | $200~$300 |
| Windows EV 인증서 | $300~$500 |
| **최소 합계 (OV)** | ~$300 |
| **권장 합계 (EV)** | ~$600 |

---

## 빠른 체크리스트

### macOS
- [ ] Apple Developer 가입
- [ ] Developer ID Application 인증서 생성
- [ ] 앱 전용 암호 발급
- [ ] 환경변수 4개 설정
- [ ] `entitlements.plist` 작성
- [ ] `./build_signed.sh mac` 성공
- [ ] 다른 Mac에서 다운로드 → 더블클릭 → 경고 없이 실행 확인

### Windows
- [ ] OV 또는 EV 인증서 구매
- [ ] .pfx 로 변환 + 안전한 보관
- [ ] 환경변수 3개 설정
- [ ] signtool 또는 osslsigncode 설치
- [ ] `./build_signed.sh windows` 성공
- [ ] 다른 PC에서 다운로드 → 실행 → SmartScreen 통과 확인
