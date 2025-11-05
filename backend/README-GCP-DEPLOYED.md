# Backend — GCP Deployment Reference

This document describes the backend components of the Dashboard project as deployed to Google Cloud Platform (GCP). It is intended as a concise, operational reference for engineers and maintainers. Use the links section below to point to runbooks, dashboards, artifact locations and CI/CD pipelines (placeholders left intentionally blank).

---

## Overview

The backend implements data ingestion, feature engineering and scoring pipelines that power the governance dashboard. All production services are deployed on GCP and integrate with BigQuery, Firestore, Cloud Storage, Vertex AI (or managed model endpoints), Cloud Functions, Cloud Run and Cloud Scheduler.

This README is a reference; the code in this repository is the canonical source and the GCP deployment is the runtime environment.

---

## High-level architecture

- Data ingestion: Streamlit-based data seeder (data_ingestion/) — runs on Cloud Run; writes processed CSV/PDF outputs into BigQuery and optionally Cloud Storage.
- Real-time scoring: `realtime-scorer/` — exposes an HTTP endpoint (Cloud Function or Vertex AI endpoint proxy) for real-time inference and writes alerts to Firestore.
- Batch scoring (infrastructure & services): `batch-scorer/`, `batch-infra-scorer/`, `public-safety-scorer/`, `citizen services & feedback/` — scheduled jobs (Cloud Scheduler → Cloud Functions / Cloud Run) that read from BigQuery, call Vertex AI endpoints or local models, and persist results to Firestore or GCS.
- API gateway: `api-gateway/` — a Cloud Function that aggregates Firestore/GCS outputs and exposes the single API consumed by the frontend.
- Models & training artifacts: stored as joblib pickles during development and as Vertex AI Model artifacts for production deployment.

---

## GCP Services used

- BigQuery: primary analytical data store for raw and aggregated tables (datasets: e.g., `complete_db`).
- Cloud Storage (GCS): intermediary artifacts, dashboards and exported JSON blobs (used by frontend for department metrics, safety scores, etc.).
- Firestore (Native mode): small document store for real-time alerts and district risk scores.
- Cloud Functions: lightweight HTTP entry points (API gateway, batch triggers) and scheduled tasks.
- Cloud Run: containerized UI or long-running processes (data seeder Streamlit app).
- Vertex AI: model hosting (endpoints) for production inference. Models may also be called via client libraries from Cloud Functions.
- Cloud Scheduler & Pub/Sub: schedule batch scoring runs and trigger functions.
- Cloud Logging / Error Reporting / Monitoring: central logging and alerting for services.

---

## Environment & Configuration

Each deployed service reads configuration from environment variables. Common env vars used across services:

- PROJECT_ID — GCP project (default in code: `artful-affinity-476513-t7`)
- BQ_DATASET — BigQuery dataset name (e.g., `complete_db`)
- BUCKET_NAME / PUBLIC_SAFETY_BUCKET / CITIZEN_SERVICES_BUCKET — GCS buckets used for artifacts
- ENDPOINT_ID — Vertex AI endpoint id for model inference
- HEALTH_COLLECTION / INFRA_COLLECTION — Firestore collection names
- LOG_LEVEL, ALERT_LIMIT, other service-specific env vars

Make sure the Cloud Run / Cloud Function service account has least-privilege roles for BigQuery, Firestore, Storage and Vertex AI prediction.

---

## Deployment notes (high-level)

1. Build and push container images (if applicable) to Artifact Registry or GCR.
2. Deploy Cloud Functions with the appropriate entry points from the `backend/` folders.
3. Deploy Cloud Run services for containerized apps (data seeder).
4. Upload model artifacts to Vertex AI (Model upload), create an Endpoint and deploy the model.
5. Configure Cloud Scheduler jobs to trigger batch scoring functions.
6. Configure IAM roles for service accounts and enable required APIs: BigQuery, Cloud Functions, Cloud Run, Vertex AI, Firestore, Cloud Storage, Cloud Scheduler.

---

## Observability & Operations

- Logging: use Cloud Logging; ensure structured logs for errors and important events.
- Monitoring: create uptime checks and alerting policies for key endpoints (API gateway, real-time scorer endpoint).
- Error reporting: enable Error Reporting for Cloud Functions and Cloud Run services.
- Access & secrets: use Secret Manager for sensitive config (API keys, service credentials). Avoid committing secrets to repo.

---

## Security

- Principle of least privilege for service accounts.
- Use HTTPS for all public endpoints and restrict inbound access where possible.
- Store secrets in Secret Manager and mount or fetch at runtime.
- Use VPC Service Controls or organisation policies if handling sensitive data.

---

## Local development

- Many backend components can be run locally for iteration: use local BigQuery emulation where possible or run against a test dataset in GCP.
- Use `functions_framework` for Cloud Functions local testing (python -m functions_framework --target YOUR_HANDLER).
- For Cloud Run local testing, use Docker and `gcloud run services replace` / `gcloud builds submit` workflows.

---

## Useful links (fill in for your environment)

- CI/CD pipeline: 

- Production Vertex AI Model & Endpoint: 

- Artifact Registry / Container images: 

- BigQuery dataset console: 

- Firestore console collection: 

- Cloud Storage bucket(s): 

- Runbooks / on-call contact: 

---

## Troubleshooting

- Model predictions failing: verify ENDPOINT_ID, Vertex AI model health, and that the invocation payload matches the feature order used at training.
- Missing data in BigQuery: check ingestion logs and data seeder job outputs in Cloud Logging / Cloud Storage.
- Permissions errors: verify service account roles and that the runtime identity matches the configured project.

---

If you want, I can also:
- Add a short diagram of the architecture
- Produce per-service deployment commands or GitHub Actions workflow templates

(Placeholders above are intentionally blank — add your project-specific console links and runbooks.)
