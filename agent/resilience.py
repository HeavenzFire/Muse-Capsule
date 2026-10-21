"""Small stdlib-only resilience primitives for Muse agent runtime."""
from __future__ import annotations
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Type

class CircuitOpenError(RuntimeError):
    """Raised while a dependency circuit is open and not probe-eligible."""

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.25
    max_delay: float = 2.0
    jitter: float = 0.1

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay < 0 or self.max_delay < 0 or self.jitter < 0:
            raise ValueError("retry delays and jitter must be non-negative")

class CircuitBreaker:
    """Thread-safe closed/open/half-open breaker with one recovery probe."""
    def __init__(self, failure_threshold=3, recovery_timeout=15.0, clock=time.monotonic):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout < 0:
            raise ValueError("recovery_timeout must be non-negative")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at = None
        self._probe_in_flight = False

    @property
    def state(self):
        with self._lock:
            if self._opened_at is None:
                return "closed"
            return "half_open" if self._clock() - self._opened_at >= self.recovery_timeout else "open"

    def before_call(self):
        with self._lock:
            if self._opened_at is None:
                return
            if self._clock() - self._opened_at < self.recovery_timeout:
                raise CircuitOpenError("dependency circuit open; cooldown has not elapsed")
            if self._probe_in_flight:
                raise CircuitOpenError("dependency circuit half-open; recovery probe already in flight")
            self._probe_in_flight = True

    def record_success(self):
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._probe_in_flight = False

    def record_failure(self):
        with self._lock:
            self._probe_in_flight = False
            self._failures += 1
            if self._opened_at is not None or self._failures >= self.failure_threshold:
                self._opened_at = self._clock()

    def snapshot(self):
        with self._lock:
            if self._opened_at is None:
                state = "closed"
            else:
                state = "half_open" if self._clock() - self._opened_at >= self.recovery_timeout else "open"
            return {"state": state, "consecutive_failures": self._failures, "recovery_timeout": self.recovery_timeout, "probe_in_flight": self._probe_in_flight}

def call_with_retry(fn: Callable[[], object], policy: RetryPolicy = RetryPolicy(),
                    breaker: Optional[CircuitBreaker] = None,
                    retry_on: Iterable[Type[BaseException]] = (TimeoutError, ConnectionError),
                    sleep: Callable[[float], None] = time.sleep,
                    random_value: Callable[[], float] = random.random):
    """Bounded exponential retry; use only for safe dependency calls."""
    if breaker is not None:
        breaker.before_call()
    retry_types = tuple(retry_on)
    for attempt in range(1, policy.max_attempts + 1):
        try:
            result = fn()
        except retry_types:
            if attempt >= policy.max_attempts:
                if breaker is not None:
                    breaker.record_failure()
                raise
            delay = min(policy.max_delay, policy.base_delay * (2 ** (attempt - 1)))
            if policy.jitter:
                delay += delay * policy.jitter * random_value()
            sleep(delay)
        except BaseException:
            if breaker is not None:
                breaker.record_failure()
            raise
        else:
            if breaker is not None:
                breaker.record_success()
            return result
    raise AssertionError("unreachable retry loop")
