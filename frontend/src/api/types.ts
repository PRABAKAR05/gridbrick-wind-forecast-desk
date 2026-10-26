/** Wire types mirroring the FastAPI schemas. Kept hand-written so the frontend
 *  has no build-time coupling to the backend process. */

export interface Band {
  p10: number;
  p25: number;
  p50: number | null;
  p75: number;
  p90: number;
  source: string | null;
}

export interface DecisionHour {
  hour: number;
  start_utc: string;
  forecast_mw: number | null;
  calibrated_mw: number | null;
  actual_mw: number | null;
  residual_mw: number | null;
  raw_residual_mw: number | null;
  lead_hours: number | null;
  band: Band | null;
}

export interface CalibrationFit {
  slope: number;
  intercept_mw: number;
  samples: number;
  r2: number;
  method: string;
}

export interface BandInfo {
  available: boolean;
  reason?: string;
  usable_days: number;
  lookback_days: number;
  samples?: number;
  median_lead_hours?: number;
  p10_offset_mw?: number;
  p90_offset_mw?: number;
  p80_width_mw?: number;
  capacity_note?: string;
}

export interface DecisionSummary {
  realised: boolean;
  hours_with_forecast: number;
  hours_with_actual: number;
  calibration: CalibrationFit;
  wind_forecast_mwh: number | null;
  wind_forecast_mean_mw: number | null;
  wind_forecast_min_mw: number | null;
  wind_forecast_max_mw: number | null;
  wind_calibrated_mwh: number | null;
  wind_calibrated_mean_mw: number | null;
  wind_nominated_mwh: number | null;
  nomination_uplift_mwh: number | null;
  wind_p10_mwh: number | null;
  wind_p90_mwh: number | null;
  downside_p90_mwh: number | null;
  upside_p90_mwh: number | null;
  band: BandInfo;
  policy: { critical_fractile: number; c_short: number; c_long: number; confidence_pct: number };
  expected_shortfall_mwh: number | null;
  expected_surplus_mwh: number | null;
  prob_short: number | null;
  hours_in_risk_calc: number;
  wind_actual_mwh?: number;
  wind_actual_mean_mw?: number;
  mae_mw?: number;
  bias_mw?: number;
  rmse_mw?: number;
  energy_error_mwh?: number;
  raw_mae_mw?: number | null;
  raw_bias_mw?: number | null;
  within_p10_p90?: number;
  utilisation_pct?: number;
}

export interface Decision {
  delivery_date: string;
  cutoff_utc: string;
  as_of_utc: string;
  vintage: {
    available: boolean;
    publish_time_utc: string | null;
    age_hours: number | null;
    horizon_hours: number | null;
    note: string;
  };
  summary: DecisionSummary;
  hours: DecisionHour[];
  delivery_hours: { hour: number; start_utc: string }[];
}

export interface VintageSeries {
  publish_time_utc: string;
  age_hours: number;
  mean_mw: number;
  values: (number | null)[];
}

export interface VintageEvolution {
  delivery_date: string;
  cutoff_utc: string;
  hours: { hour: number; start_utc: string }[];
  vintages: VintageSeries[];
  selected_vintage_utc: string | null;
  actual_mw: (number | null)[] | null;
  total_vintages_available: number;
}

export interface DayStatus {
  delivery_date: string;
  cutoff_utc: string;
  status: "pending_gate" | "awaiting_outturn" | "partial" | "realised";
  vintage_publish_utc: string | null;
  vintage_age_hours: number | null;
  hours_realised: number;
  mae_mw: number | null;
  bias_mw: number | null;
  forecast_mwh: number | null;
}

export interface DeliveryDays {
  as_of_utc: string;
  days: DayStatus[];
}

export interface ErrorSummary {
  n: number;
  mae_mw: number;
  rmse_mw: number;
  bias_mw: number;
  mape_pct: number | null;
  nrmse_pct_of_capacity: number | null;
  nrmse_pct_of_mean_actual: number | null;
  r2: number;
  correlation: number;
  mean_forecast_mw: number;
  mean_actual_mw: number;
  p90_abs_error_mw: number;
  max_abs_error_mw: number;
}

export interface CalibrationRow {
  nominal: number;
  observed: number | null;
  raw_observed: number | null;
  gap: number | null;
  samples: number;
}

export interface AccuracyReport {
  as_of: string;
  window: { start: string | null; end: string | null; days: number; hours_evaluated: number };
  headline: ErrorSummary;
  raw: ErrorSummary;
  calibrated: ErrorSummary;
  calibration: {
    walk_forward: {
      scored_days: number;
      inflation: number;
      table: CalibrationRow[];
      pinball_loss: { p10: number | null; p90: number | null };
      mean_abs_gap: number | null;
    };
    fit_history: ({ delivery_date: string } & CalibrationFit)[];
    current: CalibrationFit;
    method: string;
  };
  by_horizon: {
    lead_hours: number;
    lead_label: string;
    n: number;
    mae_mw: number;
    rmse_mw: number;
    bias_mw: number;
    mape_pct: number | null;
  }[];
  by_hour: {
    hour: number;
    label: string;
    n: number;
    mae_mw: number;
    bias_mw: number;
    calibrated_mae_mw: number;
    mean_actual_mw: number;
    mean_forecast_mw: number;
  }[];
  by_day: {
    delivery_date: string;
    n: number;
    mae_mw: number | null;
    bias_mw: number | null;
    rmse_mw: number | null;
    raw_mae_mw: number | null;
    raw_bias_mw: number | null;
    abs_energy_mwh: number | null;
    bias_energy_mwh: number | null;
    coverage_p80: number | null;
  }[];
  benchmarks: {
    name: string;
    mae_mw: number;
    rmse_mw: number;
    bias_mw: number;
    n: number;
    skill: number | null;
    note: string;
    kind: "model" | "calibrated" | "baseline";
  }[];
  distribution: {
    bin_start: number[];
    bin_end: number[];
    count: number[];
    quantiles: Record<string, number>;
    raw_quantiles: Record<string, number>;
  };
  matrix: { delivery_date: string; residuals: (number | null)[] }[];
  scatter: { forecast: number; calibrated: number | null; actual: number }[];
}

export interface Exactions {
  expected_shortfall_mw: number | null;
  expected_surplus_mw: number | null;
  prob_short: number | null;
  offset_mw: number | null;
}

export interface PlanHour {
  hour: number;
  start_utc: string;
  demand_mw: number | null;
  wind_forecast_mw: number | null;
  wind_raw_mw: number | null;
  wind_nominated_mw: number | null;
  wind_p10_mw: number | null;
  wind_p90_mw: number | null;
  thermal_baseline_mw: number | null;
  thermal_procured_mw: number | null;
  uplift_mw: number | null;
  exposure: Exactions | null;
}

export interface ProcurementPlan {
  delivery_date: string;
  cutoff_utc: string;
  as_of_utc: string;
  profile: {
    id: string;
    label: string;
    synthetic: boolean;
    description: string;
    peak_mw?: number;
    trough_mw?: number;
    flat_mw?: number;
  };
  policy: {
    critical_fractile: number;
    confidence_pct: number;
    c_short: number;
    c_long: number;
    short_long_ratio: number;
    rule: string;
  };
  totals: {
    demand_mwh: number | null;
    wind_forecast_mwh: number;
    wind_nominated_mwh: number;
    thermal_baseline_mwh: number | null;
    thermal_procured_mwh: number | null;
    risk_uplift_mwh: number | null;
    expected_shortfall_mwh: number | null;
    hours_covered: number;
  };
  hours: PlanHour[];
  forecast: {
    vintage: Decision["vintage"];
    summary: DecisionSummary;
  };
}

export interface DemandProfile {
  id: string;
  label: string;
  synthetic: boolean;
  description: string;
}

export interface Meta {
  app: string;
  version: string;
  environment: string;
  pilot: { start: string; end: string; days: number; note: string };
  data: {
    actual_start_utc: string | null;
    actual_end_utc: string | null;
    forecast_publish_start_utc: string | null;
    forecast_publish_end_utc: string | null;
    latest_observable_utc: string | null;
    actuals: number;
    forecast_points: number;
    vintages: number;
    capacity_mw: number;
  };
  defaults: {
    cutoff_hour: number;
    cutoff_minute: number;
    band_lookback_days: number;
    band_min_days: number;
    c_short: number;
    c_long: number;
  };
  demand_profiles: DemandProfile[];
  ingestion_runs: {
    started_at: string;
    finished_at: string | null;
    status: string;
    trigger: string;
    actuals_upserted: number;
    forecasts_upserted: number;
    message: string | null;
  }[];
}
