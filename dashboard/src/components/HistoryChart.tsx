import type { Reading } from "../api";

interface HistoryChartProps {
  data: Reading[];
  width?: number;
  height?: number;
}

export default function HistoryChart({ data, width = 240, height = 100 }: HistoryChartProps) {
  if (data.length === 0) return <p className="no-history">No history yet</p>;

  const padding = 20;
  const maxVal = 100;
  const stepX = (width - padding * 2) / (data.length - 1 || 1);

  const points = data.map((d, i) => {
    const x = padding + i * stepX;
    const y = height - padding - (d.fill_percentage / maxVal) * (height - padding * 2);
    return `${x},${y}`;
  });

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline points={points.join(" ")} fill="none" stroke="#1976d2" strokeWidth="2" />
      {data.map((_, i) => {
        const [x, y] = points[i].split(",").map(Number);
        return <circle key={i} cx={x} cy={y} r="3" fill="#1976d2" />;
      })}
    </svg>
  );
}