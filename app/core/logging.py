"""
Structured Logger
==================
Thin wrapper around Python's stdlib logging, providing structured log calls
that are safe for production (Render, Docker, etc.) and easy to grep.

Usage:
    from app.core.logging import get_logger
    log = get_logger(__name__)
    log.info("payment_captured", user_id="abc", amount=49)
"""
import logging
import json
import sys


class StructuredFormatter(logging.Formatter):
    """Emits JSON-like lines: level=INFO msg=payment_captured user_id=abc"""

    def format(self, record: logging.LogRecord) -> str:
        base = f"level={record.levelname} msg={record.getMessage()}"
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in logging.LogRecord.__dict__
            and k not in ("message", "msg", "args", "exc_info", "exc_text",
                          "stack_info", "created", "msecs", "relativeCreated",
                          "thread", "threadName", "processName", "process",
                          "filename", "module", "funcName", "lineno", "name",
                          "pathname", "levelname", "levelno", "taskName")
        }
        if extras:
            extra_str = " ".join(f"{k}={v}" for k, v in extras.items())
            return f"{base} {extra_str}"
        return base


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
