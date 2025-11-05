import os
import io
from typing import List, Tuple, Optional

import streamlit as st
import pandas as pd
from google.cloud import bigquery

# Optional dependency: Document AI
try:
    from google.cloud import documentai as documentai
except Exception:  # pragma: no cover - if not installed, we'll detect at runtime
    documentai = None

# -----------------------------
# Configuration
# -----------------------------
PROJECT_ID = os.getenv("PROJECT_ID") or os.getenv("GCP_PROJECT")
BQ_DATASET = os.getenv("BQ_DATASET", "data_seeding")
DOC_AI_PROJECT_ID = os.getenv("DOC_AI_PROJECT_ID", PROJECT_ID)
DOC_AI_LOCATION = os.getenv("DOC_AI_LOCATION")  # e.g. "us" or "eu"
DOC_AI_PROCESSOR_ID = os.getenv("DOC_AI_PROCESSOR_ID")  # e.g. "abcdef123456"

# Streamlit page config
st.set_page_config(page_title="Automated Data Seeding", page_icon="📥", layout="centered")

# -----------------------------
# Helpers
# -----------------------------

def get_bq_client() -> bigquery.Client:
    """Return a BigQuery client using ADC (works on Cloud Run with bound SA)."""
    if not PROJECT_ID:
        st.warning("PROJECT_ID not set. Set env var PROJECT_ID for BigQuery operations.")
    return bigquery.Client(project=PROJECT_ID)


def get_docai_client():
    """Return a Document AI client if configured and available, else None."""
    if not DOC_AI_PROCESSOR_ID or not DOC_AI_LOCATION or not DOC_AI_PROJECT_ID:
        return None
    if documentai is None:
        return None
    return documentai.DocumentProcessorServiceClient()


def snake_case(name: str) -> str:
    import re
    s = name.strip().lower()
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s)
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    if not s:
        s = "col"
    if s[0].isdigit():
        s = f"c_{s}"
    return s


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Clean and dedupe column names
    cols = [snake_case(c) for c in df.columns]
    seen = {}
    new_cols = []
    for c in cols:
        if c in seen:
            seen[c] += 1
            new_cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            new_cols.append(c)
    df = df.copy()
    df.columns = new_cols
    return df


def derive_table_name(file_name: str) -> str:
    base = os.path.splitext(os.path.basename(file_name))[0]
    return snake_case(base)


def load_dataframe_to_bq(df: pd.DataFrame, dataset_id: str, table_name: str, client: bigquery.Client) -> Tuple[bool, str]:
    """
    --- MODIFIED FUNCTION ---
    Loads a DataFrame to BigQuery, creating or overwriting the table.
    """
    table_id = f"{client.project}.{dataset_id}.{table_name}"
    
    # --- FIX 1: ADDED create_disposition, autodetect, and changed to WRITE_TRUNCATE ---
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
        autodetect=True  # Automatically detect schema from the DataFrame
    )
    
    try:
        job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
        job.result()  # Wait for job to complete
        return True, f"Loaded {len(df)} rows into {table_id}."
    except Exception as e:
        return False, f"BigQuery load failed for {table_id}: {e}"


def process_csv(file_bytes: bytes, filename: str, dataset_id: str, client: bigquery.Client) -> Tuple[bool, str]:
    """
    --- MODIFIED FUNCTION ---
    Tries to read CSV as 'utf-8', then falls back to 'latin1'.
    """
    file_buffer = io.BytesIO(file_bytes)
    try:
        # --- FIX 2: Try standard 'utf-8' first ---
        df = pd.read_csv(file_buffer, encoding='utf-8')
    except UnicodeDecodeError:
        try:
            # --- FIX 2: If 'utf-8' fails, reset buffer and try 'latin1' ---
            st.warning(f"UTF-8 decoding failed for {filename}. Retrying with 'latin1' encoding.")
            file_buffer.seek(0) # Reset buffer to the beginning
            df = pd.read_csv(file_buffer, encoding='latin1')
        except Exception as e:
            return False, f"Failed to parse CSV {filename} with any encoding: {e}"
    except Exception as e:
         return False, f"Failed to parse CSV {filename}: {e}"


    if df.empty:
        return False, f"CSV {filename} contains no rows."

    df = clean_columns(df)
    table_name = derive_table_name(filename)
    ok, msg = load_dataframe_to_bq(df, dataset_id, table_name, client)
    return ok, msg


def process_pdf_with_docai(file_bytes: bytes, filename: str, dataset_id: str, client: bigquery.Client) -> Tuple[bool, str]:
    """
    Minimal PDF handler using Document AI. Extracts page-level text and stores it in a generic table.
    Extend this function to parse forms/tables and write to domain-specific tables.
    """
    docai_client = get_docai_client()
    if not docai_client:
        return False, (
            "Document AI is not configured. Set DOC_AI_PROJECT_ID, DOC_AI_LOCATION, and DOC_AI_PROCESSOR_ID env vars "
            "and include google-cloud-documentai in requirements."
        )

    name = docai_client.processor_path(DOC_AI_PROJECT_ID, DOC_AI_LOCATION, DOC_AI_PROCESSOR_ID)

    try:
        raw_document = documentai.RawDocument(content=file_bytes, mime_type="application/pdf")
        request = documentai.ProcessRequest(name=name, raw_document=raw_document)
        result = docai_client.process_document(request=request)
        doc = result.document

        # Build a simple record per page with text content
        records = []
        full_text = doc.text or ""
        for i, page in enumerate(doc.pages or []):
            # Derive text for the page via text segments
            page_text = []
            for segment in page.layout.text_anchor.text_segments:
                start = int(segment.start_index) if segment.start_index is not None else 0
                end = int(segment.end_index) if segment.end_index is not None else 0
                page_text.append(full_text[start:end])
            records.append({
                "file_name": filename,
                "page_number": i + 1,
                "text_content": "".join(page_text).strip(),
            })

        if not records:
            # Fallback to full text
            records = [{"file_name": filename, "page_Number": 1, "text_content": full_text.strip()}]

        df = pd.DataFrame.from_records(records)
        df = clean_columns(df)
        table_name = derive_table_name("pdf_text")
        ok, msg = load_dataframe_to_bq(df, dataset_id, table_name, client)
        return ok, msg

    except Exception as e:
        return False, f"Document AI processing failed for {filename}: {e}"


# -----------------------------
# UI
# -----------------------------
st.title("Automated Data Seeding")
st.caption("Upload CSV or PDF files to automatically parse and load into BigQuery.")

with st.sidebar:
    st.subheader("Configuration")
    st.write(f"Project: {PROJECT_ID or 'unset'}")
    dataset = st.text_input("BigQuery Dataset", value=BQ_DATASET, help="Target dataset must exist.")
    st.write("Document AI:")
    st.write(f"Processor: {DOC_AI_PROCESSOR_ID or 'unset'}")
    st.write(f"Location: {DOC_AI_LOCATION or 'unset'}")

uploaded_files = st.file_uploader(
    "Select one or more files (CSV or PDF)", type=["csv", "pdf"], accept_multiple_files=True
)

if "results" not in st.session_state:
    st.session_state.results = []

if uploaded_files:
    if st.button("Process & Load"):
        client = get_bq_client()
        results: List[Tuple[str, bool, str]] = []

        progress = st.progress(0)
        status = st.empty()

        total = len(uploaded_files)
        for idx, uf in enumerate(uploaded_files, start=1):
            fname = uf.name
            ext = os.path.splitext(fname)[1].lower()
            status.write(f"Processing {idx}/{total}: {fname}")

            try:
                file_bytes = uf.getvalue()
                if ext == ".csv":
                    ok, msg = process_csv(file_bytes, fname, dataset, client)
                elif ext == ".pdf":
                    ok, msg = process_pdf_with_docai(file_bytes, fname, dataset, client)
                else:
                    ok, msg = False, f"Unsupported file type: {ext}"
            except Exception as e:
                ok, msg = False, f"Unexpected error for {fname}: {e}"

            color = "green" if ok else "red"
            st.markdown(f"<div style='color:{color};'><strong>{fname}</strong>: {msg}</div>", unsafe_allow_html=True)
            results.append((fname, ok, msg))

            progress.progress(int(idx / total * 100))

        st.success("Processing complete.")
        st.session_state.results = results

if st.session_state.get("results"):
    st.subheader("Summary")
    success_count = sum(1 for _, ok, _ in st.session_state.results if ok)
    fail_count = len(st.session_state.results) - success_count
    st.write(f"Succeeded: {success_count} | Failed: {fail_count}")
    with st.expander("Details"):
        for fname, ok, msg in st.session_state.results:
            st.write(f"- {fname}: {'Success' if ok else 'Failed'} — {msg}")

st.markdown("---")
st.caption(
    "Note: PDF parsing uses Google Document AI if configured. Extend the PDF handler in app.py to map fields or tables to your target schema."
)
