from time import perf_counter
from typing import Optional

from prometheus_client import Counter, Histogram

# ---- METRICS (names are Prometheus-safe; units are in names) ----

TRIAGE_REQUESTS = Counter(
    "triage_requests_total",
    "Total /api/chat requests by final status",
    labelnames=("status",),
)

SAFETY_CHECK_OUTCOMES = Counter(
    "safety_check_outcomes_total",
    "Safety self-check outcomes",
    labelnames=("action",),
)

REQUEST_LATENCY_MS = Histogram(
    "request_latency_ms",
    "End-to-end latency of /api/chat in milliseconds",
    # Buckets tuned for sub-second API responses
    buckets=(25, 50, 100, 200, 400, 800, 1600, 3200, 6400)
)

ERRORS_TOTAL = Counter(
    "errors_total",
    "Count of errors by type",
    labelnames=("type",),
)

# ---- HELPERS ----

def timer_start() -> float:
    return perf_counter()

def timer_observe_ms(start: float) -> float:
    elapsed_ms = (perf_counter() - start) * 1000.0
    REQUEST_LATENCY_MS.observe(elapsed_ms)
    return elapsed_ms

def record_status(status: str) -> None:
    TRIAGE_REQUESTS.labels(status=status).inc()

def record_safety(action: Optional[str]) -> None:
    if action:
        SAFETY_CHECK_OUTCOMES.labels(action=action).inc()

def record_error(err_type: str) -> None:
    ERRORS_TOTAL.labels(type=err_type).inc()
