"""Image Service for Atlas Watch Flip Tracker.

Handles image metadata management and pre-signed URL generation for
direct browser-to-S3 uploads. Supports JPEG, PNG, and WebP formats
with a maximum of 10 images per watch.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from src.utils import error_response, json_response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGES_PER_WATCH = 10
PRESIGNED_URL_EXPIRY = 300  # 5 minutes

# Map content type to file extension
CONTENT_TYPE_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_table():
    """Return the DynamoDB Table resource for the Atlas table."""
    table_name = os.environ.get("TABLE_NAME", "")
    return boto3.resource("dynamodb").Table(table_name)


def _get_s3_client():
    """Return an S3 client."""
    return boto3.client("s3")


def _get_bucket_name() -> str:
    """Return the image bucket name from environment variables."""
    return os.environ.get("IMAGE_BUCKET_NAME", "")


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _serialize_item(item: dict) -> dict:
    """Convert DynamoDB item to JSON-serializable dict.

    Converts Decimal values to int or float as appropriate and removes
    internal DynamoDB key attributes.
    """
    result = {}
    internal_keys = {"PK", "SK", "GSI1PK", "GSI1SK", "entityType"}

    for key, value in item.items():
        if key in internal_keys:
            continue
        if isinstance(value, Decimal):
            result[key] = int(value) if value == int(value) else float(value)
        else:
            result[key] = value

    return result


def _watch_exists(table, watch_id: str) -> bool:
    """Check whether a watch record exists in DynamoDB."""
    try:
        result = table.get_item(Key={"PK": f"WATCH#{watch_id}", "SK": "METADATA"})
        return "Item" in result
    except ClientError:
        return False


def _count_images(table, watch_id: str) -> int:
    """Count the number of image records for a watch."""
    try:
        response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"WATCH#{watch_id}",
                ":sk_prefix": "IMAGE#",
            },
            Select="COUNT",
        )
        return response.get("Count", 0)
    except ClientError:
        return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_upload_url(watch_id: str, data: dict) -> dict:
    """Generate a pre-signed S3 PUT URL for image upload.

    Args:
        watch_id: The watch UUID.
        data: Dict with ``filename`` and ``contentType``.

    Returns:
        API Gateway response dict with the pre-signed URL and image metadata
        (200), validation error (400), not found (404), or conflict (409).
    """
    # Validate required fields
    filename = data.get("filename")
    content_type = data.get("contentType")

    errors = []
    if not filename or not str(filename).strip():
        errors.append("filename is required")
    if not content_type or not str(content_type).strip():
        errors.append("contentType is required")

    if errors:
        return error_response(400, "VALIDATION_ERROR", "Validation failed", {"errors": errors})

    # Validate content type
    if content_type not in VALID_CONTENT_TYPES:
        return error_response(
            400,
            "VALIDATION_ERROR",
            f"Invalid content type: {content_type}. Accepted formats: image/jpeg, image/png, image/webp",
        )

    table = _get_table()

    # Check watch exists
    if not _watch_exists(table, watch_id):
        return error_response(404, "NOT_FOUND", f"Watch {watch_id} not found")

    # Check image count limit
    image_count = _count_images(table, watch_id)
    if image_count >= MAX_IMAGES_PER_WATCH:
        return error_response(
            409,
            "CONFLICT",
            f"Image limit reached. Maximum {MAX_IMAGES_PER_WATCH} images per watch.",
        )

    # Generate image ID and S3 key
    image_id = str(uuid.uuid4())
    ext = CONTENT_TYPE_TO_EXT[content_type]
    s3_key = f"watches/{watch_id}/{image_id}.{ext}"

    # Generate pre-signed URL
    bucket_name = _get_bucket_name()
    s3_client = _get_s3_client()

    try:
        upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": bucket_name,
                "Key": s3_key,
                "ContentType": content_type,
            },
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )
    except ClientError as exc:
        logger.error("Failed to generate pre-signed URL: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to generate upload URL")

    return json_response(200, {
        "uploadUrl": upload_url,
        "imageId": image_id,
        "s3Key": s3_key,
    })


def confirm_upload(watch_id: str, image_id: str) -> dict:
    """Confirm an image upload and store metadata in DynamoDB.

    Verifies the S3 object exists before storing metadata.

    Args:
        watch_id: The watch UUID.
        image_id: The image UUID.

    Returns:
        API Gateway response dict with image metadata (200),
        not found (404), or error (500).
    """
    table = _get_table()

    # Check watch exists
    if not _watch_exists(table, watch_id):
        return error_response(404, "NOT_FOUND", f"Watch {watch_id} not found")

    bucket_name = _get_bucket_name()
    s3_client = _get_s3_client()

    # Try to find the S3 object — we need to determine the extension
    s3_key = None
    content_type = None
    for ct, ext in CONTENT_TYPE_TO_EXT.items():
        candidate_key = f"watches/{watch_id}/{image_id}.{ext}"
        try:
            s3_client.head_object(Bucket=bucket_name, Key=candidate_key)
            s3_key = candidate_key
            content_type = ct
            break
        except ClientError:
            continue

    if s3_key is None:
        return error_response(404, "NOT_FOUND", f"Image {image_id} not found in S3")

    now = _now_iso()

    # Extract filename from s3_key
    filename = s3_key.split("/")[-1]

    item = {
        "PK": f"WATCH#{watch_id}",
        "SK": f"IMAGE#{image_id}",
        "GSI1PK": f"WATCH#{watch_id}#IMAGES",
        "GSI1SK": f"{now}#{image_id}",
        "entityType": "IMAGE",
        "imageId": image_id,
        "watchId": watch_id,
        "s3Key": s3_key,
        "filename": filename,
        "contentType": content_type,
        "uploadedAt": now,
    }

    try:
        table.put_item(Item=item)
    except ClientError as exc:
        logger.error("Failed to store image metadata: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to confirm upload")

    return json_response(200, _serialize_item(item))


def list_images(watch_id: str) -> dict:
    """List all images for a watch.

    Returns pre-signed GET URLs for each image so the browser can display them.

    Args:
        watch_id: The watch UUID.

    Returns:
        API Gateway response dict with a list of image metadata records (200).
    """
    table = _get_table()

    try:
        response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"WATCH#{watch_id}",
                ":sk_prefix": "IMAGE#",
            },
        )
    except ClientError as exc:
        logger.error("Failed to list images: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to list images")

    items = response.get("Items", [])
    images = [_serialize_item(item) for item in items]

    # Generate pre-signed GET URLs for each image
    bucket_name = _get_bucket_name()
    if bucket_name:
        s3_client = _get_s3_client()
        for img in images:
            s3_key = img.get("s3Key", "")
            if s3_key:
                try:
                    img["url"] = s3_client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": bucket_name, "Key": s3_key},
                        ExpiresIn=3600,
                    )
                except ClientError:
                    pass

    return json_response(200, {"images": images})


def delete_image(watch_id: str, image_id: str) -> dict:
    """Delete an image from S3 and its metadata from DynamoDB.

    Args:
        watch_id: The watch UUID.
        image_id: The image UUID.

    Returns:
        API Gateway response dict (200 on success, 404 if not found).
    """
    table = _get_table()

    # Check image metadata exists
    try:
        result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": f"IMAGE#{image_id}"}
        )
    except ClientError as exc:
        logger.error("Failed to check image existence: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to delete image")

    item = result.get("Item")
    if not item:
        return error_response(404, "NOT_FOUND", f"Image {image_id} not found")

    s3_key = item.get("s3Key", "")

    # Delete S3 object
    bucket_name = _get_bucket_name()
    s3_client = _get_s3_client()

    try:
        s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
    except ClientError as exc:
        logger.error("Failed to delete S3 object: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to delete image from storage")

    # Delete DynamoDB metadata
    try:
        table.delete_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": f"IMAGE#{image_id}"}
        )
    except ClientError as exc:
        logger.error("Failed to delete image metadata: %s", exc)
        return error_response(500, "INTERNAL_ERROR", "Failed to delete image metadata")

    return json_response(200, {"message": f"Image {image_id} deleted"})
