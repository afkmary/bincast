"""
Light policy: which status light a reading deserves.

Pure functions only. No GPIO, no threads, no imports that need a Pi -- so
this runs anywhere and is trivial to unit test. `leds.py` handles the actual
hardware and imports its decision from here.

Splitting it this way means the rules can be argued about and tested without
anyone touching a wire.

States:

    ok           steady green      nothing to do
    warning      steady amber      filling up
    full         flashing red      needs pickup
    obstructed   flashing amber    reads full but evidence is bad
    error        flashing red      sensor fault
    calibrating  flashing blue     still learning the bin
    offline      steady blue       caching locally

Thresholds live in config.py, not here.
"""

import config

# Every state, in the order they take priority. First match wins.
PRIORITY = ["error", "obstructed", "calibrating", "offline", "full", "warning", "ok"]

COLORS = {
    "ok": "green",
    "warning": "amber",
    "full": "red",
    "obstructed": "amber",
    "error": "red",
    "calibrating": "blue",
    "offline": "blue",
    "off": "off",
}

FLASHING = {
    "ok": False,
    "warning": False,
    "full": True,
    "obstructed": True,
    "error": True,
    "calibrating": True,
    "offline": False,
    "off": False,
}


def status_for_fill(fill_percentage: float) -> str:
    """
    Fill level alone, ignoring everything else.

    This is the simple case: how full is it, and what does that mean.
    Thresholds come from config so changing them is a one-line edit in one
    file, not a hunt through the light code.
    """
    if fill_percentage is None:
        return "error"
    if fill_percentage >= config.FULL_PERCENT:
        return "full"
    if fill_percentage >= config.WARNING_PERCENT:
        return "warning"
    return "ok"


def state_for(
    status: str,
    confident: bool = True,
    online: bool = True,
) -> str:
    """
    The full decision, taking everything into account.

    Priority order is the point of this function, and it is deliberate:

      A sensor fault outranks a full bin, because a fault means the fill
      number cannot be trusted in the first place. Flashing red for "full"
      when the sensor is broken sends someone to empty a bin that might be
      half empty.

      An obstruction outranks fill for the same reason -- that is the whole
      obstruction differentiator, expressed in the light.

      Calibrating outranks fill because the percentage is provisional until
      the device has learned the bin's range.
    """
    if status == "error":
        return "error"
    if status == "obstructed":
        return "obstructed"
    if not confident:
        return "calibrating"
    if not online:
        return "offline"
    if status in COLORS:
        return status
    return "ok"


def get_light_color(fill_percentage: float) -> str:
    """
    Colour name for a fill percentage. Kept for the simple case and for
    anyone testing the thresholds without the rest of the pipeline.

    Note this returns "amber" in the warning band -- the original two-colour
    version jumped straight from green to red at 75%. If the team wants that
    behaviour back, set WARNING_PERCENT and FULL_PERCENT to the same number
    in config.py and the amber band disappears on its own.
    """
    return COLORS[status_for_fill(fill_percentage)]


def is_flashing(state: str) -> bool:
    return FLASHING.get(state, False)


def describe(state: str) -> str:
    """Human-readable, for logs and the LCD."""
    return {
        "ok": "All good",
        "warning": "Filling up",
        "full": "FULL - pickup",
        "obstructed": "Check sensor",
        "error": "Sensor fault",
        "calibrating": "Learning bin",
        "offline": "Offline",
    }.get(state, state)


if __name__ == "__main__":
    print(f"Thresholds: warning at {config.WARNING_PERCENT}%, "
          f"full at {config.FULL_PERCENT}%\n")

    print("Fill level alone:")
    for pct in [0, 30, 69, 70, 75, 89, 90, 100]:
        print(f"  {pct:3}% -> {status_for_fill(pct):11} ({get_light_color(pct)})")

    print("\nFull decision, priority order:")
    cases = [
        ("ok",         True,  True,  "normal, low fill"),
        ("full",       True,  True,  "genuinely full"),
        ("full",       False, True,  "full BUT still calibrating"),
        ("full",       True,  False, "full BUT offline"),
        ("obstructed", True,  True,  "reads full, evidence bad"),
        ("full",       True,  True,  "full, everything fine"),
        ("error",      True,  True,  "sensor dead"),
        ("error",      False, False, "sensor dead, everything else wrong too"),
    ]
    for status, confident, online, note in cases:
        state = state_for(status, confident, online)
        flash = " FLASHING" if is_flashing(state) else ""
        print(f"  {note:38} -> {COLORS[state]:6}{flash}")
