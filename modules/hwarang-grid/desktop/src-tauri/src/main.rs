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
//   hwarang.ai 열기
//   종료

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{
    CustomMenuItem, Manager, SystemTray, SystemTrayEvent, SystemTrayMenu,
    SystemTrayMenuItem, SystemTraySubmenu,
};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

// 에이전트 상태
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
        }
    }
}

fn main() {
    let state = Arc::new(Mutex::new(AgentState::default()));
    let state_clone = state.clone();

    // 시스템 트레이 메뉴 구성
    let tray_menu = build_tray_menu(&state.lock().unwrap());

    let system_tray = SystemTray::new().with_menu(tray_menu);

    tauri::Builder::default()
        .system_tray(system_tray)
        .on_system_tray_event(move |app, event| {
            match event {
                SystemTrayEvent::MenuItemClick { id, .. } => {
                    let mut state = state_clone.lock().unwrap();

                    match id.as_str() {
                        // 실행/중지 토글
                        "toggle" => {
                            if state.status == "stopped" {
                                state.status = "idle".into();
                                state.connected = true;
                                // TODO: 실제 에이전트 시작
                                println!("Grid Agent 시작");
                            } else {
                                state.status = "stopped".into();
                                state.connected = false;
                                // TODO: 실제 에이전트 중지
                                println!("Grid Agent 중지");
                            }
                            // 트레이 메뉴 갱신
                            let new_menu = build_tray_menu(&state);
                            app.tray_handle().set_menu(new_menu).unwrap();
                            update_tray_icon(app, &state);
                        }

                        // 내 현황 보기 (웹 대시보드)
                        "dashboard" => {
                            let _ = open::that("https://hwarang.ai/dashboard");
                        }

                        // 커뮤니티 (Grid 현황)
                        "community" => {
                            let _ = open::that("https://hwarang.ai/community");
                        }

                        // 설정
                        "settings" => {
                            // TODO: 설정 창 열기
                            let _ = open::that("https://hwarang.ai/settings");
                        }

                        // hwarang.ai 열기
                        "website" => {
                            let _ = open::that("https://hwarang.ai");
                        }

                        // 종료
                        "quit" => {
                            state.status = "stopped".into();
                            std::process::exit(0);
                        }

                        _ => {}
                    }
                }

                // 트레이 아이콘 클릭 (Mac에서는 왼쪽 클릭)
                SystemTrayEvent::LeftClick { .. } => {
                    // 상태 패널 표시 또는 메뉴 열기
                }

                _ => {}
            }
        })
        .setup(|app| {
            // 백그라운드 상태 업데이트 스레드
            let app_handle = app.handle();
            let bg_state = state.clone();

            thread::spawn(move || {
                loop {
                    thread::sleep(Duration::from_secs(5));

                    let mut state = bg_state.lock().unwrap();
                    if state.status != "stopped" {
                        // TODO: 실제 GPU 상태 읽기
                        // TODO: 실제 작업 수행 + 토큰 적립
                        state.uptime_minutes += 1;

                        // 트레이 메뉴 갱신
                        let new_menu = build_tray_menu(&state);
                        app_handle.tray_handle().set_menu(new_menu).unwrap();
                        update_tray_icon(&app_handle, &state);
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// 트레이 메뉴 구성
fn build_tray_menu(state: &AgentState) -> SystemTrayMenu {
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

    let mut menu = SystemTrayMenu::new();

    // 상태 표시 (클릭 불가)
    menu = menu.add_item(
        CustomMenuItem::new("status", format!(
            "{} {} | 오늘 +{} 토큰",
            status_icon, status_text, format_tokens(state.tokens_today)
        )).disabled()
    );

    // GPU 정보
    if state.status != "stopped" {
        menu = menu.add_item(
            CustomMenuItem::new("gpu_info", format!(
                "   {} | {}% | {}°C",
                state.gpu_name, state.gpu_usage_percent as i32, state.gpu_temp
            )).disabled()
        );
        menu = menu.add_item(
            CustomMenuItem::new("work_info", format!(
                "   오늘 {}건 처리 | 총 {} 토큰",
                state.work_count_today, format_tokens(state.tokens_total)
            )).disabled()
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

    // 링크
    menu = menu.add_item(CustomMenuItem::new("website", "🔗 hwarang.ai"));

    menu = menu.add_native_item(SystemTrayMenuItem::Separator);

    // 종료
    menu = menu.add_item(CustomMenuItem::new("quit", "종료"));

    menu
}

/// 상태에 따라 트레이 아이콘 변경
fn update_tray_icon<R: tauri::Runtime>(app: &tauri::AppHandle<R>, state: &AgentState) {
    // TODO: 상태별 아이콘 파일
    // running: icon-green.png
    // idle: icon-yellow.png
    // stopped: icon-gray.png
    // error: icon-red.png
    let _icon_name = match state.status.as_str() {
        "running" => "icon-green",
        "idle" => "icon-yellow",
        "stopped" => "icon-gray",
        "error" => "icon-red",
        _ => "icon-gray",
    };

    // app.tray_handle().set_icon(tauri::Icon::File(icon_path)).unwrap();

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
