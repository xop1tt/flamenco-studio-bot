import resource
import sys
from typing import Tuple


def get_process_resources() -> Tuple[float, float]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    max_rss = usage.ru_maxrss
    memory_mb = max_rss / (1024 * 1024 if sys.platform == "darwin" else 1024)
    cpu_seconds = usage.ru_utime + usage.ru_stime
    return memory_mb, cpu_seconds
