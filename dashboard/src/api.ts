// api.ts
export interface Bin {
  bin_id: string;
  location: string;
  fill_percent: number;
  classification: "full" | "not_full" | "obstructed" | "anomaly";
  last_updated: string;
  recommendation: string | null;
}

export interface HistoryPoint {
  timestamp: string;
  fill_percent: number;
}

const API_URL = import.meta.env.VITE_API_URL;

export async function fetchBins(): Promise<Bin[]> {
  const res = await fetch(`${API_URL}/bins`);
  if (!res.ok) throw new Error("Failed to fetch bins");
  return res.json();
}

export async function fetchHistory(binId: string): Promise<HistoryPoint[]> {
  const res = await fetch(`${API_URL}/history`);
  if (!res.ok) throw new Error("Failed to fetch history");
  const all = await res.json();
  return all[binId] ?? [];
}