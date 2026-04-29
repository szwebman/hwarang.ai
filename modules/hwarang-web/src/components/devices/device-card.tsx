"use client";

/**
 * DeviceCard
 *
 * 화랑 그리드 다중 기기 로그인 시스템에서 등록 기기 1개를 표시하는 공통 카드.
 * - /account/devices (사용자 기기 관리)
 * - /agent-login (현재 디바이스 등록 + 기존 디바이스 목록)
 * 양쪽에서 재사용한다.
 */

import { useMemo } from "react";

export interface DeviceCardDevice {
  id: string;
  deviceName: string | null;
  deviceOs: string | null;
  deviceArch: string | null;
  deviceGpu: string | null;
  deviceKind?: string | null;
  lastSeenAt: string | null;
  isActive: boolean;
  keyPrefix: string;
  isCurrent?: boolean;
}

export interface DeviceCardProps {
  device: DeviceCardDevice;
  onRevoke?: (id: string) => void | Promise<void>;
  highlightCurrent?: boolean;
  busy?: boolean;
}

/**
 * OS 식별 이모지 — 사용자가 어떤 기기인지 한눈에 알 수 있게.
 * 의미 있는 식별 아이콘이므로 이모지 사용 OK.
 */
export function getOsIcon(os: string | null | undefined): string {
  if (!os) return "💻";
  const s = os.toLowerCase();
  if (s.includes("mac") || s.includes("darwin") || s.includes("osx")) return "🍎";
  if (s.includes("win")) return "🪟";
  if (s.includes("linux") || s.includes("ubuntu") || s.includes("debian") || s.includes("fedora") || s.includes("arch")) return "🐧";
  if (s.includes("android")) return "🤖";
  if (s.includes("ios")) return "📱";
  return "💻";
}

/**
 * 한국어 상대시간 포맷터.
 * date-fns / dayjs 등 외부 라이브러리 없이 직접 구현 — 의존성 추가 회피.
 */
export function formatRelativeKo(iso: string | null | undefined): string {
  if (!iso) return "기록 없음";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "기록 없음";
  const diffSec = Math.max(0, Math.floor((Date.now() - t) / 1000));

  if (diffSec < 30) return "방금 전";
  if (diffSec < 60) return `${diffSec}초 전`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}시간 전`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay === 1) return "어제";
  if (diffDay < 7) return `${diffDay}일 전`;
  if (diffDay < 30) return `${Math.floor(diffDay / 7)}주 전`;
  if (diffDay < 365) return `${Math.floor(diffDay / 30)}개월 전`;
  return `${Math.floor(diffDay / 365)}년 전`;
}

/** lastSeenAt < 5분이면 ONLINE 으로 본다. */
export function isOnline(lastSeenAt: string | null | undefined): boolean {
  if (!lastSeenAt) return false;
  const t = new Date(lastSeenAt).getTime();
  if (Number.isNaN(t)) return false;
  return Date.now() - t < 5 * 60 * 1000;
}

export function DeviceCard({
  device,
  onRevoke,
  highlightCurrent = false,
  busy = false,
}: DeviceCardProps) {
  const online = useMemo(
    () => isOnline(device.lastSeenAt) && device.isActive,
    [device.lastSeenAt, device.isActive],
  );
  const relTime = useMemo(() => formatRelativeKo(device.lastSeenAt), [device.lastSeenAt]);
  const icon = useMemo(() => getOsIcon(device.deviceOs), [device.deviceOs]);

  const isCurrent = highlightCurrent && device.isCurrent === true;

  const handleRevoke = async () => {
    if (!onRevoke) return;
    const label = device.deviceName || device.keyPrefix;
    const ok = window.confirm(
      `정말로 "${label}" 기기를 폐기하시겠습니까?\n\n` +
        `이 기기에서 발급된 API 키는 즉시 만료되며,\n` +
        `해당 기기의 화랑 그리드 에이전트는 더 이상 작동하지 않습니다.`,
    );
    if (!ok) return;
    await onRevoke(device.id);
  };

  return (
    <div
      className="rounded-2xl border p-5 transition-all hover:shadow-md"
      style={{
        borderColor: isCurrent ? "var(--primary)" : "var(--border)",
        background: isCurrent ? "var(--accent)" : "var(--background)",
        boxShadow: isCurrent ? "0 0 0 2px var(--primary)" : undefined,
      }}
    >
      <div className="flex items-start gap-4">
        {/* OS 아이콘 */}
        <div
          className="flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center text-2xl"
          style={{ background: "var(--muted)" }}
          aria-hidden
        >
          {icon}
        </div>

        {/* 본문 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold truncate">
              {device.deviceName || "이름 없는 기기"}
            </h3>
            {isCurrent && (
              <span
                className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                style={{ background: "var(--primary)", color: "#fff" }}
              >
                이 기기
              </span>
            )}
            <span
              className="text-xs font-medium flex items-center gap-1"
              style={{ color: online ? "#16a34a" : "var(--muted-foreground)" }}
            >
              <span aria-hidden>{online ? "🟢" : "⚪"}</span>
              {online ? "ONLINE" : "OFFLINE"}
            </span>
          </div>

          <div
            className="text-xs mt-1 space-x-2"
            style={{ color: "var(--muted-foreground)" }}
          >
            {device.deviceOs && <span>{device.deviceOs}</span>}
            {device.deviceArch && (
              <>
                <span aria-hidden>·</span>
                <span>{device.deviceArch}</span>
              </>
            )}
            {device.deviceGpu && (
              <>
                <span aria-hidden>·</span>
                <span>{device.deviceGpu}</span>
              </>
            )}
          </div>

          <div
            className="text-xs mt-2 flex items-center gap-2 flex-wrap"
            style={{ color: "var(--muted-foreground)" }}
          >
            <code
              className="text-[10px] px-1.5 py-0.5 rounded font-mono"
              style={{ background: "var(--muted)" }}
            >
              {device.keyPrefix}
            </code>
            <span aria-hidden>·</span>
            <span>마지막 활동 {relTime}</span>
          </div>
        </div>

        {/* 폐기 버튼 */}
        {onRevoke && (
          <button
            type="button"
            onClick={handleRevoke}
            disabled={busy}
            className="flex-shrink-0 text-xs px-3 py-1.5 rounded-lg border transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[var(--muted)]"
            style={{ borderColor: "var(--border)", color: "var(--destructive)" }}
            title="이 기기 폐기"
          >
            {busy ? "처리 중..." : "이 기기 폐기"}
          </button>
        )}
      </div>
    </div>
  );
}

export default DeviceCard;
