"""Profit/Loss Calculator for Atlas Watch Flip Tracker.

Computes profit/loss for individual watches and portfolio-level summaries
based on expense records and sale records stored in DynamoDB.
All monetary values are in integer cents.
"""

import logging
import os
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


def _serialize_decimal(value):
    """Convert a Decimal to int if it's a whole number, otherwise float."""
    if isinstance(value, Decimal):
        return int(value) if value == int(value) else float(value)
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_watch_pnl(watch_id: str) -> dict:
    """Calculate profit/loss for a single watch.

    Fetches all expenses (PK=WATCH#{id}, SK begins_with EXPENSE#) and the
    sale record (PK=WATCH#{id}, SK=SALE) for the given watch. Computes:
      - If sale exists: pnl = salePriceCents - sum(expense amountCents)
      - If no sale: pnl = -sum(expense amountCents)

    Args:
        watch_id: The watch UUID.

    Returns:
        API Gateway response dict with P&L data (200) or not found (404).
    """
    if not watch_id:
        return error_response(400, "VALIDATION_ERROR", "watchId is required")

    table = _get_table()

    # Verify watch exists
    try:
        watch_result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": "METADATA"}
        )
    except ClientError as exc:
        logger.error("Failed to get watch for P&L: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to calculate P&L")

    if "Item" not in watch_result:
        return error_response(404, "NOT_FOUND", f"Watch {watch_id} not found")

    watch_item = watch_result["Item"]
    purchase_price_cents = _serialize_decimal(watch_item.get("purchasePriceCents", 0)) or 0

    # Fetch all expenses for this watch
    try:
        expense_response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"WATCH#{watch_id}",
                ":sk_prefix": "EXPENSE#",
            },
        )
    except ClientError as exc:
        logger.error("Failed to query expenses for P&L: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to calculate P&L")

    expenses = expense_response.get("Items", [])
    total_expense_cents = sum(
        _serialize_decimal(e.get("amountCents", 0)) for e in expenses
    )

    total_cost_cents = purchase_price_cents + total_expense_cents

    # Fetch sale record
    try:
        sale_result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": "SALE"}
        )
    except ClientError as exc:
        logger.error("Failed to get sale for P&L: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to calculate P&L")

    sale_item = sale_result.get("Item")
    sale_price_cents = None

    if sale_item:
        sale_price_cents = _serialize_decimal(sale_item.get("salePriceCents", 0))
        pnl_cents = sale_price_cents - total_cost_cents
    else:
        pnl_cents = -total_cost_cents

    # Determine indicator
    if pnl_cents > 0:
        indicator = "profit"
    elif pnl_cents < 0:
        indicator = "loss"
    else:
        indicator = "break_even"

    result = {
        "watchId": watch_id,
        "pnlCents": pnl_cents,
        "indicator": indicator,
        "purchasePriceCents": purchase_price_cents,
        "totalExpenseCents": total_expense_cents,
        "salePriceCents": sale_price_cents,
    }

    return json_response(200, result)


def calculate_portfolio_summary() -> dict:
    """Calculate portfolio-level P&L summary across all watches.

    Queries GSI1 for all watches (GSI1PK=WATCHES), computes individual P&L
    for each, and aggregates totals. Unsold watches are tracked in the watch
    list and unsoldCount, but excluded from realized total P&L and
    profit/loss counts.

    Returns:
        API Gateway response dict with portfolio summary (200).
    """
    table = _get_table()

    # Fetch all watches via GSI1
    try:
        response = table.query(
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :pk",
            ExpressionAttributeValues={":pk": "WATCHES"},
        )
    except ClientError as exc:
        logger.error("Failed to list watches for portfolio summary: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to calculate portfolio summary")

    watches = response.get("Items", [])

    total_pnl_cents = 0
    profitable_count = 0
    loss_count = 0
    unsold_count = 0
    watch_pnl_list = []

    for watch_item in watches:
        watch_id = watch_item.get("watchId")
        if not watch_id:
            continue

        purchase_price_cents = _serialize_decimal(watch_item.get("purchasePriceCents", 0)) or 0

        # Fetch expenses for this watch
        try:
            expense_response = table.query(
                KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                ExpressionAttributeValues={
                    ":pk": f"WATCH#{watch_id}",
                    ":sk_prefix": "EXPENSE#",
                },
            )
        except ClientError as exc:
            logger.error("Failed to query expenses for watch %s: %s", watch_id, exc)
            continue

        expenses = expense_response.get("Items", [])
        total_expense_cents = sum(
            _serialize_decimal(e.get("amountCents", 0)) for e in expenses
        )

        total_cost_cents = purchase_price_cents + total_expense_cents

        # Fetch sale record
        try:
            sale_result = table.get_item(
                Key={"PK": f"WATCH#{watch_id}", "SK": "SALE"}
            )
        except ClientError as exc:
            logger.error("Failed to get sale for watch %s: %s", watch_id, exc)
            continue

        sale_item = sale_result.get("Item")
        sale_price_cents = None

        if sale_item:
            sale_price_cents = _serialize_decimal(sale_item.get("salePriceCents", 0))
            pnl_cents = sale_price_cents - total_cost_cents
            total_pnl_cents += pnl_cents
            if pnl_cents > 0:
                profitable_count += 1
            elif pnl_cents < 0:
                loss_count += 1
        else:
            pnl_cents = -total_cost_cents
            unsold_count += 1

        # Determine indicator
        if pnl_cents > 0:
            indicator = "profit"
        elif pnl_cents < 0:
            indicator = "loss"
        else:
            indicator = "break_even"

        watch_pnl_list.append({
            "watchId": watch_id,
            "pnlCents": pnl_cents,
            "indicator": indicator,
            "totalExpenseCents": total_expense_cents,
            "salePriceCents": sale_price_cents,
        })

    summary = {
        "totalPnlCents": total_pnl_cents,
        "profitableCount": profitable_count,
        "lossCount": loss_count,
        "unsoldCount": unsold_count,
        "watches": watch_pnl_list,
    }

    return json_response(200, summary)
