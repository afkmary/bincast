import type { Bin } from "../api";

interface PickupQueueProps {
  bins: Bin[];
}

export default function PickupQueue({ bins }: PickupQueueProps) {
  const fill = (b: Bin) => b.fill_percentage ?? 0;

  const queue = [...bins]
    .filter((b) => fill(b) >= 70 || b.classification === "obstructed")
    .sort((a, b) => fill(b) - fill(a));

  if (queue.length === 0) {
    return <p className="queue-empty">No pickups needed right now.</p>;
  }

  return (
    <div className="pickup-queue">
      {queue.map((bin) => (
        <div key={bin.bin_id} className="pickup-row">
          <span className="pickup-label">{bin.location}</span>
          <div className="pickup-bar-track">
            <div className="pickup-bar-fill" style={{ width: `${bin.fill_percentage}%` }} />
          </div>
          <span className="pickup-percent">{bin.fill_percentage}%</span>
        </div>
      ))}
    </div>
  );
}