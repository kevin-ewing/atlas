"""Unit tests for watch filtering logic.

Tests each individual filter, combined filters (AND logic),
empty result sets, and year range boundary conditions.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8
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


class TestFilterByMaker:
    """Requirement 6.1: Filter by maker (case-insensitive exact match)."""

    def test_filter_by_maker_exact(self, aws):
        _create_watch({"maker": "Rolex", "model": "Submariner"})
        _create_watch({"maker": "Omega", "model": "Speedmaster"})

        watches = _list_watches({"maker": "Rolex"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "Rolex"

    def test_filter_by_maker_case_insensitive(self, aws):
        _create_watch({"maker": "Rolex", "model": "Submariner"})
        _create_watch({"maker": "Omega", "model": "Speedmaster"})

        watches = _list_watches({"maker": "rolex"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "Rolex"

    def test_filter_by_maker_no_match(self, aws):
        _create_watch({"maker": "Rolex", "model": "Submariner"})

        watches = _list_watches({"maker": "Patek Philippe"})
        assert len(watches) == 0


class TestFilterByStatus:
    """Requirement 6.2: Filter by status."""

    def test_filter_by_status(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "status": "in_collection"})
        _create_watch({"maker": "Omega", "model": "Speed", "status": "for_sale"})
        _create_watch({"maker": "Tudor", "model": "BB", "status": "sold"})

        watches = _list_watches({"status": "for_sale"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "Omega"

    def test_filter_by_status_no_match(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "status": "in_collection"})

        watches = _list_watches({"status": "sold"})
        assert len(watches) == 0


class TestFilterByCondition:
    """Requirement 6.3: Filter by condition."""

    def test_filter_by_condition(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "condition": "excellent"})
        _create_watch({"maker": "Omega", "model": "Speed", "condition": "good"})

        watches = _list_watches({"condition": "excellent"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "Rolex"


class TestFilterByMovementType:
    """Requirement 6.4: Filter by movement type."""

    def test_filter_by_movement_type(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "movementType": "automatic"})
        _create_watch({"maker": "Casio", "model": "F91W", "movementType": "quartz"})

        watches = _list_watches({"movementType": "quartz"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "Casio"


class TestFilterByCaseMaterial:
    """Requirement 6.5: Filter by case material (case-insensitive)."""

    def test_filter_by_case_material(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "caseMaterial": "Stainless Steel"})
        _create_watch({"maker": "AP", "model": "RO", "caseMaterial": "Gold"})

        watches = _list_watches({"caseMaterial": "stainless steel"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "Rolex"

    def test_filter_by_case_material_no_match(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "caseMaterial": "Steel"})

        watches = _list_watches({"caseMaterial": "Titanium"})
        assert len(watches) == 0


class TestFilterByYearRange:
    """Requirement 6.7: Filter by year range (inclusive)."""

    def test_filter_by_year_min(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "yearOfProduction": 2020})
        _create_watch({"maker": "Omega", "model": "Speed", "yearOfProduction": 2015})

        watches = _list_watches({"yearMin": "2018"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "Rolex"

    def test_filter_by_year_max(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "yearOfProduction": 2020})
        _create_watch({"maker": "Omega", "model": "Speed", "yearOfProduction": 2015})

        watches = _list_watches({"yearMax": "2018"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "Omega"

    def test_filter_by_year_range_inclusive(self, aws):
        """Both min and max bounds are inclusive."""
        _create_watch({"maker": "A", "model": "M", "yearOfProduction": 2000})
        _create_watch({"maker": "B", "model": "M", "yearOfProduction": 2005})
        _create_watch({"maker": "C", "model": "M", "yearOfProduction": 2010})

        watches = _list_watches({"yearMin": "2000", "yearMax": "2005"})
        makers = {w["maker"] for w in watches}
        assert makers == {"A", "B"}

    def test_filter_by_year_exact_boundary(self, aws):
        """A watch at exactly the boundary should be included."""
        _create_watch({"maker": "A", "model": "M", "yearOfProduction": 2000})

        watches = _list_watches({"yearMin": "2000", "yearMax": "2000"})
        assert len(watches) == 1

    def test_filter_by_year_excludes_watches_without_year(self, aws):
        """Watches without yearOfProduction are excluded by year filters."""
        _create_watch({"maker": "A", "model": "M"})  # no yearOfProduction
        _create_watch({"maker": "B", "model": "M", "yearOfProduction": 2020})

        watches = _list_watches({"yearMin": "2000"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "B"


class TestFilterByFeatures:
    """Requirement 6.8: Filter by features (subset check)."""

    def test_filter_by_single_feature(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "features": ["date", "diving bezel"]})
        _create_watch({"maker": "Omega", "model": "Speed", "features": ["chronograph", "date"]})

        watches = _list_watches({"features": "diving bezel"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "Rolex"

    def test_filter_by_multiple_features(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "features": ["date", "diving bezel"]})
        _create_watch({"maker": "Omega", "model": "Speed", "features": ["chronograph", "date"]})

        watches = _list_watches({"features": "chronograph,date"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "Omega"

    def test_filter_by_features_no_match(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "features": ["date"]})

        watches = _list_watches({"features": "tourbillon"})
        assert len(watches) == 0

    def test_filter_by_features_excludes_watches_without_features(self, aws):
        _create_watch({"maker": "A", "model": "M"})  # no features
        _create_watch({"maker": "B", "model": "M", "features": ["date"]})

        watches = _list_watches({"features": "date"})
        assert len(watches) == 1
        assert watches[0]["maker"] == "B"


class TestCombinedFilters:
    """Requirement 6.6: Multiple filters combined with logical AND."""

    def test_combined_maker_and_status(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "status": "in_collection"})
        _create_watch({"maker": "Rolex", "model": "Daytona", "status": "for_sale"})
        _create_watch({"maker": "Omega", "model": "Speed", "status": "in_collection"})

        watches = _list_watches({"maker": "Rolex", "status": "for_sale"})
        assert len(watches) == 1
        assert watches[0]["model"] == "Daytona"

    def test_combined_filters_empty_result(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub", "condition": "excellent"})
        _create_watch({"maker": "Omega", "model": "Speed", "condition": "good"})

        watches = _list_watches({"maker": "Rolex", "condition": "good"})
        assert len(watches) == 0

    def test_combined_multiple_filters(self, aws):
        _create_watch({
            "maker": "Rolex", "model": "Sub",
            "status": "in_collection", "movementType": "automatic",
            "yearOfProduction": 2020,
        })
        _create_watch({
            "maker": "Rolex", "model": "Daytona",
            "status": "for_sale", "movementType": "automatic",
            "yearOfProduction": 2018,
        })
        _create_watch({
            "maker": "Casio", "model": "F91W",
            "status": "in_collection", "movementType": "quartz",
            "yearOfProduction": 2022,
        })

        watches = _list_watches({
            "maker": "Rolex",
            "movementType": "automatic",
            "yearMin": "2019",
        })
        assert len(watches) == 1
        assert watches[0]["model"] == "Sub"


class TestNoFilters:
    """When no filters are applied, all watches are returned."""

    def test_no_filters_returns_all(self, aws):
        _create_watch({"maker": "Rolex", "model": "Sub"})
        _create_watch({"maker": "Omega", "model": "Speed"})

        watches = _list_watches()
        assert len(watches) == 2
