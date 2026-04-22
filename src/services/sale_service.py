"""Sale Service for Atlas Watch Flip Tracker.

Handles CRUD operations for sale records associated with watches,
including validation of required fields, integer-cents storage,
and watch status management on sale creation/deletion.
"""

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from src.utils import error_response, json_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_table():
    """Return the DynamoDB Table resource for the Atlas table."""
    table_name = os.environ.get("TABLE_NAME", "")
    return boto3.resource("dynamodb").Table(table_name)


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _validate_sale_data(data: dict, is_update: bool = False) -> list[str]:
    """Validate sale data and return a list of error messages.

    For creation (is_update=False), salePriceCents and saleDate are required.
    For updates, only provided fields are validated.
    """
    errors = []

    if not is_update:
        if "salePriceCents" not in data or data.get("salePriceCents") is None:
            errors.append("salePriceCents is required")
        elif not isinstance(data["salePriceCents"], int) or data["salePriceCents"] <= 0:
            errors.append("salePriceCents must be a positive integer")

        if not data.get("saleDate") or not str(data.get("saleDate", "")).strip():
            errors.append("saleDate is required")
    else:
        # For updates, validate only if the field is provided
        if "salePriceCents" in data:
            if not isinstance(data["salePriceCents"], int) or data["salePriceCents"] <= 0:
                errors.append("salePriceCents must be a positive integer")
        if "saleDate" in data:
            if not data["saleDate"] or not str(data["saleDate"]).strip():
                errors.append("saleDate must be a non-empty string")

    return errors


def _serialize_item(item: dict) -> dict:
    """Convert DynamoDB item to JSON-serializable dict.

    Converts Decimal values to int or float as appropriate and removes
    internal DynamoDB key attributes.
    """
    result = {}
    internal_keys = {"PK", "SK", "GSI1PK", "GSI1SK", "entityType"}

    for key, value in item.items():
        if key in internal_keys:
            continue
        if isinstance(value, Decimal):
            result[key] = int(value) if value == int(value) else float(value)
        else:
            result[key] = value

    return result


def _watch_exists(table, watch_id: str) -> bool:
    """Check whether a watch record exists in DynamoDB."""
    try:
        result = table.get_item(Key={"PK": f"WATCH#{watch_id}", "SK": "METADATA"})
        return "Item" in result
    except ClientError:
        return False


def _sale_exists(table, watch_id: str) -> bool:
    """Check whether a sale record already exists for a watch."""
    try:
        result = table.get_item(Key={"PK": f"WATCH#{watch_id}", "SK": "SALE"})
        return "Item" in result
    except ClientError:
        return False


def _update_watch_status(table, watch_id: str, status: str) -> None:
    """Update the watch METADATA item's status field."""
    try:
        table.update_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": "METADATA"},
            UpdateExpression="SET #s = :status, updatedAt = :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": status,
                ":now": _now_iso(),
            },
        )
    except ClientError as exc:
        logger.error("Failed to update watch status: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_sale(watch_id: str, data: dict) -> dict:
    """Create a sale record for a watch.

    Args:
        watch_id: The watch UUID.
        data: Dict with sale attributes. ``salePriceCents`` and ``saleDate``
              are required.

    Returns:
        API Gateway response dict with the created sale (201),
        validation error (400), not found (404), or conflict (409).
    """
    errors = _validate_sale_data(data, is_update=False)
    if errors:
        return error_response(400, "VALIDATION_ERROR", "Validation failed", {"errors": errors})

    table = _get_table()

    if not _watch_exists(table, watch_id):
        return error_response(404, "NOT_FOUND", f"Watch {watch_id} not found")

    if _sale_exists(table, watch_id):
        return error_response(409, "CONFLICT", f"Sale already exists for watch {watch_id}")

    now = _now_iso()

    item = {
        "PK": f"WATCH#{watch_id}",
        "SK": "SALE",
        "GSI1PK": f"WATCH#{watch_id}#SALE",
        "GSI1SK": "SALE",
        "entityType": "SALE",
        "watchId": watch_id,
        "salePriceCents": data["salePriceCents"],
        "saleDate": data["saleDate"],
        "createdAt": now,
        "updatedAt": now,
    }

    # Optional fields
    if data.get("buyerOrPlatform") is not None:
        item["buyerOrPlatform"] = data["buyerOrPlatform"]
    if data.get("notes") is not None:
        item["notes"] = data["notes"]

    try:
        table.put_item(Item=item)
    except ClientError as exc:
        logger.error("Failed to create sale: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to create sale")

    # Update watch status to "sold"
    _update_watch_status(table, watch_id, "sold")

    return json_response(201, _serialize_item(item))


def get_sale(watch_id: str) -> dict:
    """Retrieve the sale record for a watch.

    Args:
        watch_id: The watch UUID.

    Returns:
        API Gateway response dict with the sale record (200) or not found (404).
    """
    if not watch_id:
        return error_response(400, "VALIDATION_ERROR", "watchId is required")

    table = _get_table()
    try:
        result = table.get_item(Key={"PK": f"WATCH#{watch_id}", "SK": "SALE"})
    except ClientError as exc:
        logger.error("Failed to get sale: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to retrieve sale")

    item = result.get("Item")
    if not item:
        return error_response(404, "NOT_FOUND", f"Sale not found for watch {watch_id}")

    return json_response(200, _serialize_item(item))


def update_sale(watch_id: str, data: dict) -> dict:
    """Update an existing sale record with partial data.

    Only the provided fields are updated; all other fields are preserved.
    The ``updatedAt`` timestamp is always refreshed.

    Args:
        watch_id: The watch UUID.
        data: Dict with fields to update.

    Returns:
        API Gateway response dict with the updated sale (200),
        not found (404), or validation error (400).
    """
    errors = _validate_sale_data(data, is_update=True)
    if errors:
        return error_response(400, "VALIDATION_ERROR", "Validation failed", {"errors": errors})

    table = _get_table()

    # Fetch existing sale
    try:
        result = table.get_item(Key={"PK": f"WATCH#{watch_id}", "SK": "SALE"})
    except ClientError as exc:
        logger.error("Failed to get sale for update: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to update sale")

    existing = result.get("Item")
    if not existing:
        return error_response(404, "NOT_FOUND", f"Sale not found for watch {watch_id}")

    now = _now_iso()

    # Merge: update only provided fields
    updatable_fields = ["salePriceCents", "saleDate", "buyerOrPlatform", "notes"]
    for field in updatable_fields:
        if field in data:
            existing[field] = data[field]

    existing["updatedAt"] = now

    try:
        table.put_item(Item=existing)
    except ClientError as exc:
        logger.error("Failed to update sale: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to update sale")

    return json_response(200, _serialize_item(existing))


def delete_sale(watch_id: str) -> dict:
    """Delete a sale record and revert watch status.

    Args:
        watch_id: The watch UUID.

    Returns:
        API Gateway response dict (200 on success, 404 if not found).
    """
    if not watch_id:
        return error_response(400, "VALIDATION_ERROR", "watchId is required")

    table = _get_table()

    # Check sale exists
    try:
        result = table.get_item(Key={"PK": f"WATCH#{watch_id}", "SK": "SALE"})
    except ClientError as exc:
        logger.error("Failed to check sale existence: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to delete sale")

    if not result.get("Item"):
        return error_response(404, "NOT_FOUND", f"Sale not found for watch {watch_id}")

    try:
        table.delete_item(Key={"PK": f"WATCH#{watch_id}", "SK": "SALE"})
    except ClientError as exc:
        logger.error("Failed to delete sale: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to delete sale")

    # Revert watch status to "in_collection"
    _update_watch_status(table, watch_id, "in_collection")

    return json_response(200, {"message": f"Sale for watch {watch_id} deleted"})
