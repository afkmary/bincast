"""
Sends readings to the cloud ingest endpoint.

Written so it works before Kate's endpoint exists. With no API_URL set, or
in mock mode, send() reports failure -- which sends the reading to the
cache instead. That is a real exercise of the offline path, so the whole
loop is testable today.

The payload must validate against schema/reading.schema.json. If you change
the shape here, change the schema in the same commit.
"""

import json

import config

try:
    import requests
except ImportError:
    requests = None


def build_payload(
    quality: dict,
    fill_percentage: float,
    status: str,
    calibration: dict,
    timestamp: str,
    fill_rate_cm_per_hr: float = None,
    buffered: bool = False,
    online: bool = True,
) -> dict:
    """
    Assemble a reading in the exact shape the schema requires.

    Everything downstream depends on this function, so it is the one place
    field names are written out. Nobody else should be building this dict.
    """
    payload = {
        "device_id": config.DEVICE_ID,
        "bin_id": config.BIN_ID,
        "timestamp": timestamp,
        "raw_distance_cm": quality["distance_cm"] if quality["distance_cm"] is not None else 0.0,
        "fill_percentage": fill_percentage,
        "status": status,
        "quality": {
            "samples": quality["samples"],
            "spread_cm": quality["spread_cm"],
            "rejected": quality["rejected"],
        },
        "connectivity_status": "online" if online else "offline",
        "buffered": buffered,
        "firmware_version": config.FIRMWARE_VERSION,
    }

    # Omit calibration entirely when nothing has been learned. The schema
    # allows it to be absent; sending nulls would be worse.
    if calibration.get("empty_cm") is not None:
        payload["calibration"] = calibration

    if fill_rate_cm_per_hr is not None:
        payload["fill_rate_cm_per_hr"] = round(max(0.0, fill_rate_cm_per_hr), 2)

    return payload


def send(reading: dict) -> bool:
    """
    POST one reading. Returns True on success, False on any failure.

    Never raises. A failed send is a normal condition, not an error -- the
    caller caches and moves on.
    """
    if config.MOCK:
        print(f"  [cloud] MOCK, not sending: {json.dumps(reading)[:90]}...")
        return False

    if not config.API_URL:
        return False

    if requests is None:
        print("[cloud] requests not installed")
        return False

    headers = {"Content-Type": "application/json"}
    if config.API_KEY:
        headers["x-api-key"] = config.API_KEY

    try:
        response = requests.post(
            config.API_URL,
            json=reading,
            headers=headers,
            timeout=config.REQUEST_TIMEOUT_SEC,
        )
    except Exception as e:
        print(f"[cloud] send failed: {type(e).__name__}")
        return False

    if 200 <= response.status_code < 300:
        return True

    # 4xx means the payload is wrong and retrying won't help. Say so loudly
    # -- it almost always means the schema and this file disagree.
    if 400 <= response.status_code < 500:
        print(f"[cloud] rejected ({response.status_code}): {response.text[:200]}")
    else:
        print(f"[cloud] server error ({response.status_code})")

    return False


def flush_cache() -> int:
    """
    Try to send everything in the cache. Returns how many got through.

    Stops at the first failure and keeps the rest, so a network that drops
    mid-flush doesn't lose readings.
    """
    import cache

    pending = cache.load_all()
    if not pending:
        return 0

    sent = 0
    for reading in pending:
        reading["buffered"] = True
        if send(reading):
            sent += 1
        else:
            break

    if sent == len(pending):
        cache.clear()
    elif sent > 0:
        cache.rewrite(pending[sent:])

    return sent
