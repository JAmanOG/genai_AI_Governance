"""HTTP gateway that stitches together data for the governance dashboard."""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import functions_framework
from flask import make_response


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))


try:  # Optional in local dev; Cloud Functions runtime provides these deps.
    from google.api_core.exceptions import GoogleAPIError
except Exception:  # pragma: no cover - fallback when package missing
    GoogleAPIError = Exception  # type: ignore[misc,assignment]

try:
    from google.auth.exceptions import DefaultCredentialsError
except Exception:  # pragma: no cover
    DefaultCredentialsError = Exception  # type: ignore[misc,assignment]

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover
    firestore = None  # type: ignore[assignment]
    logging.warning("google-cloud-firestore not installed; API will return 500s.")

try:
    from google.cloud import storage
except Exception:  # pragma: no cover
    storage = None  # type: ignore[assignment]
    logging.info("google-cloud-storage not available; department data will be skipped.")

if TYPE_CHECKING:
    from typing import Any as _Any

    FirestoreClient = _Any
    StorageClient = _Any
else:  # pragma: no cover - runtime uses duck typing
    FirestoreClient = Any  # type: ignore[misc,assignment]
    StorageClient = Any  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Configuration via environment variables.
# ---------------------------------------------------------------------------
PROJECT_ID = os.getenv("PROJECT_ID", "artful-affinity-476513-t7")
HEALTH_COLLECTION = os.getenv("HEALTH_COLLECTION", "outbreak_alerts")
INFRA_COLLECTION = os.getenv("INFRA_COLLECTION", "infra_risk_scores")

try:
    ALERT_LIMIT = int(os.getenv("ALERT_LIMIT", "5"))
except ValueError:
    logging.warning("Invalid ALERT_LIMIT provided; defaulting to 5.")
    ALERT_LIMIT = 5

DEPARTMENTS_BUCKET = os.getenv("DEPARTMENTS_BUCKET", "citizen-services-feedback-bucket")
DEPARTMENTS_BLOB = os.getenv("DEPARTMENTS_BLOB", "csf_dashboard_metrics.json")
DEPARTMENTS_FALLBACK_PATH = os.getenv("DEPARTMENTS_FALLBACK_PATH")

PUBLIC_SAFETY_BUCKET = os.getenv("PUBLIC_SAFETY_BUCKET", "safety-dashboard-bucket")
PUBLIC_SAFETY_BLOB = os.getenv("PUBLIC_SAFETY_BLOB", "safety_dashboard_metrics.json")
PUBLIC_SAFETY_SCORES_BLOB = os.getenv("PUBLIC_SAFETY_SCORES_BLOB", "safety_scores.json")
PUBLIC_SAFETY_FALLBACK_PATH = os.getenv("PUBLIC_SAFETY_FALLBACK_PATH")

CITIZEN_SERVICES_BUCKET = os.getenv("CITIZEN_SERVICES_BUCKET", "citizen-services-feedback-bucket")
KPI_CSF_DASHBOARD_BLOB_DEFAULT = "csf_dashboard_metrics.json"
CITIZEN_SERVICES_BLOB = os.getenv("CITIZEN_SERVICES_BLOB", "csf_forecasts.json")
CITIZEN_SERVICES_FALLBACK_PATH = os.getenv("CITIZEN_SERVICES_FALLBACK_PATH")

KPI_POPULATION_VALUE = os.getenv("KPI_POPULATION_VALUE")
KPI_BUDGET_VALUE = os.getenv("KPI_BUDGET_VALUE")

CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*")
CORS_ALLOW_HEADERS = os.getenv("CORS_ALLOW_HEADERS", "Content-Type,Authorization")
CORS_ALLOW_METHODS = os.getenv("CORS_ALLOW_METHODS", "GET,OPTIONS")


_firestore_client: Optional[FirestoreClient] = None
_storage_client: Optional[StorageClient] = None


# ---------------------------------------------------------------------------
# Client helpers
# ---------------------------------------------------------------------------
def _get_firestore_client() -> Optional[FirestoreClient]:
    """Create (or reuse) the Firestore client safely."""

    global _firestore_client

    if firestore is None:
        logging.error("Firestore dependency not available.")
        return None

    if _firestore_client is not None:
        return _firestore_client

    try:
        _firestore_client = firestore.Client(project=PROJECT_ID)
        logging.info("Connected to Firestore project %s", PROJECT_ID)
    except (DefaultCredentialsError, GoogleAPIError, OSError) as exc:
        logging.exception("Failed to initialise Firestore client: %s", exc)
        _firestore_client = None

    return _firestore_client


def _get_storage_client() -> Optional[StorageClient]:
    """Create (or reuse) the Cloud Storage client."""

    global _storage_client

    if storage is None:
        return None

    if _storage_client is not None:
        return _storage_client

    try:
        _storage_client = storage.Client(project=PROJECT_ID)
        logging.info("Connected to Cloud Storage project %s", PROJECT_ID)
    except (DefaultCredentialsError, GoogleAPIError, OSError) as exc:
        logging.exception("Failed to initialise Storage client: %s", exc)
        _storage_client = None

    return _storage_client


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def _serialise(value: Any) -> Any:
    """Make Firestore/GCS payloads JSON serialisable."""

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return base64.b64encode(value).decode("ascii")

    if isinstance(value, dict):
        return {key: _serialise(val) for key, val in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_serialise(item) for item in value]

    # Firestore DocumentReference detection (duck typing to avoid imports).
    if hasattr(value, "path") and hasattr(value, "id"):
        return {"referencePath": getattr(value, "path", None)}

    return value


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------
def _fetch_district_risks(client: FirestoreClient) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}

    try:
        documents = client.collection(INFRA_COLLECTION).stream()
        for doc in documents:
            payload = doc.to_dict() or {}
            serialised = _serialise(payload)
            serialised.setdefault("id", doc.id)
            serialised.setdefault("district", doc.id)
            output[doc.id] = serialised
    except GoogleAPIError as exc:
        logging.exception("Failed to read Firestore collection '%s': %s", INFRA_COLLECTION, exc)

    return output


def _fetch_alerts(client: FirestoreClient) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []

    try:
        query = (
            client.collection(HEALTH_COLLECTION)
            .order_by("time", direction=firestore.Query.DESCENDING)
            .limit(ALERT_LIMIT)
        )

        for doc in query.stream():
            payload = doc.to_dict() or {}
            serialised = _serialise(payload)
            serialised.setdefault("id", doc.id)
            alerts.append(serialised)
    except GoogleAPIError as exc:
        logging.exception("Failed to read Firestore collection '%s': %s", HEALTH_COLLECTION, exc)

    return alerts


def _load_json_payload(resource_label: str, bucket_name: Optional[str], blob_name: Optional[str], fallback_path: Optional[str]) -> Any:
    payload: Optional[str] = None

    if bucket_name and blob_name:
        storage_client = _get_storage_client()
        if storage_client is not None:
            try:
                blob = storage_client.bucket(bucket_name).blob(blob_name)
                payload = blob.download_as_text()
                logging.info("Loaded %s from gs://%s/%s", resource_label, bucket_name, blob_name)
            except GoogleAPIError as exc:
                logging.exception("Failed to download %s from gs://%s/%s: %s", resource_label, bucket_name, blob_name, exc)

    if payload is None and fallback_path:
        try:
            with open(fallback_path, "r", encoding="utf-8") as handle:
                payload = handle.read()
                logging.info("Loaded %s from fallback path %s", resource_label, fallback_path)
        except FileNotFoundError:
            logging.warning("%s fallback path not found: %s", resource_label, fallback_path)
        except OSError as exc:
            logging.exception("Unable to read %s fallback file %s: %s", resource_label, fallback_path, exc)

    if payload is None:
        logging.warning("%s data unavailable after checking configured sources.", resource_label)
        return None

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        logging.exception("%s payload contains invalid JSON: %s", resource_label, exc)
        return None


def _normalise_departments(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [_serialise(item) if isinstance(item, dict) else {"value": _serialise(item)} for item in raw]

    if isinstance(raw, dict):
        output: List[Dict[str, Any]] = []
        for key, value in raw.items():
            record: Dict[str, Any] = {"district": key}
            if isinstance(value, dict):
                record.update(_serialise(value))
            else:
                record["value"] = _serialise(value)
            output.append(record)
        return output

    return []


def _load_departments_data() -> List[Dict[str, Any]]:
    raw_data = _load_json_payload(
        "Department metrics",
        DEPARTMENTS_BUCKET,
        DEPARTMENTS_BLOB,
        DEPARTMENTS_FALLBACK_PATH,
    )

    # Fallback: try the citizen services bucket if the first attempt failed
    if raw_data is None and CITIZEN_SERVICES_BUCKET:
        raw_data = _load_json_payload(
            "Department metrics (fallback bucket)",
            CITIZEN_SERVICES_BUCKET,
            DEPARTMENTS_BLOB,
            None,
        )

    if raw_data is None:
        return []

    return _normalise_departments(raw_data)


def _load_public_safety_data() -> Dict[str, Any]:
    dashboard = _load_json_payload(
        "Public safety dashboard metrics",
        PUBLIC_SAFETY_BUCKET,
        PUBLIC_SAFETY_BLOB,
        PUBLIC_SAFETY_FALLBACK_PATH,
    )

    scores = _load_json_payload(
        "Public safety station scores",
        PUBLIC_SAFETY_BUCKET,
        PUBLIC_SAFETY_SCORES_BLOB,
        None,
    )

    return {
        "dashboard": _serialise(dashboard) if dashboard is not None else [],
        "scores": _serialise(scores) if scores is not None else [],
    }


def _load_citizen_services_feedback_data() -> Dict[str, Any]:
    # forecasts (separate data feed)
    forecasts = _load_json_payload(
        "Citizen services forecasts",
        CITIZEN_SERVICES_BUCKET,
        CITIZEN_SERVICES_BLOB,
        CITIZEN_SERVICES_FALLBACK_PATH,
    )

    # district aggregates used by 'departments' above
    dashboard = _load_json_payload(
        "Citizen services dashboard metrics",
        CITIZEN_SERVICES_BUCKET,
        KPI_CSF_DASHBOARD_BLOB_DEFAULT,
        None,
    )

    return {
        "forecasts": _serialise(forecasts) if forecasts is not None else [],
        "dashboard": _serialise(dashboard) if dashboard is not None else [],
    }


# ---------------------------------------------------------------------------
# KPI helpers
# ---------------------------------------------------------------------------
def _format_ratio(part: int, whole: int) -> str:
    whole = max(whole, 1)
    return f"{part}/{whole}"


def _safe_number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_kpis(alerts: List[Dict[str, Any]], district_risks: Dict[str, Dict[str, Any]], departments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    critical_alerts = sum(1 for alert in alerts if str(alert.get("level", "")).lower() == "critical")
    high_risk_districts = sum(1 for record in district_risks.values() if str(record.get("level", "")).lower() == "high")

    population_value = KPI_POPULATION_VALUE
    budget_value = KPI_BUDGET_VALUE

    if population_value is None:
        pending_counts = [_safe_number(item.get("pending")) for item in departments]
        pending_counts = [value for value in pending_counts if value is not None]
        if pending_counts:
            population_value = f"{int(sum(pending_counts)):,}"
    if population_value is None:
        population_value = "Not available"

    if budget_value is None:
        budgets = [_safe_number(item.get("budget")) or _safe_number(item.get("budget_utilized_cr")) for item in departments]
        budgets = [value for value in budgets if value is not None]
        if budgets:
            budget_value = f"₹{round(sum(budgets), 2):,} Cr"
    if budget_value is None:
        budget_value = "Not available"

    total_districts = len(district_risks)

    return {
        "critical": {
            "value": critical_alerts,
            "label": "CRITICAL ALERTS",
            "iconName": "AlertCircle",
            "color": "text-destructive",
        },
        "highRisk": {
            "value": _format_ratio(high_risk_districts, total_districts),
            "label": "HIGH RISK DISTRICTS",
            "iconName": "TrendingUp",
            "color": "text-orange-500",
        },
        "population": {
            "value": population_value,
            "label": "AFFECTED POPULATION",
            "iconName": "Users",
            "color": "text-blue-500",
        },
        "budget": {
            "value": budget_value,
            "label": "BUDGET IMPACT",
            "iconName": "Wallet",
            "color": "text-emerald-500",
        },
    }


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------
def _cors_headers(response) -> None:
    response.headers["Access-Control-Allow-Origin"] = CORS_ALLOW_ORIGINS
    response.headers["Access-Control-Allow-Headers"] = CORS_ALLOW_HEADERS
    response.headers["Access-Control-Allow-Methods"] = CORS_ALLOW_METHODS


def _json_response(payload: Dict[str, Any], status_code: int = 200):
    response = make_response(json.dumps(payload, default=str), status_code)
    response.headers["Content-Type"] = "application/json"
    _cors_headers(response)
    return response


def _handle_preflight():
    response = make_response("", 204)
    _cors_headers(response)
    return response


# ---------------------------------------------------------------------------
# HTTP entry point
# ---------------------------------------------------------------------------
@functions_framework.http
def get_dashboard_data(request):
    """HTTP Cloud Function entry point."""

    if request.method == "OPTIONS":
        return _handle_preflight()

    client = _get_firestore_client()
    if client is None:
        return _json_response({"error": "Database not connected"}, 500)

    try:
        district_risks = _fetch_district_risks(client)
        alerts = _fetch_alerts(client)
        departments = _load_departments_data()
        public_safety = _load_public_safety_data()
        citizen_services_feedback = _load_citizen_services_feedback_data()
        kpi_data = _build_kpis(alerts, district_risks, departments)

        pipeline_data = {
            "health": {
                "label": "Health",
                "pipeline": "realtime-health-scorer",
                "pattern": "Real-time API (Endpoint)",
                "destination": {
                    "type": "firestore",
                    "collection": HEALTH_COLLECTION,
                },
                "dashboardComponent": "Live Alerts Feed",
                "data": alerts,
                "status": "ok" if alerts else "empty",
            },
            "infrastructure": {
                "label": "Infrastructure",
                "pipeline": "batch-infra-scorer",
                "pattern": "Batch Job (to DB)",
                "destination": {
                    "type": "firestore",
                    "collection": INFRA_COLLECTION,
                },
                "dashboardComponent": "Infrastructure Dept. View",
                "data": district_risks,
                "status": "ok" if district_risks else "empty",
            },
            "publicSafety": {
                "label": "Public Safety",
                "pipeline": "public-safety-scorer",
                "pattern": "Batch Job (to File)",
                "destination": {
                    "type": "gcs",
                    "bucket": PUBLIC_SAFETY_BUCKET,
                    "blob": PUBLIC_SAFETY_BLOB,
                },
                "dashboardComponent": "Public Safety Dept. View",
                "data": public_safety,
                "status": "ok" if (public_safety.get("dashboard") or public_safety.get("scores")) else "empty",
            },
            "citizenServicesFeedback": {
                "label": "Citizen Services & Feedback",
                "pipeline": "citizen-services-feedback",
                "pattern": "Batch Job (to File)",
                "destination": {
                    "type": "gcs",
                    "bucket": CITIZEN_SERVICES_BUCKET,
                    "blob": CITIZEN_SERVICES_BLOB,
                },
                "dashboardComponent": "Citizen Services View",
                "data": citizen_services_feedback,
                "status": "ok" if (citizen_services_feedback.get("forecasts") or citizen_services_feedback.get("dashboard")) else "empty",
            },
        }

        payload = {
            "kpiData": kpi_data,
            "districtRisks": district_risks,
            "alerts": alerts,
            "departments": departments,
            "pipelines": pipeline_data,
        }

        logging.info(
            "Assembled dashboard payload: %d districts, %d alerts, %d department entries",
            len(district_risks),
            len(alerts),
            len(departments),
        )

        return _json_response(payload)

    except Exception as exc:  # pragma: no cover - defensive guard
        logging.exception("Failed to assemble dashboard data: %s", exc)
        return _json_response({"error": str(exc)}, 500)
"""HTTP gateway that stitches together data for the governance dashboard."""

