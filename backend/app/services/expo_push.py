"""Opt-in Expo delivery with per-device tickets, receipts and bounded retries.

An accepted ticket is not delivery. SENT means Expo's receipt reports hand-off
to the platform provider; physical receipt/viewing still needs device acceptance.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import re
import logging

import httpx
from sqlalchemy import or_, select

from app.models import (Assignment, MarshalProfile, NotificationAttempt, NotificationOutbox,
    Property, PropertyMembership, ReporterIncident, SecurityEvent, User)
from app.models.operations import NotificationPreference, UserDeviceToken
from app.repositories.dispatch import OutboxRepository

TOKEN = re.compile(r'^(?:ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]+\]$')
logger = logging.getLogger(__name__)


class ExpoPushWorker:
    def __init__(self, factory, access_token='', transport=None):
        self.factory, self.access_token, self.transport = factory, access_token, transport

    async def api(self, action, body):
        headers = {'Accept': 'application/json'}
        if self.access_token:
            headers['Authorization'] = 'Bearer ' + self.access_token
        async with httpx.AsyncClient(timeout=15, transport=self.transport) as client:
            response = await client.post('https://exp.host/--/api/v2/push/' + action, json=body, headers=headers)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or 'data' not in payload:
                raise ValueError('Invalid Expo response')
            return payload['data']

    async def recipients(self, session, row):
        payload = row.payload or {}
        dispatch = row.kind.startswith(('ASSIGNMENT_', 'DISPATCH_'))
        category = 'DISPATCH_UPDATES' if dispatch else 'INCIDENT_UPDATES' if payload.get('reporter_incident_id') else 'SECURITY_ALERTS'
        if row.kind == 'PUSH_SELF_TEST' and payload.get('category') in ('SECURITY_ALERTS', 'INCIDENT_UPDATES', 'DISPATCH_UPDATES'):
            category = payload['category']
        candidates = set()
        destination = row.destination or ''
        if destination.startswith('marshal:'):
            try:
                profile = await session.get(MarshalProfile, int(destination.split(':')[1]))
                if profile and profile.active and profile.property_id == row.property_id:
                    candidates.add(profile.user_id)
            except ValueError:
                pass
        elif destination.startswith('reporter:'):
            try:
                candidates.add(int(destination.split(':')[1]))
            except ValueError:
                pass
        else:
            roles = ('owner', 'dispatcher') if destination.endswith(':dispatchers') else ('owner', 'reporter', 'dispatcher')
            candidates.update((await session.scalars(select(PropertyMembership.user_id).where(
                PropertyMembership.property_id == row.property_id, PropertyMembership.role.in_(roles),
                PropertyMembership.active.is_(True)))).all())
        report_id = payload.get('reporter_incident_id')
        if report_id:
            report = await session.get(ReporterIncident, report_id)
            if report and report.property_id == row.property_id:
                candidates.add(report.reporter_user_id)
        # Every retry rechecks active membership, account, device and explicit opt-in.
        devices = (await session.scalars(select(UserDeviceToken).join(User).join(
            PropertyMembership, PropertyMembership.user_id == User.id).join(Property,
            Property.id == PropertyMembership.property_id).join(NotificationPreference,
            NotificationPreference.user_id == User.id).where(User.id.in_(candidates), User.active.is_(True),
            Property.id == row.property_id, Property.active.is_(True), PropertyMembership.active.is_(True),
            NotificationPreference.category == category, NotificationPreference.enabled.is_(True),
            UserDeviceToken.active.is_(True), UserDeviceToken.provider == 'expo').distinct())).all()
        return devices, category

    async def run_once(self, limit=25):
        async with self.factory() as session, session.begin():
            rows = await OutboxRepository(session).claim_batch('expo-push', datetime.now(timezone.utc), limit,
                exclude_destination_prefixes=('sms:', 'voice:', 'whatsapp:', 'emergency:'))
            ids = [row.id for row in rows]
        for row_id in ids:
            try:
                await self.deliver(row_id)
            except Exception:
                logger.exception('Expo work item failed', extra={'outbox_id': row_id})
        return len(ids)

    async def deliver(self, row_id):
        now = datetime.now(timezone.utc)
        async with self.factory() as session, session.begin():
            row = await session.scalar(select(NotificationOutbox).where(NotificationOutbox.id == row_id).with_for_update())
            if not row or row.status != 'PROCESSING':
                return
            devices, category = await self.recipients(session, row)
            if row.kind == 'INCIDENT_OPENED' and row.security_event_id:
                event = await session.get(SecurityEvent, row.security_event_id)
                if event and (event.event_type == 'DETECTION' or event.severity == 'INFO'):
                    row.status = 'SKIPPED'
                    return
            if not devices:
                row.status = 'SKIPPED'
                return
            previous = await session.scalar(select(NotificationAttempt).where(
                NotificationAttempt.outbox_id == row.id, NotificationAttempt.provider == 'expo')
                .order_by(NotificationAttempt.attempt_number.desc()).limit(1))
            state = deepcopy((previous.response_metadata or {}).get('devices', {})) if previous else {}
            device_map = {str(d.id): d for d in devices}
            state = {key: value for key, value in state.items() if key in device_map}
            for key, device in device_map.items():
                fingerprint = hashlib.sha256(device.push_token.encode()).hexdigest()
                if not TOKEN.fullmatch(device.push_token):
                    device.active = False
                    state[key] = {'status': 'disabled', 'fingerprint': fingerprint}
                elif state.get(key, {}).get('fingerprint') != fingerprint:
                    state[key] = {'status': 'retry', 'fingerprint': fingerprint}
            for value in state.values():
                if value.get('status') == 'ticket' and now.timestamp() - value.get('submitted_at', now.timestamp()) >= 86400:
                    value['status'] = 'permanent'
            tickets = {v['ticket']: key for key, v in state.items() if v.get('status') == 'ticket'}
            try:
                if tickets:
                    receipts = {}
                    ticket_ids = list(tickets)
                    for offset in range(0, len(ticket_ids), 1000):
                        batch = await self.api('getReceipts', {'ids': ticket_ids[offset:offset + 1000]})
                        if not isinstance(batch, dict):
                            raise ValueError('Invalid receipt response')
                        receipts.update(batch)
                    for ticket, key in tickets.items():
                        receipt = receipts.get(ticket)
                        if not receipt:
                            age = now.timestamp() - state[key].get('submitted_at', now.timestamp())
                            if age >= 86400:
                                state[key]['status'] = 'permanent'
                            continue
                        if receipt.get('status') == 'ok':
                            state[key]['status'] = 'sent'
                        else:
                            self.failed_device(device_map[key], state[key], receipt)
                pending = [key for key, value in state.items() if value['status'] == 'retry']
                attempts = previous.attempt_number if previous else 0
                if pending and attempts < 5:
                    payload = row.payload or {}
                    report_id = payload.get('reporter_incident_id')
                    event_id = row.security_event_id or payload.get('incident_id')
                    kind = 'reporter_incident' if report_id else 'camera_event' if event_id else 'home'
                    messages = [{'to': device_map[key].push_token, 'title': 'SecurePulse update',
                        'body': 'A security or response record has an update. Open the app to review it.',
                        'sound': 'default', 'channelId': 'security-updates',
                        'data': {'kind': kind, 'id': report_id or event_id, 'property_id': row.property_id,
                                 'user_id': device_map[key].user_id, 'category': category}} for key in pending]
                    for offset in range(0, len(messages), 100):
                        batch = messages[offset:offset + 100]
                        results = await self.api('send', batch)
                        if isinstance(results, dict) and len(batch) == 1:
                            results = [results]
                        if not isinstance(results, list) or len(results) != len(batch) or not all(isinstance(item, dict) for item in results):
                            raise ValueError('Invalid ticket response')
                        for key, result in zip(pending[offset:offset + 100], results):
                            if result.get('status') == 'ok' and isinstance(result.get('id'), str):
                                state[key].update(status='ticket', ticket=result['id'], submitted_at=now.timestamp())
                            else:
                                self.failed_device(device_map[key], state[key], result)
                    receipt = NotificationAttempt(outbox_id=row.id, attempt_number=attempts + 1,
                        provider='expo', status='ACCEPTED', attempted_at=now, response_metadata={'devices': state})
                    session.add(receipt)
                    previous = receipt
                elif pending:
                    for key in pending:
                        state[key]['status'] = 'permanent'
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                attempts = previous.attempt_number if previous else 0
                if attempts >= 5:
                    for value in state.values():
                        if value['status'] == 'retry':
                            value['status'] = 'permanent'
                else:
                    previous = NotificationAttempt(outbox_id=row.id, attempt_number=attempts + 1,
                        provider='expo', status='FAILED', error_code='EXPO_UNAVAILABLE', attempted_at=now,
                        response_metadata={'devices': state})
                    session.add(previous)
            if previous:
                previous.response_metadata = {'devices': state}
            statuses = {value['status'] for value in state.values()}
            if statuses & {'ticket', 'retry'}:
                row.status = 'PENDING'
                row.available_at = now + timedelta(seconds=60 if 'ticket' in statuses else min(5 * 2 ** (previous.attempt_number if previous else 0), 300))
            elif 'permanent' in statuses:
                row.status = 'EXHAUSTED'
                if previous:
                    previous.status = 'FAILED'
                    previous.error_code = 'EXPO_DELIVERY_FAILED'
            elif 'sent' in statuses:
                row.status, row.sent_at = 'SENT', now
                if previous:
                    previous.status = 'DELIVERED'
            else:
                row.status = 'SKIPPED'

    @staticmethod
    def failed_device(device, state, result):
        code = (result.get('details') or {}).get('error')
        state['error_code'] = code if code in ('DeviceNotRegistered', 'MessageTooBig', 'InvalidCredentials', 'MismatchSenderId', 'MessageRateExceeded') else 'EXPO_RETRYABLE_ERROR'
        if code == 'DeviceNotRegistered':
            device.active = False
            state['status'] = 'disabled'
        elif code in ('MessageTooBig', 'InvalidCredentials', 'MismatchSenderId'):
            state['status'] = 'permanent'
        else:
            state['status'] = 'retry'
