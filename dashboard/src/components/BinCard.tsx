import { useEffect, useState } from "react";
import FillGauge from "./FillGauge";
import HistoryChart from "./HistoryChart";
import { fetchHistory, postDecision, type Bin, type Reading } from "../api";

interface BinCardProps {
  bin: Bin;
}

const classificationLabel: Record<Bin["classification"], string> = {
  full: "Full",
  not_full: "OK",
  obstructed: "Obstructed",
  anomaly: "Anomaly",
};

const classificationColor: Record<Bin["classification"], string> = {
  full: "#e08a5b",
  not_full: "#6fb98f",
  obstructed: "#e8b04b",
  anomaly: "#7a9cc6",
};

export default function BinCard({ bin }: BinCardProps) {
  const [history, setHistory] = useState<Reading[]>([]);
  const [decided, setDecided] = useState<"approved" | "rejected" | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchHistory(bin.bin_id).then(setHistory);
  }, [bin.bin_id]);

  async function handleDecision(review_status: "approved" | "rejected") {
    if (!bin.decision_id) return;
    setSaving(true);
    try {
      await postDecision({
        bin_id: bin.bin_id,
        decision_id: bin.decision_id,
        review_status,
      });
      setDecided(review_status);
    } catch {
      alert("Could not save decision — try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bin-card">
      <div className="bin-card-header">
        <h3>{bin.location}</h3>
        <span className="bin-tag" style={{ backgroundColor: classificationColor[bin.classification] }}>
          {classificationLabel[bin.classification]}
        </span>
      </div>
      <FillGauge
        percent={bin.fill_percentage ?? 0}
        binId={bin.bin_id}
        classification={bin.classification}
      />
      <HistoryChart data={history} />
      {bin.recommendation && (
        <>
          <p className="bin-recommendation">{bin.recommendation}</p>
          {decided ? (
            <p className={`decision-tag ${decided}`}>
              {decided === "approved" ? "Approved" : "Rejected"}
            </p>
          ) : (
            <div className="decision-buttons">
              <button
                className="approve-btn"
                disabled={saving}
                onClick={() => handleDecision("approved")}
              >
                Approve
              </button>
              <button
                className="reject-btn"
                disabled={saving}
                onClick={() => handleDecision("rejected")}
              >
                Reject
              </button>
            </div>
          )}
        </>
      )}
      <p className="bin-updated">
        {bin.last_updated
          ? `Updated: ${new Date(bin.last_updated).toLocaleTimeString()}`
          : "No readings yet"}
      </p>
    </div>
  );
}