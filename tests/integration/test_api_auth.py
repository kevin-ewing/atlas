"""Integration tests for the end-to-end authentication flow.

Tests exercise the Lambda handler directly with API Gateway HTTP API v2
events, using moto mocks for all AWS services.

Requirements validated: 1.1–1.8
"""

import json
from datetime import datetime, timezone, timedelta

import src.services.auth_service as auth_mod
from src.handler import lambda_handler
from tests.conftest import TEST_USERNAME, TEST_PASSWORD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login_event(username, password):
    """Build an API Gateway event for POST /auth/login."""
    return {
        "routeKey": "POST /auth/login",
        "headers": {},
        "pathParameters": {},
        "body": json.dumps({"username": username, "password": password}),
    }


def _parse_body(response):
    """Parse the JSON body from a Lambda response."""
    return json.loads(response["body"])


def _authenticated_event(route_key, token, path_params=None, body=None):
    """Build an authenticated API Gateway event."""
    event = {
        "routeKey": route_key,
        "headers": {"authorization": f"Bearer {token}"},
        "pathParameters": path_params or {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAuthLoginFlow:
    """End-to-end login, token issuance, and token validation."""

    def test_successful_login_returns_token(self, aws):
        """Req 1.1: Valid credentials → Session_Token returned."""
        auth_mod._cached_secret = None
        resp = lambda_handler(_login_event(TEST_USERNAME, TEST_PASSWORD), None)

        assert resp["statusCode"] == 200
        body = _parse_body(resp)
        assert "token" in body
        assert isinstance(body["token"], str)
        assert len(body["token"]) > 0

    def test_token_grants_access_to_protected_route(self, aws):
        """Req 1.1, 1.7: Token from login allows access to protected routes."""
        auth_mod._cached_secret = None
        login_resp = lambda_handler(_login_event(TEST_USERNAME, TEST_PASSWORD), None)
        token = _parse_body(login_resp)["token"]

        # Use the token to access a protected route
        resp = lambda_handler(
            _authenticated_event("GET /watches", token),
            None,
        )
        assert resp["statusCode"] == 200

    def test_invalid_password_returns_401(self, aws):
        """Req 1.2: Invalid credentials → auth error."""
        auth_mod._cached_secret = None
        resp = lambda_handler(_login_event(TEST_USERNAME, "WrongPassword!"), None)

        assert resp["statusCode"] == 401
        body = _parse_body(resp)
        assert body["error"]["code"] == "UNAUTHORIZED"

    def test_invalid_username_returns_401(self, aws):
        """Req 1.2: Wrong username → same generic error."""
        auth_mod._cached_secret = None
        resp = lambda_handler(_login_event("wronguser", TEST_PASSWORD), None)

        assert resp["statusCode"] == 401
        body = _parse_body(resp)
        assert body["error"]["code"] == "UNAUTHORIZED"

    def test_identical_error_for_wrong_user_and_wrong_pass(self, aws):
        """Req 1.2: Error messages are identical regardless of which field is wrong."""
        auth_mod._cached_secret = None
        resp_wrong_user = lambda_handler(_login_event("wronguser", TEST_PASSWORD), None)
        auth_mod._cached_secret = None
        resp_wrong_pass = lambda_handler(_login_event(TEST_USERNAME, "WrongPass!"), None)
        auth_mod._cached_secret = None
        resp_both_wrong = lambda_handler(_login_event("wronguser", "WrongPass!"), None)

        msg1 = _parse_body(resp_wrong_user)["error"]["message"]
        msg2 = _parse_body(resp_wrong_pass)["error"]["message"]
        msg3 = _parse_body(resp_both_wrong)["error"]["message"]

        assert msg1 == msg2 == msg3

    def test_missing_token_returns_401(self, aws):
        """Req 1.7: Request without token → 401."""
        resp = lambda_handler(
            {"routeKey": "POST /watches", "headers": {}, "pathParameters": {}, "body": '{"maker":"X","model":"Y"}'},
            None,
        )
        assert resp["statusCode"] == 401

    def test_invalid_token_returns_401(self, aws):
        """Req 1.7: Request with invalid token → 401."""
        resp = lambda_handler(
            _authenticated_event("POST /watches", "not.a.valid.token"),
            None,
        )
        assert resp["statusCode"] == 401


class TestAuthLockout:
    """End-to-end lockout flow."""

    def test_lockout_after_five_failures(self, aws):
        """Req 1.4: 5 consecutive failures → account locked."""
        bad_event = _login_event(TEST_USERNAME, "WrongPassword!")

        for _ in range(5):
            auth_mod._cached_secret = None
            resp = lambda_handler(bad_event, None)
            assert resp["statusCode"] == 401

        # 6th attempt should be locked
        auth_mod._cached_secret = None
        resp = lambda_handler(bad_event, None)
        assert resp["statusCode"] == 403
        body = _parse_body(resp)
        assert body["error"]["code"] == "ACCOUNT_LOCKED"

    def test_lockout_rejects_valid_credentials(self, aws):
        """Req 1.3: While locked, even valid credentials are rejected."""
        bad_event = _login_event(TEST_USERNAME, "WrongPassword!")

        for _ in range(5):
            auth_mod._cached_secret = None
            lambda_handler(bad_event, None)

        # Valid credentials should still be rejected
        auth_mod._cached_secret = None
        resp = lambda_handler(_login_event(TEST_USERNAME, TEST_PASSWORD), None)
        assert resp["statusCode"] == 403

    def test_lockout_expires_after_duration(self, aws):
        """Req 1.5: After lockout duration, login is allowed again."""
        bad_event = _login_event(TEST_USERNAME, "WrongPassword!")

        for _ in range(5):
            auth_mod._cached_secret = None
            lambda_handler(bad_event, None)

        # Verify locked
        auth_mod._cached_secret = None
        resp = lambda_handler(bad_event, None)
        assert resp["statusCode"] == 403

        # Fast-forward: set lockoutUntil to the past
        table = aws["dynamodb_table"]
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        table.update_item(
            Key={"PK": "AUTH", "SK": "LOCKOUT"},
            UpdateExpression="SET lockoutUntil = :lu",
            ExpressionAttributeValues={":lu": past},
        )

        # Now login should succeed
        auth_mod._cached_secret = None
        resp = lambda_handler(_login_event(TEST_USERNAME, TEST_PASSWORD), None)
        assert resp["statusCode"] == 200

    def test_successful_login_resets_counter(self, aws):
        """Req 1.5: Successful login resets the failed attempt counter."""
        bad_event = _login_event(TEST_USERNAME, "WrongPassword!")

        # 4 failures (below threshold)
        for _ in range(4):
            auth_mod._cached_secret = None
            lambda_handler(bad_event, None)

        # Successful login resets counter
        auth_mod._cached_secret = None
        resp = lambda_handler(_login_event(TEST_USERNAME, TEST_PASSWORD), None)
        assert resp["statusCode"] == 200

        # Another 4 failures should NOT trigger lockout
        for _ in range(4):
            auth_mod._cached_secret = None
            lambda_handler(bad_event, None)

        # 5th after reset — still not locked
        auth_mod._cached_secret = None
        resp = lambda_handler(bad_event, None)
        assert resp["statusCode"] == 401  # not 403
