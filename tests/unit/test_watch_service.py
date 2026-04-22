"""Unit tests for the Watch Service."""

import json

import pytest

from tests.conftest import TEST_IMAGE_BUCKET, TEST_TABLE_NAME


class TestCreateWatch:
    """Tests for watch_service.create_watch()."""

    def test_create_watch_with_required_fields(self, aws):
        """Creating a watch with maker and model returns 201."""
        from src.services.watch_service import create_watch

        resp = create_watch({"maker": "Rolex", "model": "Submariner"})
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["maker"] == "Rolex"
        assert body["model"] == "Submariner"
        assert "watchId" in body
        assert "createdAt" in body
        assert "updatedAt" in body

    def test_create_watch_default_status_is_in_collection(self, aws):
        """Default status should be in_collection when not specified."""
        from src.services.watch_service import create_watch

        resp = create_watch({"maker": "Omega", "model": "Speedmaster"})
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["status"] == "in_collection"

    def test_create_watch_with_all_optional_fields(self, aws):
        """Creating a watch with all optional fields preserves them."""
        from src.services.watch_service import create_watch

        data = {
            "maker": "Rolex",
            "model": "Daytona",
            "referenceNumber": "116500LN",
            "yearOfProduction": 2020,
            "caseMaterial": "Stainless Steel",
            "caseDiameterMm": 40,
            "movementType": "automatic",
            "dialColor": "White",
            "bandMaterial": "Oyster",
            "bandColor": "Silver",
            "condition": "excellent",
            "boxIncluded": True,
            "papersIncluded": True,
            "features": ["chronograph", "date"],
            "serialNumber": "ABC123",
            "acquisitionDate": "2024-01-15",
            "acquisitionSource": "Chrono24",
            "status": "in_collection",
            "notes": "Great condition",
        }
        resp = create_watch(data)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])

        for key, value in data.items():
            assert body[key] == value, f"{key}: expected {value}, got {body[key]}"

    def test_create_watch_missing_maker_returns_400(self, aws):
        """Missing maker should return 400 validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({"model": "Submariner"})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_create_watch_missing_model_returns_400(self, aws):
        """Missing model should return 400 validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({"maker": "Rolex"})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_create_watch_missing_both_returns_400(self, aws):
        """Missing both maker and model should list both in errors."""
        from src.services.watch_service import create_watch

        resp = create_watch({})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        errors = body["error"]["details"]["errors"]
        assert any("maker" in e for e in errors)
        assert any("model" in e for e in errors)

    def test_create_watch_invalid_movement_type(self, aws):
        """Invalid movementType should return validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({
            "maker": "Rolex",
            "model": "Sub",
            "movementType": "solar",
        })
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_create_watch_invalid_condition(self, aws):
        """Invalid condition should return validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({
            "maker": "Rolex",
            "model": "Sub",
            "condition": "terrible",
        })
        assert resp["statusCode"] == 400

    def test_create_watch_invalid_status(self, aws):
        """Invalid status should return validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({
            "maker": "Rolex",
            "model": "Sub",
            "status": "lost",
        })
        assert resp["statusCode"] == 400

    def test_create_watch_invalid_features(self, aws):
        """Invalid feature values should return validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({
            "maker": "Rolex",
            "model": "Sub",
            "features": ["laser_beam"],
        })
        assert resp["statusCode"] == 400

    def test_create_watch_with_custom_status(self, aws):
        """Providing a valid status overrides the default."""
        from src.services.watch_service import create_watch

        resp = create_watch({
            "maker": "Omega",
            "model": "Speedmaster",
            "status": "for_sale",
        })
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["status"] == "for_sale"


class TestGetWatch:
    """Tests for watch_service.get_watch()."""

    def test_get_existing_watch(self, aws):
        """Getting an existing watch returns 200 with full data."""
        from src.services.watch_service import create_watch, get_watch

        create_resp = create_watch({"maker": "Rolex", "model": "Submariner"})
        watch_id = json.loads(create_resp["body"])["watchId"]

        resp = get_watch(watch_id)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["maker"] == "Rolex"
        assert body["model"] == "Submariner"

    def test_get_nonexistent_watch_returns_404(self, aws):
        """Getting a non-existent watch returns 404."""
        from src.services.watch_service import get_watch

        resp = get_watch("nonexistent-id")
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "NOT_FOUND"

    def test_get_watch_empty_id_returns_400(self, aws):
        """Getting a watch with empty ID returns 400."""
        from src.services.watch_service import get_watch

        resp = get_watch("")
        assert resp["statusCode"] == 400


class TestListWatches:
    """Tests for watch_service.list_watches()."""

    def test_list_watches_empty(self, aws):
        """Listing watches when none exist returns empty list."""
        from src.services.watch_service import list_watches

        resp = list_watches({})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["watches"] == []

    def test_list_watches_returns_all(self, aws):
        """Listing watches returns all created watches."""
        from src.services.watch_service import create_watch, list_watches

        create_watch({"maker": "Rolex", "model": "Submariner"})
        create_watch({"maker": "Omega", "model": "Speedmaster"})

        resp = list_watches({})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["watches"]) == 2

    def test_list_watches_sorted_by_acquisition_date_desc(self, aws):
        """Watches should be sorted by acquisition date descending."""
        from src.services.watch_service import create_watch, list_watches

        create_watch({
            "maker": "Rolex",
            "model": "Submariner",
            "acquisitionDate": "2023-01-01",
        })
        create_watch({
            "maker": "Omega",
            "model": "Speedmaster",
            "acquisitionDate": "2024-06-15",
        })

        resp = list_watches({})
        body = json.loads(resp["body"])
        watches = body["watches"]
        assert len(watches) == 2
        # Newer date should come first (descending)
        assert watches[0]["acquisitionDate"] == "2024-06-15"
        assert watches[1]["acquisitionDate"] == "2023-01-01"


class TestUpdateWatch:
    """Tests for watch_service.update_watch()."""

    def test_update_watch_partial(self, aws):
        """Updating a subset of fields preserves unchanged fields."""
        from src.services.watch_service import create_watch, update_watch

        create_resp = create_watch({
            "maker": "Rolex",
            "model": "Submariner",
            "condition": "good",
        })
        watch_id = json.loads(create_resp["body"])["watchId"]

        resp = update_watch(watch_id, {"condition": "excellent"})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["condition"] == "excellent"
        assert body["maker"] == "Rolex"
        assert body["model"] == "Submariner"

    def test_update_watch_refreshes_updated_at(self, aws):
        """Updating a watch should refresh the updatedAt timestamp."""
        from src.services.watch_service import create_watch, update_watch

        create_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        created = json.loads(create_resp["body"])
        watch_id = created["watchId"]
        original_updated = created["updatedAt"]

        resp = update_watch(watch_id, {"notes": "Updated notes"})
        updated = json.loads(resp["body"])
        assert updated["updatedAt"] >= original_updated

    def test_update_nonexistent_watch_returns_404(self, aws):
        """Updating a non-existent watch returns 404."""
        from src.services.watch_service import update_watch

        resp = update_watch("nonexistent-id", {"maker": "Omega"})
        assert resp["statusCode"] == 404

    def test_update_watch_invalid_enum(self, aws):
        """Updating with invalid enum value returns 400."""
        from src.services.watch_service import create_watch, update_watch

        create_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(create_resp["body"])["watchId"]

        resp = update_watch(watch_id, {"movementType": "solar"})
        assert resp["statusCode"] == 400


class TestDeleteWatch:
    """Tests for watch_service.delete_watch()."""

    def test_delete_existing_watch(self, aws):
        """Deleting an existing watch returns 200."""
        from src.services.watch_service import create_watch, delete_watch, get_watch

        create_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(create_resp["body"])["watchId"]

        resp = delete_watch(watch_id)
        assert resp["statusCode"] == 200

        # Verify it's gone
        get_resp = get_watch(watch_id)
        assert get_resp["statusCode"] == 404

    def test_delete_nonexistent_watch_returns_404(self, aws):
        """Deleting a non-existent watch returns 404."""
        from src.services.watch_service import delete_watch

        resp = delete_watch("nonexistent-id")
        assert resp["statusCode"] == 404

    def test_cascade_delete_removes_expenses(self, aws):
        """Deleting a watch removes associated expense records."""
        from src.services.watch_service import create_watch, delete_watch

        create_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(create_resp["body"])["watchId"]

        # Manually add an expense record
        table = aws["dynamodb_table"]
        table.put_item(Item={
            "PK": f"WATCH#{watch_id}",
            "SK": "EXPENSE#exp-001",
            "entityType": "EXPENSE",
            "expenseId": "exp-001",
            "watchId": watch_id,
            "category": "Service",
            "amountCents": 5000,
        })

        resp = delete_watch(watch_id)
        assert resp["statusCode"] == 200

        # Verify expense is gone
        result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": "EXPENSE#exp-001"}
        )
        assert "Item" not in result

    def test_cascade_delete_removes_sale(self, aws):
        """Deleting a watch removes associated sale record."""
        from src.services.watch_service import create_watch, delete_watch

        create_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(create_resp["body"])["watchId"]

        # Manually add a sale record
        table = aws["dynamodb_table"]
        table.put_item(Item={
            "PK": f"WATCH#{watch_id}",
            "SK": "SALE",
            "entityType": "SALE",
            "watchId": watch_id,
            "salePriceCents": 100000,
            "saleDate": "2024-06-01",
        })

        resp = delete_watch(watch_id)
        assert resp["statusCode"] == 200

        # Verify sale is gone
        result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": "SALE"}
        )
        assert "Item" not in result

    def test_cascade_delete_removes_images_from_dynamodb_and_s3(self, aws):
        """Deleting a watch removes image metadata and S3 objects."""
        from src.services.watch_service import create_watch, delete_watch

        create_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(create_resp["body"])["watchId"]

        # Upload a fake image to S3
        s3_key = f"watches/{watch_id}/img-001.jpg"
        aws["s3_client"].put_object(
            Bucket=TEST_IMAGE_BUCKET,
            Key=s3_key,
            Body=b"fake-image-data",
        )

        # Add image metadata to DynamoDB
        table = aws["dynamodb_table"]
        table.put_item(Item={
            "PK": f"WATCH#{watch_id}",
            "SK": "IMAGE#img-001",
            "entityType": "IMAGE",
            "imageId": "img-001",
            "watchId": watch_id,
            "s3Key": s3_key,
            "filename": "photo.jpg",
            "contentType": "image/jpeg",
        })

        resp = delete_watch(watch_id)
        assert resp["statusCode"] == 200

        # Verify image metadata is gone
        result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": "IMAGE#img-001"}
        )
        assert "Item" not in result

        # Verify S3 object is gone
        from botocore.exceptions import ClientError
        try:
            aws["s3_client"].head_object(
                Bucket=TEST_IMAGE_BUCKET, Key=s3_key
            )
            assert False, "S3 object should have been deleted"
        except ClientError as e:
            assert e.response["Error"]["Code"] == "404"

    def test_cascade_delete_removes_all_associated_data(self, aws):
        """Deleting a watch removes watch, expenses, sale, and images."""
        from src.services.watch_service import create_watch, delete_watch

        create_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(create_resp["body"])["watchId"]

        table = aws["dynamodb_table"]

        # Add expense
        table.put_item(Item={
            "PK": f"WATCH#{watch_id}",
            "SK": "EXPENSE#exp-001",
            "entityType": "EXPENSE",
            "expenseId": "exp-001",
            "watchId": watch_id,
            "category": "Service",
            "amountCents": 5000,
        })

        # Add sale
        table.put_item(Item={
            "PK": f"WATCH#{watch_id}",
            "SK": "SALE",
            "entityType": "SALE",
            "watchId": watch_id,
            "salePriceCents": 100000,
            "saleDate": "2024-06-01",
        })

        # Add image metadata
        s3_key = f"watches/{watch_id}/img-001.jpg"
        table.put_item(Item={
            "PK": f"WATCH#{watch_id}",
            "SK": "IMAGE#img-001",
            "entityType": "IMAGE",
            "imageId": "img-001",
            "watchId": watch_id,
            "s3Key": s3_key,
        })

        # Upload fake S3 object
        aws["s3_client"].put_object(
            Bucket=TEST_IMAGE_BUCKET,
            Key=s3_key,
            Body=b"fake",
        )

        resp = delete_watch(watch_id)
        assert resp["statusCode"] == 200

        # Verify all items are gone
        query_resp = table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": f"WATCH#{watch_id}"},
        )
        assert len(query_resp["Items"]) == 0
