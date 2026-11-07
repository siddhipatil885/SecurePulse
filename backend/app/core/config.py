"""Typed application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    app_name: str = Field(default="EDI-SecurePulse", validation_alias="APP_NAME")
    app_env: Literal["development", "production"] = Field(
        default="development", validation_alias="APP_ENV"
    )
    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    port: int = Field(default=8000, ge=1, le=65535, validation_alias="PORT")
    cors_origins: str = Field(
        default="http://localhost:5500,http://127.0.0.1:5500,http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="CORS_ORIGINS",
    )
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    database_url_unpooled: str = Field(default="", validation_alias="DATABASE_URL_UNPOOLED")
    database_storage_budget_bytes: int = Field(default=1_000_000_000, ge=1_000_000, validation_alias="DATABASE_STORAGE_BUDGET_BYTES")
    neon_auth_base_url: str = Field(default="", validation_alias="NEON_AUTH_BASE_URL")
    neon_auth_jwks_url: str = Field(default="", validation_alias="NEON_AUTH_JWKS_URL")
    evidence_storage: Literal["local", "s3"] = Field(default="local", validation_alias="EVIDENCE_STORAGE")
    evidence_bucket: str = Field(default="assets", validation_alias="EVIDENCE_BUCKET")
    aws_access_key_id: str = Field(default="", validation_alias="AWS_ACCESS_KEY_ID", repr=False)
    aws_secret_access_key: str = Field(default="", validation_alias="AWS_SECRET_ACCESS_KEY", repr=False)
    aws_endpoint_url_s3: str = Field(default="", validation_alias="AWS_ENDPOINT_URL_S3")
    aws_region: str = Field(default="", validation_alias="AWS_REGION")
    frigate_url: str = Field(default="http://localhost:5000", validation_alias="FRIGATE_URL")
    go2rtc_url: str = Field(default="http://localhost:1984", validation_alias="GO2RTC_URL")
    frigate_username: str | None = Field(default=None, validation_alias="FRIGATE_USERNAME")
    frigate_password: str | None = Field(default=None, validation_alias="FRIGATE_PASSWORD")
    frigate_verify_ssl: bool = Field(default=True, validation_alias="FRIGATE_VERIFY_SSL")
    security_engine_url: str = Field(
        default="http://localhost:8100", validation_alias="SECURITY_ENGINE_URL"
    )
    security_engine_decision_path: str = Field(
        default="/decide", validation_alias="SECURITY_ENGINE_DECISION_PATH"
    )
    security_engine_timeout_seconds: float = Field(
        default=5.0, gt=0, validation_alias="SECURITY_ENGINE_TIMEOUT_SECONDS"
    )
    security_engine_failure_mode: Literal["STORE_UNCLASSIFIED", "REJECT"] = Field(
        default="STORE_UNCLASSIFIED", validation_alias="SECURITY_ENGINE_FAILURE_MODE"
    )
    security_engine_supports_tracking: bool = Field(
        default=False, validation_alias="SECURITY_ENGINE_SUPPORTS_TRACKING"
    )
    use_local_security_engine: bool = Field(
        default=False, validation_alias="USE_LOCAL_SECURITY_ENGINE"
    )
    auth_enabled: bool = Field(default=False, validation_alias="AUTH_ENABLED")
    dashboard_registration_enabled: bool = Field(default=True, validation_alias="DASHBOARD_REGISTRATION_ENABLED")
    dispatch_notification_provider: Literal["disabled", "recording-fake", "expo", "routing"] = Field(
        default="disabled", validation_alias="DISPATCH_NOTIFICATION_PROVIDER")
    expo_push_access_token: str = Field(default='', validation_alias='EXPO_PUSH_ACCESS_TOKEN', repr=False)
    twilio_account_sid: str = Field(default="", validation_alias="TWILIO_ACCOUNT_SID", repr=False)
    twilio_auth_token: str = Field(default="", validation_alias="TWILIO_AUTH_TOKEN", repr=False)
    twilio_sms_from: str = Field(default="", validation_alias="TWILIO_SMS_FROM")
    twilio_voice_from: str = Field(default="", validation_alias="TWILIO_VOICE_FROM")
    twilio_whatsapp_from: str = Field(default="", validation_alias="TWILIO_WHATSAPP_FROM")
    emergency_police_webhook_url: str = Field(default="", validation_alias="EMERGENCY_POLICE_WEBHOOK_URL")
    emergency_fire_webhook_url: str = Field(default="", validation_alias="EMERGENCY_FIRE_WEBHOOK_URL")
    emergency_ambulance_webhook_url: str = Field(default="", validation_alias="EMERGENCY_AMBULANCE_WEBHOOK_URL")
    emergency_webhook_secret: str = Field(default="", validation_alias="EMERGENCY_WEBHOOK_SECRET", repr=False)
    alert_routing_destinations: str = Field(default="", validation_alias="ALERT_ROUTING_DESTINATIONS")
    evidence_root: str = Field(default="", validation_alias="EVIDENCE_ROOT")
    marshal_identity_key: str = Field(default='', validation_alias='MARSHAL_IDENTITY_KEY', repr=False)
    marshal_identity_root: str = Field(default='', validation_alias='MARSHAL_IDENTITY_ROOT')
    marshal_identity_insecure_test_mode: bool = Field(default=False, validation_alias='MARSHAL_IDENTITY_INSECURE_TEST_MODE')
    reporter_evidence_max_bytes: int = Field(default=10_000_000, ge=1_000_000, validation_alias="REPORTER_EVIDENCE_MAX_BYTES")
    reporter_evidence_max_files: int = Field(default=5, ge=1, le=50, validation_alias="REPORTER_EVIDENCE_MAX_FILES")
    reporter_evidence_max_incident_bytes: int = Field(default=50_000_000, ge=1_000_000, validation_alias="REPORTER_EVIDENCE_MAX_INCIDENT_BYTES")
    reporter_evidence_max_property_bytes: int = Field(default=1_000_000_000, ge=1_000_000, validation_alias="REPORTER_EVIDENCE_MAX_PROPERTY_BYTES")
    reporter_evidence_min_free_bytes: int = Field(default=1_000_000_000, ge=0, validation_alias="REPORTER_EVIDENCE_MIN_FREE_BYTES")
    mutation_rate_limit_per_minute: int = Field(
        default=30, ge=1, validation_alias="MUTATION_RATE_LIMIT_PER_MINUTE"
    )
    jwt_secret: str = Field(default="", validation_alias="JWT_SECRET")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = Field(
        default="HS256", validation_alias="JWT_ALGORITHM"
    )
    jwt_issuer: str | None = Field(default=None, validation_alias="JWT_ISSUER")
    mqtt_host: str = Field(default="localhost", validation_alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, ge=1, le=65535, validation_alias="MQTT_PORT")
    mqtt_username: str | None = Field(default=None, validation_alias="MQTT_USERNAME")
    mqtt_password: str | None = Field(default=None, validation_alias="MQTT_PASSWORD")
    mqtt_event_queue_size: int = Field(
        default=256, ge=1, le=10000, validation_alias="MQTT_EVENT_QUEUE_SIZE"
    )
    frigate_mqtt_topic: str = Field(
        default="frigate/events", validation_alias="FRIGATE_MQTT_TOPIC"
    )
    mqtt_client_id: str = Field(
        default="securepulse-backend", validation_alias="MQTT_CLIENT_ID"
    )
    mqtt_reconnect_min_delay: int = Field(
        default=1, ge=1, validation_alias="MQTT_RECONNECT_MIN_DELAY"
    )
    mqtt_reconnect_max_delay: int = Field(
        default=30, ge=1, validation_alias="MQTT_RECONNECT_MAX_DELAY"
    )
    frigate_event_cooldown_seconds: float = Field(
        default=30.0, ge=0, validation_alias="FRIGATE_EVENT_COOLDOWN_SECONDS"
    )
    tracking_lost_track_timeout_seconds: float = Field(
        default=3.0, gt=0, validation_alias="TRACKING_LOST_TRACK_TIMEOUT_SECONDS"
    )
    tracking_minimum_detection_confidence: float = Field(
        default=0.5, ge=0, le=1, validation_alias="TRACKING_MINIMUM_DETECTION_CONFIDENCE"
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    frame_width: int = Field(default=1280, gt=0, validation_alias="FRAME_WIDTH")
    frame_height: int = Field(default=720, gt=0, validation_alias="FRAME_HEIGHT")

    @model_validator(mode="after")
    def validate_authentication_configuration(self) -> "Settings":
        from urllib.parse import urlsplit
        for endpoint in (self.neon_auth_base_url, self.aws_endpoint_url_s3):
            if endpoint:
                parsed = urlsplit(endpoint)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise ValueError("Neon service endpoints must be HTTPS without credentials, query or fragment")
        if self.evidence_storage == "s3" and not all((self.evidence_bucket, self.aws_access_key_id,
                self.aws_secret_access_key, self.aws_endpoint_url_s3, self.aws_region)):
            raise ValueError("S3 evidence requires a bucket and complete AWS_* configuration")
        if bool(self.mqtt_username) != bool(self.mqtt_password):
            raise ValueError("MQTT_USERNAME and MQTT_PASSWORD must be configured together")
        if self.auth_enabled and len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters when authentication is enabled")
        if self.app_env == "production" and not self.auth_enabled:
            raise ValueError("AUTH_ENABLED must be true in production")
        if self.app_env == "production" and self.dispatch_notification_provider == "recording-fake":
            raise ValueError("The recording fake notification provider is development-only")
        if self.dispatch_notification_provider == "routing" and (
            bool(self.twilio_account_sid) != bool(self.twilio_auth_token)
        ):
            raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be configured together")
        if self.app_env == "production" and not self.database_url:
            raise ValueError("DATABASE_URL must be configured in production")
        if not self.parsed_cors_origins:
            raise ValueError("CORS_ORIGINS must contain at least one origin")
        if self.app_env == "production" and "*" in self.parsed_cors_origins:
            raise ValueError("Wildcard CORS origins are not allowed in production")
        return self

    @property
    def parsed_cors_origins(self) -> list[str]:
        """Return normalized comma-separated browser origins."""
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def parsed_alert_routing_destinations(self) -> tuple[str, ...]:
        """Return explicitly configured external destinations."""
        return tuple(
            destination.strip()
            for destination in self.alert_routing_destinations.split(",")
            if destination.strip()
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
