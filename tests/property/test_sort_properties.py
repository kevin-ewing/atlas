"""Property-based tests for watch sorting logic.

Feature: watch-flip-tracker, Property 13: Sort ordering correctness

Validates: Requirements 7.1, 7.2, 7.3, 7.4
"""

import json

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from tests.conftest import (
    watch_attributes,
    sort_params,
    SORT_FIELDS,
    SORT_DIRECTIONS,
)


def _get_sort_key(watch: dict, field: str) -> object:
    """Extract the sort key value from a watch dict for comparison."""
    if field == "acquisitionDate":
        return watch.get("acquisitionDate") or ""
    elif field == "maker":
        return (watch.get("maker") or "").lower()
    elif field == "yearOfProduction":
        return watch.get("yearOfProduction") or 0
    # pnl is handled separately since it requires computation
    return None


# Feature: watch-flip-tracker, Property 13: Sort ordering correctness
class TestSortOrderingCorrectness:
    """Property 13: Sort ordering correctness.

    **Validates: Requirements 7.1-7.4**

    For any set of watches and any supported sort field with a specified
    direction, the returned list should be ordered such that each
    consecutive pair of elements respects the sort direction.
    """

    @given(
        watch_list=st.lists(watch_attributes(), min_size=2, max_size=5),
        sort=sort_params(),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_sort_ordering_correctness(self, watch_list, sort, aws):
        from src.services.watch_service import create_watch, list_watches

        field = sort["field"]
        direction = sort["direction"]

        # Skip pnl for property test — it requires expense/sale setup
        # and is covered by unit tests with controlled data.
        assume(field != "pnl")

        # Create watches
        for attrs in watch_list:
            resp = create_watch(attrs)
            assert resp["statusCode"] == 201

        # List with sort params
        event = {
            "queryStringParameters": {
                "sortBy": field,
                "sortDir": direction,
            }
        }
        resp = list_watches(event)
        assert resp["statusCode"] == 200
        result_watches = json.loads(resp["body"])["watches"]

        # Verify ordering: each consecutive pair respects the sort direction
        for i in range(len(result_watches) - 1):
            key_a = _get_sort_key(result_watches[i], field)
            key_b = _get_sort_key(result_watches[i + 1], field)

            if direction == "asc":
                assert key_a <= key_b, (
                    f"Sort violation at index {i}: {key_a!r} > {key_b!r} "
                    f"(field={field}, dir={direction})"
                )
            else:
                assert key_a >= key_b, (
                    f"Sort violation at index {i}: {key_a!r} < {key_b!r} "
                    f"(field={field}, dir={direction})"
                )
