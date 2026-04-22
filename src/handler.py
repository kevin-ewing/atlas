"""Lambda handler entry point for the Atlas Watch Flip Tracker API.

Routes all API Gateway HTTP API v2 requests to the appropriate service
function.  Every route except ``POST /auth/login`` requires a valid JWT
in the ``Authorization: Bearer <token>`` header.
"""

import logging
import traceback

from src.utils import error_response, json_response, parse_body, get_path_parameter
from src.services import auth_service, watch_service, expense_service, sale_service, image_service, profit_loss_service

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Route table
# ---------------------------------------------------------------------------
# Each key is the API Gateway ``routeKey`` (e.g. "GET /watches").
# The value is a callable that accepts (event, body, path_params) and returns
# an API Gateway response dict.
# ---------------------------------------------------------------------------

def _route_login(event, body, _params):
    return auth_service.login(body or {})


def _route_list_watches(event, body, _params):
    return watch_service.list_watches(event)


def _route_create_watch(event, body, _params):
    return watch_service.create_watch(body or {})


def _route_get_watch(event, body, params):
    return watch_service.get_watch(params.get("watchId"))


def _route_update_watch(event, body, params):
    return watch_service.update_watch(params.get("watchId"), body or {})


def _route_delete_watch(event, body, params):
    return watch_service.delete_watch(params.get("watchId"))


def _route_list_expenses(event, body, params):
    return expense_service.list_expenses(params.get("watchId"))


def _route_create_expense(event, body, params):
    return expense_service.create_expense(params.get("watchId"), body or {})


def _route_update_expense(event, body, params):
    return expense_service.update_expense(
        params.get("watchId"), params.get("expenseId"), body or {},
    )


def _route_delete_expense(event, body, params):
    return expense_service.delete_expense(params.get("watchId"), params.get("expenseId"))


def _route_get_sale(event, body, params):
    return sale_service.get_sale(params.get("watchId"))


def _route_create_sale(event, body, params):
    return sale_service.create_sale(params.get("watchId"), body or {})


def _route_update_sale(event, body, params):
    return sale_service.update_sale(params.get("watchId"), body or {})


def _route_delete_sale(event, body, params):
    return sale_service.delete_sale(params.get("watchId"))


def _route_get_upload_url(event, body, params):
    return image_service.get_upload_url(params.get("watchId"), body or {})


def _route_confirm_upload(event, body, params):
    return image_service.confirm_upload(params.get("watchId"), params.get("imageId"))


def _route_list_images(event, body, params):
    return image_service.list_images(params.get("watchId"))


def _route_delete_image(event, body, params):
    return image_service.delete_image(params.get("watchId"), params.get("imageId"))


def _route_portfolio_summary(event, body, _params):
    return profit_loss_service.calculate_portfolio_summary()


ROUTES = {
    # Auth
    "POST /auth/login": _route_login,
    # Watches
    "GET /watches": _route_list_watches,
    "POST /watches": _route_create_watch,
    "GET /watches/{watchId}": _route_get_watch,
    "PUT /watches/{watchId}": _route_update_watch,
    "DELETE /watches/{watchId}": _route_delete_watch,
    # Expenses
    "GET /watches/{watchId}/expenses": _route_list_expenses,
    "POST /watches/{watchId}/expenses": _route_create_expense,
    "PUT /watches/{watchId}/expenses/{expenseId}": _route_update_expense,
    "DELETE /watches/{watchId}/expenses/{expenseId}": _route_delete_expense,
    # Sale
    "GET /watches/{watchId}/sale": _route_get_sale,
    "POST /watches/{watchId}/sale": _route_create_sale,
    "PUT /watches/{watchId}/sale": _route_update_sale,
    "DELETE /watches/{watchId}/sale": _route_delete_sale,
    # Images
    "POST /watches/{watchId}/images/upload-url": _route_get_upload_url,
    "POST /watches/{watchId}/images/{imageId}/confirm": _route_confirm_upload,
    "GET /watches/{watchId}/images": _route_list_images,
    "DELETE /watches/{watchId}/images/{imageId}": _route_delete_image,
    # Portfolio
    "GET /portfolio/summary": _route_portfolio_summary,
}

# The only route that does NOT require authentication.
PUBLIC_ROUTES = {"POST /auth/login"}


# ---------------------------------------------------------------------------
# Authentication helper
# ---------------------------------------------------------------------------

def _authenticate(event: dict) -> dict | None:
    """Validate the JWT from the Authorization header.

    Returns:
        The decoded token claims dict on success, or an error response dict
        on failure (which should be returned directly to API Gateway).
    """
    headers = event.get("headers") or {}
    # API Gateway HTTP API v2 lowercases all header names.
    auth_header = headers.get("authorization", "")

    if not auth_header.startswith("Bearer "):
        return error_response(401, "UNAUTHORIZED", "Missing or invalid authentication token")

    token = auth_header[len("Bearer "):]
    try:
        claims = auth_service.validate_token(token)
        return claims  # dict with user info — not an error
    except Exception:
        return error_response(401, "UNAUTHORIZED", "Missing or invalid authentication token")


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    """Main Lambda handler — authenticates and dispatches to service layer."""
    route_key = event.get("routeKey", "")

    # Look up the handler for this route.
    handler_fn = ROUTES.get(route_key)
    if handler_fn is None:
        return error_response(404, "NOT_FOUND", f"Route not found: {route_key}")

    # Authenticate (skip for public routes).
    if route_key not in PUBLIC_ROUTES:
        auth_result = _authenticate(event)
        # If auth_result is a response dict (has "statusCode"), it's an error.
        if isinstance(auth_result, dict) and "statusCode" in auth_result:
            return auth_result

    # Parse request body and path parameters.
    body = parse_body(event)
    path_params = event.get("pathParameters") or {}

    try:
        return handler_fn(event, body, path_params)
    except Exception as exc:
        logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
        return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred")
