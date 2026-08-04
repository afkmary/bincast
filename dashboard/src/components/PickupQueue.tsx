import type { Bin } from "../api";

interface PickupQueueProps {
  bins: Bin[];
}

export default function PickupQueue({ bins }: PickupQueueProps) {
  const queue = [...bins]
    .filter((b) => b.fill_percent >= 70 || b.classification === "obstructed")
    .sort((a, b) => b.fill_percent - a.fill_percent);

  if (queue.length === 0) {
    return <p className="queue-empty">No pickups needed right now.</p>;
  }

  return (
    <div className="pickup-queue">
      {queue.map((bin) => (
        <div key={bin.bin_id} className="pickup-row">
          <span className="pickup-label">{bin.location}</span>
          <div className="pickup-bar-track">
            <div className="pickup-bar-fill" style={{ width: `${bin.fill_percent}%` }} />
          </div>
          <span className="pickup-percent">{bin.fill_percent}%</span>
        </div>
      ))}
    </div>
  );
}