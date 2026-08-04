import { useEffect, useState } from "react";
import FillGauge from "./FillGauge";
import HistoryChart from "./HistoryChart";
import { fetchHistory, type Bin, type HistoryPoint } from "../api";

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
  full: "#e53935",
  not_full: "#43a047",
  obstructed: "#fb8c00",
  anomaly: "#8e24aa",
};

export default function BinCard({ bin }: BinCardProps) {
  const [history, setHistory] = useState<HistoryPoint[]>([]);

  useEffect(() => {
    fetchHistory(bin.bin_id).then(setHistory);
  }, [bin.bin_id]);

  return (
    <div className="bin-card">
      <div className="bin-card-header">
        <h3>{bin.location}</h3>
        <span className="bin-tag" style={{ backgroundColor: classificationColor[bin.classification] }}>
          {classificationLabel[bin.classification]}
        </span>
      </div>
      <FillGauge percent={bin.fill_percent} />
      <HistoryChart data={history} />
      {bin.recommendation && <p className="bin-recommendation">{bin.recommendation}</p>}
      <p className="bin-updated">Updated: {new Date(bin.last_updated).toLocaleTimeString()}</p>
    </div>
  );
}