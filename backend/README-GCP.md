# Backend — GCP Deployment Reference

This document describes the backend services for the Dashboard project and how they are deployed and operated on Google Cloud Platform (GCP). It is intended as a concise reference for engineers and operators. Use the "Links" section at the end to add environment-specific URLs (console, endpoints, dashboards).

---

## Project Overview

The backend implements data ingestion, scoring and API layers that feed the governance dashboard. Core responsibilities:
- Ingest raw CSV / PDF data and load to BigQuery
- Build weekly/time-series panels and engineer features
- Score districts with ML models (real-time and batch) and persist risk metrics
- Produce department-level KPIs and forecasts for the front-end
- Serve a lightweight API gateway that stitches results for the UI

Components (repository folders):
- api-gateway — HTTP Cloud Function that assembles dashboard payloads from Firestore / GCS / BigQuery
- realtime-scorer — real-time scoring function (Vertex AI / model artifact) writing alerts to Firestore
- batch-scorer / batch-infra-scorer — scheduled batch jobs that call Vertex AI endpoints and update Firestore or GCS
- public-safety-scorer — batch scoring pipeline for public-safety data (exports to GCS)
- Citizen Services & Feedback — scoring and export jobs that generate forecasts and dashboard metrics
- data_ingestion — Streamlit app for optional manual data seeding into BigQuery (Cloud Run)
- model / PREDICTIVE MODELS — notebooks and training code used to create artifacts

---

## GCP Services Used (deployed architecture)
- BigQuery — canonical data store for raw tables and engineered feature tables
- Cloud Functions (HTTP) — api-gateway, batch triggers, and some scoring entrypoints
- Cloud Run — optional UI / ingestion app (data_ingestion)
- Cloud Scheduler — schedules HTTP triggers for batch-scorer and other periodic jobs
- Vertex AI — hosted model endpoints for predictions (deployed model.joblib wrapped in prediction container)
- Cloud Storage — store JSON metrics, model artifacts and export files
- Firestore (Document DB) — live alerts and district risk documents consumed by the frontend
- Cloud Logging & Monitoring — centralized logs, uptime checks and alerting
- IAM & Secret Manager — service accounts, permissions and secret storage for API keys and credentials

---

## Configuration & Environment

Each Cloud Function / Cloud Run service expects environment variables for project-specific configuration. Examples used in repo:
- PROJECT_ID — GCP project id
- BQ_DATASET — BigQuery dataset name
- BUCKET_NAME, PUBLIC_SAFETY_BUCKET, CITIZEN_SERVICES_BUCKET — GCS buckets used for exports
- ENDPOINT_ID / VERTEX_ENDPOINT_ID — Vertex AI endpoint id for model prediction
- HEALTH_COLLECTION / INFRA_COLLECTION — Firestore collection names
- DOC_AI_* — Document AI processor identifiers for PDF parsing (optional)

Secrets and keys should never be committed. Use Secret Manager and mount or inject at deployment time.

---

## Deployment Notes (high-level)

1. Build and publish model artifacts to a GCS bucket.
2. Deploy model to Vertex AI (create Model and Endpoint) — record ENDPOINT_ID.
3. Deploy Cloud Functions (api-gateway, batch functions, realtime functions) with required env vars and service accounts.
4. Deploy data_ingestion to Cloud Run (if used) and configure Service Account with BigQuery and Storage permissions.
5. Create Cloud Scheduler jobs that call batch function endpoints on desired cadence.
6. Ensure Firestore, BigQuery dataset and GCS buckets exist and the service accounts have appropriate roles.

Tip: Use least-privilege IAM roles (BigQuery Data Viewer/Editor, Storage Object Admin/Viewer, Firestore Datastore User, Vertex AI User as appropriate).

---

## Observability & Runbook

- Logs: Check Cloud Logging for each Cloud Function / Cloud Run service. Filter by function name.
- Monitoring: Create uptime checks for the API gateway endpoint and set alerting policies.
- Failures: If batch job fails, inspect recent Cloud Scheduler job logs and function logs. For model prediction errors, verify Vertex AI endpoint health and input shape/schema.
- Data issues: Validate source tables in BigQuery; run data_ingestion locally to reproduce parsing problems.

Quick recovery steps:
1. Roll back a function to the previous revision (Cloud Functions/Cloud Run revision history).
2. Re-deploy model to Vertex AI if endpoint is unhealthy.
3. Re-run batch job manually via HTTP trigger for on-demand backfill.

---

## Security & Compliance

- Use Secret Manager for credentials and API keys. Do not commit secrets.
- Limit service account scopes and grant roles at the minimum resource level.
- Enable VPC-SC or restricted networking if handling sensitive datasets.
- Ensure BigQuery dataset access is restricted to authorized service accounts / principals.

---

## Troubleshooting Checklist

- "Model failed to load" logs in realtime-scorer: confirm model artifact path and container image compatibility.
- "BigQuery load failed": inspect job details in BigQuery UI and verify dataset/table permissions and schema.
- "Firestore write errors": check service account permissions and Firestore region matching.
- "Document AI not configured": set DOC_AI_* env vars and ensure Document AI API enabled.

---

## Useful Commands (gcloud)

# Deploy function (example)
# gcloud functions deploy api-gateway --entry-point=get_dashboard_data --runtime python311 --trigger-http --project=PROJECT_ID --region=REGION --set-env-vars=PROJECT_ID=...,BQ_DATASET=...

# Deploy Streamlit to Cloud Run (example)
# gcloud run deploy data-ingestion --source=./backend/data_ingestion --project=PROJECT_ID --region=REGION --allow-unauthenticated --platform=managed

# Upload model artifact
# gsutil cp model.joblib gs://BUCKET_NAME/model.joblib

---
