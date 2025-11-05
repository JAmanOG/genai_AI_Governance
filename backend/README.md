# Dashboard Backend — README

This document describes the backend components for the Dashboard project. All backend services are expected to be deployed on Google Cloud Platform (GCP). This README is for reference and developer onboarding — production URLs and links are left as placeholders below.

## Overview

The backend implements multiple microservices and batch jobs that power the governance dashboard. Core responsibilities include:
- Ingesting and normalising source data (BigQuery, ingestion UI)
- Running predictive models (realtime scoring and batch scoring)
- Producing dashboard-friendly summaries and KPIs
- Storing outputs in Firestore and GCS for the frontend to consume

The repo contains multiple service folders under `backend/` — each folder typically contains a small Python app, requirements, and a Cloud Function/Cloud Run entry point.

## High-level architecture

- Data sources: BigQuery tables and uploaded CSV/PDFs
- Ingestion: `data_ingestion/` (Streamlit app) — optional, used to seed BigQuery
- Real-time scoring: `realtime-scorer/` — loads pipeline model artifact (`model.joblib`), intended to run as an HTTP endpoint (Cloud Run or Cloud Function)
- Batch scoring (infrastructure / safety / citizen services): `batch-scorer/`, `batch-infra-scorer/`, `public-safety-scorer/`, `Citizen Services & Feedback/` — scheduled via Cloud Scheduler, produce outputs to Firestore or GCS
- Model training & notebooks: `PREDICTIVE MODELS/` contains Jupyter notebooks used to prepare and train models (for reference)
- API gateway: `api-gateway/` — Cloud Function that aggregates Firestore/GCS content into a single JSON payload for the frontend
- Storage and serving: Firestore (document store for district scores & alerts), GCS (JSON blobs for dashboard feeds), BigQuery (source and intermediate tables)
- Vertex AI: optional — used if model is deployed to a Vertex AI endpoint (see notebooks & batch-scorer example)

## Important backend folders (summary)

- backend/api-gateway/ — HTTP Cloud Function that assembles dashboard data for the frontend
- backend/realtime-scorer/ — realtime scoring endpoint (loads model.joblib)
- backend/batch-scorer/ — scheduled batch job that calls Vertex AI endpoint or local model to score districts and writes to Firestore
- backend/batch-infra-scorer/ — infra-specific batch scoring pipeline
- backend/public-safety-scorer/ — public safety batch scoring wrapper
- backend/Citizen Services & Feedback/ — batch scoring for citizen services and exports to GCS
- backend/data_ingestion/ — Streamlit app to upload and load CSV/PDF into BigQuery
- backend/PREDICTIVE MODELS/ — notebooks used to build and test models (reference only)

## Key GCP services used

- BigQuery — canonical storage for raw and processed datasets
- Vertex AI — optional model hosting & online prediction (or use on-prem saved model/joblib)
- Cloud Run / Cloud Functions — run HTTP endpoints (realtime & API gateway)
- Cloud Scheduler — trigger batch scoring jobs
- Firestore (Datastore mode) — store district risk documents and alerts
- Cloud Storage (GCS) — store JSON blobs for dashboards, model artifacts, and CSV uploads
- Cloud Logging / Monitoring (Stackdriver) — logs, metrics, and alerts

## Environment variables (per-service)

Each service reads environment variables. Examples (not exhaustive):

- PROJECT_ID — GCP project id
- BQ_DATASET — BigQuery dataset containing source tables
- BUCKET_NAME (or PUBLIC_SAFETY_BUCKET / CITIZEN_SERVICES_BUCKET / DEPARTMENTS_BUCKET) — GCS bucket for blobs and model artifacts
- ENDPOINT_ID — Vertex AI endpoint id (if using Vertex AI)
- HEALTH_COLLECTION / INFRA_COLLECTION — Firestore collection names
- LOG_LEVEL, ALERT_LIMIT, KPI_* — feature flags and thresholds

Check the top of each service's `main.py` for the exact env var names used.

## Secrets & IAM

- Use Workload Identity (Cloud Run) or the Cloud Functions runtime Service Account — avoid embedding service-account JSON keys in the repo.
- Grant least-privilege roles to the service accounts: BigQuery Data Viewer / Job User, Storage Object Admin (or Storage Object Creator), Firestore Writer, Vertex AI Viewer/Invoker as required.
- Keep API keys (if any) and external secrets in Secret Manager and inject them into runtime environments.

## Local development

1. Set up Google Cloud SDK and authenticate: `gcloud auth login && gcloud auth application-default login`.
2. Export required env vars locally (example):

   export PROJECT_ID=your-project-id
   export BQ_DATASET=complete_db
   export BUCKET_NAME=your-bucket

3. For function local testing use functions-framework or run HTTP wrappers directly:
   - Install requirements from the service folder: `pip install -r requirements.txt`
   - Start: `functions-framework --target=get_dashboard_data --source=api-gateway/main.py --port=8080`

4. For the Streamlit ingestion app:
   - cd backend/data_ingestion
   - pip install -r requirements.txt
   - streamlit run app.py

5. For model testing locally, ensure `model.joblib` exists in the service folder (realtime-scorer) or update path accordingly.

## Deployment (GCP) — reference steps

Note: these are reference steps — adapt to your CI/CD.

1. Build and push container images (if using Cloud Run):
   - `gcloud builds submit --tag REGION-docker.pkg.dev/${PROJECT_ID}/REPO/backend-service:tag`
2. Deploy Cloud Run services:
   - `gcloud run deploy realtime-scorer --image IMAGE --region REGION --platform managed --service-account SERVICE_ACCOUNT`
3. Deploy Cloud Functions:
   - `gcloud functions deploy get_dashboard_data --runtime python312 --trigger-http --entry-point=get_dashboard_data --region REGION --project ${PROJECT_ID}`
4. Create Firestore and BigQuery datasets/tables as per `data.md` and the notebooks.
5. (Optional) Upload model artifact to GCS and register with Vertex AI; set ENDPOINT_ID in batch job config.
6. Configure Cloud Scheduler jobs to call batch scorer functions on the desired cadence.

## CI / CD (suggestions)

- Use Cloud Build or GitHub Actions to build and push images, and then call `gcloud run deploy` or `gcloud functions deploy`.
- Keep deployment configuration per-environment (dev/staging/prod) and inject env vars via Cloud Run service settings or Cloud Functions environment variables.

## Monitoring & Observability

- Use Cloud Logging (Stackdriver) to collect logs from Cloud Run and Cloud Functions.
- Create basic uptime checks and alerting policies for the realtime endpoint and API gateway.
- Instrument key metrics (prediction latency, error counts, number of districts scored) and expose them to Cloud Monitoring.

## Troubleshooting

- BigQuery permission errors: ensure the runtime service account has `roles/bigquery.dataViewer` and `roles/bigquery.jobUser`.
- Firestore write failures: check IAM and ensure Firestore is in the correct mode and project.
- Vertex AI invocation issues: verify `ENDPOINT_ID`, region, and that the service account has `roles/aiplatform.user` or endpoint-invoker role.
- Missing model.joblib: ensure the artifact is built and available in the runtime image or GCS path.

## Useful commands

- Run a Cloud Function locally (Functions Framework):
  `functions-framework --target=FUNCTION_NAME --source=path/to/main.py --port=8080`

- Deploy Cloud Run container:
  `gcloud run deploy SERVICE --image IMAGE --region REGION --platform managed`

- Trigger Cloud Scheduler job (manual): use `gcloud scheduler jobs run JOB_NAME`

## Links & References (placeholders)

- Architecture diagram: [PLACEHOLDER - insert architecture diagram URL]

- Production API gateway URL: [PLACEHOLDER - insert URL]

- Vertex AI model endpoint console: [PLACEHOLDER - insert Vertex AI endpoint link]

- Firestore collection (infra, alerts): [PLACEHOLDER - insert Firestore console link]

- BigQuery dataset / tables: [PLACEHOLDER - insert BigQuery console link]

- CI/CD pipeline (link): [PLACEHOLDER - insert pipeline link]

## Contact

For questions about backend deployment or credentials, contact the platform or engineering lead.

---

This README is intended as a reference. Update sections and placeholders with your production links and access instructions before sharing externally.