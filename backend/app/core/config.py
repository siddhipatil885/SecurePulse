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
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    frigate_url: str = Field(default="http://localhost:5000", validation_alias="FRIGATE_URL")
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
    auth_enabled: bool = Field(default=False, validation_alias="AUTH_ENABLED")
    jwt_secret: str = Field(default="", validation_alias="JWT_SECRET")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = Field(
        default="HS256", validation_alias="JWT_ALGORITHM"
    )
    jwt_issuer: str | None = Field(default=None, validation_alias="JWT_ISSUER")
    mqtt_host: str = Field(default="localhost", validation_alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, ge=1, le=65535, validation_alias="MQTT_PORT")
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
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    @model_validator(mode="after")
    def validate_authentication_configuration(self) -> "Settings":
        if self.auth_enabled and len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters when authentication is enabled")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()