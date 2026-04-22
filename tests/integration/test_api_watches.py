"""Integration tests for end-to-end watch CRUD through the Lambda handler.

Tests exercise the full request path: API Gateway event → Lambda handler →
service layer → DynamoDB (moto), verifying response codes and body content.

Requirements validated: 2.1–2.7
"""

import json

import src.services.auth_service as auth_mod
from src.handler import lambda_handler
from tests.conftest import TEST_USERNAME, TEST_PASSWORD


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


def _auth_event(route_key, token, path_params=None, body=None, query_params=None):
    """Build an authenticated API Gateway event."""
    event = {
        "routeKey": route_key,
        "headers": {"authorization": f"Bearer {token}"},
        "pathParameters": path_params or {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if query_params is not None:
        event["queryStringParameters"] = query_params
    return event


def _body(resp):
    return json.loads(resp["body"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWatchCRUD:
    """End-to-end watch create, read, update, delete."""

    def test_create_watch(self, aws):
        """Req 2.1: Create a watch with valid attributes → 201 with unique ID."""
        token = _login(aws)
        resp = lambda_handler(
            _auth_event("POST /watches", token, body={
                "maker": "Omega",
                "model": "Speedmaster",
                "yearOfProduction": 1969,
                "movementType": "manual",
            }),
            None,
        )
        assert resp["statusCode"] == 201
        data = _body(resp)
        assert data["maker"] == "Omega"
        assert data["model"] == "Speedmaster"
        assert "watchId" in data
        assert data["status"] == "in_collection"

    def test_get_watch(self, aws):
        """Req 2.3: Get a specific watch by ID."""
        token = _login(aws)

        # Create
        create_resp = lambda_handler(
            _auth_event("POST /watches", token, body={
                "maker": "Rolex", "model": "Submariner",
            }),
            None,
        )
        watch_id = _body(create_resp)["watchId"]

        # Read
        get_resp = lambda_handler(
            _auth_event("GET /watches/{watchId}", token, path_params={"watchId": watch_id}),
            None,
        )
        assert get_resp["statusCode"] == 200
        data = _body(get_resp)
        assert data["watchId"] == watch_id
        assert data["maker"] == "Rolex"

    def test_list_watches(self, aws):
        """Req 2.2: List all watches."""
        token = _login(aws)

        # Create two watches
        lambda_handler(
            _auth_event("POST /watches", token, body={"maker": "Seiko", "model": "SKX007"}),
            None,
        )
        lambda_handler(
            _auth_event("POST /watches", token, body={"maker": "Casio", "model": "F-91W"}),
            None,
        )

        # List
        list_resp = lambda_handler(
            _auth_event("GET /watches", token),
            None,
        )
        assert list_resp["statusCode"] == 200
        watches = _body(list_resp)["watches"]
        assert len(watches) == 2

    def test_update_watch(self, aws):
        """Req 2.4: Update a watch preserves unchanged fields."""
        token = _login(aws)

        create_resp = lambda_handler(
            _auth_event("POST /watches", token, body={
                "maker": "Tudor", "model": "Black Bay", "condition": "new",
            }),
            None,
        )
        watch_id = _body(create_resp)["watchId"]

        # Update only condition
        update_resp = lambda_handler(
            _auth_event("PUT /watches/{watchId}", token,
                        path_params={"watchId": watch_id},
                        body={"condition": "excellent"}),
            None,
        )
        assert update_resp["statusCode"] == 200
        data = _body(update_resp)
        assert data["condition"] == "excellent"
        assert data["maker"] == "Tudor"  # unchanged
        assert data["model"] == "Black Bay"  # unchanged

    def test_delete_watch(self, aws):
        """Req 2.5: Delete a watch removes it."""
        token = _login(aws)

        create_resp = lambda_handler(
            _auth_event("POST /watches", token, body={"maker": "Timex", "model": "Weekender"}),
            None,
        )
        watch_id = _body(create_resp)["watchId"]

        # Delete
        del_resp = lambda_handler(
            _auth_event("DELETE /watches/{watchId}", token, path_params={"watchId": watch_id}),
            None,
        )
        assert del_resp["statusCode"] == 200

        # Verify gone
        get_resp = lambda_handler(
            _auth_event("GET /watches/{watchId}", token, path_params={"watchId": watch_id}),
            None,
        )
        assert get_resp["statusCode"] == 404

    def test_create_watch_missing_required_fields(self, aws):
        """Req 2.7: Missing maker/model → validation error."""
        token = _login(aws)

        resp = lambda_handler(
            _auth_event("POST /watches", token, body={"yearOfProduction": 2020}),
            None,
        )
        assert resp["statusCode"] == 400
        data = _body(resp)
        assert data["error"]["code"] == "VALIDATION_ERROR"
        errors = data["error"]["details"]["errors"]
        assert any("maker" in e for e in errors)
        assert any("model" in e for e in errors)

    def test_get_nonexistent_watch_returns_404(self, aws):
        """Req 2.3: Non-existent watch → 404."""
        token = _login(aws)
        resp = lambda_handler(
            _auth_event("GET /watches/{watchId}", token,
                        path_params={"watchId": "00000000-0000-0000-0000-000000000000"}),
            None,
        )
        assert resp["statusCode"] == 404


class TestWatchWithExpensesAndSale:
    """End-to-end watch lifecycle: create, add expenses, record sale, check P&L."""

    def test_full_lifecycle(self, aws):
        """Reqs 2.1, 3.1, 4.1, 4.7, 5.1: Full watch lifecycle through the handler."""
        token = _login(aws)

        # 1. Create watch
        create_resp = lambda_handler(
            _auth_event("POST /watches", token, body={
                "maker": "Omega", "model": "Seamaster",
            }),
            None,
        )
        assert create_resp["statusCode"] == 201
        watch_id = _body(create_resp)["watchId"]

        # 2. Add expense
        exp_resp = lambda_handler(
            _auth_event("POST /watches/{watchId}/expenses", token,
                        path_params={"watchId": watch_id},
                        body={"category": "Purchase", "amountCents": 500000}),
            None,
        )
        assert exp_resp["statusCode"] == 201

        # 3. Record sale
        sale_resp = lambda_handler(
            _auth_event("POST /watches/{watchId}/sale", token,
                        path_params={"watchId": watch_id},
                        body={"salePriceCents": 650000, "saleDate": "2024-06-15"}),
            None,
        )
        assert sale_resp["statusCode"] == 201

        # 4. Verify watch status is now "sold"
        get_resp = lambda_handler(
            _auth_event("GET /watches/{watchId}", token, path_params={"watchId": watch_id}),
            None,
        )
        assert _body(get_resp)["status"] == "sold"

        # 5. Check portfolio summary
        summary_resp = lambda_handler(
            _auth_event("GET /portfolio/summary", token),
            None,
        )
        assert summary_resp["statusCode"] == 200
        summary = _body(summary_resp)
        assert summary["totalPnlCents"] == 150000  # 650000 - 500000

    def test_cascade_delete_removes_expenses_and_sale(self, aws):
        """Req 2.5: Deleting a watch removes associated expenses and sale."""
        token = _login(aws)

        # Create watch + expense + sale
        create_resp = lambda_handler(
            _auth_event("POST /watches", token, body={"maker": "IWC", "model": "Pilot"}),
            None,
        )
        watch_id = _body(create_resp)["watchId"]

        lambda_handler(
            _auth_event("POST /watches/{watchId}/expenses", token,
                        path_params={"watchId": watch_id},
                        body={"category": "Service", "amountCents": 30000}),
            None,
        )
        lambda_handler(
            _auth_event("POST /watches/{watchId}/sale", token,
                        path_params={"watchId": watch_id},
                        body={"salePriceCents": 800000, "saleDate": "2024-07-01"}),
            None,
        )

        # Delete watch
        lambda_handler(
            _auth_event("DELETE /watches/{watchId}", token, path_params={"watchId": watch_id}),
            None,
        )

        # Expenses should be gone
        exp_resp = lambda_handler(
            _auth_event("GET /watches/{watchId}/expenses", token,
                        path_params={"watchId": watch_id}),
            None,
        )
        assert _body(exp_resp)["expenses"] == []

        # Sale should be gone
        sale_resp = lambda_handler(
            _auth_event("GET /watches/{watchId}/sale", token,
                        path_params={"watchId": watch_id}),
            None,
        )
        assert sale_resp["statusCode"] == 404
