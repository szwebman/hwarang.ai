"use client";

/**
 * /account/devices
 *
 * 화랑 그리드 다중 기기 로그인 시스템 — 사용자가 자기 등록 기기를 관리하는 페이지.
 *
 * 흐름:
 * - NextAuth 세션 검증 (미로그인 시 /login 으로 리다이렉트, callbackUrl 보존)
 * - GET  /api/auth/agent/devices    → 등록 기기 목록
 * - DELETE /api/auth/agent/devices  → 기기 폐기 (id 쿼리)
 * - 30초 자동 폴링 + 수동 새로고침
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import Link from "next/link";

import { DeviceCard, type DeviceCardDevice } from "@/components/devices/device-card";

const POLL_INTERVAL_MS = 30_000;

interface DevicesResponse {
  devices: DeviceCardDevice[];
}

export default function AccountDevicesPage() {
  const router = useRouter();
  const { status } = useSession();

  const [devices, setDevices] = useState<DeviceCardDevice[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  // 미로그인 → 로그인 페이지
  useEffect(() => {
    if (status === "unauthenticated") {
      router.push(`/login?callbackUrl=${encodeURIComponent("/account/devices")}`);
    }
  }, [status, router]);

  // 토스트 자동 해제
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const fetchDevices = useCallback(
    async (mode: "initial" | "refresh") => {
      if (mode === "initial") setLoading(true);
      else setRefreshing(true);
      setError(null);
      try {
        const resp = await fetch("/api/auth/agent/devices", {
          method: "GET",
          credentials: "include",
          cache: "no-store",
        });
        if (!resp.ok) {
          throw new Error(
            `기기 목록을 불러오지 못했습니다 (HTTP ${resp.status})`,
          );
        }
        const data = (await resp.json()) as DevicesResponse | DeviceCardDevice[];
        const list = Array.isArray(data) ? data : data.devices;
        setDevices(Array.isArray(list) ? list : []);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "알 수 없는 오류";
        setError(msg);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [],
  );

  // 인증 시 1회 로드 + 30초 폴링
  const pollRef = useRef<number | null>(null);
  useEffect(() => {
    if (status !== "authenticated") return;
    fetchDevices("initial");
    pollRef.current = window.setInterval(() => {
      fetchDevices("refresh");
    }, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, [status, fetchDevices]);

  const handleRevoke = useCallback(
    async (id: string) => {
      setRevokingId(id);
      try {
        const resp = await fetch(
          `/api/auth/agent/devices?id=${encodeURIComponent(id)}`,
          {
            method: "DELETE",
            credentials: "include",
          },
        );
        if (!resp.ok) {
          const text = await resp.text().catch(() => "");
          throw new Error(text || `폐기 실패 (HTTP ${resp.status})`);
        }
        setDevices((prev) => (prev ? prev.filter((d) => d.id !== id) : prev));
        setToast({ kind: "ok", msg: "기기가 폐기되었습니다." });
      } catch (e) {
        const msg = e instanceof Error ? e.message : "폐기 중 오류가 발생했습니다.";
        setToast({ kind: "err", msg });
      } finally {
        setRevokingId(null);
      }
    },
    [],
  );

  if (status === "loading" || status === "unauthenticated") {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--background)" }}
      >
        <div
          className="animate-pulse text-sm"
          style={{ color: "var(--muted-foreground)" }}
        >
          로딩 중...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-8 flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold">내 기기</h1>
            <p
              className="text-sm mt-1"
              style={{ color: "var(--muted-foreground)" }}
            >
              화랑 그리드에 연결된 기기를 관리합니다. 사용하지 않는 기기는
              폐기하여 보안을 유지하세요.
            </p>
          </div>
          <button
            type="button"
            onClick={() => fetchDevices("refresh")}
            disabled={refreshing}
            className="px-4 py-2 rounded-xl text-sm font-medium border transition-all disabled:opacity-50 hover:bg-[var(--muted)]"
            style={{ borderColor: "var(--border)" }}
          >
            {refreshing ? "새로고침 중..." : "새로고침"}
          </button>
        </div>

        {/* 토스트 */}
        {toast && (
          <div
            className="rounded-xl border p-3 mb-4 text-sm"
            style={{
              borderColor:
                toast.kind === "ok" ? "#16a34a" : "var(--destructive)",
              background:
                toast.kind === "ok"
                  ? "rgba(22,163,74,0.08)"
                  : "rgba(239,68,68,0.08)",
              color: toast.kind === "ok" ? "#16a34a" : "var(--destructive)",
            }}
            role="status"
          >
            {toast.msg}
          </div>
        )}

        {/* 에러 */}
        {error && (
          <div
            className="rounded-xl border p-3 mb-4 text-sm"
            style={{
              borderColor: "var(--destructive)",
              background: "rgba(239,68,68,0.08)",
              color: "var(--destructive)",
            }}
            role="alert"
          >
            {error}
          </div>
        )}

        {/* 본문 */}
        {loading && devices === null ? (
          <div
            className="rounded-2xl border p-12 text-center text-sm"
            style={{
              borderColor: "var(--border)",
              color: "var(--muted-foreground)",
            }}
          >
            기기 목록 불러오는 중...
          </div>
        ) : devices && devices.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-3">
            {devices?.map((d) => (
              <DeviceCard
                key={d.id}
                device={d}
                onRevoke={handleRevoke}
                highlightCurrent
                busy={revokingId === d.id}
              />
            ))}
          </div>
        )}

        {/* 푸터 안내 */}
        <p
          className="text-xs mt-8 text-center"
          style={{ color: "var(--muted-foreground)" }}
        >
          기기 목록은 30초마다 자동으로 갱신됩니다.
        </p>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div
      className="rounded-2xl border p-12 text-center"
      style={{ borderColor: "var(--border)" }}
    >
      <div
        className="w-16 h-16 mx-auto rounded-2xl flex items-center justify-center text-3xl mb-4"
        style={{ background: "var(--muted)" }}
        aria-hidden
      >
        💻
      </div>
      <h2 className="text-lg font-semibold mb-2">
        아직 등록된 기기가 없습니다
      </h2>
      <p
        className="text-sm mb-6"
        style={{ color: "var(--muted-foreground)" }}
      >
        화랑 그리드 데스크탑 에이전트를 설치하면 이 기기가 자동으로
        등록됩니다.
      </p>
      <Link
        href="https://hwarang.ai/grid"
        target="_blank"
        rel="noreferrer"
        className="inline-block px-5 py-2.5 rounded-xl text-sm font-medium text-white"
        style={{ background: "var(--primary)" }}
      >
        화랑 그리드 다운로드
      </Link>
    </div>
  );
}
