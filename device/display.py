"""
Everything the 16x2 LCD does.

One rule: no other module talks to the screen. If something needs to be
shown, it calls a function here. That keeps formatting in one place and
means the LCD can be swapped or removed without touching the main loop.

In mock mode this prints to the terminal in a little box, so you can see
exactly what the screen would show without owning a screen.
"""

import config

_lcd = None
_last_lines = ("", "")


def _hardware_lcd():
    global _lcd
    if _lcd is None:
        from RPLCD.i2c import CharLCD

        _lcd = CharLCD(
            i2c_expander="PCF8574",
            address=config.LCD_I2C_ADDRESS,
            cols=config.LCD_COLS,
            rows=config.LCD_ROWS,
            auto_linebreaks=False,
        )
    return _lcd


def _fit(text: str) -> str:
    """Pad or truncate to exactly the display width."""
    return text[: config.LCD_COLS].ljust(config.LCD_COLS)


def _write(line1: str, line2: str) -> None:
    global _last_lines

    line1, line2 = _fit(line1), _fit(line2)

    # Skip the write if nothing changed. Redrawing an identical screen
    # every minute makes the LCD visibly flicker.
    if (line1, line2) == _last_lines:
        return
    _last_lines = (line1, line2)

    if config.MOCK:
        print(f"  +{'-' * config.LCD_COLS}+")
        print(f"  |{line1}|")
        print(f"  |{line2}|")
        print(f"  +{'-' * config.LCD_COLS}+")
        return

    try:
        lcd = _hardware_lcd()
        lcd.clear()
        lcd.cursor_pos = (0, 0)
        lcd.write_string(line1)
        lcd.cursor_pos = (1, 0)
        lcd.write_string(line2)
    except Exception as e:
        print(f"[display] LCD write failed: {e}")


# --- what the rest of the program calls --------------------------------------


def show(fill_percentage: float, status: str, provisional: bool = False) -> None:
    """
    The normal screen.

        +----------------+
        |Fill:  73%      |
        |Filling up      |
        +----------------+
    """
    pct = f"{fill_percentage:.0f}%"
    line1 = f"Fill: {pct:>4}"
    if provisional:
        line1 += " ~"           # tilde means calibration is still learning

    line2 = {
        "ok": "All good",
        "warning": "Filling up",
        "full": "FULL - pickup",
        "obstructed": "Check sensor",
        "error": "Sensor fault",
    }.get(status, status)

    _write(line1, line2)


def show_message(line1: str, line2: str = "") -> None:
    """Free-form two-line message, for boot and error screens."""
    _write(line1, line2)


def show_booting() -> None:
    show_message("Bincast", "Starting up...")


def show_calibrating(sample_count: int) -> None:
    show_message("Learning bin...", f"{sample_count} readings")


def show_offline(cached_count: int) -> None:
    show_message("Offline", f"{cached_count} saved")


def clear() -> None:
    global _last_lines
    _last_lines = ("", "")
    if config.MOCK:
        return
    try:
        _hardware_lcd().clear()
    except Exception:
        pass


if __name__ == "__main__":
    import time

    config.MOCK = True
    show_booting()
    time.sleep(0.5)
    show_calibrating(12)
    time.sleep(0.5)
    for pct, st in [(22, "ok"), (73, "warning"), (98, "full"), (100, "obstructed")]:
        show(pct, st)
        time.sleep(0.5)
    show(48, "ok", provisional=True)
