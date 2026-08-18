# edge-device/main.py
"""
Entry point for the sensor/mini-computer code.

Reads the ultrasonic sensor, feeds calibration, works out fill % and status,
drives the LCD and RGB LED, and sends the reading to the cloud (caching it
locally if that fails).

This file is the merge point between the two halves described in the
README (sensing vs. output+cloud). It owns the loop and the order of
operations; it does not contain sensor maths, light rules, or payload
shape -- those stay in their own modules.
"""

import time
from datetime import datetime, timezone

import cache
import calibration
import cloud
import config
import display
import leds
import rgb_light
import sensor


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status_for(quality: dict, fill_percentage: float) -> str:
    """
    Device-side status only -- the agent makes the real call downstream.

    A sensor fault and an obstruction both outrank the fill number, because
    in either case the fill number can't be trusted.
    """
    if quality["distance_cm"] is None:
        return "error"
    if sensor.looks_obstructed(quality):
        return "obstructed"
    return rgb_light.status_for_fill(fill_percentage)


def _fill_rate(prev_distance_cm, prev_time, distance_cm, now) -> float:
    """
    Centimetres of fill per hour, from the last two readings.

    Distance shrinking means the bin is filling, so a shrinking distance is
    a positive fill rate. Returns None when there isn't a previous reading
    to compare against, or elapsed time is effectively zero.
    """
    if prev_distance_cm is None or distance_cm is None or prev_time is None:
        return None
    elapsed_hr = (now - prev_time).total_seconds() / 3600.0
    if elapsed_hr <= 0:
        return None
    return (prev_distance_cm - distance_cm) / elapsed_hr


def _update_outputs(status: str, fill_percentage: float, confident: bool, online: bool) -> str:
    """
    Drive the LED and LCD together so they never disagree about state.

    Returns the led_state, in case the caller wants it (main doesn't, but
    keeping the return makes this testable on its own).
    """
    led_state = rgb_light.state_for(status, confident=confident, online=online)
    leds.set_state(led_state)

    # error/obstructed take priority over calibrating/offline, matching the
    # priority baked into rgb_light.state_for -- the LCD and the LED must
    # never tell two different stories.
    if status in ("error", "obstructed"):
        display.show(fill_percentage, status, provisional=not confident)
    elif not confident:
        display.show_calibrating(_calibration_instance.sample_count)
    elif led_state == "offline":
        display.show_offline(cache.count())
    else:
        display.show(fill_percentage, status, provisional=False)

    return led_state


_calibration_instance = None  # set in main(), read by _update_outputs


def main():
    global _calibration_instance

    display.show_booting()
    _calibration_instance = calibration.Calibration()

    # A device coming back online should clear out whatever piled up while
    # it was offline, before it starts publishing new readings.
    cloud.flush_cache()

    prev_distance_cm = None
    prev_time = None

    while True:
        now = datetime.now(timezone.utc)
        quality = sensor.read_distance()
        distance_cm = quality["distance_cm"]

        _calibration_instance.observe(distance_cm)
        fill_percentage = _calibration_instance.to_fill_percentage(distance_cm)

        status = _status_for(quality, fill_percentage)
        fill_rate = _fill_rate(prev_distance_cm, prev_time, distance_cm, now)

        payload = cloud.build_payload(
            quality=quality,
            fill_percentage=fill_percentage,
            status=status,
            calibration=_calibration_instance.as_dict(),
            timestamp=_timestamp(),
            fill_rate_cm_per_hr=fill_rate,
            buffered=False,
            online=True,
        )

        online = cloud.send(payload)
        if online:
            # A send just succeeded -- good moment to clear anything left
            # over from an earlier outage.
            cloud.flush_cache()
        else:
            payload["connectivity_status"] = "offline"
            cache.append(payload)

        _update_outputs(status, fill_percentage, _calibration_instance.confident, online)

        prev_distance_cm, prev_time = distance_cm, now
        time.sleep(config.POLL_INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        leds.cleanup()
        display.clear()