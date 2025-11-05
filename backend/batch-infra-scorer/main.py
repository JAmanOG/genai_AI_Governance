import functions_framework
import google.cloud.firestore
import os
import json
from datetime import datetime

# --- YEH AAPKE SCRIPT KA NAAM HAI ---
import infra_model 

# --- !!! CONFIGURATION !!! ---
PROJECT_ID = "artful-affinity-476513-t7"
BQ_DATASET = "complete_db"
# Naya collection, khaas infrastructure ke liye
DB_COLLECTION_NAME = "infra_risk_scores" 
# ------------------------------

# Global client
db = google.cloud.firestore.Client()

@functions_framework.http
def run_infra_batch_score(request):
    """
    Cloud Scheduler se trigger hone wala function.
    1. Aapke 'infra_model.py' script ko run karta hai.
    2. Results ko Firestore mein save karta hai.
    """
    try:
        # 1. Aapke script ko run karein
        print("Running infra_model.score_and_export...")
        # Hum /tmp/ folder ka istemaal karenge (jo Cloud Functions mein writable hai)
        output_dir = "/tmp"
        as_of = datetime.now() 
        
        per_road_df, district_dict = infra_model.score_and_export(
            project_id=PROJECT_ID,
            dataset=BQ_DATASET,
            as_of_date=as_of,
            output_dir=output_dir
        )
        
        print(f"Model run complete. Scored {len(per_road_df)} roads.")
        print(f"Aggregated {len(district_dict)} districts.")

        # 2. Results ko Firestore mein save karein
        if not district_dict:
            print("No district metrics generated.")
            return "No metrics generated", 200

        batch = db.batch() # Ek batch write ka istemaal karein (faster)
        
        print(f"Saving {len(district_dict)} district scores to Firestore collection '{DB_COLLECTION_NAME}'...")
        
        for district_name, data in district_dict.items():
            # Hum district ke naam ko document ID banayenge
            doc_ref = db.collection(DB_COLLECTION_NAME).document(district_name)
            
            # Aapke dashboard data schema se fields add karein
            data_to_save = {
                "district": district_name,
                "risk": data.get("metrics", [0,0,0])[0], # Avg Repair Prob
                "level": "high" if data.get("critical_roads", 0) > 0 else "medium", # Simple logic
                "backlog_cr": data.get("metrics", [0,0,0])[1],
                "avg_impact": data.get("metrics", [0,0,0])[2],
                "critical_roads_count": data.get("critical_roads", 0),
                "top_factor": data.get("top_factor_line", "N/A"),
                "last_updated": google.cloud.firestore.SERVER_TIMESTAMP
            }
            batch.set(doc_ref, data_to_save)
            
        batch.commit() # Saare changes ek saath save karein
        
        print("Firestore update complete.")
        return f"Successfully scored and saved {len(district_dict)} districts.", 200

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return "Internal Server Error", 500