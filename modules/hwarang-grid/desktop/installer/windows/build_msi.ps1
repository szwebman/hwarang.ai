# ─────────────────────────────────────────────────────────────────────────────
# 화랑 Grid Agent — Windows MSI 빌드 (WiX Toolset)
#
# 사전 요구:
#   1. WiX Toolset v3.11+ 설치 (https://wixtoolset.org/releases/)
#      Chocolatey: choco install wixtoolset -y
#   2. PowerShell 5.0+
#
# 사용법:
#   .\build_msi.ps1
#   .\build_msi.ps1 -Version "0.2.0" -Sign $true
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

param(
    [string]$Version = "",
    [switch]$Sign = $false,
    [string]$OutDir = ""
)

# ─── 경로 ──────────────────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir = Resolve-Path "$ScriptDir\..\.."
$BundleDir = Join-Path $DesktopDir "src-tauri\target\release"
$DistDir = if ($OutDir) { $OutDir } else { Join-Path $DesktopDir "dist" }

if (-not (Test-Path $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir | Out-Null
}

# ─── 버전 추출 ─────────────────────────────────────────────────────────────
if (-not $Version) {
    $tauriConf = Get-Content (Join-Path $DesktopDir "src-tauri\tauri.conf.json") -Raw | ConvertFrom-Json
    $Version = $tauriConf.package.version
}
Write-Host "[INFO] 버전: $Version"

# ─── WiX 도구 확인 ────────────────────────────────────────────────────────
$candle = (Get-Command candle.exe -ErrorAction SilentlyContinue).Source
$light  = (Get-Command light.exe -ErrorAction SilentlyContinue).Source

if (-not $candle -or -not $light) {
    # 기본 설치 경로 시도
    $wixPath = "${env:ProgramFiles(x86)}\WiX Toolset v3.11\bin"
    if (Test-Path "$wixPath\candle.exe") {
        $candle = "$wixPath\candle.exe"
        $light  = "$wixPath\light.exe"
    } else {
        Write-Error "WiX Toolset 미설치. https://wixtoolset.org/releases/ 에서 설치하세요."
        exit 1
    }
}

Write-Host "[INFO] candle: $candle"
Write-Host "[INFO] light:  $light"

# ─── 빌드 디렉토리 준비 ────────────────────────────────────────────────────
$BuildDir = Join-Path $env:TEMP "hwarang-msi-build"
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
New-Item -ItemType Directory -Path $BuildDir | Out-Null

# 실행파일 복사
$ExeSrc = Join-Path $BundleDir "hwarang-grid.exe"
if (-not (Test-Path $ExeSrc)) {
    Write-Host "[INFO] hwarang-grid.exe 빌드 중 (cargo tauri build)..."
    Push-Location $DesktopDir
    try {
        cargo tauri build
        if ($LASTEXITCODE -ne 0) { throw "cargo tauri build 실패" }
    } finally {
        Pop-Location
    }
}
Copy-Item $ExeSrc $BuildDir
Copy-Item (Join-Path $ScriptDir "installer.wxs") $BuildDir
Copy-Item (Join-Path $DesktopDir "installer\uninstall\uninstall_windows.ps1") $BuildDir

# 라이선스 (없으면 더미 생성)
$LicenseRtf = Join-Path $BuildDir "license.rtf"
if (-not (Test-Path (Join-Path $ScriptDir "license.rtf"))) {
    @"
{\rtf1\ansi\deff0
{\fonttbl{\f0 Calibri;}}
\f0\fs22 Hwarang Grid Agent\par
Copyright (c) Hwarang AI\par\par
이 소프트웨어는 사용자에게 GPU 공유 네트워크 참여 기능을 제공합니다.\par
}
"@ | Out-File -FilePath $LicenseRtf -Encoding ASCII
} else {
    Copy-Item (Join-Path $ScriptDir "license.rtf") $LicenseRtf
}

# ─── candle (.wxs → .wixobj) ───────────────────────────────────────────────
Write-Host "[INFO] candle 컴파일..."
Push-Location $BuildDir
try {
    & $candle "installer.wxs" -ext WixUtilExtension
    if ($LASTEXITCODE -ne 0) { throw "candle 실패" }

    # ─── light (.wixobj → .msi) ────────────────────────────────────────────
    $MsiName = "Hwarang-Grid-Agent-$Version-x64.msi"
    Write-Host "[INFO] light 링크 → $MsiName ..."
    & $light "installer.wixobj" `
        -ext WixUIExtension `
        -ext WixUtilExtension `
        -cultures:ko-kr `
        -o $MsiName
    if ($LASTEXITCODE -ne 0) { throw "light 실패" }

    $MsiPath = Join-Path $BuildDir $MsiName

    # ─── 서명 ──────────────────────────────────────────────────────────────
    if ($Sign) {
        if (-not $env:WINDOWS_CERT_PATH -or -not $env:WINDOWS_CERT_PASSWORD) {
            Write-Warning "WINDOWS_CERT_PATH / WINDOWS_CERT_PASSWORD 미설정 → 서명 건너뜀"
        } else {
            $tsUrl = if ($env:WINDOWS_TIMESTAMP_URL) { $env:WINDOWS_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }
            Write-Host "[INFO] MSI 서명..."
            & signtool sign `
                /fd SHA256 `
                /f $env:WINDOWS_CERT_PATH `
                /p $env:WINDOWS_CERT_PASSWORD `
                /tr $tsUrl `
                /td SHA256 `
                $MsiPath
            if ($LASTEXITCODE -ne 0) { throw "signtool 실패" }
            Write-Host "[ OK ] 서명 완료"
        }
    }

    # ─── 결과 복사 + 체크섬 ───────────────────────────────────────────────
    $FinalMsi = Join-Path $DistDir $MsiName
    Copy-Item $MsiPath $FinalMsi -Force

    $hash = (Get-FileHash $FinalMsi -Algorithm SHA256).Hash.ToLower()
    "$hash  $MsiName" | Out-File -FilePath "$FinalMsi.sha256" -Encoding ASCII

    Write-Host ""
    Write-Host "[ OK ] 빌드 완료" -ForegroundColor Green
    Write-Host "  MSI:      $FinalMsi"
    Write-Host "  체크섬:   $FinalMsi.sha256"
} finally {
    Pop-Location
}
