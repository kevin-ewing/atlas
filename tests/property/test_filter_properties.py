"""Property-based tests for watch filtering logic.

Feature: watch-flip-tracker, Property 12: Multi-filter AND correctness

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8
"""

import json

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from tests.conftest import (
    watch_attributes,
    filter_criteria,
    VALID_STATUSES,
    VALID_CONDITIONS,
    VALID_MOVEMENT_TYPES,
    VALID_FEATURES,
)


def _matches_filter(watch: dict, criteria: dict) -> bool:
    """Oracle: check if a single watch matches all filter criteria."""
    if "maker" in criteria:
        if watch.get("maker", "").lower() != criteria["maker"].lower():
            return False
    if "status" in criteria:
        if watch.get("status") != criteria["status"]:
            return False
    if "condition" in criteria:
        if watch.get("condition") != criteria["condition"]:
            return False
    if "movementType" in criteria:
        if watch.get("movementType") != criteria["movementType"]:
            return False
    if "caseMaterial" in criteria:
        if watch.get("caseMaterial", "").lower() != criteria["caseMaterial"].lower():
            return False
    if "yearMin" in criteria:
        yop = watch.get("yearOfProduction")
        if yop is None or yop < criteria["yearMin"]:
            return False
    if "yearMax" in criteria:
        yop = watch.get("yearOfProduction")
        if yop is None or yop > criteria["yearMax"]:
            return False
    if "features" in criteria:
        watch_features = set(watch.get("features") or [])
        if not set(criteria["features"]).issubset(watch_features):
            return False
    return True


def _build_query_params(criteria: dict) -> dict:
    """Convert filter_criteria dict to query string parameters."""
    params = {}
    if "maker" in criteria:
        params["maker"] = criteria["maker"]
    if "status" in criteria:
        params["status"] = criteria["status"]
    if "condition" in criteria:
        params["condition"] = criteria["condition"]
    if "movementType" in criteria:
        params["movementType"] = criteria["movementType"]
    if "caseMaterial" in criteria:
        params["caseMaterial"] = criteria["caseMaterial"]
    if "yearMin" in criteria:
        params["yearMin"] = str(criteria["yearMin"])
    if "yearMax" in criteria:
        params["yearMax"] = str(criteria["yearMax"])
    if "features" in criteria:
        params["features"] = ",".join(criteria["features"])
    return params


# Feature: watch-flip-tracker, Property 12: Multi-filter AND correctness
class TestMultiFilterAndCorrectness:
    """Property 12: Multi-filter AND correctness.

    **Validates: Requirements 6.1-6.8**

    For any set of watches and any combination of filter criteria,
    the filtered result should contain exactly those watches that
    satisfy all specified criteria simultaneously (logical AND),
    and no watches that fail any criterion.
    """

    @given(
        watch_list=st.lists(watch_attributes(), min_size=1, max_size=5),
        criteria=filter_criteria(),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_multi_filter_and_correctness(self, watch_list, criteria, aws):
        from src.services.watch_service import create_watch, list_watches

        # Create watches
        created_ids = []
        for attrs in watch_list:
            resp = create_watch(attrs)
            assert resp["statusCode"] == 201
            body = json.loads(resp["body"])
            created_ids.append(body["watchId"])

        # Get ALL watches currently in the database (data accumulates)
        all_resp = list_watches({})
        assert all_resp["statusCode"] == 200
        all_watches = json.loads(all_resp["body"])["watches"]

        # Build query params from criteria
        query_params = _build_query_params(criteria)

        # Call list_watches with filters
        event = {"queryStringParameters": query_params} if query_params else {}
        resp = list_watches(event)
        assert resp["statusCode"] == 200
        result_watches = json.loads(resp["body"])["watches"]
        result_ids = {w["watchId"] for w in result_watches}

        # Compute expected result using oracle against ALL watches
        expected_ids = {
            w["watchId"] for w in all_watches
            if _matches_filter(w, criteria)
        }

        # Every returned watch must match all criteria, and no matching
        # watch should be missing
        assert result_ids == expected_ids
