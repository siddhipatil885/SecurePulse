# Phase 6 — Camera and alert actions

## Status

**Partially complete; alert review is implemented and camera media contracts are present, but native live playback is not fully validated.**

## Implemented

- Reporter event responses now include the authorized operator alert ID/status when one exists.
- Property-authorized `POST /api/v1/reporter/events/{event_id}/review` supports `CONFIRMED` and `FALSE_ALARM`.
- Review actions are server-authorized, lock the alert row, reject repeat decisions, record actor/time, and create an audit record.
- Mobile alert details show Confirm threat and Dismiss as false alarm only for an active backend alert.
- Existing FastAPI Frigate routes continue to authorize camera access through property-scoped camera lookup and proxy credentials rather than exposing Frigate credentials.

## API and database

Migration `0016_alert_review` adds `alerts.reviewed_by` and `alerts.reviewed_at`.

The existing media routes remain:

- `GET /api/v1/frigate/cameras/{camera_name}/snapshot`
- `POST /api/v1/frigate/cameras/{camera_id}/webrtc`

Reporter camera names are intentionally redacted, so a future mobile stream hook must obtain a short-lived authorized media contract rather than reconstructing internal Frigate URLs.

## Validation

- Backend reporter, metadata, and media security tests passed.
- TypeScript check passed.
- Existing Frigate proxy tests and full suite must remain green.
- No physical WebRTC playback, camera network access, or terminated/background media behavior was claimed.

## Security

- Reporter membership is checked on every review action.
- Alert decisions are server-side and one-way after the first review.
- Review actor and timestamp are audited.
- No camera credentials or internal camera names are returned to mobile.

## Blockers

- React Native WebRTC playback requires a compatible native player/development build and a deployed go2rtc/WebRTC endpoint.
- Snapshot/clip retrieval for reporter incidents still needs a short-lived authorized media URL and retention policy.
- Live camera status remains unverified rather than inferred from `enabled`.

## Next phase

Phase 7 should complete incident history filtering, profile/account settings, feedback, and accessibility. Release hardening should follow only after native media and notification providers are available.
