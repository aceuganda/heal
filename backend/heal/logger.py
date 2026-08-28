"""Logging for Heal modules.

Deliberately independent of `danswer.utils.logger`, which carries indexing-job
context that Heal is retiring. New code should not take a dependency on code on
its way out.
"""
import logging
import os

_LOG_LEVEL = (os.environ.get("LOG_LEVEL") or "INFO").upper()


def get_logger(name: str = "heal") -> logging.Logger:
    """Return a configured logger. Safe to call repeatedly."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
    return logger
