//! 데스크탑 ↔ 웹 KYC / 로그인 플로우.
//!
//! 흐름:
//!   1. 데스크탑이 외부 브라우저로 https://hwarang.ai/agent-login?nonce=XYZ&os=... 열기
//!   2. 사용자가 웹에서 로그인 + 필요시 KYC 완료
//!   3. 웹은 deep link 로 hwarang-grid://auth?token=...&nonce=XYZ&email=...&kyc=true 호출
//!   4. 데스크탑은 nonce 일치 확인 → 서버에 token 검증 → ~/.hwarang/account.json 저장
//!
//! 저장 경로: ~/.hwarang/account.json, ~/.hwarang/.pending_nonce
//!
//! KYC 단독 흐름:
//!   - 이미 로그인된 상태에서 KYC만 시작할 때
//!   - https://hwarang.ai/kyc?source=desktop_agent&token=API_KEY 열기

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

const PENDING_NONCE_FILE: &str = ".pending_nonce";
const ACCOUNT_FILE: &str = "account.json";
const NONCE_TTL_SECS: i64 = 600; // 10 분

/// 계정 정보 (~/.hwarang/account.json).
#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct AccountInfo {
    pub email: Option<String>,
    pub user_id: Option<String>,
    pub api_key: Option<String>,
    #[serde(default)]
    pub kyc_verified: bool,
    #[serde(default = "default_tier")]
    pub tier: String,
    #[serde(default)]
    pub expert_credentials: Vec<String>,
    pub last_synced_at: Option<String>,
}

impl Default for AccountInfo {
    fn default() -> Self {
        Self {
            email: None,
            user_id: None,
            api_key: None,
            kyc_verified: false,
            tier: default_tier(),
            expert_credentials: vec![],
            last_synced_at: None,
        }
    }
}

fn default_tier() -> String {
    "BRONZE".to_string()
}

#[derive(Serialize, Deserialize)]
struct PendingNonce {
    nonce: String,
    created_at: i64, // unix seconds
}

/// `~/.hwarang/` 디렉터리 (없으면 생성).
fn hwarang_dir() -> Result<PathBuf, String> {
    let home = dirs::home_dir().ok_or_else(|| "home dir 없음".to_string())?;
    let dir = home.join(".hwarang");
    fs::create_dir_all(&dir).map_err(|e| format!("디렉터리 생성 실패: {}", e))?;
    Ok(dir)
}

fn now_secs() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// 간단한 v4 비슷한 nonce (uuid 의존성 없이).
fn generate_nonce() -> String {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};

    let mut h = DefaultHasher::new();
    now_secs().hash(&mut h);
    std::process::id().hash(&mut h);
    let a = h.finish();

    let mut h2 = DefaultHasher::new();
    a.hash(&mut h2);
    "salt".hash(&mut h2);
    let b = h2.finish();

    format!("{:016x}{:016x}", a, b)
}

fn save_pending_nonce(nonce: &str) -> Result<(), String> {
    let path = hwarang_dir()?.join(PENDING_NONCE_FILE);
    let payload = PendingNonce {
        nonce: nonce.to_string(),
        created_at: now_secs(),
    };
    let json = serde_json::to_string(&payload).map_err(|e| e.to_string())?;
    fs::write(&path, json).map_err(|e| format!("nonce 저장 실패: {}", e))
}

fn load_pending_nonce() -> Option<PendingNonce> {
    let path = hwarang_dir().ok()?.join(PENDING_NONCE_FILE);
    let content = fs::read_to_string(&path).ok()?;
    serde_json::from_str(&content).ok()
}

fn clear_pending_nonce() {
    if let Ok(path) = hwarang_dir().map(|d| d.join(PENDING_NONCE_FILE)) {
        let _ = fs::remove_file(path);
    }
}

/// 로그인 플로우 시작 — 외부 브라우저를 연다.
///
/// `api_url` 예: "https://hwarang.ai"
pub fn open_login_flow(api_url: &str) -> Result<String, String> {
    let nonce = generate_nonce();
    let url = format!(
        "{}/agent-login?nonce={}&os={}",
        api_url.trim_end_matches('/'),
        nonce,
        std::env::consts::OS,
    );
    save_pending_nonce(&nonce)?;
    open::that(&url).map_err(|e| format!("브라우저 열기 실패: {}", e))?;
    log::info!("로그인 플로우 시작: nonce={}", &nonce[..8]);
    Ok(nonce)
}

/// KYC 플로우 시작 (이미 로그인된 상태 가정).
pub fn open_kyc_flow(api_url: &str) -> Result<(), String> {
    let account = load_account().ok_or_else(|| "먼저 로그인이 필요합니다".to_string())?;
    let api_key = account
        .api_key
        .as_deref()
        .ok_or_else(|| "API 키가 없습니다".to_string())?;

    let url = format!(
        "{}/kyc?source=desktop_agent&token={}",
        api_url.trim_end_matches('/'),
        api_key,
    );
    open::that(&url).map_err(|e| format!("브라우저 열기 실패: {}", e))?;
    log::info!("KYC 플로우 시작");
    Ok(())
}

/// `hwarang-grid://auth?...` 형태의 deep link 를 파싱한다.
fn parse_query(url: &str) -> std::collections::HashMap<String, String> {
    let mut map = std::collections::HashMap::new();
    let q = match url.find('?') {
        Some(i) => &url[i + 1..],
        None => return map,
    };
    for pair in q.split('&') {
        if let Some(eq) = pair.find('=') {
            let k = &pair[..eq];
            let v = &pair[eq + 1..];
            map.insert(
                k.to_string(),
                urldecode(v).unwrap_or_else(|| v.to_string()),
            );
        }
    }
    map
}

fn urldecode(s: &str) -> Option<String> {
    let bytes = s.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'+' => {
                out.push(b' ');
                i += 1;
            }
            b'%' if i + 2 < bytes.len() => {
                let hex = std::str::from_utf8(&bytes[i + 1..i + 3]).ok()?;
                let v = u8::from_str_radix(hex, 16).ok()?;
                out.push(v);
                i += 3;
            }
            c => {
                out.push(c);
                i += 1;
            }
        }
    }
    String::from_utf8(out).ok()
}

/// Deep link 처리. nonce 검증 + 서버 토큰 검증 (verify_with_server=true) 후 저장.
pub async fn handle_deep_link(url: &str, api_url: &str) -> Result<AccountInfo, String> {
    log::info!("Deep link 수신: {}", url);

    if !url.starts_with("hwarang-grid://") {
        return Err("지원하지 않는 스킴".into());
    }

    let params = parse_query(url);

    // 1. nonce 검증
    let recv_nonce = params
        .get("nonce")
        .ok_or_else(|| "nonce 파라미터 없음".to_string())?;
    let pending = load_pending_nonce().ok_or_else(|| "대기 중인 로그인 요청 없음".to_string())?;
    if &pending.nonce != recv_nonce {
        return Err("nonce 불일치 — 다른 세션에서의 응답일 수 있습니다".into());
    }
    if now_secs() - pending.created_at > NONCE_TTL_SECS {
        clear_pending_nonce();
        return Err("로그인 요청이 만료되었습니다 (10분). 다시 시도하세요".into());
    }

    // 2. token
    let token = params
        .get("token")
        .ok_or_else(|| "token 파라미터 없음".to_string())?
        .clone();

    // 3. 서버에 검증 (실패해도 일단 로컬 정보 사용 — 오프라인 케이스 고려)
    let mut info = match verify_token_with_server(&token, api_url).await {
        Ok(info) => info,
        Err(e) => {
            log::warn!("서버 검증 실패 ({}); deep link 정보로 대체", e);
            AccountInfo {
                email: params.get("email").cloned(),
                user_id: params.get("user_id").cloned(),
                api_key: Some(token.clone()),
                kyc_verified: params
                    .get("kyc")
                    .map(|v| v == "true" || v == "1")
                    .unwrap_or(false),
                tier: params.get("tier").cloned().unwrap_or_else(default_tier),
                expert_credentials: vec![],
                last_synced_at: None,
            }
        }
    };

    // 검증된 정보 보강
    if info.api_key.is_none() {
        info.api_key = Some(token);
    }
    info.last_synced_at = Some(chrono_now_iso());

    save_account(&info)?;
    clear_pending_nonce();
    log::info!("로그인 완료: email={:?}, kyc={}", info.email, info.kyc_verified);
    Ok(info)
}

fn chrono_now_iso() -> String {
    chrono::Local::now().to_rfc3339()
}

/// 서버에 token 유효성 검증.
///
/// `GET {api_url}/api/auth/whoami` Authorization: Bearer ...
pub async fn verify_token_with_server(token: &str, api_url: &str) -> Result<AccountInfo, String> {
    let url = format!(
        "{}/api/auth/whoami",
        api_url.trim_end_matches('/'),
    );
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(8))
        .build()
        .map_err(|e| e.to_string())?;

    let resp = client
        .get(&url)
        .bearer_auth(token)
        .send()
        .await
        .map_err(|e| format!("요청 실패: {}", e))?;

    if !resp.status().is_success() {
        return Err(format!("HTTP {}", resp.status()));
    }

    let body: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;

    Ok(AccountInfo {
        email: body["email"].as_str().map(String::from),
        user_id: body["user_id"].as_str().map(String::from)
            .or_else(|| body["id"].as_str().map(String::from)),
        api_key: Some(token.to_string()),
        kyc_verified: body["kyc_verified"].as_bool().unwrap_or(false),
        tier: body["tier"]
            .as_str()
            .map(String::from)
            .unwrap_or_else(default_tier),
        expert_credentials: body["expert_credentials"]
            .as_array()
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default(),
        last_synced_at: Some(chrono_now_iso()),
    })
}

pub fn load_account() -> Option<AccountInfo> {
    let path = hwarang_dir().ok()?.join(ACCOUNT_FILE);
    let content = fs::read_to_string(&path).ok()?;
    serde_json::from_str(&content).ok()
}

pub fn save_account(info: &AccountInfo) -> Result<(), String> {
    let path = hwarang_dir()?.join(ACCOUNT_FILE);
    let json = serde_json::to_string_pretty(info).map_err(|e| e.to_string())?;
    fs::write(&path, json).map_err(|e| format!("계정 저장 실패: {}", e))?;
    Ok(())
}

pub fn clear_account() -> Result<(), String> {
    let path = hwarang_dir()?.join(ACCOUNT_FILE);
    if path.exists() {
        fs::remove_file(&path).map_err(|e| format!("계정 삭제 실패: {}", e))?;
    }
    clear_pending_nonce();
    Ok(())
}
