"""Expense Service for Atlas Watch Flip Tracker.

Handles CRUD operations for expense records associated with watches,
including validation of required fields and integer-cents storage.
"""

import logging
import os
import uuid
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


def _validate_expense_data(data: dict, is_update: bool = False) -> list[str]:
    """Validate expense data and return a list of error messages.

    For creation (is_update=False), category and amountCents are required.
    For updates, only provided fields are validated.
    """
    errors = []

    if not is_update:
        if not data.get("category") or not str(data.get("category", "")).strip():
            errors.append("category is required")
        if "amountCents" not in data or data.get("amountCents") is None:
            errors.append("amountCents is required")
        elif not isinstance(data["amountCents"], int) or data["amountCents"] <= 0:
            errors.append("amountCents must be a positive integer")
    else:
        # For updates, validate only if the field is provided
        if "category" in data:
            if not data["category"] or not str(data["category"]).strip():
                errors.append("category must be a non-empty string")
        if "amountCents" in data:
            if not isinstance(data["amountCents"], int) or data["amountCents"] <= 0:
                errors.append("amountCents must be a positive integer")

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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_expense(watch_id: str, data: dict) -> dict:
    """Create a new expense record for a watch.

    Args:
        watch_id: The watch UUID.
        data: Dict with expense attributes. ``category`` and ``amountCents``
              are required.

    Returns:
        API Gateway response dict with the created expense (201),
        validation error (400), or not found (404).
    """
    errors = _validate_expense_data(data, is_update=False)
    if errors:
        return error_response(400, "VALIDATION_ERROR", "Validation failed", {"errors": errors})

    table = _get_table()

    if not _watch_exists(table, watch_id):
        return error_response(404, "NOT_FOUND", f"Watch {watch_id} not found")

    expense_id = str(uuid.uuid4())
    now = _now_iso()
    expense_date = data.get("expenseDate", now[:10])

    item = {
        "PK": f"WATCH#{watch_id}",
        "SK": f"EXPENSE#{expense_id}",
        "GSI1PK": f"WATCH#{watch_id}#EXPENSES",
        "GSI1SK": f"{expense_date}#{expense_id}",
        "entityType": "EXPENSE",
        "expenseId": expense_id,
        "watchId": watch_id,
        "category": data["category"].strip(),
        "amountCents": data["amountCents"],
        "expenseDate": expense_date,
        "createdAt": now,
        "updatedAt": now,
    }

    # Optional fields
    if data.get("vendor") is not None:
        item["vendor"] = data["vendor"]
    if data.get("description") is not None:
        item["description"] = data["description"]

    try:
        table.put_item(Item=item)
    except ClientError as exc:
        logger.error("Failed to create expense: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to create expense")

    return json_response(201, _serialize_item(item))


def list_expenses(watch_id: str) -> dict:
    """List all expenses for a watch.

    Args:
        watch_id: The watch UUID.

    Returns:
        API Gateway response dict with a list of expense records (200).
    """
    table = _get_table()

    try:
        response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"WATCH#{watch_id}",
                ":sk_prefix": "EXPENSE#",
            },
        )
    except ClientError as exc:
        logger.error("Failed to list expenses: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to list expenses")

    items = response.get("Items", [])
    expenses = [_serialize_item(item) for item in items]

    return json_response(200, {"expenses": expenses})


def update_expense(watch_id: str, expense_id: str, data: dict) -> dict:
    """Update an existing expense record with partial data.

    Only the provided fields are updated; all other fields are preserved.
    The ``updatedAt`` timestamp is always refreshed.

    Args:
        watch_id: The watch UUID.
        expense_id: The expense UUID.
        data: Dict with fields to update.

    Returns:
        API Gateway response dict with the updated expense (200),
        not found (404), or validation error (400).
    """
    errors = _validate_expense_data(data, is_update=True)
    if errors:
        return error_response(400, "VALIDATION_ERROR", "Validation failed", {"errors": errors})

    table = _get_table()

    # Fetch existing expense
    try:
        result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": f"EXPENSE#{expense_id}"}
        )
    except ClientError as exc:
        logger.error("Failed to get expense for update: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to update expense")

    existing = result.get("Item")
    if not existing:
        return error_response(404, "NOT_FOUND", f"Expense {expense_id} not found")

    now = _now_iso()

    # Merge: update only provided fields
    updatable_fields = ["category", "amountCents", "expenseDate", "vendor", "description"]
    for field in updatable_fields:
        if field in data:
            existing[field] = data[field]

    existing["updatedAt"] = now

    # Update GSI1SK if expenseDate changed
    if "expenseDate" in data and data["expenseDate"] is not None:
        existing["GSI1SK"] = f"{data['expenseDate']}#{expense_id}"

    try:
        table.put_item(Item=existing)
    except ClientError as exc:
        logger.error("Failed to update expense: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to update expense")

    return json_response(200, _serialize_item(existing))


def delete_expense(watch_id: str, expense_id: str) -> dict:
    """Delete a single expense record.

    Args:
        watch_id: The watch UUID.
        expense_id: The expense UUID.

    Returns:
        API Gateway response dict (200 on success, 404 if not found).
    """
    table = _get_table()

    # Check expense exists
    try:
        result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": f"EXPENSE#{expense_id}"}
        )
    except ClientError as exc:
        logger.error("Failed to check expense existence: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to delete expense")

    if not result.get("Item"):
        return error_response(404, "NOT_FOUND", f"Expense {expense_id} not found")

    try:
        table.delete_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": f"EXPENSE#{expense_id}"}
        )
    except ClientError as exc:
        logger.error("Failed to delete expense: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to delete expense")

    return json_response(200, {"message": f"Expense {expense_id} deleted"})
