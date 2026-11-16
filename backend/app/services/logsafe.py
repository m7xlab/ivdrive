"""One line of text for the log.

Anything that came from a request, or from an upstream error body, is flattened before it is logged
so a value cannot forge extra log lines (CodeQL py/log-injection). Use it on every such value:
``logger.info("...%s", log_safe(value))``.
"""
from __future__ import annotations


def log_safe(value: object, limit: int = 500) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")[:limit]
