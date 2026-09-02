// Mirrors agent/schema.py exactly. Keep in sync by hand -- there's no
// shared schema generation between the Python backend and this frontend,
// so a field added on one side needs to be added here too.

export interface ConfidenceInfo {
  score: number;
  is_low_confidence: boolean;
  reasons: string[];
}

export interface ContributingLineItem {
  date: string;
  type: "inflow" | "outflow";
  category: string;
  amount: number;
  note: string;
  basis: "recurring_projection" | "historical_outlier";
}

export interface Recommendation {
  rank: number;
  action: "delay_payment" | "accelerate_collection";
  description: string;
  reference_date: string;
  reference_category: string;
  reference_amount: number;
  suggested_shift_days: number;
  projected_shortfall_relief: number;
  projected_new_minimum: number;
}

export interface ForecastOutput {
  forecast: number[];
  confidence: ConfidenceInfo;
  risk_flag: boolean;
  risk_reason: string | null;
  contributing_line_items: ContributingLineItem[];
  recommendations: Recommendation[];
}

export interface TransactionRecord {
  date: string;
  type: "inflow" | "outflow";
  category: string;
  amount: number;
  invoice_date: string | null;
  note: string | null;
}

export interface CalibrationBucket {
  label: "low_confidence" | "high_confidence";
  num_runs: number;
  mean_confidence_score: number | null;
  mean_error_rmse: number | null;
  mean_error_mae: number | null;
}

export interface CalibrationReport {
  tenant_id: string;
  total_runs_with_known_outcome: number;
  buckets: CalibrationBucket[];
  is_well_calibrated: boolean | null;
  summary: string;
}
