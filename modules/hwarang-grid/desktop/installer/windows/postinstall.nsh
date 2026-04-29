; ─────────────────────────────────────────────────────────────────────────────
;  화랑 Grid Agent — Windows NSIS 후크 (Tauri 1.x bundler)
;
;  Tauri 가 NSIS 인스톨러를 만들 때 본 파일의 매크로를 자동으로 주입한다.
;  목적:
;    1. 설치 후: PyInstaller 사이드카 (hwarang-agent.exe) 디렉토리를
;       시스템 PATH 에 등록 → 터미널에서 `hwarang-agent` 호출 가능
;    2. 제거 전: PATH 항목 정리
;
;  EnVar 플러그인은 NSIS 표준 플러그인 — Tauri 1.x 가 내장.
;  Machine-wide (HKLM) 가 실패하면 User (HKCU) 로 fallback.
;
;  추가로 wrapper hwarang-agent.cmd 를 같은 폴더에 만들어,
;  사이드카 실제 파일명이 hwarang-agent-x86_64-pc-windows-msvc.exe 라도
;  사용자는 `hwarang-agent` 만 입력하면 동작하도록 한다.
; ─────────────────────────────────────────────────────────────────────────────

!macro NSIS_HOOK_POSTINSTALL
    ; %INSTDIR% = 설치 폴더 (예: C:\Program Files\Hwarang Grid Agent)
    ; 사이드카는 %INSTDIR%\binaries\ 또는 %INSTDIR% 자체에 위치 가능
    DetailPrint "─── 화랑 Grid: hwarang-agent CLI 등록 ───"

    ; wrapper .cmd 작성 — 실제 사이드카 파일명에 의존하지 않도록
    FileOpen $0 "$INSTDIR\hwarang-agent.cmd" w
    FileWrite $0 "@echo off$\r$\n"
    FileWrite $0 "setlocal$\r$\n"
    FileWrite $0 "set HWARANG_AGENT_BIN=%~dp0binaries\hwarang-agent-x86_64-pc-windows-msvc.exe$\r$\n"
    FileWrite $0 'if not exist "%HWARANG_AGENT_BIN%" set HWARANG_AGENT_BIN=%~dp0binaries\hwarang-agent.exe$\r$\n'
    FileWrite $0 'if not exist "%HWARANG_AGENT_BIN%" set HWARANG_AGENT_BIN=%~dp0hwarang-agent.exe$\r$\n'
    FileWrite $0 'if not exist "%HWARANG_AGENT_BIN%" ($\r$\n'
    FileWrite $0 '  echo [ERROR] hwarang-agent 사이드카를 찾을 수 없습니다.$\r$\n'
    FileWrite $0 '  exit /b 1$\r$\n'
    FileWrite $0 ')$\r$\n'
    FileWrite $0 '"%HWARANG_AGENT_BIN%" %*$\r$\n'
    FileWrite $0 "endlocal$\r$\n"
    FileClose $0
    DetailPrint "  wrapper 작성: $INSTDIR\hwarang-agent.cmd"

    ; PATH 등록 (Machine-wide HKLM 우선)
    EnVar::SetHKLM
    EnVar::Check "Path" "$INSTDIR"
    Pop $0
    ${If} $0 != 0
        EnVar::AddValue "Path" "$INSTDIR"
        Pop $0
        ${If} $0 = 0
            DetailPrint "  PATH 등록 (시스템): $INSTDIR"
        ${Else}
            DetailPrint "  HKLM PATH 실패 ($0) → HKCU 로 fallback"
            EnVar::SetHKCU
            EnVar::AddValue "Path" "$INSTDIR"
            Pop $0
            DetailPrint "  PATH 등록 (사용자): $INSTDIR (결과 $0)"
        ${EndIf}
    ${Else}
        DetailPrint "  PATH 이미 포함: $INSTDIR (건너뜀)"
    ${EndIf}

    DetailPrint "  사용 예: hwarang-agent login / hwarang-agent status"
    DetailPrint "  주의: 새 명령 프롬프트를 열어야 PATH 가 적용됩니다."
!macroend

!macro NSIS_HOOK_PREUNINSTALL
    DetailPrint "─── 화랑 Grid: PATH 정리 ───"
    EnVar::SetHKLM
    EnVar::DeleteValue "Path" "$INSTDIR"
    Pop $0
    DetailPrint "  HKLM PATH 제거: $INSTDIR (결과 $0)"
    EnVar::SetHKCU
    EnVar::DeleteValue "Path" "$INSTDIR"
    Pop $0
    DetailPrint "  HKCU PATH 제거: $INSTDIR (결과 $0)"

    Delete "$INSTDIR\hwarang-agent.cmd"
!macroend
