# Backend — GCP Deployment Reference

This document briefly describes the backend components for the Dashboard project and how they are deployed on Google Cloud Platform. It is intended as a reference (not an operational runbook). Leave the placeholder links blank so they can be filled with the real GCP console / service URLs.

## Overview

The backend is composed of multiple server components (Cloud Functions, Cloud Run services, Batch jobs, and Vertex AI endpoints) that produce data for the frontend dashboard. All production/staging deployments are assumed to be hosted on GCP.

## High-level architecture

- API Gateway (Cloud Function)
  - Path: `backend/api-gateway`
  - Purpose: Aggregates Firestore / GCS / BigQuery outputs into a single dashboard payload (get_dashboard_data).
  - Runtime: Cloud Functions (HTTP)

- Real-time scorer (realtime-scorer)
  - Path: `backend/realtime-scorer`
  - Purpose: Low-latency scoring for incoming events; writes alerts to Firestore collection `outbreak_alerts`.
  - Runtime: Cloud Functions / Endpoint (depending on configuration)
  - Model artifact: `model.joblib` (used locally by function) or Vertex AI endpoint when available.

- Batch scorers
  - Batch infrastructure scorer: `backend/batch-infra-scorer` (scheduled job, writes to Firestore `infra_risk_scores`)
  - Public safety scorer: `backend/public-safety-scorer` (exports metrics to GCS)
  - Citizen services & feedback scorer: `backend/Citizen Services & Feedback` (exports `csf_forecasts.json` and `csf_dashboard_metrics.json` to GCS)
  - Batch runner: `backend/batch-scorer` (optional wrapper that can call Vertex AI endpoints)

- Data ingestion UI
  - Path: `backend/data_ingestion`
  - Purpose: Streamlit app to upload CSV/PDFs and load into BigQuery. Deployable on Cloud Run.

- Supporting artifacts
  - BigQuery dataset: `complete_db` (example) — stores raw tables used for feature engineering
  - Firestore collections: `outbreak_alerts`, `infra_risk_scores`, `district_risk_scores` (examples)
  - GCS buckets: `citizen-services-feedback-bucket`, `safety-dashboard-bucket`, `safety-dashboard-bucket` (examples)

## Key environment variables (per service)

- PROJECT_ID — GCP project ID
- BQ_DATASET — BigQuery dataset used by jobs (e.g. `complete_db`)
- BUCKET_NAME or specific bucket envs — GCS bucket names for outputs
- ENDPOINT_ID — Vertex AI Endpoint ID (if using hosted model)
- HEALTH_COLLECTION / INFRA_COLLECTION — Firestore collection names used by API Gateway
- DOC_AI_PROCESSOR_ID, DOC_AI_LOCATION — (data ingestion) Document AI Processor configuration

## Operational notes

- Models
  - Training and model artifacts live in `backend/PREDICTIVE MODELS` and `backend` scripts produce `model.joblib`. For production use prefer Vertex AI models/endpoints and set ENDPOINT_ID in batch functions.

- Scheduling
  - Batch scorers should be scheduled with Cloud Scheduler to invoke the relevant Cloud Function HTTP trigger.

- Permissions
  - Each Cloud Run / Cloud Function service account needs least-privilege roles to access BigQuery, Firestore and Cloud Storage (e.g. roles/bigquery.dataViewer, roles/datastore.user, roles/storage.objectAdmin as required).

- Monitoring & logging
  - Use Cloud Logging and Cloud Monitoring (Uptime checks, Error Reporting, Alerts) to detect runtime errors and SLO breaches.

## How to call / sample endpoints

- Dashboard API (Cloud Function):
  - GET /get_dashboard_data  — returns assembled dashboard payload (kpiData, districtRisks, alerts, departments, pipelines)
  - (placeholder link):

- Real-time scoring endpoint (example):
  - POST /realtime/score — accepts JSON event and returns risk/alert
  - (placeholder link):

- Citizen services outputs (GCS):
  - `gs://<bucket>/csf_forecasts.json`
  - `gs://<bucket>/csf_dashboard_metrics.json`

## Quick local / developer run notes

- Many backend modules are runnable locally for development. Typical steps:
  1. Activate Python venv and install requirements for the service you are working on (pip install -r requirements.txt)
  2. Set environment variables (PROJECT_ID, BQ_DATASET, BUCKET_NAME, etc.)
  3. Use the Functions Framework for local testing of HTTP functions:
     - `pip install functions-framework` and run `functions-framework --target=get_dashboard_data --port=8080`

- Data ingestion (Streamlit):
  - `python -m venv .venv && .venv\Scripts\activate` (Windows)
  - `pip install -r requirements.txt`
  - `streamlit run app.py`

## CI/CD & deployment (summary)

- Build and push container images for Cloud Run using Cloud Build / Artifact Registry.
- Deploy Cloud Functions with `gcloud functions deploy` or via Cloud Build steps.
- Use Cloud Scheduler to trigger periodic batch runs.

## Security & best practices

- Do not store service account keys in the repo. Use Workload Identity (GKE) or bound service accounts (Cloud Run / Cloud Functions).
- Restrict access to GCS buckets and BigQuery datasets using IAM at project or resource level.
- Validate and sanitize all incoming payloads before scoring.

## Links / references

- GCP Project console:  

- Cloud Functions dashboard:  

- Vertex AI endpoints:  

- BigQuery dataset:  

- Firestore collections console:  


---

This README is a high-level reference describing which backend components exist and how they map to GCP resources. For runbooks, deployment scripts, or IaC please consult infra-specific documentation or the `backend/*/README-GCP.md` files.
