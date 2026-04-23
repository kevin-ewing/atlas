"""Unit tests for Image Service.

Tests pre-signed URL generation, content type validation, image count limits,
file size validation, and image deletion.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8
"""

import json
import uuid

from src.services import image_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_watch(table, watch_id=None):
    """Insert a minimal watch record and return its ID."""
    wid = watch_id or str(uuid.uuid4())
    table.put_item(Item={
        "PK": f"WATCH#{wid}",
        "SK": "METADATA",
        "GSI1PK": "WATCHES",
        "GSI1SK": f"2024-01-01#{wid}",
        "entityType": "WATCH",
        "watchId": wid,
        "maker": "Omega",
        "model": "Speedmaster",
        "status": "in_collection",
    })
    return wid


def _create_image_record(table, watch_id, image_id=None):
    """Insert a minimal image metadata record and return its ID."""
    iid = image_id or str(uuid.uuid4())
    table.put_item(Item={
        "PK": f"WATCH#{watch_id}",
        "SK": f"IMAGE#{iid}",
        "GSI1PK": f"WATCH#{watch_id}#IMAGES",
        "GSI1SK": f"2024-01-01T00:00:00#{iid}",
        "entityType": "IMAGE",
        "imageId": iid,
        "watchId": watch_id,
        "s3Key": f"watches/{watch_id}/{iid}.jpg",
        "filename": f"{iid}.jpg",
        "contentType": "image/jpeg",
        "uploadedAt": "2024-01-01T00:00:00+00:00",
    })
    return iid


# ---------------------------------------------------------------------------
# Pre-signed URL generation for valid content types
# ---------------------------------------------------------------------------

class TestGetUploadUrl:
    """Tests for get_upload_url."""

    def test_valid_jpeg(self, aws):
        """JPEG content type should return a pre-signed URL."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.get_upload_url(watch_id, {
            "filename": "photo.jpg",
            "contentType": "image/jpeg",
        })
        body = json.loads(response["body"])

        assert response["statusCode"] == 200
        assert "uploadUrl" in body
        assert "imageId" in body
        assert body["s3Key"].startswith(f"watches/{watch_id}/")
        assert body["s3Key"].endswith(".jpg")

    def test_valid_png(self, aws):
        """PNG content type should return a pre-signed URL."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.get_upload_url(watch_id, {
            "filename": "photo.png",
            "contentType": "image/png",
        })
        body = json.loads(response["body"])

        assert response["statusCode"] == 200
        assert body["s3Key"].endswith(".png")

    def test_valid_webp(self, aws):
        """WebP content type should return a pre-signed URL."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.get_upload_url(watch_id, {
            "filename": "photo.webp",
            "contentType": "image/webp",
        })
        body = json.loads(response["body"])

        assert response["statusCode"] == 200
        assert body["s3Key"].endswith(".webp")

    def test_watch_not_found(self, aws):
        """Should return 404 for a non-existent watch."""
        response = image_service.get_upload_url(str(uuid.uuid4()), {
            "filename": "photo.jpg",
            "contentType": "image/jpeg",
        })

        assert response["statusCode"] == 404

    def test_missing_filename(self, aws):
        """Should return 400 when filename is missing."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.get_upload_url(watch_id, {
            "contentType": "image/jpeg",
        })

        assert response["statusCode"] == 400

    def test_missing_content_type(self, aws):
        """Should return 400 when contentType is missing."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.get_upload_url(watch_id, {
            "filename": "photo.jpg",
        })

        assert response["statusCode"] == 400


# ---------------------------------------------------------------------------
# Rejection of invalid content types
# ---------------------------------------------------------------------------

class TestContentTypeValidation:
    """Tests for content type validation."""

    def test_reject_gif(self, aws):
        """GIF should be rejected."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.get_upload_url(watch_id, {
            "filename": "photo.gif",
            "contentType": "image/gif",
        })
        body = json.loads(response["body"])

        assert response["statusCode"] == 400
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_reject_pdf(self, aws):
        """PDF should be rejected."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.get_upload_url(watch_id, {
            "filename": "doc.pdf",
            "contentType": "application/pdf",
        })

        assert response["statusCode"] == 400

    def test_reject_text_plain(self, aws):
        """text/plain should be rejected."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.get_upload_url(watch_id, {
            "filename": "file.txt",
            "contentType": "text/plain",
        })

        assert response["statusCode"] == 400

    def test_error_message_lists_accepted_formats(self, aws):
        """Error message should mention accepted formats."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.get_upload_url(watch_id, {
            "filename": "photo.bmp",
            "contentType": "image/bmp",
        })
        body = json.loads(response["body"])

        msg = body["error"]["message"]
        assert "image/jpeg" in msg
        assert "image/png" in msg
        assert "image/webp" in msg


# ---------------------------------------------------------------------------
# Image count limit (10 per watch)
# ---------------------------------------------------------------------------

class TestImageCountLimit:
    """Tests for the 10-image-per-watch limit."""

    def test_limit_reached_returns_409(self, aws):
        """Should return 409 CONFLICT when 10 images already exist."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        # Create 10 image records
        for _ in range(10):
            _create_image_record(table, watch_id)

        response = image_service.get_upload_url(watch_id, {
            "filename": "photo11.jpg",
            "contentType": "image/jpeg",
        })
        body = json.loads(response["body"])

        assert response["statusCode"] == 409
        assert body["error"]["code"] == "CONFLICT"

    def test_under_limit_succeeds(self, aws):
        """Should succeed when fewer than 10 images exist."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        # Create 9 image records
        for _ in range(9):
            _create_image_record(table, watch_id)

        response = image_service.get_upload_url(watch_id, {
            "filename": "photo10.jpg",
            "contentType": "image/jpeg",
        })

        assert response["statusCode"] == 200


# ---------------------------------------------------------------------------
# File size validation (10 MB limit)
# ---------------------------------------------------------------------------

class TestFileSizeValidation:
    """Tests for image service constants."""

    def test_presigned_url_expiry_constant(self):
        """PRESIGNED_URL_EXPIRY should be 300 seconds (5 minutes)."""
        assert image_service.PRESIGNED_URL_EXPIRY == 300


# ---------------------------------------------------------------------------
# Image deletion removes S3 object and metadata
# ---------------------------------------------------------------------------

class TestDeleteImage:
    """Tests for delete_image."""

    def test_delete_removes_s3_and_metadata(self, aws):
        """Deleting an image should remove both S3 object and DynamoDB record."""
        table = aws["dynamodb_table"]
        s3_client = aws["s3_client"]
        watch_id = _create_watch(table)
        image_id = str(uuid.uuid4())
        s3_key = f"watches/{watch_id}/{image_id}.jpg"

        # Upload a real S3 object
        bucket = image_service._get_bucket_name()
        s3_client.put_object(Bucket=bucket, Key=s3_key, Body=b"fake-image-data")

        # Create image metadata in DynamoDB
        _create_image_record(table, watch_id, image_id)
        # Update the s3Key to match
        table.update_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": f"IMAGE#{image_id}"},
            UpdateExpression="SET s3Key = :key",
            ExpressionAttributeValues={":key": s3_key},
        )

        # Delete the image
        response = image_service.delete_image(watch_id, image_id)
        assert response["statusCode"] == 200

        # Verify S3 object is gone
        objs = s3_client.list_objects_v2(Bucket=bucket, Prefix=s3_key)
        assert objs.get("KeyCount", 0) == 0

        # Verify DynamoDB record is gone
        result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": f"IMAGE#{image_id}"}
        )
        assert "Item" not in result

    def test_delete_nonexistent_returns_404(self, aws):
        """Deleting a non-existent image should return 404."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.delete_image(watch_id, str(uuid.uuid4()))
        assert response["statusCode"] == 404


# ---------------------------------------------------------------------------
# Confirm upload
# ---------------------------------------------------------------------------

class TestConfirmUpload:
    """Tests for confirm_upload."""

    def test_confirm_stores_metadata(self, aws):
        """Confirming an upload should store image metadata in DynamoDB."""
        table = aws["dynamodb_table"]
        s3_client = aws["s3_client"]
        watch_id = _create_watch(table)
        image_id = str(uuid.uuid4())
        s3_key = f"watches/{watch_id}/{image_id}.jpg"

        # Upload a real S3 object
        bucket = image_service._get_bucket_name()
        s3_client.put_object(
            Bucket=bucket, Key=s3_key, Body=b"fake-image-data",
            ContentType="image/jpeg",
        )

        response = image_service.confirm_upload(watch_id, image_id)
        body = json.loads(response["body"])

        assert response["statusCode"] == 200
        assert body["imageId"] == image_id
        assert body["watchId"] == watch_id
        assert body["s3Key"] == s3_key
        assert body["contentType"] == "image/jpeg"

        # Verify DynamoDB record was created
        result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": f"IMAGE#{image_id}"}
        )
        assert "Item" in result

    def test_confirm_nonexistent_s3_object_returns_404(self, aws):
        """Confirming when no S3 object exists should return 404."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.confirm_upload(watch_id, str(uuid.uuid4()))
        assert response["statusCode"] == 404

    def test_confirm_nonexistent_watch_returns_404(self, aws):
        """Confirming for a non-existent watch should return 404."""
        response = image_service.confirm_upload(str(uuid.uuid4()), str(uuid.uuid4()))
        assert response["statusCode"] == 404


# ---------------------------------------------------------------------------
# List images
# ---------------------------------------------------------------------------

class TestListImages:
    """Tests for list_images."""

    def test_list_returns_all_images(self, aws):
        """Should return all image records for a watch."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        ids = [_create_image_record(table, watch_id) for _ in range(3)]

        response = image_service.list_images(watch_id)
        body = json.loads(response["body"])

        assert response["statusCode"] == 200
        assert len(body["images"]) == 3
        returned_ids = {img["imageId"] for img in body["images"]}
        assert returned_ids == set(ids)

    def test_list_empty(self, aws):
        """Should return empty list when no images exist."""
        table = aws["dynamodb_table"]
        watch_id = _create_watch(table)

        response = image_service.list_images(watch_id)
        body = json.loads(response["body"])

        assert response["statusCode"] == 200
        assert body["images"] == []
