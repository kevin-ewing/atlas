"""Authentication service for Atlas Watch Flip Tracker.

Handles login, JWT issuance/validation, and account lockout enforcement.
Credentials are retrieved exclusively from AWS Secrets Manager and cached
for the lifetime of the Lambda execution environment.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import bcrypt
import boto3
import jwt
from botocore.exceptions import ClientError

from src.utils import error_response, json_response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_JWT_EXPIRATION_SECONDS = 24 * 60 * 60  # 24 hours
_LOCKOUT_THRESHOLD = 5  # consecutive failed attempts before lockout
_LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 minutes
_GENERIC_INVALID_MSG = "Invalid username or password"

# ---------------------------------------------------------------------------
# Module-level secret cache (persists across invocations in the same
# Lambda execution environment)
# ---------------------------------------------------------------------------

_cached_secret: dict | None = None


def _get_secret() -> dict:
    """Retrieve and cache the authentication secret from Secrets Manager.

    Returns:
        A dict with keys: username, passwordHash, jwtSigningKey.

    Raises:
        RuntimeError: If Secrets Manager is unreachable or the secret
            cannot be parsed.
    """
    global _cached_secret
    if _cached_secret is not None:
        return _cached_secret

    secret_name = os.environ.get("SECRET_NAME", "")
    try:
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_name)
        _cached_secret = json.loads(response["SecretString"])
        return _cached_secret
    except (ClientError, KeyError, json.JSONDecodeError) as exc:
        logger.error("Failed to retrieve secret from Secrets Manager: %s", exc)
        raise RuntimeError("Secrets Manager unavailable") from exc


# ---------------------------------------------------------------------------
# DynamoDB helpers for lockout state
# ---------------------------------------------------------------------------

def _get_table():
    """Return the DynamoDB Table resource for the Atlas table."""
    table_name = os.environ.get("TABLE_NAME", "")
    return boto3.resource("dynamodb").Table(table_name)


def _check_lockout() -> dict | None:
    """Check whether the account is currently locked out.

    Returns:
        None if the account is NOT locked out (login may proceed).
        An API Gateway error response dict if the account IS locked out.
    """
    table = _get_table()
    try:
        result = table.get_item(Key={"PK": "AUTH", "SK": "LOCKOUT"})
    except ClientError:
        # If we can't read lockout state, allow the attempt (fail open
        # for availability; the lockout is a rate-limit, not a security gate).
        return None

    item = result.get("Item")
    if not item:
        return None

    lockout_until = item.get("lockoutUntil")
    if not lockout_until:
        return None

    # Parse the ISO-8601 lockout expiry
    try:
        lockout_dt = datetime.fromisoformat(lockout_until)
    except (ValueError, TypeError):
        return None

    now = datetime.now(timezone.utc)
    if now < lockout_dt:
        remaining_seconds = int((lockout_dt - now).total_seconds())
        remaining_minutes = max(1, (remaining_seconds + 59) // 60)
        return error_response(
            403,
            "ACCOUNT_LOCKED",
            f"Account is locked. Try again in {remaining_minutes} minute(s).",
        )

    # Lockout has expired — reset state so the counter starts fresh.
    _reset_failed_attempts()
    return None


def _record_failed_attempt() -> None:
    """Increment the failed-attempt counter in DynamoDB.

    If the counter reaches ``_LOCKOUT_THRESHOLD``, set a lockout expiry.
    """
    table = _get_table()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        # Atomically increment failedAttempts
        result = table.update_item(
            Key={"PK": "AUTH", "SK": "LOCKOUT"},
            UpdateExpression=(
                "SET failedAttempts = if_not_exists(failedAttempts, :zero) + :one, "
                "lastFailedAt = :now, "
                "entityType = :et"
            ),
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":now": now_iso,
                ":et": "AUTH_STATE",
            },
            ReturnValues="ALL_NEW",
        )
        new_count = int(result["Attributes"].get("failedAttempts", 0))

        if new_count >= _LOCKOUT_THRESHOLD:
            lockout_until = datetime.now(timezone.utc).replace(
                microsecond=0,
            )
            lockout_until = datetime.fromtimestamp(
                lockout_until.timestamp() + _LOCKOUT_DURATION_SECONDS,
                tz=timezone.utc,
            )
            table.update_item(
                Key={"PK": "AUTH", "SK": "LOCKOUT"},
                UpdateExpression="SET lockoutUntil = :lu",
                ExpressionAttributeValues={":lu": lockout_until.isoformat()},
            )
    except ClientError as exc:
        logger.error("Failed to record failed login attempt: %s", exc)


def _reset_failed_attempts() -> None:
    """Reset the failed-attempt counter and clear any lockout."""
    table = _get_table()
    try:
        table.put_item(
            Item={
                "PK": "AUTH",
                "SK": "LOCKOUT",
                "entityType": "AUTH_STATE",
                "failedAttempts": 0,
            },
        )
    except ClientError as exc:
        logger.error("Failed to reset failed attempts: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def login(body: dict) -> dict:
    """Authenticate a user and issue a JWT on success.

    Args:
        body: A dict with ``username`` and ``password`` keys.

    Returns:
        An API Gateway response dict.  200 with a token on success,
        403 if locked out, 401 for invalid credentials, or 503 if
        Secrets Manager is unreachable.
    """
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()

    if not username or not password:
        return error_response(401, "UNAUTHORIZED", _GENERIC_INVALID_MSG)

    # Retrieve credentials from Secrets Manager
    try:
        secret = _get_secret()
    except RuntimeError:
        return error_response(
            503,
            "SERVICE_UNAVAILABLE",
            "Authentication service is temporarily unavailable",
        )

    # Check lockout BEFORE validating credentials
    lockout_resp = _check_lockout()
    if lockout_resp is not None:
        return lockout_resp

    # Validate credentials
    stored_username = secret.get("username", "")
    stored_hash = secret.get("passwordHash", "")

    username_valid = username == stored_username
    try:
        password_valid = bcrypt.checkpw(
            password.encode("utf-8"),
            stored_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        password_valid = False

    if not username_valid or not password_valid:
        _record_failed_attempt()
        return error_response(401, "UNAUTHORIZED", _GENERIC_INVALID_MSG)

    # Successful login — reset lockout counter and issue JWT
    _reset_failed_attempts()

    signing_key = secret.get("jwtSigningKey", "")
    now = time.time()
    payload = {
        "sub": stored_username,
        "iat": int(now),
        "exp": int(now) + _JWT_EXPIRATION_SECONDS,
    }
    token = jwt.encode(payload, signing_key, algorithm="HS256")

    return json_response(200, {"token": token})


def validate_token(token: str) -> dict:
    """Decode and verify a JWT.

    Args:
        token: The raw JWT string.

    Returns:
        The decoded claims dict on success.

    Raises:
        Exception: If the token is invalid, expired, or the signing key
            cannot be retrieved.
    """
    secret = _get_secret()
    signing_key = secret.get("jwtSigningKey", "")

    # PyJWT automatically checks expiration
    claims = jwt.decode(token, signing_key, algorithms=["HS256"])
    return claims
