"""
Table Storage helper for the BinCast backend.

Design (matches proposal Sections 4 + 7):

  Table "readings"         PartitionKey = bin_id, RowKey = inverted timestamp
      -> newest-first reads without sorting the whole partition in memory.
  Table "decisions"        PartitionKey = bin_id, RowKey = decision_id
      -> one agent decision per reading, plus the human approve/reject.
  Table "bins"             PartitionKey = "bin",  RowKey = bin_id
      -> the roster: which bins exist and where they are. Location lives
         here because it is a property of the BIN, not of a reading --
         the device is designed to move between bins.

Connection string comes from an app setting (Key Vault reference in Azure),
never hardcoded. See Section 8: Security and Responsible AI.

--------------------------------------------------------------------------
IMPORTANT -- why the flatten/unflatten pair exists
--------------------------------------------------------------------------
Azure Table Storage entities only accept FLAT primitive values: str, int,
float, bool, datetime, bytes, GUID. A nested dict raises on insert.

Our data contract has two nested objects (`calibration` and `quality`), so
every reading is flattened on the way in:

    {"calibration": {"empty_cm": 82.0}}  ->  {"calibration__empty_cm": 82.0}

and rebuilt on the way out, so the rest of the codebase and the dashboard
only ever see the contract shape. Nothing outside this module needs to know
the storage layer is flat.
"""

import os
import json
from datetime import datetime, timezone

from azure.data.tables import TableServiceClient, TableClient
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

CONNECTION_STRING_ENV_VAR = "BINCAST_STORAGE_CONNECTION_STRING"

READINGS_TABLE = "readings"
DECISIONS_TABLE = "decisions"
BINS_TABLE = "bins"

# Separator for flattened nested keys. Double underscore because no field in
# the data contract contains one, so unflattening is unambiguous.
NESTED_SEP = "__"

# RowKeys sort lexicographically ascending in Table Storage. Storing
# (MAX_TICKS - actual_ticks) means the newest reading sorts FIRST, so
# "give me the last 20" is a top-N query instead of a full partition scan.
_MAX_TICKS = 9999999999999


def _get_connection_string() -> str:
    conn_str = os.environ.get(CONNECTION_STRING_ENV_VAR)
    if not conn_str:
        raise RuntimeError(
            f"Missing required app setting '{CONNECTION_STRING_ENV_VAR}'. "
            "Set it in Azure Function App Settings (never commit it to source). "
            "For local dev, copy local.settings.json.example to "
            "local.settings.json and use 'UseDevelopmentStorage=true' with Azurite."
        )
    return conn_str


def get_table_client(table_name: str) -> TableClient:
    """Returns a client for the given table, creating the table if needed."""
    service_client = TableServiceClient.from_connection_string(_get_connection_string())
    try:
        service_client.create_table(table_name)
    except ResourceExistsError:
        pass
    return service_client.get_table_client(table_name)


# --- Flattening ---------------------------------------------------------------

def _flatten(data: dict, prefix: str = "") -> dict:
    """One level of nesting is all the contract has, but this handles any depth."""
    flat = {}
    for key, value in data.items():
        full_key = f"{prefix}{NESTED_SEP}{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, full_key))
        elif isinstance(value, (list, tuple)):
            # No list fields in the contract today, but fail usefully if one
            # is added rather than throwing an opaque Azure serialization error.
            flat[full_key] = json.dumps(value)
        elif value is None:
            continue  # Table Storage has no concept of a null column.
        else:
            flat[full_key] = value
    return flat


def _unflatten(entity: dict) -> dict:
    """Rebuilds the contract shape and drops Table Storage's own columns."""
    result = {}
    for key, value in entity.items():
        if key in ("PartitionKey", "RowKey", "Timestamp", "etag") or key.startswith("_"):
            continue
        if NESTED_SEP in key:
            parent, child = key.split(NESTED_SEP, 1)
            result.setdefault(parent, {})[child] = value
        else:
            result[key] = value
    return result


def _row_key_for_timestamp(timestamp: str) -> str:
    """
    Inverted-ticks RowKey so newest sorts first.
    Falls back to the raw timestamp if it somehow can't be parsed --
    validation should have caught that long before we get here.
    """
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ticks = int(dt.timestamp() * 1000)
        return f"{_MAX_TICKS - ticks:013d}"
    except (ValueError, AttributeError, OverflowError):
        return timestamp


def _escape(value: str) -> str:
    """
    Escapes a value for an OData filter literal.

    Table Storage filters are string-built, so an unescaped single quote in a
    bin_id would break the query (and in principle widen it). validate_reading()
    already restricts IDs to [a-z0-9-], but this is defence in depth --
    the roster and dashboard paths accept IDs that never went through it.
    """
    return str(value).replace("'", "''")


# --- Readings -----------------------------------------------------------------

def save_reading(reading: dict) -> None:
    """
    Persists a validated reading. Call validate_reading() first --
    this assumes the payload is already schema-valid.
    """
    table_client = get_table_client(READINGS_TABLE)
    entity = _flatten(reading)
    entity["PartitionKey"] = reading["bin_id"]
    entity["RowKey"] = _row_key_for_timestamp(reading["timestamp"])
    table_client.upsert_entity(entity)


def get_recent_readings(bin_id: str, limit: int = 20) -> list:
    """
    Returns the most recent readings for a bin, newest first, in contract shape.
    This is what feeds the dashboard history chart and the agent's trend check.
    """
    table_client = get_table_client(READINGS_TABLE)
    entities = table_client.query_entities(
        query_filter="PartitionKey eq @bin_id",
        parameters={"bin_id": _escape(bin_id)},
        results_per_page=limit,
    )
    readings = []
    for entity in entities:
        readings.append(_unflatten(entity))
        if len(readings) >= limit:
            break
    return readings


def get_latest_reading(bin_id: str):
    """Returns the single newest reading for a bin, or None."""
    readings = get_recent_readings(bin_id, limit=1)
    return readings[0] if readings else None


# --- Decisions ----------------------------------------------------------------

def save_decision(decision: dict) -> None:
    """
    Persists an agent decision. decision_id is derived from the reading
    timestamp so re-processing the same reading overwrites rather than
    duplicating.
    """
    table_client = get_table_client(DECISIONS_TABLE)
    entity = _flatten(decision)
    entity["PartitionKey"] = decision["bin_id"]
    entity["RowKey"] = decision["decision_id"]
    table_client.upsert_entity(entity)


def get_decisions(bin_id: str = None, limit: int = 50) -> list:
    """
    Returns decisions, newest first. Pass bin_id to scope to one bin,
    or leave it out for the dashboard's full decision log.
    """
    table_client = get_table_client(DECISIONS_TABLE)
    if bin_id:
        entities = table_client.query_entities(
            query_filter="PartitionKey eq @bin_id",
            parameters={"bin_id": _escape(bin_id)},
        )
    else:
        entities = table_client.list_entities()

    decisions = [_unflatten(e) for e in entities]
    decisions.sort(key=lambda d: d.get("timestamp", ""), reverse=True)
    return decisions[:limit]


def get_latest_decision(bin_id: str):
    decisions = get_decisions(bin_id=bin_id, limit=1)
    return decisions[0] if decisions else None


def update_decision(bin_id: str, decision_id: str, updates: dict) -> dict:
    """
    Used by the dashboard's approve/reject action to write staff_id,
    confirmed_at, and review_status onto an existing decision.

    Raises ResourceNotFoundError if the decision doesn't exist, so the
    endpoint can return a 404 instead of silently creating a ghost record.
    """
    table_client = get_table_client(DECISIONS_TABLE)
    entity = table_client.get_entity(partition_key=bin_id, row_key=decision_id)
    entity.update(_flatten(updates))
    table_client.update_entity(entity)
    return _unflatten(entity)


# --- Bin roster ---------------------------------------------------------------

def upsert_bin(bin_id: str, location: str = None) -> None:
    """
    Registers a bin. Called automatically on first reading so a device can
    be clipped to a brand-new bin with no setup step -- differentiator #1.
    An unknown bin gets a placeholder location that staff can rename later.
    """
    table_client = get_table_client(BINS_TABLE)
    try:
        existing = table_client.get_entity(partition_key="bin", row_key=bin_id)
        if location and existing.get("location") != location:
            existing["location"] = location
            table_client.update_entity(existing)
        return
    except ResourceNotFoundError:
        pass

    table_client.upsert_entity({
        "PartitionKey": "bin",
        "RowKey": bin_id,
        "bin_id": bin_id,
        "location": location or f"Unassigned ({bin_id})",
        "registered_at": datetime.now(timezone.utc).isoformat(),
    })


def list_bins() -> list:
    """Returns the bin roster: every bin the system has ever seen."""
    table_client = get_table_client(BINS_TABLE)
    return [_unflatten(e) for e in table_client.list_entities()]

def delete_bin(bin_id: str) -> dict:
    """
    Permanently removes a bin and every reading/decision recorded for it.

    Meant for clearing out accidental test entries (test_button.py runs,
    demo dry-runs) — not a routine action. There is no undo: once this
    runs, the readings are gone from Table Storage, not just hidden.
    """
    readings_deleted = _delete_partition(READINGS_TABLE, bin_id)
    decisions_deleted = _delete_partition(DECISIONS_TABLE, bin_id)

    bins_table = get_table_client(BINS_TABLE)
    try:
        bins_table.delete_entity(partition_key="bin", row_key=bin_id)
        bin_deleted = True
    except ResourceNotFoundError:
        bin_deleted = False

    return {
        "bin_id": bin_id,
        "bin_deleted": bin_deleted,
        "readings_deleted": readings_deleted,
        "decisions_deleted": decisions_deleted,
    }


def _delete_partition(table_name: str, partition_key: str) -> int:
    """Deletes every entity in one partition. Returns how many were removed."""
    table_client = get_table_client(table_name)
    entities = table_client.query_entities(
        query_filter="PartitionKey eq @pk",
        parameters={"pk": _escape(partition_key)},
        select=["PartitionKey", "RowKey"],
    )
    count = 0
    for entity in entities:
        table_client.delete_entity(partition_key=entity["PartitionKey"], row_key=entity["RowKey"])
        count += 1
    return count