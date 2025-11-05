import functions_framework
import google.cloud.firestore
from google.cloud import aiplatform
from google.cloud import bigquery
import pandas as pd
import numpy as np
import joblib
import os
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.base import BaseEstimator, TransformerMixin

# --- !!! CONFIGURATION !!! ---
PROJECT_ID = "artful-affinity-476513-t7"
REGION = "us-central1"
BQ_DATASET = "complete_db"
# --- !!! Yahaan ENDPOINT_ID paste karein jab woh ready ho jaaye !!! ---
ENDPOINT_ID = "YOUR_ENDPOINT_ID_HERE" 
DB_COLLECTION_NAME = "district_risk_scores" # Yeh naya collection hai
# ------------------------------

# --- Data Engineering Helpers (Aapke notebook se) ---
def norm_dist(series):
    return series.astype(str).str.strip().str.lower().str.replace(r"\s+", " ", regex=True)

def norm_week(timestamp_series):
    ts = pd.to_datetime(timestamp_series, errors='coerce')
    try: ts = ts.dt.tz_localize(None)
    except Exception:
        try: ts = ts.dt.tz_convert(None)
        except Exception: pass
    return ts.dt.to_period('W-MON').dt.start_time

def find_date_col(df):
    for col in ('report_date', 'last_inspection_date', 'request_date', 'last_updated'):
        if col in df.columns: return col
    return None

def first_existing(df, candidates):
    for column in candidates:
        if column in df.columns: return column
    return None

# --- Vertex AI Bug Fix (Aapke notebook se) ---
class ReshapeTo2D(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None): return self
    def transform(self, X):
        if len(getattr(X, 'shape', [])) == 1:
            return np.array(X).reshape(1, -1)
        return X

# --- Global Clients ---
db = google.cloud.firestore.Client()
bq_client = bigquery.Client(project=PROJECT_ID)
aiplatform.init(project=PROJECT_ID, location=REGION)
endpoint = None # Hum ise neeche initialize karenge

# --- Feature List (Aapke notebook se) ---
FEATURE_ORDER = [
    'pm25_level', 'pm10_level', 'air_quality_index', 
    'water_quality_index', 'waste_collection_efficiency', 
    'population_density_per_sqkm', 'avg_household_size', 
    'patient_inflow_mean', 'pm25_roll_1w', 'pm25_roll_2w', 
    'pm25_roll_4w', 'patient_inflow_roll_1w', 
    'patient_inflow_roll_2w', 'patient_inflow_roll_4w'
]

def load_and_engineer_features():
    """
    Yeh function aapke notebook ke Cell 3-6 ka poora data engineering
    BigQuery se data load karke karta hai.
    """
    print("Loading all tables from BigQuery...")
    # Load all tables
    tables_to_load = {
        'df_health': 'ai_governance_health_facilities',
        'df_env': 'ai_governance_environment_monitoring',
        'df_pop': 'ai_governance_population_demographics',
    }
    dfs = {}
    for varname, table in tables_to_load.items():
        sql = f"SELECT * FROM `{PROJECT_ID}.{BQ_DATASET}.{table}`"
        dfs[varname] = bq_client.query(sql).to_dataframe()

    # Normalize (Aapke notebook se helper functions)
    df_health = dfs['df_health']
    df_health['district_norm'] = norm_dist(df_health['district'])
    df_health[find_date_col(df_health)] = pd.to_datetime(df_health[find_date_col(df_health)], errors='coerce')
    
    df_env = dfs['df_env']
    df_env['district_norm'] = norm_dist(df_env['district'])
    df_env[find_date_col(df_env)] = pd.to_datetime(df_env[find_date_col(df_env)], errors='coerce')
    
    df_pop = dfs['df_pop']
    df_pop['district_norm'] = norm_dist(df_pop['district'])

    print("Building time-series panel...")
    # Health weekly aggregation
    health_date = find_date_col(df_health)
    patient_col = first_existing(df_health, ['patient_inflow_daily'])
    h = df_health[['district_norm', health_date, patient_col]].copy()
    h = h.dropna(subset=['district_norm', health_date])
    h['week_start'] = norm_week(h[health_date])
    h['patient_inflow_value'] = pd.to_numeric(h[patient_col], errors='coerce')
    health_week = h.groupby(['district_norm', 'week_start']).agg({'patient_inflow_value': 'mean'}).reset_index()
    health_week = health_week.rename(columns={'patient_inflow_value': 'patient_inflow_mean'})
    
    # Environment weekly aggregation
    env_date = find_date_col(df_env)
    env_metrics = [c for c in ['air_quality_index', 'pm25_level', 'pm10_level', 'water_quality_index', 'waste_collection_efficiency'] if c in df_env.columns]
    e = df_env[['district_norm', env_date] + env_metrics].copy()
    e = e.dropna(subset=['district_norm', env_date])
    e['week_start'] = norm_week(e[env_date])
    env_week = e.groupby(['district_norm', 'week_start']).agg({c: 'mean' for c in env_metrics}).reset_index()
    
    # Create Panel
    all_weeks = health_week['week_start'].unique()
    all_districts = df_pop['district_norm'].unique()
    panel = pd.MultiIndex.from_product([all_districts, all_weeks], names=['district_norm', 'week_start']).to_frame(index=False)
    panel['week_start'] = pd.to_datetime(panel['week_start']).dt.floor('D')
    
    def merge_weekly(base, weekly):
        if weekly is None or weekly.empty: return base
        temp = weekly.copy()
        temp['week_start'] = pd.to_datetime(temp['week_start']).dt.floor('D')
        return base.merge(temp, on=['district_norm', 'week_start'], how='left')
        
    panel = merge_weekly(panel, health_week)
    panel = merge_weekly(panel, env_week)
    
    pop_cols = [c for c in ['district_norm', 'district', 'population_density_per_sqkm', 'avg_household_size'] if c in df_pop.columns]
    panel = panel.merge(df_pop[pop_cols].drop_duplicates(subset=['district_norm']), on='district_norm', how='left')
    
    cont_cols = [c for c in FEATURE_ORDER if c in panel.columns and 'roll' not in c]
    for col in cont_cols:
        panel[col] = pd.to_numeric(panel[col], errors='coerce')
        panel[col] = panel.groupby('district_norm')[col].transform(lambda s: s.ffill().bfill())
        panel[col] = panel[col].fillna(panel[col].median(skipna=True))
    
    print("Creating rolling window features...")
    for window in [1, 2, 4]:
        if 'pm25_level' in panel.columns:
            panel[f'pm25_roll_{window}w'] = panel.groupby('district_norm')['pm25_level'].transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
        if 'patient_inflow_mean' in panel.columns:
            panel[f'patient_inflow_roll_{window}w'] = panel.groupby('district_norm')['patient_inflow_mean'].transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
    
    # Get *only* the most recent data for each district
    panel = panel.sort_values('week_start', ascending=False).drop_duplicates(subset=['district_norm'])
    
    # Final data, drop rows that still have NaNs
    panel = panel.dropna(subset=FEATURE_ORDER)
    
    print(f"Successfully engineered features for {len(panel)} districts.")
    return panel


# Yeh humara main function hai (Scheduler se trigger hoga)
@functions_framework.http
def update_all_district_scores(request):
    """
    Ek HTTP-triggered function jo Cloud Scheduler se run hoga.
    Yeh BigQuery se saara data load karta hai, features banata hai,
    har district ke liye AI model ko call karta hai, aur Firestore ko update karta hai.
    """
    global endpoint # Global client ka istemaal karein
    try:
        if endpoint is None:
            print("Warming up endpoint client...")
            endpoint = aiplatform.Endpoint(ENDPOINT_ID)
            
        # 1. BigQuery se data load karein aur features banayein
        df_features = load_and_engineer_features()
        
        # 2. AI Model ko call karne ke liye instances banayein
        #    (Bilkul waisa hi jaisa realtime-scorer mein kiya tha)
        instances_to_predict = []
        districts_to_update = []
        
        for index, row in df_features.iterrows():
            model_input = {}
            for feature in FEATURE_ORDER:
                model_input[feature] = float(row[feature])
            instances_to_predict.append(model_input)
            districts_to_update.append(row['district_norm'])
        
        if not instances_to_predict:
            print("No districts to score.")
            return "No districts to score", 200

        # 3. AI Model ko call karein (saare districts ek saath)
        print(f"Sending {len(instances_to_predict)} districts to AI model...")
        predictions = endpoint.predict(instances=instances_to_predict)
        
        # 4. Results ko Firestore mein save karein
        batch = db.batch() # Ek batch write ka istemaal karein (faster)
        
        print("Saving new scores to Firestore...")
        for i, prediction in enumerate(predictions.predictions):
            risk_score = prediction[0]
            risk_percentage = round(risk_score * 100, 2)
            district_name = districts_to_update[i]
            
            risk_level = "low"
            if risk_percentage > 80: risk_level = "critical"
            elif risk_percentage > 60: risk_level = "high"
            elif risk_percentage > 40: risk_level = "medium"

            # Yeh aapke dashboard ke `districtRisks` object se match karta hai
            score_doc = {
                "district": district_name,
                "risk": risk_percentage,
                "level": risk_level,
                "last_updated": google.cloud.firestore.SERVER_TIMESTAMP
            }
            
            # Hum har district ke naam ko document ID banayenge
            doc_ref = db.collection(DB_COLLECTION_NAME).document(district_name)
            batch.set(doc_ref, score_doc)
            
        batch.commit() # Saare changes ek saath save karein
        
        print(f"Successfully updated scores for {len(predictions.predictions)} districts.")
        return f"Successfully updated scores for {len(predictions.predictions)} districts.", 200

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return "Internal Server Error", 500
