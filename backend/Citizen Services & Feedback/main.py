import functions_framework
import os
from datetime import datetime
import app as scorer

# --- Configuration ---
PROJECT_ID = os.getenv("PROJECT_ID") or "artful-affinity-476513-t7"
BQ_DATASET = os.getenv("BQ_DATASET") or "complete_db"
BUCKET_NAME = os.getenv("BUCKET_NAME") or "citizen-services-feedback-bucket"

@functions_framework.http
def run_citizen_services_batch_score(request):
    """
    An HTTP-triggered Cloud Function that runs the citizen services batch scorer.
    It calls the scoring script and logs the outcome.
    """
    try:
        print("Starting citizen services batch scoring process...")
        
        as_of = datetime.now()
        
        # Call the main function from the scoring script
        features, agg = scorer.score_and_export(
            project_id=PROJECT_ID,
            dataset=BQ_DATASET,
            as_of=as_of,
            output_dir="/tmp",
            bucket_name=BUCKET_NAME
        )
        
        success_message = f"Successfully scored {len(features)} district×service entries and generated aggregates for {len(agg)} districts."
        print(success_message)
        return success_message, 200

    except Exception as e:
        error_message = f"An error occurred during the scoring process: {e}"
        print(error_message)
        return error_message, 500
