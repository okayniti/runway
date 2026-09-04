import type { CalibrationReport, ForecastOutput, TrackRecordStats, TransactionRecord } from "@/lib/types";

export class ApiError extends Error {}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      // FastAPI/Pydantic validation errors: a list of {loc, msg, ...}
      return body.detail.map((e: { msg?: string }) => e.msg).join("; ");
    }
  } catch {
    // fall through to the generic message below
  }
  return `Request failed with status ${response.status}.`;
}

/** Every call in this file goes through this same relative path -- there
 * is no env var (NEXT_PUBLIC_ or otherwise) involved in constructing the
 * URL on the client at all. The actual backend address lives entirely in
 * next.config.ts's server-side rewrite (BACKEND_URL), which proxies
 * `/api/backend/*` to the real API before it ever reaches this code; the
 * browser only ever sees a same-origin request to the path below. If that
 * proxy is misconfigured (BACKEND_URL missing or unreachable), you still
 * get a real request and a real error status here -- Next.js's rewrite
 * returns its own failure response rather than the request silently never
 * firing. logFailedRequest exists so that failure is loud and specific in
 * the browser console instead of only the generic message the UI shows. */
function logFailedRequest(path: string, error: unknown): void {
  console.error(`[runway] request to "${path}" failed:`, error);
}

export async function runForecast(
  transactions: TransactionRecord[],
  shortfallThreshold: number
): Promise<ForecastOutput> {
  const path = "/api/backend/forecast";
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transactions, shortfall_threshold: shortfallThreshold }),
    });
  } catch (error) {
    // fetch() itself only throws for something before a response exists at
    // all -- a network error, a blocked request, this same-origin path
    // somehow not resolving. A non-2xx response (the far more likely
    // failure mode here -- see the comment above) does NOT land here; it's
    // handled below instead, same as before.
    logFailedRequest(path, error);
    throw error;
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    logFailedRequest(path, `HTTP ${response.status}: ${detail}`);
    throw new ApiError(detail);
  }

  return response.json();
}

export async function fetchCalibration(): Promise<CalibrationReport> {
  const path = "/api/backend/calibration";
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    logFailedRequest(path, `HTTP ${response.status}: ${detail}`);
    throw new ApiError(detail);
  }
  return response.json();
}

export async function fetchStats(): Promise<TrackRecordStats> {
  const path = "/api/backend/stats";
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    logFailedRequest(path, `HTTP ${response.status}: ${detail}`);
    throw new ApiError(detail);
  }
  return response.json();
}
