# Schema — the shared data contract

Everything in Bincast talks through these two shapes. Build against them with
the sample data now; swap in real integrations later.

## Files

| File | What it defines | Who it's for |
|---|---|---|
| `reading.schema.json` | What the device sends to the cloud | device pair, Kate |
| `agent-output.schema.json` | What the agent returns | Anh Quan, Kate, Mary |
| `sample-readings.json` | Ten readings covering the main scenarios | everyone |

## Conventions

**`snake_case` everywhere.** Field names, enum values, all of it. The device
and agent are Python; JavaScript reads snake keys fine.

**Enum values are lowercase.** `"online"`, not `"Online"`.

**Timestamps are UTC, ISO 8601, with a trailing `Z`.** The timestamp is when
the reading was *taken*, not when it was sent — a buffered reading keeps its
original time.

## The flow

```
device  --reading-->  api  --reading-->  agent
                       |                   |
                       |<--decision--------|
                       |
                 dashboard reads both
```

## Two things the schema deliberately does not have

**No configured bin height.** The device learns each bin's range by
observation and reports it in `calibration`. `confident` is false until it has
enough samples. This is the zero-config differentiator — if a human types in a
bin depth anywhere, the feature isn't real.

**No pre-computed sensor confidence on the reading.** The device reports raw
evidence (`quality.spread_cm`, `quality.rejected`, `fill_rate_cm_per_hr`) and
the *agent* reaches its own confidence from it. Handing the agent a confidence
number to repeat isn't reasoning.

## Rules

**Don't change a schema alone.** Both files are consumed by at least three
people. Raise it in the group chat, then change it in one commit.

**Additive changes are safe, renames are not.** Adding an optional field
breaks nothing. Renaming or removing one breaks everyone downstream.

**`additionalProperties` is `false` on purpose.** If validation rejects a
field you think should exist, fix the schema — not the validator.

## Using the samples

Each entry has a `_case` key describing what it represents. That is
documentation only, not part of the schema — strip it before validating.

The obstruction case and the genuinely-full case are the pair worth testing
against: near-identical `fill_percentage`, opposite correct recommendation.
If the agent treats them the same, the anomaly reasoning isn't working.

## Validating

```bash
pip install jsonschema
```

```python
import json
from jsonschema import validate

schema = json.load(open("schema/reading.schema.json"))
samples = json.load(open("schema/sample-readings.json"))

for s in samples:
    s.pop("_case", None)
    validate(instance=s, schema=schema)
print(f"{len(samples)} samples valid")
```
