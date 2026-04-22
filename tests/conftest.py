"""Shared test fixtures and Hypothesis strategies for Atlas test suite."""

import json
import os
import string

import bcrypt
import boto3
import pytest
from moto import mock_aws

from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Constants used across fixtures and strategies
# ---------------------------------------------------------------------------

TEST_TABLE_NAME = "atlas-table-test"
TEST_IMAGE_BUCKET = "atlas-images-test"
TEST_WEB_BUCKET = "atlas-web-test"
TEST_SECRET_NAME = "atlas-secret-test"
TEST_USERNAME = "testadmin"
TEST_PASSWORD = "TestPassword123!"
TEST_JWT_SIGNING_KEY = "test-jwt-signing-key-for-atlas"
AWS_REGION = "us-east-1"

VALID_MOVEMENT_TYPES = ["automatic", "manual", "quartz"]
VALID_CONDITIONS = ["new", "excellent", "good", "fair", "poor"]
VALID_STATUSES = ["in_collection", "for_sale", "sold"]
VALID_FEATURES = [
    "chronograph", "date", "GMT", "moon phase", "tourbillon",
    "minute repeater", "perpetual calendar", "diving bezel",
    "power reserve indicator", "alarm",
]
VALID_CONTENT_TYPES = ["image/jpeg", "image/png", "image/webp"]

FILTER_FIELDS = ["maker", "status", "condition", "movementType", "caseMaterial"]
SORT_FIELDS = ["pnl", "acquisitionDate", "maker", "yearOfProduction"]
SORT_DIRECTIONS = ["asc", "desc"]


# ---------------------------------------------------------------------------
# Environment variable setup
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _set_env_vars(monkeypatch):
    """Set environment variables expected by Lambda function code."""
    monkeypatch.setenv("TABLE_NAME", TEST_TABLE_NAME)
    monkeypatch.setenv("IMAGE_BUCKET_NAME", TEST_IMAGE_BUCKET)
    monkeypatch.setenv("SECRET_NAME", TEST_SECRET_NAME)
    monkeypatch.setenv("AWS_DEFAULT_REGION", AWS_REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


# ---------------------------------------------------------------------------
# AWS moto mocks
# ---------------------------------------------------------------------------

@pytest.fixture
def aws_credentials():
    """Mocked AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = AWS_REGION


@pytest.fixture
def dynamodb_resource(aws_credentials):
    """Provide a moto-mocked DynamoDB resource with the Atlas table created."""
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name=AWS_REGION)
        resource.create_table(
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
        yield resource


@pytest.fixture
def dynamodb_table(dynamodb_resource):
    """Return the Atlas DynamoDB Table object directly."""
    return dynamodb_resource.Table(TEST_TABLE_NAME)


@pytest.fixture
def s3_client(aws_credentials):
    """Provide a moto-mocked S3 client with image and web buckets created."""
    with mock_aws():
        client = boto3.client("s3", region_name=AWS_REGION)
        client.create_bucket(Bucket=TEST_IMAGE_BUCKET)
        client.create_bucket(Bucket=TEST_WEB_BUCKET)
        yield client


@pytest.fixture
def s3_resource(aws_credentials):
    """Provide a moto-mocked S3 resource with image and web buckets created."""
    with mock_aws():
        resource = boto3.resource("s3", region_name=AWS_REGION)
        resource.create_bucket(Bucket=TEST_IMAGE_BUCKET)
        resource.create_bucket(Bucket=TEST_WEB_BUCKET)
        yield resource


@pytest.fixture
def secrets_client(aws_credentials):
    """Provide a moto-mocked Secrets Manager client with test credentials."""
    with mock_aws():
        client = boto3.client("secretsmanager", region_name=AWS_REGION)
        password_hash = bcrypt.hashpw(
            TEST_PASSWORD.encode("utf-8"), bcrypt.gensalt(rounds=12)
        ).decode("utf-8")
        secret_value = json.dumps({
            "username": TEST_USERNAME,
            "passwordHash": password_hash,
            "jwtSigningKey": TEST_JWT_SIGNING_KEY,
        })
        client.create_secret(
            Name=TEST_SECRET_NAME,
            SecretString=secret_value,
        )
        yield client


# ---------------------------------------------------------------------------
# Combined fixture — all AWS services mocked together
# ---------------------------------------------------------------------------

@pytest.fixture
def aws(aws_credentials):
    """Provide all mocked AWS services under a single mock_aws context.

    Yields a dict with keys: dynamodb_resource, dynamodb_table, s3_client,
    s3_resource, secrets_client.
    """
    with mock_aws():
        # DynamoDB
        ddb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
        ddb_resource.create_table(
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
        table = ddb_resource.Table(TEST_TABLE_NAME)

        # S3
        s3_c = boto3.client("s3", region_name=AWS_REGION)
        s3_c.create_bucket(Bucket=TEST_IMAGE_BUCKET)
        s3_c.create_bucket(Bucket=TEST_WEB_BUCKET)
        s3_r = boto3.resource("s3", region_name=AWS_REGION)

        # Secrets Manager
        sm_client = boto3.client("secretsmanager", region_name=AWS_REGION)
        password_hash = bcrypt.hashpw(
            TEST_PASSWORD.encode("utf-8"), bcrypt.gensalt(rounds=12)
        ).decode("utf-8")
        sm_client.create_secret(
            Name=TEST_SECRET_NAME,
            SecretString=json.dumps({
                "username": TEST_USERNAME,
                "passwordHash": password_hash,
                "jwtSigningKey": TEST_JWT_SIGNING_KEY,
            }),
        )

        yield {
            "dynamodb_resource": ddb_resource,
            "dynamodb_table": table,
            "s3_client": s3_c,
            "s3_resource": s3_r,
            "secrets_client": sm_client,
        }


# ---------------------------------------------------------------------------
# Hypothesis custom strategies
# ---------------------------------------------------------------------------

def _non_empty_text(min_size=1, max_size=100):
    """Strategy for non-empty printable text strings."""
    return st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=min_size,
        max_size=max_size,
    ).filter(lambda s: s.strip())


def _iso_date():
    """Strategy for ISO 8601 date strings (YYYY-MM-DD)."""
    return st.dates().map(lambda d: d.isoformat())


@st.composite
def watch_attributes(draw):
    """Generate a valid watch attributes dict.

    Always includes the required fields (maker, model) and randomly includes
    optional fields matching the Watch Record schema.
    """
    attrs = {
        "maker": draw(_non_empty_text(min_size=1, max_size=50)),
        "model": draw(_non_empty_text(min_size=1, max_size=50)),
    }

    # Optional fields — each included with ~50 % probability
    if draw(st.booleans()):
        attrs["referenceNumber"] = draw(_non_empty_text(max_size=30))
    if draw(st.booleans()):
        attrs["yearOfProduction"] = draw(st.integers(min_value=1800, max_value=2100))
    if draw(st.booleans()):
        attrs["caseMaterial"] = draw(_non_empty_text(max_size=30))
    if draw(st.booleans()):
        attrs["caseDiameterMm"] = draw(st.integers(min_value=20, max_value=60))
    if draw(st.booleans()):
        attrs["movementType"] = draw(st.sampled_from(VALID_MOVEMENT_TYPES))
    if draw(st.booleans()):
        attrs["dialColor"] = draw(_non_empty_text(max_size=20))
    if draw(st.booleans()):
        attrs["bandMaterial"] = draw(_non_empty_text(max_size=30))
    if draw(st.booleans()):
        attrs["bandColor"] = draw(_non_empty_text(max_size=20))
    if draw(st.booleans()):
        attrs["condition"] = draw(st.sampled_from(VALID_CONDITIONS))
    if draw(st.booleans()):
        attrs["boxIncluded"] = draw(st.booleans())
    if draw(st.booleans()):
        attrs["papersIncluded"] = draw(st.booleans())
    if draw(st.booleans()):
        features = draw(
            st.lists(st.sampled_from(VALID_FEATURES), min_size=0, max_size=5, unique=True)
        )
        attrs["features"] = features
    if draw(st.booleans()):
        attrs["serialNumber"] = draw(_non_empty_text(max_size=30))
    if draw(st.booleans()):
        attrs["acquisitionDate"] = draw(_iso_date())
    if draw(st.booleans()):
        attrs["acquisitionSource"] = draw(_non_empty_text(max_size=50))
    if draw(st.booleans()):
        attrs["status"] = draw(st.sampled_from(VALID_STATUSES))
    if draw(st.booleans()):
        attrs["notes"] = draw(_non_empty_text(max_size=200))

    return attrs


@st.composite
def expense_data(draw):
    """Generate a valid expense data dict.

    Always includes required fields (category, amountCents) and randomly
    includes optional fields.
    """
    data = {
        "category": draw(_non_empty_text(min_size=1, max_size=50)),
        "amountCents": draw(st.integers(min_value=1, max_value=100_000_00)),
    }

    if draw(st.booleans()):
        data["expenseDate"] = draw(_iso_date())
    if draw(st.booleans()):
        data["vendor"] = draw(_non_empty_text(max_size=50))
    if draw(st.booleans()):
        data["description"] = draw(_non_empty_text(max_size=200))

    return data


@st.composite
def sale_data(draw):
    """Generate a valid sale data dict.

    Always includes required fields (salePriceCents, saleDate) and randomly
    includes optional fields.
    """
    data = {
        "salePriceCents": draw(st.integers(min_value=1, max_value=1_000_000_00)),
        "saleDate": draw(_iso_date()),
    }

    if draw(st.booleans()):
        data["buyerOrPlatform"] = draw(_non_empty_text(max_size=50))
    if draw(st.booleans()):
        data["notes"] = draw(_non_empty_text(max_size=200))

    return data


@st.composite
def filter_criteria(draw):
    """Generate a random combination of filter criteria.

    Produces a dict with a random subset of the supported filter fields,
    each populated with a valid value for that field.
    """
    criteria = {}

    if draw(st.booleans()):
        criteria["maker"] = draw(_non_empty_text(min_size=1, max_size=30))
    if draw(st.booleans()):
        criteria["status"] = draw(st.sampled_from(VALID_STATUSES))
    if draw(st.booleans()):
        criteria["condition"] = draw(st.sampled_from(VALID_CONDITIONS))
    if draw(st.booleans()):
        criteria["movementType"] = draw(st.sampled_from(VALID_MOVEMENT_TYPES))
    if draw(st.booleans()):
        criteria["caseMaterial"] = draw(_non_empty_text(min_size=1, max_size=30))
    if draw(st.booleans()):
        year_min = draw(st.integers(min_value=1900, max_value=2050))
        year_max = draw(st.integers(min_value=year_min, max_value=2100))
        criteria["yearMin"] = year_min
        criteria["yearMax"] = year_max
    if draw(st.booleans()):
        criteria["features"] = draw(
            st.lists(st.sampled_from(VALID_FEATURES), min_size=1, max_size=3, unique=True)
        )

    return criteria


@st.composite
def sort_params(draw):
    """Generate a random sort field and direction."""
    return {
        "field": draw(st.sampled_from(SORT_FIELDS)),
        "direction": draw(st.sampled_from(SORT_DIRECTIONS)),
    }


@st.composite
def content_type(draw):
    """Generate a random MIME content-type string.

    Produces both valid image types (image/jpeg, image/png, image/webp) and
    random invalid types to exercise validation logic.
    """
    if draw(st.booleans()):
        # Valid content type
        return draw(st.sampled_from(VALID_CONTENT_TYPES))
    else:
        # Random invalid content type
        main_types = ["application", "text", "audio", "video", "image", "font"]
        main = draw(st.sampled_from(main_types))
        sub = draw(st.text(
            alphabet=string.ascii_lowercase + string.digits + "-",
            min_size=1,
            max_size=20,
        ))
        result = f"{main}/{sub}"
        # Ensure it's actually invalid
        if result in VALID_CONTENT_TYPES:
            return "application/octet-stream"
        return result


@st.composite
def invalid_credentials(draw):
    """Generate credential pairs that are always invalid.

    Produces one of three scenarios:
    - Wrong username, correct password
    - Correct username, wrong password
    - Both wrong
    """
    scenario = draw(st.sampled_from(["wrong_username", "wrong_password", "both_wrong"]))

    wrong_user = draw(
        _non_empty_text(min_size=1, max_size=30).filter(lambda u: u != TEST_USERNAME)
    )
    wrong_pass = draw(
        _non_empty_text(min_size=1, max_size=30).filter(lambda p: p != TEST_PASSWORD)
    )

    if scenario == "wrong_username":
        return {"username": wrong_user, "password": TEST_PASSWORD}
    elif scenario == "wrong_password":
        return {"username": TEST_USERNAME, "password": wrong_pass}
    else:
        return {"username": wrong_user, "password": wrong_pass}
