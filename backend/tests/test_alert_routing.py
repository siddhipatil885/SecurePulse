import hashlib
import hmac
import json

import httpx
import pytest

from app.services.alert_routing import (
    EmergencyWebhookProvider,
    TwilioAlertProvider,
    TwilioConfig,
)


@pytest.mark.asyncio
async def test_twilio_routes_sms_voice_and_whatsapp_without_leaking_credentials():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(201, json={"sid": "SM123"})

    provider = TwilioAlertProvider(
        TwilioConfig("AC123", "secret", "+15550001", "+15550002", "+15550003"),
        transport=httpx.MockTransport(handler),
    )
    for destination in ("sms:+15550010", "voice:+15550010", "whatsapp:+15550010"):
        result = await provider.deliver(destination, "INCIDENT_OPENED", {"severity": "HIGH", "incident_id": 7}, "key-7")
        assert result.delivered
    assert len(calls) == 3
    assert calls[0].url.path.endswith("/Messages.json")
    assert calls[1].url.path.endswith("/Calls.json")
    assert "secret" not in str(calls[0].content)


@pytest.mark.asyncio
async def test_emergency_webhook_is_signed_and_idempotent():
    calls = []
    secret = "webhook-secret"

    def handler(request):
        calls.append(request)
        expected = hmac.new(secret.encode(), request.content, hashlib.sha256).hexdigest()
        assert request.headers["X-SecurePulse-Signature"] == expected
        assert json.loads(request.content)["idempotency_key"] == "incident-7"
        return httpx.Response(202, headers={"x-request-id": "agency-1"})

    provider = EmergencyWebhookProvider(
        {"police": "https://agency.example/alerts"}, secret, httpx.MockTransport(handler)
    )
    result = await provider.deliver("emergency:police", "INCIDENT_OPENED", {"incident_id": 7}, "incident-7")
    assert result.delivered and result.provider_message_id == "agency-1"
    assert len(calls) == 1
