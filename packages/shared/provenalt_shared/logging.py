"""Structured logging for Provenalt services, built on structlog.

``configure_logging`` sets a process-wide configuration; ``get_logger`` returns a bound
logger. Production uses ``fmt="json"`` (one JSON object per line, friendly to log
aggregators); local dev uses ``fmt="console"`` (colorless, human-readable).
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Literal, TextIO

import structlog

LogFormat = Literal["json", "console"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


def configure_logging(
    level: LogLevel = "INFO",
    fmt: LogFormat = "json",
    stream: TextIO | None = None,
) -> None:
    """Configure structlog process-wide.

    Args:
        level: minimum level to emit.
        fmt: ``"json"`` for machine-readable lines, ``"console"`` for human-readable.
        stream: output stream; defaults to stdout. Injectable for tests.
    """
    output = stream if stream is not None else sys.stdout
    level_num = logging.getLevelName(level)
    if not isinstance(level_num, int):  # unknown level name
        level_num = logging.INFO

    renderer: structlog.types.Processor
    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_num),
        logger_factory=structlog.PrintLoggerFactory(file=output),
        # Do not cache — tests (and services) may reconfigure the logger.
        cache_logger_on_first_use=False,
    )


def get_logger(name: str, **initial_values: Any) -> Any:
    """Return a bound logger tagged with ``logger=<name>`` plus any initial fields."""
    return structlog.get_logger().bind(logger=name, **initial_values)
