"""Unit tests for watch sorting logic.

Tests each sort field, ascending/descending directions,
and default sort (acquisition date descending).

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

import json

import pytest


def _create_watch(data):
    """Helper to create a watch and return the parsed body."""
    from src.services.watch_service import create_watch

    resp = create_watch(data)
    assert resp["statusCode"] == 201
    return json.loads(resp["body"])


def _list_watches(query_params=None):
    """Helper to list watches with optional query string parameters."""
    from src.services.watch_service import list_watches

    event = {}
    if query_params:
        event["queryStringParameters"] = query_params
    resp = list_watches(event)
    assert resp["statusCode"] == 200
    return json.loads(resp["body"])["watches"]


class TestSortByAcquisitionDate:
    """Requirement 7.2: Sort by acquisition date."""

    def test_sort_acquisition_date_desc(self, aws):
        _create_watch({"maker": "A", "model": "M", "acquisitionDate": "2023-01-01"})
        _create_watch({"maker": "B", "model": "M", "acquisitionDate": "2024-06-15"})
        _create_watch({"maker": "C", "model": "M", "acquisitionDate": "2022-03-10"})

        watches = _list_watches({"sortBy": "acquisitionDate", "sortDir": "desc"})
        dates = [w["acquisitionDate"] for w in watches]
        assert dates == ["2024-06-15", "2023-01-01", "2022-03-10"]

    def test_sort_acquisition_date_asc(self, aws):
        _create_watch({"maker": "A", "model": "M", "acquisitionDate": "2023-01-01"})
        _create_watch({"maker": "B", "model": "M", "acquisitionDate": "2024-06-15"})
        _create_watch({"maker": "C", "model": "M", "acquisitionDate": "2022-03-10"})

        watches = _list_watches({"sortBy": "acquisitionDate", "sortDir": "asc"})
        dates = [w["acquisitionDate"] for w in watches]
        assert dates == ["2022-03-10", "2023-01-01", "2024-06-15"]


class TestSortByMaker:
    """Requirement 7.3: Sort by maker (alphabetical)."""

    def test_sort_maker_asc(self, aws):
        _create_watch({"maker": "Omega", "model": "M"})
        _create_watch({"maker": "Rolex", "model": "M"})
        _create_watch({"maker": "Casio", "model": "M"})

        watches = _list_watches({"sortBy": "maker", "sortDir": "asc"})
        makers = [w["maker"] for w in watches]
        assert makers == ["Casio", "Omega", "Rolex"]

    def test_sort_maker_desc(self, aws):
        _create_watch({"maker": "Omega", "model": "M"})
        _create_watch({"maker": "Rolex", "model": "M"})
        _create_watch({"maker": "Casio", "model": "M"})

        watches = _list_watches({"sortBy": "maker", "sortDir": "desc"})
        makers = [w["maker"] for w in watches]
        assert makers == ["Rolex", "Omega", "Casio"]


class TestSortByYearOfProduction:
    """Requirement 7.4: Sort by year of production."""

    def test_sort_year_asc(self, aws):
        _create_watch({"maker": "A", "model": "M", "yearOfProduction": 2020})
        _create_watch({"maker": "B", "model": "M", "yearOfProduction": 2015})
        _create_watch({"maker": "C", "model": "M", "yearOfProduction": 2022})

        watches = _list_watches({"sortBy": "yearOfProduction", "sortDir": "asc"})
        years = [w["yearOfProduction"] for w in watches]
        assert years == [2015, 2020, 2022]

    def test_sort_year_desc(self, aws):
        _create_watch({"maker": "A", "model": "M", "yearOfProduction": 2020})
        _create_watch({"maker": "B", "model": "M", "yearOfProduction": 2015})
        _create_watch({"maker": "C", "model": "M", "yearOfProduction": 2022})

        watches = _list_watches({"sortBy": "yearOfProduction", "sortDir": "desc"})
        years = [w["yearOfProduction"] for w in watches]
        assert years == [2022, 2020, 2015]


class TestSortByPnl:
    """Requirement 7.1: Sort by profit/loss (computed value)."""

    def test_sort_pnl_desc(self, aws):
        """Watches sorted by P&L descending: highest profit first."""
        from src.services.expense_service import create_expense
        from src.services.sale_service import create_sale

        w1 = _create_watch({"maker": "A", "model": "M"})
        w2 = _create_watch({"maker": "B", "model": "M"})
        w3 = _create_watch({"maker": "C", "model": "M"})

        # w1: expense 5000, sale 10000 → pnl = +5000
        create_expense(w1["watchId"], {"category": "Purchase", "amountCents": 5000})
        create_sale(w1["watchId"], {"salePriceCents": 10000, "saleDate": "2024-01-01"})

        # w2: expense 8000, sale 6000 → pnl = -2000
        create_expense(w2["watchId"], {"category": "Purchase", "amountCents": 8000})
        create_sale(w2["watchId"], {"salePriceCents": 6000, "saleDate": "2024-01-01"})

        # w3: expense 3000, no sale → pnl = -3000
        create_expense(w3["watchId"], {"category": "Purchase", "amountCents": 3000})

        watches = _list_watches({"sortBy": "pnl", "sortDir": "desc"})
        makers = [w["maker"] for w in watches]
        assert makers == ["A", "B", "C"]

    def test_sort_pnl_asc(self, aws):
        """Watches sorted by P&L ascending: biggest loss first."""
        from src.services.expense_service import create_expense
        from src.services.sale_service import create_sale

        w1 = _create_watch({"maker": "A", "model": "M"})
        w2 = _create_watch({"maker": "B", "model": "M"})

        # w1: expense 5000, sale 10000 → pnl = +5000
        create_expense(w1["watchId"], {"category": "Purchase", "amountCents": 5000})
        create_sale(w1["watchId"], {"salePriceCents": 10000, "saleDate": "2024-01-01"})

        # w2: expense 8000, no sale → pnl = -8000
        create_expense(w2["watchId"], {"category": "Purchase", "amountCents": 8000})

        watches = _list_watches({"sortBy": "pnl", "sortDir": "asc"})
        makers = [w["maker"] for w in watches]
        assert makers == ["B", "A"]


class TestDefaultSort:
    """Requirement 7.5: Default sort is acquisition date descending."""

    def test_default_sort_no_params(self, aws):
        _create_watch({"maker": "A", "model": "M", "acquisitionDate": "2023-01-01"})
        _create_watch({"maker": "B", "model": "M", "acquisitionDate": "2024-06-15"})

        watches = _list_watches()
        assert watches[0]["acquisitionDate"] == "2024-06-15"
        assert watches[1]["acquisitionDate"] == "2023-01-01"

    def test_default_sort_empty_query_params(self, aws):
        _create_watch({"maker": "A", "model": "M", "acquisitionDate": "2023-01-01"})
        _create_watch({"maker": "B", "model": "M", "acquisitionDate": "2024-06-15"})

        watches = _list_watches({})
        assert watches[0]["acquisitionDate"] == "2024-06-15"
        assert watches[1]["acquisitionDate"] == "2023-01-01"
