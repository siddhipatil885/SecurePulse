# Phase 7 — Incident history and accessible account workflows

## Status

**Complete for the scoped mobile history work.**

Reporter incident history now supports server-side status filtering, preserves
pagination, and renders each report as an accessible navigable control. The
detail route remains ownership-protected by the backend and exposes timeline,
dispatch, and evidence metadata.

## API changes

`GET /api/v1/reporter/incidents` accepts optional `status` and
`incident_type` filters. Filtering occurs before pagination and remains scoped
to the authenticated reporter, so the client never downloads another user's
reports to filter locally.

## Mobile changes

- Added status filter controls for all, received, dispatched, and resolved
  reports.
- Added accessible report cards with labels and deep links to incident detail.
- Preserved retry, loading, empty, pagination, and offline query states.
- Query keys include the active filter so switching filters cannot reuse an
  unrelated cached page.

## Deliberate limits

Profile editing, password rotation, support/feedback submission, authorized
evidence media retrieval, push delivery, physical-device validation, and live
WebRTC playback still require backend/provider or deployment work. They are
not represented as completed by this phase.

## Validation

Run the backend reporter tests, mobile typecheck, Vitest/API tests, Jest
navigation tests, and Android/iOS Expo exports before release.
