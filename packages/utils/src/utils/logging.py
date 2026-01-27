"""Structured logging with Airflow integration.

In production (Airflow):
- Routes through Python's logging module for proper level integration
- Airflow captures and displays with correct log levels
- Key=value format for readability, no duplicate timestamps

In development (localhost):
- Uses structlog's colorized console output
- Easier to read during local development
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from structlog.typing import FilteringBoundLogger, WrappedLogger


def _key_value_renderer(
    logger: WrappedLogger,
    method_name: str,
    event_dict: dict[str, Any],
) -> str:
    """Render log event as key=value format for Airflow.

    Output format: event key=value key2=value2
    No timestamp or level prefix - Airflow adds its own.
    """
    event = event_dict.pop("event", "")
    # Remove fields that Airflow handles or that clutter output
    event_dict.pop("level", None)
    event_dict.pop("service", None)

    # Format remaining keys as key=value
    pairs = " ".join(f"{k}={v}" for k, v in sorted(event_dict.items()))

    if pairs:
        return f"{event} {pairs}"
    return event


def _get_airflow_processors() -> list[structlog.types.Processor]:
    """Get processors for Airflow/production environment.

    Routes through stdlib logging for proper Airflow integration.
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]


def _get_dev_processors() -> list[structlog.types.Processor]:
    """Get processors for development environment.

    Uses colorized console output for local debugging.
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(colors=True),
    ]


def _configure_stdlib_logging(log_level: int) -> None:
    """Configure Python's standard logging for Airflow integration."""
    # Create formatter that renders as key=value
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=_key_value_renderer,
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.format_exc_info,
        ],
    )

    # Get root logger and set level
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Configure handler if not already present
    # Airflow's task handler will capture this
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)


@lru_cache(maxsize=1)
def _configure_logging(*, is_production: bool, is_silent: bool) -> None:
    """Configure structlog for the application.

    Args:
        is_production: Use Airflow-compatible logging (routes through stdlib).
        is_silent: Suppress all logging output.
    """
    min_level = logging.CRITICAL if is_silent else logging.DEBUG

    if is_production:
        # Production: Route through Python logging for Airflow capture
        _configure_stdlib_logging(min_level)

        structlog.configure(
            processors=_get_airflow_processors(),
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Development: Direct console output with colors
        structlog.configure(
            processors=_get_dev_processors(),
            wrapper_class=structlog.make_filtering_bound_logger(min_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )


def get_logger(name: str) -> FilteringBoundLogger:
    """Get a logger for a specific module/service.

    In production (Airflow):
        Logs are captured by Airflow's task logging system.

    In development:
        Logs are printed to console with colors.

    Args:
        name: Logger name (typically module name like "db.client").

    Returns:
        Configured structlog logger with service context.

    Example:
        >>> log = get_logger("db.client")
        >>> log.info("connected", host="localhost", port=5432)
    """
    from utils.settings import get_settings

    settings = get_settings()
    _configure_logging(is_production=settings.is_production, is_silent=settings.is_silent)

    return structlog.get_logger(service=name)  # type: ignore[no-any-return]
