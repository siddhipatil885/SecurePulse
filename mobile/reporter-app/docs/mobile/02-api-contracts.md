# SecurePulse Mobile API Contract Register

This is the contract currently documented or exercised by the mobile application. Routes are relative to `/api/v1`. Backend source files were intentionally not inspected because this task is restricted to the mobile folder.

## Verified by mobile contract tests and README

| Method | Route | Auth | Mobile use |
| --- | --- | --- | --- |
| POST | `/auth/login` | Public endpoint; server authentication required | Returns bearer token and expiry |
| GET | `/auth/me` | Reporter bearer token | Validates session and returns profile/property memberships |
| POST | `/auth/logout` | Reporter bearer token | Revokes server-side reporter tokens |
| GET | `/reporter/cameras` | Reporter bearer token + `property_id` | Lists assigned cameras |
| GET | `/reporter/cameras/{id}` | Reporter bearer token + `property_id` | Reads one authorized camera |
| GET | `/reporter/events` | Reporter bearer token + `property_id`, `page`, `page_size` | Reads paginated property events |
| GET | `/reporter/events/{id}` | Reporter bearer token + `property_id` | Reads one authorized event |
| GET | `/reporter/summary` | Reporter bearer token + `property_id` | Reads property counts and alert summary |

Responses are parsed with Zod before reaching screens. A 401 invalidates the current session when the request used the active token.

## Required contracts that are not verified or present in the mobile app

Do not implement callers for these routes until the backend owner provides the actual route, request schema, response schema, authorization rules, and tests:

- Manual incident create, list, detail, cancel.
- Evidence upload and evidence download.
- Incident status timeline and realtime updates.
- Marshal assignment and dispatch status.
- Push-device registration and notification preferences.
- Notification list and deep-link payload.
- Camera stream session/token and snapshot/clip access.
- Confirm-threat, false-alarm, and escalation actions.

For each new route, add:

1. A typed request/response schema.
2. A client method with cancellation and normalized errors.
3. A query or mutation with an authorization-aware key.
4. API tests for success, validation failure, unauthorized access, timeout, and malformed response.
5. A README and phase report update.
