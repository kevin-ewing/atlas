"""Unit tests for the Profit/Loss Calculator service.

Tests P&L computation for individual watches and portfolio summaries
with specific examples covering profit, loss, break-even, and edge cases.
"""

import json

import pytest


class TestCalculateWatchPnl:
    """Tests for calculate_watch_pnl function."""

    def test_pnl_profit_case(self, aws):
        """Watch sold for more than expenses yields profit indicator."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense
        from src.services.sale_service import create_sale
        from src.services.profit_loss_service import calculate_watch_pnl

        # Create watch
        watch_resp = create_watch({"maker": "Rolex", "model": "Submariner"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        # Add expenses totaling 500_00 cents ($500)
        create_expense(watch_id, {"category": "Purchase", "amountCents": 300_00})
        create_expense(watch_id, {"category": "Service", "amountCents": 200_00})

        # Sell for 800_00 cents ($800)
        create_sale(watch_id, {"salePriceCents": 800_00, "saleDate": "2024-06-01"})

        pnl_resp = calculate_watch_pnl(watch_id)
        assert pnl_resp["statusCode"] == 200
        result = json.loads(pnl_resp["body"])

        assert result["pnlCents"] == 300_00  # 800 - 500
        assert result["indicator"] == "profit"
        assert result["totalExpenseCents"] == 500_00
        assert result["salePriceCents"] == 800_00
        assert result["watchId"] == watch_id

    def test_pnl_loss_case(self, aws):
        """Watch sold for less than expenses yields loss indicator."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense
        from src.services.sale_service import create_sale
        from src.services.profit_loss_service import calculate_watch_pnl

        watch_resp = create_watch({"maker": "Omega", "model": "Speedmaster"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_expense(watch_id, {"category": "Purchase", "amountCents": 600_00})
        create_expense(watch_id, {"category": "Repair", "amountCents": 200_00})

        create_sale(watch_id, {"salePriceCents": 500_00, "saleDate": "2024-06-01"})

        pnl_resp = calculate_watch_pnl(watch_id)
        result = json.loads(pnl_resp["body"])

        assert result["pnlCents"] == -300_00  # 500 - 800
        assert result["indicator"] == "loss"
        assert result["totalExpenseCents"] == 800_00
        assert result["salePriceCents"] == 500_00

    def test_pnl_break_even_case(self, aws):
        """Watch sold for exactly the expense total yields break_even indicator."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense
        from src.services.sale_service import create_sale
        from src.services.profit_loss_service import calculate_watch_pnl

        watch_resp = create_watch({"maker": "Seiko", "model": "Presage"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_expense(watch_id, {"category": "Purchase", "amountCents": 350_00})

        create_sale(watch_id, {"salePriceCents": 350_00, "saleDate": "2024-06-01"})

        pnl_resp = calculate_watch_pnl(watch_id)
        result = json.loads(pnl_resp["body"])

        assert result["pnlCents"] == 0
        assert result["indicator"] == "break_even"
        assert result["totalExpenseCents"] == 350_00
        assert result["salePriceCents"] == 350_00

    def test_pnl_without_sale_unrealized_cost(self, aws):
        """Watch with expenses but no sale shows negative P&L (unrealized cost)."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense
        from src.services.profit_loss_service import calculate_watch_pnl

        watch_resp = create_watch({"maker": "Tudor", "model": "Black Bay"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        create_expense(watch_id, {"category": "Purchase", "amountCents": 400_00})
        create_expense(watch_id, {"category": "Polish", "amountCents": 50_00})

        pnl_resp = calculate_watch_pnl(watch_id)
        result = json.loads(pnl_resp["body"])

        assert result["pnlCents"] == -450_00
        assert result["indicator"] == "loss"
        assert result["totalExpenseCents"] == 450_00
        assert result["salePriceCents"] is None

    def test_pnl_no_expenses_no_sale(self, aws):
        """Watch with no expenses and no sale has zero P&L (break_even)."""
        from src.services.watch_service import create_watch
        from src.services.profit_loss_service import calculate_watch_pnl

        watch_resp = create_watch({"maker": "Casio", "model": "G-Shock"})
        watch_id = json.loads(watch_resp["body"])["watchId"]

        pnl_resp = calculate_watch_pnl(watch_id)
        result = json.loads(pnl_resp["body"])

        assert result["pnlCents"] == 0
        assert result["indicator"] == "break_even"
        assert result["totalExpenseCents"] == 0
        assert result["salePriceCents"] is None

    def test_pnl_nonexistent_watch_returns_404(self, aws):
        """P&L for a nonexistent watch returns 404."""
        from src.services.profit_loss_service import calculate_watch_pnl

        pnl_resp = calculate_watch_pnl("nonexistent-watch-id")
        assert pnl_resp["statusCode"] == 404
        body = json.loads(pnl_resp["body"])
        assert body["error"]["code"] == "NOT_FOUND"


class TestCalculatePortfolioSummary:
    """Tests for calculate_portfolio_summary function."""

    def test_portfolio_summary_mixed_states(self, aws):
        """Portfolio with profitable, loss, and unsold watches."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense
        from src.services.sale_service import create_sale
        from src.services.profit_loss_service import calculate_portfolio_summary

        # Watch 1: Profitable (sold for 1000, expenses 600 => +400)
        w1_resp = create_watch({"maker": "Rolex", "model": "Datejust"})
        w1_id = json.loads(w1_resp["body"])["watchId"]
        create_expense(w1_id, {"category": "Purchase", "amountCents": 600_00})
        create_sale(w1_id, {"salePriceCents": 1000_00, "saleDate": "2024-01-15"})

        # Watch 2: Loss (sold for 200, expenses 500 => -300)
        w2_resp = create_watch({"maker": "Omega", "model": "Seamaster"})
        w2_id = json.loads(w2_resp["body"])["watchId"]
        create_expense(w2_id, {"category": "Purchase", "amountCents": 500_00})
        create_sale(w2_id, {"salePriceCents": 200_00, "saleDate": "2024-02-20"})

        # Watch 3: Unsold (expenses 300 => -300)
        w3_resp = create_watch({"maker": "Tudor", "model": "Pelagos"})
        w3_id = json.loads(w3_resp["body"])["watchId"]
        create_expense(w3_id, {"category": "Purchase", "amountCents": 300_00})

        summary_resp = calculate_portfolio_summary()
        assert summary_resp["statusCode"] == 200
        summary = json.loads(summary_resp["body"])

        # Total P&L includes only sold watches: +400 + (-300) = +100
        assert summary["totalPnlCents"] == 100_00
        assert summary["profitableCount"] == 1
        assert summary["lossCount"] == 1
        assert summary["unsoldCount"] == 1
        assert len(summary["watches"]) == 3

    def test_empty_portfolio(self, aws):
        """Portfolio with no watches returns zero totals."""
        from src.services.profit_loss_service import calculate_portfolio_summary

        summary_resp = calculate_portfolio_summary()
        assert summary_resp["statusCode"] == 200
        summary = json.loads(summary_resp["body"])

        assert summary["totalPnlCents"] == 0
        assert summary["profitableCount"] == 0
        assert summary["lossCount"] == 0
        assert summary["unsoldCount"] == 0
        assert summary["watches"] == []

    def test_portfolio_all_profitable(self, aws):
        """Portfolio where all watches are profitable."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense
        from src.services.sale_service import create_sale
        from src.services.profit_loss_service import calculate_portfolio_summary

        for i in range(2):
            w_resp = create_watch({"maker": f"Maker{i}", "model": f"Model{i}"})
            w_id = json.loads(w_resp["body"])["watchId"]
            create_expense(w_id, {"category": "Purchase", "amountCents": 100_00})
            create_sale(w_id, {"salePriceCents": 500_00, "saleDate": "2024-03-01"})

        summary_resp = calculate_portfolio_summary()
        summary = json.loads(summary_resp["body"])

        assert summary["totalPnlCents"] == 800_00  # 2 * (500 - 100)
        assert summary["profitableCount"] == 2
        assert summary["lossCount"] == 0
        assert summary["unsoldCount"] == 0

    def test_portfolio_all_unsold(self, aws):
        """Portfolio where all watches are unsold."""
        from src.services.watch_service import create_watch
        from src.services.expense_service import create_expense
        from src.services.profit_loss_service import calculate_portfolio_summary

        for i in range(3):
            w_resp = create_watch({"maker": f"Maker{i}", "model": f"Model{i}"})
            w_id = json.loads(w_resp["body"])["watchId"]
            create_expense(w_id, {"category": "Purchase", "amountCents": 200_00})

        summary_resp = calculate_portfolio_summary()
        summary = json.loads(summary_resp["body"])

        assert summary["totalPnlCents"] == 0
        assert summary["profitableCount"] == 0
        assert summary["lossCount"] == 0
        assert summary["unsoldCount"] == 3
