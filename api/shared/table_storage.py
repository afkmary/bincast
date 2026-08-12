"""
Table Storage helper for the AI/ML... err, for the BinCast backend.

Design (matches proposal Section 4 + 7):
- Table: "readings"        PartitionKey = bin_id, RowKey = timestamp (ISO 8601)
    -> fast "give me all readings for bin X, in time order" queries,
       which is exactly what the fill-rate trend and the AI agent need.
- Table: "recommendations" PartitionKey = bin_id, RowKey = recommendation_id
    -> ties each recommendation back to its bin for the dashboard's
       pending-pickup queue and decision log.

Connection string is read from an environment variable (App Settings /
Key Vault reference) — never hardcoded. See Section 8: Security and
Responsible AI.
"""

import os
from azure.data.tables import TableServiceClient, TableClient
from azure.core.exceptions import ResourceExistsError

CONNECTION_STRING_ENV_VAR = "BINCAST_STORAGE_CONNECTION_STRING"

READINGS_TABLE = "readings"
RECOMMENDATIONS_TABLE = "recommendations"


def _get_connection_string() -> str:
    conn_str = os.environ.get(CONNECTION_STRING_ENV_VAR)
    if not conn_str:
        raise RuntimeError(
            f"Missing required app setting '{CONNECTION_STRING_ENV_VAR}'. "
            "Set it in Azure Function App Settings (never commit it to source)."
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


def save_reading(reading: dict) -> None:
    """
    Persists a validated reading. Call validate_reading() first —
    this function assumes the payload is already schema-valid.
    """
    table_client = get_table_client(READINGS_TABLE)
    entity = {
        "PartitionKey": reading["bin_id"],
        "RowKey": reading["timestamp"],
        **reading,
    }
    table_client.upsert_entity(entity)


def get_recent_readings(bin_id: str, limit: int = 20) -> list:
    """
    Returns the most recent readings for a bin, newest first.
    This is what feeds the AI agent's fill-rate trend (Section 5).
    """
    table_client = get_table_client(READINGS_TABLE)
    entities = table_client.query_entities(
        query_filter=f"PartitionKey eq '{bin_id}'"
    )
    readings = sorted(entities, key=lambda e: e["RowKey"], reverse=True)
    return readings[:limit]


def save_recommendation(recommendation: dict) -> None:
    """Persists an agent-generated pickup recommendation."""
    table_client = get_table_client(RECOMMENDATIONS_TABLE)
    entity = {
        "PartitionKey": recommendation["bin_id"],
        "RowKey": recommendation["recommendation_id"],
        **recommendation,
    }
    table_client.upsert_entity(entity)


def update_recommendation_status(bin_id: str, recommendation_id: str, updates: dict) -> None:
    """
    Used by the dashboard's approve/reject action to write staff_id,
    confirmation_timestamp, confirmation_source, recommendation_status, etc.
    """
    table_client = get_table_client(RECOMMENDATIONS_TABLE)
    entity = table_client.get_entity(partition_key=bin_id, row_key=recommendation_id)
    entity.update(updates)
    table_client.update_entity(entity)
