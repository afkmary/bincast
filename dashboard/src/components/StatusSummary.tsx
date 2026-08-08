// dashboard/src/components/StatusSummary.tsx
import type { Bin } from "../api";

interface StatusSummaryProps {
  bins: Bin[];
}

export default function StatusSummary({ bins }: StatusSummaryProps) {
  if (bins.length === 0) {
    return <p className="queue-empty">No bins reporting.</p>;
  }

  const needsPickup = bins.filter((b) => b.fill_percent >= 70).length;
  const flagged = bins.filter(
    (b) => b.classification === "obstructed" || b.classification === "anomaly"
  ).length;
  const avgFill = Math.round(
    bins.reduce((sum, b) => sum + b.fill_percent, 0) / bins.length
  );

  // Highest fill first, but anything the agent flagged jumps the line.
  const priority = [...bins].sort((a, b) => {
    const flaggedFirst = (bin: Bin) =>
      bin.classification === "obstructed" || bin.classification === "anomaly" ? 1 : 0;
    return (
      flaggedFirst(b) - flaggedFirst(a) || b.fill_percent - a.fill_percent
    );
  })[0];

  const stats = [
    { value: bins.length, label: "bins reporting", tone: "neutral" },
    { value: needsPickup, label: "need pickup", tone: "warn" },
    { value: flagged, label: "flagged by agent", tone: "alert" },
    { value: `${avgFill}%`, label: "average fill", tone: "neutral" },
  ];

  return (
    <div className="status-summary">
      <div className="status-stats">
        {stats.map((s) => (
          <div className={`status-stat status-stat--${s.tone}`} key={s.label}>
            <span className="status-value">{s.value}</span>
            <span className="status-label">{s.label}</span>
          </div>
        ))}
      </div>

      {priority.recommendation && (
        <p className="status-next">
          <span className="status-next-tag">Next up</span>
          <strong>{priority.location}</strong>
          <span className="status-next-why">{priority.recommendation}</span>
        </p>
      )}
    </div>
  );
}
