/**
 * Hwarang Grid 데스크탑 / CLI 에이전트 로그인 페이지
 *
 * 두 가지 모드:
 *
 * (A) 데스크탑 모드 — Tauri 앱 deep link
 *     URL: /agent-login?nonce=XXX&os=darwin&arch=arm64&gpu=...&hostname=...&fingerprint=YYY
 *     흐름:
 *       1. 미로그인 → /login?callbackUrl=/agent-login?... 으로 리다이렉트
 *       2. 사용자가 "이 기기 등록" 클릭 → /api/auth/agent/register-device POST
 *       3. 받은 rawKey 를 deep link 로 전달:
 *          hwarang-grid://auth?token={rawKey}&nonce={nonce}&device_id={id}&email={email}
 *
 * (B) CLI 모드 — RFC 8628 Device Authorization Flow
 *     URL: /agent-login?nonce=XXX&cli=1&os=linux&arch=x86_64&...
 *     흐름:
 *       1. CLI → POST /api/auth/agent/cli-init → nonce + login_url 발급
 *       2. 사용자가 login_url 을 다른 기기 브라우저에서 열기
 *       3. 로그인 후 "이 기기 인증 승인" → POST /api/auth/agent/cli-approve
 *       4. CLI 가 cli-poll 폴링으로 rawKey 수령 → 로컬 저장
 *
 * 양쪽 모드 모두: 다른 기기 폐기 가능 (DELETE /api/auth/agent/devices/[id])
 */

"use client";

import { useSession } from "next-auth/react";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useState, Suspense, useCallback } from "react";

interface DeviceRow {
  id: string;
  deviceName: string | null;
  deviceOs: string | null;
  deviceArch: string | null;
  deviceGpu: string | null;
  deviceFingerprint: string | null;
  keyPrefix: string;
  lastSeenAt: string | null;
  isActive: boolean;
  createdAt: string;
  isCurrent: boolean;
}

function AgentLoginInner() {
  const { data: session, status } = useSession();
  const searchParams = useSearchParams();
  const router = useRouter();

  const nonce = searchParams.get("nonce") || "";
  const os = searchParams.get("os") || "";
  const arch = searchParams.get("arch") || "";
  const gpu = searchParams.get("gpu") || "";
  const hostname = searchParams.get("hostname") || "";
  const fingerprint = searchParams.get("fingerprint") || "";
  // CLI 모드: hwarang-agent login 등 헤드리스 환경에서 nonce 받아오는 흐름
  // (deep link 대신 단순 승인 후 폴링으로 인계)
  const isCliMode = searchParams.get("cli") === "1";

  const [deviceName, setDeviceName] = useState(hostname || "");
  const [devices, setDevices] = useState<DeviceRow[]>([]);
  const [loadingDevices, setLoadingDevices] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [issuedKeyPrefix, setIssuedKeyPrefix] = useState("");

  // 미로그인 시 /login 으로
  useEffect(() => {
    if (status === "unauthenticated") {
      const qs = searchParams.toString();
      const callback = encodeURIComponent(`/agent-login?${qs}`);
      router.push(`/login?callbackUrl=${callback}`);
    }
  }, [status, searchParams, router]);

  useEffect(() => {
    if (hostname && !deviceName) setDeviceName(hostname);
  }, [hostname, deviceName]);

  const loadDevices = useCallback(async () => {
    setLoadingDevices(true);
    try {
      const r = await fetch("/api/auth/agent/devices");
      if (r.ok) {
        const data = await r.json();
        setDevices(data.devices || []);
      }
    } catch {
      // ignore
    } finally {
      setLoadingDevices(false);
    }
  }, []);

  useEffect(() => {
    if (status === "authenticated") loadDevices();
  }, [status, loadDevices]);

  const handleRegister = async () => {
    setRegistering(true);
    setError("");
    try {
      // CLI 모드: 서버측 cli-approve 로 nonce 승인 → CLI 가 polling 으로 키 수령
      if (isCliMode) {
        if (!nonce) {
          throw new Error("CLI nonce 가 없습니다");
        }
        const resp = await fetch("/api/auth/agent/cli-approve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            nonce,
            deviceName: deviceName || hostname || "CLI 기기",
          }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          throw new Error(data.error || "CLI 승인 실패");
        }
        setSuccess(true);
        loadDevices();
        return;
      }

      // 데스크탑 (deep link) 모드: 기존 흐름
      const resp = await fetch("/api/auth/agent/register-device", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deviceName: deviceName || hostname || "Grid Agent",
          deviceOs: os || null,
          deviceArch: arch || null,
          deviceGpu: gpu || null,
          deviceFingerprint: fingerprint || null,
          reuseFingerprint: true,
        }),
      });

      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(txt || "기기 등록 실패");
      }

      const data = await resp.json();
      setIssuedKeyPrefix(data.keyPrefix || "");

      // whoami 보다는 세션 데이터로 충분 (deep link 페이로드)
      const email = session?.user?.email || "";
      // KYC / tier 는 추후 whoami 로 정확히 — 현재는 unknown 으로 둔다
      const params = new URLSearchParams({
        token: data.key,
        nonce,
        device_id: data.deviceId,
        email,
      });

      const deepLink = `hwarang-grid://auth?${params.toString()}`;

      setSuccess(true);

      // deep link 트리거
      window.location.href = deepLink;

      // 목록 갱신
      loadDevices();
    } catch (e: any) {
      setError(e.message || "등록 실패");
    } finally {
      setRegistering(false);
    }
  };

  const handleRevoke = async (deviceId: string) => {
    if (!confirm("이 기기를 폐기하시겠습니까? 해당 기기의 에이전트는 즉시 차단됩니다.")) return;
    try {
      const r = await fetch(`/api/auth/agent/devices/${deviceId}`, {
        method: "DELETE",
      });
      if (!r.ok) throw new Error(await r.text());
      loadDevices();
    } catch (e: any) {
      setError(e.message || "폐기 실패");
    }
  };

  if (status === "loading") {
    return (
      <div style={styles.page}>
        <div style={styles.card}>
          <div style={styles.spinner} />
          <p style={styles.muted}>로딩 중...</p>
        </div>
      </div>
    );
  }

  if (status !== "authenticated") return null;

  return (
    <div style={styles.page}>
      <div style={{ ...styles.card, maxWidth: 640 }}>
        <div style={styles.logo}>H</div>
        <h1 style={styles.title}>
          {isCliMode
            ? "Hwarang Grid CLI 인증"
            : "Hwarang Grid 데스크탑 에이전트"}
        </h1>
        <p style={styles.subtitle}>
          {isCliMode
            ? "헤드리스 서버 / SSH 환경의 CLI 를 인증합니다"
            : "이 PC 의 GPU 를 화랑 그리드에 연결합니다"}
        </p>

        <div style={styles.userBox}>
          {session?.user?.image && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={session.user.image} alt="" style={styles.avatar} />
          )}
          <div style={{ textAlign: "left", flex: 1 }}>
            <div style={styles.userName}>{session?.user?.name}</div>
            <div style={styles.userEmail}>{session?.user?.email}</div>
          </div>
        </div>

        {error && <div style={styles.error}>{error}</div>}

        {success ? (
          <div style={styles.success}>
            {isCliMode ? (
              <>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>
                  ✓ CLI 인증 완료
                </div>
                <div style={{ fontSize: 13 }}>
                  터미널로 돌아가세요. CLI 가 3초 안에 자동 인식합니다.
                </div>
                <button
                  onClick={() => window.close()}
                  style={{
                    ...styles.button,
                    marginTop: 14,
                    background: "rgba(255,255,255,0.08)",
                  }}
                >
                  터미널 창으로 돌아가기 (이 창 닫기)
                </button>
              </>
            ) : (
              <>
                연결 완료. 데스크탑 앱으로 돌아가세요.
                {issuedKeyPrefix && (
                  <div style={{ marginTop: 6, fontSize: 11, opacity: 0.7 }}>
                    발급된 키: {issuedKeyPrefix}
                  </div>
                )}
              </>
            )}
          </div>
        ) : (
          <>
            {/* 이 기기 정보 */}
            <div style={styles.section}>
              <div style={styles.sectionTitle}>
                {isCliMode ? "CLI 기기 인증 승인" : "이 기기 등록"}
              </div>
              <div style={styles.deviceMeta}>
                <div>
                  <span style={styles.metaLabel}>OS</span>
                  <span style={styles.metaValue}>{os || "-"}</span>
                </div>
                <div>
                  <span style={styles.metaLabel}>Arch</span>
                  <span style={styles.metaValue}>{arch || "-"}</span>
                </div>
                <div>
                  <span style={styles.metaLabel}>GPU</span>
                  <span style={styles.metaValue}>{gpu || "-"}</span>
                </div>
                <div>
                  <span style={styles.metaLabel}>Hostname</span>
                  <span style={styles.metaValue}>{hostname || "-"}</span>
                </div>
              </div>

              <label style={styles.label}>기기 이름</label>
              <input
                type="text"
                value={deviceName}
                onChange={(e) => setDeviceName(e.target.value)}
                placeholder="예: Jin's MacBook Pro"
                style={styles.input}
              />

              <button
                onClick={handleRegister}
                disabled={registering}
                style={{
                  ...styles.button,
                  opacity: registering ? 0.5 : 1,
                  cursor: registering ? "default" : "pointer",
                  marginTop: 12,
                }}
              >
                {registering
                  ? isCliMode
                    ? "승인 중..."
                    : "등록 중..."
                  : isCliMode
                  ? "이 기기 인증 승인"
                  : "이 기기 등록 + 연결"}
              </button>
            </div>

            {/* 등록된 기기 목록 */}
            <div style={styles.section}>
              <div style={styles.sectionTitle}>
                내 기기 목록{" "}
                <span style={styles.countBadge}>
                  {devices.filter((d) => d.isActive).length} 활성
                </span>
              </div>

              {loadingDevices ? (
                <p style={styles.muted}>불러오는 중...</p>
              ) : devices.length === 0 ? (
                <p style={styles.muted}>등록된 기기가 없습니다.</p>
              ) : (
                <div style={styles.deviceList}>
                  {devices.map((d) => {
                    const isThis =
                      !!fingerprint && d.deviceFingerprint === fingerprint;
                    return (
                      <div
                        key={d.id}
                        style={{
                          ...styles.deviceRow,
                          opacity: d.isActive ? 1 : 0.5,
                          borderColor: isThis
                            ? "rgba(192,132,252,0.5)"
                            : "rgba(255,255,255,0.08)",
                        }}
                      >
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={styles.deviceName}>
                            {d.deviceName || "(이름 없음)"}
                            {isThis && (
                              <span style={styles.thisBadge}>이 기기</span>
                            )}
                            {!d.isActive && (
                              <span style={styles.inactiveBadge}>폐기됨</span>
                            )}
                          </div>
                          <div style={styles.deviceMetaLine}>
                            {d.deviceOs || "?"} · {d.deviceGpu || "GPU 정보 없음"}
                          </div>
                          <div style={styles.deviceMetaLine}>
                            {d.lastSeenAt
                              ? `마지막 접속: ${new Date(
                                  d.lastSeenAt
                                ).toLocaleString("ko-KR")}`
                              : "아직 접속 기록 없음"}{" "}
                            · {d.keyPrefix}
                          </div>
                        </div>
                        {d.isActive && (
                          <button
                            onClick={() => handleRevoke(d.id)}
                            style={styles.revokeButton}
                          >
                            폐기
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}

        <p style={styles.footer}>
          API 키는 안전하게 데스크탑 앱으로 전달됩니다. 언제든{" "}
          <a href="/api-keys" style={styles.link}>
            API 키 관리
          </a>{" "}
          또는 이 페이지에서 폐기할 수 있습니다.
        </p>
      </div>
    </div>
  );
}

export default function AgentLoginPage() {
  return (
    <Suspense fallback={<div style={styles.page} />}>
      <AgentLoginInner />
    </Suspense>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background:
      "linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #312e81 100%)",
    padding: "20px",
  },
  card: {
    width: "100%",
    maxWidth: "420px",
    background: "rgba(255,255,255,0.05)",
    backdropFilter: "blur(20px)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: "20px",
    padding: "40px 32px",
    textAlign: "center",
    color: "#fff",
  },
  logo: {
    width: "64px",
    height: "64px",
    borderRadius: "16px",
    background: "linear-gradient(135deg, #c084fc, #7c3aed, #6366f1)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "28px",
    fontWeight: 800,
    color: "#fff",
    margin: "0 auto 20px",
    boxShadow: "0 10px 30px rgba(124,58,237,0.4)",
  },
  title: { fontSize: "22px", fontWeight: 700, marginBottom: "6px" },
  subtitle: {
    fontSize: "14px",
    color: "rgba(255,255,255,0.6)",
    marginBottom: "24px",
  },
  userBox: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "14px 16px",
    background: "rgba(255,255,255,0.05)",
    borderRadius: "12px",
    marginBottom: "20px",
  },
  avatar: { width: "40px", height: "40px", borderRadius: "50%" },
  userName: { fontSize: "14px", fontWeight: 600 },
  userEmail: { fontSize: "12px", color: "rgba(255,255,255,0.5)" },
  section: {
    marginTop: 18,
    padding: "16px",
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 12,
    textAlign: "left",
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: 700,
    color: "rgba(255,255,255,0.85)",
    marginBottom: 12,
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  countBadge: {
    fontSize: 10,
    padding: "2px 8px",
    borderRadius: 999,
    background: "rgba(124,58,237,0.25)",
    color: "#c4b5fd",
    fontWeight: 600,
  },
  deviceMeta: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 8,
    marginBottom: 14,
  },
  metaLabel: {
    display: "block",
    fontSize: 10,
    color: "rgba(255,255,255,0.4)",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  metaValue: { fontSize: 12, color: "rgba(255,255,255,0.85)" },
  label: {
    display: "block",
    fontSize: 11,
    color: "rgba(255,255,255,0.5)",
    marginBottom: 4,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  input: {
    width: "100%",
    padding: "10px 12px",
    background: "rgba(0,0,0,0.25)",
    color: "#fff",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 8,
    fontSize: 13,
    outline: "none",
  },
  button: {
    width: "100%",
    padding: "12px 20px",
    background: "linear-gradient(135deg, #7c3aed, #6366f1)",
    color: "#fff",
    border: "none",
    borderRadius: "10px",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    transition: "opacity 0.15s",
  },
  deviceList: { display: "flex", flexDirection: "column", gap: 8 },
  deviceRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 14px",
    background: "rgba(0,0,0,0.2)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
  },
  deviceName: {
    fontSize: 13,
    fontWeight: 600,
    color: "#fff",
    display: "flex",
    alignItems: "center",
    gap: 6,
    flexWrap: "wrap",
  },
  deviceMetaLine: {
    fontSize: 11,
    color: "rgba(255,255,255,0.5)",
    marginTop: 2,
  },
  thisBadge: {
    fontSize: 9,
    padding: "2px 6px",
    borderRadius: 4,
    background: "rgba(192,132,252,0.25)",
    color: "#e9d5ff",
    fontWeight: 700,
    textTransform: "uppercase",
  },
  inactiveBadge: {
    fontSize: 9,
    padding: "2px 6px",
    borderRadius: 4,
    background: "rgba(239,68,68,0.2)",
    color: "#fca5a5",
    fontWeight: 700,
    textTransform: "uppercase",
  },
  revokeButton: {
    padding: "6px 10px",
    background: "rgba(239,68,68,0.15)",
    color: "#fca5a5",
    border: "1px solid rgba(239,68,68,0.3)",
    borderRadius: 6,
    fontSize: 11,
    fontWeight: 600,
    cursor: "pointer",
  },
  success: {
    padding: "14px 16px",
    background: "rgba(74,222,128,0.15)",
    color: "#4ade80",
    borderRadius: "10px",
    fontSize: "14px",
    fontWeight: 500,
  },
  error: {
    padding: "10px 14px",
    background: "rgba(239,68,68,0.15)",
    color: "#f87171",
    borderRadius: "8px",
    fontSize: "12px",
    marginBottom: "16px",
    textAlign: "left",
  },
  footer: {
    fontSize: "11px",
    color: "rgba(255,255,255,0.4)",
    marginTop: "20px",
    lineHeight: 1.6,
  },
  link: { color: "#c084fc", textDecoration: "none" },
  muted: { color: "rgba(255,255,255,0.5)", fontSize: "13px" },
  spinner: {
    width: "32px",
    height: "32px",
    border: "3px solid rgba(255,255,255,0.1)",
    borderTopColor: "#c084fc",
    borderRadius: "50%",
    margin: "0 auto 12px",
    animation: "spin 0.8s linear infinite",
  },
};
