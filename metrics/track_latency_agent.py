import time
from contextlib import contextmanager

from metrics.metrics import AGENT_EXECUTION_TIME

@contextmanager
def track_agent_latency(agent_name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        AGENT_EXECUTION_TIME.labels(agent_name=agent_name).observe(duration)