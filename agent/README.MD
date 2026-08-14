# Agent — the AI decision layer

Turns one reading into a decision the dashboard can show a human. See
`FOUNDRY_SETUP.md` for how the actual Foundry agent is built (role,
instructions, model settings) — this file covers the code.

## Files

| File | What it is |
|---|---|
| `agent.py` | `classify_reading()` — deterministic rule engine (routing + anomaly detection + confidence). `classify_with_foundry()` — wraps it with a Foundry call for the natural-language reasoning. |
| `FOUNDRY_SETUP.md` | Portal steps: create the agent, paste in instructions, test it, wire the endpoint/agent ID into the app. |

## Why two layers

`action`, `anomaly`, and `confidence` come from `classify_reading()` alone —
a pure function, no network call, fully covered by `tests/test_agent.py`.
The Foundry agent only writes the `reasoning` sentence and, on the
`no_action`/`schedule_pickup` boundary only, may offer a second opinion. It
can never turn a `no_action` into an `inspect`, and it can never be the only
thing standing between a bad reading and a wasted pickup — that's the rule
engine's job, and it works with zero Azure configuration.

If Foundry is unreachable, misconfigured, or returns something that doesn't
parse, `classify_with_foundry()` returns the rule engine's own result. The
flow never blocks on the LLM.

## Auto-calibration: whose job is it

The bin's empty/full range is learned **on the device**
(`device/calibration.py`), by watching the running maximum distance —
that's the zero-config differentiator, and it happens continuously as the
device runs. The agent does not relearn it. What the agent does is *respect*
it:

- `calibration.confident == False` → anomaly `uncalibrated`, action
  `recalibrate`, confidence capped low. The fill percentage is shown but
  flagged provisional, per the schema's own note on that field.
- `calibration` missing entirely (e.g. a sensor-error reading with nothing
  usable) → treated even more conservatively, folded into `sensor_error`.

## Catching weird or blocked readings

`_detect_anomaly()` in `agent.py`, checked in this order (first match wins):

1. **sensor_error** — every ping rejected, or the device already says `status: "error"`.
2. **obstruction** — device says `status: "obstructed"`, or spread ≥ 15cm *and* at least one rejected ping. (Spread alone isn't enough — that's just a noisy reading; it takes the combination.)
3. **implausible_jump** — fill rate > 15cm/hr with no obstruction signature; something's off about the trend even if this one reading looks clean.
4. **stuck_reading** — identical raw distance across the last few polls (needs `history` passed in — a single reading can't show this).
5. **uncalibrated** — `calibration.confident` is `False` or missing.

Two samples in `schema/sample-readings.json` are deliberately paired to test
this: `bin-001@2026-08-07T22:00:00Z` (obstructed, ~100% fill, should say
**inspect**) and `bin-002@2026-08-07T18:30:00Z` (genuinely full, ~99% fill,
should say **schedule_pickup**). Same number, opposite call — if a change to
this file makes those agree, something broke.

## Running it

```bash
# quick manual pass over the shared sample data
python agent/agent.py

# the real test suite
pip install pytest jsonschema
pytest tests/test_agent.py -v
```

## The full flow

```
device --reading--> POST /api/readings
                       |
                       | 1. check      shared/validation.py (schema/reading.schema.json)
                       | 2. ask agent  agent/agent.py -> classify_with_foundry()
                       | 3. route      no_action -> auto_closed; else -> pending
                       | 4. log        every decision saved to the recommendations table
                       v
              dashboard reads GET /api/recommendations (pending queue)
                       |
                       v
        POST /api/recommendations/{bin_id}/{id}/approve  (or /reject)
                       |
                       v
              5. logged: staff_id + timestamp written back to the same record
```

See `api/function_app.py` for the implementation and `api/README.md` for
running the API locally.
