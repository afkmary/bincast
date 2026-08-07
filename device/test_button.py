"""
Demo test button.

Fires a synthetic reading at the cloud so you can trigger an event on stage
without physically filling a bin. This is the demo backup -- if the sensor
misbehaves in front of the class, this still produces a live end-to-end
event through the real pipeline.

    python test_button.py              # the full-bin case
    python test_button.py obstructed   # the obstruction case
    python test_button.py --list       # show every scenario

Field names come from cloud.build_payload(), the same function the real
device uses. That is deliberate: a test tool that builds its own payload
drifts from the real one and stops testing anything useful.
"""

import sys
from datetime import datetime, timezone

import cloud
import config


# Each scenario is the sensor evidence, not the conclusion. The agent is
# supposed to reach the conclusion itself -- that is the thing being demoed.
SCENARIOS = {
    "empty": {
        "description": "Freshly emptied bin, nothing to do",
        "distance_cm": 88.0,
        "spread_cm": 0.8,
        "rejected": 0,
        "fill_rate": 0.4,
        "status": "ok",
    },
    "filling": {
        "description": "Half full and rising steadily",
        "distance_cm": 50.0,
        "spread_cm": 1.4,
        "rejected": 0,
        "fill_rate": 3.2,
        "status": "ok",
    },
    "warning": {
        "description": "Getting high, forecast matters",
        "distance_cm": 31.0,
        "spread_cm": 2.0,
        "rejected": 0,
        "fill_rate": 4.5,
        "status": "warning",
    },
    "full": {
        "description": "Genuinely full: tight spread, plausible rate. Agent should say schedule_pickup",
        "distance_cm": 12.0,
        "spread_cm": 0.9,
        "rejected": 0,
        "fill_rate": 3.1,
        "status": "full",
    },
    "obstructed": {
        "description": "Reads full but the evidence is bad. Agent should say inspect, NOT pickup",
        "distance_cm": 5.0,
        "spread_cm": 24.3,
        "rejected": 3,
        "fill_rate": 26.5,
        "status": "obstructed",
    },
    "error": {
        "description": "Sensor failure, every ping rejected",
        "distance_cm": None,
        "spread_cm": 0.0,
        "rejected": 7,
        "fill_rate": None,
        "status": "error",
    },
}

# A calibrated bin, matching what a device would have learned by now.
CALIBRATION = {
    "empty_cm": 90.0,
    "full_cm": 10.0,
    "confident": True,
    "sample_count": 240,
}


def _fill_percentage(distance_cm) -> float:
    """Same maths as calibration.to_fill_percentage, using the fixed values above."""
    if distance_cm is None:
        return 0.0
    span = CALIBRATION["empty_cm"] - CALIBRATION["full_cm"]
    pct = (CALIBRATION["empty_cm"] - distance_cm) / span * 100.0
    return round(min(100.0, max(0.0, pct)), 1)


def build_test_reading(scenario: str = "full") -> dict:
    """Build a schema-valid reading for the named scenario."""
    if scenario not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario '{scenario}'. Options: {', '.join(SCENARIOS)}"
        )

    s = SCENARIOS[scenario]

    quality = {
        "distance_cm": s["distance_cm"],
        "samples": 7,
        "spread_cm": s["spread_cm"],
        "rejected": s["rejected"],
    }

    return cloud.build_payload(
        quality=quality,
        fill_percentage=_fill_percentage(s["distance_cm"]),
        status=s["status"],
        calibration=CALIBRATION,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        fill_rate_cm_per_hr=s["fill_rate"],
        buffered=False,
        online=True,
    )


def fire(scenario: str = "full") -> bool:
    """Build and send. Returns True if the cloud accepted it."""
    reading = build_test_reading(scenario)

    print(f"Scenario: {scenario} -- {SCENARIOS[scenario]['description']}")
    print(f"  {reading['fill_percentage']}% full, "
          f"spread {reading['quality']['spread_cm']}cm, "
          f"{reading['quality']['rejected']}/7 rejected")

    if cloud.send(reading):
        print("  sent")
        return True

    print("  send failed (no API_URL set, or endpoint unreachable)")
    return False


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--list" in args:
        print("Scenarios:\n")
        for name, s in SCENARIOS.items():
            print(f"  {name:12} {s['description']}")
        sys.exit(0)

    scenario = args[0] if args else "full"

    if scenario not in SCENARIOS:
        print(f"Unknown scenario '{scenario}'. Try --list.")
        sys.exit(1)

    print(f"Device {config.DEVICE_ID} on {config.BIN_ID}")
    print(f"Endpoint: {config.API_URL or '(not set)'}\n")

    import json
    reading = build_test_reading(scenario)
    print(json.dumps(reading, indent=2))
    print()

    fire(scenario)
