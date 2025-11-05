import functions_framework
import numpy as np
import joblib
import json
import xgboost as xgb
import logging
import pandas as pd
import os
import google.cloud.firestore  

# --- Model aur Features ---
try:
    # Model ko cold start par ek baar load karein
    model = joblib.load("model.joblib")
    logging.info("✅ Model loaded successfully.")
except Exception as e:
    logging.error(f"❌ Model failed to load: {e}")
    model = None

# Yeh 14 features hain (aapke notebook se)
FEATURES = [
    "pm25_level", "pm10_level", "air_quality_index", "water_quality_index",
    "waste_collection_efficiency", "population_density_per_sqkm",
    "avg_household_size", "patient_inflow_mean",
    "pm25_roll_1w", "pm25_roll_2w", "pm25_roll_4w",
    "patient_inflow_roll_1w", "patient_inflow_roll_2w", "patient_inflow_roll_4w"
]
# ------------------------------

# --- !!! YEH NAYA HAI: Firestore Client ---
# Client ko global rakhein taaki woh "warm" rahe
try:
    db = google.cloud.firestore.Client()
    COLLECTION_NAME = "outbreak_alerts" # Aapka collection naam
    logging.info("✅ Firestore client initialized successfully.")
except Exception as e:
    logging.error(f"❌ Firestore client failed to initialize: {e}")
    db = None
# ------------------------------


@functions_framework.http
def score_new_data(request):
    try:
        if model is None:
            logging.error("Model object is None. Cannot predict.")
            return {"error": "Model not loaded"}, 500
        
        if db is None:
            logging.error("Database client is None. Cannot save.")
            return {"error": "Database not connected"}, 500

        data = request.get_json(force=True)
        if not data:
            return {"error": "No JSON body found"}, 400

        # --- 1. Model Se Prediction Lena ---
        input_data_dict = {f: [data.get(f, 0)] for f in FEATURES}
        df = pd.DataFrame.from_dict(input_data_dict)
        probabilities = model.predict_proba(df)
        risk_score = probabilities[0][1] # Class 1 (Outbreak) ki probability
        risk_percentage = round(risk_score * 100, 2)
        
        # --- 2. District Ka Naam Lena ---
        district_name = data.get("district", "Unknown")
        logging.info(f"Prediction received for {district_name}: {risk_percentage}%")

        # --- 3. Dashboard Format Taiyaar Karna ---
        risk_level = "low"
        if risk_percentage > 80: risk_level = "critical"
        elif risk_percentage > 60: risk_level = "high"
        elif risk_percentage > 40: risk_level = "medium"
            
        alert_doc = {
            "district": district_name, 
            "level": risk_level,
            "title": f"Outbreak Risk: {risk_percentage}%",
            "description": "ETA: 14 Days (model T+14)",
            "trigger": f"Water Quality: {data.get('water_quality_index')}, PM2.5: {data.get('pm25_level')}",
            "actions": ["Deploy Health Teams", "Sanitation Drive"] if risk_level in ["high", "critical"] else ["Monitor"],
            "time": google.cloud.firestore.SERVER_TIMESTAMP,
            "raw_score": float(risk_score),
            "input_features": data 
        }

        # --- 4. Firestore Mein Save Karna (Step J) ---
        db.collection(COLLECTION_NAME).document().set(alert_doc)
        logging.info(f"Successfully saved alert for {district_name} to Firestore.")

        # --- 5. Final Response Bhejna ---
        return json.dumps({
            "status": "success",
            "district_name": district_name,
            "outbreak_risk_score": float(risk_score)
        }), 200, {"Content-Type": "application/json"}

    except Exception as e:
        logging.exception("Prediction failed")
        return json.dumps({
            "error": f"Prediction failed: {str(e)}"
        }), 500, {"Content-Type": "application/json"}