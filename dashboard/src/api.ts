// dashboard/src/api.ts
//
// Talks to the BinCast Azure Functions backend.
//
// Field names here MUST match schema/reading.schema.json and
// schema/agent-output.schema.json. The one exception is `classification`,
// which the backend derives for display only (see _classify_for_display in
// function_app.py) -- it is not part of the data contract.
//
// VITE_API_URL should include the /api prefix, e.g.
//   local:  http://localhost:7071/api
//   Azure:  https://bincast-api.azurewebsites.net/api

export type BinClassification = "full" | "not_full" | "obstructed" | "anomaly";

export type AgentAction =
  | "no_action"
  | "schedule_pickup"
  | "inspect"
  | "recalibrate";

export type ReviewStatus = "pending" | "approved" | "rejected";

export interface Bin {
  bin_id: string;
  location: string;
  fill_percentage: number | null;
  classification: BinClassification;
  last_updated: string | null;
  connectivity_status: "online" | "offline" | "stale";

  // Agent output. Null until the first reading has been classified.
  action: AgentAction | null;
  recommendation: string | null; // the agent's plain-language `reasoning`
  confidence: number | null; // 0..1
  decision_id: string | null;
  review_status: ReviewStatus | null;
  predicted_full_at: string | null;
  anomaly_type: string;

  // Auto-calibration state -- show "still learning" rather than presenting a
  // provisional fill number as fact.
  calibration_confident: boolean;
  calibration_samples: number;
}

export interface Reading {
  device_id: string;
  bin_id: string;
  timestamp: string;
  raw_distance_cm: number;
  fill_percentage: number;
  status: "ok" | "warning" | "full" | "obstructed" | "error";
  calibration?: {
    empty_cm: number;
    full_cm: number;
    confident: boolean;
    sample_count?: number;
  };
  quality?: { samples?: number; spread_cm?: number; rejected?: number };
  fill_rate_cm_per_hr?: number;
  connectivity_status?: "online" | "offline" | "stale";
  buffered?: boolean;
  firmware_version?: string;
}

export interface Decision {
  decision_id: string;
  device_id: string;
  bin_id: string;
  timestamp: string;
  fill_percentage: number;
  confidence: number;
  action: AgentAction;
  reasoning: string;
  anomaly?: { detected: boolean; type: string; note?: string };
  predicted_full_at: string | null;
  model_version: string;

  // Added by the backend, not the agent.
  review_status: ReviewStatus;
  created_at: string;
  confirmed_at?: string;
  staff_id?: string;
  note?: string;
}

const API_URL: string = import.meta.env.VITE_API_URL ?? "";

if (!API_URL && import.meta.env.DEV) {
  console.warn(
    "VITE_API_URL is not set. Create dashboard/.env.local with e.g.\n" +
    "  VITE_API_URL=http://localhost:7071/api",
  );
}

/**
 * One place for fetch + error handling, so a failing endpoint surfaces the
 * backend's actual message instead of a generic "Failed to fetch".
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new Error(
      `Cannot reach the API at ${API_URL}. Is the backend running, and is CORS configured?`,
    );
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.details ? body.details.join("; ") : (body.error ?? detail);
    } catch {
      /* non-JSON error body -- keep the status text */
    }
    throw new Error(`${path} failed (${res.status}): ${detail}`);
  }

  return res.json() as Promise<T>;
}

/** Fleet summary — one entry per bin with its latest reading + recommendation. */
export function fetchBins(): Promise<Bin[]> {
  return request<Bin[]>("/bins");
}

/** Reading history for one bin, newest first. */
export async function fetchHistory(
  binId: string,
  limit = 20,
): Promise<Reading[]> {
  const data = await request<{ readings: Reading[] }>(
    `/bins/${encodeURIComponent(binId)}/readings?limit=${limit}`,
  );
  return data.readings ?? [];
}

/** The decision log. Pass a binId to scope it to one bin. */
export function fetchDecisions(binId?: string, limit = 50): Promise<Decision[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (binId) params.set("bin_id", binId);
  return request<Decision[]>(`/decisions?${params}`);
}

/**
 * Record a human approving or rejecting a recommendation.
 * This is the human-in-the-loop step -- the agent never acts on its own.
 */
export function postDecision(input: {
  bin_id: string;
  decision_id: string;
  review_status: "approved" | "rejected";
  staff_id?: string;
  note?: string;
}): Promise<Decision> {
  return request<Decision>("/decisions", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/** Rename a bin. The only manual setup step in the product. */
export function renameBin(binId: string, location: string): Promise<{ bin_id: string; location: string }> {
  return request(`/bins/${encodeURIComponent(binId)}`, {
    method: "PATCH",
    body: JSON.stringify({ location }),
  });
}