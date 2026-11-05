# Phase 5 — Notification registration

## Status

**Partially complete; registration and preference synchronization implemented, delivery not fully validated.**

## Implemented

- Expo notification permission request from Settings.
- Expo push-token registration bound to a SecureStore device identifier.
- Server-side device registration, update, deactivation, and logout deactivation.
- Server-side notification categories: security alerts, incident updates, and dispatch updates.
- Mobile preference synchronization after enabling notifications.
- No token, password, evidence, or location data is logged or displayed.

## API

- `POST /api/v1/reporter/devices`
- `DELETE /api/v1/reporter/devices/{device_id}`
- `GET /api/v1/reporter/notification-preferences`
- `PUT /api/v1/reporter/notification-preferences`

All routes require the authenticated reporter token and are account-scoped.

## Database

Migration `0015_reporter_notifications` adds `user_device_tokens` and `notification_preferences`.

## Configuration

Set `EXPO_PUBLIC_EXPO_PROJECT_ID` in the mobile environment and configure real Expo/FCM/APNs credentials before requesting push registration in a release build. The backend still needs a configured notification provider worker; registering a token does not claim delivery.

## Validation

The backend reporter tests cover registration, deactivation, preference persistence, and account scoping. TypeScript, unit tests, navigation tests, and bundle exports cover the mobile changes. Physical Android/iOS permission prompts, terminated-app handling, provider delivery, invalid-token cleanup, and deep links remain unverified.

## Blockers

- No push provider credentials or delivery implementation is configured in this repository.
- Foreground/background/terminated delivery cannot be claimed until a provider worker and physical devices are available.
