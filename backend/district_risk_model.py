# district_risk_model.py
# Model to predict district risk using features from all tables

import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.preprocessing import OneHotEncoder, LabelEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from google.cloud import bigquery
import numpy as np

PROJECT_ID = "artful-affinity-476513-t7"
BQ_DATASET = "complete_db"
REGION = "us-central1"

bq_client = bigquery.Client(project=PROJECT_ID)

TABLE_MAP = {
    'df_health': 'ai_governance_health_facilities',
    'df_roads': 'ai_governance_infrastructure_roads',
    'df_safety': 'ai_governance_public_safety_reports',
    'df_services': 'ai_governance_citizen_services_requests',
    'df_env': 'ai_governance_environment_monitoring',
    'df_agri': 'ai_governance_agriculture_insights',
    'df_pop': 'ai_governance_population_demographics',
}

for varname, table in TABLE_MAP.items():
    fq_table = f"{PROJECT_ID}.{BQ_DATASET}.{table}"
    try:
        print(f"Loading `{fq_table}` -> {varname} ...")
        sql = f"SELECT * FROM `{fq_table}`"
        job = bq_client.query(sql)
        df = job.to_dataframe()
        globals()[varname] = df
        print(f"Loaded {varname}: shape={df.shape}")
    except Exception as e:
        print(f"Failed to load `{fq_table}` into {varname}: {e}")
        globals()[varname] = pd.DataFrame()

# Normalize districts
def norm_dist(series):
    return (
        series.astype(str)
              .str.strip()
              .str.lower()
              .str.replace(r"\s+", " ", regex=True)
    )

for df_name in TABLE_MAP.keys():
    df = globals()[df_name]
    if not df.empty and 'district' in df.columns:
        df['district_norm'] = norm_dist(df['district'])
    globals()[df_name] = df

# Aggregate features per district
district_features = {}

# Population
if not df_pop.empty:
    pop_agg = df_pop.groupby('district_norm').agg({
        'total_population': 'first',
        'population_density_per_sqkm': 'first',
        'avg_household_size': 'first'
    }).reset_index()
    district_features['pop'] = pop_agg

# Health
if not df_health.empty:
    health_agg = df_health.groupby('district_norm').agg({
        'patient_inflow_daily': 'mean',
        'disease_outbreak': lambda x: (x.notna() & (x != '')).sum()
    }).reset_index()
    district_features['health'] = health_agg

# Environment
if not df_env.empty:
    env_agg = df_env.groupby('district_norm').agg({
        'air_quality_index': 'mean',
        'pm25_level': 'mean',
        'pm10_level': 'mean',
        'water_quality_index': 'mean',
        'waste_collection_efficiency': 'mean'
    }).reset_index()
    district_features['env'] = env_agg

# Safety
if not df_safety.empty and 'crime_reports' in df_safety.columns:
    def parse_crime(value):
        if pd.isna(value):
            return {}
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
            if isinstance(parsed, dict):
                return parsed
            elif isinstance(parsed, list):
                counts = {}
                for item in parsed:
                    if isinstance(item, dict):
                        crime_type = item.get('type')
                        count = item.get('count', 1)
                        counts[crime_type] = counts.get(crime_type, 0) + count
                return counts
        except:
            pass
        return {}
    
    df_safety['crime_counts'] = df_safety['crime_reports'].apply(parse_crime)
    crime_rows = []
    for _, row in df_safety.iterrows():
        counts = row['crime_counts']
        for crime_type, count in counts.items():
            crime_rows.append({'district_norm': row['district_norm'], 'crime_type': crime_type, 'count': count})
    if crime_rows:
        crime_df = pd.DataFrame(crime_rows)
        safety_agg = crime_df.groupby('district_norm')['count'].sum().reset_index()
        safety_agg.rename(columns={'count': 'total_crime_count'}, inplace=True)
        district_features['safety'] = safety_agg

# Services
if not df_services.empty:
    services_agg = df_services.groupby('district_norm').size().reset_index(name='service_requests_count')
    district_features['services'] = services_agg

# Roads (target is risk from here)
if not df_roads.empty:
    roads_agg = df_roads.groupby('district_norm').agg({
        'backlog_cr': 'sum',
        'risk': 'mean',  # target
        'critical_roads_count': 'sum'
    }).reset_index()
    district_features['roads'] = roads_agg

# Merge all features
df_features = None
for key, df in district_features.items():
    if df_features is None:
        df_features = df
    else:
        df_features = df_features.merge(df, on='district_norm', how='outer')

# Fill NaN
df_features = df_features.fillna(0)

# Features and target
feature_cols = [c for c in df_features.columns if c not in ['district_norm', 'risk']]
X = df_features[feature_cols]
y = df_features['risk']

# Split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Model
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Evaluate
y_pred = model.predict(X_test)
print(f"MSE: {mean_squared_error(y_test, y_pred)}")
print(f"R2: {r2_score(y_test, y_pred)}")

# Save
joblib.dump(model, 'district_risk_model.joblib')
print('Saved district_risk_model.joblib')