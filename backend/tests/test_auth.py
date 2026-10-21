"""Phase 8 authentication and authorization tests."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from pydantic import ValidationError

from app.core.auth import authenticate_token
from app.core.config import Settings
from app.core.exceptions import ApplicationError

SECRET = "test-only-secret-with-at-least-32-bytes"


def make_token(**claims: object) -> str:
    values = {
        "sub": "operator-1",
        "scope": "read",
        "property_ids": [1],
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    values.update(claims)
    return jwt.encode(values, SECRET, algorithm="HS256")


def auth_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "auth_enabled": True,
        "jwt_secret": SECRET,
        "jwt_algorithm": "HS256",
    }
    values.update(overrides)
    return Settings(**values)


def test_valid_token_returns_principal() -> None:
    principal = authenticate_token(make_token(), auth_settings())

    assert principal.subject == "operator-1"
    assert "read" in principal.scopes
    assert principal.can_access_property(1)
    assert not principal.can_access_property(2)


@pytest.mark.parametrize("token", [None, "not-a-token"])
def test_missing_or_invalid_token_is_rejected(token: str | None) -> None:
    with pytest.raises(ApplicationError) as error:
        authenticate_token(token, auth_settings())

    assert error.value.code == "UNAUTHORIZED"


def test_expired_token_is_rejected() -> None:
    token = make_token(exp=datetime.now(timezone.utc) - timedelta(minutes=1))

    with pytest.raises(ApplicationError) as error:
        authenticate_token(token, auth_settings())

    assert error.value.code == "UNAUTHORIZED"


def test_wrong_scope_is_preserved_for_authorization_layer() -> None:
    principal = authenticate_token(make_token(scope="admin"), auth_settings())

    assert "read" not in principal.scopes


@pytest.mark.parametrize("property_ids", [[0], [True], ["1"], "1"])
def test_invalid_property_access_claim_is_rejected(property_ids: object) -> None:
    with pytest.raises(ApplicationError) as error:
        authenticate_token(make_token(property_ids=property_ids), auth_settings())

    assert error.value.code == "UNAUTHORIZED"


def test_production_auth_requires_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", auth_enabled=True, jwt_secret="")


def test_production_requires_authentication_and_database() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", auth_enabled=False)
    with pytest.raises(ValidationError):
        Settings(app_env="production", auth_enabled=True, jwt_secret=SECRET, database_url="")


def test_cors_origins_are_normalized_and_production_rejects_wildcard() -> None:
    settings = Settings(cors_origins="http://localhost:5173/, https://example.test ")
    assert settings.parsed_cors_origins == ["http://localhost:5173", "https://example.test"]
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            auth_enabled=True,
            jwt_secret=SECRET,
            database_url="postgresql://placeholder/db",
            cors_origins="*",
        )
