/**
 * DomainBar — SVG 기반 막대 차트 (가로/세로)
 * 도메인별 사실 분포, 상태별 분포 등에 사용
 */

interface BarItem {
  label: string;
  value: number;
  color?: string;
}

interface DomainBarProps {
  title?: string;
  items: BarItem[];
  orientation?: "horizontal" | "vertical";
  height?: number;
  emptyMessage?: string;
}

const DEFAULT_COLORS = [
  "#2563eb",
  "#7c3aed",
  "#db2777",
  "#dc2626",
  "#ea580c",
  "#d97706",
  "#16a34a",
  "#0891b2",
  "#475569",
  "#be185d",
];

export default function DomainBar({
  title,
  items,
  orientation = "horizontal",
  height = 220,
  emptyMessage = "아직 데이터가 없습니다",
}: DomainBarProps) {
  if (!items || items.length === 0) {
    return (
      <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
        {title && <h3 className="mb-3 text-sm font-semibold text-gray-900">{title}</h3>}
        <div className="flex h-32 items-center justify-center text-sm text-gray-400">
          {emptyMessage}
        </div>
      </div>
    );
  }

  const max = Math.max(...items.map((i) => i.value), 1);

  return (
    <div className="rounded-xl border bg-white p-5" style={{ borderColor: "#e5e7eb" }}>
      {title && <h3 className="mb-4 text-sm font-semibold text-gray-900">{title}</h3>}

      {orientation === "horizontal" ? (
        <div className="space-y-2">
          {items.map((item, idx) => {
            const pct = (item.value / max) * 100;
            const color = item.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length];
            return (
              <div key={idx} className="flex items-center gap-3 text-xs">
                <div className="w-28 truncate text-gray-700" title={item.label}>
                  {item.label}
                </div>
                <div className="relative flex-1">
                  <div
                    className="h-5 rounded"
                    style={{ background: "#f1f5f9" }}
                  />
                  <div
                    className="absolute left-0 top-0 h-5 rounded transition-all"
                    style={{ width: `${pct}%`, background: color }}
                  />
                </div>
                <div className="w-16 text-right font-medium tabular-nums text-gray-900">
                  {item.value.toLocaleString("ko-KR")}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <svg width="100%" height={height} viewBox={`0 0 ${items.length * 60} ${height}`}>
          {items.map((item, idx) => {
            const barHeight = (item.value / max) * (height - 40);
            const x = idx * 60 + 10;
            const y = height - 20 - barHeight;
            const color = item.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length];
            return (
              <g key={idx}>
                <rect
                  x={x}
                  y={y}
                  width={40}
                  height={barHeight}
                  fill={color}
                  rx={3}
                />
                <text
                  x={x + 20}
                  y={y - 4}
                  textAnchor="middle"
                  fontSize="10"
                  fill="#111827"
                  fontWeight="600"
                >
                  {item.value.toLocaleString("ko-KR")}
                </text>
                <text
                  x={x + 20}
                  y={height - 4}
                  textAnchor="middle"
                  fontSize="10"
                  fill="#6b7280"
                >
                  {item.label.length > 8 ? item.label.slice(0, 8) + "…" : item.label}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
