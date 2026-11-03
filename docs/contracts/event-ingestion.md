# Frigate event ingestion contract

Version: 1.0
Boundary: Frigate MQTT `frigate/events` → backend `FrigateEventParser` → bounded in-process queue → `EventProcessor` / database receipt transaction.

## Source event fields

The parser accepts Frigate event lifecycle messages with `type` equal to `new`, `update`, or `end`, and an `after` object containing:

| Source field | Normalized field | Rule |
|---|---|---|
| `after.id` | `source_event_id` | Required non-empty source tracking/event ID; stable across that event's lifecycle. |
| `after.camera` | `camera` | Required non-empty Frigate camera identifier, mapped by the backend to its registered camera. |
| `after.label` | `object_type` | Required non-empty label. Person filtering and incident decisions remain in the Security Engine. |
| `after.top_score` | `confidence` | Required finite number in `[0, 1]`; booleans are rejected. |
| `after.start_time` | `timestamp` / `occurred_at` | UTC source event start for `new` and `update`. |
| `after.end_time` | `timestamp` / `occurred_at` for `end` | UTC event end when supplied; otherwise the parser falls back to start time. |
| MQTT `type` | `metadata.event_phase` | One of `new`, `update`, `end`. |
| Parsed event | `metadata.ingested_at` | UTC adapter receive/normalization time, not source time. |
| `after.box` | `metadata.bounding_box` | Optional four finite values in Frigate `[x1, y1, x2, y2]` pixel coordinates. Frame dimensions are passed through when supplied. |
| zone fields | `metadata.zones`, `current_zones`, `entered_zones` | Optional zone identifiers; Frigate may omit these in early lifecycle messages. |
| `has_snapshot`, `has_clip` | matching booleans | Evidence availability flags only. The adapter never copies image bytes or credentials into event logs. |
| event contents | `metadata.revision` | SHA-256 of canonicalized source event content; used with phase for durable replay receipts. |

Normalized events also carry `source="frigate"`, the source event ID, camera, label, confidence, and timezone-aware timestamp. `backend/app/domain/events.py` is the shared model; no second competing event schema is introduced.

## Delivery, retries, and idempotency

Frigate is the sole publisher on `frigate/#`; the backend account can read `frigate/events` and availability state but cannot publish upstream. The callback validates and places normalized events into a bounded in-memory queue. Processing runs sequentially off the Paho network callback. A full queue rejects the event with source ID and camera in the structured error log. Shutdown allows up to ten seconds for the queue to drain and logs remaining depth on timeout.

The queue is not durable. MQTT delivery from Frigate is not treated as exactly once or replayable, and an event can be lost while the broker/backend is disconnected or when a bounded queue overflows. After receipt, the backend persists idempotency using the unique source system, source event ID, lifecycle phase, and revision tuple (`SourceEventReceipt`). Duplicate receipts are suppressed by the database transaction. The receiver/database, not the edge adapter, owns durable deduplication.

There is no source sequence number in this contract. `end` closes an existing event; consumers must tolerate a delayed `update` and must not infer a real-world identity across distinct Frigate event IDs. Arrival order and source clock skew remain observable limitations.

## Camera health envelope

`GET /health/edge` reports MQTT connected/disconnected, Frigate reachable/unavailable, queue depth/capacity, and each Frigate camera's `camera_fps` and `process_fps`. Status semantics: `online` means positive camera FPS and a nonzero or unavailable process FPS; `degraded` means camera frames arrive while processing FPS is zero; `offline` means Frigate is reachable and reports zero camera FPS; `unknown` means the stats response lacks a valid FPS. The endpoint reports a UTC observation time. This signal is not yet persisted to the camera health observation table.

The backend health endpoint does not include RTSP credentials, internal stream URLs, or video. Dashboard access must use an approved playback endpoint; it must not expose raw camera URLs.

## Fixture status

`backend/tests/fixtures/frigate/v0.13/events.json` is a sanitized, versioned contract fixture covering the three lifecycle phases. Its synthetic IDs and coordinates are test data; it is not evidence of a live Frigate capture. A live sanitized capture must be added after the runtime smoke test, without image bytes, usernames, passwords, or private camera addresses.
