"""Render Compose without starting containers or loading deployment secrets."""
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess

from cryptography.fernet import Fernet
import pytest

from app.core.config import Settings


@pytest.fixture
def compose_command():
    if os.getenv('COMPOSE_BINARY'):
        return [os.environ['COMPOSE_BINARY']]
    if shutil.which('docker'):
        return ['docker', 'compose']
    if shutil.which('docker-compose'):
        return ['docker-compose']
    pytest.skip('Requires Compose CLI for configuration rendering; no daemon needed')


def render(command, overrides=None):
    env = {**os.environ, 'POSTGRES_PASSWORD': 'compose-test-only',
        'MQTT_BACKEND_PASSWORD': 'compose-test-only', 'MQTT_FRIGATE_PASSWORD': 'compose-test-only',
        'DATABASE_URL': '', 'DATABASE_URL_UNPOOLED': '', 'NEON_AUTH_BASE_URL': '', 'NEON_AUTH_JWKS_URL': '',
        'AUTH_ENABLED': 'true', 'APP_ENV': 'production', 'JWT_SECRET': 'compose-test-secret-at-least-32-characters',
        'DISPATCH_NOTIFICATION_PROVIDER': 'disabled', 'MARSHAL_IDENTITY_KEY': '', 'EXPO_PUSH_ACCESS_TOKEN': '',
        'ALERT_ROUTING_DESTINATIONS': '', 'TWILIO_ACCOUNT_SID': '', 'TWILIO_AUTH_TOKEN': '',
        'TWILIO_SMS_FROM': '', 'TWILIO_VOICE_FROM': '', 'TWILIO_WHATSAPP_FROM': '',
        'EMERGENCY_POLICE_WEBHOOK_URL': '', 'EMERGENCY_FIRE_WEBHOOK_URL': '',
        'EMERGENCY_AMBULANCE_WEBHOOK_URL': '', 'EMERGENCY_WEBHOOK_SECRET': '',
        'EVIDENCE_STORAGE': 'local', 'CORS_ORIGINS': 'https://dashboard.example.test', **(overrides or {})}
    path = Path(__file__).resolve().parents[1] / 'deployment/docker-compose.yml'
    result = subprocess.run([*command, '--project-name', 'securepulse-config-check',
        '--env-file', os.devnull, '-f', str(path), 'config', '--format', 'json'],
        env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, 'Compose config must render successfully with isolated test settings'
    return json.loads(result.stdout)


def test_default_delivery_stays_disabled_and_identity_files_have_private_persistent_storage(compose_command):
    config = render(compose_command)
    backend = config['services']['backend']
    settings = Settings(_env_file=None, **backend['environment'])
    assert settings.dispatch_notification_provider == 'disabled'
    assert not settings.marshal_identity_key and not settings.marshal_identity_insecure_test_mode
    mount = next(v for v in backend['volumes'] if v['source'] == 'marshal_identities')
    assert mount['type'] == 'volume' and not mount.get('read_only', False)
    assert 'marshal_identities' in config['volumes']
    assert PurePosixPath(settings.marshal_identity_root).is_relative_to(mount['target'])
    assert settings.marshal_identity_root != mount['target']  # application creates a private child
    assert not settings.marshal_identity_root.startswith(settings.evidence_root)
    for name, service in config['services'].items():
        if name != 'backend':
            assert not any(v.get('source') == 'marshal_identities' for v in service.get('volumes', []))


@pytest.mark.parametrize('mode', ['expo', 'routing'])
def test_provider_and_identity_settings_reach_backend_configuration(compose_command, mode):
    values = {'DISPATCH_NOTIFICATION_PROVIDER': mode, 'MARSHAL_IDENTITY_KEY': Fernet.generate_key().decode(),
        'EXPO_PUSH_ACCESS_TOKEN': 'test-expo-access', 'TWILIO_ACCOUNT_SID': 'test-twilio-account',
        'TWILIO_AUTH_TOKEN': 'test-twilio-auth', 'TWILIO_SMS_FROM': '+15550001',
        'TWILIO_VOICE_FROM': '+15550002', 'TWILIO_WHATSAPP_FROM': '+15550003',
        'ALERT_ROUTING_DESTINATIONS': 'sms:+15550010,emergency:police',
        'EMERGENCY_POLICE_WEBHOOK_URL': 'https://police.example.test/alerts',
        'EMERGENCY_FIRE_WEBHOOK_URL': 'https://fire.example.test/alerts',
        'EMERGENCY_AMBULANCE_WEBHOOK_URL': 'https://ambulance.example.test/alerts',
        'EMERGENCY_WEBHOOK_SECRET': 'test-agency-secret'}
    config = render(compose_command, values)
    environment = config['services']['backend']['environment']
    for key, value in values.items():
        assert environment[key] == value
    settings = Settings(_env_file=None, **environment)
    assert settings.dispatch_notification_provider == mode
    assert settings.parsed_alert_routing_destinations == ('sms:+15550010', 'emergency:police')
    Fernet(settings.marshal_identity_key.encode())
