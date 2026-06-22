import time

from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

from backend.services.task_manager import task_manager

request_count = Counter(
    "shadowhive_http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

request_latency = Histogram(
    "shadowhive_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

active_requests = Gauge(
    "shadowhive_http_requests_in_flight",
    "Currently active HTTP requests",
)

active_tasks = Gauge(
    "shadowhive_tasks_active",
    "Currently active (running) generation tasks",
)

task_queue_depth = Gauge(
    "shadowhive_task_queue_depth",
    "Number of queued or running tasks",
)


async def collect_task_metrics() -> None:
    running = sum(
        1 for t in task_manager._tasks.values() if t.status == "running"
    )
    active_tasks.set(running)
    task_queue_depth.set(len(task_manager._tasks))


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        active_requests.inc()
        start = time.time()
        method = request.method
        endpoint = request.url.path

        try:
            response = await call_next(request)
            status = str(response.status_code)
            request_count.labels(method=method, endpoint=endpoint, status=status).inc()
            return response
        except Exception:
            request_count.labels(method=method, endpoint=endpoint, status="500").inc()
            raise
        finally:
            request_latency.labels(method=method, endpoint=endpoint).observe(
                time.time() - start
            )
            active_requests.dec()
