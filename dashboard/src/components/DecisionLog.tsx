import { useEffect, useState } from "react";
import { fetchDecisions, type Decision } from "../api";

export default function DecisionLog() {
  const [decisions, setDecisions] = useState<Decision[]>([]);

  useEffect(() => {
    fetchDecisions().then((data) =>
      setDecisions([...data].reverse())
    );
  }, []);

  if (decisions.length === 0) {
    return <p className="queue-empty">No decisions logged yet.</p>;
  }

  return (
    <ul className="decision-log">
      {decisions.map((d) => (
        <li key={d.id ?? d.timestamp}>
          <span className="log-location">{d.location}</span>
          <span className="log-recommendation">{d.recommendation}</span>
          <span className={`log-decision ${d.decision}`}>
            {d.decision === "approved" ? "Approved" : "Rejected"}
          </span>
        </li>
      ))}
    </ul>
  );
}