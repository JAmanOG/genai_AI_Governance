# Governance Dashboard — Backend Reference

This repository contains reference implementations for the backend services powering the Governance Dashboard. All backend services are considered deployed to Google Cloud Platform (GCP) — this README documents the architecture, service responsibilities, configuration, and local development notes for reference only.

> NOTE: Production deployments live in GCP. Use the placeholders below to link to Cloud Console pages, Cloud Run/Cloud Functions, Firestore, BigQuery, Vertex AI, and buckets.

---

## Overview

The backend is organised under the `backend/` folder and contains multiple small services and data pipelines that produce the datasets and feeds displayed by the frontend dashboard. Each service is implemented as a Python Cloud Function, Cloud Run service, or simple script and expects to run on GCP with appropriate service accounts and permissions.

This repository is a reference; it is intentionally kept as the source of truth for code and local run instructions. All production endpoints, buckets, datasets and links are hosted on GCP — see the Links section to add your deployment URLs.

---

## Services (paths and responsibilities)

- backend/api-gateway/
  - main.py — HTTP gateway (Cloud Function) that assembles dashboard payloads by reading Firestore, Cloud Storage and fallback files.
  - Purpose: single API for frontend to fetch KPI, district risk, alerts, departments and pipeline status.

- backend/realtime-scorer/
  - main.py — realtime model scorer (Cloud Function or Vertex endpoint client) used to process single-instance payloads and write alerts to Firestore.
  - model.joblib — trained model artifact used by the function (production may use Vertex AI endpoint instead).

- backend/batch-scorer/
  - main.py — batch scoring pipeline that runs on a schedule (Cloud Function or Cloud Scheduler → Cloud Function) and writes results (Firestore / BigQuery).

- backend/batch-infra-scorer/
  - main.py — infrastructure risk scorer (batch job) used to compute infra risk per district and persist results.

- backend/public-safety-scorer/
  - main.py + safety_crime_model.py — batch job that computes public safety metrics and writes to GCS or BigQuery.

- backend/Citizen Services & Feedback/
  - app.py + main.py — batch scorer for citizen services requests that generates forecasts and dashboard aggregates. Exports JSON and optionally uploads to a bucket.

- backend/data_ingestion/
  - app.py (Streamlit) — a small web app to upload CSV/PDF and load into BigQuery (useful for seeding and local testing). Can be containerised and run on Cloud Run.

- backend/model.py and notebooks (PREDICTIVE MODELS/)
  - Notebooks and scripts used for feature engineering and training. `model.joblib` artifacts are created here for local testing or packaging.

- other helpers and scripts exist for orchestration and demo data.

---

## GCP Resources (placeholders — fill with your links)

- Project: <YOUR_GCP_PROJECT>

- Cloud Functions / Cloud Run services:
  - API Gateway (Cloud Function) URL: 
  - Realtime scorer (Cloud Function or endpoint): 
  - Batch scorer (Cloud Function): 
  - Citizen Services batch job (Cloud Function): 

- BigQuery
  - Dataset name: `complete_db` (or configured dataset)
  - Helpful link: 

- Firestore
  - Collections used: `outbreak_alerts`, `infra_risk_scores`, `district_risk_scores` (and others)
  - Helpful link: 

- Cloud Storage buckets
  - Citizen services / dashboards bucket: `citizen-services-feedback-bucket` → 
  - Public safety bucket: `safety-dashboard-bucket` → 

- Vertex AI
  - Model endpoint ID(s): ENDPOINT_ID = <your_endpoint_id_here>
  - Helpful link: 

- Monitoring & Logging
  - Cloud Monitoring dashboard: 
  - Logging (Cloud Logging): 

---

## Environment variables (per service)

General variables across services (examples):

- PROJECT_ID — GCP project id
- BQ_DATASET — BigQuery dataset name (e.g., `complete_db`)
- BUCKET_NAME / DEPARTMENTS_BUCKET / PUBLIC_SAFETY_BUCKET — GCS bucket names
- ENDPOINT_ID — Vertex AI endpoint id used by batch/online scorers
- HEALTH_COLLECTION / INFRA_COLLECTION — Firestore collection names
- KPI_POPULATION_VALUE, KPI_BUDGET_VALUE — optional KPI overrides used by api-gateway
- LOG_LEVEL — e.g. `INFO` / `DEBUG`

Each function also documents service-specific env vars in its source file header comments.

---

## Local development (reference)

This repository can be used for local testing and debugging. The instructions below are reference examples — production traffic should use the deployed GCP services.

- Cloud Functions (local): use the Functions Framework to run a function locally for testing. Example:

  - Install dependencies in a venv and run the function with the same function name as the entry-point.

- Data ingestion Streamlit app:

  - `backend/data_ingestion/app.py` can be run locally with Streamlit for ad-hoc dataset uploads and BigQuery seeding.

- Model testing:

  - Notebook training code is in `backend/PREDICTIVE MODELS/`. After training, `joblib.dump` produces `model.joblib` for local scoring.

Notes:
- Ensure Application Default Credentials are available locally (`gcloud auth application-default login`) if you call GCP APIs from local code.
- Use a development BigQuery dataset or emulator to avoid writing to production tables.

---

## Observability & Ops

- Logs: Cloud Logging (formerly Stackdriver) for Cloud Functions and Cloud Run.
- Metrics/alerts: Cloud Monitoring configured per service (recommended alerts for function failure rates and high-latency predictions).
- Storage: GCS buckets for batch exports and frontend JSON artifacts.

---

## Security

- Follow principle of least privilege for service accounts. Grant BigQuery/DataEditor, Storage Object Admin (or more restrictive roles), Firestore roles where appropriate.
- Do not store secrets in repository. Use Secret Manager for API keys, DB credentials, or other sensitive values.

---

## Troubleshooting

- Missing data in frontend: check API Gateway logs and whether Firestore / GCS objects are present; API will fall back to files under `.next`/fallback or local JSON files if configured.
- Model errors: check batch/online scorer logs and ensure Vertex endpoint exists and is reachable. Verify feature shape matches expected FEATURE_ORDER.

---

## Contributing / Changes

- Use the notebooks under `backend/PREDICTIVE MODELS/` to re-train models.
- When updating model artifacts, ensure the serving container (Vertex or sklearn container) expects the same pipeline signature.

---

## Links (fill-in)

- GCP Project Console: 
- API Gateway (Cloud Function) URL: 
- Realtime Scorer endpoint: 
- Batch Scorer Cloud Function: 
- Citizen Services bucket (GCS): 
- BigQuery dataset console: 
- Vertex AI model / endpoint: 
- Monitoring dashboard: 

---

For any operational questions, use the project owners/contact list in your organisation. This README is intentionally concise — refer to each service's source file for implementation details and comments.
