"""
Structured logging, Azure App Insights telemetry, and metrics.
"""
import logging
import json
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Optional

from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer

from backend.core.config import settings


# ── Structured JSON formatter ────────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, "agent_id"):
            log_record["agent_id"] = record.agent_id
        if hasattr(record, "session_id"):
            log_record["session_id"] = record.session_id
        if hasattr(record, "correlation_id"):
            log_record["correlation_id"] = record.correlation_id
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Azure App Insights handler (if key provided)
        if settings.AZURE_APP_INSIGHTS_KEY and settings.ENABLE_TELEMETRY:
            azure_handler = AzureLogHandler(
                connection_string=f"InstrumentationKey={settings.AZURE_APP_INSIGHTS_KEY}"
            )
            azure_handler.setFormatter(JSONFormatter())
            logger.addHandler(azure_handler)

    return logger


# ── Tracer (distributed tracing) ────────────────────────────────────────────
def get_tracer() -> Optional[Tracer]:
    if settings.AZURE_APP_INSIGHTS_KEY and settings.ENABLE_TELEMETRY:
        return Tracer(
            exporter=AzureExporter(
                connection_string=f"InstrumentationKey={settings.AZURE_APP_INSIGHTS_KEY}"
            ),
            sampler=ProbabilitySampler(1.0),
        )
    return None


# ── Decorator: log and time agent calls ─────────────────────────────────────
def log_agent_call(agent_name: str):
    def decorator(func: Callable) -> Callable:
        logger = get_logger(f"agent.{agent_name}")

        @wraps(func)
        async def wrapper(*args, **kwargs):
            correlation_id = str(uuid.uuid4())
            start = time.perf_counter()
            extra = {"agent_id": agent_name, "correlation_id": correlation_id}

            logger.info(
                f"[{agent_name}] Starting call: {func.__name__}",
                extra=extra,
            )
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                logger.info(
                    f"[{agent_name}] Completed in {elapsed:.1f}ms",
                    extra={**extra, "duration_ms": elapsed},
                )
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                logger.error(
                    f"[{agent_name}] Failed after {elapsed:.1f}ms: {exc}",
                    exc_info=True,
                    extra={**extra, "duration_ms": elapsed},
                )
                raise

        return wrapper
    return decorator


# ── Simple in-process metrics store (replace with Prometheus in prod) ────────
class MetricsCollector:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data: dict[str, Any] = {
                "agent_calls": {},
                "errors": {},
                "latencies": {},
                "hitl_events": 0,
            }
        return cls._instance

    def record_call(self, agent: str, latency_ms: float, success: bool):
        self._data["agent_calls"].setdefault(agent, 0)
        self._data["agent_calls"][agent] += 1
        self._data["latencies"].setdefault(agent, [])
        self._data["latencies"][agent].append(latency_ms)
        if not success:
            self._data["errors"].setdefault(agent, 0)
            self._data["errors"][agent] += 1

    def record_hitl(self):
        self._data["hitl_events"] += 1

    def snapshot(self) -> dict:
        snap = dict(self._data)
        snap["avg_latencies"] = {
            agent: round(sum(v) / len(v), 1)
            for agent, v in self._data["latencies"].items()
            if v
        }
        return snap


metrics = MetricsCollector()
