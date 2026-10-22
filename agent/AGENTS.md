# Local Agent Runtime Instructions

Scope: `agent/**`. Root `AGENTS.md` security, approval, and reporting rules remain mandatory.

- Keep runtime behavior deterministic where possible and preserve the pre-execution approval gate and audit-chain behavior.
- Do not add an unattended bypass or `--yes` equivalent without explicit owner approval and a reviewed threat model.
- Do not add network destinations, tool capabilities, credential access, or shell execution authority without explicit approval.
- Keep tests dependency-light where practical; existing CI uses Python 3.11 and stdlib unittest.
- Focused validation from repository root: `python -m py_compile agent/agent.py agent/resilience.py agent/test_resilience.py`.
- Unit tests: run `python -m unittest -v test_resilience.py` with working directory `agent/`.
- For changes to approval or audit behavior, add tests for denied actions, malformed requests, and audit integrity as applicable.
- Never use production secrets or persistent user data in tests; use synthetic fixtures.
