import type { CalibrationReport, ForecastOutput, TransactionRecord } from "@/lib/types";

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

export async function runForecast(
  transactions: TransactionRecord[],
  shortfallThreshold: number
): Promise<ForecastOutput> {
  const response = await fetch("/api/backend/forecast", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions, shortfall_threshold: shortfallThreshold }),
  });

  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response));
  }

  return response.json();
}

export async function fetchCalibration(): Promise<CalibrationReport> {
  const response = await fetch("/api/backend/calibration", { cache: "no-store" });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response));
  }
  return response.json();
}
