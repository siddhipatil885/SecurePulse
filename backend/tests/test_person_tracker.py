"""Tests for the Frigate-backed, anonymous live person track projection."""

from datetime import datetime, timedelta, timezone

from app.domain.events import DetectionEvent
from app.realtime.publisher import InMemoryEventPublisher
from app.services.person_tracker import PersonTracker


def detection(source_event_id: str = "frigate-object-1", *, lifecycle: str = "update", at: datetime | None = None, box: list[float] | None = None) -> DetectionEvent:
    return DetectionEvent(source="frigate", source_event_id=source_event_id, camera="front_door", object_type="person", confidence=0.91, timestamp=at or datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc), metadata={"lifecycle": lifecycle, "bounding_box": box or [128, 72, 512, 648], "frame_width": 1280, "frame_height": 720})


def test_one_hundred_observations_remain_one_track() -> None:
    tracker = PersonTracker()
    start = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    for index in range(100):
        tracker.observe(detection(lifecycle="new" if index == 0 else "update", at=start + timedelta(milliseconds=index)), "1")
    tracks = tracker.tracks_for_camera("1")
    assert len(tracks) == 1
    assert tracks[0]["track_id"] == "person_track_frigate-object-1"
    assert tracks[0]["bounding_box"] == {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.8}


def test_two_native_frigate_objects_are_two_tracks() -> None:
    tracker = PersonTracker()
    tracker.observe(detection("object-a", lifecycle="new"), "1")
    tracker.observe(detection("object-b", lifecycle="new"), "1")
    assert [track["track_id"] for track in tracker.tracks_for_camera("1")] == ["person_track_object-a", "person_track_object-b"]


def test_temporary_loss_is_reacquired_without_a_new_identity() -> None:
    tracker = PersonTracker(lost_track_timeout_seconds=3)
    start = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    tracker.observe(detection(lifecycle="new", at=start), "1")
    lost = tracker.observe(detection(lifecycle="end", at=start + timedelta(seconds=1)), "1")
    assert lost is not None and lost.state == "TEMPORARILY_LOST"
    recovered = tracker.observe(detection(lifecycle="update", at=start + timedelta(seconds=2)), "1")
    assert recovered is not None
    assert recovered.track_id == "person_track_frigate-object-1"
    assert recovered.state == "ACTIVE"


def test_track_expires_after_loss_timeout_and_new_person_gets_new_session() -> None:
    tracker = PersonTracker(lost_track_timeout_seconds=2)
    start = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    tracker.observe(detection(lifecycle="new", at=start), "1")
    tracker.observe(detection(lifecycle="end", at=start + timedelta(seconds=1)), "1")
    expired = tracker.expire_stale(start + timedelta(seconds=3))
    new_track = tracker.observe(detection("frigate-object-2", lifecycle="new", at=start + timedelta(seconds=4)), "1")
    assert [track.track_id for track in expired] == ["person_track_frigate-object-1"]
    assert new_track is not None and new_track.track_id == "person_track_frigate-object-2"
    assert len(tracker.tracks_for_camera("1")) == 1


async def test_track_messages_are_separate_from_security_events() -> None:
    publisher = InMemoryEventPublisher()
    queue = await publisher.subscribe()
    await publisher.publish_tracks("1", [{"track_id": "person_track_a"}])
    assert await queue.get() == {"type": "person_tracks", "data": {"camera_id": "1", "tracks": [{"track_id": "person_track_a"}]}}
