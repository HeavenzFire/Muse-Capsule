import unittest
from resilience import CircuitBreaker, CircuitOpenError, RetryPolicy, call_with_retry

class FakeClock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds

class ResilienceTests(unittest.TestCase):
    def test_retries_transient_failure_then_succeeds(self):
        calls, sleeps = [], []
        def work():
            calls.append(1)
            if len(calls) < 3: raise TimeoutError("temporary")
            return "ok"
        self.assertEqual(call_with_retry(work, RetryPolicy(3, 0.1, 1.0, 0), sleep=sleeps.append), "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [0.1, 0.2])

    def test_retries_are_bounded(self):
        calls = []
        def work(): calls.append(1); raise ConnectionError("offline")
        with self.assertRaises(ConnectionError):
            call_with_retry(work, RetryPolicy(2, 0, 0, 0), sleep=lambda _: None)
        self.assertEqual(len(calls), 2)

    def test_non_transient_error_is_not_retried(self):
        calls = []
        def work(): calls.append(1); raise ValueError("invalid")
        with self.assertRaises(ValueError):
            call_with_retry(work, RetryPolicy(4, 0, 0, 0), sleep=lambda _: None)
        self.assertEqual(len(calls), 1)

    def test_breaker_opens_then_recovers(self):
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=5, clock=clock)
        breaker.record_failure(); breaker.record_failure()
        self.assertEqual(breaker.state, "open")
        with self.assertRaises(CircuitOpenError): call_with_retry(lambda: "no", breaker=breaker)
        clock.advance(5)
        self.assertEqual(breaker.state, "half_open")
        self.assertEqual(call_with_retry(lambda: "recovered", breaker=breaker), "recovered")
        self.assertEqual(breaker.state, "closed")
        self.assertEqual(breaker.snapshot()["consecutive_failures"], 0)

    def test_breaker_counts_exhausted_call_once(self):
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=5)
        def work(): raise TimeoutError("down")
        with self.assertRaises(TimeoutError):
            call_with_retry(work, RetryPolicy(2, 0, 0, 0), breaker=breaker, sleep=lambda _: None)
        self.assertEqual(breaker.snapshot()["consecutive_failures"], 1)
        self.assertEqual(breaker.state, "open")

if __name__ == "__main__": unittest.main()
