import functions_framework
import os
from datetime import datetime
import importlib

# Import the scoring script. Since the filename has hyphens, we use importlib.
scorer = importlib.import_module("safety_crime_model")

# --- Configuration ---
PROJECT_ID = os.getenv("PROJECT_ID") or "artful-affinity-476513-t7"
BQ_DATASET = os.getenv("BQ_DATASET") or "complete_db"
BUCKET_NAME = os.getenv("BUCKET_NAME") or "safety-dashboard-bucket"

@functions_framework.http
def run_safety_crime_batch_score(request):
    """
    An HTTP-triggered Cloud Function that runs the public safety crime batch scorer.
    It calls the scoring script and logs the outcome.
    """
    try:
        print("Starting public safety crime batch scoring process...")
        
        as_of = datetime.now()
        
        # Call the main function from the scoring script
        features, agg = scorer.score_and_export(
            project_id=PROJECT_ID,
            dataset=BQ_DATASET,
            as_of=as_of,
            bucket_name=BUCKET_NAME
        )
        
        success_message = f"Successfully scored {len(features)} stations and generated aggregates for {len(agg)} districts."
        print(success_message)
        return success_message, 200

    except Exception as e:
        error_message = f"An error occurred during the scoring process: {e}"
        print(error_message)
        # It's good practice to return a 500 status code for internal server errors.
        return error_message, 500
