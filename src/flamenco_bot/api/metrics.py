"""Показатели нагрузки процесса API для окна администратора на сайте.

Только стандартная библиотека (без psutil): запросы считает middleware в
памяти процесса, CPU — по ``os.times()``, память — по ``/proc`` (Linux) или
``getrusage`` (macOS). Чего платформа не даёт (например, память на Windows),
отдаётся как ``None`` — окно показывает «—».
"""

import asyncio
import os
import platform
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Tuple


# Окно, за которое считаются запросы/задержки, и предел хранимых записей
# (защита памяти при всплеске нагрузки: при переполнении теряются старые).
REQUEST_WINDOW_SECONDS = 300
MAX_TRACKED_REQUESTS = 50_000


@dataclass(frozen=True)
class RequestStats:
    window_seconds: int
    total_since_start: int
    in_flight: int
    requests_last_minute: int
    requests_in_window: int
    errors_in_window: int
    client_errors_in_window: int
    avg_ms: Optional[float]
    p95_ms: Optional[float]
    max_ms: Optional[float]


class RequestMetrics:
    """Скользящее окно HTTP-запросов: время ответа и статус."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: Deque[Tuple[float, float, int]] = deque(
            maxlen=MAX_TRACKED_REQUESTS
        )
        self._total = 0
        self._in_flight = 0

    def started(self) -> None:
        with self._lock:
            self._in_flight += 1

    def finished(self, duration_ms: float, status_code: int) -> None:
        with self._lock:
            self._in_flight -= 1
            self._total += 1
            self._samples.append((time.monotonic(), duration_ms, status_code))

    def snapshot(self) -> RequestStats:
        now = time.monotonic()
        with self._lock:
            while self._samples and now - self._samples[0][0] > REQUEST_WINDOW_SECONDS:
                self._samples.popleft()
            samples = list(self._samples)
            total = self._total
            in_flight = self._in_flight
        durations = sorted(sample[1] for sample in samples)
        return RequestStats(
            window_seconds=REQUEST_WINDOW_SECONDS,
            total_since_start=total,
            in_flight=max(in_flight, 0),
            requests_last_minute=sum(1 for sample in samples if now - sample[0] <= 60),
            requests_in_window=len(samples),
            errors_in_window=sum(1 for sample in samples if sample[2] >= 500),
            client_errors_in_window=sum(
                1 for sample in samples if 400 <= sample[2] < 500
            ),
            avg_ms=round(sum(durations) / len(durations), 2) if durations else None,
            p95_ms=round(durations[int(0.95 * (len(durations) - 1))], 2)
            if durations
            else None,
            max_ms=round(durations[-1], 2) if durations else None,
        )


@dataclass(frozen=True)
class ProcessStats:
    pid: int
    uptime_seconds: int
    cpu_percent: Optional[float]
    cpu_count: int
    memory_rss_bytes: Optional[int]
    memory_is_peak: bool
    load_average: Optional[Tuple[float, float, float]]
    threads: int
    asyncio_tasks: int
    event_loop_lag_ms: float
    python_version: str
    platform: str


class ProcessMetrics:
    """CPU процесса считается между двумя вызовами ``snapshot`` (первый
    вызов — среднее с момента запуска)."""

    def __init__(self) -> None:
        self._started_wall = time.time()
        self._last_wall = time.monotonic()
        self._last_cpu = self._cpu_seconds()
        self._started_mono = self._last_wall
        self._first = True

    @staticmethod
    def _cpu_seconds() -> float:
        times = os.times()
        return times.user + times.system

    def _cpu_percent(self) -> Optional[float]:
        now = time.monotonic()
        cpu = self._cpu_seconds()
        elapsed = now - (self._started_mono if self._first else self._last_wall)
        used = cpu - (0.0 if self._first else self._last_cpu)
        self._first = False
        self._last_wall, self._last_cpu = now, cpu
        if elapsed <= 0:
            return None
        return round(100.0 * used / elapsed, 1)

    async def snapshot(self) -> ProcessStats:
        lag_started = time.perf_counter()
        await asyncio.sleep(0)
        lag_ms = (time.perf_counter() - lag_started) * 1000
        memory, is_peak = _memory_rss()
        return ProcessStats(
            pid=os.getpid(),
            uptime_seconds=int(time.time() - self._started_wall),
            cpu_percent=self._cpu_percent(),
            cpu_count=os.cpu_count() or 1,
            memory_rss_bytes=memory,
            memory_is_peak=is_peak,
            load_average=_load_average(),
            threads=threading.active_count(),
            asyncio_tasks=len(asyncio.all_tasks()),
            event_loop_lag_ms=round(lag_ms, 2),
            python_version=platform.python_version(),
            platform="{} {}".format(platform.system(), platform.machine()),
        )


def _memory_rss() -> Tuple[Optional[int], bool]:
    """(байты, это_пик). Linux — текущий RSS, macOS — пиковый (getrusage)."""
    try:
        with open("/proc/self/statm", encoding="ascii") as statm:
            pages = int(statm.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE"), False
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    try:
        import resource
    except ImportError:  # Windows
        return None, False
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS отдаёт байты, Linux — килобайты.
    return (peak if sys.platform == "darwin" else peak * 1024), True


def _load_average() -> Optional[Tuple[float, float, float]]:
    if not hasattr(os, "getloadavg"):
        return None
    try:
        one, five, fifteen = os.getloadavg()
    except OSError:
        return None
    return round(one, 2), round(five, 2), round(fifteen, 2)
