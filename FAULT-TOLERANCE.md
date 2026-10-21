# Additive fault tolerance

This is an additive resilience layer. Existing tools and tool contracts remain available.

## Behavior
- Bounded exponential backoff for transient model transport/time-out failures.
- Circuit breaker with closed/open/half-open states and one recovery probe.
- Automatic recovery after cooldown; successful probe resets the breaker.
- Standard-library-only implementation; no new runtime dependency.

## Safe retry boundary
Shell execution, filesystem writes, and memory append are not blindly replayed. If a side effect times out after it may have happened, retrying can duplicate it. Such actions need durable idempotency and reconciliation before replay.

## Tests (run from the agent directory)
```powershell
python -m unittest -v test_resilience.py
python -m py_compile agent.py resilience.py test_resilience.py
```

This branch does not claim that Muse is running or that full Windows integration has passed.