"""
Public Safety Scorer

Outputs per station/district for dashboard Safety tab:
- crime_risk_0_100
- response_efficiency_pct
- resolution_rate_pct
- hotspot flag and alert lines

Data sources (BigQuery; defaults to dataset 'complete_db'):
- ai_governance_public_safety_reports
  station_id, district, crime_reports(JSON), complaints_logged, avg_response_time_minutes,
  resolved_cases_percentage, priority_cases_count, last_updated

- ai_governance_population_demographics
  district, total_population (alias: population_total)

- ai_governance_environment_monitoring
  district, air_quality_index, noise_level_db (proxy), last_inspection_date

- ai_governance_department_budgets
  district, financial_year, total_budget_allocated_cr, budget_utilized_cr, last_updated

Optional
- ai_governance_citizen_services_requests (service_type='Public Safety') for demand pressure
"""

from __future__ import annotations

import os
import json
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from google.cloud import storage

try:
	from google.cloud import bigquery
except Exception:
	bigquery = None

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


def parse_crime_reports(value) -> Dict[str, int]:
	if pd.isna(value):
		return {}
	parsed = None
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
		except Exception:
			return {}
	elif isinstance(value, dict):
		parsed = [value]
	else:
		parsed = value
	if not isinstance(parsed, (list, tuple)):
		return {}
	counts = {}
	for item in parsed:
		if not isinstance(item, dict):
			continue
		t = item.get("type")
		c = item.get("count", 1)
		try:
			c = int(float(c))
		except Exception:
			c = 0
		if t and c:
			counts[t] = counts.get(t, 0) + c
	return counts


# -----------------------------
# Load tables
# -----------------------------
def load_tables(project_id: str = DEFAULT_PROJECT_ID, dataset: str = DEFAULT_DATASET) -> Dict[str, pd.DataFrame]:
	if bigquery is None:
		raise RuntimeError("google-cloud-bigquery not installed.")
	client = bigquery.Client(project=project_id)

	def q(name: str):
		sql = f"SELECT * FROM `{project_id}.{dataset}.{name}`"
		return client.query(sql).to_dataframe()

	tables = {
		"safety": q("ai_governance_public_safety_reports"),
		"pop": q("ai_governance_population_demographics"),
		"env": q("ai_governance_environment_monitoring"),
		"bud": q("ai_governance_department_budgets"),
	}

	# Optional: citizen services for public safety
	try:
		tables["svc"] = q("ai_governance_citizen_services_requests")
	except Exception:
		tables["svc"] = pd.DataFrame()

	return tables


# -----------------------------
# Feature engineering
# -----------------------------
def build_features(t: Dict[str, pd.DataFrame], as_of: Optional[pd.Timestamp] = None) -> pd.DataFrame:
	as_of = _to_dt(as_of) if as_of is not None else pd.Timestamp.today().normalize()
	safety = t["safety"].copy()
	if safety.empty:
		return pd.DataFrame()

	# Coerce types
	for c in [
		"complaints_logged",
		"avg_response_time_minutes",
		"resolved_cases_percentage",
		"priority_cases_count",
	]:
		if c in safety.columns:
			safety[c] = pd.to_numeric(safety[c], errors="coerce")

	date_col = None
	for c in ["last_updated", "report_date", "date"]:
		if c in safety.columns:
			date_col = c
			break
	if date_col:
		safety[date_col] = _to_dt(safety[date_col]).dt.tz_localize(None)
		safety = safety[safety[date_col] <= as_of]

	# Crime JSON -> counts per type, plus total
	if "crime_reports" in safety.columns:
		counts = safety["crime_reports"].apply(parse_crime_reports)
		long_rows = []
		for i, cc in counts.items():
			for k, v in cc.items():
				long_rows.append({"idx": i, "crime_type": k, "count": v})
		if long_rows:
			long_df = pd.DataFrame(long_rows)
			wide = long_df.pivot_table(index="idx", columns="crime_type", values="count", aggfunc="sum", fill_value=0)
			safety = safety.join(wide, how="left")
			safety["crime_count_total"] = wide.sum(axis=1)
		else:
			safety["crime_count_total"] = np.nan
	else:
		safety["crime_count_total"] = np.nan

	# Population per district
	pop = t["pop"].copy()
	if not pop.empty:
		pop_col = "total_population" if "total_population" in pop.columns else ("population_total" if "population_total" in pop.columns else None)
		if pop_col is None and "Population" in pop.columns:
			pop_col = "Population"
		if pop_col:
			pop[pop_col] = pd.to_numeric(pop[pop_col], errors="coerce")
			pop = pop[["district", pop_col]].rename(columns={pop_col: "total_population"}).dropna()
		else:
			pop = pd.DataFrame(columns=["district", "total_population"])
	else:
		pop = pd.DataFrame(columns=["district", "total_population"])

	# Environment stress (AQI + noise)
	env = t["env"].copy()
	env_stress = pd.DataFrame(columns=["district", "env_stress"])  # default
	if not env.empty:
		dtc = None
		for c in ["last_updated", "last_inspection_date", "date"]:
			if c in env.columns:
				dtc = c
				break
		if dtc:
			env[dtc] = _to_dt(env[dtc]).dt.tz_localize(None)
			env = env[env[dtc] <= as_of]
		# Build stress index from AQI and noise
		aqi = pd.to_numeric(env.get("air_quality_index"), errors="coerce")
		noise = pd.to_numeric(env.get("noise_level_db"), errors="coerce")
		env["aqi_norm"] = _minmax(aqi) if aqi is not None else 0
		env["noise_norm"] = _minmax(noise) if noise is not None else 0
		env["env_stress"] = 0.8 * env["aqi_norm"].fillna(0) + 0.2 * env["noise_norm"].fillna(0)
		env_stress = env.groupby("district")["env_stress"].mean().reset_index()

	# Budgets: utilization ratio latest per district
	bud = t["bud"].copy()
	bud_latest = pd.DataFrame(columns=["district", "budget_utilization_ratio"])  # default
	if not bud.empty:
		if "last_updated" in bud.columns:
			bud["last_updated_dt"] = _to_dt(bud["last_updated"]).dt.tz_localize(None)
		fy = "financial_year" if "financial_year" in bud.columns else None
		def _fy_end(v):
			try:
				s = str(v)
				yrs = [int(x) for x in __import__("re").findall(r"(\d{4})", s)]
				return max(yrs) if yrs else np.nan
			except Exception:
				return np.nan
		if fy:
			bud["fy_num"] = pd.to_numeric(bud[fy], errors="coerce")
			if bud["fy_num"].isna().all():
				bud["fy_num"] = bud[fy].apply(_fy_end)
			if bud["fy_num"].isna().all() and "last_updated_dt" in bud.columns:
				bud = bud.sort_values(["district", "last_updated_dt"]).copy()
			else:
				bud = bud.sort_values(["district", "fy_num"]).copy()
		elif "last_updated_dt" in bud.columns:
			bud = bud.sort_values(["district", "last_updated_dt"]).copy()
		latest = bud.groupby("district").tail(1)
		for c in ["budget_utilized_cr", "total_budget_allocated_cr"]:
			if c in latest.columns:
				latest[c] = pd.to_numeric(latest[c], errors="coerce")
		if {"budget_utilized_cr", "total_budget_allocated_cr"}.issubset(latest.columns):
			latest["budget_utilization_ratio"] = latest["budget_utilized_cr"] / latest["total_budget_allocated_cr"].replace(0, np.nan)
		bud_latest = latest[[c for c in ["district", "budget_utilization_ratio"] if c in latest.columns]].copy()

	# Citizen services (Public Safety) demand pressure last 60d
	svc = t.get("svc", pd.DataFrame()).copy()
	svc_pressure = pd.DataFrame(columns=["district", "svc_public_safety_60d"])
	if not svc.empty:
		if "service_type" in svc.columns:
			svc["service_type_norm"] = svc["service_type"].astype(str).str.strip().str.lower()
			svc = svc[svc["service_type_norm"] == "public safety"]
		dcol = None
		for c in ["request_date", "last_updated", "date"]:
			if c in svc.columns:
				dcol = c
				break
		if dcol:
			svc[dcol] = _to_dt(svc[dcol]).dt.tz_localize(None)
			start = as_of - pd.Timedelta(days=60)
			svc = svc[(svc[dcol] <= as_of) & (svc[dcol] >= start)]
		if "district" in svc.columns:
			svc_pressure = svc.groupby("district").size().rename("svc_public_safety_60d").reset_index()

	# Join enrichments to station-level rows
	feat = safety.merge(pop, on="district", how="left") \
				 .merge(env_stress, on="district", how="left") \
				 .merge(bud_latest, on="district", how="left") \
				 .merge(svc_pressure, on="district", how="left")

	# Derived features
	feat["total_population"] = pd.to_numeric(feat.get("total_population"), errors="coerce")
	feat["complaints_logged"] = pd.to_numeric(feat.get("complaints_logged"), errors="coerce")
	feat["priority_cases_count"] = pd.to_numeric(feat.get("priority_cases_count"), errors="coerce").fillna(0)
	feat["per_capita_crime"] = np.where(feat["total_population"].fillna(0) > 0, feat["complaints_logged"] / feat["total_population"], np.nan)
	feat["demand_norm"] = _minmax(pd.to_numeric(feat.get("svc_public_safety_60d"), errors="coerce"))
	feat["env_norm"] = _minmax(pd.to_numeric(feat.get("env_stress"), errors="coerce"))
	feat["prio_norm"] = _minmax(pd.to_numeric(feat.get("priority_cases_count"), errors="coerce"))
	feat["crime_pc_norm"] = _minmax(feat["per_capita_crime"]) if "per_capita_crime" in feat.columns else 0

	# Scores
	# Crime risk (0–100): blend of per-capita crime, priority cases, env stress, demand pressure
	crime_risk = (
		0.5 * feat["crime_pc_norm"].fillna(0) +
		0.25 * feat["prio_norm"].fillna(0) +
		0.15 * feat["env_norm"].fillna(0) +
		0.10 * feat["demand_norm"].fillna(0)
	)
	feat["crime_risk_0_100"] = (100 * crime_risk).clip(0, 100)

	# Response efficiency: prefer resolved_cases_percentage; else invert normalized response time
	if "resolved_cases_percentage" in feat.columns:
		feat["resolution_rate_pct"] = pd.to_numeric(feat["resolved_cases_percentage"], errors="coerce")
	else:
		feat["resolution_rate_pct"] = np.nan
	if "avg_response_time_minutes" in feat.columns:
		rt_norm = _minmax(pd.to_numeric(feat["avg_response_time_minutes"], errors="coerce"))
		feat["response_efficiency_pct"] = (100 * (1 - rt_norm)).clip(0, 100)
	else:
		feat["response_efficiency_pct"] = np.nan

	# Hotspot flag
	feat["is_hotspot"] = (feat["crime_risk_0_100"] >= 70) | (feat["priority_cases_count"] >= (np.nanmedian(feat["priority_cases_count"]) + 1))

	# Keep projection
	cols = [
		c for c in [
			"station_id", "district", "complaints_logged", "crime_count_total",
			"per_capita_crime", "priority_cases_count", "crime_risk_0_100",
			"response_efficiency_pct", "resolution_rate_pct", "is_hotspot"
		] if c in feat.columns
	]
	return feat[cols].copy()


# -----------------------------
# Aggregates and export
# -----------------------------
def dashboard_aggregates(per_station: pd.DataFrame) -> Dict[str, dict]:
	if per_station.empty:
		return {}
	out: Dict[str, dict] = {}
	g = per_station.groupby("district")
	for district, df in g:
		avg_risk = float(np.nanmean(df["crime_risk_0_100"]))
		avg_eff = float(np.nanmean(df.get("response_efficiency_pct", np.nan)))
		avg_res = float(np.nanmean(df.get("resolution_rate_pct", np.nan)))
		hotspot_count = int(df["is_hotspot"].fillna(False).sum())
		top = df.sort_values(["crime_risk_0_100", "priority_cases_count"], ascending=False).head(1)
		factor_line = "—"
		if not top.empty:
			sid = str(top.iloc[0].get("station_id", "Station"))
			urgency = int(round(top.iloc[0].get("crime_risk_0_100", 0)))
			factor_line = f"{sid} (Risk: {urgency}%)"
		out[district] = {
			"metrics": [
				round(avg_risk, 1),         # Crime risk (0–100)
				round(avg_eff, 1),          # Response efficiency (%)
				round(avg_res, 1),          # Resolution rate (%)
			],
			"hotspots": hotspot_count,
			"top_factor_line": factor_line,
			"alert": {
				"title": f"Safety Hotspots: {hotspot_count}",
				"description": f"Avg Risk: {avg_risk:.0f} | Response Eff.: {avg_eff:.0f}% | Resolution: {avg_res:.0f}%",
			},
		}
	return out


# def score_and_export(
# 	project_id: str = DEFAULT_PROJECT_ID,
# 	dataset: str = DEFAULT_DATASET,
# 	as_of: Optional[str | pd.Timestamp] = None,
# 	output_dir: str = ".",
# ) -> Tuple[pd.DataFrame, Dict[str, dict]]:
# 	t = load_tables(project_id, dataset)
# 	features = build_features(t, as_of)
# 	# Export per-station
# 	per_station_path = os.path.join(output_dir, "safety_scores.json")
# 	features.to_json(per_station_path, orient="records")
# 	# Aggregates
# 	agg = dashboard_aggregates(features)
# 	agg_path = os.path.join(output_dir, "safety_dashboard_metrics.json")
# 	with open(agg_path, "w") as f:
# 		json.dump(agg, f, indent=2)
# 	return features, agg


def score_and_export(
    project_id: str = DEFAULT_PROJECT_ID,
    dataset: str = DEFAULT_DATASET,
    as_of: Optional[str | pd.Timestamp] = None,
    bucket_name: str = "safety-dashboard-bucket"  # <-- Add this!
) -> Tuple[pd.DataFrame, Dict[str, dict]]:

    # --- 1. Initialize GCS Client ---
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)

    # --- 2. Load and Build (no change here) ---
    t = load_tables(project_id, dataset)
    features = build_features(t, as_of)
    agg = dashboard_aggregates(features)
    
    # --- 3. Export per-station to GCS ---
    per_station_json = features.to_json(orient="records")
    blob_station = bucket.blob("safety_scores.json")
    blob_station.upload_from_string(per_station_json, content_type="application/json")
    print(f"Wrote safety_scores.json to GCS bucket: {bucket_name}")

    # --- 4. Export aggregates to GCS ---
    agg_json = json.dumps(agg, indent=2)
    blob_agg = bucket.blob("safety_dashboard_metrics.json")
    blob_agg.upload_from_string(agg_json, content_type="application/json")
    print(f"Wrote safety_dashboard_metrics.json to GCS bucket: {bucket_name}")

    return features, agg

if __name__ == "__main__":
	as_of = os.getenv("AS_OF_DATE")  # e.g., 2025-11-01
	df, agg = score_and_export(DEFAULT_PROJECT_ID, DEFAULT_DATASET, as_of, ".")
	print(f"Scored {len(df)} stations. Wrote safety_scores.json and safety_dashboard_metrics.json")

