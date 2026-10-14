"""``configure_logging()`` guards the sinks it did not add — the guarantee, pinned.

The function's docstring promises that a host (or a test harness) which configured loguru before
importing this module keeps its sinks: ``logger.remove()`` runs on the first call only. That is the
whole reason the body is not allowed to run twice, and it is invisible to every other test — the
suite imports the module, which configures logging once, and never watches a sink disappear.
"""

from __future__ import annotations

from scrinalia.core.logger import configure_logging, logger


def test_configure_logging_keeps_a_sink_it_did_not_add() -> None:
    """A second call must not disarm a sink of somebody else's — ours, in this case."""
    received: list[str] = []
    sink = logger.add(lambda message: received.append(message.record["message"]), level="INFO")
    try:
        configure_logging()
        logger.info("still wired")
    finally:
        logger.remove(sink)

    assert received == ["still wired"], (
        "configure_logging() removed the sinks that were already installed: the second call must be "
        "a no-op (``lru_cache``), not a ``logger.remove()``."
    )
