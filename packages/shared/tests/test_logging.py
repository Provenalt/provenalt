"""Unit tests for structured logging configuration."""

from __future__ import annotations

import io
import json

from provenalt_shared.logging import configure_logging, get_logger


def test_json_format_emits_parseable_line_with_bound_fields() -> None:
    stream = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=stream)

    log = get_logger("indexer")
    log.info("backfill_progress", agent_id=42, block=1234)

    line = stream.getvalue().strip().splitlines()[-1]
    record = json.loads(line)

    assert record["event"] == "backfill_progress"
    assert record["agent_id"] == 42
    assert record["block"] == 1234
    assert record["level"] == "info"
    assert record["logger"] == "indexer"
    assert "timestamp" in record


def test_level_filtering_suppresses_below_threshold() -> None:
    stream = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=stream)

    log = get_logger("indexer")
    log.debug("should_not_appear")
    log.warning("should_appear")

    output = stream.getvalue()
    assert "should_not_appear" not in output
    assert "should_appear" in output


def test_console_format_is_human_readable_not_json() -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", fmt="console", stream=stream)

    log = get_logger("api")
    log.info("request_handled", path="/v1/agents")

    output = stream.getvalue()
    assert "request_handled" in output
    # Console output is not a JSON object line.
    assert not output.strip().startswith("{")
