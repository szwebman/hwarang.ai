//! 기기 식별 (device fingerprint) 헬퍼.
//!
//! 다중 기기 로그인 지원을 위해 데스크탑 클라이언트가 자신의 기기 정보를
//! 서버에 전달한다. 서버는 ApiKey 1:N User 구조이므로 device_id (= ApiKey.id)
//! 기반으로 기기별 세션을 분리한다.
//!
//! 동작 보증:
//!   - `collect_device_info()` 는 시작 시 1회만 호출 (Lazy 캐싱 권장)
//!   - 같은 PC 에서는 항상 같은 fingerprint 반환 (결정성)
//!   - panic 금지 — 모든 IO 실패는 fallback 값 (e.g. "Unknown") 으로 흡수

use serde::{Deserialize, Serialize};
use std::env;

/// 기기 식별 정보 — 로그인 URL query string + heartbeat payload.
#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct DeviceInfo {
    pub hostname: String,
    /// `env::consts::OS` — "windows" / "macos" / "linux"
    pub os: String,
    /// `env::consts::ARCH` — "x86_64" / "aarch64"
    pub arch: String,
    /// 감지된 GPU 이름 (실패 시 "Unknown")
    pub gpu: String,
    /// SHA256(hostname + os + arch) 의 hex
    pub fingerprint: String,
}

impl DeviceInfo {
    /// 로그인 URL 의 query string 일부를 만든다 (앞에 `&` 없음).
    pub fn to_query_string(&self) -> String {
        format!(
            "os={}&arch={}&hostname={}&gpu={}&fingerprint={}",
            urlencode(&self.os),
            urlencode(&self.arch),
            urlencode(&self.hostname),
            urlencode(&self.gpu),
            urlencode(&self.fingerprint),
        )
    }
}

/// 시스템에서 기기 정보를 수집한다. 시작 시 1회만 호출하면 충분.
pub fn collect_device_info() -> DeviceInfo {
    let hostname = read_hostname();
    let os = env::consts::OS.to_string();
    let arch = env::consts::ARCH.to_string();
    let gpu = detect_gpu();
    let fingerprint = compute_fingerprint(&hostname, &os, &arch);

    DeviceInfo {
        hostname,
        os,
        arch,
        gpu,
        fingerprint,
    }
}

/// hostname 을 추출. 실패 시 "unknown-host".
fn read_hostname() -> String {
    // 의존성 회피: 플랫폼별 환경변수/명령으로 읽는다.
    // - Unix: $HOSTNAME 또는 `hostname` 명령
    // - Windows: $COMPUTERNAME
    if let Ok(name) = env::var("HOSTNAME") {
        if !name.trim().is_empty() {
            return name.trim().to_string();
        }
    }
    if let Ok(name) = env::var("COMPUTERNAME") {
        if !name.trim().is_empty() {
            return name.trim().to_string();
        }
    }
    if let Ok(out) = std::process::Command::new("hostname").output() {
        if out.status.success() {
            if let Ok(s) = String::from_utf8(out.stdout) {
                let trimmed = s.trim();
                if !trimmed.is_empty() {
                    return trimmed.to_string();
                }
            }
        }
    }
    "unknown-host".to_string()
}

/// GPU 이름 감지: nvidia-smi → sysctl (Apple) → rocm-smi → "Unknown".
/// main.rs 의 백그라운드 폴링과 같은 우선순위.
pub fn detect_gpu() -> String {
    // 1. NVIDIA
    if let Ok(out) = std::process::Command::new("nvidia-smi")
        .args(["--query-gpu=name", "--format=csv,noheader"])
        .output()
    {
        if out.status.success() {
            if let Ok(text) = String::from_utf8(out.stdout) {
                let trimmed = text.trim();
                if !trimmed.is_empty() {
                    return trimmed.lines().next().unwrap_or(trimmed).to_string();
                }
            }
        }
    }

    // 2. Apple Silicon
    #[cfg(target_os = "macos")]
    {
        if let Ok(out) = std::process::Command::new("sysctl")
            .args(["-n", "machdep.cpu.brand_string"])
            .output()
        {
            if let Ok(text) = String::from_utf8(out.stdout) {
                let trimmed = text.trim();
                if trimmed.contains("Apple") {
                    return trimmed.to_string();
                }
            }
        }
    }

    // 3. AMD
    if let Ok(out) = std::process::Command::new("rocm-smi")
        .args(["--showproductname"])
        .output()
    {
        if out.status.success() {
            if let Ok(text) = String::from_utf8(out.stdout) {
                if text.contains("GPU") || text.contains("Radeon") {
                    return "AMD GPU".to_string();
                }
            }
        }
    }

    "Unknown".to_string()
}

/// SHA256(hostname || "|" || os || "|" || arch) 의 hex.
///
/// 의존성 회피를 위해 std 의 hash 가 아닌 직접 구현.
/// 같은 PC 에서는 항상 같은 값을 반환 (결정성).
fn compute_fingerprint(hostname: &str, os: &str, arch: &str) -> String {
    let payload = format!("{}|{}|{}", hostname, os, arch);
    sha256_hex(payload.as_bytes())
}

// ---------------------------------------------------------------------------
// SHA-256 (의존성 없는 간이 구현 — 결정성만 보장하면 충분)
// ---------------------------------------------------------------------------

const K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

fn sha256_hex(data: &[u8]) -> String {
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];

    // padding: 1비트 + 0... + 길이(64bit big-endian)
    let bit_len = (data.len() as u64) * 8;
    let mut buf: Vec<u8> = data.to_vec();
    buf.push(0x80);
    while buf.len() % 64 != 56 {
        buf.push(0);
    }
    buf.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in buf.chunks(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([
                chunk[i * 4], chunk[i * 4 + 1], chunk[i * 4 + 2], chunk[i * 4 + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }

        let mut a = h[0];
        let mut b = h[1];
        let mut c = h[2];
        let mut d = h[3];
        let mut e = h[4];
        let mut f = h[5];
        let mut g = h[6];
        let mut hh = h[7];

        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let t1 = hh.wrapping_add(s1).wrapping_add(ch).wrapping_add(K[i]).wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(maj);

            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }

        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }

    let mut out = String::with_capacity(64);
    for word in &h {
        out.push_str(&format!("{:08x}", word));
    }
    out
}

/// 최소한의 URL encode (RFC 3986 unreserved 외 모두 %XX).
pub fn urlencode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.as_bytes() {
        match *b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(*b as char);
            }
            _ => {
                out.push_str(&format!("%{:02X}", b));
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fingerprint_is_deterministic() {
        let a = compute_fingerprint("host", "macos", "aarch64");
        let b = compute_fingerprint("host", "macos", "aarch64");
        assert_eq!(a, b);
        assert_eq!(a.len(), 64);
    }

    #[test]
    fn fingerprint_differs_per_host() {
        let a = compute_fingerprint("host-a", "macos", "aarch64");
        let b = compute_fingerprint("host-b", "macos", "aarch64");
        assert_ne!(a, b);
    }

    #[test]
    fn urlencode_basic() {
        assert_eq!(urlencode("hello world"), "hello%20world");
        assert_eq!(urlencode("Jin's Mac"), "Jin%27s%20Mac");
        assert_eq!(urlencode("abc-_.~"), "abc-_.~");
    }
}
