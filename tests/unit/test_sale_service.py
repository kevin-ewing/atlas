"""Unit tests for the Sale Service.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

import json


class TestCreateSale:
    """Tests for sale_service.create_sale()."""

    def test_create_sale_with_required_fields(self, aws):
        """Creating a sale with salePriceCents and saleDate returns 201."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Submariner"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"salePriceCents": 1500000, "saleDate": "2024-06-15"})
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["salePriceCents"] == 1500000
        assert body["saleDate"] == "2024-06-15"
        assert "watchId" in body
        assert "createdAt" in body
        assert "updatedAt" in body
        assert body["watchId"] == watch_id

    def test_create_sale_with_all_optional_fields(self, aws):
        """Creating a sale with all fields preserves them."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Omega", "model": "Speedmaster"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        data = {
            "salePriceCents": 800000,
            "saleDate": "2024-07-01",
            "buyerOrPlatform": "Chrono24",
            "notes": "Sold quickly at asking price",
        }
        resp = create_sale(watch_id, data)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["salePriceCents"] == 800000
        assert body["saleDate"] == "2024-07-01"
        assert body["buyerOrPlatform"] == "Chrono24"
        assert body["notes"] == "Sold quickly at asking price"

    def test_create_sale_price_stored_as_integer_cents(self, aws):
        """salePriceCents is stored and returned as an integer."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"salePriceCents": 750000, "saleDate": "2024-06-01"})
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert isinstance(body["salePriceCents"], int)
        assert body["salePriceCents"] == 750000

    def test_create_sale_missing_price_returns_400(self, aws):
        """Missing salePriceCents should return 400 validation error."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"saleDate": "2024-06-01"})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("salePriceCents" in e for e in errors)

    def test_create_sale_missing_date_returns_400(self, aws):
        """Missing saleDate should return 400 validation error."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"salePriceCents": 500000})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("saleDate" in e for e in errors)

    def test_create_sale_missing_both_returns_400(self, aws):
        """Missing both salePriceCents and saleDate lists both in errors."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        errors = body["error"]["details"]["errors"]
        assert any("salePriceCents" in e for e in errors)
        assert any("saleDate" in e for e in errors)

    def test_create_sale_negative_price_returns_400(self, aws):
        """Negative salePriceCents should return validation error."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"salePriceCents": -100, "saleDate": "2024-06-01"})
        assert resp["statusCode"] == 400

    def test_create_sale_zero_price_returns_400(self, aws):
        """Zero salePriceCents should return validation error."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"salePriceCents": 0, "saleDate": "2024-06-01"})
        assert resp["statusCode"] == 400

    def test_create_sale_float_price_returns_400(self, aws):
        """Float salePriceCents should return validation error (must be integer)."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"salePriceCents": 500.5, "saleDate": "2024-06-01"})
        assert resp["statusCode"] == 400

    def test_create_sale_nonexistent_watch_returns_404(self, aws):
        """Creating a sale for a non-existent watch returns 404."""
        from src.services.sale_service import create_sale

        resp = create_sale("nonexistent-id", {"salePriceCents": 500000, "saleDate": "2024-06-01"})
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "NOT_FOUND"

    def test_create_sale_conflict_when_sale_exists(self, aws):
        """Creating a second sale for the same watch returns 409 CONFLICT."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # First sale succeeds
        resp1 = create_sale(watch_id, {"salePriceCents": 500000, "saleDate": "2024-06-01"})
        assert resp1["statusCode"] == 201

        # Second sale returns 409
        resp2 = create_sale(watch_id, {"salePriceCents": 600000, "saleDate": "2024-07-01"})
        assert resp2["statusCode"] == 409
        body = json.loads(resp2["body"])
        assert body["error"]["code"] == "CONFLICT"

    def test_create_sale_sets_watch_status_to_sold(self, aws):
        """Creating a sale updates the watch status to 'sold'."""
        from src.services.watch_service import create_watch, get_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Verify initial status
        get_resp = get_watch(watch_id)
        initial = json.loads(get_resp["body"])
        assert initial["status"] == "in_collection"

        # Create sale
        create_sale(watch_id, {"salePriceCents": 500000, "saleDate": "2024-06-01"})

        # Verify status changed
        get_resp = get_watch(watch_id)
        updated = json.loads(get_resp["body"])
        assert updated["status"] == "sold"


class TestGetSale:
    """Tests for sale_service.get_sale()."""

    def test_get_existing_sale(self, aws):
        """Getting an existing sale returns 200 with sale data."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale, get_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_sale(watch_id, {"salePriceCents": 500000, "saleDate": "2024-06-01"})

        resp = get_sale(watch_id)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["salePriceCents"] == 500000
        assert body["saleDate"] == "2024-06-01"
        assert body["watchId"] == watch_id

    def test_get_nonexistent_sale_returns_404(self, aws):
        """Getting a sale for a watch with no sale returns 404."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import get_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = get_sale(watch_id)
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "NOT_FOUND"


class TestUpdateSale:
    """Tests for sale_service.update_sale()."""

    def test_update_sale_partial(self, aws):
        """Updating a subset of fields preserves unchanged fields."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale, update_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_sale(watch_id, {
            "salePriceCents": 500000,
            "saleDate": "2024-06-01",
            "buyerOrPlatform": "eBay",
        })

        resp = update_sale(watch_id, {"salePriceCents": 550000})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["salePriceCents"] == 550000
        assert body["saleDate"] == "2024-06-01"
        assert body["buyerOrPlatform"] == "eBay"

    def test_update_sale_refreshes_updated_at(self, aws):
        """Updating a sale should refresh the updatedAt timestamp."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale, update_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_resp = create_sale(watch_id, {"salePriceCents": 500000, "saleDate": "2024-06-01"})
        created = json.loads(create_resp["body"])
        original_updated = created["updatedAt"]

        resp = update_sale(watch_id, {"notes": "Updated notes"})
        updated = json.loads(resp["body"])
        assert updated["updatedAt"] >= original_updated

    def test_update_nonexistent_sale_returns_404(self, aws):
        """Updating a non-existent sale returns 404."""
        from src.services.sale_service import update_sale

        resp = update_sale("some-watch", {"salePriceCents": 100000})
        assert resp["statusCode"] == 404

    def test_update_sale_invalid_price_returns_400(self, aws):
        """Updating with invalid salePriceCents returns 400."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale, update_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_sale(watch_id, {"salePriceCents": 500000, "saleDate": "2024-06-01"})

        resp = update_sale(watch_id, {"salePriceCents": -50})
        assert resp["statusCode"] == 400


class TestDeleteSale:
    """Tests for sale_service.delete_sale()."""

    def test_delete_existing_sale(self, aws):
        """Deleting an existing sale returns 200."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale, delete_sale, get_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_sale(watch_id, {"salePriceCents": 500000, "saleDate": "2024-06-01"})

        resp = delete_sale(watch_id)
        assert resp["statusCode"] == 200

        # Verify it's gone
        get_resp = get_sale(watch_id)
        assert get_resp["statusCode"] == 404

    def test_delete_nonexistent_sale_returns_404(self, aws):
        """Deleting a non-existent sale returns 404."""
        from src.services.sale_service import delete_sale

        resp = delete_sale("some-watch")
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "NOT_FOUND"

    def test_delete_sale_reverts_watch_status(self, aws):
        """Deleting a sale reverts the watch status to 'in_collection'."""
        from src.services.watch_service import create_watch, get_watch
        from src.services.sale_service import create_sale, delete_sale

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Create sale — status becomes "sold"
        create_sale(watch_id, {"salePriceCents": 500000, "saleDate": "2024-06-01"})
        get_resp = get_watch(watch_id)
        assert json.loads(get_resp["body"])["status"] == "sold"

        # Delete sale — status reverts to "in_collection"
        delete_sale(watch_id)
        get_resp = get_watch(watch_id)
        assert json.loads(get_resp["body"])["status"] == "in_collection"
