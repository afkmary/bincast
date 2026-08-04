interface FillGaugeProps {
  percent: number;
  size?: number;
}

export default function FillGauge({ percent, size = 100 }: FillGaugeProps) {
  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percent / 100) * circumference;

  const color = percent >= 80 ? "#e08a5b" : percent >= 50 ? "#e8b04b" : "#6fb98f";

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e3f2e8" strokeWidth="8" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth="8"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dashoffset 0.5s ease" }}
      />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle" fontSize={size / 5} fontWeight="bold" fill="#333">
        {percent}%
      </text>
    </svg>
  );
}