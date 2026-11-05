# SecurePulse Mobile Database Change Plan

## Current decision

No database migration is proposed from the mobile-only Phase 0 audit. The mobile app does not access PostgreSQL and has no migration files. Existing documented reporter access is described as an additive backend migration, but its schema and migration execution were not independently inspected because the repository boundary is limited to `mobile`.

## Conditions for future migrations

A migration may be requested only after the backend owner confirms that an equivalent entity does not already exist. Candidate entities from the master prompt include:

- reporter profiles and property memberships;
- manual incidents and incident status history;
- evidence references;
- notification/device registrations;
- reporter feedback.

Before any migration is authored, document:

1. Existing model/table searched and why it cannot be reused.
2. New columns, indexes, foreign keys, and ownership constraints.
3. Backfill and rollback strategy.
4. PostgreSQL compatibility and deployment order.
5. API authorization and audit logging requirements.
6. Tests for ownership boundaries and concurrent writes.

The mobile app must remain compatible with the deployed API during migration rollout. Additive fields and endpoints are preferred; destructive changes require a separately coordinated release.
