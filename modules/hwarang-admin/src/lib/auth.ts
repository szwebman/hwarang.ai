/**
 * 관리자 인증 유틸리티
 */

import crypto from "crypto";

export function verifyToken(token: string): { userId: string; role: string } | null {
  try {
    const [payloadB64, sig] = token.split(".");
    const secret = process.env.ADMIN_SECRET || "hwarang-admin-secret";
    const expectedSig = crypto.createHmac("sha256", secret).update(Buffer.from(payloadB64, "base64")).digest("hex");

    if (sig !== expectedSig) return null;

    const payload = JSON.parse(Buffer.from(payloadB64, "base64").toString());
    if (payload.exp < Date.now()) return null;

    return { userId: payload.userId, role: payload.role };
  } catch {
    return null;
  }
}

// 클라이언트 측 인증 헬퍼
export function getAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("admin_token");
}

export function getAdminUser(): any | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("admin_user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function isLoggedIn(): boolean {
  return !!getAdminToken();
}

export function logout() {
  localStorage.removeItem("admin_token");
  localStorage.removeItem("admin_user");
  window.location.href = "/login";
}

/**
 * 관리자 API 공용 fetch 래퍼.
 * admin_token 자동 첨부. 401/403 시 로그인 페이지로 리다이렉트.
 */
export async function adminFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = getAdminToken();
  const headers = new Headers(init.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");

  const resp = await fetch(input, { ...init, headers });

  if (resp.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("admin_token");
      window.location.href = "/login";
    }
  }
  return resp;
}
