"""Unit tests for the Expense Service.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8
"""

import json


class TestCreateExpense:
    """Tests for expense_service.create_expense()."""

    def test_create_expense_with_required_fields(self, aws):
        """Creating an expense with category and amountCents returns 201."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Submariner"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"category": "Service", "amountCents": 5000})
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["category"] == "Service"
        assert body["amountCents"] == 5000
        assert "expenseId" in body
        assert "createdAt" in body
        assert "updatedAt" in body
        assert body["watchId"] == watch_id

    def test_create_expense_with_all_optional_fields(self, aws):
        """Creating an expense with all fields preserves them."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "Omega", "model": "Speedmaster"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        data = {
            "category": "Repair",
            "amountCents": 15000,
            "expenseDate": "2024-03-15",
            "vendor": "WatchFix Inc",
            "description": "Crystal replacement",
        }
        resp = create_expense(watch_id, data)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["category"] == "Repair"
        assert body["amountCents"] == 15000
        assert body["expenseDate"] == "2024-03-15"
        assert body["vendor"] == "WatchFix Inc"
        assert body["description"] == "Crystal replacement"

    def test_create_expense_amount_stored_as_integer_cents(self, aws):
        """amountCents is stored and returned as an integer (no fractional component)."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"category": "Polish", "amountCents": 7500})
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert isinstance(body["amountCents"], int)
        assert body["amountCents"] == 7500

    def test_create_expense_missing_category_returns_400(self, aws):
        """Missing category should return 400 validation error."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"amountCents": 5000})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("category" in e for e in errors)

    def test_create_expense_missing_amount_returns_400(self, aws):
        """Missing amountCents should return 400 validation error."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"category": "Service"})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("amountCents" in e for e in errors)

    def test_create_expense_missing_both_returns_400(self, aws):
        """Missing both category and amountCents lists both in errors."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        errors = body["error"]["details"]["errors"]
        assert any("category" in e for e in errors)
        assert any("amountCents" in e for e in errors)

    def test_create_expense_negative_amount_returns_400(self, aws):
        """Negative amountCents should return validation error."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"category": "Service", "amountCents": -100})
        assert resp["statusCode"] == 400

    def test_create_expense_zero_amount_returns_400(self, aws):
        """Zero amountCents should return validation error."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"category": "Service", "amountCents": 0})
        assert resp["statusCode"] == 400

    def test_create_expense_float_amount_returns_400(self, aws):
        """Float amountCents should return validation error (must be integer)."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"category": "Service", "amountCents": 50.5})
        assert resp["statusCode"] == 400

    def test_create_expense_nonexistent_watch_returns_404(self, aws):
        """Creating an expense for a non-existent watch returns 404."""
        from src.services.expense_service import create_expense

        resp = create_expense("nonexistent-id", {"category": "Service", "amountCents": 5000})
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "NOT_FOUND"


class TestListExpenses:
    """Tests for expense_service.list_expenses()."""

    def test_list_expenses_empty(self, aws):
        """Listing expenses for a watch with none returns empty list."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import list_expenses

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = list_expenses(watch_id)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["expenses"] == []

    def test_list_expenses_returns_all(self, aws):
        """Listing expenses returns all created expenses for the watch."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense, list_expenses

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_expense(watch_id, {"category": "Service", "amountCents": 5000})
        create_expense(watch_id, {"category": "Parts", "amountCents": 3000})

        resp = list_expenses(watch_id)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["expenses"]) == 2

    def test_list_expenses_only_for_specified_watch(self, aws):
        """Expenses for one watch should not appear in another watch's list."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense, list_expenses

        watch1_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch1_id = json.loads(watch1_resp["body"])["watchId"]

        watch2_resp = create_watch({"maker": "Omega", "model": "Speedy"})
        watch2_id = json.loads(watch2_resp["body"])["watchId"]

        create_expense(watch1_id, {"category": "Service", "amountCents": 5000})
        create_expense(watch2_id, {"category": "Parts", "amountCents": 3000})

        resp = list_expenses(watch1_id)
        body = json.loads(resp["body"])
        assert len(body["expenses"]) == 1
        assert body["expenses"][0]["category"] == "Service"


class TestUpdateExpense:
    """Tests for expense_service.update_expense()."""

    def test_update_expense_partial(self, aws):
        """Updating a subset of fields preserves unchanged fields."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense, update_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_resp = create_expense(watch_id, {
            "category": "Service",
            "amountCents": 5000,
            "vendor": "WatchFix",
        })
        expense_id = json.loads(create_resp["body"])["expenseId"]

        resp = update_expense(watch_id, expense_id, {"amountCents": 7500})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["amountCents"] == 7500
        assert body["category"] == "Service"
        assert body["vendor"] == "WatchFix"

    def test_update_expense_refreshes_updated_at(self, aws):
        """Updating an expense should refresh the updatedAt timestamp."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense, update_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_resp = create_expense(watch_id, {"category": "Service", "amountCents": 5000})
        created = json.loads(create_resp["body"])
        expense_id = created["expenseId"]
        original_updated = created["updatedAt"]

        resp = update_expense(watch_id, expense_id, {"description": "Updated"})
        updated = json.loads(resp["body"])
        assert updated["updatedAt"] >= original_updated

    def test_update_nonexistent_expense_returns_404(self, aws):
        """Updating a non-existent expense returns 404."""
        from src.services.expense_service import update_expense

        resp = update_expense("some-watch", "nonexistent-id", {"amountCents": 100})
        assert resp["statusCode"] == 404

    def test_update_expense_invalid_amount_returns_400(self, aws):
        """Updating with invalid amountCents returns 400."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense, update_expense

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_resp = create_expense(watch_id, {"category": "Service", "amountCents": 5000})
        expense_id = json.loads(create_resp["body"])["expenseId"]

        resp = update_expense(watch_id, expense_id, {"amountCents": -50})
        assert resp["statusCode"] == 400


class TestDeleteExpense:
    """Tests for expense_service.delete_expense()."""

    def test_delete_existing_expense(self, aws):
        """Deleting an existing expense returns 200."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense, delete_expense, list_expenses

        watch_resp = create_watch({"maker": "Rolex", "model": "Sub"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_resp = create_expense(watch_id, {"category": "Service", "amountCents": 5000})
        expense_id = json.loads(create_resp["body"])["expenseId"]

        resp = delete_expense(watch_id, expense_id)
        assert resp["statusCode"] == 200

        # Verify it's gone
        list_resp = list_expenses(watch_id)
        body = json.loads(list_resp["body"])
        assert len(body["expenses"]) == 0

    def test_delete_nonexistent_expense_returns_404(self, aws):
        """Deleting a non-existent expense returns 404."""
        from src.services.expense_service import delete_expense

        resp = delete_expense("some-watch", "nonexistent-id")
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "NOT_FOUND"
