"""Property-based tests for CRUD operations.

Uses Hypothesis to verify data integrity invariants across many inputs.
"""

import json

import pytest
from hypothesis import given, settings, HealthCheck

from tests.conftest import watch_attributes


# Feature: watch-flip-tracker, Property 3: Watch create/read round-trip
class TestWatchCreateReadRoundTrip:
    """Property 3: Watch create/read round-trip.

    **Validates: Requirements 2.1, 2.3, 2.6**

    For any valid set of watch attributes (with at least maker and model
    provided), creating a Watch_Record and then reading it back by its
    returned identifier should yield a record with all original attributes
    preserved exactly.
    """

    @given(attrs=watch_attributes())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_watch_create_read_round_trip(self, attrs, aws):
        """Created watch attributes are preserved on read-back."""
        from src.services.watch_service import create_watch, get_watch

        # Create
        create_resp = create_watch(attrs)
        assert create_resp["statusCode"] == 201, (
            f"Expected 201, got {create_resp['statusCode']}: "
            f"{create_resp['body']}"
        )

        created = json.loads(create_resp["body"])
        watch_id = created["watchId"]

        # Read back
        get_resp = get_watch(watch_id)
        assert get_resp["statusCode"] == 200
        fetched = json.loads(get_resp["body"])

        # Verify all original attributes are preserved
        for key, value in attrs.items():
            assert key in fetched, f"Missing attribute: {key}"
            assert fetched[key] == value, (
                f"Attribute {key} mismatch: expected {value!r}, got {fetched[key]!r}"
            )

        # Verify system-generated fields exist
        assert "watchId" in fetched
        assert "createdAt" in fetched
        assert "updatedAt" in fetched

        # Default status should be in_collection if not provided
        if "status" not in attrs:
            assert fetched["status"] == "in_collection"


# Feature: watch-flip-tracker, Property 7: Entity validation rejects missing required fields
class TestWatchValidationRejectsMissingFields:
    """Property 7: Entity validation rejects missing required fields (watch portion).

    **Validates: Requirement 2.7**

    For any watch creation request where maker and/or model are missing,
    the Watch_Service should return a validation error listing the missing
    required fields.
    """

    def test_missing_maker_returns_validation_error(self, aws):
        """Creating a watch without maker returns validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({"model": "Submariner"})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("maker" in e for e in errors)

    def test_missing_model_returns_validation_error(self, aws):
        """Creating a watch without model returns validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({"maker": "Rolex"})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("model" in e for e in errors)

    def test_missing_both_returns_validation_error(self, aws):
        """Creating a watch without maker and model returns validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("maker" in e for e in errors)
        assert any("model" in e for e in errors)

    def test_empty_maker_returns_validation_error(self, aws):
        """Creating a watch with empty maker returns validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({"maker": "", "model": "Submariner"})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_whitespace_maker_returns_validation_error(self, aws):
        """Creating a watch with whitespace-only maker returns validation error."""
        from src.services.watch_service import create_watch

        resp = create_watch({"maker": "   ", "model": "Submariner"})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"


from tests.conftest import expense_data


# Feature: watch-flip-tracker, Property 4: Expense create/read round-trip with integer cents
class TestExpenseCreateReadRoundTrip:
    """Property 4: Expense create/read round-trip with integer cents.

    **Validates: Requirements 3.1, 3.2, 3.8**

    For any valid expense data (with category and amount provided), creating
    an Expense_Record for a watch and then reading it back should yield a
    record with all original attributes preserved, and the stored amount
    should be an integer (cents) with no fractional component.
    """

    @given(exp=expense_data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_expense_create_read_round_trip(self, exp, aws):
        """Created expense attributes are preserved on read-back, amount is integer cents."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense, list_expenses

        # First create a watch to attach expenses to
        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        assert watch_resp["statusCode"] == 201
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Create expense
        create_resp = create_expense(watch_id, exp)
        assert create_resp["statusCode"] == 201, (
            f"Expected 201, got {create_resp['statusCode']}: "
            f"{create_resp['body']}"
        )

        created = json.loads(create_resp["body"])
        expense_id = created["expenseId"]

        # Read back via list_expenses
        list_resp = list_expenses(watch_id)
        assert list_resp["statusCode"] == 200
        expenses = json.loads(list_resp["body"])["expenses"]

        # Find our expense
        fetched = next((e for e in expenses if e["expenseId"] == expense_id), None)
        assert fetched is not None, "Created expense not found in list"

        # Verify all original attributes are preserved
        for key, value in exp.items():
            assert key in fetched, f"Missing attribute: {key}"
            # category is stripped on storage (same as maker/model in watch service)
            expected = value.strip() if key == "category" else value
            assert fetched[key] == expected, (
                f"Attribute {key} mismatch: expected {expected!r}, got {fetched[key]!r}"
            )

        # Verify amountCents is an integer (no fractional component)
        assert isinstance(fetched["amountCents"], int), (
            f"amountCents should be int, got {type(fetched['amountCents'])}"
        )

        # Verify system-generated fields exist
        assert "expenseId" in fetched
        assert "watchId" in fetched
        assert "createdAt" in fetched
        assert "updatedAt" in fetched
        assert fetched["watchId"] == watch_id


# Feature: watch-flip-tracker, Property 7: Entity validation rejects missing required fields
class TestExpenseValidationRejectsMissingFields:
    """Property 7: Entity validation rejects missing required fields (expense portion).

    **Validates: Requirement 3.6**

    For any expense creation request where category and/or amountCents are
    missing, the Expense_Service should return a validation error listing
    the missing required fields.
    """

    def test_missing_category_returns_validation_error(self, aws):
        """Creating an expense without category returns validation error."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"amountCents": 5000})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("category" in e for e in errors)

    def test_missing_amount_returns_validation_error(self, aws):
        """Creating an expense without amountCents returns validation error."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"category": "Service"})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("amountCents" in e for e in errors)

    def test_missing_both_returns_validation_error(self, aws):
        """Creating an expense without category and amountCents returns validation error."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("category" in e for e in errors)
        assert any("amountCents" in e for e in errors)

    def test_empty_category_returns_validation_error(self, aws):
        """Creating an expense with empty category returns validation error."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"category": "", "amountCents": 5000})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_whitespace_category_returns_validation_error(self, aws):
        """Creating an expense with whitespace-only category returns validation error."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_expense(watch_id, {"category": "   ", "amountCents": 5000})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"


from tests.conftest import sale_data


# Feature: watch-flip-tracker, Property 5: Sale create/read round-trip
class TestSaleCreateReadRoundTrip:
    """Property 5: Sale create/read round-trip.

    **Validates: Requirements 4.1, 4.2, 4.5**

    For any valid sale data (with sale price and sale date provided), creating
    a Sale_Record for a watch and then reading it back should yield a record
    with all original attributes preserved, with the sale price stored as
    integer cents.
    """

    @given(sale=sale_data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_sale_create_read_round_trip(self, sale, aws):
        """Created sale attributes are preserved on read-back, price is integer cents."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale, get_sale

        # First create a watch to attach the sale to
        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        assert watch_resp["statusCode"] == 201
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Create sale
        create_resp = create_sale(watch_id, sale)
        assert create_resp["statusCode"] == 201, (
            f"Expected 201, got {create_resp['statusCode']}: "
            f"{create_resp['body']}"
        )

        created = json.loads(create_resp["body"])

        # Read back via get_sale
        get_resp = get_sale(watch_id)
        assert get_resp["statusCode"] == 200
        fetched = json.loads(get_resp["body"])

        # Verify all original attributes are preserved
        for key, value in sale.items():
            assert key in fetched, f"Missing attribute: {key}"
            assert fetched[key] == value, (
                f"Attribute {key} mismatch: expected {value!r}, got {fetched[key]!r}"
            )

        # Verify salePriceCents is an integer (no fractional component)
        assert isinstance(fetched["salePriceCents"], int), (
            f"salePriceCents should be int, got {type(fetched['salePriceCents'])}"
        )

        # Verify system-generated fields exist
        assert "watchId" in fetched
        assert "createdAt" in fetched
        assert "updatedAt" in fetched
        assert fetched["watchId"] == watch_id


# Feature: watch-flip-tracker, Property 9: Recording a sale sets watch status to sold
class TestSaleSetsWatchStatusToSold:
    """Property 9: Recording a sale sets watch status to sold.

    **Validates: Requirement 4.7**

    For any Watch_Record with a status other than "sold", creating a
    Sale_Record for that watch should update the Watch_Record's status
    to "sold".
    """

    @given(sale=sale_data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_sale_sets_watch_status_to_sold(self, sale, aws):
        """Creating a sale updates the watch status to 'sold'."""
        from src.services.watch_service import create_watch, get_watch
        from src.services.sale_service import create_sale

        # Create a watch (default status is in_collection)
        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        assert watch_resp["statusCode"] == 201
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Verify initial status is not "sold"
        get_resp = get_watch(watch_id)
        initial = json.loads(get_resp["body"])
        assert initial["status"] != "sold"

        # Create sale
        create_resp = create_sale(watch_id, sale)
        assert create_resp["statusCode"] == 201

        # Verify watch status is now "sold"
        get_resp = get_watch(watch_id)
        updated = json.loads(get_resp["body"])
        assert updated["status"] == "sold", (
            f"Expected status 'sold', got {updated['status']!r}"
        )


# Feature: watch-flip-tracker, Property 7: Entity validation rejects missing required fields
class TestSaleValidationRejectsMissingFields:
    """Property 7: Entity validation rejects missing required fields (sale portion).

    **Validates: Requirement 4.6**

    For any sale creation request where salePriceCents and/or saleDate are
    missing, the Sale_Service should return a validation error listing the
    missing required fields.
    """

    def test_missing_sale_price_returns_validation_error(self, aws):
        """Creating a sale without salePriceCents returns validation error."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"saleDate": "2024-06-01"})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("salePriceCents" in e for e in errors)

    def test_missing_sale_date_returns_validation_error(self, aws):
        """Creating a sale without saleDate returns validation error."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"salePriceCents": 50000})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        errors = body["error"]["details"]["errors"]
        assert any("saleDate" in e for e in errors)

    def test_missing_both_returns_validation_error(self, aws):
        """Creating a sale without salePriceCents and saleDate lists both in errors."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        errors = body["error"]["details"]["errors"]
        assert any("salePriceCents" in e for e in errors)
        assert any("saleDate" in e for e in errors)

    def test_empty_sale_date_returns_validation_error(self, aws):
        """Creating a sale with empty saleDate returns validation error."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"salePriceCents": 50000, "saleDate": ""})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_whitespace_sale_date_returns_validation_error(self, aws):
        """Creating a sale with whitespace-only saleDate returns validation error."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        resp = create_sale(watch_id, {"salePriceCents": 50000, "saleDate": "   "})
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"


from hypothesis import strategies as st


# Feature: watch-flip-tracker, Property 6: Entity update preserves unchanged fields
class TestEntityUpdatePreservesUnchangedFields:
    """Property 6: Entity update preserves unchanged fields.

    **Validates: Requirements 2.4, 3.3, 4.3**

    For any existing Watch_Record, Expense_Record, or Sale_Record, and any
    valid partial update, the updated record should reflect exactly the
    changed attributes while all non-updated attributes remain identical
    to their pre-update values.
    """

    @given(attrs=watch_attributes())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_watch_update_preserves_unchanged_fields(self, attrs, aws):
        """Updating a watch preserves fields not included in the update."""
        from src.services.watch_service import create_watch, get_watch, update_watch

        # Create watch with generated attributes
        create_resp = create_watch(attrs)
        assert create_resp["statusCode"] == 201
        created = json.loads(create_resp["body"])
        watch_id = created["watchId"]

        # Read back original state
        get_resp = get_watch(watch_id)
        assert get_resp["statusCode"] == 200
        original = json.loads(get_resp["body"])

        # Update only the notes field (a field unlikely to be in generated attrs)
        update_data = {"notes": "Updated notes value"}
        update_resp = update_watch(watch_id, update_data)
        assert update_resp["statusCode"] == 200
        updated = json.loads(update_resp["body"])

        # Verify the updated field changed
        assert updated["notes"] == "Updated notes value"

        # Verify all other fields (except updatedAt and notes) are preserved
        for key, value in original.items():
            if key in ("updatedAt", "notes"):
                continue
            assert key in updated, f"Missing field after update: {key}"
            assert updated[key] == value, (
                f"Field {key} changed unexpectedly: {value!r} -> {updated[key]!r}"
            )

    @given(exp=expense_data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_expense_update_preserves_unchanged_fields(self, exp, aws):
        """Updating an expense preserves fields not included in the update."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense, list_expenses, update_expense

        # Create a watch
        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        assert watch_resp["statusCode"] == 201
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Create expense
        create_resp = create_expense(watch_id, exp)
        assert create_resp["statusCode"] == 201
        created = json.loads(create_resp["body"])
        expense_id = created["expenseId"]

        # Read back original state via list
        list_resp = list_expenses(watch_id)
        assert list_resp["statusCode"] == 200
        expenses = json.loads(list_resp["body"])["expenses"]
        original = next(e for e in expenses if e["expenseId"] == expense_id)

        # Update only the description field
        update_data = {"description": "Updated description"}
        update_resp = update_expense(watch_id, expense_id, update_data)
        assert update_resp["statusCode"] == 200
        updated = json.loads(update_resp["body"])

        # Verify the updated field changed
        assert updated["description"] == "Updated description"

        # Verify all other fields (except updatedAt and description) are preserved
        for key, value in original.items():
            if key in ("updatedAt", "description"):
                continue
            assert key in updated, f"Missing field after update: {key}"
            assert updated[key] == value, (
                f"Field {key} changed unexpectedly: {value!r} -> {updated[key]!r}"
            )

    @given(sale=sale_data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_sale_update_preserves_unchanged_fields(self, sale, aws):
        """Updating a sale preserves fields not included in the update."""
        from src.services.watch_service import create_watch
        from src.services.sale_service import create_sale, get_sale, update_sale

        # Create a watch
        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        assert watch_resp["statusCode"] == 201
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Create sale
        create_resp = create_sale(watch_id, sale)
        assert create_resp["statusCode"] == 201

        # Read back original state
        get_resp = get_sale(watch_id)
        assert get_resp["statusCode"] == 200
        original = json.loads(get_resp["body"])

        # Update only the notes field
        update_data = {"notes": "Updated sale notes"}
        update_resp = update_sale(watch_id, update_data)
        assert update_resp["statusCode"] == 200
        updated = json.loads(update_resp["body"])

        # Verify the updated field changed
        assert updated["notes"] == "Updated sale notes"

        # Verify all other fields (except updatedAt and notes) are preserved
        for key, value in original.items():
            if key in ("updatedAt", "notes"):
                continue
            assert key in updated, f"Missing field after update: {key}"
            assert updated[key] == value, (
                f"Field {key} changed unexpectedly: {value!r} -> {updated[key]!r}"
            )


# Feature: watch-flip-tracker, Property 8: Watch cascade delete removes all associated data
class TestWatchCascadeDeleteRemovesAllData:
    """Property 8: Watch cascade delete removes all associated data.

    **Validates: Requirement 2.5**

    For any Watch_Record that has associated Expense_Records, a Sale_Record,
    and Image records, deleting the watch should remove the Watch_Record and
    all associated Expense_Records, Sale_Records, and image metadata from
    DynamoDB.
    """

    @given(
        expenses=st.lists(expense_data(), min_size=1, max_size=3),
        sale=sale_data(),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_cascade_delete_removes_all_associated_data(self, expenses, sale, aws):
        """Deleting a watch removes all expenses, sale, and image metadata."""
        import uuid
        from src.services.watch_service import create_watch, get_watch, delete_watch
        from src.services.expense_service import create_expense, list_expenses
        from src.services.sale_service import create_sale, get_sale

        # Create a watch
        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        assert watch_resp["statusCode"] == 201
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Create expenses
        for exp in expenses:
            resp = create_expense(watch_id, exp)
            assert resp["statusCode"] == 201

        # Create sale
        sale_resp = create_sale(watch_id, sale)
        assert sale_resp["statusCode"] == 201

        # Create an image metadata record directly in DynamoDB
        table = aws["dynamodb_table"]
        image_id = str(uuid.uuid4())
        table.put_item(Item={
            "PK": f"WATCH#{watch_id}",
            "SK": f"IMAGE#{image_id}",
            "GSI1PK": f"WATCH#{watch_id}#IMAGES",
            "GSI1SK": f"2024-01-01#{image_id}",
            "entityType": "IMAGE",
            "imageId": image_id,
            "watchId": watch_id,
            "s3Key": f"watches/{watch_id}/{image_id}.jpg",
            "filename": "test.jpg",
            "contentType": "image/jpeg",
            "uploadedAt": "2024-01-01T00:00:00+00:00",
        })

        # Verify data exists before delete
        assert get_watch(watch_id)["statusCode"] == 200
        expenses_resp = list_expenses(watch_id)
        assert len(json.loads(expenses_resp["body"])["expenses"]) == len(expenses)
        assert get_sale(watch_id)["statusCode"] == 200

        # Delete the watch
        delete_resp = delete_watch(watch_id)
        assert delete_resp["statusCode"] == 200

        # Verify watch is gone
        assert get_watch(watch_id)["statusCode"] == 404

        # Verify expenses are gone
        expenses_resp = list_expenses(watch_id)
        assert json.loads(expenses_resp["body"])["expenses"] == []

        # Verify sale is gone
        assert get_sale(watch_id)["statusCode"] == 404

        # Verify image metadata is gone
        img_result = table.get_item(
            Key={"PK": f"WATCH#{watch_id}", "SK": f"IMAGE#{image_id}"}
        )
        assert "Item" not in img_result
