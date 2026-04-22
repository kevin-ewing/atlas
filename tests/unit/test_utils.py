"""Unit tests for the shared utilities module."""

import json

import pytest

from src.utils import json_response, error_response, parse_body, get_path_parameter, CORS_HEADERS


# ---------------------------------------------------------------------------
# json_response
# ---------------------------------------------------------------------------

class TestJsonResponse:
    """Test the JSON response helper."""

    def test_returns_correct_status_code(self):
        resp = json_response(200, {"ok": True})
        assert resp["statusCode"] == 200

    def test_body_is_json_string(self):
        resp = json_response(200, {"key": "value"})
        parsed = json.loads(resp["body"])
        assert parsed == {"key": "value"}

    def test_content_type_header(self):
        resp = json_response(200, {})
        assert resp["headers"]["Content-Type"] == "application/json"

    def test_cors_headers_present(self):
        resp = json_response(200, {})
        for key, value in CORS_HEADERS.items():
            assert resp["headers"][key] == value

    def test_various_status_codes(self):
        for code in [200, 201, 400, 401, 404, 500]:
            resp = json_response(code, {})
            assert resp["statusCode"] == code


# ---------------------------------------------------------------------------
# error_response
# ---------------------------------------------------------------------------

class TestErrorResponse:
    """Test the standardised error response builder."""

    def test_error_structure(self):
        resp = error_response(400, "VALIDATION_ERROR", "Bad input")
        body = json.loads(resp["body"])
        assert "error" in body
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["message"] == "Bad input"
        assert body["error"]["details"] == {}

    def test_error_with_details(self):
        details = {"missing_fields": ["maker", "model"]}
        resp = error_response(400, "VALIDATION_ERROR", "Missing fields", details)
        body = json.loads(resp["body"])
        assert body["error"]["details"] == details

    def test_error_status_code(self):
        resp = error_response(404, "NOT_FOUND", "Watch not found")
        assert resp["statusCode"] == 404

    def test_error_has_cors_headers(self):
        resp = error_response(500, "INTERNAL_ERROR", "Oops")
        for key, value in CORS_HEADERS.items():
            assert resp["headers"][key] == value


# ---------------------------------------------------------------------------
# parse_body
# ---------------------------------------------------------------------------

class TestParseBody:
    """Test the request body parser."""

    def test_valid_json_body(self):
        event = {"body": '{"name": "Rolex"}'}
        result = parse_body(event)
        assert result == {"name": "Rolex"}

    def test_missing_body_returns_none(self):
        event = {}
        assert parse_body(event) is None

    def test_empty_string_body_returns_none(self):
        event = {"body": ""}
        assert parse_body(event) is None

    def test_none_body_returns_none(self):
        event = {"body": None}
        assert parse_body(event) is None

    def test_invalid_json_returns_none(self):
        event = {"body": "not json {{{"}
        assert parse_body(event) is None

    def test_numeric_body_returns_none_for_type_error(self):
        event = {"body": 12345}
        # json.loads(12345) raises TypeError
        assert parse_body(event) is None


# ---------------------------------------------------------------------------
# get_path_parameter
# ---------------------------------------------------------------------------

class TestGetPathParameter:
    """Test the path parameter extractor."""

    def test_extracts_existing_parameter(self):
        event = {"pathParameters": {"watchId": "abc-123"}}
        assert get_path_parameter(event, "watchId") == "abc-123"

    def test_returns_none_for_missing_parameter(self):
        event = {"pathParameters": {"watchId": "abc-123"}}
        assert get_path_parameter(event, "expenseId") is None

    def test_returns_none_when_path_parameters_missing(self):
        event = {}
        assert get_path_parameter(event, "watchId") is None

    def test_returns_none_when_path_parameters_is_none(self):
        event = {"pathParameters": None}
        assert get_path_parameter(event, "watchId") is None

    def test_extracts_multiple_parameters(self):
        event = {"pathParameters": {"watchId": "w1", "expenseId": "e1"}}
        assert get_path_parameter(event, "watchId") == "w1"
        assert get_path_parameter(event, "expenseId") == "e1"
