"""
BinCast Backend — Azure Functions (Python v2 programming model)

Endpoints
---------
  POST   /api/readings                  ingest: validate -> classify -> store
  GET    /api/bins                      fleet summary for the dashboard
  GET    /api/bins/{bin_id}/readings    reading history for one bin
  GET    /api/decisions                 decision log (all bins, newest first)
  POST   /api/decisions                 human approve/reject of a recommendation
  GET    /api/health                    liveness check

The ingest path is the whole product in one function:
    device -> validate -> AI agent -> store reading + decision -> dashboard

Owner: Kate (endpoints/storage) with Anh Quan (agent call).
Matches proposal Sections 4 (Architecture), 6 (Workflow) and 8 (Security).
"""

import logging
import json
import os
from datetime import datetime, timezone

import azure.functions as func

from shared.validation import validate_reading, ValidationError
from shared import table_storage as store

# The agent lives in agent/agent.py at the repo root so Anh Quan can work on
# it and test it without touching the Functions project. deploy.yml copies it
# into api/shared/ at build time (see the "Bundle the agent" step).
#
# If it isn't there, ingest still works -- readings are stored, they just
# arrive with no recommendation. A missing agent must not lose data.
try:
    from shared import agent as bincast_agent
    AGENT_AVAILABLE = True
except ImportError:  # pragma: no cover
    logging.warning("agent module not bundled — readings will be stored unclassified")
    bincast_agent = None
    AGENT_AVAILABLE = False

app = func.FunctionApp()

# Read endpoints are anonymous so the dashboard (a static SPA) can call them
# without embedding a key in shipped JavaScript, where it would be readable by
# anyone. Ingest requires a function key because that's the only write path
# exposed to the open internet.
#
# NOTE for the Section 8 write-up: POST /decisions is currently ANONYMOUS for
# demo simplicity. In a real deployment it would sit behind Entra ID auth,
# since it records who approved a pickup. Say this out loud in the report
# rather than hoping nobody notices.
ANON = func.AuthLevel.ANONYMOUS

# Set to your deployed dashboard origin before the demo. "*" is fine for
# local dev and the classroom demo; it is not fine for a graded security
# section, so change it and mention that you did.
ALLOWED_ORIGIN = os.environ.get("BINCAST_ALLOWED_ORIGIN", "*")


# =============================================================================
# Ingest
# =============================================================================

@app.route(route="readings", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.FUNCTION)
def ingest_reading(req: func.HttpRequest) -> func.HttpResponse:
    """
    Receives one sensor reading, validates it against the data contract,
    runs the AI agent over it, and stores both the reading and the resulting
    decision. An invalid reading is rejected here and never reaches storage
    or the agent (proposal Section 6).
    """
    if req.method == "OPTIONS":
        return _preflight()

    try:
        payload = req.get_json()
    except ValueError:
        logging.warning("Rejected reading: body was not valid JSON")
        return _json_response({"error": "Request body must be valid JSON"}, 400)

    try:
        validate_reading(payload)
    except ValidationError as e:
        logging.warning(
            "Rejected reading for bin_id=%s: %s",
            payload.get("bin_id", "unknown") if isinstance(payload, dict) else "unknown",
            e.errors,
        )
        return _json_response({"error": "Invalid reading", "details": e.errors}, 400)

    bin_id = payload["bin_id"]

    # Register the bin on first sight. This is what makes the device
    # genuinely clip-on: no one provisions a bin before using it.
    try:
        store.upsert_bin(bin_id)
    except Exception:
        logging.exception("Could not register bin_id=%s (continuing)", bin_id)

    # Store the reading BEFORE classifying. If the agent fails we still keep
    # the data -- the reading is the fact, the decision is an opinion about it.
    try:
        store.save_reading(payload)
    except Exception:
        logging.exception("Failed to store reading for bin_id=%s", bin_id)
        return _json_response({"error": "Internal storage error"}, 500)

    decision = None
    if AGENT_AVAILABLE:
        try:
            history = store.get_recent_readings(bin_id, limit=10)
            # get_recent_readings includes the reading we just saved; the agent
            # wants the PRIOR readings as history.
            prior = [r for r in history if r.get("timestamp") != payload.get("timestamp")]

            decision = bincast_agent.classify_with_foundry(payload, prior)
            decision["decision_id"] = _decision_id(payload)
            decision["review_status"] = "pending"
            decision["created_at"] = _now_iso()

            store.save_decision(decision)
        except Exception:
            # A failed classification is not a failed ingest.
            logging.exception("Agent/decision step failed for bin_id=%s", bin_id)
            decision = None

    logging.info(
        "Stored reading bin_id=%s fill_percentage=%s action=%s",
        bin_id, payload["fill_percentage"],
        decision.get("action") if decision else "none",
    )

    return _json_response({
        "status": "accepted",
        "bin_id": bin_id,
        "decision": decision,
    }, 201)


# =============================================================================
# Dashboard reads
# =============================================================================

@app.route(route="bins", methods=["GET", "OPTIONS"], auth_level=ANON)
def get_bins(req: func.HttpRequest) -> func.HttpResponse:
    """
    Fleet summary — one row per bin with its latest reading and the agent's
    latest recommendation. This is the dashboard's main screen.
    """
    if req.method == "OPTIONS":
        return _preflight()

    try:
        roster = store.list_bins()
    except Exception:
        logging.exception("Failed to list bins")
        return _json_response({"error": "Internal storage error"}, 500)

    summaries = []
    for bin_row in roster:
        bin_id = bin_row.get("bin_id")
        if not bin_id:
            continue
        try:
            reading = store.get_latest_reading(bin_id)
            decision = store.get_latest_decision(bin_id)
        except Exception:
            logging.exception("Failed to summarise bin_id=%s (skipping)", bin_id)
            continue
        summaries.append(_build_bin_summary(bin_row, reading, decision))

    summaries.sort(key=lambda b: b.get("fill_percentage") or 0, reverse=True)
    return _json_response(summaries)


@app.route(route="bins/{bin_id}/readings", methods=["GET", "OPTIONS"], auth_level=ANON)
def get_bin_readings(req: func.HttpRequest) -> func.HttpResponse:
    """Recent reading history for one bin — feeds the history chart."""
    if req.method == "OPTIONS":
        return _preflight()

    bin_id = req.route_params.get("bin_id")

    try:
        limit = max(1, min(int(req.params.get("limit", 20)), 200))
    except ValueError:
        return _json_response({"error": "'limit' must be an integer"}, 400)

    try:
        readings = store.get_recent_readings(bin_id, limit=limit)
    except Exception:
        logging.exception("Failed to fetch readings for bin_id=%s", bin_id)
        return _json_response({"error": "Internal storage error"}, 500)

    return _json_response({
        "bin_id": bin_id,
        "count": len(readings),
        "readings": readings,
    })

@app.route(route="bins/{bin_id}", methods=["PATCH", "OPTIONS"], auth_level=ANON)
def rename_bin(req: func.HttpRequest) -> func.HttpResponse:
    """
    Renames a bin. This is the only setup step the product has: clip the
    device on, it auto-registers as "Unassigned", staff give it a name.
    Nothing about the bin's depth or shape is ever configured by hand --
    that's learned (differentiator #1).
    """
    if req.method == "OPTIONS":
        return _preflight()

    bin_id = req.route_params.get("bin_id")

    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Request body must be valid JSON"}, 400)

    location = (body or {}).get("location")
    if not isinstance(location, str) or not location.strip():
        return _json_response({"error": "Field 'location' must be a non-empty string"}, 400)

    location = location.strip()[:60]

    try:
        store.upsert_bin(bin_id, location=location)
    except Exception:
        logging.exception("Failed to rename bin_id=%s", bin_id)
        return _json_response({"error": "Internal storage error"}, 500)

    logging.info("Renamed bin_id=%s to %r", bin_id, location)
    return _json_response({"bin_id": bin_id, "location": location})


@app.route(route="decisions", methods=["GET", "POST", "OPTIONS"], auth_level=ANON)
def decisions(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET  — the decision log, newest first. Optional ?bin_id= and ?limit=.
    POST — records a human approving or rejecting a recommendation.
           This is the human-in-the-loop step from proposal Section 6.
    """
    if req.method == "OPTIONS":
        return _preflight()

    if req.method == "GET":
        bin_id = req.params.get("bin_id")
        try:
            limit = max(1, min(int(req.params.get("limit", 50)), 200))
        except ValueError:
            return _json_response({"error": "'limit' must be an integer"}, 400)
        try:
            return _json_response(store.get_decisions(bin_id=bin_id, limit=limit))
        except Exception:
            logging.exception("Failed to fetch decisions")
            return _json_response({"error": "Internal storage error"}, 500)

    # --- POST: record the human's call ---
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Request body must be valid JSON"}, 400)

    errors = []
    if not isinstance(body, dict):
        return _json_response({"error": "Request body must be a JSON object"}, 400)

    for field in ("bin_id", "decision_id", "review_status"):
        if not body.get(field):
            errors.append(f"Missing required field: '{field}'")

    if body.get("review_status") not in ("approved", "rejected", None):
        errors.append("Field 'review_status' must be 'approved' or 'rejected'")

    if errors:
        return _json_response({"error": "Invalid decision", "details": errors}, 400)

    updates = {
        "review_status": body["review_status"],
        "confirmed_at": _now_iso(),
        "staff_id": body.get("staff_id", "demo-operator"),
        "confirmation_source": body.get("confirmation_source", "dashboard"),
    }
    if body.get("note"):
        updates["note"] = str(body["note"])[:200]

    try:
        updated = store.update_decision(body["bin_id"], body["decision_id"], updates)
    except Exception as e:
        if type(e).__name__ == "ResourceNotFoundError":
            return _json_response({"error": "No such decision"}, 404)
        logging.exception("Failed to update decision")
        return _json_response({"error": "Internal storage error"}, 500)

    logging.info(
        "Decision %s for bin_id=%s marked %s",
        body["decision_id"], body["bin_id"], body["review_status"],
    )
    return _json_response(updated)


@app.route(route="health", methods=["GET"], auth_level=ANON)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Liveness check — no auth, so uptime monitors can hit it directly.
    Reports whether storage is reachable and whether the agent is bundled,
    which turns "the demo is broken" into a one-line diagnosis.
    """
    storage_ok = True
    try:
        store.list_bins()
    except Exception:
        storage_ok = False
        logging.exception("Health check: storage unreachable")

    body = {
        "status": "healthy" if storage_ok else "degraded",
        "storage": "ok" if storage_ok else "unreachable",
        "agent": "loaded" if AGENT_AVAILABLE else "not bundled",
        "checked_at": _now_iso(),
    }
    return _json_response(body, 200 if storage_ok else 503)


# =============================================================================
# Helpers
# =============================================================================

def _build_bin_summary(bin_row: dict, reading: dict, decision: dict) -> dict:
    """
    Flattens the latest reading + latest decision into the one object the
    dashboard renders per bin.

    `classification` is DERIVED here, not stored. It is a display concept
    (what colour is this card?) rather than part of the data contract, and
    deriving it in one place keeps the four components that use it in sync.
    """
    reading = reading or {}
    decision = decision or {}
    anomaly = decision.get("anomaly") or {}
    calibration = reading.get("calibration") or {}

    fill = decision.get("fill_percentage", reading.get("fill_percentage"))

    return {
        "bin_id": bin_row.get("bin_id"),
        "location": bin_row.get("location"),
        "fill_percentage": fill,
        "classification": _classify_for_display(reading, decision),
        "last_updated": reading.get("timestamp"),
        "connectivity_status": reading.get("connectivity_status", "stale"),

        # Agent output — the explainability surface (differentiator #3).
        "action": decision.get("action"),
        "recommendation": decision.get("reasoning"),
        "confidence": decision.get("confidence"),
        "decision_id": decision.get("decision_id"),
        "review_status": decision.get("review_status"),
        "predicted_full_at": decision.get("predicted_full_at"),
        "anomaly_type": anomaly.get("type", "none"),

        # Calibration state — lets the UI show "still learning this bin"
        # instead of presenting a provisional number as fact.
        "calibration_confident": calibration.get("confident", False),
        "calibration_samples": calibration.get("sample_count", 0),
    }


def _classify_for_display(reading: dict, decision: dict) -> str:
    """Maps agent output onto the four states the dashboard cards know about."""
    anomaly = (decision.get("anomaly") or {}).get("type", "none")

    if anomaly == "obstruction":
        return "obstructed"
    if anomaly not in ("none", None):
        return "anomaly"
    if reading.get("status") == "obstructed":
        return "obstructed"
    if decision.get("action") == "schedule_pickup":
        return "full"
    if (reading.get("fill_percentage") or 0) >= 90:
        return "full"
    return "not_full"


def _decision_id(reading: dict) -> str:
    """
    Stable ID derived from the reading, so re-processing the same reading
    updates its decision instead of creating a second one. Colons and plus
    signs are stripped because Table Storage RowKeys reject some of them.
    """
    ts = str(reading.get("timestamp", "")).replace(":", "").replace("+", "").replace(".", "")
    return f"{reading.get('device_id', 'unknown')}-{ts}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, x-functions-key",
        "Access-Control-Max-Age": "3600",
    }


def _preflight() -> func.HttpResponse:
    return func.HttpResponse(status_code=204, headers=_cors_headers())


def _json_response(body, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, default=str),
        status_code=status_code,
        mimetype="application/json",
        headers=_cors_headers(),
    )