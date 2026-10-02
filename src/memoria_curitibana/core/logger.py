"""Loguru sinks shared by the API, the workers and the dashboard."""

import logging
import sys
from pathlib import Path

from loguru import logger

from memoria_curitibana.core.config import settings

CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

_CONFIGURED = False


class InterceptHandler(logging.Handler):
    """
    Forwards stdlib records (uvicorn, Litestar, Alembic) to the loguru sinks.

    The depth is walked through the *caller's* frames until the logging
    infrastructure is left behind, which is what loguru's documentation
    prescribes. Note that the loop tests ``record.pathname`` (the origin of the
    log call), not ``logging.__file__``: the latter compares against the same file
    the loop already stands on and therefore never advances, which silently
    corrupts the reported ``name``/``line`` of every intercepted record.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == record.pathname:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def intercept_stdlib_logging() -> None:
    """
    Routes every stdlib record to the loguru sinks.

    The intercept handler is attached to the root logger, which sits outside the
    chain uvicorn builds for ``uvicorn.error``/``uvicorn.access``; those loggers
    keep their own console handler so the familiar startup output does not
    disappear, and their records still reach the sinks through propagation.
    """
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)


def configure_logging() -> None:
    """
    Installs the loguru sinks. Safe to call more than once.

    ``logger.remove()`` only runs on the first call: importing this module after
    some other component has already configured loguru (for example a host
    application or a test harness) must not tear those sinks down.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()

    # Sink 1: terminal, level from the environment.
    logger.add(sys.stdout, format=CONSOLE_FORMAT, level=settings.LOG_LEVEL)

    # Sink 2: critical errors, kept for post-mortem analysis.
    logger.add(
        log_dir / "critical.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message} | {exception}",
        rotation="10 MB",
        retention="30 days",
        backtrace=False,
        diagnose=False,
    )

    # Sink 3: structured stream, bounded by retention so it cannot fill the disk.
    logger.add(
        log_dir / "ui_stream.jsonl",
        level=settings.LOG_LEVEL,
        serialize=True,
        rotation="50 MB",
        retention="7 days",
    )

    intercept_stdlib_logging()
    _CONFIGURED = True


configure_logging()

__all__ = ["InterceptHandler", "configure_logging", "intercept_stdlib_logging", "logger"]
