# Phase 10 — Account self-service

## Status

**Complete for reporter profile and password management.**

Authenticated reporters can update their display name and rotate their
password from Profile. Password changes use the current password, require a
12-character minimum replacement, update the salted scrypt hash, increment
the server token version, and therefore invalidate all existing sessions.
The mobile app signs out locally after a successful rotation so the user must
sign in again with the new password.

## Security

- Email and property memberships remain administrator-controlled.
- Current-password verification happens server-side.
- Password values are never persisted or logged by the mobile app.
- Token invalidation is enforced by the existing reporter authentication
  dependency, not by client state.

## Remaining release blockers

Production migration application, physical-device validation, push-provider
delivery, live WebRTC, and native video playback remain deployment-dependent.
