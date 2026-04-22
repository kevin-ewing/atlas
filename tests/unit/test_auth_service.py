"""Unit tests for the Auth Service."""

import json
import time

import bcrypt
import jwt
import pytest
from moto import mock_aws

from tests.conftest import (
    TEST_JWT_SIGNING_KEY,
    TEST_PASSWORD,
    TEST_SECRET_NAME,
    TEST_TABLE_NAME,
    TEST_USERNAME,
)


@pytest.fixture(autouse=True)
def _clear_secret_cache():
    """Clear the module-level secret cache before each test."""
    import src.services.auth_service as mod
    mod._cached_secret = None
    yield
    mod._cached_secret = None


class TestLogin:
    """Tests for auth_service.login()."""

    def test_successful_login_returns_token(self, aws):
        """Valid credentials should return 200 with a JWT token."""
        from src.services.auth_service import login

        body = {"username": TEST_USERNAME, "password": TEST_PASSWORD}
        response = login(body)

        assert response["statusCode"] == 200
        resp_body = json.loads(response["body"])
        assert "token" in resp_body

        # Verify the token is a valid JWT
        decoded = jwt.decode(
            resp_body["token"], TEST_JWT_SIGNING_KEY, algorithms=["HS256"]
        )
        assert decoded["sub"] == TEST_USERNAME
        assert "exp" in decoded
        assert "iat" in decoded

    def test_successful_login_token_has_24h_expiry(self, aws):
        """Issued JWT should expire in 24 hours."""
        from src.services.auth_service import login

        body = {"username": TEST_USERNAME, "password": TEST_PASSWORD}
        response = login(body)
        resp_body = json.loads(response["body"])

        decoded = jwt.decode(
            resp_body["token"], TEST_JWT_SIGNING_KEY, algorithms=["HS256"]
        )
        assert decoded["exp"] - decoded["iat"] == 24 * 60 * 60

    def test_wrong_password_returns_401(self, aws):
        """Wrong password should return 401 with generic message."""
        from src.services.auth_service import login

        body = {"username": TEST_USERNAME, "password": "WrongPassword!"}
        response = login(body)

        assert response["statusCode"] == 401
        resp_body = json.loads(response["body"])
        assert resp_body["error"]["message"] == "Invalid username or password"

    def test_wrong_username_returns_401(self, aws):
        """Wrong username should return 401 with generic message."""
        from src.services.auth_service import login

        body = {"username": "wronguser", "password": TEST_PASSWORD}
        response = login(body)

        assert response["statusCode"] == 401
        resp_body = json.loads(response["body"])
        assert resp_body["error"]["message"] == "Invalid username or password"

    def test_both_wrong_returns_401(self, aws):
        """Both wrong username and password should return 401 with generic message."""
        from src.services.auth_service import login

        body = {"username": "wronguser", "password": "WrongPassword!"}
        response = login(body)

        assert response["statusCode"] == 401
        resp_body = json.loads(response["body"])
        assert resp_body["error"]["message"] == "Invalid username or password"

    def test_all_invalid_credential_errors_are_identical(self, aws):
        """All invalid credential scenarios must return the same error body."""
        from src.services.auth_service import login

        wrong_user = login({"username": "wrong", "password": TEST_PASSWORD})
        # Clear cache between calls to avoid lockout interference
        import src.services.auth_service as mod
        mod._cached_secret = None

        wrong_pass = login({"username": TEST_USERNAME, "password": "wrong"})
        mod._cached_secret = None

        both_wrong = login({"username": "wrong", "password": "wrong"})

        # All three should have the same status code and error structure
        assert wrong_user["statusCode"] == wrong_pass["statusCode"] == both_wrong["statusCode"] == 401

        body1 = json.loads(wrong_user["body"])
        body2 = json.loads(wrong_pass["body"])
        body3 = json.loads(both_wrong["body"])

        assert body1["error"]["message"] == body2["error"]["message"] == body3["error"]["message"]
        assert body1["error"]["code"] == body2["error"]["code"] == body3["error"]["code"]

    def test_empty_username_returns_401(self, aws):
        """Empty username should return 401."""
        from src.services.auth_service import login

        response = login({"username": "", "password": TEST_PASSWORD})
        assert response["statusCode"] == 401

    def test_empty_password_returns_401(self, aws):
        """Empty password should return 401."""
        from src.services.auth_service import login

        response = login({"username": TEST_USERNAME, "password": ""})
        assert response["statusCode"] == 401

    def test_missing_fields_returns_401(self, aws):
        """Missing username/password keys should return 401."""
        from src.services.auth_service import login

        response = login({})
        assert response["statusCode"] == 401


class TestLockout:
    """Tests for account lockout behavior."""

    def test_lockout_after_5_failed_attempts(self, aws):
        """Account should be locked after 5 consecutive failed attempts."""
        from src.services.auth_service import login

        bad_body = {"username": TEST_USERNAME, "password": "wrong"}

        for _ in range(5):
            resp = login(bad_body)
            assert resp["statusCode"] == 401

        # 6th attempt should be locked out
        resp = login(bad_body)
        assert resp["statusCode"] == 403
        resp_body = json.loads(resp["body"])
        assert resp_body["error"]["code"] == "ACCOUNT_LOCKED"

    def test_lockout_rejects_valid_credentials(self, aws):
        """Even valid credentials should be rejected during lockout."""
        from src.services.auth_service import login

        bad_body = {"username": TEST_USERNAME, "password": "wrong"}
        for _ in range(5):
            login(bad_body)

        # Valid credentials during lockout
        good_body = {"username": TEST_USERNAME, "password": TEST_PASSWORD}
        resp = login(good_body)
        assert resp["statusCode"] == 403

    def test_successful_login_resets_counter(self, aws):
        """A successful login should reset the failed attempt counter."""
        from src.services.auth_service import login

        bad_body = {"username": TEST_USERNAME, "password": "wrong"}
        good_body = {"username": TEST_USERNAME, "password": TEST_PASSWORD}

        # 4 failed attempts (below threshold)
        for _ in range(4):
            login(bad_body)

        # Successful login resets counter
        resp = login(good_body)
        assert resp["statusCode"] == 200

        # 4 more failed attempts should NOT trigger lockout
        for _ in range(4):
            login(bad_body)

        # Should still be able to try (not locked)
        resp = login(bad_body)
        assert resp["statusCode"] == 401  # invalid, but not locked


class TestValidateToken:
    """Tests for auth_service.validate_token()."""

    def test_valid_token_returns_claims(self, aws):
        """A valid JWT should return decoded claims."""
        from src.services.auth_service import login, validate_token

        body = {"username": TEST_USERNAME, "password": TEST_PASSWORD}
        resp = login(body)
        token = json.loads(resp["body"])["token"]

        claims = validate_token(token)
        assert claims["sub"] == TEST_USERNAME

    def test_expired_token_raises(self, aws):
        """An expired JWT should raise an exception."""
        from src.services.auth_service import validate_token

        # Create an already-expired token
        payload = {
            "sub": TEST_USERNAME,
            "iat": int(time.time()) - 3600,
            "exp": int(time.time()) - 1,
        }
        token = jwt.encode(payload, TEST_JWT_SIGNING_KEY, algorithm="HS256")

        with pytest.raises(jwt.ExpiredSignatureError):
            validate_token(token)

    def test_invalid_signature_raises(self, aws):
        """A JWT signed with the wrong key should raise an exception."""
        from src.services.auth_service import validate_token

        payload = {
            "sub": TEST_USERNAME,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, "wrong-key", algorithm="HS256")

        with pytest.raises(jwt.InvalidSignatureError):
            validate_token(token)

    def test_malformed_token_raises(self, aws):
        """A malformed token string should raise an exception."""
        from src.services.auth_service import validate_token

        with pytest.raises(Exception):
            validate_token("not.a.valid.jwt")


class TestSecretsManagerFailure:
    """Tests for Secrets Manager unavailability."""

    def test_login_returns_503_when_secrets_unavailable(self, aws):
        """Login should return 503 if Secrets Manager secret doesn't exist."""
        import src.services.auth_service as mod
        from src.services.auth_service import login

        # Clear cache and point to a non-existent secret
        mod._cached_secret = None
        original = os.environ.get("SECRET_NAME")
        os.environ["SECRET_NAME"] = "nonexistent-secret"

        try:
            resp = login({"username": "user", "password": "pass"})
            assert resp["statusCode"] == 503
            resp_body = json.loads(resp["body"])
            assert resp_body["error"]["code"] == "SERVICE_UNAVAILABLE"
        finally:
            if original:
                os.environ["SECRET_NAME"] = original


class TestSecretCaching:
    """Tests for secret caching behavior."""

    def test_secret_is_cached_after_first_call(self, aws):
        """The secret should be cached after the first retrieval."""
        import src.services.auth_service as mod

        assert mod._cached_secret is None

        body = {"username": TEST_USERNAME, "password": TEST_PASSWORD}
        mod.login(body)

        assert mod._cached_secret is not None
        assert mod._cached_secret["username"] == TEST_USERNAME


# Need os for the secrets manager failure test
import os
