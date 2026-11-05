# Rules and dispatch runbook

## Current pilot behavior

- A plain `person` sighting is informational. The local security adapter only
  emits an incident decision when another configured rule triggers.
- Security rule configuration defaults to policy version `1`; bump
  `SecurityConfig.policy_version` when rule or severity policy changes.
- Zone polygons use source-frame pixels. Configure their reference frame size
  to scale them when a camera resolution changes. Empty restricted hours mean
  all day; configured windows use the zone's IANA timezone, include the start,
  and exclude the end. Zone confidence defaults to `0.5` and dwell to zero.
- Dispatch can be manual through `GET /api/v1/dispatch/eligible-marshals` and
  `POST /api/v1/dispatch/offers`, or automatic through
  `POST /api/v1/dispatch/incidents/{incident_id}/dispatch`. The automatic path
  chooses the least-loaded eligible marshal, then the lowest profile ID.
- Marshal availability is a manual `on_duty` / `available` update. It is
  considered fresh for five minutes. Marshal capacity counts both offers and
  accepted/in-progress work.
- Offers default to 60 seconds and accept 10–3600 seconds. After a decline or
  expiry, the next eligible marshal is offered the incident. Selection sorts
  by active workload, then profile ID, and skips marshals who already declined
  or timed out on that incident. After three offers or when none are eligible,
  the incident moves to `ESCALATED` and a dispatcher intent is queued.
- Marshal actions require the targeted marshal account and current assignment
  version: accept/decline, then progress through `EN_ROUTE`, `ON_SCENE`, and
  `COMPLETED`. Completion resolves the incident and writes assignment and
  incident history.
- Assignment changes, history, and notification intents are stored in the
  same transaction. The worker retries failed deliveries up to five attempts
  with exponential delay and jitter; `EXHAUSTED` rows require operator review.
- Notification delivery defaults to `DISPATCH_NOTIFICATION_PROVIDER=disabled`;
  intents remain pending. For local drills, explicitly opt in to `recording-fake`.
  Production configuration rejects that fake provider. It records attempts and never contacts marshals or public
  emergency services. `SENT` with provider `recording-fake` means only that the
  fake sink recorded the intent, not that a person was contacted or read it.

## Reproduce the pilot drill

From `backend/`, run:

```sh
pytest -q tests/test_dispatch.py::test_detection_to_resolution_drill_with_fake_notification_provider
```

The test uses a simulated restricted-zone person event and the local fake
provider. The broader failure and policy suite is `pytest -q`.

## Failure diagnosis

- `MARSHAL_UNAVAILABLE`: confirm the profile is active, the user has an active
  marshal membership for the property, and availability was refreshed within
  five minutes.
- `MARSHAL_AT_CAPACITY`: complete or cancel existing assignments, or increase
  capacity only after the responsible operator confirms it.
- `ACTIVE_ASSIGNMENT_EXISTS`: inspect the active assignment for the incident;
  do not bypass the one-active-assignment constraint.
- `OFFER_CONFLICT`: refresh the offer and submit the current version. The
  timeout worker and marshal response race safely through a row lock.
- `EXHAUSTED` notification: inspect `notification_attempts` and the provider
  error, then arrange an operator follow-up. The incident and assignment
  records remain intact.
- If a worker is stopped, pending offers remain in the database. On restart,
  the timeout worker finds due offers and the notification worker reclaims
  pending, failed, or stale processing rows.

## Product decisions still required

The five-minute availability freshness, default one-minute offer, three-offer
automatic reassignment policy, dispatcher authority, and final escalation handling are safe
development defaults, not approved production policy. Confirm these with the
product owner before using dispatch operationally. No external delivery
provider or emergency-service integration is configured.
