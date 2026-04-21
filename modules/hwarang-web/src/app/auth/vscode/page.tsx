/**
 * VS Code 확장팩 인증 페이지
 *
 * 흐름:
 * 1. VS Code 확장팩이 callback_port와 함께 이 페이지를 엶
 * 2. 로그인 안 되어 있으면 /login으로 리다이렉트 (callbackUrl 포함)
 * 3. 로그인 상태면 "VS Code에 연결" 버튼 표시
 * 4. 버튼 클릭 → API 키 발급 → http://localhost:{port}?api_key=... 로 리다이렉트
 */

"use client";

import { useSession } from "next-auth/react";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useState, Suspense } from "react";

function VSCodeAuthInner() {
  const { data: session, status } = useSession();
  const searchParams = useSearchParams();
  const router = useRouter();

  const callbackPort = searchParams.get("callback_port");
  const editor = searchParams.get("editor") || "vscode";

  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [autoStarted, setAutoStarted] = useState(false);

  // 로그인 안 되어 있으면 로그인 페이지로
  useEffect(() => {
    if (status === "unauthenticated") {
      const current = encodeURIComponent(
        `/auth/vscode?callback_port=${callbackPort}&editor=${editor}`
      );
      router.push(`/login?callbackUrl=${current}`);
    }
  }, [status, callbackPort, editor, router]);

  const handleConnect = async () => {
    if (!callbackPort) {
      setError("콜백 포트가 없습니다. VS Code에서 다시 시도하세요.");
      return;
    }

    setConnecting(true);
    setError("");

    try {
      // API 키 발급
      const resp = await fetch("/api/auth/vscode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `VS Code - ${new Date().toLocaleDateString("ko-KR")}`,
        }),
      });

      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(err || "API 키 발급 실패");
      }

      const { key } = await resp.json();

      // 로컬 콜백으로 리다이렉트
      const callbackUrl = `http://127.0.0.1:${callbackPort}/?api_key=${encodeURIComponent(key)}`;

      setSuccess(true);

      // 짧은 지연 후 리다이렉트
      setTimeout(() => {
        window.location.href = callbackUrl;
      }, 800);
    } catch (e: any) {
      setError(e.message);
      setConnecting(false);
    }
  };

  // 로그인 완료 + callback_port가 있으면 자동으로 연결 시작
  useEffect(() => {
    if (
      status === "authenticated" &&
      callbackPort &&
      !autoStarted &&
      !connecting &&
      !success
    ) {
      setAutoStarted(true);
      handleConnect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, callbackPort, autoStarted]);

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

  if (status !== "authenticated") {
    return null; // 리다이렉트 중
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <div style={styles.logo}>H</div>
        <h1 style={styles.title}>VS Code 연결</h1>
        <p style={styles.subtitle}>
          화랑 AI 확장팩을 VS Code에 연결합니다
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

        {!callbackPort && (
          <div style={styles.warning}>
            ⚠️ 콜백 포트가 없습니다. VS Code 확장팩에서 "로그인" 버튼으로 다시 시도하세요.
          </div>
        )}

        {error && <div style={styles.error}>{error}</div>}

        {success ? (
          <div style={styles.success}>
            ✓ 연결 완료! VS Code로 돌아가주세요...
          </div>
        ) : (
          <button
            onClick={handleConnect}
            disabled={connecting || !callbackPort}
            style={{
              ...styles.button,
              opacity: connecting || !callbackPort ? 0.5 : 1,
              cursor: connecting || !callbackPort ? "default" : "pointer",
            }}
          >
            {connecting ? "연결 중..." : "VS Code에 연결"}
          </button>
        )}

        <p style={styles.footer}>
          API 키가 안전하게 VS Code로 전달됩니다.
          <br />
          언제든지{" "}
          <a href="/api-keys" style={styles.link}>
            API 키 관리
          </a>
          에서 취소할 수 있습니다.
        </p>
      </div>
    </div>
  );
}

export default function VSCodeAuthPage() {
  return (
    <Suspense fallback={<div style={styles.page} />}>
      <VSCodeAuthInner />
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
  title: {
    fontSize: "24px",
    fontWeight: 700,
    marginBottom: "6px",
  },
  subtitle: {
    fontSize: "14px",
    color: "rgba(255,255,255,0.6)",
    marginBottom: "28px",
  },
  userBox: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "14px 16px",
    background: "rgba(255,255,255,0.05)",
    borderRadius: "12px",
    marginBottom: "24px",
  },
  avatar: {
    width: "40px",
    height: "40px",
    borderRadius: "50%",
  },
  userName: {
    fontSize: "14px",
    fontWeight: 600,
  },
  userEmail: {
    fontSize: "12px",
    color: "rgba(255,255,255,0.5)",
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
  warning: {
    padding: "10px 14px",
    background: "rgba(251,191,36,0.12)",
    color: "#fbbf24",
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
  link: {
    color: "#c084fc",
    textDecoration: "none",
  },
  muted: {
    color: "rgba(255,255,255,0.5)",
    fontSize: "13px",
  },
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
