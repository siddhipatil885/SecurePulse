"""SQLAlchemy persistence models."""

from app.models.camera import Camera
from app.models.camera_operations import CameraHealthObservation, Zone
from app.models.evidence import Evidence
from app.models.security_event import SecurityEvent
from app.models.reporter_incident import ReporterIncident, ReporterIncidentEvidence, ReporterIncidentTimeline
from app.models.track import Track
from app.models.alert import Alert
from app.models.tenancy import Property, PropertyMembership, User
from app.models.operations import (
    Assignment,
    AssignmentEvent,
    AuditRecord,
    IncidentStatusHistory,
    MarshalAvailability,
    MarshalProfile,
    NotificationAttempt,
    NotificationOutbox,
    NotificationPreference,
    UserDeviceToken,
    SourceEventReceipt,
)

__all__ = [
    "Alert", "Assignment", "AssignmentEvent", "AuditRecord", "Camera", "CameraHealthObservation", "Evidence",
    "IncidentStatusHistory", "MarshalAvailability", "MarshalProfile", "NotificationAttempt",
    "NotificationOutbox", "NotificationPreference", "Property", "PropertyMembership",
    "SecurityEvent", "UserDeviceToken",
    "ReporterIncident", "ReporterIncidentEvidence", "ReporterIncidentTimeline",
    "SourceEventReceipt", "Track", "User", "Zone",
]
