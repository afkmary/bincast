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
    <ul className="pickup-queue">
      {queue.map((bin) => (
        <li key={bin.bin_id}>
          <span>{bin.location}</span>
          <span className="queue-percent">{bin.fill_percent}%</span>
        </li>
      ))}
    </ul>
  );
}