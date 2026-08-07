"""
Local cache for readings taken while the network is down.

Uses JSON Lines -- one JSON object per line. Appending is a single write
with no need to parse what's already there, which matters because power
can cut at any moment and a half-written file should cost you one reading,
not the whole cache.
"""

import json
import os

import config


def append(reading: dict) -> None:
    """Save a reading that failed to send."""
    try:
        with open(config.CACHE_FILE, "a") as f:
            f.write(json.dumps(reading) + "\n")
    except OSError as e:
        print(f"[cache] could not write: {e}")


def count() -> int:
    """How many readings are waiting."""
    if not os.path.exists(config.CACHE_FILE):
        return 0
    try:
        with open(config.CACHE_FILE) as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def load_all() -> list:
    """Read every cached reading. Bad lines are skipped, not fatal."""
    if not os.path.exists(config.CACHE_FILE):
        return []

    readings = []
    try:
        with open(config.CACHE_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    readings.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        print(f"[cache] could not read: {e}")

    return readings


def clear() -> None:
    """Delete the cache. Only call this after a successful flush."""
    try:
        if os.path.exists(config.CACHE_FILE):
            os.remove(config.CACHE_FILE)
    except OSError as e:
        print(f"[cache] could not clear: {e}")


def rewrite(readings: list) -> None:
    """
    Replace the cache with the given readings.

    Used after a partial flush -- keep what didn't send, drop what did.
    Also enforces the size cap by dropping the oldest.
    """
    readings = readings[-config.MAX_CACHED_READINGS:]
    try:
        with open(config.CACHE_FILE, "w") as f:
            for r in readings:
                f.write(json.dumps(r) + "\n")
    except OSError as e:
        print(f"[cache] could not rewrite: {e}")


if __name__ == "__main__":
    config.CACHE_FILE = "cache.test.jsonl"
    clear()

    append({"bin_id": "bin-001", "fill_percentage": 30.0})
    append({"bin_id": "bin-001", "fill_percentage": 35.0})
    print(f"cached: {count()}")
    print(f"loaded: {load_all()}")

    clear()
    print(f"after clear: {count()}")
