import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

_LOGGER_NAME = "triage"

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()[:30] or "log"),
        }
        # Merge any structured fields passed via extra={"fields": {...}}
        fields = getattr(record, "fields", {})
        if isinstance(fields, dict):
            base.update(fields)
        # Avoid duplicating the raw message (may contain PII)
        return json.dumps(base, ensure_ascii=False)

def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        h = logging.StreamHandler()
        h.setFormatter(_JsonFormatter())
        logger.addHandler(h)
        logger.propagate = False
    return logger

def log_event(event: str, **fields: Dict[str, Any]) -> None:
    """
    Log a structured, PII-safe JSON line.
    DO NOT pass raw user text; only derived flags/ids.
    """
    logger = get_logger()
    logger.info("", extra={"event": event, "fields": fields})
