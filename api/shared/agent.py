# agent/agent.py
"""
BinCast AI agent — turns one reading (+ recent history) into a decision that
matches schema/agent-output.schema.json.

Two layers, on purpose:

  1. `classify_reading()` — a deterministic rule engine. This is the safety
     net: fill-level routing and anomaly detection never depend on an LLM
     call succeeding, timing out, or hallucinating a threshold. It's also
     what makes the agent testable without any Azure credentials at all.

  2. `classify_with_foundry()` — calls the Azure AI Foundry agent to turn the
     rule engine's findings into the natural-language `reasoning` a human
     reads on the dashboard, and as a second opinion on `action` for
     borderline cases. If Foundry is unreachable, misconfigured, or returns
     something that doesn't validate against the schema, this silently
     falls back to the rule engine's own reasoning. The agent must never go
     silent just because the LLM call failed.

Auto-calibration note: the bin's empty/full range is learned on the DEVICE
(see device/calibration.py) by watching the running maximum distance. This
module does not relearn it -- that would be two sources of truth for the
same number. What the agent owns is *trusting it correctly*: reading
`calibration.confident` and `calibration.sample_count` and treating
`fill_percentage` as provisional, not authoritative, until the device says
it's confident.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

AGENT_MODEL_VERSION = "bincast-agent-rule-v1"

# --- Thresholds ---------------------------------------------------------------
# Mirrors device/config.py where the same concept exists there (WARNING_PERCENT,
# FULL_PERCENT, MAX_SPREAD_CM) so the two layers agree on what "high" means.
WARNING_FILL_PCT = 70.0
FULL_FILL_PCT = 90.0

# device/config.py flags a single reading unstable above 8cm of spread.
# The agent asks for more before calling it an obstruction outright, because
# a merely-noisy reading and a blocked sensor look similar at first glance.
OBSTRUCTION_SPREAD_CM = 15.0
UNSTABLE_SPREAD_CM = 8.0

# A bin filling faster than this in one hour is more likely a bad reading
# than actual waste. Real bins fill over hours; sensors misfire in seconds.
MAX_PLAUSIBLE_FILL_RATE_CM_PER_HR = 15.0

STUCK_READING_MIN_REPEATS = 3  # current reading + this many identical priors


# --- Public entry point --------------------------------------------------------

def classify_reading(reading: dict, history: list[dict] | None = None) -> dict:
    """
    The rule engine. Pure function: same reading + history in, same decision
    out. No network calls, no randomness -- this is what the test cases in
    tests/test_agent.py exercise directly.

    `history` is the bin's recent prior readings (most recent first is fine
    since we only look at the first couple); pass whatever
    `GET /api/bins/{bin_id}/readings` returns.
    """
    history = history or []

    anomaly_type = _detect_anomaly(reading, history)
    confidence = _estimate_confidence(reading, anomaly_type)
    action = _decide_action(reading, anomaly_type)
    predicted_full_at = _predicted_full_at(reading, anomaly_type)
    reasoning = _explain(reading, anomaly_type, action, confidence)

    return {
        "device_id": reading.get("device_id"),
        "bin_id": reading.get("bin_id"),
        "timestamp": reading.get("timestamp"),
        "fill_percentage": reading.get("fill_percentage", 0.0),
        "confidence": confidence,
        "action": action,
        "reasoning": reasoning,
        "anomaly": {
            "detected": anomaly_type != "none",
            "type": anomaly_type,
            **({"note": _anomaly_note(reading, anomaly_type)} if anomaly_type != "none" else {}),
        },
        "predicted_full_at": predicted_full_at,
        "model_version": AGENT_MODEL_VERSION,
    }


# --- Anomaly detection ("catch weird or blocked readings") --------------------

def _detect_anomaly(reading: dict, history: list[dict]) -> str:
    """
    Checked in order of how much they undermine trust in the reading.
    First match wins -- a sensor that's entirely dead is a bigger problem
    than a bin that's merely uncalibrated, so sensor_error is checked first.
    """
    quality = reading.get("quality") or {}
    samples = quality.get("samples")
    rejected = quality.get("rejected")
    spread = quality.get("spread_cm")
    calibration = reading.get("calibration")
    status = reading.get("status")
    fill_rate = reading.get("fill_rate_cm_per_hr")

    # 1. Sensor error: nothing usable came back, or the device already gave up.
    if status == "error":
        return "sensor_error"
    if samples is not None and rejected is not None and samples > 0 and rejected >= samples:
        return "sensor_error"

    # 2. Obstruction: unstable readings AND rejected pings AND (usually) the
    #    device already flagged it. Requires the combination, not spread alone
    #    -- a single noisy reading shouldn't trigger an inspection.
    if status == "obstructed":
        return "obstruction"
    if spread is not None and spread >= OBSTRUCTION_SPREAD_CM and (rejected or 0) > 0:
        return "obstruction"

    # 3. Implausible jump: the level changed faster than physically likely,
    #    but without the spread/rejection signature of an obstruction --
    #    i.e. something's wrong with the trend, not (as far as we can tell)
    #    this one reading.
    if fill_rate is not None and fill_rate > MAX_PLAUSIBLE_FILL_RATE_CM_PER_HR:
        return "implausible_jump"

    # 4. Stuck reading: identical raw distance across several consecutive
    #    readings. Healthy bins move even slowly; a perfectly flat line
    #    over multiple polls usually means a frozen sensor, not stillness.
    if _is_stuck(reading, history):
        return "stuck_reading"

    # 5. Uncalibrated: the device is honest that it doesn't trust its own
    #    range yet. Nothing here is a sensor problem -- it just means
    #    fill_percentage is provisional.
    if calibration is None or calibration.get("confident") is False:
        return "uncalibrated"

    return "none"


def _is_stuck(reading: dict, history: list[dict]) -> bool:
    current = reading.get("raw_distance_cm")
    if current is None or len(history) < STUCK_READING_MIN_REPEATS - 1:
        return False
    recent = history[: STUCK_READING_MIN_REPEATS - 1]
    return all(
        h.get("raw_distance_cm") is not None and abs(h["raw_distance_cm"] - current) < 0.05
        for h in recent
    )


def _anomaly_note(reading: dict, anomaly_type: str) -> str:
    quality = reading.get("quality") or {}
    if anomaly_type == "sensor_error":
        return f"{quality.get('rejected', 'all')} of {quality.get('samples', '?')} pings rejected; no usable distance."
    if anomaly_type == "obstruction":
        return (
            f"spread_cm={quality.get('spread_cm')}, rejected={quality.get('rejected')}, "
            f"fill_rate={reading.get('fill_rate_cm_per_hr')}cm/hr -- consistent with something blocking the sensor."
        )
    if anomaly_type == "implausible_jump":
        return f"fill_rate_cm_per_hr={reading.get('fill_rate_cm_per_hr')} exceeds plausible fill speed."
    if anomaly_type == "stuck_reading":
        return "raw_distance_cm identical across recent readings."
    if anomaly_type == "uncalibrated":
        cal = reading.get("calibration") or {}
        return f"calibration.confident=false, sample_count={cal.get('sample_count', 0)}."
    return ""


# --- Confidence -----------------------------------------------------------

def _estimate_confidence(reading: dict, anomaly_type: str) -> float:
    quality = reading.get("quality") or {}
    samples = quality.get("samples")
    rejected = quality.get("rejected")
    spread = quality.get("spread_cm")
    calibration = reading.get("calibration")

    if anomaly_type == "sensor_error":
        return 0.05

    if anomaly_type == "uncalibrated":
        sample_count = (calibration or {}).get("sample_count", 0)
        return round(min(0.5, 0.15 + 0.03 * sample_count), 2)

    if anomaly_type in ("obstruction", "implausible_jump", "stuck_reading"):
        # Confidence here means "how sure the agent is that something is
        # wrong", not confidence in fill_percentage -- those are different
        # questions once an anomaly is flagged.
        evidence = 0.6
        if spread is not None:
            evidence += min(0.3, spread / 60)
        if rejected:
            evidence += min(0.15, rejected * 0.05)
        return round(min(0.95, evidence), 2)

    # Clean reading: start high, discount for noise.
    conf = 0.97
    if spread is not None:
        conf -= min(0.4, spread / 40)
    if rejected and samples:
        conf -= min(0.3, rejected / samples)
    if calibration and calibration.get("confident") is False:
        conf = min(conf, 0.5)
    return round(max(0.05, min(0.99, conf)), 2)


# --- Routing ("what info the agent outputs": the action) ----------------------

def _decide_action(reading: dict, anomaly_type: str) -> str:
    if anomaly_type in ("sensor_error", "obstruction", "implausible_jump", "stuck_reading"):
        return "inspect"
    if anomaly_type == "uncalibrated":
        return "recalibrate"

    fill_pct = reading.get("fill_percentage", 0.0)
    if fill_pct >= FULL_FILL_PCT:
        return "schedule_pickup"
    return "no_action"  # includes the 70-90% warning band: forecast, don't dispatch yet


def _predicted_full_at(reading: dict, anomaly_type: str):
    # Don't forecast off a rate we don't trust.
    if anomaly_type in ("sensor_error", "obstruction", "implausible_jump", "stuck_reading"):
        return None

    fill_rate = reading.get("fill_rate_cm_per_hr")
    calibration = reading.get("calibration")
    raw = reading.get("raw_distance_cm")
    if not fill_rate or fill_rate <= 0 or not calibration or raw is None:
        return None

    full_cm = calibration.get("full_cm")
    if full_cm is None:
        return None

    remaining_cm = raw - full_cm
    try:
        ts = datetime.fromisoformat(reading["timestamp"].replace("Z", "+00:00"))
    except (ValueError, KeyError, AttributeError):
        return None

    if remaining_cm <= 0:
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")  # already at/past the full line

    hours = remaining_cm / fill_rate
    predicted = ts + timedelta(hours=hours)
    return predicted.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Explanation ("explainability requirement") --------------------------------

def _explain(reading: dict, anomaly_type: str, action: str, confidence: float) -> str:
    fill_pct = reading.get("fill_percentage", 0.0)
    bin_id = reading.get("bin_id", "this bin")

    if anomaly_type == "sensor_error":
        return (
            f"{bin_id}: sensor returned no usable reading (pings rejected). "
            "Cannot trust fill level right now -- flagging for inspection."
        )
    if anomaly_type == "obstruction":
        return (
            f"{bin_id}: reading looks like {fill_pct}% full, but spread and rejected "
            "pings point to something blocking the sensor rather than genuine fill. "
            "Recommending inspection, not pickup."
        )
    if anomaly_type == "implausible_jump":
        return (
            f"{bin_id}: fill level rose faster than physically plausible "
            f"({reading.get('fill_rate_cm_per_hr')} cm/hr). Likely a bad reading -- inspect before acting."
        )
    if anomaly_type == "stuck_reading":
        return (
            f"{bin_id}: distance reading hasn't changed across recent polls. "
            "Possible frozen or failed sensor -- inspect."
        )
    if anomaly_type == "uncalibrated":
        cal = reading.get("calibration") or {}
        return (
            f"{bin_id}: still learning this bin's range ({cal.get('sample_count', 0)} samples so far). "
            f"Fill estimate ({fill_pct}%) is provisional until calibration is confident."
        )

    if action == "schedule_pickup":
        return f"{bin_id}: reading is clean and fill is {fill_pct}%, at or above the pickup threshold."
    if fill_pct >= WARNING_FILL_PCT:
        return (
            f"{bin_id}: fill is {fill_pct}%, approaching full but not there yet. "
            "No action needed now -- see predicted_full_at for the forecast."
        )
    return f"{bin_id}: fill is {fill_pct}%, reading is clean. Nothing to do."


# --- Optional: Azure AI Foundry call for the natural-language layer -----------

def classify_with_foundry(reading: dict, history: list[dict] | None = None) -> dict:
    """
    Calls the published Foundry agent (see agent/FOUNDRY_SETUP.md) to produce
    the decision, using the rule engine's own result as the source of truth
    for `action`, `anomaly`, and `confidence` -- the LLM is only trusted to
    write the `reasoning` string and, optionally, override `action` one notch
    in either direction on genuinely ambiguous cases (never across the
    inspect/recalibrate boundary; those stay rule-driven).

    Calls the agent's published endpoint directly over the Responses API
    protocol, authenticating with the caller's Entra identity (DefaultAzureCredential)
    against the agent's own Entra agent identity -- there's no separate
    "agent ID" to configure in the current Foundry publishing model, just the
    one endpoint URL shown on the agent's details page.

    Falls back to the pure rule engine's own reasoning whenever:
      - BINCAST_FOUNDRY_AGENT_ENDPOINT isn't set,
      - the `requests` / `azure-identity` packages aren't available,
      - the call fails, times out, or returns a non-200,
      - the response doesn't parse into the expected JSON shape.
    A production agent that goes silent when the LLM hiccups is worse than
    one that just uses its own deterministic reasoning.
    """
    baseline = classify_reading(reading, history)

    endpoint = os.environ.get("BINCAST_FOUNDRY_AGENT_ENDPOINT")
    if not endpoint:
        return baseline

    try:
        import requests
        from azure.identity import DefaultAzureCredential

        token = DefaultAzureCredential().get_token("https://ai.azure.com/.default").token
        prompt = _build_foundry_prompt(reading, history, baseline)

        resp = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"input": prompt},
            timeout=15,
        )
        if resp.status_code != 200:
            return baseline

        llm_result = _parse_responses_output(resp.json())
        if llm_result is None:
            return baseline

        merged = dict(baseline)
        if isinstance(llm_result.get("reasoning"), str) and 10 <= len(llm_result["reasoning"]) <= 500:
            merged["reasoning"] = llm_result["reasoning"]
        # action is only accepted from the LLM if it doesn't cross the
        # inspect/recalibrate line the rule engine already drew.
        safe_actions = {"no_action", "schedule_pickup"}
        if baseline["action"] in safe_actions and llm_result.get("action") in safe_actions:
            merged["action"] = llm_result["action"]
        merged["model_version"] = f"{AGENT_MODEL_VERSION}+foundry"
        return merged

    except Exception:
        return baseline


def _parse_responses_output(response_json: dict):
    """
    Pulls the assistant's text out of a Responses-API-shaped payload and
    parses it as the {"action", "reasoning"} JSON the agent's instructions
    ask for. Returns None on anything unexpected -- the caller falls back
    to the rule engine rather than trusting a shape we didn't ask for.
    """
    try:
        text = response_json["output_text"]
    except (KeyError, TypeError):
        text = None

    if not text:
        try:
            for item in response_json.get("output", []):
                if item.get("type") == "message":
                    for part in item.get("content", []):
                        if part.get("type") in ("output_text", "text"):
                            text = part.get("text")
                            break
                if text:
                    break
        except (AttributeError, TypeError):
            text = None

    if not text:
        return None

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _build_foundry_prompt(reading: dict, history: list[dict] | None, baseline: dict) -> str:
    return json.dumps(
        {
            "reading": reading,
            "recent_history": (history or [])[:5],
            "rule_engine_findings": {
                "action": baseline["action"],
                "anomaly": baseline["anomaly"],
                "confidence": baseline["confidence"],
            },
        },
        default=str,
    )


if __name__ == "__main__":
    # Quick manual run over the shared sample data.
    here = os.path.dirname(os.path.abspath(__file__))
    samples_path = os.path.join(here, "..", "schema", "sample-readings.json")
    with open(samples_path) as f:
        samples = json.load(f)

    history_by_bin: dict[str, list[dict]] = {}
    for s in samples:
        s = dict(s)
        s.pop("_case", None)
        bin_id = s["bin_id"]
        decision = classify_reading(s, history=history_by_bin.get(bin_id, []))
        print(f"{s['timestamp']}  {bin_id:10s}  fill={s['fill_percentage']:5.1f}%  "
              f"-> action={decision['action']:15s} conf={decision['confidence']:.2f}  "
              f"anomaly={decision['anomaly']['type']}")
        history_by_bin.setdefault(bin_id, []).insert(0, s)
