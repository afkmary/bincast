# Device — Raspberry Pi edge code

Reads the bin, shows fill on the LCD, sets the status light, sends to the
cloud, and caches when it can't.

## Run it without any hardware

```bash
# Windows PowerShell
$env:BINCAST_MOCK="true"; python main.py

# Mac / Linux / Pi
BINCAST_MOCK=true python3 main.py
```

Mock mode fakes the sensor, prints the LCD as a box in the terminal, and
prints the LED state. Nobody needs the Pi to work on this.

Each module also runs standalone for testing just that piece:

```bash
python sensor.py        # live distance readings
python calibration.py   # watch it learn a bin's range
python display.py       # cycle through every screen
python leds.py          # cycle through every light state
python cache.py         # write and read the cache
```

## Splitting the work

The two halves barely touch, so they can be built in parallel:

| | Files | Needs hardware? |
|---|---|---|
| **Sensing** | `sensor.py`, `calibration.py`, `config.py` | Yes |
| **Output + cloud** | `display.py`, `leds.py`, `cloud.py`, `cache.py` | No |

`main.py` is where the two meet, so it's the only real merge-conflict risk.
One person should own it, and it should change last.

## Wiring

Pin numbers are BCM, set in `config.py`.

| Component | Pin | GPIO |
|---|---|---|
| HC-SR04 VCC | 2 | 5V |
| HC-SR04 TRIG | 16 | GPIO23 |
| HC-SR04 ECHO | 18 | GPIO24 |
| HC-SR04 GND | 6 | GND |
| LED red | 11 | GPIO17 |
| LED green | 13 | GPIO27 |
| LED blue | 15 | GPIO22 |
| LCD SDA | 3 | GPIO2 |
| LCD SCL | 5 | GPIO3 |

**The ECHO pin outputs 5V and the Pi's GPIO is 3.3V.** Put a voltage divider
on it — 1kΩ from ECHO to GPIO24, 2kΩ from GPIO24 to ground. Skipping this
can damage the Pi.

Each LED leg needs its own resistor, 220Ω or 330Ω.

## Enabling I2C for the LCD

```bash
sudo raspi-config      # Interface Options -> I2C -> Enable
sudo i2cdetect -y 1    # should show 27 or 3f
```

If the address isn't `0x27`, set `LCD_I2C_ADDRESS` in `config.py`.

## Auto-start on boot

```bash
sudo cp smartbin.service /etc/systemd/system/bincast.service
sudo systemctl daemon-reload
sudo systemctl enable bincast
sudo systemctl start bincast
```

Check it:

```bash
sudo systemctl status bincast
journalctl -u bincast -f
```

Edit the `Environment=` lines in the unit file to set the device and bin ID
before installing. Those are the only per-device values.

## Status light

| State | Light | Meaning |
|---|---|---|
| ok | steady green | nothing to do |
| warning | steady amber | filling up |
| full | flashing red | needs pickup |
| obstructed | flashing amber | reading is suspect |
| error | flashing red | sensor fault |
| calibrating | flashing blue | still learning the bin |
| offline | steady blue | caching locally |

Priority: a sensor fault outranks a full bin, because a fault means the fill
number can't be trusted in the first place.

## Auto-calibration

Nobody configures a bin depth. `calibration.py` tracks the largest plausible
distance ever seen — when a bin is emptied, the sensor sees to the bottom,
so that running maximum converges on the true depth. `confident` stays false
until 30 readings are in, and everything downstream treats fill as
provisional until then.

When the device moves to a new bin, call `Calibration().reset()` or delete
`calibration.json`.

## Before Kate's endpoint exists

Leave `BINCAST_API_URL` empty. `cloud.send()` returns False, readings go to
`cache.jsonl`, and the offline path gets exercised properly. When the URL is
set, the cache flushes automatically on the next successful send.

Check what's queued:

```bash
wc -l cache.jsonl
```

## The one rule

`cloud.build_payload()` is the only place reading field names are written.
It must match `schema/reading.schema.json`. If you change one, change the
other in the same commit.
