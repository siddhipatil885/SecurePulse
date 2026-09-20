# Security Intelligence Module

> **Person 3 — Security Intelligence Engine**
>
> Analyze detections and determine whether a security rule has been triggered.

---

## Overview

The Security Intelligence module is a **standalone, stateless-by-contract rule engine** that receives normalized detection data and produces security event candidates. It is deliberately decoupled from:

- **Database / SQLAlchemy** (Person 1's responsibility)
- **Frigate / MQTT internals** (Person 2's responsibility)
- **Dashboard / Alert providers** (Person 4's responsibility)

```text
                DetectionEvent
                      │
                      ▼
              ┌───────────────┐
              │ SecurityEngine│
              └───────┬───────┘
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
   Person Rule    Zone Rule    Multiple Rule
                      │
                      ▼
               Loitering Rule
                      │
                      ▼
              Cooldown Manager
                      │
                      ▼
              Severity Resolver
                      │
                      ▼
          SecurityEventCandidate
```

---

## Input Schema: DetectionEvent

```python
DetectionEvent(
    source="frigate",
    source_event_id="abc123",
    camera_id="cam1",
    object_id="person-123",
    object_type="person",
    confidence=0.92,
    timestamp=datetime(...),
    bbox=BoundingBox(x1=100, y1=100, x2=300, y2=500),
    frame_width=1920,
    frame_height=1080,
    event_state="start",
    metadata={}
)
```

| Field | Type | Required | Description |
|:---|:---|:---|:---|
| `source` | `str` | ✅ | Detection source (e.g. `"frigate"`) |
| `source_event_id` | `str` | ✅ | Upstream event identifier |
| `camera_id` | `str` | ✅ | Camera identifier |
| `object_id` | `str` | ✅ | Tracked object identifier |
| `object_type` | `str` | ✅ | Detected object class (e.g. `"person"`) |
| `confidence` | `float` | ✅ | Detection confidence 0.0–1.0 |
| `timestamp` | `datetime` | ✅ | When the detection occurred |
| `bbox` | `BoundingBox` | ❌ | Bounding box in pixel coords |
| `frame_width` | `int` | ❌ | Frame width in pixels |
| `frame_height` | `int` | ❌ | Frame height in pixels |
| `event_state` | `EventState` | ❌ | `start`, `update`, or `end` |
| `metadata` | `dict` | ❌ | Arbitrary extra data |

---

## Output Schema: SecurityEventCandidate

```python
SecurityEventCandidate(
    event_type="ZONE_ENTRY",
    camera_id="cam1",
    source_event_id="abc123",
    object_id="person-123",
    severity="MEDIUM",
    confidence=0.92,
    timestamp=datetime(...),
    zone_id="server-room",
    reason="Person entered restricted zone 'Server Room'",
    metadata={}
)
```

### Event Types

| Event Type | Description |
|:---|:---|
| `PERSON_DETECTED` | A person was detected |
| `ZONE_ENTRY` | A person transitioned from outside to inside a restricted zone |
| `LOITERING` | A person remained in a restricted zone beyond the threshold |
| `MULTIPLE_PERSONS` | The number of simultaneous persons exceeded the threshold |

### Severity Levels

| Severity | Default Events |
|:---|:---|
| `INFO` | `PERSON_DETECTED` |
| `LOW` | — |
| `MEDIUM` | `ZONE_ENTRY`, `MULTIPLE_PERSONS` |
| `HIGH` | `LOITERING` |
| `CRITICAL` | — |

---

## Rule Architecture

All rules implement `SecurityRule`:

```python
class SecurityRule(ABC):
    def evaluate(self, context: SecurityContext) -> SecurityRuleResult | None:
        ...
```

Rules receive a `SecurityContext` containing the current detection, active detections, configured zones, and the evaluation timestamp.

### PersonDetectedRule
- Triggers when `object_type == "person"`
- Stateless

### ZoneEntryRule
- Triggers on **outside → inside** transition
- Tracks per `(camera_id, object_id, zone_id)`
- Does NOT re-trigger while person remains inside

### LoiteringRule
- Triggers when a person remains in a zone beyond `loitering_threshold_seconds`
- Tracks `entered_at`, `last_seen_at`, `triggered` per `(camera_id, object_id, zone_id)`
- Fires once per visit; resets when person leaves

### MultiplePersonRule
- Triggers when simultaneous person count ≥ `multiple_person_threshold`
- Counts from `active_detections` on the same camera

---

## Zone Representation

```python
Zone(
    id="server-room",
    name="Server Room",
    camera_id="cam1",
    polygon=[Point(x=400, y=200), Point(x=800, y=200),
             Point(x=800, y=600), Point(x=400, y=600)],
    enabled=True
)
```

- Coordinates are in **pixel space** (origin top-left)
- Point-in-polygon uses the **ray-casting algorithm** (works for convex and concave polygons)
- The person's position is the **bottom-center** of their bounding box

---

## Loitering State Management

```text
Person enters zone
     ↓
Start timer (entered_at = now)
     ↓
Update last_seen_at each frame
     ↓
If elapsed ≥ threshold → LOITERING (once)
     ↓
Person leaves → state cleared
     ↓
Re-entry → timer restarts from zero
```

---

## Cooldown Behaviour

Prevents duplicate events within a configurable window:

```text
Key = (camera_id, event_type, object_id)

First trigger   → ✅ allowed, record timestamp
Same key < TTL  → ❌ suppressed
Same key ≥ TTL  → ✅ allowed, refresh timestamp
```

Default cooldowns:

| Event Type | Cooldown (seconds) |
|:---|:---|
| `PERSON_DETECTED` | 5 |
| `ZONE_ENTRY` | 30 |
| `LOITERING` | 60 |
| `MULTIPLE_PERSONS` | 30 |

---

## Configuration

All tunables via `SecurityConfig`:

```python
SecurityConfig(
    confidence_threshold=0.5,
    loitering_threshold_seconds=15.0,
    multiple_person_threshold=3,
    person_detected_cooldown_seconds=5.0,
    zone_entry_cooldown_seconds=30.0,
    loitering_cooldown_seconds=60.0,
    multiple_person_cooldown_seconds=30.0,
    severity_map={"PERSON_DETECTED": "CRITICAL"},  # override
    zones=[...],
)
```

---

## Integration Contracts

### Person 2 → Security Engine (Input)

Person 2 produces `app.domain.events.DetectionEvent`. A thin adapter maps it to `app.security.models.DetectionEvent`:

```python
from app.security.models import DetectionEvent, BoundingBox

# Adapter (to be built during integration)
security_detection = DetectionEvent(
    source=frigate_detection.source,
    source_event_id=frigate_detection.source_event_id,
    camera_id=frigate_detection.camera,
    object_id=frigate_detection.metadata.get("object_id", frigate_detection.source_event_id),
    object_type=frigate_detection.object_type,
    confidence=frigate_detection.confidence,
    timestamp=frigate_detection.timestamp,
    bbox=BoundingBox(...),  # from metadata
)
```

### Security Engine → Person 1 (Output)

`SecurityEventCandidate` maps to Person 1's `SecurityDecision`:

```python
from app.domain.security import SecurityDecision

decision = SecurityDecision(
    event_type=candidate.event_type.value,
    score=int(candidate.confidence * 100),
    severity=candidate.severity.value,
    reason=candidate.reason,
    metadata=candidate.metadata,
)
```

### Security Engine → Person 4 (Consumption)

Person 4 consumes persisted `SecurityEvent` records via Person 1's API. The event includes all fields needed for alerts:

```json
{
    "event_type": "LOITERING",
    "severity": "HIGH",
    "camera_id": "cam1",
    "zone_id": "server-room",
    "timestamp": "2026-09-20T10:00:15Z",
    "reason": "Person remained in restricted zone 'Server Room' for 15 seconds"
}
```

---

## Known Limitations

1. **In-memory state**: Zone membership, loitering timers, and cooldowns are stored in process memory. Service restarts reset all state. For production scaling, replace with Redis or equivalent.
2. **Single-zone result per evaluation**: The zone entry and loitering rules currently return the *last* triggered zone result if multiple zones match. This is acceptable for the prototype.
3. **No cross-camera tracking**: Each camera is evaluated independently. Cross-camera re-identification is deferred to v2.
4. **Boundary precision**: Point-on-edge results may vary due to floating-point precision in the ray-casting algorithm.
5. **No persistence**: The engine does not save events. It only produces candidates for Person 1 to persist.

---

## Running Tests

```bash
cd backend
python -m pytest tests/security/ -v
```

All tests run with **zero external dependencies** — no database, no Frigate, no network.
