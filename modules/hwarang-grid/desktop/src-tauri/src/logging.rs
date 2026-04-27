//! 데스크탑 앱 로그 시스템.
//!
//! 출력 위치:
//!   - stdout (디버그 빌드)
//!   - ~/.hwarang/logs/desktop-YYYY-MM-DD.log (영속)
//!
//! 사용:
//!   logging::init_logging()?;        // main.rs 시작부에서 1회
//!   log::info!("...");
//!
//! 로테이션: 30일 이상된 로그 자동 삭제.

use chrono::Local;
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::sync::Mutex;

const KEEP_DAYS_DEFAULT: u32 = 30;

static FILE_HANDLE: Mutex<Option<File>> = Mutex::new(None);

fn logs_dir() -> Result<PathBuf, std::io::Error> {
    let home = dirs::home_dir()
        .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::NotFound, "home dir 없음"))?;
    let dir = home.join(".hwarang").join("logs");
    std::fs::create_dir_all(&dir)?;
    Ok(dir)
}

/// 오늘 날짜의 로그 파일 경로.
pub fn log_path() -> PathBuf {
    let date = Local::now().format("%Y-%m-%d").to_string();
    logs_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(format!("desktop-{}.log", date))
}

/// 로그 시스템 초기화. main.rs 시작 시 1회만 호출.
pub fn init_logging() -> Result<PathBuf, std::io::Error> {
    let path = log_path();

    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)?;

    *FILE_HANDLE.lock().unwrap() = Some(file);

    // env_logger 를 사용하여 stdout 로 보내고, 별도 file_writer 로 파일에도 미러.
    // 단순화를 위해 자체 로거 등록.
    let _ = log::set_logger(&FILE_LOGGER);
    log::set_max_level(log::LevelFilter::Info);

    log::info!(
        "===== 화랑 Grid 데스크탑 시작 v{} ({}) =====",
        env!("CARGO_PKG_VERSION"),
        std::env::consts::OS
    );

    // 백그라운드: 시작 시 오래된 로그 삭제
    let _ = rotate_old_logs(KEEP_DAYS_DEFAULT);

    Ok(path)
}

/// 30일 이상 지난 로그 삭제. 삭제된 파일 수 반환.
pub fn rotate_old_logs(keep_days: u32) -> Result<u32, std::io::Error> {
    let dir = logs_dir()?;
    let cutoff = Local::now().naive_local()
        - chrono::Duration::days(keep_days as i64);
    let mut deleted = 0u32;

    for entry in std::fs::read_dir(&dir)? {
        let entry = match entry {
            Ok(e) => e,
            Err(_) => continue,
        };
        let name = entry.file_name();
        let name_str = match name.to_str() {
            Some(s) => s,
            None => continue,
        };
        // desktop-YYYY-MM-DD.log
        if !name_str.starts_with("desktop-") || !name_str.ends_with(".log") {
            continue;
        }
        let date_part = &name_str["desktop-".len()..name_str.len() - ".log".len()];
        let parsed = chrono::NaiveDate::parse_from_str(date_part, "%Y-%m-%d");
        if let Ok(d) = parsed {
            let dt = d.and_hms_opt(0, 0, 0).unwrap_or_default();
            if dt < cutoff {
                if std::fs::remove_file(entry.path()).is_ok() {
                    deleted += 1;
                }
            }
        }
    }
    Ok(deleted)
}

// --- 자체 Logger 구현 (stdout + file) ---

struct FileLogger;
static FILE_LOGGER: FileLogger = FileLogger;

impl log::Log for FileLogger {
    fn enabled(&self, metadata: &log::Metadata) -> bool {
        metadata.level() <= log::Level::Info
            || cfg!(debug_assertions)
    }

    fn log(&self, record: &log::Record) {
        if !self.enabled(record.metadata()) {
            return;
        }

        let line = format!(
            "[{}] [{:5}] [{}] {}\n",
            Local::now().format("%Y-%m-%d %H:%M:%S"),
            record.level(),
            record.target(),
            record.args()
        );

        // stdout
        #[cfg(debug_assertions)]
        {
            print!("{}", line);
        }

        // file
        if let Ok(mut guard) = FILE_HANDLE.lock() {
            if let Some(f) = guard.as_mut() {
                let _ = f.write_all(line.as_bytes());
            }
        }
    }

    fn flush(&self) {
        if let Ok(mut guard) = FILE_HANDLE.lock() {
            if let Some(f) = guard.as_mut() {
                let _ = f.flush();
            }
        }
    }
}
