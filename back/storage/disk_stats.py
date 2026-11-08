import time


class DiskStats:
    def __init__(self):
        self.reads: int = 0
        self.writes: int = 0
        self._start: float = time.time()

    def reset(self) -> None:
        self.reads = 0
        self.writes = 0
        self._start = time.time()

    def snapshot(self) -> dict:
        return {
            "reads": self.reads,
            "writes": self.writes,
            "time_ms": round((time.time() - self._start) * 1000, 3),
        }
