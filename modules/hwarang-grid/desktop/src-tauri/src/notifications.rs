// 알림 모듈 - 사용자 데스크탑 알림
//
// 트리거 종류:
//   1. 보상 도착 (reward)            - tokens_today 증가
//   2. 라운드 완료 (round_completed) - current_round_id null + tokens 증가
//   3. KYC 미인증 (kyc_required)     - 첫 실행 시 1회
//   4. GPU 과열 (overheating)        - gpu_temp >= 85°C
//   5. 라운드 실패 (round_failed)    - last_error 발생
//
// 중복 방지:
//   - 보상 알림: 최소 30초 간격
//   - 과열 알림: 최소 5분 간격
//   - KYC 알림: 한 번만
//   - 에러 알림: 같은 에러 메시지는 5분 간격

use std::time::{Duration, Instant};
use tauri::api::notification::Notification;
use tauri::Manager;

const REWARD_COOLDOWN: Duration = Duration::from_secs(30);
const OVERHEAT_COOLDOWN: Duration = Duration::from_secs(300);
const ERROR_COOLDOWN: Duration = Duration::from_secs(300);

#[derive(Default)]
pub struct NotificationTracker {
    pub last_reward_at: Option<Instant>,
    pub last_overheat_at: Option<Instant>,
    pub notified_kyc_required: bool,
    pub last_error_msg: Option<String>,
    pub last_error_at: Option<Instant>,
}

impl NotificationTracker {
    pub fn allow_reward(&self) -> bool {
        match self.last_reward_at {
            None => true,
            Some(t) => t.elapsed() >= REWARD_COOLDOWN,
        }
    }
    pub fn mark_reward(&mut self) {
        self.last_reward_at = Some(Instant::now());
    }

    pub fn allow_overheat(&self) -> bool {
        match self.last_overheat_at {
            None => true,
            Some(t) => t.elapsed() >= OVERHEAT_COOLDOWN,
        }
    }
    pub fn mark_overheat(&mut self) {
        self.last_overheat_at = Some(Instant::now());
    }

    pub fn allow_error(&self, msg: &str) -> bool {
        match (&self.last_error_msg, self.last_error_at) {
            (Some(prev), Some(t)) if prev == msg => t.elapsed() >= ERROR_COOLDOWN,
            _ => true,
        }
    }
    pub fn mark_error(&mut self, msg: &str) {
        self.last_error_msg = Some(msg.to_string());
        self.last_error_at = Some(Instant::now());
    }
}

fn bundle_id<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> String {
    app.config().tauri.bundle.identifier.clone()
}

pub fn notify_reward_received<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    amount: i64,
    round_name: &str,
) {
    let _ = Notification::new(bundle_id(app))
        .title("HWARANG 보상 도착! 💰")
        .body(format!("{} 작업 완료, +{} 토큰", round_name, amount))
        .icon("icon")
        .show();
}

pub fn notify_round_completed<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    round_name: &str,
) {
    let _ = Notification::new(bundle_id(app))
        .title("라운드 완료 ✅")
        .body(format!("'{}' 라운드를 끝냈습니다. 보상은 곧 정산됩니다.", round_name))
        .icon("icon")
        .show();
}

pub fn notify_kyc_required<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    let _ = Notification::new(bundle_id(app))
        .title("KYC 인증이 필요합니다 🔐")
        .body("토큰 수령을 위해 hwarang.ai 에서 본인 인증을 완료해 주세요.")
        .icon("icon")
        .show();
}

pub fn notify_overheating<R: tauri::Runtime>(app: &tauri::AppHandle<R>, temp: i32) {
    let _ = Notification::new(bundle_id(app))
        .title("GPU 과열 경고 🔥")
        .body(format!(
            "GPU 온도가 {}°C 입니다. 작업이 일시 감속될 수 있습니다.",
            temp
        ))
        .icon("icon")
        .show();
}

pub fn notify_round_failed<R: tauri::Runtime>(app: &tauri::AppHandle<R>, reason: &str) {
    let _ = Notification::new(bundle_id(app))
        .title("작업 실패 ⚠️")
        .body(format!("라운드 처리 중 오류: {}", reason))
        .icon("icon")
        .show();
}

pub fn notify_login_completed<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    email: &str,
    kyc_verified: bool,
) {
    let body = if kyc_verified {
        format!("{} 로그인 완료. KYC 인증 완료 ✅", email)
    } else {
        format!("{} 로그인 완료. KYC 인증이 필요합니다 🔐", email)
    };
    let _ = Notification::new(bundle_id(app))
        .title("로그인 완료 🎉")
        .body(body)
        .icon("icon")
        .show();
}

pub fn notify_login_failed<R: tauri::Runtime>(app: &tauri::AppHandle<R>, reason: &str) {
    let _ = Notification::new(bundle_id(app))
        .title("로그인 실패")
        .body(format!("로그인 처리 중 오류: {}", reason))
        .icon("icon")
        .show();
}
