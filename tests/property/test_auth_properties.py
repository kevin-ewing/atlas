"""Property-based tests for the Auth Service.

Uses Hypothesis to verify authentication invariants across many inputs.
"""

import json
import os

import bcrypt
import boto3
import pytest
from hypothesis import given, settings, HealthCheck
from moto import mock_aws

from tests.conftest import (
    AWS_REGION,
    TEST_PASSWORD,
    TEST_SECRET_NAME,
    TEST_TABLE_NAME,
    TEST_USERNAME,
    TEST_JWT_SIGNING_KEY,
    invalid_credentials,
)


@pytest.fixture(autouse=True)
def _clear_secret_cache():
    """Clear the module-level secret cache before each test."""
    import src.services.auth_service as mod
    mod._cached_secret = None
    yield
    mod._cached_secret = None


def _setup_aws_resources():
    """Create DynamoDB table and Secrets Manager secret for testing."""
    # DynamoDB
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
    ddb.create_table(
        TableName=TEST_TABLE_NAME,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Secrets Manager
    sm = boto3.client("secretsmanager", region_name=AWS_REGION)
    password_hash = bcrypt.hashpw(
        TEST_PASSWORD.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")
    sm.create_secret(
        Name=TEST_SECRET_NAME,
        SecretString=json.dumps({
            "username": TEST_USERNAME,
            "passwordHash": password_hash,
            "jwtSigningKey": TEST_JWT_SIGNING_KEY,
        }),
    )


# Feature: watch-flip-tracker, Property 1: Invalid credentials return identical error messages
class TestInvalidCredentialsIdenticalErrors:
    """Property 1: Invalid credentials return identical error messages.

    **Validates: Requirement 1.2**

    For any invalid credential pair — whether the username is wrong, the
    password is wrong, or both are wrong — the Auth_Service should return
    the same error response with no information distinguishing which field
    was incorrect.
    """

    @given(creds=invalid_credentials())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_invalid_credentials_return_identical_error_messages(self, creds):
        """All invalid credential scenarios must produce the same error response."""
        import src.services.auth_service as mod

        with mock_aws():
            _setup_aws_resources()
            mod._cached_secret = None

            from src.services.auth_service import login

            response = login(creds)

            # Must return 401
            assert response["statusCode"] == 401, (
                f"Expected 401 for invalid creds, got {response['statusCode']}"
            )

            body = json.loads(response["body"])

            # Must have the standard error structure
            assert "error" in body
            assert body["error"]["code"] == "UNAUTHORIZED"
            assert body["error"]["message"] == "Invalid username or password"

            # The error details must be empty — no extra info leaking
            assert body["error"]["details"] == {}

            # Reset failed attempts to avoid lockout across hypothesis examples
            mod._reset_failed_attempts()


# Feature: watch-flip-tracker, Property 2: Lockout state machine correctness
class TestLockoutStateMachine:
    """Property 2: Lockout state machine correctness.

    **Validates: Requirements 1.3, 1.4, 1.5**

    For any sequence of consecutive failed login attempts, the Auth_Service
    should lock the account when the count reaches the Lockout_Threshold (5),
    reject all login attempts while locked, and allow attempts again after
    the Lockout_Duration (15 minutes) expires with the counter reset to zero.
    """

    def test_lockout_triggers_at_threshold(self, aws):
        """Account locks after exactly 5 consecutive failed attempts."""
        from src.services.auth_service import login
        import src.services.auth_service as mod

        bad_creds = {"username": TEST_USERNAME, "password": "WrongPass!"}

        # First 5 attempts should return 401 (not locked)
        for i in range(5):
            mod._cached_secret = None
            resp = login(bad_creds)
            assert resp["statusCode"] == 401, f"Attempt {i+1} should return 401"

        # 6th attempt should be locked (403)
        mod._cached_secret = None
        resp = login(bad_creds)
        assert resp["statusCode"] == 403
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "ACCOUNT_LOCKED"

    def test_lockout_rejects_valid_credentials(self, aws):
        """Valid credentials are rejected while account is locked."""
        from src.services.auth_service import login
        import src.services.auth_service as mod

        bad_creds = {"username": TEST_USERNAME, "password": "WrongPass!"}
        good_creds = {"username": TEST_USERNAME, "password": TEST_PASSWORD}

        # Trigger lockout
        for _ in range(5):
            mod._cached_secret = None
            login(bad_creds)

        # Valid credentials should still be rejected
        mod._cached_secret = None
        resp = login(good_creds)
        assert resp["statusCode"] == 403
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "ACCOUNT_LOCKED"

    def test_lockout_expires_and_resets_counter(self, aws):
        """After lockout expires, the counter resets and login attempts are allowed."""
        from src.services.auth_service import login, _reset_failed_attempts, _get_table
        from datetime import datetime, timezone, timedelta
        import src.services.auth_service as mod

        bad_creds = {"username": TEST_USERNAME, "password": "WrongPass!"}

        # Trigger lockout
        for _ in range(5):
            mod._cached_secret = None
            login(bad_creds)

        # Verify locked
        mod._cached_secret = None
        resp = login(bad_creds)
        assert resp["statusCode"] == 403

        # Simulate lockout expiry by setting lockoutUntil to the past
        table = _get_table()
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        table.update_item(
            Key={"PK": "AUTH", "SK": "LOCKOUT"},
            UpdateExpression="SET lockoutUntil = :lu",
            ExpressionAttributeValues={":lu": past_time},
        )

        # Now login should be allowed again (counter was reset)
        mod._cached_secret = None
        resp = login({"username": TEST_USERNAME, "password": TEST_PASSWORD})
        assert resp["statusCode"] == 200, "Login should succeed after lockout expires"

    def test_successful_login_resets_counter_before_threshold(self, aws):
        """A successful login before reaching threshold resets the counter."""
        from src.services.auth_service import login
        import src.services.auth_service as mod

        bad_creds = {"username": TEST_USERNAME, "password": "WrongPass!"}
        good_creds = {"username": TEST_USERNAME, "password": TEST_PASSWORD}

        # 4 failed attempts (below threshold)
        for _ in range(4):
            mod._cached_secret = None
            login(bad_creds)

        # Successful login resets counter
        mod._cached_secret = None
        resp = login(good_creds)
        assert resp["statusCode"] == 200

        # Another 4 failed attempts should NOT trigger lockout
        for _ in range(4):
            mod._cached_secret = None
            login(bad_creds)

        # 5th attempt after reset — still not locked
        mod._cached_secret = None
        resp = login(bad_creds)
        assert resp["statusCode"] == 401, "Should not be locked after counter reset"

    def test_lockout_message_includes_remaining_duration(self, aws):
        """Lockout response includes remaining duration information."""
        from src.services.auth_service import login
        import src.services.auth_service as mod

        bad_creds = {"username": TEST_USERNAME, "password": "WrongPass!"}

        # Trigger lockout
        for _ in range(5):
            mod._cached_secret = None
            login(bad_creds)

        # Check lockout response
        mod._cached_secret = None
        resp = login(bad_creds)
        assert resp["statusCode"] == 403
        body = json.loads(resp["body"])
        assert "minute" in body["error"]["message"].lower()
