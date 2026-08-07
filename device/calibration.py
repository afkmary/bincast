"""
Zero-config auto-calibration.

This module is the differentiator. Nobody types in a bin depth anywhere --
the device works it out by watching. Clip it on any bin and it figures out
the range on its own.

How it works:

  empty_cm  The largest plausible distance ever observed. When a bin is
            emptied, the sensor sees all the way to the bottom, and that
            is the deepest reading it will ever get. So the running maximum
            converges on the bin's true depth.

  full_cm   empty_cm minus a fixed margin. A bin is "full" when contents
            reach within ~10cm of the rim.

  confident False until enough readings have accumulated. Downstream must
            treat fill_percentage as provisional while this is false --
            that is what makes the provisional state honest rather than a
            silent guess.

State persists to disk so a reboot doesn't throw away what was learned.
"""

import json
import os

import config


class Calibration:
    def __init__(self, path: str = None):
        self.path = path or config.CALIBRATION_FILE
        self.empty_cm = None
        self.full_cm = None
        self.sample_count = 0
        self._load()

    # --- persistence ---------------------------------------------------------

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                saved = json.load(f)
            self.empty_cm = saved.get("empty_cm")
            self.full_cm = saved.get("full_cm")
            self.sample_count = saved.get("sample_count", 0)
        except (json.JSONDecodeError, OSError):
            pass    # corrupt file just means we start learning again

    def _save(self) -> None:
        try:
            with open(self.path, "w") as f:
                json.dump(
                    {
                        "empty_cm": self.empty_cm,
                        "full_cm": self.full_cm,
                        "sample_count": self.sample_count,
                    },
                    f,
                    indent=2,
                )
        except OSError:
            pass    # losing calibration is survivable; crashing is not

    # --- learning ------------------------------------------------------------

    def observe(self, distance_cm: float) -> None:
        """
        Feed one distance in. Call this on every reading.

        The running maximum is what learns the bin depth. Everything else
        follows from it.
        """
        if distance_cm is None:
            return

        self.sample_count += 1

        if self.empty_cm is None or distance_cm > self.empty_cm:
            self.empty_cm = round(distance_cm, 1)
            self.full_cm = _full_distance(self.empty_cm)

        self._save()

    @property
    def confident(self) -> bool:
        return (
            self.empty_cm is not None
            and self.sample_count >= config.MIN_SAMPLES_FOR_CONFIDENCE
        )

    # --- using it ------------------------------------------------------------

    def to_fill_percentage(self, distance_cm: float) -> float:
        """
        Convert a distance to a fill percentage, clamped to 0-100.

        Returns 0.0 when nothing has been learned yet -- but `confident`
        will be False in that case, so downstream knows not to trust it.
        """
        if distance_cm is None or self.empty_cm is None or self.full_cm is None:
            return 0.0

        span = self.empty_cm - self.full_cm
        if span <= 0:
            return 0.0

        pct = (self.empty_cm - distance_cm) / span * 100.0
        return round(min(100.0, max(0.0, pct)), 1)

    def as_dict(self) -> dict:
        """The `calibration` block for the reading payload."""
        return {
            "empty_cm": self.empty_cm,
            "full_cm": self.full_cm,
            "confident": self.confident,
            "sample_count": self.sample_count,
        }

    def reset(self) -> None:
        """Wipe and relearn. Call this when the device moves to a new bin."""
        self.empty_cm = None
        self.full_cm = None
        self.sample_count = 0
        self._save()


def _full_distance(empty_cm: float) -> float:
    """
    The distance reading that means "full".

    Measured from the SENSOR, not from the bottom. A full bin has contents
    close to the sensor, so full_cm is a small number. Getting this
    backwards silently produces fill percentages that look plausible but
    are wildly wrong, so it lives in its own function with this comment.

    Shallow bins get a proportionally smaller margin, otherwise a 30cm bin
    would be "full" at a third empty.
    """
    margin = min(config.FULL_CM_MARGIN, empty_cm * 0.15)
    return round(max(config.MIN_VALID_CM, margin), 1)


if __name__ == "__main__":
    cal = Calibration(path="calibration.test.json")
    cal.reset()

    print("Simulating a bin that gets emptied, then fills up.\n")
    for d in [40, 55, 70, 88, 90, 75, 60, 45, 30, 15]:
        cal.observe(d)
        print(
            f"saw {d:5.1f} cm -> {cal.to_fill_percentage(d):5.1f}% full"
            f"   (empty_cm={cal.empty_cm}, confident={cal.confident})"
        )

    os.remove("calibration.test.json")
