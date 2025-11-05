## Proactive Governance Platform — AI-Powered Governance (ScriptDevs)

Live dashboard: https://genai-ai-governance.vercel.app/

Team: ScriptDevs
- Team leader: Aman Jaiswal
- Team members: Rohit Rathod, Rahul Sahu, Bhavik Prajapati

Problem Statement
-----------------
AI-Powered Governance: Transforming Citizen Service Delivery

Brief about the prototype
-------------------------
The Proactive Governance Platform helps government bodies monitor public well-being and infrastructure conditions before problems escalate. It brings together data, AI, and automation to support faster, smarter decision-making.

Key aspects of the prototype
- Automated Data Seeding: A Streamlit app ingests CSV and PDF files. PDF documents are processed with Google AI Document Intelligence (Document AI) and converted to structured CSV before being stored in BigQuery. Data is organised district-wise for regional analysis.
- Proactive AI Models: Models for Health, Infrastructure and Public Safety predict risks and provide actionable summaries. Models can cross-inform each other so insights in one domain may influence others.
- Dual-Pipeline Architecture: A realtime pipeline produces instant alerts from live events and sensors. A nightly batch pipeline produces district-level reports and aggregates for analytics.
- Unified API Gateway: A Cloud Function stitches together Firestore and GCS outputs into a single JSON payload consumed by the Next.js dashboard.
- Production-ready & Secure: Designed for GCP (BigQuery, Firestore, GCS, Cloud Functions, Vertex AI, IAM, VPC) to ensure secure, scalable operations.

How this is different / Why it matters
-------------------------------------
1. Proactive vs Reactive: Instead of waiting for incidents, the platform predicts and flags risk early (e.g., outbreak risk, infrastructure stress).
2. Cross-domain intelligence: Health, Safety, and Infrastructure models work together and share signals for better context-aware predictions.
3. Automated ingestion: PDF -> extracted CSV via Document AI and bulk CSV seeders reduce manual entry and speed up data onboarding.

How this solves the problem
---------------------------
1. Combine live alerts, batch analytics and ML predictions to identify early signs of issues and prioritise interventions.
2. Dual-pipeline ensures immediate operational alerts and in-depth nightly analytics for planning.
3. GCP-backed infrastructure provides security, access control and scaling for state-level rollouts.

Unique Selling Points (USP)
--------------------------
- Unified, scalable cloud architecture bridging realtime, batch and AI workflows.
- Cross-AI intelligence enabling models to share context for improved accuracy.
- Automated district-wise insights with minimal human effort.
- Actionable dashboard served via a single API layer for rapid operator workflows.

Architecture diagram
--------------------
Include or link an architecture diagram showing: Streamlit Seeder → BigQuery (Data Warehouse) → Batch scoring (Cloud Functions / Vertex AI) → GCS / Firestore (outputs) → API Gateway → Next.js Dashboard. Also show realtime scorer path (events → realtime Cloud Function → Vertex AI → Firestore → Dashboard). Add VPC/IAM boundaries.

Technologies
------------
1. Cloud & Infra: Google Cloud Platform (VPC, IAM, Cloud Functions, Cloud Scheduler)
2. Data Layer: BigQuery, Cloud Storage (GCS), Firestore
3. Ingestion: Streamlit Seeder App, Google AI Document Intelligence (Document AI)
4. ML & AI: Vertex AI (training & endpoints), Python scoring code
5. Processing: Cloud Functions (API gateway, realtime and batch jobs), Cloud Scheduler
6. Frontend: Next.js (TypeScript + React), Tailwind CSS
7. Monitoring: Cloud Logging / Cloud Monitoring

Delivered (Prototype) — Hackathon mapping
---------------------------------------
Requirement / Demand  | Implemented in prototype
--------------------- | -----------------------------------------------------------
AI-driven governance  | 3 ML models trained (Health, Infrastructure, Safety) using Vertex AI
Real-time pipeline     | Realtime Cloud Function (realtime-scorer) → Vertex AI → Firestore alerts
Automated ingestion    | Streamlit Seeder App with Document AI for PDF extraction → BigQuery
Central data store     | BigQuery used as single source of truth
Secure infra           | IAM roles, VPC patterns included; Cloud Functions deployed to GCP
Batch processing       | batch-infra-scorer, public-safety-scorer, citizen-services-scorer scheduled via Cloud Scheduler
Dashboard              | Interactive Next.js dashboard pulling from API Gateway (Cloud Function) and Firestore/GCS

- Live dashboard: [Production dashboard — genai-ai-governance.vercel.app](https://genai-ai-governance.vercel.app/) — public demo URL.
- Demo video: [Demo video (Google Drive folder)](https://drive.google.com/drive/folders/1LEh1x6UypaXSy0o8a0V5eheLdyiTF6F_?usp=sharing) — replace with a shareable direct video link if available.
- Presentation (PPT / PDF): [Prototype slide deck & demo script (PDF)](https://storage.googleapis.com/vision-hack2skill-production/innovator/USER00788870/1762366567782-GenAIExchangeHackathonPrototypeSubmissionScriptDevs.pdf)
- Architecture diagram:
  - Embedded (repo): ![Architecture diagram](architecture.png)
  - Full-size / downloadable: [Architecture diagram (PNG)](architecture.png) — commit a high-res PNG/SVG to ./docs or ./assets and update this path.
- Backend API docs / Postman:
  - Docs: [backend/README.md](backend/README.md)
  - API Gateway URL: [API Gateway (Cloud Function) URL](https://us-central1-artful-affinity-476513-t7.cloudfunctions.net/get_dashboard_data)

Note: replace local-repo paths and placeholder links with final public URLs (Cloud Console, Postman, or hosted assets) before publishing.

Hackathon details / Talking points
----------------------------------
- Team: ScriptDevs — Leader: Aman Jaiswal; Members: Rohit Rathod, Rahul Sahu, Bhavik Prajapati
- Problem: AI-Powered Governance: Transforming Citizen Service Delivery
- Demo narrative: Show Streamlit Seeder uploading a PDF, verify ingestion to BigQuery, run nightly batch job (or simulate), show realtime alert from realtime-scorer, then open dashboard to show district risk and drill into department cards and district modal.

Local development (quick start)
-------------------------------
Prereqs: Node.js, pnpm (or npm), Python 3.10+, gcloud SDK (for optional local emulation)

Frontend
1) cd frontend
2) pnpm install
3) pnpm dev
Notes: Configure `NEXT_PUBLIC_CLOUD_FUNC_URL` or use the internal `/api/enriched_dashboard` route which falls back to `get_dashboard_data.json` during dev.

Backend (local emulation)
- Many backend services are Python Cloud Functions and small apps. For local function testing you can use `functions-framework` (Python) or run scripts directly.
Example (api-gateway):
1) cd backend/api-gateway
2) python -m venv .venv
3) .venv\Scripts\Activate.ps1  # on PowerShell
4) pip install -r requirements.txt
5) functions-framework --target=get_dashboard_data --source=main.py --port=8080

Notes on env vars and secrets
- Replace the placeholders below where needed (example env vars used across services):
  - PROJECT_ID
  - NEXT_PUBLIC_CLOUD_FUNC_URL
  - BQ_DATASET, BUCKET_NAME
  - GOOGLE_APPLICATION_CREDENTIALS (for local dev/integration)

Where to find things in the repo
- frontend/: Next.js dashboard (app/ + components + lib)
- backend/api-gateway/: Cloud Function that aggregates data for the dashboard
- backend/data_ingestion/: Streamlit Seeder App (CSV/PDF ingestion)
- backend/realtime-scorer/: Realtime model scoring (model.joblib)
- backend/batch-*: Batch scoring pipelines

How to update the README with your links
--------------------------------------
1. Edit this file and replace placeholder links (video, ppt, diagram) with actual URLs.
2. Commit and push — the live Vercel preview will reflect link updates on the dashboard README page if you surface it on the site.

Credits & Contact
-----------------
ScriptDevs — Team Lead: Aman Jaiswal (contact: [hello@aman-jaiswal.tech])

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

For any operational questions, use the project owners/contact list in your organisation. This README is intentionally concise — refer to each service's source file for implementation details and comments.
