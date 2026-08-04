// mockData.ts
// Temporary mock data matching the shared data contract (docs/README.md).
// Swap this out for a real API call once Kate's Azure endpoint is live.

export type BinClassification = "full" | "not_full" | "obstructed" | "anomaly";

export interface Bin {
  bin_id: string;
  location: string;
  fill_percent: number; // 0-100
  classification: BinClassification;
  last_updated: string; // ISO 8601
  recommendation: string | null;
}

export const mockBins: Bin[] = [
  {
    bin_id: "bin-001",
    location: "Main Building - Lobby",
    fill_percent: 82,
    classification: "full",
    last_updated: "2026-08-04T14:32:00Z",
    recommendation: "Bin nearing capacity — schedule pickup soon.",
  },
  {
    bin_id: "bin-002",
    location: "Main Building - Cafeteria",
    fill_percent: 45,
    classification: "not_full",
    last_updated: "2026-08-04T14:30:00Z",
    recommendation: null,
  },
  {
    bin_id: "bin-003",
    location: "Library - 2nd Floor",
    fill_percent: 91,
    classification: "obstructed",
    last_updated: "2026-08-04T14:28:00Z",
    recommendation: "Reading suggests full, but pattern is unusual — inspect for obstruction.",
  },
  {
    bin_id: "bin-004",
    location: "Gym - Entrance",
    fill_percent: 12,
    classification: "not_full",
    last_updated: "2026-08-04T14:25:00Z",
    recommendation: null,
  },
  {
    bin_id: "bin-005",
    location: "Parkade - Level 1",
    fill_percent: 67,
    classification: "anomaly",
    last_updated: "2026-08-04T14:20:00Z",
    recommendation: "Fill level jumped abnormally fast — flagged for review.",
  },
];

// Simulates an async API call so components can be written the same way
// they will be once the real endpoint exists.
export function fetchMockBins(): Promise<Bin[]> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(mockBins), 300);
  });
}