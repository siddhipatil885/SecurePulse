"""Explicit external alert adapters.

Destinations are intentionally explicit (``sms:+...``, ``voice:+...``,
``whatsapp:+...`` and ``emergency:police|fire|ambulance``). No provider is
contacted unless routing is enabled and its credentials or endpoint is set.
"""

from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Any

import httpx

from app.services.dispatch_workers import DeliveryResult


@dataclass(frozen=True)
class TwilioConfig:
    account_sid: str
    auth_token: str
    sms_from: str = ""
    voice_from: str = ""
    whatsapp_from: str = ""


class TwilioAlertProvider:
    name = "twilio"

    def __init__(self, config: TwilioConfig, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self.transport = transport

    async def deliver(self, destination: str, event_type: str, payload: dict[str, Any],
                      idempotency_key: str) -> DeliveryResult:
        channel, recipient = destination.split(":", 1) if ":" in destination else ("", "")
        sender = {
            "sms": self.config.sms_from,
            "voice": self.config.voice_from,
            "whatsapp": self.config.whatsapp_from,
        }.get(channel, "")
        if channel not in {"sms", "voice", "whatsapp"} or not recipient or not sender:
            return DeliveryResult(False, error="invalid_or_unconfigured_twilio_destination")
        body = self._message(event_type, payload)
        data = {"To": self._address(channel, recipient), "From": self._address(channel, sender)}
        if channel == "voice":
            data["Twiml"] = f"<Response><Say>{body}</Say></Response>"
        else:
            data["Body"] = body
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.config.account_sid}/Messages.json" if channel != "voice" else (
            f"https://api.twilio.com/2010-04-01/Accounts/{self.config.account_sid}/Calls.json"
        )
        auth = (self.config.account_sid, self.config.auth_token)
        async with httpx.AsyncClient(timeout=15, transport=self.transport) as client:
            response = await client.post(url, data=data, auth=auth)
        if response.status_code >= 400:
            return DeliveryResult(False, error=f"twilio_http_{response.status_code}")
        result = response.json()
        return DeliveryResult(True, provider_message_id=result.get("sid"), metadata={"channel": channel})

    @staticmethod
    def _address(channel: str, value: str) -> str:
        return value if channel != "whatsapp" or value.startswith("whatsapp:") else f"whatsapp:{value}"

    @staticmethod
    def _message(event_type: str, payload: dict[str, Any]) -> str:
        severity = str(payload.get("severity", "unknown")).upper()
        incident_id = payload.get("incident_id") or payload.get("security_event_id", "unknown")
        return f"SecurePulse {severity} alert. Incident {incident_id}. Event: {event_type}."


class EmergencyWebhookProvider:
    name = "emergency-webhook"

    def __init__(self, endpoints: dict[str, str], secret: str = "",
                 transport: httpx.AsyncBaseTransport | None = None):
        self.endpoints = endpoints
        self.secret = secret.encode()
        self.transport = transport

    async def deliver(self, destination: str, event_type: str, payload: dict[str, Any],
                      idempotency_key: str) -> DeliveryResult:
        agency = destination.removeprefix("emergency:")
        url = self.endpoints.get(agency, "")
        if not url:
            return DeliveryResult(False, error=f"unconfigured_emergency_{agency}")
        body = {"event_type": event_type, "idempotency_key": idempotency_key, "incident": payload}
        encoded = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        headers = {"Content-Type": "application/json", "Idempotency-Key": idempotency_key}
        if self.secret:
            headers["X-SecurePulse-Signature"] = hmac.new(self.secret, encoded, hashlib.sha256).hexdigest()
        async with httpx.AsyncClient(timeout=15, transport=self.transport) as client:
            response = await client.post(url, content=encoded, headers=headers)
        if response.status_code >= 400:
            return DeliveryResult(False, error=f"emergency_webhook_http_{response.status_code}")
        return DeliveryResult(True, provider_message_id=response.headers.get("x-request-id"),
                             metadata={"agency": agency})


class AlertRoutingProvider:
    """Route explicit destinations to Twilio or an emergency agency webhook."""

    name = "external-alert-routing"

    def __init__(self, twilio: TwilioAlertProvider | None,
                 emergency: EmergencyWebhookProvider | None):
        self.twilio = twilio
        self.emergency = emergency

    async def deliver(self, destination: str, event_type: str, payload: dict[str, Any],
                      idempotency_key: str) -> DeliveryResult:
        if destination.startswith(("sms:", "voice:", "whatsapp:")):
            if not self.twilio:
                return DeliveryResult(False, error="twilio_not_configured")
            return await self.twilio.deliver(destination, event_type, payload, idempotency_key)
        if destination.startswith("emergency:"):
            if not self.emergency:
                return DeliveryResult(False, error="emergency_webhook_not_configured")
            return await self.emergency.deliver(destination, event_type, payload, idempotency_key)
        return DeliveryResult(False, error="unsupported_external_destination")
