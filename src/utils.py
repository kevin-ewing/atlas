"""Shared utilities for Atlas API responses, request parsing, and parameter extraction."""

import json
import logging

logger = logging.getLogger(__name__)

# CORS headers applied to every response.
# Allows all origins for now; will be restricted to the CloudFront domain later.
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


def json_response(status_code: int, body: dict) -> dict:
    """Build an API Gateway-compatible JSON response with CORS headers.

    Args:
        status_code: HTTP status code (e.g. 200, 400, 404).
        body: Dictionary to serialise as the JSON response body.

    Returns:
        A dict matching the API Gateway HTTP API v2 response format.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            **CORS_HEADERS,
        },
        "body": json.dumps(body),
    }


def error_response(status_code: int, code: str, message: str, details: dict | None = None) -> dict:
    """Build a standardised error response.

    Error format follows the design document:
        {"error": {"code": "ERROR_CODE", "message": "...", "details": {}}}

    Args:
        status_code: HTTP status code.
        code: Machine-readable error code (e.g. ``VALIDATION_ERROR``).
        message: Human-readable description.
        details: Optional dict with additional error context.

    Returns:
        API Gateway response dict.
    """
    return json_response(status_code, {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    })


def parse_body(event: dict) -> dict | None:
    """Parse the JSON body from an API Gateway HTTP API v2 event.

    Args:
        event: The Lambda event dict.

    Returns:
        Parsed dict on success, or ``None`` if the body is missing or invalid.
    """
    raw = event.get("body")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def get_path_parameter(event: dict, name: str) -> str | None:
    """Extract a single path parameter from the event.

    Args:
        event: The Lambda event dict.
        name: The parameter name (e.g. ``watchId``).

    Returns:
        The parameter value as a string, or ``None`` if not present.
    """
    params = event.get("pathParameters") or {}
    return params.get(name)
