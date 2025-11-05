# !pip install google-cloud-aiplatform google-cloud-bigquery pandas scikit-learn joblib xgboost --upgrade

print("Libraries installed!")
# ------------------------------------------------------------------
# CELL 2: Imports and Configuration
# ------------------------------------------------------------------
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    recall_score,
    precision_recall_curve,
    auc,
)
from sklearn.preprocessing import OneHotEncoder, LabelEncoder
from sklearn.impute import SimpleImputer
from sklearn.calibration import calibration_curve

# --- !!! PRODUCTION-GRADE IMPORTS !!! ---
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
# -----------------------------------------

from google.cloud import bigquery
from google.cloud import aiplatform
import numpy as np
import xgboost as xgb
from sklearn.svm import SVC

import json

# --- !!! YOUR PROJECT DETAILS !!! ---
PROJECT_ID = "artful-affinity-476513-t7"
BQ_DATASET = "complete_db"
REGION = "us-central1"
MODEL_DISPLAY_NAME = "disease_outbreak_prediction_model"
# -------------------------------------

# Initialize the Google Cloud clients
bq_client = bigquery.Client(project=PROJECT_ID)
aiplatform.init(project=PROJECT_ID, location=REGION)

print(f"Clients initialized for project {PROJECT_ID}. Ready to load data.")

from pandas.api.types import is_datetime64_any_dtype as is_datetime_dtype

DISTRICT_RENAME_MAP = {
    'District': 'district',
    'district_name': 'district',
    'DistrictName': 'district',
    'Population': 'total_population',
    'population': 'total_population',
    'Patient Inflow (Daily)': 'patient_inflow_daily',
    'patient_inflow_daily': 'patient_inflow_daily',
    'Disease Outbreak': 'disease_outbreak',
    'disease_outbreak': 'disease_outbreak',
    'last_updated': 'last_updated',
    'last_inspection_date': 'last_inspection_date',
    'request_date': 'request_date',
    'report_date': 'report_date',
    'total_population': 'total_population'
}

def norm_dist(series):
    return (
        series.astype(str)
              .str.strip()
              .str.lower()
              .str.replace(r"\s+", " ", regex=True)
    )

def norm_week(timestamp_series):
    ts = pd.to_datetime(timestamp_series, errors='coerce')
    try:
        ts = ts.dt.tz_localize(None)
    except (AttributeError, TypeError):
        try:
            ts = ts.dt.tz_convert(None)
        except Exception:
            pass
    return ts.dt.to_period('W-MON').dt.start_time

def find_date_col(df, candidates=None):
    if df is None or df.empty:
        return None
    if candidates is None:
        candidates = (
            'report_date',
            'request_date',
            'last_updated',
            'inspection_date',
            'last_inspection_date',
            'resolution_date',
            'date',
            'event_date'
        )
    for col in candidates:
        if col in df.columns:
            return col
    for col in df.columns:
        lowered = col.lower()
        if 'date' in lowered or 'time' in lowered or 'updated' in lowered:
            return col
    for col in df.columns:
        try:
            if is_datetime_dtype(df[col]):
                return col
        except Exception:
            continue
    return None

def normalize_tables():
    for var in ['df_health','df_roads','df_safety','df_services','df_env','df_agri','df_pop']:
        df = globals().get(var)
        if df is None or df.empty:
            continue
        rename_candidates = {c: DISTRICT_RENAME_MAP[c] for c in df.columns if c in DISTRICT_RENAME_MAP}
        if rename_candidates:
            df = df.rename(columns=rename_candidates)
        if 'district' in df.columns and 'district_norm' not in df.columns:
            df['district_norm'] = norm_dist(df['district'])
        date_col = find_date_col(df)
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        globals()[var] = df

print('Normalization helpers ready. Call normalize_tables() after loading raw tables.')
TABLE_MAP = {
    'df_health': 'ai_governance_health_facilities',
    'df_roads': 'ai_governance_infrastructure_roads',
    'df_safety': 'ai_governance_public_safety_reports',
    'df_services': 'ai_governance_citizen_services_requests',
    'df_env': 'ai_governance_environment_monitoring',
    'df_agri': 'ai_governance_agriculture_insights',
    'df_pop': 'ai_governance_population_demographics',
}

# Optional: limit rows for quick iteration (set to None to load full table)
ROW_LIMIT = None  # e.g., 20000 or None

for varname, table in TABLE_MAP.items():
    fq_table = f"{PROJECT_ID}.{BQ_DATASET}.{table}"
    try:
        print(f"Loading `{fq_table}` -> {varname} ...")
        if ROW_LIMIT:
            sql = f"SELECT * FROM `{fq_table}` LIMIT {ROW_LIMIT}"
        else:
            sql = f"SELECT * FROM `{fq_table}`"
        job = bq_client.query(sql)
        df = job.to_dataframe()   # may take time for big tables
        globals()[varname] = df
        print(f"Loaded {varname}: shape={df.shape}")
    except Exception as e:
        print(f"Failed to load `{fq_table}` into {varname}: {e}")

normalize_tables()
print('Applied normalization to loaded tables (district_norm + datetime coercion).')

# Quick peek
for var in TABLE_MAP.keys():
    if var in globals() and getattr(globals()[var], "shape", (0,0))[0] > 0:
        print(f"\n{var} sample (first 3 rows):")
        display(globals()[var].head(3))
    else:
        print(f"\n{var} is empty or not found (shape={getattr(globals().get(var), 'shape', None)})")
def first_existing(df, candidates):
    for column in candidates:
        if column in df.columns:
            return column
    return None

def parse_crime_reports(value):
    if pd.isna(value):
        return {}
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
        crime_type = item.get('type')
        count = item.get('count', 1)
        try:
            count = int(float(count))
        except Exception:
            count = 0
        if crime_type and count:
            counts[crime_type] = counts.get(crime_type, 0) + count
    return counts

for suffix in ['health', 'env', 'safety', 'services', 'roads', 'agri', 'pop']:
    var_name = f'df_{suffix}'
    if var_name not in globals():
        globals()[var_name] = pd.DataFrame()

date_cols = {}
for suffix in ['health', 'env', 'safety', 'services', 'roads', 'agri']:
    df = globals()[f'df_{suffix}']
    if not df.empty and 'district_norm' not in df.columns and 'district' in df.columns:
        df['district_norm'] = norm_dist(df['district'])
    date_col = find_date_col(df)
    date_cols[suffix] = date_col
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    globals()[f'df_{suffix}'] = df

if not df_pop.empty and 'district_norm' not in df_pop.columns and 'district' in df_pop.columns:
    df_pop['district_norm'] = norm_dist(df_pop['district'])

# Health weekly aggregation
health_week = pd.DataFrame()
if not df_health.empty and date_cols.get('health'):
    health_date = date_cols['health']
    patient_col = first_existing(df_health, ['patient_inflow_daily', 'patient_inflow', 'patient_inflow_mean'])
    outbreak_col = first_existing(df_health, ['disease_outbreak'])
    health_cols = ['district_norm', health_date]
    if patient_col:
        health_cols.append(patient_col)
    if outbreak_col:
        health_cols.append(outbreak_col)
    h = df_health[health_cols].copy()
    h = h.dropna(subset=['district_norm'])
    h['week_start'] = norm_week(h[health_date])
    h = h.dropna(subset=['week_start'])
    h['health_events'] = 1
    agg_map = {'health_events': 'sum'}
    if patient_col:
        h['patient_inflow_value'] = pd.to_numeric(h[patient_col], errors='coerce')
        agg_map['patient_inflow_value'] = 'mean'
    if outbreak_col:
        outbreak_series = h[outbreak_col].astype(str).str.strip().str.lower()
        h['outbreak_flag'] = (~outbreak_series.isin({'', 'none', 'null', 'nan'})).astype(int)
        agg_map['outbreak_flag'] = 'sum'
    health_week = h.groupby(['district_norm', 'week_start']).agg(agg_map).reset_index()
    if 'patient_inflow_value' in health_week.columns:
        health_week = health_week.rename(columns={'patient_inflow_value': 'patient_inflow_mean'})
    if 'outbreak_flag' in health_week.columns:
        health_week = health_week.rename(columns={'outbreak_flag': 'outbreak_count'})
    else:
        health_week['outbreak_count'] = 0
    if 'health_events' not in health_week.columns:
        health_week['health_events'] = 0

# Environment weekly aggregation
env_week = pd.DataFrame()
if not df_env.empty and date_cols.get('env'):
    env_date = date_cols['env']
    env_metrics = [c for c in ['air_quality_index', 'pm25_level', 'pm10_level', 'water_quality_index', 'waste_collection_efficiency'] if c in df_env.columns]
    if env_metrics:
        env_cols = ['district_norm', env_date] + env_metrics
        e = df_env[env_cols].copy()
        e = e.dropna(subset=['district_norm'])
        e['week_start'] = norm_week(e[env_date])
        e = e.dropna(subset=['week_start'])
        agg_map = {c: 'mean' for c in env_metrics}
        env_week = e.groupby(['district_norm', 'week_start']).agg(agg_map).reset_index()

# Services weekly aggregation
services_week = pd.DataFrame()
if not df_services.empty and date_cols.get('services'):
    services_date = date_cols['services']
    service_cols = ['district_norm', services_date]
    if 'service_type' in df_services.columns:
        service_cols.append('service_type')
    svc = df_services[service_cols].copy()
    svc = svc.dropna(subset=['district_norm'])
    svc['week_start'] = norm_week(svc[services_date])
    svc = svc.dropna(subset=['week_start'])
    svc['services_events'] = 1
    agg_map = {'services_events': 'sum'}
    if 'service_type' in svc.columns:
        agg_map['service_type'] = 'count'
    services_week = svc.groupby(['district_norm', 'week_start']).agg(agg_map).reset_index()
    if 'service_type' in services_week.columns:
        services_week = services_week.rename(columns={'service_type': 'complaint_count'})

# Safety weekly aggregation from crime JSON
safety_week = pd.DataFrame()
if not df_safety.empty and date_cols.get('safety') and 'crime_reports' in df_safety.columns:
    safety_date = date_cols['safety']
    safe = df_safety[['district_norm', safety_date, 'crime_reports']].copy()
    safe = safe.dropna(subset=['district_norm'])
    safe['week_start'] = norm_week(safe[safety_date])
    safe = safe.dropna(subset=['week_start'])
    safe['crime_counts'] = safe['crime_reports'].apply(parse_crime_reports)
    crime_rows = []
    for _, row in safe.iterrows():
        counts = row['crime_counts'] or {}
        for crime_type, count in counts.items():
            crime_rows.append({'district_norm': row['district_norm'], 'week_start': row['week_start'], 'crime_type': crime_type, 'count': count})
    if crime_rows:
        crime_df = pd.DataFrame(crime_rows)
        safety_week = (
            crime_df.groupby(['district_norm', 'week_start', 'crime_type'])['count']
            .sum()
            .unstack(fill_value=0)
            .reset_index()
        )

for label, wk in [('health', health_week), ('env', env_week), ('services', services_week), ('safety', safety_week)]:
    if wk is None or wk.empty:
        print(f'{label}_week: empty')
    else:
        print(
            f"{label}_week rows={len(wk)}, districts={wk['district_norm'].nunique()}, "
            f"weeks={wk['week_start'].min()}->{wk['week_start'].max()}"
        )

weekly_tables = [health_week, env_week, services_week, safety_week]

def _uniq(series):
    return set(series.dropna().unique().tolist())

signal_districts = set()
week_union = set()
for wk in weekly_tables:
    if wk is not None and not wk.empty:
        signal_districts |= _uniq(wk['district_norm'])
        week_union |= _uniq(wk['week_start'])

if df_pop.empty:
    raise ValueError('Population table is required to build the panel.')

if 'district_norm' not in df_pop.columns and 'district' in df_pop.columns:
    df_pop['district_norm'] = norm_dist(df_pop['district'])

pop_districts = _uniq(df_pop['district_norm'])
missing_in_pop = sorted(signal_districts - pop_districts)
if missing_in_pop:
    preview = ', '.join(missing_in_pop[:8])
    print(f'Districts with weekly signal missing in population ({len(missing_in_pop)}): {preview}')
missing_signal = sorted(pop_districts - signal_districts)
print(f'Districts with population but no weekly signal: {len(missing_signal)}')

districts = sorted(signal_districts & pop_districts)
weeks = sorted(week_union)

if not districts or not weeks:
    raise ValueError('No overlapping districts/weeks between population and weekly tables after normalization.')

panel = pd.MultiIndex.from_product([districts, weeks], names=['district_norm', 'week_start']).to_frame(index=False)

def merge_weekly(base, weekly):
    if weekly is None or weekly.empty:
        return base
    temp = weekly.copy()
    temp['week_start'] = pd.to_datetime(temp['week_start']).dt.floor('D')
    return base.merge(temp, on=['district_norm', 'week_start'], how='left')

panel['week_start'] = pd.to_datetime(panel['week_start']).dt.floor('D')
panel = merge_weekly(panel, health_week)
panel = merge_weekly(panel, env_week)
panel = merge_weekly(panel, services_week)
panel = merge_weekly(panel, safety_week)

def inner_hits(base, weekly):
    if weekly is None or weekly.empty:
        return 0
    pairs = weekly[['district_norm', 'week_start']].dropna().drop_duplicates()
    pairs['week_start'] = pd.to_datetime(pairs['week_start']).dt.floor('D')
    return base[['district_norm', 'week_start']].merge(pairs, how='inner').shape[0]

print('Inner hits with weekly tables:',
      inner_hits(panel, health_week),
      inner_hits(panel, env_week),
      inner_hits(panel, services_week),
      inner_hits(panel, safety_week))

pop_cols = [c for c in ['district_norm', 'district', 'total_population', 'population_density_per_sqkm', 'avg_household_size'] if c in df_pop.columns]
pop_frame = df_pop[pop_cols].drop_duplicates(subset=['district_norm'])
panel = panel.merge(pop_frame, on='district_norm', how='left')

if 'district' not in panel.columns:
    panel['district'] = panel['district_norm']

if 'total_population' in panel.columns:
    panel['total_population'] = pd.to_numeric(panel['total_population'], errors='coerce')
    panel['pop_per_100k'] = panel['total_population'].replace({0: np.nan}) / 100000.0
else:
    panel['pop_per_100k'] = np.nan

count_cols = [c for c in ['outbreak_count', 'health_events', 'services_events', 'complaint_count'] if c in panel.columns]
for col in count_cols:
    panel[col] = pd.to_numeric(panel[col], errors='coerce').fillna(0)

crime_cols = [c for c in panel.columns if c.startswith('crime_')]
for col in crime_cols:
    panel[col] = pd.to_numeric(panel[col], errors='coerce').fillna(0)
    panel[col] = np.where(panel['pop_per_100k'] > 0, panel[col] / panel['pop_per_100k'], 0)

cont_candidates = [
    'patient_inflow_mean',
    'air_quality_index',
    'pm25_level',
    'pm10_level',
    'water_quality_index',
    'waste_collection_efficiency',
    'traffic_volume_daily',
    'condition_score'
]
cont_cols = [c for c in cont_candidates if c in panel.columns]
for col in cont_cols:
    panel[col] = pd.to_numeric(panel[col], errors='coerce')
    panel[col] = panel.groupby('district_norm')[col].transform(lambda s: s.ffill().bfill())
    median_val = panel[col].median(skipna=True)
    panel[col] = panel[col].fillna(median_val)

for window in [1, 2, 4]:
    if 'pm25_level' in panel.columns:
        panel[f'pm25_roll_{window}w'] = panel.groupby('district_norm')['pm25_level'].transform(
            lambda s: s.shift(1).rolling(window, min_periods=1).mean()
        )
    if 'patient_inflow_mean' in panel.columns:
        panel[f'patient_inflow_roll_{window}w'] = panel.groupby('district_norm')['patient_inflow_mean'].transform(
            lambda s: s.shift(1).rolling(window, min_periods=1).mean()
        )

def future_sum(series, horizon):
    values = series.fillna(0).to_numpy()
    out = np.zeros(len(values), dtype=float)
    for idx in range(len(values)):
        start = idx + 1
        end = min(idx + 1 + horizon, len(values))
        out[idx] = values[start:end].sum()
    return pd.Series(out, index=series.index)

if 'outbreak_count' not in panel.columns:
    panel['outbreak_count'] = 0
panel['outbreak_count'] = pd.to_numeric(panel['outbreak_count'], errors='coerce').fillna(0)

HORIZON_WEEKS = 2
panel = panel.sort_values(['district_norm', 'week_start']).reset_index(drop=True)
panel['outbreak_next_14d'] = (
    panel.groupby('district_norm')['outbreak_count']
         .transform(lambda s: future_sum(s, HORIZON_WEEKS))
         .gt(0)
         .astype(int)
)

positive_rows = int((panel['outbreak_count'] > 0).sum())
positive_rate = float(panel['outbreak_next_14d'].mean())
print('Panel districts:', len(districts))
print('Panel weeks:', len(weeks))
print('Rows with outbreak_count>0:', positive_rows)
print('Positive rate (outbreak_next_14d):', positive_rate)

if not env_week.empty and len(panel) > 0:
    env_share = (
        panel[['district_norm', 'week_start']]
        .merge(env_week[['district_norm', 'week_start']].drop_duplicates(), how='inner')
        .shape[0] / len(panel)
    )
    print(f'Share of rows with raw env coverage: {env_share:.3f}')
elif env_week.empty:
    print('Share of rows with raw env coverage: 0.000')

df_model = panel.copy()
df_model.to_csv('district_week_panel_demo.csv', index=False)
print('Saved CLEAN district_week_panel_demo.csv (normalized panel).')
# 1) Compare district vocabularies
print("pop districts (sample):", df_pop['district'].dropna().unique()[:10])
print("health districts (sample):", df_health['district'].dropna().unique()[:10])

# 2) How many overlaps?
pop_set = set(df_pop['district'].dropna().str.strip().str.lower())
health_set = set(df_health['district'].dropna().str.strip().str.lower())
print("overlap count:", len(pop_set & health_set))

# Inspect health / env columns & dtypes
print("df_health columns:", df_health.columns.tolist())
print(df_health.dtypes)
display(df_health.head(5))

print("df_env columns:", df_env.columns.tolist())
print(df_env.dtypes)
display(df_env.head(5))

cands = ['patient_inflow','patient_inflow_daily','Patient Inflow (Daily)','patient_inflow_mean']
for c in cands:
    if c in df_health.columns:
        print(c, "non-null fraction:", df_health[c].notna().mean(), "dtype:", df_health[c].dtype)
        
for c in ['disease_outbreak','Disease Outbreak','diseaseOutbreak']:
    if c in df_health.columns:
        print(c, "unique values:", df_health[c].astype(str).value_counts(dropna=False).head(10))
        
def coverage(panel, cols):
    return panel.groupby('district')[cols].apply(lambda s: s.notna().mean()).head(10)
print("Coverage sample (env + health):")
print(coverage(panel, [c for c in ['pm25_level','patient_inflow_mean','air_quality_index'] if c in panel.columns]))
print("Outbreak positives:", panel['outbreak_next_14d'].sum(), " / ", len(panel))
# --- Create df_merged skeleton from the weekly panel so downstream joins work ---
# Place this right after you create `panel` and before CELL 4.1

df_merged = (
    panel[['district', 'district_norm', 'week_start']]
    .rename(columns={'week_start': 'feature_date'})
    .copy()
)

# If `district` might be missing in panel, backfill from district_norm
if 'district' not in df_merged.columns:
    df_merged['district'] = df_merged['district_norm']

# Ensure proper dtypes
df_merged['feature_date'] = pd.to_datetime(df_merged['feature_date'], errors='coerce')
df_merged['district_norm'] = norm_dist(df_merged['district_norm'])
# ------------------------------------------------------------------
 # CELL 4.1: Create forward-looking target & windowed features (Horizon)
 # ------------------------------------------------------------------
import warnings
from datetime import timedelta
HORIZON_DAYS = 14  # predict outbreak within next 14 days
# 1) Forward-looking target from health events
date_col = find_date_col(df_health)
outbreak_col = first_existing(df_health, ['disease_outbreak', 'Disease Outbreak'])
if date_col is None or outbreak_col is None:
    warnings.warn('Health table lacks a usable date or outbreak column; skipping forward-looking label build.')
elif 'df_merged' not in globals():
    warnings.warn('df_merged is not defined; cannot project forward-looking label onto merged feature table.')
else:
    df_health[date_col] = pd.to_datetime(df_health[date_col], errors='coerce')
    outbreak_series = df_health[outbreak_col].astype(str).str.strip().str.lower()
    valid_mask = ~outbreak_series.isin({'', 'none', 'null', 'nan'})
    df_events = df_health[valid_mask][['district', 'district_norm', date_col]].copy()
    df_events = df_events.rename(columns={date_col: 'report_date'})
    def has_future_outbreak(row):
        d_norm = row.get('district_norm')
        if d_norm is None or pd.isna(d_norm):
            d_norm = norm_dist(pd.Series([row.get('district', '')])).iloc[0]
        t0 = row.get('feature_date')
        if d_norm is None or pd.isna(t0):
            return 0
        ev = df_events[df_events['district_norm'] == d_norm]['report_date']
        if ev.empty:
            return 0
        future = ev[(ev > t0) & (ev <= t0 + pd.Timedelta(days=HORIZON_DAYS))]
        return int(not future.empty)
    df_merged['district_norm'] = norm_dist(df_merged['district']) if 'district_norm' not in df_merged.columns else df_merged['district_norm']
    df_merged['outbreak_future_14d'] = df_merged.apply(has_future_outbreak, axis=1)
    df_merged['outbreak_risk'] = df_merged['outbreak_future_14d']
    print(f"Created forward-looking label outbreak_future_14d using {date_col} / {outbreak_col}")
# 2) Parse crime JSON into district-level columns (no week, district-level)
if 'crime_reports' in df_safety.columns and 'df_merged' in globals():
    safe = df_safety[['district_norm', 'crime_reports']].dropna(subset=['district_norm']).copy()
    safe['crime_counts'] = safe['crime_reports'].apply(parse_crime_reports)

    # explode into long rows: (district_norm, crime_type, count)
    rows = []
    for _, r in safe.iterrows():
        cc = r['crime_counts'] or {}
        for ctype, cnt in cc.items():
            rows.append({'district_norm': r['district_norm'], 'crime_type': ctype, 'count': int(cnt)})
    if rows:
        crime_df = pd.DataFrame(rows)
        # aggregate across all safety rows per district
        crime_wide = (
            crime_df.groupby(['district_norm', 'crime_type'])['count']
                    .sum()
                    .unstack(fill_value=0)
                    .add_prefix('crime_')
                    .reset_index()
        )
        # merge once (unique index ensured by reset_index)
        df_merged = df_merged.merge(crime_wide, on='district_norm', how='left')
        # fill NaNs from left-join
        crime_cols = [c for c in df_merged.columns if c.startswith('crime_')]
        df_merged[crime_cols] = df_merged[crime_cols].fillna(0).astype(int)
        print(f"Merged crime JSON counts into df_merged ({len(crime_cols)} columns).")
    else:
        print("crime_reports present but no parsable rows.")
elif 'df_merged' not in globals():
    warnings.warn('df_merged is not defined; skipping crime_reports feature engineering.')
else:
    print('No crime_reports column available to parse.')
# 3) Placeholder for rolling environmental joins (requires df_merged with feature_date)
env_date_col = find_date_col(df_env)
if env_date_col and 'df_merged' in globals():
    df_env[env_date_col] = pd.to_datetime(df_env[env_date_col], errors='coerce')
    env_weekly = df_env.copy()
    env_weekly['week_start'] = norm_week(env_weekly[env_date_col])
    env_metrics = env_weekly.groupby(['district_norm', 'week_start']).agg({
        'pm25_level': 'mean',
        'pm10_level': 'mean',
        'air_quality_index': 'mean'
    }).reset_index()
    df_merged['feature_week'] = norm_week(df_merged['feature_date'])
    df_merged = df_merged.merge(
        env_metrics.rename(columns={'week_start': 'feature_week'}),
        on=['district_norm', 'feature_week'],
        how='left'
    )
    print('Merged weekly environmental metrics onto df_merged (demo).')
elif 'df_merged' not in globals():
    warnings.warn('df_merged missing; skipping environmental feature join.')
else:
    print('No date column in environment_monitoring; skipping environmental window features.')
print('Horizon & windowed feature step complete (demo skeleton).')
# ------------------------------------------------------------------
# CELL 5: Preprocess Data (NO FEATURE SELECTION)
# ------------------------------------------------------------------

# Select limited, meaningful features for modeling (as-of at week_start)
relevant_features = [
    'pm25_level', 'pm10_level', 'air_quality_index', 'water_quality_index', 'waste_collection_efficiency',
    'population_density_per_sqkm', 'avg_household_size',
    'patient_inflow_mean',
    # rolling features
    'pm25_roll_1w', 'pm25_roll_2w', 'pm25_roll_4w',
    'patient_inflow_roll_1w', 'patient_inflow_roll_2w', 'patient_inflow_roll_4w'
]

# Ensure features exist
relevant_features = [f for f in relevant_features if f in df_model.columns]
print('--- Using all 14 features: ---')
print(relevant_features)

# Target
target_col = 'outbreak_next_14d'
X_df = df_model[['district', 'week_start'] + relevant_features].copy()
y = df_model[target_col].copy()

# Drop initial rows with NaN in key features (e.g., from rolling windows)
X_df = X_df.dropna(subset=relevant_features)
# align y
y = y.loc[X_df.index]

# Split by time: train up to a date, test after
cutoff = X_df['week_start'].quantile(0.8)
train_mask = X_df['week_start'] <= cutoff
X_train_raw = X_df[train_mask].drop(columns=['district', 'week_start'])
X_test_raw = X_df[~train_mask].drop(columns=['district', 'week_start'])
y_train = y[train_mask]
y_test = y[~train_mask]

print(f'\nTrain weeks: {X_df[train_mask]["week_start"].min()} to {X_df[train_mask]["week_start"].max()}')
print(f'Test weeks: {X_df[~train_mask]["week_start"].min()} to {X_df[~train_mask]["week_start"].max()}')

# --- This is our full feature list ---
numerical_cols = X_train_raw.select_dtypes(include=[np.number]).columns.tolist()
print(f"Training with {len(numerical_cols)} features.")

# --- This is our preprocessor ---
numerical_transformer = Pipeline(steps=[
    ('imputer', SimpleImputer(strategy='mean')),
])
# We only have numeric features, so the preprocessor is simple
preprocessor = ColumnTransformer(transformers=[('num', numerical_transformer, numerical_cols)])

print('Final feature matrix shapes (before model pipeline):', X_train_raw.shape, X_test_raw.shape)
print('Train positive rate:', y_train.mean(), 'Test positive rate:', y_test.mean())

# ------------------------------------------------------------------
# CELL 6: Data Exploration (Split moved to CELL 5)
# ------------------------------------------------------------------

print("Time-based data split completed in CELL 5 to avoid data leakage.")
print(f"Train period: {X_df[train_mask]['week_start'].min()} to {X_df[train_mask]['week_start'].max()}")
print(f"Test period: {X_df[~train_mask]['week_start'].min()} to {X_df[~train_mask]['week_start'].max()}")
print('Number of districts in panel:', df_model['district'].nunique())
print('Date range in panel:', df_model['week_start'].min(), 'to', df_model['week_start'].max())

best_model = None
# ------------------------------------------------------------------
# CELL 7: Choose Best Algorithm (class-weighting)
# ------------------------------------------------------------------
from sklearn.metrics import average_precision_score, roc_auc_score

from sklearn.exceptions import UndefinedMetricWarning
import warnings
warnings.filterwarnings("ignore", category=UndefinedMetricWarning)

# Compute class weight / scale
pos = y_train.sum()
neg = len(y_train) - pos
scale_pos_weight = (neg / pos) if pos > 0 else 1.0
print('scale_pos_weight (neg/pos):', scale_pos_weight)

# --- We will build the *full* pipeline for each model ---
models_to_test = {
    'RandomForest': RandomForestClassifier(
        n_estimators=100,
        class_weight='balanced',
        max_depth=10,
        random_state=42
    ),
    'XGBoost': xgb.XGBClassifier(
        objective='binary:logistic',
        scale_pos_weight=scale_pos_weight,
        max_depth=6,
        learning_rate=0.1,
        random_state=42
    )
}

best_model_estimator = None
best_score = -np.inf
best_name = ''

for name, model_estimator in models_to_test.items():
    # --- Build the full pipeline for this model ---
    test_pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', model_estimator)
    ])

    # Fit the *entire* pipeline on the *raw* training data
    print(f"\nTraining {name}...")
    test_pipeline.fit(X_train_raw, y_train)

    # Evaluate
    y_pred = test_pipeline.predict(X_test_raw)
    y_proba = test_pipeline.predict_proba(X_test_raw)[:, 1]

    pr_auc = average_precision_score(y_test, y_proba)
    roc_auc = roc_auc_score(y_test, y_proba)

    print(f"--- {name} Results ---")
    print(f"ROC AUC: {roc_auc:.4f}")
    print(f"PR AUC (Area Under Precision-Recall Curve): {pr_auc:.4f}")
    print(classification_report(y_test, y_pred, target_names=["No Outbreak", "Outbreak"], zero_division=0))

    score = pr_auc

    if score > best_score:
        best_score = score
        best_model_estimator = model_estimator
        best_name = name

print(f"\nBest model: {best_name} with PR AUC {best_score:.4f}")
# ------------------------------------------------------------------
# CELL 8: Train Final Model and Save (artifact at root) 
# ------------------------------------------------------------------

if 'best_model_estimator' in locals():
    print(f"Building final pipeline with best model: {best_name}")

    # Create final pipeline
    full_pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', best_model_estimator)
    ])

    # Fit on full training set
    full_pipeline.fit(X_train_raw, y_train)

    # Save artifact at repo root
    import joblib
    joblib.dump(full_pipeline, 'model.joblib')
    print('Saved final pipeline as model.joblib')

    # You are now ready to run Cell 9 (Upload) and Cell 10 (Deploy)

else:
    print("Error: No best model was selected. Cannot build final pipeline.")
