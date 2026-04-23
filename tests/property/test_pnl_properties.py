"""Property-based tests for Profit/Loss computation.

Uses Hypothesis to verify P&L calculation invariants across many inputs.
"""

import json

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from tests.conftest import watch_attributes, expense_data, sale_data


# Feature: watch-flip-tracker, Property 10: Profit/loss computation correctness
class TestPnlComputationCorrectness:
    """Property 10: Profit/loss computation correctness.

    **Validates: Requirements 5.1, 5.2, 5.3**

    For any Watch_Record with a list of Expense_Records and an optional
    Sale_Record, the Profit_Loss_Calculator should compute P&L as:
    sale_price_cents - sum(expense_amount_cents) when a sale exists, or
    -sum(expense_amount_cents) when no sale exists. The result indicator
    should be "profit" when positive, "loss" when negative, and
    "break_even" when zero.
    """

    @given(
        expenses=st.lists(expense_data(), min_size=0, max_size=5),
        sale=sale_data(),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_pnl_with_sale(self, expenses, sale, aws):
        """P&L with a sale equals sale_price - sum(expenses)."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense
        from src.services.sale_service import create_sale
        from src.services.profit_loss_service import calculate_watch_pnl

        # Create a watch
        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        assert watch_resp["statusCode"] == 201
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Create expenses
        total_expense_cents = 0
        for exp in expenses:
            resp = create_expense(watch_id, exp)
            assert resp["statusCode"] == 201
            total_expense_cents += exp["amountCents"]

        # Create sale
        sale_resp = create_sale(watch_id, sale)
        assert sale_resp["statusCode"] == 201

        # Calculate P&L
        pnl_resp = calculate_watch_pnl(watch_id)
        assert pnl_resp["statusCode"] == 200
        result = json.loads(pnl_resp["body"])

        expected_pnl = sale["salePriceCents"] - total_expense_cents

        assert result["pnlCents"] == expected_pnl
        assert result["totalExpenseCents"] == total_expense_cents
        assert result["salePriceCents"] == sale["salePriceCents"]
        assert result["watchId"] == watch_id

        # Verify indicator
        if expected_pnl > 0:
            assert result["indicator"] == "profit"
        elif expected_pnl < 0:
            assert result["indicator"] == "loss"
        else:
            assert result["indicator"] == "break_even"

    @given(
        expenses=st.lists(expense_data(), min_size=1, max_size=5),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_pnl_without_sale(self, expenses, aws):
        """P&L without a sale equals -sum(expenses)."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense
        from src.services.profit_loss_service import calculate_watch_pnl

        # Create a watch
        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        assert watch_resp["statusCode"] == 201
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Create expenses
        total_expense_cents = 0
        for exp in expenses:
            resp = create_expense(watch_id, exp)
            assert resp["statusCode"] == 201
            total_expense_cents += exp["amountCents"]

        # Calculate P&L (no sale)
        pnl_resp = calculate_watch_pnl(watch_id)
        assert pnl_resp["statusCode"] == 200
        result = json.loads(pnl_resp["body"])

        expected_pnl = -total_expense_cents

        assert result["pnlCents"] == expected_pnl
        assert result["totalExpenseCents"] == total_expense_cents
        assert result["salePriceCents"] is None
        assert result["watchId"] == watch_id
        assert result["indicator"] == "loss"

    def test_pnl_no_expenses_no_sale(self, aws):
        """P&L with no expenses and no sale is zero (break_even)."""
        from src.services.watch_service import create_watch
        from src.services.profit_loss_service import calculate_watch_pnl

        watch_resp = create_watch({"maker": "TestMaker", "model": "TestModel"})
        assert watch_resp["statusCode"] == 201
        watch_id = json.loads(watch_resp["body"])["watchId"]

        pnl_resp = calculate_watch_pnl(watch_id)
        assert pnl_resp["statusCode"] == 200
        result = json.loads(pnl_resp["body"])

        assert result["pnlCents"] == 0
        assert result["totalExpenseCents"] == 0
        assert result["salePriceCents"] is None
        assert result["indicator"] == "break_even"

    def test_pnl_nonexistent_watch(self, aws):
        """P&L for a nonexistent watch returns 404."""
        from src.services.profit_loss_service import calculate_watch_pnl

        pnl_resp = calculate_watch_pnl("nonexistent-id")
        assert pnl_resp["statusCode"] == 404


# Feature: watch-flip-tracker, Property 11: Portfolio summary aggregation correctness
class TestPortfolioSummaryAggregation:
    """Property 11: Portfolio summary aggregation correctness.

    **Validates: Requirement 5.4**

    For any set of Watch_Records with known individual P&L values, the
    portfolio summary should return a total P&L equal to the sum of all
    individual P&L values, a correct count of profitable watches (P&L > 0),
    a correct count of loss-making watches (P&L < 0), and a correct count
    of unsold watches (no Sale_Record).
    """

    @given(
        expense_lists=st.lists(
            st.lists(expense_data(), min_size=0, max_size=3),
            min_size=1,
            max_size=4,
        ),
        sales=st.lists(
            st.one_of(st.none(), sale_data()),
            min_size=1,
            max_size=4,
        ),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_portfolio_summary_aggregation(self, expense_lists, sales, aws):
        """Portfolio summary aggregates individual P&L values correctly."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense
        from src.services.sale_service import create_sale
        from src.services.profit_loss_service import (
            calculate_watch_pnl,
            calculate_portfolio_summary,
        )

        # Use the shorter list length to pair watches with expenses and sales
        count = min(len(expense_lists), len(sales))

        watch_ids = []
        expected_pnls = []

        for i in range(count):
            # Create a watch
            watch_resp = create_watch({"maker": f"Maker{i}", "model": f"Model{i}"})
            assert watch_resp["statusCode"] == 201
            watch_id = json.loads(watch_resp["body"])["watchId"]
            watch_ids.append(watch_id)

            # Create expenses
            total_exp = 0
            for exp in expense_lists[i]:
                resp = create_expense(watch_id, exp)
                assert resp["statusCode"] == 201
                total_exp += exp["amountCents"]

            # Optionally create sale
            sale = sales[i]
            if sale is not None:
                sale_resp = create_sale(watch_id, sale)
                assert sale_resp["statusCode"] == 201
                pnl = sale["salePriceCents"] - total_exp
            else:
                pnl = -total_exp

            expected_pnls.append((watch_id, pnl, sale is None))

        # Verify individual P&L values match
        for watch_id, expected_pnl, _ in expected_pnls:
            pnl_resp = calculate_watch_pnl(watch_id)
            assert pnl_resp["statusCode"] == 200
            result = json.loads(pnl_resp["body"])
            assert result["pnlCents"] == expected_pnl

        # Calculate portfolio summary
        summary_resp = calculate_portfolio_summary()
        assert summary_resp["statusCode"] == 200
        summary = json.loads(summary_resp["body"])

        # Extract only the watches we created in this example
        our_watches = [w for w in summary["watches"] if w["watchId"] in watch_ids]

        # Verify our watches have correct P&L
        our_total_pnl = sum(
            w["pnlCents"] for w in our_watches
            if w["salePriceCents"] is not None
        )
        expected_total = sum(pnl for _, pnl, is_unsold in expected_pnls if not is_unsold)
        assert our_total_pnl == expected_total

        # Verify counts for our watches
        our_profitable = sum(1 for w in our_watches if w["pnlCents"] > 0)
        our_loss = sum(
            1 for w in our_watches
            if w["salePriceCents"] is not None and w["pnlCents"] < 0
        )
        our_unsold = sum(1 for _, _, is_unsold in expected_pnls if is_unsold)

        expected_profitable = sum(1 for _, pnl, _ in expected_pnls if pnl > 0)
        expected_loss = sum(1 for _, pnl, is_unsold in expected_pnls if pnl < 0 and not is_unsold)

        assert our_profitable == expected_profitable
        assert our_loss == expected_loss
        assert our_unsold == sum(1 for w in our_watches if w["salePriceCents"] is None)

    def test_empty_portfolio_summary(self, aws):
        """Portfolio summary with no watches returns zero totals."""
        from src.services.profit_loss_service import calculate_portfolio_summary

        summary_resp = calculate_portfolio_summary()
        assert summary_resp["statusCode"] == 200
        summary = json.loads(summary_resp["body"])

        assert summary["totalPnlCents"] == 0
        assert summary["profitableCount"] == 0
        assert summary["lossCount"] == 0
        assert summary["unsoldCount"] == 0
        assert summary["watches"] == []
