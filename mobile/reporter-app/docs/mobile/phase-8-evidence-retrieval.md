# Phase 8 — Secure evidence retrieval

## Status

**Complete for reporter-uploaded image retrieval.**

Reporter incident evidence now supports an authenticated, short-lived access
grant. The grant is bound to the reporter subject, incident ID, and evidence
ID, and the content route re-checks ownership before serving the private file.
Both grant issuance and content access are audited.

## API

- `POST /reporter/incidents/{incident_id}/evidence/{evidence_id}/access`
- `GET /reporter/incidents/{incident_id}/evidence/{evidence_id}/content?grant=...`

Grants expire after 60 seconds and never contain or expose the storage path.
Path resolution remains rooted under `EVIDENCE_ROOT`; missing or escaped files
are rejected.

## Mobile

Image evidence can be loaded on demand from incident detail using the
short-lived grant and the authenticated bearer header. Video metadata remains
visible, but playback is intentionally deferred until a native media-player
contract is selected and tested.

## Validation and limits

Reporter evidence access, invalid grants, audit records, TypeScript, and
platform bundles are covered by validation. Physical-device image loading,
video playback, push delivery, and live WebRTC remain deployment-dependent.
