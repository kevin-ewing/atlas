"""Property-based tests for Image Service.

Uses Hypothesis to verify correctness properties for image content type
validation across a wide range of inputs.
"""

import json
import uuid

from hypothesis import given, settings, HealthCheck

from tests.conftest import content_type, VALID_CONTENT_TYPES

from src.services import image_service


# Feature: watch-flip-tracker, Property 14: Image content type validation
# **Validates: Requirements 8.2, 8.3**
@given(ct=content_type())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_image_content_type_validation(ct, aws):
    """For any content type string, the Image_Service validation should accept
    the upload request if and only if the content type is one of image/jpeg,
    image/png, or image/webp, and reject all other content types with a
    validation error specifying the accepted formats.
    """
    # Create a watch first so we can test the image upload URL endpoint
    table = aws["dynamodb_table"]
    watch_id = str(uuid.uuid4())
    table.put_item(Item={
        "PK": f"WATCH#{watch_id}",
        "SK": "METADATA",
        "GSI1PK": "WATCHES",
        "GSI1SK": f"2024-01-01#{watch_id}",
        "entityType": "WATCH",
        "watchId": watch_id,
        "maker": "TestMaker",
        "model": "TestModel",
        "status": "in_collection",
    })

    data = {"filename": "test.img", "contentType": ct}
    response = image_service.get_upload_url(watch_id, data)
    body = json.loads(response["body"])

    if ct in VALID_CONTENT_TYPES:
        # Valid content type → should succeed (200)
        assert response["statusCode"] == 200, (
            f"Expected 200 for valid content type '{ct}', got {response['statusCode']}"
        )
        assert "uploadUrl" in body
        assert "imageId" in body
        assert "s3Key" in body
    else:
        # Invalid content type → should fail with validation error (400)
        assert response["statusCode"] == 400, (
            f"Expected 400 for invalid content type '{ct}', got {response['statusCode']}"
        )
        assert body["error"]["code"] == "VALIDATION_ERROR"
        # Error message should mention accepted formats
        msg = body["error"]["message"]
        assert "image/jpeg" in msg or "jpeg" in msg.lower(), (
            f"Error message should mention accepted formats, got: {msg}"
        )
