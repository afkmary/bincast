"""
Validates incoming bin sensor readings against the team's Data Contract.

SOURCE OF TRUTH: schema/reading.schema.json

This module is a hand-written mirror of that schema. If the schema changes,
change this file in the same commit -- and vice versa. The test at the bottom
of the repo (tests/test_validation.py) runs every entry in
schema/sample-readings.json through validate_reading() to keep the two honest.

Any reading that fails validation is rejected BEFORE it reaches storage or
the AI agent, per proposal Section 6 (Workflow Design).

Design notes for the write-up:
  - There is deliberately NO bin_height_cm. The bin's usable depth is LEARNED
    by the device (calibration.empty_cm), not configured by a human. That is
    differentiator #1 (zero-config auto-calibration) -- requiring a configured
    height here would contradict it.
  - There is deliberately NO sensor_confidence. The device reports raw signal
    evidence (quality.spread_cm, quality.rejected) and the AGENT reaches its
    own confidence from it. Handing the agent a pre-computed number would
    undercut differentiator #3 (explainable AI judgment).
"""

from datetime import datetime

# --- Required fields (must match "required" in reading.schema.json) -----------
REQUIRED_FIELDS = {
    "device_id": str,
    "bin_id": str,
    "timestamp": str,
    "raw_distance_cm": (int, float),
    "fill_percentage": (int, float),
    "status": str,
}

# --- Optional top-level fields -----------------------------------------------
OPTIONAL_FIELDS = {
    "calibration": dict,
    "quality": dict,
    "fill_rate_cm_per_hr": (int, float),
    "connectivity_status": str,
    "buffered": bool,
    "firmware_version": str,
}

VALID_STATUS = {"ok", "warning", "full", "obstructed", "error"}
VALID_CONNECTIVITY_STATUS = {"online", "offline", "stale"}

MAX_DISTANCE_CM = 500.0

# ID pattern from the schema: ^[a-z0-9-]{3,32}$
_ID_MIN_LEN, _ID_MAX_LEN = 3, 32
_ID_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789-")


class ValidationError(Exception):
    """Raised when a reading fails schema validation."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _is_valid_id(value: str) -> bool:
    return (
        isinstance(value, str)
        and _ID_MIN_LEN <= len(value) <= _ID_MAX_LEN
        and set(value) <= _ID_ALLOWED
    )


def _is_number(value) -> bool:
    # bool is a subclass of int in Python -- exclude it explicitly.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_reading(payload: dict) -> None:
    """
    Validates a reading dict against the Data Contract.

    Raises ValidationError carrying a list of EVERY problem found, not just
    the first, so the device gets one useful 400 instead of a guessing game.
    Returns None on success.
    """
    if not isinstance(payload, dict):
        raise ValidationError(["Payload must be a JSON object"])

    errors = []

    # 1. Required fields present, non-null, correct type
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in payload:
            errors.append(f"Missing required field: '{field}'")
            continue
        if payload[field] is None:
            errors.append(f"Field '{field}' cannot be null")
            continue
        if expected_type in ((int, float),):
            if not _is_number(payload[field]):
                errors.append(
                    f"Field '{field}' must be a number "
                    f"(got {type(payload[field]).__name__})"
                )
        elif not isinstance(payload[field], expected_type):
            errors.append(
                f"Field '{field}' has wrong type "
                f"(got {type(payload[field]).__name__}, "
                f"expected {expected_type.__name__})"
            )

    # 2. Unknown fields -- the schema sets additionalProperties: false.
    #    Rejected rather than ignored so a typo like "fill_percent" fails
    #    loudly instead of silently storing nothing.
    known = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    for field in payload:
        if field not in known and not field.startswith("_"):
            errors.append(f"Unknown field: '{field}' (not in the data contract)")

    if errors:
        # Stop here -- no point range-checking fields that are missing or
        # the wrong type.
        raise ValidationError(errors)

    # 3. IDs match the contract's pattern
    for id_field in ("device_id", "bin_id"):
        if not _is_valid_id(payload[id_field]):
            errors.append(
                f"Field '{id_field}' must be 3-32 chars of lowercase letters, "
                f"digits or hyphens (e.g. 'bin-001')"
            )

    # 4. Timestamp is valid ISO 8601
    if not _is_iso8601(payload["timestamp"]):
        errors.append(
            "Field 'timestamp' is not valid ISO 8601 (e.g. 2026-08-04T14:32:00Z)"
        )

    # 5. Numeric ranges
    if not (0 <= payload["raw_distance_cm"] <= MAX_DISTANCE_CM):
        errors.append(
            f"Field 'raw_distance_cm' must be between 0 and {MAX_DISTANCE_CM}"
        )

    if not (0 <= payload["fill_percentage"] <= 100):
        errors.append("Field 'fill_percentage' must be between 0 and 100")

    # 6. Enums
    if payload["status"] not in VALID_STATUS:
        errors.append(f"Field 'status' must be one of {sorted(VALID_STATUS)}")

    # --- Optional fields: validated only when present ------------------------

    for field, expected_type in OPTIONAL_FIELDS.items():
        if field not in payload or payload[field] is None:
            continue
        if expected_type in ((int, float),):
            if not _is_number(payload[field]):
                errors.append(f"Field '{field}' must be a number")
        elif not isinstance(payload[field], expected_type):
            errors.append(
                f"Field '{field}' has wrong type "
                f"(got {type(payload[field]).__name__})"
            )

    if "connectivity_status" in payload and isinstance(
        payload.get("connectivity_status"), str
    ):
        if payload["connectivity_status"] not in VALID_CONNECTIVITY_STATUS:
            errors.append(
                f"Field 'connectivity_status' must be one of "
                f"{sorted(VALID_CONNECTIVITY_STATUS)} (lowercase)"
            )

    if "fill_rate_cm_per_hr" in payload and _is_number(
        payload.get("fill_rate_cm_per_hr")
    ):
        if payload["fill_rate_cm_per_hr"] < 0:
            errors.append("Field 'fill_rate_cm_per_hr' cannot be negative")

    if isinstance(payload.get("calibration"), dict):
        errors.extend(_validate_calibration(payload["calibration"]))

    if isinstance(payload.get("quality"), dict):
        errors.extend(_validate_quality(payload["quality"]))

    if errors:
        raise ValidationError(errors)


def _validate_calibration(cal: dict) -> list:
    """calibration is optional, but if sent it must be complete."""
    errors = []

    for field in ("empty_cm", "full_cm", "confident"):
        if field not in cal:
            errors.append(f"Field 'calibration.{field}' is required when calibration is sent")

    if errors:
        return errors

    for field in ("empty_cm", "full_cm"):
        if not _is_number(cal[field]):
            errors.append(f"Field 'calibration.{field}' must be a number")
        elif not (0 <= cal[field] <= MAX_DISTANCE_CM):
            errors.append(
                f"Field 'calibration.{field}' must be between 0 and {MAX_DISTANCE_CM}"
            )

    if not isinstance(cal["confident"], bool):
        errors.append("Field 'calibration.confident' must be true or false")

    if "sample_count" in cal:
        if not isinstance(cal["sample_count"], int) or isinstance(cal["sample_count"], bool):
            errors.append("Field 'calibration.sample_count' must be an integer")
        elif cal["sample_count"] < 0:
            errors.append("Field 'calibration.sample_count' cannot be negative")

    # A full bin is CLOSER to the sensor than an empty one, so full_cm should
    # be the smaller distance. Catching this here saves the agent from
    # reasoning about an inverted calibration.
    if not errors and cal["full_cm"] > cal["empty_cm"]:
        errors.append(
            "Field 'calibration.full_cm' must be less than or equal to "
            "'calibration.empty_cm' (a full bin reads a shorter distance)"
        )

    return errors


def _validate_quality(quality: dict) -> list:
    """quality is optional; each sub-field is independently optional."""
    errors = []

    int_fields = {"samples": 1, "rejected": 0}
    for field, minimum in int_fields.items():
        if field not in quality:
            continue
        value = quality[field]
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"Field 'quality.{field}' must be an integer")
        elif value < minimum:
            errors.append(f"Field 'quality.{field}' must be at least {minimum}")

    if "spread_cm" in quality:
        if not _is_number(quality["spread_cm"]):
            errors.append("Field 'quality.spread_cm' must be a number")
        elif quality["spread_cm"] < 0:
            errors.append("Field 'quality.spread_cm' cannot be negative")

    for field in quality:
        if field not in ("samples", "spread_cm", "rejected"):
            errors.append(f"Unknown field: 'quality.{field}'")

    return errors


def _is_iso8601(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        # Python's fromisoformat doesn't accept the trailing Z before 3.11.
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except (ValueError, AttributeError):
        return False