# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — Windows 제거 스크립트
#
# 사용법:
#   .\uninstall_windows.ps1                # 대화형
#   .\uninstall_windows.ps1 -YesAll        # 사용자 데이터까지 모두 삭제
#   .\uninstall_windows.ps1 -Keep          # 사용자 데이터 유지
# ─────────────────────────────────────────────────────────────────────────────

param(
    [switch]$YesAll = $false,
    [switch]$Keep   = $false
)

$ErrorActionPreference = "Continue"  # 일부 단계 실패해도 계속 진행

$AppName     = "Hwarang Grid Agent"
$InstallDir  = Join-Path $env:LOCALAPPDATA "HwarangGrid"
$HwarangDir  = Join-Path $env:USERPROFILE ".hwarang"
$StartMenu   = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Hwarang Grid"
$DesktopLnk  = Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk"

function Log($msg)  { Write-Host "[INFO] $msg" }
function OK($msg)   { Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

Write-Host "═══════════════════════════════════════════"
Write-Host " 화랑 Grid Agent 제거"
Write-Host "═══════════════════════════════════════════"

# 1. 프로세스 종료
Log "에이전트 종료 중..."
Get-Process -Name "hwarang-grid" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $_.Kill()
        $_.WaitForExit(5000) | Out-Null
    } catch { }
}
Start-Sleep -Seconds 1
OK "프로세스 종료"

# 2. 자동 시작 레지스트리 제거
Log "자동 시작 키 제거..."
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty -Path $runKey -Name "HwarangGrid" -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $runKey -Name "HwarangGrid" -ErrorAction SilentlyContinue
    OK "자동 시작 제거"
}

# 3. 시작 메뉴 / 데스크탑 바로가기
if (Test-Path $StartMenu) {
    Remove-Item -Recurse -Force $StartMenu
    OK "시작 메뉴 정리"
}
if (Test-Path $DesktopLnk) {
    Remove-Item -Force $DesktopLnk
    OK "데스크탑 바로가기 제거"
}

# 4. 방화벽 규칙
try {
    $rule = Get-NetFirewallRule -DisplayName $AppName -ErrorAction SilentlyContinue
    if ($rule) {
        Remove-NetFirewallRule -DisplayName $AppName -ErrorAction SilentlyContinue
        OK "방화벽 규칙 제거"
    }
} catch { Warn "방화벽 규칙 제거 실패 (무시 가능)" }

# 5. 설치 폴더
if (Test-Path $InstallDir) {
    Log "설치 폴더 삭제..."
    try {
        Remove-Item -Recurse -Force $InstallDir
        OK "$InstallDir 삭제"
    } catch {
        Warn "삭제 실패. 수동 삭제 필요: $InstallDir"
    }
}

# 6. 제어판 등록 정리
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
if (Test-Path $uninstallKey) {
    Remove-Item -Recurse -Force $uninstallKey -ErrorAction SilentlyContinue
    OK "제어판 등록 정리"
}

$brandKey = "HKCU:\Software\HwarangAI"
if (Test-Path $brandKey) {
    Remove-Item -Recurse -Force $brandKey -ErrorAction SilentlyContinue
}

# 7. 사용자 데이터
if (Test-Path $HwarangDir) {
    $shouldDelete = $false
    if ($YesAll) {
        $shouldDelete = $true
    } elseif ($Keep) {
        $shouldDelete = $false
    } else {
        Write-Host ""
        $answer = Read-Host "사용자 데이터 ($HwarangDir) 도 삭제하시겠습니까? [y/N]"
        if ($answer -match '^[Yy]') { $shouldDelete = $true }
    }

    if ($shouldDelete) {
        Remove-Item -Recurse -Force $HwarangDir
        OK "사용자 데이터 삭제: $HwarangDir"
    } else {
        Log "사용자 데이터 유지: $HwarangDir"
    }
}

Write-Host ""
Write-Host "═══════════════════════════════════════════" -ForegroundColor Green
Write-Host " 화랑 Grid Agent 제거 완료" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════" -ForegroundColor Green
