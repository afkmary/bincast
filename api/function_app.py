"""
BinCast Backend — Azure Functions (Python v2 programming model)

Endpoints:
  POST /api/readings              -> receive + validate + store a sensor reading
  GET  /api/bins/{bin_id}/readings -> recent reading history for one bin
  GET  /api/health                -> health check (used by Application Insights /
                                       uptime monitoring, Section 4 of proposal)

Owner: Kate — matches proposal Sections 4 (Architecture) and 8 (Security & Responsible AI)
"""

import logging
import json
import azure.functions as func

from shared.validation import validate_reading, ValidationError
from shared.table_storage import save_reading, get_recent_readings

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="readings", methods=["POST"])
def ingest_reading(req: func.HttpRequest) -> func.HttpResponse:
    """
    Receives one sensor reading (see Data Contract), validates it,
    and stores it in Table Storage. Invalid readings are rejected here
    and never reach storage or the AI agent.
    """
    try:
        payload = req.get_json()
    except ValueError:
        logging.warning("Rejected reading: body was not valid JSON")
        return _json_response({"error": "Request body must be valid JSON"}, status_code=400)

    try:
        validate_reading(payload)
    except ValidationError as e:
        logging.warning("Rejected reading for bin_id=%s: %s",
                         payload.get("bin_id", "unknown"), e.errors)
        return _json_response({"error": "Invalid reading", "details": e.errors}, status_code=400)

    try:
        save_reading(payload)
    except Exception:
        logging.exception("Failed to store reading for bin_id=%s", payload.get("bin_id"))
        return _json_response({"error": "Internal storage error"}, status_code=500)

    logging.info("Stored reading for bin_id=%s fill_percentage=%s",
                 payload["bin_id"], payload["fill_percentage"])
    return _json_response({"status": "accepted", "bin_id": payload["bin_id"]}, status_code=201)


@app.route(route="bins/{bin_id}/readings", methods=["GET"])
def get_bin_readings(req: func.HttpRequest) -> func.HttpResponse:
    """Returns recent reading history for one bin (used by dashboard + agent)."""
    bin_id = req.route_params.get("bin_id")
    limit = int(req.params.get("limit", 20))

    try:
        readings = get_recent_readings(bin_id, limit=limit)
    except Exception:
        logging.exception("Failed to fetch readings for bin_id=%s", bin_id)
        return _json_response({"error": "Internal storage error"}, status_code=500)

    return _json_response({"bin_id": bin_id, "count": len(readings), "readings": readings})


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Simple liveness check — no auth required, so uptime monitors can hit it directly."""
    return _json_response({"status": "healthy"})


def _json_response(body: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, default=str),
        status_code=status_code,
        mimetype="application/json",
    )
