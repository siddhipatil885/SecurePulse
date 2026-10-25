# Dashboard transport contract v1

Keep the existing WebSocket because the backend and track projection already
use it. The dashboard needs server-to-client invalidation; replacing this
working transport with SSE would add a second path without a client benefit.

Connect `/api/v1/events/stream` with browser subprotocols
`securepulse.v1` and `bearer.<access JWT>`. Only `securepulse.v1` is echoed.
Native clients may use Authorization; legacy query tokens remain supported
for compatibility but the dashboard never puts tokens in URLs. Require TLS
and proxy header redaction in production. Origins must match configured CORS
origins. Authentication uses the shared read principal and property claims.

Security event envelope:

```json
{
  "version": 1,
  "event_id": "process-epoch:42",
  "sequence": 42,
  "property_id": 1,
  "kind": "incident.updated",
  "incident_id": 101,
  "occurred_at": "2026-10-25T12:00:00+00:00",
  "type": "security_event",
  "data": { "id": 101, "property_id": 1, "camera_id": 1, "status": "OPEN" }
}
```

`data` is the complete existing EventResponse, not the abbreviated example.
`occurred_at` is the source observation time, **not** transition or delivery
time; transitions have their own persisted history timestamps.
`person_tracks` has version/event_id/sequence/property_id and
`data: {camera_id, tracks}` using the existing track schema. Camera-less or
unscoped tracks are not sent to property-scoped subscribers.

Sequence is monotonic within one process, with gaps due to property filtering;
it is not a durable cursor. On every subscription the server first sends
`{version:1,type:"resync_required"}`. A full queue is discarded and replaced
with the same resync marker. Queue capacity is 100, global connections 100,
send deadline 10s, heartbeat at most every 15s when idle. JWT validity and scope
are checked before every send; expiry closes 4401. Claim-based access cannot
observe DB membership revocation before JWT expiry; Engineer 2 must supply a
shared revocation-aware principal for that production requirement.

The browser treats notifications as invalidations and refetches persisted REST
state. This deliberately prevents out-of-order messages from rolling state
back. Event IDs are deduplicated with a bounded 1000-entry cache, fetches are
coalesced to one pending refresh per second and one request batch at a time.
REST polling runs every 15s even without the socket. A dirty refresh runs again
after the in-flight snapshot so updates arriving during fetch are recovered.
Six exponential reconnect attempts (up to 30s, with jitter), then polling-only
mode; Retry resets the connection. Heartbeat silence over 35s forces recovery.
401/403 or socket 4401/1008 stops the session and removes displayed records.
Transient REST failures remove stale monitoring values and retry on polling.

Important new OPEN HIGH/CRITICAL incidents produce an in-page alert after the
first REST baseline, once per incident per connection generation; repeated
or reordered transport messages do not duplicate it. Initial baseline alerts
remain visible in the durable list without popup spam. Retry/new session
establishes a new baseline. Browser notifications do not dispatch responders.

Status commands publish the committed result after IncidentService completes
its DB transaction. REST remains available if transport is interrupted.
There is no durable transport replay log or second incident store. Run one
Uvicorn worker for realtime; shared fanout is a deployment handoff. Periodic
REST resync still recovers final state across process restarts/worker splits,
but transient intermediate transitions must be read from incident history.

Playback access: POST `/frigate/cameras/{id}/playback-access` requires the
existing read principal and authorized enabled camera, returns `grant` and
`expires_at` (60s). POST SDP to `/frigate/cameras/{id}/webrtc` with bearer and
`X-Playback-Grant`; signature, audience, actor, camera and property are checked.
Browser closes/renegotiates before expiry. No RTSP credentials enter the client.
An established upstream peer cannot yet be forcibly revoked by this gateway;
server-owned peer lifecycle remains an explicit Engineer 1/2 blocker.

Maintain frontend wire interfaces in `src/api.ts` against backend
`schemas/{camera,event,incident,property}.py` and `/openapi.json`. Run
`npm run typecheck`, browser contract tests and Python tests after changing
either side. Dispatch event kinds remain pending Engineer 3 agreement.
