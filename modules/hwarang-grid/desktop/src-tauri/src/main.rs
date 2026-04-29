// Hwarang Grid Agent - 데스크톱 앱 (Tauri)
//
// Windows: 시스템 트레이 아이콘
// Mac: 상단 메뉴바 아이콘
//
// 상태:
//   🟢 실행중 (Running) - GPU 작업 처리 중
//   🟡 대기중 (Idle) - 작업 대기, GPU 놀고 있음
//   🔴 중지됨 (Stopped) - 에이전트 중지
//   ⚠️ 오류 (Error) - 연결 문제 등
//
// 트레이 메뉴:
//   상태: 🟢 실행중 | 오늘 +1,234 토큰
//   ─────────────────
//   실행 / 중지
//   내 현황 보기
//   설정
//   ─────────────────
//   ✓ 시스템 시작 시 자동 실행
//   🌙 야간 모드 (밤 10시-7시만 실행)
//   🔕 알림 끄기
//   ─────────────────
//   🎯 도메인 프리셋 (법률/의료/세무/일반)
//   ─────────────────
//   hwarang.ai 열기
//   종료

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod auth;
mod device;
mod logging;
mod notifications;

use once_cell::sync::Lazy;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::api::process::{Command as SidecarCommand, CommandChild, CommandEvent};
use tauri::{
    CustomMenuItem, Manager, SystemTray, SystemTrayEvent, SystemTrayMenu,
    SystemTrayMenuItem,
};
use tauri_plugin_autostart::{ManagerExt, MacosLauncher};

use device::DeviceInfo;
use notifications::NotificationTracker;

const API_BASE_URL: &str = "https://hwarang.ai";
const DEEP_LINK_SCHEME: &str = "hwarang-grid";

/// 시작 시 1회 수집되는 기기 정보 (캐싱).
/// 같은 PC 에서는 항상 같은 fingerprint 를 내도록 결정성 유지.
static DEVICE_INFO: Lazy<DeviceInfo> = Lazy::new(device::collect_device_info);

/// PyInstaller 사이드카 자식 프로세스 핸들 (트레이/스레드 간 공유).
type SidecarHandle = Arc<Mutex<Option<CommandChild>>>;

/// `binaries/hwarang-agent-<triple>` 사이드카를 spawn. 이미 떠 있으면 noop.
fn spawn_agent_sidecar(sidecar: &SidecarHandle) -> Result<(), String> {
    {
        let guard = sidecar.lock().map_err(|e| e.to_string())?;
        if guard.is_some() {
            return Ok(());
        }
    }

    let cmd = SidecarCommand::new_sidecar("hwarang-agent")
        .map_err(|e| format!("사이드카 정의 누락 (build_binary.py 실행 필요?): {}", e))?
        .args(["daemon"]);

    let (mut rx, child) = cmd
        .spawn()
        .map_err(|e| format!("사이드카 spawn 실패: {}", e))?;

    {
        let mut guard = sidecar.lock().map_err(|e| e.to_string())?;
        *guard = Some(child);
    }

    // stdout/stderr 비동기 소비 (드롭하지 않으면 파이프가 막힐 수 있음)
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => log::info!("[agent] {}", line),
                CommandEvent::Stderr(line) => log::warn!("[agent err] {}", line),
                CommandEvent::Error(err) => log::error!("[agent error] {}", err),
                CommandEvent::Terminated(payload) => {
                    log::warn!(
                        "[agent terminated] code={:?} signal={:?}",
                        payload.code, payload.signal
                    );
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(())
}

/// 사이드카 자식 프로세스 종료. 핸들이 없으면 noop.
fn stop_agent_sidecar(sidecar: &SidecarHandle) {
    let mut guard = match sidecar.lock() {
        Ok(g) => g,
        Err(e) => {
            log::warn!("sidecar 락 획득 실패: {}", e);
            return;
        }
    };
    if let Some(child) = guard.take() {
        if let Err(e) = child.kill() {
            log::warn!("사이드카 kill 실패: {}", e);
        }
    }
}

// ---------------------------------------------------------------------------
// 에이전트 상태
// ---------------------------------------------------------------------------
#[derive(Clone, Debug, serde::Serialize)]
struct AgentState {
    status: String,        // "running", "idle", "stopped", "error"
    gpu_name: String,
    gpu_usage_percent: f32,
    gpu_temp: i32,
    tokens_today: i64,
    tokens_total: i64,
    uptime_minutes: i64,
    work_count_today: i64,
    connected: bool,
    current_round_id: Option<String>,
    current_round_name: String,
    kyc_verified: bool,
    last_error: Option<String>,
    // 로그인 상태 — 트레이 메뉴 표시용
    logged_in: bool,
    user_email: Option<String>,
    user_tier: String,
    // 다중 기기 식별 — 트레이 메뉴 표시 + heartbeat 용
    device_id: Option<String>,
    device_name: Option<String>,
}

impl Default for AgentState {
    fn default() -> Self {
        Self {
            status: "stopped".into(),
            gpu_name: "감지 중...".into(),
            gpu_usage_percent: 0.0,
            gpu_temp: 0,
            tokens_today: 0,
            tokens_total: 0,
            uptime_minutes: 0,
            work_count_today: 0,
            connected: false,
            current_round_id: None,
            current_round_name: String::new(),
            kyc_verified: false,
            last_error: None,
            logged_in: false,
            user_email: None,
            user_tier: "BRONZE".into(),
            device_id: None,
            device_name: None,
        }
    }
}

/// `~/.hwarang/account.json` 을 읽어 AgentState 의 로그인 필드를 갱신.
/// 백그라운드 스레드와 deep link 콜백 양쪽에서 호출된다.
fn refresh_account_into_state(state: &mut AgentState) {
    match auth::load_account() {
        Some(info) => {
            state.logged_in = info.api_key.is_some();
            state.user_email = info.email.clone();
            state.user_tier = info.tier.clone();
            state.kyc_verified = info.kyc_verified;
            state.device_id = info.device_id.clone();
            // 서버가 device_name 을 안 줬으면 hostname 으로 fallback
            state.device_name = info
                .device_name
                .clone()
                .or_else(|| Some(DEVICE_INFO.hostname.clone()));
        }
        None => {
            state.logged_in = false;
            state.user_email = None;
            state.device_id = None;
            state.device_name = None;
        }
    }
}

// ---------------------------------------------------------------------------
// 사용자 환경설정 (~/.hwarang/desktop_prefs.json)
// ---------------------------------------------------------------------------
fn prefs_path() -> PathBuf {
    dirs::home_dir()
        .map(|h| h.join(".hwarang").join("desktop_prefs.json"))
        .unwrap_or_else(|| PathBuf::from("desktop_prefs.json"))
}

fn default_prefs() -> serde_json::Value {
    serde_json::json!({
        "autostart": false,
        "night_mode_only": false,
        "notifications_enabled": true,
        "selected_preset": "general",
    })
}

fn load_desktop_prefs() -> serde_json::Value {
    let path = prefs_path();
    if let Ok(text) = std::fs::read_to_string(&path) {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) {
            return v;
        }
    }
    default_prefs()
}

fn save_desktop_prefs(prefs: &serde_json::Value) -> std::io::Result<()> {
    let path = prefs_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let text = serde_json::to_string_pretty(prefs).unwrap_or_else(|_| "{}".to_string());
    std::fs::write(&path, text)
}

fn toggle_pref(key: &str) -> bool {
    let mut prefs = load_desktop_prefs();
    let cur = prefs.get(key).and_then(|v| v.as_bool()).unwrap_or(false);
    let new_val = !cur;
    prefs[key] = serde_json::Value::Bool(new_val);
    let _ = save_desktop_prefs(&prefs);
    new_val
}

fn set_preset(preset: &str) {
    let mut prefs = load_desktop_prefs();
    prefs["selected_preset"] = serde_json::Value::String(preset.to_string());
    let _ = save_desktop_prefs(&prefs);

    // agent_profile.yaml 갱신
    if let Some(profile_path) = dirs::home_dir().map(|h| h.join(".hwarang").join("agent_profile.yaml")) {
        if let Some(parent) = profile_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let yaml = format!("preset: {}\n", preset);
        let _ = std::fs::write(&profile_path, yaml);
    }

    // Python 데몬에 SIGUSR1 (재로드 신호)
    #[cfg(unix)]
    {
        if let Ok(pid_str) = std::fs::read_to_string("/tmp/hwarang-agent.pid") {
            if let Ok(pid) = pid_str.trim().parse::<i32>() {
                let _ = std::process::Command::new("kill")
                    .args(["-USR1", &pid.to_string()])
                    .output();
            }
        }
    }
}

// ---------------------------------------------------------------------------
// 알림 트래커 (중복 방지) - 전역
// ---------------------------------------------------------------------------
static NOTIF_TRACKER: Lazy<Mutex<NotificationTracker>> =
    Lazy::new(|| Mutex::new(NotificationTracker::default()));

// ---------------------------------------------------------------------------
// Tauri command: 자동 시작 토글
// ---------------------------------------------------------------------------
#[tauri::command]
async fn toggle_autostart(app_handle: tauri::AppHandle, enable: bool) -> Result<(), String> {
    let autostart = app_handle.autolaunch();
    if enable {
        autostart.enable().map_err(|e| e.to_string())?;
    } else {
        autostart.disable().map_err(|e| e.to_string())?;
    }
    let mut prefs = load_desktop_prefs();
    prefs["autostart"] = serde_json::Value::Bool(enable);
    let _ = save_desktop_prefs(&prefs);
    Ok(())
}

#[tauri::command]
async fn is_autostart_enabled(app_handle: tauri::AppHandle) -> Result<bool, String> {
    app_handle.autolaunch().is_enabled().map_err(|e| e.to_string())
}

// ---------------------------------------------------------------------------
// Settings 윈도우용 commands
// ---------------------------------------------------------------------------
fn profile_path() -> PathBuf {
    dirs::home_dir()
        .map(|h| h.join(".hwarang").join("agent_profile.yaml"))
        .unwrap_or_else(|| PathBuf::from("agent_profile.yaml"))
}

#[tauri::command]
async fn get_profile() -> Result<serde_json::Value, String> {
    let path = profile_path();
    let text = match std::fs::read_to_string(&path) {
        Ok(t) => t,
        Err(_) => return Ok(serde_json::json!({"preset": "general"})),
    };
    let value: serde_yaml::Value =
        serde_yaml::from_str(&text).map_err(|e| format!("YAML 파싱 실패: {}", e))?;
    let json = serde_json::to_value(value).map_err(|e| e.to_string())?;
    Ok(json)
}

#[tauri::command]
async fn save_profile(profile: serde_json::Value) -> Result<(), String> {
    let path = profile_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let yaml = serde_yaml::to_string(&profile).map_err(|e| e.to_string())?;
    std::fs::write(&path, yaml).map_err(|e| format!("프로필 저장 실패: {}", e))?;

    // Python 데몬 SIGUSR1 (재로드)
    #[cfg(unix)]
    {
        if let Ok(pid_str) = std::fs::read_to_string("/tmp/hwarang-agent.pid") {
            if let Ok(pid) = pid_str.trim().parse::<i32>() {
                let _ = std::process::Command::new("kill")
                    .args(["-USR1", &pid.to_string()])
                    .output();
            }
        }
    }
    Ok(())
}

#[tauri::command]
async fn get_desktop_prefs() -> Result<serde_json::Value, String> {
    let mut prefs = load_desktop_prefs();
    prefs["app_version"] = serde_json::Value::String(env!("CARGO_PKG_VERSION").to_string());
    Ok(prefs)
}

#[tauri::command]
async fn save_desktop_prefs_cmd(prefs: serde_json::Value) -> Result<(), String> {
    save_desktop_prefs(&prefs).map_err(|e| format!("환경설정 저장 실패: {}", e))
}

#[tauri::command]
async fn get_account_status() -> Result<serde_json::Value, String> {
    let info = auth::load_account().unwrap_or_default();
    serde_json::to_value(info).map_err(|e| e.to_string())
}

#[tauri::command]
async fn clear_account_status() -> Result<(), String> {
    auth::clear_account()
}

#[tauri::command]
async fn open_login_flow() -> Result<String, String> {
    auth::open_login_flow(API_BASE_URL, Some(&*DEVICE_INFO))
}

#[tauri::command]
async fn open_kyc_flow() -> Result<(), String> {
    auth::open_kyc_flow(API_BASE_URL)
}

#[tauri::command]
async fn open_logs_folder() -> Result<(), String> {
    let path = logging::log_path();
    let folder = path.parent().unwrap_or(&path).to_path_buf();
    open::that(&folder).map_err(|e| format!("로그 폴더 열기 실패: {}", e))
}

#[tauri::command]
async fn open_profile_file() -> Result<(), String> {
    let path = profile_path();
    if !path.exists() {
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let _ = std::fs::write(&path, "preset: general\n");
    }
    open::that(&path).map_err(|e| format!("프로필 파일 열기 실패: {}", e))
}

#[tauri::command]
async fn check_update_manual(app_handle: tauri::AppHandle) -> Result<serde_json::Value, String> {
    match app_handle.updater().check().await {
        Ok(update) => {
            if update.is_update_available() {
                let notes = update
                    .body()
                    .map(|b| b.to_string())
                    .unwrap_or_default();
                Ok(serde_json::json!({
                    "available": true,
                    "version": update.latest_version(),
                    "current": env!("CARGO_PKG_VERSION"),
                    "notes": notes,
                }))
            } else {
                Ok(serde_json::json!({
                    "available": false,
                    "current": env!("CARGO_PKG_VERSION"),
                }))
            }
        }
        Err(e) => Err(format!("업데이트 확인 실패: {}", e)),
    }
}

#[tauri::command]
async fn reset_all() -> Result<(), String> {
    let home = dirs::home_dir().ok_or_else(|| "home 없음".to_string())?;
    let dir = home.join(".hwarang");
    let _ = std::fs::remove_file(dir.join("desktop_prefs.json"));
    let _ = std::fs::remove_file(dir.join("agent_profile.yaml"));
    let _ = std::fs::remove_file(dir.join("account.json"));
    let _ = std::fs::remove_file(dir.join(".pending_nonce"));
    log::info!("전체 초기화 완료 (logs 는 보존)");
    Ok(())
}

#[tauri::command]
async fn save_settings(settings: serde_json::Value) -> Result<(), String> {
    if let Some(profile) = settings.get("profile") {
        save_profile(profile.clone()).await?;
    }
    if let Some(prefs) = settings.get("prefs") {
        save_desktop_prefs(prefs).map_err(|e| format!("환경설정 저장 실패: {}", e))?;
    }
    log::info!("설정 저장 완료");
    Ok(())
}

#[tauri::command]
async fn show_settings_window(app_handle: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_window("settings") {
        window.show().map_err(|e| e.to_string())?;
        window.set_focus().map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err("settings 윈도우 미정의".into())
    }
}

// ---------------------------------------------------------------------------
// 자동 업데이트 백그라운드 루프
// ---------------------------------------------------------------------------
async fn run_updater_loop(handle: tauri::AppHandle) {
    // 시작 후 5분 뒤 첫 체크 (네트워크 안정화 대기)
    tokio::time::sleep(Duration::from_secs(300)).await;
    loop {
        match handle.updater().check().await {
            Ok(update) if update.is_update_available() => {
                log::info!(
                    "업데이트 사용 가능: {} → {}",
                    env!("CARGO_PKG_VERSION"),
                    update.latest_version()
                );
                // dialog: true 이므로 자동 prompt
                if let Err(e) = update.download_and_install().await {
                    log::error!("업데이트 설치 실패: {}", e);
                }
            }
            Ok(_) => log::debug!("최신 버전입니다"),
            Err(e) => log::warn!("업데이트 체크 실패: {}", e),
        }
        // 6시간마다 재확인
        tokio::time::sleep(Duration::from_secs(6 * 3600)).await;
    }
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------
fn main() {
    // Deep link single-instance 등록은 Tauri::Builder 호출 전에 해야 한다.
    // (FabianLars/tauri-plugin-deep-link 1.x 요구사항)
    // 인자: 다른 인스턴스끼리 IPC 시 식별자 (보통 bundle identifier)
    tauri_plugin_deep_link::prepare("ai.hwarang.grid");

    // 로그 초기화 (가능한 한 빨리)
    if let Err(e) = logging::init_logging() {
        eprintln!("로그 초기화 실패: {}", e);
    }

    let mut initial_state = AgentState::default();
    refresh_account_into_state(&mut initial_state);
    let state = Arc::new(Mutex::new(initial_state));
    let state_clone = state.clone();
    let state_for_deep_link = state.clone();

    // PyInstaller 사이드카 자식 프로세스 핸들 (Mutex 로 트레이/quit 양쪽에서 공유)
    let sidecar: SidecarHandle = Arc::new(Mutex::new(None));
    let sidecar_for_event = sidecar.clone();

    // 시스템 트레이 메뉴 구성 (초기)
    let prefs = load_desktop_prefs();
    let tray_menu = build_tray_menu(&state.lock().unwrap(), &prefs);

    let system_tray = SystemTray::new().with_menu(tray_menu);

    tauri::Builder::default()
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec!["--minimized"]), // 자동 시작 시 트레이만 표시
        ))
        .invoke_handler(tauri::generate_handler![
            toggle_autostart,
            is_autostart_enabled,
            get_profile,
            save_profile,
            get_desktop_prefs,
            save_desktop_prefs_cmd,
            get_account_status,
            clear_account_status,
            open_login_flow,
            open_kyc_flow,
            open_logs_folder,
            open_profile_file,
            check_update_manual,
            reset_all,
            save_settings,
            show_settings_window,
        ])
        .system_tray(system_tray)
        .on_system_tray_event(move |app, event| {
            match event {
                SystemTrayEvent::MenuItemClick { id, .. } => {
                    let mut state = state_clone.lock().unwrap();

                    match id.as_str() {
                        // 실행/중지 토글
                        "toggle" => {
                            if state.status == "stopped" {
                                // PyInstaller 사이드카 시작 (Python 미설치 PC 에서도 동작)
                                match spawn_agent_sidecar(&sidecar_for_event) {
                                    Ok(()) => {
                                        state.status = "idle".into();
                                        state.connected = true;
                                        state.last_error = None;
                                        log::info!("Grid Agent 사이드카 시작");
                                    }
                                    Err(err) => {
                                        log::error!("사이드카 시작 실패: {}", err);
                                        state.status = "error".into();
                                        state.last_error = Some(err);
                                    }
                                }
                            } else {
                                // 사이드카 종료 (kill 핸들로 graceful → CommandChild::kill)
                                stop_agent_sidecar(&sidecar_for_event);
                                state.status = "stopped".into();
                                state.connected = false;
                                state.current_round_id = None;
                                state.current_round_name = String::new();
                                log::info!("Grid Agent 중지");
                            }
                        }

                        // 내 현황 보기 (웹 대시보드)
                        "dashboard" => {
                            let _ = open::that("https://hwarang.ai/dashboard");
                        }

                        // 커뮤니티 (Grid 현황)
                        "community" => {
                            let _ = open::that("https://hwarang.ai/community");
                        }

                        // 설정 — 네이티브 윈도우 표시
                        "settings" => {
                            if let Some(window) = app.get_window("settings") {
                                let _ = window.show();
                                let _ = window.set_focus();
                                let _ = window.unminimize();
                            } else {
                                log::warn!("settings 윈도우가 정의되지 않음, 웹 폴백");
                                let _ = open::that("https://hwarang.ai/settings");
                            }
                        }

                        // 자동 시작 토글
                        "autostart_toggle" => {
                            let autostart = app.autolaunch();
                            let cur_enabled = autostart.is_enabled().unwrap_or(false);
                            let new_val = !cur_enabled;
                            let res = if new_val {
                                autostart.enable()
                            } else {
                                autostart.disable()
                            };
                            if let Err(e) = res {
                                eprintln!("autostart 토글 실패: {}", e);
                            } else {
                                let mut prefs = load_desktop_prefs();
                                prefs["autostart"] = serde_json::Value::Bool(new_val);
                                let _ = save_desktop_prefs(&prefs);
                            }
                        }

                        // 야간 모드 토글
                        "night_mode_toggle" => {
                            toggle_pref("night_mode_only");
                        }

                        // 알림 토글
                        "mute_notifications" => {
                            let mut prefs = load_desktop_prefs();
                            let cur = prefs.get("notifications_enabled")
                                .and_then(|v| v.as_bool()).unwrap_or(true);
                            prefs["notifications_enabled"] = serde_json::Value::Bool(!cur);
                            let _ = save_desktop_prefs(&prefs);
                        }

                        // 도메인 프리셋
                        "preset_law" => set_preset("law_specialist"),
                        "preset_medical" => set_preset("medical_specialist"),
                        "preset_tax" => set_preset("tax_specialist"),
                        "preset_general" => set_preset("general"),

                        // 로그인 — 외부 브라우저로 nonce 기반 플로우 시작 (device 정보 포함)
                        "login" => {
                            match auth::open_login_flow(API_BASE_URL, Some(&*DEVICE_INFO)) {
                                Ok(nonce) => {
                                    log::info!("로그인 플로우 시작 (nonce={})", &nonce[..8]);
                                }
                                Err(e) => {
                                    log::error!("로그인 시작 실패: {}", e);
                                    state.last_error = Some(format!("로그인 실패: {}", e));
                                }
                            }
                        }

                        // 기기 관리 — 외부 브라우저로 기기 목록 페이지 열기
                        "manage_devices" => {
                            let _ = open::that("https://hwarang.ai/account/devices");
                        }

                        // 로그아웃 — 로컬 account.json 삭제
                        "logout" => {
                            if let Err(e) = auth::clear_account() {
                                log::error!("로그아웃 실패: {}", e);
                            } else {
                                log::info!("로그아웃 완료");
                            }
                            refresh_account_into_state(&mut state);
                        }

                        // KYC 인증 — 이미 로그인된 상태에서 KYC 페이지 열기
                        "kyc_open" => {
                            if let Err(e) = auth::open_kyc_flow(API_BASE_URL) {
                                log::error!("KYC 시작 실패: {}", e);
                            }
                        }

                        // hwarang.ai 열기
                        "website" => {
                            let _ = open::that("https://hwarang.ai");
                        }

                        // 종료
                        "quit" => {
                            stop_agent_sidecar(&sidecar_for_event);
                            state.status = "stopped".into();
                            std::process::exit(0);
                        }

                        _ => {}
                    }

                    // 메뉴/아이콘 갱신
                    let prefs = load_desktop_prefs();
                    let new_menu = build_tray_menu(&state, &prefs);
                    let _ = app.tray_handle().set_menu(new_menu);
                    update_tray_icon(app, &state);
                }

                // 트레이 아이콘 좌클릭.
                // - 미로그인: 즉시 로그인 플로우 트리거 (가장 흔한 첫 액션)
                // - 로그인됨: 플랫폼 기본 동작 (Mac/Windows 모두 메뉴 자동 표시)
                SystemTrayEvent::LeftClick { .. } => {
                    let logged_in = {
                        let s = state_clone.lock().unwrap();
                        s.logged_in
                    };
                    if !logged_in {
                        if let Err(e) = auth::open_login_flow(API_BASE_URL, Some(&*DEVICE_INFO)) {
                            log::error!("좌클릭 로그인 트리거 실패: {}", e);
                        } else {
                            log::info!("좌클릭으로 로그인 플로우 시작");
                        }
                    }
                    // 로그인 상태에서는 OS 가 자동으로 메뉴 표시
                }

                // 우클릭은 OS 가 자동으로 메뉴 표시 — 별도 처리 불필요
                SystemTrayEvent::RightClick { .. } => {}

                _ => {}
            }
        })
        .on_window_event(|event| {
            // settings 윈도우의 닫기 버튼은 destroy 대신 hide 로 처리한다.
            // (트레이 메뉴에서 다시 열 때 같은 윈도우 인스턴스 재사용)
            if let tauri::WindowEvent::CloseRequested { api, .. } = event.event() {
                let win = event.window();
                if win.label() == "settings" {
                    let _ = win.hide();
                    api.prevent_close();
                }
            }
        })
        .setup(move |app| {
            // ───── Deep link 등록 ─────
            // hwarang-grid://auth?... 콜백을 받아 로그인/KYC 결과를 처리한다.
            let dl_handle = app.handle();
            let dl_state = state_for_deep_link.clone();
            if let Err(e) = tauri_plugin_deep_link::register(
                DEEP_LINK_SCHEME,
                move |request| {
                    log::info!("deep link 수신: {}", request);
                    let h = dl_handle.clone();
                    let s = dl_state.clone();
                    tauri::async_runtime::spawn(async move {
                        match auth::handle_deep_link(&request, API_BASE_URL).await {
                            Ok(info) => {
                                log::info!(
                                    "로그인 처리 완료: email={:?}, kyc={}",
                                    info.email, info.kyc_verified
                                );
                                // 트레이 메뉴 즉시 갱신 (로그인 완료 → 메뉴에 이메일 표시)
                                {
                                    let mut state = s.lock().unwrap();
                                    refresh_account_into_state(&mut state);
                                    let prefs = load_desktop_prefs();
                                    let new_menu = build_tray_menu(&state, &prefs);
                                    let _ = h.tray_handle().set_menu(new_menu);
                                    update_tray_icon(&h, &state);
                                }
                                notifications::notify_login_completed(
                                    &h,
                                    info.email.as_deref().unwrap_or(""),
                                    info.kyc_verified,
                                );
                            }
                            Err(err) => {
                                log::error!("deep link 처리 실패: {}", err);
                                notifications::notify_login_failed(&h, &err);
                            }
                        }
                    });
                },
            ) {
                log::warn!("deep link 등록 실패: {}", e);
            }

            // ───── 자동 업데이트 백그라운드 루프 ─────
            let upd_handle = app.handle();
            tauri::async_runtime::spawn(async move {
                run_updater_loop(upd_handle).await;
            });

            // 백그라운드 상태 업데이트 스레드
            let app_handle = app.handle();
            let bg_state = state.clone();

            // 첫 실행 시 KYC 알림 (필요 시)
            {
                let s = bg_state.lock().unwrap();
                let prefs = load_desktop_prefs();
                let notifs_on = prefs.get("notifications_enabled")
                    .and_then(|v| v.as_bool()).unwrap_or(true);
                if notifs_on && !s.kyc_verified {
                    let mut tracker = NOTIF_TRACKER.lock().unwrap();
                    if !tracker.notified_kyc_required {
                        notifications::notify_kyc_required(&app_handle);
                        tracker.notified_kyc_required = true;
                    }
                }
            }

            thread::spawn(move || {
                let mut prev_tokens: i64 = 0;
                let mut prev_round_id: Option<String> = None;
                // 10초마다 도는 루프에서 heartbeat 는 6틱(=60초)마다 1회.
                let mut heartbeat_tick: u32 = 0;

                loop {
                    thread::sleep(Duration::from_secs(10));
                    heartbeat_tick = heartbeat_tick.wrapping_add(1);

                    let mut state = bg_state.lock().unwrap();

                    // 야간 모드 검사: 밤 10시-7시만 실행
                    let prefs = load_desktop_prefs();
                    let night_only = prefs.get("night_mode_only")
                        .and_then(|v| v.as_bool()).unwrap_or(false);
                    if night_only && state.status != "stopped" {
                        let hour = current_hour();
                        let in_night = hour >= 22 || hour < 7;
                        if !in_night {
                            // 야간 모드인데 낮 시간 → 작업 중지 상태로 전환
                            state.status = "idle".into();
                        }
                    }

                    if state.status != "stopped" {
                        // GPU 상태 읽기 (NVIDIA → Apple Silicon → AMD 순)
                        let mut gpu_detected = false;

                        // 1. NVIDIA (nvidia-smi)
                        if let Ok(output) = std::process::Command::new("nvidia-smi")
                            .args([
                                "--query-gpu=name,utilization.gpu,temperature.gpu",
                                "--format=csv,noheader,nounits",
                            ])
                            .output()
                        {
                            if output.status.success() {
                                if let Ok(text) = String::from_utf8(output.stdout) {
                                    let parts: Vec<&str> = text.trim().split(", ").collect();
                                    if parts.len() >= 3 {
                                        state.gpu_name = parts[0].to_string();
                                        state.gpu_usage_percent =
                                            parts[1].parse().unwrap_or(0.0);
                                        state.gpu_temp = parts[2].parse().unwrap_or(0);
                                        gpu_detected = true;
                                    }
                                }
                            }
                        }

                        // 2. Apple Silicon (macOS)
                        #[cfg(target_os = "macos")]
                        if !gpu_detected {
                            if let Ok(output) = std::process::Command::new("sysctl")
                                .args(["-n", "machdep.cpu.brand_string"])
                                .output()
                            {
                                if let Ok(text) = String::from_utf8(output.stdout) {
                                    if text.contains("Apple") {
                                        state.gpu_name = text.trim().to_string();
                                        // Apple Silicon은 사용률을 직접 측정하기 어려움
                                        state.gpu_usage_percent = 0.0;
                                        state.gpu_temp = 0;
                                        gpu_detected = true;
                                    }
                                }
                            }
                        }

                        // 3. AMD (rocm-smi)
                        if !gpu_detected {
                            if let Ok(output) = std::process::Command::new("rocm-smi")
                                .args(["--showproductname"])
                                .output()
                            {
                                if output.status.success() {
                                    if let Ok(text) = String::from_utf8(output.stdout) {
                                        if text.contains("GPU") || text.contains("Radeon") {
                                            state.gpu_name = "AMD GPU".to_string();
                                            gpu_detected = true;
                                        }
                                    }
                                }
                            }
                        }

                        if !gpu_detected {
                            state.gpu_name = "CPU only".to_string();
                        }

                        // 상태 갱신
                        if gpu_detected && state.gpu_usage_percent > 10.0 {
                            state.status = "running".into();
                        } else if gpu_detected {
                            state.status = "idle".into();
                        }

                        // 에이전트 상태 파일에서 토큰/라운드/KYC 읽기
                        let status_file = dirs::home_dir()
                            .map(|h| h.join(".hwarang").join("agent_status.json"))
                            .unwrap_or_default();

                        if let Ok(content) = std::fs::read_to_string(&status_file) {
                            if let Ok(json) =
                                serde_json::from_str::<serde_json::Value>(&content)
                            {
                                state.tokens_today =
                                    json["tokens_today"].as_i64().unwrap_or(0);
                                state.tokens_total =
                                    json["tokens_total"].as_i64().unwrap_or(0);
                                state.work_count_today =
                                    json["work_count_today"].as_i64().unwrap_or(0);
                                state.connected =
                                    json["connected"].as_bool().unwrap_or(false);
                                state.current_round_id = json["current_round_id"]
                                    .as_str()
                                    .map(|s| s.to_string());
                                state.current_round_name = json["current_round_name"]
                                    .as_str()
                                    .unwrap_or("")
                                    .to_string();
                                state.kyc_verified =
                                    json["kyc_verified"].as_bool().unwrap_or(false);
                                state.last_error = json["last_error"]
                                    .as_str()
                                    .filter(|s| !s.is_empty())
                                    .map(|s| s.to_string());
                            }
                        }

                        state.uptime_minutes += 1;

                        // ----------- 알림 트리거 -----------
                        let prefs = load_desktop_prefs();
                        let notifs_on = prefs.get("notifications_enabled")
                            .and_then(|v| v.as_bool()).unwrap_or(true);

                        if notifs_on {
                            let mut tracker = NOTIF_TRACKER.lock().unwrap();

                            // 1. 토큰 증가 → 보상 알림
                            if state.tokens_today > prev_tokens && prev_tokens > 0 {
                                let delta = state.tokens_today - prev_tokens;
                                if tracker.allow_reward() {
                                    notifications::notify_reward_received(
                                        &app_handle,
                                        delta,
                                        if state.current_round_name.is_empty() {
                                            "라운드"
                                        } else {
                                            &state.current_round_name
                                        },
                                    );
                                    tracker.mark_reward();
                                }
                            }

                            // 2. 라운드 종료 (current_round_id null로 바뀜 + 토큰 증가)
                            if prev_round_id.is_some()
                                && state.current_round_id.is_none()
                                && state.tokens_today > prev_tokens
                            {
                                let name = prev_round_id
                                    .clone()
                                    .unwrap_or_else(|| "라운드".to_string());
                                notifications::notify_round_completed(&app_handle, &name);
                            }

                            // 3. KYC 미인증
                            if !state.kyc_verified && !tracker.notified_kyc_required {
                                notifications::notify_kyc_required(&app_handle);
                                tracker.notified_kyc_required = true;
                            }

                            // 4. GPU 과열
                            if state.gpu_temp >= 85 && tracker.allow_overheat() {
                                notifications::notify_overheating(
                                    &app_handle,
                                    state.gpu_temp,
                                );
                                tracker.mark_overheat();
                            }

                            // 5. 라운드 실패
                            if let Some(err) = state.last_error.clone() {
                                if tracker.allow_error(&err) {
                                    notifications::notify_round_failed(&app_handle, &err);
                                    tracker.mark_error(&err);
                                }
                            }
                        }

                        prev_tokens = state.tokens_today;
                        prev_round_id = state.current_round_id.clone();

                        // 트레이 메뉴 갱신
                        let new_menu = build_tray_menu(&state, &prefs);
                        let _ = app_handle.tray_handle().set_menu(new_menu);
                        update_tray_icon(&app_handle, &state);

                        // ───── heartbeat: 60초마다 1회 ─────
                        // 로그인된 + status != stopped 일 때만.
                        // 실패해도 panic 없이 다음 회차에 재시도.
                        if heartbeat_tick % 6 == 0 && state.logged_in {
                            if let Some(account) = auth::load_account() {
                                if let Some(api_key) = account.api_key.clone() {
                                    let usage = state.gpu_usage_percent;
                                    let temp = state.gpu_temp;
                                    let status = state.status.clone();
                                    tauri::async_runtime::spawn(async move {
                                        if let Err(e) = auth::send_heartbeat(
                                            &api_key,
                                            API_BASE_URL,
                                            usage,
                                            temp,
                                            &status,
                                        )
                                        .await
                                        {
                                            log::debug!("heartbeat 실패 (다음 회 재시도): {}", e);
                                        }
                                    });
                                }
                            }
                        }
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

// ---------------------------------------------------------------------------
// 트레이 메뉴 구성
// ---------------------------------------------------------------------------
fn build_tray_menu(state: &AgentState, prefs: &serde_json::Value) -> SystemTrayMenu {
    let status_icon = match state.status.as_str() {
        "running" => "🟢",
        "idle" => "🟡",
        "stopped" => "🔴",
        "error" => "⚠️",
        _ => "⚪",
    };

    let status_text = match state.status.as_str() {
        "running" => "실행중 - GPU 작업 처리 중",
        "idle" => "대기중 - 작업 대기",
        "stopped" => "중지됨",
        "error" => "오류 발생",
        _ => "알 수 없음",
    };

    let toggle_text = if state.status == "stopped" {
        "▶️ 실행"
    } else {
        "⏹️ 중지"
    };

    let autostart_on = prefs.get("autostart")
        .and_then(|v| v.as_bool()).unwrap_or(false);
    let night_mode_on = prefs.get("night_mode_only")
        .and_then(|v| v.as_bool()).unwrap_or(false);
    let notifs_on = prefs.get("notifications_enabled")
        .and_then(|v| v.as_bool()).unwrap_or(true);
    let selected_preset = prefs.get("selected_preset")
        .and_then(|v| v.as_str()).unwrap_or("general");

    let mut menu = SystemTrayMenu::new();

    // ───── 계정 섹션 (최상단) ─────
    if state.logged_in {
        // 로그인된 상태: 이메일 + 등급 표시 (disabled)
        let account_label = match state.user_email.as_deref() {
            Some(email) => format!("👤 {} ({})", email, state.user_tier),
            None => format!("👤 로그인됨 ({})", state.user_tier),
        };
        menu = menu.add_item(CustomMenuItem::new("account_info", account_label).disabled());

        // 현재 기기 이름 (서버 등록 이름 → hostname 순으로 fallback)
        if let Some(name) = state.device_name.as_deref() {
            menu = menu.add_item(
                CustomMenuItem::new("device_info", format!("  💻 {}", name)).disabled(),
            );
        }

        // KYC 상태
        if state.kyc_verified {
            menu = menu
                .add_item(CustomMenuItem::new("kyc_status", "  ✅ KYC 인증 완료").disabled());
        } else {
            menu = menu.add_item(CustomMenuItem::new("kyc_open", "  🛡️ KYC 인증하기"));
        }

        // 기기 관리 — 다중 기기 로그인 사용자를 위해
        menu = menu.add_item(CustomMenuItem::new("manage_devices", "🖥️ 내 기기 관리"));

        menu = menu.add_item(CustomMenuItem::new("logout", "🚪 로그아웃"));
    } else {
        // 미로그인: 클릭 가능한 로그인 버튼 (강조)
        menu = menu.add_item(CustomMenuItem::new("login", "👤 로그인 / 회원가입"));
        menu = menu.add_item(
            CustomMenuItem::new("login_help", "  로그인 후 토큰 보상 적립")
                .disabled(),
        );
    }

    menu = menu.add_native_item(SystemTrayMenuItem::Separator);

    // 상태 표시 (클릭 불가)
    menu = menu.add_item(
        CustomMenuItem::new(
            "status",
            format!(
                "{} {} | 오늘 +{} 토큰",
                status_icon,
                status_text,
                format_tokens(state.tokens_today)
            ),
        )
        .disabled(),
    );

    // GPU 정보
    if state.status != "stopped" {
        menu = menu.add_item(
            CustomMenuItem::new(
                "gpu_info",
                format!(
                    "   {} | {}% | {}°C",
                    state.gpu_name, state.gpu_usage_percent as i32, state.gpu_temp
                ),
            )
            .disabled(),
        );
        menu = menu.add_item(
            CustomMenuItem::new(
                "work_info",
                format!(
                    "   오늘 {}건 처리 | 총 {} 토큰",
                    state.work_count_today,
                    format_tokens(state.tokens_total)
                ),
            )
            .disabled(),
        );
    }

    menu = menu.add_native_item(SystemTrayMenuItem::Separator);

    // 실행/중지
    menu = menu.add_item(CustomMenuItem::new("toggle", toggle_text));

    // 내 현황
    menu = menu.add_item(CustomMenuItem::new("dashboard", "📊 내 현황 보기"));

    // 커뮤니티
    menu = menu.add_item(CustomMenuItem::new("community", "🌐 커뮤니티 (Grid 현황)"));

    // 설정
    menu = menu.add_item(CustomMenuItem::new("settings", "⚙️ 설정"));

    menu = menu.add_native_item(SystemTrayMenuItem::Separator);

    // 자동 실행 / 야간 모드 / 알림
    menu = menu.add_item(CustomMenuItem::new(
        "autostart_toggle",
        if autostart_on {
            "✓ 시스템 시작 시 자동 실행"
        } else {
            "  시스템 시작 시 자동 실행"
        },
    ));
    menu = menu.add_item(CustomMenuItem::new(
        "night_mode_toggle",
        if night_mode_on {
            "✓ 🌙 야간 모드 (밤 10시-7시만)"
        } else {
            "  🌙 야간 모드 (밤 10시-7시만)"
        },
    ));
    menu = menu.add_item(CustomMenuItem::new(
        "mute_notifications",
        if notifs_on {
            "  🔔 알림 켜짐 (클릭 시 끄기)"
        } else {
            "✓ 🔕 알림 꺼짐"
        },
    ));

    menu = menu.add_native_item(SystemTrayMenuItem::Separator);

    // 도메인 프리셋
    menu = menu.add_item(
        CustomMenuItem::new("preset_label", "🎯 도메인 프리셋:").disabled(),
    );
    menu = menu.add_item(CustomMenuItem::new(
        "preset_law",
        if selected_preset == "law_specialist" {
            "  ✓ ⚖️  법률 전문"
        } else {
            "    ⚖️  법률 전문"
        },
    ));
    menu = menu.add_item(CustomMenuItem::new(
        "preset_medical",
        if selected_preset == "medical_specialist" {
            "  ✓ 🏥  의료 전문"
        } else {
            "    🏥  의료 전문"
        },
    ));
    menu = menu.add_item(CustomMenuItem::new(
        "preset_tax",
        if selected_preset == "tax_specialist" {
            "  ✓ 💼  세무 전문"
        } else {
            "    💼  세무 전문"
        },
    ));
    menu = menu.add_item(CustomMenuItem::new(
        "preset_general",
        if selected_preset == "general" {
            "  ✓ 🌐  일반"
        } else {
            "    🌐  일반"
        },
    ));

    menu = menu.add_native_item(SystemTrayMenuItem::Separator);

    // 링크
    menu = menu.add_item(CustomMenuItem::new("website", "🔗 hwarang.ai"));

    menu = menu.add_native_item(SystemTrayMenuItem::Separator);

    // 종료
    menu = menu.add_item(CustomMenuItem::new("quit", "종료"));

    menu
}

// ---------------------------------------------------------------------------
// 상태에 따라 트레이 아이콘 변경 (include_bytes! 임베드)
// ---------------------------------------------------------------------------
fn update_tray_icon<R: tauri::Runtime>(app: &tauri::AppHandle<R>, state: &AgentState) {
    let icon_bytes: &[u8] = match state.status.as_str() {
        "running" => include_bytes!("../icons/icon-green.png"),
        "idle"    => include_bytes!("../icons/icon-yellow.png"),
        "stopped" => include_bytes!("../icons/icon-gray.png"),
        "error"   => include_bytes!("../icons/icon-red.png"),
        _         => include_bytes!("../icons/icon-gray.png"),
    };

    let _ = app
        .tray_handle()
        .set_icon(tauri::Icon::Raw(icon_bytes.to_vec()));

    // Mac: 메뉴바에 텍스트 표시 (토큰)
    #[cfg(target_os = "macos")]
    {
        let title = if state.status == "stopped" {
            "H".to_string()
        } else {
            format!("H +{}", format_tokens(state.tokens_today))
        };
        let _ = app.tray_handle().set_title(&title);
    }
}

fn format_tokens(n: i64) -> String {
    if n >= 1_000_000 {
        format!("{:.1}M", n as f64 / 1_000_000.0)
    } else if n >= 1_000 {
        format!("{:.0}K", n as f64 / 1_000.0)
    } else {
        n.to_string()
    }
}

/// 현재 시간 (0-23) — 야간 모드 검사용
fn current_hour() -> u32 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    // 로컬 타임존 오프셋: date 명령으로 추출
    let offset_secs: i64 = if let Ok(out) = std::process::Command::new("date").arg("+%z").output() {
        if let Ok(s) = String::from_utf8(out.stdout) {
            let s = s.trim();
            // ±HHMM
            if s.len() >= 5 {
                let sign = if s.starts_with('-') { -1i64 } else { 1i64 };
                let hh: i64 = s[1..3].parse().unwrap_or(0);
                let mm: i64 = s[3..5].parse().unwrap_or(0);
                sign * (hh * 3600 + mm * 60)
            } else {
                0
            }
        } else {
            0
        }
    } else {
        0
    };
    let local_secs = secs + offset_secs;
    (((local_secs % 86400 + 86400) % 86400) / 3600) as u32
}
