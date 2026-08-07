"""
RGB status light -- hardware driver.

This module only knows how to make the LED show a colour. Which colour a
reading deserves is decided in rgb_light.py, which is pure logic and needs
no Pi. Keeping them apart means the rules can be tested by anyone, and the
wiring can be debugged without touching the rules.

Flashing runs on a background thread. main.py must never sleep-and-toggle --
that would block the sensor loop.
"""

import threading
import time

import config
import rgb_light

# Colour name -> (red, green, blue), each 0.0-1.0
_RGB = {
    "green": (0.0, 1.0, 0.0),
    "amber": (1.0, 0.6, 0.0),
    "red":   (1.0, 0.0, 0.0),
    "blue":  (0.0, 0.3, 1.0),
    "off":   (0.0, 0.0, 0.0),
}

_led = None
_flash_thread = None
_stop_flashing = threading.Event()
_current_state = None


def _hardware_led():
    """Lazily create the LED so mock mode never imports gpiozero."""
    global _led
    if _led is None:
        from gpiozero import RGBLED

        _led = RGBLED(
            red=config.LED_R_PIN,
            green=config.LED_G_PIN,
            blue=config.LED_B_PIN,
            active_high=not config.LED_COMMON_ANODE,
        )
    return _led


def _apply(colour: tuple) -> None:
    if config.MOCK:
        return
    try:
        _hardware_led().color = colour
    except Exception as e:
        print(f"[leds] LED write failed: {e}")


def _flash_loop(colour: tuple) -> None:
    half_period = 1.0 / (2 * config.LED_FLASH_HZ)
    on = True
    while not _stop_flashing.is_set():
        _apply(colour if on else _RGB["off"])
        on = not on
        _stop_flashing.wait(half_period)
    _apply(_RGB["off"])


def set_state(state: str) -> None:
    """
    Set the light. Safe to call every loop -- a repeat call with the same
    state is ignored, so a flashing light won't restart mid-blink.
    """
    global _flash_thread, _current_state

    if state == _current_state:
        return
    _current_state = state

    colour_name = rgb_light.COLORS.get(state, "off")
    colour = _RGB[colour_name]
    flashing = rgb_light.is_flashing(state)

    # Stop any running flash thread before starting a new pattern.
    if _flash_thread and _flash_thread.is_alive():
        _stop_flashing.set()
        _flash_thread.join(timeout=1.0)
    _stop_flashing.clear()

    if config.MOCK:
        print(f"  [LED] {colour_name.upper()}{' FLASHING' if flashing else ''}")
        return

    if flashing:
        _flash_thread = threading.Thread(
            target=_flash_loop, args=(colour,), daemon=True
        )
        _flash_thread.start()
    else:
        _apply(colour)


# Re-exported so main.py has one import for light behaviour. The decision
# itself lives in rgb_light.
state_for = rgb_light.state_for


def off() -> None:
    set_state("off")


def cleanup() -> None:
    """Call on shutdown so the LED doesn't stay lit."""
    global _flash_thread
    _stop_flashing.set()
    if _flash_thread and _flash_thread.is_alive():
        _flash_thread.join(timeout=1.0)
    _apply(_RGB["off"])


if __name__ == "__main__":
    config.MOCK = True
    for s in ["calibrating", "ok", "warning", "full", "obstructed", "error", "offline"]:
        print(f"state: {s:12} {rgb_light.describe(s)}")
        set_state(s)
        time.sleep(0.3)
    cleanup()
