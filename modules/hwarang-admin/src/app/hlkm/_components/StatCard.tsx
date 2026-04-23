/**
 * StatCard — 재사용 가능한 통계 숫자 카드
 * 대시보드 상단에 큰 숫자 + 레이블 + 부가 정보 표시
 */

type Trend = "up" | "down" | "flat";

interface StatCardProps {
  label: string;
  value: number | string;
  hint?: string;
  delta?: number; // 변동치 (예: +12, -3)
  trend?: Trend;
  icon?: string;
  accent?: "primary" | "success" | "warning" | "danger" | "neutral";
}

const ACCENTS: Record<NonNullable<StatCardProps["accent"]>, string> = {
  primary: "#2563eb",
  success: "#16a34a",
  warning: "#d97706",
  danger: "#dc2626",
  neutral: "#475569",
};

function formatValue(v: number | string): string {
  if (typeof v === "number") return v.toLocaleString("ko-KR");
  return v;
}

export default function StatCard({
  label,
  value,
  hint,
  delta,
  trend,
  icon,
  accent = "primary",
}: StatCardProps) {
  const accentColor = ACCENTS[accent];
  const trendArrow = trend === "up" ? "▲" : trend === "down" ? "▼" : "—";
  const trendColor =
    trend === "up" ? "#16a34a" : trend === "down" ? "#dc2626" : "#64748b";

  return (
    <div
      className="rounded-xl border bg-white p-5 transition-shadow hover:shadow-md"
      style={{ borderColor: "#e5e7eb" }}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2 text-xs font-medium text-gray-500">
          {icon && <span className="text-base">{icon}</span>}
          <span>{label}</span>
        </div>
        {delta !== undefined && (
          <span
            className="text-xs font-medium tabular-nums"
            style={{ color: trendColor }}
          >
            {trendArrow} {Math.abs(delta).toLocaleString("ko-KR")}
          </span>
        )}
      </div>

      <div
        className="mt-3 text-3xl font-bold tabular-nums"
        style={{ color: accentColor }}
      >
        {formatValue(value)}
      </div>

      {hint && (
        <div className="mt-1 text-xs text-gray-500">{hint}</div>
      )}
    </div>
  );
}
