import os
import sys

from loguru import logger

os.makedirs("logs", exist_ok=True)

logger.remove()

# Sink 1: Terminal
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:sc}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",  # Mostra INFO, WARNING, ERROR, CRITICAL. (Esconde DEBUG)
)

# Sink 2: Erros Críticos
logger.add(
    "logs/criticos.log",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message} | {exception}",
    rotation="10 MB",
    retention="30 days",
)

# Sink 3: JSON
logger.add(
    "logs/ui_stream.jsonl",
    level="DEBUG",
    serialize=True,
    rotation="50 MB",
)

__all__ = ["logger"]
