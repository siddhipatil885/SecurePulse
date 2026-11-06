"""Property-scoped operator projection over camera and manually reported cases."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Integer, String, case, cast, func, literal, null, or_, select, union_all, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationError
from app.models import (Assignment, AssignmentEvent, AuditRecord, Camera, Evidence,
    IncidentStatusHistory, NotificationOutbox, Property, ReporterIncident,
    ReporterIncidentEvidence, ReporterIncidentTimeline, SecurityEvent, MarshalAvailability)
from app.schemas.case import (CaseCommand, CaseDetail, CaseEvidence, CaseEvidencePage,
    CaseLocation, CasePage, CaseSummary, CaseTimelineItem, CaseTimelinePage)
from app.schemas.dispatch import OfferView, ResponderLocation
from app.services.location import distance_metres, estimate_eta_seconds, MIN_MOVING_SPEED_MPS

ACTIVE_ASSIGNMENTS = ("OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE")
TRANSITIONS = {
    "acknowledge": ({"OPEN"}, "ACKNOWLEDGED"),
    "resolve": ({"OPEN", "ACKNOWLEDGED"}, "RESOLVED"),
    "dismiss": ({"OPEN", "ACKNOWLEDGED", "UNCLASSIFIED"}, "DISMISSED"),
    "reopen": ({"RESOLVED", "DISMISSED", "CLOSED"}, "OPEN"),
}


def normalized_status(status: str) -> str:
    return "OPEN" if status == "RECEIVED" else status


def assignment_filter(source: str, source_id: int):
    return (Assignment.security_event_id == source_id if source == "camera"
            else Assignment.reporter_incident_id == source_id)


class CaseService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, property_id: int, source: str, source_id: int, *, lock=False):
        model = SecurityEvent if source == "camera" else ReporterIncident
        statement = select(model).where(model.id == source_id, model.property_id == property_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        item = await self.session.scalar(statement)
        if item is None:
            raise ApplicationError("CASE_NOT_FOUND", "The incident does not exist in this property.", 404)
        return item

    def summary(self, item, source: str, assignment=None) -> CaseSummary:
        camera = source == "camera"
        return CaseSummary(
            key=f"{source}:{item.id}", source=source, source_id=item.id, property_id=item.property_id,
            incident_type=item.event_type if camera else item.incident_type,
            status=normalized_status(item.status), source_status=item.status,
            severity=item.severity if camera else None,
            occurred_at=item.timestamp if camera else item.created_at,
            description=item.reason if camera else item.description,
            camera_id=item.camera_id if camera else None,
            latest_assignment=OfferView.model_validate(assignment) if assignment else None,
        )

    async def detail(self, property_id: int, source: str, source_id: int) -> CaseDetail:
        item = await self.get(property_id, source, source_id)
        assignment = await self.session.scalar(select(Assignment).where(
            Assignment.property_id == property_id, assignment_filter(source, source_id))
            .order_by(Assignment.offered_at.desc(), Assignment.id.desc()).limit(1))
        summary = self.summary(item, source, assignment)
        destination_latitude = getattr(item, "latitude", None)
        destination_longitude = getattr(item, "longitude", None)
        if assignment and assignment.status in ACTIVE_ASSIGNMENTS:
            availability = await self.session.get(MarshalAvailability, assignment.marshal_profile_id)
            if availability and availability.location_updated_at and availability.latitude is not None and availability.longitude is not None:
                eta_fields = {}
                if destination_latitude is not None and destination_longitude is not None:
                    distance = distance_metres(
                        availability.latitude, availability.longitude,
                        destination_latitude, destination_longitude,
                    )
                    eta_fields = {
                        "distance_m": round(distance, 1),
                        "eta_seconds": estimate_eta_seconds(distance, availability.location_speed_mps),
                        "eta_source": "gps_speed" if availability.location_speed_mps is not None and availability.location_speed_mps >= MIN_MOVING_SPEED_MPS else "urban_fallback",
                    }
                summary.latest_assignment.responder_location = ResponderLocation(
                    latitude=availability.latitude,
                    longitude=availability.longitude,
                    accuracy_m=availability.location_accuracy_m,
                    heading=availability.location_heading,
                    speed_mps=availability.location_speed_mps,
                    updated_at=availability.location_updated_at,
                    **eta_fields,
                )
        if source == "camera":
            camera = await self.session.get(Camera, item.camera_id)
            property = await self.session.get(Property, property_id)
            location = CaseLocation(address=camera.location or property.address)
        else:
            location = CaseLocation(address=item.address, latitude=item.latitude,
                longitude=item.longitude, accuracy_metres=item.location_accuracy)
        active = await self.session.scalar(select(Assignment.id).where(
            Assignment.property_id == property_id, assignment_filter(source, source_id),
            Assignment.status.in_(ACTIVE_ASSIGNMENTS)).limit(1))
        actions = [name for name, (allowed, _) in TRANSITIONS.items() if summary.status in allowed]
        if active is not None:
            actions = [name for name in actions if name not in {"resolve", "dismiss"}]
        return CaseDetail(**summary.model_dump(), location=location,
            confidence=item.confidence if source == "camera" else None,
            zone=item.zone if source == "camera" else None, allowed_actions=actions,
            dispatch_allowed=summary.status in {"OPEN", "ACKNOWLEDGED"} and active is None)

    @staticmethod
    def feed(property_id):
        cameras = select(literal("camera").label("source"), SecurityEvent.id.label("source_id"),
            SecurityEvent.property_id, SecurityEvent.event_type.label("incident_type"),
            SecurityEvent.status, SecurityEvent.status.label("source_status"), SecurityEvent.severity,
            SecurityEvent.timestamp.label("occurred_at"), SecurityEvent.reason.label("description"),
            SecurityEvent.camera_id).where(SecurityEvent.property_id == property_id)
        reports = select(literal("reporter").label("source"), ReporterIncident.id.label("source_id"),
            ReporterIncident.property_id, ReporterIncident.incident_type,
            case((ReporterIncident.status == "RECEIVED", "OPEN"), else_=ReporterIncident.status).label("status"),
            ReporterIncident.status.label("source_status"), cast(null(), String).label("severity"),
            ReporterIncident.created_at.label("occurred_at"), ReporterIncident.description,
            cast(null(), Integer).label("camera_id")).where(ReporterIncident.property_id == property_id)
        return union_all(cameras, reports).subquery("case_feed")

    async def list(self, property_id, *, source=None, status=None, severity=None, page=1, page_size=50):
        feed = self.feed(property_id)
        statement = select(feed)
        for column, value in ((feed.c.source, source), (feed.c.status, status), (feed.c.severity, severity)):
            if value is not None:
                statement = statement.where(column == value)
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (await self.session.execute(statement.order_by(feed.c.occurred_at.desc(), feed.c.source,
            feed.c.source_id.desc()).offset((page - 1) * page_size).limit(page_size))).mappings().all()
        camera_ids = [row["source_id"] for row in rows if row["source"] == "camera"]
        report_ids = [row["source_id"] for row in rows if row["source"] == "reporter"]
        ranked = select(Assignment.id.label("assignment_id"), func.row_number().over(
            partition_by=(Assignment.security_event_id, Assignment.reporter_incident_id),
            order_by=(Assignment.offered_at.desc(), Assignment.id.desc())).label("rank")).where(
                Assignment.property_id == property_id,
                or_(Assignment.security_event_id.in_(camera_ids), Assignment.reporter_incident_id.in_(report_ids))).subquery()
        assignments = (await self.session.scalars(select(Assignment).join(ranked,
            Assignment.id == ranked.c.assignment_id).where(ranked.c.rank == 1))).all() if rows else []
        latest = {}
        for item in assignments:
            key = ("camera", item.security_event_id) if item.security_event_id is not None else ("reporter", item.reporter_incident_id)
            latest.setdefault(key, item)
        items = [CaseSummary(**row, key=f"{row['source']}:{row['source_id']}",
            latest_assignment=OfferView.model_validate(latest[(row["source"], row["source_id"])])
            if (row["source"], row["source_id"]) in latest else None) for row in rows]
        return CasePage(items=items, total=total, page=page, page_size=page_size)

    async def overview(self, property_id):
        feed = self.feed(property_id)
        rows = (await self.session.execute(select(feed.c.source, feed.c.status, func.count()).group_by(feed.c.source, feed.c.status))).all()
        return {"total": sum(count for _, _, count in rows),
                "active": sum(count for _, status, count in rows if status in {"OPEN", "ACKNOWLEDGED"}),
                "by_source": {source: sum(count for kind, _, count in rows if kind == source) for source in ("camera", "reporter")}}

    async def command(self, property_id: int, source: str, source_id: int, body: CaseCommand, actor: str):
        item = await self.get(property_id, source, source_id, lock=True)
        receipt = await self.session.scalar(select(AuditRecord).where(
            AuditRecord.property_id == property_id, AuditRecord.resource_type == f"{source}_incident",
            AuditRecord.resource_id == str(source_id), AuditRecord.action == "CASE_STATUS_CHANGED",
            AuditRecord.correlation_id == body.correlation_id).limit(1))
        if receipt is not None:
            if (receipt.actor_subject, receipt.details.get("command"), receipt.details.get("reason"),
                receipt.details.get("expected_status")) != (actor, body.command, body.reason, body.expected_status):
                raise ApplicationError("IDEMPOTENCY_CONFLICT", "This request ID was already used for a different action.", 409)
            return await self.detail(property_id, source, source_id)
        old_status = item.status
        status = normalized_status(old_status)
        allowed, new_status = TRANSITIONS[body.command]
        if status != body.expected_status or status not in allowed:
            raise ApplicationError("CASE_CONFLICT", "The incident has changed. Reload it before applying this action.", 409)
        if body.command in {"resolve", "dismiss"}:
            active = await self.session.scalar(select(Assignment.id).where(Assignment.property_id == property_id,
                assignment_filter(source, source_id), Assignment.status.in_(ACTIVE_ASSIGNMENTS)).limit(1))
            if active is not None:
                raise ApplicationError("ACTIVE_ASSIGNMENT_EXISTS", "Cancel the active assignment before closing this incident.", 409)
        stored_status = "RECEIVED" if source == "reporter" and new_status == "OPEN" else new_status
        model = SecurityEvent if source == "camera" else ReporterIncident
        result = await self.session.execute(update(model).where(model.id == source_id,
            model.property_id == property_id, model.status == old_status).values(status=stored_status))
        if result.rowcount != 1:
            raise ApplicationError("CASE_CONFLICT", "The incident has changed. Reload it before applying this action.", 409)
        now = datetime.now(timezone.utc)
        if source == "camera":
            self.session.add(IncidentStatusHistory(security_event_id=source_id, previous_status=old_status,
                new_status=stored_status, actor_subject=actor, reason=body.reason,
                correlation_id=body.correlation_id, occurred_at=now))
        else:
            self.session.add(ReporterIncidentTimeline(incident_id=source_id, status=stored_status,
                actor_subject=actor, message=body.reason, occurred_at=now))
        self.session.add(AuditRecord(property_id=property_id, actor_subject=actor, action="CASE_STATUS_CHANGED",
            resource_type=f"{source}_incident", resource_id=str(source_id), correlation_id=body.correlation_id,
            details={"previous_status": old_status, "new_status": stored_status, "reason": body.reason,
                     "command": body.command, "expected_status": body.expected_status}))
        self.session.add(NotificationOutbox(property_id=property_id,
            security_event_id=source_id if source == "camera" else None,
            kind="CASE_STATUS_CHANGED", destination=f"property:{property_id}:dispatchers",
            dedupe_key=f"case:{uuid4().hex}", payload={"source": source, "source_id": source_id,
                "status": new_status, "reporter_incident_id": source_id if source == "reporter" else None}))
        await self.session.commit()
        return await self.detail(property_id, source, source_id)

    async def timeline(self, property_id, source, source_id, page, page_size):
        await self.get(property_id, source, source_id)
        if source == "camera":
            history = select(literal("incident_status").label("kind"), IncidentStatusHistory.id,
                IncidentStatusHistory.previous_status, IncidentStatusHistory.new_status.label("status"),
                IncidentStatusHistory.actor_subject, IncidentStatusHistory.reason,
                IncidentStatusHistory.occurred_at, cast(null(), Integer).label("assignment_id"))
            history = history.where(IncidentStatusHistory.security_event_id == source_id)
        else:
            history = select(literal("incident_status").label("kind"), ReporterIncidentTimeline.id,
                cast(null(), String).label("previous_status"), ReporterIncidentTimeline.status,
                ReporterIncidentTimeline.actor_subject, ReporterIncidentTimeline.message.label("reason"),
                ReporterIncidentTimeline.occurred_at, cast(null(), Integer).label("assignment_id"))
            history = history.where(ReporterIncidentTimeline.incident_id == source_id)
        offers = select(literal("assignment_status").label("kind"), AssignmentEvent.id,
            AssignmentEvent.previous_status, AssignmentEvent.new_status.label("status"),
            AssignmentEvent.actor_subject, AssignmentEvent.reason, AssignmentEvent.occurred_at,
            AssignmentEvent.assignment_id).join(Assignment).where(Assignment.property_id == property_id,
                assignment_filter(source, source_id))
        feed = union_all(history, offers).subquery("case_timeline")
        total = await self.session.scalar(select(func.count()).select_from(feed))
        rows = (await self.session.execute(select(feed).order_by(feed.c.occurred_at, feed.c.kind, feed.c.id)
            .offset((page - 1) * page_size).limit(page_size))).mappings().all()
        return CaseTimelinePage(items=[CaseTimelineItem(**row, key=f"{row['kind']}:{row['id']}") for row in rows],
                                total=total, page=page, page_size=page_size)

    async def evidence(self, property_id, source, source_id, page, page_size):
        await self.get(property_id, source, source_id)
        model = Evidence if source == "camera" else ReporterIncidentEvidence
        condition = model.event_id == source_id if source == "camera" else model.incident_id == source_id
        total = await self.session.scalar(select(func.count()).select_from(model).where(condition))
        rows = (await self.session.scalars(select(model).where(condition).order_by(model.id)
            .offset((page - 1) * page_size).limit(page_size))).all()
        return CaseEvidencePage(items=[CaseEvidence(id=item.id, kind=item.type if source == "camera" else "ATTACHMENT",
            media_type=None if source == "camera" else item.media_type,
            original_filename=None if source == "camera" else item.original_filename,
            byte_size=None if source == "camera" else item.byte_size,
            occurred_at=item.timestamp if source == "camera" else item.created_at) for item in rows],
            total=total, page=page, page_size=page_size)

    async def evidence_record(self, property_id, source, source_id, evidence_id):
        item = await self.get(property_id, source, source_id)
        model = Evidence if source == "camera" else ReporterIncidentEvidence
        condition = model.event_id == source_id if source == "camera" else model.incident_id == source_id
        evidence = await self.session.scalar(select(model).where(condition, model.id == evidence_id))
        if evidence is None:
            raise ApplicationError("EVIDENCE_NOT_FOUND", "The requested evidence does not exist for this incident.", 404)
        return item, evidence
