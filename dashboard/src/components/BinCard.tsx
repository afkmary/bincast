import { useEffect, useState } from "react";
import FillGauge from "./FillGauge";
import HistoryChart from "./HistoryChart";
import { fetchHistory, postDecision, renameBin, type Bin, type Reading } from "../api";


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
  const [name, setName] = useState(bin.location);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(bin.location);

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

  async function saveName() {
    const next = draft.trim();
    setEditing(false);
    if (!next || next === name) return;
    const previous = name;
    setName(next);                    // optimistic
    try {
      await renameBin(bin.bin_id, next);
    } catch {
      setName(previous);              // roll back if the API rejects it
      alert("Could not rename — try again.");
    }
  }

  return (
    <div className="bin-card">
      <div className="bin-card-header">
        {editing ? (
          <input
            className="bin-name-input"
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onBlur={saveName}
            onKeyDown={(e) => {
              if (e.key === "Enter") saveName();
              if (e.key === "Escape") { setDraft(name); setEditing(false); }
            }}
          />
        ) : (
          <h3
            className="bin-name"
            onClick={() => { setDraft(name); setEditing(true); }}
            title="Click to rename"
          >
            {name}
          </h3>
        )}
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