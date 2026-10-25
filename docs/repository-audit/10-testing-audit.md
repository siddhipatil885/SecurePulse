# Testing and Quality Audit

## Test discovery

Only `ai-cctv/tests/test_mqtt_subscriber.py` exists. Despite its name, it defines no `test_*` function/class and contains no assertion or fixture. It is an indefinitely running manual subscriber (`:44-64`), not a pytest test.

| Test class | Found | Notes |
|---|---|---|
| Unit tests | No | Zero pytest tests collected |
| Integration tests | No | Manual MQTT observation does not assert behavior |
| API tests | No | No API |
| Database tests | No | No application DB |
| Security tests | No | None discoverable |
| Frontend/mobile tests | No | No clients |
| End-to-end tests | No | No camera-to-incident assertion |

Coverage is not measurable because no automated test executes application behavior and no coverage configuration/dependency exists.

## Commands executed

All checks were read-only/non-destructive; bytecode and pytest cache creation were disabled.

| Command/check | Result | Interpretation |
|---|---|---|
| `python --version` | PASS: Python 3.14.7 available | Host does not match documented minimum exactly but exceeds it (`phase1_setup.md:13`) |
| AST parse of `test_mqtt_subscriber.py` | PASS | Python syntax is valid; dependencies/runtime not proven |
| `python -m pytest --collect-only -q -p no:cacheprovider ai-cctv/tests` | Completed: **no tests collected** | Security and functional tests do not exist as pytest cases |
| `docker --version` | BLOCKED: command not found | Container runtime unavailable |
| `docker compose version` | BLOCKED: command not found | Compose validation unavailable |
| `docker compose ... config` | BLOCKED: command not found | Rendered Compose could not be checked |
| Git clean/status and branch/history inspection | PASS | No pre-audit worktree changes; one visible main branch |

No dependency installation, image pull, service startup, network camera access, database operation, migration, or cloud operation was attempted.

## Static validation results

- Subscriber syntax is valid.
- `pytest` is installed in the audit environment, but discovers zero tests.
- The subscriber depends on Paho at import time (`test_mqtt_subscriber.py:9`); import/connect behavior was not counted as passing because no broker was run.
- Compose contains a deterministically conflicting host-port declaration for `8554` (`docker-compose.yml:25`, `:49`).
- No linter, formatter, type-checker, frontend builder, vulnerability scanner, coverage tool, or CI config is declared.

## Missing high-value test layers

1. Config lint: Compose render, Frigate config validation against the pinned image, Mosquitto config test, duplicate host-port policy.
2. Video smoke test: deterministic sample publisher → decodable Frigate feed → person fixture event.
3. MQTT contract tests: captured Frigate new/update/end payloads, malformed/missing/out-of-order/duplicate variants.
4. Adapter unit tests: normalization, schema rejection, idempotency, retry/dead-letter decisions.
5. Rule-engine unit tests: zone boundary, confidence threshold, temporal rule, suppression/correlation.
6. Repository/API integration tests with ephemeral PostgreSQL and migrations.
7. Authorization tests: role/property matrix, IDOR negatives, evidence access, realtime connection auth.
8. Dispatch concurrency tests: duplicate worker, simultaneous accept/timeout, stale availability, notification failure.
9. Browser/mobile contract and end-to-end tests using real test APIs.
10. Recovery tests: broker/backend/DB restart, replay, backup restore, disk capacity and retention.

## Quality risks

- Minimum-only dependency ranges (`requirements.txt:1-9`) can resolve differently over time.
- There is no package layout or `__init__.py` because backend code is absent.
- Documentation asserts expected runtime output without preserving logs, fixtures, or automated proof (`phase1_setup.md:70-103`).
- README and Phase 1 docs disagree about repository emptiness/current state (`README.md:215-244`; Phase 1 docs `:17-35`).

