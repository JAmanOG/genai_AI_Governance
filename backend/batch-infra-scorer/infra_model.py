"""
Infrastructure predictions: Road Repair Probability (90d), Repair Cost Estimate, Traffic Impact Score,
and Priority Rank per road_id, with district-level aggregates for dashboard feeds.

Data sources (BigQuery; dataset defaults to 'complete_db'):
- ai_governance_infrastructure_roads (base entity = road_id)
  Fields used: road_id, district, condition_score, last_maintenance_year, last_maintenance_date,
			   traffic_volume_daily, road_length_km, surface_type, repair_requests_last_quarter, status

- ai_governance_maintenance_work_orders (labels + costs)
  Fields: work_order_id, road_id, district, work_type, actual_cost_cr, start_date, completion_date, status

- ai_governance_department_budgets (budget pressure)
  Fields: dept_id, department_name, district, financial_year, total_budget_allocated_cr, budget_utilized_cr

- ai_governance_citizen_services_requests (demand proxy)
  Filter service_type in ("Road Repair", "Pothole", "Drainage", "Streetlight Outage"); aggregate recent counts

- ai_governance_transport_vehicles (traffic proxy by district & year)
  Fields: registered_vehicles (by type), year. Normalize per km of road network in district.

- ai_governance_agriculture_insights (rainfall feature)
  Fields: rainfall_mm_last_month aggregated to district-month; map to roads by district.

Targets
T1. Repair in next 90 days (binary): label=1 if any work_order.start_date in (as_of_date, as_of_date+90d], else 0.
T2. Repair cost (₹ Cr) for T1=1: target = actual_cost_cr for the first work order in window.
T3. Traffic impact (0–100): score from traffic_volume_daily, road_length_km, detour proxy, district vehicle density.
T4. Priority rank (0–100): composite of T1 probability, T3 impact, and condition severity + demand.

Assumptions
- condition_score: higher is better (0–100). We derive severity = 100 - condition_score.
- If per-road citizen requests are unavailable, we allocate district totals uniformly per km as a proxy.
- If T1 training data is sparse, we fall back to a calibrated rule-based probability.
- If T2 has no labels, we estimate cost from surface-type cost-per-km × road_length_km.

Outputs
- Per-road predictions DataFrame and JSON: infra_roads_scores.json
- District aggregates JSON: infra_dashboard_metrics.json
	- critical_roads: count(prob>=0.8 or priority>=80)
	- metrics[0]: avg repair probability (%),
	  metrics[1]: expected repair backlog (₹ Cr, sum of prob*cost),
	  metrics[2]: avg traffic impact (0–100)
- Alerts skeleton per district (e.g., Thane Infrastructure): Top priority road line + counts.

Run
- Import and call score_and_export(project_id, dataset, as_of_date=None, output_dir=".")
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
	from google.cloud import bigquery
except Exception:  # Allows local import without GCP libs
	bigquery = None

DEFAULT_PROJECT_ID = os.getenv("PROJECT_ID") or "artful-affinity-476513-t7"
DEFAULT_DATASET = os.getenv("BQ_DATASET") or "complete_db"


# -----------------------------
# Utilities
# -----------------------------
def _to_datetime(s):
	return pd.to_datetime(s, errors="coerce")


def _coalesce(*vals):
	for v in vals:
		if v is not None and not (isinstance(v, float) and np.isnan(v)):
			return v
	return None


def _safe_num(x, default=np.nan):
	try:
		return float(x)
	except Exception:
		return default


def _minmax(x: pd.Series) -> pd.Series:
	x = x.astype(float)
	lo, hi = x.min(skipna=True), x.max(skipna=True)
	if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
		return pd.Series(np.zeros(len(x)), index=x.index)
	return (x - lo) / (hi - lo)


def _month_start(dt: pd.Timestamp) -> pd.Timestamp:
	return pd.Timestamp(year=dt.year, month=dt.month, day=1)


def _last_quarter_window(as_of: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
	end = as_of
	start = as_of - pd.Timedelta(days=90)
	return (start, end)


# -----------------------------
# Data loading
# -----------------------------
@dataclass
class InfraTables:
	roads: pd.DataFrame
	work_orders: pd.DataFrame
	budgets: pd.DataFrame
	services: pd.DataFrame
	vehicles: pd.DataFrame
	agri: pd.DataFrame


def load_tables(project_id: str = DEFAULT_PROJECT_ID, dataset: str = DEFAULT_DATASET) -> InfraTables:
	if bigquery is None:
		raise RuntimeError("google-cloud-bigquery is not installed in this environment.")

	client = bigquery.Client(project=project_id)

	def q(table: str) -> pd.DataFrame:
		sql = f"SELECT * FROM `{project_id}.{dataset}.{table}`"
		return client.query(sql).to_dataframe()

	roads = q("ai_governance_infrastructure_roads")
	work_orders = q("ai_governance_maintenance_work_orders")
	budgets = q("ai_governance_department_budgets")
	services = q("ai_governance_citizen_services_requests")
	vehicles = q("ai_governance_transport_vehicles")
	agri = q("ai_governance_agriculture_insights")

	return InfraTables(roads=roads, work_orders=work_orders, budgets=budgets, services=services, vehicles=vehicles, agri=agri)


# -----------------------------
# Feature engineering at as_of_date
# -----------------------------
def build_features(t: InfraTables, as_of_date: Optional[pd.Timestamp] = None) -> pd.DataFrame:
	"""Return per-road feature frame for the given as_of_date.
	Uses only information available up to as_of_date.
	"""
	as_of = _to_datetime(as_of_date) if as_of_date is not None else pd.Timestamp.today().normalize()

	roads = t.roads.copy()
	if roads.empty:
		return pd.DataFrame()

	# Basic type coercions
	for col in [
		"condition_score",
		"traffic_volume_daily",
		"road_length_km",
		"repair_requests_last_quarter",
	]:
		if col in roads.columns:
			roads[col] = pd.to_numeric(roads[col], errors="coerce")

	if "last_maintenance_date" in roads.columns:
		roads["last_maintenance_date"] = _to_datetime(roads["last_maintenance_date"]).dt.tz_localize(None)

	# Recency since last maintenance: days
	if "last_maintenance_date" in roads.columns:
		roads["days_since_maintenance"] = (as_of - roads["last_maintenance_date"]).dt.days
	elif "last_maintenance_year" in roads.columns:
		# Approx: assume mid-year date
		try:
			roads["days_since_maintenance"] = (as_of - pd.to_datetime(roads["last_maintenance_year"].astype(str) + "-07-01", errors="coerce")).dt.days
		except Exception:
			roads["days_since_maintenance"] = np.nan
	else:
		roads["days_since_maintenance"] = np.nan

	# Citizen services: filter by service types in last 90 days, aggregate per district
	svc = t.services.copy()
	svc_types = {"road repair", "pothole", "drainage", "streetlight outage"}
	if not svc.empty:
		if "service_type" in svc.columns:
			svc["service_type_norm"] = svc["service_type"].astype(str).str.strip().str.lower()
			svc = svc[svc["service_type_norm"].isin(svc_types)]
		# pick a date column
		svc_date_col = None
		for c in ["request_date", "report_date", "created_at", "last_updated", "date"]:
			if c in svc.columns:
				svc_date_col = c
				break
		if svc_date_col:
			svc[svc_date_col] = _to_datetime(svc[svc_date_col]).dt.tz_localize(None)
			start, end = _last_quarter_window(as_of)
			svc_recent = svc[(svc[svc_date_col] <= end) & (svc[svc_date_col] >= start)].copy()
		else:
			svc_recent = svc.copy()
		if "district" in svc_recent.columns:
			svc_agg = (
				svc_recent.groupby("district").size().rename("svc_reports_last_qtr").reset_index()
			)
		else:
			svc_agg = pd.DataFrame(columns=["district", "svc_reports_last_qtr"])  # no district info
	else:
		svc_agg = pd.DataFrame(columns=["district", "svc_reports_last_qtr"])  # empty

	# Vehicles by district/year: get latest year per district; compute vehicle_density_per_km
	veh = t.vehicles.copy()
	if not veh.empty:
		year_col = "year" if "year" in veh.columns else None
		if year_col is None:
			# try to infer a year-like column
			for c in veh.columns:
				if c.lower().endswith("year"):
					year_col = c
					break
		if year_col:
			veh[year_col] = pd.to_numeric(veh[year_col], errors="coerce")
			veh = veh.sort_values(year_col).dropna(subset=[year_col])
			veh_latest = veh.groupby("district").tail(1)
		else:
			veh_latest = veh
		# sum all vehicle counts columns
		veh_count_cols = [c for c in veh_latest.columns if c not in ("district", year_col) and veh_latest[c].dtype != "O"]
		veh_latest["registered_vehicles_total"] = veh_latest[veh_count_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1)
		# road network km per district from roads table
		network = roads.groupby("district")["road_length_km"].sum(min_count=1).rename("road_network_km").reset_index()
		veh_den = veh_latest.merge(network, on="district", how="left")
		veh_den["vehicle_density_per_km"] = veh_den["registered_vehicles_total"] / veh_den["road_network_km"].replace(0, np.nan)
		veh_den = veh_den[["district", "vehicle_density_per_km"]]
	else:
		veh_den = pd.DataFrame(columns=["district", "vehicle_density_per_km"])  # empty

	# Rainfall: take last month for the district
	agri = t.agri.copy()
	if not agri.empty:
		# find a date-like column
		date_col = None
		for c in ["date", "last_updated", "month", "as_of_date"]:
			if c in agri.columns:
				date_col = c
				break
		if date_col:
			agri[date_col] = _to_datetime(agri[date_col]).dt.tz_localize(None)
			agri["month_start"] = agri[date_col].dt.to_period("M").dt.start_time
			month_ref = _month_start(as_of - pd.Timedelta(days=1))  # previous month
			agri_recent = agri[agri["month_start"] == month_ref]
		else:
			agri_recent = agri.copy()
		rain_col = "rainfall_mm_last_month" if "rainfall_mm_last_month" in agri_recent.columns else None
		if rain_col is None:
			# try generic rainfall column
			for c in agri_recent.columns:
				if "rainfall" in c.lower():
					rain_col = c
					break
		if rain_col:
			rain = agri_recent[["district", rain_col]].rename(columns={rain_col: "rainfall_mm_last_month"}).dropna()
		else:
			rain = pd.DataFrame(columns=["district", "rainfall_mm_last_month"])  # none
	else:
		rain = pd.DataFrame(columns=["district", "rainfall_mm_last_month"])  # empty

	# Budgets: latest per district + utilization ratio (robust to FY strings like "2024-2025")
	b = t.budgets.copy()
	if not b.empty:
		# Prepare sorting keys
		if "last_updated" in b.columns:
			b["last_updated_dt"] = _to_datetime(b["last_updated"]).dt.tz_localize(None)

		fy_col = "financial_year" if "financial_year" in b.columns else None

		def _parse_fy(v):
			try:
				s = str(v)
				# Extract all 4-digit numbers; choose the max as the end year
				yrs = [int(x) for x in __import__("re").findall(r"(\d{4})", s)]
				return max(yrs) if yrs else np.nan
			except Exception:
				return np.nan

		if fy_col:
			# Build a numeric key even for string FYs like "2024-2025"
			fy_key = f"{fy_col}_num"
			b[fy_key] = pd.to_numeric(b[fy_col], errors="coerce")
			if b[fy_key].isna().all():
				b[fy_key] = b[fy_col].apply(_parse_fy)

			# If still NaN for all, fallback to last_updated_dt
			if b[fy_key].isna().all() and "last_updated_dt" in b.columns:
				b = b.sort_values(["district", "last_updated_dt"]).copy()
			else:
				b = b.sort_values(["district", fy_key]).copy()
		elif "last_updated_dt" in b.columns:
			b = b.sort_values(["district", "last_updated_dt"]).copy()

		b_latest = b.groupby("district").tail(1)

		for c in ["total_budget_allocated_cr", "budget_utilized_cr"]:
			if c in b_latest.columns:
				b_latest[c] = pd.to_numeric(b_latest[c], errors="coerce")

		if {"budget_utilized_cr", "total_budget_allocated_cr"}.issubset(b_latest.columns):
			b_latest["budget_utilization_ratio"] = (
				b_latest["budget_utilized_cr"] / b_latest["total_budget_allocated_cr"].replace(0, np.nan)
			)
		else:
			b_latest["budget_utilization_ratio"] = np.nan

		keep_b_cols = [c for c in ["district", "budget_utilization_ratio", "total_budget_allocated_cr"] if c in b_latest.columns]
		b_latest = b_latest[keep_b_cols].copy()
	else:
		b_latest = pd.DataFrame(columns=["district", "budget_utilization_ratio", "total_budget_allocated_cr"])

	# Join district-level enrichments
	feat = roads.merge(veh_den, on="district", how="left") \
			   .merge(rain, on="district", how="left") \
			   .merge(svc_agg, on="district", how="left") \
			   .merge(b_latest, on="district", how="left")

	# Fill NaNs and derive helpful normals
	feat["svc_reports_last_qtr"] = pd.to_numeric(feat.get("svc_reports_last_qtr", np.nan), errors="coerce").fillna(0)
	feat["vehicle_density_per_km"] = pd.to_numeric(feat.get("vehicle_density_per_km", np.nan), errors="coerce")
	feat["rainfall_mm_last_month"] = pd.to_numeric(feat.get("rainfall_mm_last_month", np.nan), errors="coerce")
	feat["budget_utilization_ratio"] = pd.to_numeric(feat.get("budget_utilization_ratio", np.nan), errors="coerce")

	# Normalize/scale helper features
	# condition_score may be 0–1, 0–10, or 0–100. Normalize to 0–100 first, then severity=100-score.
	cond_raw = pd.to_numeric(feat.get("condition_score", np.nan), errors="coerce")
	cond_max = np.nanmax(cond_raw.values) if len(cond_raw) else np.nan
	if np.isfinite(cond_max) and cond_max <= 1.0:
		cond_scaled = cond_raw * 100.0
	elif np.isfinite(cond_max) and cond_max <= 10.0:
		cond_scaled = cond_raw * 10.0
	else:
		cond_scaled = cond_raw
	feat["cond_severity"] = (100.0 - cond_scaled).clip(lower=0, upper=100)
	feat["traffic_norm"] = _minmax(feat.get("traffic_volume_daily", pd.Series(np.nan, index=feat.index)))
	feat["length_norm"] = _minmax(feat.get("road_length_km", pd.Series(np.nan, index=feat.index)))
	feat["veh_den_norm"] = _minmax(feat.get("vehicle_density_per_km", pd.Series(np.nan, index=feat.index)))
	feat["svc_norm"] = _minmax(feat.get("svc_reports_last_qtr", pd.Series(np.nan, index=feat.index)))
	feat["rain_norm"] = _minmax(feat.get("rainfall_mm_last_month", pd.Series(np.nan, index=feat.index)))

	# A simple rule-based traffic impact (0–100)
	# Intuition: closures on long, high-traffic roads in dense districts have bigger impact; rainfall ups fragility
	base_impact = 0.6 * feat["traffic_norm"] + 0.3 * feat["veh_den_norm"] + 0.1 * feat["length_norm"]
	feat["traffic_impact_0_100"] = (100 * (0.85 * base_impact + 0.15 * feat["rain_norm"]))
	feat["traffic_impact_0_100"] = feat["traffic_impact_0_100"].clip(0, 100).fillna(0)

	# Keep key columns
	keep_cols = [
		"road_id", "district", "road_length_km", "surface_type", "condition_score", "status",
		"traffic_volume_daily", "repair_requests_last_quarter", "days_since_maintenance",
		"vehicle_density_per_km", "rainfall_mm_last_month", "svc_reports_last_qtr",
		"budget_utilization_ratio", "total_budget_allocated_cr", "traffic_impact_0_100", "cond_severity"
	]
	keep_cols = [c for c in keep_cols if c in feat.columns]
	feat = feat[keep_cols].copy()

	return feat


# -----------------------------
# Label building for T1/T2
# -----------------------------
def build_labels(t: InfraTables, as_of_date: pd.Timestamp) -> pd.DataFrame:
	"""Return per-road labels for T1/T2 at the given as_of_date.
	T1: repair_in_90d (0/1), T2: repair_cost_cr (float, NaN if T1=0).
	"""
	wo = t.work_orders.copy()
	if wo.empty:
		return pd.DataFrame(columns=["road_id", "repair_in_90d", "repair_cost_cr"])

	for c in ["start_date", "completion_date"]:
		if c in wo.columns:
			wo[c] = _to_datetime(wo[c]).dt.tz_localize(None)

	start, end = as_of_date, as_of_date + pd.Timedelta(days=90)
	if "start_date" not in wo.columns:
		# Can't label without start_date
		return pd.DataFrame(columns=["road_id", "repair_in_90d", "repair_cost_cr"])

	# First work order in window per road
	mask = (wo["start_date"] > start) & (wo["start_date"] <= end)
	inwin = wo[mask].copy().sort_values(["road_id", "start_date"])  # earliest first
	first_inwin = inwin.groupby("road_id").head(1)

	labels = first_inwin[["road_id"]].drop_duplicates().copy()
	labels["repair_in_90d"] = 1
	if "actual_cost_cr" in first_inwin.columns:
		labels = labels.merge(first_inwin[["road_id", "actual_cost_cr"]], on="road_id", how="left")
		labels = labels.rename(columns={"actual_cost_cr": "repair_cost_cr"})
	else:
		labels["repair_cost_cr"] = np.nan

	# Add zeros for roads with no upcoming repair
	all_roads = t.roads[["road_id"]].drop_duplicates()
	labels = all_roads.merge(labels, on="road_id", how="left").fillna({"repair_in_90d": 0})
	return labels


# -----------------------------
# Simple model training (optional) and rule-based fallback
# -----------------------------
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer


def _prepare_X(feat: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
	candidate_feats = [
		"cond_severity",
		"days_since_maintenance",
		"traffic_volume_daily",
		"road_length_km",
		"vehicle_density_per_km",
		"svc_reports_last_qtr",
		"rainfall_mm_last_month",
		"budget_utilization_ratio",
		"traffic_impact_0_100",
	]
	cols = [c for c in candidate_feats if c in feat.columns]
	X = feat[cols].apply(pd.to_numeric, errors="coerce")
	return X, cols


def train_t1_t2_models(t: InfraTables, as_of_date: Optional[pd.Timestamp] = None):
	"""Train T1 (probability 90d) and T2 (cost) models using snapshot at as_of_date.
	For simplicity (and limited data), this uses a single snapshot and falls back to rules if labels insufficient.
	Returns: (clf_or_None, reg_or_None, rulebacks)
	"""
	as_of = _to_datetime(as_of_date) if as_of_date is not None else pd.Timestamp.today().normalize()
	feat = build_features(t, as_of)
	labels = build_labels(t, as_of)
	if feat.empty:
		return None, None, {}
	df = feat.merge(labels, on="road_id", how="left")
	df["repair_in_90d"] = df["repair_in_90d"].fillna(0)

	X, cols = _prepare_X(df)
	imp = SimpleImputer(strategy="median")
	X_imp = imp.fit_transform(X)

	# --- T1 Classification ---
	y = df["repair_in_90d"].astype(int)
	pos = int(y.sum())
	clf = None
	if pos >= 25:  # need a few positives to learn anything
		clf = LogisticRegression(max_iter=1000, class_weight="balanced")
		clf.fit(X_imp, y)

	# Rule-based prob fallback: calibrated risk from severity, traffic, recency, demand
	rb_prob = None
	if clf is None:
		z = (
			0.4 * _minmax(df["cond_severity"]) +
			0.25 * _minmax(df["traffic_volume_daily"]) +
			0.2 * _minmax(df["days_since_maintenance"]) +
			0.15 * _minmax(df["svc_reports_last_qtr"])
		)
		rb_prob = (0.15 + 0.85 * z).clip(0, 1).values  # keep some base rate

	# --- T2 Regression (on positives) ---
	reg = None
	cost_labels = df.loc[df["repair_in_90d"] == 1, ["repair_cost_cr"]].copy()
	if cost_labels["repair_cost_cr"].notna().sum() >= 25 and clf is not None:
		X_pos_imp = X_imp[df["repair_in_90d"].values.astype(bool)]
		y_cost = cost_labels["repair_cost_cr"].astype(float).values
		reg = GradientBoostingRegressor(random_state=42)
		reg.fit(X_pos_imp, y_cost)

	# Rule-based cost fallback by surface_type cost per km
	# Default costs (₹ Cr/km): flexible placeholders; calibrate with your data later
	surf_cost_cr_km = {
		"asphalt": 0.8,
		"concrete": 1.2,
		"gravel": 0.3,
		"dirt": 0.2,
	}
	rb_cost = (
		df.apply(
			lambda r: surf_cost_cr_km.get(str(r.get("surface_type", "")).strip().lower(), 0.7)
			* _safe_num(r.get("road_length_km"), 0.0),
			axis=1,
		).values
	)

	rulebacks = {"imputer": imp, "rb_prob": rb_prob, "rb_cost": rb_cost, "feature_cols": cols}
	return clf, reg, rulebacks


# -----------------------------
# Scoring and priority computation
# -----------------------------
def score_now(t: InfraTables, clf, reg, rulebacks, as_of_date: Optional[pd.Timestamp] = None) -> pd.DataFrame:
	as_of = _to_datetime(as_of_date) if as_of_date is not None else pd.Timestamp.today().normalize()
	feat = build_features(t, as_of)
	if feat.empty:
		return pd.DataFrame()

	X, cols = _prepare_X(feat)
	imp = rulebacks.get("imputer")
	X_imp = imp.transform(X)

	# T1
	if clf is not None:
		prob = clf.predict_proba(X_imp)[:, 1]
	else:
		prob = rulebacks["rb_prob"]
		if prob is None:
			# very last resort
			prob = (0.5 * _minmax(feat.get("cond_severity", pd.Series(0))) + 0.5 * _minmax(feat.get("traffic_volume_daily", pd.Series(0)))).fillna(0).values

	# T2
	if reg is not None:
		# Estimate expected cost for all (can also gate by prob threshold)
		cost_est = reg.predict(X_imp)
		# clean negatives
		cost_est = np.maximum(cost_est, 0)
	else:
		cost_est = rulebacks["rb_cost"]

	df = feat.copy()
	df["repair_probability_90d"] = prob
	df["repair_cost_estimate_cr"] = cost_est

	# T3 already in features: traffic_impact_0_100
	impact = df.get("traffic_impact_0_100", pd.Series(np.zeros(len(df))))

	# T4: Priority rank (0–100)
	# Blend: 50% prob, 30% impact (scaled 0–1), 20% condition severity (0–1), slight lift from demand
	priority_0_100 = 100 * (
		0.5 * df["repair_probability_90d"] +
		0.3 * (impact / 100.0) +
		0.18 * _minmax(df.get("cond_severity", pd.Series(0))) +
		0.02 * _minmax(df.get("svc_reports_last_qtr", pd.Series(0)))
	)
	df["priority_rank_0_100"] = priority_0_100.clip(0, 100)

	return df


# -----------------------------
# Dashboard aggregation and export
# -----------------------------
def dashboard_aggregates(per_road: pd.DataFrame) -> Dict[str, dict]:
	if per_road.empty:
		return {}

	out: Dict[str, dict] = {}
	per_road = per_road.copy()
	per_road["district"] = per_road["district"].fillna("Unknown").astype(str)

	# Define critical
	crit_mask = (per_road["repair_probability_90d"] >= 0.8) | (per_road["priority_rank_0_100"] >= 80)
	per_road["expected_cost_cr"] = per_road["repair_probability_90d"] * per_road["repair_cost_estimate_cr"].clip(lower=0)

	grp = per_road.groupby("district")
	for district, g in grp:
		avg_prob_pct = float(np.nanmean(g["repair_probability_90d"]) * 100.0)
		backlog_cr = float(np.nansum(g["expected_cost_cr"]))
		avg_impact = float(np.nanmean(g.get("traffic_impact_0_100", 0)))
		crit_count = int(crit_mask.reindex(g.index, fill_value=False).sum())

		# Top factor line (example): "{RoadName or road_id} (Urgency: 89%)"
		top = g.sort_values("priority_rank_0_100", ascending=False).head(1)
		if not top.empty:
			rid = str(top.iloc[0].get("road_id", "Road"))
			urgency = int(round(top.iloc[0].get("priority_rank_0_100", 0)))
			factor_line = f"{rid} (Urgency: {urgency}%)"
		else:
			factor_line = "—"

		out[district] = {
			"critical_roads": crit_count,
			"metrics": [
				round(avg_prob_pct, 2),            # departments[infrastructure].metrics[0]
				round(backlog_cr, 2),              # departments[infrastructure].metrics[1]
				round(avg_impact, 1),              # departments[infrastructure].metrics[2]
			],
			"top_factor_line": factor_line,
			"alert": {
				"title": f"Critical Roads: {crit_count}",
				"description": f"Avg Repair Prob: {avg_prob_pct:.1f}% | Backlog: ₹{backlog_cr:.2f} Cr | Impact: {avg_impact:.0f}",
			},
		}
	return out


def score_and_export(
	project_id: str = DEFAULT_PROJECT_ID,
	dataset: str = DEFAULT_DATASET,
	as_of_date: Optional[str | pd.Timestamp] = None,
	output_dir: str = ".",
) -> Tuple[pd.DataFrame, Dict[str, dict]]:
	"""High-level runner: trains simple models (with fallback), scores now, and exports JSON files.
	Returns: (per_road_df, district_metrics_dict)
	"""
	t = load_tables(project_id, dataset)
	clf, reg, rulebacks = train_t1_t2_models(t, as_of_date)
	scored = score_now(t, clf, reg, rulebacks, as_of_date)

	roads_json_path = os.path.join(output_dir, "infra_roads_scores.json")
	scored_out = scored.copy()
	# keep compact columns for export
	export_cols = [
		"road_id", "district", "repair_probability_90d", "repair_cost_estimate_cr",
		"traffic_impact_0_100", "priority_rank_0_100"
	]
	export_cols = [c for c in export_cols if c in scored_out.columns]
	scored_out[export_cols].to_json(roads_json_path, orient="records")

	district_dict = dashboard_aggregates(scored)
	dash_json_path = os.path.join(output_dir, "infra_dashboard_metrics.json")
	with open(dash_json_path, "w") as f:
		json.dump(district_dict, f, indent=2)

	return scored, district_dict


if __name__ == "__main__":
	# Optional CLI runner for local testing (requires ADC with BigQuery access)
	as_of_str = os.getenv("AS_OF_DATE")  # e.g., 2025-11-01
	as_of = pd.to_datetime(as_of_str).date() if as_of_str else None
	df, agg = score_and_export(DEFAULT_PROJECT_ID, DEFAULT_DATASET, as_of, ".")
	print(f"Scored {len(df)} roads. Wrote infra_roads_scores.json and infra_dashboard_metrics.json")

