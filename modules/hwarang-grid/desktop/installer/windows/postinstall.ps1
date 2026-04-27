# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — Windows 첫 실행 / 설치 후 동작
#
# 호출 시점: MSI/NSIS 설치 후 또는 .exe 첫 실행 시
# 동작:
#   1. %USERPROFILE%\.hwarang\ 디렉토리 생성
#   2. (옵션) 자동 시작 레지스트리 등록
#   3. Windows Defender 예외 처리 안내 (자동 등록 X, 안내만)
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

$AppName = "Hwarang Grid Agent"
$HwarangDir = Join-Path $env:USERPROFILE ".hwarang"
$InstallDir = Join-Path $env:LOCALAPPDATA "HwarangGrid"
$ExePath    = Join-Path $InstallDir "hwarang-grid.exe"

function Log($msg)  { Write-Host "[INFO] $msg" }
function OK($msg)   { Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

# 1. 사용자 디렉토리
Log "사용자 디렉토리 초기화..."
foreach ($sub in @("logs","cache","config")) {
    $path = Join-Path $HwarangDir $sub
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}
OK $HwarangDir

# 2. 자동 시작 (사용자 환경변수로 제어)
$enableAutostart = if ($env:HWARANG_AUTOSTART) { $env:HWARANG_AUTOSTART } else { "1" }

if ($enableAutostart -eq "1") {
    Log "자동 시작 등록 (HKCU\...\Run)..."
    $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    if (-not (Test-Path $runKey)) {
        New-Item -Path $runKey -Force | Out-Null
    }
    Set-ItemProperty -Path $runKey -Name "HwarangGrid" -Value "`"$ExePath`" --background"
    OK "자동 시작 등록 완료"
} else {
    Log "자동 시작 비활성화 (HWARANG_AUTOSTART != 1)"
}

# 3. Windows Defender 예외 안내 (자동 등록은 위험하므로 안내만)
Log "Windows Defender 예외 등록을 권장합니다 (관리자 권한 필요):"
Write-Host "  Add-MpPreference -ExclusionPath '$InstallDir'"
Write-Host "  Add-MpPreference -ExclusionPath '$HwarangDir'"

# 4. 방화벽 규칙 (Tauri 앱이 네트워크 사용)
try {
    $rule = Get-NetFirewallRule -DisplayName $AppName -ErrorAction SilentlyContinue
    if (-not $rule) {
        Log "방화벽 규칙 추가 시도 (관리자 권한이 있을 때만 성공)..."
        New-NetFirewallRule -DisplayName $AppName `
            -Direction Outbound `
            -Action Allow `
            -Program $ExePath `
            -Profile Any `
            -ErrorAction Stop | Out-Null
        OK "방화벽 규칙 추가됨"
    } else {
        OK "방화벽 규칙 이미 존재"
    }
} catch {
    Warn "방화벽 규칙 추가 실패 (관리자 권한 필요, 무시 가능)"
}

OK "초기화 완료"
Write-Host ""
Write-Host "  사용자 데이터:    $HwarangDir"
Write-Host "  설치 경로:        $InstallDir"
Write-Host "  자동 시작:        $($enableAutostart -eq '1')"
