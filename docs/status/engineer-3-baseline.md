# Engineer 3 baseline: security rules and response workflow

Initial inventory checked against `main` at `c3ac692` (26 October 2026), then
updated with follow-up implementation evidence on 5 November 2026.

## P3-00 inventory

The previously reported engine is present and is retained. This baseline was
verified by tracing imports and call sites in source. Tests run in an isolated
`/private/tmp/securepulse-venv` because the checkout's system Python does not
have `pytest` installed.

| Component | Status | Evidence |
|---|---|---|
| Rule engine and candidate | KEEP | `backend/app/security/engine.py`, `backend/app/security/models.py`; `backend/tests/security/test_engine.py` |
| Frigate normalization | FIX | `backend/app/security/adapters/frigate.py`; `backend/tests/security/test_frigate_adapter.py`. Converts Frigate event lifecycle and pixel boxes; no real sanitized Engineer 1 capture found in tracked files. |
| Restricted-zone rule | FIX | `backend/app/security/rules/zone.py`; `backend/tests/security/test_policy_edge_cases.py`. Camera-specific pixel polygons with validated geometry, configured frame scaling, local operating windows, confidence/dwell thresholds, inclusive boundaries, and end/out-of-order handling. |
| Candidate to backend decision | FIX | `backend/app/integrations/local_security_engine.py`; `backend/app/domain/security.py`. Decision carries event type, reason, severity and metadata; candidate maps track/zone/tripwire. Policy version added in this change. |
| Plain person detection | FIX | `PersonDetectedRule` emits `PERSON_DETECTED/INFO`; local adapter previously returned it as an incident-worthy decision. Adapter now maps a sighting without another triggered rule to `DETECTION/INFO`. |
| Incident persistence/idempotency | KEEP | `backend/app/services/event_processor.py`, `backend/app/models/operations.py`, `backend/app/models/security_event.py`; source receipt uniqueness and incident key uniqueness exist. |
| Incident lifecycle | FIX | `backend/app/services/incident_service.py`, `backend/app/api/incidents.py`, and `backend/app/repositories/dispatch.py`; acknowledge/resolve/dismiss/reopen plus audited dispatching/escalated/resolved transitions. |
| Assignments and notification outbox | FIX | `backend/app/services/dispatch_service.py`, `backend/app/services/dispatch_workers.py`, `backend/app/api/dispatch.py`, and `backend/tests/test_dispatch.py`. Offers use deterministic least-load selection, bounded reassignments, explicit escalation, a recording fake provider, retries, and persisted timeout recovery. |

## Existing candidate contract

`SecurityEventCandidate` contains event type, camera, source event ID, object
ID, optional anonymous track ID, severity, detector confidence, timestamp,
optional zone/tripwire IDs, reason, and metadata. Its confidence is detector
evidence and is not incident certainty. Candidate policy version is now
explicit. The local adapter returns the existing `SecurityDecision` contract;
the event processor persists decision fields and metadata in
`SecurityEvent` (`event_type`, `severity`, `score`, `reason`, metadata, and
source Frigate event ID). No persistence columns are added by this work.

## Known limitations for next steps

- Rule state and cooldown are process-local, so horizontal workers can disagree.
- The Frigate adapter maps MQTT `new`/`update`/`end` phases, but zone state is
  not cleaned on end and replay ordering is not persisted.
- Default configuration has no restricted zones. Zone polygons and boxes use
  source-frame pixel coordinates; local normalized boxes are scaled when frame
  dimensions are available.
- There is no sanitized captured Frigate payload in the checkout to validate
  against; deterministic fixtures are available in the security tests.
- Product decisions from package F remain pending; defaults must be
  conservative and no external emergency dispatch is present.
