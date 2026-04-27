; ─────────────────────────────────────────────────────────────────────────────
;  화랑 Grid Agent — NSIS 인스톨러 (간이 버전, WiX 대안)
;
;  컴파일:
;    makensis installer.nsi
;
;  결과:
;    Hwarang-Grid-Agent-Setup.exe
; ─────────────────────────────────────────────────────────────────────────────

!define APPNAME "Hwarang Grid Agent"
!define COMPANYNAME "Hwarang AI"
!define DESCRIPTION "GPU 공유 네트워크 참여"
!define VERSIONMAJOR 0
!define VERSIONMINOR 1
!define VERSIONBUILD 0
!define HELPURL "https://hwarang.ai/support"
!define UPDATEURL "https://hwarang.ai/download"
!define ABOUTURL "https://hwarang.ai"
!define INSTALLSIZE 65536  ; KB

RequestExecutionLevel user   ; perUser 설치 (관리자 불필요)
InstallDir "$LOCALAPPDATA\HwarangGrid"
Name "${APPNAME}"
Icon "..\..\src-tauri\icons\icon.ico"
OutFile "Hwarang-Grid-Agent-Setup.exe"

!include LogicLib.nsh
!include "MUI2.nsh"

; ─── UI ─────────────────────────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON       "..\..\src-tauri\icons\icon.ico"
!define MUI_UNICON     "..\..\src-tauri\icons\icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\hwarang-grid.exe"
!define MUI_FINISHPAGE_RUN_TEXT "지금 화랑 Grid Agent 실행"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Korean"

; ─── 설치 ───────────────────────────────────────────────────────────────────
Section "Install"
    SetOutPath $INSTDIR

    ; 메인 실행 파일 (cargo tauri build 결과 가정)
    File "..\..\src-tauri\target\release\hwarang-grid.exe"

    ; 추가 리소스
    File /nonfatal "..\..\src-tauri\icons\icon.ico"
    File /nonfatal "..\uninstall\uninstall_windows.ps1"

    ; 사용자 데이터 디렉토리
    CreateDirectory "$PROFILE\.hwarang"
    CreateDirectory "$PROFILE\.hwarang\logs"

    ; 시작 메뉴
    CreateDirectory "$SMPROGRAMS\${APPNAME}"
    CreateShortcut  "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\hwarang-grid.exe" "" "$INSTDIR\icon.ico"
    CreateShortcut  "$SMPROGRAMS\${APPNAME}\제거.lnk" "$INSTDIR\uninstall.exe"

    ; 데스크탑
    CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\hwarang-grid.exe" "" "$INSTDIR\icon.ico"

    ; 자동 시작 (HKCU\...\Run)
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "HwarangGrid" '"$INSTDIR\hwarang-grid.exe" --background'

    ; 언인스톨러 작성
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; 제어판 → 프로그램 추가/제거 등록
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName"      "${APPNAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon"     "$INSTDIR\icon.ico"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher"       "${COMPANYNAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "HelpLink"        "${HELPURL}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLUpdateInfo"   "${UPDATEURL}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLInfoAbout"    "${ABOUTURL}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion"  "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMajor"  ${VERSIONMAJOR}
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMinor"  ${VERSIONMINOR}
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoModify"      1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoRepair"      1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}
SectionEnd

; ─── 제거 ───────────────────────────────────────────────────────────────────
Section "Uninstall"
    ; 데몬 종료 시도
    ExecWait 'taskkill /F /IM hwarang-grid.exe' $0

    ; 자동 시작 키 삭제
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "HwarangGrid"

    ; 시작 메뉴
    Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
    Delete "$SMPROGRAMS\${APPNAME}\제거.lnk"
    RMDir  "$SMPROGRAMS\${APPNAME}"

    ; 데스크탑
    Delete "$DESKTOP\${APPNAME}.lnk"

    ; 설치 폴더
    Delete "$INSTDIR\hwarang-grid.exe"
    Delete "$INSTDIR\icon.ico"
    Delete "$INSTDIR\uninstall_windows.ps1"
    Delete "$INSTDIR\uninstall.exe"
    RMDir  "$INSTDIR"

    ; 사용자 데이터는 묻고 삭제 (NSIS는 GUI MessageBox)
    MessageBox MB_YESNO "사용자 데이터 ($PROFILE\.hwarang) 도 삭제하시겠습니까?" IDNO skip_userdata
        RMDir /r "$PROFILE\.hwarang"
    skip_userdata:

    ; 레지스트리 정리
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
    DeleteRegKey HKCU "Software\HwarangAI\Grid"
SectionEnd
