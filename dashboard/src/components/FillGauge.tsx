// dashboard/src/components/FillGauge.tsx
import { useEffect, useState } from "react";
import type { Bin } from "../api";

interface FillGaugeProps {
  percent: number;
  /** Pass bin.bin_id so each gauge gets its own clip path. */
  binId?: string;
  /** Optional - lets an obstructed or anomalous bin colour itself correctly. */
  classification?: Bin["classification"];
}

// Body of the bin in SVG user units - the fill animates between these.
const TOP = 34;
const BOTTOM = 104;

// Thresholds match PickupQueue: anything 70+ is queued for pickup.
function bandColor(percent: number, classification?: Bin["classification"]): string {
  if (classification === "obstructed") return "#e8b04b";
  if (classification === "anomaly") return "#7a9cc6";
  if (percent >= 85) return "#e08a5b";
  if (percent >= 70) return "#e8b04b";
  return "#6fb98f";
}

export default function FillGauge({ percent, binId, classification }: FillGaugeProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const safe = Math.max(0, Math.min(100, Math.round(percent)));
  const color = bandColor(safe, classification);
  const fillTop = BOTTOM - ((BOTTOM - TOP) * safe) / 100;
  const clipId = `bin-clip-${binId ?? safe}`;

  return (
    <div className="fill-gauge">
      <svg
        viewBox="0 0 88 132"
        className="fill-gauge-svg"
        role="img"
        aria-label={`${safe} percent full`}
      >
        <defs>
          <clipPath id={clipId}>
            <path d="M22 34 H66 L61 104 H27 Z" />
          </clipPath>
        </defs>

        {/* ultrasonic ping from the clip-on module */}
        <g className="fill-gauge-ping" stroke={color} fill="none" strokeLinecap="round">
          <path d="M31 17 A 13 13 0 0 1 57 17" strokeWidth="2.5" opacity="0.35" />
          <path d="M35 10 A 9 9 0 0 1 53 10" strokeWidth="2.5" opacity="0.7" />
        </g>

        {/* empty interior */}
        <path d="M22 34 H66 L61 104 H27 Z" className="fill-gauge-well" />

        {/* the fill */}
        <rect
          x="20"
          y={fillTop}
          width="48"
          height={BOTTOM - fillTop}
          fill={color}
          clipPath={`url(#${clipId})`}
          className="fill-gauge-level"
          style={{
            transform: mounted ? "scaleY(1)" : "scaleY(0)",
            transformOrigin: `0px ${BOTTOM}px`,
          }}
        />

        {/* outline over the fill keeps the edge crisp */}
        <path d="M22 34 H66 L61 104 H27 Z" className="fill-gauge-outline" />
        <rect x="16" y="25" width="56" height="9" rx="4" className="fill-gauge-lid" />

        <text x="44" y="126" className="fill-gauge-value" textAnchor="middle" fill={color}>
          {safe}%
        </text>
      </svg>
    </div>
  );
}
