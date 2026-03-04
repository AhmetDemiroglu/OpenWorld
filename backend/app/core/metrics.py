"""
Prometheus Metrics for Monitoring
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

# In-memory metrics storage
_metrics: Dict[str, Any] = {
    "counters": {},
    "gauges": {},
    "histograms": {}
}


class MetricsCollector:
    """Simple metrics collector compatible with Prometheus format."""
    
    @staticmethod
    def counter(name: str, description: str, labels: Optional[list] = None) -> "Counter":
        if name not in _metrics["counters"]:
            _metrics["counters"][name] = Counter(name, description, labels or [])
        return _metrics["counters"][name]
    
    @staticmethod
    def gauge(name: str, description: str, labels: Optional[list] = None) -> "Gauge":
        if name not in _metrics["gauges"]:
            _metrics["gauges"][name] = Gauge(name, description, labels or [])
        return _metrics["gauges"][name]
    
    @staticmethod
    def histogram(name: str, description: str, labels: Optional[list] = None, buckets: Optional[list] = None) -> "Histogram":
        if name not in _metrics["histograms"]:
            _metrics["histograms"][name] = Histogram(name, description, labels or [], buckets)
        return _metrics["histograms"][name]


class Counter:
    def __init__(self, name: str, description: str, labels: list):
        self.name = name
        self.description = description
        self.labels = labels
        self._values: Dict[str, int] = {}
    
    def inc(self, value: int = 1, **label_values) -> None:
        key = self._make_key(label_values)
        self._values[key] = self._values.get(key, 0) + value
    
    def _make_key(self, label_values: dict) -> str:
        if not self.labels:
            return "_total"
        parts = [f"{k}={label_values.get(k, '')}" for k in self.labels]
        return "{" + ",".join(parts) + "}"
    
    def get_value(self, **label_values) -> int:
        key = self._make_key(label_values)
        return self._values.get(key, 0)
    
    def to_prometheus(self) -> str:
        lines = [f"# HELP {self.name} {self.description}", f"# TYPE {self.name} counter"]
        for key, value in self._values.items():
            if key == "_total":
                lines.append(f"{self.name}_total {value}")
            else:
                lines.append(f"{self.name}{key} {value}")
        return "\n".join(lines)


class Gauge:
    def __init__(self, name: str, description: str, labels: list):
        self.name = name
        self.description = description
        self.labels = labels
        self._values: Dict[str, float] = {}
    
    def set(self, value: float, **label_values) -> None:
        key = self._make_key(label_values)
        self._values[key] = value
    
    def inc(self, value: float = 1, **label_values) -> None:
        key = self._make_key(label_values)
        self._values[key] = self._values.get(key, 0) + value
    
    def dec(self, value: float = 1, **label_values) -> None:
        key = self._make_key(label_values)
        self._values[key] = self._values.get(key, 0) - value
    
    def _make_key(self, label_values: dict) -> str:
        if not self.labels:
            return ""
        parts = [f"{k}={label_values.get(k, '')}" for k in self.labels]
        return "{" + ",".join(parts) + "}"
    
    def to_prometheus(self) -> str:
        lines = [f"# HELP {self.name} {self.description}", f"# TYPE {self.name} gauge"]
        for key, value in self._values.items():
            if key:
                lines.append(f"{self.name}{key} {value}")
            else:
                lines.append(f"{self.name} {value}")
        return "\n".join(lines)


class Histogram:
    def __init__(self, name: str, description: str, labels: list, buckets: Optional[list] = None):
        self.name = name
        self.description = description
        self.labels = labels
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
        self._observations: Dict[str, list] = {}
    
    def observe(self, value: float, **label_values) -> None:
        key = self._make_key(label_values)
        if key not in self._observations:
            self._observations[key] = []
        self._observations[key].append(value)
    
    def _make_key(self, label_values: dict) -> str:
        if not self.labels:
            return ""
        parts = [f"{k}={label_values.get(k, '')}" for k in self.labels]
        return "{" + ",".join(parts) + "}"
    
    def to_prometheus(self) -> str:
        lines = [f"# HELP {self.name} {self.description}", f"# TYPE {self.name} histogram"]
        for key, values in self._observations.items():
            for bucket in self.buckets:
                count = sum(1 for v in values if v <= bucket)
                suffix = f"_bucket{key},le={bucket}" if key else f"_bucket{{le={bucket}}}"
                lines.append(f"{self.name}{suffix} {count}")
            lines.append(f"{self.name}_sum{key} {sum(values)}")
            lines.append(f"{self.name}_count{key} {len(values)}")
        return "\n".join(lines)


# Predefined metrics
tool_execution_total = MetricsCollector.counter(
    "openworld_tool_execution_total",
    "Total number of tool executions",
    ["tool_name", "status"]
)

tool_execution_duration = MetricsCollector.histogram(
    "openworld_tool_execution_duration_seconds",
    "Tool execution duration in seconds",
    ["tool_name"]
)

llm_requests_total = MetricsCollector.counter(
    "openworld_llm_requests_total",
    "Total number of LLM requests",
    ["model", "status"]
)

llm_tokens_total = MetricsCollector.counter(
    "openworld_llm_tokens_total",
    "Total number of LLM tokens used",
    ["model", "type"]
)

llm_request_duration = MetricsCollector.histogram(
    "openworld_llm_request_duration_seconds",
    "LLM request duration in seconds",
    ["model"]
)

chat_sessions_active = MetricsCollector.gauge(
    "openworld_chat_sessions_active",
    "Number of active chat sessions"
)

messages_total = MetricsCollector.counter(
    "openworld_messages_total",
    "Total number of messages",
    ["role", "source"]
)

errors_total = MetricsCollector.counter(
    "openworld_errors_total",
    "Total number of errors",
    ["type"]
)

uptime_seconds = MetricsCollector.gauge(
    "openworld_uptime_seconds",
    "Application uptime in seconds"
)


@contextmanager
def timer(metric: Histogram, **labels) -> Generator[None, None, None]:
    """Context manager for timing operations."""
    start = time.time()
    try:
        yield
        status = "success"
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.time() - start
        metric.observe(duration, **labels)


def get_all_metrics() -> str:
    """Export all metrics in Prometheus format."""
    sections = []
    
    for metric_type in ["counters", "gauges", "histograms"]:
        for metric in _metrics[metric_type].values():
            sections.append(metric.to_prometheus())
    
    return "\n\n".join(sections)
