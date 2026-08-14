import { useEffect, useState } from "react";
import { fetchDecisions, type Decision } from "../api";

export default function DecisionLog() {
  const [decisions, setDecisions] = useState<Decision[]>([]);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDecisions().then(setDecisions).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="queue-empty">Could not load decisions: {error}</p>;

  if (decisions.length === 0) {
    return <p className="queue-empty">No decisions logged yet.</p>;
  }

  return (
    <ul className="decision-log">
      {decisions.map((d) => (
        <li key={d.decision_id}>
          <span className="log-location">{d.bin_id}</span>
          <span className="log-recommendation">{d.reasoning}</span>
          <span className={`log-decision ${d.review_status}`}>
            {d.review_status === "approved" ? "Approved"
              : d.review_status === "rejected" ? "Rejected" : "Pending"}
          </span>
        </li>
      ))}
    </ul>
  );
}