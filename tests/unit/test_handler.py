"""Unit tests for the Lambda handler and route dispatcher."""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.handler import lambda_handler, _authenticate, ROUTES, PUBLIC_ROUTES
from src.utils import json_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(route_key, body=None, headers=None, path_params=None):
    """Build a minimal API Gateway HTTP API v2 event."""
    event = {
        "routeKey": route_key,
        "headers": headers or {},
        "pathParameters": path_params or {},
    }
    if body is not None:
        event["body"] = json.dumps(body) if isinstance(body, dict) else body
    return event


def _bearer_header(token="valid-token"):
    return {"authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Route table completeness
# ---------------------------------------------------------------------------

class TestRouteTable:
    """Verify the route table covers all expected endpoints."""

    EXPECTED_ROUTES = [
        "POST /auth/login",
        "GET /watches",
        "POST /watches",
        "GET /watches/{watchId}",
        "PUT /watches/{watchId}",
        "DELETE /watches/{watchId}",
        "GET /watches/{watchId}/expenses",
        "POST /watches/{watchId}/expenses",
        "PUT /watches/{watchId}/expenses/{expenseId}",
        "DELETE /watches/{watchId}/expenses/{expenseId}",
        "GET /watches/{watchId}/sale",
        "POST /watches/{watchId}/sale",
        "PUT /watches/{watchId}/sale",
        "DELETE /watches/{watchId}/sale",
        "POST /watches/{watchId}/images/upload-url",
        "POST /watches/{watchId}/images/{imageId}/confirm",
        "GET /watches/{watchId}/images",
        "DELETE /watches/{watchId}/images/{imageId}",
        "GET /portfolio/summary",
    ]

    def test_all_routes_registered(self):
        for route in self.EXPECTED_ROUTES:
            assert route in ROUTES, f"Missing route: {route}"

    def test_no_extra_routes(self):
        for route in ROUTES:
            assert route in self.EXPECTED_ROUTES, f"Unexpected route: {route}"

    def test_only_login_is_public(self):
        assert PUBLIC_ROUTES == {"POST /auth/login"}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAuthentication:
    """Test JWT authentication enforcement."""

    def test_missing_auth_header_returns_401(self):
        event = _make_event("GET /watches")
        result = lambda_handler(event, None)
        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert body["error"]["code"] == "UNAUTHORIZED"

    def test_malformed_auth_header_returns_401(self):
        event = _make_event("GET /watches", headers={"authorization": "Basic abc"})
        result = lambda_handler(event, None)
        assert result["statusCode"] == 401

    def test_empty_bearer_token_returns_401(self):
        event = _make_event("GET /watches", headers={"authorization": "Bearer "})
        result = lambda_handler(event, None)
        assert result["statusCode"] == 401

    @patch("src.handler.auth_service")
    def test_invalid_token_returns_401(self, mock_auth):
        mock_auth.validate_token.side_effect = Exception("invalid token")
        event = _make_event("GET /watches", headers=_bearer_header("bad-token"))
        result = lambda_handler(event, None)
        assert result["statusCode"] == 401

    @patch("src.handler.auth_service")
    @patch("src.handler.watch_service")
    def test_valid_token_passes_through(self, mock_watch, mock_auth):
        mock_auth.validate_token.return_value = {"sub": "admin"}
        mock_watch.list_watches.return_value = json_response(200, {"watches": []})
        event = _make_event("GET /watches", headers=_bearer_header())
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200

    @patch("src.handler.auth_service")
    def test_login_does_not_require_auth(self, mock_auth):
        mock_auth.login.return_value = json_response(200, {"token": "jwt"})
        event = _make_event("POST /auth/login", body={"username": "a", "password": "b"})
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        # validate_token should NOT have been called
        mock_auth.validate_token.assert_not_called()


# ---------------------------------------------------------------------------
# Route dispatching
# ---------------------------------------------------------------------------

class TestRouteDispatch:
    """Test that requests are dispatched to the correct service functions."""

    def test_unknown_route_returns_404(self):
        event = _make_event("GET /unknown")
        result = lambda_handler(event, None)
        assert result["statusCode"] == 404
        body = json.loads(result["body"])
        assert body["error"]["code"] == "NOT_FOUND"

    @patch("src.handler.auth_service")
    @patch("src.handler.watch_service")
    def test_get_watch_dispatches_correctly(self, mock_watch, mock_auth):
        mock_auth.validate_token.return_value = {"sub": "admin"}
        mock_watch.get_watch.return_value = json_response(200, {"watch": {}})
        event = _make_event(
            "GET /watches/{watchId}",
            headers=_bearer_header(),
            path_params={"watchId": "abc-123"},
        )
        result = lambda_handler(event, None)
        mock_watch.get_watch.assert_called_once_with("abc-123")
        assert result["statusCode"] == 200

    @patch("src.handler.auth_service")
    @patch("src.handler.expense_service")
    def test_update_expense_dispatches_correctly(self, mock_expense, mock_auth):
        mock_auth.validate_token.return_value = {"sub": "admin"}
        mock_expense.update_expense.return_value = json_response(200, {"expense": {}})
        body = {"amountCents": 500}
        event = _make_event(
            "PUT /watches/{watchId}/expenses/{expenseId}",
            body=body,
            headers=_bearer_header(),
            path_params={"watchId": "w1", "expenseId": "e1"},
        )
        result = lambda_handler(event, None)
        mock_expense.update_expense.assert_called_once_with("w1", "e1", body)
        assert result["statusCode"] == 200

    @patch("src.handler.auth_service")
    @patch("src.handler.profit_loss_service")
    def test_portfolio_summary_dispatches_correctly(self, mock_pnl, mock_auth):
        mock_auth.validate_token.return_value = {"sub": "admin"}
        mock_pnl.calculate_portfolio_summary.return_value = json_response(200, {"summary": {}})
        event = _make_event("GET /portfolio/summary", headers=_bearer_header())
        result = lambda_handler(event, None)
        mock_pnl.calculate_portfolio_summary.assert_called_once()
        assert result["statusCode"] == 200


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Test consistent error response format and unhandled exception handling."""

    @patch("src.handler.auth_service")
    @patch("src.handler.watch_service")
    def test_unhandled_exception_returns_500(self, mock_watch, mock_auth):
        mock_auth.validate_token.return_value = {"sub": "admin"}
        mock_watch.list_watches.side_effect = RuntimeError("boom")
        event = _make_event("GET /watches", headers=_bearer_header())
        result = lambda_handler(event, None)
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert body["error"]["code"] == "INTERNAL_ERROR"

    def test_error_response_format(self):
        event = _make_event("GET /watches")
        result = lambda_handler(event, None)
        body = json.loads(result["body"])
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "details" in body["error"]

    def test_cors_headers_present_on_error(self):
        event = _make_event("GET /unknown")
        result = lambda_handler(event, None)
        assert result["headers"]["Access-Control-Allow-Origin"] == "*"
