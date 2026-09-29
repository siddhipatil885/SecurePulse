# Anonymous person tracking

## Pipeline

```text
Frigate native object track (event.id + box)
  -> MQTT `new` / `update` / `end`
  -> FrigateEventParser
  -> PersonTracker
  -> `/api/v1/tracks` + WebSocket `person_tracks`
  -> React video overlay
```

Frigate is the sole detector and multi-object tracker. `PersonTracker` is a
small projection of Frigate's lifecycle for the dashboard; it does not inspect
frames, associate faces, generate embeddings, or try to override Frigate with
a second tracker.

## Identities and data

`person_track_<frigate-event-id>` is an anonymous, camera-local session ID.
It is stable while Frigate reports the same object and is discarded after the
lost-track grace period. A later re-entry is a new session. It is not a person
identifier and must not be joined to a name or biometric data.

The live contract contains only:

```json
{
  "track_id": "person_track_abc123",
  "camera_id": "1",
  "object_type": "person",
  "bounding_box": { "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.8 },
  "frame_width": 1280,
  "frame_height": 720,
  "state": "ACTIVE",
  "face_visible": null
}
```

Boxes are normalized before the frontend receives them. The overlay maps them
through the actual displayed `object-fit: cover` rectangle, including crop
offsets. It therefore must remain a sibling of the video element inside the
same positioned camera container.

## State transitions

```text
new/update -> ACTIVE
end        -> TEMPORARILY_LOST
update before timeout -> ACTIVE (same track)
timeout    -> EXPIRED (removed from live snapshot)
```

`TRACKING_LOST_TRACK_TIMEOUT_SECONDS` defaults to 3 seconds and
`TRACKING_MINIMUM_DETECTION_CONFIDENCE` defaults to 0.5. Tune these only with
recorded camera evidence; do not use a high threshold as a false-positive fix.

Security incidents remain separate from detection observations. Database
idempotency uses Frigate's source event ID, while the live track stream is
ephemeral. Set `SECURITY_ENGINE_SUPPORTS_TRACKING=true` after an external
security engine has adopted the extended contract; it then receives `track_id`,
normalized box, and current active-person count as anonymous context. The
default keeps the pre-existing external-engine contract unchanged.

## Validation without infrastructure

Run these checks from the repository root:

```powershell
py -m pytest backend/tests -q -p no:cacheprovider
cd dashboard
npm run build
npm run lint
```

When a camera is available, verify the following in order:

1. Enter the frame and remain visible: one label and one box should follow the person.
2. Walk around, stop, then briefly occlude the person: the label should retain the same temporary session.
3. Leave for longer than the configured grace period: the count should become zero.
4. Add a second person: two boxes and a count of two should appear; neither existing box should be renumbered.
5. Resize primary and secondary camera cards: boxes must remain aligned through the `cover` crop.
6. Confirm debug mode displays only temporary technical state and that the normal view displays no confidence, model, face, or identity information.
