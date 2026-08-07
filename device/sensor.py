"""
Ultrasonic distance reading.

Owns exactly one job: turn pings into a distance in centimetres, plus the
evidence of how trustworthy that distance is. It knows nothing about bins,
fill levels, or the cloud.

The quality numbers matter as much as the distance. A bag stuck across the
sensor reads the same as a full bin -- the only thing telling them apart is
that the raw pings scatter. That scatter is `spread_cm`.
"""

import random
import statistics
import time

import config

_sensor = None


def _hardware_sensor():
    """Lazily create the gpiozero sensor so mock mode never imports it."""
    global _sensor
    if _sensor is None:
        from gpiozero import DistanceSensor

        _sensor = DistanceSensor(
            echo=config.ECHO_PIN,
            trigger=config.TRIG_PIN,
            max_distance=config.MAX_VALID_CM / 100.0,
        )
    return _sensor


def _ping_hardware() -> float:
    """One raw ping, in centimetres."""
    return _hardware_sensor().distance * 100.0


# Mock state: a bin that slowly fills, so the dashboard sees movement.
_mock_distance = 80.0


def _ping_mock() -> float:
    """One fake ping. Drifts downward with occasional junk values."""
    global _mock_distance
    _mock_distance = max(8.0, _mock_distance - random.uniform(0.0, 0.4))
    if random.random() < 0.05:
        return random.uniform(0.0, 400.0)     # junk, should get rejected
    return _mock_distance + random.gauss(0, 0.5)


def read_distance() -> dict:
    """
    Take several pings and reduce them to one trustworthy number.

    Returns a dict shaped like the schema's `quality` block plus the distance:

        {
            "distance_cm": 51.2,   # median of the valid samples
            "samples": 7,          # raw pings attempted
            "spread_cm": 1.4,      # max - min across valid samples
            "rejected": 0,         # samples outside the plausible range
        }

    distance_cm is None when every sample was rejected -- that is a sensor
    failure and the caller must handle it.
    """
    ping = _ping_mock if config.MOCK else _ping_hardware

    valid = []
    rejected = 0

    for _ in range(config.SAMPLES_PER_READING):
        try:
            value = ping()
        except Exception:
            rejected += 1
            continue

        if config.MIN_VALID_CM <= value <= config.MAX_VALID_CM:
            valid.append(value)
        else:
            rejected += 1

        time.sleep(config.SAMPLE_GAP_SEC)

    if not valid:
        return {
            "distance_cm": None,
            "samples": config.SAMPLES_PER_READING,
            "spread_cm": 0.0,
            "rejected": rejected,
        }

    return {
        "distance_cm": round(statistics.median(valid), 1),
        "samples": config.SAMPLES_PER_READING,
        "spread_cm": round(max(valid) - min(valid), 1),
        "rejected": rejected,
    }


def looks_obstructed(quality: dict) -> bool:
    """
    Cheap device-side hint, not a verdict.

    The agent makes the real obstruction call using the full picture. This
    only flags the obvious case so the LED can react without waiting for a
    round trip to the cloud.
    """
    if quality["distance_cm"] is None:
        return False
    return (
        quality["spread_cm"] > config.MAX_SPREAD_CM
        or quality["rejected"] >= config.SAMPLES_PER_READING // 2
    )


if __name__ == "__main__":
    print("Reading sensor. Ctrl+C to stop.\n")
    try:
        while True:
            q = read_distance()
            print(
                f"{q['distance_cm']} cm   "
                f"spread {q['spread_cm']} cm   "
                f"rejected {q['rejected']}/{q['samples']}"
            )
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
