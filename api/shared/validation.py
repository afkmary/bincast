"""
Validates incoming bin sensor readings against the team's Data Contract
(see Data_Contract.docx — "Reading object (device -> cloud)").

Any reading that fails validation is rejected BEFORE it reaches storage
or the AI agent, per proposal Section 6 (Workflow Design):
"an invalid reading is rejected before storage and never reaches the agent"
"""

from datetime import datetime

REQUIRED_FIELDS = {
    "bin_id": str,
    "timestamp": str,
    "raw_distance_cm": (int, float),
    "fill_percentage": (int, float),
    "bin_height_cm": (int, float),
    "sensor_confidence": (int, float),
    "connectivity_status": str,
    "buffered": bool,
    "fill_rate_cm_per_hr": (int, float),
}

VALID_CONNECTIVITY_STATUS = {"Online", "Offline", "Stale"}


class ValidationError(Exception):
    """Raised when a reading fails schema validation."""
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_reading(payload: dict) -> None:
    """
    Validates a reading dict against the Data Contract.
    Raises ValidationError with a list of every problem found
    (not just the first one) so the caller can report everything at once.
    """
    if not isinstance(payload, dict):
        raise ValidationError(["Payload must be a JSON object"])

    errors = []

    # 1. Required fields present + correct type
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in payload:
            errors.append(f"Missing required field: '{field}'")
            continue
        if payload[field] is None:
            errors.append(f"Field '{field}' cannot be null")
            continue
        if not isinstance(payload[field], expected_type):
            errors.append(
                f"Field '{field}' has wrong type "
                f"(got {type(payload[field]).__name__})"
            )

    if errors:
        # Stop here — no point range-checking fields that don't exist / are wrong type
        raise ValidationError(errors)

    # 2. Timestamp is valid ISO 8601 UTC
    try:
        ts = payload["timestamp"].replace("Z", "+00:00")
        datetime.fromisoformat(ts)
    except (ValueError, AttributeError):
        errors.append("Field 'timestamp' is not valid ISO 8601 (e.g. 2026-08-04T14:32:00Z)")

    # 3. fill_percentage in [0, 100]
    if not (0 <= payload["fill_percentage"] <= 100):
        errors.append("Field 'fill_percentage' must be between 0 and 100")

    # 4. sensor_confidence in [0.0, 1.0]
    if not (0.0 <= payload["sensor_confidence"] <= 1.0):
        errors.append("Field 'sensor_confidence' must be between 0.0 and 1.0")

    # 5. connectivity_status is a known enum value
    if payload["connectivity_status"] not in VALID_CONNECTIVITY_STATUS:
        errors.append(
            f"Field 'connectivity_status' must be one of "
            f"{sorted(VALID_CONNECTIVITY_STATUS)}"
        )

    # 6. raw_distance_cm must be within the bin's calibrated span (0 to bin_height_cm)
    #    A small tolerance is allowed since the sensor can read slightly past
    #    the calibrated "empty" point.
    tolerance_cm = 5.0
    if not (-tolerance_cm <= payload["raw_distance_cm"] <= payload["bin_height_cm"] + tolerance_cm):
        errors.append(
            "Field 'raw_distance_cm' is outside the bin's calibrated range "
            f"(0 to {payload['bin_height_cm']} cm)"
        )

    # 7. bin_height_cm must be positive
    if payload["bin_height_cm"] <= 0:
        errors.append("Field 'bin_height_cm' must be greater than 0")

    if errors:
        raise ValidationError(errors)
