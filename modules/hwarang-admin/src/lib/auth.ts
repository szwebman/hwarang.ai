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
