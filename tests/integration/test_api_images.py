"""Integration tests for the image upload flow through the Lambda handler.

Tests exercise pre-signed URL generation, upload confirmation, listing,
and deletion — all via the Lambda handler with moto-mocked S3.

Requirements validated: 8.1–8.8
"""

import json

import src.services.auth_service as auth_mod
from src.handler import lambda_handler
from tests.conftest import TEST_USERNAME, TEST_PASSWORD, TEST_IMAGE_BUCKET


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(aws):
    """Login and return a valid JWT token."""
    auth_mod._cached_secret = None
    event = {
        "routeKey": "POST /auth/login",
        "headers": {},
        "pathParameters": {},
        "body": json.dumps({"username": TEST_USERNAME, "password": TEST_PASSWORD}),
    }
    resp = lambda_handler(event, None)
    return json.loads(resp["body"])["token"]


def _auth_event(route_key, token, path_params=None, body=None):
    """Build an authenticated API Gateway event."""
    event = {
        "routeKey": route_key,
        "headers": {"authorization": f"Bearer {token}"},
        "pathParameters": path_params or {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _body(resp):
    return json.loads(resp["body"])


def _create_watch(token):
    """Create a watch and return its ID."""
    resp = lambda_handler(
        _auth_event("POST /watches", token, body={"maker": "Rolex", "model": "Daytona"}),
        None,
    )
    return json.loads(resp["body"])["watchId"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestImageUploadFlow:
    """End-to-end image upload: get URL → upload to S3 → confirm → list → delete."""

    def test_get_upload_url(self, aws):
        """Req 8.8: Pre-signed URL is generated for valid content type."""
        token = _login(aws)
        watch_id = _create_watch(token)

        resp = lambda_handler(
            _auth_event(
                "POST /watches/{watchId}/images/upload-url",
                token,
                path_params={"watchId": watch_id},
                body={"filename": "front.jpg", "contentType": "image/jpeg"},
            ),
            None,
        )
        assert resp["statusCode"] == 200
        data = _body(resp)
        assert "uploadUrl" in data
        assert "imageId" in data
        assert "s3Key" in data
        assert data["s3Key"].startswith(f"watches/{watch_id}/")

    def test_full_upload_confirm_list_delete(self, aws):
        """Reqs 8.1, 8.5, 8.6, 8.8: Full image lifecycle."""
        token = _login(aws)
        watch_id = _create_watch(token)

        # 1. Get pre-signed URL
        url_resp = lambda_handler(
            _auth_event(
                "POST /watches/{watchId}/images/upload-url",
                token,
                path_params={"watchId": watch_id},
                body={"filename": "dial.png", "contentType": "image/png"},
            ),
            None,
        )
        url_data = _body(url_resp)
        image_id = url_data["imageId"]
        s3_key = url_data["s3Key"]

        # 2. Simulate upload by putting an object directly in moto S3
        s3_client = aws["s3_client"]
        s3_client.put_object(
            Bucket=TEST_IMAGE_BUCKET,
            Key=s3_key,
            Body=b"fake-image-data",
            ContentType="image/png",
        )

        # 3. Confirm upload
        confirm_resp = lambda_handler(
            _auth_event(
                "POST /watches/{watchId}/images/{imageId}/confirm",
                token,
                path_params={"watchId": watch_id, "imageId": image_id},
            ),
            None,
        )
        assert confirm_resp["statusCode"] == 200
        confirm_data = _body(confirm_resp)
        assert confirm_data["imageId"] == image_id
        assert confirm_data["contentType"] == "image/png"

        # 4. List images
        list_resp = lambda_handler(
            _auth_event(
                "GET /watches/{watchId}/images",
                token,
                path_params={"watchId": watch_id},
            ),
            None,
        )
        assert list_resp["statusCode"] == 200
        images = _body(list_resp)["images"]
        assert len(images) == 1
        assert images[0]["imageId"] == image_id

        # 5. Delete image
        del_resp = lambda_handler(
            _auth_event(
                "DELETE /watches/{watchId}/images/{imageId}",
                token,
                path_params={"watchId": watch_id, "imageId": image_id},
            ),
            None,
        )
        assert del_resp["statusCode"] == 200

        # 6. Verify image is gone
        list_resp2 = lambda_handler(
            _auth_event(
                "GET /watches/{watchId}/images",
                token,
                path_params={"watchId": watch_id},
            ),
            None,
        )
        assert _body(list_resp2)["images"] == []

    def test_invalid_content_type_rejected(self, aws):
        """Req 8.2, 8.3: Invalid content type → validation error."""
        token = _login(aws)
        watch_id = _create_watch(token)

        resp = lambda_handler(
            _auth_event(
                "POST /watches/{watchId}/images/upload-url",
                token,
                path_params={"watchId": watch_id},
                body={"filename": "doc.pdf", "contentType": "application/pdf"},
            ),
            None,
        )
        assert resp["statusCode"] == 400
        data = _body(resp)
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_image_limit_enforced(self, aws):
        """Req 8.7: Maximum 10 images per watch."""
        token = _login(aws)
        watch_id = _create_watch(token)
        s3_client = aws["s3_client"]

        # Upload 10 images
        for i in range(10):
            url_resp = lambda_handler(
                _auth_event(
                    "POST /watches/{watchId}/images/upload-url",
                    token,
                    path_params={"watchId": watch_id},
                    body={"filename": f"img{i}.jpg", "contentType": "image/jpeg"},
                ),
                None,
            )
            assert url_resp["statusCode"] == 200
            data = _body(url_resp)

            # Simulate upload
            s3_client.put_object(
                Bucket=TEST_IMAGE_BUCKET,
                Key=data["s3Key"],
                Body=b"fake",
                ContentType="image/jpeg",
            )

            # Confirm
            lambda_handler(
                _auth_event(
                    "POST /watches/{watchId}/images/{imageId}/confirm",
                    token,
                    path_params={"watchId": watch_id, "imageId": data["imageId"]},
                ),
                None,
            )

        # 11th should be rejected
        resp = lambda_handler(
            _auth_event(
                "POST /watches/{watchId}/images/upload-url",
                token,
                path_params={"watchId": watch_id},
                body={"filename": "extra.jpg", "contentType": "image/jpeg"},
            ),
            None,
        )
        assert resp["statusCode"] == 409

    def test_confirm_without_s3_object_returns_404(self, aws):
        """Req 8.8: Confirm upload fails if S3 object doesn't exist."""
        token = _login(aws)
        watch_id = _create_watch(token)

        resp = lambda_handler(
            _auth_event(
                "POST /watches/{watchId}/images/{imageId}/confirm",
                token,
                path_params={
                    "watchId": watch_id,
                    "imageId": "00000000-0000-0000-0000-000000000000",
                },
            ),
            None,
        )
        assert resp["statusCode"] == 404

    def test_webp_content_type_accepted(self, aws):
        """Req 8.2: WebP format is accepted."""
        token = _login(aws)
        watch_id = _create_watch(token)

        resp = lambda_handler(
            _auth_event(
                "POST /watches/{watchId}/images/upload-url",
                token,
                path_params={"watchId": watch_id},
                body={"filename": "photo.webp", "contentType": "image/webp"},
            ),
            None,
        )
        assert resp["statusCode"] == 200
        assert _body(resp)["s3Key"].endswith(".webp")
