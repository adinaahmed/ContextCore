import time
from contextlib import contextmanager


class LatencyProfiler:
    def __init__(self):
        self.timings: dict[str, float] = {}

    @contextmanager
    def measure(self, stage_name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.timings[stage_name] = round(elapsed * 1000, 2)

    def get_report(self) -> dict:
        total = round(sum(self.timings.values()), 2)
        return {"stages_ms": self.timings, "total_ms": total}
