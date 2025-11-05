# Automated Data Seeding App (Streamlit + Cloud Run)

A simple, production-ready web UI for uploading CSVs and PDFs and automatically loading parsed data into BigQuery. PDFs are processed with Google Document AI (optional).

## Features

- Streamlit UI for multi-file upload (CSV/PDF)
- CSVs parsed with pandas; column names normalized to snake_case
- BigQuery ingestion via Python BigQuery client
- PDFs optionally parsed by Document AI; page-level text loaded into BigQuery (easy to extend to forms/tables)
- Deployable on Cloud Run with a dedicated Service Account

## App configuration

The app reads configuration from environment variables:

- PROJECT_ID: Google Cloud project ID (falls back to GCP_PROJECT)
- BQ_DATASET: Target BigQuery dataset (default: `data_seeding`) — must exist
- DOC_AI_PROJECT_ID: Project ID for Document AI (defaults to PROJECT_ID)
- DOC_AI_LOCATION: Location for Document AI processor, e.g. `us` or `eu`
- DOC_AI_PROCESSOR_ID: Document AI Processor ID (Form Parser / Universal / Document OCR)

## Run locally

Prereqs: Python 3.10+ and Google credentials with access to BigQuery and (optionally) Document AI.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export PROJECT_ID=your-project
export BQ_DATASET=data_seeding
# Optional for PDFs
export DOC_AI_PROJECT_ID=your-project
export DOC_AI_LOCATION=us
export DOC_AI_PROCESSOR_ID=your-processor-id

streamlit run app.py
```

Create the dataset if it doesn't exist:

```bash
bq --project_id "$PROJECT_ID" mk --dataset "$PROJECT_ID:$BQ_DATASET" || true
```

## Containerize and deploy to Cloud Run

### 1) Enable required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  bigquery.googleapis.com \
  documentai.googleapis.com
```

### 2) Create a service account and grant roles

```bash
SA=data-seeding-sa
PROJECT_ID=$(gcloud config get-value core/project)

gcloud iam service-accounts create "$SA" \
  --display-name "Data Seeding Service Account"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:$SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role roles/bigquery.dataEditor

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:$SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role roles/bigquery.jobUser

# Required for Document AI processing (optional if you won't upload PDFs)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:$SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role roles/documentai.editor
```

Create the BigQuery dataset if needed:

```bash
bq mk --dataset "$PROJECT_ID:$BQ_DATASET" || true
```

### 3) Build and push container

Using Cloud Build and Artifact Registry (recommended):

```bash
REGION=us-central1
REPO=data-seeding
IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/app:latest

# Create a Docker repository once
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Data seeding images" || true

# Build and push
gcloud builds submit --tag "$IMAGE" .
```

Alternatively, use GCR (legacy):

```bash
IMAGE=gcr.io/$PROJECT_ID/data-seeding:latest
gcloud builds submit --tag "$IMAGE" .
```

### 4) Deploy to Cloud Run

```bash
SERVICE=data-seeding
REGION=us-central1

# Choose the same IMAGE you built above
# IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/data-seeding/app:latest
# or IMAGE=gcr.io/$PROJECT_ID/data-seeding:latest

# Deploy
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --service-account "$SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars PROJECT_ID=$PROJECT_ID \
  --set-env-vars BQ_DATASET=data_seeding \
  --set-env-vars DOC_AI_PROJECT_ID=$PROJECT_ID \
  --set-env-vars DOC_AI_LOCATION=us \
  --set-env-vars DOC_AI_PROCESSOR_ID=your-processor-id
```

Output will include a public URL for the service.

## How it works

- CSV: The app reads the file with pandas (tries UTF-8, Latin-1, CP1252 encodings), cleans column names to snake_case, and loads to BigQuery as `<dataset>.<file_basename>` using truncate semantics (overwrites existing tables). Tables are auto-created if they don't exist.
- PDF: If Document AI is configured, the app sends the PDF to the processor and stores page-level text into `<dataset>.pdf_text`. You can extend the PDF handler in app.py to parse forms/tables and write to domain-specific tables.

## Extending PDF parsing (optional)

In `app.py`, update `process_pdf_with_docai` to do any of the following:

- Extract Key-Value pairs from `doc.pages[*].form_fields` and write to a `kv_pairs` table.
- Iterate tables via `doc.pages[*].tables` to build rows and load to `inferred_table_<name>`.
- Normalize fields to a target schema and upsert into business tables.

## Security

- Cloud Run uses a bound Service Account; no key files are required.
- BigQuery roles are scoped to the dataset/project as needed.
- Document AI is optional and can be omitted by not setting its env vars.

## Troubleshooting

- Permission errors: Verify the Cloud Run service account has BigQuery and Document AI roles. Check dataset-level ACLs if using restricted datasets.
- Dataset not found: Ensure `BQ_DATASET` exists or create it with `bq mk`. The app does not create datasets automatically.
- CSV encoding issues: The app tries UTF-8, Latin-1, and CP1252 encodings. If your CSV uses a different encoding, it may fail.
- PDF not processed: Confirm `DOC_AI_*` env vars and that the processor is in the specified location.
- Large CSVs: For very large files, consider chunked ingest or direct BigQuery load jobs. The current implementation reads into memory for simplicity.

## License

MIT
