"""
Citizen Services & Feedback Scorer

Targets powered for dashboard:
- T1: Forecast request volume next 7/30 days (district × service_type)
- T2: SLA breach probability (per incoming pattern → aggregated as expected breach rate)
- T3: Expected satisfaction next period (district × service_type)
- T4: Backlog clearance ETA (days), district-wise

Outputs:
- csf_forecasts.json: per district × service_type with forecasts and KPIs
- csf_dashboard_metrics.json: district aggregates for dashboard tiles and alerts
"""

from __future__ import annotations

import os
import json
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
	from google.cloud import bigquery, storage
except Exception:
	bigquery = None
	storage = None

DEFAULT_PROJECT_ID = os.getenv("PROJECT_ID") or "artful-affinity-476513-t7"
DEFAULT_DATASET = os.getenv("BQ_DATASET") or "complete_db"


# -----------------------------
# Helpers
# -----------------------------
def _to_dt(s):
	return pd.to_datetime(s, errors="coerce")


def _minmax(x: pd.Series) -> pd.Series:
	x = pd.to_numeric(x, errors="coerce")
	lo, hi = x.min(skipna=True), x.max(skipna=True)
	if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
		return pd.Series(np.zeros(len(x)), index=x.index)
	return (x - lo) / (hi - lo)


def load_tables(project_id: str = DEFAULT_PROJECT_ID, dataset: str = DEFAULT_DATASET) -> Dict[str, pd.DataFrame]:
	if bigquery is None:
		raise RuntimeError("google-cloud-bigquery not installed.")
	client = bigquery.Client(project=project_id)

	def q(name: str):
		sql = f"SELECT * FROM `{project_id}.{dataset}.{name}`"
		return client.query(sql).to_dataframe()

	tables = {
		"svc": q("ai_governance_citizen_services_requests"),
		"pop": q("ai_governance_population_demographics"),
		"env": q("ai_governance_environment_monitoring"),
		"bud": q("ai_governance_department_budgets"),
	}

	# Optional infra linkage for spikes in Road Repair
	try:
		tables["roads"] = q("ai_governance_infrastructure_roads")
	except Exception:
		tables["roads"] = pd.DataFrame()
	return tables


# -----------------------------
# Daily panel (district × day × service_type)
# -----------------------------
def build_daily_panel(t: Dict[str, pd.DataFrame], as_of: Optional[pd.Timestamp] = None) -> pd.DataFrame:
	as_of = _to_dt(as_of) if as_of is not None else pd.Timestamp.today().normalize()
	svc = t["svc"].copy()
	if svc.empty:
		return pd.DataFrame()

	# Ensure essential columns
	for c in ["response_time_hours", "satisfaction_score"]:
		if c in svc.columns:
			svc[c] = pd.to_numeric(svc[c], errors="coerce")

	# Dates
	req_col = None
	for c in ["request_date", "created_at", "date"]:
		if c in svc.columns:
			req_col = c
			break
	res_col = "resolution_date" if "resolution_date" in svc.columns else None
	if req_col is None:
		raise ValueError("ai_governance_citizen_services_requests must have a request_date-like column")
	svc[req_col] = _to_dt(svc[req_col]).dt.tz_localize(None)
	if res_col:
		svc[res_col] = _to_dt(svc[res_col]).dt.tz_localize(None)

	svc = svc[svc[req_col] <= as_of]

	# SLA label per row (default 72h; can be refined per service_type later)
	SLA_HOURS_DEFAULT = 72.0
	svc["sla_hours"] = SLA_HOURS_DEFAULT
	if "service_type" in svc.columns:
		# Example custom SLA overrides (adjust as needed)
		st = svc["service_type"].astype(str).str.strip().str.lower()
		svc.loc[st.str.contains("drainage|road repair", na=False), "sla_hours"] = 120.0
	if "response_time_hours" in svc.columns:
		svc["sla_breach"] = (svc["response_time_hours"] > svc["sla_hours"]).astype(float)
	else:
		svc["sla_breach"] = np.nan

	# Buckets: district × day × service_type
	svc["req_day"] = svc[req_col].dt.floor("D")
	keys = [c for c in ["district", "service_type", "req_day"] if c in svc.columns]
	if not set(["district", "req_day"]).issubset(set(keys)):
		raise ValueError("citizen services table missing required columns: district and request_date")

	# Arrivals per day
	arrivals = (
		svc.groupby(keys).agg(
			req_count=("request_id" if "request_id" in svc.columns else req_col, "count"),
			avg_sat=("satisfaction_score", "mean"),
			med_resp_h=("response_time_hours", "median"),
			sla_breach_rate=("sla_breach", "mean"),
		).reset_index()
	)

	# Resolved per day (use resolution_date)
	if res_col:
		svc["res_day"] = svc[res_col].dt.floor("D")
		resolved = (
			svc.dropna(subset=["res_day"]).groupby([c for c in keys if c != "req_day"] + ["res_day"]).size().rename("resolved_count").reset_index()
		)
		resolved = resolved.rename(columns={"res_day": "req_day"})
	else:
		resolved = pd.DataFrame(columns=keys + ["resolved_count"])  # fallback

	# Combine
	panel = arrivals.merge(resolved, on=keys, how="left").fillna({"resolved_count": 0})

	# Fill missing service_type as "All" if absent
	if "service_type" not in panel.columns:
		panel["service_type"] = "All"

	# Build continuous daily index per district × service_type
	full_idx = (
		panel.groupby(["district", "service_type"])  
			  .apply(lambda g: pd.DataFrame({
				  "req_day": pd.date_range(g["req_day"].min(), as_of, freq="D")
			  }))
			  .reset_index(level=[0,1])
	)
	full_idx = full_idx.rename(columns={0: "_"})
	panel = full_idx.merge(panel, on=["district", "service_type", "req_day"], how="left")
	for c in ["req_count", "resolved_count"]:
		panel[c] = pd.to_numeric(panel.get(c), errors="coerce").fillna(0)
	for c in ["avg_sat", "med_resp_h", "sla_breach_rate"]:
		panel[c] = pd.to_numeric(panel.get(c), errors="coerce")

	# Open queue end-of-day
	panel = panel.sort_values(["district", "service_type", "req_day"]).reset_index(drop=True)
	panel["cum_arrivals"] = panel.groupby(["district", "service_type"])['req_count'].cumsum()
	panel["cum_resolved"] = panel.groupby(["district", "service_type"])['resolved_count'].cumsum()
	panel["open_eod"] = (panel["cum_arrivals"] - panel["cum_resolved"]).clip(lower=0)

	# Moving features
	for w in [7, 14, 28]:
		panel[f"req_count_{w}d_ma"] = panel.groupby(["district", "service_type"])['req_count'].transform(lambda s: s.rolling(w, min_periods=1).mean())
	# WoW change: compare last 7d vs previous 7d
	panel["req_sum_7d"] = panel.groupby(["district", "service_type"])['req_count'].transform(lambda s: s.rolling(7, min_periods=1).sum())
	panel["req_sum_prev7"] = panel.groupby(["district", "service_type"])['req_count'].transform(lambda s: s.shift(7).rolling(7, min_periods=1).sum())
	panel["wow_change_pct"] = np.where(panel["req_sum_prev7"].fillna(0) > 0, (panel["req_sum_7d"] - panel["req_sum_prev7"]) / panel["req_sum_prev7"], 0.0)

	# Rolling satisfaction and resolution time
	panel["avg_sat_7d"] = panel.groupby(["district", "service_type"])['avg_sat'].transform(lambda s: s.rolling(7, min_periods=1).mean())
	panel["med_resp_h_7d"] = panel.groupby(["district", "service_type"])['med_resp_h'].transform(lambda s: s.rolling(7, min_periods=1).median())
	panel["sla_breach_rate_28d"] = panel.groupby(["district", "service_type"])['sla_breach_rate'].transform(lambda s: s.rolling(28, min_periods=1).mean())

	return panel


# -----------------------------
# Forecasts and KPIs
# -----------------------------
def compute_forecasts(panel: pd.DataFrame, as_of: Optional[pd.Timestamp] = None) -> pd.DataFrame:
	if panel.empty:
		return pd.DataFrame()
	# Take last available day per district × service_type
	last_rows = panel.sort_values("req_day").groupby(["district", "service_type"]).tail(1).copy()

	# T1: Forecast volume next 7d/30d using moving averages + WoW trend
	last_rows["forecast_next_7d"] = (7.0 * last_rows["req_count_7d_ma"] * (1.0 + 0.5 * last_rows["wow_change_pct"]).clip(lower=0.5, upper=1.5)).fillna(0)
	last_rows["forecast_next_30d"] = (30.0 * last_rows["req_count_28d_ma"]).fillna(0)

	# T2: Expected SLA breach rate (proxy): recent 28d average
	last_rows["expected_sla_breach_rate"] = (100.0 * last_rows["sla_breach_rate_28d"].clip(0, 1)).fillna(0)

	# T3: Expected satisfaction: recent 7d average, bound [0,10]
	last_rows["expected_satisfaction_next_7d"] = last_rows["avg_sat_7d"].clip(lower=0, upper=10).fillna(0)

	# T4: Backlog clearance ETA = open_eod / avg_daily_resolve_7d
	# Approximate resolve rate 7d as median of resolved_count (robust to spikes)
	# If not available, fallback to req_count_7d_ma × (1 - sla_breach_rate)
	# We need resolved_count_7d_ma from panel; compute group-wise last 7d median resolved
	# Since we only have last_rows, approximate with req_count_7d_ma and breach rate
	eff_resolve_rate = (last_rows["req_count_7d_ma"] * (1.0 - last_rows["sla_breach_rate_28d"].fillna(0))).clip(lower=0.01)
	last_rows["backlog_eta_days"] = (last_rows["open_eod"] / eff_resolve_rate).replace([np.inf, -np.inf], np.nan).clip(lower=0).fillna(0)

	# Convenience: forecast requests per day (next 7d)
	last_rows["forecast_per_day_next_7"] = (last_rows["forecast_next_7d"] / 7.0).round(2)

	keep = [
		"district", "service_type", "req_day", "req_count_7d_ma", "wow_change_pct", "open_eod",
		"forecast_per_day_next_7", "forecast_next_7d", "forecast_next_30d",
		"expected_sla_breach_rate", "expected_satisfaction_next_7d", "backlog_eta_days"
	]
	return last_rows[keep].copy()


def dashboard_aggregates(per_group: pd.DataFrame) -> Dict[str, dict]:
	if per_group.empty:
		return {}
	out: Dict[str, dict] = {}
	g = per_group.groupby("district")
	for district, df in g:
		vol_per_day = float(np.nansum(df["forecast_per_day_next_7"]))  # sum across services
		sla_breach_pct = float(np.nanmean(df["expected_sla_breach_rate"]))
		sat = float(np.nanmean(df["expected_satisfaction_next_7d"]))
		open_total = float(np.nansum(df["open_eod"]))
		# Backlog ETA at district: weighted by open tickets
		if df["open_eod"].sum() > 0:
			eta = float(np.nansum(df["backlog_eta_days"] * df["open_eod"]) / np.nansum(df["open_eod"]))
		else:
			eta = float(np.nanmean(df["backlog_eta_days"]))

		# Simple spike alert: max service-type WoW change
		top = df.sort_values("wow_change_pct", ascending=False).head(1)
		alert_line = "—"
		if not top.empty and np.isfinite(top.iloc[0].get("wow_change_pct", np.nan)):
			svc = str(top.iloc[0].get("service_type", "All"))
			pct = int(round(100 * top.iloc[0].get("wow_change_pct", 0)))
			if pct >= 15:
				alert_line = f"Spike likely in {district} ({svc}): +{pct}% volume"
			else:
				alert_line = f"Stable demand in {district} ({svc})"

		out[district] = {
			"metrics": [
				round(vol_per_day, 1),       # Request Volume (per day forecast)
				round(eta, 1),               # Backlog ETA (days)
				round(sat, 1),               # Expected Satisfaction (0–10)
				round(sla_breach_pct, 1),    # Expected SLA Breach Rate (%)
			],
			"pending": int(round(open_total)),
			"alert": {
				"title": "Citizen Services",
				"description": alert_line,
			},
		}
	return out


def _upload_to_gcs(bucket_name: str, source_file_name: str, destination_blob_name: str):
	"""Uploads a file to the bucket."""
	if storage is None:
		print(f"GCS client not available. Cannot upload {source_file_name}")
		return
	storage_client = storage.Client()
	bucket = storage_client.bucket(bucket_name)
	blob = bucket.blob(destination_blob_name)
	blob.upload_from_filename(source_file_name)
	print(f"File {source_file_name} uploaded to {destination_blob_name}.")


def score_and_export(
	project_id: str = DEFAULT_PROJECT_ID,
	dataset: str = DEFAULT_DATASET,
	as_of: Optional[str | pd.Timestamp] = None,
	output_dir: str = ".",
	bucket_name: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, dict]]:
	tables = load_tables(project_id, dataset)
	panel = build_daily_panel(tables, as_of)
	forecasts = compute_forecasts(panel, as_of)
	# Export per district × service_type
	per_path = os.path.join(output_dir, "csf_forecasts.json")
	forecasts.to_json(per_path, orient="records")
	# Aggregates per district
	agg = dashboard_aggregates(forecasts)
	agg_path = os.path.join(output_dir, "csf_dashboard_metrics.json")
	with open(agg_path, "w") as f:
		json.dump(agg, f, indent=2)

	if bucket_name:
		_upload_to_gcs(bucket_name, per_path, "csf_forecasts.json")
		_upload_to_gcs(bucket_name, agg_path, "csf_dashboard_metrics.json")

	return forecasts, agg


if __name__ == "__main__":
	as_of = os.getenv("AS_OF_DATE")  # e.g., 2025-11-01
	df, agg = score_and_export(DEFAULT_PROJECT_ID, DEFAULT_DATASET, as_of, ".")
	print(f"Scored {len(df)} district×service entries. Wrote csf_forecasts.json and csf_dashboard_metrics.json")

