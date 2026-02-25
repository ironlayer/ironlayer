"""Tests for the JSON log formatter (I1)."""

from __future__ import annotations

import json
import logging

import pytest

from api.middleware.json_formatter import JSONFormatter


@pytest.fixture
def formatter() -> JSONFormatter:
    return JSONFormatter()


class TestJSONFormatter:
    """Verify structured JSON output from the formatter."""

    def test_basic_format(self, formatter: JSONFormatter) -> None:
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "test message"
        assert "timestamp" in data

    def test_single_line_output(self, formatter: JSONFormatter) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="warn msg",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "\n" not in output

    def test_request_context_included(self, formatter: JSONFormatter) -> None:
        record = logging.LogRecord(
            name="api.access",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="request completed",
            args=(),
            exc_info=None,
        )
        record.request = {  # type: ignore[attr-defined]
            "method": "GET",
            "path": "/api/v1/health",
            "status_code": 200,
            "duration_ms": 1.5,
            "tenant_id": "acme",
            "identity_kind": "user",
        }
        output = formatter.format(record)
        data = json.loads(output)

        assert "request" in data
        assert data["request"]["method"] == "GET"
        assert data["request"]["tenant_id"] == "acme"
        assert data["request"]["identity_kind"] == "user"

    def test_no_request_context_omitted(self, formatter: JSONFormatter) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="plain msg",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "request" not in data

    def test_exception_info_included(self, formatter: JSONFormatter) -> None:
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="error occurred",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert "exc_info" in data
        assert "ValueError: test error" in data["exc_info"]
        assert "Traceback" in data["exc_info"]

    def test_timestamp_is_utc_iso_format(self, formatter: JSONFormatter) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="ts test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        ts = data["timestamp"]
        # Should contain UTC offset
        assert "+00:00" in ts

    def test_error_level_formatted(self, formatter: JSONFormatter) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="error",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "ERROR"
