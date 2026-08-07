"""
Every value a human might want to change lives here.

Nothing in this file contains logic. If you find yourself editing another
module to change a number, that number belongs here instead.
"""

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# --- Identity ----------------------------------------------------------------
# device_id is the clip-on unit and never changes.
# bin_id is whichever bin it is currently attached to, so it DOES change.
DEVICE_ID = os.environ.get("BINCAST_DEVICE_ID", "dev-a1")
BIN_ID = os.environ.get("BINCAST_BIN_ID", "bin-001")

FIRMWARE_VERSION = "0.1.0"


# --- Mock mode ---------------------------------------------------------------
# MOCK=true runs the whole program with no hardware and no network.
# This is what lets both device people (and everyone else) work at once.
#   Windows:  $env:BINCAST_MOCK="true"; python main.py
#   Mac/Pi:   BINCAST_MOCK=true python3 main.py
MOCK = _env_bool("BINCAST_MOCK", False)


# --- Timing ------------------------------------------------------------------
POLL_INTERVAL_SEC = 60          # how often to take a reading
SAMPLES_PER_READING = 7         # raw pings, median-filtered down to one value
SAMPLE_GAP_SEC = 0.06           # pause between pings so echoes don't overlap


# --- Sensor ------------------------------------------------------------------
TRIG_PIN = 23
ECHO_PIN = 24

MIN_VALID_CM = 2.0              # HC-SR04 cannot resolve closer than this
MAX_VALID_CM = 400.0            # nor further than this
MAX_SPREAD_CM = 8.0             # above this, the reading is unstable


# --- RGB LED -----------------------------------------------------------------
LED_R_PIN = 17
LED_G_PIN = 27
LED_B_PIN = 22

LED_COMMON_ANODE = False        # True if your LED is common-anode (inverts)
LED_FLASH_HZ = 1.5


# --- LCD ---------------------------------------------------------------------
LCD_I2C_ADDRESS = 0x27          # try 0x3F if 0x27 shows nothing
LCD_COLS = 16
LCD_ROWS = 2


# --- Fill thresholds ---------------------------------------------------------
# Device-side status only. The agent makes the real call.
WARNING_PERCENT = 70.0
FULL_PERCENT = 90.0


# --- Calibration -------------------------------------------------------------
CALIBRATION_FILE = "calibration.json"
MIN_SAMPLES_FOR_CONFIDENCE = 30     # readings needed before confident = True
FULL_CM_MARGIN = 10.0               # treated as full this far below the rim


# --- Cloud -------------------------------------------------------------------
# Kate fills this in. Until then, leave it empty and readings go to the
# cache file, which is a perfectly good way to test the rest of the loop.
API_URL = os.environ.get("BINCAST_API_URL", "")
API_KEY = os.environ.get("BINCAST_API_KEY", "")
REQUEST_TIMEOUT_SEC = 10

CACHE_FILE = "cache.jsonl"
MAX_CACHED_READINGS = 5000
