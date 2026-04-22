"""Watch Service for Atlas Watch Flip Tracker.

Handles CRUD operations for watch records, including validation of
required fields and enum values, cascade deletion of associated data
(expenses, sales, images), and listing with GSI1 queries.
"""

import json
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
# Constants
# ---------------------------------------------------------------------------

VALID_MOVEMENT_TYPES = {"automatic", "manual", "quartz"}
VALID_CONDITIONS = {"new", "excellent", "good", "fair", "poor"}
VALID_STATUSES = {"in_collection", "for_sale", "sold"}
VALID_FEATURES = {
    "chronograph", "date", "GMT", "moon phase", "tourbillon",
    "minute repeater", "perpetual calendar", "diving bezel",
    "power reserve indicator", "alarm",
}

# Optional string fields on a watch record
_OPTIONAL_STRING_FIELDS = [
    "referenceNumber", "caseMaterial", "dialColor",
    "bandMaterial", "bandColor", "serialNumber",
    "acquisitionDate", "acquisitionSource", "notes",
]

# Optional fields that need special handling (not plain strings)
_OPTIONAL_SPECIAL_FIELDS = [
    "yearOfProduction", "caseDiameterMm", "movementType",
    "condition", "boxIncluded", "papersIncluded", "features", "status",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_table():
    """Return the DynamoDB Table resource for the Atlas table."""
    table_name = os.environ.get("TABLE_NAME", "")
    return boto3.resource("dynamodb").Table(table_name)


def _get_s3_client():
    """Return an S3 client."""
    return boto3.client("s3")


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _validate_watch_data(data: dict, is_update: bool = False) -> list[str]:
    """Validate watch data and return a list of error messages.

    For creation (is_update=False), maker and model are required.
    For updates, only provided fields are validated.
    """
    errors = []

    if not is_update:
        if not data.get("maker") or not str(data.get("maker", "")).strip():
            errors.append("maker is required")
        if not data.get("model") or not str(data.get("model", "")).strip():
            errors.append("model is required")

    # Validate enum fields if provided
    if "movementType" in data and data["movementType"] is not None:
        if data["movementType"] not in VALID_MOVEMENT_TYPES:
            errors.append(
                f"movementType must be one of: {', '.join(sorted(VALID_MOVEMENT_TYPES))}"
            )

    if "condition" in data and data["condition"] is not None:
        if data["condition"] not in VALID_CONDITIONS:
            errors.append(
                f"condition must be one of: {', '.join(sorted(VALID_CONDITIONS))}"
            )

    if "status" in data and data["status"] is not None:
        if data["status"] not in VALID_STATUSES:
            errors.append(
                f"status must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )

    if "features" in data and data["features"] is not None:
        features = data["features"]
        if not isinstance(features, list):
            errors.append("features must be a list")
        else:
            invalid = [f for f in features if f not in VALID_FEATURES]
            if invalid:
                errors.append(
                    f"invalid features: {', '.join(invalid)}. "
                    f"Valid features: {', '.join(sorted(VALID_FEATURES))}"
                )

    return errors


def _serialize_item(item: dict) -> dict:
    """Convert DynamoDB item to JSON-serializable dict.

    Converts Decimal values to int or float as appropriate and removes
    internal DynamoDB key attributes.
    """
    result = {}
    # Keys to exclude from the public response
    internal_keys = {"PK", "SK", "GSI1PK", "GSI1SK", "entityType"}

    for key, value in item.items():
        if key in internal_keys:
            continue
        if isinstance(value, Decimal):
            # Convert to int if it's a whole number, otherwise float
            if value == int(value):
                result[key] = int(value)
            else:
                result[key] = float(value)
        elif isinstance(value, list):
            result[key] = [
                int(v) if isinstance(v, Decimal) and v == int(v)
                else float(v) if isinstance(v, Decimal)
                else v
                for v in value
            ]
        else:
            result[key] = value

    return result


def _build_watch_item(watch_id: str, data: dict, now: str) -> dict:
    """Build a complete DynamoDB item for a new watch record."""
    acquisition_date = data.get("acquisitionDate", now[:10])
    status = data.get("status", "in_collection")

    item = {
        "PK": f"WATCH#{watch_id}",
        "SK": "METADATA",
        "GSI1PK": "WATCHES",
        "GSI1SK": f"{acquisition_date}#{watch_id}",
        "entityType": "WATCH",
        "watchId": watch_id,
        "maker": data["maker"],
        "model": data["model"],
        "status": status,
        "createdAt": now,
        "updatedAt": now,
    }

    # Add optional string fields
    for field in _OPTIONAL_STRING_FIELDS:
        if field in data and data[field] is not None:
            if field == "acquisitionDate":
                # Already handled above for GSI1SK
                item[field] = data[field]
            else:
                item[field] = data[field]

    # Add optional special fields
    if "yearOfProduction" in data and data["yearOfProduction"] is not None:
        item["yearOfProduction"] = data["yearOfProduction"]
    if "caseDiameterMm" in data and data["caseDiameterMm"] is not None:
        item["caseDiameterMm"] = data["caseDiameterMm"]
    if "movementType" in data and data["movementType"] is not None:
        item["movementType"] = data["movementType"]
    if "condition" in data and data["condition"] is not None:
        item["condition"] = data["condition"]
    if "boxIncluded" in data and data["boxIncluded"] is not None:
        item["boxIncluded"] = data["boxIncluded"]
    if "papersIncluded" in data and data["papersIncluded"] is not None:
        item["papersIncluded"] = data["papersIncluded"]
    if "features" in data and data["features"] is not None:
        item["features"] = data["features"]

    return item


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_watch(data: dict) -> dict:
    """Create a new watch record.

    Args:
        data: Dict with watch attributes. ``maker`` and ``model`` are required.

    Returns:
        API Gateway response dict with the created watch record (201) or
        validation error (400).
    """
    errors = _validate_watch_data(data, is_update=False)
    if errors:
        return error_response(400, "VALIDATION_ERROR", "Validation failed", {"errors": errors})

    watch_id = str(uuid.uuid4())
    now = _now_iso()

    item = _build_watch_item(watch_id, data, now)

    table = _get_table()
    try:
        table.put_item(Item=item)
    except ClientError as exc:
        logger.error("Failed to create watch: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to create watch")

    return json_response(201, _serialize_item(item))


def get_watch(watch_id: str) -> dict:
    """Retrieve a single watch record by ID.

    Args:
        watch_id: The watch UUID.

    Returns:
        API Gateway response dict with the watch record (200) or not found (404).
    """
    if not watch_id:
        return error_response(400, "VALIDATION_ERROR", "watchId is required")

    table = _get_table()
    try:
        result = table.get_item(Key={"PK": f"WATCH#{watch_id}", "SK": "METADATA"})
    except ClientError as exc:
        logger.error("Failed to get watch: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to retrieve watch")

    item = result.get("Item")
    if not item:
        return error_response(404, "NOT_FOUND", f"Watch {watch_id} not found")

    return json_response(200, _serialize_item(item))


def _apply_filters(watches: list[dict], params: dict) -> list[dict]:
    """Apply in-memory filters to a list of serialized watch dicts.

    All specified filters are combined with logical AND.

    Supported query-string parameters:
        maker         – case-insensitive exact match
        status        – exact match (in_collection, for_sale, sold)
        condition     – exact match (new, excellent, good, fair, poor)
        movementType  – exact match (automatic, manual, quartz)
        caseMaterial  – case-insensitive exact match
        yearMin       – inclusive lower bound on yearOfProduction
        yearMax       – inclusive upper bound on yearOfProduction
        features      – comma-separated list; watch must contain ALL
    """
    maker = params.get("maker")
    status = params.get("status")
    condition = params.get("condition")
    movement_type = params.get("movementType")
    case_material = params.get("caseMaterial")
    year_min = params.get("yearMin")
    year_max = params.get("yearMax")
    features_raw = params.get("features")

    # Parse year bounds
    year_min_int = None
    year_max_int = None
    if year_min is not None:
        try:
            year_min_int = int(year_min)
        except (ValueError, TypeError):
            pass
    if year_max is not None:
        try:
            year_max_int = int(year_max)
        except (ValueError, TypeError):
            pass

    # Parse features list
    required_features: list[str] | None = None
    if features_raw:
        required_features = [f.strip() for f in features_raw.split(",") if f.strip()]

    result = []
    for w in watches:
        # maker – case-insensitive exact match
        if maker and w.get("maker", "").lower() != maker.lower():
            continue
        # status – exact match
        if status and w.get("status") != status:
            continue
        # condition – exact match
        if condition and w.get("condition") != condition:
            continue
        # movementType – exact match
        if movement_type and w.get("movementType") != movement_type:
            continue
        # caseMaterial – case-insensitive exact match
        if case_material and w.get("caseMaterial", "").lower() != case_material.lower():
            continue
        # yearMin – inclusive lower bound
        if year_min_int is not None:
            yop = w.get("yearOfProduction")
            if yop is None or yop < year_min_int:
                continue
        # yearMax – inclusive upper bound
        if year_max_int is not None:
            yop = w.get("yearOfProduction")
            if yop is None or yop > year_max_int:
                continue
        # features – watch must contain ALL specified features
        if required_features:
            watch_features = set(w.get("features") or [])
            if not set(required_features).issubset(watch_features):
                continue

        result.append(w)

    return result


def _compute_pnl_for_watch(table, watch_id: str) -> int:
    """Compute profit/loss in cents for a single watch (inline).

    Returns pnl_cents: sale_price - sum(expenses) if sale exists,
    otherwise -sum(expenses).
    """
    # Fetch expenses
    try:
        expense_resp = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"WATCH#{watch_id}",
                ":sk_prefix": "EXPENSE#",
            },
        )
    except ClientError:
        expense_resp = {"Items": []}

    expenses = expense_resp.get("Items", [])
    total_expense_cents = 0
    for e in expenses:
        amt = e.get("amountCents", 0)
        if isinstance(amt, Decimal):
            amt = int(amt)
        total_expense_cents += amt

    # Fetch sale
    try:
        sale_result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": "SALE"}
        )
    except ClientError:
        sale_result = {}

    sale_item = sale_result.get("Item")
    if sale_item:
        sp = sale_item.get("salePriceCents", 0)
        if isinstance(sp, Decimal):
            sp = int(sp)
        return sp - total_expense_cents
    else:
        return -total_expense_cents


def _sort_watches(watches: list[dict], sort_by: str | None, sort_dir: str | None, table) -> list[dict]:
    """Sort a list of serialized watch dicts in-memory.

    Supported sort fields:
        pnl               – computed profit/loss value
        acquisitionDate   – ISO date string
        maker             – alphabetical (case-insensitive)
        yearOfProduction  – integer year

    Default: acquisitionDate descending.
    """
    if not sort_by:
        sort_by = "acquisitionDate"
    if not sort_dir:
        sort_dir = "desc"

    reverse = sort_dir == "desc"

    if sort_by == "pnl":
        # Compute P&L for each watch and attach for sorting
        pnl_map: dict[str, int] = {}
        for w in watches:
            wid = w.get("watchId", "")
            pnl_map[wid] = _compute_pnl_for_watch(table, wid)

        watches.sort(key=lambda w: pnl_map.get(w.get("watchId", ""), 0), reverse=reverse)
    elif sort_by == "acquisitionDate":
        watches.sort(key=lambda w: w.get("acquisitionDate") or "", reverse=reverse)
    elif sort_by == "maker":
        watches.sort(key=lambda w: (w.get("maker") or "").lower(), reverse=reverse)
    elif sort_by == "yearOfProduction":
        watches.sort(key=lambda w: w.get("yearOfProduction") or 0, reverse=reverse)
    else:
        # Unknown sort field — fall back to default
        watches.sort(key=lambda w: w.get("acquisitionDate") or "", reverse=True)

    return watches


def list_watches(event: dict) -> dict:
    """List all watches with optional filtering and sorting.

    Queries GSI1 with GSI1PK=WATCHES, then applies in-memory filters
    (logical AND) and sorts by the requested field/direction.

    Query string parameters (all optional):
        Filters: maker, status, condition, movementType, caseMaterial,
                 yearMin, yearMax, features (comma-separated)
        Sort:    sortBy (pnl|acquisitionDate|maker|yearOfProduction),
                 sortDir (asc|desc)

    Default sort: acquisitionDate descending.

    Args:
        event: The full API Gateway event dict.

    Returns:
        API Gateway response dict with a list of watch records (200).
    """
    table = _get_table()

    try:
        response = table.query(
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :pk",
            ExpressionAttributeValues={":pk": "WATCHES"},
        )
    except ClientError as exc:
        logger.error("Failed to list watches: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to list watches")

    items = response.get("Items", [])
    watches = [_serialize_item(item) for item in items]

    # Extract query string parameters
    params = event.get("queryStringParameters") or {}

    # Apply filters
    watches = _apply_filters(watches, params)

    # Apply sorting
    sort_by = params.get("sortBy")
    sort_dir = params.get("sortDir")
    watches = _sort_watches(watches, sort_by, sort_dir, table)

    return json_response(200, {"watches": watches})


def update_watch(watch_id: str, data: dict) -> dict:
    """Update an existing watch record with partial data.

    Only the provided fields are updated; all other fields are preserved.
    The ``updatedAt`` timestamp is always refreshed.

    Args:
        watch_id: The watch UUID.
        data: Dict with fields to update.

    Returns:
        API Gateway response dict with the updated watch record (200),
        not found (404), or validation error (400).
    """
    if not watch_id:
        return error_response(400, "VALIDATION_ERROR", "watchId is required")

    errors = _validate_watch_data(data, is_update=True)
    if errors:
        return error_response(400, "VALIDATION_ERROR", "Validation failed", {"errors": errors})

    table = _get_table()

    # Fetch existing item
    try:
        result = table.get_item(Key={"PK": f"WATCH#{watch_id}", "SK": "METADATA"})
    except ClientError as exc:
        logger.error("Failed to get watch for update: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to update watch")

    existing = result.get("Item")
    if not existing:
        return error_response(404, "NOT_FOUND", f"Watch {watch_id} not found")

    now = _now_iso()

    # Merge: update only provided fields
    updatable_fields = (
        ["maker", "model"]
        + _OPTIONAL_STRING_FIELDS
        + _OPTIONAL_SPECIAL_FIELDS
    )

    for field in updatable_fields:
        if field in data:
            existing[field] = data[field]

    existing["updatedAt"] = now

    # Update GSI1SK if acquisitionDate changed
    if "acquisitionDate" in data and data["acquisitionDate"] is not None:
        existing["GSI1SK"] = f"{data['acquisitionDate']}#{watch_id}"

    try:
        table.put_item(Item=existing)
    except ClientError as exc:
        logger.error("Failed to update watch: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to update watch")

    return json_response(200, _serialize_item(existing))


def delete_watch(watch_id: str) -> dict:
    """Delete a watch and all associated data (expenses, sale, images).

    Queries all items with PK=WATCH#{id}, batch deletes them from DynamoDB,
    and removes any S3 image objects.

    Args:
        watch_id: The watch UUID.

    Returns:
        API Gateway response dict (200 on success, 404 if watch not found).
    """
    if not watch_id:
        return error_response(400, "VALIDATION_ERROR", "watchId is required")

    table = _get_table()
    pk = f"WATCH#{watch_id}"

    # First check the watch exists
    try:
        result = table.get_item(Key={"PK": pk, "SK": "METADATA"})
    except ClientError as exc:
        logger.error("Failed to check watch existence: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to delete watch")

    if not result.get("Item"):
        return error_response(404, "NOT_FOUND", f"Watch {watch_id} not found")

    # Query ALL items with this PK (watch metadata, expenses, sale, images)
    try:
        query_response = table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": pk},
        )
    except ClientError as exc:
        logger.error("Failed to query watch data for deletion: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to delete watch")

    items = query_response.get("Items", [])

    # Collect S3 keys from image items for deletion
    s3_keys = []
    for item in items:
        sk = item.get("SK", "")
        if sk.startswith("IMAGE#") and "s3Key" in item:
            s3_keys.append(item["s3Key"])

    # Batch delete all DynamoDB items
    try:
        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
    except ClientError as exc:
        logger.error("Failed to batch delete watch data: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to delete watch")

    # Delete S3 image objects
    if s3_keys:
        bucket_name = os.environ.get("IMAGE_BUCKET_NAME", "")
        s3_client = _get_s3_client()
        for key in s3_keys:
            try:
                s3_client.delete_object(Bucket=bucket_name, Key=key)
            except ClientError as exc:
                logger.warning("Failed to delete S3 object %s: %s", key, exc)

    return json_response(200, {"message": f"Watch {watch_id} and all associated data deleted"})
