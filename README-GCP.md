# Governance Dashboard — Backend (GCP) reference

This document describes the backend components for the Governance Dashboard project and how they are deployed on Google Cloud Platform (GCP). This README is informational only — production services are assumed to be deployed in GCP. Use this file as a reference for architecture, configuration, and local development workflow.

> Links / consoles / dashboards
>
> - GCP Project:  
> - Firestore Console:  
> - BigQuery Console:  
> - Cloud Functions / Cloud Run:  
> - Vertex AI / Endpoints:  
> - Cloud Storage (buckets):  
>

Summary
-------
The backend contains multiple services and batch jobs that prepare and serve data for the frontend dashboard. Core responsibilities:

- Ingest and normalise domain data (BigQuery tables) — data_ingestion app (Streamlit) for manual uploads.
- Real-time scoring (HTTP endpoint) — realtime-scorer (sklearn/XGBoost) for per-instance risk scoring.
- Batch scoring pipelines — batch-scorer, batch-infra-scorer, public-safety-scorer, citizen services scorer.
- API gateway — a Cloud Function that aggregates and exposes the dashboard payload (kpis, alerts, district risk map, department metrics).
- Storage & persistence — BigQuery (raw and engineered tables), Firestore (alerts & district risk documents), Cloud Storage (JSON feeds and artifacts), Vertex AI (model hosting) and optionally GCS for model artifacts.

Repository layout (relevant folders)
-----------------------------------
- backend/api-gateway — Cloud Function that assembles dashboard payload (get_dashboard_data)
- backend/realtime-scorer — real-time scoring function (loads model.joblib)
- backend/batch-scorer — batch scoring runner that calls Vertex AI endpoint and writes to Firestore
- backend/batch-infra-scorer — infra-specific batch scorer
- backend/public-safety-scorer — public safety batch job
- backend/Citizen Services & Feedback — citizen services scoring + export
- backend/data_ingestion — Streamlit app for CSV/PDF ingestion -> BigQuery (Cloud Run)
- backend/live-dashboard — small HTTP app used for live demo views (if present)
- backend/PREDICTIVE MODELS — notebooks and model training scripts (for reference)

GCP architecture (high level)
-----------------------------
- BigQuery: canonical raw tables and engineered tables used by model pipelines.
- Vertex AI: model hosting (prediction endpoint) or use self-hosted scoring container if preferred.
- Cloud Functions / Cloud Run: HTTP endpoints for API gateway and batch triggers.
- Cloud Scheduler: triggers batch functions on a schedule.
- Firestore: stores alerts and per-district risk documents used by the dashboard.
- Cloud Storage: stores JSON output for dashboard feeds and model artifacts.

Configuration (environment variables)
-------------------------------------
Each service uses environment variables. Typical variables used across the backend:

- PROJECT_ID: GCP project id
- BQ_DATASET: BigQuery dataset name (e.g., complete_db)
- BUCKET_NAME / PUBLIC_SAFETY_BUCKET / CITIZEN_SERVICES_BUCKET / DEPARTMENTS_BUCKET: GCS buckets for artifacts and JSON feeds
- HEALTH_COLLECTION / INFRA_COLLECTION: Firestore collections used by API gateway
- ENDPOINT_ID: Vertex AI endpoint id (when calling hosted model)
- KPI_POPULATION_VALUE / KPI_BUDGET_VALUE: optional KPI overrides for API
- ALERT_LIMIT: number of recent alerts to return
- OTHER: service-specific env vars (see each service's requirements.txt / main.py for details)

Security & secrets
------------------
- Use Secret Manager or environment variables in Cloud Run / Cloud Functions to store API keys and secrets (do not commit secrets to repo).
- Vertex AI and BigQuery access should be via service accounts with least privilege.

Local development
-----------------
A lightweight path to run services locally for testing:

1. Local Python virtual environment
   - python -m venv .venv
   - source .venv/bin/activate (or .venv\Scripts\activate on Windows)
   - pip install -r backend/<service>/requirements.txt

2. Run API Gateway locally (requires Google credentials or mock data)
   - Set PROJECT_ID and GOOGLE_APPLICATION_CREDENTIALS for service account with read access to Firestore/BigQuery
   - Start function locally or run the Flask handler (the gateway is implemented as a Cloud Function).

3. Data ingestion (Streamlit) locally
   - cd backend/data_ingestion
   - pip install -r requirements.txt
   - streamlit run app.py

4. Model & scorer testing
   - Place model.joblib in realtime-scorer folder for local scoring
   - Test predict functions by invoking endpoints or calling main functions directly

Deployment notes (GCP)
----------------------
- data_ingestion: deploy to Cloud Run (containerized). Use the Dockerfile in backend/data_ingestion/.
- API gateway: deploy as a Cloud Function (Python runtime) with proper env vars for PROJECT_ID and collection names.
- realtime-scorer: deploy as Cloud Function or Cloud Run depending on latency and cold start requirements. Ensure model artifact (model.joblib) is available in the function/container or loaded from GCS.
- batch-scorer / batch-infra-scorer / public-safety-scorer / citizen services scorer: deploy as Cloud Functions or Cloud Run jobs and execute via Cloud Scheduler. They call Vertex AI endpoint or run internal model scoring.
- Vertex AI: upload model artifact (or container) and create a prediction endpoint. Set ENDPOINT_ID in batch pipelines.
- Firestore: ensure collection names are created and security rules allow the service account to update documents.

Operational tips
----------------
- Logging: send logs to Cloud Logging; include structured logs (json) where possible.
- Monitoring: use Cloud Monitoring alerts for function failures, high error rates, or pipeline lag.
- Secrets: use Secret Manager and mount as environment variables in Cloud Run or reference in Cloud Functions.
- CI/CD: use Cloud Build or GitHub Actions to build images and deploy to Cloud Run / Cloud Functions. Store infrastructure deployment steps in a pipeline (IaC) when possible.

Troubleshooting checklist
-------------------------
- 500s from API gateway: check Firestore / Storage permissions and existence of configured buckets / collections.
- Missing model at runtime: verify model.joblib is available in the runtime or load from GCS.
- Batch job returns empty predictions: ensure Vertex AI endpoint id is correct and service account has aiplatform.predict permission.
- CSV ingestion errors: data_ingestion app attempts utf-8 then latin1; validate CSV encodings and schema.

Where to edit source of truth
-----------------------------
- BigQuery table schemas and raw data: managed in BigQuery console and ingestion jobs.
- Model training notebooks: backend/PREDICTIVE MODELS/ (notebooks for reference).
- Production configs and links: add here in the Links section (top) for consoles, dashboards and runbooks.

Contact & runbooks
------------------
- On-call / owner: __________________
- Runbook link:  

Notes
-----
This README is a living reference. Add deployment links and runbook URLs in the Links section above after provisioning resources.
