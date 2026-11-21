"""API configuration, read from CARDWISE_* environment variables or .env.

The app refuses to start on a deployed environment (Vercel preview or production) when a
required value is missing, so a misconfigured deploy fails at import instead of per request.
"""

from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["local", "development", "preview", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CARDWISE_",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        validate_by_name=True,
    )

    environment: Environment = Field(
        default="local", validation_alias=AliasChoices("CARDWISE_ENVIRONMENT", "VERCEL_ENV")
    )
    """Vercel sets VERCEL_ENV (development, preview, production) on every deployment."""

    database_url: SecretStr | None = None
    """Supabase transaction pooler URL (port 6543) when deployed."""

    supabase_url: HttpUrl | None = None
    """Project URL. Tokens are checked against its JWKS and its `/auth/v1` issuer."""

    jwt_issuer: str | None = None
    """Override for the expected `iss`. Defaults to `<supabase_url>/auth/v1`."""
    jwt_audience: str = "authenticated"
    jwt_leeway_s: Annotated[int, Field(ge=0, le=120)] = 30
    jwks_cache_ttl_s: Annotated[int, Field(ge=60, le=86_400)] = 600
    jwks_min_refresh_interval_s: Annotated[int, Field(ge=0, le=3_600)] = 30
    """Unknown key IDs trigger a JWKS refetch at most this often, so junk tokens can't flood it."""

    web_origin: Annotated[tuple[str, ...], NoDecode] = ("http://localhost:3000",)
    """Comma-separated browser origins allowed by CORS, e.g. the web production URL."""
    web_origin_regex: str | None = None
    """Optional regex for Vercel preview origins, e.g. ^https://cardwise-web-[a-z0-9-]+\\.vercel\\.app$."""

    messages_per_hour: Annotated[int, Field(ge=1)] = 20
    concurrent_streams: Annotated[int, Field(ge=1)] = 1
    stream_lease_s: Annotated[int, Field(ge=30, le=900)] = 330
    """A stream slot frees itself after this long even if the function died mid-stream."""
    heartbeat_s: Annotated[float, Field(gt=0, le=60)] = 15.0

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("web_origin", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("web_origin")
    @classmethod
    def _check_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        for origin in origins:
            parts = urlsplit(origin)
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or "*" in origin
                or parts.path
                or parts.query
                or parts.fragment
                or parts.username
            ):
                raise ValueError(f"not an origin (scheme://host[:port]): {origin!r}")
        return origins

    @property
    def deployed(self) -> bool:
        return self.environment in ("preview", "production")

    @property
    def issuer(self) -> str | None:
        if self.jwt_issuer:
            return self.jwt_issuer
        if self.supabase_url is None:
            return None
        return f"{str(self.supabase_url).rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str | None:
        if self.supabase_url is None:
            return None
        return f"{str(self.supabase_url).rstrip('/')}/auth/v1/.well-known/jwks.json"

    @model_validator(mode="after")
    def _deployed_needs_everything(self) -> Self:
        if not self.deployed:
            return self
        missing = [
            name
            for name, value in (
                ("CARDWISE_DATABASE_URL", self.database_url),
                ("CARDWISE_SUPABASE_URL", self.supabase_url),
            )
            if value is None
        ]
        if missing:
            raise ValueError(f"{self.environment} deploy is missing {', '.join(missing)}")
        if self.supabase_url is not None and self.supabase_url.scheme != "https":
            raise ValueError("CARDWISE_SUPABASE_URL must use https when deployed")
        return self
