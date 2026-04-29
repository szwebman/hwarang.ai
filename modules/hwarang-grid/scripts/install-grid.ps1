# 화랑그리드 CLI Windows 설치
# 사용:
#   irm https://hwarang.ai/install-grid.ps1 | iex
#   $env:HWARANG_VERSION="v1.0.0"; irm https://hwarang.ai/install-grid.ps1 | iex

$ErrorActionPreference = "Stop"

# ───── 설정 ─────
$Repo       = if ($env:HWARANG_REPO)    { $env:HWARANG_REPO }    else { "gallera/hwarang.ai" }
$Version    = if ($env:HWARANG_VERSION) { $env:HWARANG_VERSION } else { "latest" }
$DoLogin    = if ($env:HWARANG_LOGIN)   { $true }                else { $false }
$InstallDir = if ($env:HWARANG_PREFIX)  { $env:HWARANG_PREFIX }  else { "$env:LOCALAPPDATA\HwarangGrid" }

function Log($msg)  { Write-Host "[화랑] $msg"  -ForegroundColor Green }
function Warn($msg) { Write-Host "[화랑 ⚠] $msg" -ForegroundColor Yellow }
function Err($msg)  { Write-Host "[화랑 ✗] $msg" -ForegroundColor Red; exit 1 }

# ───── 아키텍처 감지 ─────
$arch = if ([Environment]::Is64BitOperatingSystem) {
  if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x86_64" }
} else {
  Err "32비트 Windows 는 지원하지 않습니다."
}
$Artifact = "hwarang-agent-windows-$arch.exe"

# ───── 버전 결정 ─────
if ($Version -eq "latest") {
  Log "최신 버전 조회 중..."
  try {
    $rel = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest" -UseBasicParsing
    $Version = $rel.tag_name
  } catch {
    Err "최신 버전을 가져오지 못했습니다: $_"
  }
}
Log "설치 버전: $Version ($arch)"

# ───── 다운로드 ─────
$Url    = "https://github.com/$Repo/releases/download/$Version/$Artifact"
$ShaUrl = "$Url.sha256"
$Tmp    = New-TemporaryFile
$TmpExe = "$($Tmp.FullName).exe"
Remove-Item $Tmp -Force

Log "다운로드: $Url"
try {
  Invoke-WebRequest -Uri $Url -OutFile $TmpExe -UseBasicParsing
} catch {
  Err "다운로드 실패: $_"
}

# ───── SHA256 검증 ─────
try {
  $expected = (Invoke-WebRequest -Uri $ShaUrl -UseBasicParsing).Content.Trim().Split(" ")[0]
  $actual   = (Get-FileHash -Algorithm SHA256 -Path $TmpExe).Hash.ToLower()
  if ($expected -and $actual -ne $expected.ToLower()) {
    Remove-Item $TmpExe -Force
    Err "체크섬 불일치 — 다운로드 손상 가능성"
  }
  Log "체크섬 OK"
} catch {
  Warn "체크섬 파일 없음 — 검증 생략"
}

# ───── 설치 ─────
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Target = Join-Path $InstallDir "hwarang-agent.exe"
Move-Item -Path $TmpExe -Destination $Target -Force
Log "설치 위치: $Target"

# ───── PATH 추가 (User scope, 멱등) ─────
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
$paths = $userPath.Split(";") | Where-Object { $_ -ne "" }
if ($paths -notcontains $InstallDir) {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$InstallDir", "User")
  Warn "PATH 에 추가됨 (새 셸에서 적용): $InstallDir"
}
$env:Path = "$env:Path;$InstallDir"

# ───── 검증 ─────
try {
  & $Target version
  Log "✓ 설치 완료"
} catch {
  Warn "검증 실패 — 직접 실행해 보세요: $Target --help"
}

Write-Host ""
Write-Host "다음 단계:" -ForegroundColor Cyan
Write-Host "  hwarang-agent login"
Write-Host "  hwarang-agent daemon"
Write-Host "  hwarang-agent status"
Write-Host ""
Write-Host "문서: https://hwarang.ai/grid/docs"
Write-Host ""

if ($DoLogin) {
  Log "로그인 시작..."
  & $Target login
}
